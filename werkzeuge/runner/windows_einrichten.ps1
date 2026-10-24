# Richtet auf Patricks PC den eigenen GitHub-Runner für den Windows-Build ein (kostet kein Actions-Kontingent).
# Anleitung: werkzeuge/runner/ANLEITUNG.md. Aufruf in PowerShell 'Als Administrator ausführen':
#   powershell -ExecutionPolicy Bypass -File windows_einrichten.ps1 -Token <Token von GitHub>
# Installiert Git, Python 3.12, PowerShell 7, Inno Setup, GitHub CLI und die C++-Build-Tools (für den selbst übersetzten
# PyInstaller-Bootloader), legt den Windows-Benutzer 'github-runner' ohne Adminrechte an und richtet den Runner
# 'rohrlaser-windows' (Label rohrlaser) als Dienst unter diesem Benutzer ein. Der Build installiert das Programm
# testweise - unter diesem Benutzer, deine eigene Installation und deine Daten bleiben unberührt.
# Erneut ausführbar: Vorhandenes wird übersprungen.
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Repo = "https://github.com/patrickbrundiers-dev/Rohrlaser-Kalkulation-",
    [string]$Ordner = "C:\actions-runner",
    [switch]$WslAktivHalten        # Aufgabe bei Anmeldung, die WSL-Ubuntu für den Test-Runner laufen lässt
)
$ErrorActionPreference = "Stop"
$istAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $istAdmin) { throw "Bitte PowerShell mit Rechtsklick → 'Als Administrator ausführen' starten." }

Write-Host "1/5 Werkzeuge installieren (winget, kann 15-30 Minuten dauern) ..."
$pakete = @(
    @("Git.Git", ""),
    @("Python.Python.3.12", ""),
    @("Microsoft.PowerShell", ""),
    @("JRSoftware.InnoSetup", ""),
    @("GitHub.cli", ""),
    @("Microsoft.VisualStudio.2022.BuildTools",
      "--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended")
)
foreach ($p in $pakete) {
    winget list --id $p[0] --exact --accept-source-agreements *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "   $($p[0]) schon da"; continue }
    $arg = @("install", "--id", $p[0], "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements")
    if ($p[1]) { $arg += @("--override", $p[1]) }
    winget @arg --scope machine           # für alle Benutzer, damit auch github-runner es findet
    if ($LASTEXITCODE -ne 0) { winget @arg }   # Paket ohne Auswahl 'für alle Benutzer'
    if ($LASTEXITCODE -ne 0) { throw "Installation von $($p[0]) fehlgeschlagen (Rückgabewert $LASTEXITCODE)" }
}

Write-Host "2/5 Windows-Benutzer github-runner (ohne Adminrechte) ..."
$benutzer = "github-runner"
# zufälliges Kennwort (groß, klein, Ziffer, Zeichen), nur der Dienst kennt es
$kennwort = "Rl#7" + -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 20 | ForEach-Object { [char]$_ })
$sicher = ConvertTo-SecureString $kennwort -AsPlainText -Force
$angemeldet = Test-Path "$Ordner\.runner"
if (Get-LocalUser -Name $benutzer -ErrorAction SilentlyContinue) {
    if (-not $angemeldet) { Set-LocalUser -Name $benutzer -Password $sicher }   # sonst bliebe der Dienst ohne Kennwort
} else {
    New-LocalUser -Name $benutzer -Password $sicher -PasswordNeverExpires -UserMayNotChangePassword `
        -Description "Dienst für den GitHub-Runner (Rohrlaser)" | Out-Null
}

Write-Host "3/5 Runner herunterladen nach $Ordner ..."
New-Item -ItemType Directory -Force $Ordner | Out-Null
if (-not (Test-Path "$Ordner\config.cmd")) {
    $rel = Invoke-RestMethod "https://api.github.com/repos/actions/runner/releases/latest"
    $v = $rel.tag_name.TrimStart("v")
    $zip = "$env:TEMP\actions-runner-win-x64-$v.zip"
    Invoke-WebRequest "https://github.com/actions/runner/releases/download/v$v/actions-runner-win-x64-$v.zip" -OutFile $zip
    Expand-Archive -Force $zip $Ordner
    Remove-Item $zip
}
icacls $Ordner /grant "${benutzer}:(OI)(CI)M" /T /Q | Out-Null
# Virenscanner soll die frisch gebauten .exe im Arbeitsordner nicht während des Builds sperren
Add-MpPreference -ExclusionPath $Ordner -ErrorAction SilentlyContinue

Write-Host "4/5 Runner bei GitHub anmelden und als Dienst einrichten ..."
Push-Location $Ordner
if ($angemeldet) {
    Write-Host "   Runner ist schon angemeldet (zum Neu-Anmelden erst: .\config.cmd remove --token <Token>)"
} else {
    .\config.cmd --unattended --url $Repo --token $Token --name "rohrlaser-windows" --labels "rohrlaser" `
        --work "_work" --runasservice --windowslogonaccount ".\$benutzer" --windowslogonpassword $kennwort
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Anmelden fehlgeschlagen (Token abgelaufen? Er gilt 1 Stunde.)" }
}
Pop-Location

if ($WslAktivHalten) {
    Write-Host "5/5 Aufgabe 'WSL für GitHub-Runner' bei deiner Anmeldung ..."
    $aktion = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-WindowStyle Hidden -Command wsl.exe -d Ubuntu-24.04 --exec sleep infinity"
    $ausloeser = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $einst = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName "WSL für GitHub-Runner" -Action $aktion -Trigger $ausloeser -Settings $einst -Force |
        Out-Null
} else {
    Write-Host "5/5 (WSL-Aufgabe übersprungen; mit -WslAktivHalten anlegen)"
}
Write-Host ""
Write-Host "Fertig. Unter GitHub → Settings → Actions → Runners steht jetzt 'rohrlaser-windows' (Idle)."
