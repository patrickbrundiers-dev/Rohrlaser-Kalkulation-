# Offene Punkte

Stand 17.11.2026. Reihenfolge wie im Maßnahmenplan ([AUDIT_REPORT.md](AUDIT_REPORT.md#4-maßnahmenplan)).

## Offen – wird in dieser Prüfung noch umgesetzt

Nichts mehr: Alle Maßnahmen 1–6 sind umgesetzt (0.9.375–0.9.382), siehe [FIX_LOG.md](FIX_LOG.md).

## Offen – bewusst nicht jetzt

| ID | P | Warum nicht jetzt |
|---|---|---|
| SEC-03 | P2 | Admin-Schutz am eigenen Platz lässt sich ohne Server nicht erzwingen (die Datendatei gehört dem Benutzer). Nach SEC-01/02 wirkt eine Änderung nur noch lokal und wird zurückgesetzt. Endgültig erst mit zentralem PostgreSQL-Server und Rechten in der Datenbank. |
| CODE-01 | P3 | Ungenutzte Funktionen (vulture, Konfidenz 60–100 %) werden nicht gelöscht: Ein Teil wird über Qt-Signale, Tests oder dynamisch aufgerufen, und Löschen ohne fachlichen Anlass bringt keinen Nutzen für Kalkulation oder Daten (Regel 1). Beim nächsten Umbau des jeweiligen Moduls mitprüfen. |
| CODE-03 | P3 | Parameter ohne Wirkung bleiben, damit Aufrufer und gespeicherte Abläufe unverändert bleiben (Regel 2); beim nächsten Umbau der Funktion entfernen. |
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

- **SEC-01/02 sind ab 0.9.376 im Programm behoben, greifen aber erst, wenn die Hauptadmin-Lizenz eingerichtet ist und
  der Hauptadmin einmal die Admin-Vorgaben speichert.** Bis dahin gilt der alte Weg (unsignierte Pakete).

- Hauptadmin-Ersteinrichtung (Voraussetzung, damit SEC-01/02 voll greifen).
- Lizenzen für alle Plätze vor dem 20.11.2026 (Durchsetzung der Lizenz ab diesem Tag).
- Echttest Outlook am PC.
