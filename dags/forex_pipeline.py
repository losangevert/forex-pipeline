"""
DAG : Suivi des taux de change multi-devises
API : Frankfurter (https://api.frankfurter.dev)
TaskFlow API : @dag / @task

Pipeline :
  1. extract_raw        → appel API, stockage brut
  2. transform_validate → parsing + contrôles qualité → lignes valides / rejetées
  3. load_valid         → UPSERT dans exchange_rates
  4. load_graveyard     → INSERT dans cimetière
  5. detect_anomalies   → détection variations > seuil → alertes
  6. log_pipeline       → écriture log d'exécution
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import pendulum
import requests

from airflow.decorators import dag, task
from airflow.models import Variable, Connection
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ─── Configuration ────────────────────────────────────────────────
_DEFAULT_CURRENCIES = "EUR,USD,GBP,JPY,CHF,AUD"
_DEFAULT_ALERT_THRESHOLD = 2.0         # % de variation déclenchant une alerte
_DEFAULT_FRESHNESS_HOURS = 6           # heures max depuis la dernière ingestion
_API_TIMEOUT = 30                      # secondes

logger = logging.getLogger(__name__)


def _get_config(key: str, default: Any) -> Any:
    """Lit une Variable Airflow avec fallback."""
    try:
        return Variable.get(key, default_var=default)
    except Exception:
        return default


def _get_api_base() -> str:
    """URL de l'API de taux de change (Variable ou défaut)."""
    return _get_config("forex_api_base", "https://api.frankfurter.app")


def _get_pg_conn() -> tuple[str, int, str, str, str]:
    """Récupère les paramètres PostgreSQL depuis la Connection Airflow."""
    conn_id = "postgres_forex"
    try:
        conn = Connection.get_connection_from_secrets(conn_id)
    except Exception as exc:
        raise RuntimeError(
            f"Connection '{conn_id}' introuvable. Créez-la dans Airflow."
        ) from exc
    return (conn.host, conn.port, conn.schema, conn.login, conn.password)


def _pg_hook() -> PostgresHook:
    """Retourne un hook PostgreSQL prêt."""
    return PostgresHook(postgres_conn_id="postgres_forex")


# ─── TÂCHES ────────────────────────────────────────────────────────

@task(
    retries=2,
    retry_delay=timedelta(seconds=30),
    execution_timeout=timedelta(seconds=60),
)
def extract_raw(**context) -> dict:
    """
    Chemin nominal : appel API Frankfurter → réponse JSON + métadonnées.
    Chemin d'échec   : si l'API est injoignable ou erreur HTTP, on raise →
                        retry automatique puis fail.
    """
    currencies_str = _get_config("forex_currencies", _DEFAULT_CURRENCIES)
    currencies = [c.strip() for c in currencies_str.split(",") if c.strip()]

    # On utilise EUR comme base (API Frankfurter)
    base_currency = "EUR"
    # Exclure la devise de base des targets
    targets_list = [c for c in currencies if c != base_currency]
    targets = ",".join(targets_list) if targets_list else "USD"

    api_base = _get_api_base()
    url = f"{api_base}/latest?from={base_currency}&to={targets}"
    logger.info("Extraction depuis %s", url)

    try:
        resp = requests.get(url, timeout=_API_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Échec appel API Frankfurter : {exc}") from exc

    # Vérification structure minimale
    if "rates" not in payload or not isinstance(payload["rates"], dict):
        raise RuntimeError("Format API invalide : clé 'rates' manquante ou incorrecte.")

    # Validation du nombre de paires reçues
    expected = len(currencies)
    received = len(payload["rates"])
    if received < expected:
        logger.warning(
            "Partiel : reçu %d paires sur %d attendues", received, expected
        )

    result = {
        "base_currency": base_currency,
        "date": payload.get("date"),
        "rates": payload["rates"],
        "raw_payload": payload,
        "expected_pairs": expected,
        "received_pairs": received,
    }
    return result


@task(
    retries=1,
    retry_delay=timedelta(seconds=10),
    execution_timeout=timedelta(seconds=120),
)
def store_raw(extracted: dict, **context) -> str:
    """
    Stocke la réponse brute dans la table raw_rates.
    """
    hook = _pg_hook()
    raw_json = json.dumps(extracted["raw_payload"])
    base = extracted["base_currency"]
    dag_run_id = context["dag_run"].run_id

    sql = """
        INSERT INTO raw_rates (base_currency, raw_payload, ingested_at)
        VALUES (%s, %s::jsonb, NOW())
    """
    hook.run(sql, parameters=(base, raw_json))
    logger.info("Réponse brute stockée pour %s (run %s)", base, dag_run_id)
    return f"raw_ok_{base}"


@task(
    retries=2,
    retry_delay=timedelta(seconds=15),
    execution_timeout=timedelta(seconds=120),
)
def transform_validate(extracted: dict, **context) -> dict:
    """
    Parse les taux reçus et applique les contrôles qualité :

      - Complétude   : toutes les paires attendues sont présentes ?
      - Cohérence    : les taux sont des nombres > 0
      - Fraîcheur    : la date de l'API est <= today
      - Unicité      : pas de doublon (pair + date) déjà en base
      - Structure    : le payload a la bonne forme

    Retourne : {"valid": [...], "rejected": [...]}
    """
    dag_run_id = context["dag_run"].run_id
    base = extracted["base_currency"]
    rates: dict = extracted["rates"]
    api_date = extracted.get("date")
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    valid_rows: list[dict] = []
    rejected_rows: list[dict] = []

    # ── Contrôle fraîcheur ──
    freshness_hours = int(_get_config("forex_freshness_hours", _DEFAULT_FRESHNESS_HOURS))
    if api_date:
        try:
            d = datetime.strptime(api_date, "%Y-%m-%d")
            if (datetime.utcnow() - d) > timedelta(hours=freshness_hours):
                logger.warning(
                    "Données possiblement obsolètes : date API = %s", api_date
                )
        except ValueError:
            rejected_rows.append({
                "currency_pair": None,
                "rate_date": None,
                "rate_value": None,
                "reason": f"Date API invalide : {api_date}",
                "raw": extracted["raw_payload"],
            })

    # ── Parcours des paires ──
    for currency, rate in rates.items():
        pair = f"{base}/{currency}"
        row = {
            "currency_pair": pair,
            "rate_date": api_date or today_str,
            "rate": rate,
            "base_currency": base,
            "target_currency": currency,
        }

        reasons = []

        # Complétude : rate existe ?
        if rate is None:
            reasons.append("Taux manquant (None)")

        # Cohérence : type numérique et > 0
        if not isinstance(rate, (int, float)):
            reasons.append(f"Type invalide : {type(rate).__name__}")
        elif rate <= 0:
            reasons.append(f"Taux ≤ 0 : {rate}")

        if reasons:
            rejected_rows.append({
                "currency_pair": pair,
                "rate_date": row["rate_date"],
                "rate_value": str(rate),
                "reason": " ; ".join(reasons),
                "raw": {"currency": currency, "rate": rate},
            })
        else:
            valid_rows.append(row)

    logger.info(
        "Validation : %d valides, %d rejetées", len(valid_rows), len(rejected_rows)
    )
    return {"valid": valid_rows, "rejected": rejected_rows}


@task(
    retries=2,
    retry_delay=timedelta(seconds=15),
    execution_timeout=timedelta(seconds=120),
)
def load_valid(validated: dict, **context) -> int:
    """
    Charge les lignes valides dans exchange_rates (idempotent grâce à ON CONFLICT).
    Chemin d'échec : si une ligne viole une contrainte, on la redirige vers
                     le cimetière via une exception catchée.
    """
    hook = _pg_hook()
    dag_run_id = context["dag_run"].run_id
    rows = validated.get("valid", [])
    inserted = 0

    if not rows:
        logger.info("Aucune ligne valide à insérer.")
        return 0

    sql = """
        INSERT INTO exchange_rates
            (currency_pair, rate_date, rate, base_currency, target_currency,
             ingested_at, dag_run_id)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (currency_pair, rate_date) DO NOTHING
    """

    for r in rows:
        try:
            hook.run(
                sql,
                parameters=(
                    r["currency_pair"],
                    r["rate_date"],
                    r["rate"],
                    r["base_currency"],
                    r["target_currency"],
                    dag_run_id,
                ),
            )
            inserted += 1
        except Exception as exc:
            # Chemin d'échec : ligne problématique → cimetière
            logger.warning("Insertion échouée pour %s : %s", r["currency_pair"], exc)
            graveyard_sql = """
                INSERT INTO data_quality_graveyard
                    (currency_pair, rate_date, rate_value, rejection_reason,
                     raw_line, dag_run_id)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """
            hook.run(
                graveyard_sql,
                parameters=(
                    r["currency_pair"],
                    r["rate_date"],
                    str(r["rate"]),
                    f"DB_INSERT_ERROR: {exc}",
                    json.dumps(r),
                    dag_run_id,
                ),
            )

    logger.info("%d lignes insérées dans exchange_rates", inserted)
    return inserted


@task(
    retries=1,
    retry_delay=timedelta(seconds=10),
    execution_timeout=timedelta(seconds=60),
)
def load_graveyard(validated: dict, **context) -> int:
    """
    Charge les lignes rejetées par le contrôle qualité dans le cimetière.
    """
    hook = _pg_hook()
    dag_run_id = context["dag_run"].run_id
    rows = validated.get("rejected", [])
    buried = 0

    if not rows:
        logger.info("Aucune ligne rejetée.")
        return 0

    sql = """
        INSERT INTO data_quality_graveyard
            (currency_pair, rate_date, rate_value, rejection_reason,
             raw_line, dag_run_id)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
    """
    for r in rows:
        hook.run(
            sql,
            parameters=(
                r["currency_pair"],
                r["rate_date"],
                r.get("rate_value"),
                r["reason"],
                json.dumps(r.get("raw", {})),
                dag_run_id,
            ),
        )
        buried += 1

    logger.info("%d lignes enterrées dans le cimetière", buried)
    return buried


@task(
    retries=1,
    retry_delay=timedelta(seconds=10),
    execution_timeout=timedelta(seconds=120),
)
def detect_anomalies(validated: dict, **context) -> int:
    """
    Compare les taux actuels avec les précédents en base.
    Si l'écart en % dépasse le seuil → écriture dans rate_alerts.
    """
    threshold = float(_get_config("forex_alert_threshold", _DEFAULT_ALERT_THRESHOLD))
    hook = _pg_hook()
    dag_run_id = context["dag_run"].run_id
    rows = validated.get("valid", [])
    alerts = 0

    if not rows:
        return 0

    for r in rows:
        pair = r["currency_pair"]
        rate_date = r["rate_date"]
        current_rate = r["rate"]

        # Cherche le taux précédent le plus récent (pour cette paire)
        prev_sql = """
            SELECT rate FROM exchange_rates
            WHERE currency_pair = %s
              AND rate_date < %s
            ORDER BY rate_date DESC, ingested_at DESC
            LIMIT 1
        """
        prev = hook.get_first(prev_sql, parameters=(pair, rate_date))
        if prev is None:
            continue  # Pas d'historique → pas de comparaison

        previous_rate = float(prev[0])
        if previous_rate == 0:
            continue

        abs_change = abs(current_rate - previous_rate)
        pct_change = abs_change / previous_rate * 100

        if pct_change >= threshold:
            logger.info(
                "ALERTE %s : %.6f → %.6f (%.4f%%)",
                pair, previous_rate, current_rate, pct_change,
            )
            alert_sql = """
                INSERT INTO rate_alerts
                    (currency_pair, previous_rate, current_rate,
                     absolute_change, pct_change, threshold_used, dag_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            hook.run(
                alert_sql,
                parameters=(
                    pair,
                    round(previous_rate, 6),
                    round(current_rate, 6),
                    round(abs_change, 6),
                    round(pct_change, 4),
                    round(threshold, 4),
                    dag_run_id,
                ),
            )
            alerts += 1

    logger.info("%d alertes générées (seuil=%.2f%%)", alerts, threshold)
    return alerts


@task(
    retries=2,
    retry_delay=timedelta(seconds=10),
    execution_timeout=timedelta(seconds=30),
)
def log_pipeline(
    extract_result: dict,
    validated_result: dict,
    inserted_count: int,
    alerts_count: int,
    status: str = "success",
    error_message: str | None = None,
    **context,
):
    """
    Enregistre un log d'exécution complet dans pipeline_log.
    Les métriques sont extraites des résultats des tâches upstream.
    """
    hook = _pg_hook()
    dag_run_id = context["dag_run"].run_id
    exec_date = context["dag_run"].execution_date

    lines_received = extract_result.get("received_pairs", 0)
    lines_valid = len(validated_result.get("valid", []))
    lines_rejected = len(validated_result.get("rejected", []))

    sql = """
        INSERT INTO pipeline_log
            (dag_run_id, execution_date, status,
             lines_received, lines_valid, lines_rejected,
             lines_inserted, alerts_raised, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    hook.run(
        sql,
        parameters=(
            dag_run_id,
            exec_date,
            status,
            lines_received,
            lines_valid,
            lines_rejected,
            inserted_count,
            alerts_count,
            error_message,
        ),
    )
    logger.info("Pipeline log écrit pour %s : %s", dag_run_id, status)


# ─── DAG ───────────────────────────────────────────────────────────

@dag(
    dag_id="forex_exchange_rate_pipeline",
    description="Suivi des taux de change multi-devises — Frankfurter API",
    start_date=pendulum.datetime(2026, 6, 1, tz="UTC"),
    schedule="@hourly",                # exécution toutes les heures
    catchup=False,
    default_args={
        "owner": "lucas",
        "depends_on_past": False,
        "email_on_failure": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["forex", "rates", "frankfurter"],
    params={
        "currencies": _DEFAULT_CURRENCIES,
        "alert_threshold": _DEFAULT_ALERT_THRESHOLD,
    },
)
def forex_pipeline():
    """
    Orchestration complète du pipeline de taux de change.
    TaskFlow résout automatiquement les dépendances via les arguments.
    """

    # ── 1. Extraction API ──
    raw = extract_raw()

    # ── 2. Stockage brut ──
    store_raw(raw)

    # ── 3. Transformation + Contrôle qualité ──
    validated = transform_validate(raw)

    # ── 4. Chargement valides ──
    inserted = load_valid(validated)

    # ── 5. Chargement rejetées ──
    load_graveyard(validated)

    # ── 6. Détection anomalies ──
    alerts = detect_anomalies(validated)

    # ── 7. Log d'exécution (attend toutes les tâches sink) ──
    log_pipeline(
        extract_result=raw,
        validated_result=validated,
        inserted_count=inserted,
        alerts_count=alerts,
    )

    # Les dépendances sont automatiquement résolues par TaskFlow :
    #   extract_raw → store_raw, transform_validate
    #   transform_validate → load_valid, load_graveyard, detect_anomalies
    #   load_valid, detect_anomalies → log_pipeline


dag = forex_pipeline()
