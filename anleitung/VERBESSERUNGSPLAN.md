# Verbesserungsplan – Stand 0.9.164 (28.10.2026)

Der Wettbewerbsplan (`VERGLEICH_WETTBEWERB_UND_VERBESSERUNGEN.md`) ist mit 0.9.161 umgesetzt: Lager/Reste, Nachkalk-Auswertung,
STEP-Merkmale, Arbeitsgänge, Varianten und Fertigung. Dieser Plan setzt deshalb nicht bei neuen Funktionen an, sondern bei
**Wartbarkeit, Zuverlässigkeit und Tempo der Weiterentwicklung**. Grundlage sind Messungen am Code, keine Vermutungen.

## Befund in Zahlen

| Messung | Wert | Bewertung |
|---|---|---|
| Module in `programm/rohrlaser` | 194 | ok, gut aufgeteilt |
| Größte Dateien | `angebot_fenster.py` 5.885, `step_geometrie.py` 4.062, `rechnen.py` 3.444, `baugruppe_dialog.py` 3.328, `datenbank.py` 2.591 Zeilen | zu groß, Konfliktherd bei parallelen PRs |
| Funktionen > 150 Zeilen / > 300 Zeilen | 22 / 8 (größte: `_profil_messen` 511, `netz_rechnen` 397, `step.uebernehmen` 395, `AngebotFenster.__init__` 392, `rechnen.kalkulation` 343) | schwer zu testen und zu prüfen |
| ruff C901 (zu komplex) / PLR0912 (zu viele Zweige) | 266 / 145 | derzeit nicht geprüft (nur `E9`, `F`) |
| `except Exception:` mit nur `pass`/`return`/`continue` | 47 (davon 8 in `step_geometrie.py`) | Fehler werden still geschluckt |
| ruff B905 (`zip` ohne `strict`) | 241 | stille Fehler bei ungleich langen Listen |
| Rückgabe-Typangaben | 0 von 5.301 Funktionen | keine statische Prüfung möglich |
| Module ohne Erwähnung in `tests/` | u. a. `fracht_seite` (1.125), `editor_eigenschaften` (472), `nachkalk_seite` (447), `lager_seite` (283), `versand_seite`, `fertigung_seite`, `varianten_dialog`, `arbeitsgaenge_dialog` | Oberflächen der neuen Funktionen aus 0.9.161 ungetestet |
| Schema-Version | 65 | viele Migrationen in einer Datei |
| `neuerungen.py` | 1.471 Zeilen Text im Quellcode | wächst mit jedem Release |
| Commits letzte 30 Tage | 60 | hohes Tempo → Architektur muss parallele Arbeit tragen |

## P0 – Zuverlässigkeit (zuerst, klein, kein Verhalten ändern)

### 1. Still geschluckte Fehler sichtbar machen – **erledigt in 0.9.165**
- Alle 47 `except Exception: pass/return/continue` durchgehen. Je Fall entscheiden: engere Ausnahme (`OSError`, `ValueError` …),
  oder `protokoll`-Eintrag mit Stacktrace, oder bewusst still mit Kommentar *warum*.
- Schwerpunkt `step_messung/step_geometrie.py` und `step_offenes_rohr.py`: dort verdeckt ein stiller Fehler eine falsche Messung,
  die dann als Rechenwert im Angebot landet.
- **Abnahme:** ruff-Regel `BLE001`/`S110` aktiv; jede verbleibende Ausnahme hat `# noqa` mit Begründung.

### 2. `zip(..., strict=True)` in Rechen- und Geometriecode – **erledigt in 0.9.165** (strict=True nur im Rechenkern, sonst ausdrücklich False)
- 241 Stellen; zuerst `rechnen.py`, `optimierung.py`, `schneidweg.py`, `step_messung/*`, `pdf.py` (Werte ↔ Spalten).
- Wo ungleiche Länge gewollt ist: `strict=False` ausdrücklich hinschreiben.
- **Abnahme:** `B905` aktiv, Tests und Abnahme (`tests/test_abnahme.py`) unverändert grün.

### 3. Oberflächen der neuen Reiter testen
- Hinweis: Die Liste unten beruht auf einer Namenssuche in `tests/`; manche Reiter werden womöglich indirekt über das
  Hauptfenster getestet. Vor dem Schreiben neuer Tests deshalb zuerst P0-4 (Abdeckung messen).
- Rauchtests (öffnen, füllen, speichern, im Lesemodus öffnen) für `fracht_seite`, `nachkalk_seite`, `lager_seite`,
  `fertigung_seite`, `versand_seite`, `varianten_dialog`, `arbeitsgaenge_dialog`, `editor_eigenschaften`.
- Muster wie die bestehenden Qt-Tests mit `QT_QPA_PLATFORM=offscreen`; in `tests/alle.py` eintragen.
- **Abnahme:** jedes Modul in `programm/rohrlaser` ist von mindestens einem Test importiert (kleines Prüfskript im Workflow,
  analog zur Regel „jede Testdatei steht in TESTS“).

### 4. Abdeckung messen und Untergrenze setzen
- `tests/alle.py --coverage` gibt es schon, läuft aber nicht im Workflow. Einmal je Sammel-Release laufen lassen, Bericht als Artefakt.
- Untergrenze je Kernmodul (`rechnen`, `optimierung`, `datenbank`, `schneidweg`, `step`) festhalten, darf nicht sinken.

## P1 – Wartbarkeit (schrittweise, je PR ein Modul)

### 5. `angebot_fenster.py` aufteilen (5.885 Zeilen)
- `__init__` (392 Zeilen) in Aufbau je Bereich zerlegen; Tabellenmodelle (Zeile 108/827 ff.), Kalkulationsansicht,
  Variantenvergleich (um Zeile 1350) und Ausgabe in eigene Module wie schon bei `angebot_oben.py`, `angebot_spalten.py`.
- Ziel: keine Datei über ~2.000 Zeilen, damit parallele PRs seltener kollidieren.
- **Regel:** reines Verschieben, keine Logikänderung im selben PR; Bildschirmfotos der Anleitung als Gegenprobe.

### 6. Lange Rechenfunktionen zerlegen und typisieren
- `rechnen.kalkulation` (343), `schneidweg.rechnen` (270), `step.uebernehmen` (395), `step.rechner_eingaben` (209),
  `step_geometrie._profil_messen` (511), `rohr3d.netz_rechnen` (397).
- Vorgehen je Funktion: erst Charakterisierungstest (Ein-/Ausgabe einfrieren, z. B. aus den Abnahmeangeboten), dann in
  benannte Teilschritte zerlegen. Zwischenergebnisse als `dataclass` statt verschachtelter `dict`s.
- Typangaben zuerst in diesen Kernmodulen; `mypy` oder `pyright` nur für diese Dateien im Workflow (Liste wächst mit).

### 7. ruff schrittweise schärfer
- Jetzt: `E9`, `F`. Nächste Stufen je eigener PR: `B` (Bugbear, inkl. B905/B023/B904), `BLE`, `SIM`, dann `C901` mit hoher
  Grenze (z. B. 40) und `per-file-ignores` für die bekannten Großfunktionen, Grenze senkt sich mit jedem Umbau.
- Die Ausnahme `programm/step_messung/*.py = F401` aufheben, sobald der dort erwähnte Umbau fertig ist.
- `B023` (40 Treffer): Stellen prüfen; die meisten sind sofort aufgerufene Hilfsfunktionen (harmlos), echte Gefahr
  besteht bei Qt-`lambda`s in Signalen, die erst später laufen.

### 8. Datenbank-Migrationen entflechten
- Schema 65 in `datenbank.py`: Migrationen als nummerierte Schritte (eine Funktion je Version) statt einer langen Kette.
- Test: Datendateien jeder Schema-Version (aus den Sicherungen erzeugt) migrieren und mit `PRAGMA integrity_check` prüfen.
- Dynamische Tabellen-/Spaltennamen in SQL (`datenbank.py:2262/2292`, `teilen.py:94/317`, `nummern.py:137`) gegen eine
  feste Liste prüfen (Whitelist), auch wenn die Namen heute nur aus dem Programm kommen.

### 9. `neuerungen.py` als Daten
- Die 1.471 Zeilen Text in eine Datei (`neuerungen.json`/`.md`) verschieben, die das Programm liest. Weniger
  Merge-Konflikte, weil jedes Release dort eine Zeile anhängt.

## P2 – Arbeitsablauf und Produkt

### 10. Schnellere Rückmeldung im PR
- Testlauf nach betroffenen Bereichen staffeln (STEP-Änderung → STEP-Tests zuerst), damit ein Fehler nach Minuten statt nach
  dem ganzen Lauf sichtbar ist.
- Optional: `pre-commit` mit ruff lokal, damit Lint-Fehler gar nicht erst in den PR kommen.

### 11. Fehlerberichte aus dem Feld
- Bei unerwarteten Ausnahmen einen Bericht (Version, Schema, Stacktrace, ohne Kundendaten) in `Daten/Protokoll` schreiben
  und im Menü **Hilfe → Fehlerbericht speichern …** als ZIP anbieten. Offline, kein Versand ohne Zutun des Anwenders.

### 12. Leistung großer Angebote
- Messen statt raten: Zeit für Öffnen, Optimieren und PDF bei einem großen Abnahmeangebot im Workflow festhalten
  (wie das Abnahmeprotokoll) und Ausreißer zwischen Releases melden.

### 13. Code-Signatur
- Laut README verschwinden die SmartScreen-/Defender-Warnungen erst mit Signatur. Kosten/Nutzen eines Zertifikats
  (z. B. Azure Trusted Signing) prüfen; das wäre für Kunden die größte spürbare Verbesserung beim Installieren.

## Reihenfolge

1. P0-1 und P0-2 (je ein PR, nur Code-Hygiene, Rechenergebnisse unverändert).
2. P0-3 und P0-4 (Tests, kein Programmcode).
3. P1-7 Stufe `B` aktivieren – sichert die Arbeit aus Schritt 1 und 2 ab.
4. P1-5 und P1-6 modulweise, jeweils mit Charakterisierungstest vorher.
5. P1-8, P1-9, danach P2 nach Bedarf.

**Leitplanken wie bisher:** kleine, einzeln prüfbare Schritte; Rechenregeln nicht nebenbei ändern; Preis-Snapshots, Lesemodus,
Sicherung, Lizenz und Update schützen; bei jedem Schritt Abnahme und STEP-Referenztests grün.
