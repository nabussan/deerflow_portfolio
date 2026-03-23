# DeerFlow Port-Weiterleitung
# Als Windows-Aufgabe beim Start ausführen

# WSL2-IP ermitteln
$wslIP = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "WSL2-IP: $wslIP"

# Alte Regeln entfernen
netsh interface portproxy reset

# Neue Regeln setzen
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=$wslIP
netsh interface portproxy add v4tov4 listenport=2026 listenaddress=0.0.0.0 connectport=2026 connectaddress=$wslIP
netsh interface portproxy add v4tov4 listenport=8001 listenaddress=0.0.0.0 connectport=8001 connectaddress=$wslIP

Write-Host "✅ Port-Weiterleitung gesetzt für $wslIP"
