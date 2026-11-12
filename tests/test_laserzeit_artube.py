"""Laserzeit genauer (Plan ArTube-Unterlagen Paket 2 und 7, Patrick 12.11.2026 „Alles einbauen“; zeit_zusatz.py):
- Z1 Regeln: Seiten, Drehzeit je Seitenwechsel, Messzyklen, Active Tilt, Abfall zerteilen, Anfahrweg mit Überlappung,
  dicke Wand mit N₂, Schnittqualität (auch Kleines Rohr automatisch), Ausrichten, Lademinimum, Entladegrenze
- Z2 Angebot ohne neue Maschinenfelder: alle neuen Zeitanteile 0, Laserzeit bitgleich mit dem alten Rechenweg
- Z3 Angebot mit Feldern: jeder Anteil von Hand nachgerechnet, Laser brutto wächst genau um die Summe, Drehen/Messen/
  Entnahme ohne Schneidgas, Ausrichten des U-Profils je Stange im Stangenwechsel
- Z4 Schnittqualität Qualität: Schneidanteile × 1,25

Aufruf: python tests/test_laserzeit_artube.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import rechnen, zeit_zusatz as zz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) <= eps * max(1.0, abs(a), abs(b)), f"{text}: {a} != {b}"


def technik(*konturen):
    return json.dumps(dict(quelle="Schneidweg-Rechner", konturen=list(konturen)))


B_OBEN = dict(art="Bohrung", d=12, anzahl=4, abstand=30, x=300, seite="oben")
B_UNTEN = dict(art="Bohrung", d=12, anzahl=1, x=600, seite="unten")
GROSS = dict(art="Rechteck", b=150, h=30, anzahl=1, x=900, seite="vorne")

# ------------------------------------------------------------------ Z1 Regeln
p = dict(laenge=1200, technik=technik(B_OBEN, B_UNTEN, GROSS))
assert zz.seiten(p) == 3 and zz.seiten(dict(laenge=1000)) == 0
assert zz.drehen_s(p, dict(zeit_drehen=2.5)) == 5.0 and zz.drehen_s(p, {}) == 0
assert zz.messen_s(dict(messungen=3), {}) == 12 and zz.messen_s(dict(messungen=3, messart="sorgfältig"), {}) == 24
assert zz.messen_s(dict(messungen=2), dict(zeit_messen_schnell=5)) == 10 and zz.messen_s({}, {}) == 0
m_t = dict(active_tilt="ja")
assert zz.tilt_s(p, m_t, 2.0, 1.0) == 3 * 0.5 and zz.tilt_s(p, m_t, 4.0, 1.0) == 0 and zz.tilt_s(p, {}, 2.0, 1.0) == 0
n, mm = zz.abfall_zerteilen(p, dict(abfall_max=100))
assert n == 1 and mm > 150 - 1e-6, (n, mm)
assert zz.abfall_zerteilen(p, {}) == (0, 0.0) and zz.abfall_zerteilen(p, dict(abfall_max=500)) == (0, 0.0)
assert zz.anfahrweg_mm(p, dict(anfahrweg=3), 2, 6) == 18 and zz.anfahrweg_mm(p, dict(anfahrweg=3), 8, 6) == 24
assert zz.beschleunigung(dict(beschleunigung_dick="ja"), 8, "N₂") == 1.2
assert zz.beschleunigung(dict(beschleunigung_dick="ja"), 8, "O₂") == 1.0
assert zz.beschleunigung(dict(beschleunigung_dick="ja"), 5, "N₂") == 1.0 and zz.beschleunigung({}, 12, "N₂") == 1.0
rr = dict(form="Rundrohr", a=16, b=None, wand=1.5)
assert zz.qualitaet({}, dict(kleines_rohr_bis=20), rr) == "Kleines Rohr" and zz.qualitaet({}, {}, rr) == "Standard"
assert zz.qualitaet(dict(schnittqualitaet="Schnell"), dict(kleines_rohr_bis=20), rr) == "Schnell"
v, fe = zz.vorschuebe((3000, 2000, 1000, 5000, 0.5), dict(schnittqualitaet="Qualität"), {}, rr, 2, "N₂")
assert v == (2400, 1600, 800, 5000, 0.5) and fe == 1.0
v, fe = zz.vorschuebe((3000, 2000, 1000, 5000, 0.5), {}, dict(beschleunigung_dick="ja"), rr, 10, "N₂")
nah(v[1], 2000 / 1.3) and nah(v[2], 1000 / 1.3)
assert v[0] == 3000 and fe == 1.3


class K:
    profile = {"U": dict(form="U-Profil"), "Q": dict(form="Quadratrohr")}


s_u, s_q = dict(profil="U", stange=6000), dict(profil="Q", stange=2000, werkstuecke=[dict(laenge=1800), dict(laenge=3000)])
m_b = dict(zeit_ausrichten=20, lademinimum=2500)
assert zz.beladung_s(s_u, m_b, K) == 20 and zz.beladung_s(s_q, m_b, K) == 60 and zz.beladung_s(s_u, {}, K) == 0
assert zz.kurz_geladen([s_u, s_q], m_b) == 1
assert zz.entnahme_grund(dict(laenge=4000), dict(entlade_laenge=3000), None).startswith("Teil länger")
assert zz.entnahme_s(dict(laenge=4000), dict(entlade_laenge=3000), None) == 30
assert zz.entnahme_s(dict(laenge=2000), dict(entlade_laenge=3000), None) == 0
ok("Z1 Regeln: 3 Seiten -> 2 × Drehzeit, Messen 4/8 s, Tilt bis 3 mm, Abfall > Grenze, Anfahrweg + 1 mm ab 6 mm, "
   "N₂ ab 6 mm langsamer, Qualität/Kleines Rohr, Ausrichten, Lademinimum, Entladegrenze")


# ------------------------------------------------------------------ Z2/Z3 Angebot
def angebot(db, maschine=None, pos_extra=None):
    for x in db.zeilen("maschinen"):
        for n_, w in (maschine or {}).items():
            db.aendern("maschinen", x["id"], n_, w)
    a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
    db.position_neu(a, dict(pos=10, artikel="Q1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1200,
                            stueck=10, schneidweg=900, einstiche=8, technik=technik(B_OBEN, B_UNTEN, GROSS),
                            **(pos_extra or {})))
    db.position_neu(a, dict(pos=20, artikel="U1", profil_id="UPN 40", werkstoff_id="S235-10219", laenge=700,
                            stueck=5, schneidweg=300, einstiche=2))
    kopf, pos = db.angebot(a), db.positionen(a)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    e = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    return zeilen, summen, erg


tmp = Path(tempfile.mkdtemp())
NEU = ("drehen", "messen", "anfahrweg", "abfall", "entnahme")
z0, s0, e0 = angebot(Datenbank(tmp / "alt.db"))
assert all(not z[f"zeit_{n_}"] for z in z0 for n_ in NEU) and not s0["beladung_extra_s"]
ok(f"Z2 ohne neue Felder: neue Zeitanteile 0, Laser brutto Q1 {z0[0]['laser_brutto']:.2f} s")

MASCH = dict(zeit_drehen=2.0, zeit_ausrichten=15, active_tilt="ja", abfall_max=100, anfahrweg=3.0,
             entlade_laenge=1000, zeit_kontur=1.0)
z1, s1, e1 = angebot(Datenbank(tmp / "neu.db"), MASCH, dict(messungen=2, messart="sorgfältig"))
a, b = z1[0], z0[0]
nah(a["zeit_drehen"], 2 * 2.0, "Drehen")
nah(a["zeit_messen"], 2 * 8.0, "Messen")
nah(a["zeit_entnahme"], 30.0, "Entnahme")
nah(a["zeit_anfahrweg"], 60 * 6 * 3.0 / a["vorschub_klein"], "Anfahrweg 6 Innenkonturen")    # 4 + 1 + 1
assert a["zeit_abfall"] > 0
mehr = sum(a[f"zeit_{n_}"] for n_ in NEU) + a["zeit_anfahren"] - (b["zeit_anfahren"] or 0)
nah(a["laser_brutto"], b["laser_brutto"] + mehr, "Laser brutto = vorher + neue Anteile")
nah(a["zeit_anfahren"], 8 * 1.0 - 3 * 0.5, "Anfahren mit Active Tilt (3 weitere Löcher)")
assert not z1[1]["zeit_entnahme"]
n_u = sum(1 for s in e1["stangen"] if s["profil"] == "UPN 40")
nah(s1["beladung_extra_s"], 15 * n_u, "Ausrichten U-Profil je Stange")
nah(s1["stangenwechsel_s"], s0["stangenwechsel_s"] + 15 * n_u, "Stangenwechsel + Ausrichten")
if a.get("zeit_gas") is not None and b.get("zeit_gas") is not None:
    nah(a["zeit_gas"] - b["zeit_gas"], a["zeit_anfahrweg"] + a["zeit_abfall"], "Gas nur für Anfahrweg und Abfall")
ok(f"Z3 mit Feldern: Drehen {a['zeit_drehen']:.1f} s, Messen {a['zeit_messen']:.1f} s, Anfahrweg "
   f"{a['zeit_anfahrweg']:.2f} s, Abfall {a['zeit_abfall']:.2f} s, Entnahme 30 s, Tilt −1,5 s, Ausrichten {n_u} × 15 s")

zq, _, _ = angebot(Datenbank(tmp / "q.db"), None, dict(schnittqualitaet="Qualität"))
for n_ in ("gross", "mittel", "klein"):
    if z0[0][f"zeit_{n_}"]:
        nah(zq[0][f"zeit_{n_}"], z0[0][f"zeit_{n_}"] / 0.8, n_)
ok(f"Z4 Schnittqualität Qualität: Schneidzeit groß {z0[0]['zeit_gross']:.2f} -> {zq[0]['zeit_gross']:.2f} s")
print("Alle Laserzeit-Tests (ArTube) bestanden.")
