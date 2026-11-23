"""Nesting-Engine (Master-Auftrag Verschachtelung auf CAD/CAM-Niveau, Patrick 23.11.2026): Strategien A–E,
Mischlängen mit Preisen, Mindestabnahme, Reststücke (nur optional), Reste bündeln, Prüfung und Längenbilanz,
Einbau in die Optimierung (Strategie je Abmessung, Belegung von Hand), Einkauf/kalkulatorisch, Lagerzustände.

Szenarien laut Auftrag: einzelnes Teil, viele gleiche Teile, verschiedene Längen und Stückzahlen, mehrere
Lieferlängen, verschiedene Preise, vorhandene Reste, nicht kompatible Werkstoffe/Querschnitte/Wandstärken,
Schnittverluste und Einspannlängen, sehr große Aufträge, Handänderungen.

Aufruf: python tests/test_nesting_2311.py
"""
import random
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import lager, nesting as ne, optimierung as opt, rechnen  # noqa: E402

EPS = 1e-6


def gruppe(teile, stange=6000, end=10, greif=142, kerf=0.2, abstand=0.0, **kw):
    g = opt.Gruppe(profil="QR 40x40x2", werkstoff="S235", stange=stange, endbeschnitt=end, greiferrest=greif,
                   kerf=kerf, abstand=abstand, **kw)
    ts = []
    for z, spec in enumerate(teile):
        laenge, n = spec[:2]
        gerade = spec[2] if len(spec) > 2 else True
        for i in range(n):
            ts.append(opt.Teil(zeile=13 + z, pos=10 * (z + 1), artikel=f"A{z}", nr=i + 1, laenge=laenge,
                               a_gerade=gerade, b_gerade=gerade, a_schnitt=160, b_schnitt=160))
    g.teile = ts
    return g


L6 = [ne.Laenge(6000, 60.0)]
MIX = [ne.Laenge(3000, 33.0), ne.Laenge(6000, 60.0), ne.Laenge(6500, 66.0), ne.Laenge(7000, 72.0)]
PATRICK = [(850, 12), (1250, 8), (430, 6), (1800, 4)]


def bilanz(g, p):
    """Bilanz je Plan: Teile + Schnitt + verwertbar + nicht verwertbar = Stangenlänge gesamt; je Stange Belegung +
    Greiferrest ≤ Stangenlänge (unabhängig von nesting.pruefe nachgerechnet)."""
    w = p.werte
    assert abs(w["teile_mm"] + w["schnitt_mm"] + w["rest_verwertbar_mm"] + w["verschnitt_mm"] - w["gesamt_mm"]) < 1e-6
    for laenge, f, _ in p.stangen:
        h = opt.replace(g, stange=laenge, teile=[t for t, _ in f])
        assert opt.verbrauch(h, f) + opt.hinten(h, f) <= laenge + EPS, (laenge, opt.verbrauch(h, f))
        assert sum(t.laenge for t, _ in f) + g.endbeschnitt <= laenge - g.greiferrest + EPS
    assert sum(len(f) for _, f, _ in p.stangen) + len(p.uebrig) == len(g.teile)


# ------------------------------------------------------------------ 1 Einzelnes Teil, viele gleiche Teile
g = gruppe([(1000, 1)])
for s in "ABDE":
    p = ne.planen(g, s, L6)
    assert p.werte["stangen"] == 1 and p.werte["teile"] == 1, (s, p.werte)
    bilanz(g, p)
g = gruppe([(1900, 30)])
p = ne.planen(g, ne.B, L6)
assert p.werte["stangen"] == 10 and opt.untergrenze(g) == 10, p.werte     # 3 × 1.900 je Stange
bilanz(g, p)
print("Einzelteil und gleiche Teile OK")

# ------------------------------------------------------------------ 2 Patrick-Beispiel: Längen mischen
g = gruppe(PATRICK)
bisher = ne._einzeln(g, 6000)
wb = ne.kennzahlen(g, bisher, [], MIX)
assert wb["stangen"] == 6 and wb["einkauf"] == 360.0, wb
pl = ne.alle(g, MIX)
for s, p in pl.items():
    bilanz(g, p)
    ne.pruefe(g, p.stangen, p.uebrig, MIX)
a, b = pl[ne.A], pl[ne.B]
assert a.werte["gekauft_mm"] < 36000 and b.werte["einkauf"] < 360.0, (a.werte["gekauft_mm"], b.werte["einkauf"])
assert a.werte["gekauft_mm"] <= min(p.werte["gekauft_mm"] for p in pl.values()) + EPS      # A = wenigste mm
assert b.werte["einkauf"] <= min(p.werte["einkauf"] for p in pl.values()) + EPS             # B = billigster Einkauf
assert pl[ne.D].werte["beladungen"] <= min(p.werte["beladungen"] for p in pl.values())      # D = wenigste Beladungen
assert ne.C not in pl                                                   # ohne Reste keine Strategie C
s, text = ne.empfehlung(pl, wb)
assert s == ne.E and "gegenüber bisher" in text and "," in text, text
print("Mischlängen OK:", text)

# andere Preise: 6,5 m sehr teuer -> B meidet 6,5 m, A nicht
TEUER = [ne.Laenge(6000, 60.0), ne.Laenge(6500, 200.0)]
pa, pb = ne.planen(g, ne.A, TEUER), ne.planen(g, ne.B, TEUER)
assert 6500 in pa.werte["je_laenge"] and 6500 not in pb.werte["je_laenge"], (pa.werte["je_laenge"], pb.werte["je_laenge"])
# fehlender Preis: nie als 0 €
pf = ne.planen(g, ne.B, [ne.Laenge(6000, None)])
assert pf.werte["einkauf"] is None and pf.werte["preis_fehlt"], pf.werte
# begrenzte Verfügbarkeit: höchstens 1 × 7 m
VERF = [ne.Laenge(6000, 60.0), ne.Laenge(7000, 65.0, anzahl=1)]
pv = ne.planen(g, ne.B, VERF)
assert pv.werte["je_laenge"].get(7000, 0) <= 1, pv.werte
# Mindestabnahme (Walzlänge vom Werk, Patrick 23.11.2026): 7 m nur ab 50 Stangen -> nicht im Plan
pm = ne.planen(g, ne.B, [ne.Laenge(6000, 60.0), ne.Laenge(7000, 65.0, mindest=50)])
assert 7000 not in pm.werte["je_laenge"], pm.werte
print("Preise, Verfügbarkeit und Mindestabnahme OK")

# ------------------------------------------------------------------ 3 Reststücke (nur optional)
RESTE = [ne.Rest("R-00001", 2400, 24.0), ne.Rest("R-00002", 1900, 19.0), ne.Rest("R-00003", 350, 3.5)]
assert not ne.verwertbar(g, 350, 500) and not ne.verwertbar(g, 200) and ne.verwertbar(g, 2400, 500)
pc = ne.planen(g, ne.C, MIX, RESTE)
bilanz(g, pc)
assert pc.werte["reste"] >= 1 and "R-00003" not in pc.werte["rest_kennungen"], pc.werte     # 350 mm nicht verwertbar
assert pc.werte["einkauf"] < b.werte["einkauf"], (pc.werte["einkauf"], b.werte["einkauf"])
assert abs(pc.werte["kalkulatorisch"] - pc.werte["einkauf"] - sum(r.wert for r in RESTE
                                                                  if r.kennung in pc.werte["rest_kennungen"])) < 1e-6
for kennung in pc.werte["rest_kennungen"]:      # Rest mit seiner echten Länge
    r = next(r for r in RESTE if r.kennung == kennung)
    assert any(abs(laenge - r.laenge) < EPS and rk == kennung for laenge, _, rk in pc.stangen)
try:
    ne.pruefe(g, pc.stangen + [pc.stangen[0]], [], MIX, RESTE)
    raise SystemExit("Doppelte Stange nicht erkannt")
except AssertionError:
    pass
print("Reststücke OK")

# ------------------------------------------------------------------ 4 Reste bündeln: gleiche Stangenzahl, größter Rest
random.seed(7)
g = gruppe([(random.randint(300, 2200), random.randint(2, 9)) for _ in range(12)])
roh = ne._einzeln(g, 6000)
neu = ne.buendeln(g, roh)
assert len(neu) <= len(roh)
ne.pruefe(g, neu, [], L6)
fr_roh = sorted((ne.frei(g, x, f) for x, f, _ in roh), reverse=True)
fr_neu = sorted((ne.frei(g, x, f) for x, f, _ in neu), reverse=True)
assert sum(x * x for x in fr_neu) >= sum(x * x for x in fr_roh) - EPS and fr_neu[0] >= fr_roh[0] - EPS
print(f"Bündeln OK: größter freier Platz {fr_roh[0]:.0f} -> {fr_neu[0]:.0f} mm")

# ------------------------------------------------------------------ 5 Schnittverluste, Abstand, Einspannlänge, Gehrung
g = gruppe([(995, 18, False), (1495, 6)], kerf=1.0, abstand=10.0, greif=300, end=20)
for s in "ABDE":
    p = ne.planen(g, s, MIX)
    bilanz(g, p)
    for laenge, f, _ in p.stangen:      # ungerade Enden: 2 Schnitte + Abstand, nie gemeinsamer Schnitt
        assert opt.gemeinsame_schnitte(f) <= sum(1 for (t1, _), (t2, _) in zip(f, f[1:]) if t1.b_gerade and t2.a_gerade)
print("Schnittverlust und Einspannlänge OK")

# ------------------------------------------------------------------ 6 Sehr großer Auftrag (Zeit und Reproduzierbarkeit)
random.seed(3)
gross = [(random.randint(150, 2900), random.randint(5, 30)) for _ in range(30)]
g = gruppe(gross)
t = time.perf_counter()
p1 = ne.planen(g, ne.B, MIX)
dt = time.perf_counter() - t
opt.merker_leeren()
p2 = ne.planen(gruppe(gross), ne.B, MIX)
assert [(x, [(t.zeile, t.nr) for t, _ in f]) for x, f, _ in p1.stangen] == \
       [(x, [(t.zeile, t.nr) for t, _ in f]) for x, f, _ in p2.stangen], "nicht reproduzierbar"
bilanz(g, p1)
wb = ne.kennzahlen(g, ne._einzeln(g, 6000), [], MIX)
assert p1.werte["einkauf"] <= wb["einkauf"] + EPS
print(f"Großer Auftrag OK: {p1.werte['teile']} Teile, {dt:.1f} s, {wb['einkauf']:.0f} -> {p1.werte['einkauf']:.0f} €")

# ------------------------------------------------------------------ 7 Einbau in die Optimierung
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
QR, RE, ST, VA = "QR 40x40x3", "RE 60x40x3", "S235-10219", "1.4301"
for laenge in (6500, 7000):
    db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=laenge))
einst = db.einstellungen()
kopf = dict(maschine="T03", stange=6000)
pos = [dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id=QR, werkstoff_id=ST, laenge=lg, stueck=n)
       for i, (lg, n) in enumerate(PATRICK)]
pos.append(dict(pos=90, artikel="RE", profil_id=RE, werkstoff_id=ST, laenge=1200, stueck=7))      # andere Abmessung
k, tab = db.kontext(), db.tabellen()
erg0 = rechnen.optimieren(kopf, pos, k, tab, einst)
erg1 = rechnen.optimieren(kopf, pos, k, tab, einst)
assert erg0 == erg1 and not any(s.get("nesting") for s in erg0["stangen"])     # Vorgabe: wie bisher
schl = rechnen.laengen_schluessel(("QR 40x40x3", ST, "", 6000))
kb = dict(kopf, nesting={schl: "A"})
erg = rechnen.optimieren(kb, pos, k, tab, einst)
qr = [s for s in erg["stangen"] if s["profil"] == QR]
re_ = [s for s in erg["stangen"] if s["profil"] == RE]
assert all(s["nesting"] == "A" for s in qr) and not any(s.get("nesting") for s in re_)      # nur diese Abmessung
assert sum(s["stange"] for s in qr) < sum(s["stange"] for s in erg0["stangen"] if s["profil"] == QR)
assert {s["stange"] for s in qr} <= {6000, 6500, 7000}
assert not erg["fehler"] and sum(len(s["teile"]) for s in qr) == 30
assert any("Verschachtelung A" in a["bewertung"] for a in erg["auswertung"])
sw = rechnen.stangen_werte(erg, kb, pos, k, tab)
assert all(w["pruefung"] == "OK" for w in sw)
assert all("einkauf" in w for s, w in zip(erg["stangen"], sw) if s.get("nesting"))
assert all("einkauf" not in w for s, w in zip(erg["stangen"], sw) if not s.get("nesting"))
# Einstellung für alle Abmessungen, „bisher“ je Abmessung schlägt sie
e2 = dict(einst, nesting_strategie="B Geringste Materialkosten")
erg = rechnen.optimieren(dict(kopf, nesting={schl: "bisher"}), pos, k, tab, e2)
assert not any(s.get("nesting") for s in erg["stangen"] if s["profil"] == QR)
assert all(s.get("nesting") == "B" for s in erg["stangen"] if s["profil"] == RE)
# Kalkulation läuft mit dem Nesting-Plan
z, summen = rechnen.kalkulation(kb, pos, rechnen.optimieren(kb, pos, k, tab, einst), k, tab,
                                rechnen.einstellungen_angebot(kb, einst))
assert summen and z
print("Einbau in die Optimierung OK")

# ------------------------------------------------------------------ 8 Belegung von Hand
erg = rechnen.optimieren(kb, pos, k, tab, einst)
qr = [s for s in erg["stangen"] if s["profil"] == QR]
hand = [dict(laenge=s["stange"], rest="", teile=[[t["ref"], t["laenge"]] for t in s["teile"]]) for s in qr]
# ein Teil von der letzten auf die erste Stange, wenn es passt; sonst auf eine eigene Stange
t = hand[-1]["teile"].pop()
hand.append(dict(laenge=6000, rest="", teile=[t]))
kh = dict(kopf, stangen_hand={schl: hand})
erg_h = rechnen.optimieren(kh, pos, k, tab, einst)
qh = [s for s in erg_h["stangen"] if s["profil"] == QR]
assert all(s["nesting"] == rechnen.NESTING_HAND for s in qh) and sum(len(s["teile"]) for s in qh) == 30
assert any(len(s["teile"]) == 1 and s["stange"] == 6000 for s in qh)
assert any("Belegung von Hand" in a["bewertung"] for a in erg_h["auswertung"])
# Menge geändert: überzählige Teile fallen weg, neue werden dazu geplant (B), nie überbelegt
pos2 = [dict(p, stueck=p["stueck"] + 3) if p["pos"] == 10 else p for p in pos]
erg_m = rechnen.optimieren(kh, pos2, k, tab, einst)
assert sum(len(s["teile"]) for s in erg_m["stangen"] if s["profil"] == QR) == 33 and not erg_m["fehler"]
assert all(w["pruefung"] == "OK" for w in rechnen.stangen_werte(erg_m, kh, pos2, k, tab))
# überbelegte Handstange wird aufgelöst
voll = [dict(laenge=6000, rest="", teile=[[t["ref"], t["laenge"]] for s in qr for t in s["teile"]])]
erg_v = rechnen.optimieren(dict(kopf, stangen_hand={schl: voll}), pos, k, tab, einst)
assert any("aufgelöst" in a["bewertung"] for a in erg_v["auswertung"])
assert all(w["pruefung"] == "OK" for w in rechnen.stangen_werte(erg_v, kopf, pos, k, tab))
print("Belegung von Hand OK")

# ------------------------------------------------------------------ 9 Reststücke nur optional, Lagerzustände
reste = [dict(id=1, kennung="R-00007", profil=QR, werkstoff=ST, oberflaeche="", laenge=2600, verfuegbar=1,
              status="frei"),
         dict(id=2, kennung="R-00008", profil=QR, werkstoff=VA, oberflaeche="", laenge=5000, verfuegbar=1,
              status="frei"),                                    # anderer Werkstoff: nie
         dict(id=3, kennung="R-00009", profil=QR, werkstoff=ST, oberflaeche="", laenge=4000, verfuegbar=1,
              status="gesperrt")]                                # gesperrt: nie
tab_r = dict(tab, lager_reste=reste)
kc = dict(kopf, nesting={schl: "C"})
aus = rechnen.optimieren(kc, pos, k, tab_r, einst)                # Lager aus: C rechnet wie B, keine Reste
assert not any(s.get("rest") for s in aus["stangen"])
an = dict(einst, lager_aktiv="ja", reste_aktiv="ja")
erg_c = rechnen.optimieren(kc, pos, k, tab_r, an)
mit = [s for s in erg_c["stangen"] if s.get("rest")]
assert [s["rest"] for s in mit] == ["R-00007"] and mit[0]["stange"] == 2600, [(s["rest"], s["stange"]) for s in mit]
sw = rechnen.stangen_werte(erg_c, kc, pos, k, tab_r)
w = next(w for s, w in zip(erg_c["stangen"], sw) if s.get("rest"))
assert w["einkauf"] == 0.0 and w["kosten"] == mit[0]["rest_wert"] > 0 and w["pruefung"] == "OK"

for n, v in (("lager_aktiv", "ja"), ("reste_aktiv", "ja")):
    db.einstellung_setzen(n, v)
(rid,) = lager.zugang(db, "Rest", QR, ST, 2600, 1)
assert [z["kennung"] for z in lager.reste_fuer_nesting(db)] == [lager.posten(db, rid)["kennung"]]
lager.status_setzen(db, rid, "gesperrt", "krumm")
assert lager.reste_fuer_nesting(db) == []
lager.status_setzen(db, rid, "Ausschuss")
assert lager.bestand(db)[0]["status"] == "Ausschuss" and lager.reste_fuer_nesting(db) == []
lager.status_setzen(db, rid, "frei")
assert len(lager.reste_fuer_nesting(db)) == 1
assert any(b["art"] == "Status" for b in lager.buchungen(db, bestand_id=rid))
db.einstellung_setzen("reste_aktiv", "nein")
assert lager.reste_fuer_nesting(db) == []                       # nur optional (Patrick 23.11.2026)
print("Reststücke optional und Lagerzustände OK")

# ------------------------------------------------------------------ 9b 12 m mit Zuschnitt (immer ganze Stange bezahlt)
m03 = k.maschinen["T03"]
maxw = rechnen._n(m03.get("max_stange"))
for laenge in (6000, 12000):
    db.neu("lieferlaengen", dict(profil_id=RE, werkstoff_id=ST, laenge=laenge))
k, tab = db.kontext(), db.tabellen()
schl_re = rechnen.laengen_schluessel((RE, ST, "", 6000))
p31 = [dict(pos=10, artikel="Z", profil_id=RE, werkstoff_id=ST, laenge=3100, stueck=31)]
e_zs = dict(einst, zuschnitt_kosten=0.0)
erg6 = rechnen.optimieren(kopf, p31, k, tab, e_zs)
erg_z = rechnen.optimieren(dict(kopf, nesting={schl_re: "A"}), p31, k, tab, e_zs)
sw6, swz = rechnen.stangen_werte(erg6, kopf, p31, k, tab), rechnen.stangen_werte(erg_z, kopf, p31, k, tab)
assert all(w["pruefung"] == "OK" for w in swz) and sum(len(s["teile"]) for s in erg_z["stangen"]) == 31
if maxw and maxw < 12000:
    zug = [s for s in erg_z["stangen"] if s.get("werkstuecke")]
    assert zug and all(s["stange"] == 12000 and s["nesting"] == "A" for s in zug), [s["stange"] for s in erg_z["stangen"]]
    mm6, mmz = sum(s["stange"] for s in erg6["stangen"]), sum(s["stange"] for s in erg_z["stangen"])
    assert mmz < mm6 and mmz <= 126000, (mmz, mm6)   # 31 × 3.100: 6 m trägt 1 Teil, 12 m (Zuschnitt) 3 Teile
    a = next(a for a in erg_z["auswertung"] if a.get("nesting"))
    assert "mit Zuschnitt" in a["bewertung"] and a["nesting_werte"]["zuschnitt_laenge"] == 12000, a
    print("Zuschnitt 12 m OK:", a["bewertung"], f"({mm6} -> {mmz} mm)")
else:
    print("Zuschnitt 12 m: Maschine lädt 12 m selbst, kein Zuschnitt nötig")

# ------------------------------------------------------------------ 10 Gespeichert je Angebot (Schema 103)
aid = db.angebot_neu(dict(nummer="NEST-1", kunde="Test", maschine="T03", stange=6000))
db.nesting_speichern(aid, {schl: "B"}, {schl: hand})
a = db.angebot(aid)
assert a["nesting"] == {schl: "B"} and a["stangen_hand"] == {schl: hand}
kopie = db.angebot_kopieren(aid)
assert db.angebot(kopie)["nesting"] == {schl: "B"}
db.nesting_speichern(aid, {}, {})
assert db.angebot(aid)["nesting"] is None and db.angebot(aid)["stangen_hand"] is None
db.schliessen()
print("Speichern je Angebot OK")
print("Alle Tests OK")
