# IBC (IB Controller) Setup

> **Ziel:** Automatischer IB Gateway Login nach Saturday-Night-Disconnect und Windows-Neustart.
> **Status:** Bereit zur Durchführung
> **Voraussetzung:** IB Gateway läuft bereits stabil (Phase 3 Tests bestanden)

---

## Was ist IBC?

IBC ist ein Open-Source-Tool, das IB Gateway headless startet und automatisch einloggt.
Es übernimmt das Login-Formular, akzeptiert Warnungen und hält die Verbindung am Leben.

- GitHub: https://github.com/IbcAlpha/IBC
- Entwickelt von der Community, gewartet von `IbcAlpha`
- Offiziell von Interactive Brokers empfohlen für automatisierte Setups

---

## Einmaliges Setup (Windows, ~10 Minuten)

### Schritt 1 – IBC herunterladen

1. Aktuelle Release-Version öffnen: https://github.com/IbcAlpha/IBC/releases
2. `IBCWin_x.y.z.zip` herunterladen (Windows-Version)
3. ZIP nach `C:\IBC\` entpacken

Prüfen, ob `C:\IBC\IBGatewayStart.bat` existiert.

### Schritt 2 – Setup-Skript ausführen

PowerShell **als Administrator** öffnen, dann:

```powershell
cd C:\Users\deerflow
# Skript aus WSL2-Verzeichnis kopieren oder direkt aufrufen:
powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\deerflow\deer-flow\scripts\ibc-setup.ps1"
```

Das Skript:
- Erkennt die installierte IB Gateway Version automatisch
- Fragt Benutzername und Passwort ab (nicht in Git gespeichert)
- Schreibt `C:\IBC\config.ini` mit den Zugangsdaten
- Löscht den alten `IBGateway-Autostart` Task
- Erstellt neuen Task, der IBC (statt `ibgateway.exe` direkt) beim Anmelden startet
- Bietet optionalen Test-Start an

### Schritt 3 – Testen

```powershell
# Scheduled Task manuell starten:
Start-ScheduledTask -TaskName "IBGateway-Autostart"
```

Erwartetes Verhalten:
- IB Gateway öffnet sich
- Login-Formular wird automatisch ausgefüllt
- IB Gateway ist nach ~30 Sekunden eingeloggt
- WSL2 → `nc -zv <IBKR_HOST> 4002` → succeeded

---

## Wie IBC den Saturday-Disconnect behandelt

| Ereignis | Ohne IBC | Mit IBC |
|---|---|---|
| Sa. 23:00 Disconnect | Manuelle Re-Login erforderlich | IBC erkennt Logout, loggt automatisch wieder ein |
| Windows-Neustart | IBGateway-Autostart startet `ibgateway.exe`, wartet auf Login | IBC loggt automatisch ein |
| Gateway-Absturz | Kein Neustart | IBC startet Gateway neu (Scheduled Task `RestartCount=3`) |

---

## Konfiguration (`C:\IBC\config.ini`)

Wichtige Parameter:

```ini
IbLoginId=dein_benutzername
IbPassword=dein_passwort
TradingMode=paper          # "paper" oder "live"
ReadOnlyLogin=no
AcceptNonBrokerageAccountWarning=yes
IbAutoClosedown=no         # Gateway läuft dauerhaft
LoginDialogDisplayTimeout=60
```

> Die config.ini enthält das Passwort im Klartext — sie liegt nur lokal auf Windows und ist nicht im Git-Repository.

---

## Troubleshooting

### IBC startet, aber Login schlägt fehl

- Falsches Passwort? → `C:\IBC\config.ini` prüfen
- Zwei-Faktor-Authentifizierung aktiv? → In IBKR-Einstellungen für API-Zugang deaktivieren oder `IbcTwoFactorMethod` konfigurieren (siehe IBC User Guide)
- LYNX-spezifische Login-Seite? → `IbLoginId` muss der exakte Benutzername (ohne `@domain`) sein

### IBC-Logs

```
C:\IBC\twsstart.log         # IBC-Startprotokoll
%USERPROFILE%\Jts\*.log     # IB Gateway eigene Logs
```

### Scheduled Task zeigt "Last Run Result: 0x1"

Task ohne Admin-Rechte ausgeführt → Task in Aufgabenplanung → Eigenschaften → "Mit höchsten Berechtigungen ausführen" aktivieren.

---

## Rollback

Falls IBC nicht funktioniert, Scheduled Task auf direkten IB Gateway Start zurücksetzen:

```powershell
$Action = New-ScheduledTaskAction `
    -Execute "C:\Jts\ibgateway\1037\ibgateway.exe"
$Trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "IBGateway-Autostart" -Action $Action -Trigger $Trigger -Force
```

---

## Referenzen

- IBC User Guide: https://github.com/IbcAlpha/IBC/blob/master/userguide.md
- IBC Releases: https://github.com/IbcAlpha/IBC/releases
- IBC für LYNX: Kompatibel (LYNX nutzt IB-Infrastruktur)
