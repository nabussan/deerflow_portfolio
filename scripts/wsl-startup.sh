#!/bin/bash
# WSL2 Autostart Script
# Startet nginx und DeerFlow beim WSL2-Start

# Warten bis Netzwerk bereit
sleep 5

# IBKR_HOST zuerst aktualisieren – bevor DeerFlow startet
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')
sed -i "s/IBKR_HOST=.*/IBKR_HOST=$WINDOWS_IP/" /home/$(whoami)/deer-flow/backend/.env
echo "IBKR_HOST gesetzt auf $WINDOWS_IP"

# nginx starten
sudo nginx -c /home/$(whoami)/deer-flow/docker/nginx/nginx.local.conf -p /usr/share/nginx/ 2>/dev/null || sudo nginx -s reload

# DeerFlow starten
cd /home/$(whoami)/deer-flow
./start.sh
