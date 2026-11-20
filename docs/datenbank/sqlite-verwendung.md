# Wo SQLite nach dem Datenbank-Auftrag noch vorkommt (Stand 19.11.2026, Schritt 6)

Die Hauptdaten liegen nur noch in PostgreSQL (je PC ein eigener Server, `pg_lokal`). Es gibt keinen Rückfall auf
SQLite und keinen Menüpunkt dafür. SQLite bleibt nur als **Dateiformat**. Jede Stelle unten ist bewusst so.

| Stelle | Wozu | Warum SQLite |
| --- | --- | --- |
| `datenspeicher.umstellen`, `Datenbank.__init__` | alte Datendatei einmal nach PostgreSQL übernehmen | Bestand vor 0.9.407 ist eine SQLite-Datei |
| `Datenbank.sicherung`, `db_kopie.pg_nach_sqlite` | jede Sicherung als Datei (dazu `.pgdump`, Schritt 4) | auf jedem PC lesbar und prüfbar, auch ohne PostgreSQL |
| `Datenbank.wiederherstellen`, `db_kopie.sqlite_nach_pg` | Sicherung, Export, Abbild einlesen | einziger Rückweg, geprüft (ein Abbild wird erst zur Datei) |
| `pruef_wiederherstellung` | wöchentliche Probe der neuesten Sicherung | prüft genau die Datei, die man zurückholen würde |
| `Datenbank.exportieren` | Umzug, Weitergabe (ZIP mit Datendatei) | Format für andere Rechner und Versionen |
| `teilen` (gemeinsamer Ordner) | Austauschdateien der Kollegen | alte und neue Versionen müssen sie lesen |
| `archiv` | Jahresarchiv alter Angebote | eigenständige Datei je Jahr |
| `dauermerker` (Daten/Rechenmerker) | Angebots-Cache je PC | Zwischenspeicher, kein Datenbestand |
| `db_verbindung.SqliteVerbindung` | Zugriff auf die Dateien oben | dieselbe Schicht wie für PostgreSQL |
| Fehlerklassen (`DbFehler` erbt von `sqlite3.DatabaseError`) | bestehende `except sqlite3.…` greifen weiter | reine Klassenhierarchie, kein Datenzugriff |

Entfernt in Schritt 6: Schnellprüfung der SQLite-Datendatei beim Start (`PruefLauf`, `PRAGMA quick_check`), die mit
PostgreSQL nie mehr lief; veralteter Hinweis „Datenbank wird modernisiert“ in der Anleitung.

Rohrlaser Auslastung ist nicht Teil dieses Auftrags (eigenes Programm, eigener Datenspeicher).
