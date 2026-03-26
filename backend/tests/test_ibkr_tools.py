"""
Unit-Tests für IBKR Tools (SK-02 bis SK-07).
Alle Tests mocken die ib_insync-Verbindung – kein echtes IB Gateway nötig.
"""

import asyncio
import math
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── Stub ib_insync before any real import ─────────────────────────────────────
_ib_stub = ModuleType("ib_insync")
_ib_stub.IB = MagicMock
_ib_stub.Stock = MagicMock
_ib_stub.Forex = MagicMock
_ib_stub.MarketOrder = MagicMock
_ib_stub.LimitOrder = MagicMock
sys.modules.setdefault("ib_insync", _ib_stub)

# Stub dotenv so load_dotenv("/home/python/...") doesn't fail
_dotenv_stub = ModuleType("dotenv")
_dotenv_stub.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv_stub)

# Stub logger module
_logger_stub = ModuleType("src.tools.logger")
_logger_stub.get_logger = lambda name: MagicMock()
sys.modules["src.tools.logger"] = _logger_stub


# ── Helper to build a fake IB object ──────────────────────────────────────────

def _make_ib(connected=True):
    ib = MagicMock()
    ib.isConnected.return_value = connected
    return ib


# ── Patch get_ibkr_connection globally ────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_validate():
    """Skip _validate_trading_mode() and ibkr_submit side-effects at module load.

    Coroutines that are thin async wrappers around synchronous ib methods (e.g.
    _req/_place/_cancel) must be *executed* so their return value reaches the
    caller.  Pure infrastructure coroutines (asyncio.sleep, ib mock async calls)
    are simply closed without running to keep tests fast.
    """
    with patch.dict("os.environ", {"IBKR_MODE": "paper", "IBKR_PORT": "4002"}):
        def _handle_coro(coro):
            if not asyncio.iscoroutine(coro):
                return None
            co_name = getattr(getattr(coro, "cr_code", None), "co_name", "") or ""
            # Skip library sleep and ib_insync async calls (they return nothing useful)
            if co_name in ("sleep",) or co_name.endswith("Async"):
                coro.close()
                return None
            # Run wrapper coroutines (_req, _place, _cancel …) on a fresh event loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with patch("src.tools.ibkr_tool.ibkr_submit", side_effect=_handle_coro):
            yield


# ─────────────────────────────────────────────────────────────────────────────
# SK-02  get_account_info
# ─────────────────────────────────────────────────────────────────────────────

class TestGetAccountInfo:
    """SK-02-01: Required keys present; SK-02-02: correct port addressing."""

    def _av(self, tag, currency, value):
        av = MagicMock()
        av.tag = tag
        av.currency = currency
        av.value = str(value)
        return av

    def test_required_keys_present(self):
        """SK-02-01: NetLiquidation, TotalCashValue, BuyingPower als Plain-Keys > 0."""
        ib = _make_ib()
        ib.accountValues.return_value = [
            self._av("NetLiquidation",  "BASE", 100_000),
            self._av("TotalCashValue",  "BASE",  80_000),
            self._av("BuyingPower",     "BASE", 160_000),
            self._av("UnrealizedPnL",   "BASE",   2_000),
        ]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_account_info
            result = get_account_info.invoke({})

        assert "error" not in result
        assert "NetLiquidation" in result
        assert "TotalCashValue" in result
        assert "BuyingPower" in result
        assert result["NetLiquidation"] > 0
        assert result["TotalCashValue"] > 0
        assert result["BuyingPower"] > 0

    def test_currency_fallback_usd(self):
        """SK-02-01: Falls back to USD when BASE absent."""
        ib = _make_ib()
        ib.accountValues.return_value = [
            self._av("NetLiquidation", "USD", 50_000),
            self._av("TotalCashValue", "USD", 40_000),
            self._av("BuyingPower",    "USD", 80_000),
        ]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_account_info
            result = get_account_info.invoke({})

        assert result["NetLiquidation"] == 50_000.0
        assert result["TotalCashValue"] == 40_000.0
        assert result["BuyingPower"] == 80_000.0

    def test_returns_error_on_exception(self):
        """SK-02-01 Fehlerfall: Exception → error-Key, kein Crash."""
        ib = _make_ib()
        ib.accountValues.side_effect = RuntimeError("connection lost")
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_account_info
            result = get_account_info.invoke({})
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# SK-03  get_positions
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPositions:
    """SK-03-01: Felder Symbol, Quantity (≠ 0), AvgCost; leeres Portfolio → []."""

    def _pos(self, symbol, qty, avg_cost, currency="USD"):
        pos = MagicMock()
        pos.contract.symbol = symbol
        pos.contract.secType = "STK"
        pos.contract.currency = currency
        pos.position = qty
        pos.avgCost = avg_cost
        return pos

    def test_required_fields_present(self):
        """SK-03-01: Felder Symbol, Quantity, AvgCost vorhanden und korrekt."""
        ib = _make_ib()
        ib.positions.return_value = [
            self._pos("AAPL", 100, 175.50),
            self._pos("MSFT",  50, 410.00),
        ]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_positions
            result = get_positions.invoke({})

        assert len(result) == 2
        assert result[0]["Symbol"] == "AAPL"
        assert result[0]["Quantity"] == 100
        assert result[0]["AvgCost"] == 175.50
        assert result[1]["Symbol"] == "MSFT"
        assert "error" not in result[0]

    def test_empty_portfolio_returns_empty_list(self):
        """SK-03-01: Leeres Portfolio → leere Liste, kein Fehler."""
        ib = _make_ib()
        ib.positions.return_value = []
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_positions
            result = get_positions.invoke({})
        assert result == []

    def test_quantity_nonzero(self):
        """SK-03-01: Quantity ≠ 0 für echte Positionen."""
        ib = _make_ib()
        ib.positions.return_value = [self._pos("TSLA", 10, 200.0)]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_positions
            result = get_positions.invoke({})
        assert result[0]["Quantity"] != 0


# ─────────────────────────────────────────────────────────────────────────────
# SK-04  get_market_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMarketData:
    """SK-04-01: Bid/Ask/Last > 0 während Handelszeiten; SK-04-02: market_closed."""

    def _ticker(self, bid, ask, last, close=150.0):
        t = MagicMock()
        t.bid = bid
        t.ask = ask
        t.last = last
        t.close = close
        t.high = MagicMock()
        t.low = MagicMock()
        t.volume = MagicMock()
        return t

    def test_valid_prices_during_trading_hours(self):
        """SK-04-01: bid, ask, last numerisch und > 0."""
        ib = _make_ib()
        ib.reqMktData.return_value = self._ticker(175.0, 175.1, 175.05)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_market_data
            result = get_market_data.invoke({"symbol": "AAPL"})

        assert "error" not in result
        assert result["bid"] == 175.0
        assert result["ask"] == 175.1
        assert result["last"] == 175.05
        assert "market_closed" not in result

    def test_market_closed_flag_when_no_live_prices(self):
        """SK-04-02: market_closed=True wenn bid/ask/last ungültig."""
        ib = _make_ib()
        ib.reqMktData.return_value = self._ticker(
            bid=float("nan"), ask=float("nan"), last=float("nan"), close=174.0
        )
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_market_data
            result = get_market_data.invoke({"symbol": "AAPL"})

        assert result.get("market_closed") is True
        assert result["close"] == 174.0

    def test_market_closed_when_prices_zero(self):
        """SK-04-02: market_closed=True wenn bid/ask/last = 0."""
        ib = _make_ib()
        ib.reqMktData.return_value = self._ticker(bid=0, ask=0, last=0, close=170.0)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_market_data
            result = get_market_data.invoke({"symbol": "AAPL"})

        assert result.get("market_closed") is True

    def test_no_crash_on_exception(self):
        """SK-04-02: Kein Crash bei Exception → error-Key."""
        ib = _make_ib()
        ib.reqMktData.side_effect = RuntimeError("timeout")
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_market_data
            result = get_market_data.invoke({"symbol": "AAPL"})
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# SK-05  place_order
# ─────────────────────────────────────────────────────────────────────────────

class TestPlaceOrder:
    """SK-05-01/02: Order platzieren; SK-05-03: Ungültige Parameter abweisen."""

    def _trade(self, order_id, status="Submitted"):
        trade = MagicMock()
        trade.order.orderId = order_id
        trade.orderStatus.status = status
        trade.orderStatus.filled = 0
        return trade

    def test_market_order_returns_positive_order_id(self):
        """SK-05-01: orderId > 0 für Market-Order."""
        ib = _make_ib()
        ib.placeOrder.return_value = self._trade(42)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": 100, "order_type": "MKT"
            })
        assert "error" not in result
        assert result["orderId"] == 42

    def test_limit_order_submitted_with_correct_price(self):
        """SK-05-02: Limit-Order mit korrektem Preis, Status Submitted."""
        ib = _make_ib()
        ib.placeOrder.return_value = self._trade(99, "Submitted")
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": 10, "order_type": "LMT", "limit_price": 180.0
            })
        assert "error" not in result
        assert result["status"] == "Submitted"

    def test_quantity_zero_rejected(self):
        """SK-05-03: Quantity=0 → strukturierte Fehlermeldung, keine Order."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection") as mock_conn:
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": 0, "order_type": "MKT"
            })
        assert "error" in result
        mock_conn.return_value.placeOrder.assert_not_called()

    def test_negative_quantity_rejected(self):
        """SK-05-03: Negative Quantity → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection") as mock_conn:
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": -5, "order_type": "MKT"
            })
        assert "error" in result
        mock_conn.return_value.placeOrder.assert_not_called()

    def test_negative_limit_price_rejected(self):
        """SK-05-03: Negativer Limitpreis → Fehler, keine Order."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection") as mock_conn:
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": 10, "order_type": "LMT", "limit_price": -1.0
            })
        assert "error" in result
        mock_conn.return_value.placeOrder.assert_not_called()

    def test_invalid_action_rejected(self):
        """SK-05-03: Ungültige Action → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection"):
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "HOLD",
                "quantity": 10, "order_type": "MKT"
            })
        assert "error" in result

    def test_lmt_without_price_rejected(self):
        """SK-05-03: LMT ohne limit_price → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection"):
            from src.tools.ibkr_tool import place_order
            result = place_order.invoke({
                "symbol": "AAPL", "action": "BUY",
                "quantity": 10, "order_type": "LMT"
            })
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# SK-06  get_open_orders
# ─────────────────────────────────────────────────────────────────────────────

class TestGetOpenOrders:
    """SK-06-01: Pflichtfelder; SK-06-02: Keine offene Order → leere Liste."""

    def _trade(self, order_id, symbol, action="BUY", qty=100, order_type="MKT", status="Submitted"):
        t = MagicMock()
        t.order.orderId = order_id
        t.contract.symbol = symbol
        t.order.action = action
        t.order.totalQuantity = qty
        t.order.orderType = order_type
        t.orderStatus.status = status
        return t

    def test_required_fields_present(self):
        """SK-06-01: orderId, Symbol, Action, Quantity, OrderType in jedem Eintrag."""
        ib = _make_ib()
        ib.openTrades.return_value = [self._trade(1, "AAPL"), self._trade(2, "MSFT")]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_open_orders
            result = get_open_orders.invoke({})

        assert len(result) == 2
        for entry in result:
            assert "orderId" in entry
            assert "symbol" in entry
            assert "action" in entry
            assert "quantity" in entry
            assert "orderType" in entry
            assert "error" not in entry

    def test_empty_when_no_open_orders(self):
        """SK-06-01: Keine offene Order → leere Liste."""
        ib = _make_ib()
        ib.openTrades.return_value = []
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_open_orders
            result = get_open_orders.invoke({})
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# SK-07  cancel_order
# ─────────────────────────────────────────────────────────────────────────────

class TestCancelOrder:
    """SK-07-01: Stornierung; SK-07-02: Nicht-existente Order → 'Order not found'."""

    def _trade(self, order_id, symbol="AAPL"):
        t = MagicMock()
        t.order.orderId = order_id
        t.contract.symbol = symbol
        return t

    def test_cancel_existing_order(self):
        """SK-07-01: Vorhandene Order wird storniert, keine Exception."""
        ib = _make_ib()
        trade = self._trade(42)
        ib.openTrades.return_value = [trade]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import cancel_order
            result = cancel_order.invoke({"order_id": 42})

        assert "error" not in result
        assert result["orderId"] == 42
        ib.cancelOrder.assert_called_once_with(trade.order)

    def test_cancel_nonexistent_order_returns_order_not_found(self):
        """SK-07-02: Nicht-existente Order → 'Order not found', kein Crash."""
        ib = _make_ib()
        ib.openTrades.return_value = []
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import cancel_order
            result = cancel_order.invoke({"order_id": 9999})

        assert result.get("error") == "Order not found"

    def test_cancel_does_not_affect_other_orders(self):
        """SK-07-02: Stornierung hat keine Seiteneffekte auf andere Orders."""
        ib = _make_ib()
        t42 = self._trade(42)
        t99 = self._trade(99)
        ib.openTrades.return_value = [t42, t99]
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import cancel_order
            cancel_order.invoke({"order_id": 42})

        # Only t42.order was cancelled, not t99.order
        ib.cancelOrder.assert_called_once_with(t42.order)

# ─────────────────────────────────────────────────────────────────────────────
# SK-08  get_forex_rate
# ─────────────────────────────────────────────────────────────────────────────

class TestGetForexRate:
    """get_forex_rate: Kurs, market_closed-Flag, Fehlerbehandlung."""

    def _ticker(self, bid, ask, close=1.05, high=1.06, low=1.04):
        t = MagicMock()
        t.bid = bid
        t.ask = ask
        t.close = close
        t.high = high
        t.low = low
        return t

    def test_returns_bid_ask_mid_during_trading_hours(self):
        """Bid/ask/mid vorhanden und korrekt berechnet."""
        ib = _make_ib()
        ib.reqMktData.return_value = self._ticker(bid=1.0820, ask=1.0822)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_forex_rate
            result = get_forex_rate.invoke({"pair": "EURUSD"})

        assert "error" not in result
        assert result["pair"] == "EURUSD"
        assert result["bid"] == pytest.approx(1.0820)
        assert result["ask"] == pytest.approx(1.0822)
        assert result["mid"] == pytest.approx(1.0821, abs=1e-5)

    def test_market_closed_flag_when_no_prices(self):
        """market_closed=True wenn bid/ask ungültig."""
        ib = _make_ib()
        ib.reqMktData.return_value = self._ticker(bid=float("nan"), ask=float("nan"), close=1.05)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_forex_rate
            result = get_forex_rate.invoke({"pair": "EURUSD"})

        assert result.get("market_closed") is True
        assert result["bid"] is None
        assert result["ask"] is None
        assert result["mid"] is None

    def test_error_on_exception(self):
        """Exception → error-Key, kein Crash."""
        ib = _make_ib()
        ib.reqMktData.side_effect = RuntimeError("timeout")
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import get_forex_rate
            result = get_forex_rate.invoke({"pair": "EURUSD"})
        assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# SK-09  place_forex_order
# ─────────────────────────────────────────────────────────────────────────────

class TestPlaceForexOrder:
    """place_forex_order: Market/Limit-Order, Validierung."""

    def _trade(self, order_id=1, status="Submitted"):
        t = MagicMock()
        t.order.orderId = order_id
        t.orderStatus.status = status
        t.orderStatus.filled = 0
        return t

    def test_market_buy_returns_order_id(self):
        """BUY MKT → orderId > 0."""
        ib = _make_ib()
        ib.placeOrder.return_value = self._trade(77)
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({"pair": "EURUSD", "action": "BUY", "quantity": 10000})

        assert "error" not in result
        assert result["orderId"] == 77
        assert result["pair"] == "EURUSD"
        assert result["action"] == "BUY"

    def test_limit_sell_submitted(self):
        """SELL LMT → status Submitted."""
        ib = _make_ib()
        ib.placeOrder.return_value = self._trade(88, "Submitted")
        with patch("src.tools.ibkr_tool.get_ibkr_connection", return_value=ib):
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({
                "pair": "GBPUSD", "action": "SELL",
                "quantity": 5000, "order_type": "LMT", "limit_price": 1.2700
            })

        assert "error" not in result
        assert result["status"] == "Submitted"

    def test_invalid_action_rejected(self):
        """Ungültige Action → Fehler, keine Order."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection") as mock_conn:
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({"pair": "EURUSD", "action": "HOLD", "quantity": 1000})
        assert "error" in result
        mock_conn.return_value.placeOrder.assert_not_called()

    def test_zero_quantity_rejected(self):
        """quantity=0 → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection") as mock_conn:
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({"pair": "EURUSD", "action": "BUY", "quantity": 0})
        assert "error" in result
        mock_conn.return_value.placeOrder.assert_not_called()

    def test_lmt_without_price_rejected(self):
        """LMT ohne limit_price → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection"):
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({"pair": "EURUSD", "action": "BUY", "quantity": 1000, "order_type": "LMT"})
        assert "error" in result

    def test_negative_limit_price_rejected(self):
        """Negativer Limitkurs → Fehler."""
        with patch("src.tools.ibkr_tool.get_ibkr_connection"):
            from src.tools.ibkr_tool import place_forex_order
            result = place_forex_order.invoke({
                "pair": "EURUSD", "action": "BUY",
                "quantity": 1000, "order_type": "LMT", "limit_price": -1.0
            })
        assert "error" in result
