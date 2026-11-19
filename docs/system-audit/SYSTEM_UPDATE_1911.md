# Großes System-Update (Auftrag 19.11.2026, Version 0.9.402)

Patrick hat am 19.11.2026 eine vollständige Analyse und Modernisierung beauftragt: doppelte und unnötige
Berechnungen, zeitaufwendige Abläufe, Stabilität, Datenbank und Mehrbenutzerbetrieb, Tests und einen Abschlussbericht
mit Messwerten. Die wichtigste Regel war, dass Funktionen, Rechenergebnisse und Abläufe gleich bleiben.

Der Bericht baut auf den früheren Prüfungen auf und wiederholt sie nicht: Systemprüfung 17.11. (#545 bis #553,
AUDIT_REPORT.md und folgende), Stabilität 18.11. (#561, #566, #567, STABILITAET_1811.md), Tempo #555 und das
Supportpaket vom 19.11. (#569: Kalkulationsmerker, Maschinenvergleich abschaltbar, Entladen höchstens 5 s).

## 1. Bestandsaufnahme

Grundlage war Patricks Support-Paket vom 19.11., 15:24 Uhr (Windows, PostgreSQL, 0.9.399, Zusammenarbeit aus):

| Befund aus dem Paket (8 h 28 min Arbeit) | Wert |
|---|---|
| Datenbank-Anweisungen | 177.657, zusammen 251,8 s |
| Kalkulationen | 998, davon 58 doppelt (behebt #569) |
| Maschinenvergleich | 177×, 312 s (abschaltbar mit #569) |
| Klick auf einen Reiter | 139× bis 1,2 s |
| Stocken bei „Angebote“ | 0,6 bis 1,0 s alle 30 s |
| Dialog „Neue Position Rohr/Profil“ | 1,4 s |

Gemessen wurde zusätzlich im Container (4 Kerne, Qt offscreen) mit einem echten Angebot aus dem Support-Paket (33
STEP-Dateien, 38 Positionen; die Dateien liegen nicht im Repository), einmal mit SQLite und einmal mit PostgreSQL 16.

## 2. Ursachen

- **Reiterwechsel:** Jeder Wechsel zwischen Angebotsliste und Angebot lud das Angebot vollständig neu, auch ohne
  Änderung (0,7 bis 0,9 s).
- **Einstellungen:** `Datenbank.einstellung()` las bei jedem Aufruf aus der Datenbank. Eine Kalkulation fragt
  Dutzende Einstellungen ab, die Anfragen-Liste je Zeile mehrere. Das ergab beim Öffnen des Hauptfensters über
  1.000 Anweisungen.
- **Stocken alle 30 s:** Der Takt der Anfragen-Liste baute bei jedem Aufruf eine neue `OrdnerAblage` auf. Deren
  Zwischenspeicher war darum immer leer, und alle Akten wurden neu gelesen: bei 300 Akten 803 geöffnete Dateien und
  3.659 Einstellungs-Abfragen je Takt.
- **Nach jedem Neustart** rechnete das Programm reine Rechnungen neu, vor allem die Schneidfolge je Teil und
  Maschine. Beim Öffnen eines Angebots mit 33 STEP-Teilen war das gut die Hälfte der Zeit.
- **Lebenszeichen:** Die Hauptdatei wurde in jedem Takt geöffnet, auch ohne Änderung.

## 3. Umgesetzt

| Bereich | Änderung | Datei |
|---|---|---|
| Reiterwechsel | Neu laden nur, wenn sich Stammdaten, Angebote, Datenbank, Tag oder Kollegen geändert haben oder 5 min vergangen sind | fenster.py, angebot_fenster.py |
| Einstellungen | Einmal gelesen und gemerkt. Gültig, solange die Datenbank unverändert ist. SQLite prüft das über `data_version` und `total_changes`, PostgreSQL über die Stand-Zähler (höchstens alle 0,25 s). Ein Rollback leert den Merker. Jeder Aufruf bekommt ein frisches Objekt. | datenbank.py, db_verbindung.py |
| Anfragen-Takt | Eine Ablage je Ordner und Platz, die über Takte hinweg bestehen bleibt. Jede Zeile wird einmal ausgewertet. | anfragen_akten.py, anfragen_seite.py |
| Zusatzarbeiten-Erkennung | Sechskant und Senkung werden je Technik und Bohrbild gemerkt (bis 4.000 Einträge) | zusatz_erkennung.py |
| Merker über den Neustart | Neue Datei `Daten/Rechenmerker/rechenmerker.db` für Schneidfolge und Endabfall. Der Schlüssel ist eine SHA-256-Prüfsumme über alle Eingaben und die Programmversion. Ein gelesener Wert wird vor der Nutzung geprüft. Bei einem Fehler ist der Merker aus, es kommt eine Warnung ins Protokoll und das Programm rechnet ohne Merker. | dauermerker.py, dynamik.py, zeit_zusatz.py |
| Lebenszeichen | Die Hauptdatei wird nur bei einer Änderung geöffnet (mtime, Größe, 5-min-Takt) | teilen.py |
| Diagnose | Neue Zeilen „Reiterwechsel ohne Neuladen“ und „Über Neustart gemerkt“ in den Rechenzählern | diagnose.py |

Dabei gilt:
- An den Formeln wurde nichts geändert.
- Es gibt keine stillen `except: pass`. `test_protokoll_kontext` prüft das weiterhin.
- Ein Merker liefert nur, was auch eine neue Rechnung ergibt. Fehlt er oder ist er ungültig, rechnet das Programm neu.

## 4. Ergebnisse bleiben gleich

- **Fingerabdruck** über das ganze Angebot (Positionen, Status, Meterpreise, Kalkulation). Er wurde vor und nach
  jedem Schritt gebildet und ist identisch: 9442a92dc1b9523f nach dem Öffnen und 08036bc9fd66fdd6 nach Zelle ändern,
  Optimieren und PDF. Das gilt für SQLite und PostgreSQL.
- **Neuer Regressionstest** `tests/test_regression_ergebnisse.py`:
  - Er rechnet 20 feste Angebote: die Abnahme-Angebote sowie Rohre mit Konturen, Gehrung, Sattel und Gravur auf T11
    und LT7, jeweils mit den Staffeln 1, 10 und 100.
  - Jede Zahl wird auf 6 Nachkommastellen mit `tests/daten/regression_ergebnisse.json` verglichen.
  - Jedes Angebot wird zweimal gerechnet, beim zweiten Mal mit leeren Merkern. Beide Läufe müssen bitgleich sein.
  - Der Test läuft in `tests/alle.py` und damit vor jedem Release.
- **Prüfung gegen den alten Stand:**
  - Der Vergleichsstand wurde zuerst mit dem alten Programm (0.9.400) erzeugt. Das neue Programm rechnete alle 20
    Angebote gleich.
  - Nach dem Einarbeiten von #569 (Entladen höchstens 5 s, eine gewollte Änderung) ändern sich 365 Werte.
  - Der Vergleichsstand wurde deshalb mit dem reinen main 0.9.401 ohne dieses Update neu erzeugt. Dieses Update
    rechnet ihn bitgleich nach.

## 5. Leistung vorher und nachher

Gemessen im Container mit SQLite, Angebot mit 33 STEP-Teilen und 38 Positionen:

| Vorgang | vorher (0.9.400) | nachher | Änderung |
|---|---|---|---|
| Hauptfenster öffnen, Datenbank-Anweisungen | 1.083 | 292 | −73 % |
| Angebot neu laden, Anweisungen | 145 | 51 | −65 % |
| Zelle ändern + Angebots-Check, Anweisungen | 296–311 | 129 | −57 % |
| Angebots-PDF, Anweisungen | 250 | 113 | −55 % |
| Reiterwechsel Liste → Angebot | 0,72–0,92 s | 0,003 s | sofort |
| Angebot öffnen nach Neustart (frischer Prozess) | 4,03 s | 2,90 s ab dem 2. Start (4,79 s beim ersten nach dem Update) | −28 % |
| Angebot neu laden, warm | 0,67 s | 0,55–0,63 s | −10 % |
| Anfragen-Takt mit 300 Akten | 604 ms, 803 Dateien geöffnet, 3.659 Abfragen | 194 ms, 0 geöffnet, etwa 0 Abfragen | −68 % |

Mit PostgreSQL (lokal) sieht es ähnlich aus. Weil jede Anweisung dort teurer ist, sparen die weniger gewordenen
Anweisungen auf Patricks PC mehr als im Container. Hochgerechnet auf das Support-Paket (177.657 Anweisungen, 252 s)
entfällt grob die Hälfte bis zwei Drittel der Datenbankzeit. Das ist eine Schätzung aus den Anteilen oben, keine
Messung bei Patrick.

## 6. Stabilität

- Der Merker über den Neustart ist nur ein Zwischenspeicher:
  - Eine beschädigte Datei wird einmal ersetzt.
  - Ist der Ordner gesperrt oder kein Platz frei, ist der Merker für diesen Lauf aus, mit einer Warnung im Protokoll.
  - Ein unpassender Wert, zum Beispiel aus einer fremden Version, wird verworfen und neu gerechnet.
  - Alles ist durch Tests abgedeckt.
- Der Einstellungs-Merker wird bei einem Rollback, bei Änderungen von einem anderen Platz (PostgreSQL-Zähler bzw.
  `data_version`) und bei einer neuen Verbindung ungültig. Getestet sind ein direktes UPDATE, ein Rollback, eine
  zweite Verbindung und eine Veränderung des gelieferten Objekts.

## 7. Datenbank und Mehrbenutzer

- Es gibt keine Schemaänderung (Schema 94).
- Der Einstellungs-Merker erkennt Änderungen anderer Plätze:
  - Bei PostgreSQL über die vorhandenen Stand-Zähler (Trigger).
  - Bei SQLite über `PRAGMA data_version`.
- Der Reiterwechsel lädt neu, sobald sich der Stand der Angebote oder Stammdaten ändert, auch durch einen Kollegen.
- Die Merker-Datei liegt je PC lokal. Es gibt also keinen gemeinsamen Schreibzugriff über das Netz.

## 8. Tests

- Neu sind `tests/test_system_update_1911.py` und `tests/test_regression_ergebnisse.py`, beide in `tests/alle.py`.
- Betroffene vorhandene Tests sind grün, unter anderem:
  - Tempo, Diagnose, Doppelrechnung, Kalkulationsmerker
  - Anfragen (alle), Teilen (alle), Kollegen
  - Datenspeicher, DB-Verbindung, Zusatzerkennung, Schneidfolge, Laserzeit, Anleitung
- `test_angebot_leistung` (Zeitgrenze „Zelle ändern“ 1,0 s) liegt im Container mit dem alten und mit dem neuen Stand
  gleich bei 1,0 bis 1,1 s. Das ist eine Grenze der Maschine, kein Rückschritt. Die Prüfung in GitHub entscheidet.

## 9. Bewusst nicht geändert

Diese Punkte bleiben ohne Änderung, weil sie im Paralleltrack liegen oder die Ergebnisse nicht nachweisbar gleich
blieben:

- **3D-Gegenprobe** `step.rohr_gegenprobe`: 60 s beim Import von 33 Dateien. Das macht #569 mit Hilfsprozessen.
- **Maschinenvergleich nach dem Import:** 23 s, mit #569 abschaltbar.
- **`rohr3d.netz_rechnen`:** 45 s bei 41 Aufrufen. Das ist ein Kandidat für den Angebots-Cache (nächster Schritt).
- **`schnittkoerper._deckel/drin`:** 17 s mit 11 Millionen Punktprüfungen. Eine Optimierung ist möglich, muss aber
  geometrisch bitgleich nachgewiesen werden. Sie bleibt offen.
- **Hauptfenster-Aufbau:** 1,3 bis 1,5 s, alle Tabellen werden sofort gebaut.
- **Dialog „Neue Position“:** 1,4 s.

## 10. Nächster Schritt

Patricks Auftrag „Angebotsbezogene Zwischenspeicherung“ vom 19.11., 16:16 Uhr, baut direkt auf `dauermerker.py` auf.
Geplant ist, die Datei je Angebot zu führen und ihr eine Verwaltung, Kennzahlen und weitere Rechnungen (3D-Netz,
Kalkulation, Material und Maschine) zu geben, statt eine zweite Struktur zu bauen.
