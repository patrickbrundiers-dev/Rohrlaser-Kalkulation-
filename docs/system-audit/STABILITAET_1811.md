# Stabilität, Robustheit und Berechnungen (Auftrag 18.11.2026)

Auftrag von Patrick vom 18.11.2026: doppelte Berechnungen vermeiden, Stabilität, Datenintegrität, Performance,
Tests und Diagnose. Dieser Bericht baut auf der Systemprüfung vom 17.11. auf (AUDIT_REPORT.md und folgende) und
wiederholt sie nicht. Maßnahmenplan: https://claude.ai/artifact/YYmg2YGUrebAAz13v84UEQ

Umgesetzt in drei Paketen:
- A, Doppelrechnungen: PR #561
- B, beschädigte Werte: PR #561
- C, Diagnose, Langzeittest und dieser Bericht: eigener PR

Gemessen wurde im Linux-Container (4 Kerne, Qt offscreen). Unter Windows liegen die Werte erfahrungsgemäß etwas
höher. Grundlage ist ein echtes Angebot aus dem Support-Paket vom 18.11. (33 STEP-Dateien, 38 Positionen). Die
Dateien liegen nicht im Repository.

## Ergebnisse bleiben gleich

Nach jedem Paket wurde ein Fingerabdruck über das ganze Angebot gebildet: Positionstabelle, Status, Meterpreise und
Kalkulation (`repr` nach Neuladen, zufällige `uid` ausgeblendet). Vorher, nach A und B und nach C ist er derselbe,
`18b2ab120255124b`. Die Ergebnisse sind also bitgleich, es gibt keine Formeländerung.

## Leistung vorher und nachher

| Vorgang | vorher (main + #555) | nach A+B | nach C |
|---|---|---|---|
| STEP-Import 33 Dateien | 259 s | 243 s | 248 s |
| Neuladen kalt | 3,3 s | 2,2 s | 2,1 s |
| Neuladen warm | 1,8 s | 1,5 s | 1,6 s |
| Zelle ändern + Angebots-Check, gesamt | 8,1 s | 5,9 s | 5,9 s |
| davon wartet die Oberfläche | 8,1 s | 2,3 s | 2,3 s |
| Optimieren | 2,9 s | 2,3 s | 2,3 s |
| Werkstatt-PDF | 4,7 s | 3,5 s | 3,6 s |
| Angebots-PDF (Messung ohne Hintergrund) | 3,4 s | 5,5 s | 5,0 s |

Zur Tabelle:
- Beim Zelle ändern läuft der Maschinenvergleich jetzt im Hintergrund. Die Oberfläche wartet nur auf den Rest. Der
  Hinweis auf eine günstigere Maschine erscheint ein paar Sekunden später, mit demselben Inhalt wie vorher.
- Angebots-PDF: In der Messung läuft der Vergleich sofort, im Programm im Hintergrund. Er rechnet hier neu, weil sich
  die Preisbasis des Angebots geändert hat. Vorher lieferte ein veralteter Zwischenspeicher dieses Ergebnis, ohne zu
  rechnen. Das ist gewollt: Der Hinweis passt jetzt immer zum aktuellen Stand.
- Import: 151 s entfallen auf die STEP-Messung, die schon parallel läuft. 47 s sind die Gegenprobe der Konturen.
  Beides ist echte Rechenarbeit und bleibt unverändert, weil die Konturen nicht angefasst werden.
- Die Diagnose (Paket C) bremst nicht messbar. Die Unterschiede liegen im Rahmen der Messschwankung.

## Behobene Fehler und Schwachstellen

| Nr. | Datei / Funktion | Ursache | Auswirkung | Lösung |
|---|---|---|---|---|
| D1 | `maschinen_vergleich`, `angebot_fenster._maschinen_punkt` | Drei Aufrufer rechneten den Vergleich getrennt. Der Zwischenspeicher hing an der Änderungszeit. | Je Änderung bis zu 3 × alle Maschinen optimiert und kalkuliert, 3,6–4,8 s. | Ein gemeinsamer Merker nach Inhalt (ohne Zeitstempel und Kennzahlen). Im Check läuft der Vergleich im Hintergrund-Thread. |
| D2 | `rechnen._schneidzeit_teile` | Gleiche Position, gleiche Maschine wurde im selben Rechenlauf mehrfach gerechnet. | 477 Aufrufe beim Import. | Im Rechenlauf-Merker abgelegt, jeder Aufrufer bekommt eine Kopie. |
| D3 | `zeit_zusatz._lagen` | Die Konturdaten (JSON) wurden je Zugriff neu gelesen. | 12.000 × `json.loads`. | Begrenzter Merker je Kontur und Länge (8.731 Treffer bei 38 Neuberechnungen). |
| S1 | `datenbank.position_neu/_aendern` | SQLite speichert NaN als leer, PostgreSQL behielt NaN. | Absturz beim Optimieren unter PostgreSQL. | NaN wird überall leer gespeichert. |
| S2 | `datenbank.positionen` | Unbrauchbare Zahlen aus Import, Abgleich oder einer beschädigten Datei wurden ungeprüft gerechnet. | Stück 10¹² führte zu MemoryError, ∞ oder Text zum Abbruch. | `zahlen_bereinigen`: Diese Werte werden beim Lesen leer, und der Status meldet den fehlenden Wert. |
| S3 | `dynamik.folge`, `durchdringung` | Globale Merker wurden mit `in` + `[]` gelesen. | Mit dem Hintergrund-Thread hätte ein KeyError auftreten können. | Zugriff über `.get` bzw. abgesichertes `pop`. |
| G1 | – | Es gab keine Möglichkeit, Doppelrechnungen im Betrieb zu sehen. | Langsame Stellen nur über ein Profil auffindbar. | Diagnose: Rechenzähler (siehe unten). |

Geprüft und ohne Befund:
- Signale und Timer werden nicht doppelt verbunden.
- Die Eingabe in der Oberfläche weist NaN und ∞ schon ab.
- Die drei Neuladen beim Import folgen jeweils einer echten Änderung. Sie zusammenzulegen (D4) brächte kein anderes
  Ergebnis, darum bleibt es dabei.

## Architektur

- **`rechenmerker.Merker`**: Das ist der gemeinsame Baustein für alle Merker reiner Rechnungen.
  - Der Schlüssel besteht aus allen Eingaben, nach Inhalt.
  - Die Größe ist begrenzt (LRU), der Merker ist sicher für mehrere Threads.
  - Er zählt Treffer und Neuberechnungen.
  - Neue Merker sollen diesen Baustein nutzen, statt eigene Wörterbücher anzulegen.
- **`rechnen.merker()`** (Rechenlauf-Merker) bleibt für Werte, die nur innerhalb eines Laufs gelten. Seine Treffer
  zählt jetzt ebenfalls die Diagnose.
- **Stammdaten-Stand**: `Datenbank.kontext()` und `tabellen()` liefern je Stand dasselbe Objekt. Merker dürfen
  deshalb `id(k)` und `id(tabellen)` im Schlüssel verwenden.
- **Hintergrund-Thread** im Angebot: Er rechnet nur auf Kopien, ohne Datenbank und ohne Qt. Das Ergebnis landet im
  Merker. Ein Timer im Hauptthread holt es ab und zeigt den Check neu, aber nur, wenn das Angebot noch denselben
  Stand hat.

## Diagnose (Paket C)

Die Diagnose steht unter **Hauptadmin → Diagnose: Rechenzähler …** und als `diagnose.txt` im Support-Paket. Sie
zeigt seit dem Programmstart:
- je Rechnung (Kalkulation, Optimieren, Maschinenvergleich): Anzahl, Dauer, langsame Läufe (über 1 s) und
  „doppelt“, also dieselbe Rechnung mit genau denselben Eingaben noch einmal,
- Treffer aller Merker,
- die Anzahl der Datenbank-Anweisungen,
- Fehler, Warnungen und den Arbeitsspeicher.

Beispiel aus der Messung oben (Import, Neuladen, Zelle, Optimieren, zwei PDFs):

```
Rechnungen                         Anzahl   gesamt s   längste s  langsam  doppelt
Kalkulation                            26       30,4        4,60        7        3
Maschinenvergleich                      5       20,9        9,89        5        0
Optimieren                             17        0,5        0,19        0        0

Merker (vermiedene Doppelrechnungen)            Treffer      neu   Quote  Einträge
Konturen mit Lage (zeit_zusatz._lagen)            8.731       38   100 %  38/4.000
Rechenlauf: schneiddaten                          1.869      123    94 %         –
Datenbank: 5.365 Anweisungen, zusammen 0,3 s
```

Neuer Befund aus der Diagnose: 3 der 26 Kalkulationen laufen mit genau denselben Eingaben noch einmal. Wo genau,
ist noch nicht zugeordnet; die Messfolge legt die PDF-Ausgaben nahe. Das ist der nächste Kandidat für einen Merker. Er wurde hier nicht mehr
eingebaut, weil die Kalkulation viele Aufrufer hat und ihr Ergebnis dort verändert wird. Das muss erst einzeln
geprüft werden (Regel „bei Unsicherheit erst analysieren“).

## Tests

Alle neuen Tests stehen in `tests/alle.py`.

- `test_doppelrechnung_1811`:
  - Merker: Größe, Threads, nicht hashbare Schlüssel.
  - D1–D3: Ergebnisse gleich wie ohne Merker, Kopien.
  - Angebot: Zelle + Check rechnet den Vergleich genau einmal, auch im Hintergrund.
- `test_beschaedigte_werte_1811`:
  - 125 beschädigte Zahlenwerte direkt in der Datei.
  - Lesen, Optimieren und Kalkulieren laufen ohne Abbruch, danach ist das Ergebnis gleich.
  - Fenster mit Stück 10¹² und Länge ∞.
- `test_diagnose_1811`:
  - Zähler und Erkennung „doppelt“.
  - Bericht im Angebot, Support-Paket, Menü und Fenster.
  - **Langzeittest**: 150 Änderungen mit Check. Die Merker bleiben begrenzt, der Speicher wächst um weniger als 40 MB
    (gemessen 1,9 → 3,8 MB).
  - **Neustart-Probe**: Datei schließen und neu öffnen ergibt dasselbe Ergebnis.
- Vorhandene Tests zu Mehrbenutzer und Abgleich laufen unverändert: Datenspeicher je PC, Abgleich, Lasttest bis 25
  Plätze.

## Offen

- SEC-03 bleibt, wie in der Systemprüfung beschrieben, ohne Server nicht lösbar.
- 3 Kalkulationen mit gleichen Eingaben (vermutlich PDF-Ausgaben), siehe oben.
- Echtbetrieb mit mehreren PCs am Netzordner: Das ist der Feldtest bei Patrick. Die Diagnose im Support-Paket zeigt
  dann, ob dort noch etwas doppelt rechnet.
