# Installation Guide

> Getestet auf Ubuntu 24.04 LTS / WSL2 unter Windows 10/11

## Voraussetzungen

### Windows (Host)
- Windows 10/11
- WSL2 aktiviert
- Ubuntu 24.04 LTS installiert (`wsl --install -d Ubuntu`)
- [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) installiert
- [Tailscale](https://tailscale.com/download) (optional, für Remote-Zugriff)

### IB Gateway konfigurieren
1. IB Gateway starten → **Paper Trading** auswählen
2. **Konfigurieren → API → Einstellungen:**
   - ✅ ActiveX und Socket-Clients aktivieren
   - ❌ Schreibgeschützte API deaktivieren
   - Socket Port: `4002`
   - Vertrauenswürdige IPs: WSL2-IP eintragen
3. WSL2-IP ermitteln (in WSL2):
```bash
   hostname -I | awk '{print $1}'
```

---

## WSL2 Installation

### Schnellinstallation (empfohlen)
```bash
curl -LsSf https://raw.githubusercontent.com/nabussan/deerflow_portfolio/portfolio/install.sh | bash
```

### Manuelle Installation

#### 1. System-Updates
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git nginx
sudo mkdir -p /usr/share/nginx/logs
```

#### 2. uv (Python Package Manager)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

#### 3. Node.js 22 via nvm
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
nvm alias default 22
```

#### 4. pnpm
```bash
sudo npm install -g pnpm
```

#### 5. Repo clonen
```bash
cd ~
git clone https://github.com/nabussan/deerflow_portfolio.git deer-flow
cd deer-flow
git checkout portfolio
```

#### 6. Dependencies installieren
```bash
cd ~/deer-flow/backend
uv sync
uv add ib_insync apscheduler

cd ~/deer-flow/frontend
pnpm install
```

#### 7. Konfiguration
```bash
cd ~/deer-flow
cp config.example.yaml config.yaml
nano config.yaml
cp backend/.env.example backend/.env
nano backend/.env
echo 'NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://localhost:2026/api/langgraph"' > frontend/.env.local
```

##### backend/.env Pflichtfelder
```env
XAI_API_KEY=
TAVILY_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
IBKR_HOST=
IBKR_PORT=4002
```

---

## DeerFlow starten
```bash
cd ~/deer-flow
sudo nginx -c /home/$(whoami)/deer-flow/docker/nginx/nginx.local.conf -p /usr/share/nginx/
./start.sh
```

📺 Öffne: `http://localhost:2026/workspace`

---

## Remote-Zugriff (W541 als Server)

### Zugriffs-URLs

| Client | URL |
|---|---|
| Lokal (W541) | `http://localhost:2026/workspace` |
| LAN (z.B. P53) | `http://<Windows-LAN-IP>:2026/workspace` |
| Remote via Tailscale | `http://<Tailscale-IP>:2026/workspace` |

> **Wichtig:** Von anderen Geräten im Netz immer die **Windows-Host-IP** verwenden (z.B. `192.168.1.x`), **nicht** die WSL2-IP (`172.24.x.x`) — die ist von außen nicht erreichbar.

Windows-IPs ermitteln:
```powershell
# In PowerShell auf W541:
ipconfig | findstr /i "IPv4"
# Tailscale-IP steht beim Adapter "Tailscale"
```

### Windows Port-Weiterleitung einrichten (PowerShell als Administrator)

> ⚠️ Die WSL2-IP ändert sich bei jedem Windows-Neustart — daher immer erst alte Regeln löschen, dann neu setzen!

```powershell
# WSL2-IP ermitteln
$wslIP = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "WSL2-IP: $wslIP"

# Alte Regeln entfernen (wichtig: verhindert doppelte Einträge nach Neustart)
netsh interface portproxy delete v4tov4 listenport=2026 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=8001 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=3000 listenaddress=0.0.0.0

# Neue Regeln setzen: WSL2-Ports nach außen weiterleiten
netsh interface portproxy add v4tov4 listenport=2026 listenaddress=0.0.0.0 connectport=2026 connectaddress=$wslIP
netsh interface portproxy add v4tov4 listenport=8001 listenaddress=0.0.0.0 connectport=8001 connectaddress=$wslIP

# IBC-Port: WSL2 → IB Gateway auf Windows (wird von wsl-startup.sh benötigt)
# Achtung: listenaddress ist hier die vEthernet(WSL)-IP, NICHT 0.0.0.0
$vethIP = (Get-NetIPAddress -InterfaceAlias 'vEthernet (WSL)' -AddressFamily IPv4).IPAddress
netsh interface portproxy delete v4tov4 listenport=4002 listenaddress=$vethIP
netsh interface portproxy add v4tov4 listenport=4002 listenaddress=$vethIP connectport=4002 connectaddress=127.0.0.1

# Firewall-Regeln (einmalig, falls Windows Firewall aktiv)
New-NetFirewallRule -DisplayName "DeerFlow Gateway" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
New-NetFirewallRule -DisplayName "DeerFlow nginx" -Direction Inbound -Protocol TCP -LocalPort 2026 -Action Allow

# Aktuelle Regeln prüfen
netsh interface portproxy show all
```

**Autostart einrichten** (einmalig, PowerShell als Administrator):

Das Skript `C:\Users\<Dein-Username>\portproxy.ps1` mit obigem Inhalt anlegen, dann als geplante Aufgabe registrieren:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File C:\Users\$env:USERNAME\portproxy.ps1"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest
Register-ScheduledTask -TaskName "DeerFlow-PortProxy" -Action $action `
    -Trigger $trigger -Principal $principal -Force
```

Danach läuft die Port-Weiterleitung automatisch bei jedem Windows-Login.

---

## Bekannte Probleme

| Problem | Lösung |
|---|---|
| `pnpm: command not found` | `sudo npm install -g pnpm` |
| `uv: command not found` | `source ~/.bashrc` |
| Node.js zu alt | `nvm install 22 && nvm use 22` |
| IBKR Timeout | Windows-IP prüfen: `ip route | grep default | awk '{print $3}'` |
| LangGraph startet nicht | `fuser -k 2024/tcp && ./start.sh` |
| nginx Port belegt | `sudo nginx -s reload` |
| WSL2-IP nach Neustart geändert | Port-Weiterleitung neu setzen (`portproxy.ps1`) — zuerst löschen, dann neu setzen! |
| App von P53/anderem Gerät nicht erreichbar | Windows-LAN-IP verwenden, nicht WSL2-IP (`172.24.x.x`) |
| IB Gateway nicht erreichbar (Port 4002) | vEthernet(WSL)-Regel fehlt — `portproxy.ps1` erneut ausführen |
| nvm nicht gefunden beim Autostart | `wsl-startup.sh` sourced `.bashrc` nicht — nvm explizit laden: `source $NVM_DIR/nvm.sh` |

---

## Wöchentliche Wartung

IB Gateway hat eine wöchentliche Zwangstrennung (Samstag Nacht):
1. Telegram-Benachrichtigung kommt automatisch
2. IB Gateway auf Windows neu starten und einloggen
3. DeerFlow läuft weiter – Auto-Reconnect greift

**Aufwand: ~1 Minute pro Woche** ✅
