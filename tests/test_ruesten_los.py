"""Rüstzeit je Los und Personal/Maschine bei Zusatzarbeiten (Plan X5, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“).

- Rüstzeit [min] × Stundensatz der Zusatzarbeit einmal je Angebot, Position oder Abmessung, auf die Teile umgelegt
- je Staffel (andere Stückzahl) wieder einmal: der Betrag je Teil sinkt mit der Menge, der Gesamtbetrag bleibt
- Zeitart Personal/Maschine teilt die Zusatzarbeiten im Preisaufbau auf
- Gewinde, Senken, Flowdrill, Bohren: keine Rüstzeit (nur € je Stück, Prüfspalte FEHLER)
- ohne Rüstzeit rechnet alles wie bisher (alte Preisstände ohne Felder)

Aufruf: python tests/test_ruesten_los.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import rechnen, zusatz_regeln as zr  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nahe(a, b, text):
    assert abs(a - b) < 1e-6, f"{text}: {a} statt {b}"


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
tab = db.tabellen()
saetze = rechnen.stundensaetze(tab)
sid, satz = next((s, w) for s, w in saetze.items() if w)
entgraten = dict(name="Entgraten Test", art="€/Stück", preis=0.50, satz_id=sid, zeitart="Personal")
r = rechnen.zusatz_ruesten(dict(entgraten, ruestzeit=30, ruest_bezug="Position"), saetze)
nahe(r["eur"], 30 / 60 * satz, "Rüsten = min / 60 × Stundensatz")
assert r["bezug"] == "Position"
assert rechnen.zusatz_ruesten(dict(entgraten, ruestzeit=30, name="Senken"), saetze)["eur"] == 0
assert rechnen.zusatz_ruesten(dict(entgraten, ruestzeit=30, art="s/Stück"), saetze)["eur"] == 0
assert rechnen.zusatz_ruesten(dict(entgraten, ruestzeit=30, satz_id=None, satz=None), saetze)["eur"] == 0
assert zr.pruefung_zusatz(dict(name="Senken", art="€/Stück", ruestzeit=10)).startswith("FEHLER")
assert zr.pruefung_zusatz(dict(name="X", art="€/Stück", preis=1, ruestzeit=10)).startswith("WARNUNG")
ok(f"Rüstzeit 30 min × {rechnen.zahl(satz)} €/h; Senken, s/Stück und ohne Stundensatz ohne Rüsten")

k = db.kontext()
m = next(iter(k.maschinen))
a = db.angebot_neu(dict(kunde="Test", maschine=m))
db.angebot_aendern(a, "skonto", 0)
db.angebot_aendern(a, "fracht_modus", "keine Fracht")
pid = next(p for p, w in k.profile.items() if w.get("form") == "Quadratrohr")
pid2 = next(p for p, w in k.profile.items() if w.get("form") == "Rundrohr")
wst = next(iter(k.werkstoffe))


def rechne(ruest, bezug, stueck=(10, 30, 20), zeitart="Personal"):
    kat = dict(entgraten, ruestzeit=ruest, ruest_bezug=bezug, zeitart=zeitart)
    stand = rechnen.zusatz_stand(kat, saetze)
    e = json.dumps([dict(name=kat["name"], menge=None, preis=None, text=None, stand=stand)])
    pos = [dict(id=i + 1, pos=10 * (i + 1), artikel=f"T{i}", profil_id=p, werkstoff_id=wst, laenge=500, stueck=c,
                zusatz=e) for i, (p, c) in enumerate(zip((pid, pid, pid2), stueck))]
    kopf = db.angebot(a)
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return pos, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


pos, (z0, s0) = rechne(None, None)
basis = [z["zusatz_eigen_teil"] for z in z0]
nahe(basis[0], 0.50, "ohne Rüstzeit wie bisher")
assert s0["zusatz_ruesten"] == 0
eur = 30 / 60 * satz
for bezug, gruppen in (("Angebot", [[0, 1, 2]]), ("Position", [[0], [1], [2]]), ("Abmessung", [[0, 1], [2]])):
    _, (zz, ss) = rechne(30, bezug)
    for g in gruppen:
        n = sum(zz[i]["stueck"] for i in g)
        for i in g:
            nahe(zz[i]["zusatz_ruesten_teil"], eur / n, f"{bezug}: Rüsten je Teil")
            nahe(zz[i]["zusatz_eigen_teil"], 0.50 + eur / n, f"{bezug}: Zusatzarbeit je Teil")
    nahe(ss["zusatz_ruesten"], eur * len(gruppen), f"{bezug}: Rüsten gesamt")
    nahe(ss["zusatz_eigen"], 0.50 * 60 + eur * len(gruppen), f"{bezug}: Zusatzarbeiten gesamt")
    nahe(ss["zusatz_personal"], ss["zusatz_eigen"], f"{bezug}: alles Personal")
    ok(f"Rüstzeit je {bezug}: {len(gruppen)} × {rechnen.zahl(eur)} € auf die Teile umgelegt")
    if bezug == "Angebot":
        assert "darin Rüsten je Los" in rechnen.zusatz_davon(ss) and "davon Personal" in rechnen.zusatz_davon(ss)
        txt = dict((t.split(" (")[0], t) for t, _, _ in rechnen.kostenarten(ss, {}))["Zusatzarbeiten"]
        assert "Personal" in txt, txt

# Staffel: andere Menge, wieder einmal je Los
_, (zs, ss) = rechne(30, "Angebot", stueck=(100, 300, 200))
nahe(ss["zusatz_ruesten"], eur, "Staffel: Rüsten einmal je Los")
nahe(zs[0]["zusatz_ruesten_teil"], eur / 600, "Staffel: je Teil kleiner")
ok("Staffel mit 10-facher Menge: Rüsten einmal, je Teil ein Zehntel")

_, (zm, sm) = rechne(30, "Angebot", zeitart="Maschine")
nahe(sm["zusatz_maschine"], sm["zusatz_eigen"], "Maschine")
assert sm["zusatz_personal"] == 0
_, (zl, sl) = rechne(30, "Angebot", zeitart=None)
assert sl["zusatz_personal"] == 0 and sl["zusatz_maschine"] == 0 and sl["zusatz_ruesten"] > 0
ok("Zeitart Maschine bzw. leer (ohne Zuordnung)")

# Arbeitszeit der Zusatzarbeit enthält die Rüstzeit je Teil
_, (zt, _) = rechne(30, "Angebot")
nahe(sum(z["zusatz_arbeit_s"] * z["stueck"] for z in zt) - sum(z["zusatz_arbeit_s"] * z["stueck"] for z in z0),
     30 * 60, "Rüstzeit in der Arbeitszeit")
ok("Rüstzeit 30 min steht einmal in den Zeiten der Zusatzarbeiten")
print("Rüstzeit je Los stimmt.")
