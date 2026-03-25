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

WEEKLY_NOTIFY_HOUR = int(os.getenv("IBKR_WEEKLY_HOUR", "22"))
WEEKLY_NOTIFY_MINUTE = int(os.getenv("IBKR_WEEKLY_MINUTE", "0"))

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
                time.sleep(RECONNECT_INTERVAL)
                if not self.ib.isConnected():
                    logger.warning("Verbindung verloren, versuche Reconnect... (Versuch %d)", self._reconnect_tries + 1)
                    self._reconnect_tries += 1
                    success = self._connect()
                    if success:
                        send_telegram(
                            "✅ <b>IBKR Gateway</b>\n"
                            "Reconnected – Verbindung wiederhergestellt."
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
                if now.weekday() == 5 and now.hour == WEEKLY_NOTIFY_HOUR and now.minute == WEEKLY_NOTIFY_MINUTE:
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
