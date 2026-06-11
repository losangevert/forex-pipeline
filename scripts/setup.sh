#!/bin/bash
# ============================================================
# setup.sh — Bootstrap complet Airflow + PostgreSQL + Metabase
# pour le pipeline de taux de change multi-devises.
#
# Usage : ./scripts/setup.sh
#   ou   docker exec <container> ./scripts/setup.sh
# ============================================================
set -euo pipefail

# ─── Couleurs ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

# ─── Configuration ───
PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-forex}"
PG_USER="${PG_USER:-airflow}"
PG_PASS="${PG_PASS:-airflow_forex_2026}"

AIRFLOW_CONN_ID="${AIRFLOW_CONN_ID:-postgres_forex}"

# ─── 1. Attente PostgreSQL ───
wait_for_pg() {
    info "Attente de PostgreSQL ($PG_HOST:$PG_PORT)..."
    for i in $(seq 1 30); do
        if PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -c "SELECT 1" &>/dev/null; then
            info "PostgreSQL prêt."
            return 0
        fi
        sleep 2
    done
    err "PostgreSQL pas joignable après 60s."
    exit 1
}

# ─── 2. Initialisation DB Airflow ───
init_airflow_db() {
    info "Initialisation de la base Airflow..."
    airflow db init
    info "Base Airflow initialisée."
}

# ─── 3. Création du fichier init_db.sql (cible /docker-entrypoint-initdb.d) ───
create_init_sql() {
    local target="${1:-}"
    if [ -n "$target" ]; then
        cp "$(dirname "$0")/init_db.sql" "$target/"
        info "init_db.sql copié vers $target"
    fi
}

# ─── 4. Création tables via init_db.sql ───
create_forex_tables() {
    info "Création des tables forex..."
    local sql_file
    sql_file="$(dirname "$0")/init_db.sql"
    if [ ! -f "$sql_file" ]; then
        err "init_db.sql introuvable à $sql_file"
        exit 1
    fi
    PGPASSWORD="$PG_PASS" psql \
        -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -f "$sql_file"
    info "Tables forex créées / vérifiées."
}

# ─── 5. Connection Airflow → PostgreSQL ───
create_airflow_connection() {
    info "Création de la Connection Airflow '$AIRFLOW_CONN_ID'..."
    airflow connections delete "$AIRFLOW_CONN_ID" &>/dev/null || true
    airflow connections add "$AIRFLOW_CONN_ID" \
        --conn-type 'postgres' \
        --conn-host "$PG_HOST" \
        --conn-port "$PG_PORT" \
        --conn-schema "$PG_DB" \
        --conn-login "$PG_USER" \
        --conn-password "$PG_PASS"
    info "Connection '$AIRFLOW_CONN_ID' créée."
}

# ─── 6. Variables Airflow ───
create_airflow_variables() {
    info "Création des Variables Airflow..."

    # Devises à suivre (séparées par des virgules)
    airflow variables set 'forex_currencies' 'EUR,USD,GBP,JPY,CHF,AUD' || true

    # Seuil d'alerte de variation (en %)
    airflow variables set 'forex_alert_threshold' '2.0' || true

    # Seuil de fraîcheur (heures max depuis la date API)
    airflow variables set 'forex_freshness_hours' '6' || true

    # URL de base de l'API Frankfurter
    airflow variables set 'forex_api_base' 'https://api.frankfurter.app' || true

    info "Variables Airflow créées."
}

# ─── 7. Création utilisateur admin Airflow ───
create_admin_user() {
    info "Création de l'utilisateur admin Airflow..."
    airflow users create \
        --username admin \
        --firstname Admin \
        --lastname Forex \
        --role Admin \
        --email admin@forex.local \
        --password admin 2>/dev/null || warn "Utilisateur admin déjà existant."
    info "Utilisateur admin créé (admin / admin)."
}

# ─── 8. Vérification finale ───
verify() {
    info "Vérification..."
    echo ""
    echo "── Connections ──"
    airflow connections list | head -5
    echo ""
    echo "── Variables ──"
    airflow variables list | head -10
    echo ""
    echo "── DAGs ──"
    airflow dags list | head -5
}

# ─── Main ───
main() {
    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║  Forex Pipeline — Setup                      ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    wait_for_pg
    create_forex_tables
    init_airflow_db
    create_airflow_connection
    create_airflow_variables
    create_admin_user
    verify

    echo ""
    info "Setup terminé avec succès !"
    echo ""
    echo "  Airflow  → http://localhost:8080"
    echo "  Metabase → http://localhost:3000"
    echo "  PG       → $PG_HOST:$PG_PORT / $PG_DB"
    echo ""
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
