# Stabilitäts- und Kompatibilitätsbericht: Windows-Updates, Neustarts, Systemunabhängigkeit (26.11.2026)

Auftrag Patrick 26.11.2026 15:27 UTC. Stand main 0.9.516 (Schema 107), Ergebnis 0.9.517, kein Schema-Sprung.
Technische Dokumentation (Abhängigkeiten, Ordner, Update- und Wiederherstellungsverfahren, Vorgehen bei neuen
Windows-Versionen): [../WINDOWS_BETRIEB.md](../WINDOWS_BETRIEB.md).

Grundregeln: Rechenkern, STEP-Import, Verschachtelung, Datenbankinhalt und Oberfläche unverändert; Ergebnisse
bitgleich (keine Änderung an Rechenmodulen); nichts wird gelöscht; keine Kompatibilität behaupten, die nicht getestet
ist. Windows selbst steht in dieser Prüfumgebung nicht zur Verfügung (Linux-Container). Was nur unter Windows greift,
ist mit „nicht unter Windows ausgeführt“ markiert und wird erst im Windows-Lauf des Sammel-Release bzw. am PC belegt.

## 1. Vorgehen (Analyse)

Gesamter Quellcode `programm/rohrlaser` (über 640 Module) und Build (`paket.yml`, `.spec`, Installer) durchsucht nach:
`ctypes`/`windll`/`WinDLL`, `winreg`, `msvcrt`, `subprocess` mit Systemprogrammen (`icacls`, `powershell`), COM
(Outlook über PowerShell), festen Laufwerkspfaden, Umgebungsvariablen für Pfade, Temp-Ordnern, Dateischreibweisen
(atomar oder nicht), Sperren, Signalen des Betriebssystems (Abmelden/Herunterfahren), OpenGL-Weg, Datenbankstart,
Sicherungsablauf, Update-Ablauf. Jede Fundstelle ist in WINDOWS_BETRIEB.md Abschnitt 2 mit Verhalten bei Fehlern
aufgeführt. Bereiche aus dem Auftrag, die nicht vorkommen: .NET (keine Abhängigkeit), Registry-Schreiben (keins),
Windows-Dienste (keine), Adminrechte (nicht nötig), globale Laufzeiten (bis auf die VC++-Laufzeit für PostgreSQL, jetzt
mitgeliefert), Druckertreiber (Druck nur über das PDF-Programm des Benutzers).

## 2. Gefundene Risiken (vorher)

| Nr. | Fundstelle | Risiko | Schwere |
|---|---|---|---|
| W-01 | `__main__.main` | **Windows-Neustart bei offenem Programm**: Qt sendet bei WM_ENDSESSION `aboutToQuit`, danach beendet Windows den Prozess sofort; `app.exec()` kehrt nie zurück. Datenbank schließen, PostgreSQL stoppen, Tagessicherung abwarten und Sperre freigeben liefen nie. | hoch |
| W-02 | `Datenbank.sicherung_heute` | Eine durch Neustart/Stromausfall **halb geschriebene Tagessicherung** (Datei ohne `.json`) zählte als „heute gesichert“: an diesem Tag keine echte Sicherung, die halbe Datei lag in der Wiederherstellen-Liste. | hoch |
| W-03 | `pg_lokal.starten` | Nach Stromausfall/erzwungenem Neustart bleibt oft eine **leere `postmaster.pid`**; PostgreSQL verweigert dann den Start („lock file … is empty“) → Programm startet nicht. Kein zweiter Versuch. | hoch |
| W-04 | `pg_lokal._zugang_lesen` | **DPAPI-Zugangsdatei unlesbar** (Datenordner auf einen anderen PC kopiert, Windows neu aufgesetzt): Ausnahme beim Start, keine Daten erreichbar, obwohl die Datenbank selbst heil ist. | hoch |
| W-05 | `ansicht3d_gl` | Ein **Grafiktreiber-Update** mit Fehler beendet das Programm im Treiber (nativ, kein Python-Fehler). Beim nächsten Start wieder OpenGL → wieder Absturz, sobald 3D aufgeht. | mittel |
| W-06 | `paket.yml` PostgreSQL | `postgres.exe` braucht die **Visual-C++-Laufzeit**; sie lag nicht nachweislich im Ordner `pgsql/bin`, sondern kam vom System (global installiert). Ein frisches Windows ohne VC++-Laufzeit hätte PostgreSQL nicht starten können. | mittel (nicht beobachtet) |
| W-07 | `austausch.OrdnerWeg.erreichbar` | Gemeinsamer Ordner auf **Netzlaufwerk-Buchstaben**: nach dem Neustart oft „getrennt“, obwohl der Server erreichbar ist → Abgleich, Nummernkreis, Sicherung in den gemeinsamen Ordner ausgesetzt. | mittel |
| W-08 | `pg_lokal.starten` | **Ordnerrechte zurückgesetzt** (Update, Profil-Reparatur): PostgreSQL „Permission denied“, kein Reparaturversuch. | niedrig (nicht beobachtet) |
| W-09 | allgemein | **Unerwartetes Ende nicht erkannt**: halbe Zwischendateien blieben liegen, der Benutzer erfuhr nichts. | niedrig |
| W-10 | `outlook_anfragen` u. a. | Outlook-Funktionen nutzen COM des **klassischen Outlook**; das „neue Outlook“ hat kein COM. | mittel, nicht behebbar ohne Graph/M365-Admin |
| W-11 | Paket | nicht code-signiert (SmartScreen/Defender) | bekannt, dokumentiert |

Schon gut abgesichert (geprüft, nicht geändert): Online-Update mit Signatur, Journal und Rücknahme nach Absturz,
vorige Version wiederherstellbar, Sicherung vor Update und vor Schema-Umstellung, Schema-Sperre gegen ältere
Programme, Dateisperre über das Betriebssystem, PostgreSQL mit `fsync`/`full_page_writes`, Verbindungswächter mit
Nachtragen, Datenordner außerhalb von OneDrive, keine Adminrechte, feste Bibliotheksversionen, eigene Schriften für
PDFs, deutsches Zahlenformat fest gesetzt (`QLocale`), Remote-Desktop → Software-3D, Lizenz offline.

## 3. Änderungen

| Nr. | Änderung | Dateien |
|---|---|---|
| W-01 | Neues `sitzungsende.py`: `commitDataRequest` merkt „Sitzung endet“, `aboutToQuit` danach führt aus: Tagessicherung abwarten (max. 10 s), Datenbank schließen, PostgreSQL stoppen, Sperre frei, Laufmarker weg; jeder Schritt einzeln abgesichert, zusammen max. 15 s, nie zweimal. `SetProcessShutdownParameters(0x300)`: Programm vor PostgreSQL benachrichtigt. Normales Beenden unverändert. | `sitzungsende.py`, `__main__.py` |
| W-02 | Nur Sicherungen mit `.json` zählen als „heute gesichert“. | `datenbank.py` |
| W-03/W-08 | `LokalerServer.reparieren()`: leere/unlesbare oder fremde `postmaster.pid` → `postmaster.pid.alt` (nur wenn `pg_ctl` keinen Server sieht und die Prozessnummer kein PostgreSQL ist); „Permission denied“ → Rechte für den Benutzer (`icacls`); danach ein zweiter Startversuch, Protokolleintrag. Port wird nur noch in die Zugangsdatei geschrieben, die verschlüsselten Werte bleiben unberührt. | `pg_lokal.py`, `datenspeicher.py` |
| W-04 | `LokalerServer.zugang_erneuern()`: unlesbare Werte → kurz eine `trust`-Zeile nur für den Verwalter von 127.0.0.1 vorn in `pg_hba.conf`, neue Zufallspasswörter, sofort alte `pg_hba.conf` zurück (auch bei Fehler), neue Zugangsdatei (DPAPI). | `pg_lokal.py` |
| W-05 | Neues `laufwaechter.py` (riskante Stellen): Marker vor der OpenGL-Prüfung und bis zum ersten fertigen OpenGL-Bild; bleibt er nach einem gestorbenen Lauf stehen, zeichnet 3D für diese Programmversion mit Software (Grund in `renderer_grund`, im Protokoll und in der Anleitung beschrieben). Normales Ende räumt eigene Marker ab. | `laufwaechter.py`, `ansicht3d.py`, `ansicht3d_gl.py` |
| W-06 | Build legt `vcruntime140.dll`, `vcruntime140_1.dll`, `msvcp140.dll` neben `postgres.exe` (aus dem PyInstaller-Paket, sonst vom Build-Rechner). | `paket.yml` |
| W-07 | Neues `netzpfad.py`: UNC-Pfad hinter dem Laufwerk merken (`WNetGetConnectionW`); ist der Buchstabe getrennt, der UNC-Pfad aber da, nutzt der gemeinsame Ordner ihn. Fehlversuch 60 s gemerkt. Einstellung unverändert. | `netzpfad.py`, `austausch.py` |
| W-09 | Laufmarker `Daten\laeuft.json`: beim Start nach unerwartetem Ende Meldung, halbe Dateien dieses Laufs nach `Sicherung\Unvollstaendig` (nur ab Startzeit des Laufs, nur älter als 2 min, nichts gelöscht). | `laufwaechter.py`, `__main__.py` |
| Doku | WINDOWS_BETRIEB.md, Bedienungsanleitung (Fehlerbehebung, 4 Einträge), Neuerungen 0.9.517 | `docs/`, `anleitung/`, `neuerungen.py` |

Nicht geändert (bewusst): Rechenmodule, STEP, Verschachtelung, Datenbankschema, Oberfläche (keine neuen Dialoge; der
parallele Auftrag zu Kontextmenü/Einstellungen bleibt unberührt), Outlook-Module.

## 4. Abgesicherte Abhängigkeiten

- Bibliotheken: alle `==` (Test-Sperre), Aktualisierung nur per Pull Request.
- PostgreSQL 16.2: Prüfsumme im Build, jetzt mit eigener VC++-Laufzeit (W-06).
- Windows-APIs: jede Nutzung mit Rückfall ohne Absturz (Tabelle in WINDOWS_BETRIEB.md, Abschnitt 2).
- Feste Laufwerkspfade: 3 Stellen im Programm, alle nur als Rückfall hinter einer Umgebungsvariablen bzw. im
  Hilfetext; Test-Sperrklinke gegen neue.

## 5. Tests

| Test | Ergebnis | Wo |
|---|---|---|
| `tests/test_windows_robust.py` (neu): Laufmarker, Reste, Sperre riskanter Stellen, Software-3D bei Sperre, Sitzungsende (Kern und an `QApplication`), Einbindung in `main()`, `postmaster.pid`-Reparatur, **echter PostgreSQL**: hart abgebrochen (SIGKILL) + leere `postmaster.pid` → startet; unlesbare Zugangsdatei → erneuert, Daten erhalten, `pg_hba.conf` ohne `trust`, ohne Passwort kein Zugang; halbe Tagessicherung; Netzlaufwerk/UNC; gemeinsamer Ordner; feste Versionen; Paket; Laufwerkspfade | grün | Linux-Container, PostgreSQL 16 |
| Gesamte Testsuite `tests/alle.py` gegen PostgreSQL (`werkzeuge/mit_pg.py`) | siehe Abschnitt 5a | Linux-Container |
| `ruff` | grün | |

### 5a. Gesamtlauf

Wird im Pull Request nachgetragen (Check `tests`).

### 5b. Nicht in dieser Umgebung ausgeführt (nur unter Windows prüfbar)

- WM_QUERYENDSESSION/WM_ENDSESSION eines echten Windows-Neustarts (der Ablauf hinter den Qt-Signalen ist getestet,
  nicht das Signal von Windows selbst).
- `SetProcessShutdownParameters`, `WNetGetConnectionW`, `icacls`-Reparatur, DPAPI-Fehler eines echten anderen PCs.
- Nativer Absturz eines Grafiktreibers (nachgestellt über den Marker).
- VC++-Laufzeit neben `postgres.exe`: greift erst im nächsten Windows-Build (Sammel-Release), dort startet der Workflow
  `postgres.exe --version` und den Selbsttest.

## 6. Unterstützte Windows- und Laufzeitversionen

**Nachweislich getestet** (automatisch, bei jedem Sammel-Release): Windows-Runner `windows-latest` von GitHub
(Windows Server, 64 Bit; Image-Version steht im jeweiligen Lauf) mit Selbsttest installiert und portabel, Update-Test,
PostgreSQL-Start. **Im Betrieb** bei Patrick (Windows 10/11, genaue Builds nicht erfasst) – das ist eine Beobachtung,
kein Test.

**Laut Herstellerangaben** der Bausteine, von uns nicht einzeln geprüft: Qt 6 für Windows 10 (ab 1809) und
Windows 11, 64 Bit; Python 3.12 für Windows 8.1 und neuer; PostgreSQL 16 für Windows 10/11 und Server 2016+.
README nennt Windows 10 22H2 oder 11 (64 Bit) als Mindestvoraussetzung; Windows 10 wird von Microsoft nicht mehr
unterstützt und ist deshalb nur noch „läuft“, nicht „empfohlen“.

Nicht unterstützt / nie geprüft: 32 Bit, ARM (nur Emulation), Windows im S-Modus, Terminalserver mit mehreren
gleichzeitigen Benutzern auf einem Datenordner (Sperre verhindert es).

## 7. Verbleibende Risiken

1. „Neues Outlook“ ohne COM (W-10): Outlook-Funktionen fallen weg, wenn das klassische Outlook verschwindet.
2. Keine Code-Signatur (W-11): Defender/SmartScreen können nach Signatur-Updates warnen oder Dateien sperren.
3. Windows-spezifische Teile dieses Pakets sind erst nach dem nächsten Sammel-Release und einem echten Neustart-Test
   am PC belegt (Abschnitt 5b). Empfehlung: nach dem Update einmal bei offenem Programm Windows neu starten; danach
   darf keine Meldung „nicht normal beendet“ erscheinen.
4. Ein Windows-Update, das PostgreSQL-Prozesse vor dem Programm beendet, bleibt ohne Datenverlust (WAL), führt aber
   beim nächsten Start zur Meldung „nicht normal beendet“.
5. Antivirus, der den Ordner `Daten\pg` sperrt: weiter nur über eine Ausnahme beim Virenscanner lösbar (Meldung nennt
   das).
