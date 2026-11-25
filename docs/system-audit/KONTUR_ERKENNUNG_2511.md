# Erkennung Endkonturen und Sonderkonturen (25.11.2026)

Auftrag Patrick 25.11.2026: „Erkennung weiter verbessern und optimieren“, dazu „Okay sonderkonturen müssen auch erkannt
werden“. Version 0.9.492, kein Schema-Sprung. Baut auf #658 (Endkonturen universell, 0.9.488) auf.

## 1. Bestandsaufnahme

Der STEP-Import kannte für Enden: gerade, Gehrung (auch schon 2D geschnitten, `gehrung_aus_umriss`), Gegenrohr
(`gegen_aus_messung`), Schrägschnitt. Alles andere blieb „komplex“ mit gemessenem Umriss: richtig geschnitten, aber im
Editor ohne Namen und ohne Maße. In den 134 Prüf-STEPs: 351 gerade, 14 Gehrung, 2 Schrägschnitt, 5 komplex.
Sonderkonturen in der Wand (alles, was kein gerades Langloch, Rechteck oder Bohrung auf 0,05 mm ist) kamen nur mit
Umriss und Länge.

## 2. Endkonturart erkennen (`endkontur.erkennen`)

Nach Gehrung und Gegenrohr, nur für komplexe Enden ohne Ausflug, Rund-, Quadrat- und Rechteckrohr:

1. **Richtung**: Ein Durchgangsschnitt hängt nur von w = u·sin r + v·cos r ab. Er ist also spiegelbildlich zur Achse w.
   Kastenrohr: 0° und 90° prüfen; Rundrohr: Raster 3°, Minima fein nachsuchen, ganze Grad zuerst (Sprünge).
   An steilen Stellen sind 0,3 mm Lage frei. Je Richtung auch r + 180°.
2. **Maße**: Startwerte aus dem Verlauf d(w), danach Nelder-Mead (ohne scipy) auf die Fehlerquadrate.
   Stufen getrennt behandelt: Höhen gruppieren, Proben im Sprung ignorieren, Sprungstelle per Halbierung auf dem Umriss.
3. **Entscheid**: Gerundete Maße (0,1, dann 0,01 mm; Richtung am Rundrohr 5°, 1°, 0,1°). Jede Variante gegen den
   Umriss, mit `kurven_abstand` (Hausdorff auf dem abgewickelten Mantel):
   - Jeder Messpunkt muss auf 0,1 mm an der Kontur liegen.
   - Umgekehrt sind 0,3 mm erlaubt, weil die Messung ihre Punkte gerade verbindet (Sehne an der Wand einer U-Kerbe).

   Ein Sprung zählt als senkrechte Strecke, eine um 0,05 mm versetzte Stufe ist 0,05 mm daneben.

Ergebnis `e["kontur_erkannt"] = {kontur, abweichung}`. **Umriss und Schnittlänge der STEP bleiben maßgebend**
(Grundregel 100 % wie STEP); die erkannte Kontur benennt das Ende (Editor: „V-Kerbe t 15 b 36 (erkannt, Umriss wie
STEP)“) und belegt den Endkontur-Dialog vor. Erst OK macht daraus eine bearbeitbare Endkontur (die dann den Umriss
ersetzt, wie jede Endkontur).

Nebenbei korrigiert (Modell #658):
- Der Verlauf rechnet an Kastenrohren auf der echten Außenkontur mit Eckradius (`skizze.rund_ort`), nicht an der
  scharfen Ecke. An der Ecke eines QR 60 mit R6 lag eine V-Spitze sonst 1,2 mm daneben.
- Knickstellen werden am Rundrohr per Halbierung gesucht, statt linear zwischen Stützstellen.
- Um Knicke herum gibt es feine Stützstellen (±0,02 … 0,2 mm), sonst fehlte die senkrechte Wand einer U-Kerbe am
  Rundrohr.

## 3. Sonderkonturen (`form_erkennung.py`, neu)

1. **Zerlegen** in Geraden und Kreisbögen, enger als die Erkennung (0,03 mm):
   - Je Startpunkt wird die Reichweite als Gerade und als Bogen bestimmt. Danach sucht dynamische Programmierung die
     Zerlegung mit den wenigsten Stücken. Bei Gleichstand gewinnen die Bögen, damit die Gerade keine Bogenpunkte
     frisst.
   - Ein Bogen braucht kleine, gleichmäßige Schritte von höchstens 25° und gleichmäßigen Sehnen. Sonst passen die
     Ecken eines Rechtecks auf einen Kreis.
   - Ein Bogen braucht mindestens 8° Spanne. Sonst wäre eine verrauschte Gerade ein Bogen mit R 670.
   - Nachbarstücke desselben Kreises bzw. derselben Geraden werden mit 0,1 mm zusammengelegt.
2. **Grundform** aus der Folge der Stücke: Kreis, Langloch, Rechteck (scharf oder mit Eckradius), Dreieck,
   regelmäßiges Vieleck.
   - Die Lage kommt aus dem Ausgleich über alle Geradenpunkte. Glatte Winkel werden nur genommen, wenn sie höchstens
     0,2° daneben liegen.
   - Die Maße kommen aus der Ausdehnung quer zu den Seiten bzw. aus den Seitenlängen bei scharfen Ecken.
   - Der Eckradius wird gerundet versucht.
   - Erkannt gilt eine Grundform nur, wenn die ideale Form den Umriss überall auf 0,1 mm trifft.
3. **Sonst Freiform**: Zahl der Geraden und Bögen und deren Radien.

Ergebnis `k["form_erkannt"]` und, wenn noch keine Bemerkung da ist, `k["text"] = "<Form>: Umriss wie STEP"`
(Schneidweg-Zeile, Bemerkung, Editor „3. Sonderkontur (Sechseck SW 17,3) …“). Auch für geschlossene Sonderkonturen
offener Profile.

## 4. Verschachtelung 2D

`endkontur.ende_verlauf_zellen(…, d3=…)` nimmt den Zuschlag Wand × tan(Schwenk) nur noch bei 3D-Schnittbearbeitung
des Teils (`rechnen.kontur_enden` gibt `d3` des Teils mit). 2D heißt: der Strahl steht senkrecht zur Oberfläche, die
Innenkante liegt unter der Außenkante. Vorher wurden die Verschachtelungstiefen gemessener Enden zu klein angenommen:

| Teil | konstruiert | bisher | jetzt |
|---|---|---|---|
| RE 80×40 V-Spitze | 20 | 17,0 | 20 |
| RE 80×40 Bogen | 10 | 6,1 | 10 |
| QR 60 Bogen | 10 | 7,8 | 10 |
| RR 60 U-Kerbe | 18 | 16,2 | 18 |

Gehrungen in 3D (`e.d3` + Winkel) unverändert. `test_regression_ergebnisse` grün.

## 5. Prüfsatz und Erkennungsquote

- `tests/erzeuge_endkonturen.py`: 24 Rohre (QR 60, RE 80×40, RR 60,3) mit V-Spitze, V-Kerbe, U-Kerbe, U-Zunge,
  Bogen konvex/konkav, Stufen, Schräg (= Gehrung).
- `tests/erzeuge_sonderkonturen.py`: 15 Rohre mit schrägem Langloch, gedrehtem Rechteck R3, Dreieck, Sechseck,
  gedrehtem Quadrat, Kreuz, Schlüsselloch (QR, RE) und Langloch am Rundrohr.
- `werkzeuge/kontur_erkennung.py --pruefsatz` (oder ein eigener Ordner): **24 von 24 Enden, 14 von 14 Sonderkonturen**
  richtig. Übernahme mit Erkennung für die 39 Teile ca. 21 s. Pro komplexem Ende 0,2–2,8 s, pro Sonderkontur unter
  0,2 s.
- `tests/test_kontur_erkennung.py` (in TESTS):
  - Rundlauf jeder Art an drei Profilen, mit Versatz und Richtung.
  - Gerade und Zickzack werden nicht erkannt.
  - Formen mit Rauschen.
  - Ellipse ist kein Kreis.
  - Zuschlag 2D/3D.
  - Prüfsatz über den echten Import mit Anzeige und Verschachtelungstiefe.
