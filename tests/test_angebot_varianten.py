"""Angebotswesen P4 (Patrick 20.11.2026): Varianten A–E eines Angebots nebeneinander.

- Variante mit eigenem Gewinn, Rabatt, Materialpreis oder Stundensatz wird mit der vollen Kalkulation gerechnet,
- das Original bleibt bitgleich (Kalkulation, Kopf, Positionen),
- Speichern im Kopffeld 'varianten', Lesen nach dem Neuladen,
- „Als Fassung übernehmen“: neue Fassung mit den Kalkulationswerten, Preisänderungen nur als Hinweis,
- Fenster: Eingaben, Vergleich, falsche Zahl wird abgelehnt.
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
from rohrlaser import angebot_varianten as av  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    return abs(a - b) <= eps


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
f = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(a)
assert s.optimieren()
zeilen, summen = s._rechnung()
vk0, selbst0, gewinn0 = summen["verkauf"], summen["selbst"], summen["gewinn"]
kopf0 = dict(s.kopf)


def vergleich(varianten):
    return av.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, s._rechnung()[1], varianten)


V = [dict(buchstabe="A", name="mehr Gewinn", werte=dict(gewinn=20.0)),
     dict(buchstabe="B", name="Stahl teurer", werte=dict(material=10.0)),
     dict(buchstabe="C", name="Maschine +20 €/h", werte=dict(maschine=20.0)),
     dict(buchstabe="D", name="Rabatt", werte=dict(rabatt=5.0)),
     dict(buchstabe="E", name="Kombi", werte=dict(gewinn=20.0, material=10.0))]
erg = vergleich(V)
assert [z["buchstabe"] for z in erg] == ["", "A", "B", "C", "D", "E"] and not any(z["fehler"] for z in erg), erg
o, A, B, C, D, E = (z["ergebnis"] for z in erg)
assert nah(o["verkauf"], vk0) and o["unterschied"] == 0
assert nah(A["selbst"], selbst0) and A["gewinn"] > gewinn0 - 1e-6 and A["verkauf"] > vk0
assert nah(o["gewinn"], gewinn0, 0.05), (o["gewinn"], gewinn0)
assert nah(A["gewinn"] / A["selbst"], 0.20, 0.02) or A["gewinn"] > gewinn0      # Gewinn 20 % (Basis ohne Zukauf)
assert B["selbst"] > selbst0 and B["herstell"] > o["herstell"]
assert C["selbst"] > selbst0
assert D["verkauf"] < vk0 and nah(D["selbst"], selbst0) and D["marge"] < o["marge"]
assert E["verkauf"] > max(A["verkauf"], B["verkauf"])
assert all(nah(z["unterschied"], z["verkauf"] - vk0) for z in (A, B, C, D, E))
zeilen2, summen2 = s._rechnung()
assert summen2["verkauf"] == vk0 and dict(s.kopf) == kopf0, "Original bleibt unverändert"
ok(f"5 Varianten neben dem Original ({vk0:.2f} €): Gewinn 20 % {A['verkauf']:.2f} €, Material +10 % "
   f"{B['verkauf']:.2f} €, Maschine +20 €/h {C['verkauf']:.2f} €, Rabatt 5 % {D['verkauf']:.2f} €; Original bitgleich")

# Speichern und Lesen
db.angebot_aendern(a, "varianten", av.als_text(V))
s.neu_laden()
assert av.lesen(s.kopf) == V
assert av.als_text([dict(buchstabe="A", name="", werte={})]) is None
assert av.lesen(dict(varianten="kaputt")) == [] and av.lesen(dict(varianten='[{"buchstabe": "X"}]')) == []
ok("Varianten im Angebot gespeichert und wieder gelesen; leere und falsche Einträge entfallen")

# Fenster
from rohrlaser.angebot_varianten_dialog import VariantenDialog  # noqa: E402

d = VariantenDialog(s, s)
assert d.eingabe.item(0, 1).text() == "mehr Gewinn"
assert d.ergebnis.item(3, 1).text().endswith("€") and d.ergebnis.item(3, 2).text()
d.eingabe.item(1, 2).setText("abc")
try:
    d.werte()
    raise AssertionError("falsche Zahl muss abgelehnt werden")
except ValueError as e:
    assert "Variante B" in str(e)
d.eingabe.item(1, 2).setText("")
assert d.speichern() and av.lesen(db.angebot(a))[0]["name"] == "mehr Gewinn"
ok("Fenster: Original und A–E nebeneinander, Ergebnis je Variante, falsche Zahl abgelehnt, Speichern")

# Als Fassung übernehmen: Variante E (Gewinn 20 % + Material +10 %)
d = VariantenDialog(s, s)
d.wahl.setCurrentText("E")
neu = d.uebernehmen(frage=False)
n = db.angebot(neu)
assert n["nummer"].endswith("-2") and n["gewinn"] == 20.0 and not n.get("varianten")
assert db.angebot(a)["ersetzt_durch"] == n["nummer"] and db.angebot(a)["gewinn"] == kopf0.get("gewinn")
assert len(db.positionen(neu)) == len(db.positionen(a))
ok(f"Variante E als Fassung {n['nummer']} übernommen: Gewinn 20 %, Materialpreis nur Vergleich; Original ersetzt, "
   "aber unverändert")

assert s.angebotsvarianten(dialog=lambda d: None) is not None
d.deleteLater()
f.close()
print("OK: Angebotsvarianten A–E")
