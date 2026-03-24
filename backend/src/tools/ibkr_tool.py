import asyncio
"""
IBKR Tool für DeerFlow 2.0
Nutzt persistente Verbindung via IBKRConnectionManager.
"""

from ib_insync import Stock, MarketOrder, LimitOrder
from langchain_core.tools import tool
from src.tools.ibkr_connection import get_ibkr_connection, run_ib
import logging

logger = logging.getLogger(__name__)


@tool
def get_account_info() -> dict:
    """Gibt Kontostand, Buying Power und PnL des IBKR Paper Accounts zurück."""
    try:
        ib = get_ibkr_connection()
        tags = ["NetLiquidation", "TotalCashValue", "BuyingPower", "UnrealizedPnL", "RealizedPnL"]
        result = {}
        for av in ib.accountValues():
            if av.tag in tags and av.currency in ("EUR", "USD", "BASE"):
                result[f"{av.tag}_{av.currency}"] = float(av.value)
        return result
    except Exception as e:
        return {"error": str(e)}


@tool
def get_positions() -> list[dict]:
    """Gibt alle offenen Positionen im Paper Account zurück."""
    try:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        ib = get_ibkr_connection()
        ib.reqPositions()
        __import__("time").sleep(1)
        return [{
            "symbol": pos.contract.symbol,
            "secType": pos.contract.secType,
            "currency": pos.contract.currency,
            "position": pos.position,
            "avgCost": round(pos.avgCost, 4),
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
    import threading, queue, asyncio, os
    from ib_insync import IB as _IB, Stock as _Stock
    result_queue = queue.Queue()
    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ib = _IB()
            ib.connect(os.getenv("IBKR_HOST","172.24.128.1"), int(os.getenv("IBKR_PORT","7496")), clientId=20, timeout=10)
            contract = _Stock(symbol, exchange, currency)
            ib.qualifyContracts(contract)
            bars = ib.reqHistoricalData(contract, "", "2 D", "1 day", "TRADES", useRTH=True)
            ib.disconnect()
            if bars:
                bar = bars[-1]
                result_queue.put({"symbol":symbol,"close":bar.close,"open":bar.open,"high":bar.high,"low":bar.low,"volume":bar.volume,"date":str(bar.date)})
            else:
                result_queue.put({"error": f"Keine Daten für {symbol}"})
        except Exception as e:
            result_queue.put({"error": str(e)})
        finally:
            loop.close()
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    try:
        return result_queue.get(timeout=20)
    except Exception:
        return {"error": "Timeout"}


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
    if order_type == "LMT" and limit_price is None:
        return {"error": "limit_price erforderlich bei LMT"}
    try:
        ib = get_ibkr_connection()
        contract = Stock(symbol, exchange, currency)
        ib.qualifyContracts(contract)
        order = MarketOrder(action, quantity) if order_type == "MKT" else LimitOrder(action, quantity, limit_price)
        trade = ib.placeOrder(contract, order)
        __import__("time").sleep(1)
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
        ib = get_ibkr_connection()
        ib.reqAllOpenOrders()
        __import__("time").sleep(1)
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
        ib = get_ibkr_connection()
        target = next((t for t in ib.openTrades() if t.order.orderId == order_id), None)
        if target is None:
            return {"error": f"Order {order_id} nicht gefunden"}
        ib.cancelOrder(target.order)
        __import__("time").sleep(1)
        return {"orderId": order_id, "status": "Storniert", "symbol": target.contract.symbol}
    except Exception as e:
        return {"error": str(e)}


IBKR_TOOLS = [
    get_account_info,
    get_positions,
    get_market_data,
    place_order,
    get_open_orders,
    cancel_order,
]
