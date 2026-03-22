"""
Portfolio Monitor Agent
Läuft täglich um 08:00, 15:00 und 21:00
Prüft Positionen auf kritische Signale und sendet Telegram-Alerts.
"""

import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from apscheduler.schedulers.blocking import BlockingScheduler

from src.tools.ibkr_connection import get_ibkr_connection, send_telegram

load_dotenv("/home/python/deer-flow/backend/.env")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# LLM via Grok
llm = ChatOpenAI(
    model="grok-4-1-fast",
    base_url="https://api.x.ai/v1",
    api_key=os.getenv("XAI_API_KEY"),
)

# Kritische Signal-Kriterien
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
            exchange = pos.contract.exchange or "SMART"
            currency = pos.contract.currency

            if market == "EU" and currency == "EUR":
                positions.append({
                    "symbol": pos.contract.symbol,
                    "currency": currency,
                    "position": pos.position,
                    "avgCost": pos.avgCost,
                })
            elif market == "US" and currency == "USD":
                positions.append({
                    "symbol": pos.contract.symbol,
                    "currency": currency,
                    "position": pos.position,
                    "avgCost": pos.avgCost,
                })
            elif market == "ASIA" and currency in ("HKD", "JPY", "SGD", "AUD"):
                positions.append({
                    "symbol": pos.contract.symbol,
                    "currency": currency,
                    "position": pos.position,
                    "avgCost": pos.avgCost,
                })
        return positions
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Positionen: {e}")
        return []


def search_news(symbol: str) -> str:
    """Sucht aktuelle News für ein Symbol via Tavily."""
    try:
        from src.community.tavily.tools import web_search_tool
        results = web_search_tool.invoke({
            "query": f"{symbol} stock news today negative",
            "max_results": 5,
        })
        return str(results)
    except Exception as e:
        logger.error(f"News-Suche Fehler für {symbol}: {e}")
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

        # Parse Antwort
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
        return result
    except Exception as e:
        logger.error(f"Analyse Fehler für {symbol}: {e}")
        return {"symbol": symbol, "kritisch": False, "fehler": str(e)}


def run_monitor(market: str):
    """Hauptfunktion: Prüft alle Positionen des jeweiligen Marktes."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    logger.info(f"Portfolio Monitor gestartet: {market} um {now}")

    positions = get_positions_for_market(market)

    if not positions:
        logger.info(f"Keine {market}-Positionen gefunden.")
        return

    alerts = []
    for pos in positions:
        symbol = pos["symbol"]
        logger.info(f"Analysiere {symbol}...")
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

    if alerts:
        message = (
            f"🔔 <b>Portfolio Alert – {market} ({now})</b>\n\n"
            + "\n\n".join(alerts)
        )
        send_telegram(message)
        logger.info(f"{len(alerts)} Alert(s) gesendet.")
    else:
        logger.info(f"Keine kritischen Signale für {market}-Positionen.")


def main():
    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    # EU: 08:00
    scheduler.add_job(lambda: run_monitor("EU"), "cron", hour=8, minute=0)
    # US: 15:00
    scheduler.add_job(lambda: run_monitor("US"), "cron", hour=15, minute=0)
    # ASIA: 21:00
    scheduler.add_job(lambda: run_monitor("ASIA"), "cron", hour=21, minute=0)

    logger.info("Portfolio Monitor Scheduler gestartet.")
    logger.info("Läuft täglich um 08:00 (EU), 15:00 (US), 21:00 (ASIA)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Portfolio Monitor gestoppt.")


if __name__ == "__main__":
    main()
