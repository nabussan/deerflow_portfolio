# Troubleshooting – DeerFlow Portfolio

Schnelle Fehlerdiagnose. Ausführliche Hintergründe → `DEVGUIDE.md`.

---

## IBKR / ib_insync

### „There is no current event loop in thread"

```
RuntimeError: There is no current event loop in thread 'ThreadPoolExecutor-...'
```

**Ursache:** Ein synchroner ib_insync-Call (z.B. `reqMktData`, `placeOrder`) wurde direkt aus dem LangGraph-Thread-Pool aufgerufen. In Python 3.12 wirft `asyncio.get_event_loop()` dort eine Exception.

**Fix bereits implementiert** (v0.1.2): Betroffene Calls laufen als `async`-Wrapper über `ibkr_submit()`.

Falls der Fehler erneut auftritt bei einem neuen ib_insync-Call:
```python
# Falsch – direkt aus Thread-Pool:
ticker = ib.reqMktData(contract, "", False, False)

# Richtig – über ibkr-loop:
async def _req():
    return ib.reqMktData(contract, "", False, False)
ticker = ibkr_submit(_req())
```

---

### „coroutine was never awaited"

```
RuntimeWarning: coroutine 'IB.qualifyContractsAsync' was never awaited
```

**Ursache:** Eine ib_insync-Coroutine wurde mit `ib.qualifyContracts()` (sync) statt mit `ibkr_submit(ib.qualifyContractsAsync())` aufgerufen, oder der Loop war noch nicht bereit.

**Fix:** Alle Coroutinen via `ibkr_submit()` ausführen:
```python
ibkr_submit(ib.qualifyContractsAsync(contract))
```

---

### IBKR Gateway nicht verbunden

```
ConnectionError: IBKR Gateway nicht verbunden
```

**Checkliste:**
1. IB Gateway läuft auf Windows? → Taskleiste prüfen
2. Port 4002 erreichbar? → `nc -zv 127.0.0.1 4002`
3. Saturday-Night-Disconnect? → IB Gateway manuell neu einloggen
4. `.env` korrekt? → `IBKR_HOST`, `IBKR_PORT=4002`, `IBKR_MODE=paper`
5. Logs prüfen: `tail -50 backend/logs/ibkr_connection.log`

---

### Kurs-Abfrage liefert nur `close`, kein bid/ask

**Ursache:** Markt geschlossen (z.B. nach 22:00 Uhr oder Wochenende). Das Feld `market_closed: true` wird gesetzt.

**Normal** – `close` enthält den letzten Schlusskurs.

---

## xAI / Grok

### 400 „Each message must have at least one content element"

```
openai.BadRequestError: Error code: 400
'Each message must have at least one content element'
```

**Ursache:** Eine `AIMessage` mit `tool_calls` hat leeres `content`-Feld. xAI/Grok lehnt das ab.

**Fix bereits implementiert** (v0.1.2): `DanglingToolCallMiddleware._fix_empty_ai_content()` ersetzt leeren Content vor dem API-Call durch `" "`.

Falls der Fehler erneut auftritt: prüfen ob eine neue Middleware die Messages vor `DanglingToolCallMiddleware` verändert.

---

### Agent verwendet Web-Suche statt IBKR-Tools

**Ursache A:** Backend läuft noch mit altem Code → `make stop && make dev`

**Ursache B:** Tool nicht in `config.yaml` registriert.

Prüfen:
```bash
grep "ibkr\|place_order\|get_forex" config.yaml
```

Fehlt ein Tool, eintragen:
```yaml
tools:
  - name: mein_neues_tool
    group: ibkr
    use: src.tools.ibkr_tool:mein_neues_tool
```

Dann Backend neu starten.

---

## Backend / Services

### LangGraph startet nicht

```bash
# Logs prüfen
cat /tmp/deerflow_startup.log
tail -50 backend/logs/backend.log

# Manuell starten für detaillierte Fehlermeldung
cd backend && uv run langgraph dev
```

**Häufige Ursachen:**
- `config.yaml` Syntaxfehler (YAML-Einrückung!)
- Fehlende Env-Variable (`$XAI_API_KEY` nicht gesetzt)
- Port 2024 bereits belegt → `lsof -i :2024`

---

### „Environment variable XAI_API_KEY not found"

`.env` Datei fehlt oder nicht geladen:
```bash
# Prüfen
cat backend/.env | grep XAI

# Notfalls manuell exportieren
export XAI_API_KEY=xai-...
```

---

### Tests schlagen fehl wegen ibkr_submit

Wenn neue ib_insync-Synchron-Calls hinzugefügt werden, muss die Test-Fixture in `test_ibkr_tools.py` wissen, ob der Wrapper ausgeführt werden soll:

```python
# In patch_validate fixture:
# - co_name == "sleep"        → schließen (kein Ausführen)
# - co_name.endswith("Async") → schließen (ib_insync async, gibt nichts zurück)
# - alles andere              → auf frischem Event-Loop ausführen (z.B. _req, _place)
```

---

## Bekannte Einschränkungen

| Einschränkung | Workaround |
|---|---|
| IB Gateway Sa.-Nacht-Disconnect (23:00) | Manuelles Re-Login, Auto-Reconnect startet danach |
| Forex-Positionen in `get_positions` haben `secType=CASH` | Normales IBKR-Verhalten, kein Bug |
| Marktdaten nach Börsenschluss nur als `close` | `market_closed: true` Flag auswerten |
| xAI lehnt leere AIMessage-Content ab | Fix in `DanglingToolCallMiddleware` (v0.1.2) |
