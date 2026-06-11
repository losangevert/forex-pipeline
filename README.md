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
- Devises : EUR/USD, EUR/GBP, EUR/JPY, EUR/CHF, EUR/AUD (configurable via Variable `forex_currencies`)
- Seuil d'alerte : 2% (configurable via Variable `forex_alert_threshold`)
- URL API : `forex_api_base` (défaut : `https://api.frankfurter.app`)
- Fraîcheur max : 6h (configurable via Variable `forex_freshness_hours`)

## Contrôles qualité

| Dimension    | Contrôle                                             |
| ------------ | ---------------------------------------------------- |
| Complétude   | Toutes les paires attendues sont présentes           |
| Cohérence    | Les taux sont des nombres > 0                        |
| Fraîcheur    | La date API ≤ `freshness_hours`                      |
| Unicité      | Contrainte UNIQUE + ON CONFLICT DO NOTHING           |
| Structure    | Vérification de la clé `rates` dans la réponse API   |

## Vues SQL et Graphiques Metabase

### `v_last_30d_trend` — Tendance des taux sur 30 jours

```sql
SELECT currency_pair, rate_date, rate, daily_pct_change
FROM v_last_30d_trend
ORDER BY currency_pair, rate_date;
```

**Colonnes :**
| Champ | Description |
|---|---|
| `currency_pair` | Paire de devises (ex: EUR/USD) |
| `rate_date` | Date du taux |
| `rate` | Taux de change |
| `daily_pct_change` | Variation en % par rapport à la veille |

**Usage Metabase :** `+ New > Question > SQL query`
- **Line chart :** Axe X = `rate_date`, Axe Y = `rate`, Série = `currency_pair`
- Affiche l'évolution des 5 paires simultanément
- On peut aussi filtrer par paire pour un graphique individuel

**Lecture métier :**
- Tendance haussière → devise de base (EUR) se renforce
- Tendance baissière → devise de base s'affaiblit
- Forte variation quotidienne → événement macroéconomique

---

### `v_top_weekly_variations` — Variations les plus fortes sur 7 jours

```sql
SELECT currency_pair, rate_date, abs_variation
FROM v_top_weekly_variations
WHERE abs_variation IS NOT NULL
ORDER BY abs_variation DESC
LIMIT 20;
```

**Colonnes :**
| Champ | Description |
|---|---|
| `currency_pair` | Paire de devises |
| `rate_date` | Date de la variation |
| `abs_variation` | Écart absolu |

**Usage Metabase :**
- **Bar chart :** Axe X = `currency_pair`, Axe Y = `abs_variation`
- Met en évidence les jours de forte volatilité

**Lecture métier :**
- Identifie les paires les plus volatiles
- Repère les crises / annonces impactant le forex
- Utile pour backtesting de stratégies de trading

---

### Dashboard "Taux de change — Suivi"

6 graphiques pré-construits dans Metabase :

| Graphique | Type | Intérêt |
|---|---|---|
| EUR/USD — 30j | Courbe | Paire la plus échangée au monde |
| EUR/GBP — 30j | Courbe | Brexit & relations UK/EU |
| EUR/JPY — 30j | Courbe | Yen comme valeur refuge |
| EUR/CHF — 30j | Courbe | Franc suisse, safe haven |
| Toutes paires — 30j | Courbes superposées | Comparaison directe |
| Top variations hebdo | Barres | Alertes visuelles |

### Dashboard "Pipeline — Monitoring"

| Graphique | Type | Intérêt |
|---|---|---|
| Derniers logs pipeline | Tableau | Vérifier l'exécution du DAG |
| Alertes taux de change | Tableau | Lire les alertes déclenchées |

---

### Créer ses propres graphiques

Dans Metabase (admin@forex.local / admin1234) :

1. `+ New > Question > SQL query`
2. Coller une requête SQL (voir ci-dessus)
3. Cliquer sur **Visualize**
4. Choisir le type de graphique (Line, Bar, Table...)
5. `Save` → choisir un dashboard existant

Conseils :
- Filtrer par `currency_pair` pour isoler une paire
- Ajouter `WHERE rate_date >= '2026-06-01'` pour une période spécifique
- Utiliser `AVG(rate)` et `GROUP BY rate_date` pour des moyennes mobiles

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
