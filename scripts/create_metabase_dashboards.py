#!/usr/bin/env python3
"""
create_metabase_dashboards.py
Crée les dashboards Metabase pour le pipeline Forex.
Utilisation : python3 create_metabase_dashboards.py
"""

import json, os, sys, urllib.request

MB_URL = os.environ.get("MB_URL", "http://localhost:3000")
MB_EMAIL = os.environ.get("MB_EMAIL", "admin@forex.local")
MB_PASS = os.environ.get("MB_PASS", "admin1234")

def api(method, path, data=None, token=None):
    url = f"{MB_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ⚠ HTTP {e.code} sur {method} {path}: {err[:200]}")
        return None

def main():
    # ── Login ──
    sess = api("POST", "/api/session", {"username": MB_EMAIL, "password": MB_PASS})
    if not sess or "id" not in sess:
        print("❌ Connexion impossible")
        sys.exit(1)
    token = sess["id"]
    print(f"✅ Session: {token[:8]}...")

    # ── Récup DB ID ──
    dbs = api("GET", "/api/database", token=token)
    if not dbs:
        print("❌ Pas de base")
        sys.exit(1)
    db_id = None
    for db in dbs.get("data", []):
        if db["engine"] == "postgres" and db["name"] != "Sample Database":
            db_id = db["id"]
            break
    if not db_id:
        print("❌ Base forex introuvable")
        sys.exit(1)
    print(f"✅ Database ID: {db_id}")

    # ── Définition des cartes (questions) ──
    cards_def = [
        {
            "name": "Tendance EUR/USD — 30 jours",
            "display": "line",
            "description": "Évolution du taux EUR/USD sur 30 jours glissants",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT rate_date, rate
                        FROM v_last_30d_trend
                        WHERE currency_pair = 'EUR/USD'
                        ORDER BY rate_date
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["rate_date"],
                "graph.metrics": ["rate"],
                "series_settings": {"rate": {"title": "EUR/USD"}}
            }
        },
        {
            "name": "Tendance EUR/GBP — 30 jours",
            "display": "line",
            "description": "Évolution du taux EUR/GBP sur 30 jours",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT rate_date, rate
                        FROM v_last_30d_trend
                        WHERE currency_pair = 'EUR/GBP'
                        ORDER BY rate_date
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["rate_date"],
                "graph.metrics": ["rate"],
                "series_settings": {"rate": {"title": "EUR/GBP"}}
            }
        },
        {
            "name": "Tendance EUR/JPY — 30 jours",
            "display": "line",
            "description": "Évolution du taux EUR/JPY sur 30 jours",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT rate_date, rate
                        FROM v_last_30d_trend
                        WHERE currency_pair = 'EUR/JPY'
                        ORDER BY rate_date
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["rate_date"],
                "graph.metrics": ["rate"],
                "series_settings": {"rate": {"title": "EUR/JPY"}}
            }
        },
        {
            "name": "Tendance EUR/CHF — 30 jours",
            "display": "line",
            "description": "Évolution du taux EUR/CHF sur 30 jours",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT rate_date, rate
                        FROM v_last_30d_trend
                        WHERE currency_pair = 'EUR/CHF'
                        ORDER BY rate_date
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["rate_date"],
                "graph.metrics": ["rate"],
                "series_settings": {"rate": {"title": "EUR/CHF"}}
            }
        },
        {
            "name": "Toutes les paires — 30 jours",
            "display": "line",
            "description": "Comparaison de toutes les paires de devises sur 30 jours",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT rate_date, currency_pair, rate
                        FROM v_last_30d_trend
                        ORDER BY currency_pair, rate_date
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["rate_date"],
                "graph.metrics": ["rate"],
                "graph.series_order": ["EUR/CHF", "EUR/GBP", "EUR/JPY", "EUR/USD"]
            }
        },
        {
            "name": "Top variations hebdomadaires",
            "display": "bar",
            "description": "Les plus fortes variations absolues sur 7 jours",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT currency_pair, rate_date, abs_variation
                        FROM v_top_weekly_variations
                        WHERE abs_variation IS NOT NULL
                        ORDER BY abs_variation DESC
                        LIMIT 10
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "graph.dimensions": ["currency_pair"],
                "graph.metrics": ["abs_variation"],
                "graph.series_order_dimension": "currency_pair"
            }
        },
        {
            "name": "Derniers logs pipeline",
            "display": "table",
            "description": "Statut des 10 dernières exécutions du pipeline",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT execution_date, status, lines_received,
                               lines_valid, lines_rejected, lines_inserted,
                               alerts_raised
                        FROM pipeline_log
                        ORDER BY execution_date DESC
                        LIMIT 10
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "table.columns": [
                    {"name": "execution_date", "enabled": True},
                    {"name": "status", "enabled": True},
                    {"name": "lines_received", "enabled": True},
                    {"name": "lines_valid", "enabled": True},
                    {"name": "lines_rejected", "enabled": True},
                    {"name": "lines_inserted", "enabled": True},
                    {"name": "alerts_raised", "enabled": True},
                ]
            }
        },
        {
            "name": "Alertes taux de change",
            "display": "table",
            "description": "Dernières alertes de variation de taux",
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {
                    "query": """
                        SELECT alert_date, currency_pair,
                               previous_rate, current_rate,
                               pct_change, threshold_used
                        FROM rate_alerts
                        ORDER BY alert_date DESC
                        LIMIT 20
                    """,
                    "template-tags": {}
                }
            },
            "visualization_settings": {
                "table.columns": [
                    {"name": "alert_date", "enabled": True},
                    {"name": "currency_pair", "enabled": True},
                    {"name": "pct_change", "enabled": True},
                ]
            }
        },
    ]

    # ── Création des cartes ──
    created_cards = []
    for i, cdef in enumerate(cards_def):
        print(f"  Création carte {i+1}/{len(cards_def)}: {cdef['name']}...", end=" ")
        card = api("POST", "/api/card", cdef, token=token)
        if card and "id" in card:
            created_cards.append(card)
            print(f"✅ id={card['id']}")
        else:
            print("❌ Échec")

    # ── Dashboard 1: Taux de change ──
    print("\n📊 Création dashboard 'Taux de change — Suivi'...")
    d1 = api("POST", "/api/dashboard", {
        "name": "Taux de change — Suivi",
        "description": "Évolution des taux de change et variations anormales"
    }, token=token)
    if d1 and "id" in d1:
        d1_id = d1["id"]
        print(f"✅ Dashboard id={d1_id}")
        # Add cards to dashboard 1 (indices 0-5: 4 individual lines + all pairs + top vars)
        positions = [
            {"card_id": created_cards[0]["id"], "row": 0, "col": 0, "size_x": 6, "size_y": 6},
            {"card_id": created_cards[1]["id"], "row": 0, "col": 6, "size_x": 6, "size_y": 6},
            {"card_id": created_cards[2]["id"], "row": 6, "col": 0, "size_x": 6, "size_y": 6},
            {"card_id": created_cards[3]["id"], "row": 6, "col": 6, "size_x": 6, "size_y": 6},
            {"card_id": created_cards[4]["id"], "row": 12, "col": 0, "size_x": 12, "size_y": 6},
            {"card_id": created_cards[5]["id"], "row": 18, "col": 0, "size_x": 12, "size_y": 5},
        ]
        # PUT /api/dashboard/:id/cards remplace toutes les cartes
        d1_result = api("PUT", f"/api/dashboard/{d1_id}/cards", {
            "cards": [
                {"id": i, "card_id": p["card_id"], "row": p["row"],
                 "col": p["col"], "size_x": p["size_x"], "size_y": p["size_y"]}
                for i, p in enumerate(positions)
            ]
        }, token=token)
        if d1_result:
            dc_count = len(d1_result.get("cards", []))
            print(f"    {dc_count} cartes ajoutées au dashboard")
    else:
        print("❌")

    # ── Dashboard 2: Pipeline ──
    print("\n📊 Création dashboard 'Pipeline — Monitoring'...")
    d2 = api("POST", "/api/dashboard", {
        "name": "Pipeline — Monitoring",
        "description": "Suivi des exécutions du pipeline Airflow"
    }, token=token)
    if d2 and "id" in d2:
        d2_id = d2["id"]
        print(f"✅ Dashboard id={d2_id}")
        positions2 = [
            {"card_id": created_cards[6]["id"], "row": 0, "col": 0, "size_x": 12, "size_y": 5},
            {"card_id": created_cards[7]["id"], "row": 5, "col": 0, "size_x": 12, "size_y": 5},
        ]
        d2_result = api("PUT", f"/api/dashboard/{d2_id}/cards", {
            "cards": [
                {"id": i, **p} for i, p in enumerate(positions2)
            ]
        }, token=token)
        if d2_result:
            dc_count = len(d2_result.get("cards", []))
            print(f"    {dc_count} cartes ajoutées au dashboard")
    else:
        print("❌")

    # ── Export dashboards ──
    print("\n💾 Export des dashboards...")
    exports = []
    for did, dname in [(d1.get("id"), "Taux de change — Suivi") if d1 else (None, None),
                       (d2.get("id"), "Pipeline — Monitoring") if d2 else (None, None)]:
        if did:
            dash = api("GET", f"/api/dashboard/{did}", token=token)
            if dash:
                exports.append(dash)
                print(f"  ✅ Exporté: {dname}")

    # ── Sauvegarde JSON ──
    out_path = os.path.join(os.path.dirname(__file__) or ".", "metabase_dashboards.json")
    with open(out_path, "w") as f:
        json.dump(exports, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n✅ Export sauvegardé dans {out_path}")

    print("\n✅ Terminé !")
    print(f"   Metabase: http://localhost:3000")
    print(f"   Dashboards créés : Taux de change — Suivi / Pipeline — Monitoring")


if __name__ == "__main__":
    main()
