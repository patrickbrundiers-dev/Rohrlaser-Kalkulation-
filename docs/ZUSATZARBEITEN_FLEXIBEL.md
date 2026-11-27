# Zusatzarbeiten flexibel: global und je Position (0.9.455, 23.11.2026)

Master-Auftrag Patrick 23.11.2026: Zusatzarbeiten wahlweise für das ganze Angebot oder je Position, mit eigenen
Einheitspreisen und Mengen, als eigene Zeilen im Kundenangebot. Bestehende Funktionen wurden erweitert, nicht ersetzt.

## Ausgangslage (vorher)

| Anforderung | vorher vorhanden | jetzt |
|---|---|---|
| Zentrale Verwaltung (Bezeichnung, Preis, Einheit, Kategorie, Beschreibung, aktiv) | ja, Einstellungen → Zusatzarbeiten | unverändert, liefert Vorschläge |
| Zusatzarbeiten je Position mit Menge und Preis von Hand | ja (Fenster Zusatzarbeiten …) | + Haken **Preis = Verkauf** |
| Preis-Snapshot je Position | ja (Preisstand `stand`) | unverändert |
| €/Stück, €/m, €/m², €/kg, €/h, €/Angebot | ja | unverändert |
| Zusatzarbeiten für das ganze Angebot als eigene Zeilen | nein (€/Angebot wurde auf die Teile umgelegt) | **neu**: Unterreiter *Kalkulation → Zusatzarbeiten* |
| Prozentualer Zuschlag | nein | **neu** (Grundlage wählbar) |
| Warnung bei doppelt hinterlegter Leistung | nein | **neu** (Reiter + Angebots-Check) |
| Darstellung im PDF wählbar | nein („inkl. …“) | **neu**: zusammengefasst / detailliert / nur Gesamtpreis |
| Übertragen auf mehrere Positionen | je Position bzw. Mehrfachauswahl | + aus allgemeinen Zusatzarbeiten |

## Datenmodell und Migration

**Kein Schema-Sprung, keine Migration nötig, kein Datenverlust.** Gespeichert wird in vorhandenen JSON-Feldern:

- `angebote.zusatz` (seit Schema 73), Schlüssel `zusatzarbeiten`: Liste der allgemeinen Zusatzarbeiten
  `{id, name, katalog, menge, einheit, preis, beschreibung, kosten, zeit_min, basis, stand}`.
  `preis` = Verkaufspreis je Einheit, `kosten`/`zeit_min` = intern je Einheit, `stand` = Standardpreis und Datum
  beim Übernehmen aus der Verwaltung (Snapshot).
- `angebote.zusatz`, Schlüssel `zusatz_darstellung`: Darstellung im Kundenangebot (leer = Einstellung
  `zusatz_darstellung`, Vorgabe „zusammengefasst“).
- `positionen.zusatz` (bestehend): je Eintrag neu optional `vk: "ja"` (Preis = Verkaufspreis) und `kosten`
  (interne Kosten je Einheit, nur beim Übertragen aus allgemeinen Zusatzarbeiten).

Ältere Programme ignorieren die neuen Schlüssel. Angebote ohne die Schlüssel rechnen Cent für Cent wie vorher
(geprüft mit `tests/test_ein_rechenweg.py`, 40 Abnahmeangebote, und Szenario 12 in `tests/test_zusatz_global.py`).
Speichern: jede Änderung ist eine Schreibtransaktion (`Datenbank.zusatz_setzen`) und setzt „geändert am“, damit der
Abgleich über den gemeinsamen Ordner sie mitnimmt. Kopie und neue Fassung übernehmen beide Schlüssel.

## Rechnung

- **Allgemeine Zusatzarbeiten** (`zusatz_global.anwenden`, nach der Preisschicht): Gesamt = Menge × Preis je
  Einheit (kaufmännisch auf den Cent); % = Satz × Grundlage (Positionen bzw. Positionen + übrige allgemeine).
  Summe als Kostenart `zusatz_global` im Verkaufspreis (Netto, MwSt, Brutto, Angebotsliste), interne Kosten als
  `zusatz_global_kosten` in den Kosten der Marge (`marge.kosten`). Nicht betroffen: Mindestauftragswert, Rabatt,
  Skonto und Staffelpreise (Staffeln rechnen mit `zusatz_global.ohne(kopf)`).
- **Je Position mit Haken „Preis = Verkauf“** (`rechnen.zusatz_werte`, `rechnen.zusatz_vk_teil`): der Betrag geht
  nicht in Zusatzarbeiten eigen/fremd (also ohne Zuschlag und Gewinn), sondern nach Gewinn und Skonto direkt in den
  Stückpreis; interne Kosten = Menge × Preis der Verwaltung bzw. des Preisstands; Gewinn = Verkauf − Kosten.
  Neue Felder `zusatz_vk_teil`, `zusatz_vk_kosten_teil` (Zeile) und `zusatz_vk`, `zusatz_vk_kosten` (Summen) nur,
  wenn es solche Einträge gibt.
- **Ohne Haken** unverändert: Preis + Zuschlag Fertigung bzw. Fremdleistung + Gewinn.
- Regeln des Projekts bleiben: Gewinde/Senken/Flowdrill/Bohren nur €/Stück; Zukauf ohne Gewinn; Einstichzeit
  separat.

## Oberfläche

- Angebot → Reiter Kalkulation → Unterreiter **Zusatzarbeiten** (`zusatz_global_seite.py`): Tabelle der allgemeinen Zusatzarbeiten
  (Bezeichnung, Menge, Einheit, Preis je Einheit, Gesamt, Beschreibung, intern Kosten/Zeit, Grundlage bei %),
  Knöpfe *＋ Aus Verwaltung*, *＋ Frei*, *＋ Pauschale*, *＋ Zuschlag %*, *Entfernen*, *Standardpreis*,
  *Auf Positionen …*; darunter die Zusatzarbeiten je Position (Übersicht), gelbe Warnung bei Überschneidung,
  Darstellung im Kundenangebot und Summen (Positionen, allgemeine, netto, MwSt, brutto, intern Kosten, Zeit, DB).
- Fenster **Zusatzarbeiten …** einer Position: neue Spalte **Preis = Verkauf**.
- Angebots-Check: Warnung „Zusatzarbeit möglicherweise doppelt berechnet“ (Klick führt zum Reiter).
- Einstellungen → Angebot: *Zusatzarbeiten im Kundenangebot* (Vorgabe der Darstellung).

## Kundenangebot (PDF)

- zusammengefasst (Vorgabe): Positionstext wie bisher („inkl. …“), allgemeine als eigene Zeilen.
- detailliert: je Position „Zusatzarbeiten:“ mit Leistung, Menge, Einheitspreis, Gesamt und „Positionspreis
  einschließlich Zusatzarbeiten“; allgemeine mit Beschreibung. Preise ohne Haken als Anteil am Stückpreis
  (Kostenbetrag × Stückpreis ÷ Selbstkosten), mit Haken exakt.
- nur Gesamtpreis: keine Zusatzarbeiten im Positionstext, allgemeine als eine Summenzeile.
- Interne Kosten, Zeiten und Deckungsbeiträge stehen nie im Kundenangebot (Test prüft das); die Angebotsakte
  (intern) zeigt die Kostenart *Allgemeine Zusatzarbeiten* mit den internen Kosten.

## Tests

`tests/test_zusatz_global.py` (in `tests/alle.py`), die 12 Szenarien des Auftrags:

| Nr. | Szenario | Ergebnis |
|---|---|---|
| 1 | Globale Zusatzarbeit (3 h × 65 €) | 195 € als eigene Zeile, netto/MwSt/brutto, Kosten in der Marge |
| 2 | Zusatzarbeit einer Position | Stückpreis + 2,50 € + 4 × 0,80 € exakt |
| 3 | Unterschiedliche Preise je Position | Pos. 10 Entgraten 2,50 €, Pos. 20 3,00 € |
| 4 | Standardpreis aus der Verwaltung | Kosten × Zuschlag × Gewinn vorgeschlagen, Snapshot |
| 5 | Standardpreis überschreiben | 9,99 € bleibt, auch nach Preisänderung in der Verwaltung |
| 6/7 | Positionsmenge 10 → 25 | Zusatzarbeiten und % neu gerechnet |
| 8 | Globale Pauschale | Verpackung 45 € |
| 9 | Prozentualer Zuschlag | 2 % auf Positionen bzw. Positionen + Zusatzarbeiten |
| 10 | PDF | drei Darstellungen, PDF-Datei erzeugt, keine internen Werte |
| 11 | Erneut öffnen | gleiche Preise, Darstellung gespeichert |
| 12 | Bestehende Angebote | ohne Einträge und ohne Haken Cent für Cent wie vorher |
| + | Überschneidung, Übertragen, Kopie, Staffeln | Warnung, 2 Positionen, Kopie übernimmt, Staffeln ohne |

Bestehende Tests: `test_ein_rechenweg.py` (40 Angebote, Staffel = PDF Cent für Cent) unverändert grün.

## Nachtrag 0.9.457: Zeit aus dem Stundensatz (Patrick 23.11.2026)

Freie allgemeine Zusatzarbeiten ohne eigene Zeit (Einheit nicht h/min/%) bekommen ihre interne Zeit je Einheit aus
der Einstellung `zusatz_stundensatz` (*Zusatzarbeiten: Stundensatz für die Zeit [€/h]*, Einstellungen → Zuschläge und
Preise, Vorgabe 60 €/h, 0 = aus): Kosten je Einheit ÷ Stundensatz × 60 min, ohne Kosten Preis je Einheit ÷
Stundensatz × 60 min (`zusatz_global.zeit_je_einheit`). Anzeige grau in der Spalte Zeit, eigene Zeit überschreibt,
leer machen rechnet wieder. Die Zeit geht nur in die Summe Zeit, kein Preis ändert sich.

## Nachtrag 0.9.548: Zeit eigener Zusatzarbeiten an der Position (Patrick 27.11.2026)

`rechnen.zusatz_werte`: eigene Zusatzarbeiten (nicht Fremdleistung, nicht s/Stück, €/Angebot, €/h) ohne Zeitaufwand
in Stammdaten bzw. Preisstand bekommen `arbeit_s` = Betrag je Teil ÷ `zusatz_stundensatz` × 3600. Wirkt nur auf
Zeiten (Zeile „Zusatzarbeiten mit Zeit“), Personalzeit und Arbeitsplan, nicht auf Preise.
