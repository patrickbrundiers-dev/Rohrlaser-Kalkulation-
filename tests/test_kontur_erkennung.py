"""Erkennung von Endkonturen und Sonderkonturen aus der STEP (Patrick 25.11.2026 „Erkennung weiter verbessern und
optimieren“, „Sonderkonturen müssen auch erkannt werden“).

1. endkontur.erkennen: Umriss jeder Konturart (V-Spitze, V-Kerbe, U-Kerbe, U-Zunge, Bogen konvex/konkav, S-Kurve,
   Schräg, Stufen; mit Versatz und Richtung) an Quadrat-, Rechteck- und Rundrohr wird mit Art und Maßen erkannt und
   trifft den Umriss überall auf 0,1 mm; gerade Enden und Freiformen werden nicht „erkannt“.
2. form_erkennung.erkennen: Kreis, Langloch, Rechteck mit/ohne Radius in beliebiger Lage, Dreieck, Sechseck;
   unregelmäßige Formen = Freiform mit Geraden/Bögen; Messrauschen 0,03 mm.
3. Verschachtelung: kein Zuschlag für einen gemessenen Schwenk bei 2D-Schnitten (Innenkante unter der Außenkante).
4. Prüfsätze als STEP (tests/erzeuge_endkonturen.py, tests/erzeuge_sonderkonturen.py) über den echten Import:
   alle Sollwerte erkannt, Anzeige im Editor, Verschachtelungstiefe wie konstruiert.

Aufruf: python werkzeuge/mit_pg.py -- python tests/test_kontur_erkennung.py
"""
import math
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "werkzeuge"), str(HIER)]

from rohrlaser import endkontur as ek, form_erkennung as fe, skizze as sk  # noqa: E402

fehler = 0


def pruef(bed, text):
    global fehler
    if not bed:
        fehler += 1
        print("FEHLER", text)


def qs_von(form, a, b, wand, r):
    return sk.Querschnitt(dict(form=form, a=a, b=b, wand=wand, r_aussen=r))


QS = [("QR60", qs_von("Quadratrohr", 60, None, 3, 6.0)), ("RE80x40", qs_von("Rechteckrohr", 80, 40, 3, 6.0)),
      ("RR60", qs_von("Rundrohr", 60.3, None, 3, None))]


def test_endkontur_rundlauf():
    """Kontur -> Umriss -> erkennen: gleiche Art, Umriss überall auf 0,1 mm."""
    for name, qs in QS:
        halb = (ek._wbereich(qs, 0)[1] - ek._wbereich(qs, 0)[0]) / 2
        arten = [dict(typ=ek.V_SPITZE, tiefe=20), dict(typ=ek.V_SPITZE, tiefe=12, versatz=6),
                 dict(typ=ek.V_KERBE, tiefe=15, breite=round(1.2 * halb, 1)),
                 dict(typ=ek.U_KERBE, tiefe=18, breite=round(halb, 1)),
                 dict(typ=ek.U_ZUNGE, tiefe=18, breite=round(halb, 1)),
                 dict(typ=ek.BOGEN_VEX, tiefe=10), dict(typ=ek.BOGEN_KAV, tiefe=8),
                 dict(typ=ek.S_KURVE, tiefe=14),
                 dict(typ=ek.STUFEN, stufen=[[round(halb, 2), 0.0], [round(halb, 2), 12.0]]),
                 dict(typ=ek.V_KERBE, tiefe=10, breite=20, richtung=90)]
        for k in arten:
            um = ek.umriss(qs, k)
            er = ek.erkennen(qs, um)
            pruef(er is not None, f"{name} {ek.text(k)}: nicht erkannt")
            if not er:
                continue
            pk = ek.umriss(qs, er["kontur"])
            x = ek.kurven_abstand(um, pk, qs.umfang)
            pruef(x <= 0.1 + 1e-9, f"{name} {ek.text(k)} -> {ek.text(er['kontur'])}: {x:.3f} mm daneben")
            pruef(er["abweichung"] <= 0.1, f"{name} {ek.text(k)}: Abweichung {er['abweichung']}")
            # Art: Schräg/S-Kurve dürfen gleichwertig erkannt werden, sonst dieselbe Art
            if k["typ"] not in (ek.S_KURVE,):
                pruef(er["kontur"]["typ"] == k["typ"], f"{name} {ek.text(k)}: als {ek.text(er['kontur'])} erkannt")
        # gerade und unregelmäßig: keine Konturart
        pruef(ek.erkennen(qs, [[0, 0], [qs.umfang / 2, 0]]) is None, f"{name}: gerades Ende erkannt")
        rnd = random.Random(3)
        frei = [[qs.umfang * i / 40, rnd.uniform(0, 12)] for i in range(40)]
        er = ek.erkennen(qs, frei)
        pruef(er is None or ek.kurven_abstand(frei, ek.umriss(qs, er["kontur"]), qs.umfang) <= 0.1,
              f"{name}: Zickzack als {er and ek.text(er['kontur'])} erkannt")
    print("OK endkontur rundlauf")


def test_kurven_abstand():
    U = 240.0
    a = [[0, 0], [100, 0], [100.0, 12], [200, 12]]
    b = [[0, 0], [100.05, 0], [100.05, 12], [200, 12]]
    x = ek.kurven_abstand(a, b, U)
    pruef(abs(x - 0.05) < 1e-6, f"Sprung 0,05 mm versetzt = {x} (soll 0,05, nicht die Stufenhöhe)")
    print("OK kurven_abstand")


def test_formen():
    rnd = random.Random(7)

    def rauschen(p, a=0.03):
        return [(x + rnd.uniform(-a, a), y + rnd.uniform(-a, a)) for x, y in p]
    kreis = [(10 * math.cos(2 * math.pi * i / 72), 10 * math.sin(2 * math.pi * i / 72)) for i in range(72)]
    faelle = [
        (kreis, fe.KREIS, "Kreis Ø20"),
        (fe._langloch(3, 1, 40, 12, 30, 40), fe.LANGLOCH, "Langloch 40 × 12, 30° zur Achse"),
        (fe._langloch(0, 0, 30, 8, 90, 30), fe.LANGLOCH, "Langloch 30 × 8, quer"),
        (fe._rechteck(0, 0, 30, 16, 45, 3), fe.RECHTECK, "Rechteck 30 × 16 R3, 45° zur Achse"),
        (fe._rechteck(0, 0, 30, 16, 120, 3, 4), fe.RECHTECK, "Rechteck 30 × 16 R3, 120° zur Achse"),
        (fe._rechteck(0, 0, 30, 16, 33.3), fe.RECHTECK, "Rechteck 30 × 16, 33,3° zur Achse"),
        (rauschen(fe._rechteck(5, 5, 30, 16, 33, 4, 10)), fe.RECHTECK, "Rechteck 30 × 16 R4, 33° zur Achse"),
        ([(10 * math.cos(2 * math.pi * i / 6), 10 * math.sin(2 * math.pi * i / 6)) for i in range(6)], fe.VIELECK,
         "Sechseck SW 17,3"),
        ([(0, 0), (20, 0), (10, 17.3205)], fe.DREIECK, "Dreieck 20 × 20 × 20"),
        ([(0, 0), (20, 0), (20, 5), (10, 5), (10, 15), (0, 15)], fe.FREIFORM, "Freiform: 6 Geraden"),
        ([(x * 1.3, y) for x, y in kreis], fe.FREIFORM, None),          # Ellipse: kein Kreis
    ]
    for pts, typ, text in faelle:
        r = fe.erkennen(pts)
        pruef(r and r["typ"] == typ, f"{text or typ}: erkannt als {r and r.get('text')}")
        if r and text:
            pruef(r["text"] == text, f"Text {r['text']!r}, soll {text!r}")
        if r and typ != fe.FREIFORM:
            pruef(r["abweichung"] <= fe.ERKENNUNG_TOL, f"{text}: Abweichung {r['abweichung']}")
    pruef(fe.erkennen([(0, 0), (1, 0)]) is None, "zwei Punkte erkannt")
    # gleich lange Seiten, aber 40°/80° im Wechsel: kein regelmäßiges Sechseck
    sechs, x, y, w = [], 0.0, 0.0, 0.0
    for i in range(6):
        sechs.append((x, y))
        x, y = x + 10 * math.cos(math.radians(w)), y + 10 * math.sin(math.radians(w))
        w += 40 if i % 2 == 0 else 80
    r = fe.erkennen(sechs)
    pruef(r and r["typ"] == fe.FREIFORM, f"Sechseck 40°/80° als {r and r['text']} erkannt")
    # dichte Umrisse (Review #661): schnell und gleich erkannt
    import time
    for n in (250, 600, 1500):
        k = [(10 * math.cos(2 * math.pi * i / n) + rnd.uniform(-.02, .02),
              10 * math.sin(2 * math.pi * i / n) + rnd.uniform(-.02, .02)) for i in range(n)]
        t0 = time.perf_counter()
        r = fe.erkennen(k)
        dt = time.perf_counter() - t0
        pruef(r and r["text"] == "Kreis Ø20", f"Kreis mit {n} Punkten als {r and r['text']}")
        pruef(dt < 2.0, f"Kreis mit {n} Punkten: {dt:.1f} s")
    ll = fe._langloch(3, 1, 40, 12, 30, 400)
    r = fe.erkennen(ll)
    pruef(r and r["text"] == "Langloch 40 × 12, 30° zur Achse", f"dichtes Langloch als {r and r['text']}")
    pruef(fe.text(dict(form_erkannt=dict(text="Sechseck SW 17,3"))) == "Sechseck SW 17,3: Umriss wie STEP",
          "Bemerkungstext")
    print("OK formen")


def test_freimachung():
    """Rechteck mit Freimachungen Ø d (mittig auf der Ecke / um r längs versetzt), Ausklinkung am Ende."""
    def bogen(mx, my, r, w0, w1, n=36):
        return [(mx + r * math.cos(math.radians(w0 + (w1 - w0) * i / n)),
                 my + r * math.sin(math.radians(w0 + (w1 - w0) * i / n))) for i in range(n + 1)]

    def gerade(a, b, n=40):
        return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(1, n)]
    # 60 × 20, Ø10 mittig auf den Ecken: je Ecke 270° außen herum
    mittig = (bogen(-30, -10, 5, 90, 360) + gerade((-25, -10), (25, -10)) + bogen(30, -10, 5, 180, 450)
              + gerade((30, -5), (30, 5)) + bogen(30, 10, 5, 270, 540) + gerade((25, 10), (-25, 10))
              + bogen(-30, 10, 5, 0, 270) + gerade((-30, 5), (-30, -5)))
    # dasselbe um r längs versetzt (Mitte auf der langen Seite, Patrick „besser“): je Ecke ein Halbkreis
    versetzt = (bogen(-25, -10, 5, 180, 360) + gerade((-20, -10), (20, -10)) + bogen(25, -10, 5, 180, 360)
                + gerade((30, -10), (30, 10)) + bogen(25, 10, 5, 0, 180) + gerade((20, 10), (-20, 10))
                + bogen(-25, 10, 5, 0, 180) + gerade((-30, 10), (-30, -10)))
    r = fe.erkennen(mittig)
    pruef(r and r["text"] == "Rechteck 60 × 20, Freimachung 4 × Ø10 mittig", f"mittig: {r and r['text']}")
    pruef(r and r.get("freimachung_d") == 10 and r.get("freimachung_lage") == "mittig"
          and r.get("freimachung_anzahl") == 4, f"Felder {r}")
    r = fe.erkennen(versetzt)
    pruef(r and r["text"] == "Rechteck 60 × 20, Freimachung 4 × Ø10 versetzt", f"versetzt: {r and r['text']}")
    # eine Freimachung kleiner (Ø6 statt Ø10): kein einheitliches Rechteck mit Freimachung
    schief = (bogen(-30, -10, 3, 90, 360) + gerade((-27, -10), (25, -10)) + mittig[37 + 39:])
    r = fe.erkennen(schief)
    pruef(not r or r["typ"] != fe.RECHTECK_FREI, f"falsche Lage erkannt: {r and r['text']}")
    # Ausklinkung am Ende (Tiefe je Umfangsstelle), RE 60 × 40 scharfkantig wie Patricks Teil C
    qs = qs_von("Rechteckrohr", 60, 40, 3, 0.0)
    um = [[0.0, 0.0], [19.999, 0.0], [20.001, 35.0]]
    um += [[20 + 5 * math.sin(math.radians(a)), 30 + 5 * math.cos(math.radians(a))] for a in range(3, 90, 3)]
    um += [[25.0, 30.0], [35.0, 30.0]]
    um += [[40 - 5 * math.cos(math.radians(a)), 30 + 5 * math.sin(math.radians(a))] for a in range(3, 90, 3)]
    um += [[39.999, 35.0], [40.001, 0.0], [199.95, 0.0]]
    er = ek.erkennen(qs, um)
    pruef(ek.erkannt_text(er) == "Ausklinkung 20 × 30, Freimachung 2 × Ø10 mittig", f"Ende: {ek.erkannt_text(er)}")
    pruef(er and er["freimachung"]["d"] == 10 and er["ausklinkung"]["tiefe"] == 30, f"Ende Felder {er}")
    print("OK freimachung")


def test_zuschlag_2d():
    """Gemessenes komplexes Ende (Schwenk 45°) eines 2D-Teils: kein Zuschlag Wand × tan(Schwenk)."""
    qs = QS[1][1]
    gk = ek.geo_schluessel(qs)
    um = ek.umriss(qs, dict(typ=ek.V_SPITZE, tiefe=20))
    e = dict(form="komplex", umriss=um, gemessen=200.0, schwenk=45.0)
    t2 = ek.profil_tiefe(ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, e, d3=False)))
    t3 = ek.profil_tiefe(ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, e, d3=True)))
    pruef(abs(t2 - 20) < 0.6, f"2D: Tiefe {t2} (soll ~20)")
    pruef(t3 < t2 - 2.5, f"3D: Tiefe {t3} soll um Wand × tan 45° kleiner sein als {t2}")
    print("OK zuschlag 2D/3D")


def test_step_pruefsatz():
    import kontur_erkennung as ke
    from rohrlaser import rechnen, teile_editor
    with tempfile.TemporaryDirectory() as tmp:
        soll = ke.pruefsatz(tmp)
        teile, zeit = ke.einlesen(sorted(Path(tmp).rglob("*.step")))
    for n, ok, text in ke.vergleich(teile, soll):
        pruef(ok, f"{n}: {text}")
    pruef(len(teile) == len(soll), f"{len(teile)} Teile, soll {len(soll)}")
    for t in teile:
        n = t["artikel"]
        if n.startswith("EK_") and not n.endswith("Schraeg"):
            b = t["b"]
            pruef(b.get("umriss") and b.get("gemessen"), f"{n}: Umriss/Schnittlänge der STEP fehlen (bleiben maßgebend)")
            txt = teile_editor.ende_text(b)
            pruef("erkannt, Umriss wie STEP" in txt, f"{n}: Anzeige {txt!r}")
            # Verschachtelung: 2D-Schnitt, Tiefe wie konstruiert (kein Schwenk-Zuschlag)
            if (b.get("kontur_erkannt") or {}).get("freimachung"):
                continue
            p = t["position"]
            _, kb, _ = rechnen.kontur_enden(p, t["profil"], p.get("a_gerade") == "ja", p.get("b_gerade") == "ja")
            soll_t = ek.tiefe(sk.Querschnitt(t["profil"]), (b.get("kontur_erkannt") or {}).get("kontur"))
            ist_t = ek.profil_tiefe(kb) if kb else None
            pruef(ist_t is not None and abs(ist_t - soll_t) < 1.0,
                  f"{n}: Verschachtelungstiefe {ist_t}, Kontur {soll_t:.2f}")
        if n.startswith("SK_") and "RR60" not in n:
            ks = [k for k in t["konturen"] if k.get("art") == "Sonderkontur"]
            pruef(ks and str(ks[0].get("text") or "").endswith("Umriss wie STEP"),
                  f"{n}: Bemerkung {ks and ks[0].get('text')!r}")
            pruef(ks and "(" in teile_editor.kontur_text(0, ks[0]), f"{n}: Editor zeigt die Form nicht")
    print(f"OK STEP-Prüfsatz ({len(teile)} Teile, Übernahme {zeit['uebernahme']:.1f} s)")


if __name__ == "__main__":
    test_kurven_abstand()
    test_endkontur_rundlauf()
    test_formen()
    test_freimachung()
    test_zuschlag_2d()
    test_step_pruefsatz()
    print("FEHLER:", fehler)
    sys.exit(1 if fehler else 0)
