"""Prüft die Konturklassen klein/mittel/groß in der Schneidzeit: Schnittweg je Klasse mit dem Vorschub der Klasse,
Anteil groß nie negativ, Warnung bei widersprüchlichen Konturwerten, Zeitanteile in der Kalkulation und im
Kalkulation-PDF, Konturliste je Position mit Neu-Einteilung bei anderen Grenzen der Maschine und das Hüllmaß aus der
abgewickelten Kontur (schräges Langloch, Schlitz um ein Rundrohr).

Aufruf: python tests/test_konturklassen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import pdf, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


# --- Rechenregel mit festen Vorschüben (groß 3000, mittel 2000, klein 1000, Gravur 6000, Einstich 0,5 s)
V = (3000, 2000, 1000, 6000, 0.5)
p = dict(schneidweg=697.1, klein_mm=125.7, mittel_mm=91.4, gross_mm=240.0, innen=457.1, gravur=0, einstiche=8)
a = rechnen.zeitanteile(p, V)
assert abs(a["gross"] - 60 * 480.0 / 3000) < EPS and abs(a["mittel"] - 60 * 91.4 / 2000) < EPS
assert abs(a["klein"] - 60 * 125.7 / 1000) < EPS and abs(a["einstiche"] - 4.0) < EPS
assert abs(sum(a.values()) - 23.884) < 1e-3
ok(f"Beispiel aus dem Prüfbericht: {sum(a.values()):.1f} s (groß {a['gross']:.1f}, mittel {a['mittel']:.1f}, "
   f"klein {a['klein']:.1f}, Einstiche {a['einstiche']:.1f})")
assert rechnen.konturen_pruefen(p) is None
ok("stimmige Konturwerte: keine Warnung")

# A: Schneidweg von Hand kleiner als klein + mittel -> Anteil groß 0 statt negativ, Warnung
q = dict(p, schneidweg=100)
assert rechnen.gross_rest(q) == 0 and rechnen.zeitanteile(q, V)["gross"] == 0
assert rechnen.konturen_pruefen(q) == "Konturen klein + mittel länger als Schneidweg"
ok("Schneidweg 100 mm < klein + mittel: Anteil groß 0 s, Warnung")
q = dict(p, innen=200)
assert rechnen.konturen_pruefen(q) == "Konturklassen länger als Innenkonturen + Anfangs-/Endschnitt"
assert rechnen.konturen_pruefen(dict(q, a_schnitt=150, b_schnitt=150)) is None
ok("Konturklassen länger als Innenkonturen + Anfangs-/Endschnitt: Warnung")
assert rechnen.konturen_pruefen(dict(schneidweg=300, einstiche=2)) is None
assert rechnen.konturen_pruefen(dict(p, schneidweg=217.3)) is None      # Rundung bis 0,5 mm erlaubt
ok("ohne Konturklassen bzw. innerhalb der Rundung: keine Warnung")
assert rechnen.zeitanteile(p, (None, None, None, None, None)) is None
ok("ohne Schneiddaten keine Zeitanteile")

# --- im Programm: Status, Kalkulation, Spalten, PDF
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
an = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
db.position_neu(an, dict(pos=10, artikel="K10", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                         stueck=4, einstiche=8, **{n: p[n] for n in ("schneidweg", "klein_mm", "mittel_mm", "gross_mm",
                                                                    "innen")}))
db.position_neu(an, dict(pos=20, artikel="K20", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                         stueck=2, schneidweg=100, einstiche=8, klein_mm=125.7, mittel_mm=91.4))
s = fenster.angebot_oeffnen(an)
assert s.optimieren()
st = [rechnen.status(x, rechnen.position_werte(x, s.kopf, s.k, s.tabellen), s.kopf, s.k) for x in s.positionen]
assert st[0] == "OK" or not st[0].startswith("WARNUNG: Kontur"), st
assert st[1] == "WARNUNG: Konturen klein + mittel länger als Schneidweg", st
ok(f"Status: Pos. 10 {st[0]!r}, Pos. 20 {st[1]!r}")
zeilen, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
z1, z2 = zeilen
assert z2["hinweis"] == "Konturen klein + mittel länger als Schneidweg"
for z in zeilen:
    teile = [z[f"zeit_{n}"] for n in rechnen.ZEITANTEILE]
    assert all(t is not None and t >= 0 for t in teile)
    assert abs(sum(teile) - z["laser_brutto"]) < 1e-6
    assert abs(z["zeit_gross"] - 60 * z["mm_gross"] / z["vorschub_gross"]) < 1e-6
    assert abs(z["zeit_klein"] - 60 * z["mm_klein"] / z["vorschub_klein"]) < 1e-6
    assert abs(z["zeit_mittel"] - 60 * z["mm_mittel"] / z["vorschub_mittel"]) < 1e-6
assert z2["mm_gross"] == 0 and z2["zeit_gross"] == 0
ok(f"Kalkulation: Zeitanteile ergeben die Laserzeit brutto (Pos. 10 {z1['laser_brutto']:.1f} s, "
   f"Vorschub groß/mittel/klein {z1['vorschub_gross']:g}/{z1['vorschub_mittel']:g}/{z1['vorschub_klein']:g})")
from rohrlaser.angebot_spalten import KALK_SPALTEN  # noqa: E402
assert {"zeit_gross", "zeit_mittel", "zeit_klein", "zeit_gravur", "zeit_einstiche"} <= {x[1] for x in KALK_SPALTEN}
ok("Reiter Kalkulation und CSV: Spalten 'davon …' je Konturklasse")
ziel = tmp / "kalkulation.pdf"
pdf.kalkulation_pdf(ziel, s.kopf, zeilen, summen, s.einst)
inhalt = ziel.read_bytes()
assert ziel.stat().st_size > 1000 and b"%PDF" in inhalt[:10]
ok("Kalkulation-PDF mit Tabelle 'Schneidzeit je Teil nach Konturklassen' erzeugt")

# --- B: Konturliste je Position, Neu-Einteilung bei anderen Grenzen
liste = rechnen.konturen_lesen("10x31,4; 8x25,1; 40x91,4; 52x150")
assert liste == [(10.0, 31.4), (8.0, 25.1), (40.0, 91.4), (52.0, 150.0)]
assert rechnen.konturen_lesen(rechnen.konturen_text(liste)) == liste
assert rechnen.konturen_lesen("Ø10; x; 5x") == []
ok(f"Konturliste lesen und schreiben: {rechnen.konturen_text(liste)!r}")
kl = rechnen.konturklassen(liste, (10, 50))
assert kl == dict(klein_n=2, klein_mm=56.5, mittel_n=1, mittel_mm=91.4, gross_n=1, gross_mm=150.0), kl
kl = rechnen.konturklassen(liste, (8, 45))
assert (kl["klein_n"], kl["mittel_n"], kl["gross_n"]) == (1, 2, 1), kl
ok("Einteilung: Ø10 auf der Grenze 10 = klein, mit Grenzen 8/45 mittel")
assert rechnen.kontur_grenzen(None) == ((10.0, 50.0), True)
assert rechnen.kontur_grenzen(dict(kontur_klein=12, kontur_mittel=60)) == ((12.0, 60.0), False)
assert rechnen.kontur_grenzen(dict(kontur_klein=60, kontur_mittel=12))[1] is True
ok("Grenzen der Maschine, ungültige oder fehlende Werte = Vorgabe 10/50 mm")

# Hüllmaß ÷ Wandstärke (Patrick 21.10.2026, B1a/B2a): die strengere Klasse gilt, Faktoren je Maschine (Vorgabe 3/8)
assert rechnen.kontur_faktoren(None) == (3.0, 8.0)
assert rechnen.kontur_faktoren(dict(kontur_klein_wand=2, kontur_mittel_wand=6)) == (2.0, 6.0)
assert rechnen.kontur_faktoren(dict(kontur_klein_wand=6, kontur_mittel_wand=2)) == (3.0, 8.0)
assert rechnen.kontur_regel(None, None) == (10.0, 50.0) and rechnen.kontur_regel(None, 0) == (10.0, 50.0)
r8, r2 = rechnen.kontur_regel(None, 8), rechnen.kontur_regel(None, 2)
assert r8 == (10.0, 50.0, 3.0, 8.0, 8.0)
assert rechnen.kontur_klasse(20, r8) == 0 and rechnen.kontur_klasse(20, r2) == 1     # Ø20: 8 mm klein, 2 mm mittel
assert rechnen.kontur_klasse(24, r8) == 0 and rechnen.kontur_klasse(24.1, r8) == 1    # genau 3 × Wand = klein
assert rechnen.kontur_klasse(60, r8) == 1 and rechnen.kontur_klasse(64.1, r8) == 2    # über 8 × Wand und 50 mm
assert rechnen.kontur_klasse(8, r2) == 0 and rechnen.kontur_klasse(45, r2) == 1       # dünn: mm-Grenzen gelten
kl = rechnen.konturklassen([(20, 62.8), (30, 94.2), (70, 220)], r8)
assert (kl["klein_n"], kl["mittel_n"], kl["gross_n"]) == (1, 1, 1), kl
assert rechnen.grenzen_text(r8) == "10/50; 3×/8× Wand 8" and rechnen.grenzen_lesen("10/50; 3×/8× Wand 8") == r8
assert rechnen.grenzen_text((10, 50, 2.5, 7, 1.5)) == "10/50; 2,5×/7× Wand 1,5"
assert rechnen.grenzen_lesen("10/50; Unsinn") is None and rechnen.grenzen_lesen("10/50") == (10.0, 50.0)
txt8 = rechnen.konturen_text([(20, 62.8)], [("A", 40, 160)])
assert rechnen.ende_vorschub(dict(konturen=txt8, a_gerade="ja"), (3000, 2000, 1000), r8) == 2000   # 40 ≤ 64 mittel
assert rechnen.ende_vorschub(dict(konturen=txt8, a_gerade="ja", kontur_grenzen="10/50; 3×/8× Wand 15"),
                             (3000, 2000, 1000), r8) == 1000                                       # 40 ≤ 45 klein
ok("Hüllmaß ÷ Wandstärke: Ø20 bei 8 mm Wand klein, bei 2 mm mittel; strengere Klasse, Text der Regel")
# Kontur kleiner als 0,7 × Wandstärke: Warnung, gerechnet wird weiter (B3a; Patrick: ab 0,7 × Wand meist kein Problem)
q = dict(schneidweg=400, konturen="A:40x160; 5,5x17,3", klein_n=1, klein_mm=17.3)
assert rechnen.konturen_pruefen(q, 8) == "Kontur kleiner als 0,7 × Wandstärke, Schneidbarkeit prüfen (ggf. nur " \
                                        "gravieren und aufbohren)"
assert rechnen.konturen_pruefen(q, 7.8) is None      # 5,5 ≥ 0,7 × 7,8 = 5,46
assert rechnen.konturen_pruefen(q, 6) is None and rechnen.konturen_pruefen(q) is None
ok("Kontur kleiner als 0,7 × Wandstärke: Warnung 'Schneidbarkeit prüfen'")

# Anfangs- und Endschnitt in der Konturliste
txt = rechnen.konturen_text([(10, 31.4)], [("A", 40, 149.7), ("E", 84.85, 249.7)])
assert txt == "A:40x149,7; E:84,85x249,7; 10x31,4", txt
assert rechnen.konturen_lesen(txt) == [(40.0, 149.7), (84.85, 249.7), (10.0, 31.4)]
assert rechnen.konturen_lesen(txt, True)[:2] == [("A", 40.0, 149.7), ("E", 84.85, 249.7)]
kl = rechnen.konturklassen(rechnen.konturen_lesen(txt), (10, 50))
assert (kl["klein_n"], kl["mittel_n"], kl["mittel_mm"], kl["gross_n"], kl["gross_mm"]) == (1, 1, 149.7, 1, 249.7)
ok("Konturliste mit Anfangsschnitt (40 mm = mittel) und Gehrung als Endschnitt (84,85 mm = groß)")
VS = (3000, 2000, 1000)
assert rechnen.ende_vorschub(dict(konturen=txt, a_gerade="ja", kontur_grenzen="10/50"), VS, (10, 50)) == 2000
assert rechnen.ende_vorschub(dict(konturen=txt, a_gerade="nein", b_gerade="ja"), VS, (10, 50)) == 3000
assert rechnen.ende_vorschub(dict(konturen="10x31,4"), VS, (10, 50)) == 3000
assert rechnen.ende_vorschub(dict(konturen=txt, a_gerade="ja", kontur_grenzen="10/30"), VS, (10, 50)) == 3000
ok("Einsparung gemeinsamer Schnitte mit dem Vorschub der Klasse des geraden Endes (ohne Enden: Vorschub groß)")
from rohrlaser import step  # noqa: E402
assert step.konturen_enden(dict(ende_a="149.7", ende_a_huelle="40.0", ende_b="149.7", ende_b_huelle="")) == \
    [("A", 40.0, 149.7)]
ok("Messung einer älteren STEP-Import.exe ohne Hüllmaß der Enden: Enden bleiben ohne Klasse")

m1 = next(iter(s.k.maschinen))
db.position_neu(an, dict(pos=30, artikel="K30", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=700,
                         stueck=2, schneidweg=600, innen=298.0, einstiche=6, konturen=rechnen.konturen_text(liste),
                         kontur_grenzen="10/50", **rechnen.konturklassen(liste, (10, 50))))
db.position_neu(an, dict(pos=40, artikel="K40", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=700,
                         stueck=2, schneidweg=300, einstiche=2, klein_n=1, klein_mm=20.0))     # ohne Konturliste
zeile = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == m1)
db.aendern("maschinen", zeile["id"], "kontur_klein", 8.0)
db.aendern("maschinen", zeile["id"], "kontur_mittel", 45.0)
s.neu_laden()
p30 = next(x for x in s.positionen if x["artikel"] == "K30")
p40 = next(x for x in s.positionen if x["artikel"] == "K40")
assert (p30["klein_n"], p30["mittel_n"], p30["gross_n"], p30["kontur_grenzen"]) == (1, 2, 1, "8/45; 3×/8× Wand 3"), p30
assert p30["klein_mm"] == 25.1 and p30["mittel_mm"] == 122.8
assert (p40["klein_n"], p40["klein_mm"]) == (1, 20.0)
ok("Grenzen der Maschine auf 8/45 mm geändert: Pos. 30 neu eingeteilt, Pos. 40 ohne Konturliste unverändert")
s.neu_laden()
assert next(x for x in s.positionen if x["artikel"] == "K30")["kontur_grenzen"] == "8/45; 3×/8× Wand 3"
# Konturliste von Hand geändert -> beim Neuladen neu eingeteilt
r = s.positionen.index(next(x for x in s.positionen if x["artikel"] == "K30"))
spalte = next(i for i, (art, f) in enumerate(s.pos_modell.spalten) if art == "feld" and f.name == "konturen")
assert s.pos_modell.setData(s.pos_modell.index(r, spalte), "60x200")
p30 = next(x for x in s.positionen if x["artikel"] == "K30")
assert (p30["klein_n"], p30["mittel_n"], p30["gross_n"], p30["gross_mm"]) == (0, 0, 1, 200.0), p30
ok("Konturliste von Hand geändert: Klassen neu eingeteilt")

# --- C: Hüllmaß aus der abgewickelten Kontur
try:
    import math
    sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
    sys.path.insert(0, str(HIER))
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf  # noqa: E402
    from erzeuge_testteile import cut, kastenrohr, rundrohr  # noqa: E402
    from step_geometrie import analysiere  # noqa: E402
    OCC = True
except ImportError:
    OCC = False
if OCC:
    def schlitz_schraeg(laenge, breite, grad, z):
        """Rechteckschlitz in der oberen Wand (+Y) eines QR 40x40x3, um die Wandnormale gedreht."""
        b = BRepPrimAPI_MakeBox(gp_Pnt(-laenge / 2, 10, z - breite / 2), laenge, 20, breite).Shape()
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, z), gp_Dir(0, 1, 0)), math.radians(grad))
        return BRepBuilderAPI_Transform(b, tr, True).Shape()

    rohr = kastenrohr(40, 40, 3, 600, 0)
    rohr = cut(rohr, schlitz_schraeg(30, 8, 45, 200))
    rohr = cut(rohr, schlitz_schraeg(46, 6, 60, 400))
    t = analysiere(rohr)
    g = sorted(round(x, 1) for x, _ in t.innen_liste)
    assert abs(g[0] - 30) < 0.2 and abs(g[1] - 46) < 0.2, g
    kl = rechnen.konturklassen(t.innen_liste, (10, 45))
    assert (kl["mittel_n"], kl["gross_n"]) == (1, 1), kl
    ok(f"schräge Schlitze 30x8 (45°) und 46x6 (60°): Hüllmaß {g[0]:g} und {g[1]:g} mm (achsparallel wären es "
       f"{(30 + 8) / math.sqrt(2):.1f} und {46 * math.sin(math.radians(60)) + 3:.1f}), mit Grenze 45 mm: 46 = groß")
    # Schlitz 8 mm breit über 90° des Umfangs eines Rundrohrs Ø60x3: Bogen außen 47,1 mm, Sehne 42,4 mm
    rr = rundrohr(60, 3, 600)
    sektor = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 296), gp_Dir(0, 0, 1)), 40, 8, math.pi / 2).Shape()
    t = analysiere(cut(rr, sektor))
    g = [round(x, 1) for x, _ in t.innen_liste]
    assert len(g) == 1 and abs(g[0] - 30 * math.pi / 2) < 0.5, g
    ok(f"Schlitz über 90° um ein Rundrohr Ø60: Hüllmaß {g[0]:g} mm = Bogenlänge (Sehne 42,4 mm)")
    # Bohrung schräg zur Wand: Hüllmaß = Ø
    t = analysiere(cut(rundrohr(42.4, 2, 500), BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, -40, 230), gp_Dir(0, 1, 0.3)), 4, 80).Shape()))
    g = [round(x, 2) for x, _ in t.innen_liste]
    assert g and all(abs(x - 8) < 0.01 for x in g), g
    ok(f"schräge Bohrung Ø8: Hüllmaß {g[0]:g} mm (= Ø)")
    # Hüllmaß der Enden: gerade QR 40x40 = 40, Gehrung 45° über die 60er Seite eines RE 60x40 = 84,85
    from step_geometrie import analysiere_datei  # noqa: E402
    t = analysiere_datei(HIER / "step" / "T04_RE60x40x3_Gehrung.step")[0]
    assert abs(t.ende_a_huelle - 60) < 0.05 and abs(t.ende_b_huelle - 60 * math.sqrt(2)) < 0.05, t
    t = analysiere_datei(HIER / "step" / "T03_QR40x3_L2150_Bohrung.step")[0]
    assert abs(t.ende_a_huelle - 40) < 0.05 and abs(t.ende_b_huelle - 40) < 0.05
    t = analysiere_datei(HIER / "step" / "T01_RR42-4x2_L1250.step")[0]
    assert abs(t.ende_a_huelle - 42.4) < 0.05
    ok("Hüllmaß der Enden: RE 60x40 gerade 60 / Gehrung 45° 84,85, QR 40 = 40, RR 42,4 = 42,4")
else:
    print("HINWEIS OpenCascade fehlt: Prüfung Hüllmaß übersprungen")
print("Alle Prüfungen bestanden.")
