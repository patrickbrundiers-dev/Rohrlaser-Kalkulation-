# Testabdeckung

Stand 17.11.2026, `main` ba3cdc2 (0.9.372).

## Vorhandene Tests

| | |
|---|---|
| Testskripte | 458 Dateien `tests/test_*.py`: 455 laufen über `tests/alle.py` in jedem PR, 2 langsame nur beim Sammel-Release (`LANGSAM`), 2 als eigene Schritte (`test_step_referenz.py` mit Testbericht, `test_abnahme.py` mit Abnahmeprotokoll) |
| Prüfungen | rund 17.800 `assert` |
| Art | Skripte ohne Testframework, je Datei ein Prozess; Unit-, Integrations- und Oberflächentests (Qt offscreen), STEP-Referenz gegen gespeicherte Messwerte, Abnahme mit Handrechnung, Leistungstests (`test_angebot_leistung.py`, `test_tempo*.py`), Sicherheit (Lizenz, Hauptadmin, Update-Signatur, Release-Prüfung, Quellcode-Schutz, Lesemodus) |
| Regel | jede neue Testdatei muss in `tests/alle.py` stehen, sonst wird der Lauf rot |

Grobe Verteilung nach Dateiname: STEP/3D/Geometrie ~130, Kalkulation/Preise ~70, Angebot/Auftrag/Anfragen ~35,
Datenbank/Abgleich ~25, Sicherheit/Lizenz/Update ~17, PDF/Anleitung/Oberfläche ~11, übrige ~170 (gemischt).

## CI (GitHub Actions `paket.yml`)

- Bei jedem PR (außer Entwurf): Tests in 3 gleich langen Teilen parallel, dazu STEP-Referenz, ruff, Abnahme,
  Bedienungsanleitung, Prüfung „Programm geändert, Anleitung auch?“. Pflicht-Check `tests` (Ruleset `main`: ohne
  grünen Check kein Merge, kein Force-Push).
- Langsame Tests (`LANGSAM`) und der Windows-Build mit Selbsttest der .exe nur beim Sammel-Release von Hand.
- Ein roter Test wird einmal allein wiederholt; grün beim zweiten Mal = „instabil“ (Lauf bleibt grün, steht in der
  Zusammenfassung).

## Heutiger Gesamtlauf

`python3 tests/alle.py -j 4` auf `main` ba3cdc2, Linux-Container, Python 3.13, Qt offscreen:

**455 von 455 Tests grün** („Alles in Ordnung.“), 22 min (Summe 88 min, 4 gleichzeitig). Langsamste:
`test_anleitung.py` 321 s, `test_kantteile_vielfalt.py` 284 s, `test_step_robust.py` 267 s.

Hinweis zur Ehrlichkeit: Ein erster Lauf lief im Container ohne die Qt-Systembibliotheken (libEGL) und wurde
abgebrochen; gezählt ist nur der zweite, vollständige Lauf. `test_step_referenz.py` und `test_abnahme.py` liefen heute
nicht lokal (laufen in jedem PR in CI).

Zusätzlich heute gegen PostgreSQL 16 (`werkzeuge/pg_testlauf.py`, Stichprobe): `test_archiv.py`, `test_reklamation.py`
grün.

Neu bzw. erweitert in dieser Prüfung:

| Test | Prüft | Befund |
|---|---|---|
| `tests/test_archiv.py` (erweitert) | Archivieren und Zurückholen mit Reklamation und Scan-Rückmeldung, keine verwaisten Zeilen | DB-02 |
| `tests/test_admin_signatur.py` (neu, 0.9.376) | Fälschungen der Admin-Vorgaben abgelehnt, Signatur Hauptadmin und weiterer Admin, Rechte nicht über den Abgleich | SEC-01, SEC-02 |

## Lücken

| Lücke | P | Vorschlag |
|---|---|---|
| PostgreSQL-Pfad nicht in CI (TEST-01) | P1 | CI-Job mit PostgreSQL 16 für Datenbank- und Abgleichtests |
| Keine gemessene Abdeckung (TEST-02) | P2 | `tests/alle.py --coverage` wöchentlich, Bericht als Artefakt; Ziel: `rechnen.py`, `ausgabe.py`, `admin_schutz.py`, `teilen.py`, `archiv.py` sichtbar |
| `pip-audit` nicht in CI (TEST-02) | P2 | im selben wöchentlichen Lauf |
| ~~Keine Prüfung auf neue stille Ausnahmen (ERR-01)~~ | P2 | erledigt 0.9.377: `test_protokoll_kontext.py` K6 (höchstens 72) |
| End-to-End Anfrage → Angebot → Auftrag → Produktion → Fertig | – | vorhanden in Teilen (`test_auftrag*.py`, `test_arbeitsablaeufe.py`, Auftragsworkflow-Tests P1–P7); ein durchgehender Ablauf in einem Test fehlt – Vorschlag als Regressionstest für die Statusweitergabe |
