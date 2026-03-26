"""
IBKR Connection Manager
- Persistente Verbindung zu IB Gateway
- Dedizierter Event-Loop-Thread für ib_insync (löst asyncio-Konflikt mit LangGraph)
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
load_dotenv()
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
# Backoff-Sequenz: Wartezeit in Sekunden zwischen Reconnect-Versuchen
_BACKOFF = [30, 60, 120, 300, 600]
ALERT_COOLDOWN = 3600  # Sekunden zwischen "Manuelle Aktion"-Alarmen
# Saturday-Night-Fenster: Sa HH:MM – So HH:MM (konfigurierbar)
SAT_NIGHT_START_HOUR = int(os.getenv("SAT_NIGHT_START_HOUR", "22"))
SAT_NIGHT_END_HOUR   = int(os.getenv("SAT_NIGHT_END_HOUR",   "12"))  # Sonntag

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


def _is_saturday_night() -> bool:
    """Samstag SAT_NIGHT_START_HOUR – Sonntag SAT_NIGHT_END_HOUR: IB-Zwangsdisconnect-Fenster."""
    now = datetime.now()
    return (
        (now.weekday() == 5 and now.hour >= SAT_NIGHT_START_HOUR)
        or (now.weekday() == 6 and now.hour < SAT_NIGHT_END_HOUR)
    )


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
    """Singleton Connection Manager für IB Gateway.

    Betreibt ib_insync in einem dedizierten Event-Loop-Thread, der dauerhaft
    läuft (run_forever). Alle ib_insync-Coroutinen werden über
    asyncio.run_coroutine_threadsafe() an diesen Loop übergeben. So gibt es
    keinen Konflikt mit LangGraphs eigenem asyncio-Loop.
    """

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
        self._last_connect_attempt: float = 0.0   # epoch seconds
        self._connect_cooldown: float = 10.0       # seconds between retries
        self._last_alert_time: float = 0.0         # epoch seconds
        self._saturday_alerted: bool = False       # einmaliger Alert pro Saturday-Disconnect
        self._connect_lock = threading.Lock()
        self._monitor_thread = None
        self._weekly_thread = None

        # Dedicated event loop – keeps running forever in its own daemon thread.
        # ib_insync's socket reader and all async operations run on this loop.
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ibkr-loop"
        )
        self._loop_thread.start()

        self._connect()
        self._start_monitor()
        self._start_weekly_notification()

    # ── Event loop ────────────────────────────────────────────────────────────

    def _run_loop(self):
        """Thread target: set and run the dedicated ib_insync event loop."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro, timeout: float = 30.0):
        """Submit a coroutine to the ib_insync event loop and block until done.

        Safe to call from any thread (including LangGraph's async thread pool).
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ── Connect / Disconnect ──────────────────────────────────────────────────

    def _connect(self) -> bool:
        if not self._connect_lock.acquire(blocking=False):
            logger.debug("Connect bereits aktiv (Lock), überspringe Versuch")
            return False
        try:
            now = time.time()
            if now - self._last_connect_attempt < self._connect_cooldown:
                logger.debug("Connect-Cooldown aktiv, überspringe Verbindungsversuch")
                return False
            self._last_connect_attempt = now
            try:
                if self.ib.isConnected():
                    self.ib.disconnect()
                self.submit(
                    self.ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID, timeout=10),
                    timeout=15,
                )
                self._connected = True
                logger.info("✅ IBKR Gateway verbunden | host=%s port=%d", IBKR_HOST, IBKR_PORT)
                return True
            except Exception as e:
                self._connected = False
                logger.error("❌ IBKR Verbindung fehlgeschlagen: %s", e, exc_info=True)
                return False
        finally:
            self._connect_lock.release()

    def get_connection(self) -> IB:
        """Gibt die aktive IB-Verbindung zurück.

        Löst einen einmaligen Reconnect-Versuch aus wenn die Verbindung fehlt.
        Persistente Reconnects übernimmt der Monitor-Thread.
        """
        if not self.ib.isConnected():
            logger.warning("Verbindung nicht aktiv, versuche Reconnect...")
            self._connect()
        return self.ib

    # ── Monitor ───────────────────────────────────────────────────────────────

    def _start_monitor(self):
        """Startet den Verbindungs-Monitor in einem Background-Thread.

        Reconnect-Strategie:
        - Exponentieller Backoff: 30 → 60 → 120 → 300 → 600 s
        - Nach Erschöpfung: stille Retries alle 10 min (kein Alarm-Dauerfeuer)
        - Alert-Cooldown: "Manuelle Aktion"-Alarm max. 1× pro Stunde
        - Saturday-Night-Modus (Sa 22:00 – So 04:00): angepasster Alert-Text
        """
        def monitor():
            sleep_time = RECONNECT_INTERVAL
            while True:
                time.sleep(sleep_time)
                if not self.ib.isConnected():
                    self._reconnect_tries += 1
                    logger.warning(
                        "Verbindung verloren, versuche Reconnect... (Versuch %d)",
                        self._reconnect_tries,
                    )
                    success = self._connect()
                    if success:
                        self._reconnect_tries = 0
                        self._saturday_alerted = False
                        sleep_time = RECONNECT_INTERVAL
                        send_telegram(
                            "✅ <b>IBKR Gateway</b>\n"
                            "Reconnected – Verbindung wiederhergestellt."
                        )
                    else:
                        # Backoff: längere Pausen nach jedem Fehlversuch
                        idx = min(self._reconnect_tries - 1, len(_BACKOFF) - 1)
                        sleep_time = _BACKOFF[idx]

                        if _is_saturday_night():
                            # Saturday-Disconnect: einmaliger Alert, danach Stille bis Reconnect
                            if not self._saturday_alerted:
                                self._saturday_alerted = True
                                logger.warning("Saturday-Night-Disconnect erkannt – nur einmaliger Alert")
                                send_telegram(
                                    "🌙 <b>IBKR Gateway – Samstag-Disconnect</b>\n\n"
                                    "IB Gateway hat die Verbindung für den wöchentlichen Neustart getrennt.\n"
                                    "Auto-Reconnect läuft im Hintergrund – bis zum Re-Login keine weiteren Alarme.\n\n"
                                    "➡️ Bitte nach dem Gateway-Neustart neu anmelden.\n"
                                    "Die Verbindung wird danach automatisch wiederhergestellt."
                                )
                        else:
                            # Normaler Disconnect: Alert mit Cooldown
                            now = time.time()
                            if now - self._last_alert_time >= ALERT_COOLDOWN:
                                self._last_alert_time = now
                                logger.error(
                                    "Reconnect nach %d Versuchen fehlgeschlagen", self._reconnect_tries
                                )
                                send_telegram(
                                    "🚨 <b>IBKR Gateway – Manuelle Aktion nötig!</b>\n\n"
                                    f"Reconnect nach {self._reconnect_tries} Versuchen fehlgeschlagen.\n"
                                    "Bitte IB Gateway auf Windows neu starten und neu anmelden."
                                )
                else:
                    # Verbindung steht – Backoff zurücksetzen
                    if self._reconnect_tries > 0:
                        logger.info("Verbindung wiederhergestellt, Backoff zurückgesetzt")
                        self._reconnect_tries = 0
                        self._saturday_alerted = False
                    sleep_time = RECONNECT_INTERVAL

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


# ── Globale Singleton-Instanz ──────────────────────────────────────────────────
_manager: IBKRConnectionManager | None = None
_manager_lock = threading.Lock()


def _get_manager() -> IBKRConnectionManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = IBKRConnectionManager()
    return _manager


def get_ibkr_connection() -> IB:
    """Gibt die persistente IBKR-Verbindung zurück."""
    return _get_manager().get_connection()


def ibkr_submit(coro, timeout: float = 30.0):
    """Führt eine ib_insync-Coroutine auf dem dedizierten Loop aus.

    Kann sicher aus beliebigen Threads aufgerufen werden.
    """
    return _get_manager().submit(coro, timeout=timeout)
