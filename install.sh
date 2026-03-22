#!/bin/bash
# DeerFlow Portfolio – Installation Script
# Ubuntu 24.04 LTS / WSL2

set -e

echo "🦌 DeerFlow Portfolio – Installation"
echo "====================================="

echo "📦 System-Updates..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git nginx
sudo mkdir -p /usr/share/nginx/logs

echo "🐍 uv installieren..."
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc || true
export PATH="$HOME/.local/bin:$PATH"

echo "⬡ Node.js 22 installieren..."
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
nvm alias default 22

echo "📦 pnpm installieren..."
sudo npm install -g pnpm

echo "📥 Repo clonen..."
cd ~
if [ -d "deer-flow" ]; then
    echo "deer-flow existiert bereits – überspringe clone."
else
    git clone https://github.com/nabussan/deerflow_portfolio.git deer-flow
fi
cd ~/deer-flow
git checkout main
git pull origin main

echo "🐍 Backend-Dependencies..."
cd ~/deer-flow/backend
uv sync
uv add ib_insync apscheduler

echo "⬡ Frontend-Dependencies..."
cd ~/deer-flow/frontend
pnpm install

echo "⚙️ Konfiguration..."
cd ~/deer-flow
[ ! -f config.yaml ] && cp config.example.yaml config.yaml && echo "✅ config.yaml angelegt"
[ ! -f backend/.env ] && cp backend/.env.example backend/.env && echo "✅ backend/.env angelegt"
[ ! -f frontend/.env.local ] && echo 'NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://localhost:2026/api/langgraph"' > frontend/.env.local

chmod +x ~/deer-flow/start.sh

echo ""
echo "====================================="
echo "✅ Installation abgeschlossen!"
echo ""
echo "Nächste Schritte:"
echo "1. nano ~/deer-flow/backend/.env  (API Keys eintragen)"
echo "2. nano ~/deer-flow/config.yaml   (LLM konfigurieren)"
echo "3. IB Gateway auf Windows starten (Port 4002)"
echo "4. cd ~/deer-flow && sudo nginx -c /home/\$(whoami)/deer-flow/docker/nginx/nginx.local.conf -p /usr/share/nginx/ && ./start.sh"
echo "📺 http://localhost:3000/workspace"
