#!/usr/bin/env bash
# restart.sh – DeerFlow Backend + Frontend neu starten (auf W541/WSL2)
# Usage: bash scripts/restart.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$ROOT_DIR/backend/logs/startup.log"

mkdir -p "$ROOT_DIR/backend/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "=== DeerFlow restart START ==="

pkill -f "uvicorn src.main" 2>/dev/null && log "Backend gestoppt" || log "Backend lief nicht"
pkill -f "next dev"          2>/dev/null && log "Frontend gestoppt" || log "Frontend lief nicht"
sleep 2

log "Starte Backend..."
cd "$ROOT_DIR/backend"
nohup uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 \
  >> "$ROOT_DIR/backend/logs/backend.log" 2>&1 &
log "Backend gestartet (PID $!)"

log "Starte Frontend..."
cd "$ROOT_DIR"
nohup pnpm dev >> "$ROOT_DIR/backend/logs/frontend.log" 2>&1 &
log "Frontend gestartet (PID $!)"

sleep 5
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  log "Backend health check: OK"
else
  log "WARNING: Backend health check fehlgeschlagen – prüfe backend/logs/backend.log"
fi

log "=== DeerFlow restart END ==="
log "Tailscale: http://100.88.180.28:3000/workspace"
