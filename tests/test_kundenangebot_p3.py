"""Angebotswesen P3 (Patrick 20.11.2026): Kundenangebot der Angebotsakte erweitert.

- Kopffeld Projekt / Bauvorhaben (Spalte angebote.projekt) im Angebot und im Kundenangebot,
- Konditionen mit Versand, Verpackung und Rabatt (ohne interne Beträge), Hinweis auf die AGB (Einstellung),
- Termin-Staffel: Preis je Liefertermin (Einstellung termin_staffel), Abschläge höchstens bis zur Mindestmarge,
  intern mit Marge je Termin; ohne Einstellung keine Tabelle. Kalkulation und Stückpreise bleiben unverändert.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import akte_pdf, termin_staffel  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Termin-Staffel lesen und rechnen
assert termin_staffel.lesen("1 Woche: +15; 3 Wochen: 0; 6 Wochen: -3") == [("1 Woche", 0.15), ("3 Wochen", 0.0),
                                                                          ("6 Wochen", -0.03)]
assert termin_staffel.lesen("KW 50 = 10 %\n8 Wochen: −2,5") == [("KW 50", 0.10), ("8 Wochen", -0.025)]
assert termin_staffel.lesen("") == [] and termin_staffel.fehler("1 Woche +15; 3 Wochen: 0") == ["1 Woche +15"]
summen = dict(selbst=800.0, gewinn=200.0, skonto_satz=0.0)
t = termin_staffel.rechnen_termine(dict(termin_staffel="eilig: 10; spät: -10"), 1000.0, summen)
assert [x["netto"] for x in t] == [1100.0, 900.0] and not any(x["begrenzt"] for x in t)
assert abs(t[1]["marge"] - 100 / 900) < 1e-9
# Mindestmarge 15 %: Gewinn muss ≥ 0,15·800/0,85 = 141,18 € bleiben -> höchstens 58,82 € Abschlag
t = termin_staffel.rechnen_termine(dict(termin_staffel="spät: -10", mindestmarge=0.15), 1000.0, summen)
assert t[0]["begrenzt"] and abs(t[0]["netto"] - 941.18) < 0.006 and t[0]["marge"] >= 0.15 - 1e-4, t
t = termin_staffel.rechnen_termine(dict(termin_staffel="spät: -10", mindestmarge=0.30), 1000.0, summen)
assert t[0]["begrenzt"] and t[0]["netto"] == 1000.0, "unter der Mindestmarge kein Abschlag, nie ein Aufschlag"
assert termin_staffel.rechnen_termine({}, 1000.0, summen) == []
ok("Termin-Staffel: Text lesen, Zu-/Abschlag je Termin, Abschlag höchstens bis zur Mindestmarge")

# ------------------------------------------------------------------ Angebot mit Projekt, Rabatt, Termin-Staffel
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
db.einstellung_setzen("pdf_vorschau", "nein")
f = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
db.angebot_aendern(a, "projekt", "Halle 3, Bauvorhaben Musterstraße")
db.angebot_aendern(a, "fracht_modus", "keine Fracht")
s = f.angebot_oeffnen(a)
assert s.optimieren()
assert s.kopf.get("projekt") == "Halle 3, Bauvorhaben Musterstraße"
zeilen, summen = s._rechnung()
vorher = (summen["verkauf"], [z["preis_teil"] for z in zeilen if z])

akte = s.akte_sammeln(bilder=False)
k = akte["kunde"]
assert k["projekt"] == "Halle 3, Bauvorhaben Musterstraße" and k["termine"] == []
assert k["versand"] == "ab Werk, Fracht nicht enthalten"
assert k["agb"] == "Es gelten unsere Allgemeinen Geschäftsbedingungen."
ok("Kundenangebot: Projekt, Versand und AGB-Hinweis; ohne Einstellung keine Termin-Staffel")

db.einstellung_setzen("termin_staffel", "1 Woche (Eilfertigung): +15; 3 Wochen: 0; 8 Wochen: -3")
db.einstellung_setzen("mindestmarge", 0.05)
s.neu_laden()
akte = s.akte_sammeln(bilder=False)
k, g = akte["kunde"], akte["gesamt"]
zeilen, summen = s._rechnung()
assert (summen["verkauf"], [z["preis_teil"] for z in zeilen if z]) == vorher, "Kalkulation unverändert"
assert [x["termin"] for x in k["termine"]] == ["1 Woche (Eilfertigung)", "3 Wochen", "8 Wochen"]
assert k["termine"][1]["netto"] == k["netto"] and k["termine"][0]["netto"] > k["netto"] > k["termine"][2]["netto"]
assert set(k["termine"][0]) == {"termin", "netto", "differenz"}, "keine Marge im Kundenteil"
assert len(g["termine"]) == 3 and all(x["marge"] is not None for x in g["termine"])
assert all(x["marge"] >= 0.05 - 1e-4 or x["satz"] >= 0 for x in g["termine"])
ok("Termin-Staffel im Angebot: Kunde sieht Netto je Termin, intern mit Marge; Kalkulation bitgleich")

pfad = tmp / "kunde.pdf"
akte_pdf.schreiben(pfad, akte, s.einst, "kunde")
text = " ".join(akte_pdf.text_der_seiten(pfad))
for wort in ("Projekt", "Halle 3, Bauvorhaben Musterstraße", "Versand", "ab Werk", "Preis nach Liefertermin",
             "1 Woche (Eilfertigung)", "8 Wochen", akte_pdf.geld(k["termine"][0]["netto"]),
             "Allgemeinen Geschäftsbedingungen"):
    assert wort.lower() in text.lower(), wort
assert akte_pdf.kunde_pruefen(pfad) == [], akte_pdf.kunde_pruefen(pfad)
pfad = tmp / "intern.pdf"
akte_pdf.schreiben(pfad, akte, s.einst, "intern", [7])
text = " ".join(akte_pdf.text_der_seiten(pfad))
assert "Preis nach Liefertermin" in text and "Marge" in text
ok("PDF: Kundenangebot mit Projekt, Versand, Termin-Staffel und AGB ohne interne Begriffe; intern mit Marge")

# Rabatt und Verpackung in den Konditionen (aus der Kalkulation, ohne Beträge)
k2 = dict(k, rabatt_satz=5.0, verpackung="im Preis enthalten")
pfad = tmp / "kunde2.pdf"
akte_pdf.schreiben(pfad, dict(akte, kunde=k2), s.einst, "kunde", [1])
text = " ".join(akte_pdf.text_der_seiten(pfad))
assert "5,0 % in den Preisen berücksichtigt" in text and "verpackung" in text.lower()
ok("Konditionen: Rabatt und Verpackung als zweite Reihe")

f.close()
print("OK: Kundenangebot P3 (Projekt, Konditionen, AGB, Termin-Staffel)")
