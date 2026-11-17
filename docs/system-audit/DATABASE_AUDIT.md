# Datenbankprüfung

Stand 17.11.2026, `main` ba3cdc2 (0.9.372), Schema 93.

## Aufbau

| | |
|---|---|
| Speicher je PC | SQLite-Datei `rohrlaser.db` oder eingebettetes PostgreSQL 16 (Ordner `Daten/pg`, seit 0.9.339; Menü Datei → Datenspeicher, nur Hauptadmin) |
| Zwischen PCs | Abgleich über einen gemeinsamen Ordner (`teilen.py`): je Platz `Rohrlaser_<Kürzel>/haupt.sqlite` + Monatsdateien, feldweise „jüngste Änderung gewinnt“, Konflikte werden je Feld gemeldet, Nummernvorrat gegen doppelte Angebotsnummern |
| Datenschicht | `db_verbindung.py` (eine Schnittstelle für SQLite und PostgreSQL, SQL-Übersetzung, Transaktionen wie `sqlite3`), `datenbank.py` (Klasse `Datenbank`) |
| Umfang | 79 Tabellen, 127 Indizes, 240 Trigger (Änderungsmerker `teilen_geaendert`, Verlauf), 6 Fremdschlüssel |
| Migrationen | `SCHEMA_VERSION` (93) + `PRAGMA user_version`; vor jeder Schema-Umstellung Sicherung `vor_schema`; neuere Datei wird abgelehnt |

## Prüfpunkte

| Prüfpunkt | Ergebnis |
|---|---|
| Integrität einer neuen Datei | `PRAGMA integrity_check` = ok, `foreign_key_check` leer [geprüft] |
| Fremdschlüssel | nur `positionen`, `step_protokoll`, `netze`, `staffeln`, `staffel_stufen` → `angebote` (CASCADE) und `lager_reservierung` → `lager_bestand`. `PRAGMA foreign_keys=ON` ist gesetzt. Alle anderen Verweise stehen im Code (DB-01) |
| Löschen eines Angebots | `angebot_loeschen` räumt Lager, Fertigungsstatus, Rückmeldungen, Reklamationen auf, Rest per CASCADE; Löschschutz für optimierte Angebote [Code] |
| Archivieren | **DB-02**: Reklamationen und Rückmeldungen blieben verwaist – behoben in 0.9.375 [geprüft, SQLite und PostgreSQL] |
| Transaktionen | Schreibvorgänge in `with db.con:`; PostgreSQL mit `pg_advisory_lock` beim Einrichten; Nummernvergabe mit bis zu 50 Wiederholungen bei gleichzeitigen Angeboten (Lasttest 14.11.) [übernommen] |
| Gleichzeitige Schreibzugriffe | SQLite: `busy_timeout` 30 s, Datei-Sperre `rohrlaser.db.sperre` gegen zwei Programme auf einer Datei; PostgreSQL: bis 25 Verbindungen ohne Fehler (Lasttest) |
| Verbindungsabbruch | SQLite lokal; gemeinsamer Ordner: Ausfall wird gemeldet, Abgleich holt nach (`test_ordner_ausfall_umzug.py`); PostgreSQL lokal, Server startet mit dem Programm |
| Doppelte Datensätze | Angebotsnummern eindeutig (Index), Konfliktkopien (OneDrive „(1)“) werden erkannt und beiseitegelegt; Statusjournal ohne Doppel (`fertigung`) |
| Indizes | für Angebote, Positionen, Staffeln, Protokoll, Abgleich vorhanden (Prüfung 28.10., PR #329) [übernommen] |
| Langsame Abfragen | Liste/Suche/Öffnen bei 10.000 Angeboten unter 0,2 s (1 Benutzer); siehe [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) |
| Sicherung | täglich beim ersten Start, beim Beenden, vor Update, Schema, Import, Archiv; geprüft mit `integrity_check` und Anzahlen, SHA-256 in `.json`; Staffelung 7/4/12; zweiter Sicherungsordner möglich; mit PostgreSQL als SQLite-Kopie (`db_kopie.py`) |
| Wiederherstellung | Probe-Wiederherstellung (Phase 7, `test_pruef_wiederherstellung.py`), neuere Version wird abgelehnt, vorher Sicherung des jetzigen Stands |

## Verweise ohne Fremdschlüssel (DB-01)

**Seit 0.9.380:** `db_verweise.zaehlen` zählt Zeilen, die ins Leere zeigen (Liste `PFLICHT`), und Journal-Zeilen ohne
Angebot (`JOURNAL`: Lagerbuchungen, Automatik, Frachtrechnungen, gewollt). Das Support-Paket legt `verweise.json` bei;
`tests/test_db_verweise.py` prüft Löschen und Archivieren.

Spalten `…_id` ohne Fremdschlüssel (aus `PRAGMA table_info`/`foreign_key_list` einer neuen Datei):

- auf `angebote`: `auftrag_status`, `automatik`, `fracht_kalkulationen`, `lager_auftraege`, `lager_buchungen`,
  `lager_reservierung`, `reklamationen`, `rueckmeldungen`, `teilen_geaendert`
- auf `positionen`: `reklamationen.position_id`, `rueckmeldungen.position_id`
- Stammdaten über Text-Schlüssel: `profil_id`, `werkstoff_id`, `maschinen_id`, `satz_id`, `zone_id`, `tarif_id`,
  `zuschlag_id`, `lht_id`, `artikel_id`, `stufe_id` u. a. (Positionen, Preise, Schneiddaten, Fracht, Zukauf)

Das ist für den Abgleich gewollt (Zeilen werden über `uid` und Text-Schlüssel zwischen PCs zusammengeführt, IDs sind
je PC verschieden). Empfehlung: keine Fremdschlüssel nachrüsten (würde Abgleich und Import brechen), sondern eine
Diagnose, die die Verweise zählt (Support-Paket, Test), und bei jedem neuen Lösch- oder Archivweg die Liste oben
mitprüfen.

## Hinweis zur ID-Vergabe

SQLite-Tabellen ohne `AUTOINCREMENT` vergeben die höchste gelöschte ID neu; `angebot_loeschen` löst deshalb
Lager-Reservierungen ausdrücklich vom Angebot. PostgreSQL nutzt Sequenzen (keine Wiedervergabe). Archivierte
Angebote haben meist kleine IDs; beim Zurückholen bleibt die ID, wenn sie frei ist, sonst gibt es eine neue (getestet).

## PostgreSQL

- Die Datenschicht ist für PostgreSQL vorbereitet und läuft heute schon je PC. Ein **zentraler Server** für 10–25
  Benutzer wäre der nächste Schritt; dann entfallen Abgleich, Konflikte und die Sicherheitslücken SEC-01/02 –
  Voraussetzung: Rechte in der Datenbank (Rollen, Row-Level-Security oder ein Dienst davor), nicht nur im Programm.
- Lücke heute: Die Tests laufen in CI nur gegen SQLite (TEST-01). `werkzeuge/pg_testlauf.py` gibt es; heute
  stichprobenartig ausgeführt: `test_archiv.py`, `test_reklamation.py` grün gegen PostgreSQL 16.
- PostgreSQL 17: offen (Projekt-Memory), kein Handlungsbedarf aus dieser Prüfung.
