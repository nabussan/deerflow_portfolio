# Migration: TWS → IB Gateway

> Branch: `feature/ibkr-gateway`
> Ziel: TWS (Port 7496) durch IB Gateway (Port 4002) ersetzen
> Hintergrund: DEVGUIDE.md § „Bekannte Architektur-Fallen", TROUBLESHOOTING.md § „IB Gateway vs. TWS"

---

## Warum IB Gateway?

| | TWS (aktuell) | IB Gateway (Ziel) |
|---|---|---|
| Port Paper | 7496 | 4002 |
| RAM | ~1 GB | ~200 MB |
| GUI | Vollständig | Keiner (headless) |
| 24/7-Betrieb | Suboptimal | Dafür gebaut |
| API + manuell gleichzeitig | Konflikte möglich | API-only, klar |

---

## Hypothese: Warum es damals scheiterte

Beim ersten Versuch (2026-03-24) trat ein `TimeoutError bei apiStart` auf.
Die Diagnose lautete: „möglicherweise LYNX-spezifische Einschränkung."

**Wahrscheinlichere Ursache:** Die Windows Firewall blockierte WSL2 → IB Gateway
auf dieselbe Weise wie TWS — nur wurde die Firewall-Deaktivierung erst *nach* dem
Wechsel zu TWS vorgenommen. IB Gateway wurde nie unter den korrekten
Netzwerkbedingungen getestet.

**Diese Migration klärt das.**

---

## Plan

### Phase 1 – Windows: IB Gateway installieren (einmalig)

> Auf dem W541 Windows-Desktop durchführen.

**Schritt 1.1 – Installer herunterladen**

```
https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-windows-x64.exe
```

Nicht die portable ZIP-Version — der Installer sorgt für Autostart-Einträge
und einen stabilen Pfad (`C:\Jts\ibgateway\`).

**Schritt 1.2 – Installieren und einloggen**

- Installer ausführen
- Mit LYNX-Zugangsdaten einloggen
- Modus: **Paper Trading**
- In den Einstellungen: `Configure → API → Settings`
  - [x] Enable ActiveX and Socket Clients
  - Socket port: **4002**
  - [x] Allow connections from localhost only → **deaktivieren** (WSL2 hat eigene IP)
  - Master API client ID: leer lassen
- Unter `Trusted IPs` eintragen: `172.24.0.0/16` (komplette WSL2-Range)

**Schritt 1.3 – Firewall prüfen**

Die Firewall-Deaktivierung ist bereits als Scheduled Task `WSL2-Firewall-Disable`
eingerichtet (aus der TWS-Migration). Sie gilt für alle Ports inkl. 4002 — kein
weiterer Schritt nötig.

Zur Sicherheit prüfen:
```powershell
Get-NetFirewallProfile | Select Name, Enabled
# Alle drei Profile müssen Enabled: False zeigen
```

**Schritt 1.4 – Verbindung von WSL2 testen (vor Code-Änderung)**

```bash
# Von WSL2 aus: kann Port 4002 auf der Windows-IP erreicht werden?
nc -zv 172.24.128.1 4002
# Erwartetes Ergebnis: "Connection to 172.24.128.1 4002 port [tcp/*] succeeded!"
```

Wenn dieser Test scheitert → Firewall-Problem, nicht LYNX-Problem.
Wenn er durchgeht → weiter mit Phase 2.

---

### Phase 2 – Code: Port und Modus umstellen

**Schritt 2.1 – `.env` anpassen**

```env
# vorher:
IBKR_HOST=172.24.128.1
IBKR_PORT=7496

# nachher:
IBKR_HOST=172.24.128.1
IBKR_PORT=4002
IBKR_MODE=paper
```

**Schritt 2.2 – Safety Guard verifizieren**

`ibkr_connection.py` prüft bereits: `IBKR_MODE=paper` → erwartet Port 4002.
Mit der Änderung ist der Mismatch-Warning weg — kein Code-Änderung nötig.

**Schritt 2.3 – Backend neu starten**

```bash
cd /home/deerflow/deer-flow
make stop && make dev
```

Erwartetes Log in `backend/logs/ibkr_connection.log`:
```
INFO  Paper trading mode | host=172.24.128.1 port=4002
INFO  ✅ IBKR Gateway verbunden | host=172.24.128.1 port=4002
```

---

### Phase 3 – Funktionstest

Die bestehende Test-Suite prüft die Tool-Logik (ohne echtes Gateway).
Für den Live-Test direkt im DeerFlow-Chat:

| Test | Prompt | Erwartetes Ergebnis |
|---|---|---|
| Verbindung | „Zeig meinen Kontostand" | NetLiquidation, BuyingPower > 0 |
| Positionen | „Was habe ich im Depot?" | Liste der Paper-Positionen |
| Kurs | „TSLA-Kurs jetzt" | bid/ask oder market_closed |
| Order | „Kaufe 1 AAPL" | orderId > 0, Status Submitted |
| Forex | „EUR/USD aktuell?" | bid/ask/mid |
| Forex-Order | „Kaufe 1000 EUR gegen USD" | orderId > 0 |

---

### Phase 4 – Autostart einrichten (nach erfolgreichem Test)

IB Gateway muss beim Windows-Start automatisch starten und eingeloggt bleiben.
IBKR bietet dafür eine offizielle Lösung: **IBC (IB Controller)**.

**IBC herunterladen:**
```
https://github.com/IbcAlpha/IBC/releases
```

IBC startet IB Gateway headless, loggt automatisch ein (Credentials in
verschlüsselter Config), und hält die Verbindung am Leben.

> ⚠️ IBC-Setup ist ein separater Schritt — erst nach erfolgreichem Phase-3-Test.

---

## Entscheidungsbaum

```
Phase 1.4: nc -zv 172.24.128.1 4002
    │
    ├─ SCHEITERT → Firewall-Problem
    │              → Scheduled Task prüfen / Windows Defender neu konfigurieren
    │
    └─ KLAPPT ──→ Phase 2: .env umstellen, Backend starten
                    │
                    ├─ Log zeigt "✅ IBKR Gateway verbunden" → Phase 3 Tests
                    │       │
                    │       ├─ Alle Tests OK → PR: feature/ibkr-gateway → dev
                    │       │                  TROUBLESHOOTING.md aktualisieren
                    │       │
                    │       └─ Tests schlagen fehl → Logs analysieren
                    │
                    └─ Log zeigt TimeoutError → LYNX-spezifisches Problem bestätigt
                                                → .env zurück auf Port 7496
                                                → Branch schließen, bei TWS bleiben
                                                → TROUBLESHOOTING.md dokumentieren
```

---

## Rollback

Falls IB Gateway nicht funktioniert:

```bash
# .env zurücksetzen
sed -i 's/IBKR_PORT=4002/IBKR_PORT=7496/' backend/.env
sed -i 's/IBKR_MODE=paper//' backend/.env
make stop && make dev
```

Branch `feature/ibkr-gateway` wird dann mit Dokumentation der Erkenntnisse
geschlossen (kein Merge).

---

## Offene Fragen / Risiken

| Frage | Risiko | Klärung in |
|---|---|---|
| Akzeptiert LYNX IB Gateway API-Connections? | Mittel – war damals unklar | Phase 1.4 + Phase 2 |
| Trusted IPs in IB Gateway konfigurierbar? | Niedrig – Standard-Feature | Phase 1.2 |
| IBC mit LYNX kompatibel? | Unbekannt | Phase 4 (nach Phase 3) |
| Saturday-Disconnect ändert sich? | Nein – gilt für beide | Keine Auswirkung |
