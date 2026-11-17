"""Eingeschnittene und gebogene Quadrat-/Rechteckrohre abwickeln (Patrick 17.11.2026, tube-laser-cut-1:
Bend_Profile_Long; Plan „gebogene und geknickte Rohre abwickeln“ B1, step_kerbbiegen).

Das Rohr wird gerade gelasert: an jeder Biegestelle sind Seitenwände und Innenwand keilförmig ausgeschnitten, nur
die Außenwand mit einem schmalen Rand bleibt stehen und wird mit Radius gebogen. Die STEP zeigt das gebogene Teil
(Testteile aus formen_kerbbiegen). Gemessen wird das gerade Rohr:
- Länge = gerade Schenkel + je Biegung (R − s/2) × Winkel (neutrale Faser der Außenwand),
- jede Kerbe als Kontur, Bohrungen an ihrer Stelle am geraden Rohr (Lage ab Ende A),
- Hinweis „Gebogenes Rohr abgewickelt“ mit Winkel und Radius je Biegung.

K1 RE 50 × 30 × 2,6, eine Biegung 35° R150
K2 zwei Biegungen in einer Ebene (30° R150, 40° R120), dazu Kerben auf beiden Seiten (S-Form)
K3 zwei Biegungen in verschiedenen Ebenen (Kerbe einmal auf der schmalen, einmal auf der breiten Seite) – Plan B1
K4 QR 40 × 40 × 3, drei Biegungen (20°, 60°, 90°), Radien 80 bis 200
K5 Gegenprobe: gerades Rohr, Rohr ohne Kerbe mit großer Bohrung bleiben wie bisher
K6 voller Querschnitt gebogen, ohne Kerbe (Plan B3): RE um beide Achsen und QR, gestreckt auf der Mittellinie
   (R − Tiefe/2) wie beim Biegerohr
K7 Arbeitsschritt Biegen (Plan B5): ein abgewickeltes Rohr schlägt „Biegen“ gelb vor, Menge = Zahl der Biegungen;
   ohne Zusatzarbeit, schon eingetragen oder ohne Abwicklung kein Vorschlag

Aufruf: python tests/test_kerbbiegen.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

import erzeuge_testteile as et  # noqa: E402
import formen_kerbbiegen as fk  # noqa: E402
import step_geometrie as g  # noqa: E402
from OCP.TopAbs import TopAbs_SOLID  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402


def ok(text):
    print("OK:", text)


def messen(form, name, tmp):
    et.schreibe(form, name, tmp)
    (t,) = analysiere_datei(tmp / f"{name}.step")
    return t


def pruefe(tmp, name, schenkel, biegungen, a=50.0, b=30.0, s=2.6, rk=5.2, bohrungen=(), rand=6.0):
    form, soll = fk.gebogen(schenkel, biegungen, a, b, s, rk, rand=rand, bohrungen=bohrungen)
    voll = rand > min(a, b)
    assert len(g._liste(form, TopAbs_SOLID)) == 1, name
    t = messen(form, name, tmp)
    profil = "Quadratrohr" if a == b else "Rechteckrohr"
    assert t.bauteiltyp == "Profil" and t.profilform == profil, (name, t.bauteiltyp, t.profilform, t.hinweise)
    assert abs(t.abm_a - max(a, b)) < 0.01 and (abs(t.abm_b - min(a, b)) < 0.01 or (a == b and t.abm_b == 0)) and abs(t.wandstaerke - s) < 0.02, \
        (name, t.abm_a, t.abm_b, t.wandstaerke)
    assert abs(t.laenge - soll) < 0.1, (name, t.laenge, soll)
    assert t.hinweise and t.hinweise[0].startswith("Gebogenes Rohr abgewickelt"), t.hinweise
    assert f"{len(biegungen)} Biegung" in t.hinweise[0], t.hinweise[0]
    innen = [d for d in t.konturen_liste if d.get("art") not in ("Ende A", "Ende B")]
    kerben = [d for d in innen if d.get("art") == "Sonderkontur"]
    assert len(kerben) == (0 if voll else len(biegungen)), (name, [(d.get("art"), d.get("z")) for d in innen])
    # Kerbe liegt am Bogen ihrer Biegung (gestreckt)
    z = 0.0
    for i, bg in enumerate(biegungen):
        z += schenkel[i]
        lg = (bg["r"] - s / 2) * bg["winkel"] * 3.141592653589793 / 180
        assert voll or any(z - 1 <= d["z"] <= z + lg + 1 for d in kerben), (name, i, z, [d["z"] for d in kerben])
        z += lg
    # Bohrungen an ihrer Stelle am geraden Rohr (beide Wände)
    for nr, lage, d, _ in bohrungen:
        z = sum(schenkel[:nr]) + sum((x["r"] - ((a if x["aussen"][1] == "x" else b) / 2 if voll else s / 2)) *
                                     x["winkel"] * 3.141592653589793 / 180 for x in biegungen[:nr]) + lage
        treffer = [x for x in innen if x.get("art") == "Bohrung" and abs(x.get("durchmesser", 0) - d) < 0.05
                   and (abs(x["z"] - z) < 0.1 or abs(x["z"] - (t.laenge - z)) < 0.1)]
        assert len(treffer) == 2, (name, z, [(x.get("durchmesser"), x["z"]) for x in innen])
    return t, soll


def k1(tmp):
    t, soll = pruefe(tmp, "K1", [120, 200], [dict(winkel=35, r=150, aussen="-x")], bohrungen=[(1, 100, 10, "z")])
    ok(f"K1 RE 50×30×2,6, 35° R150: gerades Rohr L {t.laenge:.2f} (soll {soll:.2f}), Kerbe und Bohrung an ihrer Stelle")


def k2(tmp):
    for name, aussen2 in (("K2_eben", "-x"), ("K2_S", "+x")):
        t, soll = pruefe(tmp, name, [100, 80, 150], [dict(winkel=30, r=150, aussen="-x"),
                                                    dict(winkel=40, r=120, aussen=aussen2)],
                         bohrungen=[(1, 40, 8, "z"), (2, 60, 12, "z")])
    ok(f"K2 zwei Biegungen in einer Ebene (gleiche Seite und S-Form): L {t.laenge:.2f} (soll {soll:.2f})")


def k3(tmp):
    t, soll = pruefe(tmp, "K3", [100, 80, 150], [dict(winkel=30, r=150, aussen="-x"),
                                                 dict(winkel=45, r=100, aussen="-z")],
                     bohrungen=[(0, 50, 10, "x"), (2, 50, 10, "z")])
    ok(f"K3 zwei Biegungen in verschiedenen Ebenen: L {t.laenge:.2f} (soll {soll:.2f}), Kerben auf zwei Seiten")


def k4(tmp):
    t, soll = pruefe(tmp, "K4", [80, 120, 60, 100], [dict(winkel=20, r=200, aussen="-x"),
                                                     dict(winkel=60, r=120, aussen="+z"),
                                                     dict(winkel=90, r=80, aussen="-x")],
                     a=40.0, b=40.0, s=3.0, rk=6.0, bohrungen=[(3, 50, 8, "x")])
    ok(f"K4 QR 40×40×3, drei Biegungen (20°, 60°, 90°): L {t.laenge:.2f} (soll {soll:.2f})")


def k5(tmp):
    t = messen(fk.rohr(50, 30, 2.6, 5.2, -100, 200), "K5_gerade", tmp)
    assert t.profilform == "Rechteckrohr" and abs(t.laenge - 300) < 0.05
    assert not any("Gebogenes Rohr" in h for h in t.hinweise), t.hinweise
    rr = fk._bool(fk.BRepAlgoAPI_Cut, fk.rohr(50, 30, 2.6, 5.2, 0, 300), fk._zylinder((0, 150, 0), (1, 0, 0), 12))
    t = messen(rr, "K5_bohrung", tmp)
    assert t.profilform == "Rechteckrohr" and abs(t.laenge - 300) < 0.05 and not any("Gebogenes" in h
                                                                                      for h in t.hinweise)
    ok("K5 gerades Rohr und Rohr mit Bohrung unverändert")


def k6(tmp):
    for name, aussen, a, b, ri in (("K6_RE_x", "-x", 50.0, 30.0, "z"), ("K6_RE_z", "-z", 50.0, 30.0, "x"),
                                   ("K6_QR", "-x", 40.0, 40.0, "z")):
        t, soll = pruefe(tmp, name, [120, 200], [dict(winkel=45, r=150, aussen=aussen)], a=a, b=b,
                         rand=max(a, b) + 0.5, bohrungen=[(1, 100, 10, ri)])
        assert "voller Querschnitt" in t.hinweise[0] and "Mittellinie" in t.hinweise[0], t.hinweise[0]
    t, soll = pruefe(tmp, "K6_zwei", [100, 80, 150], [dict(winkel=30, r=200, aussen="-x"),
                                                      dict(winkel=60, r=160, aussen="-z")], rand=50.5)
    ok(f"K6 voller Querschnitt gebogen (RE um beide Achsen, QR, zwei Ebenen): Mittellinie, L {t.laenge:.2f} "
       f"(soll {soll:.2f})")


def k7():
    import json

    from rohrlaser import step, zusatz_erkennung as ze
    katalog = [dict(name="Biegen", art="€/Stück", preis=1.5, aktiv="ja"), dict(name="Strahlen", aktiv="ja")]
    m = dict(hinweise="Gebogenes Rohr abgewickelt: 3 Biegungen (20° R200, 60° R120, 90° R80), gestreckte Länge …")
    e = ze.gemerkt(step.biegen_vorschlag(dict(), m, katalog))
    assert [(x["name"], x["menge"], x["quelle"]) for x in e] == [("Biegen", 3, "STEP")], e
    v = ze.offen(dict(step.biegen_vorschlag(dict(), m, katalog), art="Rohr"), {}, None,
                 dict(zusatzarbeiten=katalog))
    assert [(x["name"], x["menge"]) for x in v] == [("Biegen", 3)], v
    assert not step.biegen_vorschlag(dict(), m, katalog[1:]).get("arbeitsgaenge")
    assert not step.biegen_vorschlag(dict(), dict(hinweise="Biegerohr"), katalog).get("arbeitsgaenge")
    da = dict(zusatz=json.dumps([dict(name="Biegen", menge=3)]))
    assert not step.biegen_vorschlag(da, m, katalog).get("arbeitsgaenge")
    eigen = [dict(name="Rohr biegen (extern)", aktiv="ja")]
    assert ze.gemerkt(step.biegen_vorschlag(dict(), m, eigen))[0]["name"] == "Rohr biegen (extern)"
    ok("K7 Biegen als gelber Vorschlag, Menge = Biegungen; ohne Zusatzarbeit/schon da/nicht abgewickelt: nichts")


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    k1(tmp)
    k2(tmp)
    k3(tmp)
    k4(tmp)
    k5(tmp)
    k6(tmp)
    k7()
    print("Alle Tests bestanden.")
