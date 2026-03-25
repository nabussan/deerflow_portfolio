"""
IBKR Tool für DeerFlow 2.0
Nutzt persistente Verbindung via IBKRConnectionManager.
Alle ib_insync-Coroutinen laufen über ibkr_submit() auf dem dedizierten Loop.
"""

import asyncio
import math

from ib_insync import Forex, Stock, MarketOrder, LimitOrder
from langchain_core.tools import tool
from src.tools.ibkr_connection import get_ibkr_connection, ibkr_submit
import logging


def _ibkr_sleep(seconds: float) -> None:
    """Sleep on the ib_insync event loop so incoming data is processed."""
    ibkr_submit(asyncio.sleep(seconds))

logger = logging.getLogger(__name__)


def _require_connected():
    """Returns connected IB instance or raises ConnectionError immediately."""
    ib = get_ibkr_connection()
    if not ib.isConnected():
        raise ConnectionError("IBKR Gateway nicht verbunden")
    return ib


@tool
def get_account_info() -> dict:
    """Gibt Kontostand, Buying Power und PnL des IBKR Paper Accounts zurück."""
    try:
        ib = _require_connected()
        tags = ["NetLiquidation", "TotalCashValue", "BuyingPower", "UnrealizedPnL", "RealizedPnL"]
        # Collect all values grouped by tag; prefer BASE, then USD, then EUR
        raw: dict[str, dict[str, float]] = {}
        for av in ib.accountValues():
            if av.tag in tags and av.currency in ("BASE", "USD", "EUR"):
                raw.setdefault(av.tag, {})[av.currency] = float(av.value)
        result = {}
        for tag, by_currency in raw.items():
            # Pick BASE > USD > EUR for the canonical key
            result[tag] = by_currency.get("BASE") or by_currency.get("USD") or next(iter(by_currency.values()))
            # Also keep per-currency breakdown
            result.update({f"{tag}_{cur}": val for cur, val in by_currency.items()})
        return result
    except Exception as e:
        return {"error": str(e)}


@tool
def get_positions() -> list[dict]:
    """Gibt alle offenen Positionen im Paper Account zurück."""
    try:
        ib = _require_connected()
        ibkr_submit(ib.reqPositionsAsync())
        return [{
            "Symbol": pos.contract.symbol,
            "secType": pos.contract.secType,
            "currency": pos.contract.currency,
            "Quantity": pos.position,
            "AvgCost": round(pos.avgCost, 4),
        } for pos in ib.positions()]
    except Exception as e:
        return [{"error": str(e)}]


@tool
def get_market_data(symbol: str, exchange: str = "SMART", currency: str = "USD") -> dict:
    """
    Gibt aktuelle Marktdaten für ein Symbol zurück.
    Args:
        symbol: Tickersymbol, z.B. 'AAPL', 'SPY', 'RHM'
        exchange: Börse, z.B. 'SMART', 'XETRA' (default: SMART)
        currency: Währung, z.B. 'USD', 'EUR' (default: USD)
    """
    try:
        ib = _require_connected()
        contract = Stock(symbol, exchange, currency)
        ibkr_submit(ib.qualifyContractsAsync(contract))
        # reqMktData calls Client.sendMsg → asyncio.get_event_loop() internally;
        # must run on the dedicated ibkr-loop thread to avoid "no current event loop" error.
        async def _req():
            return ib.reqMktData(contract, "", False, False)
        ticker = ibkr_submit(_req())
        _ibkr_sleep(2)

        def _valid(v) -> bool:
            return v is not None and not math.isnan(v) and v > 0

        bid = ticker.bid if _valid(ticker.bid) else None
        ask = ticker.ask if _valid(ticker.ask) else None
        last = ticker.last if _valid(ticker.last) else None
        market_closed = not any([bid, ask, last])

        result = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "close": ticker.close,
            "high": ticker.high,
            "low": ticker.low,
            "volume": ticker.volume,
        }
        if market_closed:
            result["market_closed"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


@tool
def place_order(
    symbol: str,
    action: str,
    quantity: int,
    order_type: str = "MKT",
    limit_price: float = None,
    exchange: str = "SMART",
    currency: str = "USD",
) -> dict:
    """
    Platziert eine Order im IBKR Paper Account.
    Args:
        symbol: Tickersymbol, z.B. 'AAPL', 'SPY'
        action: 'BUY' oder 'SELL'
        quantity: Anzahl der Aktien
        order_type: 'MKT' oder 'LMT' (default: MKT)
        limit_price: Limitpreis (nur bei LMT)
        exchange: Börse (default: SMART)
        currency: Währung (default: USD)
    """
    if action not in ("BUY", "SELL"):
        return {"error": "action muss 'BUY' oder 'SELL' sein"}
    if quantity == 0:
        return {"error": "Quantity darf nicht 0 sein"}
    if quantity < 0:
        return {"error": "Quantity muss positiv sein"}
    if order_type == "LMT" and limit_price is None:
        return {"error": "limit_price erforderlich bei LMT"}
    if limit_price is not None and limit_price <= 0:
        return {"error": "limit_price muss größer als 0 sein"}
    try:
        ib = _require_connected()
        contract = Stock(symbol, exchange, currency)
        ibkr_submit(ib.qualifyContractsAsync(contract))
        order = MarketOrder(action, quantity) if order_type == "MKT" else LimitOrder(action, quantity, limit_price)
        # placeOrder calls Client.sendMsg → must run on dedicated ibkr-loop thread.
        async def _place():
            return ib.placeOrder(contract, order)
        trade = ibkr_submit(_place())
        _ibkr_sleep(1)
        return {
            "orderId": trade.order.orderId,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "orderType": order_type,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_open_orders() -> list[dict]:
    """Gibt alle offenen Orders zurück."""
    try:
        ib = _require_connected()
        return [{
            "orderId": t.order.orderId,
            "symbol": t.contract.symbol,
            "action": t.order.action,
            "quantity": t.order.totalQuantity,
            "orderType": t.order.orderType,
            "status": t.orderStatus.status,
        } for t in ib.openTrades()]
    except Exception as e:
        return [{"error": str(e)}]


@tool
def cancel_order(order_id: int) -> dict:
    """
    Storniert eine offene Order.
    Args:
        order_id: ID der zu stornierenden Order
    """
    try:
        ib = _require_connected()
        target = next((t for t in ib.openTrades() if t.order.orderId == order_id), None)
        if target is None:
            return {"error": "Order not found"}
        # cancelOrder calls Client.sendMsg → must run on dedicated ibkr-loop thread.
        async def _cancel():
            ib.cancelOrder(target.order)
        ibkr_submit(_cancel())
        _ibkr_sleep(1)
        return {"orderId": order_id, "status": "Storniert", "symbol": target.contract.symbol}
    except Exception as e:
        return {"error": str(e)}


@tool
def get_forex_rate(pair: str) -> dict:
    """
    Gibt den aktuellen Wechselkurs für ein Währungspaar zurück.
    Args:
        pair: Währungspaar, z.B. 'EURUSD', 'GBPUSD', 'USDJPY'
    Returns:
        bid, ask, mid-Kurs sowie close/high/low des Vortages.
    """
    try:
        ib = _require_connected()
        contract = Forex(pair)
        async def _req():
            return ib.reqMktData(contract, "", False, False)
        ticker = ibkr_submit(_req())
        _ibkr_sleep(2)

        def _valid(v) -> bool:
            return v is not None and not math.isnan(v) and v > 0

        bid = ticker.bid if _valid(ticker.bid) else None
        ask = ticker.ask if _valid(ticker.ask) else None
        mid = round((bid + ask) / 2, 6) if bid and ask else None

        result = {
            "pair": pair,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "close": ticker.close if _valid(ticker.close) else None,
            "high": ticker.high if _valid(ticker.high) else None,
            "low": ticker.low if _valid(ticker.low) else None,
        }
        if not any([bid, ask]):
            result["market_closed"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


@tool
def place_forex_order(
    pair: str,
    action: str,
    quantity: float,
    order_type: str = "MKT",
    limit_price: float = None,
) -> dict:
    """
    Platziert eine Forex-Order (Währungstausch) im IBKR Paper Account.
    Args:
        pair: Währungspaar, z.B. 'EURUSD', 'GBPUSD'
        action: 'BUY' (Basiswährung kaufen) oder 'SELL' (Basiswährung verkaufen)
        quantity: Betrag in der Basiswährung, z.B. 10000 für 10.000 EUR bei EURUSD
        order_type: 'MKT' oder 'LMT' (default: MKT)
        limit_price: Limitkurs (nur bei LMT), z.B. 1.0850
    """
    if action not in ("BUY", "SELL"):
        return {"error": "action muss 'BUY' oder 'SELL' sein"}
    if quantity <= 0:
        return {"error": "quantity muss größer als 0 sein"}
    if order_type == "LMT" and limit_price is None:
        return {"error": "limit_price erforderlich bei LMT"}
    if limit_price is not None and limit_price <= 0:
        return {"error": "limit_price muss größer als 0 sein"}
    try:
        ib = _require_connected()
        contract = Forex(pair)
        order = MarketOrder(action, quantity) if order_type == "MKT" else LimitOrder(action, quantity, limit_price)
        async def _place():
            return ib.placeOrder(contract, order)
        trade = ibkr_submit(_place())
        _ibkr_sleep(1)
        return {
            "orderId": trade.order.orderId,
            "pair": pair,
            "action": action,
            "quantity": quantity,
            "orderType": order_type,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
        }
    except Exception as e:
        return {"error": str(e)}


IBKR_TOOLS = [
    get_account_info,
    get_positions,
    get_market_data,
    place_order,
    get_open_orders,
    cancel_order,
    get_forex_rate,
    place_forex_order,
]
