# Session Restore – DeerFlow auf W541

Schnellreferenz: Wie kommt man nach einem Neustart, Absturz oder langer Pause
wieder in einen funktionierenden Zustand.

---

## Normalfall: Alles startet automatisch

Nach einem W541-Neustart laufen folgende Dinge **automatisch**:

| Was | Wie | Wann |
|---|---|---|
| IB Gateway | IBC via Scheduled Task `IBGateway-Autostart` | Bei Windows-Anmeldung |
| nginx + DeerFlow | `wsl-startup.sh` via `/etc/wsl.conf` | Bei WSL2-Start |
| IBKR_HOST | Wird in `.env` aktualisiert | In `wsl-startup.sh`, vor DeerFlow |

**Prüfen ob alles läuft:**

```bash
# Im Browser
http://172.24.128.1:2026/workspace

# Oder von WSL2:
curl -s http://localhost:2024/ok        # LangGraph
curl -s http://localhost:8001/health    # Gateway
nc -zv 172.24.128.1 4002               # IB Gateway
```

Chat-Test: „Zeig meinen Kontostand" → NetLiquidation > 0

---

## Services manuell neu starten (ohne Reboot)

```bash
cd ~/deer-flow
bash scripts/restart.sh
```

Das Skript stoppt alle Services, aktualisiert IBKR_HOST und startet alles neu.
Logs: `logs/langgraph.log`, `logs/gateway.log`, `logs/frontend.log`

---

## IB Gateway nicht verbunden

**Checkliste:**

1. IB Gateway läuft? → Windows-Taskleiste prüfen (grünes Icon)
2. Saturday-Disconnect (Sa. ~23:00)? → IBC manuell neu starten:
   ```powershell
   Start-ScheduledTask -TaskName "IBGateway-Autostart"
   ```
3. Port erreichbar?
   ```bash
   nc -zv $(ip route | grep default | awk '{print $3}') 4002
   ```
4. WSL2-IP in Trusted IPs? → IB Gateway: `Configure → API → Trusted IPs` → `172.24.0.0/16`
5. Startup-Log prüfen:
   ```bash
   cat /tmp/startup.log
   tail -30 backend/logs/ibkr_connection.log
   ```

---

## Code-Session wiederherstellen (P53 → W541)

### 1. Verbindung herstellen

```bash
# Tailscale-Verbindung prüfen
tailscale ping 100.88.180.28

# SSH auf W541
ssh deerflow@100.88.180.28

# Oder VS Code Remote SSH: F1 → "Remote-SSH: Connect to Host" → w541
```

### 2. Repository-Stand prüfen

```bash
cd ~/deer-flow
git status
git log --oneline -5
```

Arbeits-Branch ist `dev`. Production ist `portfolio`.

### 3. Offene Änderungen vom Remote holen

```bash
git pull origin dev
```

### 4. Services-Status prüfen

```bash
curl -s http://localhost:2024/ok && echo " LG OK"
curl -s http://localhost:8001/health && echo " GW OK"
curl -s -o /dev/null -w "NGX: %{http_code}\n" http://localhost:2026/
```

Falls ein Service nicht läuft:
```bash
bash scripts/restart.sh
```

### 5. Tests laufen lassen

```bash
cd backend
uv run pytest tests/ -v
```

---

## Nach erfolgreichem W541-Reboot-Test: dev → portfolio mergen

```bash
git checkout portfolio
git merge dev
git push origin portfolio
git checkout dev
```

Danach auf W541 ausrollen:
```bash
git pull origin portfolio
bash scripts/restart.sh
```

---

## Wichtige Pfade

| Was | Pfad |
|---|---|
| Repo | `~/deer-flow/` |
| Backend | `~/deer-flow/backend/` |
| Env-Datei | `~/deer-flow/backend/.env` (nicht in Git!) |
| Logs | `~/deer-flow/logs/` |
| IBKR-Log | `~/deer-flow/backend/logs/ibkr_connection.log` |
| Startup-Log | `/tmp/startup.log` |
| IBC-Config | `C:\IBC\config.ini` (Windows) |
| IBC-Log | `C:\IBC\twsstart.log` (Windows) |

---

## Notfall: Alles von Hand starten

```bash
cd ~/deer-flow

# IBKR_HOST aktualisieren
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')
sed -i "s/IBKR_HOST=.*/IBKR_HOST=$WINDOWS_IP/" backend/.env

# Services starten
./scripts/start.sh
```
