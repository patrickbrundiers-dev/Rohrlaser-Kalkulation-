# Rohrlaser-Kalkulation unter Windows: Abhängigkeiten, Betrieb, Updates, Wiederherstellung

Technische Dokumentation zum Auftrag Patrick 26.11.2026 „Systemunabhängigkeit, Windows-Update-Sicherheit und
langfristige Stabilität“ (Stand 0.9.517). Der Prüfbericht mit Befunden und Testergebnissen steht in
[system-audit/WINDOWS_STABILITAET_2611.md](system-audit/WINDOWS_STABILITAET_2611.md).

Grundsatz: Das Programm bringt alles mit, was es zum Laufen braucht, und hängt so wenig wie möglich von dem ab, was
Windows-Updates verändern. Was trotzdem von Windows kommt, steht unten mit dem Verhalten bei einem Fehler.

## 1. Was das Programm selbst mitbringt (app-lokal, im Programmordner)

| Baustein | Version (fest) | Wofür | Festgelegt in |
|---|---|---|---|
| Python-Laufzeit | 3.12 (Build) | gesamtes Programm, eingefroren mit PyInstaller | `.github/workflows/paket.yml` (`python-version`) |
| PyInstaller (Bootloader selbst gebaut) | 6.22.3 | .exe, `_internal` | `paket.yml` |
| Qt / PySide6-Essentials | 6.12.0 | Oberfläche, 3D (OpenGL oder Software), Druckvorschau | `programm/requirements.txt` |
| reportlab + rl_accel | 5.1.0 / 0.9.1 | alle PDFs (Schriften liegen in `rohrlaser/schriften`, keine Windows-Schriften nötig) | `programm/requirements.txt` |
| cryptography | 50.0.1 | Lizenz (Ed25519), Update-Signatur, Admin-Signatur | `programm/requirements.txt` |
| psycopg (binary, mit libpq) | 3.3.9 | Zugriff auf PostgreSQL | `programm/requirements.txt` |
| pypdfium2 / olefile | 5.13.0 / 0.47 | Anfrage-PDFs lesen, Outlook-.msg lesen | `programm/requirements.txt` |
| OpenCascade (cadquery-ocp) | 8.0.1.1.0 | STEP-Messung (`STEP-Import.exe`) | `requirements.txt` |
| PostgreSQL | 16.2 (Wheel pgserver 0.1.4, SHA-256 geprüft) | Datenbank je PC, nur 127.0.0.1 | `paket.yml` |
| Visual-C++-Laufzeit für PostgreSQL | aus dem Build (seit 0.9.517) | `vcruntime140.dll`, `vcruntime140_1.dll`, `msvcp140.dll` neben `postgres.exe` | `paket.yml` |
| Tesseract OCR | 5.4.0.20240606 + tessdata_fast 4.1.0 | Scans lesen | `paket.yml` |
| Inno Setup | aus dem Runner | Setup (nur für den Benutzer, ohne Adminrechte) | `programm/installer/rohrlaser.iss` |

Alle Bibliotheken stehen mit `==` fest (geprüft in `tests/test_windows_robust.py`, Teil 7). Eine neue Version kommt
nur bewusst per Pull Request mit vollem Testlauf, nie automatisch. numpy ist bewusst nicht im Paket (Rechenkern reines
Python).

## 2. Was von Windows kommt, und was passiert, wenn es fehlt oder sich ändert

| Windows-Teil | Wo im Programm | Wenn es fehlt / sich ändert |
|---|---|---|
| `%LOCALAPPDATA%`, Ordner „Dokumente“ (über Qt, beachtet Umleitung/OneDrive) | `orte.py` | Rückfall `~/AppData/Local` bzw. `~/Documents`; portabel: alles neben der .exe |
| Dateisperre (`msvcrt.locking`) | `orte.Sperre` | Betriebssystem-Sperre, verschwindet auch bei Absturz und Neustart |
| DPAPI „dieser Rechner“ (`crypt32`) | `zugangsschutz.py` (PostgreSQL-Passwörter) | Datei auf anderem PC / nach Neuinstallation unlesbar: **seit 0.9.517 neue Passwörter, Daten bleiben** (`pg_lokal.zugang_erneuern`) |
| Registry `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid` (nur lesen) | `lizenz.py` (Rechner-ID) | bleibt bei Updates und Funktionsupdates; nach Neuinstallation neue Rechner-ID → neue Lizenzdatei nötig, Daten unberührt |
| `GetSystemMetrics(SM_REMOTESESSION)` | `ansicht3d.py` | Remote-Desktop → 3D mit Software |
| OpenGL-Treiber (ab 2.0) | `ansicht3d_gl.py` | Fehler → Software; **nativer Treiberabsturz → seit 0.9.517 für diese Version gesperrt** (`laufwaechter`) |
| Neustart-Manager (`rstrtmgr`), `OpenProcess`/`QueryFullProcessImageNameW` | `update.py` | nur für „wer hält diese Datei“ beim Update; ohne: allgemeine Meldung |
| `WNetGetConnectionW` (`mpr`) | `netzpfad.py` (seit 0.9.517) | ohne: gemeinsamer Ordner nur über den eingetragenen Pfad |
| `SetProcessShutdownParameters` (`kernel32`) | `sitzungsende.py` (seit 0.9.517) | ohne: Windows beendet PostgreSQL ggf. vor dem Programm (PostgreSQL stellt sich selbst wieder her) |
| `icacls` | `pg_lokal._windows_zugriff` | Rechte am Datenordner für den angemeldeten Benutzer |
| Windows PowerShell 5.1 + klassisches Outlook (COM) | `outlook_anfragen.py`, `materialanfrage(n).py` | nur die Outlook-Funktionen; Rest unberührt. **Risiko „neues Outlook“** siehe Abschnitt 7 |
| Windows Defender (`MpCmdRun`) | `virenpruefung.py` | eigene Prüfung seit 0.9.349 aus |
| Systemproxy (WinINet-Einstellungen) | `update.systemproxy` | nur Online-Update; TLS-Prüfung immer an |

Es gibt keine Abhängigkeit von .NET, keine Windows-Dienste, keine Treiber, keine global registrierten COM-Bausteine
des Programms selbst und keine Schreibzugriffe auf die Registry. Adminrechte sind weder für Installation noch Betrieb
nötig. Netzwerk: nur der Update-Weg (github.com, 443) und der eingetragene gemeinsame Ordner; die KI arbeitet nur lokal.

## 3. Ordner: Programm, Daten, Einstellungen, Zwischenspeicher, Sicherungen

| Art | Installiert | Portabel | Was ein Update / eine Reparatur darf |
|---|---|---|---|
| Programm | `%LOCALAPPDATA%\Programs\Rohrlaser Angebotskalkulation` | beliebiger Ordner | nur Dateien der signierten Dateiliste tauschen |
| Daten (PostgreSQL `Daten\pg`, Merkdatei `rohrlaser.db`, Lizenz, Protokoll) | `%LOCALAPPDATA%\Rohrlaser Angebotskalkulation\Daten` | `Daten` neben der .exe | nie anfassen; Setup-Deinstallation lässt sie liegen |
| Einstellungen je Benutzer/PC | in der Datenbank (Einstellungen „je Arbeitsplatz“) und `%LOCALAPPDATA%\Rohrlaser Angebotskalkulation` (`zuletzt_benutzt.json`, `Waechter`, `netzlaufwerke.json`) | ebenso | – |
| Zwischenspeicher | `Daten\Rechenmerker`, Angebots-Cache, STEP-Lesecache | ebenso | jederzeit löschbar, wird neu gerechnet |
| Sicherungen | `Daten\Sicherung` (+ zweiter Ordner, + gemeinsamer Ordner) | ebenso | – |
| Ablage PDF/CSV | `Dokumente\Rohrlaser Angebote` | `Angebote` neben der .exe | – |

Die Datenbank liegt bewusst nicht unter „Dokumente“ (OneDrive synchronisiert den Ordner oft, Windows-Updates bieten
das Umleiten aktiv an).

## 4. Datenbank

- PostgreSQL 16.2 je PC, eigener Benutzerprozess, nur `127.0.0.1`, zufälliger Port je Start, `fsync`,
  `synchronous_commit` und `full_page_writes` an: bestätigte Speicherungen überstehen Stromausfall und harten Neustart.
- Programmkonto ohne Superuser-Rechte; Passwörter zufällig, per DPAPI verschlüsselt.
- Verbindungsabbruch: Lesen verbindet von selbst neu (auch mit Neustart des Servers), Eingaben ohne Verbindung werden
  gemerkt und nachgetragen (`verbindung_waechter.py`).
- Schema-Umstellung nur mit geprüfter Sicherung `vor_Schema_N`; eine ältere Programmversion öffnet eine neuere
  Datenbank nicht und ein Update mit einem Schema, das die Daten nicht kennt, wird nicht angeboten
  (`update.schema_pruefen`).
- Sicherungen: täglich beim ersten Start (im Hintergrund), beim Beenden, vor Update/Schema/Wiederherstellen; jede mit
  Integritätsprüfung, Anzahlen, SHA-256 und PostgreSQL-Abbild (`pg_dump`); wöchentlich eine Probe-Wiederherstellung.

## 5. Neustart, Abmeldung, Absturz (seit 0.9.517)

| Fall | Verhalten |
|---|---|
| Windows startet für Updates neu, Programm offen | `sitzungsende`: auf WM_QUERYENDSESSION/WM_ENDSESSION Tagessicherung abwarten (max. 10 s), Datenbank schließen, PostgreSQL sauber stoppen, Sperre frei, Laufmarker weg (alles in max. 15 s, jeder Schritt einzeln abgesichert). Das Programm wird vor PostgreSQL benachrichtigt. |
| Stromausfall, Absturz, Task-Manager | Laufmarker `Daten\laeuft.json` bleibt; nächster Start meldet es, verschiebt halbe Dateien dieses Laufs nach `Daten\Sicherung\Unvollstaendig` (nichts gelöscht). PostgreSQL stellt sich aus dem WAL wieder her. |
| Halbe Tagessicherung | zählt nicht mehr als „heute gesichert“ (nur Sicherungen mit `.json`). |
| Leere/veraltete `postmaster.pid` | kommt als `postmaster.pid.alt` beiseite (nur wenn kein Server läuft und die Prozessnummer kein PostgreSQL ist), ein zweiter Startversuch. |
| Ordnerrechte von einem Update zurückgesetzt | PostgreSQL meldet „Permission denied“ → Rechte für den angemeldeten Benutzer erneuern, zweiter Versuch. |
| Zugangsdatei unlesbar | neue Passwörter über eine kurze `trust`-Zeile nur für den Verwalter von 127.0.0.1, danach sofort die alte `pg_hba.conf`. |
| Grafiktreiber stürzt im 3D ab | Marker im Ordner `Waechter` bleibt → 3D mit Software bis zur nächsten Programmversion. |
| Netzlaufwerk nach Neustart getrennt | gemeinsamer Ordner über den gemerkten UNC-Pfad; Fehlversuch 60 s gemerkt (keine doppelte SMB-Wartezeit). |
| Unterbrochenes Programm-Update | Journal: alte Dateien zurück beim nächsten Start (`update.nach_absturz`, bestand schon). |

## 6. Updates des Programms (unabhängig von Windows-Updates)

- Dateiliste signiert (Ed25519), jede Datei mit SHA-256; Quellen: online, Netzwerkordner, `.rlupdate`-Datei.
- Vorher geprüfte Sicherung `vor_update`, Platz- und Schreibrechtprüfung, Hilfsprozesse beendet, eigene Dateigriffe
  freigegeben; Austausch mit Journal, bei Fehler alles zurück.
- **Vorige Version wiederherstellen** (Update-Fenster/Update-Center): der zuletzt ersetzte Stand bleibt erhalten.
- Datenbank zurück: Sicherung `vor_Schema_N` bzw. `vor_update` mit der vorigen Programmversion wiederherstellen.
- Windows-Build nur als Sammel-Release; dort laufen auf dem Windows-Runner Selbsttest (installiert und portabel,
  Ergebnisse gleich), Update-Test und PostgreSQL-Start.

## 7. Bekannte Kompatibilitätsrisiken

| Risiko | Wirkung | Stand |
|---|---|---|
| „Neues Outlook für Windows“ (kein COM) ersetzt das klassische Outlook | Outlook-Anfragen und Materialanfrage per Outlook gehen nicht mehr; Mails als .msg/.eml ablegen geht weiter | offen; Microsoft-Fahrplan beobachten, Ersatz wäre Graph-API (braucht M365-Admin) |
| Programm nicht code-signiert | SmartScreen/Defender-Warnungen, ggf. Quarantäne nach Defender-Update | offen (Code-Signatur-Zertifikat) |
| „Überwachter Ordnerzugriff“ (Defender) | Schreiben nach „Dokumente“ blockiert | Meldung mit Lösung (`klartext.py`); Ablageordner in den Einstellungen ändern oder Programm zulassen |
| Windows 10 | Microsoft-Unterstützung beendet; Qt/Python-Unterstützung kann folgen | Programm läuft, aber nicht mehr empfohlen |
| ARM-Windows (Snapdragon) | nur über x64-Emulation, nie geprüft | nicht unterstützt |
| Rechner-ID nach Neuinstallation | neue Lizenz nötig | gewollt (Lizenzbindung) |

## 8. Vorgehen bei einer neuen Windows-Version oder einem großen Funktionsupdate

1. Auf einem Test-PC (oder VM) das Release „aktuell“ installieren und portabel entpacken.
2. `Rohrlaser-Angebotskalkulation.exe --selbsttest --ergebnis selbsttest.txt` in beiden Formen; Ergebnisse müssen
   gleich sein (wie im Sammel-Release-Workflow).
3. Programm normal starten: Hilfe → Systemprüfung, ein Angebot mit STEP öffnen, optimieren, PDF erzeugen, 3D drehen.
4. Windows-Neustart bei offenem Programm auslösen; danach darf keine Meldung „nicht normal beendet“ kommen.
5. Erst danach die Windows-Version in Abschnitt 6 des Berichts als „geprüft“ eintragen.
