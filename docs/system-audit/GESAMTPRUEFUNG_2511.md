# Gesamtprüfung 25.11.2026: Codeanalyse, Fehlersuche, Leistung

Auftrag Patrick 25.11.2026 20:20 UTC. Stand main 0.9.511 (Schema 106), Sicherungszweig `sicherung/vor-gesamtpruefung-2511`.
Grundregel: Rechenergebnisse ändern sich nur bei nachgewiesenem Fehler; Beschleunigungen nur bitgleich.

## 1. Vorgehen

| Schritt | Umfang |
|---|---|
| Ausgangslauf | volle Testsuite auf main: 591 Tests, 3.479 s. 4 rot, alle durch den Container (xcb-cursor fehlte, 12-px-Schrift, Speicherschwelle test_tempo 104 ≥ 100 MB); unstabil: test_rl_auslastung, test_angebot_leistung, test_werkzeugleiste |
| Stangenoptimierung | 400 kleine Zufallsgruppen (alle Merkmale: Gehrung, schräg, Kopf, Teileabstand, Lieferlängen, Drehung) gegen vollständige Brute-Force-Suche; 40 große Gruppen mit Prüfung; 1.650 Zufallsgruppen alt/neu; Serien bis 10.000 Teile |
| Kalkulation | Invarianten (Summe Positionen = Verkauf, Teilpreis × Stück = Positionspreis, endlich, nicht negativ) für die 20 Regressionsangebote und 400 Zufallsangebote |
| Schneidweg | Fuzz aller Konturarten mit Grenzwerten (0, negativ, NaN, 10⁹) |
| DXF | Fuzz mit zerstörten Dateien |
| Mail (.msg/.eml) | 4.000 zerstörte Mails mit eingebetteten Mails und 12-fach verschachtelten ZIP |
| RP-Profile | alle 141 Bibliotheksprofile: Umriss, Fläche gegen Bibliothekswert |
| Programmabläufe | werkzeuge/systemcheck.py mit cProfile (STEP-Import, Angebot, Optimieren, Kalkulation, 3D, PDF, Langzeitlauf) |
| Datenbank | Anweisungen je Vorgang gezählt (erste Anlage und normales Öffnen) |
| Recherche | psycopg-Pipeline, OCCT-Parallelität, Python free-threading, Numba/Cython, jeweils gegen Messwerte im Programm |

## 2. Befunde

| Nr. | Modul | Befund | Ursache | Schwere | Stand |
|---|---|---|---|---|---|
| G-01 | optimierung.aufloesen | große Serien mit schrägen Enden sehr langsam (10.000 Teile 158 s) | beim Auflösen schwacher Stangen wurde jede Kandidat-Stange je Teil neu mit passt() geprüft, obwohl Stange und Teileart unverändert waren (quadratisch) | hoch (Tempo) | **behoben #675**, bitgleich |
| G-02 | schneidweg.kontur | vertippte Anzahl/Reihen (Lochfeld 10⁹) füllte den Speicher, MemoryError bzw. Programm beendet | Liste der Konturen wurde ungeprüft n-fach vervielfacht | hoch (Absturz) | **behoben #675**: ab 100.000 Konturen je Zeile Fehlermeldung, übrige Zeilen rechnen |
| G-03 | rp_profile.umriss | 37 von 141 RP-Profilen ohne Kontur („Keine Blechfläche erkannt“), RP 1253-60 mit Fläche 0 | Bibliothek speichert verschobene, auf 4 Stellen gerundete Elemente; Punkte liegen genau auf der Grenze des Fanggitters (FANG 0,001) und fallen in verschiedene Zellen | mittel (Skizze, 3D, Zeichnung leer/falsch; Preis nicht betroffen, Fläche kommt aus der Bibliothek) | **behoben #675**: Ausweg mit um FANG/4 verschobenen Elementen; 103 richtige Profile unverändert |
| G-04 | optimierung | 10.000 Teile ≤ 1 mm auf einer Stange: 19–52 s | quadratisch in der Belegung einer einzigen Stange | niedrig (unsinnige Eingabe) | offen; Maschine „kleinstes Teil“ (min_teil) kann es schon abfangen |
| G-05 | ansicht3d.zeichnen (Software-Weg) | Drehen 0,55 s je Bild ohne OpenGL (Remote-Desktop, Einstellung Software) | Dreiecke werden je Bild fürs Sortieren in Stücke geteilt (1,7 Mio. Aufrufe, 850.000 Polygone bei 7 Teilen) | mittel (nur Software-Weg) | offen; iterative Fassung gemessen nicht schneller (Python-Aufwand gleich), siehe Empfehlung E-2 |
| G-06 | schneidweg | NaN in einer Konturangabe ergibt NaN-Schneidweg | keine Prüfung auf endliche Werte | niedrig (DB verwirft NaN, nur aus Import denkbar) | **behoben 0.9.514**: Meldung je Zeile |
| G-07 | rohr3d.py:263 | MemoryError bei absurden Maßen (Ø 10⁹) | Netzdichte aus Maß | niedrig | offen |
| G-08 | datenbank.position_neu | neue Positionsnummer MAX(nr)+1 vor der Transaktion | Lesen und Einfügen getrennt | niedrig (eine PostgreSQL je PC, ein Schreiber) | offen |
| G-09 | Tests | test_tempo-Speicherschwelle (100 MB) und test_bedienung_0611 (Schriftgröße) hängen vom Rechner ab | feste Schwelle | niedrig | test_tempo **behoben 0.9.514**, Schriftgrößen-Test offen |

Ohne Befund geprüft:
- Kalkulation: alle Invarianten in 420 Angeboten gehalten.
- Stangenoptimierung: in 400 Gruppen kein falsches „bewiesen“ und keine falsche Schranke.
- DXF: zerstörte Dateien werden sauber abgelehnt.
- Mail: 4.000 zerstörte Mails ohne Absturz und ohne Hänger (keine über 2 s), Rekursionsfehler in olefile werden abgefangen und protokolliert.
- Langzeitlauf (Angebot 10× öffnen/ändern/schließen): Speicher konstant 385 MB, Zuwachs 0,0 MB je Runde.
- Mehrfachrechnungen („doppelt“): 0 in allen Abläufen.
- Datenbank öffnen: 0,19 s mit 636 Anweisungen. Nur die erste Anlage braucht 1,8 s (5.585 Anweisungen, einmalig).

## 3. Messungen vorher/nachher (G-01, gleiche Ergebnisse)

| Fall | vorher | nachher | Gewinn |
|---|---|---|---|
| 10.000 × 50 mm, Ende B schräg | 152–158 s | 5,0–5,3 s | −97 % (≈ 30×) |
| 4.000 Teile gemischt | 27–30 s | 1,5–1,8 s | −94 % |
| 3 Arten × 1.500, schräg | 2,86 s | 0,84 s | −71 % |
| Kasten Gehrung 6 × 300 | 2,36 s | 1,59 s | −33 % |
| 8 Arten × 500 | 2,25 s | 1,55 s | −31 % |
| Zufallsangebot Seed 47 / 57 | 130 s / 176 s | 5,3 s / 6,5 s | −96 % |
| 2.000er-Serie: passt()-Aufrufe | > 100.000 | 9.024 | −91 % |

Bitgleichheit: 304 Zufallsgruppen und 4 große Serien mit `AUFLOESEN_MERKEN` an/aus, 1.650 Zufallsgruppen gegen den alten Stand, 20 Regressionsangebote (test_regression_ergebnisse).

## 4. Programmabläufe (systemcheck, 7 Test-STEPs, Container ohne GPU)

| Vorgang | Zeit | SQL |
|---|---|---|
| Programmstart | 1,08 s | – |
| Datendatei öffnen (erste Anlage) | 2,18 s | 2.746 |
| Hauptfenster aufbauen | 2,75 s | 453 |
| STEP-Import 7 Dateien | 6,48 s | 387 |
| Angebot öffnen kalt / warm | 0,38 / 0,07 s | 64 / 43 |
| Zelle ändern mit Prüfung | 0,27 s | 87 |
| Optimieren | 0,13 s | 48 |
| Angebots-PDF / Werkstatt-PDF | 0,28 / 0,27 s | 122 / 36 |
| 3D 360° drehen, 36 Bilder (Software) | 21,1 s | 36 |
| 3D zoomen, 20 Bilder (Software) | 13,2 s | 22 |

Engpass ist nur das Software-3D (G-05). Alles andere liegt unter 0,4 s je Klick.

## 5. Tests

Neu: `tests/test_gesamtpruefung_2511.py` (in tests/alle.py, ~22 s) mit
- Brute-Force-Gegenprobe der Optimierung,
- Alt/Neu-Vergleich,
- passt()-Zähler für die 2.000er-Serie,
- Kontur-Grenze mit Schneidweg-Rechnung,
- allen 141 RP-Profilen.

Grün nach den Änderungen: test_regression_ergebnisse, test_optimierung*, test_stangen*, test_nesting*, test_schneidweg, test_zeichnung*, test_rp_profile, test_step_rp, test_profilwechsel, test_auto_optimieren, test_kalkulationsbasis, test_anleitung, CI `tests`.

## 6. Recherche und Bewertung

| Thema | Ergebnis | Entscheidung |
|---|---|---|
| psycopg 3 Pipeline-Modus | spart Rundreisen bei vielen kleinen Anweisungen | nicht übernommen: normales Öffnen 0,19 s, je Klick unter 150 Anweisungen in < 0,1 s; kein messbarer Gewinn |
| OCCT BRepMesh parallel / SetRunParallel | Vernetzung und Booleans parallel | schon aktiv (step_geometrie, #643) |
| Python free-threading (3.13t/3.14t) | echte Thread-Parallelität | nicht übernommen: PySide6 und OCP müssten free-threading-Builds liefern; Parallelität läuft schon über Hilfsprozesse (parallel.py) |
| Numba | schnell für Zahlenschleifen | nicht übernommen: große zusätzliche Laufzeit-Abhängigkeit; Release wird schon mit Cython übersetzt |

Quellen: psycopg.org/psycopg3/docs/advanced/pipeline.html, dev.opencascade.org (BRepMesh_IncrementalMesh, Parallelizing BOPs), docs.python.org / codspeed.io (free-threading).

## 7. Nicht vollständig prüfbar (Container)

- Outlook per COM und Windows-Build: kein Windows.
- OpenGL-3D: keine GPU, nur Software-Weg gemessen.
- Echte Kunden-STEPs: nur 7 Test-STEPs im Repository. Die STEP-Benchmark-Suite (#621) braucht Patricks Prüfordner.
- Abgleich mehrerer PCs über einen echten Netzwerkordner, PPEASE-Ablage, lokale KI-Modelle.
- Bedienbarkeit der Oberfläche von Hand: nur Abläufe und Zeiten automatisch.

## 8. Empfehlungen

- E-1 (G-09): erledigt in 0.9.514 (test_tempo prüft die Speicherzeile nicht mehr mit fester Schwelle).
- E-2 (G-05): Teilung der Dreiecke je Modell zwischenspeichern. Bei orthogonaler Ansicht ist sie drehunabhängig, bildgleich nur bis auf Gleitkomma-Reihenfolge, deshalb erst mit Bildvergleich. Alternativ beim Drehen gröber teilen und erst im Stillstand fein.
- E-3 (G-06): erledigt in 0.9.514.
- E-4 (G-08): Positionsnummer innerhalb der Transaktion vergeben, sobald mehrere Schreiber je Datenbank denkbar sind.
