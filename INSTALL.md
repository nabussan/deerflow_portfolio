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

📺 Öffne: `http://localhost:3000/workspace`

---

## Remote-Zugriff (W541 als Server)

### Windows Port-Weiterleitung (PowerShell als Administrator)
```powershell
# WSL2-IP ermitteln
wsl hostname -I

# Ports weiterleiten
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=<WSL2-IP>
netsh interface portproxy add v4tov4 listenport=2026 listenaddress=0.0.0.0 connectport=2026 connectaddress=<WSL2-IP>
netsh interface portproxy add v4tov4 listenport=8001 listenaddress=0.0.0.0 connectport=8001 connectaddress=<WSL2-IP>

# Firewall
New-NetFirewallRule -DisplayName "DeerFlow Frontend" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
New-NetFirewallRule -DisplayName "DeerFlow Gateway" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
New-NetFirewallRule -DisplayName "DeerFlow nginx" -Direction Inbound -Protocol TCP -LocalPort 2026 -Action Allow
```

> ⚠️ Die WSL2-IP ändert sich bei jedem Windows-Neustart!
> Port-Weiterleitung muss nach jedem Neustart neu gesetzt werden (→ Autostart-Skript geplant für v0.2)

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
| WSL2-IP nach Neustart geändert | Port-Weiterleitung neu setzen |

---

## Wöchentliche Wartung

IB Gateway hat eine wöchentliche Zwangstrennung (Samstag Nacht):
1. Telegram-Benachrichtigung kommt automatisch
2. IB Gateway auf Windows neu starten und einloggen
3. DeerFlow läuft weiter – Auto-Reconnect greift

**Aufwand: ~1 Minute pro Woche** ✅
