# DeerFlow Portfolio – Developer Guide

> Ergänzung zu README.md für v0.1.2
> Ziel: In 6 Monaten ohne Rätseln weitermachen können.

---

## Tailscale – Verbindung von P53 zu W541

### Einmalig einrichten

1. Tailscale auf beiden Geräten: https://tailscale.com/download
2. Auf beiden einloggen: `tailscale up`
3. Tailscale-IP des W541 im Admin Panel notieren: https://login.tailscale.com/admin/machines
   Format: `100.xx.xxx.xx` – ändert sich nicht, auch nach Neustart nicht.

### Verbindung herstellen

```bash
# Erreichbarkeit prüfen
tailscale ping 100.88.180.28

# SSH auf W541 (WSL2)
ssh python@100.88.180.28

# VS Code Remote SSH – ~/.ssh/config auf P53:
#   Host w541
#       HostName 100.88.180.28
#       User python
# Dann: F1 → "Remote-SSH: Connect to Host" → w541
```

### DeerFlow-Frontend

```
http://100.88.180.28:3000/workspace
```

### Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| `tailscale ping` timeout | W541 schläft / Tailscale gestoppt | W541 aufwecken, `tailscale up` |
| Port 3000 nicht erreichbar | WSL2-IP hat sich geändert | Task Scheduler → `wsl-portproxy` neu starten |
| IBKR nicht verbunden | IB Gateway Sa.-Nacht-Disconnect | IB Gateway manuell neu einloggen (~1 Min.) |

---

## Dev-Workflow: P53 → W541

### Branch-Strategie

| Branch | Zweck | Läuft auf |
|---|---|---|
| `portfolio` | Production | W541 |
| `dev` | Entwicklung | P53 |

```bash
# P53: Feature entwickeln
git checkout dev
# ... Änderungen ...
git add -p                  # selektiv – niemals .env stagen!
git commit -m "feat: ..."
git push origin dev

# Nach Test auf W541: merge
git checkout portfolio
git merge dev
git push origin portfolio

# W541: ausrollen
git pull origin portfolio
bash scripts/restart.sh
```

---

## Logging

Log-Dateien: `backend/logs/` (in `.gitignore`)

| Datei | Inhalt |
|---|---|
| `portfolio_monitor.log` | Monitor-Runs, Signale, Telegram-Status |
| `ibkr_connection.log` | Verbindungsstatus, Trading-Mode, Reconnects |
| `startup.log` | restart.sh Ausgaben |
| `backend.log` | Uvicorn / Backend stdout |
| `frontend.log` | Next.js / Frontend stdout |

```bash
tail -f backend/logs/portfolio_monitor.log   # live mitverfolgen
grep ERROR backend/logs/portfolio_monitor.log
tail -50 backend/logs/ibkr_connection.log
```

Rotation: 5 MB / 3 Backups → max. ~20 MB pro Komponente.

---

## Paper vs. Live – Safety Guard

```env
# Paper (default, sicher)
IBKR_MODE=paper
IBKR_PORT=4002

# Live (beide Flags erforderlich)
IBKR_MODE=live
IBKR_PORT=4001
IBKR_LIVE_CONFIRMED=true
```

Beim Start geprüft: Mismatch oder fehlende Confirmation → RuntimeError, kein Start.

---

## Komponenten-Übersicht

```
backend/src/tools/
├── logger.py                   ← Zentrales Logging (v0.1.1)
├── ibkr_connection.py          ← IB Gateway + Safety Guard (v0.1.1)
├── ibkr_tool.py                ← 8 LangChain Tools (v0.1.2)
└── portfolio_monitor.py        ← Scheduled News Monitor (v0.1.1)

backend/src/agents/middlewares/
└── dangling_tool_call_middleware.py  ← xAI-Fix: leere AIMessage-Content (v0.1.2)

config.yaml                     ← Tool-Registrierung (inkl. ibkr-Gruppe, v0.1.2)

scripts/
├── wsl-startup.sh              ← WSL2 Autostart
├── windows-portproxy.ps1       ← Windows Port-Proxy
└── restart.sh                  ← DeerFlow Neustart (v0.1.1)

backend/
├── .env                        ← Secrets (NICHT in Git)
├── .env.example                ← Template (in Git)
└── logs/                       ← Log-Dateien (NICHT in Git)
```

---

## IBKR Tools – Referenz (v0.1.2)

Alle Tools sind in `config.yaml` unter `group: ibkr` registriert und werden dem Agenten automatisch bereitgestellt.

| Tool | Beschreibung | Beispiel-Prompt |
|---|---|---|
| `get_account_info` | Kontostand, Buying Power, PnL | „Zeig meinen Kontostand" |
| `get_positions` | Alle offenen Positionen | „Was habe ich im Depot?" |
| `get_market_data` | Kurs für Aktie/ETF | „TSLA-Kurs jetzt" |
| `place_order` | Aktien/ETF kaufen oder verkaufen | „Kaufe 10 AAPL" |
| `get_open_orders` | Alle offenen Orders | „Zeig meine offenen Orders" |
| `cancel_order` | Order stornieren | „Storniere Order 42" |
| `get_forex_rate` | Wechselkurs (Bid/Ask/Mid) | „EUR/USD aktuell?" |
| `place_forex_order` | Währungstausch | „Kaufe 10 000 EUR gegen USD" |

### Forex-Details

- Exchange: `IDEALPRO` (automatisch gesetzt)
- `quantity` = Betrag in der **Basiswährung** (linke Seite des Paares)
  - `EURUSD` + `quantity=10000` → 10 000 EUR kaufen
  - `GBPUSD` + `quantity=5000` + `action=SELL` → 5 000 GBP verkaufen
- Limit-Order: `order_type="LMT"` + `limit_price=1.0850`
- Unterstützte Paare: alle bei IBKR verfügbaren (EURUSD, GBPUSD, USDJPY, EURGBP, USDCHF, …)

---

## Bekannte Architektur-Fallen (Lessons Learned)

### 1. ib_insync + Python 3.12 + LangGraph Thread-Pool

**Symptom:** `RuntimeError: There is no current event loop in thread`

**Ursache:** `ib_insync`'s `Client.sendMsg()` ruft `asyncio.get_event_loop()` auf. In Python 3.12 erzeugt das in Threads ohne eigenen Loop eine Exception (vorher wurde still ein neuer Loop erstellt).

**Fix:** Alle ib_insync-Calls, die `sendMsg()` triggern (`reqMktData`, `placeOrder`, `cancelOrder`), werden als `async def`-Wrapper über `ibkr_submit()` auf dem dedizierten `ibkr-loop`-Thread ausgeführt:

```python
async def _req():
    return ib.reqMktData(contract, "", False, False)
ticker = ibkr_submit(_req())
```

**Faustregel:** Alles, was Daten über den Socket schickt, braucht den Loop. Reine Getter (`accountValues()`, `positions()`, `openTrades()`) greifen nur auf den lokalen Cache zu und sind sicher.

---

### 2. xAI/Grok: leere AIMessage-Content nach Tool-Call

**Symptom:** `openai.BadRequestError: 400 – Each message must have at least one content element`

**Ursache:** Nach einem Tool-Call erzeugt LangGraph eine `AIMessage` mit `tool_calls=[...]` aber `content=""`. xAI/Grok lehnt das ab (Anthropic und OpenAI akzeptieren es).

**Fix:** `DanglingToolCallMiddleware._fix_empty_ai_content()` ersetzt vor jedem Model-Call leeren Content in AIMessages mit tool_calls durch `" "` (Leerzeichen).

**Gilt nur für xAI.** Bei Modellwechsel zu Claude/GPT kann diese Logik stehen bleiben – sie ist harmlos.

---

### 3. Tools in config.yaml registrieren

**Symptom:** Tool ist implementiert und getestet, aber der Agent nutzt es nie. Stattdessen macht er Web-Suche oder gibt auf.

**Ursache:** Jedes Tool muss explizit in `config.yaml` unter `tools:` eingetragen sein. Ohne Eintrag weiß `get_available_tools()` nichts von seiner Existenz.

**Fix:**
```yaml
tool_groups:
  - name: ibkr          # ← Gruppe definieren

tools:
  - name: place_forex_order
    group: ibkr
    use: src.tools.ibkr_tool:place_forex_order   # ← Module:Variable
```

**Nach jeder Änderung an config.yaml:** Backend neu starten (`make stop && make dev`).

---

### 4. Dedizierter asyncio-Loop für ib_insync

**Warum:** LangGraph hat einen eigenen asyncio-Loop im Main-Thread. ib_insync braucht seinen eigenen Loop, der dauerhaft läuft (`run_forever()`). Beide Loops dürfen sich nicht ins Gehege kommen.

**Lösung:** `IBKRConnectionManager` startet beim ersten Aufruf einen Daemon-Thread `ibkr-loop`, der `asyncio.set_event_loop(self._loop)` + `self._loop.run_forever()` ausführt. Alle ib_insync-Coroutinen werden via `asyncio.run_coroutine_threadsafe(coro, self._loop)` übergeben.

```
LangGraph Main Loop          ibkr-loop Thread
        │                          │
        │ ibkr_submit(coro) ───────►│ run_coroutine_threadsafe
        │ future.result() ◄─────────│ (blockiert bis fertig)
        │                          │
```

---

### 5. IB Gateway Trusted IPs – WSL2-Subnetz eintragen

**Symptom:** `nc -zv <windows-ip> 4002` gelingt, aber `ib.connect()` gibt nur `b''` zurück. Kein Fehler, kein Timeout — stille Verbindung.

**Ursache:** IB Gateway prüft die Trusted-IP-Liste nach dem TCP-Handshake. Die WSL2-IP (`172.24.x.x`) ist eine andere als die Windows-Host-IP (`172.24.128.1`). Nur letztere war eingetragen.

**Fix:** In IB Gateway: `Configure → API → Trusted IPs` → `172.24.0.0/16` eintragen (gesamtes WSL2-Subnetz).

**Diagnose:**
```bash
hostname -I   # → zeigt die tatsächliche WSL2-Client-IP
```

**Merke:** Die Windows-IP (Route default) ≠ die IP, die IB Gateway als Client sieht. WSL2 NAT ändert die Quell-IP nicht; IB Gateway sieht die echte WSL2-IP.

---

### 6. `langgraph dev` watchfiles-Absturz

**Symptom:** Services laufen scheinbar, aber nach 10–30 Sekunden gibt LangGraph `2 changes detected` aus und startet neu. Laufende Chat-Requests brechen ab (502 Bad Gateway).

**Ursache:** `langgraph dev` nutzt watchfiles für Hot-Reload. In der WSL2-Umgebung erkennt watchfiles auch Datei-Metadaten-Updates (z.B. durch APScheduler-Logs) als Änderungen.

**Fix:** `--no-reload` Flag:
```bash
uv run langgraph dev --port 2024 --no-browser --allow-blocking --no-reload
```

Bereits in `start.sh` und `scripts/restart.sh` eingetragen.

**Hinweis:** `--no-reload` deaktiviert nur den Code-Hot-Reload. Nach Code-Änderungen muss `make stop && make dev` manuell ausgeführt werden.

---

## Technische Schulden (nicht vergessen)

- [x] IB Gateway Auto-Login nach Saturday-Disconnect → IBC-Setup, siehe `docs/IBC_SETUP.md` + `scripts/ibc-setup.ps1`
- [x] `restart.sh` auf neuen Stack (LangGraph + Gateway + Nginx) → erledigt v0.1.3
- [ ] Health-check Endpoint im Backend (`/health`)
- [ ] APScheduler-Logs in `logs/` leiten
- [ ] `git add -p` konsequent nutzen – nie versehentlich `.env` committen
- [ ] Forex-Positionen in `get_positions` korrekt anzeigen (secType=CASH)
