# Kalkulation: Formeln und Parameter

Rechenweg der Rohrlaser-Kalkulation von Material bis Verkaufspreis, in der Reihenfolge, in der `rechnen.kalkulation`
rechnet. Alle Werte je Teil, wenn nicht anders angegeben. Ein leeres Feld rechnet nie mit einem erfundenen Wert: es
zählt 0, die Vorgabe der Einstellung oder es steht als „nicht berücksichtigt“ bzw. mit Hinweis im Status. Die
Parameter-Tabellen unten sind aus dem Programm erzeugt (`python docs/erzeuge_formeln.py`).

## 1 Material

- Stangenpreis = Preis × Bezug: €/kg × kg/m × Stangenlänge, €/m × Stangenlänge oder Tonnenpreis des Werkstoffs;
  Händler-Mehrlänge, Teuerung und Oberflächen-Aufpreis kommen dazu (Stammdaten Preise, Werkstoffe, Oberflächen).
- Material je Teil = Kosten der Stangen der Gruppe × Längenanteil des Teils (Teil + Trennung) an der Belegung.
- Schrotterlös = − Verschnitt [mm] × Preis je mm × Schrottanteil (Einstellung, leer = 0).
- Ausschuss Material = Material × a ÷ (1 − a), a = Ausschuss (Einstellung; „im Hundert“).
- Lagerzins (nur Abruf-Angebot mit Jahresbedarf) = Material × Zins × Lagerdauer.

## 2 Laserzeit je Teil

```
Zeit groß    = 60 × Schneidweg groß / Vorschub groß            [s]
Zeit mittel  = 60 × Schneidweg mittel / Vorschub mittel
Zeit klein   = 60 × Schneidweg klein / Vorschub klein
Gravur       = 60 × Gravurlänge / Vorschub Gravur
Einstiche    = Einstiche × Einstechzeit
Anfahren     = Einstiche × Zeit je Kontur   (mit Maschinendynamik stattdessen Leerwege aus dynamik.py)
+ Ecken, Mehrzeit 3D, Anschlag doppelt, Anfahrweg, Abfall zerteilen, Drehen je Seitenwechsel, Messzyklen,
  Nebenzeit je Teil, Entnahme von Hand (je nur, wenn das Feld gesetzt ist)
Laserzeit brutto = Σ aller Anteile
Laserzeit netto  = max(0, brutto − Einsparung gemeinsamer Schnitte) + Zusatzzeiten (s/Stück) + Prüfzeit Anbauteile
```

- Konturklasse einer Innenkontur nach dem Hüllmaß: klein bis / mittel bis der Maschine (Vorgabe 3 × und 8 × Wand).
- Einsparung gemeinsamer Schnitt: nur zwei benachbarte gerade Enden; je gespartes Ende Schnittlänge / Vorschub +
  Einstiche × (Einstechzeit + Zeit je Kontur).
- Schneidzeit von Hand ersetzt brutto (Zusatz- und Prüfzeit kommen dazu).
- Zeitbild (Plan X2) gliedert dieselbe Zeit in 1 Laserbearbeitung, 2 Einstich, 3 Positionieren, 4 Bewegung,
  5 Nebenzeit (1–5 = netto), 6 Rüsten, 7 Maschinenbelegung (= 1–6). Die Bearbeitungsliste (X1) zeigt sie je Ende und
  Kontur, Summe = brutto, Rest als „Abgleich“.

## 3 Laser schneiden und Gas

- Laser schneiden = Laserzeit netto / 3600 × Stundensatz Laser (Maschine bzw. Zeitbasis des Angebots).
- Schneidgas = Gaszeit / 3600 × €/h bzw. m³/h × €/m³ (Gaszeit ohne Anfahren, Nebenzeit, Drehen, Messen, Entnahme).
- Gewinde, Senken, Flowdrill, Bohren: nur € je Stück (Stammdaten Gewinde bzw. Zusatzarbeiten), keine Zeit.

## 4 Rüsten

- Rüsten Maschine = Rüstzeit der Maschine / 60 × Satz, auf alle Teile des Laufs umgelegt (Muster: eigener Lauf).
- Rüsten je Abmessung = Rüstzeit je Abmessung / 60 × Satz (+ Sonderprofil, weitere Profilform), auf die Teile der
  Abmessung.
- Stangenwechsel = Beladungen × Zeit je Stange / 3600 × Satz, nach Längenanteil auf die Teile der Gruppe.

## 5 Zusätzliche Bearbeitung

- Weitere Arbeitsschritte = (Rüstzeit je Bezug + Zeit je Einheit × Menge) × Stundensatz bzw. Festpreis.
- Zusatzarbeit je Teil = Preis je Einheit × Menge (€/kg Gewicht, €/m² Fläche, €/m Länge, €/Stück, €/h Sekunden /
  3600 × Satz), mindestens Mindestbetrag je Teil; Mindestbetrag je Angebot anteilig angehoben; €/Angebot einmal
  umgelegt. Preis je Einheit = Festpreis + Zeit × Satz + Material × (1 + Zuschlag) + weiterer Zuschlag.
- Rüstzeit je Los (X5) = Rüstzeit [min] / 60 × Stundensatz der Zusatzarbeit, einmal je Angebot, Position oder
  Abmessung, auf deren Teile umgelegt; jede Staffel ist ein eigenes Los. Nicht bei Gewinde/Senken/Flowdrill/Bohren.
- Qualität (X4) je Position und Los = (M × t_Merkmal × n_Prüf + 60 × (t_Erstmuster + t_Protokoll)) / 3600 × S_QS;
  M = Merkmale des Prüfplans, n_Prüf = alle, ⌈Stück / n⌉ oder min(n, Stück).
- Handling Kundenmaterial = €/m × Stangenlänge des beigestellten Materials.

## 6 Herstellkosten, Selbstkosten, Gewinn, Preis

```
Herstell = (Material − Schrott + Ausschuss Material + Lagerzins) × (1 + Zuschlag Material)
         + (Laser + Gas + Gewinde + Ausschuss Fertigung + Rüsten + Arbeitsschritte + Zusatzarbeiten eigen
            + Handling + Qualität) × (1 + Zuschlag Fertigung)
         + Fremdleistungen × (1 + Zuschlag Fremdleistung)
Selbst   = Herstell + Programmierung + Pauschale je Abmessung + Angebotsaufschlag + Zukaufteile (Einstand + Aufschlag)
Gewinn   = Gewinnsatz × (Selbst − Zukaufteile)           (kein Gewinn auf Zukauf und Bleche, nur deren Aufschlag)
           Gewinn auf Material mit eigenem Satz, wenn gesetzt; gestaffelter Gewinn nach dem Wert
Preis    = (Selbst + Gewinn + Fracht) / (1 − Skonto)
```

- Danach: Musterteile auf die Serie umgelegt, Mindestpreis je Angebot (alle Preise im gleichen Verhältnis),
  Angebotsregeln, Rabatt, Rundung (zentral, Einstellung), Mannlose Laufzeit, Neuteil, Verpackung, Finanzierung.
- Staffeln rechnen jede Menge als eigenen Lauf (neu optimiert) mit denselben Bausteinen; ohne Werte in der Stufe
  ist der Staffelpreis gleich dem Verkaufspreis der Kalkulation (Test test_staffelpreise).

## 7 Rundung

- Gerechnet wird ohne Zwischenrundung; gerundet werden Preise je Teil im Angebot (Einstellung Rundung) und die Anzeige
  (Nachkommastellen der Felder). Summen im Angebot = Σ gerundeter Preis je Teil × Stück.

## Änderungsprotokoll

| Paket | Datum | Änderung |
|---|---|---|
| X7 | 12.11.2026 | 12 Referenzaufträge von Hand nachgerechnet (tests/test_referenz_kalkulation.py) |
| X2 | 12.11.2026 | Zeitbild in 7 Zeitarten, keine Zahl geändert |
| X1 | 12.11.2026 | Bearbeitungsliste je Ende und Kontur, Summe = Laserzeit brutto |
| X5 | 12.11.2026 | Zusatzarbeiten: Rüstzeit je Los, Zeitart Personal/Maschine (Schema 84) |
| X4 | 12.11.2026 | Kostenart Qualität aus dem Prüfplan, Tabelle Qualitätsstufen (Schema 84) |
| X3 | 12.11.2026 | Schachtelvergleich (nur Anzeige) |
| X6 | 12.11.2026 | Reiter Optimierung, Übernehmen als neue Fassung |
| X8 | 12.11.2026 | diese Datei |

## Parameter: Einstellungen

Art „anteil“ wird in % eingegeben. Leer = siehe Vorgabe bzw. der Hinweis im Titel.

### Kalkulation

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `zuschlag_material` | Zuschlag Material | anteil | 0 % | 0 … 5 |
| `zuschlag_fertigung` | Zuschlag Fertigung | anteil | 0 % | 0 … 5 |
| `zuschlag_fremdleistung` | Zuschlag Fremdleistung | anteil | 10 % | 0 … 5 |
| `aufschlag_blech` | Aufschlag Bleche im Angebot | anteil | 10 % | 0 … 10 |
| `aufschlag_zukauf` | Aufschlag Zukaufteile im Angebot | anteil | 10 % | 0 … 10 |
| `gewinn` | Gewinn | anteil | 10 % | 0 … 5 |
| `zukauf_aufschlag` | Standardaufschlag Zukaufteile [% auf Einstand] (leer = keiner) | zahl_leer | leer | 0 … 1000 |
| `ruesten_abmessung` | Rüstzeit je Abmessung [min] | zahl | 15.0 | 0 … 1440 |
| `ruesten_abmessung_eur` | Rüsten je Abmessung als Betrag [€] (leer = Minuten) | zahl_leer | leer | 0 … 100000 |
| `ruesten_angebot_eur` | Rüsten je Angebot als Betrag [€] (leer = Minuten der Maschine) | zahl_leer | leer | 0 … 100000 |
| `pauschale_abmessung` | Pauschale je Abmessung [€] | zahl | 0.0 | 0 … 100000 |
| `programmierung_zeit` | Programmierzeit je Position [min] | zahl | 5.0 | 0 … 1440 |
| `programmierung_kontur` | Programmierzeit je Innenkontur [min] | zahl | 0.5 | 0 … 1440 |
| `angebotsaufschlag` | Angebotsaufschlag je Angebot [€] | zahl | 50.0 | 0 … 100000 |
| `gewinn_material` | Gewinn auf Material [%] (leer = wie Gewinn) | zahl_leer | leer | 0 … 500 |
| `ruesten_abmessung_wand` | Rüstzeit je Abmessung, nur Wand anders [min] (leer = volle Rüstzeit) | zahl_leer | leer | 0 … 1440 |
| `programmierung_wiederholteil` | Programmierzeit Wiederholteil mit Programm [min] (leer = volle Zeit) | zahl_leer | 1.0 | 0 … 1440 |
| `programmierung_gleich` | Gleiches Teil in mehreren Positionen nur einmal programmieren | auswahl | ja |  |
| `pruefzeit_anbau` | Prüfzeit je Teil mit unsicher erkannten Anbauteilen [min] | zahl | 0.0 | 0 … 1000 |
| `ausschuss` | Ausschuss Rohrlaserteile [%] | anteil | 0 % | 0 … 0.5 |
| `schrott_anteil` | Schrotterlös Verschnitt [%] | anteil | 0 % | 0 … 1 |
| `preiseinheit_ab` | Preis je 100 Stück unter [€] | zahl | 0.0 | 0 … 100 |
| `gewinn_bis_1` | Gewinn gestaffelt: Grenze 1 bis Auftragswert [€] | zahl | 0.0 | 0 … 1e+07 |
| `gewinn_satz_1` | Gewinn gestaffelt: Satz 1 bis Grenze 1 | anteil | 0 % | 0 … 5 |
| `gewinn_bis_2` | Gewinn gestaffelt: Grenze 2 bis Auftragswert [€] | zahl | 0.0 | 0 … 1e+07 |
| `gewinn_satz_2` | Gewinn gestaffelt: Satz 2 bis Grenze 2 | anteil | 0 % | 0 … 5 |
| `gewinn_bis_3` | Gewinn gestaffelt: Grenze 3 bis Auftragswert [€] | zahl | 0.0 | 0 … 1e+07 |
| `gewinn_satz_3` | Gewinn gestaffelt: Satz 3 bis Grenze 3 | anteil | 0 % | 0 … 5 |
| `gewinn_bis_4` | Gewinn gestaffelt: Grenze 4 bis Auftragswert [€] | zahl | 0.0 | 0 … 1e+07 |
| `gewinn_satz_4` | Gewinn gestaffelt: Satz 4 bis Grenze 4 | anteil | 0 % | 0 … 5 |
| `gewinn_satz_5` | Gewinn gestaffelt: Satz über der letzten Grenze | anteil | 0 % | 0 … 5 |
| `gas_rechnen` | Schneidgas rechnen (nein = für alle Maschinen aus) | auswahl | ja |  |
| `gaspreis_n2` | Gaspreis N₂ [€/m³] | zahl | 0.0 | 0 … 100 |
| `gaspreis_o2` | Gaspreis O₂ [€/m³] | zahl | 0.0 | 0 … 100 |
| `druckluft` | Schneiden mit Druckluft (Schneiddaten mit Gas Druckluft vor N₂) | auswahl | nein |  |
| `gaspreis_luft` | Gaspreis Druckluft [€/m³] | zahl | 0.0 | 0 … 100 |
| `gas_faktor` | Korrekturfaktor Gasverbrauch | zahl | 1.0 | 0.1 … 5 |
| `co2_strom` | CO₂-Bilanz: Strommix [kg CO₂ je kWh] | zahl | 0.38 | 0 … 2 |
| `co2_kw` | CO₂-Bilanz: Leistung der Maschine, wenn dort keine steht [kW] | zahl | 20.0 | 0 … 500 |
| `strompreis` | Stundensatz-Ermittlung: Strompreis [€/kWh] | zahl | 0.25 | 0 … 10 |
| `raumkosten` | Stundensatz-Ermittlung: Raumkosten [€/m² im Monat] | zahl | 8.0 | 0 … 1000 |
| `zinssatz` | Stundensatz-Ermittlung: Zinssatz [%] | anteil | 6 % | 0 … 0.5 |
| `bediener_satz` | Stundensatz-Ermittlung: Bedienerlohn [€/h] | zahl | 38.0 | 0 … 1000 |
| `gemeinkosten` | Stundensatz-Ermittlung: Gemeinkosten [%] | anteil | 25 % | 0 … 5 |
| `arbeitstage` | Stundensatz-Ermittlung: Arbeitstage je Jahr | zahl | 220.0 | 0 … 366 |
| `auslastung_jahr` | Stundensatz-Ermittlung: Auslastung [%] | anteil | 75 % | 0 … 1 |
| `handling_beistellung` | Handling Kundenmaterial je m Stangenlänge [€/m] (0 = keins) | zahl | 0.0 | 0 … 1000 |
| `abruf_lagerzins` | Abruf-Angebot: Lagerzins bei bevorratetem Material [% p. a.] | zahl | 8.0 | 0 … 100 |
| `abruf_laufzeit` | Abruf-Angebot: Laufzeit und Preisbindung [Monate] | ganz | 12 | 1 … 120 |
| `mindestpreis` | Mindestpreis je Angebot netto, Ware ohne Fracht nach Skonto [€] (0 = keiner) | zahl | 200.0 | 0 … 1e+06 |
| `eil_tage` | Eilzuschlag: Stufe 1 bis so viele Arbeitstage zu früh | ganz | 2 | 1 … 60 |
| `eil_zuschlag_1` | Eilzuschlag Stufe 1 (auf die Fertigung) | anteil | 15 % | 0 … 5 |
| `eil_zuschlag_2` | Eilzuschlag Stufe 2 (mehr Arbeitstage zu früh) | anteil | 30 % | 0 … 5 |
| `finanz_zins` | Finanzierung: Kalkulationszins p. a. (0 = aus) | anteil | 0 % | 0 … 1 |
| `runden_stueck` | Runden: Stückpreis aufwärts auf [€] (0 = aus) | zahl | 0 | 0 … 1000 |
| `runden_gesamt` | Runden: Gesamtpreis aufwärts auf [€] (0 = aus, nur ohne Stückrundung) | zahl | 0 | 0 … 100000 |
| `untergrenze_variabel` | Preisuntergrenze: variabler Anteil der Laserkosten (Strom, Gas, Verschleiß) | anteil | 30 % | 0 … 1 |
| `neuteil_zuschlag` | Neuteil-Zuschlag auf Material und Laser (0 = aus) | anteil | 0 % | 0 … 2 |
| `freigabe_ab` | Vier-Augen-Freigabe ab Netto [€] (0 = aus) | zahl | 0 | 0 … 1e+08 |
| `auftrag_skript` | Schnittstelle beim Beauftragen: Programm oder Skript (leer = aus) | text | leer |  |
| `freigabe_marge` | Vier-Augen-Freigabe unter Marge (0 = aus) | anteil | 0 % | 0 … 1 |
| `auslastung_hoch` | Gewinn nach Auslastung: Hinweis „voll“ ab Belegung | anteil | 90 % | 0 … 5 |
| `auslastung_niedrig` | Gewinn nach Auslastung: Hinweis „Spielraum“ unter Belegung | anteil | 50 % | 0 … 5 |

### Lieferlängen

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `laenge_vergleich` | Lieferlängen: beim Optimieren andere Lieferlängen vergleichen (z. B. 12 m) | auswahl | nein |  |
| `laenge_mindest_eur` | Lieferlängen: Mindestersparnis je Gruppe in € | zahl | 20.0 | 0 … 100000 |
| `laenge_mindest_anteil` | Lieferlängen: Mindestersparnis je Gruppe in % | anteil | 3 % | 0 … 1 |
| `muster_mehrverschnitt` | Schnittplan: weniger verschiedene Belegungen bis Mehrverschnitt [%] (0 = aus) | anteil | 0 % | 0 … 0.2 |
| `laenge_auto_huellkreis` | Lieferlängen: ohne Eintrag lieferbar ab Hüllkreis-Ø [mm] (0 = aus) | zahl | 70.0 | 0 … 2000 |
| `laenge_auto` | Lieferlängen: Länge für Profile ab diesem Hüllkreis-Ø [mm] | ganz | 12000 | 500 … 30000 |
| `zuschnitt_verlust` | Lieferlängen: Schnittverlust je Zuschnitt beim Lieferanten [mm] | zahl | 3.0 | 0 … 50 |
| `zuschnitt_puffer` | Lieferlängen: Puffer je zugeschnittener Stange [mm] | ganz | 50 | 0 … 1000 |
| `haendler_mehr_kurz` | Materialpreis: Mehrlänge je Stange, die der Händler berechnet, bis zur Grenze (z. B. 6 m) [mm] | ganz | 50 | 0 … 1000 |
| `haendler_mehr_lang` | Materialpreis: Mehrlänge je Stange über der Grenze (z. B. 12 m) [mm] | ganz | 100 | 0 … 1000 |
| `haendler_mehr_grenze` | Materialpreis: Grenze kurze/lange Stange [mm] | ganz | 6500 | 0 … 30000 |
| `zuschnitt_kosten` | Lieferlängen: Kosten je Zuschnitt beim Lieferanten [€] | zahl | 0.0 | 0 … 10000 |

### Lager und Fertigung

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `lager_aktiv` | Materialbestand verwenden (Reiter Lager) | auswahl | nein |  |
| `fuellteile` | Füllteile auf Lager (je Zeile Artikel; Profil-ID; Werkstoff-ID; Länge; höchstens Stück) | mehrzeilig | leer |  |
| `reste_aktiv` | Reststücke verwalten (lagern und wieder einplanen) | auswahl | nein |  |
| `rest_min_laenge` | Reststücke: kürzester Rest, der ins Lager kommt [mm] | zahl | 500.0 | 0 … 20000 |
| `restwert_anteil` | Reststücke und Lagerstangen: Wert in Prozent des Materialpreises | anteil | 100 % | 0 … 1 |
| `fertigung_aktiv` | Reiter Fertigung verwenden (Status beauftragter Angebote) | auswahl | ja |  |
| `fertigung_status` | Fertigungsstatus (je Zeile ein Status, in dieser Reihenfolge) | mehrzeilig | Freigegeben
Arbeitsvorbereitung
Material bereit
In Fertigung
Fremdvergabe
Qualitätsprüfung
Fertig gemeldet |  |
| `etikett_format` | Etiketten: Format | auswahl | A4, 3 × 8 Etiketten (70 × 37 mm) |  |
| `rueckmeldung_schritte` | Rückmeldung per Scan: Arbeitsschritte (eine Zeile je Schritt, der letzte = fertig) | mehrzeilig | Geschnitten
Entgratet
Verpackt |  |
| `reklamation_fehlerarten` | Reklamationen: Fehlerarten (eine Zeile je Fehlerart) | mehrzeilig | Maß außerhalb der Toleranz
Kontur fehlt oder falsch
Grat oder Schlacke
Oberfläche, Kratzer, Anlauffarben
Falscher Werkstoff oder falsches Profil
Falsche Menge
Transportschaden
Sonstiges |  |
| `schicht_stunden` | Auslastung: Stunden je Arbeitstag und Maschine (Maschine leer = dieser Wert) | zahl | 8.0 | 0 … 24 |
| `schicht_samstag` | Auslastung: Stunden am Samstag | zahl | 0.0 | 0 … 24 |
| `schicht_verfuegbar` | Auslastung: nutzbarer Anteil der Schichtzeit (Wartung, Störungen) | anteil | 85 % | 0.1 … 1 |
| `betriebsruhe` | Auslastung: Betriebsruhe (Tage und Zeiträume, z. B. 24.12.2026-31.12.2026; 02.10.2026) | text | leer |  |
| `termin_material_tage` | Termin nach Auslastung: Material-Lieferzeit [Arbeitstage] (0 = vorrätig) | ganz | 3 | 0 … 120 |
| `pruef_toleranz` | Prüfplan: Toleranzen | auswahl | ISO 2768-m |  |
| `erstmuster_preis` | Prüfplan: Preis Erstmusterprüfung je Angebot [€] (0 = nicht anbieten) | zahl | 85.0 | 0 … 100000 |
| `auslastung_vorlauf` | Auslastung: Laserzeit so viele Arbeitstage vor dem Liefertermin | ganz | 2 | 0 … 60 |
| `auslastung_austausch` | Rohrlaser Auslastung: Aufträge automatisch übergeben und Rückmeldung lesen | auswahl | ja |  |
| `auslastung_ordner` | Rohrlaser Auslastung: gemeinsamer Ordner (leer = Unterordner 'Auslastung') | ordner | leer |  |
| `termin_aus_auslastung` | Liefertermin-Vorschlag nach dem Plan der Rohrlaser Auslastung (Rückmeldung höchstens 3 Tage alt) | auswahl | ja |  |

### Schweißbaugruppen

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `schweiss_a_regel` | Schweißbaugruppen: a-Maß-Regel, a = Faktor × kleinere Wanddicke (Vorschlag) | zahl | 0.7 | 0.1 … 2 |
| `schweiss_a_min` | Schweißbaugruppen: a-Maß-Regel mindestens [mm] (EN 1993-1-8: 3 mm, höchstens die dünnere Wand; 0 = aus) | zahl | 3.0 | 0 … 10 |
| `schweiss_spalt_max` | Schweißbaugruppen: Warnung, wenn der Spalt einer Naht größer ist als [mm] | zahl | 2.0 | 0 … 10 |
| `schweiss_vk_satz` | Schweißbaugruppen: Stundensatz für Rüsten, Positionieren und Wenden | auswahl | Schweißen |  |
| `schweiss_vk_satz_nacharbeit` | Schweißbaugruppen: Stundensatz für Verputzen und Schleifen | auswahl | Schweißen |  |
| `schweiss_vk_step` | Schweißbaugruppen: Vorkalkulation automatisch (Vorgabe je Baugruppe, auch beim STEP-Import: Nahtvorschläge, a-Maß nach Regel, Schweißen, Heften, Positionieren, Wenden, Verputzen, Rüsten) | auswahl | ja |  |
| `gravur_artikel` | Gravur: Artikelnummer auf Bleche und Rohre einer Schweißbaugruppe gravieren (Vorgabe des Häkchens im Baugruppen-Editor) | auswahl | nein |  |
| `gravur_schrifthoehe` | Gravur: Schrifthöhe der Artikelnummer [mm] | zahl | 10.0 | 1 … 200 |

### Frachtkosten

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `absender_plz` | Absender-PLZ (Versandort) | text | leer |  |
| `absender_land` | Absender-Land | text | DE |  |
| `fracht_versandart` | Versandart für automatische Fracht | text | leer |  |
| `fracht_umwegfaktor` | Umwegfaktor Straße zu Luftlinie (Entfernung nach PLZ) | zahl | 1.25 | 1 … 2 |
| `frachtzeit_inland` | Frachtlaufzeit Inland bis frei Haus [Arbeitstage] | ganz | 1 | 0 … 60 |
| `frachtzeit_ausland` | Frachtlaufzeit Ausland bis frei Haus [Arbeitstage] | ganz | 3 | 0 … 60 |
| `fracht_lht_standard` | Ladungsträger im Packvorschlag | auswahl | EUR |  |
| `fracht_lht_langgut` | Ladungsträger für lange Teile (Langgut) | auswahl | LG |  |

### Blech-Richtpreis

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `blech_stundensatz` | Stundensatz Blechlaser [€/h] | zahl | 120.0 | 0 … 10000 |
| `blech_ruesten` | Rüsten und Programmieren Blechlaser je Auftrag [€] | zahl | 30.0 | 0 … 100000 |
| `blech_verschnitt` | Verschnitt Tafel (auf das Hüllrechteck) | anteil | 15 % | 0 … 5 |
| `blech_material` | Material: Tafelausnutzung oder pauschaler Verschnitt | auswahl | Tafelausnutzung |  |
| `blech_tafeln` | Tafelformate: Länge × Breite in mm, mit ; getrennt (Beispiel, bitte anpassen) | text | 3000 × 1500; 2500 × 1250 |  |
| `blech_tafel_rand` | Tafel: Randabstand [mm] | zahl | 10.0 | 0 … 200 |
| `blech_tafel_steg` | Tafel: Steg zwischen den Teilen [mm] | zahl | 5.0 | 0 … 100 |
| `blech_kantung` | Kanten: Preis je Kantung [€] | zahl | 1.2 | 0 … 10000 |
| `blech_ruesten_kanten` | Kanten: Rüsten je Auftrag [€] | zahl | 25.0 | 0 … 100000 |
| `blech_aufschlag` | Aufschlag des Lieferanten (Gewinn) | anteil | 15 % | 0 … 5 |
| `blech_kant_v` | Kantbarkeit: V-Öffnung = Faktor × Blechdicke | zahl | 8.0 | 0 … 50 |
| `blech_kant_schenkel` | Kantbarkeit: kleinstes Schenkel-Außenmaß = Faktor × V-Öffnung | zahl | 0.7 | 0 … 5 |
| `blech_kant_loch` | Kantbarkeit: Abstand Innenkontur–Biegelinie mindestens Innenradius + Faktor × Dicke | zahl | 2.0 | 0 … 20 |
| `blech_kant_radius` | Kantbarkeit: kleinster Innenradius = Faktor × Dicke | zahl | 0.5 | 0 … 20 |
| `blech_abwicklung` | Abwicklung: K-Faktor aus (K-Faktor-Tabelle, je Werkstoff oder nach Formel) | auswahl | K-Faktor-Tabelle |  |
| `blech_gesenke` | Kantbarkeit: Gesenke (je Zeile V-Weite; kleinster Schenkel; max. t/m, z. B. 16; 11; 100) | mehrzeilig | leer |  |
| `blech_presse_t` | Kantbarkeit: Presskraft der Abkantpresse [t] (0 = keine Prüfung) | zahl | 0.0 | 0 … 10000 |
| `blech_presse_laenge` | Kantbarkeit: größte Biegelänge der Abkantpresse [mm] (0 = keine Prüfung) | zahl | 0.0 | 0 … 20000 |
| `blech_dxf_layer` | DXF: Layernamen (Außenkontur; Innenkontur; Biegelinie hoch; Biegelinie runter; Gravur; Beschriftung) | text | AUSSENKONTUR; INNENKONTUR; BIEGUNG_HOCH; BIEGUNG_RUNTER; GRAVUR; BESCHRIFTUNG |  |
| `blech_dxf_biegelinien` | DXF: Biegelinien ausgeben | auswahl | ja |  |
| `dxf_weg_layer` | DXF-Import: weitere Layer ohne Schnitt (Namen oder Wortteile, mit ; getrennt) | text | leer |  |
| `dxf_splitter` | DXF-Import: Teile kleiner als [mm] nicht anhaken (Maßpfeile, Splitter) | zahl | 5.0 | 0 … 100 |

### Dreh-/Frästeil-Richtpreis

| Name | Titel | Art | Vorgabe | Bereich |
|---|---|---|---|---|
| `df_stundensatz_drehen` | Stundensatz CNC-Drehen [€/h] | zahl | 85.0 | 0 … 10000 |
| `df_stundensatz_fraesen` | Stundensatz CNC-Fräsen 3-Achs [€/h] | zahl | 95.0 | 0 … 10000 |
| `df_ruesten_drehen` | Rüsten Drehen je Auftrag [min] | zahl | 45.0 | 0 … 10000 |
| `df_ruesten_fraesen` | Rüsten Fräsen je Auftrag [min] | zahl | 60.0 | 0 … 10000 |
| `df_ruesten_aufspannung` | Fräsen: Rüsten je weitere Aufspannung [min] | zahl | 15.0 | 0 … 1000 |
| `df_programm_drehen` | Programmieren Drehen je Teil [min] | zahl | 20.0 | 0 … 10000 |
| `df_programm_fraesen` | Programmieren Fräsen je Teil [min] | zahl | 30.0 | 0 … 10000 |
| `df_programm_element` | Programmieren je Konturelement (Absatz, Bohrung …) [min] | zahl | 2.0 | 0 … 100 |
| `df_aufmass_d` | Drehen: Aufmaß auf den Durchmesser [mm] | zahl | 2.0 | 0 … 50 |
| `df_aufmass_l` | Drehen: Aufmaß Länge je Planseite [mm] | zahl | 2.0 | 0 … 50 |
| `df_aufmass_fraes` | Fräsen: Aufmaß je Seite [mm] | zahl | 1.5 | 0 … 50 |
| `df_stange_bis` | Drehen von der Stange bis Ø [mm] (darüber gesägt) | zahl | 65.0 | 0 … 1000 |
| `df_abstich` | Abstechbreite [mm] | zahl | 3.0 | 0 … 20 |
| `df_bohr_max` | Größter Bohrer [mm] (darüber ausdrehen) | zahl | 32.0 | 1 … 200 |
| `df_fraeser` | Fräser-Ø Schruppen/Schlichten [mm] | zahl | 16.0 | 1 … 100 |
| `df_nutzung` | Nutzungsgrad der Schnittwerte (Anfahren, wechselnde Zustellung) | anteil | 60 % | 0.05 … 1 |
| `df_werkzeugwechsel` | Werkzeugwechsel je Werkzeug [min] | zahl | 0.15 | 0 … 10 |
| `df_handhabung` | Handhabung/Messen je Stück [min] | zahl | 0.5 | 0 … 60 |
| `df_entgraten` | Entgraten je Stück [min] | zahl | 0.3 | 0 … 60 |
| `df_einstich` | Einstechen je Einstich [min] | zahl | 0.25 | 0 … 60 |
| `df_fase` | Je Fase/Radius/Absatz [min] | zahl | 0.05 | 0 … 60 |
| `df_aufspannen_fraesen` | Fräsen: Aufspannen je Aufspannung und Stück [min] | zahl | 1.0 | 0 … 60 |
| `df_angetrieben` | Drehmaschine mit angetriebenen Werkzeugen (Querbohrung, Schlüsselfläche) | auswahl | ja |  |
| `df_mindestzeit` | Mindestzeit je Stück [min] | zahl | 0.5 | 0 … 60 |
| `df_verschnitt` | Materialzuschlag (Stangenrest, Sägeverlust) | anteil | 5 % | 0 … 5 |
| `df_aufschlag` | Aufschlag des Lieferanten (Gewinn) | anteil | 15 % | 0 … 5 |
| `df_max_d` | Machbarkeit: größter Drehdurchmesser [mm] | zahl | 320.0 | 0 … 10000 |
| `df_max_l` | Machbarkeit: größte Drehlänge [mm] | zahl | 1000.0 | 0 … 100000 |
| `df_fraes_x` | Machbarkeit: Verfahrweg Fräsen X [mm] | zahl | 1000.0 | 0 … 100000 |
| `df_fraes_y` | Machbarkeit: Verfahrweg Fräsen Y [mm] | zahl | 500.0 | 0 … 100000 |
| `df_fraes_z` | Machbarkeit: Verfahrweg Fräsen Z [mm] | zahl | 500.0 | 0 … 100000 |
| `df_bohr_gelb` | Machbarkeit: Bohrung tiefer als × Ø = Mehraufwand | zahl | 5.0 | 0 … 100 |
| `df_bohr_rot` | Machbarkeit: Bohrung tiefer als × Ø = Tieflochbohren | zahl | 10.0 | 0 … 100 |
| `df_schlank_gelb` | Machbarkeit: Drehteil länger als × Ø = Reitstock | zahl | 4.0 | 0 … 100 |
| `df_schlank_rot` | Machbarkeit: Drehteil länger als × Ø = Lünette/Langdreher | zahl | 12.0 | 0 … 100 |
| `df_tasche_gelb` | Machbarkeit: Tasche tiefer als × Fräser-Ø = langer Fräser | zahl | 4.0 | 0 … 100 |
| `df_tasche_rot` | Machbarkeit: Tasche tiefer als × Fräser-Ø = Sonderwerkzeug | zahl | 8.0 | 0 … 100 |
| `df_wand_min` | Machbarkeit: dünnste Wand [mm] | zahl | 1.0 | 0 … 100 |
| `df_radius_min` | Machbarkeit: kleinster Innenradius ohne Erodieren [mm] | zahl | 0.5 | 0 … 100 |
| `df_schnittwerte` | Schnittwerte je Werkstoffgruppe (eine Zeile je Gruppe, mit ; getrennt; erste passende Erkennung gilt, * = Rückfall) | mehrzeilig | # Gruppe; Dichte; €/kg; Drehen vc; f; ap; Schlichten vc; f; Fräsen vc; fz; Schlichten fz; Bohren vc; Reihe; Sägen cm²/min; Erkennung
Edelstahl; 7,9; 5,00; 140; 0,20; 2,0; 180; 0,10; 90; 0,045; 0,03; 60; D; 20; 1.43,1.44,1.45,1.40,1.41,V2A,V4A,Edelstahl,Niro,X5Cr,X2Cr,X6Cr,AISI
Aluminium; 2,7; 5,50; 600; 0,30; 3,0; 700; 0,12; 450; 0,12; 0,08; 250; C; 150; Al,EN AW,3.3,3.4,Alu
Messing; 8,5; 9,50; 300; 0,25; 2,5; 350; 0,10; 300; 0,08; 0,05; 150; C; 100; CuZn,Messing,2.0,Ms58,Bronze,CuSn,Kupfer,CW0,CW1,CW4,CW5,CW6,CW7
Kunststoff; 1,4; 10,00; 400; 0,30; 3,0; 500; 0,15; 500; 0,10; 0,06; 150; C; 200; POM,PA6,PE,PVC,PTFE,PEEK,Kunststoff
Vergütungsstahl; 7,85; 2,20; 130; 0,20; 1,5; 160; 0,10; 110; 0,06; 0,04; 70; B; 35; C45,42Cr,34Cr,16Mn,20Mn,1.0503,1.7225,11SMn,Automat
Stahl; 7,85; 1,60; 220; 0,30; 2,5; 260; 0,12; 200; 0,09; 0,05; 90; A; 45; *
 |  |

## Parameter: Stammdaten

### Maschinen

Endbeschnitt = Anschnitt am Stangenanfang, Greiferrest = nicht nutzbares Ende im Greifer, Schnittverlust = Materialverlust je Trennschnitt. Konturgrenzen: größtes Hüllmaß der Innenkontur. Kontur klein/mittel bis × Wand: zusätzlich nach Hüllmaß ÷ Wandstärke (Vorgabe 3 und 8), die strengere Klasse gilt. Max. Hüllkreis-Ø und max. Metergewicht: größere oder schwerere Profile bekommen im Angebot FEHLER und werden nicht eingeplant (leer = keine Grenze). Min. Stangenlänge Zuschnitt: kürzeste Stange, die die automatische Stangenladung nimmt; keine aus einer Lieferstange (z. B. 12 m) zugeschnittene Stange wird kürzer (leer oder 0 = keine Grenze). Stangenwechsel SN: Zeit je Stange, auf der ein Teil eine feste Schweißnaht-Lage hat (Naht ausrichten), alle anderen Stangen mit 'Stangenwechsel' (leer = wie Stangenwechsel). 3D (geschwenkter Laserkopf für Gehrungen in 3D und schräge Bohrungen): nur mit 'ja' kalkuliert; Winkel außerhalb min./max. werden auf die Grenze begrenzt. Greifmaß: Abstand, den eine 3D-Bearbeitung am letzten Teil einer Stange vom Stangenende braucht (zählt statt des Greiferrests, wenn größer, nie zusätzlich). Schneidzeit 3D = Schneiddaten bei Wand ÷ cos(Winkel) × Faktor + Zusatzzeit je Bearbeitung. RP-/Sonderprofile spannbar: 'nein' = Positionen mit RP-Profil oder Sonderprofil bekommen WARNUNG (Maschine prüfen), leer = ja. Rüstzuschlag Sonderprofil: zusätzliche Rüstzeit je RP-/Sonderprofil-Abmessung (wie Rüsten je Abmessung). Mindestabstand Düse: tiefer als dieses Maß steht der Anschlag eines RP-Profils über; Innenkonturen können darunter liegen und bekommen WARNUNG (prüfen), leer = keine Prüfung. Kürzestes Teil: kürzere Teile kann die Maschine nicht fertigen; sie bekommen die Stufe der Prüfregel 'Teil zu kurz für die Maschine' (leer = keine Grenze). Zeit je Kontur (Anfahren/Drehen): Zuschlag je Einstich für das Anfahren der Kontur und das Drehen des Rohrs dazwischen (jede Innenkontur und jedes Ende), leer = 0; mit echten Schnittzeiten abgleichen. Nebenzeit je Teil: Ausschieben, Abtrennen und Entnehmen jedes Teils, leer = 0. Schneidgas N₂/O₂: Gaskosten je Stunde Laserzeit zusätzlich zum Stundensatz, je nach Gas der Schneiddaten (Stickstoff für Edelstahl und Alu ist teurer), leer = 0; nur bei Stundensatz 'ermittelt' oder 'Gas zusätzlich zum Stundensatz' = ja. Rüstzuschlag je weiterer Profilform: Spannbacken bzw. Spannmittel tauschen, wenn ein Angebot mehrere Profilformen hat (z. B. Rundrohr und Rechteckrohr), je Form ab der zweiten, leer = 0. Schicht: Stunden je Arbeitstag für die Wochenauslastung (Datei → Maschinenauslastung …; leer = Einstellung). Stundensatz von Hand/ermittelt: leer bzw. 'von Hand' = der eingetragene Stundensatz gilt und enthält Gas und Strom (Schneidgas nur mit 'Gas zusätzlich zum Stundensatz' = ja); 'ermittelt' = der Satz aus den Feldern 'Ermittlung: …' und den Einstellungen (Knopf 'Stundensatz ermitteln …'), Schneidgas kommt je Teil dazu.

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `maschinen_id` | Maschinen-ID | text |  |
| `bezeichnung` | Bezeichnung | text |  |
| `endbeschnitt` | Endbeschnitt [mm] | zahl | 0 … 2000 |
| `greiferrest` | Greiferrest [mm] | zahl | 0 … 2000 |
| `schnittverlust` | Schnittverlust je Schnitt [mm] | zahl | 0 … 20 |
| `max_stange` | Max. Stangenlänge [mm] | ganz | 500 … 20000 |
| `stundensatz` | Stundensatz [€/h] | zahl | 0 … 10000 |
| `kontur_klein` | Kontur klein bis [mm] | zahl | 0.1 … 5000 |
| `kontur_mittel` | Kontur mittel bis [mm] | zahl | 0.1 … 5000 |
| `kontur_klein_wand` | Kontur klein bis [× Wand] | zahl | 0.1 … 1000 |
| `kontur_mittel_wand` | Kontur mittel bis [× Wand] | zahl | 0.1 … 1000 |
| `abstand` | Abstand getrennte Schnitte [mm] | zahl | 0 … 100 |
| `ruestzeit` | Rüstzeit je Angebot [min] | zahl | 0 … 1440 |
| `stangenwechsel` | Stangenwechsel je Stange [s] | zahl | 0 … 3600 |
| `stangenwechsel_sn` | Stangenwechsel SN je Stange [s] | zahl | 0 … 3600 |
| `bemerkung` | Bemerkung | text |  |
| `max_huellkreis` | Max. Hüllkreis-Ø [mm] | zahl | 1 … 2000 |
| `max_kg_m` | Max. Metergewicht [kg/m] | zahl | 0.1 … 1000 |
| `min_stange` | Min. Stangenlänge Zuschnitt [mm] | ganz | 0 … 20000 |
| `d3` | 3D: Bearbeitung verfügbar | auswahl |  |
| `schwenk_min` | 3D: Schwenkwinkel min. [°] | zahl | -89 … 0 |
| `schwenk_max` | 3D: Schwenkwinkel max. [°] | zahl | 0 … 89 |
| `greif_3d` | 3D: Greifmaß [mm] | zahl | 0 … 5000 |
| `zeit_3d` | 3D: Zusatzzeit je Bearbeitung [s] | zahl | 0 … 600 |
| `faktor_3d` | 3D: Faktor Schneidzeit | zahl | 0.1 … 10 |
| `sonder_spannbar` | RP-/Sonderprofile spannbar | auswahl |  |
| `ruest_sonder` | Rüstzuschlag Sonderprofil [min je Abmessung] | zahl | 0 … 1440 |
| `duese_min` | Mindestabstand Düse [mm] | zahl | 0 … 200 |
| `min_teil` | Kürzestes Teil [mm] | zahl | 0 … 20000 |
| `zeit_kontur` | Zeit je Kontur (Anfahren/Drehen) [s] | zahl | 0 … 60 |
| `zeit_teil` | Nebenzeit je Teil (Ausschieben/Entnehmen) [s] | zahl | 0 … 600 |
| `gas_n2` | Schneidgas N₂ [€/h] | zahl | 0 … 1000 |
| `gas_o2` | Schneidgas O₂ [€/h] | zahl | 0 … 1000 |
| `ruest_form` | Rüstzuschlag je weiterer Profilform [min] | zahl | 0 … 1440 |
| `schicht_stunden` | Schicht: Stunden je Arbeitstag | zahl | 0 … 24 |
| `sperrtage` | Schicht: Sperrtage (Wartung, Stillstand; z. B. 10.11.2026; 01.12.2026-03.12.2026) | text |  |
| `mannlos_ab` | Mannlos: ab Laufzeit je Los [h] (leer = aus) | zahl | 0 … 1000 |
| `mannlos_satz` | Mannlos: Stundensatz [€/h] | zahl | 0 … 10000 |
| `satz_art` | Stundensatz von Hand/ermittelt | auswahl |  |
| `gas_zusatz` | Gas zusätzlich zum Stundensatz | auswahl |  |
| `anschaffung` | Ermittlung: Anschaffung [€] | zahl | 0 … 1e+08 |
| `nutzungsdauer` | Ermittlung: Nutzungsdauer [Jahre] | zahl | 0 … 50 |
| `flaeche` | Ermittlung: Fläche [m²] | zahl | 0 … 10000 |
| `instandhaltung` | Ermittlung: Instandhaltung [% je Jahr] | zahl | 0 … 50 |
| `wartung` | Ermittlung: Wartung, Versicherung [€/Jahr] | zahl | 0 … 1e+07 |
| `leistung_kw` | Ermittlung: Anschlussleistung [kW] | zahl | 0 … 1000 |
| `verschleiss` | Ermittlung: Verschleiß [€/h] | zahl | 0 … 1000 |
| `bediener_anteil` | Ermittlung: Bediener [% Betreuung] | zahl | 0 … 100 |
| `last_anteil` | Ermittlung: mittlere Last [% der Anschlussleistung] | zahl | 1 … 100 |
| `stangenende` | Teil am Stangenende (Abfall vorziehen) | auswahl |  |
| `stangenende_min` | Stangenende: Mindestabfall [mm] (leer = 5) | zahl | 0 … 1000 |
| `stangenende_max` | Stangenende: höchster Abfall [mm] (leer = 300) | zahl | 0 … 5000 |
| `min_huellkreis` | Min. Hüllkreis-Ø [mm] (kleinstes spannbares Profil) | zahl | 0 … 2000 |
| `max_stange_kg` | Max. Stangengewicht Lader [kg] | zahl | 0 … 10000 |
| `zeit_drehen` | Drehzeit je Seitenwechsel [s] | zahl | 0 … 600 |
| `zeit_messen_schnell` | Messzyklus schnell [s] (leer = 4) | zahl | 0 … 600 |
| `zeit_messen_sorgfaeltig` | Messzyklus sorgfältig [s] (leer = 8) | zahl | 0 … 600 |
| `zeit_ausrichten` | Ausrichtzeit asymmetrische Profile je Stange [s] | zahl | 0 … 3600 |
| `lademinimum` | Lademinimum [mm] (kürzer = von Hand laden) | zahl | 0 … 20000 |
| `zeit_hand_laden` | Laden von Hand je Stange [s] (leer = 60) | zahl | 0 … 3600 |
| `active_tilt` | Active Tilt (Lochfelder bis 3 mm Wand) | auswahl |  |
| `abfall_max` | Größter Abfall ohne Zerteilen [mm] | zahl | 0 … 2000 |
| `anfahrweg` | Anfahrweg je Innenkontur [mm] | zahl | 0 … 100 |
| `beschleunigung_dick` | Langsamer ab 6 mm Wand mit N₂ | auswahl |  |
| `kleines_rohr_bis` | Kleines Rohr bis Hüllkreis-Ø [mm] | zahl | 0 … 500 |
| `entlade_laenge` | Entladegrenze Länge [mm] | zahl | 0 … 20000 |
| `entlade_kg` | Entladegrenze Gewicht [kg] | zahl | 0 … 5000 |
| `zeit_entnahme` | Entnahme von Hand je Teil [s] (leer = 30) | zahl | 0 … 3600 |
| `ganze_stange` | Ganze Stange ohne Trennschnitt | auswahl |  |
| `param_3d` | 3D: Schnittparameter | auswahl |  |
| `kanten_innen` | Eckzeit für Innenkonturen über die Kante | auswahl |  |
| `schwenk_ueber` | 3D: Winkel über Schwenkwinkel | auswahl |  |
| `rand_ohne_einstich` | Ausklinkung offener Profile ohne Einstich | auswahl |  |
| `eilgang_x` | Dynamik: Eilgang X [m/min] | zahl | 0 … 500 |
| `beschl_x` | Dynamik: Beschleunigung X [m/s²] | zahl | 0 … 100 |
| `drehzahl` | Dynamik: Drehzahl Spannfutter [U/min] | zahl | 0 … 1000 |
| `beschl_dreh` | Dynamik: Drehbeschleunigung [°/s²] | zahl | 0 … 100000 |
| `beschl_schnitt` | Dynamik: Schneidbeschleunigung [m/s²] | zahl | 0 … 100 |
| `gas_luft` | Schneidgas Druckluft [€/h] | zahl | 0 … 1000 |

### Schneiddaten

Je Maschine + Werkstoff (oder Kategorie) + Schneidgas gestaffelt nach Wandstärke: es gilt die Zeile mit der kleinsten 'Wandstärke bis', die mindestens der Profilwandstärke entspricht. Zeilen mit Werkstoff-ID gehen vor; hat der Werkstoff keine passende Zeile, gelten die Zeilen seiner Kategorie (Werkstoff-ID leer). Schneidgas: N₂, solange es eine N₂-Zeile für die Wandstärke gibt, darüber O₂ (so endet N₂ ab einer gewissen Wandstärke). Leere Vorschübe mittel/klein/Gravur nehmen den nächstgrößeren. Zeit je Ecke: Zuschlag je Ecke im Anfangs- und Endschnitt (der Laser bremst ab): RP-Profile nach ihrer Kontur, Quadrat- und Rechteckrohr 4, andere 0; leer = 0. Düse Ø und Gasdruck (Überdruck): daraus rechnet das Programm den Gasverbrauch in m³/h, wenn in den Einstellungen ein Gaspreis €/m³ für das Gas steht (Richtwerte N₂ 1,5-3 mm bei 10-20 bar, O₂ 1-2 mm bei 0,5-1,5 bar); leer = Schneidgas-Zuschlag €/h der Maschine. Quelle der Werte (Hersteller, eigene Messung, Nachkalkulation, Richtwert, geschätzt) und Stand: die Kalkulation zeigt sie je Teil mit der Sicherheit (hoch/mittel/niedrig); leer = unbekannt.

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `maschinen_id` | Maschinen-ID | auswahl |  |
| `werkstoff_id` | Werkstoff-ID | auswahl |  |
| `kategorie` | Kategorie | auswahl |  |
| `gas` | Schneidgas | auswahl |  |
| `wand_bis` | Wandstärke bis [mm] | zahl | 0.1 … 50 |
| `vorschub_gross` | Vorschub groß / Trennschnitt [mm/min] | zahl | 1 … 100000 |
| `vorschub_mittel` | Vorschub mittel [mm/min] | zahl | 1 … 100000 |
| `vorschub_klein` | Vorschub klein [mm/min] | zahl | 1 … 100000 |
| `einstechzeit` | Einstechzeit [s] | zahl | 0 … 60 |
| `vorschub_gravur` | Vorschub Gravur [mm/min] | zahl | 1 … 100000 |
| `bemerkung` | Bemerkung | text |  |
| `zeit_ecke` | Zeit je Ecke [s] | zahl | 0 … 60 |
| `duese` | Düse Ø [mm] | zahl | 0.3 … 10 |
| `gasdruck` | Gasdruck [bar] | zahl | 0.1 … 40 |
| `quelle` | Quelle der Werte | auswahl |  |
| `datum` | Stand | datum |  |

### Stundensätze

Stundensätze für die Arbeitsschritte. Der Satz 'Maschine' steht nicht hier: er ist immer der Stundensatz der im Angebot gewählten Maschine (Stammdaten Maschinen). Neue Angebote übernehmen die Sätze beim Anlegen; spätere Änderungen wirken nur auf neue Angebote (oder im Angebot nach 'Stundensätze aus Einstellungen').

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `satz_id` | Stundensatz-ID | text |  |
| `bezeichnung` | Bezeichnung | text |  |
| `satz` | Stundensatz [€/h] | zahl | 0 … 10000 |
| `bemerkung` | Bemerkung | text |  |

### Arbeitsschritte

Zeitvorgaben je Arbeitsschritt. Gesamtzeit = Rüstzeit × Anzahl (je Angebot einmal, je Abmessung je Profil-ID) + Zeit je Einheit × Menge (je Teil = Stückzahl, je Stange, je Position); Kosten = Gesamtzeit / 60 × Stundensatz, mit Zuschlag Fertigung in die Herstellkosten. Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je Abmessung und Stangenwechsel rechnet das Programm selbst; bei ihnen zählen nur Stundensatz, Art und Parallel. Art Personal mit Parallel = ja läuft neben der Maschine und verlängert die Durchlaufzeit nicht.

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `schritt` | Arbeitsschritt | text |  |
| `satz` | Stundensatz | auswahl |  |
| `art` | Art | auswahl |  |
| `parallel` | Parallel zur Maschine | auswahl |  |
| `ruestzeit` | Rüstzeit [min] | zahl | 0 … 100000 |
| `ruest_bezug` | Rüstzeit je | auswahl |  |
| `zeit` | Zeit je Einheit [s] | zahl | 0 … 100000 |
| `bezug` | Einheit | auswahl |  |
| `bemerkung` | Bemerkung | text |  |

### Zusatzarbeiten

Auswahl für 'Zusatzarbeiten …' im Angebot. Abrechnung: €/kg (Teilegewicht), €/m² (Außenfläche = Umfang × Länge), €/m (Teilelänge), €/Stück, €/Angebot (einmal je Angebot, auf die Teile umgelegt), s/Stück (Zeit je Stück, wird zur Schneidzeit addiert, z. B. Gravur, die nicht im Teil ist), €/h (Zeit in Sekunden je Teil, im Angebot je Position eingetragen, × Stundensatz, z. B. Schweißen). Preis je Einheit = Festpreis + Zeitaufwand × Stundensatz + Material mit Materialzuschlag + weiterer Zuschlag. Mindestbetrag: liegt die Summe im Angebot darunter, wird auf den Mindestbetrag angehoben. Fremdleistung = ja: Zuschlag Fremdleistung, sonst Zuschlag Fertigung. Menge aus: leer = nach der Abrechnung, sonst z. B. Innen- + Außenfläche (Strahlen, Verzinken innen) oder Anzahl Bohrungen; Faktor: Menge × Faktor (z. B. 1,05 für Gehänge); Mindestbetrag je Teil: ein Teil kostet mindestens diesen Betrag. Abweichende Preise je Werkstoff, Profil oder Kunde und automatisches Zuordnen: Arbeitsgang-Regeln. Erkennungswörter (z. B. verzinkt; fvz): steht eines in Bezeichnung, Artikelnummer, STEP-Name, Anfrage-Mail oder Zeichnung, schlägt das Programm die Zusatzarbeit gelb vor (gerechnet erst nach Übernehmen). Formel (nur €/Stück): Preis je Teil aus Größen der Position, z. B. 2,50 + 0,004 * L; Größen L Länge, A/B Abmessung, W Wand, Q Querschnitt, U Umfang [mm], G Gewicht [kg], F Fläche [m²], N Bohrungen, I Innenkonturen, S Stückzahl, H Stundensatz, T Wert der Wertetabelle; Wertetabelle z. B. 1000 = 1,20; 3000 = 1,80 nach der Größe in 'Tabelle nach' (Vorgabe L). Rüstzeit je Los (min): einmal je Angebot, je Position oder je Abmessung (Rüstzeit je), mit dem Stundensatz der Zusatzarbeit, auf die Teile umgelegt, in jeder Staffel neu; Zeitart Personal oder Maschine teilt die Zusatzarbeiten im Preisaufbau auf. Gewinde, Senken, Flowdrill und Bohren rechnen nur € je Stück (ohne Rüstzeit).

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `name` | Zusatzarbeit | text |  |
| `art` | Abrechnung | auswahl |  |
| `preis` | Festpreis [€] bzw. Zeit [s] je Einheit | zahl | 0 … 100000 |
| `mindest` | Mindestbetrag je Angebot [€] | zahl | 0 … 100000 |
| `fremd` | Fremdleistung | auswahl |  |
| `angebotstext` | Text im Angebot | text |  |
| `bemerkung` | Beschreibung | text |  |
| `kategorie` | Kategorie | text |  |
| `aktiv` | Aktiv | auswahl |  |
| `zeit` | Zeitaufwand je Einheit | zahl | 0 … 100000 |
| `zeit_einheit` | Zeiteinheit | auswahl |  |
| `satz_id` | Stundensatz-ID | auswahl |  |
| `satz` | Stundensatz eigener [€/h] | zahl | 0 … 10000 |
| `material` | Materialkosten je Einheit [€] | zahl | 0 … 100000 |
| `zuschlag_material` | Materialzuschlag | zahl | 0 … 100000 |
| `zuschlag_material_art` | Materialzuschlag in | auswahl |  |
| `zuschlag_weitere` | Weiterer Zuschlag [%] | zahl | 0 … 1000 |
| `zuschlag_weitere_basis` | Weiterer Zuschlag auf | auswahl |  |
| `bezug` | Menge aus | auswahl |  |
| `faktor` | Faktor Menge | zahl | 0.01 … 100 |
| `mindest_teil` | Mindestbetrag je Teil [€] | zahl | 0 … 100000 |
| `erkennung` | Erkennungswörter (; getrennt) | text |  |
| `formel` | Formel Preis je Teil [€] | text |  |
| `wertetabelle` | Wertetabelle (bis = €; …) | text |  |
| `tabelle_nach` | Tabelle nach Größe | auswahl |  |
| `ruestzeit` | Rüstzeit je Los [min] | zahl | 0 … 10000 |
| `ruest_bezug` | Rüstzeit je | auswahl |  |
| `zeitart` | Zeitart | auswahl |  |

### Qualitätsstufen

Qualitätskosten je Position aus dem Prüfplan: Q = (Merkmale × Messzeit je Merkmal × geprüfte Teile + 60 × (Erstmusterprüfung + Messprotokoll)) / 3600 × Stundensatz QS. Merkmale = Zeilen des Prüfplans der Position (Länge, Gehrungen, je Kontur Maß, Lage und Teilung). Geprüfte Teile: alle, jedes n-te (Stückzahl ÷ n aufgerundet) oder die ersten n. Erstmuster und Protokoll einmal je Los (Position, in jeder Staffel neu). Die Position wählt die Stufe in der Spalte Qualitätsstufe; leer = keine Qualitätskosten. Neue Kostenart Qualität im Preisaufbau, mit Zuschlag Fertigung und Gewinn. Kein Prozentaufschlag. Der Messzyklus an der Maschine bleibt Maschinenzeit; hier zählt die Messung von Hand. Steht an der Position die Zusatzarbeit Erstmusterprüfung, zählt die Erstmusterzeit der Stufe nicht (keine Doppelzählung).

| Feld | Titel | Art | Bereich |
|---|---|---|---|
| `name` | Qualitätsstufe | text |  |
| `aktiv` | Aktiv | auswahl |  |
| `zeit_merkmal` | Messzeit je Merkmal [s] | zahl | 0 … 3600 |
| `pruefanteil` | Prüfanteil | auswahl |  |
| `pruef_n` | n (jedes n-te bzw. erste n) | ganz | 1 … 100000 |
| `erstmuster` | Erstmusterprüfung je Los [min] | zahl | 0 … 10000 |
| `protokoll` | Messprotokoll je Los [min] | zahl | 0 … 10000 |
| `satz_id` | Stundensatz-ID QS | auswahl |  |
| `satz` | Stundensatz eigener [€/h] | zahl | 0 … 10000 |
| `bemerkung` | Bemerkung | text |  |
