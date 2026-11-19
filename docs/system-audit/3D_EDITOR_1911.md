# 3D-Editor modernisieren – Bericht und Testbericht (19.11.2026)

Auftrag von Patrick vom 19.11.2026: den 3D-Editor stabiler, schneller und bedienbar wie ein CAD-Werkzeug machen.
Vorgaben: Vorhandenes nicht neu bauen, nichts ohne Ersatz entfernen, keine doppelten Berechnungen,
bestehende Projekte unverändert lassen, modular arbeiten. Umgesetzt in PR #568 (Version 0.9.400, beim Merge main+1).

## 1. Analyse (Befunde)

Messung auf main 0.9.399 mit einem 6-m-QR40 und 120 Konturen: rund 1,1 s pro Änderung.

| Nr. | Befund | Ursache |
|---|---|---|
| A1 | Netz wird bei jeder Änderung ganz neu gerechnet | `rohr3d.netz_rechnen` ~0,5 s, dient auch dem STEP-Export |
| A2 | Netzprüfung doppelt | `netz_pruefen` lief in `setzen` und noch einmal in `Modell` (2 × 0,18 s) |
| A3 | Keine Wiederherstellung | Editorstand nur im Speicher; ein Absturz bedeutete Verlust |
| A4 | Seitenleisten nicht ein-/ausblendbar | festes Layout |
| A5 | Keine Statuszeile mit Koordinaten und Maßen | – |
| A6 | Rückgängig-Verlauf unsichtbar | QUndoStack ohne Anzeige, Schritte ohne Text |
| A7 | Kein Achsenkreuz, kein Raster | – |
| A8 | Werkzeuge nur im Menüband, nicht am 3D | – |
| A9 | Legende verdeckt das Teil | Legende immer an |
| A10 | Keine Mehrfachbearbeitung | Auswahl immer nur eine Kontur |
| A11 | Kein Abstand zwischen zwei Konturen | – |

## 2. Stabilisierung (PR 1)

- **Netzprüfung einmal und schnell (A2):** `ansicht3d._zahlen_ok` prüft Zahlenlisten in einem Durchgang (Typen, `isfinite(sum)`,
  Grenzen). `Modell(netz, geprueft=True)` überspringt die zweite Prüfung, wenn `setzen` schon geprüft hat. Ergebnis gleich, nur
  einmal gerechnet.
- **Wartezeit nach Dauer:** Der Editor misst, wie lange `aktualisieren` dauert, und wartet bei großen Teilen länger
  (150 bis 600 ms, 1,5 × Dauer). Tippen bleibt flüssig, die Rechnung läuft nicht bei jedem Tastendruck.
- **Automatische Wiederherstellung (A3), neues Modul `editor_wiederherstellung.py`:** Bei jedem neuen Rückgängig-Schritt wird der
  Stand atomar (.tmp, dann umbenennen) in den Ordner `Wiederherstellung` neben der lokalen Datenbank geschrieben. Normales
  Schließen löscht die Datei. Liegt beim Öffnen derselben Position eine Datei, zeigt der Editor eine Leiste mit
  „Wiederherstellen“ und „Verwerfen“. Wiederherstellen ist ein Rückgängig-Schritt. Dateien älter als 14 Tage oder unlesbare
  Dateien werden still gelöscht. Position und Datenbank werden dabei nie verändert.
- **A1 bewusst nicht umgebaut:** `rohr3d.netz_rechnen` erzeugt auch das Netz für den STEP-Export. Ein Umbau auf ein
  inkrementelles Netz würde die Grundregel „Konturen 100 % wie STEP“ berühren. Siehe offene Potenziale.

## 3. Oberfläche (PR 2), neues Modul `editor_arbeitsbereich.py`

- **Werkzeugleiste am 3D (A8):** Verschieben (V), Auswahl (S), Messen (M), Winkel (W), Maße weg, Schnitt (Q), Eckpunkte (E),
  Bohrung (B), Ausschnitt (R), Einpassen (F), Auf Auswahl (Z), Raster (G). Alle Knöpfe rufen die vorhandenen Funktionen auf.
- **Reiter links:** Merkmale (wie bisher), Verlauf (QUndoView mit lesbaren Schritten wie „Bohrung Ø 12 eingefügt“ oder
  „Zeile 1 geändert: d 10 → 12“), Ebenen (Schnittkörper einzeln ein/aus, „Legende im 3D zeigen“, „Alle einblenden“).
- **Seitenleisten (A4):** links und rechts einklappbar (Knöpfe in der Statuszeile, Strg+1 / Strg+2), Zustand je Editorart gemerkt.
- **Statuszeile (A5):** Schneidweg, Einstiche, Schneidzeit, Konturklassen, Mauskoordinaten auf dem Teil (Rohr: quer/hoch/längs),
  Auswahl, Modellmaße, Einheit, Prüfung.
- **Legende (A9):** standardmäßig aus, einschaltbar unter Ebenen.
- Gilt für Rohr- und Blech-Editor (gemeinsamer `EditorRahmen`).

## 4. Funktionen (PR 3)

- **Achsenkreuz und Raster (A7)** in allen 3D-Fenstern (auch Baugruppe und Satz, da in `ansicht3d`): Achsenkreuz unten links
  dreht mit, Raster unter dem Teil mit Schritten nach 1-2-5 (etwa Länge/20, jede 5. Linie kräftig). Ein/aus über das Ansicht-Menü
  oder Taste G, Einstellung bleibt gespeichert. Auch in der OpenGL-Darstellung geprüft.
- **Mehrfachbearbeitung (A10), neues Modul `editor_mehrfach.py`:** Im Baum mehrere Konturen mit Strg/Umschalt markieren. Rechts
  erscheinen gemeinsame Felder (Maße bei gleicher Konturart, Anzahl, Lage verschieben, Seite bzw. x/y beim Blech). Leere Felder
  bleiben unverändert. Jede Änderung ist genau ein Rückgängig-Schritt. Dazu Duplizieren, Spiegeln, Entfernen; Entf und Strg+D
  wirken auf alle markierten.
- **Abstand zweier Konturen (A11):** Bei zwei markierten Konturen zeigt die Tafel den Abstand längs Mitte–Mitte und Kante–Kante.

## 5. Behobene Fehler während der Arbeit

- Neue Farben ohne Dunkel-Fassung (test_dunkelmodus) → vorhandene, umgesetzte Farben verwendet.
- `stil.farbe_fest` lieferte QColor statt Text im Stylesheet → `stil.umsetzen` auf dem CSS-Text.
- Zahlen im Verlaufstext als „12,0“ → eigene Formatierung `_wert`.
- Spaltenerklärung lief beim Löschen mehrerer Zeilen auf None → Signale während des Löschens gesperrt.
- Vorhandene Instabilität (nicht neu): test_satz3d schlägt selten fehl und ist beim Wiederholen grün.

## 6. Tests

Neue Testdatei `tests/test_3d_editor_modern.py` (in `tests/alle.py` eingetragen). Sie deckt A1 bis A11 ab, unter anderem:

- Netzprüfung: gültige, beschädigte (NaN, zu groß, falscher Typ) und vorgeprüfte Netze; Ergebnis gleich wie vorher.
- Wartezeit wächst mit der gemessenen Dauer und bleibt zwischen 150 und 600 ms.
- Wiederherstellung: sichern, lesen, löschen, beschädigte Datei, fremde Fassung, zu alt; Leiste anbieten, wiederherstellen als
  ein Rückgängig-Schritt, verwerfen; normales Schließen löscht die Datei.
- Verlaufstexte, Ebenen ein/aus, Legende, Seitenleisten einklappen und merken, Statuszeile mit Mauskoordinaten.
- Raster-Schritt (1-2-5), Achsenkreuz, Raster/Achsen gemerkt.
- Mehrfachbearbeitung: gemeinsame Maße, Seite, Lage verschieben, Duplizieren, Spiegeln, Entfernen, je ein Rückgängig-Schritt;
  Abstand Mitte–Mitte und Kante–Kante.
- Blech-Editor auf kleinem Bildschirm (1366×728) bedienbar.

Lokal gelaufen: 57 betroffene Testdateien (Editor, 3D-Ansicht, OpenGL unter xvfb, Blech, Baugruppe, Satz, Dunkelmodus,
Anleitung) grün; test_satz3d einmal instabil wie bisher. Der vollständige Lauf erfolgt über den Check `tests` in GitHub.

## 7. Messwerte

6-m-QR40 mit 120 Konturen, reine Rechenzeit ohne Zeichnen:

| Vorgang | vorher | nachher |
|---|---|---|
| Eine Änderung | 461 ms | 377 ms |
| Rückgängig + Wiederholen | 1050 ms | 914 ms |
| 10 Konturen einfügen | 65 ms | 49 ms |
| Speicher nach 10× Öffnen/Schließen | +0,04 MB | +0,04 MB |

Spürbar schneller wirkt der Editor zusätzlich durch die angepasste Wartezeit: bei großen Teilen wird nicht mehr bei jedem
Tastendruck gerechnet.

## 8. Offene Potenziale

1. **Inkrementelles Netz:** Nur geänderte Konturen neu ausschneiden statt des ganzen Rohrs (~0,5 s). Braucht einen getrennten
   Netzweg für die Anzeige, damit der STEP-Export unverändert bleibt.
2. **Netz in einem Hintergrund-Thread** rechnen, damit die Oberfläche auch bei sehr großen Teilen nie stockt.
3. **Kontur im 3D ziehen mit Fang an anderen Konturen** (bisher Fang an Raster und Kanten).
4. **Mehrfachauswahl direkt im 3D** per Strg+Klick (bisher im Baum).
5. **Wiederherstellung auch für Baugruppe und Satz in 3D**, die eigene Fenster ohne `EditorRahmen` haben.
