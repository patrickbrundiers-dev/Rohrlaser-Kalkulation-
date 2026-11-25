# Abwicklungskern für alle Konturen (Master-Auftrag 25.11.2026)

Plan: https://claude.ai/artifact/DpkYezVhUe2Kioe7ZL7CC7

## Ziel

Jede Kontur eines Rohrs (Anfang, innen, Ende) bekommt eine **Rolle** und eine **Schneidbarkeitsstufe** mit Grund.
Der Schneidweg wird gegen die Konstruktion geprüft: nichts doppelt, nichts fehlt, Längen richtig. Gemessene Werte,
Schnittlängen und Preise bleiben gleich, solange kein Test einen Fehler nachweist.

## Pakete

| Paket | Inhalt | Stand |
| --- | --- | --- |
| P1 | Testsammlung: 10 Referenzteile mit Sollmaßen aus der Konstruktion | PR A |
| P2 | Rolle (8) und Schneidbarkeit (1–4) je Kontur, Importanalyse | PR A |
| P3 | Schneidweg-Bilanz: jede Schnittkante genau einer Kontur | PR A |
| P4 | echte Innenkante bei 3D-Schnitten statt Wand × tan | nach dem Endkonturen-PR |
| P5 | Viewer 3D/2D: Farben je Rolle, Schalter, Auswahl, Handkorrektur | nach P2 |

## P1 Testsammlung

`tests/erzeuge_referenz_konturen.py` baut die Teile aus Grundkörpern (OpenCascade) und rechnet die Sollwerte
unabhängig von der STEP-Messung: Formel oder numerisches Integral über die Schnittkurve auf der Außenhaut (20 000
Stützstellen). Die Sollwerte stehen mit Formel in `tests/daten/referenz_konturen_soll.json`, die Teile in
`tests/step_referenz_konturen/`. `tests/test_referenz_konturen.py` misst und vergleicht (Toleranz 0,1 mm oder 0,2 %).

| Nr | Fall | Soll [mm] | gemessen [mm] |
| --- | --- | --- | --- |
| R01 | RE 60×40×3 r6, gerade | 189,699 je Ende | 189,70 |
| R02 | RR 48,3×3, Gehrung 45° | 184,516 (Ellipse) | 184,55 |
| R03 | QR 50×3, schräg 20°/10° | 208,154 | 208,15 |
| R04 | RR 60,3×3, Bohrung Ø 20 | 67,013 (2D radial) | 67,01 |
| R05 | RE 80×40×3, Langloch 40×10 | 91,416 | 91,42 |
| R06 | QR 60×3, Ø 12 durch beide Wände + 2 Rechtecke | 2 × 37,699 + 2 × 90 | 37,70 / 90,00 |
| R07 | RR 42,4×2 Sattel gegen Ø 60,3 | 138,661 | 138,66 |
| R08 | RR 33,7 unter 60° gegen Ø 60,3, 8 mm außermittig | 120,964 | 120,96 |
| R09 | RE 60×40×3, Ausklinkung am Ende + Bohrung Ø 8 | 240 + 25,133 | 240,00 / 25,13 |
| R10 | Baugruppe R01 + R02 + R07 + Platte | wie einzeln | wie einzeln |

**Befund:** Alle 10 Teile stimmen mit der Konstruktion überein. Kein Fehler der Messung gefunden, daher keine
geänderten Werte. R04: Die Bohrung im Rundrohr wird wie festgelegt als 2D-Schnitt gerechnet (Strahl zur Rohrmitte,
innen Ø 20 maßhaltig, STEP-JSON 1.11), außen 67,01 mm; die reine 3D-Schnittkurve wäre 63,29 mm. Beides steht im Soll.

## P2 Rolle und Schneidbarkeit

`programm/rohrlaser/konturrolle.py` (ohne Qt) leitet aus einer Zeile von `konturen_liste` ab:

- Rolle: Anfangsschnitt, Endeschnitt, Anschlusskontur (Ende mit Gegenrohr), Innenkontur (Bohrung, Langloch,
  Senkung), Durchbruch (gegenüberliegende Bohrung gleicher Achse), Ausschnitt, Freiformkontur, nicht eindeutig.
  Gravur, Sackbohrung, Fließloch: `schnitt=False`.
- Stufe 1 eindeutig, 2 wahrscheinlich (Sattel, 3D-Bohrung, erkannte Sonderkontur, Teil unsicher), 3 problematisch
  (ohne Grundform, Fase, mehrere Wände, Öffnung kleiner als die Wand), 4 nicht sicher (keine Schnittlänge, Form
  nicht erkannt, Lage fehlt, unbekannte Art, ungültige Zahl). Jede Stufe hat einen Grund.

`bauteil_analyse` schreibt `rolle`, `schneidbar`, `schneidbar_text`, `rolle_grund` in jedes Konturmerkmal. Die
Importanalyse zeigt die Spalten Rolle und Schneidbarkeit (Farbe je Stufe, Grund im Tooltip); „Nächstes zu prüfen“
findet auch Stufe 3 und 4. Es wird nichts neu gemessen.

Verteilung über die Prüfbasis (124 Dateien, 445 geschnittene Konturen): 439 Stufe 1, 6 Stufe 3, keine Stufe 4.
Stufe 3: 5 Enden ohne Grundform (Spitze, Ausklinkung, Gewinde-Gravur-Teil; erkennt der Endkonturen-Thread künftig
als Konturart, dann Stufe 2) und eine Bohrung Ø 1,5 in 3 mm Wand (Fertigbarkeits-Prüfteil, gewollt).

## P3 Schneidweg-Bilanz

`step_geometrie._schneidweg_bilanz` nimmt jede Kante zwischen Außenmantel und Schnittfläche (das ist eine Kante, die
der Laser schneidet) und zählt, wie vielen Konturen sie zugeordnet ist: Innenkonturen und Gravuren über die
Kantenliste der Konturliste (`_KonturListe.kanten`), Enden über die Kanten von Ende A/B. Befunde: Kante ohne Kontur
(fehlt), Kante in mehreren Konturen (doppelt), Konturkante, die auf keiner Schnittfläche liegt (fremd), und die
Längensumme (Toleranz 0,01 mm). Ergebnis in `Teil.bilanz`; in der Spalte sicherheit steht `schneidweg=geprüft` bzw.
`schneidweg=wahrscheinlich` mit einem Hinweis, der den Befund nennt (Konfidenz −8, Ampel unverändert). Kein
Schema-Sprung, kein neuer Messwert. Offene Profile haben eine eigene Konturerkennung und noch keine Bilanz.

Ergebnis: 149 Rohrteile aus der Prüfbasis und der Testsammlung, **0 fehlende, 0 doppelte Kanten**. Zeit für die
Bilanz: 0,02 s bei 54 s Messung (0,03 %).

## Abgrenzung

- Konturart der Enden (V, U, Bogen, Stufen, Sonderkonturen): Thread Endkonturen (`endkontur.py`,
  `form_erkennung.py`). konturrolle liest deren Ergebnis `kontur_erkannt` / `form_erkannt` nur aus.
- Schnitt auf 0 mit Aufmaß (#660) und Fasen-Enden: Thread Supportpaket. konturrolle liest `fase` nur aus.
