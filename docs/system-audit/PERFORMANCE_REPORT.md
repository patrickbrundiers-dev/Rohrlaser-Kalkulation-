# Performanceanalyse

Stand 17.11.2026, `main` ba3cdc2 (0.9.372). Gemessen im Linux-Container der Prüfung (4 Kerne, 15 GB, Qt offscreen,
Python 3.13), nicht auf einem Werkstatt-PC; Werte unter Windows sind erfahrungsgemäß etwas höher. Erzeugte
Testdaten, keine Kundendaten.

## Heute gemessen

### Start und Speicher (Hauptfenster, `start_messung.py` im Projektordner `system-audit/nachweise/`)

Je 3 Läufe in einem neuen Prozess; Zeit in Sekunden, Speicher = höchster belegter Arbeitsspeicher des Prozesses.

| Datendatei | Programmteile laden (Qt, Module) | Datendatei öffnen | Hauptfenster aufbauen und zeigen | Arbeitsspeicher |
|---|---|---|---|---|
| leer | 0,32–0,34 s | 0,04–0,06 s | 1,28–1,37 s | 242–243 MB |
| 1.000 Angebote (je 5 Positionen) | 0,34–0,36 s | 0,04–0,05 s | 2,15–2,77 s | 247–254 MB |

Ergebnis: Start unter 2 s ohne Daten, knapp 3 s mit 1.000 Angeboten; der Speicher wächst mit den Daten kaum
(+5–11 MB). Kein Befund.

### Datenbank (`werkzeuge/programm_messung.py --angebote 1000`, Median in ms)

| Messung | SQLite | PostgreSQL (eingebettet, 16) | 14.11. SQLite / PG |
|---|---|---|---|
| Datendatei öffnen | 44 | 295 | 46 / ~360 |
| Angebot anlegen (je Angebot, 5 Pos.) | 14,6 | 29,9 | 14,0 / 30,6 |
| Angebotsliste | 9,7 | 14,2 | 11,5 / 13,6 |
| Suche | 3,5 | 4,8 | 4,1 / 4,7 |
| Angebot öffnen 5 / 50 Positionen | 0,3 / 1,4 | 1,7 / 2,6 | 0,3 / 2,1 bzw. 1,1 / 1,8 |
| Zelle ändern | 1,1 | 2,0 | 0,9 / 2,4 |
| Angebot kopieren (50 Pos.) | 76 | 160 | 86 / 133 |
| Sicherung | 59 | 273 | 58 / 267 |

Ergebnis: alle Alltagsvorgänge unter 20 ms, gleich wie am 14.11. (kein Rückschritt seit der Umstellung). PostgreSQL
ist beim Öffnen, Kopieren und Sichern langsamer (Server-Verbindung, Sicherung als SQLite-Kopie), für einen Platz
unkritisch.

## Übernommen aus früheren Messungen

| Messung | Ergebnis | Quelle |
|---|---|---|
| Gleichzeitige Benutzer auf einer Datenbank (10.000 Angebote) | PostgreSQL: Liste 280 ms (95 %: 678 ms) bei 10 Benutzern, 885 ms (2,5 s) bei 25; SQLite bricht ab 5 Benutzern in den Spitzen ein (bis 15 s) | Lasttest Phase 8, 14.11.2026 |
| Abgleich über den gemeinsamen Ordner | 25 PCs: 358 ms je Abgleich (95 %: 432 ms), alle mit gleichem Stand, keine doppelten Nummern | Lasttest Phase 8, 14.11.2026 |
| Datenbank-Wachstum | ~0,2 MB je Angebot; Liste/Suche/Speichern unkritisch bis 10.000; Wiederholteile, Abgleich, Versand, Sicherung beschleunigt (#329, #334) | Prüfung 28.10.2026 |
| Programmstart Windows | 1,3–1,5 s, Arbeitsspeicher-Plateau ~247 MB | Prüfung 29.10.2026 |
| Optimierer | 200 Positionen 49 → 15 s; ab 1.500 Teilen bis 4 Hilfsprozesse, Ergebnis bitgleich | Prüfungen 22./24.10.2026 |

## Bewertung für 10–25 Benutzer

- Jeder PC arbeitet mit seiner eigenen Datenbank; gleichzeitig greifen nur Programme desselben PCs zu (Kalkulation,
  Auslastung, zweites Fenster). Die Zielgröße 10–25 Benutzer betrifft also vor allem den **Abgleich** über den
  gemeinsamen Ordner – gemessen bis 25 PCs unter 0,5 s je Abgleich.
- Für einen späteren **zentralen PostgreSQL-Server** zeigt der Lasttest: bis 10 gleichzeitige Benutzer unter 0,7 s
  auch im 95-%-Wert; bei 25 Benutzern Liste bis 2,5 s – dann wären seitenweise Liste und eine Volltextsuche sinnvoll.
- Engpass bei vielen gleichzeitigen neuen Angeboten ist die Nummernvergabe (Nummernvorrat ist eingebaut, Einstellung
  `nummern_vorrat`, Vorgabe 0).

## Hintergrundprozesse

Lebenszeichen im gemeinsamen Ordner alle 30 s, Abgleich nach Eingabe (Puls), Online-Update-Prüfung, tägliche
Sicherung im Hintergrund, Wiederholteile-Suche im Hintergrund, Laufzeit-Wächter (`tempo.py`), Optimierer-Hilfsprozesse
nur ab 1.500 Teilen. [Code] nur gesichtet, nicht einzeln gemessen; `tempo.py` schreibt Blockaden der Oberfläche ab 0,5 s und Hänger ab 10 s nach `Daten/Protokoll/tempo.log`.

## Optimierungsmöglichkeiten (nicht dringend)

| Punkt | Nutzen | Aufwand |
|---|---|---|
| Seitenweise Angebotsliste und Trigramm-Suche, erst mit zentralem Server | Liste bei 25 Benutzern < 0,5 s | mittel |
| Nummernvorrat für Plätze mit vielen neuen Angeboten vorbelegen (z. B. 20) | weniger Wiederholungen bei gleichzeitiger Anlage | klein |
| Leistungstest der Hauptansichten in CI (wie `test_angebot_leistung.py`) auf alle Reiter ausdehnen | Rückschritte fallen früher auf | klein |
