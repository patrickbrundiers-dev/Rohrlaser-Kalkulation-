# Software-Audit 26.11.2026: Codequalität, Architektur, Stabilität, Leistung

Auftrag Patrick 26.11.2026 05:07 UTC (Master-Prompt „Vollständiger Software-Audit“). Stand main 0.9.514 (Schema 107),
Ergebnis 0.9.515. Baut auf der Systemprüfung 17.11. ([AUDIT_REPORT.md](AUDIT_REPORT.md)), der Generalüberholung
24.11. ([GENERALUEBERHOLUNG_2411.md](GENERALUEBERHOLUNG_2411.md)) und der Gesamtprüfung 25.11.
([GESAMTPRUEFUNG_2511.md](GESAMTPRUEFUNG_2511.md)) auf; was dort geprüft und belegt ist, wird nicht wiederholt.
Schwerpunkt dieses Audits: Redundanz, Architektur (Modultrennung), Stabilität bei paralleler Rechnung, Tests.

Grundregeln: Rechenergebnisse ändern sich nicht (Regressionstest, Fingerabdruck des Systemchecks); keine Funktion wird
ohne Nachweis entfernt; jede Aussage mit Datei und Funktion belegt.

## 1. Gesamtbewertung

Der Rechenkern ist in gutem Zustand: Ergebnisse sind reproduzierbar (Regressionstest, Cache-Gleichheit), auch bei
paralleler Rechnung in mehreren Threads (neu nachgewiesen), alle Klicks liegen unter 0,4 s, die Datenbank öffnet in
0,2 s. Die Schwächen liegen in der **Struktur**, nicht in den Ergebnissen:

| Bereich | Bewertung | Kennzahl |
|---|---|---|
| Rechenergebnisse | sehr gut | 20 Regressionsangebote bitgleich, 1.320 Parallelrechnungen ohne Abweichung |
| Stabilität | gut | 0 Ausnahmen im Belastungstest, Speicher im Langzeitlauf flach (25.11.) |
| Leistung | gut, außer Software-3D | jeder Klick < 0,4 s; Software-3D beim Drehen bis 0,5 s je Bild (jetzt ≤ 0,1 s) |
| Architektur | mittel | 638 Module flach in einem Paket; 508 von 687 Modulen über Importe in Funktionen zu einem Knäuel verbunden |
| Redundanz | mittel | dieselbe Zahl-Hilfsfunktion 77-mal in 11 Fassungen |
| Wartbarkeit | mittel | 39 Funktionen über 200 Zeilen, angebot_fenster.py 11.537 Zeilen |
| Tests | gut | 595 Testskripte, CI auf PostgreSQL; neu: Architektur- und Paralleltest |

## 2. Vorgehen und Messwerkzeuge

| Prüfung | Werkzeug | Umfang |
|---|---|---|
| Statische Analyse | eigenes AST-Skript (Importgraph mit Tarjan-Zyklen, Funktionsgrößen, AST-Duplikate, except-Klauseln, Threads, SQL in Schleifen) | alle 687 Module, 313.841 Zeilen, 16.580 Funktionen |
| Toter Code | vulture 60 %, jeder Fund gegen programm/, tests/, werkzeuge/, Workflows, .spec und getattr-Muster gegengeprüft | 154 Kandidaten |
| Verhalten gleichnamiger Hilfen | jede Modulfunktion `_n`, `_z`, `_zahl` mit 12 Grenzwerten aufgerufen | 166 Funktionen |
| Kern ohne Oberfläche | jedes Kernmodul im eigenen Prozess geladen, danach `PySide6`/`OCP` in sys.modules? | 27 Module + volle Rechnung |
| Parallel | dieselben 11 Regressionsangebote in 8 Threads × 15 Runden, ein Thread leert laufend alle Merker, Threadwechsel alle 10 µs | 1.320 Rechnungen |
| Programmabläufe | werkzeuge/systemcheck.py alt/neu, Fingerabdruck der Ergebnisse | 22 Vorgänge |
| Datenbank | 3.000 Angebote, 9 typische Vorgänge, pg_stat_user_tables (volle Durchläufe) | PostgreSQL 16 |
| Software-3D | zeichnen() mit cProfile und Stückzählung | Einzelteil, Baugruppe 7 und 25 Teile |
| Testsuite | tests/alle.py vorher und nachher | 595 bzw. 596 Tests |

## 3. Befunde

### P0 – kritisch
Keine. Kalkulation, Daten und Sicherheit ohne neuen Befund (Sicherheit: siehe 17.11., SEC-01/02 behoben).

### P1 – hoch

| Nr. | Fundstelle | Befund | Auswirkung | Stand |
|---|---|---|---|---|
| A-01 | `herkunft.merkmal_sicherheit` → `teile_editor`; `step`, `rahmen`, `cam_paket`, `nesting_abwicklung`, `step_gegenprobe`, `step_viewer`, `bauteil_generator`, `materialanfragen`, `schnellimport`, `bg_schwerpunkt`, `werkzeug_koerper` → `ansicht3d`; `stammdaten`, `eingabe` → `rechenfeld`; `datenbank` → `schneiddaten_standard`; `nesting_abwicklung` → `stangen_ansicht` | Rechen- und Datenmodule holten reine Funktionen bzw. Konstanten aus **Oberflächen-Modulen** (PySide6). Nachweis: alter Stand, `herkunft.merkmal_sicherheit("STEP")` lädt PySide6 und den ganzen Teile-Editor | Rechenkern nicht unabhängig testbar; eine Änderung an einem Fenster konnte die Rechnung brechen; Hintergrundrechnung zog Qt-Objekte nach | **behoben**: 5 neue Qt-freie Module (`netz_daten`, `teile_status`, `rechenformel`, `schneiddaten_werte`, `stangen_bereiche`); die alten Module führen alle Namen weiter (Aufrufer unverändert). Importe Qt-frei → Oberfläche 56 → 41 |
| P-01 | `ansicht3d.zeichnen` (`_sortier_teile`) | Software-3D (ohne OpenGL, z. B. Remote-Desktop): auch beim Drehen mit der Maus wurde jedes Dreieck fürs Sortieren fein geteilt; eine Baugruppe aus 7 Rohren = 1.610 sichtbare Dreiecke → 85.610 Stücke je Bild | Drehen ruckelt (0,3–0,54 s je Bild), obwohl die grobe Stufe greift (die Teilung, nicht die Dreieckszahl, war der Engpass) | **behoben**: nur während der Bewegung Stücke 3× so lang (`SORTIER_GROB`); Stillstand bildgleich (Test vergleicht die Bilder). Messwerte Abschnitt 5 |

### P2 – mittel

| Nr. | Fundstelle | Befund | Auswirkung | Stand |
|---|---|---|---|---|
| R-01 | 77 Module mit eigener `_n`, 56 mit `_zahl`, 33 mit `_z`, 24 mit `_jetzt` | gleiche Aufgabe, viele Kopien: `_n` in **11 verschiedenen Verhalten** (Text „1.5“ → 0,0 in 34 Modulen, → 1,5 in 13 Modulen; None ↔ 0,0), `_zahl` in 30 | eine Korrektur trifft nur eine Kopie; neue Module wählen zufällig eine Fassung | **teilweise behoben**: die wörtlich gleichen Kopien (80 Stellen) binden `rohrlaser/zahlen.py` ein (bitgleich); abweichende Fassungen bleiben bewusst (Vereinheitlichen würde Ergebnisse ändern). Sperre im Test: keine neue Kopie |
| A-02 | Importgraph | 508 von 687 Modulen sind über Importe in Funktionen zu einem einzigen Zyklus verbunden (z. B. `rechnen > ausgabe > herkunft > teile_editor > schneidweg_dialog > fenster > angebot_fenster`); auf oberster Ebene 0 Zyklen | Module lassen sich nicht einzeln herauslösen; Importe in Funktionen verstecken Abhängigkeiten | Kette von `rechnen` zur Oberfläche durch A-01 unterbrochen; Sperrklinke im Test (höchstens 46 Importe Qt-frei → Oberfläche). Rest: Roadmap |
| D-01 | `datenbank.position_neu` | Positionsnummer `MAX(nr)+1` vor der Transaktion gelesen (G-08 vom 25.11.) | zwei Schreiber auf eine Datenbank hätten dieselbe Nummer ziehen können | **behoben**: erst das Angebot sperren (UPDATE), dann Nummer und Einfügen in derselben Transaktion |
| D-02 | `datenbank.angebote` | Angebotsliste zählt Positionen und Teile je Aufruf über die ganze Tabelle `positionen`; Suche mit `LIKE '%…%'` kann keinen Index nutzen | 3.000 Angebote: Liste 31 ms, Suche 48–65 ms; bei 10.000 Angeboten rund dreimal so viel | offen, Empfehlung Roadmap (Zähler im Angebot oder pg_trgm) |
| C-01 | toter Code | nachweislich nirgends benutzt (auch nicht per getattr, Test, Werkzeug, Workflow): `nesting_3d.py` (ganzes Modul, ersetzt am 24.11. durch Ansicht3DMitKnoepfen), `anfragen_dokumente.KundeDialog`, `schnitt_explosion.explodieren`, `kunden_daten.naechste_kundennr` (seit Patricks Regel 23.11. „Kundennummer immer von Hand“ tot), `export.profirst_schreiben`, `rp_profile.schnitt_aus_messung`, `artikelnr.hat_anhang`, `nesting_abwicklung_bild.bild_pfad`, `step_abwicklung._punkt_in`, `step_biegerohr.tangente_ende` | Pflege- und Leseaufwand, Verwechslungsgefahr | **entfernt** (rund 345 Zeilen) |
| C-02 | unbenutzt, aber fachlich angelegt | `austausch_dateien.versionen_groesse` (Hinweis ab VERSIONEN_HINWEIS_MB erscheint nie), `austausch_zuordnung.alle_anwenden` (Knopf „Zuordnung erkennen“ fehlt), `vorschlaege_mixin.zielpreis_menge`, `rahmenauftrag.position_entfernen`/`los_stornieren`, `lizenz.hauptadmin_entfernen`, `datenbank.neu_oeffnen`, `pg_lokal.verwalter_zugang` | Funktion vorhanden, aber nicht erreichbar | bewusst **nicht** entfernt: Entscheidung, ob anbinden oder löschen, bei Patrick (Roadmap) |

### P3 – niedrig

| Nr. | Befund | Stand |
|---|---|---|
| W-01 | 39 Funktionen über 200 Zeilen, 160 über 100; größte: `angebot_fenster.__init__` 668, `step_geometrie._profil_messen_kern` 638, `step_dialog.__init__` 559, `rechnen._kalkulation` 553, `step.uebernehmen` 528 | offen (Umbau nur mit fachlichem Anlass, Regel CODE-02) |
| W-02 | 638 Module flach im Paket `rohrlaser` (keine Unterpakete Kern/UI/Import/DB) | Zielarchitektur Abschnitt 6 |
| W-03 | 826 `except Exception`, davon 72 still (Grenze im Test test_protokoll_kontext seit 17.11.) | unverändert, Grenze hält |
| W-04 | bewusste Kopien mit Gleichheitstest: `bpf_xml` ↔ `step_messung/step_blm` (5 Funktionen, getrennte Prozesse), `aktualisierung.stand_text` ↔ `update.stand_text` (Auslastung darf die Kalkulation nicht importieren) | bleibt (begründet) |
| W-05 | kleine Doppelungen in der Oberfläche: `ek_import_assistent`/`kunden_import_assistent` (`__init__` gleich), `csv_import.spalte`/`kunden_csv.spalte`, `zukauf_seite`/`zusatz_verwaltung` (`_zeile`, `_frage`) | offen, beim nächsten Umbau zusammenlegen |
| G-07 | rohr3d MemoryError bei absurden Maßen (25.11.) | mit Ø 10⁹, Langloch 10⁹ und Rechteck 10⁹ **nicht nachgestellt** (Kontur wird vorher verworfen); bleibt offen, keine Änderung ohne Nachweis |

### Ohne Befund geprüft
- **Parallele Rechnung** (Frage aus dem Auftrag: „können parallele Berechnungen zu falschen Ergebnissen führen?“):
  Optimieren, Staffeln und Maschinenvergleich laufen im Programm in Threads, während die Oberfläche rechnet
  (`angebot_fenster._mv_hintergrund`, `optimieren`, `staffel_seite`). 8 Threads × 15 Runden, Merker laufend geleert:
  1.320 Rechnungen, **0 Abweichungen, 0 Ausnahmen**. Gemeinsame Merker (`rechenmerker`, `dynamik._FOLGE_MERK`,
  `rechnen._KALK_MERK`) halten.
- Gemeinsamer Lage-Merker der Baugruppen-Ansicht (`_lage_merker`): las seine Größe je Aufruf über alle Einträge, ohne
  Sperre. Jetzt mit Sperre und mitgezähltem Stand (bitgleich, kein Fehler nachgestellt, vorbeugend).
- Datenbankzugriff aus Threads: Sicherung nutzt eine eigene zweite Verbindung (`SicherungLauf`), Austausch liest nur
  Dateien; keine gemeinsame Verbindung über Threads gefunden.
- Kern-Module ohne OpenCascade: alle 27 laden ohne OCP (die STEP-Messung läuft in eigenen Prozessen).

## 4. Umgesetzte Verbesserungen (0.9.515)

| Änderung | Dateien | Nachweis |
|---|---|---|
| A-01 Rechenkern Qt-frei | neu `netz_daten.py`, `teile_status.py`, `rechenformel.py`, `schneiddaten_werte.py`, `stangen_bereiche.py`; 15 Aufrufer umgestellt; `ansicht3d`, `teile_editor`, `rechenfeld`, `schneiddaten_standard`, `stangen_ansicht` führen die Namen weiter | test_architektur_2611 Teil 1–2 |
| P-01 Software-3D beim Drehen | `ansicht3d.zeichnen(sortier_grob=…)`, `SORTIER_GROB`, `Ansicht3D.paintEvent` | Test: Stillstand bildgleich, ≤ ½ Stücke |
| R-01 gemeinsame Hilfsfunktionen | neu `zahlen.py`; 80 Kopien in 77 Modulen ersetzt | Test: keine neue Kopie; Regression bitgleich |
| D-01 Positionsnummer in der Transaktion | `datenbank.position_neu` | Testsuite |
| C-01 toter Code | 9 Funktionen/Klassen, Modul `nesting_3d.py` | Suche über Code, Tests, Werkzeuge, Workflows |
| Lage-Merker threadsicher | `netz_daten._in_lage` | Paralleltest |
| Tests | neu `tests/test_architektur_2611.py` (in tests/alle.py) | grün |

## 5. Messungen vorher/nachher

**Programmabläufe** (werkzeuge/systemcheck.py, 7 Test-STEPs, Container ohne GPU, je ein Lauf): Fingerabdruck aller
Ergebnisse **gleich**, SQL-Anweisungen je Vorgang gleich (Angebot öffnen 63/64 durch die Transaktion in
position_neu). Zeiten im Rahmen der Streuung gleich (Programmstart 0,80 → 0,45 s, Datendatei öffnen 1,74 → 1,44 s,
STEP-Import 3,49 → 3,38 s, PDF 0,15 → 0,14 s).

**Software-3D** (1400 × 900, Median je Bild, beim Drehen):

| Modell | vorher | nachher | Gewinn |
|---|---|---|---|
| Einzelrohr QR 60×3, 1.900 mm | 141 ms | 29 ms | −79 % |
| Baugruppe 7 Rohre | 301 ms | 102 ms | −66 % |
| Baugruppe 25 Rohre | 538 ms | 56 ms | −90 % |

Ursache laut cProfile (7 Rohre, 3 Bilder): `_sortier_teile` 169.610 Aufrufe, 85.610 gezeichnete Stücke; Bild im
Stillstand unverändert (neue Bilder nur während der Bewegung).

**Datenbank** (PostgreSQL 16, 3.000 Angebote, 15.000 Positionen, Median): Angebotsliste 31 ms, Suche 48–58 ms,
Angebot öffnen 1,0 ms, Position ändern 1,4 ms, Position neu 1,4 ms (vorher 1,9 ms), Phase je Anfrage 0,6 ms.
Volle Durchläufe nur bei `positionen`/`angebote` (Liste, Suche, D-02); Stammdatentabellen klein.

**Tests**: vorher 592 von 595 grün, 3 rot nur durch den Container (OpenGL ohne xcb-cursor: test_ansicht_gl,
test_schnittkoerper; Schriftgröße 12 px: test_bedienung_0611 – wie am 25.11.). Nachher siehe Pull Request.

## 6. Zielarchitektur (Empfehlung, schrittweise)

Ziel: neue Funktionen ergänzen, ohne bestehende zu beschädigen. Schichten, Abhängigkeit nur nach unten:

1. **Kern** (ohne Qt, ohne OCP): Rechnung, Optimierung, Schneidweg, Fracht/Packen, Stammdaten-Modelle, Zahlen.
2. **Daten**: Datenbank, Migrationen, Abgleich, Sicherung (ohne Qt).
3. **Import/Geometrie**: STEP-Messung (eigene Prozesse, OCP), DXF, BPF/LST, Netzdaten.
4. **Dienste**: PDF/Dokumente, Mail/Outlook, Austausch, KI (lokal).
5. **Oberfläche** (Qt): Fenster, Dialoge, 3D-Ansicht.

Weg dorthin ohne Bruch: (a) Sperrklinke im Test senkt die Zahl der Importe Kern → Oberfläche Stück für Stück (jetzt
41); (b) neue Module nach Schicht benennen bzw. später in Unterpakete verschieben, alte Namen als Weiterleitung
behalten; (c) große Fenster (angebot_fenster) in Bereiche nach dem Muster der Mixins teilen, nur beim fachlichen Umbau.

## 7. Roadmap (priorisiert)

| Prio | Schritt | Nutzen | Aufwand |
|---|---|---|---|
| 1 | Sperrklinke Kern → Oberfläche weiter senken (41 → 0), je Fund eine Qt-freie Datei | Kern unabhängig testbar | klein je Schritt |
| 2 | D-02: Positionszahl/Teile im Angebot mitführen oder Teilindex (pg_trgm) für die Suche | Liste/Suche bei 10.000+ Angeboten < 30 ms | mittel, Schema +1 mit Sicherung |
| 3 | C-02: Patrick entscheidet je Funktion „anbinden“ oder „löschen“ | keine halbfertigen Wege | klein |
| 4 | R-01 Rest: abweichende Fassungen von `_n`/`_zahl` fachlich prüfen und benennen (z. B. `text_als_zahl`) | einheitliches Zahlenlesen | mittel, mit Regressionstest |
| 5 | W-01: `angebot_fenster.__init__`, `step.uebernehmen`, `rechnen._kalkulation` beim nächsten fachlichen Umbau teilen | Lesbarkeit, kleinere Änderungsflächen | groß |
| 6 | Feldtest 10–25 Plätze am echten Netzlaufwerk (bisher nur Lasttest) | Sicherheit im Echtbetrieb | Patrick |

## 8. Nicht prüfbar im Container
Windows-Build und Startzeit unter Windows, OpenGL-3D (keine GPU), Outlook per COM, echte Kunden-STEPs und echtes
Netzlaufwerk mit mehreren PCs (wie am 25.11.).
