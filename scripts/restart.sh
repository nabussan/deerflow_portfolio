#!/usr/bin/env bash
# restart.sh – DeerFlow neu starten (W541/WSL2)
# Startet alle Services im Hintergrund und kehrt zurück.
# Usage: bash scripts/restart.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$ROOT_DIR/logs"
STARTUP_LOG="$ROOT_DIR/backend/logs/startup.log"

mkdir -p "$LOG_DIR" "$ROOT_DIR/backend/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$STARTUP_LOG"; }

log "=== DeerFlow restart START ==="

# ── IBKR_HOST aktualisieren ───────────────────────────────────────────────────

WINDOWS_IP=$(ip route | grep default | awk '{print $3}')
if [ -n "$WINDOWS_IP" ]; then
    sed -i "s/IBKR_HOST=.*/IBKR_HOST=$WINDOWS_IP/" "$ROOT_DIR/backend/.env"
    log "IBKR_HOST gesetzt auf $WINDOWS_IP"
fi

# ── Services stoppen ──────────────────────────────────────────────────────────

pkill -f "langgraph dev"            2>/dev/null && log "LangGraph gestoppt"  || true
pkill -f "uvicorn src.gateway.app"  2>/dev/null && log "Gateway gestoppt"    || true
pkill -f "next dev"                 2>/dev/null && log "Frontend gestoppt"   || true
nginx -c "$ROOT_DIR/docker/nginx/nginx.local.conf" -p "$ROOT_DIR" -s quit 2>/dev/null || true
sleep 1
pkill -9 nginx 2>/dev/null || true
log "Alle Services gestoppt"

sleep 2

# ── Config-Check ─────────────────────────────────────────────────────────────

if ! { [ -f "$ROOT_DIR/backend/config.yaml" ] || [ -f "$ROOT_DIR/config.yaml" ]; }; then
    log "FEHLER: config.yaml nicht gefunden – Abbruch"
    exit 1
fi

# ── LangGraph starten ─────────────────────────────────────────────────────────

log "Starte LangGraph..."
(cd "$ROOT_DIR/backend" && NO_COLOR=1 uv run langgraph dev \
    --no-browser --allow-blocking --no-reload \
    > "$LOG_DIR/langgraph.log" 2>&1) &

for i in $(seq 1 30); do
    sleep 2
    if curl -sf http://localhost:2024/ok > /dev/null 2>&1; then
        log "LangGraph OK (Port 2024)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log "WARNING: LangGraph nicht bereit nach 60s – prüfe $LOG_DIR/langgraph.log"
    fi
done

# ── Gateway starten ───────────────────────────────────────────────────────────

log "Starte Gateway API..."
(cd "$ROOT_DIR/backend" && uv run uvicorn src.gateway.app:app \
    --host 0.0.0.0 --port 8001 \
    > "$LOG_DIR/gateway.log" 2>&1) &

for i in $(seq 1 15); do
    sleep 2
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        log "Gateway OK (Port 8001)"
        break
    fi
    if [ "$i" -eq 15 ]; then
        log "WARNING: Gateway nicht bereit nach 30s – prüfe $LOG_DIR/gateway.log"
    fi
done

# ── Frontend starten ──────────────────────────────────────────────────────────

log "Starte Frontend..."
(cd "$ROOT_DIR/frontend" && pnpm run dev > "$LOG_DIR/frontend.log" 2>&1) &

for i in $(seq 1 30); do
    sleep 2
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        log "Frontend OK (Port 3000)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log "WARNING: Frontend nicht bereit nach 60s – prüfe $LOG_DIR/frontend.log"
    fi
done

# ── Nginx starten ─────────────────────────────────────────────────────────────

log "Starte Nginx..."
sudo nginx -c "$ROOT_DIR/docker/nginx/nginx.local.conf" -p "$ROOT_DIR" 2>/dev/null \
    || sudo nginx -s reload 2>/dev/null \
    || true

sleep 1
if curl -sf http://localhost:2026 > /dev/null 2>&1; then
    log "Nginx OK (Port 2026)"
else
    log "WARNING: Nginx nicht erreichbar – prüfe nginx-Konfiguration"
fi

# ── Fertig ────────────────────────────────────────────────────────────────────

log "=== DeerFlow restart END ==="
log "Frontend:  http://$(hostname -I | awk '{print $1}'):2026/workspace"
log "Tailscale: http://100.88.180.28:2026/workspace"
