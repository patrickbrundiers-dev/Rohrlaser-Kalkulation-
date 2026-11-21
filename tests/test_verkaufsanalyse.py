"""Verkaufsanalyse, Lernen aus Annahme/Ablehnung und Staffelkurve (Master-Prompt Angebotserstellung, Patrick
21.11.2026, Punkte 5, 8 und 9).

- Angebots-Auswertung: Reiter „Je Gewinnhöhe“, Ø Gewinn, Ø Auftragswert, verlorenes Volumen, Umsatzpotenzial,
- Startseite (Cockpit): verloren, offen, Umsatzpotenzial und Ø Gewinn,
- Trefferquote je Gewinnhöhe über alle Kunden als Hinweis im Angebot (ändert nichts),
- Staffelkurve: Stückpreis, Gesamtpreis, Gewinn und Marge je Menge, Mindestmarge als Linie.
"""
import datetime
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
from rohrlaser import absage, cockpit, lernen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


heute = datetime.date(2026, 11, 21)
d = "2026-11-10"
zeilen = [dict(id=1, vorgang="Beauftragt", vk_netto=1000.0, datum=d, gewinn=8.0),
          dict(id=2, vorgang="Beauftragt", vk_netto=3000.0, datum=d, vk_gewinn=12.0),
          dict(id=3, vorgang="Abgelehnt", vk_netto=2000.0, datum=d, gewinn=25.0),
          dict(id=4, vorgang="Verschickt", vk_netto=4000.0, datum=d, gewinn=10.0),
          dict(id=5, vorgang="Entwurf", vk_netto=500.0, datum=d)]
a = absage.auswertung(zeilen, heute=heute, zeitraum=90)
g = a["gesamt"]
assert g["offen_wert"] == 4500.0 and abs(g["trefferquote"] - 2 / 3) < 1e-9
assert g["potenzial"] == 3000.0 and g["auftrag_mittel"] == 2000.0 and abs(g["gewinn_mittel"] - 13.75) < 1e-9
klassen = {x["name"]: x for x in a["gewinn"]}
assert klassen["5 bis 10 %"]["beauftragt"] == 1 and klassen["20 bis 30 %"]["abgelehnt"] == 1
assert klassen["10 bis 15 %"]["angebote"] == 2 and klassen[absage.OHNE_GEWINN]["angebote"] == 1
assert [x["name"] for x in a["gewinn"]] == sorted(klassen, key=lambda n: ([t for _, t in absage.GEWINN_KLASSEN]
                                                                         + [absage.OHNE_GEWINN]).index(n))
ok("Auswertung: je Gewinnhöhe, Ø Gewinn 13,75 %, Ø Auftrag 2.000 €, Potenzial 4.500 € × 67 % = 3.000 €")

k = cockpit.kennzahlen(zeilen, heute=heute)
assert (k["abgelehnt"], k["abgelehnt_wert"], k["offen"], k["offen_wert"]) == (1, 2000.0, 2, 4500.0)
assert k["potenzial"] == 3000.0 and abs(k["gewinn_mittel"] - 13.75) < 1e-9
ok("Startseite: verloren 2.000 €, offen 4.500 €, Umsatzpotenzial 3.000 €, Ø Gewinn")

from rohrlaser.absage_dialog import verkauf_text  # noqa: E402

t = verkauf_text(g)
assert "Ø Auftragswert" in t and "Marge etwa" in t and "verloren" in t and "Umsatzpotenzial" in t, t
ok(f"Kopf der Auswertung: {t}")

# ------------------------------------------------------------------ Trefferquote je Gewinnhöhe (Datenbank)
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
f = Hauptfenster(db, tmp, stumm=True)
plan = [("Beauftragt", 12)] * 4 + [("Abgelehnt", 12)] * 2 + [("Beauftragt", 7)] * 5 + [("Abgelehnt", 25)] * 3
for i, (vorgang, gewinn) in enumerate(plan):
    x = beispiel_angebot.anlegen(db, dict(kundennr=f"K-{i % 4}", kunde=f"Kunde {i % 4}"))
    db.angebot_aendern(x, "gewinn", gewinn)
    db.vorgang_setzen(x, vorgang)
kl = {x["klasse"]: x for x in lernen.trefferquote_gewinn(db)}
assert (kl["10 bis 15 %"]["beauftragt"], kl["10 bis 15 %"]["abgelehnt"]) == (4, 2)
assert abs(kl["10 bis 15 %"]["quote"] - 4 / 6) < 1e-9 and kl["5 bis 10 %"]["quote"] == 1.0
assert kl["20 bis 30 %"]["quote"] is None, "unter 5 entschiedenen keine Quote"
h = lernen.gewinn_hinweis(list(kl.values()), 13.0)
assert "10 bis 15 %" in h and "67 %" in h and "5 bis 10 %: 100 %" in h, h
assert lernen.gewinn_hinweis(list(kl.values()), 25.0) == ""
ok(f"Lernen aus Annahme/Ablehnung: {h}")

a2 = beispiel_angebot.anlegen(db, dict(kundennr="K-neu", kunde="Neu GmbH"))
db.angebot_aendern(a2, "gewinn", 12.0)
s = f.angebot_oeffnen(a2)
assert s.optimieren()
s._ergebnisse_anzeigen()
assert "Alle Kunden: bei 10 bis 15 % Gewinn" in s.uebersicht_bereich.treffer.text(), s.uebersicht_bereich.treffer.text()
assert db.angebot(a2)["gewinn"] == 12.0, "Hinweis ändert nichts"
ok("Im Angebot: Trefferquote bei dieser Gewinnhöhe als Hinweis, Gewinn unverändert")

# ------------------------------------------------------------------ Staffelkurve
from rohrlaser.staffel_seite import Vergleich  # noqa: E402

v = Vergleich()
st = [dict(einheit="Stk", schluessel="10", menge=m, preis_einheit=p, preis_gesamt=p * m,
           preis=dict(gewinn_gesamt=g, marge=mg, mindestmarge=0.1))
      for m, p, g, mg in ((1, 50.0, 4.0, 0.08), (10, 20.0, 30.0, 0.15), (100, 12.0, 160.0, 0.13))]
v.setzen(st)
assert [w for _, w in v.reihen[0][1]] == [50.0, 20.0, 12.0] and v.mindestmarge is None
v.groesse_setzen("preis_gesamt")
assert [w for _, w in v.reihen[0][1]] == [50.0, 200.0, 1200.0]
v.groesse_setzen("gewinn_gesamt")
assert [w for _, w in v.reihen[0][1]] == [4.0, 30.0, 160.0]
v.groesse_setzen("marge")
assert [round(w, 6) for _, w in v.reihen[0][1]] == [8.0, 15.0, 13.0] and v.mindestmarge == 10.0
v.resize(320, 240)
v.grab()
ok("Staffelkurve: Stückpreis, Gesamtpreis, Gewinn und Marge je Menge, Mindestmarge als Linie")
f.close()
print("OK: Verkaufsanalyse, Lernen aus Annahme/Ablehnung, Staffelkurve")
