# Intelligente 12-Meter-Zuschnittoptimierung (24.11.2026)

Auftrag Patrick 24.11.2026 15:23 UTC: 12 m nur vorschlagen, wenn unter Berücksichtigung aller Kosten tatsächlich Geld
gespart wird; eine zentrale Logik für das ganze Programm.

## 1. Analyse vorher

- Zentrale Stelle gab es schon: `rechnen.laengen_vergleich_gruppe` (plant je Lieferlänge, über der Beladelänge mit
  Zuschnitt) und `rechnen.laengen_bewerten` (Gesamtkosten = Material + Beladungen + Zuschnitt, Mindestersparnis
  20 € **und** 3 %).
- `laenge_waehlen` übernahm die Empfehlung nur bei Staffel-Stufen mit Haken „Lieferlänge automatisch“; sonst blieb das
  Angebot bei 6 m bis zum Klick. Folge: Angebot und Staffeln konnten verschieden entscheiden.
- Pauschale Stellen:
  - Nesting (`nesting_zuschnitt`): Strategie A wählte 12 m nach gekauften Millimetern, D nach Beladungen, B/E nach
    Kosten, aber **ohne** Mindestersparnis. Ein 12-m-Zuschnitt konnte so für Cent-Beträge oder ganz ohne
    Kostenvorteil gewählt werden.
  - Keine Handhabungs-/Transportkosten langer Stangen.
  - Kein Wert verwertbarer Reste, auch wenn Lager und Reststücke an sind.
  - Hüllkreis > 70 mm: 12 m ist nur lieferbar, keine Empfehlung. Das ist richtig so und bleibt.

## 2. Lösung

- Eine Entscheidung, `rechnen.laenge_vorteil(basis, kandidat, par)`: lohnt nur mit Ersparnis ≥ Mindest-€ und ≥
  Mindest-%. Sie gilt in `laengen_bewerten` (Angebot, Staffeln, Rahmen/Abrufe über `staffeln.stufe_lauf`,
  Baugruppen/Schweißbaugruppen als Positionen, Materialanfrage, Fertigung/Nachkalkulation über den Plan des
  Angebots) und in `nesting_zuschnitt` (alle Strategien).
- Kostensätze: `rechnen.laenge_parameter`.
  - Beladung
  - Zuschnitt
  - Handhabung je langer Stange (`laenge_handling_eur` über `laenge_handling_ab`)
  - Mindestwerte
  - Reste (nur mit Lager **und** Reststücken; verwertbar wie im Lager, Meterpreis × Restwert-Anteil)
- Gesamtkosten = Material + Beladungen + Zuschnitt + Handhabung − Reststückwert.
- Automatik `laenge_automatisch` (Vorgabe ja, wirkt nur mit `laenge_vergleich` = ja): Das Optimieren plant gleich mit
  der empfohlenen Länge, im Angebot und je Staffel-Menge gleich. Von Hand gewählt (auch „wieder 6 m“) gilt vor.
- Anzeige: Block „Materialoptimierung“ im Lieferlängen-Vergleich mit Rohren, Material-, Verschnitt- und
  Gesamtkosteneinsparung (€, je Teil) und Empfehlung; „Geplant: … (automatisch nach Gesamtkosten / von Hand
  gewählt)“.
- Ohne Lieferlängen-Vergleich (Vorgabe nein) bleibt alles bitgleich (Regressionstest 20 Angebote).

## 3. Tests

- `tests/test_zuschnitt_12m_2411.py` deckt die 10 Pflichtszenarien mit Kontrollrechnung ab:
  1. deutlich günstiger
  2. geringfügig günstiger
  3. teurer trotz weniger Verschnitt (Handhabung)
  4. 6 m wirtschaftlicher
  5. identisch
  6. Reste verwertbar
  7. Reste nicht verwertbar
  8. Maschinenlänge
  9. Staffelmengen
  10. mehrere Abmessungen/Werkstoffe

  Dazu kommen Übersteuerung von Hand, Automatik aus und die Nesting-Entscheidung.
- Angepasst: `test_lieferlaengen`, `test_lieferlaengen_mischen` und `test_varianten` prüfen weiter den Ablauf ohne
  Automatik (`laenge_automatisch` = nein).
