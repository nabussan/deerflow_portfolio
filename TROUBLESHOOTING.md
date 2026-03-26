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
2. Port 4002 erreichbar? → `nc -zv <IBKR_HOST> 4002`
3. Saturday-Night-Disconnect? → IB Gateway manuell neu einloggen
4. `.env` korrekt? → `IBKR_HOST`, `IBKR_PORT=4002`, `IBKR_MODE=paper`
5. Logs prüfen: `tail -50 backend/logs/ibkr_connection.log`

---

### IB Gateway verbindet TCP, aber API-Handshake schlägt still fehl (`b''`)

**Symptom:** `nc -zv <IBKR_HOST> 4002` → `succeeded`, aber `ib.connect()` gibt `b''` zurück. Kein Fehler, kein Timeout, keine Verbindung.

**Ursache:** WSL2-Client-IP ist nicht in der Trusted-IP-Liste von IB Gateway.

**Diagnose:**
```bash
hostname -I   # → zeigt deine echte WSL2-Client-IP (z.B. 172.24.142.255)
```

Die IP aus `ip route | grep default` (→ `172.24.128.1`) ist die **Windows-Host-IP**, aber nicht die IP, die IB Gateway als Verbindungsquelle sieht — das ist die WSL2-eigene IP aus `hostname -I`.

**Fix:** In IB Gateway: `Configure → API → Trusted IPs` → `172.24.0.0/16` eintragen.

---

### Services stürzen alle ~10–30 Sekunden ab (502 Bad Gateway)

**Symptom:** `langgraph dev` gibt `2 changes detected – reloading` aus und startet neu. Laufende Chat-Requests brechen ab.

**Ursache:** watchfiles-Hot-Reload erkennt in WSL2 auch Metadaten-Änderungen (z.B. Log-Writes) als Code-Änderungen.

**Fix:** `start.sh` und `scripts/restart.sh` müssen `--no-reload` verwenden:
```bash
uv run langgraph dev --port 2024 --no-browser --allow-blocking --no-reload
```

**Bereits in `start.sh` eingetragen** (v0.1.3). Nach `make stop && make dev` oder `./start.sh` ist der Fix aktiv.

---

### Kurs-Abfrage liefert nur `close`, kein bid/ask

**Ursache:** Markt geschlossen (z.B. nach 22:00 Uhr oder Wochenende). Das Feld `market_closed: true` wird gesetzt.

**Normal** – `close` enthält den letzten Schlusskurs.

---

### Kurs-Abfrage zeigt `market_closed: true` obwohl Markt offen ist (LYNX)

**Symptom:** `get_market_data` gibt `market_closed: true` zurück, obwohl US-Markt offen (09:30–16:00 ET). `bid`, `ask` und `last` sind alle `None`.

**Ursache (LYNX-spezifisch):** LYNX Paper Accounts haben standardmäßig keine Echtzeit-Marktdaten-Abonnements. Ohne Abo liefert TWS kein Streaming-bid/ask — nur verzögerte Daten (15-20 Min.) oder gar nichts. Unser Code setzt `market_closed: true` wenn alle drei Felder leer sind.

**Prüfen in TWS:** `Account → Market Data Subscriptions`

**Workaround:** In TWS unter `Help → Paper Trading` Delayed Market Data aktivieren. Alternativ: `get_market_data` auf `reqHistoricalData` als Fallback umstellen (liefert immer Schlusskurs, unabhängig vom Abo).

---

### `get_open_orders` zeigt manuell in TWS platzierte Orders nicht

**Symptom:** Orders die direkt in TWS (nicht per API) platziert wurden, fehlen in der Liste.

**Ursache:** `ib.openTrades()` gibt nur Orders der aktuellen API-Session zurück. `reqAllOpenOrders()` ist nötig um auch TWS-Orders abzuholen.

**Fix bereits implementiert** (v0.1.4): `get_open_orders` ruft `ib.client.reqAllOpenOrders()` auf dem ibkr-Loop auf, wartet 1 Sekunde, dann `openTrades()`.

Hinweis: `ib.reqAllOpenOrders()` (ib_insync-Wrapper) darf nicht direkt aufgerufen werden — verursacht `RuntimeError: This event loop is already running`. Stattdessen `ib.client.reqAllOpenOrders()` innerhalb von `ibkr_submit()` verwenden.

---

### Manuell in TWS platzierte Orders haben `orderId=0` – Stornierung per API nicht möglich

**Symptom:** `get_open_orders` zeigt Order mit ID `TWS-<permId>`. `cancel_order` gibt Fehler zurück: *„Manuell in TWS platzierte Orders können nicht per API storniert werden"*. TWS-Fehlermeldung: `Error 10147: OrderId 0 that needs to be cancelled is not found`.

**Ursache:** IBKR vergibt keine API-`orderId` für Orders die direkt in TWS platziert wurden. Die API kennt sie nur via `permId`, aber `cancelOrder()` braucht eine gültige `orderId`.

**Workaround:** Solche Orders direkt in TWS stornieren. Die `permId` (z.B. `TWS-171251651`) dient nur zur Identifikation im DeerFlow-UI.

---

### IBC startet IB Gateway nicht nach Windows-Neustart (LYNX / IBC-Konfiguration)

**Symptom:** Scheduled Task `IBGateway-Autostart` zeigt Status `Bereit`, aber kein Gateway-Prozess läuft. IBC-Log: `Error while: Running StartIBC.bat / ERRORLEVEL = 1004`.

**Ursache 1:** `TWS_MAJOR_VRSN` in `C:\IBC\StartGateway.bat` ist auf alte Version hardcoded (z.B. `1019`), installierte Version ist `1037`.

**Fix:**
```powershell
(Get-Content "C:\IBC\StartGateway.bat") -replace 'set TWS_MAJOR_VRSN=1019', 'set TWS_MAJOR_VRSN=1037' | Set-Content "C:\IBC\StartGateway.bat"
```

**Ursache 2:** `CONFIG`-Pfad in `StartGateway.bat` zeigt auf `%USERPROFILE%\Documents\IBC\config.ini`, aber config liegt in `C:\IBC\config.ini`.

**Fix:**
```powershell
(Get-Content "C:\IBC\StartGateway.bat") -replace 'set CONFIG=%USERPROFILE%\\Documents\\IBC\\config.ini', 'set CONFIG=C:\IBC\config.ini' | Set-Content "C:\IBC\StartGateway.bat"
```

Nach beiden Fixes manuell testen:
```powershell
cmd /c "C:\IBC\StartGateway.bat" 1037 "C:\IBC\config.ini" "C:\IBC" Gateway
```

---

### LYNX IB Gateway akzeptiert keinen API-Handshake — dauerhafter Timeout

**Symptom:** `nc -zv <IBKR_HOST> 4002` → `succeeded`, aber `ib.connect()` gibt dauerhaft `TimeoutError`. Kein `b''`, kein Fehler — einfach Timeout nach 10 Sekunden. In IB Gateway fehlt die Option „Socket Clients aktivieren".

**Ursache (LYNX-spezifisch):** LYNX Broker Gateway (White-Label IBKR) hat im API-Settings-Dialog keine „Enable Socket Clients"-Option und blockiert den ib_insync-Handshake zuverlässig. Ursache seitens LYNX unklar — möglicherweise policy-bedingte Einschränkung.

**Workaround: TWS statt IB Gateway verwenden.**

```bash
# In backend/.env:
IBKR_PORT=7496   # TWS statt IB Gateway (4002)
```

TWS starten: `C:\Jts\tws.exe` → einloggen → API-Settings:
- Socket Port: `7496`
- Read-Only API: deaktiviert
- „Nur lokale Verbindungen": deaktiviert

IBC kann alternativ auf `StartTWS.bat` umgestellt werden statt `StartGateway.bat`.

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

## Windows / WSL2 Setup (W541-Lektionen)

Erfahrungen aus der Ersteinrichtung — erspart Umwege.

### Energieverwaltung: PC schläft ein und beendet IB Gateway

**Problem:** W541 geht in Ruhezustand, IB Gateway wird beendet.

**Lösung (PowerShell als Admin):**
```powershell
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /hibernate off
```

**Überprüfen:**
```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP
# Alle Werte müssen 0x00000000 sein
```

---

### IB Gateway vs. TWS

**Erkenntnis:** IBKR hat IB Gateway und TWS zusammengeführt. Es gibt weiterhin einen separaten IB Gateway Installer:
```
https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-windows-x64.exe
```

**WICHTIG – IB Gateway mit LYNX Broker:** Bei LYNX-Konten (White-Label IBKR) verbindet sich IB Gateway technisch korrekt (grüner Status), akzeptiert aber den API-Handshake von WSL2 nicht zuverlässig (TimeoutError bei `apiStart`). Workaround: TWS (`C:\Jts\tws.exe`) verwenden (Port 7496).

---

### Windows Firewall blockiert WSL2 → IB Gateway / TWS

**Ursache:** Windows Firewall behandelt den `vEthernet (WSL)` Adapter als eigenes Netzwerksegment.

**Was nicht funktioniert:**
- `netsh advfirewall firewall add rule ... profile=any` — greift nicht für WSL2-Adapter
- `New-NetFirewallRule ... -InterfaceAlias "vEthernet (WSL)"` — wird nicht persistent nach Neustart

**Was funktioniert:** Firewall komplett deaktivieren (akzeptabel da W541 hinter Router/NAT und Tailscale geschützt ist):
```powershell
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
```

**Persistent via Scheduled Task:**
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-Command `"Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest
Register-ScheduledTask -TaskName "WSL2-Firewall-Disable" -Action $action -Trigger $trigger -Principal $principal
```

---

### Port-Proxy für Port 7496 schadet mehr als er nützt

**Erkenntnis:** TWS auf `0.0.0.0:7496` ist direkt von WSL2 erreichbar sobald die Firewall deaktiviert ist. Ein Port-Proxy auf `172.24.128.1:7496` blockiert die Verbindung statt sie zu ermöglichen.

```powershell
# Sicherstellen dass kein Proxy für 7496 existiert:
netsh interface portproxy show all
netsh interface portproxy delete v4tov4 listenaddress=172.24.128.1 listenport=7496
```

---

## Bekannte Einschränkungen

| Einschränkung | Workaround |
|---|---|
| IB Gateway Sa.-Nacht-Disconnect (23:00) | Manuelles Re-Login, Auto-Reconnect startet danach |
| Forex-Positionen in `get_positions` haben `secType=CASH` | Normales IBKR-Verhalten, kein Bug |
| Marktdaten nach Börsenschluss nur als `close` | `market_closed: true` Flag auswerten |
| xAI lehnt leere AIMessage-Content ab | Fix in `DanglingToolCallMiddleware` (v0.1.2) |
