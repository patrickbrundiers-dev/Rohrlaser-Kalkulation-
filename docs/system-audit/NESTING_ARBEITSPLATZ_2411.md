# Nesting-Arbeitsplatz 2.0 (24.11.2026)

Auftrag Patrick 24.11.2026 15:39 UTC „Nesting-Arbeitsplatz 2.0 – Redesign, intelligente Optimierung, Performance und
Berechnungsqualität“ plus Nachträge (Verknüpfung mit der Optimierung, Darstellung wie in der Optimierung mit Gehrungen
ineinander, Teile frei verschieben, von Hand verschachteln mit Zurücksetzen, Stangenbild detaillierter).

## Ergebnis in Kürze

| Bereich | Umsetzung | Datei |
|---|---|---|
| Arbeitsplatz | links Bauteile/Material/Reststücke/Nicht eingeplant, Mitte 2D/Stangenbild/3D, rechts Kennzahlen, unten Vergleich/Kosten/Protokoll/Export, Bereiche ein-/ausblendbar | `nesting_dialog.py` |
| Darstellung | gemeinsame Zeichnung `stange_zeichnen` (Gehrungen, ineinander, gemeinsamer Schnitt, Fugen, Naht, Rest/Verschnitt, Greiferrest, Maßkette, Lineal) für Arbeitsplatz und Stangenbild | `stangen_ansicht.py`, `angebot_fenster.Stangenbild` |
| Von Hand | Ziehen (feste Reihenfolge, geprüft mit `nesting.folge_fest`), Stange auflösen, Einsetzen, Rückgängig/Wiederholen, Abmessung/Alles zurücksetzen | `nesting_vergleich.einfuegen/aufloesen`, `rechnen.hand_planen` |
| 3D | gewählte Stange als Rohr (QPainter, kein OpenGL) aus denselben Abschnitten | `nesting_3d.py` |
| Strategien | neu F Wenigste Stangen, G Geringster Verschnitt, H Schnellrechnung; E bleibt bitgleich (nur A–D) | `nesting.py` |
| Machbarkeit | max. Stangenlänge, Hüllkreis/Gewicht (`grenze_ueberschritten`), Überbelegung = Fehler; Lademinimum, kürzestes Teil, 3D-Teil = Hinweis | `nesting_machbarkeit.py` |
| Vergleich | Zeile „aktuell (gespeichert)“, Hinweis „veraltet“, Live-Status, Empfehlung nur zulässig und nur mit Vorteil | `nesting_vergleich.py` |
| Verknüpfung | Rechtsklick im Stangenbild → Arbeitsplatz bei dieser Stange; Reiter Optimierung: Vorschlag „Verschachtelung“ (≥ 1 € oder 1 Stange, nie teurer) als neue Fassung | `angebot_fenster.py`, `optimierungsvorschlaege.py`, `optimierung_seite.py` |
| Messung | Benchmark 10/50/100/500 Teile und Baugruppe, Fingerabdruck je Plan | `werkzeuge/nesting_benchmark.py` |

## Algorithmuswahl

Die Analyse zeigte: je Lieferlänge ist die Stangenzahl in allen Messfällen schon bewiesen optimal (Untergrenze
erreicht, exakte Muster-/Simplex-/B&B-Rechnung in `optimierung.py`). Ein genetischer Algorithmus oder Simulated
Annealing würde keine Stange sparen, deshalb rechnen sie nicht. Die Zeit ging in mehrfach gerechnete gleiche
Zwischenergebnisse (Plan je Lieferlänge, gemischter Plan) je Strategie. Diese werden jetzt je Abmessung einmal
gerechnet und zwischengespeichert (`nesting._grundplaene`, `planen`-Merker, max. 256 Einträge). Grenzen bleiben
Rechenschritte, keine Sekunden: das Ergebnis ist auf jedem PC gleich.

## Messung vorher/nachher (gleicher PC, Median aus 3 Läufen, Weg wie der Arbeitsplatz: Strategien A, B, D, E)

| Fall | Lieferlängen | vorher [s] | nachher [s] | Faktor | Stangen (E) vorher → nachher | eingekauft (E) [m] |
|---|---|---|---|---|---|---|
| 10 Teile | 6 m | 0.01 | 0.01 | 2.2× | 5 → 5 | 30.0 → 30.0 |
| 10 Teile | 6/12 m | 0.03 | 0.00 | 8.1× | 2 → 2 | 24.0 → 24.0 |
| 50 Teile | 6 m | 0.04 | 0.01 | 3.1× | 9 → 9 | 54.0 → 54.0 |
| 50 Teile | 6/12 m | 0.15 | 0.04 | 4.2× | 5 → 5 | 54.0 → 54.0 |
| 100 Teile | 6 m | 0.10 | 0.07 | 1.5× | 33 → 33 | 198.0 → 198.0 |
| 100 Teile | 6/12 m | 0.60 | 0.12 | 5.0× | 16 → 16 | 186.0 → 186.0 |
| 500 Teile | 6 m | 0.76 | 0.52 | 1.5× | 144 → 144 | 864.0 → 864.0 |
| 500 Teile | 6/12 m | 2.46 | 1.72 | 1.4× | 71 → 71 | 852.0 → 852.0 |
| Baugruppe 1200 Teile, 6 Abmessungen | 6 m | 0.78 | 0.42 | 1.9× | 292 → 292 | 1752.0 → 1752.0 |
| Baugruppe 1200 Teile, 6 Abmessungen | 6/12 m | 20.57 | 3.44 | 6.0× | 145 → 145 | 1728.0 → 1728.0 |

Alle Fingerabdrücke vorher = nachher (bitgleiche Pläne). Aufruf:
`python werkzeuge/nesting_benchmark.py lauf neu.json --wdh 3` und
`python werkzeuge/nesting_benchmark.py vergleich alt.json neu.json --bericht bericht.md`.

## Was bewusst nicht gebaut wurde

- 12-m-Entscheidung über Gesamtkosten: eigener Auftrag (PR #637, `rechnen.laenge_vorteil`); F/G/H nutzen keine
  12-m-Zuschnitte.
- Reststücke nur mit eingeschaltetem Lager und Reststücken (Vorgabe aus); doppelte Verplanung eines Rests verhindert
  `nesting.pruefe` je Plan.
- Parallelrechnen der Abmessungen: nach dem Zwischenspeicher nicht mehr nötig (größter Fall 3,4 s); bleibt offen.
- LST/BPF-Lernen: läuft im eigenen Thread; hier nur validierte Werte (keine Änderung).

## Tests

`tests/test_nesting_arbeitsplatz2.py` (neu, in `tests/alle.py`): Strategien F/G/H geprüft, Zwischenspeicher bitgleich,
Machbarkeit, Zeile „aktuell“, Live-Status, Protokoll, CSV, Dialog (Bereiche, 3 Ansichten, Ziehen, neue Stange,
Rückgängig/Wiederholen, zu voll, Auflösen, Einsetzen per Klick, CSV, Zurücksetzen), feste Reihenfolge gespeichert und
genau so neu optimiert, Sprung aus dem Stangenbild, Vorschlag im Reiter Optimierung als neue Fassung.
Regressionstest `test_regression_ergebnisse.py` unverändert grün (Ergebnisse bitgleich).
