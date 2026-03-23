#!/usr/bin/env bash
# setup_v011.sh – DeerFlow Portfolio v0.1.1 Setup
# Ausführen auf P53 im deer-flow Verzeichnis:
#   bash setup_v011.sh
#
# Was dieses Script tut:
#   1. dev-Branch anlegen (falls nicht vorhanden)
#   2. Neue Dateien schreiben (logger.py, restart.sh, DEVGUIDE.md)
#   3. Bestehende Dateien ersetzen (ibkr_connection.py, portfolio_monitor.py,
#      .env.example, CHANGELOG.md)
#   4. Berechtigungen setzen
#   5. Git commit + push

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   DeerFlow Portfolio – Setup v0.1.1          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. dev-Branch ─────────────────────────────────────────────────────────────
echo "▶ Branch setup..."
if git show-ref --quiet refs/heads/dev; then
  git checkout dev
  git pull origin dev 2>/dev/null || true
else
  git checkout -b dev
  git push -u origin dev
fi
echo "  ✅ Branch: dev"

# ── 2. Verzeichnisse ──────────────────────────────────────────────────────────
mkdir -p backend/src/tools
mkdir -p backend/logs
mkdir -p scripts

# ══════════════════════════════════════════════════════════════════════════════
# NEUE DATEI: backend/src/tools/logger.py
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe backend/src/tools/logger.py..."
cat > backend/src/tools/logger.py << 'PYEOF'
"""
Centralized logging configuration for DeerFlow Portfolio.
Import this module in any component that needs structured logging.

Usage:
    from src.tools.logger import get_logger
    logger = get_logger("portfolio_monitor")
    logger.info("Monitor started")
    logger.error("Connection failed", exc_info=True)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Returns a named logger with:
    - RotatingFileHandler → logs/<name>.log  (5 MB, 3 backups)
    - StreamHandler       → stdout

    Already-configured loggers are returned as-is (idempotent).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    fh = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger
PYEOF
echo "  ✅ logger.py"

# ══════════════════════════════════════════════════════════════════════════════
# ERSETZT: backend/src/tools/ibkr_connection.py
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe backend/src/tools/ibkr_connection.py..."
cat > backend/src/tools/ibkr_connection.py << 'PYEOF'
"""
IBKR Connection Manager
- Persistente Verbindung zu IB Gateway
- Auto-Reconnect bei Trennung
- Wöchentliche Telegram-Benachrichtigung (Samstag)
- Telegram-Alert falls Reconnect scheitert
"""

import asyncio
import os
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
load_dotenv("/home/python/deer-flow/backend/.env")
from ib_insync import IB

# ── Logging (v0.1.1) ──────────────────────────────────────────────────────────
from src.tools.logger import get_logger
logger = get_logger("ibkr_connection")

# ── Konfiguration ─────────────────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))
IBKR_MODE = os.getenv("IBKR_MODE", "paper").lower()
CLIENT_ID = 10
RECONNECT_INTERVAL = 30
MAX_RECONNECT_TRIES = 5

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Paper/Live Safety Guard (v0.1.1) ──────────────────────────────────────────
def _validate_trading_mode() -> None:
    if IBKR_MODE == "live":
        confirmed = os.getenv("IBKR_LIVE_CONFIRMED", "false").lower()
        if confirmed != "true":
            raise RuntimeError(
                "Live trading mode requested but IBKR_LIVE_CONFIRMED is not 'true'.\n"
                "Set IBKR_LIVE_CONFIRMED=true in backend/.env to proceed."
            )
        if IBKR_PORT != 4001:
            raise RuntimeError(
                f"IBKR_MODE=live but IBKR_PORT={IBKR_PORT} (expected 4001).\n"
                "Fix the port mismatch before proceeding."
            )
        logger.warning("⚠️  LIVE TRADING MODE ACTIVE | host=%s port=%d", IBKR_HOST, IBKR_PORT)
    elif IBKR_MODE == "paper":
        if IBKR_PORT != 4002:
            logger.warning(
                "IBKR_MODE=paper but IBKR_PORT=%d (expected 4002) – proceeding anyway",
                IBKR_PORT,
            )
        logger.info("Paper trading mode | host=%s port=%d", IBKR_HOST, IBKR_PORT)
    else:
        raise ValueError(f"Unknown IBKR_MODE='{IBKR_MODE}'. Use 'paper' or 'live'.")

_validate_trading_mode()
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(message: str):
    """Sendet eine Telegram-Nachricht."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram nicht konfiguriert")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        logger.info("Telegram gesendet: %s", message[:80])
    except Exception as e:
        logger.error("Telegram Fehler: %s", e, exc_info=True)


class IBKRConnectionManager:
    """Singleton Connection Manager für IB Gateway."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.ib = IB()
        self._connected = False
        self._reconnect_tries = 0
        self._monitor_thread = None
        self._weekly_thread = None
        self._setup_event_loop()
        self._connect()
        self._start_monitor()
        self._start_weekly_notification()

    def _setup_event_loop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                asyncio.set_event_loop(asyncio.new_event_loop())
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _connect(self) -> bool:
        try:
            self._setup_event_loop()
            if self.ib.isConnected():
                self.ib.disconnect()
            self.ib.connect(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID, timeout=15)
            self._connected = True
            self._reconnect_tries = 0
            logger.info("✅ IBKR Gateway verbunden | host=%s port=%d", IBKR_HOST, IBKR_PORT)
            return True
        except Exception as e:
            self._connected = False
            logger.error("❌ IBKR Verbindung fehlgeschlagen: %s", e, exc_info=True)
            return False

    def get_connection(self) -> IB:
        """Gibt die aktive IB-Verbindung zurück."""
        if not self.ib.isConnected():
            logger.warning("Verbindung verloren, reconnecte...")
            self._connect()
        return self.ib

    def _start_monitor(self):
        """Startet den Verbindungs-Monitor in einem Background-Thread."""
        def monitor():
            while True:
                time.sleep(60)
                if not self.ib.isConnected():
                    logger.warning("Verbindung verloren, versuche Reconnect... (Versuch %d)", self._reconnect_tries + 1)
                    self._reconnect_tries += 1
                    success = self._connect()
                    if success:
                        send_telegram(
                            "✅ <b>IBKR Gateway</b>\n"
                            "Verbindung wiederhergestellt."
                        )
                    elif self._reconnect_tries >= MAX_RECONNECT_TRIES:
                        logger.error("Reconnect nach %d Versuchen fehlgeschlagen", MAX_RECONNECT_TRIES)
                        send_telegram(
                            "🚨 <b>IBKR Gateway – Manuelle Aktion nötig!</b>\n\n"
                            f"Reconnect nach {MAX_RECONNECT_TRIES} Versuchen fehlgeschlagen.\n"
                            "Bitte IB Gateway auf Windows neu starten und neu anmelden."
                        )
                        self._reconnect_tries = 0

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    def _start_weekly_notification(self):
        """Sendet jeden Samstag um 22:00 eine Warnung vor der Gateway-Zwangstrennung."""
        def weekly_check():
            while True:
                now = datetime.now()
                if now.weekday() == 5 and now.hour == 22 and now.minute == 0:
                    logger.info("Wöchentliche Samstag-Benachrichtigung gesendet")
                    send_telegram(
                        "⚠️ <b>IBKR Gateway – Wöchentlicher Hinweis</b>\n\n"
                        "IB Gateway wird heute Nacht (Samstag) neu gestartet.\n"
                        "Die Verbindung wird kurzzeitig unterbrochen.\n"
                        "Der Auto-Reconnect versucht die Verbindung wiederherzustellen.\n\n"
                        "Falls nötig: IB Gateway auf Windows manuell neu starten."
                    )
                time.sleep(60)

        self._weekly_thread = threading.Thread(target=weekly_check, daemon=True)
        self._weekly_thread.start()


# Globale Singleton-Instanz
_manager = None
_manager_lock = threading.Lock()


def get_ibkr_connection() -> IB:
    """Gibt die persistente IBKR-Verbindung zurück."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = IBKRConnectionManager()
    return _manager.get_connection()
PYEOF
echo "  ✅ ibkr_connection.py"

# ══════════════════════════════════════════════════════════════════════════════
# ERSETZT: backend/src/tools/portfolio_monitor.py
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe backend/src/tools/portfolio_monitor.py..."
cat > backend/src/tools/portfolio_monitor.py << 'PYEOF'
"""
Portfolio Monitor Agent
Läuft täglich um 08:00, 15:00 und 21:00
Prüft Positionen auf kritische Signale und sendet Telegram-Alerts.
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from apscheduler.schedulers.blocking import BlockingScheduler

from src.tools.ibkr_connection import get_ibkr_connection, send_telegram
from src.tools.logger import get_logger  # v0.1.1

load_dotenv("/home/python/deer-flow/backend/.env")

logger = get_logger("portfolio_monitor")  # v0.1.1

# LLM via Grok
llm = ChatOpenAI(
    model="grok-4-1-fast",
    base_url="https://api.x.ai/v1",
    api_key=os.getenv("XAI_API_KEY"),
)

CRITICAL_CRITERIA = """
Bewerte ob eine der folgenden kritischen Bedingungen zutrifft:

1. MANAGEMENT: Negative Nachrichten über CEO/CFO/Management 
   (Rücktritt, Skandal, Betrug, Insiderverkäufe in großem Umfang)
   
2. HYPE/SENTIMENT: Starke Anzeichen für irrationalen Hype 
   (viral auf X/Twitter, Reddit-Pump, extreme Kursziele von Influencern)
   
3. FUNDAMENTALS: Verschlechterung der Fundamentaldaten
   (Umsatzrückgang, sinkende Bruttomarge, negativer FCF-Trend, 
   Gewinnwarnung, Guidance-Senkung)
   
4. SEKTOR: Negative externe Einflüsse auf den Sektor
   (neue Regulierung, Zölle, Rohstoffpreisschock, 
   Konkurrent mit disruptiver Ankündigung)

Antworte NUR mit:
KRITISCH: [JA/NEIN]
KATEGORIE: [MANAGEMENT/HYPE/FUNDAMENTALS/SEKTOR/KEINE]
ZUSAMMENFASSUNG: [max. 2 Sätze auf Deutsch]
HANDLUNGSEMPFEHLUNG: [SOFORT VERKAUFEN/BEOBACHTEN/KEINE AKTION]
"""


def get_positions_for_market(market: str) -> list[dict]:
    """Filtert Positionen nach Markt (EU/US/ASIA)."""
    try:
        ib = get_ibkr_connection()
        ib.reqPositions()
        ib.sleep(1)
        positions = []
        for pos in ib.positions():
            currency = pos.contract.currency
            if market == "EU" and currency == "EUR":
                positions.append({"symbol": pos.contract.symbol, "currency": currency,
                                   "position": pos.position, "avgCost": pos.avgCost})
            elif market == "US" and currency == "USD":
                positions.append({"symbol": pos.contract.symbol, "currency": currency,
                                   "position": pos.position, "avgCost": pos.avgCost})
            elif market == "ASIA" and currency in ("HKD", "JPY", "SGD", "AUD"):
                positions.append({"symbol": pos.contract.symbol, "currency": currency,
                                   "position": pos.position, "avgCost": pos.avgCost})
        logger.info("Positionen geladen: %d Symbole für Markt %s", len(positions), market)
        return positions
    except Exception as e:
        logger.error("Fehler beim Abrufen der Positionen für %s: %s", market, e, exc_info=True)
        return []


def search_news(symbol: str) -> str:
    """Sucht aktuelle News für ein Symbol via Tavily."""
    try:
        from src.community.tavily.tools import web_search_tool
        results = web_search_tool.invoke({
            "query": f"{symbol} stock news today negative",
            "max_results": 5,
        })
        logger.info("News gefunden für %s: %d Zeichen", symbol, len(str(results)))
        return str(results)
    except Exception as e:
        logger.error("News-Suche Fehler für %s: %s", symbol, e, exc_info=True)
        return f"Keine News gefunden für {symbol}"


def analyze_position(symbol: str, news: str) -> dict:
    """Analysiert News auf kritische Signale via LLM."""
    try:
        prompt = f"""
Symbol: {symbol}
Aktuelle News (letzte 24h):
{news}

{CRITICAL_CRITERIA}
"""
        response = llm.invoke(prompt)
        text = response.content
        lines = text.strip().split("\n")
        result = {
            "symbol": symbol,
            "kritisch": False,
            "kategorie": "KEINE",
            "zusammenfassung": "",
            "empfehlung": "KEINE AKTION",
        }
        for line in lines:
            if line.startswith("KRITISCH:"):
                result["kritisch"] = "JA" in line.upper()
            elif line.startswith("KATEGORIE:"):
                result["kategorie"] = line.split(":", 1)[1].strip()
            elif line.startswith("ZUSAMMENFASSUNG:"):
                result["zusammenfassung"] = line.split(":", 1)[1].strip()
            elif line.startswith("HANDLUNGSEMPFEHLUNG:"):
                result["empfehlung"] = line.split(":", 1)[1].strip()
        logger.info("Analyse %s: kritisch=%s kategorie=%s empfehlung=%s",
                    symbol, result["kritisch"], result["kategorie"], result["empfehlung"])
        return result
    except Exception as e:
        logger.error("Analyse Fehler für %s: %s", symbol, e, exc_info=True)
        return {"symbol": symbol, "kritisch": False, "fehler": str(e)}


def run_monitor(market: str):
    """Hauptfunktion: Prüft alle Positionen des jeweiligen Marktes."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    logger.info("=== Portfolio Monitor START | market=%s | %s ===", market, now)
    try:
        positions = get_positions_for_market(market)
        if not positions:
            logger.warning("Keine %s-Positionen gefunden – Monitor-Run übersprungen", market)
            return
        alerts = []
        for pos in positions:
            symbol = pos["symbol"]
            logger.info("Analysiere %s...", symbol)
            try:
                news = search_news(symbol)
                analysis = analyze_position(symbol, news)
                if analysis.get("kritisch"):
                    emoji = "🚨" if analysis["empfehlung"] == "SOFORT VERKAUFEN" else "⚠️"
                    alerts.append(
                        f"{emoji} <b>{symbol}</b>\n"
                        f"Kategorie: {analysis['kategorie']}\n"
                        f"{analysis['zusammenfassung']}\n"
                        f"→ {analysis['empfehlung']}"
                    )
            except Exception:
                logger.error("Fehler bei Symbol %s", symbol, exc_info=True)
        if alerts:
            message = (
                f"🔔 <b>Portfolio Alert – {market} ({now})</b>\n\n"
                + "\n\n".join(alerts)
            )
            send_telegram(message)
            logger.info("%d Alert(s) gesendet für %s", len(alerts), market)
        else:
            logger.info("Keine kritischen Signale für %s-Positionen", market)
    except Exception:
        logger.error("Monitor-Run fehlgeschlagen für %s", market, exc_info=True)
    finally:
        logger.info("=== Portfolio Monitor END | market=%s ===", market)


def main():
    scheduler = BlockingScheduler(timezone="Europe/Berlin")
    scheduler.add_job(lambda: run_monitor("EU"),   "cron", hour=8,  minute=0)
    scheduler.add_job(lambda: run_monitor("US"),   "cron", hour=15, minute=0)
    scheduler.add_job(lambda: run_monitor("ASIA"), "cron", hour=21, minute=0)
    logger.info("Portfolio Monitor Scheduler gestartet")
    logger.info("Läuft täglich um 08:00 (EU), 15:00 (US), 21:00 (ASIA)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Portfolio Monitor gestoppt")


if __name__ == "__main__":
    main()
PYEOF
echo "  ✅ portfolio_monitor.py"

# ══════════════════════════════════════════════════════════════════════════════
# ERSETZT: backend/.env.example
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe backend/.env.example..."
cat > backend/.env.example << 'EOF'
# ─────────────────────────────────────────────
# DeerFlow Portfolio – backend/.env.example
# Copy to backend/.env and fill in your values.
# backend/.env is in .gitignore – never commit it.
# ─────────────────────────────────────────────

# LLM
XAI_API_KEY=
GOOGLE_API_KEY=

# Broker (IB Gateway)
# Windows IP from WSL2: ip route | grep default | awk '{print $3}'
IBKR_HOST=172.18.240.1
IBKR_PORT=4002             # Paper: 4002 | Live: 4001

# SAFETY GUARD – Trading mode
# "paper" = safe default, no confirmation needed
# "live"  = requires IBKR_LIVE_CONFIRMED=true AND IBKR_PORT=4001
IBKR_MODE=paper
# IBKR_LIVE_CONFIRMED=true   ← uncomment ONLY when intentionally going live

# News
TAVILY_API_KEY=

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Optional
ALPHA_VANTAGE_API_KEY=
BRAVE_API_KEY=
EOF
echo "  ✅ .env.example"

# ══════════════════════════════════════════════════════════════════════════════
# NEUE DATEI: scripts/restart.sh
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe scripts/restart.sh..."
cat > scripts/restart.sh << 'SHEOF'
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
SHEOF
chmod +x scripts/restart.sh
echo "  ✅ scripts/restart.sh"

# ══════════════════════════════════════════════════════════════════════════════
# NEUE DATEI: DEVGUIDE.md
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe DEVGUIDE.md..."
cat > DEVGUIDE.md << 'MDEOF'
# DeerFlow Portfolio – Developer Guide

> Ergänzung zu README.md für v0.1.1  
> Ziel: In 6 Monaten ohne Rätseln weitermachen können.

---

## Tailscale – Verbindung von P53 zu W541

### Einmalig einrichten

1. Tailscale auf beiden Geräten: https://tailscale.com/download
2. Auf beiden einloggen: `tailscale up`
3. Tailscale-IP des W541 im Admin Panel notieren: https://login.tailscale.com/admin/machines  
   Format: `100.xx.xxx.xx` – ändert sich nicht, auch nach Neustart nicht.

### Verbindung herstellen

```bash
# Erreichbarkeit prüfen
tailscale ping 100.88.180.28

# SSH auf W541 (WSL2)
ssh python@100.88.180.28

# VS Code Remote SSH – ~/.ssh/config auf P53:
#   Host w541
#       HostName 100.88.180.28
#       User python
# Dann: F1 → "Remote-SSH: Connect to Host" → w541
```

### DeerFlow-Frontend

```
http://100.88.180.28:3000/workspace
```

### Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| `tailscale ping` timeout | W541 schläft / Tailscale gestoppt | W541 aufwecken, `tailscale up` |
| Port 3000 nicht erreichbar | WSL2-IP hat sich geändert | Task Scheduler → `wsl-portproxy` neu starten |
| IBKR nicht verbunden | IB Gateway Sa.-Nacht-Disconnect | IB Gateway manuell neu einloggen (~1 Min.) |

---

## Dev-Workflow: P53 → W541

### Branch-Strategie

| Branch | Zweck | Läuft auf |
|---|---|---|
| `portfolio` | Production | W541 |
| `dev` | Entwicklung | P53 |

```bash
# P53: Feature entwickeln
git checkout dev
# ... Änderungen ...
git add -p                  # selektiv – niemals .env stagen!
git commit -m "feat: ..."
git push origin dev

# Nach Test auf W541: merge
git checkout portfolio
git merge dev
git push origin portfolio

# W541: ausrollen
git pull origin portfolio
bash scripts/restart.sh
```

---

## Logging

Log-Dateien: `backend/logs/` (in `.gitignore`)

| Datei | Inhalt |
|---|---|
| `portfolio_monitor.log` | Monitor-Runs, Signale, Telegram-Status |
| `ibkr_connection.log` | Verbindungsstatus, Trading-Mode, Reconnects |
| `startup.log` | restart.sh Ausgaben |
| `backend.log` | Uvicorn / Backend stdout |
| `frontend.log` | Next.js / Frontend stdout |

```bash
tail -f backend/logs/portfolio_monitor.log   # live mitverfolgen
grep ERROR backend/logs/portfolio_monitor.log
tail -50 backend/logs/ibkr_connection.log
```

Rotation: 5 MB / 3 Backups → max. ~20 MB pro Komponente.

---

## Paper vs. Live – Safety Guard

```env
# Paper (default, sicher)
IBKR_MODE=paper
IBKR_PORT=4002

# Live (beide Flags erforderlich)
IBKR_MODE=live
IBKR_PORT=4001
IBKR_LIVE_CONFIRMED=true
```

Beim Start geprüft: Mismatch oder fehlende Confirmation → RuntimeError, kein Start.

---

## Komponenten-Übersicht

```
backend/src/tools/
├── logger.py                   ← Zentrales Logging (v0.1.1)
├── ibkr_connection.py          ← IB Gateway + Safety Guard (v0.1.1)
├── ibkr_tool.py                ← 6 LangChain Tools
└── portfolio_monitor.py        ← Scheduled News Monitor (v0.1.1)

scripts/
├── wsl-startup.sh              ← WSL2 Autostart
├── windows-portproxy.ps1       ← Windows Port-Proxy
└── restart.sh                  ← DeerFlow Neustart (v0.1.1)

backend/
├── .env                        ← Secrets (NICHT in Git)
├── .env.example                ← Template (in Git)
└── logs/                       ← Log-Dateien (NICHT in Git)
```

---

## Technische Schulden (nicht vergessen)

- [ ] IB Gateway Auto-Login nach Saturday-Disconnect
- [ ] Health-check Endpoint im Backend (`/health`)
- [ ] APScheduler-Logs in `logs/` leiten
- [ ] `git add -p` konsequent nutzen – nie versehentlich `.env` committen
MDEOF
echo "  ✅ DEVGUIDE.md"

# ══════════════════════════════════════════════════════════════════════════════
# ERSETZT: CHANGELOG.md
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ Schreibe CHANGELOG.md..."
cat > CHANGELOG.md << 'MDEOF'
# Changelog

## [0.1.1] - 2026-03-23

### Added
- `backend/src/tools/logger.py` – Centralized logging (RotatingFileHandler, 5 MB / 3 backups)
- Structured logging in `portfolio_monitor.py` – start/end, positions, signals, Telegram, tracebacks
- Structured logging in `ibkr_connection.py` – connection events, mode, reconnects
- Paper/Live safety guard in `ibkr_connection.py` – live mode requires `IBKR_MODE=live` + `IBKR_PORT=4001` + `IBKR_LIVE_CONFIRMED=true`
- `scripts/restart.sh` – one-command restart with startup logging
- `DEVGUIDE.md` – Tailscale setup, dev→prod workflow, logging reference, component map

### Changed
- `backend/.env.example` – added `IBKR_MODE` and `IBKR_LIVE_CONFIRMED` variables

## [0.1.0] - 2026-03-23

### Added
- IBKR Gateway connection via `ib_insync` (persistent, auto-reconnect)
- 6 LangChain trading tools: `get_account_info`, `get_positions`, `get_market_data`, `place_order`, `get_open_orders`, `cancel_order`
- Portfolio Monitor: daily news scan (08:00 EU / 15:00 US / 21:00 Asia)
- Critical signal detection: Management, Hype, Fundamentals, Sector
- Telegram alerts for critical portfolio signals
- Weekly IB Gateway reconnect notification via Telegram
- WSL2 autostart via `/etc/wsl.conf`
- Windows port-proxy script + scheduled task for remote access
- Tailscale integration for secure remote access
- `install.sh` for automated WSL2 setup
- `INSTALL.md` with full setup guide

### Infrastructure
- W541 ThinkPad as dedicated server (Windows 10, WSL2, Ubuntu 24.04)
- IB Gateway (Paper Account, Port 4002)
- DeerFlow 2.0 + LangGraph + Grok 4.1 Fast (xAI)
- Telegram Bot for alerts

### Known Issues
- WSL2-IP changes on reboot → port-proxy script runs automatically via Task Scheduler
- IB Gateway weekly forced disconnect (Saturday night) → manual re-login required (~1 min)

### Roadmap → v0.2
- Weekly position review (Bull/Bear debate)
- Macro indicator tracker (CPI, NFP, ISM, Fed)
- Alpha Vantage integration
- Automated port-proxy on WSL2 IP change
MDEOF
echo "  ✅ CHANGELOG.md"

# ── 3. Git commit + push ──────────────────────────────────────────────────────
echo ""
echo "▶ Git status:"
git status --short

echo ""
echo "▶ Staging (alle neuen/geänderten Dateien außer .env)..."
git add \
  backend/src/tools/logger.py \
  backend/src/tools/ibkr_connection.py \
  backend/src/tools/portfolio_monitor.py \
  backend/.env.example \
  scripts/restart.sh \
  DEVGUIDE.md \
  CHANGELOG.md

echo ""
echo "▶ Commit..."
git commit -m "feat(v0.1.1): logging, paper/live guard, devguide, restart.sh"

echo ""
echo "▶ Push origin dev..."
git push origin dev

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ✅ Setup v0.1.1 abgeschlossen              ║"
echo "║                                              ║"
echo "║   Nächste Schritte auf W541:                 ║"
echo "║   git pull origin dev                        ║"
echo "║   bash scripts/restart.sh                   ║"
echo "║   tail -f backend/logs/ibkr_connection.log  ║"
echo "╚══════════════════════════════════════════════╝"