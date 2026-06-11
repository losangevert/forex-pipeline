# Forex Exchange Rate Pipeline

Plateforme d'orchestration Airflow pour l'ingestion, le stockage, la transformation, le contrôle qualité et l'analyse des taux de change multi-devises.

**API :** [Frankfurter](https://api.frankfurter.app)

---

## Stack

| Service      | Technologie          | Port |
| ------------ | -------------------- | ---- |
| Airflow      | apache/airflow:2.10.5 | 8080 |
| PostgreSQL   | postgres:16           | 5432 |
| Metabase     | metabase:v0.53.7     | 3000 |

## Déploiement

```bash
# Cloner
git clone https://github.com/losangevert/forex-pipeline.git
cd forex-pipeline

# Lancer la stack
docker compose up -d

# Attendre ~1 min, puis initialiser Airflow
docker compose run --rm airflow-init

# Initialiser Metabase
bash scripts/setup_metabase.sh
```

## Identifiants

### Airflow
- **URL :** http://localhost:8080
- **Login :** `admin`
- **Password :** `admin`

### Metabase
- **URL :** http://localhost:3000
- **Login :** `admin@forex.local`
- **Password :** `admin1234`

### PostgreSQL
- **Host :** `postgres` (ou `localhost` depuis le VPS)
- **Port :** `5432`
- **Database :** `forex`
- **User :** `airflow`
- **Password :** `airflow_forex_2026`

## DAG : `forex_exchange_rate_pipeline`

7 tâches (TaskFlow API) :

```
extract_raw → store_raw
            → transform_validate → load_valid
                                  → load_graveyard
                                  → detect_anomalies
                                  → log_pipeline
```

- Schedule : `@hourly`
- Devises : EUR/USD, EUR/GBP, EUR/JPY, EUR/CHF (configurable via Variable `forex_currencies`)
- Seuil d'alerte : 2% (configurable via Variable `forex_alert_threshold`)
- Fraîcheur max : 6h (configurable via Variable `forex_freshness_hours`)

## Contrôles qualité

| Dimension    | Contrôle                                             |
| ------------ | ---------------------------------------------------- |
| Complétude   | Toutes les paires attendues sont présentes           |
| Cohérence    | Les taux sont des nombres > 0                        |
| Fraîcheur    | La date API ≤ `freshness_hours`                      |
| Unicité      | Contrainte UNIQUE + ON CONFLICT DO NOTHING           |
| Structure    | Vérification de la clé `rates` dans la réponse API   |

## Vues Metabase

- `v_last_30d_trend` — tendance quotidienne par paire avec variation en %
- `v_top_weekly_variations` — top 20 des plus fortes variations sur 7 jours

## Fichiers

```
├── dags/
│   └── forex_pipeline.py        # DAG principal (TaskFlow API)
├── scripts/
│   ├── init_db.sql              # Tables + vues
│   ├── setup.sh                 # Bootstrap Airflow (DB init, connection, variables)
│   └── setup_metabase.sh        # Bootstrap Metabase (admin, base PostgreSQL)
├── docker-compose.yml           # Stack complète
├── webserver_config.py          # Configuration Flask/Auth Airflow
├── ROBUSTNESS.md                # Choix de robustesse détaillés
└── DELIVERABLES.md              # Livrables du projet
```
