"""Paket 9 (Vorschläge L2, L4, L6, Patrick 08.11.2026 „Alle Empfehlungen“; L3 steht in test_art_auswahl.py):
L2 „Passt“ bestätigt alle gelben Teile gleicher Form in allen Dateien, der Knopf zeigt „Passt (N gleiche)“.
L4 Angebots-Check: „N Teile aus dem STEP-Import ungeprüft (gelb)“ und „vereinfacht gemessen“ als Hinweis mit Sprung.
L6 Prüfdialog „Werte setzen“: Art und Profil für markierte bzw. alle Zeilen.

Aufruf: python tests/test_paket9.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen  # noqa: E402
from formen_baukasten import ohne, quader, schreibe  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_check as ac  # noqa: E402
from rohrlaser import step, step_pruefung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


rohr = ohne(quader(500, 40, 40), quader(500, 34, 34, 0, 3, 3))
schreibe({"A_Rohr": rohr, "B_Rohr": rohr, "C_Rohr": ohne(quader(800, 40, 40), quader(800, 34, 34, 0, 3, 3)),
          "Lasche": quader(146, 40, 9.5)}, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(TMP / f"{n}.step") for n in ("A_Rohr", "B_Rohr", "C_Rohr", "Lasche")])
MW = step.lies_messwerte(aus)
app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "p.db")
k = db.kontext()

# ------------------------------------------------------------------ L2 Passt für gleiche Teile
werte = [dict(m) for m in MW]
for m in werte:
    m["pruefstatus"] = "prüfen"                 # alle gelb („nur nach den Maßen erkannt“)
d = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[])
d.show()
app.processEvents()


def zeile(name):
    return next(z for z in d.zeilen if name in d.messwerte[z.liste[0]]["datei"])


a, b, c = zeile("A_Rohr"), zeile("B_Rohr"), zeile("C_Rohr")
assert a.ampel == b.ampel == c.ampel == "gelb"
assert d.gleiche_gelbe(a) == [b], [d.messwerte[x.liste[0]]["datei"] for x in d.gleiche_gelbe(a)]
d.baum.setCurrentItem(a.it)
d._ampel_zeigen()
assert d.passt_knopf.text() == "Passt (1 gleiche)", d.passt_knopf.text()
d.passt(a)
assert a.ampel == "gruen" and b.ampel == "gruen" and c.ampel == "gelb", (a.ampel, b.ampel, c.ampel)
assert all(werte[i].get("_geprueft") for i in b.liste)
ok("L2: „Passt (1 gleiche)“ bestätigt das gleiche Rohr der anderen Datei mit, das längere bleibt gelb")

# ------------------------------------------------------------------ L4 Angebots-Check
gelb_m = dict(werte[c.liste[0]])
gruen_m = dict(werte[a.liste[0]])
p_gelb = dict(pos=10, stueck=1, profil_id="QR 40x40x3", step_merkmale=step_pruefung.speicherwert(gelb_m))
p_gruen = dict(pos=20, stueck=1, profil_id="QR 40x40x3", step_merkmale=step_pruefung.speicherwert(gruen_m))
assert json.loads(p_gelb["step_merkmale"])["ampel"] == "gelb" and step_pruefung.gelb_ungeprueft(p_gelb)
assert not step_pruefung.gelb_ungeprueft(p_gruen) and json.loads(p_gruen["step_merkmale"]).get("geprueft")
einf = dict(gelb_m, hinweise="vereinfacht gemessen (Zeitlimit 20 s): nur Hüllmaß und Volumen")
p_einf = dict(pos=30, stueck=1, profil_id="QR 40x40x3", step_merkmale=step_pruefung.speicherwert(einf))
assert step_pruefung.vereinfacht(p_einf)
kopf = dict(kunde="Muster GmbH", kundennr="K1", kundenreferenz="Anfrage 7", lieferzeit_art="Arbeitstage",
            lieferzeit_wert=10)
pos = [p_gruen, p_gelb, p_einf]
liste = ac.punkte(kopf, pos, ["OK"] * 3, "aktuell", dict(verkauf=1000.0, gewinn=100.0, selbst=900.0),
                  kalk_zeilen=[{}, {}, {}], kunde=dict(email="a@b.de"), mindestmarge=0.05)
g = next(x for x in liste if "ungeprüft (gelb)" in x.text)
v = next(x for x in liste if "vereinfacht gemessen" in x.text)
assert g.art == ac.HINWEIS and g.text.startswith("1 Teil aus dem STEP-Import") and g.ziel == "stepgelb:1", g
assert v.art == ac.HINWEIS and v.ziel == "stepgelb:2", v
assert not any("STEP-Merkmale zu prüfen" in x.text and "Pos. 30" in (x.details or "") for x in liste)
ok("L4: gelbe ungeprüfte Teile und vereinfacht gemessene als Hinweis mit Sprung zur Position, „Passt“ zählt nicht")

# ------------------------------------------------------------------ L6 Art und Profil für alle
werte = [dict(m) for m in MW]
d = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[])
d.show()
app.processEvents()
assert d.alle_art.count() == 1 + len(step.ART_GRUPPEN) and d.alle_profil.count() > 1
lasche = next(z for z in d.zeilen if "Lasche" in d.messwerte[z.liste[0]]["datei"])
ziel = step.ART_BLECH if step.art_gruppe(d.messwerte[lasche.liste[0]]) != step.ART_BLECH else step.ART_PROFIL
d.baum.clearSelection()
lasche.it.setSelected(True)
n = d.alle_setzen(art=ziel, nur_markierte=True)
lasche = next(z for z in d.zeilen if "Lasche" in d.messwerte[z.liste[0]]["datei"])
assert n == 1 and step.art_gruppe(d.messwerte[lasche.liste[0]]) == ziel, n
assert ziel in d.art_merken.values()
rohre = [z for z in d.zeilen if "Rohr" in d.messwerte[z.liste[0]]["datei"]]
pid = next(p for p in sorted(k.profile) if p.startswith("QR"))
d.alle_setzen(profil=pid)
assert all(z.pr.currentText() == pid for z in rohre), [z.pr.currentText() for z in rohre]
ok(f"L6: Art „{ziel}“ für die markierte Zeile, Profil {pid} für alle Rohre über „Werte setzen“")

print("Paket 9: alle Tests bestanden.")
