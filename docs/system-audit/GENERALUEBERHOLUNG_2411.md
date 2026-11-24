# Generalüberholung 24.11.2026 – Bestandsaufnahme und Maßnahmen

Auftrag Patrick 24.11.2026 „MASTER-ENTWICKLUNGSAUFTRAG: Complete UI, Performance & System Stability Overhaul“
(Phasen 1–6). Ausgangsstand main 0.9.466/0.9.467, Schema 104. Dieser Bericht hält Phase 1 (Bestandsaufnahme mit
Messwerten) fest und führt die Maßnahmen aller weiteren Phasen mit Stand. Er baut auf den früheren Prüfungen auf
(AUDIT_REPORT.md 17.11., STABILITAET_1811.md, SYSTEM_UPDATE_1911.md, SYSTEMCHECK_1911.md, RECHENKERNE_2111.md) und
wiederholt deren erledigte Punkte nicht.

Regeln dieser Arbeit: keine Funktion geht verloren, Ergebnisse bitgleich (Fingerabdruck der Kalkulation vor/nach),
jede Änderung gemessen und mit Test, kein Architekturwechsel der Datenhaltung ohne Patricks Freigabe (PostgreSQL je PC
+ Abgleich über den gemeinsamen Ordner bleibt). Bereiche, an denen parallel gearbeitet wird (Staffelkalkulation,
12-m-Zuschnitt/Nesting, Nesting-Arbeitsplatz/Stangenbild, BLM-Import, LST-Lernen), fasst diese Arbeit nicht an.

## 1. Umfang des Programms

| Kennzahl | Wert |
|---|---:|
| Python-Module `programm/rohrlaser` | 603 Dateien, 252.600 Zeilen |
| Größte Module | angebot_fenster 11.239, rechnen 5.889, fenster 5.665, baugruppe_dialog 4.545, step 4.269, neuerungen 4.096, datenbank 4.008 |
| Testskripte | 560 im Gesamtlauf (tests/alle.py), dazu 198 Einträge LANGSAM/EIGEN |
| Tabellen (CREATE TABLE) | 43 + Stammdaten-Tabellen aus stammdaten.TABELLEN |

## 2. Ausgangsmessungen (Phase 1)

Rechner: Cloud-Container, 4 Kerne, 15 GB, Qt ohne Bildschirm (offscreen), PostgreSQL 16 eingebettet wie im Programm.
Werkzeug `werkzeuge/systemcheck.py` mit 14 STEP-Dateien aus `tests/step*` (Rohre, Profile, Baugruppe mit 48 Teilen).
Absolute Zeiten liegen auf den Arbeitsplätzen anders; verglichen wird immer vorher/nachher auf demselben Rechner.

| Ablauf | Zeit | CPU | RAM danach | SQL-Anweisungen |
|---|---:|---:|---:|---:|
| Programmstart (Module laden, eigener Prozess) | 1,36 s | | | |
| Datendatei öffnen | 2,14 s | 1,09 s | 143 MB | 2.675 (1,49 s) |
| Hauptfenster mit Startseite aufbauen | 3,01 s | 2,87 s | 309 MB | 480 |
| STEP-Import 14 Dateien | 22,4 s | 2,1 s* | 358 MB | 708 |
| Angebot öffnen kalt / warm | 0,56 / 0,13 s | | 377 MB | 117 / 43 |
| Zelle ändern mit Prüfung | 0,44 s | | 402 MB | 87 |
| Optimieren | 0,17 s | | 409 MB | 48 |
| 3D-Ansicht öffnen | 0,08 s | | 422 MB | 2 |
| 3D (ohne OpenGL): zehn Teile zeigen | 4,3 s | | 433 MB | 36 |
| 3D (ohne OpenGL): 360° drehen, 36 Standbilder | 45,5 s (1,26 s/Bild) | | 465 MB | 0 |
| Angebots-PDF / Werkstatt-PDF | 0,48 / 0,47 s | | 481 MB | 122 / 36 |
| Langzeit: Angebot 10× öffnen/ändern/schließen | 1,0 s je Runde | | +1,7 MB je Runde | |

\* Geometrie in Hilfsprozessen. Während dieses Laufs lief parallel die Datenbank-Testreihe; die Zeiten sind darum
eher hoch. Doppelte Rechnungen (diagnose): überall 0.

Weitere Messungen:
- **Testreihe** (tests/alle.py, PostgreSQL): 556 von 560 grün. Rot nur Umgebung des Containers: test_ansicht_gl und
  test_schnittkoerper (OpenGL über xcb fehlt), test_tempo (Speichergrenze 100 MB, auch auf main rot, bekannt seit
  21.11.), test_bedienung_0611 (abgeschnittene Beschriftung nur mit der Schrift Inter des Containers; CI nutzt DejaVu).
- **Abhängigkeiten**: pip-audit ohne bekannte Lücken. Neuere Fassungen: cryptography 50.0.2 (Patch), pypdfium2 5.15.2.
- **Toter Code** (vulture, 60 %): 59 Kandidaten, davon nach Volltextsuche 23 echte Funktionen ohne Aufrufer (u. a.
  KundeDialog, profirst_schreiben, naechste_kundennr, los_stornieren); der Rest sind Qt-Überschreibungen und
  dynamisch aufgerufene Methoden (`_w_pdf` …). Siehe Abschnitt 4, Phase 5.
- **Stille Fehler**: 48 Stellen `except Exception: pass`, fast alle bewusst und kommentiert (Lesemodus, Zeitwächter,
  Protokoll selbst). Zentrale Fehlerbehandlung ist vorhanden (protokoll.py: sys/threading.excepthook, faulthandler,
  Zugangsdaten geschwärzt, Supportpaket).
- **Oberfläche**: Bilder aller 68 Ansichten in Hell und Dunkel mit dem neuen Werkzeug `werkzeuge/oberflaeche_bilder.py`.

## 3. Befunde

| Nr | Bereich | Befund | Ursache | Wirkung |
|---|---|---|---|---|
| B1 | Datenbank | Jede Anweisung in einer Transaktion kostet drei Wege zum Server (SAVEPOINT, Anweisung, RELEASE) | Nachbildung des SQLite-Verhaltens (Fehler verwirft nur die Anweisung) | Angebot mit 50 Positionen kopieren 132 ms, davon 38 % Sicherungspunkte; betrifft jedes Speichern, Importe, Abgleich |
| B2 | Öffnen | 952 Anweisungen bei jedem Öffnen der Datendatei | Alle rund 200 Protokoll-Trigger wurden gelöscht und neu angelegt | 0,3–0,6 s je Start, mehr auf langsamen PCs |
| B3 | Oberfläche | Anwendungsweiter Ereignisfilter erzeugte je Ereignis bis zu dreimal ein Python-Enum | stil.py prüfte die Ereignisart vor der Widget-Art | rund 144.000 Ereignisse beim Fensteraufbau, 0,9 s Profilzeit |
| B4 | Oberfläche | Startseite: Knöpfe der Schnellzugriffe auf 14 px gequetscht, nur eine Spalte | Spaltenzahl änderte sich im Layoutdurchgang, Höhe wurde nicht neu gemeldet | nach dem ersten Öffnen eines Angebots sichtbar |
| B5 | Oberfläche | Leere Tabellen zeigen eine weiße Fläche (Anfragen, Auswertung, Aufträge rechts …) | Hinweis gab es nur auf 5 Seiten | unklar, ob noch geladen wird oder nichts da ist |
| B6 | Oberfläche | Menüpfeil der Werkzeugleisten-Knöpfe („Letzte Angebote“, „Favoriten“, „Meldungen“) als Strich unter dem Text | Fusion-Vorgabe für InstantPopup | wirkt unfertig |
| B7 | Start | Hauptfenster baut alle 29 Einstellungsseiten (441 Felder) und alle Reiter sofort | Einstellungen werden über `felder` quer im Programm benutzt | rund 1 s des Fensteraufbaus |
| B8 | 3D | Software-Darstellung (ohne OpenGL, z. B. Remote-Desktop): 1,26 s je Standbild bei 3.000–5.000 Dreiecken | Sortier-Teilung und Verdeckungsraster seit 20.11. (Qualität); ~40.000 Polygone je Bild | nur Standbilder nach dem Loslassen, Drehen selbst nutzt die grobe Stufe (60 ms) |
| B9 | Anwendung | Sechs anwendungsweite Python-Ereignisfilter (stil, mausrad, tastatur, tempo, fenster_platz, Eingabewächter/Fenstermerker) | gewachsen | jedes Qt-Ereignis läuft durch sechs Python-Funktionen |
| B10 | Langzeit | +1,7 MB je Runde Angebot öffnen/ändern/schließen | noch offen (Python-Objekte 131.000) | über einen Arbeitstag einige 10 MB |

## 4. Maßnahmen und Stand

### Paket 1 (Phase 1 + 2 + erste Teile 3/4) – dieser Pull Request

| Nr | Maßnahme | Messung vorher → nachher | Ergebnis gleich? |
|---|---|---|---|
| B1 | Sicherungspunkt bleibt nach erfolgreicher Anweisung stehen, Freigabe und neuer Punkt in **einem** Weg (`RELEASE …; SAVEPOINT …`); COMMIT/ROLLBACK räumen mit ab | Kopieren 50 Pos.: 132 → 103 ms; Wege je Anweisung 3 → 2 | ja: Fehler verwirft weiter nur die eine Anweisung (Test) |
| B2 | Protokoll-Trigger bleiben stehen, nur überzählige werden am Ende entfernt | Öffnen: 952 → 346 Anweisungen, 0,58 → 0,31 s (Median zweier Läufe 0,34 → 0,19 s) | gleicher Triggerbestand (Test), Protokoll läuft weiter |
| B3 | Ereignisfilter prüft zuerst die Widget-Art, Ereignisart einmal | Profilzeit beim Fensteraufbau 0,91 → 0,26 s | gleiche Umfärbung (Test) |
| B4 | Schnellzugriffe melden ihre Höhe neu, Spalten beim Zeigen neu bestimmt | 14 px → volle Höhe, 1 → 2 Spalten | – |
| B5 | Jede Tabelle/Baumansicht zeigt leer automatisch „Keine Einträge“; eigene Texte (leerhinweis.setzen) bleiben | – | – |
| B6 | Menüpfeil rechts mittig neben dem Text (Werkzeugleisten, Statuszeile) | – | – |
| – | Werkzeug `werkzeuge/oberflaeche_bilder.py`: Bilder und Aufbauzeit aller Ansichten in Hell/Dunkel | – | – |

### Folgepakete (geplant, in dieser Reihenfolge)

| Phase | Maßnahme | Ziel/Messung |
|---|---|---|
| 3 | B9: ein gemeinsamer Ereignisverteiler statt sechs Filtern (Reihenfolge und „verschluckt“-Verhalten wie bisher) | Zeit je Ereignis, Fensteraufbau |
| 3 | B7: Einstellungsseiten erst beim ersten Zeigen aufbauen, `felder` über eine Hülle, die die Seite bei Bedarf baut | Fensteraufbau −1 s |
| 3 | B10: Langzeitlauf mit Objektzählung je Typ, Ursache des Zuwachses suchen und beheben | Zuwachs ≈ 0 |
| 3 | B8: Software-3D: Stift/Pinsel nur bei Wechsel setzen, Sortier-Teilung ohne Rekursion | ms je Standbild, Bild pixelgleich |
| 3 | Startseite: Angebotsliste ohne Nachkalkulations-JSON laden, wenn nur Zählwerte gebraucht werden | Startseite füllen bei 10.000 Angeboten |
| 4 | Designsystem: Eingabefelder, Bildlaufleisten, Fokus, Zustandsfarben einheitlich aus design.py; Kontrastprüfung Dunkel | Bilder vorher/nachher aller 68 Ansichten |
| 5 | Toter Code (23 Funktionen ohne Aufrufer) nach Einzelprüfung entfernen; Abhängigkeiten cryptography/pypdfium2 | Testreihe grün |
| 5 | Regression: Fingerabdruck, test_regression_ergebnisse, Last 1/10/25 Benutzer, Abgleich | gleiche Ergebnisse |
| 6 | Performancebericht, Änderungsprotokoll, bekannte Einschränkungen, Release über die Merge-Reihe | – |

## 5. Datenbank und 10–25 gleichzeitige Benutzer (nur Bewertung, kein Umbau)

Aufbau heute (Patrick-Entscheidung 13.11./19.11.): PostgreSQL 16 eingebettet **je PC**, Abgleich feldweise über den
gemeinsamen Ordner, Nummernvorrat gegen doppelte Angebotsnummern, Versionsnummern je Zeile (Optimistic Locking),
Sicherung als .pgdump, Verbindungswächter. Messwerte aus SYSTEMCHECK_1911 (Abgleich 25 Plätze: 0,9 s, gleicher Stand,
keine doppelten Nummern) gelten weiter; der Lasttest dieser Prüfung (1/10/25 Benutzer auf einer Datenbank,
3.000 Angebote) steht im Abschnitt 6.

Bewertung: Für 10–25 Plätze trägt der heutige Aufbau, weil jeder Platz lokal arbeitet (keine Wartezeiten im Netz)
und der Abgleich unter 1 s bleibt. Grenzen: Änderungen anderer Plätze sind erst nach dem nächsten Abgleich sichtbar,
gleichzeitige Änderung desselben Felds wird als Konflikt gemeldet (nicht still überschrieben). Ein zentraler Server
würde Sichtbarkeit in Echtzeit bringen, braucht aber einen ständig laufenden Rechner, Rechte und Sicherung an einer
Stelle. **Empfehlung: Aufbau beibehalten.** Ein Wechsel (z. B. die am 19.11. besprochene Mischform „Server-PC, sonst
Abgleich“) wird nur mit Patricks Freigabe und eigenem Migrationsplan (Sicherung, Probe-Wiederherstellung,
Rückfall) angegangen; die Schichten dafür (Versionsnummern, Verbindungswächter) sind schon vorbereitet.

## 6. Lasttest (wird nachgetragen)

Siehe Abschnitt im Pull Request; Werte vorher/nachher mit `werkzeuge/last_messung.py --angebote 3000 --benutzer 1,10,25`.
