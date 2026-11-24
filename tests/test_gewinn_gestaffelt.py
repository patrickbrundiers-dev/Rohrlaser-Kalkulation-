"""Gestaffelter Gewinn (Wunsch Patrick 29.10.2026: „Gewinn in 4 oder 5 Stufen … bis Preis x soviel %“).

- Vorgabe aus (Grenze 1 leer): Preise bitgleich wie mit festem Gewinn.
- Stufen nach der Gewinnbasis (Selbstkosten ohne Zukaufteile) des ganzen Angebots, ein Satz für alle Positionen.
- Preisboden an den Grenzen: ein größerer Auftrag wird nie billiger als einer an der Grenze darunter.
- Eigener Gewinn im Angebot oder in der Staffelstufe schaltet die Stufen aus; festgeschriebene Angebote unverändert.
- Staffelpreise: Satz nach dem Wert der ganzen Staffelstufe, ohne Stufenwerte = Verkaufspreis der Kalkulation.

Aufruf: python tests/test_gewinn_gestaffelt.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNGEN  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    return abs(a - b) < eps


STUFEN = dict(gewinn_bis_1=500, gewinn_satz_1=0.30, gewinn_bis_2=2000, gewinn_satz_2=0.20, gewinn_bis_3=10000,
              gewinn_satz_3=0.12, gewinn_satz_4=0.08)

# ------------------------------------------------------------------ Stufen und Preisboden
assert rechnen.gewinn_stufen({}) == [] and rechnen.gewinn_stufen(dict(STUFEN, gewinn_bis_1=0)) == []
st = rechnen.gewinn_stufen(STUFEN)
assert st == [(500, 0.30), (2000, 0.20), (10000, 0.12), (None, 0.08)], st
assert rechnen.gewinn_stufen(dict(STUFEN, gewinn_bis_2=400))[-1] == (None, 0.20), "fallende Grenze beendet die Liste"
g = rechnen.gewinn_gestaffelt
assert nah(g(400, st), 120) and nah(g(500, st), 150) and nah(g(501, st), 149) and nah(g(1500, st), 300)
vorher = 0.0
for basis in range(10, 20000, 7):
    preis = basis + g(basis, st)
    assert preis >= vorher - 1e-9, (basis, preis, vorher)
    vorher = preis
ok("Stufen 30 % bis 500 €, 20 % bis 2.000 €, 12 % bis 10.000 €, darüber 8 %; Preis steigt mit dem Auftragswert "
   "ohne Sprung nach unten (Boden an den Grenzen)")

# ------------------------------------------------------------------ Einstellungen
titel = {f.name: f.titel for f in EINSTELLUNGEN}
assert all(f"gewinn_bis_{i}" in titel for i in range(1, 5)) and all(f"gewinn_satz_{i}" in titel for i in range(1, 6))
assert all(f"gewinn_bis_{i}" in rechnen.EINST_FEST for i in range(1, 5)) and "gewinn_bis_1" in rechnen.EINST_NEU
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert not rechnen.gewinn_stufen(db.einstellungen()), "Vorgabe aus"
ok("Einstellungen Grenze 1–4 und Satz 1–5, Vorgabe aus; festgeschriebene Angebote ohne Werte = aus")

# ------------------------------------------------------------------ Angebote
k, tab = db.kontext(), db.tabellen()
basis_einst = db.einstellungen()
geprueft = 0
for an in ANGEBOTE:
    kopf = dict(maschine=an["maschine"], stange=an["stange"])
    positionen = [dict(pos=p_["pos"], artikel=p_["artikel"], bezeichnung=p_["bezeichnung"], profil_id=p_["profil"],
                       werkstoff_id=p_["werkstoff"], laenge=p_["laenge"], stueck=p_["stueck"],
                       **{n: p_[n] for n in ("schneidweg", "einstiche", "stange", "a_gerade", "b_gerade") if n in p_})
                  for p_ in an["positionen"]]
    erg = rechnen.optimieren(kopf, positionen, k, tab, basis_einst)
    fest = rechnen.einstellungen_angebot(kopf, basis_einst)
    _, s0 = rechnen.kalkulation(kopf, positionen, erg, k, tab, fest)
    _, s1 = rechnen.kalkulation(kopf, positionen, erg, k, tab, dict(fest, gewinn=1.0))
    basis = s1["gewinn"]
    e = rechnen.einstellungen_angebot(kopf, dict(basis_einst, **STUFEN))
    z, s = rechnen.kalkulation(kopf, positionen, erg, k, tab, e)
    assert s.get("gewinn_gestaffelt") and nah(s["gewinn"], g(basis, st), 1e-4), (an["nummer"], s["gewinn"], basis)
    assert nah(s["gewinn_stufen_basis"], basis) and not s0.get("gewinn_gestaffelt")
    # eigener Gewinn des Angebots: Stufen aus, Preis wie mit festem Gewinn
    k2 = dict(kopf, gewinn=15)
    _, sa = rechnen.kalkulation(k2, positionen, erg, k, tab, rechnen.einstellungen_angebot(k2, dict(basis_einst, **STUFEN)))
    _, sb = rechnen.kalkulation(k2, positionen, erg, k, tab, rechnen.einstellungen_angebot(k2, basis_einst))
    assert sa["verkauf"] == sb["verkauf"] and not sa.get("gewinn_gestaffelt")
    # Staffelpreise: Stufe mit den Mengen des Angebots = Verkaufspreis des Angebots (gleicher Satz)
    stufen = [dict(schluessel=str(p_["pos"]), menge=p_["stueck"]) for p_ in positionen[:2]]
    for x in staffeln.rechnen_alle(kopf, positionen, stufen, k, tab, e):
        if x["preis"]:
            assert nah(x["preis"]["netto"], x["bausteine"]["verkauf"]), (an["nummer"], x["schluessel"])
    geprueft += 1
assert geprueft == len(ANGEBOTE)
ok(f"{geprueft} Abnahmeangebote: Gewinn = Stufe der Gewinnbasis des Angebots; eigener Gewinn im Angebot schaltet "
   "die Stufen aus; Staffelstufe = Verkaufspreis ihres Mengenlaufs")

# ------------------------------------------------------------------ Staffelstufe: ganze Stufe, eigener Gewinn
b = dict(material=300.0, material_fehlt=0, fertigung=[("Laser schneiden", 200.0, "")], ruesten=[], fremd=0.0,
         pauschalen=0.0, programmierung=0.0, angebotsaufschlag=0.0, fracht=0.0, skonto_satz=0.0, satz_maschine=60.0,
         verkauf=None)
NULL = dict(zuschlag_material=0, zuschlag_fertigung=0, zuschlag_fremdleistung=0, gewinn=0.1, mwst=0.19, **STUFEN)
lz = [dict(bausteine=b, menge=10), dict(bausteine=dict(b), menge=20)]
mz = [dict(schluessel="1", menge=10), dict(schluessel="2", menge=20)]
zeilen = staffeln.stufe_bepreisen(lz, {}, mz, NULL)
assert all(nah(x["preis"]["gewinn"], 500 * 0.20 * 2 / 2) for x in zeilen), [x["preis"]["gewinn"] for x in zeilen]
einzeln = staffeln.preise(b, 10, staffeln.wirksam({}, NULL))
assert nah(einzeln["gewinn"], 150), "eine Zeile allein: 500 € Basis -> 30 %"
eigen = staffeln.stufe_bepreisen(lz, dict(gewinn=5), mz, NULL)
assert all(nah(x["preis"]["gewinn"], 25) for x in eigen)
ok("Staffelstufe mit zwei Zeilen à 500 €: Satz nach 1.000 € (20 %), eine Zeile allein 30 %; eigener Gewinn der "
   "Stufe 5 % gilt")
# ------------------------------------------------------------------ neues Angebot: ohne eigenen Gewinn
assert db.kalkulation_vorgaben()["gewinn"] == 10.0
a_fest = db.angebot_neu(dict(kunde="Fest"))
for n, w in STUFEN.items():
    db.einstellung_setzen(n, w)
assert db.kalkulation_vorgaben()["gewinn"] is None and db.kopf_vorgaben()["gewinn"] is None
a_neu = db.angebot_neu(dict(kunde="Gestaffelt"))
assert db.angebot(a_neu)["gewinn"] is None and db.angebot(a_fest)["gewinn"] == 10.0
assert rechnen.gewinn_stufen(rechnen.einstellungen_angebot(db.angebot(a_neu), db.einstellungen()))
assert not rechnen.gewinn_stufen(rechnen.einstellungen_angebot(db.angebot(a_fest), db.einstellungen()))
ok("mit Stufen bekommt ein neues Angebot keinen festen Gewinn mehr (rechnet gestaffelt); bestehende Angebote "
   "behalten ihren Gewinn")
db.schliessen()
print("OK: Gestaffelter Gewinn")
