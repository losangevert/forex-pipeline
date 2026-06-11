#!/usr/bin/env python3
"""Backfill historique depuis la machine hôte vers PostgreSQL du VPS."""
import json, urllib.request, datetime, sys

API = "https://api.frankfurter.app"
CURRENCIES = ["USD", "GBP", "JPY", "CHF"]
BASE = "EUR"

today = datetime.date.today()
start = today - datetime.timedelta(days=31)

dates = []
d = start
while d <= today:
    dates.append(d)
    d += datetime.timedelta(days=1)

print(f"Recuperation de {len(dates)} jours...")

rows = []
for dt in dates:
    date_str = dt.strftime("%Y-%m-%d")
    url = f"{API}/{date_str}?from={BASE}&to={','.join(CURRENCIES)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        rates = data.get("rates", {})
        for cur, rate in rates.items():
            rows.append((f"{BASE}/{cur}", date_str, rate, BASE, cur))
        print(f"  {date_str}: {len(rates)} paires", end="\r")
    except Exception as e:
        print(f"\n  X {date_str}: {e}")
        continue

print(f"\n=> {len(rows)} lignes")

if rows:
    import psycopg2
    conn = psycopg2.connect(
        host="149.202.63.243", port=5432, dbname="forex",
        user="airflow", password="airflow_forex_2026"
    )
    cur = conn.cursor()
    inserted = 0
    for pair, d, rate, base, target in rows:
        try:
            cur.execute("""
                INSERT INTO exchange_rates
                    (currency_pair, rate_date, rate, base_currency, target_currency,
                     ingested_at, dag_run_id)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (currency_pair, rate_date, ingested_at) DO NOTHING
            """, (pair, d, rate, base, target, "historical_backfill"))
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"  X {pair} {d}: {e}")
    conn.commit()
    cur.close()
    conn.close()
    print(f"=> {inserted} lignes inserees dans exchange_rates")
else:
    print("Aucune donnee")