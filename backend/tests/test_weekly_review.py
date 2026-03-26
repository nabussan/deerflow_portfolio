"""
Unit tests for weekly_review.py (v0.2)
Acceptance Criteria: SK-11 – Weekly Bull/Bear Review
"""
import asyncio as _asyncio
import sys
import logging
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

# ── Stub heavy dependencies before importing weekly_review ────────────────────

# ib_insync
_ib_stub = ModuleType("ib_insync")
_ib_stub.IB = MagicMock
_ib_stub.Stock = MagicMock
_ib_stub.MarketOrder = MagicMock
_ib_stub.LimitOrder = MagicMock
_ib_stub.Forex = MagicMock
sys.modules.setdefault("ib_insync", _ib_stub)

# dotenv
_dotenv_stub = ModuleType("dotenv")
_dotenv_stub.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv_stub)

# apscheduler
for _pkg in ["apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.blocking"]:
    sys.modules.setdefault(_pkg, ModuleType(_pkg))
sys.modules["apscheduler.schedulers.blocking"].BlockingScheduler = MagicMock  # type: ignore[attr-defined]

# langchain_openai – controllable fake LLM
_FAKE_BULL_RESPONSE: list[str] = ["🐂 BULL – AAPL:\n1. Starke Cashflows\n2. Marktführer\n3. Dividendenwachstum"]
_FAKE_BEAR_RESPONSE: list[str] = ["🐻 BEAR – AAPL:\n1. Bewertung zu hoch\n2. China-Risiko\n3. Sättigungsmarkt"]
_FAKE_JUDGE_RESPONSE: list[str] = ["VERDICT: HALTEN\nBEGRÜNDUNG: Solide Fundamentaldaten überwiegen.\nKONFIDENZ: HOCH"]

_llm_call_count = [0]

class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content

class _FakeChatOpenAI:
    def __init__(self, **kw):
        pass
    def invoke(self, prompt):
        # Alternate: 1st call = Bull, 2nd = Bear (per debate), 3rd = Judge
        count = _llm_call_count[0] % 3
        _llm_call_count[0] += 1
        if count == 0:
            return _FakeLLMResponse(_FAKE_BULL_RESPONSE[0])
        elif count == 1:
            return _FakeLLMResponse(_FAKE_BEAR_RESPONSE[0])
        else:
            return _FakeLLMResponse(_FAKE_JUDGE_RESPONSE[0])

_lco_stub = ModuleType("langchain_openai")
_lco_stub.ChatOpenAI = _FakeChatOpenAI
sys.modules.setdefault("langchain_openai", _lco_stub)

# src.tools.logger
_logger_stub = ModuleType("src.tools.logger")
_logger_stub.get_logger = lambda name: logging.getLogger(name)
sys.modules["src.tools.logger"] = _logger_stub

# src.tools.ibkr_connection
_mock_send_telegram = MagicMock()
_mock_get_conn = MagicMock()
def _ibkr_submit_impl(coro, timeout=30.0):
    return _asyncio.run(coro)

_mock_ibkr_submit = MagicMock(side_effect=_ibkr_submit_impl)
_ibkr_conn_stub = ModuleType("src.tools.ibkr_connection")
_ibkr_conn_stub.send_telegram = _mock_send_telegram
_ibkr_conn_stub.get_ibkr_connection = _mock_get_conn
_ibkr_conn_stub.ibkr_submit = _mock_ibkr_submit
sys.modules["src.tools.ibkr_connection"] = _ibkr_conn_stub

# src.community.tavily.tools
for _pkg in ["src.community", "src.community.tavily", "src.community.tavily.tools"]:
    sys.modules.setdefault(_pkg, ModuleType(_pkg))

# ── Load weekly_review directly ───────────────────────────────────────────────
_WR_PATH = Path(__file__).parent.parent / "src" / "tools" / "weekly_review.py"
_spec = importlib.util.spec_from_file_location("weekly_review_under_test", _WR_PATH)
wr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wr)  # type: ignore[union-attr]
# ─────────────────────────────────────────────────────────────────────────────


def _reset():
    _mock_send_telegram.reset_mock()
    _mock_get_conn.reset_mock()
    _llm_call_count[0] = 0
    # Ensure wr.llm always points to our fake regardless of sys.modules order
    wr.llm = _FakeChatOpenAI()


def _make_fake_position(symbol: str, currency: str = "USD", quantity: float = 10.0, avg_cost: float = 150.0):
    pos = MagicMock()
    pos.contract.symbol = symbol
    pos.contract.currency = currency
    pos.position = quantity
    pos.avgCost = avg_cost
    return pos


def _make_fake_ib(positions: list):
    """Erstellt einen fake IB-Mock mit awaitbarem reqPositionsAsync."""
    fake = MagicMock()
    fake.reqPositionsAsync = AsyncMock(return_value=None)
    fake.positions.return_value = positions
    return fake


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-01  bull_bear_debate() returns (bull, bear) tuple
# ══════════════════════════════════════════════════════════════════════════════

class TestBullBearDebate:
    """SK-11-01: bull_bear_debate() liefert zwei nicht-leere Strings zurück."""

    def test_returns_tuple_of_two_strings(self):
        _reset()
        bull, bear = wr.bull_bear_debate("AAPL", 10, 150.0, "Positive outlook")
        assert isinstance(bull, str) and len(bull) > 0
        assert isinstance(bear, str) and len(bear) > 0

    def test_bull_and_bear_differ(self):
        _reset()
        _FAKE_BULL_RESPONSE[0] = "🐂 BULL – TSLA:\n1. EV-Marktführer\n2. Robotaxi\n3. Energiespeicher"
        _FAKE_BEAR_RESPONSE[0] = "🐻 BEAR – TSLA:\n1. Hohe Bewertung\n2. Konkurrenz\n3. Musk-Ablenkung"
        bull, bear = wr.bull_bear_debate("TSLA", 5, 200.0, "Mixed news")
        assert bull != bear

    def test_llm_exception_returns_error_strings(self):
        """SK-11-01: LLM-Crash → kein unbehandelter Fehler, Error-Strings zurückgegeben."""
        _reset()
        original = wr.llm.invoke
        wr.llm.invoke = MagicMock(side_effect=RuntimeError("API down"))
        try:
            bull, bear = wr.bull_bear_debate("X", 1, 100.0, "some news")
        finally:
            wr.llm.invoke = original
        assert "Fehler" in bull or "Fehler" in bear


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-02  judge_debate() parses all 4 verdicts correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestJudgeDebate:
    """SK-11-02: judge_debate() parst HALTEN/AUFSTOCKEN/REDUZIEREN/VERKAUFEN korrekt."""

    def _judge(self, verdict: str, konfidenz: str = "HOCH") -> dict:
        _reset()
        original = wr.llm.invoke
        wr.llm.invoke = MagicMock(return_value=_FakeLLMResponse(
            f"VERDICT: {verdict}\nBEGRÜNDUNG: Test.\nKONFIDENZ: {konfidenz}"
        ))
        try:
            return wr.judge_debate("AAPL", "bull args", "bear args")
        finally:
            wr.llm.invoke = original

    def test_halten(self):
        r = self._judge("HALTEN")
        assert r["verdict"] == "HALTEN"
        assert r["konfidenz"] == "HOCH"
        assert len(r["begründung"]) > 0

    def test_aufstocken(self):
        r = self._judge("AUFSTOCKEN", "MITTEL")
        assert r["verdict"] == "AUFSTOCKEN"
        assert r["konfidenz"] == "MITTEL"

    def test_reduzieren(self):
        r = self._judge("REDUZIEREN", "NIEDRIG")
        assert r["verdict"] == "REDUZIEREN"

    def test_verkaufen(self):
        r = self._judge("VERKAUFEN", "HOCH")
        assert r["verdict"] == "VERKAUFEN"

    def test_default_verdict_on_missing_lines(self):
        """SK-11-02: Fehlende Zeilen → Defaults (HALTEN / MITTEL)."""
        _reset()
        original = wr.llm.invoke
        wr.llm.invoke = MagicMock(return_value=_FakeLLMResponse("BEGRÜNDUNG: Unklar."))
        try:
            r = wr.judge_debate("AMZN", "bull", "bear")
        finally:
            wr.llm.invoke = original
        assert r["verdict"] == "HALTEN"
        assert r["konfidenz"] == "MITTEL"

    def test_exception_returns_fehler_dict(self):
        """SK-11-02: LLM-Crash → strukturiertes Fehler-Dict, kein unbehandelter Fehler."""
        _reset()
        original = wr.llm.invoke
        wr.llm.invoke = MagicMock(side_effect=RuntimeError("API down"))
        try:
            r = wr.judge_debate("X", "bull", "bear")
        finally:
            wr.llm.invoke = original
        assert r["verdict"] == "FEHLER"
        assert "API down" in r["begründung"]


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-03  _format_debate_message() contains required fields
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatDebateMessage:
    """SK-11-03: Formatierte Nachricht enthält Symbol, Bull, Bear, Verdict."""

    def test_required_fields_present(self):
        verdict = {"verdict": "HALTEN", "begründung": "Solide Basis.", "konfidenz": "HOCH"}
        msg = wr._format_debate_message(
            "AAPL",
            "🐂 BULL – AAPL:\n1. Arg",
            "🐻 BEAR – AAPL:\n1. Arg",
            verdict,
        )
        assert "AAPL" in msg
        assert "🐂" in msg
        assert "🐻" in msg
        assert "HALTEN" in msg
        assert "HOCH" in msg
        assert "Solide Basis." in msg

    def test_emoji_mapping_verkaufen(self):
        verdict = {"verdict": "VERKAUFEN", "begründung": "Kritisch.", "konfidenz": "HOCH"}
        msg = wr._format_debate_message("X", "bull", "bear", verdict)
        assert "🔴" in msg

    def test_emoji_mapping_aufstocken(self):
        verdict = {"verdict": "AUFSTOCKEN", "begründung": "Stark.", "konfidenz": "MITTEL"}
        msg = wr._format_debate_message("X", "bull", "bear", verdict)
        assert "🟢" in msg

    def test_emoji_mapping_reduzieren(self):
        verdict = {"verdict": "REDUZIEREN", "begründung": "Risiko.", "konfidenz": "NIEDRIG"}
        msg = wr._format_debate_message("X", "bull", "bear", verdict)
        assert "🟠" in msg


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-04  run_weekly_review() – keine Positionen
# ══════════════════════════════════════════════════════════════════════════════

class TestRunWeeklyReviewNoPositions:
    """SK-11-04: Keine Positionen → Telegram-Info, kein Absturz."""

    def test_no_positions_sends_info_telegram(self):
        _reset()
        _mock_get_conn.return_value = _make_fake_ib([])
        wr.run_weekly_review()
        assert _mock_send_telegram.called
        msg = _mock_send_telegram.call_args[0][0]
        assert "Weekly Review" in msg or "Positionen" in msg


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-05  run_weekly_review() – volle Pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestRunWeeklyReviewWithPositions:
    """SK-11-05: Mit Positionen → Header + Debatten + Zusammenfassung via Telegram."""

    def _run_with_positions(self, symbols: list[str]):
        _reset()
        _FAKE_BULL_RESPONSE[0] = "🐂 BULL:\n1. Arg1\n2. Arg2\n3. Arg3"
        _FAKE_BEAR_RESPONSE[0] = "🐻 BEAR:\n1. Arg1\n2. Arg2\n3. Arg3"
        _FAKE_JUDGE_RESPONSE[0] = "VERDICT: HALTEN\nBEGRÜNDUNG: OK.\nKONFIDENZ: HOCH"
        _mock_get_conn.return_value = _make_fake_ib([_make_fake_position(s) for s in symbols])
        with patch.object(wr, "search_weekly_news", return_value="some weekly news"):
            wr.run_weekly_review()

    def test_sends_at_least_three_messages_for_one_position(self):
        """Header + 1 Debatte + Zusammenfassung = mindestens 3 Telegram-Nachrichten."""
        self._run_with_positions(["AAPL"])
        assert _mock_send_telegram.call_count >= 3

    def test_header_message_contains_position_count(self):
        self._run_with_positions(["AAPL", "TSLA"])
        first_msg = _mock_send_telegram.call_args_list[0][0][0]
        assert "2" in first_msg

    def test_summary_message_contains_symbol_and_verdict(self):
        self._run_with_positions(["MSFT"])
        # Letzte Nachricht ist die Zusammenfassung
        last_msg = _mock_send_telegram.call_args_list[-1][0][0]
        assert "MSFT" in last_msg
        assert "HALTEN" in last_msg

    def test_summary_contains_correct_emoji_for_halten(self):
        self._run_with_positions(["NVDA"])
        last_msg = _mock_send_telegram.call_args_list[-1][0][0]
        assert "🟡" in last_msg  # HALTEN emoji

    def test_debate_message_contains_bull_and_bear(self):
        self._run_with_positions(["AAPL"])
        # Zweite Nachricht (index 1) ist die Debatte
        debate_msg = _mock_send_telegram.call_args_list[1][0][0]
        assert "🐂" in debate_msg
        assert "🐻" in debate_msg

    def test_exception_in_single_position_does_not_abort_review(self):
        """SK-11-05: Fehler bei einem Symbol bricht nicht die gesamte Review ab."""
        _reset()
        _mock_get_conn.return_value = _make_fake_ib([
            _make_fake_position("AAPL"),
            _make_fake_position("TSLA"),
        ])

        call_count = [0]
        def patched_news(symbol):
            call_count[0] += 1
            if symbol == "AAPL":
                raise RuntimeError("News API down")
            return "good news for TSLA"

        with patch.object(wr, "search_weekly_news", side_effect=patched_news):
            wr.run_weekly_review()

        # Review muss trotzdem weiterlaufen und TSLA analysiert haben
        assert call_count[0] == 2
        assert _mock_send_telegram.called


# ══════════════════════════════════════════════════════════════════════════════
# SK-11-06  get_all_positions() – filtert leere Positionen heraus
# ══════════════════════════════════════════════════════════════════════════════

class TestGetAllPositions:
    """SK-11-06: Positionen mit quantity=0 werden nicht zurückgegeben."""

    def test_zero_quantity_positions_excluded(self):
        pos_zero = _make_fake_position("CLOSED", quantity=0.0)
        pos_open = _make_fake_position("AAPL", quantity=10.0)
        _mock_get_conn.return_value = _make_fake_ib([pos_zero, pos_open])
        result = wr.get_all_positions()
        symbols = [p["symbol"] for p in result]
        assert "CLOSED" not in symbols
        assert "AAPL" in symbols

    def test_ibkr_exception_returns_empty_list(self):
        _mock_get_conn.side_effect = RuntimeError("IBKR not connected")
        try:
            result = wr.get_all_positions()
        finally:
            _mock_get_conn.side_effect = None
        assert result == []
