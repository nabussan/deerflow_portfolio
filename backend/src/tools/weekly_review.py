"""
Weekly Position Review – Bull/Bear Debate (v0.2)
Läuft jeden Freitag um 18:00 (Berlin) oder via Env konfigurierbar.
Führt für jede Position eine Bull/Bear-Debatte durch und sendet Ergebnisse via Telegram.
"""

import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.tools.ibkr_connection import get_ibkr_connection, ibkr_submit, send_telegram
from src.tools.logger import get_logger

load_dotenv("/home/python/deer-flow/backend/.env")

logger = get_logger("weekly_review")

WEEKLY_REVIEW_HOUR = int(os.getenv("WEEKLY_REVIEW_HOUR", "18"))
WEEKLY_REVIEW_MINUTE = int(os.getenv("WEEKLY_REVIEW_MINUTE", "0"))
WEEKLY_REVIEW_DAY = os.getenv("WEEKLY_REVIEW_DAY", "fri")  # mon/tue/wed/thu/fri/sat/sun

# LLM via Grok
llm = ChatOpenAI(
    model="grok-4-1-fast",
    base_url="https://api.x.ai/v1",
    api_key=os.getenv("XAI_API_KEY"),
)

BULL_PROMPT = """\
Du bist ein optimistischer Aktienanalyst (Bull). \
Baue das stärkste mögliche Argument DAFÜR auf, diese Position zu HALTEN oder AUFZUSTOCKEN.

Symbol: {symbol}
Anzahl Aktien: {quantity}
Durchschnittlicher Einstandspreis: {avg_cost}
Aktuelle News (letzte 7 Tage):
{news}

Antworte mit exakt 3 Kernargumenten. Format:
🐂 BULL – {symbol}:
1. ...
2. ...
3. ...\
"""

BEAR_PROMPT = """\
Du bist ein kritischer Aktienanalyst (Bear). \
Baue das stärkste mögliche Argument DAGEGEN auf – warum diese Position REDUZIERT oder VERKAUFT werden sollte.

Symbol: {symbol}
Anzahl Aktien: {quantity}
Durchschnittlicher Einstandspreis: {avg_cost}
Aktuelle News (letzte 7 Tage):
{news}

Antworte mit exakt 3 Kernargumenten. Format:
🐻 BEAR – {symbol}:
1. ...
2. ...
3. ...\
"""

JUDGE_PROMPT = """\
Du bist ein unabhängiger Portfolio-Manager. Bewerte die folgende Bull/Bear-Debatte objektiv.

Symbol: {symbol}
Bull-Argumente:
{bull}

Bear-Argumente:
{bear}

Antworte NUR mit:
VERDICT: [HALTEN/AUFSTOCKEN/REDUZIEREN/VERKAUFEN]
BEGRÜNDUNG: [max. 2 Sätze auf Deutsch]
KONFIDENZ: [HOCH/MITTEL/NIEDRIG]\
"""

_VERDICT_EMOJI = {
    "HALTEN": "🟡",
    "AUFSTOCKEN": "🟢",
    "REDUZIEREN": "🟠",
    "VERKAUFEN": "🔴",
}
_KONFIDENZ_EMOJI = {"HOCH": "🔵", "MITTEL": "🟡", "NIEDRIG": "🔴"}


def get_all_positions() -> list[dict]:
    """Holt alle offenen Positionen vom IBKR Gateway."""
    try:
        ib = get_ibkr_connection()
        async def _req():
            await ib.reqPositionsAsync()
        ibkr_submit(_req())
        positions = [
            {
                "symbol": pos.contract.symbol,
                "currency": pos.contract.currency,
                "quantity": pos.position,
                "avgCost": pos.avgCost,
                "secType": pos.contract.secType,
            }
            for pos in ib.positions()
            if pos.position != 0
        ]
        logger.info("Fetched %d positions for weekly review", len(positions))
        return positions
    except Exception as e:
        logger.error("Fehler beim Abrufen der Positionen: %s", e, exc_info=True)
        return []


def search_weekly_news(symbol: str) -> str:
    """Sucht Nachrichten der letzten 7 Tage für ein Symbol."""
    try:
        from src.community.tavily.tools import web_search_tool
        results = web_search_tool.invoke({
            "query": f"{symbol} stock news analysis outlook week",
            "max_results": 7,
        })
        logger.info("Wochennews für %s: %d Zeichen", symbol, len(str(results)))
        return str(results)
    except Exception as e:
        logger.error("News-Suche Fehler für %s: %s", symbol, e, exc_info=True)
        return f"Keine News verfügbar für {symbol}"


def bull_bear_debate(
    symbol: str, quantity: float, avg_cost: float, news: str
) -> tuple[str, str]:
    """Lässt Bull und Bear getrennt argumentieren. Gibt (bull_arg, bear_arg) zurück."""
    try:
        bull_resp = llm.invoke(
            BULL_PROMPT.format(symbol=symbol, quantity=quantity, avg_cost=avg_cost, news=news)
        )
        bear_resp = llm.invoke(
            BEAR_PROMPT.format(symbol=symbol, quantity=quantity, avg_cost=avg_cost, news=news)
        )
        return bull_resp.content, bear_resp.content
    except Exception as e:
        logger.error("Debatte Fehler für %s: %s", symbol, e, exc_info=True)
        return f"🐂 Fehler: {e}", f"🐻 Fehler: {e}"


def judge_debate(symbol: str, bull_arg: str, bear_arg: str) -> dict:
    """LLM-Richter gibt ein strukturiertes Verdict zurück."""
    try:
        response = llm.invoke(
            JUDGE_PROMPT.format(symbol=symbol, bull=bull_arg, bear=bear_arg)
        )
        result = {
            "symbol": symbol,
            "verdict": "HALTEN",
            "begründung": "",
            "konfidenz": "MITTEL",
        }
        for line in response.content.strip().split("\n"):
            if line.startswith("VERDICT:"):
                result["verdict"] = line.split(":", 1)[1].strip()
            elif line.startswith("BEGRÜNDUNG:"):
                result["begründung"] = line.split(":", 1)[1].strip()
            elif line.startswith("KONFIDENZ:"):
                result["konfidenz"] = line.split(":", 1)[1].strip()
        logger.info(
            "Verdict %s: %s (Konfidenz: %s)",
            symbol, result["verdict"], result["konfidenz"],
        )
        return result
    except Exception as e:
        logger.error("Richter Fehler für %s: %s", symbol, e, exc_info=True)
        return {"symbol": symbol, "verdict": "FEHLER", "begründung": str(e), "konfidenz": "NIEDRIG"}


def _format_debate_message(
    symbol: str, bull_arg: str, bear_arg: str, verdict: dict
) -> str:
    v_emoji = _VERDICT_EMOJI.get(verdict["verdict"], "⚪")
    k_emoji = _KONFIDENZ_EMOJI.get(verdict["konfidenz"], "⚪")
    return (
        f"<b>📊 {symbol}</b>\n\n"
        f"{bull_arg}\n\n"
        f"{bear_arg}\n\n"
        f"{v_emoji} <b>Verdict: {verdict['verdict']}</b> {k_emoji} Konfidenz: {verdict['konfidenz']}\n"
        f"<i>{verdict['begründung']}</i>"
    )


def run_weekly_review():
    """Hauptfunktion: Wöchentlicher Bull/Bear Review für alle Positionen."""
    now = datetime.now().strftime("%d.%m.%Y")
    logger.info("=== Weekly Bull/Bear Review START | %s ===", now)
    try:
        positions = get_all_positions()
        if not positions:
            logger.warning("Keine Positionen – Weekly Review übersprungen")
            send_telegram("📋 <b>Weekly Review</b>\nKeine offenen Positionen gefunden.")
            return

        send_telegram(
            f"📅 <b>Wöchentlicher Portfolio-Review – {now}</b>\n"
            f"Analysiere <b>{len(positions)}</b> Position(en) via Bull/Bear-Debatte..."
        )

        verdicts: list[dict] = []
        for pos in positions:
            symbol = pos["symbol"]
            logger.info("Debatte für %s...", symbol)
            try:
                news = search_weekly_news(symbol)
                bull_arg, bear_arg = bull_bear_debate(
                    symbol, pos["quantity"], pos["avgCost"], news
                )
                verdict = judge_debate(symbol, bull_arg, bear_arg)
                verdicts.append(verdict)
                send_telegram(_format_debate_message(symbol, bull_arg, bear_arg, verdict))
            except Exception:
                logger.error("Fehler bei Symbol %s", symbol, exc_info=True)

        if verdicts:
            summary_lines = [
                f"{_VERDICT_EMOJI.get(v['verdict'], '⚪')} {v['symbol']}: {v['verdict']}"
                for v in verdicts
            ]
            send_telegram(
                f"📋 <b>Weekly Review – Zusammenfassung {now}</b>\n\n"
                + "\n".join(summary_lines)
            )
            logger.info("Weekly Review abgeschlossen: %d Positionen analysiert", len(verdicts))
    except Exception:
        logger.error("Weekly Review fehlgeschlagen", exc_info=True)
        send_telegram(
            "🚨 <b>Weekly Review Fehler</b>\n"
            "Der wöchentliche Review konnte nicht abgeschlossen werden."
        )
    finally:
        logger.info("=== Weekly Bull/Bear Review END ===")
