# Troubleshooting – DeerFlow Portfolio (W541 Setup)

> Erfahrungen vom 2026-03-24 – W541 ThinkPad, Windows 10, WSL2, Ubuntu 24.04

---

## 1. Energieverwaltung – PC schläft nach 3 Stunden ein

**Problem:** W541 geht in Ruhezustand, IB Gateway / TWS wird beendet.

**Ursache:** `powercfg` zeigte `HIBERNATEIDLE = 0x00002a30` (10.800 Sekunden = 3 Stunden).

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

## 2. IB Gateway vs. TWS

**Problem:** IB Gateway war nach Neustart nicht mehr vorhanden.

**Ursache:** IB Gateway wurde nicht installiert, sondern nur direkt als heruntergeladene Java-App gestartet. Nach dem Neustart war der Prozess weg.

**Erkenntnis:** IBKR hat IB Gateway und TWS zusammengeführt. Es gibt weiterhin einen separaten IB Gateway Installer:
```
https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-windows-x64.exe
```

**WICHTIG – IB Gateway mit LYNX Broker:** Bei LYNX-Konten handelt es sich um eine White-Label-Version von IBKR. IB Gateway verbindet sich technisch korrekt (grüner Status), akzeptiert aber den API-Handshake von WSL2 nicht zuverlässig (TimeoutError bei `apiStart`). Ursache unklar – möglicherweise LYNX-spezifische Einschränkung.

**Empfehlung: TWS verwenden** – TWS (installiert unter `C:\Jts\tws.exe`) funktioniert stabil als API-Server auf Port 7496.

---

## 3. Windows Firewall blockiert WSL2 → TWS

**Problem:** WSL2 kann Port 7496 nicht erreichen, obwohl `netstat` zeigt dass TWS auf `0.0.0.0:7496` lauscht.

**Ursache:** Windows Firewall behandelt den virtuellen `vEthernet (WSL)` Adapter als eigenes Netzwerksegment mit separaten Regeln.

**Was nicht funktioniert:**
- `netsh advfirewall firewall add rule ... profile=any` – greift nicht für WSL2-Adapter
- `New-NetFirewallRule ... -InterfaceAlias "vEthernet (WSL)"` – wird nicht persistent nach Neustart

**Was funktioniert:** Firewall komplett deaktivieren (akzeptabel da W541 hinter Router/NAT und Tailscale geschützt ist):
```powershell
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
```

**Persistent machen via Scheduled Task (PowerShell als Admin):**
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-Command `"Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "deerflow"
$principal = New-ScheduledTaskPrincipal -UserId "deerflow" -RunLevel Highest
Register-ScheduledTask -TaskName "WSL2-Firewall-Disable" -Action $action -Trigger $trigger -Principal $principal
```

---

## 4. Port-Proxy schadet mehr als er nützt

**Problem:** Port-Proxy `172.24.128.1:7496 → 127.0.0.1:7496` verhindert statt ermöglicht die Verbindung.

**Erkenntnis:** TWS auf `0.0.0.0:7496` ist direkt von WSL2 erreichbar sobald die Firewall deaktiviert ist. Kein Port-Proxy nötig.

**Sicherstellen dass kein Port-Proxy für 7496 existiert (PowerShell):**
```powershell
netsh interface portproxy show all
netsh interface portproxy delete v4tov4 listenaddress=172.24.128.1 listenport=7496
```

---

## 5. TWS API-Einstellungen

**Einmalig einrichten unter:** `Edit → Global Configuration → API → Settings` → Apply → OK

**Korrekte Einstellungen:**
- ✅ ActiveX- und Socket-Clients aktivieren
- ❌ Schreibgeschützte API (deaktiviert)
- ❌ Nur Verbindungen vom lokalen Host zulassen (deaktiviert)
- Socket Port: `7496`
- Vertrauenswürdige IPs: `172.24.128.0/24`, `172.24.142.0/24`

Diese Einstellungen werden persistent gespeichert und müssen nicht nach jedem Neustart wiederholt werden.

---

## 6. `dotenv` lädt falschen Pfad

**Problem:** `ibkr_connection.py` hatte hardcoded den falschen Pfad:
```python
load_dotenv("/home/python/deer-flow/backend/.env")  # FALSCH
```

**Fix:**
```python
load_dotenv()  # Lädt automatisch aus dem aktuellen Verzeichnis
```

---

## 7. `ib_insync` Event Loop Konflikt mit uvloop (LangGraph)

**Problem:** LangGraph nutzt `uvloop`. `ib_insync` braucht einen Standard-asyncio-Loop. Tools schlagen mit `"There is no current event loop in thread"` fehl.

**Was nicht funktioniert:**
- `nest_asyncio.apply()` – inkompatibel mit uvloop (`ValueError: Can't patch loop of type uvloop.Loop`)
- `asyncio.set_event_loop(asyncio.new_event_loop())` in `get_connection()` – reicht nicht
- `ib.sleep()` statt `time.sleep()` – blockiert uvloop
- `t.join()` im Worker-Thread – blockiert uvloop-Thread

**Was funktioniert:** Dedizierter Worker-Thread mit eigenem asyncio-Loop und `queue.get()` statt `t.join()`:
```python
import threading, queue, asyncio, random

def get_market_data(symbol, exchange="SMART", currency="USD"):
    result_queue = queue.Queue()
    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ib = IB()
            ib.connect(host, port, clientId=random.randint(50, 99), timeout=10)
            # ... IB calls ...
            result_queue.put(result)
        except Exception as e:
            result_queue.put({"error": str(e)})
        finally:
            loop.close()
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    try:
        return result_queue.get(timeout=20)  # NICHT t.join() verwenden
    except Exception:
        return {"error": "Timeout"}
```

**Wichtig:** Jeder parallele Aufruf braucht eine eindeutige `clientId` (z.B. `random.randint(50, 99)`).

---

## 8. Offene Probleme (Stand 2026-03-24)

### `get_open_orders`, `place_order`, `cancel_order` funktionieren nicht im UI

**Status:** ⚠️ Offen

**Symptom:** Agent ruft das Tool auf, aber keine Reaktion im Frontend.

**Vermutung:** Dieselbe Event-Loop-Problematik wie bei `get_market_data` vor dem Fix.

**TODO:** Worker-Thread-Pattern aus `get_market_data` auf alle verbleibenden Tools übertragen.

### IB Gateway (LYNX) akzeptiert keinen API-Handshake von WSL2

**Status:** ⚠️ Offen / Workaround: TWS nutzen

**Symptom:** `nc` erreicht Port 4002, aber `ib_insync` schlägt bei `apiStart` mit TimeoutError fehl.

**Nächste Schritte:**
- IBC (IB Controller) für automatischen TWS-Login testen: https://github.com/IbcAlpha/IBC
- IBKR/LYNX Support kontaktieren ob API-Verbindungen von WSL2-IPs unterstützt werden

---

## Funktionierende Konfiguration (Stand 2026-03-24)

| Komponente | Wert |
|---|---|
| Broker-App | TWS (`C:\Jts\tws.exe`) |
| API Port | 7496 |
| IBKR_HOST | 172.24.128.1 (Windows-IP aus WSL2) |
| Firewall | Deaktiviert (Scheduled Task bei Login) |
| Port-Proxy | Keiner für Port 7496 |
| Autostart | TWS-Autostart Scheduled Task |

| Tool | Status |
|---|---|
| `get_account_info` | ✅ |
| `get_positions` | ✅ |
| `get_market_data` | ✅ |
| `get_open_orders` | ⚠️ offen |
| `place_order` | ⚠️ offen |
| `cancel_order` | ⚠️ offen |
