#!/bin/bash
# ============================================================
# setup_metabase.sh — Bootstrap Metabase
# Crée le compte admin + connecte la base PostgreSQL forex.
# Idempotent : ne recrée pas si déjà fait.
#
# Usage : ./scripts/setup_metabase.sh
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

MB_URL="${MB_URL:-http://localhost:3000}"
MB_EMAIL="${MB_EMAIL:-admin@forex.local}"
MB_PASS="${MB_PASS:-admin1234}"
MB_FIRSTNAME="${MB_FIRSTNAME:-Admin}"
MB_LASTNAME="${MB_LASTNAME:-Forex}"
MB_SITE_NAME="${MB_SITE_NAME:-Forex Pipeline}"

PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-forex}"
PG_USER="${PG_USER:-airflow}"
PG_PASS="${PG_PASS:-airflow_forex_2026}"

DB_NAME="${DB_NAME:-Forex (PostgreSQL)}"

# ─── 1. Attente ───
wait_mb() {
    info "Attente de Metabase ($MB_URL)..."
    for i in $(seq 1 60); do
        if curl -sf "${MB_URL}/api/health" &>/dev/null; then
            info "Metabase prête."
            return 0
        fi
        sleep 2
    done
    err "Metabase pas joignable après 120s."
    exit 1
}

# ─── 2. Setup admin (idempotent) ───
setup_admin() {
    local token
    token=$(curl -s "${MB_URL}/api/session/properties" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('setup-token', ''))" 2>/dev/null || echo "")

    if [ -z "$token" ]; then
        info "Metabase déjà configurée."
        return 0
    fi

    info "Création du compte admin ($MB_EMAIL / $MB_PASS)..."
    local resp
    resp=$(curl -s -X POST "${MB_URL}/api/setup" \
        -H "Content-Type: application/json" \
        -d "{
            \"token\": \"$token\",
            \"user\": {
                \"first_name\": \"$MB_FIRSTNAME\",
                \"last_name\": \"$MB_LASTNAME\",
                \"email\": \"$MB_EMAIL\",
                \"password\": \"$MB_PASS\"
            },
            \"prefs\": {
                \"site_name\": \"$MB_SITE_NAME\"
            },
            \"database\": null
        }" 2>/dev/null || echo "{}")

    local user_id
    user_id=$(echo "$resp" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(r.get('id', 'NA'))
" 2>/dev/null || echo "NA")

    if [ "$user_id" != "NA" ] && [ -n "$user_id" ]; then
        info "Admin créé : $MB_EMAIL / $MB_PASS"
    else
        warn "Setup déjà effectué."
    fi
}

# ─── 3. Session token ───
get_session_token() {
    curl -s -X POST "${MB_URL}/api/session" \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"$MB_EMAIL\", \"password\": \"$MB_PASS\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || echo ""
}

# ─── 4. Ajout base PostgreSQL (idempotent) ───
add_database() {
    local token="$1"
    if [ -z "$token" ]; then
        err "Pas de session."
        return 1
    fi

    # Vérifier si la base existe déjà
    local existing
    existing=$(curl -s -H "X-Metabase-Session: $token" "${MB_URL}/api/database" \
        | python3 -c "
import sys, json
dbs = json.load(sys.stdin).get('data', [])
for db in dbs:
    if db.get('name') == '$DB_NAME':
        print(db['id'])
        break
" 2>/dev/null || echo "")

    if [ -n "$existing" ]; then
        info "Base '$DB_NAME' déjà connectée (id=$existing)."
        return 0
    fi

    info "Ajout de la base PostgreSQL '$DB_NAME'..."
    local resp
    resp=$(curl -s -X POST "${MB_URL}/api/database" \
        -H "Content-Type: application/json" \
        -H "X-Metabase-Session: $token" \
        -d "{
            \"name\": \"$DB_NAME\",
            \"engine\": \"postgres\",
            \"description\": \"Pipeline Forex Airflow\",
            \"details\": {
                \"host\": \"$PG_HOST\",
                \"port\": $PG_PORT,
                \"dbname\": \"$PG_DB\",
                \"user\": \"$PG_USER\",
                \"password\": \"$PG_PASS\",
                \"ssl\": false
            },
            \"is_full_sync\": true
        }" 2>/dev/null || echo "{}")

    local db_id
    db_id=$(echo "$resp" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(r.get('id', 'FAIL'))
" 2>/dev/null || echo "FAIL")

    if [ "$db_id" != "FAIL" ] && [ -n "$db_id" ]; then
        info "Base '$DB_NAME' ajoutée (id=$db_id)."
    else
        local err_msg
        err_msg=$(echo "$resp" | python3 -c "
import sys, json
r = json.load(sys.stdin)
errs = r.get('errors', {})
if errs:
    print(json.dumps(errs)[:200])
else:
    print('ok')
" 2>/dev/null || echo "?")
        warn "Ajout base : $err_msg"
    fi
}

# ─── 5. Vérification ───
verify() {
    local token="$1"
    if [ -z "$token" ]; then
        warn "Pas de session."
        return
    fi

    info "Bases de données connectées :"
    curl -s -H "X-Metabase-Session: $token" "${MB_URL}/api/database" 2>/dev/null \
        | python3 -c "
import sys, json
dbs = json.load(sys.stdin).get('data', [])
for db in dbs:
    name = db.get('name', '?')
    engine = db.get('engine', '?')
    print(f\"  ─ {name} ({engine})\")
" 2>/dev/null || warn "Impossible de lister."
}

# ─── Main ───
main() {
    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║  Forex Pipeline — Setup Metabase             ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    wait_mb
    setup_admin

    local session
    session=$(get_session_token)

    if [ -n "$session" ]; then
        info "Session OK."
        add_database "$session"
        verify "$session"
    else
        warn "Connexion impossible."
    fi

    echo ""
    info "Setup Metabase terminé !"
    echo ""
    echo "  URL       → $MB_URL"
    echo "  Login     → $MB_EMAIL / $MB_PASS"
    echo "  Database  → $DB_NAME"
    echo ""
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
