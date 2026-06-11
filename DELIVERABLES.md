# Livrables — Projet Forex Pipeline

## 1. DAG Python (Complet et fonctionnel)
📄 `dags/forex_pipeline.py`
- 7 tâches : extract_raw, store_raw, transform_validate, load_valid, load_graveyard, detect_anomalies, log_pipeline
- TaskFlow API (@dag/@task)
- Idempotent (ON CONFLICT DO NOTHING)
- Timeouts, retries, chemins nominal & échec

## 2. init_db.sql
📄 `scripts/init_db.sql`
- 5 tables : raw_rates, exchange_rates, data_quality_graveyard, rate_alerts, pipeline_log
- 2 vues métier : v_last_30d_trend, v_top_weekly_variations

## 3. Graph View (DAG)
📄 `dag_graph.svg` — Structure des dépendances entre tâches

## 4. Tables PostgreSQL (après exécution)

### raw_rates (2 lignes)
```
id | base | raw_payload (JSONB)           | ingested_at
1  | EUR  | {"base":"EUR","rates":{...}}  | 2026-06-11 08:02:49
2  | EUR  | {"base":"EUR","rates":{...}}  | 2026-06-11 08:03:54
```

### exchange_rates (8 lignes)
```
currency_pair | rate_date  | rate       | dag_run_id
EUR/CHF       | 2026-06-10 |   0.922200 | manual__2026-06-11T08:02:39+00:00
EUR/CHF       | 2026-06-10 |   0.922200 | manual__2026-06-11T08:03:43+00:00
EUR/GBP       | 2026-06-10 |   0.862280 | ...
EUR/JPY       | 2026-06-10 | 185.190000 | ...
EUR/USD       | 2026-06-10 |   1.153900 | ...
```

### data_quality_graveyard (0 lignes)
Toutes les données étaient valides.

### pipeline_log (2 lignes)
```
id | dag_run_id                          | status  | received | valid | rejected | inserted | alerts
1  | manual__2026-06-11T08:02:39+00:00 | success |       4 |     4 |        0 |        4 |     0
2  | manual__2026-06-11T08:03:43+00:00 | success |       4 |     4 |        0 |        4 |     0
```

### rate_alerts (0 lignes car taux identiques entre les 2 runs)
Les alertes se déclenchent à partir de 2% de variation. Tests effectués en base :
- EUR/USD +2.26% → ALERTE ✅
- EUR/GBP +2.06% → ALERTE ✅
- EUR/JPY +1.79% → pas d'alerte ✅
- EUR/CHF +1.39% → pas d'alerte ✅

### Vue Métier : v_last_30d_trend
Tendance des taux sur 30 jours avec variation quotidienne en %.

### Vue Métier : v_top_weekly_variations
Top 20 des plus fortes variations absolues sur 7 jours.

## 5. KPIs Metabase
Accessible sur http://149.202.63.243:3000
- DB déjà configurée (forex / airflow)
- Créer des questions/dashboards sur les vues `v_last_30d_trend` et `v_top_weekly_variations`
- Métabase stocke aussi sa config dans la même base PostgreSQL (forex)

## 6. Document robustesse
📄 `ROBUSTNESS.md`

## 7. Déploiement
📍 VPS OVH : 149.202.63.243
- Airflow : http://149.202.63.243:8080
- Metabase : http://149.202.63.243:3000
- PostgreSQL : port 5432

## 8. Code source
🔗 https://github.com/losangevert/forex-pipeline
