# Maschinendaten: LST und BPF

Stand 24.11.2026 (Master-Auftrag „Intelligente Maschinendaten-Analyse“). Die Angaben stammen aus den echten Dateien,
die Patrick bereitgestellt hat: fünf TRUMPF-LST (TruTops Tube) und eine BLM-BPF. Kundendaten sind nicht im Repository.
Was in diesen Dateien nicht vorkommt, ist hier auch nicht beschrieben. Es wird nichts erfunden.

Programm: `programm/rohrlaser/maschinendaten.py`. Jeder gelesene Wert wird als `[Wert, Einheit, Quelle, Deutung,
sicher]` gespeichert. `sicher = False` heißt, die Bedeutung ist aus den Beispielen geschlossen und nicht belegt. Fehlt ein
Wert, wird er nicht ergänzt. Er steht dann in `fehlend`. Felder, die gelesen, aber nicht gedeutet werden, stehen in
`unbekannt` und im Importprotokoll. Maschinenprogramme werden nur gelesen und nie verändert.

## LST (TRUMPF TruTops Tube)

### Aufbau

* Textdatei in cp1252. Abschnitte stehen zwischen `BEGIN_<Name>` und `ENDE_<Name>`.
* `MM`-Zeilen beschreiben die Spalten. Der Feldname steht in Spalte 8, die Einheit in Spalte 10.
* `DA`-Zeilen enthalten die Werte. Fortsetzungszeilen beginnen mit `*`.
* Der NC-Teil steht zwischen `BEGIN_PROGRAMM` und `ENDE_PROGRAMM`. Er enthält die Zyklen `TC_LASER_ON`,
  `TC_LASER_OFF`, `TC_POS` und `TC_TUBE_CHUCKMOVE`, außerdem Kommentare `;(Contour: n)` und Kreise `G02`/`G03` mit
  I/J.
* Auftragslisten in `FERTIGUNG_AUFTRAG_TMP` sind durch `BD` getrennt.

### Gelesene Abschnitte

| Abschnitt | Inhalt | Wird genutzt als |
|---|---|---|
| EINRICHTEPLAN_INFO | Maschine, Steuerung, CAM-Version, Bearbeiter, Datum, Programm, Maschinenzeit, Cutting length, Tafelgewicht | Kopf je Programm |
| TUBE_TECH | Werkstoff, Stangenlänge, Wand, Profilmaße, Metergewicht, Umfang, Achsgrenzen, Technologietabelle | Profil und Material |
| TUBE_CORNER | Ecken-Vorschub und Ecken-Abstand je Stufe | Information |
| TUBE_LOAD | Anschnitt am Stangenanfang | Materialverbrauch |
| TUBE_PART_TECH | je Teil: Länge, Bearbeitungslänge, Teileabstand, Zugaben, kleinste Kontur, Futterposition | Teil |
| TUBE_PART_TIMES | je Teil: Zeiten berechnet und gemessen für First Cut, Contour, Cut Off | Zeit je Teil |
| CONSUMPTION_TIMES | Verbrauchszeiten in Gruppen (siehe unten) | Laser an / Verfahren |
| TOPS_DATA | Wert 103 = TruTops-Zeit, Gruppe-1-Werte Schneidgas | Gegenkontrolle |
| FERTIGUNG_AUFTRAG_TMP | Auftrag, Artikel, Stückzahl | Zuordnung zur Position |

Die Abschnitte TUBE_PART_UNLOAD, TUBE_UNLOAD, TUBE_END_LEFT/RIGHT, GLOBAL_DATASET, LTT_CALLS, ANALYTICS_DATA und
TUBE_PART_VARIANTS sind bekannt, werden aber nicht ausgewertet. Unbekannte Abschnitte und Felder kommen ins
Importprotokoll.

### Zeiten

* **TUBE_PART_TIMES:** Für jedes Teil gibt es eine berechnete und eine gemessene Zeit. In allen fünf Beispielen ist
  die gemessene Zeit 0. Die Maschine hat sie also noch nicht zurückgeschrieben. Ein Messwert zählt nur, wenn er
  größer als 0 ist.
* **CONSUMPTION_TIMES Gruppe 1:** Schneidgas.
* **CONSUMPTION_TIMES Gruppe 2:** Zeiten je Laserleistung.
  * Zeilen mit 0 W sind Verfahren und Positionieren bei ausgeschaltetem Laser.
  * Zeilen mit einer Leistung über 0 sind „Laser an“ für diese Leistungsstufe.
  * Die Summe der Gruppe 2 ist gleich der berechneten Maschinenzeit. Beispiel P20: 12,68 s Laser an und 9,78 s
    Verfahren ergeben 22,45 s.
  * „Laser an“ wird nur gesetzt, wenn es eine Zeile mit Leistung über 0 gibt. Ältere Dateien ohne Leistungsangabe
    liefern deshalb keine reine Laserzeit.
* **Laserzeit:** Steht eine reine Laserzeit in den Daten, wird sie als Laserzeit genommen. Einstich, Positionieren
  und die übrigen Zuschläge werden wie bisher dazugerechnet (Patrick, 24.11.).

### Längen

* **Cutting length (EINRICHTEPLAN_INFO):** Weg der Maschinenachsen einschließlich der Anfahrten. Das ist nicht die
  reine Schnittlänge am Material.
* **Schnittlänge am Material:** Sie wird aus dem NC-Teil gerechnet (`schnittlaenge_material`, Import-Thread #634 ff.).
  Ist sie vorhanden, ist sie die Schnittlänge. Sonst wird Cutting length genommen und als „unsicher“ markiert.
* **Konturklassen groß, mittel, klein:** Liefert der Import die Längen und Anzahlen je Klasse, werden sie angezeigt
  und daraus gelernt (`produktion_zeitmodell.py`).

### NC-Ereignisse (nur gezählt, keine Geometrie)

| Ereignis | Erkannt an |
|---|---|
| Konturen | `;(Contour: n)`. Fehlen die Kommentare, wird nichts gezählt (Wert fehlt, nicht 0). |
| Einstiche | `TC_LASER_ON` |
| Positionierungen | `TC_POS` |
| Umspannen | `TC_TUBE_CHUCKMOVE` |
| Vollkreise | `G02`/`G03` nur mit I/J (Endpunkt = Startpunkt) |

### Abgeleitete Werte (Quelle „berechnet aus …“)

* Materialverbrauch je Teil = Bearbeitungslänge + Teileabstand.
* Teile je Stange = (Stangenlänge − Futterposition) ÷ Verbrauch. Unsicher, weil die Deutung der Futterposition nicht
  belegt ist.
* Ausnutzung in %. Unsicher.
* Mittlerer Vorschub = Maschinenweg ÷ Konturzeit.
* Rohgewicht = Metergewicht × Länge.

### Unsichere Deutungen

* Tafelgewicht ist vermutlich das Gewicht der Fertigteile (Rohgewicht minus Ausschnitte).
* Für Spanntechnik, Entladeart und Fasenschnitt-Version sind nur Codes vorhanden, deren Bedeutung nicht belegt ist.
* Metergewicht: Die Datei schreibt „kg“, gemeint ist kg/m. Die Einheit wird berichtigt.

## BPF (BLM ArTube)

### Aufbau

* zlib-komprimiertes XML. Es wird mit `step_blm.bpf_dokumente` gelesen.
* `Progetto` enthält:
  * `info_tubo` und `sezione`: Profil, Maße, Wand, Radius, Werkstoff.
  * `info_pezzo`: Länge und Volumen.
  * `geometrie` und `info_geo` je Kontur:
    * `tipogeo`: 1 = geschlossen, 2 = Trennschnitt, 3 = offen. Aus den Beispielen geschlossen, nicht belegt.
    * `dimensioni/l`: Länge.
    * `tipo_faccia = 2`: Anfahrweg.
    * `accensione`: Einstich.
  * `rapidi`: Eilgänge.
  * `nesting`: `AngIn` und `AngOut` (Gehrungswinkel an den Enden), `XCutMax`.

### Gelesene Werte

Gelesen werden Profil und Kopfdaten, Länge, Konturen gesamt und je Art, Schnittlänge, Anfahrweg, Vollkreise (aus den
Punkten erkannt), Einstiche (einmal je Kontur), Eilgänge, Gehrung an Anfang und Ende, Maschine, Werkstoff und die
Version.

### Grenzen

* **Die BPF enthält keine Zeiten.** In `fehlend` steht dann „Zeiten (die BPF enthält keine Zeiten)“.
* BPF-Teile ergänzen deshalb Geometrie und Abgleich, zählen aber nicht für das Zeitlernen. Ihre Qualität ist „Teilwerte
  fehlen“.
* Felder, die nicht in `BPF_BENUTZT` stehen, kommen als „unbekannt“ ins Importprotokoll.

## Lernen und Bewertung

* **Abgleich** (`produktion_abgleich.py`): 12 Werte, Kalkulation gegen Maschine. Jeder Wert ist als berechnet,
  geschätzt, ermittelt oder fehlt gekennzeichnet. Die Zeitabweichung wird in Ursachen zerlegt: Schnittlänge, Einstiche,
  Positionieren, Vorschub und Laserleistung, übrige Zeit.
* **Gegenprobe** (`lst_lernen.validieren`): Jedes Programm wird aus den übrigen gelernt. Ist ein Vorschlag damit nicht
  besser, kann er nur mit ausdrücklicher Bestätigung freigegeben werden. Ohne Freigabe ändert sich nichts. Jede
  Freigabe lässt sich zurücksetzen.
* **Zeitmodell je Konturklasse** (`produktion_zeitmodell.py`): Je Maschine, Werkstoff und Wandbereich wird gerechnet:
  Laser an ≈ groß × a + mittel × b + klein × c + Einstiche × e. Gelöst wird mit kleinsten Quadraten und Werten ≥ 0, ab 3
  Programmen, mit Gegenprobe. Das Modell ist nur ein Hinweis und ändert keine Schneiddaten.
* **Genauigkeit** (`produktion_genauigkeit.py`):
  * „sehr gut“ nur mit mindestens 10 gemessenen Teilen und höchstens 10 % Abweichung.
  * „gut“ mit mindestens 3 gemessenen Teilen und höchstens 20 % Abweichung.
  * Nur CAM-Zeiten ergeben höchstens „gering“.
  * Ohne Daten heißt es „keine Produktionsdaten“.
