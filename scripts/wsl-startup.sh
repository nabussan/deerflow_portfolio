#!/bin/bash
# WSL2 Autostart Script
# Startet nginx und DeerFlow beim WSL2-Start

# Warten bis Netzwerk bereit
sleep 5

# nginx starten
sudo nginx -c /home/$(whoami)/deer-flow/docker/nginx/nginx.local.conf -p /usr/share/nginx/ 2>/dev/null || sudo nginx -s reload

# DeerFlow starten
cd /home/$(whoami)/deer-flow
./start.sh
