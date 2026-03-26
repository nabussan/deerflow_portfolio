# ibc-setup.ps1 – IBC (IB Controller) einrichten und Scheduled Task aktualisieren
#
# Voraussetzungen:
#   1. IBC ZIP von https://github.com/IbcAlpha/IBC/releases heruntergeladen und
#      nach C:\IBC\ entpackt (IBCWin64.bat und config.ini müssen dort liegen)
#   2. IB Gateway bereits installiert unter C:\Jts\ibgateway\
#   3. Skript als Administrator ausführen
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ibc-setup.ps1

param(
    [string]$IbcDir      = "C:\IBC",
    [string]$GatewayDir  = "C:\Jts\ibgateway",
    [string]$IbUsername  = "",   # Pflichtfeld – interaktiv abfragen wenn leer
    [string]$IbPassword  = "",   # Pflichtfeld – interaktiv abfragen wenn leer
    [string]$TradingMode = "paper"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== IBC Setup fuer IB Gateway ===" -ForegroundColor Cyan
Write-Host ""

# ── Verzeichnis pruefen ───────────────────────────────────────────────────────

if (-not (Test-Path $IbcDir)) {
    Write-Host "FEHLER: $IbcDir nicht gefunden." -ForegroundColor Red
    Write-Host "IBC herunterladen: https://github.com/IbcAlpha/IBC/releases" -ForegroundColor Yellow
    Write-Host "ZIP nach $IbcDir entpacken, dann Skript erneut ausfuehren." -ForegroundColor Yellow
    exit 1
}

$IbcScript = Join-Path $IbcDir "IBGatewayStart.bat"
if (-not (Test-Path $IbcScript)) {
    Write-Host "FEHLER: $IbcScript nicht gefunden – IBC korrekt entpackt?" -ForegroundColor Red
    exit 1
}

# ── Gateway-Version ermitteln ─────────────────────────────────────────────────

$GatewayVersionDir = Get-ChildItem -Path $GatewayDir -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1

if (-not $GatewayVersionDir) {
    Write-Host "FEHLER: Kein Versionsordner in $GatewayDir gefunden." -ForegroundColor Red
    exit 1
}

$GatewayVersion = $GatewayVersionDir.Name
Write-Host "IB Gateway Version erkannt: $GatewayVersion"

# ── Zugangsdaten abfragen ─────────────────────────────────────────────────────

if (-not $IbUsername) {
    $IbUsername = Read-Host "LYNX/IBKR Benutzername"
}
if (-not $IbPassword) {
    $SecurePassword = Read-Host "LYNX/IBKR Passwort" -AsSecureString
    $IbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    )
}

# ── config.ini schreiben ──────────────────────────────────────────────────────

$ConfigPath = Join-Path $IbcDir "config.ini"

$ConfigContent = @"
# IBC Configuration – automatisch erstellt von ibc-setup.ps1
# Doku: https://github.com/IbcAlpha/IBC/blob/master/userguide.md

IbLoginId=$IbUsername
IbPassword=$IbPassword
TradingMode=$TradingMode

# Login-Optionen
ReadOnlyLogin=no
AcceptNonBrokerageAccountWarning=yes
LoginDialogDisplayTimeout=60

# Kein automatischer Neustart
IbAutoClosedown=no

# Paper-Konto-Warnung automatisch bestaetigen
AcceptBidAskLastSizeDisplayUpdateNotification=accept

# API-Einstellungen nicht aendern
"@

$ConfigContent | Out-File -FilePath $ConfigPath -Encoding ASCII -Force
Write-Host "config.ini geschrieben nach: $ConfigPath" -ForegroundColor Green

# ── Scheduled Task aktualisieren ──────────────────────────────────────────────

$TaskName = "IBGateway-Autostart"

# Alten Task entfernen
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Alter Task '$TaskName' entfernt."
}

# Neuer Task: IBC startet IB Gateway mit automatischem Login
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$IbcScript`" $GatewayVersion `"$ConfigPath`" `"$IbcDir`" Gateway"

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host "Scheduled Task '$TaskName' erstellt." -ForegroundColor Green

# ── Test-Start ────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "IBC ist eingerichtet. Moechtest du IB Gateway jetzt via IBC starten? (j/n)" -ForegroundColor Yellow
$Answer = Read-Host
if ($Answer -eq "j") {
    Write-Host "Starte IB Gateway via IBC..."
    Start-Process "cmd.exe" -ArgumentList "/c `"$IbcScript`" $GatewayVersion `"$ConfigPath`" `"$IbcDir`" Gateway" -WindowStyle Normal
    Write-Host "IB Gateway wird gestartet – bitte warte 30 Sekunden." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Setup abgeschlossen ===" -ForegroundColor Green
Write-Host ""
Write-Host "Naechste Schritte:" -ForegroundColor Cyan
Write-Host "  1. IB Gateway oeffnet sich und loggt automatisch ein"
Write-Host "  2. Beim naechsten Windows-Start startet IBC automatisch"
Write-Host "  3. Nach Saturday-Disconnect startet IBC beim naechsten Login automatisch neu"
Write-Host ""
Write-Host "Logs: $IbcDir\twsstart.log (IBC) und IB Gateway Logs in %USERPROFILE%\Jts\"
