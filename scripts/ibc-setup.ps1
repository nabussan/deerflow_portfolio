# ibc-setup.ps1 - IBC (IB Controller) einrichten und Scheduled Task aktualisieren
#
# Voraussetzungen:
#   1. IBC ZIP von https://github.com/IbcAlpha/IBC/releases heruntergeladen und
#      nach C:\IBC\ entpackt (IBGatewayStart.bat muss dort liegen)
#   2. IB Gateway bereits installiert unter C:\Jts\ibgateway\
#   3. Skript als Administrator ausfuehren
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ibc-setup.ps1

param(
    [string]$IbcDir      = "C:\IBC",
    [string]$GatewayDir  = "C:\Jts\ibgateway",
    [string]$IbUsername  = "",
    [string]$IbPassword  = "",
    [string]$TradingMode = "paper"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== IBC Setup fuer IB Gateway ===" -ForegroundColor Cyan
Write-Host ""

# IBC herunterladen und entpacken falls nicht vorhanden
if (-not (Test-Path $IbcDir)) {
    Write-Host "C:\IBC nicht gefunden - lade IBC automatisch herunter..." -ForegroundColor Yellow

    try {
        $ApiUrl  = "https://api.github.com/repos/IbcAlpha/IBC/releases/latest"
        $Headers = @{ "User-Agent" = "ibc-setup-script" }
        $Release = Invoke-RestMethod -Uri $ApiUrl -Headers $Headers
        $Asset   = $Release.assets | Where-Object { $_.name -like "IBCWin*.zip" } | Select-Object -First 1

        if (-not $Asset) {
            Write-Host "FEHLER: Kein Windows-ZIP in aktuellem Release gefunden." -ForegroundColor Red
            exit 1
        }

        $ZipPath = Join-Path $env:TEMP $Asset.name
        Write-Host "Lade herunter: $($Asset.name) ($([math]::Round($Asset.size/1MB, 1)) MB)..."
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $ZipPath -UseBasicParsing

        Write-Host "Entpacke nach $IbcDir ..."
        Expand-Archive -Path $ZipPath -DestinationPath $IbcDir -Force
        Remove-Item $ZipPath

        Write-Host "IBC $($Release.tag_name) installiert." -ForegroundColor Green
    } catch {
        Write-Host "FEHLER beim Herunterladen: $_" -ForegroundColor Red
        Write-Host "Manuell herunterladen: https://github.com/IbcAlpha/IBC/releases" -ForegroundColor Yellow
        exit 1
    }
}

$IbcScript = Join-Path $IbcDir "IBGatewayStart.bat"
if (-not (Test-Path $IbcScript)) {
    Write-Host "FEHLER: $IbcScript nicht gefunden - IBC korrekt entpackt?" -ForegroundColor Red
    exit 1
}

# Gateway-Version ermitteln
$GatewayVersionDir = Get-ChildItem -Path $GatewayDir -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1

if (-not $GatewayVersionDir) {
    Write-Host "FEHLER: Kein Versionsordner in $GatewayDir gefunden." -ForegroundColor Red
    exit 1
}

$GatewayVersion = $GatewayVersionDir.Name
Write-Host "IB Gateway Version erkannt: $GatewayVersion"

# Zugangsdaten abfragen
if (-not $IbUsername) {
    $IbUsername = Read-Host "LYNX/IBKR Benutzername"
}
if (-not $IbPassword) {
    $SecurePassword = Read-Host "LYNX/IBKR Passwort" -AsSecureString
    $IbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    )
}

# config.ini schreiben (ohne Here-String)
$ConfigPath = Join-Path $IbcDir "config.ini"

$lines = @(
    "# IBC Configuration - automatisch erstellt von ibc-setup.ps1",
    "# Doku: https://github.com/IbcAlpha/IBC/blob/master/userguide.md",
    "",
    "IbLoginId=$IbUsername",
    "IbPassword=$IbPassword",
    "TradingMode=$TradingMode",
    "",
    "ReadOnlyLogin=no",
    "AcceptNonBrokerageAccountWarning=yes",
    "LoginDialogDisplayTimeout=60",
    "IbAutoClosedown=no",
    "AcceptBidAskLastSizeDisplayUpdateNotification=accept"
)

[System.IO.File]::WriteAllLines($ConfigPath, $lines, [System.Text.Encoding]::ASCII)
Write-Host "config.ini geschrieben nach: $ConfigPath" -ForegroundColor Green

# Scheduled Task aktualisieren
$TaskName = "IBGateway-Autostart"

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Alter Task '$TaskName' entfernt."
}

$Argument = "/c `"$IbcScript`" $GatewayVersion `"$ConfigPath`" `"$IbcDir`" Gateway"
$Action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $Argument
$Trigger  = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Scheduled Task '$TaskName' erstellt." -ForegroundColor Green

# Test-Start anbieten
Write-Host ""
Write-Host "IBC eingerichtet. IB Gateway jetzt via IBC starten? (j/n)" -ForegroundColor Yellow
$Answer = Read-Host
if ($Answer -eq "j") {
    Write-Host "Starte IB Gateway via IBC..."
    Start-Process "cmd.exe" -ArgumentList $Argument -WindowStyle Normal
    Write-Host "IB Gateway wird gestartet - bitte warte 30 Sekunden." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Setup abgeschlossen ===" -ForegroundColor Green
Write-Host ""
Write-Host "Naechste Schritte:" -ForegroundColor Cyan
Write-Host "  1. IB Gateway oeffnet sich und loggt automatisch ein"
Write-Host "  2. Beim naechsten Windows-Start startet IBC automatisch"
Write-Host "  3. Nach Saturday-Disconnect loggt IBC automatisch neu ein"
Write-Host ""
Write-Host "IBC-Log: $IbcDir\twsstart.log"
Write-Host "Gateway-Log: $env:USERPROFILE\Jts\"
