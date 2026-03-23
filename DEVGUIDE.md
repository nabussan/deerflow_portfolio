# DeerFlow Portfolio – Developer Guide

> Ergänzung zu README.md für v0.1.1  
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
├── ibkr_tool.py                ← 6 LangChain Tools
└── portfolio_monitor.py        ← Scheduled News Monitor (v0.1.1)

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

## Technische Schulden (nicht vergessen)

- [ ] IB Gateway Auto-Login nach Saturday-Disconnect
- [ ] Health-check Endpoint im Backend (`/health`)
- [ ] APScheduler-Logs in `logs/` leiten
- [ ] `git add -p` konsequent nutzen – nie versehentlich `.env` committen
