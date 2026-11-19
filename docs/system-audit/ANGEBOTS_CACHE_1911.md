# Angebots-Cache (Auftrag 19.11.2026 „Angebotsbezogene Zwischenspeicherung“)

Patrick hat am 19.11.2026 einen dauerhaften Zwischenspeicher je Angebot beauftragt. Er soll mit Abhängigkeits- und
Versionsprüfung arbeiten, eine Verwaltung, Kennzahlen und Tests haben, und die Ergebnisse müssen gleich bleiben.

Der Cache baut auf drei vorhandenen Bausteinen auf, statt eine zweite Struktur zu schaffen:
- Merker über den Neustart `dauermerker.py` (#572)
- Kalkulationsmerker im Speicher (#569)
- Merker im Speicher (`rechenmerker`, #561)

## 1. Identifizierte Zwischenberechnungen

Gemessen beim Öffnen eines Angebots aus dem Support-Paket (33 STEP-Teile, 38 Positionen) in einem frischen Prozess,
ohne gemerkte Ergebnisse (profiliert, darum langsamer als ohne Profiler):

| Rechnung | Zeit (profiliert) | Abhängig von | Entscheidung |
|---|---|---|---|
| Schnittzeiten je Position (`rechnen._schneidzeit_teile`: Schneiddaten, Vorschübe, 3D, Enden, Ecken, Leerwege, Schneidfolge) | 11,8 s | Position, Kopf (Maschine, Gravur-Platzhalter), Wand, Stammdaten ohne Preise | **Angebots-Cache** |
| davon Schneidfolge (`dynamik.folge`, 2-opt) | 7,2 s | Konturlagen, Maschine, Länge | allgemeiner Cache (#572) |
| davon Endabfall aus dem 3D-Netz (`zeit_zusatz.ende_abfall`) | 3,5 s | Technik, Profil, Länge | allgemeiner Cache (#572) |
| Kalkulation (`rechnen.kalkulation`: Material, Maschine, Rüsten, Zusatzarbeiten, Zuschläge, Staffeln, Summen) | 4,3 s | Kopf, alle Positionen, Optimierergebnis, Einstellungen, alle Stammdaten, Tag | **Angebots-Cache** |
| Prüfstatus: Fertigungsprüfung Rohr/Blech (`dfm._rohr`, `dfm._blech_position`) | 2,2 s | Technik, Länge, Profil, Wand, Prüfregeln | **allgemeiner Cache** |
| Sechskant/Senkung (`zusatz_erkennung.geometrie`) | 0,4 s | Technik, Bohrbild | **allgemeiner Cache** |
| 3D-Netz (`rohr3d.netz_rechnen`) | 3,2 s (45 s beim Import) | Technik, Profil | offen: groß (Gitter), steckt im Endabfall schon gemerkt |
| Optimierung (Stangen, Schnittschema) | – | | steht schon in der Datenbank (`angebote.ergebnis`) |
| Materialpreise, Zukauf, Normteile, Stammdaten | – | | bleiben in der Datenbank (maßgeblich, Merker #572 im Speicher) |
| Positionstabelle, Angebotsliste | – | | kurzlebig: Reiterwechsel lädt nicht neu (#572) |
| PDF-Vorbereitung, Stückliste | – | | nutzen die gemerkte Kalkulation |
| STEP-Vormessung, Vorschaubilder | – | | eigener Cache (#559) |

Die Unterscheidung nach Patricks Punkt 2 sieht so aus:
- **Dauerhaft im Cache:** reine Rechnungen, die teuer sind und deren Ergebnis allein von den Eingaben abhängt.
- **Kurzlebig, nur im Speicher:** Tabellenanzeige und Zwischenwerte einer Rechnung (`rechnen.merker`).
- **Direkt aus der Datenbank:** alles Verbindliche, also Angebote, Kunden, Stammdaten, Preise und Optimierung.

## 2. Cache-Dateien

Der Cache liegt lokal auf jedem PC neben der Datendatei:

```
Daten/Rechenmerker/
├── rechenmerker.db          allgemein: Schneidfolge, Endabfall, Fertigungsprüfung, Sechskant/Senkung
└── Angebote/
    └── A<Angebots-ID>.db    je Angebot: Bereiche „Kalkulation“ und „Schnittzeiten je Position“
```

Jede Datei ist eine SQLite-Datei mit zwei Tabellen:
- **`kopf`** entspricht dem manifest.json aus Patricks Beispiel: Angebots-ID, Angebotsnummer, Programmversion,
  Cache-Schema, angelegt, zuletzt benutzt.
- **`merker`** hat die Spalten Bereich, Schlüssel, Art, Wert, Programmversion, Rechendauer und Zeit.

Statt einer Datei je Bereich (kalkulation.cache, geometrie.cache …) gibt es eine Datei je Angebot mit Bereichen.
Grund: Eine SQLite-Datei schreibt jeden Eintrag atomar und übersteht einen Programmabsturz (WAL). Viele lose Dateien
könnten halb geschrieben zurückbleiben.

Es entsteht nur, was gebraucht wird: Eine Angebotsdatei gibt es erst, wenn das Angebot gerechnet wurde.

**Ort:** Die Datei liegt bewusst nicht im Angebotsordner auf dem Netzlaufwerk und nicht in PostgreSQL. Patrick hat
dafür die Dauerfreigabe gegeben, umgesetzt ist die Empfehlung.
- SQLite über ein Netzlaufwerk ist bei 10 bis 25 Plätzen sperr- und fehleranfällig.
- Die PPEASE-Angebotsordner legt das Programm nie selbst an.
- Ein Cache in der Hauptdatenbank würde genau die Datenbank belasten, die entlastet werden soll.
- Weil jeder Eintrag über Prüfsummen reproduzierbar ist, rechnet jeder PC ein Angebot höchstens einmal.

## 3. Architektur

- **Schlüssel** sind SHA-256-Prüfsummen über alle Eingaben einer Rechnung, die Programmversion und das Cache-Schema.
  Das deckt Patricks Punkt 10 ab: Angebots-ID, Bauteil (Inhalt der Position), Eingabedaten, Parameter,
  Material- und Maschinenversion (Inhalt der Stammdaten), Logikversion (Programmversion), Schema und Zeitstempel.
- **Abhängigkeiten:**
  - Der Schlüssel enthält genau die Eingaben, die eine Rechnung liest. Ändert sich eine Eingabe, findet der Cache
    nichts mehr, und genau diese Rechnung läuft neu.
  - Die Schnittzeit liest keine Materialpreise (Preisliste, Tonnenpreis, Teuerung). Deren Änderung rechnet darum nur
    die Kalkulation neu.
  - Kopffelder, die die Schnittzeit nicht liest (Optimierergebnis, Stand, Verkaufspreis …), stehen nicht im Schlüssel.
  - Beides prüft ein Test.
- **Veraltete Ergebnisse** können nicht in die Kalkulation kommen, aus zwei Gründen:
  - Jede Änderung einer Eingabe ergibt einen anderen Schlüssel.
  - Ein Softwareupdate ändert die Version im Schlüssel.
- **Typgenaue Ablage:**
  - Tupel, Zahlen-Schlüssel, Decimal, -0.0, inf und nan bleiben genau, was sie waren.
  - Was sich nicht genau ablegen lässt, wird nicht gemerkt.
  - Ein gelesener Wert wird auf seine Form geprüft, bevor er benutzt wird.
- **Komprimierung:** Werte über 2 KB werden mit zlib komprimiert.
- **Asynchrones Speichern:**
  - Ein Hintergrund-Faden schreibt gesammelt in einer Transaktion. Lesen sieht noch nicht geschriebene Werte.
  - `leeren()` wartet, bis alles geschrieben ist: beim Schließen eines Angebots und am Programmende.
  - Die Oberfläche wartet nie auf das Schreiben.
- **Fehler:**
  - Eine beschädigte Datei wird ersetzt, ein unlesbarer Eintrag gelöscht.
  - Ist der Ordner nicht nutzbar, gibt es eine Warnung im Protokoll, und das Programm rechnet ohne Cache.
  - Die Hauptdatenbank wird nie berührt.

## 4. Speicher je Angebot

Gemessen am Beispielangebot mit 38 Positionen, nach drei Messläufen mit Zellen ändern, Optimieren und PDF:

| Bereich | Einträge | Größe |
|---|---|---|
| Kalkulation (begrenzt auf die 40 neuesten je Angebot) | 40 | 0,7 MB komprimiert |
| Schnittzeiten je Position | 293 | 0,27 MB |
| allgemein (Schneidfolge, Endabfall, Fertigungsprüfung, Sechskant/Senkung) | etwa 240 | unter 0,1 MB |

Die Grenzen sind:
- 20.000 Einträge je Angebot,
- 50.000 in der allgemeinen Datei,
- 1 GB für alle Angebote zusammen (die am längsten unbenutzten fallen weg),
- 180 Tage ohne Benutzung (dann wird die Datei entfernt).

## 5. und 7. Eingesparte Berechnungen und Trefferquote

Beim erneuten Öffnen nach einem Neustart kommen alle Kalkulationen, Schnittzeiten und Prüfstatus des unveränderten
Angebots aus dem Cache, die Trefferquote liegt also bei 100 %. Im Regressionstest wurden alle 20 Kalkulationen aus
dem Cache geladen.

Im Programm zeigt **Hauptadmin → Angebots-Cache …** die Kennzahlen seit dem Programmstart:
- Berechnungen gesamt, aus dem Cache geladen, neu berechnet,
- Trefferquote, eingesparte Berechnungen,
- eingesparte Rechenzeit (die Dauer der ursprünglichen Rechnung wird mitgespeichert), Ladezeit,
- Dateien und Größe.

Die Rechenzähler (Diagnose) zeigen dasselbe je Bereich. Sie stehen auch im Support-Paket (diagnose.txt).

## 6. Leistung vorher und nachher

Gemessen im Container mit SQLite, Angebot mit 33 STEP-Teilen und 38 Positionen, jeweils in einem frischen Prozess
(wie nach einem Neustart):

| Vorgang | 0.9.400 (vor dem System-Update) | 0.9.402 (#572) | mit Angebots-Cache, 1. Start nach Update | mit Angebots-Cache, ab 2. Start |
|---|---|---|---|---|
| Angebot öffnen | 4,03 s | 2,90 s | 4,69 s | **0,58–0,62 s** |
| Angebot neu laden (warm) | 0,67 s | 0,55 s | 0,34 s | 0,31–0,36 s |
| Zelle ändern + Angebots-Check | 2,80 s | 2,59 s | 1,59 s | 1,00–1,06 s |
| Optimieren | 1,32 s | 1,04 s | 0,50 s | 0,49–0,61 s |
| Angebots-PDF | 3,53 s | 2,77 s | 2,06 s | 1,29 s |
| Werkstatt-PDF | 2,17 s | 2,17 s | 1,73 s | 1,13–1,34 s |

Der erste Start nach einem Update rechnet einmal alles neu und legt es ab. Das kostet etwa so viel wie vorher.

Der Fingerabdruck des ganzen Angebots ist in allen Läufen identisch: 24f6b5eb0cdead13 nach dem Öffnen und
e4dc67a5a137682d nach Zelle ändern, Optimieren und PDF. Diese Werte gelten auf dem Stand 0.9.401 bzw. 0.9.402, also
mit dem gewollten „Entladen höchstens 5 s“ aus #569.

## 8. Verhalten bei Änderungen

Alle Fälle sind in `tests/test_angebots_cache.py` geprüft. Jeder wird mit einer vollständigen Neuberechnung ohne
Cache verglichen (typgenau, `repr`).

| Änderung | neu gerechnet | aus dem Cache |
|---|---|---|
| Länge eines Bauteils | Schnittzeit dieses Bauteils, Kalkulation | Schnittzeiten der übrigen Bauteile |
| Stückzahl mehrerer Bauteile | deren Schnittzeiten (Stück steht in der Position), Kalkulation | übrige |
| Materialpreis (Preisliste, Tonnenpreis) | Kalkulation | alle Schnittzeiten |
| Maschinenparameter (Vorschub, Beschleunigung) | alle Schnittzeiten, Kalkulation | |
| Kontur entfernt | Schnittzeit dieses Bauteils, Kalkulation | übrige |
| Optimierergebnis, Stand, Verkaufspreis im Kopf | Kalkulation | Schnittzeiten |
| Softwareupdate | alles einmal | |

## 9. Mehrbenutzer

- Jeder PC hat seinen eigenen Cache. Es gibt also kein gemeinsames Schreiben, keine Sperrkonflikte über das Netz und
  keine gegenseitige Überschreibung.
- Mehrere Programme auf einem PC teilen die Dateien sicher. SQLite WAL mit Wartezeit schreibt jeden Eintrag atomar.
  Getestet mit vier Prozessen, die gleichzeitig in dieselbe Datei schreiben.
- Ändert ein Kollege ein Angebot oder Stammdaten in der gemeinsamen Datenbank, ändern sich die Eingaben und damit die
  Schlüssel. Der Cache des eigenen PCs rechnet dann neu, mit den Daten aus der Datenbank.
- Ein zentraler Cache (Server oder Datenbank) wurde geprüft und verworfen: Netzlast, Sperren und eine zweite
  Datenquelle. Patricks Frage „damit nicht jeder Arbeitsplatz neu rechnet“ löst stattdessen das **Teilen über den
  gemeinsamen Ordner** (nur wenn Kürzel und gemeinsamer Ordner eingetragen sind):
  - Beim Schließen eines Angebots legt jeder Platz im Hintergrund eine Kopie seiner Angebotsdatei als
    `Rechenmerker/<uid>.<Kürzel>.db` in den gemeinsamen Ordner (Zwischendatei, dann umbenannt; nur wenn sich etwas
    geändert hat). Jeder Platz schreibt nur seine eigene Datei, es gibt keine Sperren und keine Konflikte.
  - Beim Öffnen übernimmt ein anderer Platz aus diesen Kopien die fehlenden Einträge seiner Programmversion. Gelesen
    wird eine lokale Kopie; geprüft werden Datei (quick_check), Schema und jeder Eintrag. Das Öffnen wartet höchstens
    2 s auf das Netz.
  - Sicher, weil der Schlüssel eine Prüfsumme über alle Eingaben ist: ein fremder Eintrag passt nur bei genau gleichem
    Angebot, gleichen Stammdaten und gleicher Version. Die Angebots-ID ist je PC verschieden, darum die feste Kennung
    `uid` im Dateinamen.
  - Beim Start räumt jeder Platz nur seine eigenen Kopien gelöschter Angebote auf.
  - Kennzahlen im Fenster: „Von Kollegen übernommen“, „In den gemeinsamen Ordner gelegt“.

## 10. Testergebnisse

**`tests/test_angebots_cache.py`** (neu, in `tests/alle.py`), alle bestanden:
- Ablage typgenau
- neues Angebot (eigene Datei mit Kopf)
- Neustart (alles aus dem Cache)
- ein Bauteil bzw. mehrere Bauteile ändern
- Materialpreis, Kopffelder, Maschinenparameter und Geometrie ändern
- Datei beschädigt, gelöscht, unlesbarer Eintrag
- Ordner verschwunden (Netz unterbrochen)
- vier Programme gleichzeitig
- Programm beim Schreiben beendet
- Softwareupdate
- Bereichsgrenze
- Verwaltung: Export, Aufräumen gelöschter und lange unbenutzter Angebote
- Kennzahlen, Diagnose, Fenster

**`tests/test_regression_ergebnisse.py`:** Ein dritter Lauf wie nach einem Neustart lädt alle 20 Kalkulationen aus
dem Cache. Sie sind typgenau gleich der vollen Neuberechnung und gleich dem gespeicherten Stand.

**Betroffene vorhandene Tests** sind grün, unter anderem:
- dfm, Zusatzerkennung, Schneidfolge, Laserzeit
- Kalkulationsmerker, Doppelrechnung, Diagnose, Tempo
- Support 19.11., Zeitbild, Staffelpreise, Maschine je Position, Teuerung, Meterpreis
- Kopfweg, 3D-Editor, Anleitung, Protokoll (keine neue stille Ausnahme)

`test_angebot_leistung` hält die Zeitgrenze „Zelle ändern 1,0 s“ im Container auch auf main ohne diese Änderung nicht
(1,0 bis 1,1 s). Die Prüfung in GitHub entscheidet.

## 11. Offene Optimierungen

- **3D-Netz** (`rohr3d.netz_rechnen`): 45 s beim Import von 33 Teilen. Es ist groß (Gitter) und wird für Ansicht und
  Endabfall gebraucht. Ein Merker als komprimiertes Gitter ist möglich, muss aber erst auf Speicherbedarf geprüft
  werden.
- **STEP-Import:**
  - 3D-Gegenprobe (60 s, mit #569 auf Hilfsprozessen)
  - `schnittkoerper._deckel/drin` (17 s)
  - Maschinenvergleich nach dem Import (abschaltbar, #569)
- **Hauptfenster-Aufbau:** 1,4 bis 1,5 s, alle Tabellen werden sofort gebaut.
- **Vorladen im Hintergrund:** Die zuletzt benutzten Angebote könnten nach dem Start im Hintergrund vorgeladen werden.
  Das ist heute nicht nötig, weil das Öffnen aus dem Cache unter einer Sekunde liegt.
