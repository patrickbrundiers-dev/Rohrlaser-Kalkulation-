# Systemprüfung Rohrlaser-Kalkulation – Gesamtbericht

Auftrag: Patrick, 17.11.2026 („Master-Prompt: Vollständige Systemprüfung“).
Geprüfter Stand: `main` ba3cdc2, Programmversion 0.9.372, Datenbank-Schema 93. Die Fehlerbehebungen dieses Berichts
stehen in [FIX_LOG.md](FIX_LOG.md).

Kennzeichnung in allen Dateien dieses Ordners:

- **[geprüft]**: mit einem Skript oder Test nachgestellt, das Ergebnis steht dabei.
- **[Code]**: aus dem Quelltext abgeleitet, nicht ausgeführt.
- **[übernommen]**: Messung oder Befund aus einer früheren Prüfung (Quelle genannt), heute nicht wiederholt.

Die einzelnen Teile:

| Datei | Inhalt |
|---|---|
| [BUGS.md](BUGS.md) | alle Befunde mit Priorität P0–P3, Nachweis, Lösung |
| [SECURITY_AUDIT.md](SECURITY_AUDIT.md) | Login, Hauptadmin, Lizenz, Rechte, Update, Injection, Geheimnisse |
| [DATABASE_AUDIT.md](DATABASE_AUDIT.md) | Tabellen, Verweise, Transaktionen, Migration, Sicherung, PostgreSQL |
| [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) | Start, Module, Datenbank, 10–25 Benutzer |
| [TEST_COVERAGE.md](TEST_COVERAGE.md) | vorhandene Tests, CI, heutiger Gesamtlauf, Lücken |
| [FIX_LOG.md](FIX_LOG.md) | was in dieser Prüfung behoben wurde |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | was offen bleibt, mit Begründung |

## 1. Ergebnis in Kürze

Die Software ist für ihre Größe in gutem Zustand: 454 Testskripte mit rund 17.800 Prüfungen, CI mit Pflicht-Check
`tests` vor jedem Merge, signiertes Online-Update, signierte Lizenzen, Lesemodus in der Datenschicht, zentrales
Fehlerprotokoll, tägliche geprüfte Sicherungen, keine bekannten Schwachstellen in den Abhängigkeiten (pip-audit),
keine Geheimnisse im Repository, keine Import-Zyklen auf Modulebene, ruff ohne Befund.

Gefunden wurden trotzdem zwei **kritische Sicherheitslücken (P0)** mit derselben Ursache: Die Admin-Rechte über alle
Arbeitsplätze hängen an Dateien im gemeinsamen Ordner, die nicht signiert sind. Jeder Mitarbeiter mit Schreibrecht
auf diesen Ordner kann damit das Admin-Passwort aller Plätze ersetzen und geschützte Kalkulationswerte (z. B. Gewinn)
verändern. Beides ist nachgestellt [geprüft]. Dazu kommt ein Datenbankfehler (P1, behoben): Beim Archivieren blieben
Reklamationen und Scan-Rückmeldungen verwaist zurück.

| Priorität | Anzahl | davon behoben | Beispiele |
|---|---|---|---|
| P0 kritisch | 2 | 0 (Fix in Arbeit, eigener PR) | SEC-01 gefälschte Admin-Vorgaben, SEC-02 Admin-Passwort über den Abgleich |
| P1 hoch | 2 | 1 | DB-02 Archiv verwaist (behoben), TEST-01 PostgreSQL-Pfad nicht in CI |
| P2 mittel | 6 | 0 | stille Ausnahmen (u. a. Kalkulations-PDF lässt Bearbeitung einer Position still weg), Protokoll ohne Modul/Benutzer, `round()` an Geldstellen, Verweise nur im Code |
| P3 niedrig | 5 | 0 | ungenutzter Code, sehr große Funktionen, Parameter ohne Wirkung |

Keine Kalkulationsformel wurde geändert. Fachliche Regeln (Gewinde nur €/Stück, kein Gewinn auf Zukauf, Rechnungen
im ERP, Staffeln nie automatisch, Konturen 100 % wie STEP …) sind unberührt.

## 2. Was geprüft wurde

| Bereich | Wie | Ergebnis |
|---|---|---|
| Struktur, Technik, Abhängigkeiten | Verzeichnisse, `requirements*.txt`, Workflows gelesen | Abschnitt 3 |
| Gesamte Testsuite | `tests/alle.py -j 4` auf `main` (Linux, Python 3.13, offscreen) | [TEST_COVERAGE.md](TEST_COVERAGE.md) |
| Statische Prüfung | ruff (Projektregeln), vulture (ungenutzter Code), radon (Komplexität), eigenes Skript für Import-Zyklen | ruff 0, Zyklen 0, Befunde P3 |
| Abhängigkeiten | `pip-audit` gegen `requirements.txt` und `programm/requirements.txt` | keine bekannten Schwachstellen |
| Geheimnisse | `git ls-files` und `git grep` nach Schlüsseln, Passwörtern, Datenbanken | nichts gefunden |
| SQL-Injection | alle `execute(f"…")` (195 Stellen) durchgesehen | nur Tabellen-/Spaltennamen aus dem Programm, Werte immer als Parameter |
| Admin, Hauptadmin, Lizenz | Code gelesen, Angriff über den gemeinsamen Ordner nachgestellt | SEC-01, SEC-02 [geprüft] |
| Fehlerbehandlung | alle `except … pass` (35) und `except Exception` (425) gesichtet | ERR-01, ERR-02 |
| Datenbank | Tabellen, Fremdschlüssel, Löschen, Archivieren, Zurückholen, PostgreSQL-Pfad | DB-01, DB-02 [geprüft] |
| Kalkulation | Angebotssumme, Satzpreis, Mindestpreis, Rundung (`ausgabe.py`, `zukauf.py`, `rechnen.py`) gelesen; Abnahmetest mit Handrechnung läuft in CI | CALC-01 (Rundung), sonst ohne Befund |
| Performance | vorhandene Messungen (Lasttest 14.11., Prüfung 29.10.) ausgewertet | [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) |

Nicht geprüft (bewusst, siehe [OPEN_ISSUES.md](OPEN_ISSUES.md)): Bedienung am echten Windows-PC, Outlook per COM,
STEP-Messung mit Kundendateien, Verhalten auf einem echten Netzlaufwerk mit mehreren PCs.

## 3. Bestandsaufnahme (Phase 1)

### 3.1 Technik

| | |
|---|---|
| Sprache | Python 3.12 (Windows-Build), Tests laufen auch mit 3.13 |
| Oberfläche | PySide6 (Qt 6.12), offscreen testbar |
| 3D/STEP | OpenCascade über `cadquery-ocp` in einem eigenen Prozess (`STEP-Import.exe`, `programm/step_messung`) |
| PDF | reportlab 5.1 (+ rl_accel), pypdfium2 und Tesseract zum Lesen von Anfragen |
| Datenbank | SQLite (Datei je PC) oder eingebettetes PostgreSQL 16 je PC (seit 0.9.339, Menü Datei → Datenspeicher); Abgleich zwischen PCs über einen gemeinsamen Ordner (`teilen.py`, feldweise) |
| Sicherheit | `cryptography` (Ed25519, AES-GCM, scrypt), PBKDF2 für Passwörter |
| Auslieferung | PyInstaller, Inno Setup, portables ZIP, Online-Update aus dem Repository Rohrlaser-Updates (signiert), Cython-Übersetzung |
| CI | GitHub Actions `paket.yml` (Tests in 3 Teilen, STEP-Referenz, ruff, Abnahme, Anleitung; Windows-Build nur von Hand) und `auslastung.yml` |

### 3.2 Umfang

| Ordner | Dateien | Zeilen | Inhalt |
|---|---|---|---|
| `programm/rohrlaser` | 458 | 185.700 | Kalkulationsprogramm |
| `programm/rl_auslastung` | 17 | 15.100 | Programm Rohrlaser Auslastung |
| `programm/step_messung` | 16 | 13.500 | STEP-Messung (eigener Prozess) |
| `tests` | 478 | 93.500 | 454 Testskripte in `tests/alle.py` |
| `anleitung` | 2 | 15.500 | Bedienungsanleitung (PDF entsteht im Build) |
| `werkzeuge` | 8 | 1.900 | Lizenz-Werkzeug, Messungen, Lasttest, PostgreSQL-Testlauf |

Datenbank: 79 Tabellen, 127 Indizes, 240 Trigger (Änderungsmerker für den Abgleich), 6 Fremdschlüssel, Schema 93.

### 3.3 Module nach Bereich (Auswahl)

| Bereich (Master-Prompt Nr.) | Hauptmodule |
|---|---|
| 1 Dashboard | `fenster.py` (Startseite), `automatik.py`, `startseite*` |
| 2–3 Anfragen, Outlook | `anfragen*.py`, `outlook_anfragen.py`, `mail.py`, `anfrage_erkennung.py`, `anfrage_ohne_step*.py` |
| 4–5 Material, Materialanfragen | `stammdaten.py`, `materialanfrage*.py`, `lager.py`, `lieferantenangebote.py` |
| 6–9 STEP, Rohrimport, 3D-Editor, Konturen | `step.py`, `step_dialog.py`, `programm/step_messung/*`, `teile_editor.py`, `ansicht3d*.py`, `editor_*.py`, `dxf_import.py` |
| 10 Zukauf/Normteile | `zukauf*.py`, `normteile*`, `drehfraes*` |
| 11 Kalkulation | `rechnen.py`, `optimierung.py`, `ausgabe.py`, `staffeln.py`, `preisschicht.py`, `laserzeit*`, `schneidfolge.py` |
| 12 Schweißbaugruppen | `baugruppe*.py`, `vorkalk.py`, `schweiss*.py` |
| 13–16 Angebot, Auftrag, Produktion | `angebot_fenster.py`, `auftraege.py`, `auftrag_*.py`, `fertigung.py`, `etiketten.py`, `reklamation.py` |
| 17 PDF | `pdf.py`, `pdf_*.py`, `angebot_ausgabe.py` |
| 18 Benutzer, Rechte | `admin_schutz*.py`, `hauptadmin*.py`, `rollen.py`, `lizenz*.py`, `passwort.py` |
| 19 Einstellungen | `einstellungen*.py`, `stammdaten.py` |
| 20 Datenbank | `datenbank.py`, `db_verbindung.py`, `pg_lokal.py`, `datenspeicher.py`, `teilen.py`, `archiv.py`, `db_kopie.py` |

### 3.4 Kritische Module

Geordnet nach Schaden bei einem Fehler (Kalkulation und Datensicherheit zuerst):

1. **`rechnen.py`** (5.300 Zeilen, `_kalkulation` mit Komplexität 331): jeder Preis. Abgesichert durch Abnahme mit
   Handrechnung, viele Preistests und festgeschriebene Preisbasis je Angebot. Risiko: Größe, nicht Fehlerdichte.
2. **`ausgabe.py` / `pdf.py`**: Angebotssumme, Satzpreis, MwSt, Staffeln im PDF. Kaufmännische Rundung zentral.
3. **`admin_schutz.py`, `teilen.py`, `hauptadmin.py`, `lizenz.py`**: Rechte und Abgleich, hier liegen SEC-01/02.
4. **`datenbank.py`, `db_verbindung.py`, `archiv.py`**: Speichern, Löschen, Archiv (DB-02), Migrationen.
5. **`optimierung.py`**: Stangenbelegung, bitgleich reproduzierbar (Suche nach Schritten, nie nach Zeit begrenzt).
6. **`step.py` + `programm/step_messung`**: Geometrie, eigene Referenztests mit Prüfbericht in CI.

### 3.5 Bewertung der Architektur

- **Wartbar, aber an der Grenze der Dateigröße.** `angebot_fenster.py` hat 10.300 Zeilen, `fenster.py` 4.800,
  `rechnen.py` 5.300; 135 Funktionen mit Komplexität über 40 (radon Stufe F). Das funktioniert, weil fast jede
  Funktion durch Tests abgedeckt ist. Ein Komplettumbau ist nicht nötig und wäre riskant; empfohlen ist, neue
  Funktionen in eigene Module zu legen (wie bisher z. B. `vorschlaege_mixin.py`) und große Funktionen nur beim
  nächsten fachlichen Umbau zu teilen (P3, [OPEN_ISSUES.md](OPEN_ISSUES.md)).
- **Klare Schichten wo es zählt:** Rechnen ohne Qt (`rechnen.py`, `ausgabe.py` testbar ohne Fenster), Datenschicht
  mit `@liest/@schreibt/@erlaubt` für den Lesemodus, STEP-Messung als eigener Prozess.
- **1.823 Importe innerhalb von Funktionen** verhindern Zyklen, machen Abhängigkeiten aber schwer sichtbar.
- **Verweise zwischen Tabellen stehen im Code, nicht in der Datenbank** (6 Fremdschlüssel bei 79 Tabellen,
  Stammdaten über Text-Schlüssel und `uid`). Das ist für den Abgleich zwischen PCs gewollt, verlangt aber, dass jeder
  Lösch- und Archivweg alle abhängigen Tabellen kennt (DB-02 war genau so ein Fall).
- **PostgreSQL:** Die Datenschicht ist schon neutral (`db_verbindung.py`, eingebettetes PG je PC, Lasttest bis 25
  Verbindungen). Ein späterer zentraler PostgreSQL-Server ist möglich; dann entfällt der Abgleich über den Ordner und
  mit ihm SEC-01/02 – die Rechte müssten dann aber in der Datenbank (Rollen) durchgesetzt werden, nicht nur im
  Programm.

## 4. Maßnahmenplan

Reihenfolge nach Wichtigkeit; jede Maßnahme ein kleiner PR mit Test, Versionsnummer main+1, Anleitung.

| Schritt | Befunde | Inhalt | Stand |
|---|---|---|---|
| 1 | DB-02 | Archiv nimmt Reklamationen und Rückmeldungen mit | **erledigt** (dieser PR, 0.9.373) |
| 2 | SEC-01, SEC-02 | Admin-Vorgaben signieren (Hauptadmin-Schlüssel, Admin-Schlüssel aus dem Passwort), geschützte Werte nie über den normalen Abgleich, Übergang ohne Bruch für Plätze ohne Hauptadmin-Lizenz | nächster PR |
| 3 | TEST-01 | PostgreSQL-Testlauf für die Datenbank-Tests in CI (nur Linux, kleiner Teil) | danach |
| 4 | ERR-01, ERR-02, LOG-01 | stille Ausnahmen ins Protokoll (WARNING mit Stacktrace, Verhalten gleich), Protokoll mit Modul, Funktion, Kürzel, Version; Passwörter und Zugangsdaten werden aus Protokolltexten entfernt | danach |
| 5 | CALC-01 | `round()` an Geldstellen durch die kaufmännische Rundung ersetzen, nur wo die Stelle ein Betrag ist; mit Vergleich alter/neuer Werte | danach, mit Prüfung jeder Stelle |
| 6 | DB-01 | Diagnose „verwaiste Verweise“ (Positionen ohne Angebot, Reklamationen ohne Position …) im Support-Paket und als Test | danach |
| 7 | P3 | ungenutzten Code entfernen, große Funktionen bei Gelegenheit teilen | laufend |

Jeder Schritt bekommt Regressionstests; der Gesamtlauf wird am Ende wiederholt (Phase 5).
