#!/usr/bin/env python3
"""Capture screenshots for deliverables."""
import sys, json, time
from playwright.sync_api import sync_playwright

HOST = "149.202.63.243"
OUT = "/home/node/.openclaw/workspace/airflow-forex-pipeline/screenshots"

AF_USER = "admin"
AF_PASS = "admin"
MB_USER = "admin@forex.local"
MB_PASS = "admin1234"

def screenshot(page, url, path, sleep_s=3):
    print(f"  📸 {path}...", end="", flush=True)
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(sleep_s)
    page.screenshot(path=f"{OUT}/{path}", full_page=False)
    print(" ✅")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # ── 1. Airflow Login & DAG Graph ──
        print("\n🔐 Airflow login...")
        page.goto(f"http://{HOST}:8080/login", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)
        # Fill login form (Airflow uses input[type=submit], not button)
        page.fill("#username", AF_USER)
        page.fill("#password", AF_PASS)
        page.click("input[type=submit]")
        time.sleep(3)
        page.wait_for_load_state("networkidle", timeout=15000)

        screenshot(page, f"http://{HOST}:8080/dags/forex_exchange_rate_pipeline/graph",
                   "01_airflow_graph.png")

        # DAG details
        screenshot(page, f"http://{HOST}:8080/dags/forex_exchange_rate_pipeline/details",
                   "02_airflow_details.png")

        # DAG runs - list successful runs
        screenshot(page, f"http://{HOST}:8080/dags/forex_exchange_rate_pipeline/grid",
                   "03_airflow_grid.png")

        # ── 2. Airflow variables ──
        screenshot(page, f"http://{HOST}:8080/variable/list",
                   "04_airflow_variables.png")

        # ── 3. Airflow connections ──
        screenshot(page, f"http://{HOST}:8080/connection/list",
                   "05_airflow_connections.png")

        # ── 4. Metabase dashboards ──
        print("\n🔐 Metabase login...")
        page.goto(f"http://{HOST}:3000", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)
        time.sleep(4)
        page.fill("input[type=email]", MB_USER)
        page.fill("input[type=password]", MB_PASS)
        page.click("button[type=submit]")
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=20000)

        # Dashboard 1
        screenshot(page, f"http://{HOST}:3000/dashboard/2",
                   "06_metabase_dashboard1.png", sleep_s=6)

        # Dashboard 2
        screenshot(page, f"http://{HOST}:3000/dashboard/3",
                   "07_metabase_dashboard2.png", sleep_s=6)

        browser.close()
        print("\n✅ Toutes les captures terminées !")

    # ── 5. PostgreSQL screenshots (via text/html) ──
    print("\n📋 Génération des captures SQL...")
    generate_sql_screenshots(HOST)

def generate_sql_screenshots(host):
    import psycopg2
    conn = psycopg2.connect(
        host=host, port=5432, dbname="forex",
        user="airflow", password="airflow_forex_2026"
    )
    cur = conn.cursor()

    queries = {
        "08_postgres_exchange_rates": "SELECT currency_pair, rate_date, rate, dag_run_id FROM exchange_rates ORDER BY currency_pair, rate_date LIMIT 20",
        "09_postgres_raw_rates": "SELECT id, base_currency, ingested_at FROM raw_rates",
        "10_postgres_pipeline_log": "SELECT id, dag_run_id, status, lines_received, lines_valid, lines_inserted, alerts_raised FROM pipeline_log",
        "11_postgres_graveyard": "SELECT * FROM data_quality_graveyard",
        "12_postgres_alerts": "SELECT * FROM rate_alerts ORDER BY alert_date DESC LIMIT 10",
        "13_postgres_view_trend": "SELECT * FROM v_last_30d_trend ORDER BY currency_pair, rate_date LIMIT 15",
        "14_postgres_view_variations": "SELECT * FROM v_top_weekly_variations WHERE abs_variation IS NOT NULL ORDER BY abs_variation DESC LIMIT 10",
    }

    import os
    os.makedirs(OUT, exist_ok=True)

    for name, sql in queries.items():
        path = f"{OUT}/{name}.txt"
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            with open(path, "w") as f:
                f.write(" | ".join(cols) + "\n")
                f.write("-" * (sum(len(c) for c in cols) + 3 * len(cols)) + "\n")
                for row in rows:
                    f.write(" | ".join(str(c) if c is not None else "NULL" for c in row) + "\n")
            print(f"  ✅ {name}.txt ({len(rows)} lignes)")
        except Exception as e:
            print(f"  ⚠ {name}: {e}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    main()
