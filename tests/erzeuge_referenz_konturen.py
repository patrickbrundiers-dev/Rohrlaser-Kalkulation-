"""Referenzteile mit Sollmaßen aus der Konstruktion (Master-Auftrag Patrick 25.11.2026 „Abwicklungskern für den STEP-/
CAD-Import grundlegend erweitern“, Abschnitt Testsammlung; Plan https://claude.ai/artifact/DpkYezVhUe2Kioe7ZL7CC7).

Anders als die Prüfbasis (tests/daten/abwicklungskern_soll.json vergleicht mit dem eigenen früheren Ergebnis) kommen
die Sollwerte hier aus der Konstruktion selbst: das Skript baut jedes Teil aus Grundkörpern und rechnet die Schnittlänge
jeder Kontur unabhängig von der STEP-Messung (Formel oder numerisches Integral über die Schnittkurve auf der
Außenhaut). Die Sollwerte stehen mit Formel in tests/daten/referenz_konturen_soll.json.

R01 gerader Schnitt · R02 Gehrung · R03 schräger Schnitt in zwei Richtungen · R04 rundes Seitenloch · R05 Langloch ·
R06 mehrere Durchbrüche · R07 Sattelschnitt · R08 komplexe Rohrverbindung (schräg, außermittig) · R09 mehrere Konturen
am Ende · R10 Baugruppe aus R01, R02, R07 und einer Platte.

Rollen (konturrolle.py): Anfangsschnitt (Ende A), Endeschnitt (Ende B), Innenkontur, Durchbruch, Ausschnitt,
Anschlusskontur (Sattel gegen ein Gegenrohr), Freiformkontur, nicht eindeutig.

Aufruf: python tests/erzeuge_referenz_konturen.py [Zielordner] – schreibt die STEP-Dateien (Standard
tests/step_referenz_konturen) und mit --soll die Sollwerte nach tests/daten/referenz_konturen_soll.json.
"""
import json
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import erzeuge_testteile as et  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

ZIEL = HIER / "step_referenz_konturen"
SOLL = HIER / "daten" / "referenz_konturen_soll.json"
TOL = dict(laenge_mm=0.1, laenge_rel=0.002, lage_mm=0.05, winkel=0.1)
N = 20000                                   # Stützstellen der numerischen Kurvenlängen


def _kurve(f, n=N):
    """Länge der geschlossenen Raumkurve f(t), t in [0, 2π)."""
    pts = [f(2 * math.pi * i / n) for i in range(n)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


def _ellipse(a, b):
    return _kurve(lambda t: (a * math.cos(t), b * math.sin(t), 0.0))


def _kasten_umfang(b, h, r):
    return 2 * (b + h) - 8 * r + 2 * math.pi * r


def _box(x0, y0, z0, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def _zyl(p, d, durchm, laenge):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*d)), durchm / 2, laenge).Shape()


def _sattel(r, R, z0, achse=(1.0, 0.0, 0.0), versatz=(0.0, 0.0)):
    """Eintrittskurve eines Rohrs (Außenradius r, Achse Z) in einen Zylinder (Radius R, Achse 'achse' durch
    (versatz[0], versatz[1], z0)): kleinere Lösung w = z - z0 der Gleichung |v|² - (v·d)² = R²."""
    dx, dy, dz = achse
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    dx, dy, dz = dx / n, dy / n, dz / n
    ox, oy = versatz

    def p(t):
        x, y = r * math.cos(t), r * math.sin(t)
        vx, vy = x - ox, y - oy
        # |v|² - (v·d)² mit v = (vx, vy, w)
        a = 1 - dz * dz
        b = -2 * (vx * dx + vy * dy) * dz
        c = vx * vx + vy * vy - (vx * dx + vy * dy) ** 2 - R * R
        w = (-b - math.sqrt(b * b - 4 * a * c)) / (2 * a)
        return (x, y, z0 + w)
    return p


def _loch_rund(r_rohr, d, z0):
    """Schnittkurve einer radialen Bohrung Ø d (Achse +Y) mit der Außenhaut eines Rundrohrs (Radius r_rohr)."""
    return lambda t: (d / 2 * math.cos(t), math.sqrt(r_rohr ** 2 - (d / 2 * math.cos(t)) ** 2), z0 + d / 2 * math.sin(t))


def _loch_rund_2d(r_rohr, wand, d, z0):
    """2D-Schnitt einer Bohrung Ø d im Rundrohr (Strahl zur Rohrmitte, STEP-JSON 1.11): innen Ø d maßhaltig, außen die
    radiale Projektion der Innenkurve auf die Außenhaut."""
    ri = r_rohr - wand

    def p(t):
        x = d / 2 * math.cos(t)
        y = math.sqrt(ri * ri - x * x)
        return (x * r_rohr / ri, y * r_rohr / ri, z0 + d / 2 * math.sin(t))
    return p


def _ebene_kasten(b, h, z0, um_x, um_y):
    """Umfang der Schnittfigur einer Ebene (wie erzeuge_testteile.schraeg_ende) mit einem scharfkantigen
    Kastenprofil b × h (außen)."""
    ax, ay = math.radians(um_x), math.radians(um_y)
    # Normale (0,0,1) erst um X, dann um Y gedreht
    n1 = (0.0, -math.sin(ax), math.cos(ax))
    n = (n1[0] * math.cos(ay) + n1[2] * math.sin(ay), n1[1], -n1[0] * math.sin(ay) + n1[2] * math.cos(ay))
    ecken = [(b / 2, h / 2), (-b / 2, h / 2), (-b / 2, -h / 2), (b / 2, -h / 2)]
    p = [(x, y, z0 - (n[0] * x + n[1] * y) / n[2]) for x, y in ecken]
    return sum(math.dist(a, c) for a, c in zip(p, p[1:] + p[:1])), n


def teile():
    """[(name, shape, soll)] – soll: dict(profil, konturen=[dict(rolle, schnittlaenge, formel, ...)])."""
    out = []

    # R01 gerader Schnitt: RE 60×40×3, Außenradius 6, L 500
    s = et.kastenrohr(60, 40, 3, 500, 6)
    u = _kasten_umfang(60, 40, 6)
    f = "2·(60+40) − 8·6 + 2π·6"
    out.append(("R01_RE60x40x3_gerade", s, dict(profil="Rechteckrohr", laenge=500, konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=u, z=0, formel=f),
        dict(rolle="Endeschnitt", schnittlaenge=u, z=500, formel=f)])))

    # R02 Gehrung: RR 48,3×3, L 400, Ende B 45° (Ebene um Y geneigt)
    s = et.gehrung(et.rundrohr(48.3, 3, 450), 400, 45)
    r = 48.3 / 2
    out.append(("R02_RR48-3x3_Gehrung45", s, dict(profil="Rundrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=math.pi * 48.3, z=0, formel="π·48,3"),
        dict(rolle="Endeschnitt", schnittlaenge=_ellipse(r / math.cos(math.radians(45)), r), gehrung=45,
             formel="Ellipsenumfang a = r/cos 45°, b = r, r = 24,15")])))

    # R03 schräger Schnitt in zwei Richtungen: QR 50×3 scharfkantig, Ende B um X 20°, um Y 10°
    s = et.schraeg_ende(et.kastenrohr(50, 50, 3, 500, 0), 400, 20, 10)
    u, n = _ebene_kasten(50, 50, 400, 20, 10)
    gesamt = math.degrees(math.acos(n[2]))
    out.append(("R03_QR50x3_schraeg_20_10", s, dict(profil="Quadratrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=200.0, z=0, formel="4·50"),
        dict(rolle="Endeschnitt", schnittlaenge=u, gehrung=gesamt,
             formel="Umfang der Schnittebene (Normale um X 20°, um Y 10°) mit dem Quadrat 50 × 50")])))

    # R04 rundes Seitenloch: RR 60,3×3, L 400, Bohrung Ø 20 radial bei z = 200 (eine Wand)
    s = et.cut(et.rundrohr(60.3, 3, 400), _zyl((0, 0, 200), (0, 1, 0), 20, 50))
    out.append(("R04_RR60-3x3_Seitenloch20", s, dict(profil="Rundrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=math.pi * 60.3, z=0, formel="π·60,3"),
        dict(rolle="Endeschnitt", schnittlaenge=math.pi * 60.3, z=400, formel="π·60,3"),
        dict(rolle="Innenkontur", art="Bohrung", durchmesser=20, z=200,
             schnittlaenge=_kurve(_loch_rund_2d(60.3 / 2, 3, 20, 200)),
             schnittlaenge_3d=_kurve(_loch_rund(60.3 / 2, 20, 200)),
             formel="2D-Schnitt (Strahl zur Rohrmitte): innen Ø 20 maßhaltig, außen radiale Projektion auf Ø 60,3 "
                    "(numerisch); schnittlaenge_3d = Schnittkurve Zylinder Ø 20 mit dem Außenmantel")])))

    # R05 Langloch: RE 80×40×3 scharfkantig, L 400, Langloch 40 × 10 in der breiten Seite (oben, +Y), Mitte z = 200
    loch = BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(_zyl((0, 0, 185), (0, 1, 0), 10, 50), _zyl((0, 0, 215), (0, 1, 0), 10, 50))
                            .Shape(), _box(-5, 0, 185, 10, 50, 30)).Shape()
    s = et.cut(et.kastenrohr(80, 40, 3, 400, 0), loch)
    out.append(("R05_RE80x40x3_Langloch40x10", s, dict(profil="Rechteckrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=240.0, z=0, formel="2·(80+40)"),
        dict(rolle="Endeschnitt", schnittlaenge=240.0, z=400, formel="2·(80+40)"),
        dict(rolle="Innenkontur", art="Langloch", laenge=40, breite=10, z=200, schnittlaenge=2 * 30 + math.pi * 10,
             formel="2·30 + π·10")])))

    # R06 mehrere Durchbrüche: QR 60×3 scharfkantig, L 500, Bohrung Ø 12 quer durch beide Wände bei z = 100,
    # zwei Rechtecke 30 × 15 in der Oberseite bei z = 250 und z = 380 (15 quer, 30 längs)
    s = et.bohrung_quer(et.kastenrohr(60, 60, 3, 500, 0), 12, 100)
    for zm in (250, 380):
        s = et.cut(s, _box(-7.5, 0, zm - 15, 15, 50, 30))
    kreis = math.pi * 12
    out.append(("R06_QR60x3_Durchbrueche", s, dict(profil="Quadratrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=240.0, z=0, formel="4·60"),
        dict(rolle="Endeschnitt", schnittlaenge=240.0, z=500, formel="4·60"),
        dict(rolle="Durchbruch", art="Bohrung", durchmesser=12, z=100, schnittlaenge=kreis, formel="π·12 je Wand"),
        dict(rolle="Durchbruch", art="Bohrung", durchmesser=12, z=100, schnittlaenge=kreis, formel="π·12 je Wand"),
        dict(rolle="Ausschnitt", art="Rechteckausschnitt", z=250, schnittlaenge=90.0, formel="2·(30+15)"),
        dict(rolle="Ausschnitt", art="Rechteckausschnitt", z=380, schnittlaenge=90.0, formel="2·(30+15)")])))

    # R07 Sattelschnitt: RR 42,4×2, Ende B gegen Gegenrohr Ø 60,3 senkrecht (Achse X durch z = 350)
    s = et.cut(et.rundrohr(42.4, 2, 350), _zyl((-100, 0, 350), (1, 0, 0), 60.3, 200))
    out.append(("R07_RR42-4x2_Sattel60-3", s, dict(profil="Rundrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=math.pi * 42.4, z=0, formel="π·42,4"),
        dict(rolle="Anschlusskontur", gegenrohr=60.3, stufe=2, schnittlaenge=_kurve(_sattel(21.2, 30.15, 350)),
             formel="Eintrittskurve Ø 42,4 in Zylinder Ø 60,3, Achsen senkrecht (numerisch)")])))

    # R08 komplexe Rohrverbindung: RR 33,7×2,6 gegen RR 60,3 unter 60° (Achse in XZ um 30° aus X), außermittig 8 mm
    d = (math.cos(math.radians(30)), 0.0, math.sin(math.radians(30)))
    p0 = (-150 * d[0], 8.0 - 150 * d[1], 300 - 150 * d[2])
    s = et.cut(et.rundrohr(33.7, 2.6, 300), _zyl(p0, d, 60.3, 300))
    out.append(("R08_RR33-7_60Grad_aussermittig", s, dict(profil="Rundrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=math.pi * 33.7, z=0, formel="π·33,7"),
        dict(rolle="Anschlusskontur", gegenrohr=60.3, stufe=2,
             schnittlaenge=_kurve(_sattel(33.7 / 2, 30.15, 300, d, (0.0, 8.0))),
             formel="Eintrittskurve Ø 33,7 in Zylinder Ø 60,3, Achsen 60°, Versatz 8 mm (numerisch)")])))

    # R09 mehrere Konturen am Ende: RE 60×40×3 scharfkantig, L 400, Ende B mit Ausklinkung 20 × 20 in der Oberseite
    # (durch die Wand), Bohrung Ø 8 in der Seite 35 mm vor dem Ende
    s = et.kastenrohr(60, 40, 3, 400, 0)
    s = et.cut(s, _box(-10, 10, 380, 20, 20, 30))
    s = et.cut(s, _zyl((0, 0, 365), (1, 0, 0), 8, 50))
    out.append(("R09_RE60x40x3_Ende_mehrfach", s, dict(profil="Rechteckrohr", konturen=[
        dict(rolle="Anfangsschnitt", schnittlaenge=200.0, z=0, formel="2·(60+40)"),
        dict(rolle="Endeschnitt", schnittlaenge=200 - 20 + 3 * 20, stufe=3,
             formel="200 − 20 + 3·20 (Ausklinkung im Endschnitt)"),
        dict(rolle="Innenkontur", art="Bohrung", durchmesser=8, z=365, schnittlaenge=math.pi * 8, formel="π·8")])))

    # R10 Baugruppe: R01, R02, R07 nebeneinander und eine Platte 200 × 100 × 5
    r01, r02, r07 = out[0], out[1], out[6]
    platte = _box(400, 0, 0, 200, 100, 5)
    s = et.baugruppe(r01[1], et.verschiebe(r02[1], 150, 0, 0), et.verschiebe(r07[1], 250, 0, 0), platte)
    out.append(("R10_Baugruppe", s, dict(baugruppe=[r01[0], r02[0], r07[0]], platte=dict(x=200, y=100, dicke=5))))
    return out


def soll_daten(liste):
    teile_soll = {}
    for name, _, soll in liste:
        s = dict(soll)
        if "konturen" in s:
            s["konturen"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in k.items()} for k in s["konturen"]]
        teile_soll[name] = s
    return dict(stand="2026-11-25", toleranz=TOL, teile=teile_soll)


def main(args):
    ziel = Path(args[0]) if args and not args[0].startswith("--") else ZIEL
    liste = teile()
    for name, shape, _ in liste:
        et.schreibe(shape, name, ziel)
    if "--soll" in args:
        SOLL.write_text(json.dumps(soll_daten(liste), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(liste)} Referenzteile in {ziel}")


if __name__ == "__main__":
    main(sys.argv[1:])
