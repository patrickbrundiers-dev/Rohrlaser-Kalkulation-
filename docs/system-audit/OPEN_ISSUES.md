# Offene Punkte

Stand 17.11.2026. Reihenfolge wie im Maßnahmenplan ([AUDIT_REPORT.md](AUDIT_REPORT.md#4-maßnahmenplan)).

## Offen – wird in dieser Prüfung noch umgesetzt

| ID | P | Was | Nächster Schritt |
|---|---|---|---|
| SEC-01, SEC-02 | P0 | Admin-Vorgaben signieren, Rechte-Werte nie über den normalen Abgleich | eigener PR nach diesem; wirkt voll erst, wenn die Hauptadmin-Lizenz im Betrieb ist (Ersteinrichtung bei Patrick offen) |
| TEST-01 | P1 | PostgreSQL-Testlauf in CI | Job mit PostgreSQL 16 aus Ubuntu, Datenbank- und Abgleichtests |
| ERR-01, LOG-01 | P2 | stille Ausnahmen protokollieren, Protokoll mit Modul/Funktion/Kürzel/Version, Zugangsdaten entfernen | ein PR, Verhalten unverändert |
| CALC-01 | P2 | kaufmännische Rundung an den fünf `round()`-Geldstellen | je Stelle prüfen, ob festgeschriebene Angebote betroffen sind |
| DB-01 | P2 | Diagnose verwaister Verweise | Support-Paket + Test |
| TEST-02 | P2 | wöchentlicher Lauf mit Abdeckung und `pip-audit` | Workflow mit `schedule`, nicht im Pflicht-Check |

## Offen – bewusst nicht jetzt

| ID | P | Warum nicht jetzt |
|---|---|---|
| SEC-03 | P2 | Admin-Schutz am eigenen Platz lässt sich ohne Server nicht erzwingen (die Datendatei gehört dem Benutzer). Nach SEC-01/02 wirkt eine Änderung nur noch lokal und wird zurückgesetzt. Endgültig erst mit zentralem PostgreSQL-Server und Rechten in der Datenbank. |
| CODE-02 | P3 | Große Dateien/Funktionen nur beim nächsten fachlichen Umbau teilen; ein Umbau ohne Anlass gefährdet bitgleiche Ergebnisse (Regel: keine größeren Umbauten ohne Begründung). |
| CODE-04 | P3 | Importe in Funktionen sind die gewählte Lösung gegen Zyklen. |
| SEC-04 | P3 | Klartext-Altpasswort wird beim Öffnen umgestellt; Entfernen erst, wenn keine Version vor 0.8 mehr im Umlauf ist. |

## Nicht prüfbar in dieser Umgebung

- Bedienung am echten Windows-PC, Startzeit und Speicher unter Windows, Grafiktreiber (3D).
- Outlook über COM (klassisches Outlook): nur Tests mit nachgebildetem Outlook; Echttest bei Patrick offen.
- Gemeinsamer Ordner auf einem echten Netzlaufwerk/OneDrive mit mehreren PCs gleichzeitig (Tests mit lokalen Ordnern
  und dem Lasttest bis 25 Plätze).
- STEP-Messung mit echten Kundendateien (nur Referenzdateien aus `tests/step`).
- 10–25 gleichzeitige Benutzer im Echtbetrieb: Lasttest vom 14.11. mit erzeugten Daten, kein Feldtest.

## Offen bei Patrick (unverändert aus dem Projekt)

- Hauptadmin-Ersteinrichtung (Voraussetzung, damit SEC-01/02 voll greifen).
- Lizenzen für alle Plätze vor dem 20.11.2026 (Durchsetzung der Lizenz ab diesem Tag).
- Echttest Outlook am PC.
