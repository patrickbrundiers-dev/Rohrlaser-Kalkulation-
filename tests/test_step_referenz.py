"""Referenztests der STEP-Messung mit maschinenlesbarem Testbericht.

Jeder Fall vergleicht Messwerte mit Sollwerten aus den Konstruktionsmaßen in tests/erzeuge_testteile.py (unabhängig
von der Messung erzeugt). Je Merkmal stehen Soll, Ist, Abweichung, Toleranz und ok im Bericht.

Katalog: RE 60x40x2, QR 40x40x2, RR 42,4x2, Rohr mit bekannten Bohrungen, 45°-Gehrung, gedrehte/verschobene Modelle,
Baugruppe, ungültige Datei, Kombination aus Bohrungen + Ausschnitten + Schrägschnitt, dazu STEP-Varianten
(AP203/AP214/AP242), Einheiten (Zoll, Meter), CAD-Toleranzen, Fasen statt Radien und Freiformflächen.

Aufruf: python tests/test_step_referenz.py [--bericht testbericht.json] [--markdown zusammenfassung.md]
"""
import json
import math
import platform
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei  # noqa: E402
sys.path.insert(0, str(HIER.parent / "programm"))
import step_ergebnis  # noqa: E402

REF = HIER / "step_referenz"
TOL_MASS = 0.01      # mm, Maße an exakt modellierten Teilen
TOL_WINKEL = 0.1     # Grad
TOL_LAGE = 0.05      # mm, Lage von Konturen entlang der Achse

# Bekannte Grenzen der Erkennung (stehen auch in der Bedienungsanleitung)
GRENZEN = [
    "Gebogene Rohre und Rohre mit veränderlichem Querschnitt werden nicht gemessen (Prüfstatus 'nicht messbar' "
    "oder 'prüfen').",
    "Gewinde werden nur als Kernloch erkannt; ein Gewindevorschlag kommt aus dem Kernloch-Ø und muss geprüft werden.",
    "Offene Profile (U, L, C, Flachstahl): Konturen mit Lage entlang der Achse (z), aber ohne Lage um das Profil "
    "(Steg/Flansch). Schnittlänge = halbe Länge der Konturkanten (Laser schneidet jede Wand einmal). Vierkant- und "
    "Rundstahl sowie nicht erkannte offene Profile (z. B. Z-Profil, 'offenes Sonderprofil') werden nur gemeldet, "
    "nicht kalkuliert. I-/H-Träger und T-Profile seit 20.10.2026 erkannt; Normname nur bei passenden Maßen.",
    "Nicht konvexe Hohlprofile (z. B. Rohre mit Sicke) werden über ihr umschließendes Rechteck gemessen; sie "
    "erscheinen als Rechteck-/Quadratrohr mit Prüfstatus 'prüfen' (Wandstärke uneinheitlich), nicht als Sonderprofil.",
    "Schräge Bohrungen werden über die Zylinderfläche erkannt; nicht zylindrische schräge Durchbrüche erscheinen als "
    "Ausschnitt mit Umriss.",
    "Flächenmodelle werden nur gemessen, wenn sie sich zu einem geschlossenen Körper vernähen lassen; lose Flächen "
    "werden als 'Flächenmodell offen' gemeldet.",
    "Bleche: Dicke = Abstand der beiden Hauptflächen, Länge × Breite = kleinstes umschreibendes Rechteck der "
    "Außenkontur. Flach und stabförmig (Breite bis 150 mm, Länge ab 3 × Breite, gerade Längsseiten) gilt als "
    "Flachstahl. Gekantete Bleche nur mit Biegeradien; ein Kantteil mit gleichbleibendem Querschnitt bleibt "
    "L-/U-/C-Profil. Abwicklung gekanteter Bleche ohne Biegefaktor (immer 'prüfen').",
    "Prüfstatus 'plausibel' ist keine Fertigungsfreigabe.",
]
NICHT_AUSGEFUEHRT = [
    {"test": "STEP-Import.exe unter Windows", "grund": "läuft nur in der CI (GitHub Actions, Job 'windows'), "
     "dort Vergleich der exe-Ausgabe mit der Python-Messung"},
]

faelle = []


class Fall:
    def __init__(self, nr, name, datei):
        self.nr, self.name, self.datei = nr, name, datei
        self.merkmale = []
        self.fehler = None

    def wert(self, merkmal, ist, soll, tol, einheit="mm"):
        ok = ist is not None and abs(ist - soll) <= tol
        self.merkmale.append(dict(merkmal=merkmal, soll=soll, ist=None if ist is None else round(ist, 4),
                                  abweichung=None if ist is None else round(ist - soll, 4), toleranz=tol,
                                  einheit=einheit, ok=ok))

    def gleich(self, merkmal, ist, soll):
        self.merkmale.append(dict(merkmal=merkmal, soll=soll, ist=ist, abweichung=None, toleranz=None, einheit=None,
                                  ok=ist == soll))

    def winkel(self, merkmal, ist, soll, tol=TOL_WINKEL):
        d = None if ist is None else (ist - soll + 180) % 360 - 180
        self.wert(merkmal, None if d is None else soll + d, soll, tol, "°")

    @property
    def ok(self):
        return self.fehler is None and all(m["ok"] for m in self.merkmale)


def fall(nr, name, datei):
    def deko(fn):
        f = Fall(nr, name, str(datei.relative_to(HIER)))
        t0 = time.time()
        try:
            fn(f, datei)
        except Exception as e:      # Absturz der Messung zählt als Fehler des Falls
            f.fehler = f"{type(e).__name__}: {e}"
        f.dauer = round(time.time() - t0, 2)
        faelle.append(f)
        schlecht = [m for m in f.merkmale if not m["ok"]]
        print(f"{'OK    ' if f.ok else 'FEHLER'} {nr} {name}"
              + (f": {f.fehler}" if f.fehler else "")
              + "".join(f"\n         {m['merkmal']}: ist {m['ist']}, soll {m['soll']}" for m in schlecht))
        return fn
    return deko


def grundmasse(f, t, form, a, b, w, l):
    f.gleich("Profilform", t.profilform, form)
    f.wert("Außenmaß A", t.abm_a, a, TOL_MASS)
    f.wert("Außenmaß B", t.abm_b, b, TOL_MASS)
    f.wert("Wandstärke", t.wandstaerke, w, TOL_MASS)
    f.wert("Länge", t.laenge, l, TOL_MASS)
    f.gleich("Prüfstatus", t.pruefstatus, "plausibel")


def kastenflaeche(a, b, t, r):
    """Querschnittsfläche Kastenrohr mit Außenradius r und Innenradius r-t (0 bei r <= t)."""
    ri = max(r - t, 0)
    return (a * b - (4 - math.pi) * r * r) - ((a - 2 * t) * (b - 2 * t) - (4 - math.pi) * ri * ri)


def gerade_enden(f, t, umfang):
    for k in t.konturen_liste[:2]:
        f.gleich(f"{k['art']} Form", k["form"], "gerade")
        f.wert(f"{k['art']} Schnittlänge", k["schnittlaenge"], umfang, 0.05)


@fall("REF01", "Rechteckrohr 60x40x2, Radius 4, L 1000", REF / "REF01_RE60x40x2_L1000.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Rechteckrohr", 60, 40, 2, 1000)
    f.wert("Querschnittsfläche", t.flaeche, kastenflaeche(60, 40, 2, 4), 0.05, "mm²")
    f.wert("Innenmaß A", t.innen_a, 56, TOL_MASS)
    f.wert("Innenmaß B", t.innen_b, 36, TOL_MASS)
    f.gleich("Wandmessungen alle 2,00", all(abs(m[3] - 2) <= TOL_MASS for m in t.wand_messungen), True)
    f.gleich("Anzahl Wandmessungen >= 12", len(t.wand_messungen) >= 12, True)
    gerade_enden(f, t, 2 * (52 + 32) + 2 * math.pi * 4)


@fall("REF02", "Quadratrohr 40x40x2, Radius 3, L 1000", REF / "REF02_QR40x40x2_L1000.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Quadratrohr", 40, 0, 2, 1000)
    f.wert("Querschnittsfläche", t.flaeche, kastenflaeche(40, 40, 2, 3), 0.05, "mm²")
    gerade_enden(f, t, 4 * 34 + 2 * math.pi * 3)


@fall("REF03", "Rundrohr 42,4x2, L 1000", REF / "REF03_RR42-4x2_L1000.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Rundrohr", 42.4, 0, 2, 1000)
    f.wert("Querschnittsfläche", t.flaeche, math.pi / 4 * (42.4 ** 2 - 38.4 ** 2), 0.05, "mm²")
    gerade_enden(f, t, math.pi * 42.4)


for nr, schema in (("REF04", "AP203"), ("REF05", "AP214IS"), ("REF06", "AP242DIS")):
    @fall(nr, f"RE 60x40x2 als {schema}, schräg im Raum gedreht und verschoben",
          REF / f"{nr}_RE60x40x2_{schema}.step")
    def _(f, p):
        (t,) = analysiere_datei(p)
        grundmasse(f, t, "Rechteckrohr", 60, 40, 2, 1000)
        f.wert("Querschnittsfläche", t.flaeche, kastenflaeche(60, 40, 2, 4), 0.05, "mm²")


@fall("REF07", "CAD-Toleranzen: 60,02 x 39,99, Wand 2,01 (Maße wie modelliert, kein Runden)",
      REF / "REF07_RE60x40x2_Toleranz.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Rechteckrohr", 60.02, 39.99, 2.01, 1000)
    f.gleich("Profilvorschlag", t.profil_id_vorschlag, "RE 60x40x2")


@fall("REF08", "Quadratrohr 40x2 mit Fasen statt Radien", REF / "REF08_QR40x2_Fasen_L800.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Quadratrohr", 40, 0, 2, 800)


@fall("REF09", "Rechteckrohr 60x40x2 mit 45°-Gehrung", REF / "REF09_RE60x40x2_Gehrung45.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Rechteckrohr", 60, 40, 2, 1030)
    a, b = t.konturen_liste[:2]
    f.gleich("Ende A Form", a["form"], "gerade")
    f.wert("Ende A Schnittlänge", a["schnittlaenge"], 200, 0.05)
    f.gleich("Ende B Form", b["form"], "Gehrung")
    f.winkel("Ende B Gehrungswinkel", b["gehrung"], 45)
    f.winkel("Ende B Richtung (am längsten rechts, 90°)", b["richtung"], 90)
    f.winkel("Ende B um Y", b["um_y"], 45)
    f.winkel("Ende B um X", b["um_x"], 0)
    f.wert("Ende B Schnittlänge", b["schnittlaenge"], 2 * (60 * math.sqrt(2) + 40), 0.05)


@fall("REF10", "Baugruppe aus drei Rohren (verschoben, gedreht)", REF / "REF10_Baugruppe_3Rohre.step")
def _(f, p):
    teile = analysiere_datei(p)
    f.gleich("Anzahl Körper", len(teile), 3)
    soll = [("Rechteckrohr", 60, 40, 1000), ("Rundrohr", 42.4, 0, 600), ("Quadratrohr", 40, 0, 500)]
    for t, (form, a, b, l) in zip(teile, soll):
        f.gleich(f"Körper {t.koerper} Profilform", t.profilform, form)
        f.wert(f"Körper {t.koerper} Außenmaß A", t.abm_a, a, TOL_MASS)
        f.wert(f"Körper {t.koerper} Außenmaß B", t.abm_b, b, TOL_MASS)
        f.wert(f"Körper {t.koerper} Wandstärke", t.wandstaerke, 2, TOL_MASS)
        f.wert(f"Körper {t.koerper} Länge", t.laenge, l, TOL_MASS)


@fall("REF11", "Grenzfall gebogenes Rohr: keine Maße, Status 'nicht messbar'", REF / "REF11_RR42-4x2_Bogen90.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Prüfstatus", t.pruefstatus, "nicht messbar")
    f.gleich("keine Länge erfunden", t.laenge, 0)
    f.gleich("Hinweis 'Erkennung unsicher'", any("Erkennung unsicher" in h for h in t.hinweise), True)


@fall("REF12", "Grenzfall Rohr mit Sicke (nicht konvex): nicht 'plausibel'", REF / "REF12_QR40x2_Sicke.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Prüfstatus", t.pruefstatus, "prüfen")
    f.gleich("Hinweis Wandstärke uneinheitlich", any("nicht einheitlich" in h for h in t.hinweise), True)


@fall("REF13", "T-Profil 40 hoch, Flansch 50 x 5, Steg 5 (seit 20.10.2026 erkannt)", REF / "REF13_T50x40x5_L600.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "T-Profil", 40, 50, 5, 600)
    f.wert("Flanschdicke", t.flanschdicke, 5, TOL_MASS)
    f.gleich("Profil-ID-Vorschlag", t.profil_id_vorschlag, "T 40x50x5x5")


@fall("REF18", "Z 60 × 40 × 4 scharfkantig: Kantteil (Blech-Editor) mit Schenkeln 40/60/40, nie Rohrlaser",
      REF / "REF18_Z60x40x4_L500.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Profilform", t.profilform, "Blech gekantet")
    f.gleich("Prüfstatus", t.pruefstatus, "prüfen")
    f.gleich("Schenkel", [x["laenge"] for x in t.blech["abwicklung"]["schenkel"]], [40, 60, 40])
    f.wert("Kantlänge", t.blech["abwicklung"]["kantlaenge"], 500, TOL_MASS)


@fall("REF14", "Flächenmodell mit loser Fläche: Rohr gemessen, lose Fläche gemeldet",
      REF / "REF14_Flaechenmodell_mit_loser_Flaeche.step")
def _(f, p):
    teile = analysiere_datei(p)
    f.gleich("Körperarten", [t.koerperart for t in teile], ["aus Flächenmodell genäht", "Flächenmodell offen"])
    f.gleich("Profilform Körper 1", teile[0].profilform, "Quadratrohr")
    f.wert("Seite Körper 1", teile[0].abm_a, 40, TOL_MASS)
    f.gleich("Prüfstatus lose Fläche", teile[1].pruefstatus, "nicht messbar")


@fall("REF15", "U 50x30x3 mit Bohrungen in Steg und Flansch, Ausschnitt, Sackbohrung, 45°-Gehrung",
      REF / "REF15_U50x30x3_Konturen.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Profilform", t.profilform, "U-Profil")
    for was, ist, soll in (("Steg", t.abm_a, 50), ("Flansch", t.abm_b, 30), ("Wand", t.wandstaerke, 3),
                           ("Länge", t.laenge, 800), ("Querschnitt", t.flaeche, 312)):
        f.wert(was, ist, soll, TOL_MASS)
    a, b = t.konturen_liste[:2]
    f.gleich("Ende A Form", a["form"], "gerade")
    f.wert("Ende A Schnittlänge (halber Umfang)", a["schnittlaenge"], 107, 0.05)
    f.gleich("Ende B Form", b["form"], "Gehrung")
    f.winkel("Ende B Gehrungswinkel", b["gehrung"], 45)
    f.wert("Ende B Schnittlänge", b["schnittlaenge"], (100 + 114 * math.sqrt(2)) / 2, 0.05)
    soll = [("Bohrung", 200, dict(durchmesser=8)), ("Bohrung", 400, dict(durchmesser=6)),
            ("Ausschnitt", 600, dict(laenge=20, breite=10)), ("Sackbohrung", 700, dict(durchmesser=5))]
    f.gleich("Konturarten", [d["art"] for d in t.konturen_liste[2:]], [x[0] for x in soll])
    for i, (d, (art, z, masse)) in enumerate(zip(t.konturen_liste[2:], soll), 1):
        f.wert(f"{i} {art} z", d["z"], z, TOL_LAGE)
        for k, v in masse.items():
            f.wert(f"{i} {art} {k}", d[k], v, TOL_MASS)
    f.wert("Schneidweg", t.schneidweg, 107 + (100 + 114 * math.sqrt(2)) / 2 + math.pi * 14 + 60, 0.1)
    f.gleich("Einstiche", t.konturen, 5)
    f.gleich("Prüfstatus (Sackbohrung)", t.pruefstatus, "prüfen")


@fall("REF16", "L 40x40x4 mit Bohrung Ø10", REF / "REF16_L40x40x4_Bohrung.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "L-Profil", 40, 40, 4, 500)
    f.wert("Schneidweg", t.schneidweg, 2 * 80 + math.pi * 10, 0.05)
    f.gleich("Bohrungen", t.bohrungen, {10.0: 1})
    f.wert("Bohrung z", t.konturen_liste[2]["z"], 150, TOL_LAGE)


@fall("REF17", "Flachstahl 40x5 mit zwei Bohrungen Ø9", REF / "REF17_FL40x5_Bohrungen.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Flachstahl", 40, 5, 0, 300)
    f.wert("Schneidweg", t.schneidweg, 2 * 45 + 2 * math.pi * 9, 0.05)
    f.gleich("Lage der Bohrungen", [d["z"] for d in t.konturen_liste[2:]], [50.0, 250.0])
    f.gleich("Einstiche", t.konturen, 4)


BL = HIER / "step_bleche"
# Bleche (seit 20.10.2026): Bauteiltyp, Länge, Breite, Dicke, Kontur, Bohrungen; Abgrenzung zum Flachstahl
# (Breite bis 150 mm, Länge mindestens 3 × Breite, gerade Längsseiten) und Negativfälle
BLECHE = [  # Nr, Datei, Typ, Länge, Breite, Dicke, Kontur, Bohrungen {Ø: Anzahl}, Innenkonturen, Prüfstatus
    ("BL01", "B01_Blech_500x300x5", "Blech", 500, 300, 5, "rechteckig", {}, 0, "plausibel"),
    ("BL02", "B02_Blech_400x200x4_Bohrungen", "Blech", 400, 200, 4, "rechteckig", {10.0: 4, 20.0: 1}, 5, "plausibel"),
    ("BL03", "B03_Blech_600x400x3_Ausschnitte", "Blech", 600, 400, 3, "rechteckig", {}, 2, "plausibel"),
    ("BL04", "B04_Blech_400x250x6_Kontur", "Blech", 400, 250, 6, "frei", {}, 0, "plausibel"),
    ("BL05", "B05_Blech_500x300x5_gedreht", "Blech", 500, 300, 5, "rechteckig", {}, 0, "plausibel"),
    ("BL06", "B06_Blech_250x180x8_schraeg", "Blech", 250, 180, 8, "rechteckig", {16.0: 1}, 1, "plausibel"),
    ("BL07", "B07_Blech_gekantet_Winkel", "Blech gekantet", 120, 100, 3, "gekantet", {}, 0, "prüfen"),
    ("BL10", "B10_Blech_1000x160x8", "Blech", 1000, 160, 8, "rechteckig", {}, 0, "plausibel"),
    ("BL11", "B11_Blech_100x40x8", "Blech", 100, 40, 8, "rechteckig", {}, 0, "plausibel"),
    ("BL12", "B12_Blech_300x200x5_Fase", "Blech", 300, 200, 5, "rechteckig", {}, 0, "plausibel"),
    ("BL13", "B13_Blech_30x20x3_Rest", "Blech", 30, 20, 3, "rechteckig", {}, 0, "plausibel"),
]


def _blech_fall(nr, datei, typ, lg, br, d, kontur, bohrungen, innen, status):
    @fall(nr, f"{typ}: {datei.split('_', 1)[1]}", BL / f"{datei}.step")
    def _(f, p):
        (t,) = analysiere_datei(p)
        f.gleich("Bauteiltyp", t.bauteiltyp, typ)
        f.wert("Länge", t.blech and t.blech["laenge"], lg, TOL_MASS)
        f.wert("Breite", t.blech and t.blech["breite"], br, TOL_MASS)
        f.wert("Dicke", t.blech and t.blech["dicke"], d, TOL_MASS)
        f.gleich("Kontur", t.blech and t.blech["kontur"], kontur)
        f.gleich("Bohrungen", t.blech and t.blech["bohrungen"], bohrungen)
        f.gleich("Innenkonturen", t.blech and t.blech["innen"], innen)
        f.gleich("Prüfstatus", t.pruefstatus, status)
        f.gleich("kein Profil-ID-Vorschlag", t.profil_id_vorschlag, "")


for _z in BLECHE:
    _blech_fall(*_z)


@fall("BL08", "dünne Platte mit Tasche ist kein Blech (prüfen)", BL / "B08_Platte_mit_Tasche.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("kein Blech", t.bauteiltyp in ("Blech", "Blech gekantet"), False)
    f.gleich("Prüfstatus", t.pruefstatus, "prüfen")


@fall("BL09", "Flachstahl 100x10 L 800 bleibt Flachstahl", BL / "B09_FL100x10_L800.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Bauteiltyp", t.bauteiltyp, "Profil")
    grundmasse(f, t, "Flachstahl", 100, 10, 0, 800)


@fall("BL14", "Baugruppe Rechteckrohr mit zwei Fußplatten", BL / "B14_Baugruppe_Rohr_2Bleche.step")
def _(f, p):
    teile = analysiere_datei(p)
    f.gleich("Bauteiltypen", [t.bauteiltyp for t in teile], ["Profil", "Blech", "Blech"])
    grundmasse(f, teile[0], "Rechteckrohr", 60, 40, 2, 800)
    for t in teile[1:]:
        f.wert(f"K{t.koerper} Länge", t.blech["laenge"], 150, TOL_MASS)
        f.wert(f"K{t.koerper} Dicke", t.blech["dicke"], 8, TOL_MASS)


@fall("BL15", "Flachstahl-Grenze aus der Einstellung (200 mm: 160 breit ist Flachstahl)", BL / "B10_Blech_1000x160x8.step")
def _(f, p):
    (t,) = analysiere_datei(p, flach_bis=200)
    f.gleich("Bauteiltyp", t.bauteiltyp, "Profil")
    grundmasse(f, t, "Flachstahl", 160, 8, 0, 1000)


@fall("BL16", "Profile und Rohre sind keine Bleche (alle Referenzteile)", REF)
def _(f, p):
    for q in sorted(list(p.glob("*.step")) + list((HIER / "step_profile").glob("*.step"))):
        try:
            teile = analysiere_datei(q)
        except ValueError:
            continue
        f.gleich(f"{q.stem}", [t.bauteiltyp for t in teile if t.bauteiltyp in ("Blech", "Blech gekantet")], [])


TG = HIER / "step_traeger"
# Träger und T-Profile (seit 20.10.2026): Höhe, Breite, Steg, Flansch, Symmetrie, Normprofil nur bei passenden Maßen
TRAEGER = [  # Nr, Datei, Form, h, b, Steg, Flansch, symmetrisch, Normprofil, Profil-ID, Prüfstatus
    ("TR01", "TR01_IPE200_L1000", "I-/H-Träger", 200, 100, 5.6, 8.5, True, "IPE 200", "IPE 200", "plausibel"),
    ("TR02", "TR02_HEB160_L800", "I-/H-Träger", 160, 160, 8, 13, True, "HEB 160", "HEB 160", "plausibel"),
    ("TR03", "TR03_HEA200_gedreht_L600", "I-/H-Träger", 190, 200, 6.5, 10, True, "HEA 200", "HEA 200", "plausibel"),
    ("TR04", "TR04_I150x80x5x7_L700", "I-/H-Träger", 150, 80, 5, 7, True, "", "I 150x80x5x7", "plausibel"),
    ("TR05", "TR05_I200_unsymmetrisch_L600", "I-/H-Träger", 200, 100, 6, 8, False, "", "I 200x100x6x8", "prüfen"),
    ("TR06", "TR06_T50_L600", "T-Profil", 50, 50, 6, 6, True, "T 50", "T 50", "plausibel"),
    ("TR07", "TR07_T60x40x5x7_L500", "T-Profil", 60, 40, 5, 7, True, "", "T 60x40x5x7", "plausibel"),
    ("TR09", "TR09_IPE200_Stegbohrungen_L1000", "I-/H-Träger", 200, 100, 5.6, 8.5, True, "IPE 200", "IPE 200",
     "plausibel"),
]


def _traeger_fall(nr, datei, form, h, b, tw, tf, sym, norm, pid, status):
    @fall(nr, f"{form}: {datei.split('_', 1)[1]}", TG / f"{datei}.step")
    def _(f, p):
        (t,) = analysiere_datei(p)
        f.gleich("Profilform", t.profilform, form)
        f.wert("Höhe", t.abm_a, h, TOL_MASS)
        f.wert("Breite", t.abm_b, b, TOL_MASS)
        f.wert("Stegdicke", t.stegdicke, tw, TOL_MASS)
        f.wert("Flanschdicke", t.flanschdicke, tf, TOL_MASS)
        f.gleich("Wandstärke = Steg", round(t.wandstaerke, 3), round(t.stegdicke, 3))
        f.gleich("symmetrisch", t.symmetrisch, sym)
        f.gleich("Normprofil", t.normprofil, norm)
        f.gleich("Profil-ID-Vorschlag", t.profil_id_vorschlag, pid)
        f.gleich("Prüfstatus", t.pruefstatus, status)
        f.gleich("Enden gerade", [k["form"] for k in t.konturen_liste[:2]], ["gerade", "gerade"])


for _z in TRAEGER:
    _traeger_fall(*_z)


@fall("TR08", "U-Profil mit Normmaßen UPN 100 (Steg 6, Flansch 8,5)", TG / "TR08_UPN100_L900.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "U-Profil", 100, 50, 6, 900)
    f.gleich("Normprofil", t.normprofil, "UPN 100")
    f.wert("Flanschdicke", t.flanschdicke, 8.5, TOL_MASS)


@fall("TR10", "Bohrungen im IPE-Steg: zwei Konturen mit Schneidweg", TG / "TR09_IPE200_Stegbohrungen_L1000.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Innenkonturen", t.innen_konturen, 2)
    f.wert("Schnittlänge Bohrungen", t.innen, 2 * 13 * math.pi, 0.1)


@fall("TR11", "Normprofil nur bei passenden Maßen (Tabelle)", TG)
def _(f, p):
    from rohrlaser import normprofile
    f.gleich("IPE 200", normprofile.zuordnen("I-/H-Träger", 200, 100, 5.6, 8.5, 2848), "IPE 200")
    f.gleich("Steg 0,5 mm dicker: kein IPE", normprofile.zuordnen("I-/H-Träger", 200, 100, 6.1, 8.5), None)
    f.gleich("Fläche 5 % größer: kein IPE", normprofile.zuordnen("I-/H-Träger", 200, 100, 5.6, 8.5, 2990), None)
    f.gleich("HEB 300", normprofile.zuordnen("I-/H-Träger", 300, 300, 11, 19, 14910), "HEB 300")
    f.gleich("L 50x50x5", normprofile.zuordnen("L-Profil", 50, 50, 5, 5), "L 50x50x5")
    f.gleich("L 55x50x5 kein Normwinkel", normprofile.zuordnen("L-Profil", 55, 50, 5, 5), None)


def k01_pruefen(f, t, mit_winkel):
    f.gleich("Profilform", t.profilform, "Rechteckrohr")
    for was, ist, soll in (("Außenmaß A", t.abm_a, 60), ("Außenmaß B", t.abm_b, 40), ("Wandstärke", t.wandstaerke, 3),
                           ("Länge", t.laenge, 850 + 20 * math.tan(math.radians(30)))):
        f.wert(was, ist, soll, TOL_MASS)
    # Sackbohrung ist nicht laserbar: Teil muss zur Prüfung, nicht 'plausibel'
    f.gleich("Prüfstatus", t.pruefstatus, "prüfen")
    f.gleich("Hinweis Sackbohrung", any("Sackbohrung" in h for h in t.hinweise), True)
    kl = t.konturen_liste
    f.gleich("Ende B Form", kl[1]["form"], "Gehrung")
    f.winkel("Ende B Gehrungswinkel", kl[1]["gehrung"], 30)
    soll = [("Bohrung", 100, 0, dict(durchmesser=10)), ("Bohrung", 200, 270, dict(durchmesser=6.6)),
            ("Langloch", 400, 180, dict(laenge=30, breite=10)),
            ("Rechteckausschnitt", 600, 90, dict(laenge=20, breite=10)),
            ("Sackbohrung", 700, 0, dict(durchmesser=6))]
    f.gleich("Konturarten", [d["art"] for d in kl[2:]], [s[0] for s in soll])
    for i, (d, (art, z, w, masse)) in enumerate(zip(kl[2:], soll), 1):
        f.wert(f"{i} {art} z", d["z"], z, TOL_LAGE)
        if mit_winkel:
            f.winkel(f"{i} {art} Umfangswinkel", d["winkel"], w, 0.2)
        for k, v in masse.items():
            f.wert(f"{i} {art} {k}", d[k], v, TOL_MASS)
        f.gleich(f"{i} {art} durchgehend", d["durchgehend"], art != "Sackbohrung")


@fall("K01", "Rohr mit bekannten Bohrungen, Langloch, Ausschnitt, Sackbohrung und 30°-Schrägschnitt",
      HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    k01_pruefen(f, t, True)


@fall("K02", "dasselbe Teil gedreht und verschoben", HIER / "step_konturen" / "K02_RE60x40x3_Konturen_gedreht.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    k01_pruefen(f, t, False)      # Umfangswinkel hängen von der Lage in der Datei ab (0° = oben)


@fall("K03", "Rundrohr mit Bohrungen, schräger Bohrung und zweiachsigem Schrägschnitt",
      HIER / "step_konturen" / "K03_RR42-4x2_Konturen.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Profilform", t.profilform, "Rundrohr")
    f.wert("Außen-Ø", t.abm_a, 42.4, TOL_MASS)
    f.wert("Wandstärke", t.wandstaerke, 2, TOL_MASS)
    # Ende A: Schnittebene durch z 30, um 20° und 10° geneigt; z der Konturen zählt ab dem tiefsten Punkt von Ende A
    a20, a10 = math.radians(20), math.radians(10)
    n = (math.cos(a20) * math.sin(a10), -math.sin(a20), math.cos(a20) * math.cos(a10))
    zmin = 30 - 21.2 * math.hypot(n[0], n[1]) / n[2]
    a = t.konturen_liste[0]
    f.gleich("Ende A Form", a["form"], "Schrägschnitt zweiachsig")
    f.winkel("Ende A Gesamtneigung", a["gehrung"], math.degrees(math.acos(n[2])))
    f.winkel("Ende A um Y", a["um_y"], 10)
    f.wert("Länge", t.laenge, 700 - zmin, TOL_MASS)
    bohr = [d for d in t.konturen_liste[2:] if d["art"] == "Bohrung"]
    f.gleich("Anzahl Bohrungen", len(bohr), 3)
    for d, (z, dm, w) in zip(bohr, ((150, 8, 0), (300, 8, 0), (450, 12, 90))):
        if z != 300:      # schräge Bohrung: Lage = Mitte des Austritts außen, liegt hinter z 300
            f.wert(f"Bohrung z {z}", d["z"], z - zmin, TOL_LAGE)
            f.winkel(f"Bohrung z {z} Umfangswinkel", d["winkel"], w, 0.2)
        f.wert(f"Bohrung z {z} Ø", d["durchmesser"], dm, TOL_MASS)
    f.winkel("schräge Bohrung Neigung", bohr[1].get("schraeg"), 30)


@fall("I01", "Einheit Zoll", HIER / "step_import" / "I01_RE60x40x2_L1000_Zoll.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Einheit", t.einheit, "inch")
    grundmasse(f, t, "Rechteckrohr", 60, 40, 2, 1000)


@fall("I02", "Einheit Meter", HIER / "step_import" / "I02_RR42-4x2_L1000_Meter.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Einheit", t.einheit, "m")
    grundmasse(f, t, "Rundrohr", 42.4, 0, 2, 1000)


@fall("I03", "Flächenmodell wird vernäht und gemessen", HIER / "step_import" / "I03_QR40x2_L800_Flaechenmodell.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    f.gleich("Körperart", t.koerperart, "aus Flächenmodell genäht")
    f.gleich("Warnung Flächenmodell", any("Flächenmodell" in h for h in t.hinweise), True)
    f.wert("Seite", t.abm_a, 40, TOL_MASS)
    f.wert("Wandstärke", t.wandstaerke, 2, TOL_MASS)


@fall("I05", "ungültige STEP-Datei wird gemeldet, keine Maße erfunden", HIER / "step_import" / "I05_defekt.step")
def _(f, p):
    try:
        teile = analysiere_datei(p)
    except ValueError as e:
        f.gleich("Fehlermeldung 'nicht lesbar'", "nicht lesbar" in str(e), True)
    else:
        f.gleich("Fehlermeldung 'nicht lesbar'", f"keine, {len(teile)} Körper", "Fehler")


@fall("R01", "Freiformflächen (NURBS) statt Ebenen/Radien", HIER / "step_regression" / "R01_RE60x40x2_L1000_Freiform.step")
def _(f, p):
    (t,) = analysiere_datei(p)
    grundmasse(f, t, "Rechteckrohr", 60, 40, 2, 1000)
    f.gleich("Außenmantel nicht als Innenkontur", len(t.konturen_liste), 2)


def _lesen(q):
    try:
        return analysiere_datei(q), None
    except ValueError as e:
        return [], str(e)


@fall("JSON", "Messergebnis als JSON: Schema, Version, null für nicht Gemessenes", HIER / "step_import")
def _(f, p):
    ergebnis = step_ergebnis.gesamt([step_ergebnis.datei(q.name, *_lesen(q)) for q in sorted(p.glob("*.step"))])
    text = json.dumps(ergebnis, ensure_ascii=False)
    f.gleich("Schema", ergebnis["schema"], step_ergebnis.SCHEMA)
    f.gleich("Version", ergebnis["schema_version"], step_ergebnis.SCHEMA_VERSION)
    nach = {d["datei"]: d for d in ergebnis["dateien"]}
    offen = nach["I04_Flaechenmodell_offen.step"]["koerper"][0]
    f.gleich("offenes Flächenmodell: Länge null", offen["laenge"], None)
    f.gleich("defekte Datei: kein Körper", nach["I05_defekt.step"]["koerper"], [])
    f.gleich("JSON gültig", json.loads(text)["schema_version"], step_ergebnis.SCHEMA_VERSION)


def bericht():
    return {
        "bericht": "rohrlaser-step-referenztests",
        "version": "1.0",
        "zeitpunkt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "umgebung": {"python": platform.python_version(), "system": platform.system()},
        "toleranzen": {"mass_mm": TOL_MASS, "winkel_grad": TOL_WINKEL, "lage_mm": TOL_LAGE},
        "zusammenfassung": {"faelle": len(faelle), "ok": sum(f.ok for f in faelle),
                            "fehler": sum(not f.ok for f in faelle),
                            "merkmale": sum(len(f.merkmale) for f in faelle),
                            "merkmale_ok": sum(m["ok"] for f in faelle for m in f.merkmale)},
        "faelle": [dict(nr=f.nr, name=f.name, datei=f.datei, ok=f.ok, fehler=f.fehler, dauer_s=f.dauer,
                        merkmale=f.merkmale) for f in faelle],
        "nicht_ausgefuehrt": NICHT_AUSGEFUEHRT,
        "bekannte_grenzen": GRENZEN,
        "hinweis": "Testbericht der Messung, keine Fertigungsfreigabe.",
    }


def markdown(b):
    """Kurzfassung für die CI-Übersicht (GITHUB_STEP_SUMMARY)."""
    z = b["zusammenfassung"]
    zeilen = [f"## STEP-Referenztests: {z['ok']}/{z['faelle']} Fälle ok, {z['merkmale_ok']}/{z['merkmale']} Merkmale ok",
              "", "| Fall | Teil | Ergebnis | Merkmale |", "|---|---|---|---|"]
    for f in b["faelle"]:
        n_ok = sum(m["ok"] for m in f["merkmale"])
        zeilen.append(f"| {f['nr']} | {f['name']} | {'ok' if f['ok'] else 'FEHLER'} | {n_ok}/{len(f['merkmale'])} |")
    zeilen += ["", "Nicht ausgeführt: " + "; ".join(f"{n['test']} ({n['grund']})" for n in b["nicht_ausgefuehrt"]),
               "", "Bekannte Grenzen:", ""] + [f"- {g}" for g in b["bekannte_grenzen"]]
    return "\n".join(zeilen) + "\n"


if __name__ == "__main__":
    b = bericht()
    if "--bericht" in sys.argv:
        ziel = Path(sys.argv[sys.argv.index("--bericht") + 1])
        ziel.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Testbericht:", ziel)
    if "--markdown" in sys.argv:
        Path(sys.argv[sys.argv.index("--markdown") + 1]).open("a", encoding="utf-8").write(markdown(b))
    z = b["zusammenfassung"]
    print(f"{z['ok']}/{z['faelle']} Fälle ok, {z['merkmale_ok']}/{z['merkmale']} Merkmale ok")
    sys.exit(1 if z["fehler"] else 0)
