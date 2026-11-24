# STEP Import Engine 2.0 – Bestandsanalyse, Umsetzung, Messwerte (24.11.2026)

Auftrag Patrick 24.11.2026 17:00 UTC („STEP IMPORT ENGINE 2.0 – CAD-Kern erweitern, Berechnungen beschleunigen und
eigenen STEP-Viewer entwickeln“). Regeln: kein zweiter Kern, keine Ersatzberechnungen, keine simulierten Geometrien,
keine künstlichen Leistungsanzeigen, Kalkulationswerte nur mit Validierung ändern (Projektregel: nur bitgleich).

## 1. Bestandsanalyse

| Bereich | Stand vor diesem Auftrag | Ort |
|---|---|---|
| Bibliothek / Kern | OpenCascade (OCP 8.0.1.1) in einem eigenen Messprozess (STEP-Import.exe), Hauptprogramm ohne OCC | `programm/step_messung/` |
| Formate | STEP AP203/AP214/AP242 (OCCT STEPControl), IGES, TUBX, BLM ArTube (#634); Einheiten werden von OCCT in mm umgerechnet | `step_messen.py`, `step_blm.py` |
| Baugruppen | XCAF-Struktur, Kopien/Instanzen, Unterbaugruppen, Satz nie automatisch | `step_struktur`, `step.struktur_anhaengen` |
| Fehlerhafte Dateien | Prozessaufsicht mit Zeitlimit je Körper, ShapeFix, Fehler je Körper statt Abbruch | `step_messen.py --zeitlimit` |
| Rohrerkennung | Rund/Vierkant/Rechteck/Oval/Sonderprofile, offene Profile (U/C/L/T/Z, Flachstahl), Wand, Länge, Enden/Gehrung/Schräg, Bohrungen, Langlöcher, Ausschnitte, Gravuren, Senkung/Fließloch/Gewinde | `step_geometrie.py` |
| Normteile | Name/Metadaten vorab (N1), Geometrie (Kugel/Sechskant/Mutter), Lernen (N6), aus dem Schneidweg ausgeschlossen | `zukaufteile.py`, `step_drehfraes.normteil` |
| Tempo | Zwischenspeicher je Datei+Einstellungen, Parallelmessung (`--prozesse`), Kopien nur einmal messen, Boolean einmal (#612), Schwenk-Projektor (#616) | `step_messen.py`, `parallel.py` |
| 3D-Ansicht | Ansicht3D (QPainter/GL) mit Blick, 13 Darstellungen, Perspektive/Ortho, Messen, Auswahl Körper/Fläche/Kante/Punkt, Schnitt, Explosion | `ansicht3d.py` |
| Messen | Messkern M1–M3 (Abstand, Winkel, Ø, Radius, Wand, Teil messen) | `mess_kern.py` |
| Analysestufen | Standard (Import); Schnellmodus wird im Thread „Schnellimport“ gebaut | – |

**Lücken (Grundlage dieses Auftrags):**

1. Kein eigenständiger Viewer – eine STEP-Datei ließ sich nur über den Import in ein Angebot ansehen.
2. Keine Zuordnung 3D-Linie → Kontur: man sah Linien, aber nicht, welche Kontur mit welcher Schnittlänge dahinter steht.
3. Kein Konturpanel mit Berechnungswerten, keine Gegenprobe Schneidweg ↔ 3D.
4. Keine Expertenstufe (feineres Netz für genaues Messen/Ansehen).
5. Keine gemessenen Ladezeiten des Viewers (Zeit bis zum ersten 3D-Bild, Netz laden, Zeichnen).
6. Erkennung im Viewer nicht korrigierbar (nur im Prüfdialog beim Import).

## 2. Architektur

```
STEP-Datei ──► step_messen.py (eigener Prozess, OCCT)          ← EIN Kern, unverändert in den Messwerten
                 ├─ messwerte.txt / ergebnis.json  ───────────► Position (Kalkulation) übernimmt schneidweg, konturen …
                 └─ netze/*.json  {p,t,l,tf,fk,lage, lk NEU}
                                       │
rohrlaser/step_viewer.py (ohne Qt) ◄───┘  Kopf, Messung, Erkennung, Konturzeilen, Gegenprobe, Summen, Leistung
rohrlaser/step_viewer_fenster.py (Qt)     Fenster: Baum, Ansicht3DMitKnoepfen, Reiter Erkennung/Konturen/Datei/Leistung
```

* **Viewer und Kalkulation getrennt:** Der Viewer liest nur Messwerte; er rechnet keinen Schneidweg nach und ändert kein
  Angebot. „Ins Angebot übernehmen“ ruft den normalen Import auf (Messung kommt aus dem Zwischenspeicher).
* **Konturnummer je Linie (`lk`):** `step_geometrie.linien_kennung` merkt sich beim Aufbau der Konturliste, welche
  OCCT-Kanten zu welcher Kontur gehören (`_KonturListe`), `dreiecksnetz` schreibt je Linienzug die Nummer, und
  `step_messen.kontur_kennung` rechnet sie auf die endgültige (nach Gravurkörpern umsortierte) Liste um. Neues Feld,
  bestehende Felder unverändert; `li` (Kennung für Anklicken) entsteht nur in der Viewer-Kopie, damit Schneidfolge,
  Kostentreiber und Teile-Editor unberührt bleiben.
* **Expertenstufe:** `--netze-fein` (einst `netz_fein`) – Netzabweichung ¼, Winkel 0,2 rad. Nur das Netz ändert sich.

## 3. Umgesetzt

* Eigener STEP-Viewer (Datei → STEP-Viewer, Strg+Umschalt+O; Werkzeugleiste; Rechtsklick Position → Im STEP-Viewer
  öffnen): Datei-Kopf sofort (Format AP203/AP214/AP242, Einheit, Baugruppen, Körper, Flächen, Normteile laut Name,
  Messzeit geschätzt), Bauteilbaum nach Rohr/Blech/Dreh-Fräs/Normteil/nicht messbar, 3D mit allen vorhandenen
  Werkzeugen, Erkennung je Teil, Konturliste mit Farben je Art, Klick auf Kontur (Liste oder 3D) zeigt Werte,
  Gesamtschneidweg und Einstiche, Art ändern (gemerkt für künftige Importe), Dunkel (CAD), Werte kopieren, Ziehen und
  Ablegen.
* Gegenprobe Schneidweg ↔ 3D-Linien: offene Profile halbe Kantenlänge (Wand beidseitig), Rundrohr-Bohrungen als
  2D-Schnitt (Sattelkurve zwischen π·Ø und 2D-Schnitt), Senkung/Fließloch/Gewinde nicht vergleichbar, Enden mit
  Innensteg (Schnitt durch den Steg zählt laut Messung), Bleche aus der Blechmessung (Außenkontur + Innenkonturen).

## 4. Qualitätssicherung

* **Messwerte bitgleich:** `werkzeuge/step_benchmark.py vergleich` 0.9.467 (main) gegen diesen Stand über alle 126
  Test-STEPs: **126 gleich, 0 anders, Toleranz 0** ([Bericht](../performance/step_engine_2_2411/benchmark_alt_neu.md)).
  Die Laufzeit-Summe 353,6 s → 337,0 s ist Messrauschen (an der Messung selbst wurde nichts beschleunigt).
* **Gegenprobe über alle Netze des Benchmarks:** 216 Körper (179 mit Konturnummern, Rest Bleche/Drehteile),
  **446 von 446** vergleichbaren Konturen passen, bei allen Körpern Summe der Konturen = Schneidweg der Messung.
* Test `tests/test_step_viewer.py` (echte Messung: K01, K03, K10, R06, B02, R08; Experte; Fenster).

## 5. Leistung des Viewers (gemessen, Testrechner Cloud, Linux)

| Datei | Messung gesamt | erstes 3D-Bild | Zeichnen |
|---|---:|---:|---:|
| K01 RE60×40×3 Konturen | 1,3–1,9 s (davon Prozessstart ≈ 1 s) | 1,6–1,9 s | 0,26–0,36 s |

Die Leistung-Seite im Viewer zeigt diese Werte je Datei (gemessen, nicht geschätzt): Kopf lesen, Messung (Einlesen,
Analyse, Abschluss), Netze laden, Modell aufbauen, Zeichnen, erstes Bild, Dreiecke.

## 6. Offen / nächste Schritte

* Schnellmodus „nur Linien“ baut der Thread Schnellimport (`--netze-linien`); beim Zusammenführen bleibt `lk` in
  derselben Linienschleife erhalten.
* Weitere Beschleunigung der Messung nur bitgleich (Vorschläge aus #616/#621: Lift Cart K32 Schnitte, Nahtkandidaten).
* Instancing gleicher Körper im Zeichnen (große Baugruppen).
