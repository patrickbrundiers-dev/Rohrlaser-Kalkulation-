# Durchgeführte Fehlerbehebungen

Jede Behebung: eigener PR, Regressionstest, der mit dem alten Code rot und mit dem neuen grün ist, Version main+1,
Eintrag in `neuerungen.py`, Bedienungsanleitung angepasst. Keine Kalkulationsformel und keine fachliche Regel geändert.

## DB-02 – Archiv nimmt Reklamationen und Scan-Rückmeldungen mit (0.9.375)

| | |
|---|---|
| Befund | [BUGS.md → DB-02](BUGS.md#db-02-p1-archivieren-ließ-reklamationen-und-scan-rückmeldungen-verwaist-zurück-geprüft-behoben) |
| Geändert | `programm/rohrlaser/archiv.py`: `JE_ANGEBOT` um `reklamationen`, `rueckmeldungen` erweitert; `OHNE_KASKADE` (ausdrücklich löschen, da kein `ON DELETE CASCADE`); Zurückholen über alle Tabellen aus `JE_ANGEBOT` mit `_verweise` (neue Angebots-, Stufen- und Positions-ID) – SQLite- und PostgreSQL-Weg |
| Test | `tests/test_archiv.py`: Reklamation und Rückmeldung am archivierten Angebot; nach dem Archivieren keine verwaisten Zeilen, nach dem Zurückholen Inhalt gleich (inkl. Position der Reklamation/Rückmeldung) |
| Gegenprobe | erweiterter Test mit altem `archiv.py`: rot („Reklamationen/Rückmeldungen archivierter Angebote dürfen nicht verwaist zurückbleiben“); mit neuem: grün |
| PostgreSQL | `werkzeuge/pg_testlauf.py test_archiv.py test_reklamation.py` (PostgreSQL 16, Nicht-root-Benutzer): 2 von 2 grün |
| Anleitung | Kapitel „Alte Angebote archivieren“ (Marke `archiv`): Reklamationen und Scan-Rückmeldungen wandern mit |
| Ältere Archive | Archivdateien ohne diese Tabellen bleiben lesbar (Tabellen werden beim nächsten Archivieren angelegt, beim Zurückholen übersprungen, wenn sie fehlen) |
| Bereits verwaiste Zeilen | bleiben, wie sie sind (kein automatisches Löschen von Kundendaten); die geplante Diagnose DB-01 zeigt sie an |

## SEC-01 / SEC-02 – signierte Admin-Vorgaben (0.9.376)

| | |
|---|---|
| Befund | [BUGS.md → SEC-01](BUGS.md), SEC-02; Konzept in [SECURITY_AUDIT.md](SECURITY_AUDIT.md) |
| Neu | `programm/rohrlaser/admin_signatur.py`: Ed25519-Signatur des Pakets; Hauptadmin mit dem Schlüssel aus seinem Tresor (Anker = signierter Inhalt der Hauptadmin-Lizenz, geprüft mit dem eingebauten Lizenzschlüssel); weitere Admins mit Schlüssel aus scrypt(Passwort, eigenes Salz), öffentlicher Schlüssel in der Admin-Liste; ein weiterer Admin darf nur seinen eigenen Eintrag und keine Rechte-Werte ändern; gesperrte/ersetzte Lizenzen werden abgelehnt |
| Geändert | `admin_schutz.py` (Paket lesen/schreiben/anwenden prüft und setzt die Signatur, Platz merkt sich signierten Betrieb, `ausfiltern` hält Rechte-Werte aus dem normalen Abgleich), `teilen.py` (übergibt die Datenbank an `ausfiltern`), `lizenz.py` (Hauptadmin-Schlüssel nur im Speicher, nach Abmelden gelöscht, nach Notfallcode keiner), `fenster.py` (Schlüssel beim Freischalten) |
| Test | `tests/test_admin_signatur.py` S1–S5: Hauptadmin-Paket angenommen; Fälschungen (ohne Signatur, Inhalt geändert, eigener Anker) abgelehnt, Werte bleiben; Admin-Passwort aus manipulierter Datendatei geht nicht über den Abgleich; weiterer Admin signiert, darf keine Rechte ändern, gesperrt = abgelehnt; Übergang ohne Hauptadmin-Lizenz wie bisher. Dazu grün: `test_admin_schutz.py`, `test_hauptadmin.py`, `test_rollen.py`, alle sechs `test_teilen*.py` |
| Gegenprobe | Der Nachweis aus Phase 1 (gefälschtes Paket ersetzt Passwort und Gewinn) gelingt mit dem alten Code; S2 prüft dieselbe Fälschung mit dem neuen Code an einem Platz im signierten Betrieb: abgelehnt. Der neue Test selbst nutzt die neue Schnittstelle und läuft gegen den alten Code nicht (TypeError), ist also keine Rot-Probe im engeren Sinn |
| Grenze | Wirkt erst, wenn ein Platz einmal ein vom Hauptadmin signiertes Paket gesehen hat. Ohne Hauptadmin-Lizenz im Betrieb bleibt alles wie vorher (kein Bruch für bestehende Plätze) |
| Anleitung | Kapitel Admin-Rechte (Marke `admin_rechte`): Absatz „Gegen Fälschung signiert“ |
| Kalkulation | unverändert |

## ERR-01 / LOG-01 – Fehlerprotokoll mit Programmstelle, stille Fehler als Warnung (0.9.378)

| | |
|---|---|
| Befund | [BUGS.md → ERR-01, LOG-01](BUGS.md) |
| Geändert | `protokoll.py`: Format `Zeit Stufe Modul.Funktion \| Text`, `kopfzeile()` (Version, Kürzel, Datenspeicher; Aufruf in `__main__.py` nach dem Öffnen der Datendatei), `warnung()` (WARNING mit Stacktrace, höchstens 3 je Stelle und Lauf), `bereinigen()` (Passwort, Token, Bearer, Notfallcode, Seed → `***`); `fehler_seit` liest altes und neues Format |
| Stellen | 19 `except Exception: pass/continue` in `angebot_ausgabe`, `zusatz_formel`, `automatik`, `nachkalk_vorbelegen`, `preiswaechter`, `lernen`, `angebot_automatik`, `teilen`, `vorschlaege_mixin` rufen jetzt `protokoll.warnung`; Verhalten (weiter ohne Abbruch) unverändert |
| Test | neu `tests/test_protokoll_kontext.py` K1–K6 (Programmstelle, Zugangsdaten, Begrenzung, `fehler_seit`, Zusatzformel-Ergebnis gleich mit Warnung, höchstens 72 stille Ausnahmen); grün dazu `test_protokoll.py`, `test_paket3.py`, `test_lernen.py`, `test_angebot_automatik.py`, `test_materialanfrage.py`, `test_nachkalk_auswertung.py`, `test_rohrlaser_zusatz.py`, `test_zusatzarbeiten.py`, `test_vorschlaege_0211.py`, `test_vorschlaege_1111.py`, `test_teilen.py`, `test_teilen_monate.py`, `test_anfragen_paket3.py`, `test_release_pruefen.py` |
| Anleitung | Anhang „Häufige Fragen und Meldungen“: Zeile „Was im Fehlerprotokoll steht“ |
| Kalkulation | unverändert |
