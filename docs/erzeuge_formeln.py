"""Erzeugt docs/KALKULATION_FORMELN.md (Plan X1–X8, Paket X8, Patrick 12.11.2026): Formeln von Material bis
Verkaufspreis in Rechenreihenfolge (von Hand gepflegt, unten FORMELN) und die Parameter-Tabellen (aus den Stammdaten
und Einstellungen des Programms erzeugt, damit sie nie veralten). tests/test_formeln_doku.py prüft, dass die Datei
aktuell ist.

Aufruf: python docs/erzeuge_formeln.py
"""
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import stammdaten as sd  # noqa: E402

ZIEL = HIER / "KALKULATION_FORMELN.md"
GRUPPEN = ("Kalkulation", "Lieferlängen", "Lager und Fertigung", "Schweißbaugruppen", "Frachtkosten",
           "Blech-Richtpreis", "Dreh-/Frästeil-Richtpreis")
TABELLEN = ("maschinen", "schneiddaten", "stundensaetze", "arbeitsschritte", "zusatzarbeiten", "qualitaetsstufen")

FORMELN = r"""# Kalkulation: Formeln und Parameter

Rechenweg der Rohrlaser-Kalkulation von Material bis Verkaufspreis, in der Reihenfolge, in der `rechnen.kalkulation`
rechnet. Alle Werte je Teil, wenn nicht anders angegeben. Ein leeres Feld rechnet nie mit einem erfundenen Wert: es
zählt 0, die Vorgabe der Einstellung oder es steht als „nicht berücksichtigt“ bzw. mit Hinweis im Status. Die
Parameter-Tabellen unten sind aus dem Programm erzeugt (`python docs/erzeuge_formeln.py`).

## 1 Material

- Stangenpreis = Preis × Bezug: €/kg × kg/m × Stangenlänge, €/m × Stangenlänge oder Tonnenpreis des Werkstoffs;
  Händler-Mehrlänge, Teuerung und Oberflächen-Aufpreis kommen dazu (Stammdaten Preise, Werkstoffe, Oberflächen).
- Material je Teil = Kosten der Stangen der Gruppe × Längenanteil des Teils (Teil + Trennung) an der Belegung.
- Schrotterlös = − Verschnitt [mm] × Preis je mm × Schrottanteil (Einstellung, leer = 0).
- Ausschuss Material = Material × a ÷ (1 − a), a = Ausschuss (Einstellung; „im Hundert“).
- Lagerzins (nur Abruf-Angebot mit Jahresbedarf) = Material × Zins × Lagerdauer.

## 2 Laserzeit je Teil

```
Zeit groß    = 60 × Schneidweg groß / Vorschub groß            [s]
Zeit mittel  = 60 × Schneidweg mittel / Vorschub mittel
Zeit klein   = 60 × Schneidweg klein / Vorschub klein
Gravur       = 60 × Gravurlänge / Vorschub Gravur
Einstiche    = Einstiche × Einstechzeit
Anfahren     = Einstiche × Zeit je Kontur   (mit Maschinendynamik stattdessen Leerwege aus dynamik.py)
+ Ecken, Mehrzeit 3D, Anschlag doppelt, Anfahrweg, Abfall zerteilen, Drehen je Seitenwechsel, Messzyklen,
  Nebenzeit je Teil, Entnahme von Hand (je nur, wenn das Feld gesetzt ist)
Laserzeit brutto = Σ aller Anteile
Laserzeit netto  = max(0, brutto − Einsparung gemeinsamer Schnitte) + Zusatzzeiten (s/Stück) + Prüfzeit Anbauteile
```

- Konturklasse einer Innenkontur nach dem Hüllmaß: klein bis / mittel bis der Maschine (Vorgabe 3 × und 8 × Wand).
- Einsparung gemeinsamer Schnitt: nur zwei benachbarte gerade Enden; je gespartes Ende Schnittlänge / Vorschub +
  Einstiche × (Einstechzeit + Zeit je Kontur).
- Schneidzeit von Hand ersetzt brutto (Zusatz- und Prüfzeit kommen dazu).
- Zeitbild (Plan X2) gliedert dieselbe Zeit in 1 Laserbearbeitung, 2 Einstich, 3 Positionieren, 4 Bewegung,
  5 Nebenzeit (1–5 = netto), 6 Rüsten, 7 Maschinenbelegung (= 1–6). Die Bearbeitungsliste (X1) zeigt sie je Ende und
  Kontur, Summe = brutto, Rest als „Abgleich“.

## 3 Laser schneiden und Gas

- Laser schneiden = Laserzeit netto / 3600 × Stundensatz Laser (Maschine bzw. Zeitbasis des Angebots).
- Schneidgas = Gaszeit / 3600 × €/h bzw. m³/h × €/m³ (Gaszeit ohne Anfahren, Nebenzeit, Drehen, Messen, Entnahme).
- Gewinde, Senken, Flowdrill, Bohren: nur € je Stück (Stammdaten Gewinde bzw. Zusatzarbeiten), keine Zeit.

## 4 Rüsten

- Rüsten Maschine = Rüstzeit der Maschine / 60 × Satz, auf alle Teile des Laufs umgelegt (Muster: eigener Lauf).
- Rüsten je Abmessung = Rüstzeit je Abmessung / 60 × Satz (+ Sonderprofil, weitere Profilform), auf die Teile der
  Abmessung.
- Stangenwechsel = Beladungen × Zeit je Stange / 3600 × Satz, nach Längenanteil auf die Teile der Gruppe.

## 5 Zusätzliche Bearbeitung

- Weitere Arbeitsschritte = (Rüstzeit je Bezug + Zeit je Einheit × Menge) × Stundensatz bzw. Festpreis.
- Zusatzarbeit je Teil = Preis je Einheit × Menge (€/kg Gewicht, €/m² Fläche, €/m Länge, €/Stück, €/h Sekunden /
  3600 × Satz), mindestens Mindestbetrag je Teil; Mindestbetrag je Angebot anteilig angehoben; €/Angebot einmal
  umgelegt. Preis je Einheit = Festpreis + Zeit × Satz + Material × (1 + Zuschlag) + weiterer Zuschlag.
- Rüstzeit je Los (X5) = Rüstzeit [min] / 60 × Stundensatz der Zusatzarbeit, einmal je Angebot, Position oder
  Abmessung, auf deren Teile umgelegt; jede Staffel ist ein eigenes Los. Nicht bei Gewinde/Senken/Flowdrill/Bohren.
- Qualität (X4) je Position und Los = (M × t_Merkmal × n_Prüf + 60 × (t_Erstmuster + t_Protokoll)) / 3600 × S_QS;
  M = Merkmale des Prüfplans, n_Prüf = alle, ⌈Stück / n⌉ oder min(n, Stück).
- Handling Kundenmaterial = €/m × Stangenlänge des beigestellten Materials.

## 6 Herstellkosten, Selbstkosten, Gewinn, Preis

```
Herstell = (Material − Schrott + Ausschuss Material + Lagerzins) × (1 + Zuschlag Material)
         + (Laser + Gas + Gewinde + Ausschuss Fertigung + Rüsten + Arbeitsschritte + Zusatzarbeiten eigen
            + Handling + Qualität) × (1 + Zuschlag Fertigung)
         + Fremdleistungen × (1 + Zuschlag Fremdleistung)
Selbst   = Herstell + Programmierung + Pauschale je Abmessung + Angebotsaufschlag + Zukaufteile (Einstand + Aufschlag)
Gewinn   = Gewinnsatz × (Selbst − Zukaufteile)           (kein Gewinn auf Zukauf und Bleche, nur deren Aufschlag)
           Gewinn auf Material mit eigenem Satz, wenn gesetzt; gestaffelter Gewinn nach dem Wert
Preis    = (Selbst + Gewinn + Fracht) / (1 − Skonto)
```

- Danach: Musterteile auf die Serie umgelegt, Mindestpreis je Angebot (alle Preise im gleichen Verhältnis),
  Angebotsregeln, Rabatt, Rundung (zentral, Einstellung), Mannlose Laufzeit, Neuteil, Verpackung, Finanzierung.
- Staffeln rechnen jede Menge als eigenen Lauf (neu optimiert) mit denselben Bausteinen; ohne Werte in der Stufe
  ist der Staffelpreis gleich dem Verkaufspreis der Kalkulation (Test test_staffelpreise).

## 7 Rundung

- Gerechnet wird ohne Zwischenrundung; gerundet werden Preise je Teil im Angebot (Einstellung Rundung) und die Anzeige
  (Nachkommastellen der Felder). Summen im Angebot = Σ gerundeter Preis je Teil × Stück.

## Änderungsprotokoll

| Paket | Datum | Änderung |
|---|---|---|
| X7 | 12.11.2026 | 12 Referenzaufträge von Hand nachgerechnet (tests/test_referenz_kalkulation.py) |
| X2 | 12.11.2026 | Zeitbild in 7 Zeitarten, keine Zahl geändert |
| X1 | 12.11.2026 | Bearbeitungsliste je Ende und Kontur, Summe = Laserzeit brutto |
| X5 | 12.11.2026 | Zusatzarbeiten: Rüstzeit je Los, Zeitart Personal/Maschine (Schema 84) |
| X4 | 12.11.2026 | Kostenart Qualität aus dem Prüfplan, Tabelle Qualitätsstufen (Schema 84) |
| X3 | 12.11.2026 | Schachtelvergleich (nur Anzeige) |
| X6 | 12.11.2026 | Reiter Optimierung, Übernehmen als neue Fassung |
| X8 | 12.11.2026 | diese Datei |
"""


def _bereich(f):
    if f.von is None and f.bis is None:
        return ""
    return f"{'' if f.von is None else f.von:g} … {'' if f.bis is None else f.bis:g}"


def _vorgabe(e):
    if e.vorgabe in (None, ""):
        return "leer"
    if e.art == "anteil" and isinstance(e.vorgabe, (int, float)):
        return f"{100 * e.vorgabe:g} %"
    return str(e.vorgabe)


def inhalt():
    zeilen = [FORMELN.strip(), "", "## Parameter: Einstellungen", "",
              "Art „anteil“ wird in % eingegeben. Leer = siehe Vorgabe bzw. der Hinweis im Titel.", ""]
    for g in GRUPPEN:
        es = [e for e in sd.EINSTELLUNGEN if e.gruppe == g]
        if not es:
            continue
        zeilen += [f"### {g}", "", "| Name | Titel | Art | Vorgabe | Bereich |", "|---|---|---|---|---|"]
        for e in es:
            zeilen.append(f"| `{e.name}` | {e.titel.replace('|', '/')} | {e.art} | {_vorgabe(e)} | "
                          f"{_bereich(e)} |")
        zeilen.append("")
    zeilen += ["## Parameter: Stammdaten", ""]
    for t in TABELLEN:
        tab = sd.TABELLE[t]
        zeilen += [f"### {tab.titel}", "", tab.hinweis.replace("\n", " "), "", "| Feld | Titel | Art | Bereich |",
                   "|---|---|---|---|"]
        for f in tab.felder:
            zeilen.append(f"| `{f.name}` | {f.titel.replace('|', '/')} | {f.art} | {_bereich(f)} |")
        zeilen.append("")
    return "\n".join(zeilen).rstrip() + "\n"


if __name__ == "__main__":
    ZIEL.write_text(inhalt(), encoding="utf-8")
    print(f"geschrieben: {ZIEL}")
