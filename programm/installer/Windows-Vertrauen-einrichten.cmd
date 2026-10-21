@echo off
rem Rohrlaser Angebotskalkulation: Windows-Vertrauen einrichten (einmal je PC und Benutzer)
rem  - nimmt bei Setup.exe und ZIP neben dieser Datei die Markierung "aus dem Internet" weg (wie Eigenschaften ->
rem    Zulassen); liegt die Datei im Programmordner, bei allen Programmdateien
rem  - traegt das Zertifikat ein, mit dem Programm und Setup signiert sind (fuer den angemeldeten Benutzer)
rem Braucht keine Adminrechte. Nur mit Adminrechten gestartet (Build-Test) gilt das Zertifikat fuer den ganzen PC.
rem Aufruf: Doppelklick | Windows-Vertrauen-einrichten.cmd entfernen | Zusatz /still (ohne Fragen, fuer den Build-Test)
setlocal
set "RL_SKRIPT=%~f0"
set "RL_ARGUMENTE=%*"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$t = [IO.File]::ReadAllText($env:RL_SKRIPT, [Text.Encoding]::UTF8); $global:RL_RC = 0; Invoke-Expression ($t.Substring($t.IndexOf('#' + 'POWERSHELL#'))); exit $global:RL_RC"
exit /b %ERRORLEVEL%

#POWERSHELL#
# Ab hier PowerShell; cmd liest nicht so weit (exit /b oben).
$ErrorActionPreference = 'Stop'
$argumente = @(($env:RL_ARGUMENTE -split '\s+') | Where-Object { $_ } | ForEach-Object { $_.Trim('"').ToLower() })
$entfernen = $argumente -contains 'entfernen'
$still = $argumente -contains '/still'

$name = 'Rohrlaser Angebotskalkulation'
$skriptOrdner = Split-Path -Parent $env:RL_SKRIPT
$istAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

# Zertifikat "Patrick Brundiers" (nur Codesignatur), mit dem der Build signiert. Der Build setzt es hier ein
# (öffentlicher Teil aus dem Secret SIGNATUR_PFX); ohne Secret bleibt die Stelle leer und nur die Freigabe läuft.
$zertifikatText = '@ZERTIFIKAT@'
$zertifikat = $null
if ($zertifikatText -notlike '@*') {
    $zertifikat = New-Object Security.Cryptography.X509Certificates.X509Certificate2(,[Convert]::FromBase64String($zertifikatText))
}

function Meldung($text) { Write-Host $text }

function Speicher($name, $ort) {
    $s = New-Object Security.Cryptography.X509Certificates.X509Store($name, $ort)
    $s.Open('ReadWrite')
    return $s
}

# Root: Windows vertraut der Signatur; TrustedPublisher: Herausgeber ohne Rückfrage.
# Für den Benutzer zeigt Windows beim Eintrag in Root einmal die Frage „Zertifikat installieren?“.
function Zertifikat-Eintragen($ort) {
    if (-not $zertifikat) { Meldung 'Dieser Stand ist nicht signiert, kein Zertifikat einzutragen.'; return }
    foreach ($n in @('Root', 'TrustedPublisher')) {
        $s = Speicher $n $ort
        try { $s.Add($zertifikat) } finally { $s.Close() }
    }
    Meldung "Zertifikat Patrick Brundiers eingetragen ($ort)."
}

function Zertifikat-Entfernen($ort) {
    if (-not $zertifikat) { return }
    foreach ($n in @('TrustedPublisher', 'Root')) {
        $s = Speicher $n $ort
        try {
            $s.Certificates | Where-Object { $_.Thumbprint -eq $zertifikat.Thumbprint } | ForEach-Object { $s.Remove($_) }
        } finally { $s.Close() }
    }
    Meldung "Zertifikat entfernt ($ort)."
}

# Markierung „aus dem Internet“ (Zone.Identifier) entfernen, wie Eigenschaften → Zulassen
function Freigeben {
    $dateien = @(Get-ChildItem -LiteralPath $skriptOrdner -File |
                 Where-Object { $_.Name -like 'Rohrlaser-Angebotskalkulation*' -or $_.Name -like 'Windows-Vertrauen*' })
    if (Test-Path -LiteralPath (Join-Path $skriptOrdner 'Rohrlaser-Angebotskalkulation.exe')) {
        $dateien = @(Get-ChildItem -LiteralPath $skriptOrdner -File -Recurse)     # Programmordner: alle Dateien
    }
    $n = 0
    foreach ($d in $dateien) {
        if (Get-Item -LiteralPath $d.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue) {
            Unblock-File -LiteralPath $d.FullName
            $n++
        }
    }
    Meldung "Markierung „aus dem Internet“ bei $n Datei(en) in $skriptOrdner entfernt."
}

$ort = if ($istAdmin) { 'LocalMachine' } else { 'CurrentUser' }
try {
    if ($entfernen) {
        Meldung "$name – Windows-Vertrauen entfernen"
        Zertifikat-Entfernen $ort
    } else {
        Meldung "$name – Windows-Vertrauen einrichten"
        Freigeben
        Zertifikat-Eintragen $ort
    }
    Meldung ''
    Meldung 'Fertig.'
} catch {
    Meldung "FEHLER: $($_.Exception.Message)"
    $global:RL_RC = 1
}
if (-not $still) { Read-Host 'Eingabetaste zum Schließen' | Out-Null }
