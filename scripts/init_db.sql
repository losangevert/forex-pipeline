-- ============================================================
-- init_db.sql — Forex Exchange Rate Pipeline
-- Toutes les tables sont créées ici (versionné)
-- ============================================================

-- 1. Table brute : stockage de la réponse API complète
CREATE TABLE IF NOT EXISTS raw_rates (
    id              SERIAL PRIMARY KEY,
    base_currency   VARCHAR(3) NOT NULL,
    raw_payload     JSONB NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Table structurée : une ligne par paire de devises et par date
CREATE TABLE IF NOT EXISTS exchange_rates (
    id              SERIAL PRIMARY KEY,
    currency_pair   VARCHAR(7) NOT NULL,   -- ex: EUR/USD
    rate_date       DATE NOT NULL,
    rate            NUMERIC(18,6) NOT NULL,
    base_currency   VARCHAR(3) NOT NULL,
    target_currency VARCHAR(3) NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dag_run_id      VARCHAR(255),
    UNIQUE (currency_pair, rate_date, ingested_at)
);

-- 3. Cimetière de données : lignes invalides rejetées
CREATE TABLE IF NOT EXISTS data_quality_graveyard (
    id              SERIAL PRIMARY KEY,
    currency_pair   VARCHAR(7),
    rate_date       DATE,
    rate_value      TEXT,
    rejection_reason TEXT NOT NULL,
    raw_line        JSONB,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dag_run_id      VARCHAR(255)
);

-- 4. Table d'alertes : variations anormales entre deux runs
CREATE TABLE IF NOT EXISTS rate_alerts (
    id              SERIAL PRIMARY KEY,
    currency_pair   VARCHAR(7) NOT NULL,
    previous_rate   NUMERIC(18,6) NOT NULL,
    current_rate    NUMERIC(18,6) NOT NULL,
    absolute_change NUMERIC(18,6) NOT NULL,
    pct_change      NUMERIC(10,4) NOT NULL,
    threshold_used  NUMERIC(10,4) NOT NULL,
    alert_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dag_run_id      VARCHAR(255)
);

-- 5. Table de logs d'exécution du pipeline
CREATE TABLE IF NOT EXISTS pipeline_log (
    id              SERIAL PRIMARY KEY,
    dag_run_id      VARCHAR(255) NOT NULL,
    execution_date  TIMESTAMPTZ NOT NULL,
    status          VARCHAR(20) NOT NULL,  -- success / failed / partial
    lines_received  INTEGER DEFAULT 0,
    lines_valid     INTEGER DEFAULT 0,
    lines_rejected  INTEGER DEFAULT 0,
    lines_inserted  INTEGER DEFAULT 0,
    alerts_raised   INTEGER DEFAULT 0,
    error_message   TEXT,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index pour performances
CREATE INDEX IF NOT EXISTS idx_exchange_rates_pair_date ON exchange_rates(currency_pair, rate_date);
CREATE INDEX IF NOT EXISTS idx_alert_log_pair ON rate_alerts(currency_pair);
CREATE INDEX IF NOT EXISTS idx_pipeline_log_exec ON pipeline_log(execution_date);


-- ============================================================
-- VUES METIER (KPIs) — exploitables depuis Metabase
-- ============================================================

-- Vue 1 : Évolution des taux sur 30 jours glissants
CREATE OR REPLACE VIEW v_last_30d_trend AS
SELECT
    currency_pair,
    rate_date,
    rate,
    ROUND(
        (rate - LAG(rate, 1) OVER (PARTITION BY currency_pair ORDER BY rate_date))
        / NULLIF(LAG(rate, 1) OVER (PARTITION BY currency_pair ORDER BY rate_date), 0) * 100,
        4
    ) AS daily_pct_change
FROM exchange_rates
WHERE rate_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY currency_pair, rate_date;

-- Vue 2 : Top 5 des plus fortes variations absolues sur 7 jours
CREATE OR REPLACE VIEW v_top_weekly_variations AS
SELECT
    currency_pair,
    rate_date,
    rate,
    ABS(rate - LAG(rate, 1) OVER (PARTITION BY currency_pair ORDER BY rate_date)) AS abs_variation
FROM exchange_rates
WHERE rate_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY abs_variation DESC NULLS LAST
LIMIT 20;
