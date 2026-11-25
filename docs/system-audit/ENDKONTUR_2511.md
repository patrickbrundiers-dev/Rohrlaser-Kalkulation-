# Endkonturen universell + Konturverschachtelung (25.11.2026)

Master-Auftrag Patrick 25.11.2026: „Nicht mehr die Frage, ob zwei Gehrungen ineinanderpassen, soll entscheidend
sein, sondern ob zwei beliebige geometrische Schnittkonturen technisch zulässig ineinander verschachtelt werden
können.“ Version 0.9.488 (vorläufig), kein Schema-Sprung.

## 1. Recherche: Verfahren für Rohr-Nesting mit Endkonturen

| Verfahren | Wofür in der Literatur | Bewertung für uns |
|---|---|---|
| No-Fit-Polygon / Minkowski-Summe | 2D-Blech-Nesting freier Formen | Für ein Rohr reduziert sich das Problem auf **eine** Dimension (Längsabstand zweier Nachbarn bei fester Drehung). Statt Polygon-Minkowski genügt das Maximum über Zellpaare des abgewickelten Mantels – exakt, schneller und ohne Rundungsprobleme. |
| Raster/Pixel-Verfahren | robuste Kollisionsprüfung | Übernommen als **Zellen am Umfang** (0,5 mm, sicheres Minimum je Zelle), damit beliebige Verläufe (auch STEP-Umrisse) gleich behandelt werden. |
| Bin-Packing (FFD/BFD, Muster, Simplex, Branch-and-Bound) | 1D-Zuschnitt | Bleibt unverändert der Kern (#630/#639); die Konturtrennung ist nur ein anderer Abstand zwischen Nachbarn. |
| Genetische Algorithmen / Simulated Annealing | große, unstrukturierte Suchräume | Bringen bei uns nichts (Benchmark #639: Stangenzahl je Länge bereits bewiesen optimal). Für die **Reihenfolge** auf der Stange reicht eine deterministische lokale Suche (Strategie P). |
| Räumliche Indizes (R-Baum, Gitter) | schnelle Nachbarsuche | Umgesetzt als Fenster in `Geo.nachbarn`: je Zelle nur Zellen, deren Querabstand kleiner als der geforderte Abstand ist. |

Alle Grenzen sind Rechenschritte, keine Sekunden: dasselbe Angebot ergibt auf jedem PC denselben Schnittplan.

## 2. Konturmodell (endkontur.py)

Jedes Ende ist ein Verlauf d(s) auf dem abgewickelten Mantel (s wie `skizze.s_zu_uv`, Blick von A; d = Abstand
hinter der Spitze). Gerade, Gehrung, Schrägschnitt, Ausklinkung, Gegenrohr, gemessene STEP-Enden und die neuen
Endkonturen liefern alle über `skizze.schnitt_x` / `ende_abwicklung` denselben Verlauf.

Neue Endkonturen (Eingabe `kontur` am Ende): Schräg, V-Spitze, V-Kerbe, U-Kerbe, U-Zunge, S-Kurve, Bogen konvex,
Bogen konkav, Stufen, Freiform (Seitenansicht), Freiform Abwicklung (direkt auf dem Mantel), Kombination.

- Schnittlänge: Kurvenlänge auf dem Mantel / Umfang × gerade Schnittlänge (Eckradien und offene Profile wie beim
  geraden Schnitt).
- Prüfung (`pruefen`): Kontur tiefer als das Teil, Schlitz schmaler als die Fuge = FEHLER; dünne Zunge,
  Innenecke < 60° = HINWEIS.
- Darstellung: Skizze, Abwicklung, 3D (`rohr3d`), Stangenabwicklung und DXF lesen denselben Verlauf.

## 3. Verschachtelung

Material von Teil 1 bei z ≤ −d_B(j), von Teil 2 bei z ≥ x + d_A(i). Gesucht ist der kleinste Längsabstand x der
Spitzen, bei dem an jeder Stelle der Abstand im Raum mindestens G = 2 × Schnittverlust + Abstand + Sicherheit ist:

    x = max über Zellpaare (i, j) mit Querabstand q < G von  sqrt(G² − q²) − d_B(j) − d_A(i)

q ist eine sichere untere Schranke (kleinerer Abstand außen/innen minus Zellgröße), d je Zelle das sichere
Minimum (Stützstellen, halber Sprung, Knicke genau). 3D-Schnitte werden um Wand × tan(Winkel) nach vorn angenommen.
Drehung = Verschiebung um ganze Zellen; erlaubt sind nur die Drehungen der bestehenden Regeln (feste/unbekannte Naht
nie, gewendet nie). Ein gewendetes Duplikat nimmt das andere Ende gespiegelt.

- **Kollisionsprüfung**: `pruefe_drehungen` misst für jede Konturstelle unabhängig über **alle** Zellpaare
  (`kleinster_abstand`); zu eng = AssertionError. Tests prüfen zusätzlich an der feinen echten Kante
  (`echter_abstand`).
- **Bitgleichheit**: Gruppen, die außer ebenen Gehrungen keine Endkontur haben, verlieren die Verläufe
  (`rechnen._konturen_nur_wo_noetig`) und rechnen mit der alten Formel. `test_regression_ergebnisse` grün.
- Nasen einer Steckverbindung und offene Profile: keine Verschachtelung.

## 4. Strategien (Zuordnung zum Auftrag)

| Auftrag | Programm |
|---|---|
| A maximale Materialausnutzung | A Minimaler Materialverbrauch |
| B Schnelloptimierung | H Schnellrechnung |
| C Präzisionsoptimierung | **P Präzisionsoptimierung (neu)**: A + lokale Suche (schieben/tauschen, 600 Bewertungen bis 40 Teile) + exakte Suche × 4; nie schlechter als A |
| D Fertigungsoptimierung | D Schnellste Fertigung |

## 5. Vergleich und Anzeige

Nesting-Arbeitsplatz: Zeile **ohne Konturverschachtelung** (ursprüngliche Belegung), Spalten *Enden ineinander*,
*davon Endkonturen*, *Trennschnitte*; Karte Status mit Einsparung (Stangen, m, €, %); Bericht-Text mit Ausnutzung
vorher → nachher. Stangenabwicklung und 3D zeigen die Konturen an ihrem Platz.

Beispiel (Test): 26 Teile 450 mm, V-Kerbe/V-Spitze 25 mm auf QR 60×3, Fuge 0,2, Abstand 2,5, Sicherheit 0,5:
ohne Konturverschachtelung 3 Stangen, mit 2 Stangen (24 Konturstellen), −6 m, −60 € (bei 60 €/Stange).

## 6. Einstellungen

- `kontur_verschachtelung` (ja/nein, Vorgabe ja)
- `kontur_sicherheit` (mm, Vorgabe 0,5)

## 7. Tests

`tests/test_endkontur.py` (neu, in TESTS): Arten, Prüfung, Verschachteln auf Rund-/Quadrat-/Rechteckrohr mit
Gegenprobe, Mindestabstand, Kollision, Drehung, Nasen/offene Profile, feste Naht, Bitgleichheit Gehrungen,
Strategie P, Vergleich, Schneidweg-Rechner. Bestehende Tests angepasst: `test_nesting_arbeitsplatz` (P in der
Reihe).
