# Materialdatenbank

Stand 23.11.2026 (Master-Auftrag „Intelligente Materialdatenbank mit ERP-CSV-Import“). Die Materialdatenbank ist
keine zweite Datenbank: Sie erweitert die vorhandenen Stammdaten (Profile, Werkstoffe, Preise, Lieferlängen,
Material-Lieferanten) um den Materialstamm, den Stammdaten-Import mit Importhistorie und die Bereiche der Seite
Material.

## Funktionen

| Bereich (Seite Material) | Inhalt | Modul |
|---|---|---|
| Dashboard | Kennzahlen, letzter Import, Preiswarnungen | `material_bereiche.DashboardSeite`, `material_stamm.kennzahlen` |
| Materialübersicht | Arbeitsliste Abmessung × Werkstoff, Matrix, Detail | `material_seite.MaterialBereich` |
| Werkstoffe, Abmessungen, Materialkombinationen, Einkaufspreise, Lieferanten | dieselben Tabellenseiten wie unter Einstellungen (Admin-Schutz gleich) | `material_bereiche.tabellenseite` |
| ERP-Import | Materialstamm/EK-Preise, Einkäufe (EK-CSV), Lieferanten-Preisliste, Importprofile | `material_import`, `erp_preise`, `material_bereiche.stamm_import` |
| Preisverlauf | alt/neu, %, Datum, Herkunft, Lieferant, Importquelle | `material_bereiche.verlauf_zeilen` |
| Importhistorie | Läufe, Einzeländerungen, Rückgängig | `material_import.laeufe/rueckgaengig` |
| Einstellungen | wichtigste Einstellungen mit Sprung | `material_bereiche.EinstellungenSeite` |

Weitere Regeln:

- **Nie raten.** Ein Werkstoff ohne eindeutige Norm (z. B. „S355“) landet in „nicht zuordenbar“. Im STEP-Import
  gibt es nur einen Hinweis aus dem Materialstamm, der Werkstoff wird nicht geändert.
- **Erkennung vorhandener Materialien** in beiden Importen: gemerkte Zuordnung → Artikelnummer (Materialnummer im
  Materialstamm) → Bestellnummer (Artikelnr. der Lieferantenpreise) → Bezeichnung/Maße/Werkstoff. Eine Nummer, die
  auf mehrere Materialien zeigt, gilt nicht (`material_stamm.nummern`).
- **Nichts ohne Vorschau.** `material_import.analysieren` ändert nichts; erst `ausfuehren` schreibt, nach Sicherung,
  als ein Lauf. Schlägt etwas fehl, wird der Lauf zurückgenommen.
- **Angebote ändern sich nie rückwirkend.** Der Import schreibt nur Stammdaten; festgeschriebene Angebote bleiben,
  offene meldet der Preiswächter.
- **Lieferantenvorschlag**: `material_stamm.angebote_fuer` (Staffel ab Menge, Mindestabnahme, Verpackungseinheit,
  Gültigkeit) und `lieferant_vorschlag` (bevorzugter Lieferant bis 2 % Mehrkosten).

## Datenbankänderungen (Schema 103)

- Neue Stammdatentabelle `materialstamm` (abgeglichen wie alle Stammdaten): `profil_id`, `werkstoff_id`,
  `oberflaeche`, `materialnr`, `bezeichnung`, `handelsname`, `lieferant`, `aktiv`, `angelegt`, `geaendert`, `quelle`,
  `bemerkung`; Schlüssel (`profil_id`, `werkstoff_id`, `oberflaeche`).
- `material_lieferanten`: neue Felder `ab_menge` (Staffel ab m), `ve_stangen`, `bevorzugt`; Schlüssel um `ab_menge`
  erweitert (mehrere Staffeln je Lieferant).
- Lokale Tabellen je PC: `material_importe` (Läufe) und `material_import_posten` (jede Änderung mit alt/neu als
  JSON), angelegt in `material_import.einrichten`.
- Migration: `Datenbank._materialstamm_ergaenzen` füllt den Materialstamm einmal aus Preisen, Lieferlängen,
  Lieferantenpreisen und EK-Käufen (Einstellung `materialstamm_stand`).
- Einstellungen: `erp_direkt_tage`, `erp_direkt_stangen`, `erp_werkstoff_vorwahl`, intern `material_importprofile`.

## Importformate

- Dateien: CSV/TXT in UTF-8 (mit/ohne BOM) oder ANSI (cp1252); Trennzeichen Semikolon, Komma, Tabulator oder `|`;
  Dezimalkomma oder -punkt; Excel `.xlsx` (erstes Blatt, ohne Zusatzpaket).
- Felder (`material_import.FELDER`): Materialnummer, Bezeichnung, Werkstoff, Abmessung, Profilart, Außen-Ø/Breite,
  Höhe, Wandstärke, Länge, EK-Preis (Pflicht), Preiseinheit, Lieferant, Gewicht, Gültig ab, Oberfläche,
  Handelsbezeichnung, Bestellnummer (Lieferant). Spaltennamen werden deutsch und englisch erkannt
  (`material_import._KOPF`).
- Preiseinheiten: €/m, €/kg, €/t (→ €/kg), €/100 m (→ €/m), €/Stange bzw. Stück (ohne Länge 6.000 mm).
- Vorschau-Gruppen: neu, Preisänderung, aktualisiert, unverändert, doppelt, fehlerhaft, nicht zuordenbar.
- Einkäufe (EK-CSV): siehe `erp_preise` (Kaufdatum, Menge, Meterpreis, Artikelnummer, EK-Artikel, Zusatztext, PE).

## Konfiguration

Einstellungen → ERP-Preisimport → Auswertung: Zeitraum der Käufe, Ausreißer-Grenze, Direkt-Regel (Alter in Tagen,
Stangenzahl ±), Werkstoff-Vorauswahl. Importprofile liegen je Arbeitsplatz. Admin-Schutz: Preise, Werkstoffe und
Materialstamm ändern nur Admins, wenn der Schutz eingeschaltet ist.

## Tests

`tests/test_materialdatenbank.py` (Formate, Gruppen, Übernehmen, Rückgängig, Nummern-Erkennung, 4.000 Zeilen,
Lieferanten, Seite), `tests/test_erp_anlegen.py`, `tests/test_erp_preise.py`, `tests/test_material_seite.py`,
`tests/test_materialplattform.py`.

## Bekannte Grenzen

- Staffelpreise kommen über die Tabelle Lieferanten (Staffel ab m), nicht über eigene Spalten im Stammdaten-Import.
- Preise gelten für Rohware; eine Oberfläche im Import legt nur die Materialstamm-Zeile an, keinen eigenen Preis.
- Excel: nur das erste Blatt, keine Formeln-Neuberechnung, keine `.xls`.
- Rückgängig stellt Felder nicht zurück, die nach dem Import von Hand geändert wurden (Meldung).
- Kein Restelager und keine Bestellung aus dem Programm; Lieferantenvorschlag ist eine Empfehlung.
- Preisverlauf-Grafik je Material steht im Reiter Preishistorie der Materialübersicht, nicht im Bereich Preisverlauf.

## Ausbau (Folge-PR, 0.9.460)

- **Lieferzeit aus dem EK**: Feld `liefertermin` im EK-Import (`erp_preise.FELDER`, Spalte `erp_kaeufe.liefertermin`, lokal), `erp_preise.lieferzeit()` = Liefertermin minus Kaufdatum über `erp_monate`; Käufe ohne Termin, mit Termin vor dem Kauf oder über 365 Tagen zählen nicht. Anzeige: Materialübersicht (Spalte, Detail, Export, Vergleich), Lieferantenvergleich, Fenster Material je Abmessung. Der Export enthält keinen Wareneingang, es ist die zugesagte Lieferzeit.
- **ERP-Vorschlag im Fenster Material je Abmessung**: Spalte mit dem Kauf zum Bedarf; ein Klick trägt ihn als Meterpreis des Angebots ein (Stammdaten unverändert).
- **Zuordnen in der Vorschau** (1.3): `material_import.analysieren(..., hand={Zeile: Zuordnung})`, `hand_merken()` schreibt die Artikelnummer in `erp_zuordnung`.
- **Auswirkung auf offene Angebote** (2.5): `material_import.auswirkung()`, nur Anzeige; festgeschriebene Angebote (`preisbasis`) und Positionen mit eigenem `preis_m` zählen nicht.
- **Lieferantenvorschlag im Angebot** (3.1): Spalte „Lieferant (Vorschlag)“ aus `material_stamm.lieferant_vorschlag()`.
- **Werkstoffwahl im Prüfdialog** (4.1): Gruppe „im Materialstamm“ oben in der Werkstoff-Liste (`step_dialog._stamm_werkstoffe`); keine Vorauswahl.
- Kein Schema-Sprung (nur die lokale Tabelle `erp_kaeufe` bekommt eine Spalte).

Bekannte Grenzen: Die Lieferzeit gilt je Material über alle Lieferanten (der EK-Export nennt keinen Lieferanten). Die Gruppe „im Materialstamm“ richtet sich nach dem Profil beim Öffnen des Prüfdialogs, nicht nach einem dort geänderten Profil.
