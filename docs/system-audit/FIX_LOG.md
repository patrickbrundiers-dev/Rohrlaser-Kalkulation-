# Durchgeführte Fehlerbehebungen

Jede Behebung: eigener PR, Regressionstest, der mit dem alten Code rot und mit dem neuen grün ist, Version main+1,
Eintrag in `neuerungen.py`, Bedienungsanleitung angepasst. Keine Kalkulationsformel und keine fachliche Regel geändert.

## DB-02 – Archiv nimmt Reklamationen und Scan-Rückmeldungen mit (0.9.373)

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

## SEC-01 / SEC-02 – signierte Admin-Vorgaben (in Arbeit, nächster PR)

Siehe [SECURITY_AUDIT.md](SECURITY_AUDIT.md#geplanter-fix-für-sec-01sec-02). Wird hier nachgetragen, sobald gemergt.
