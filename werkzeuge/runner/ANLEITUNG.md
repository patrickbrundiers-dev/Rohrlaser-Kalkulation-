# Eigener GitHub-Runner auf dem Windows-PC

Ein eigener Runner verbraucht **kein Actions-Kontingent**. Der Workflow `.github/workflows/paket.yml` nimmt ihn, sobald
die Repository-Variable `RUNNER` auf `pc` steht; sonst laufen die Jobs wie bisher auf den GitHub-Runnern.

| Job | Eigener PC | Läuft als |
| --- | --- | --- |
| `tests` (ruff, Tests, Anleitung) | Runner `rohrlaser-wsl` in WSL-Ubuntu 24.04 | Dienst in Ubuntu, solange Ubuntu läuft |
| `windows` (Build, Selbsttest, Setup, Release) | Runner `rohrlaser-windows` | Windows-Dienst unter dem Benutzer `github-runner` |

Jobs laufen nur, wenn der PC an ist (Energiesparen: „Nie“ in den Ruhezustand). Sonst warten sie bis zu 24 Stunden.

Sicherheit: Der Runner ist nur in diesem privaten Repository angemeldet. Der Workflow lässt Pull Requests aus Forks
nicht laufen. `github-runner` hat keine Adminrechte; deine Installation und deine Daten bleiben unberührt.

## 1. Token holen (gilt 1 Stunde, für beide Runner)

GitHub → Repository **Rohrlaser-Kalkulation-** → **Settings → Actions → Runners → New self-hosted runner** → Windows.
Im Abschnitt „Configure“ steht `--token AAAA…`. Diese Zeichenfolge kopieren (nur den Token).

## 2. Windows-Runner einrichten

1. Repository als ZIP herunterladen (GitHub → **Code → Download ZIP**) und entpacken; gebraucht wird der Ordner
   `werkzeuge\runner` darin.
2. Startmenü → „PowerShell“ → Rechtsklick → **Als Administrator ausführen**.
3. In den Ordner wechseln und starten:

   ```powershell
   cd "<entpackter Ordner>\werkzeuge\runner"
   powershell -ExecutionPolicy Bypass -File windows_einrichten.ps1 -Token AAAA… -WslAktivHalten
   ```

   Installiert Git, Python 3.12, PowerShell 7, Inno Setup, GitHub CLI und die C++-Build-Tools (dauert 15–30 Minuten),
   legt den Benutzer `github-runner` an und richtet den Dienst ein. `-WslAktivHalten` legt eine Aufgabe an, die bei
   deiner Anmeldung Ubuntu im Hintergrund laufen lässt (für Schritt 3).

## 3. Test-Runner in WSL-Ubuntu einrichten

1. PowerShell als Administrator: `wsl --install -d Ubuntu-24.04`, danach PC neu starten.
2. „Ubuntu 24.04“ aus dem Startmenü öffnen, Benutzername und Kennwort festlegen.
3. Im Ubuntu-Fenster (Pfad an deinen Download anpassen; `C:` heißt dort `/mnt/c`):

   ```bash
   bash "/mnt/c/Users/<DeinName>/Downloads/<entpackter Ordner>/werkzeuge/runner/wsl_einrichten.sh" AAAA…
   ```

   Meldet das Skript „systemd eingeschaltet“: in PowerShell `wsl --shutdown`, Ubuntu neu öffnen, Befehl wiederholen.
   Ist der Token inzwischen abgelaufen, in Schritt 1 einen neuen holen.

## 4. Umschalten

GitHub → **Settings → Secrets and variables → Actions → Variables → New repository variable**:
Name `RUNNER`, Wert `pc`. Zurück auf die GitHub-Runner: Variable löschen oder auf `github` setzen.

Unter **Settings → Actions → Runners** stehen dann `rohrlaser-windows` und `rohrlaser-wsl` mit „Idle“.

## Gut zu wissen

- Auf dem PC wird die Zertifikat-Eintragung (Windows-Vertrauen) nicht getestet, weil `github-runner` keine
  Adminrechte hat; auf dem GitHub-Runner wird sie weiterhin geprüft.
- Pakete bleiben zwischen den Läufen liegen (`C:\Users\github-runner\rohrlaser-venv`, in Ubuntu `~/.local`);
  dadurch sind die Läufe schneller.
- Runner abmelden: in `C:\actions-runner` bzw. `~/actions-runner` `config.cmd remove --token …` /
  `sudo ./svc.sh uninstall && ./config.sh remove --token …` (Token aus Schritt 1).
