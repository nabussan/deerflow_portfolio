# Acceptance Criteria – Agent Skills

> **Bezug:** v0.2.0 (2026-03-26) | **Stand:** 2026-03-26  
> Jedes Kriterium ist **binär** – entweder vollständig erfüllt oder nicht erfüllt. Teilerfüllung gilt als ✗ NICHT ERFÜLLT.  
> Alle Tests mit Paper-Konto (Port 4002), sofern nicht anders angegeben.

---

## SK-01 · IBKR-Verbindung `ibkr_connection.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-01-01 | Verbindung zu IB Gateway herstellen | `isConnected() = True` nach Connect; keine Exception | Exception beim Connect oder `isConnected() = False` |
| SK-01-02 | Auto-Reconnect nach Verbindungsabbruch | Binnen 60 s selbstständige Reconnection nach simuliertem Abbruch; keine manuelle Aktion nötig | Agent bleibt dauerhaft getrennt oder wirft unbehandelte Exception |
| SK-01-03 | Telegram-Benachrichtigung bei Reconnect | Telegram-Nachricht mit Text `Reconnected` trifft binnen 30 s nach Reconnect ein | Keine Nachricht oder falscher Inhalt |
| SK-01-04 | Wöchentliche Gateway-Disconnect-Erinnerung | Telegram-Meldung am Samstagabend (konfigurierter Zeitpunkt, ±5 min) mit Hinweis auf manuellen Re-Login | Meldung bleibt aus oder kommt zur falschen Zeit |

---

## SK-02 · `get_account_info` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-02-01 | Rückgabe der Kontoübersicht | Dict/JSON mit `NetLiquidation`, `TotalCashValue`, `BuyingPower`; alle numerisch und > 0 für aktives Konto | Exception, leeres Objekt oder fehlendes Pflichtfeld |
| SK-02-02 | Korrektes Konto adressiert | Ergebnis stammt vom konfigurierten Port (`4002` = Paper, `4001` = Live); kein Cross-Connect | Tool verbindet sich mit falschem Port oder gibt Daten vom falschen Konto zurück |

---

## SK-03 · `get_positions` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-03-01 | Rückgabe aller offenen Positionen | Liste mit `Symbol`, `Quantity` (≠ 0), `AvgCost` pro Position; leeres Portfolio → leere Liste (kein Fehler) | Exception, `None` oder fehlende Pflichtfelder |
| SK-03-02 | Konsistenz mit IB-Gateway-Anzeige | Anzahl und Symbole stimmen mit Portfolio-Ansicht im IB Gateway überein (manuelle Prüfung) | Abweichung bei Anzahl oder Symbol |

---

## SK-04 · `get_market_data` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-04-01 | Gültiger Marktpreis während Handelszeiten | `Bid`, `Ask`, `Last` für übergebenes Symbol; alle numerisch und > 0 | Exception, Wert = 0 oder `None` während Handelszeiten |
| SK-04-02 | Verhalten außerhalb der Handelszeiten | Letzter verfügbarer Close-Preis oder expliziter Hinweis `market closed`; kein Crash | Unbehandelte Exception oder irreführende Nullwerte ohne Hinweis |

---

## SK-05 · `place_order` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-05-01 | Market-Order platzieren (Paper) | `orderId > 0`; Order erscheint unter offenen Orders im IB Gateway | Exception, `orderId ≤ 0` oder Order nicht sichtbar |
| SK-05-02 | Limit-Order platzieren (Paper) | IB Gateway zeigt Status `Submitted` mit dem korrekt übermittelten Limit-Preis | Falscher Preis, fehlende Order oder Status ≠ `Submitted` |
| SK-05-03 | Ungültige Parameter abweisen | `Quantity = 0` oder negativer Preis → strukturierte Fehlermeldung; keine Order im Gateway angelegt | Ungültige Order wird durchgeschleust oder unbehandelte Exception |

---

## SK-06 · `get_open_orders` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-06-01 | Liste offener Orders abrufen | Liste mit `orderId`, `Symbol`, `Action`, `Quantity`, `OrderType`; keine offene Order → leere Liste | Exception, `None` oder fehlende Felder |
| SK-06-02 | Konsistenz mit IB Gateway | Anzahl und IDs der offenen Orders stimmen mit IB-Gateway-Anzeige überein | Abweichung bei Count oder `orderId` |

---

## SK-07 · `cancel_order` `ibkr_tool.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-07-01 | Offene Order stornieren | IB Gateway zeigt Status `Cancelled` für die übergebene `orderId` binnen 10 s | Order bleibt offen, Status ≠ `Cancelled` oder Exception |
| SK-07-02 | Stornierung nicht-existenter Order | Strukturierte Fehlermeldung `Order not found`; kein Crash; keine Seiteneffekte | Unbehandelte Exception oder stille Fehler ohne Rückmeldung |

---

## SK-08 · Portfolio Monitor `portfolio_monitor.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-08-01 | Scheduler-Timing | Monitor startet um 08:00 EU / 15:00 US / 21:00 Asia (±5 min) gemäß APScheduler-Log | Kein Log-Eintrag zur erwarteten Zeit oder Abweichung > 5 min mehr als 1× pro Woche |
| SK-08-02 | Positionen vor News-Scan geladen | Log zeigt `Fetched N positions` vor dem ersten Tavily-API-Aufruf; N = Ergebnis von `get_positions` | News-Scan ohne vorheriges Positions-Laden oder N = 0 bei vorhandenen Positionen |
| SK-08-03 | Tavily-Suche pro Position | Für jede Position im Portfolio mindestens 1 Tavily-Request im Log / Trace nachweisbar | Position ohne zugehörigen News-API-Call |
| SK-08-04 | LLM liefert strukturiertes Ergebnis | Grok-Antwort enthält eine der vier Kategorien (`MANAGEMENT` / `HYPE` / `FUNDAMENTALS` / `SECTOR`) oder `NO_SIGNAL` | Antwort ohne erkennbare Kategorie, leer oder JSON-Parse-Fehler |

---

## SK-09 · Critical Signal Detection `portfolio_monitor.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-09-01 | `MANAGEMENT` korrekt erkannt | Test-Prompt mit CEO-Rücktritts-News → LLM klassifiziert als `MANAGEMENT`; Telegram-Alert ausgelöst | Signal unerkannt (`NO_SIGNAL`) oder falsche Kategorie |
| SK-09-02 | `HYPE` korrekt erkannt | Test-Prompt mit viralen Reddit/X-Pump-Nachrichten → LLM klassifiziert als `HYPE`; Alert ausgelöst | Signal unerkannt oder falsche Kategorie |
| SK-09-03 | `FUNDAMENTALS` korrekt erkannt | Test-Prompt mit Umsatzrückgang + Guidance-Senkung → LLM klassifiziert als `FUNDAMENTALS`; Alert ausgelöst | Signal unerkannt oder falsche Kategorie |
| SK-09-04 | `SECTOR` korrekt erkannt | Test-Prompt mit Regulatorik-Schock → LLM klassifiziert als `SECTOR`; Alert ausgelöst | Signal unerkannt oder falsche Kategorie |
| SK-09-05 | Kein False Positive bei neutralen News | Test-Prompt mit normalen In-line-Quartalszahlen → LLM gibt `NO_SIGNAL` zurück; kein Alert | Alert trotz neutralem Test-Prompt |

---

## SK-10 · Telegram Alerts `ibkr_connection.py` / `portfolio_monitor.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-10-01 | Pflichtfelder in Alert-Nachricht | Jede Nachricht enthält: Symbol, Signal-Kategorie, Zusammenfassung (≥ 1 Satz), Timestamp | Fehlende Felder oder leere Nachricht |
| SK-10-02 | Zustellung binnen 60 s | Telegram-Nachricht trifft innerhalb von 60 s nach Trigger im Chat ein | Verzögerung > 60 s oder keine Zustellung |
| SK-10-03 | Kein Alert bei `NO_SIGNAL` | Bei explizitem `NO_SIGNAL` durch LLM wird keine Telegram-Nachricht gesendet | Nachricht wird trotz `NO_SIGNAL` gesendet |

---

---

## SK-11 · Weekly Bull/Bear Review `weekly_review.py`

| ID | Akzeptanzkriterium | ✓ ERFÜLLT | ✗ NICHT ERFÜLLT |
|---|---|---|---|
| SK-11-01 | Bull/Bear-Debatte pro Position | `bull_bear_debate()` liefert zwei nicht-leere Strings (Bull + Bear); beide unterscheiden sich inhaltlich | Leere Strings, identische Inhalte oder unbehandelte Exception |
| SK-11-02 | Richter-Verdict strukturiert | `judge_debate()` gibt Dict mit `verdict` ∈ {HALTEN, AUFSTOCKEN, REDUZIEREN, VERKAUFEN} und `konfidenz` ∈ {HOCH, MITTEL, NIEDRIG} zurück | Fehlende Felder, ungültiger Verdict-Wert oder Exception |
| SK-11-03 | Telegram-Nachricht vollständig | Jede Positions-Nachricht enthält Symbol, Bull-Argumente (🐂), Bear-Argumente (🐻), Verdict-Emoji + Text, Konfidenz | Fehlende Pflichtfelder oder leere Nachricht |
| SK-11-04 | Kein Absturz bei leeren Positionen | `run_weekly_review()` mit 0 Positionen → Telegram-Info-Nachricht; kein Crash | Unbehandelte Exception oder keine Rückmeldung |
| SK-11-05 | Fehler bei einzelner Position bricht Review nicht ab | Exception bei einem Symbol → Review läuft für alle anderen Symbole weiter; Zusammenfassung wird gesendet | Gesamter Review abbrechend bei erstem Fehler |
| SK-11-06 | Scheduler-Timing | Review startet freitags um 18:00 (±5 min) gemäß APScheduler-Log; konfigurierbar via `WEEKLY_REVIEW_DAY/HOUR/MINUTE` | Kein Log-Eintrag zur erwarteten Zeit oder nicht konfigurierbar |