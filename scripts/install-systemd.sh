#!/bin/bash
# install-systemd.sh – Installiert DeerFlow systemd-Services
#
# Voraussetzung: systemd=true in /etc/wsl.conf muss aktiv sein
# (WSL-Neustart nötig wenn gerade noch command= verwendet wird)
#
# Aufruf: sudo bash scripts/install-systemd.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="$REPO_ROOT/scripts/systemd"
SERVICE_DEST="/etc/systemd/system"

# Prüfen ob systemd läuft
if ! systemctl --version &>/dev/null || [ "$(ps -p 1 -o comm=)" != "systemd" ]; then
    echo "✗ systemd ist nicht PID 1. Bitte zuerst /etc/wsl.conf anpassen:"
    echo ""
    echo "  [boot]"
    echo "  systemd=true"
    echo ""
    echo "  Dann WSL neu starten: wsl --shutdown (in PowerShell)"
    exit 1
fi

echo "Installiere DeerFlow systemd-Services..."

SERVICES=(
    deerflow-setup.service
    deerflow-portfolio-monitor.service
    deerflow-langgraph.service
    deerflow-gateway.service
    deerflow-frontend.service
    deerflow-nginx.service
)

# Services kopieren und aktivieren
for svc in "${SERVICES[@]}"; do
    echo "  → $svc"
    cp "$SYSTEMD_DIR/$svc" "$SERVICE_DEST/$svc"
done

systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
    systemctl enable "$svc"
done

echo ""
echo "✓ Services installiert und aktiviert."
echo ""
echo "Starten:"
echo "  sudo systemctl start deerflow-setup"
echo "  sudo systemctl start deerflow-portfolio-monitor"
echo "  sudo systemctl start deerflow-langgraph deerflow-gateway deerflow-frontend deerflow-nginx"
echo ""
echo "Status prüfen:"
echo "  systemctl status deerflow-portfolio-monitor"
echo "  journalctl -u deerflow-portfolio-monitor -f"
