# STEP-Import: Performance-Messungen

Werkzeug: `werkzeuge/step_benchmark.py` (Master-Prompt Patrick 21.11.2026 „Extreme Performance-Optimierung
STEP-Import“).

```
python werkzeuge/step_benchmark.py lauf  BAUM_ALT ergebnis_alt tests --prozesse 1
python werkzeuge/step_benchmark.py lauf  BAUM_NEU ergebnis_neu tests --prozesse 1
python werkzeuge/step_benchmark.py vergleich ergebnis_alt ergebnis_neu --bericht bericht.md
```

`lauf` misst jede Datei mit der STEP-Messung des jeweiligen Programmstands in einem eigenen Prozess und hält Dauer,
CPU-Zeit, CPU-Auslastung und RAM-Spitze fest. `vergleich` prüft das JSON der Messung **ungerundet** (Toleranz 0): jede
Zahl, jeder Text und jede Liste muss gleich sein. Nur Zeitpunkt und Programmversion zählen nicht. Bei einem
Unterschied ist der Rückgabewert 1.

Beide Stände laufen gleichzeitig auf demselben Rechner (gleiche Last). Die Zeiten schwanken trotzdem um etwa ±10 %.
Kleine Faktoren um 1,0 sind deshalb kein Unterschied.

## 0.9.447 (Basis 0.9.444)

Was geändert wurde:

- **Schwenkwinkel:** Der Projektor wird je Fläche einmal eingerichtet, danach je Punkt nur noch gerechnet.
- **Schweißnaht-Körper:** Nur Rohre, Bleche und Profile werden als Nachbarn exakt vermessen. Bisher geschah das
  danach für alle Körper. Die Hüllquader werden je Körper einmal gebildet.
- **Normteile laut Name:** Teile mit DIN/ISO eines Verbindungselements, rund und bis 150 mm, werden nur als
  Zukaufteil gemessen.

### 126 Test-STEPs (tests/)

| | alt | neu |
|---|---:|---:|
| Summe | 365,8 s | 344,3 s |
| Messwerte gleich | | 126 von 126 |

Rohre mit vielen Konturen messen rund 10 % schneller (z. B. K07/K08 U80x40x4: 25,3 s → 22,8 s). Einzelteile mit
1–2 s ändern sich kaum, weil dort der Start des Messprogramms und der CAD-Kern die Zeit bestimmen.

### Echte Baugruppen

| Datei | Körper | alt s | neu s | Faktor | RAM alt/neu MB | gleich |
|---|---:|---:|---:|---:|---:|---|
| MASTER_TOWER_V1.1 | 1080 | 755,1 | 511,9 | 1,47 | 661 / 649 | ja |
| Pizza_oven | 231 | 286,7 | 291,3 | 0,98 | 363 / 358 | ja |
| Кузов | | 129,2 | 147,8 | 0,87 | 339 / 338 | ja |
| Industrial_Scrap_Bin | | 21,4 | 23,4 | 0,91 | 286 / 286 | ja |
| Grab | | 15,5 | 15,6 | 0,99 | 286 / 285 | ja |

Die Baugruppen liefen mit der Messung im Stand **ohne** Normteil-Vorab-Erkennung, deshalb sind sie bitgleich.
Kontrolle der Schwankung: Der alte Stand zweimal gleichzeitig ergab für Кузов 149,1 s und 148,4 s, für Scrap Bin
22,9 s und 23,2 s. Кузов (148 s neu) ist also unverändert; die 129 s im ersten Lauf waren Schwankung.

### Normteile laut Name: alte gegen neue Messung je Normteil

Geprüft wurde jedes einzeln gemessene Normteil (Kopien übernehmen die Messung des Vorbilds). Verglichen wurden Art,
Maße, Drehteil-Daten und Fingerabdruck.

| Datei | Teil | voll s | kurz s | gleich |
|---|---|---:|---:|---|
| Pizza_oven | Blindniet DIN 7337 4x8 (169 Stück) | 12,52 | 0,06 | ja |
| Pizza_oven | DIN 7984 M4x12 | 0,02 | 0,07 | ja |
| U_29MB | DIN 933 M12x40, M10x30, M10x50 | 0,01–0,02 | 0,01 | ja |
| U_29MB | DIN 934 M12, M10 | 0,02 | 0,02 | ja |

Scheiben und Sicherungsringe (DIN 125, 127, 433, 471, 472) bleiben voll gemessen, wie bisher als Blech.

Ganzer Pizza-Ofen mit Normteil-Vorab-Erkennung: **286,7 s → 253,6 s**. Unterschiede gibt es nur bei den 173
Normteil-Körpern (169 Niete, 4 Schrauben DIN 7984). Bei ihnen steht als Grund *Norm DIN 7337 im Bauteilnamen*. Es
fehlen die nicht gewählte Auswahlmessung „offenes Sonderprofil“ und die Längsachse, also Felder der übersprungenen
Profilmessung. Art, Maße, Volumen und Netz sind gleich. Alle übrigen 58 Körper sind bitgleich. Die 126 Test-STEPs sind
auch mit der Vorab-Erkennung 126 von 126 bitgleich (keine Normteile mit Normnamen darunter).

## 0.9.448 (Basis 0.9.447)

Schweißnaht-Körper: Der Abstand zu den Nachbarn wird nur noch zwischen den Flächen gemessen, die in der Hülle des
anderen Körpers liegen (`step_geometrie._abstand`, gleicher Wert wie über die ganzen Körper).

| Datei | alt s | neu s | Faktor | gleich |
|---|---:|---:|---:|---|
| MASTER_TOWER_V1.1 | 523,9 | 468,9 | 1,12 | ja |
| Pizza_oven | 264,7 | 211,0 | 1,25 | ja |
| Кузов | 136,8 | 142,8 | 0,96 | ja |
| Grab | 15,0 | 16,4 | 0,91 | ja |
| Industrial_Scrap_Bin | 21,6 | 23,3 | 0,93 | ja |

Gegenüber 0.9.444: MASTER TOWER 755 s → 469 s (Faktor 1,6), Pizza-Ofen 287 s → 211 s (Faktor 1,36).

## 0.9.449 (Basis 0.9.448)

Nahtkandidaten: `step_geometrie._beruehrung` schneidet die beiden Körper zuerst. Liegt ein Punkt einer Schnittkante
so nah an beiden Körpern, dass ihr Abstand höchstens 0,1 mm ist (Dreiecksungleichung), ist die Berührung bewiesen:
Spalt 0, derselbe Schnitt wird weiterverwendet, die Abstandsmessung der ganzen Körper entfällt. Sonst wie bisher.

| Datei | alt s | neu s | Faktor | gleich |
|---|---:|---:|---:|---|
| MASTER_TOWER_V1.1 | 391,5 | 378,6 | 1,03 | ja |
| Pizza_oven | 196,3 | 194,2 | 1,01 | ja |
| Кузов | 134,9 | 126,5 | 1,07 | ja (Erreichbarkeit: Zeitbudget, siehe unten) |
| Grab | 15,3 | 16,3 | 0,94 | ja |
| Industrial_Scrap_Bin | 20,6 | 20,5 | 1,00 | ja |
| 126 Test-STEPs | 289,1 | 280,8 | 1,03 | ja |

Bei Кузов fehlten im alten Lauf die Erreichbarkeits-Felder von 4 Nahtkandidaten: das Zeitbudget von 20 s war unter
Last erschöpft (bekannte Grenze, siehe oben); alle Messwerte sind gleich. Geprüft und verworfen: Flächenpaare je
Hüllquader vorfiltern (kein Gewinn, 782,9 → 781,4 s). Die übrigen Abstandsmessungen betreffen Paare, die sich nicht
berühren (Pizza-Ofen: 629 Paare, 26 s).

## Wo die Zeit heute liegt (Profil, py-spy)

| Datei | Anteil |
|---|---|
| Test-STEPs | Ebenenschnitte 28 %, Boolesche Operationen (offene Profile) 22 %, Laden des CAD-Kerns 9 %, Schwenkwinkel 7,5 % |
| Lift Cart | Ebenenschnitte 76 % (ein Körper mit Freiformflächen, jeder Schnitt ~5 s) |
| Кузов | Ebenenschnitte 38 %, Anbauteile trennen 26 %, Erreichbarkeit 16 %, Nahtsuche 13 % |
| MASTER TOWER (vor 0.9.447) | Schweißnaht-Körper 45 % (davon Nachbarn exakt 43 %), Nahtkandidaten 21 %, Profilmessung 20 % |
| MASTER TOWER (0.9.448) | Ebenenschnitte der Profilmessung 44 %, Nahtkandidaten 29 %, Anbauteile trennen 12 %, Schweißnaht-Körper nur noch 5 % |
| Pizza-Ofen (0.9.448) | Ebenenschnitte 35 %, Nahtkandidaten 29 %, Anbauteile trennen 16 %, Schweißnaht-Körper 14 % |
| U_29MB (870 Körper) | Einlesen 370 s, davon 96 % in der Formheilung des CAD-Kerns: Der STEP fehlen die Parameterkurven der Kanten, sie werden beim Einlesen auf die Freiformflächen projiziert (ShapeFix_Edge::FixAddPCurve). Das Messen der Normteile dauert nur 3,5 s |

- **Lift Cart Körper 32:** Wendel mit zwei Freiformflächen zu je 6 × 361 Polen. Jeder Ebenenschnitt dauert etwa
  5 s, der Körper läuft ins Zeitlimit (600 s) und wird vereinfacht als Frästeil gemessen. Der CAD-Kern schneidet
  schon parallel (SetRunParallel). Schneller ginge es nur mit einer anderen Messart für Wendeln; die würde das
  Ergebnis ändern und ist deshalb ein eigener Vorschlag.

Getestet und verworfen:

- **Threads für Ebenenschnitte:** 3,1 s gegen 2,8 s. Der CAD-Kern gibt in Python die Sperre (GIL) nicht frei, deshalb
  bleibt nur die Verteilung auf mehrere Prozesse.
- **Rasterpunkte auf Flächen** für die Schweißnaht-Körper: langsamer (241 s statt 186 s).
- Gröbere Toleranzen, weniger Schnitte und Netz statt B-Rep: ausgeschlossen, weil sie die Ergebnisse ändern.
- **Einlesen ohne Formheilung:** Ohne die nachgerechneten Parameterkurven sind die Flächen ungültig, und die
  Messung ändert sich. Beim zweiten Import derselben Datei entfällt die Zeit, weil der Messcache das Ergebnis
  liefert. Innerhalb eines Imports liest nur ein Prozess die Datei, die anderen laden den Schnappschuss.
