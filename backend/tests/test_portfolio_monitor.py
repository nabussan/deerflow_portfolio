"""
Unit tests for portfolio_monitor.py
Covers SK-08-04, SK-09-01…SK-09-05, SK-10-01, SK-10-03
"""
import sys
import logging
import importlib.util
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

# ── Stub heavy dependencies before importing portfolio_monitor ─────────────

# ib_insync – needs Stock/MarketOrder/LimitOrder for ibkr_tool.py (loaded via src.tools.__init__)
_ib_stub = ModuleType("ib_insync")
_ib_stub.IB = MagicMock
_ib_stub.Stock = MagicMock
_ib_stub.MarketOrder = MagicMock
_ib_stub.LimitOrder = MagicMock
sys.modules.setdefault("ib_insync", _ib_stub)

# dotenv
_dotenv_stub = ModuleType("dotenv")
_dotenv_stub.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv_stub)

# apscheduler
for _pkg in ["apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.blocking"]:
    sys.modules.setdefault(_pkg, ModuleType(_pkg))
sys.modules["apscheduler.schedulers.blocking"].BlockingScheduler = MagicMock  # type: ignore[attr-defined]

# langchain_openai – fake ChatOpenAI whose response we control
_FAKE_LLM_RESPONSE: list[str] = [""]

class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content

class _FakeChatOpenAI:
    def __init__(self, **kw):
        pass
    def invoke(self, prompt):
        return _FakeLLMResponse(_FAKE_LLM_RESPONSE[0])

_lco_stub = ModuleType("langchain_openai")
_lco_stub.ChatOpenAI = _FakeChatOpenAI
sys.modules.setdefault("langchain_openai", _lco_stub)

# src.tools.logger
_logger_stub = ModuleType("src.tools.logger")
_logger_stub.get_logger = lambda name: logging.getLogger(name)
sys.modules["src.tools.logger"] = _logger_stub

# src.tools.ibkr_connection – mock send_telegram and get_ibkr_connection
_mock_send_telegram = MagicMock()
_mock_get_conn = MagicMock()
_ibkr_conn_stub = ModuleType("src.tools.ibkr_connection")
_ibkr_conn_stub.send_telegram = _mock_send_telegram
_ibkr_conn_stub.get_ibkr_connection = _mock_get_conn
sys.modules["src.tools.ibkr_connection"] = _ibkr_conn_stub

# src.community.tavily.tools (used inside search_news at call time, not module level)
for _pkg in ["src.community", "src.community.tavily", "src.community.tavily.tools"]:
    sys.modules.setdefault(_pkg, ModuleType(_pkg))


# ── Load portfolio_monitor directly (bypasses src.tools.__init__ chain) ─────
_PM_PATH = Path(__file__).parent.parent / "src" / "tools" / "portfolio_monitor.py"
_spec = importlib.util.spec_from_file_location("portfolio_monitor_under_test", _PM_PATH)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)   # type: ignore[union-attr]
# ─────────────────────────────────────────────────────────────────────────────


def _set_llm_response(text: str):
    _FAKE_LLM_RESPONSE[0] = text


def _make_fake_position(symbol: str, currency: str = "USD", quantity: float = 100.0, avg_cost: float = 150.0):
    pos = MagicMock()
    pos.contract.symbol = symbol
    pos.contract.currency = currency
    pos.position = quantity
    pos.avgCost = avg_cost
    return pos


# ══════════════════════════════════════════════════════════════════════════════
# SK-08-04  LLM returns structured result
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzePositionParsing:
    """SK-08-04: Grok-Antwort enthält eine der vier Kategorien oder NO_SIGNAL."""

    def test_management_signal_parsed(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: MANAGEMENT\n"
            "ZUSAMMENFASSUNG: Der CEO trat überraschend zurück.\n"
            "HANDLUNGSEMPFEHLUNG: SOFORT VERKAUFEN"
        )
        result = pm.analyze_position("AAPL", "CEO resigned")
        assert result["kritisch"] is True
        assert result["kategorie"] == "MANAGEMENT"
        assert len(result["zusammenfassung"]) > 0

    def test_hype_signal_parsed(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: HYPE\n"
            "ZUSAMMENFASSUNG: Viraler Reddit-Pump erkannt.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        result = pm.analyze_position("GME", "Reddit going crazy")
        assert result["kritisch"] is True
        assert result["kategorie"] == "HYPE"

    def test_fundamentals_signal_parsed(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: FUNDAMENTALS\n"
            "ZUSAMMENFASSUNG: Umsatzrückgang und Guidance-Senkung.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        result = pm.analyze_position("TSLA", "Revenue miss")
        assert result["kritisch"] is True
        assert result["kategorie"] == "FUNDAMENTALS"

    def test_sector_signal_parsed(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: SECTOR\n"
            "ZUSAMMENFASSUNG: Neue EU-Regulierung trifft den Bankensektor hart.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        result = pm.analyze_position("JPM", "Banking regulation")
        assert result["kritisch"] is True
        assert result["kategorie"] == "SECTOR"

    def test_no_signal_parsed(self):
        _set_llm_response(
            "KRITISCH: NEIN\nKATEGORIE: NO_SIGNAL\n"
            "ZUSAMMENFASSUNG: Keine kritischen Signale erkannt.\n"
            "HANDLUNGSEMPFEHLUNG: KEINE AKTION"
        )
        result = pm.analyze_position("MSFT", "Earnings in line")
        assert result["kritisch"] is False
        assert result["kategorie"] == "NO_SIGNAL"

    def test_default_kategorie_on_missing_line(self):
        """SK-08-04: If LLM omits KATEGORIE line, default is NO_SIGNAL."""
        _set_llm_response("KRITISCH: NEIN\nZUSAMMENFASSUNG: Alles ok.\nHANDLUNGSEMPFEHLUNG: KEINE AKTION")
        result = pm.analyze_position("AMZN", "boring news")
        assert result["kategorie"] == "NO_SIGNAL"

    def test_exception_returns_error_dict(self):
        """SK-08-04: LLM crash → structured error dict, no unhandled exception."""
        original = pm.llm.invoke
        pm.llm.invoke = MagicMock(side_effect=RuntimeError("API down"))
        try:
            result = pm.analyze_position("X", "whatever")
        finally:
            pm.llm.invoke = original
        assert "fehler" in result
        assert result["kritisch"] is False


# ══════════════════════════════════════════════════════════════════════════════
# SK-09  Critical Signal Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestCriticalSignalDetection:
    """SK-09-01…SK-09-05: Signal detection and NO_SIGNAL false-positive guard."""

    def test_sk09_01_management_signal(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: MANAGEMENT\n"
            "ZUSAMMENFASSUNG: CEO trat zurück wegen Bilanzskandal.\n"
            "HANDLUNGSEMPFEHLUNG: SOFORT VERKAUFEN"
        )
        r = pm.analyze_position("AAPL", "CEO steps down amid accounting scandal")
        assert r["kritisch"] is True
        assert r["kategorie"] == "MANAGEMENT"

    def test_sk09_02_hype_signal(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: HYPE\n"
            "ZUSAMMENFASSUNG: Aktie viral auf Reddit und X.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        r = pm.analyze_position("GME", "Stock trending on Reddit r/wallstreetbets")
        assert r["kritisch"] is True
        assert r["kategorie"] == "HYPE"

    def test_sk09_03_fundamentals_signal(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: FUNDAMENTALS\n"
            "ZUSAMMENFASSUNG: Umsatzrückgang und Guidance-Senkung bestätigt.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        r = pm.analyze_position("TSLA", "Revenue down 20%, guidance slashed")
        assert r["kritisch"] is True
        assert r["kategorie"] == "FUNDAMENTALS"

    def test_sk09_04_sector_signal(self):
        _set_llm_response(
            "KRITISCH: JA\nKATEGORIE: SECTOR\n"
            "ZUSAMMENFASSUNG: Neue EU-Regulierung trifft den Bankensektor.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN"
        )
        r = pm.analyze_position("DB", "EU banking regulation shock")
        assert r["kritisch"] is True
        assert r["kategorie"] == "SECTOR"

    def test_sk09_05_no_false_positive_on_neutral_news(self):
        _set_llm_response(
            "KRITISCH: NEIN\nKATEGORIE: NO_SIGNAL\n"
            "ZUSAMMENFASSUNG: Quartalszahlen im Rahmen der Erwartungen.\n"
            "HANDLUNGSEMPFEHLUNG: KEINE AKTION"
        )
        r = pm.analyze_position("MSFT", "Quarterly results in line with estimates")
        assert r["kritisch"] is False
        assert r["kategorie"] == "NO_SIGNAL"


# ══════════════════════════════════════════════════════════════════════════════
# SK-10  Telegram Alert content and NO_SIGNAL suppression
# ══════════════════════════════════════════════════════════════════════════════

class TestTelegramAlert:
    """SK-10-01: Alert contains Symbol, Kategorie, Zusammenfassung, Timestamp.
       SK-10-03: No alert sent for NO_SIGNAL."""

    def _run_with_one_us_position(self, llm_response: str, symbol: str = "AAPL"):
        _set_llm_response(llm_response)
        fake_ib = MagicMock()
        fake_ib.positions.return_value = [_make_fake_position(symbol, currency="USD")]
        _mock_get_conn.return_value = fake_ib
        _mock_send_telegram.reset_mock()
        with patch.object(pm, "search_news", return_value="some news"):
            pm.run_monitor("US")

    def test_sk10_01_alert_contains_required_fields(self):
        """SK-10-01: Symbol, Kategorie, Zusammenfassung and Timestamp all present."""
        self._run_with_one_us_position(
            "KRITISCH: JA\nKATEGORIE: MANAGEMENT\n"
            "ZUSAMMENFASSUNG: CEO trat zurück.\n"
            "HANDLUNGSEMPFEHLUNG: SOFORT VERKAUFEN",
            symbol="AAPL",
        )
        assert _mock_send_telegram.called, "send_telegram was not called"
        msg = _mock_send_telegram.call_args[0][0]

        assert "AAPL" in msg, f"Symbol missing. Got: {msg}"
        assert "MANAGEMENT" in msg, f"Kategorie missing. Got: {msg}"
        assert "CEO trat zurück" in msg, f"Zusammenfassung missing. Got: {msg}"
        today = datetime.now().strftime("%d.%m.%Y")
        assert today in msg, f"Timestamp missing. Got: {msg}"

    def test_sk10_03_no_alert_on_no_signal(self):
        """SK-10-03: NO_SIGNAL → send_telegram must NOT be called."""
        self._run_with_one_us_position(
            "KRITISCH: NEIN\nKATEGORIE: NO_SIGNAL\n"
            "ZUSAMMENFASSUNG: Alles normal.\n"
            "HANDLUNGSEMPFEHLUNG: KEINE AKTION"
        )
        _mock_send_telegram.assert_not_called()

    def test_sk10_03_no_alert_when_kritisch_nein(self):
        """SK-10-03 variant: kritisch=NEIN with any category → no alert."""
        self._run_with_one_us_position(
            "KRITISCH: NEIN\nKATEGORIE: HYPE\n"
            "ZUSAMMENFASSUNG: Leichter Hype, unkritisch.\n"
            "HANDLUNGSEMPFEHLUNG: KEINE AKTION"
        )
        _mock_send_telegram.assert_not_called()

    def test_alert_uses_siren_emoji_for_sell(self):
        """run_monitor uses 🚨 emoji when SOFORT VERKAUFEN."""
        self._run_with_one_us_position(
            "KRITISCH: JA\nKATEGORIE: MANAGEMENT\n"
            "ZUSAMMENFASSUNG: Sofort handeln.\n"
            "HANDLUNGSEMPFEHLUNG: SOFORT VERKAUFEN",
        )
        msg = _mock_send_telegram.call_args[0][0]
        assert "🚨" in msg

    def test_alert_uses_warning_emoji_for_beobachten(self):
        """run_monitor uses ⚠️ emoji when BEOBACHTEN."""
        self._run_with_one_us_position(
            "KRITISCH: JA\nKATEGORIE: HYPE\n"
            "ZUSAMMENFASSUNG: Beobachtungswürdig.\n"
            "HANDLUNGSEMPFEHLUNG: BEOBACHTEN",
        )
        msg = _mock_send_telegram.call_args[0][0]
        assert "⚠️" in msg
