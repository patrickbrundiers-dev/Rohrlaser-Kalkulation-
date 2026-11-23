# Materialoptimierung und Verschachtelung (23.11.2026)

Auftrag Patrick 23.11.2026 20:30 UTC: Verschachtelung auf CAD/CAM-Niveau. Ergänzungen: Reste und Lager nur optional;
alles nach Empfehlung einbauen; Zuschnitte aus 12 m bedeuten immer den Kauf der ganzen 12-m-Stange (Walzlängen vom
Werk ab ca. 20 t nur Sonderfall); Standardlängen 6 und 12 m, nahtlose Rohre auch 5–7 m.

## 1. Analyse vorher

- `optimierung.py`: exaktes Schnittmuster-Verfahren je Stangenlänge (Muster aufzählen, Simplex/B&B auf ganzzahlige
  Stangenzahl, FFD als Start, musterarm). Ergebnis je Länge optimal (wenigste Stangen).
- `rechnen.py`: je Abmessung **eine** Stangenlänge (Angebotsstange). Lieferlängen-Vergleich (`laenge_vergleich`)
  wählt die günstigste einzelne Lieferlänge; Mischen nur über `vorrat_planen` (Vorrat, Lager).
- Lücken: keine gemischten Lieferlängen nach Preis; kein Vergleich mehrerer Ziele; keine Sicht auf die Stangen mit
  Handänderung; Reststücke nur über den Lagerplan, ohne Zustand gesperrt/Ausschuss; keine Trennung Einkauf
  gegenüber kalkulatorisch je Stange.

## 2. Benchmark

| Fall | bisher | neu |
|---|---|---|
| Patrick-Beispiel 12×850, 8×1250, 6×430, 4×1800 (QR 40x40x3, Lieferlängen 6/6,5/7 m mit Preis) | 6 × 6 m = 36.000 mm, 360 € | A/B: 3 × 6,5 m + 2 × 6 m = 31.500 mm, 318 € |
| typische Aufträge, gemischte Längen | – | 1–6 % weniger Einkauf |
| 12 m mit Zuschnitt (T03, Beladung bis 6,5 m), Test 9 | 186.000 mm | 126.000 mm (ganze 12-m-Stangen bezahlt) |
| Großauftrag 519 Teile, Strategie B | – | 2,8 s (vorher 13 s vor Begrenzung des Mischplans, gleiches Ergebnis) |

Alle Pläne sind geprüft (`nesting.pruefe`): jedes Teil genau einmal, keine Stange überbelegt, Teile + Schnitte +
Endbeschnitt + Rest = Stangenlänge, Greiferrest frei, Verfügbarkeit und Reststücke eingehalten.

## 3. Lösung

- `nesting.py` (ohne Qt): Strategien A Material, B Kosten, C Reste zuerst, D Fertigung, E ausgewogen (€-Punkte:
  Material + Beladungen + € je verschiedene Belegung − Restgutschrift). Kombination: exakte Einzellänge
  (bestehender Kern, B&B/Simplex), Mischplan über `vorrat_planen`, Umverteilung der schwächsten Stangen
  (`schwanz`, Multi-Start über Mischungen), Bündeln (Teile tauschen, Freiraum sammeln), Reste füllen. Jede Strategie
  ist nie schlechter als der bisherige Plan in ihrem Ziel. Mindestabnahme je Lieferlänge wird eingehalten.
- 12 m mit Zuschnitt: Lieferlängen über der Beladelänge über `variante_planen`; die ganze Lieferstange wird
  bezahlt; gemischt mit ladbaren Längen.
- `rechnen.py`: Wahl je Abmessung (`kopf['nesting']`) bzw. Belegung von Hand (`kopf['stangen_hand']`), Schema 104
  `angebote.nesting`. Ohne Wahl genau wie bisher (Regressionstest bitgleich).
- Kalkulation: Stangen tragen Einkauf und kalkulatorische Kosten getrennt; Reststücke Einkauf 0 €, kalkulatorisch
  Restwert. Kundenangebot ohne Interna (Test mit Kunden-PDF).
- Lager: Zustand frei/gesperrt/Ausschuss mit Journal, verwertbar (Endbeschnitt + Greiferrest + Schnitt +
  `rest_min_nutz`), Reststücke im Nesting nur mit Lager **und** Reststücken (Vorgabe aus).
- Nesting-Arbeitsplatz (`nesting_dialog.py`): Vergleichstabelle mit 15 Kennzahlen und Rechenzeit, maßstäbliches
  Stangenbild, Teile per Klick umsetzen (geprüft), Rückgängig, Übernehmen; Rechnung im Hintergrund mit Fortschritt
  und Abbruch.
- Lokale Hinweise (`nesting_hinweise.py`): feste Prüfregeln, keine Netzverbindung, keine Rechnung.

## 4. Bewusst nicht gebaut

- Genetischer Algorithmus: für eindimensionales Schneiden liefert der bestehende exakte Kern je Länge bereits das
  Optimum; ein GA bringt dort nur Laufzeit und Zufall (Ergebnisse müssen auf jedem PC gleich sein).
- 3D-Ansicht des Nestings: bei Stangen ohne Mehrwert gegenüber dem maßstäblichen 2D-Bild.
- Common-Line-Cutting: bleibt bei der vorhandenen Regel (zwei gerade Enden teilen einen Schnitt).
- Aufträge übergreifend verschachteln: nur innerhalb eines Angebots (Staffeln/Positionen); übergreifend gehört in
  die Fertigung/Auslastung.

## 5. Tests

- `tests/test_nesting_2311.py` (Engine, 12 Szenarien), `tests/test_nesting_arbeitsplatz.py` (Oberfläche, Angebot,
  Kunden-PDF, Lager).
- Bestehend grün: Lager, Optimierung, Schachtelvergleich, Stangenvorgabe, Lieferlängen, Varianten, Staffelpreise,
  Regression (20 Angebote unverändert), Teilen, Cache, Fertigung u. a.
