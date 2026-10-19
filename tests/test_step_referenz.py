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
    "Offene Profile (U, L, C, Flachstahl) werden erkannt und gemeldet, aber nicht kalkuliert; ihre Konturen werden "
    "nicht ausgewertet.",
    "Nicht konvexe Hohlprofile (z. B. Rohre mit Sicke) werden über ihr umschließendes Rechteck gemessen; sie "
    "erscheinen als Rechteck-/Quadratrohr mit Prüfstatus 'prüfen' (Wandstärke uneinheitlich), nicht als Sonderprofil.",
    "Schräge Bohrungen werden über die Zylinderfläche erkannt; nicht zylindrische schräge Durchbrüche erscheinen als "
    "Ausschnitt mit Umriss.",
    "Flächenmodelle werden nur gemessen, wenn sie sich zu einem geschlossenen Körper vernähen lassen.",
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
