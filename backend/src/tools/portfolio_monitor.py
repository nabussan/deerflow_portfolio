"""
Portfolio Monitor Agent
Läuft täglich um 08:00, 15:00 und 21:00
Prüft Positionen auf kritische Signale und sendet Telegram-Alerts.
Weekly Bull/Bear Review: Freitag 18:00 (konfigurierbar via WEEKLY_REVIEW_*)
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

2. HYPE: Starke Anzeichen für irrationalen Hype
   (viral auf X/Twitter, Reddit-Pump, extreme Kursziele von Influencern)

3. FUNDAMENTALS: Verschlechterung der Fundamentaldaten
   (Umsatzrückgang, sinkende Bruttomarge, negativer FCF-Trend,
   Gewinnwarnung, Guidance-Senkung)

4. SECTOR: Negative externe Einflüsse auf den Sektor
   (neue Regulierung, Zölle, Rohstoffpreisschock,
   Konkurrent mit disruptiver Ankündigung)

Antworte NUR mit:
KRITISCH: [JA/NEIN]
KATEGORIE: [MANAGEMENT/HYPE/FUNDAMENTALS/SECTOR/NO_SIGNAL]
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
        logger.info("Fetched %d positions for market %s", len(positions), market)
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
            "kategorie": "NO_SIGNAL",
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
    from src.tools.weekly_review import run_weekly_review, WEEKLY_REVIEW_HOUR, WEEKLY_REVIEW_MINUTE, WEEKLY_REVIEW_DAY  # noqa: PLC0415

    scheduler = BlockingScheduler(timezone="Europe/Berlin")
    scheduler.add_job(lambda: run_monitor("EU"),   "cron", hour=8,  minute=0)
    scheduler.add_job(lambda: run_monitor("US"),   "cron", hour=15, minute=0)
    scheduler.add_job(lambda: run_monitor("ASIA"), "cron", hour=21, minute=0)
    scheduler.add_job(
        run_weekly_review,
        "cron",
        day_of_week=WEEKLY_REVIEW_DAY,
        hour=WEEKLY_REVIEW_HOUR,
        minute=WEEKLY_REVIEW_MINUTE,
    )
    logger.info("Portfolio Monitor Scheduler gestartet")
    logger.info("Läuft täglich um 08:00 (EU), 15:00 (US), 21:00 (ASIA)")
    logger.info(
        "Weekly Bull/Bear Review: %s um %02d:%02d",
        WEEKLY_REVIEW_DAY.capitalize(), WEEKLY_REVIEW_HOUR, WEEKLY_REVIEW_MINUTE,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Portfolio Monitor gestoppt")


if __name__ == "__main__":
    main()
