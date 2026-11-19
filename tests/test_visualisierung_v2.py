"""3D-Visualisierungsupdate V2 (Patrick 19.11.2026): Material, Lichtprofil, Hintergrund, Kontaktschatten.

V1 visualisierung: Vorgaben, Unbekanntes fällt auf die Vorgabe zurück; ohne Umgebungsspiegelung rechnet „Standard“ +
   „Werkstatt“ das Licht genau wie vorher, mit ihr ist die Oberseite deutlich heller als die Seite (plastischer);
   gleiche Formel wie im OpenGL-Shader
V2 Material färbt nur Außen-/Innenwand und Blech; Signalfarben (Konturen, Gravur, Schnitte, Nähte, Teilfarben) bleiben
V3 Bild: Materialien sehen verschieden aus, Hintergrund Weiß/Verlauf, Dunkelmodus bleibt dunkel; Netz unverändert
V4 Kontaktschatten unter dem Modell auf seinem Boden (aus: kein Schatten; Drahtgitter/Durchsichtig: keiner)
V5 Leiste „Aussehen“ in jeder 3D-Ansicht, Einstellungen je Arbeitsplatz (lokal, nie abgeglichen), Einstellungsseite
V6 Tempo (Phase V3): Körperkanten großer Modelle im Hintergrund, Farb-Zwischenspeicher, Umriss beim Drehen,
   STEP-Viewer mit Laufbalken und verstrichener Zeit

Aufruf: python tests/test_visualisierung_v2.py
"""
import copy
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, ansicht3d_leiste, einstellungen_ordnung, rohr3d, stil, teilen  # noqa: E402
from rohrlaser import visualisierung as vis  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNGEN  # noqa: E402

ansicht3d.renderer_setzen("Software")
fehler = []


def ok(bedingung, text):
    print(("OK     " if bedingung else "FEHLER ") + text, flush=True)
    if not bedingung:
        fehler.append(text)


# V1
w = vis.setzen({"ansicht3d_material": "Gold", "ansicht3d_licht": "", "ansicht3d_hintergrund": None,
                "ansicht3d_schatten": "aus"})
ok(w == dict(vis.VORGABEN, ansicht3d_schatten="nein"), f"V1 Unbekanntes → Vorgabe, Schatten aus ({w})")
vis.setzen({})


def alt(nx, ny, nz):            # Formel vor V2 (ansicht3d.licht_wert bis 0.9.409)
    a, neig, fuell, glanz, exp = (0.38, 0.06, 0.16, 0.22, 36.0)
    li, l2 = (-0.35, 0.45, 0.82), (0.55, -0.35, 0.76)
    hell = a + neig * ny + (1 - a) * max(0.0, nx * li[0] + ny * li[1] + nz * li[2]) \
        + fuell * max(0.0, nx * l2[0] + ny * l2[1] + nz * l2[2])
    hx, hy, hz = li[0], li[1], li[2] + 1.0
    b = math.sqrt(hx * hx + hy * hy + hz * hz)
    return hell, glanz * max(0.0, (nx * hx + ny * hy + nz * hz) / b) ** exp


normalen = [(0.0, 0.0, 1.0), (0.6, 0.0, 0.8), (-0.3, 0.5, 0.81), (0.0, -1.0, 0.0), (0.2, 0.9, 0.39)]
ohne_umgebung = vis.licht_werte()[:7] + (0.0, 1.0, 1.0, 1.0)
ok(all(max(abs(x - y) for x, y in zip(ansicht3d.licht_wert(*n, ohne_umgebung), alt(*n))) < 1e-12 for n in normalen),
   "V1 Standard + Werkstatt ohne Umgebungsspiegelung: Licht genau wie vorher")
oben, seite = ansicht3d.licht_wert(0.0, 0.7071, 0.7071)[0], ansicht3d.licht_wert(0.7071, 0.0, 0.7071)[0]
alt_oben, alt_seite = alt(0.0, 0.7071, 0.7071)[0], alt(0.7071, 0.0, 0.7071)[0]
ok(oben - seite > 1.5 * abs(alt_oben - alt_seite) and oben - seite > 0.25,
   f"V1 Umgebungsspiegelung: Oberseite deutlich heller als Seite ({oben:.2f}/{seite:.2f}, vorher "
   f"{alt_oben:.2f}/{alt_seite:.2f})")
ok(abs(vis.umgebung(0.0, 1.2, 0.6, 0.8) - 0.6) < 1e-12 and abs(vis.umgebung(1.0, 1.2, 0.6, 0.8) - 1.2) < 1e-12
   and abs(vis.umgebung(-1.0, 1.2, 0.6, 0.8) - 0.8) < 1e-12, "V1 Umgebung: Horizont, Himmel, Boden")
vis.setzen({"ansicht3d_licht": "Technisch (flach)"})
ok(all(ansicht3d.licht_wert(*n)[1] == 0.0 for n in normalen), "V1 Technisch (flach): ohne Glanz")
vis.setzen({"ansicht3d_material": "Matt"})
ok(all(ansicht3d.licht_wert(*n)[1] == 0.0 for n in normalen), "V1 Matt: ohne Glanz")
vis.setzen({"ansicht3d_material": "Edelstahl", "ansicht3d_licht": "Studio"})
ok(ansicht3d.licht_wert(-0.2, 0.3, 0.93)[1] > alt(-0.2, 0.3, 0.93)[1], "V1 Edelstahl/Studio glänzt stärker")
gl_quelle = Path(ansicht3d.__file__).with_name("ansicht3d_gl.py").read_text(encoding="utf-8")
ok("glanz * pow(max(0.0, dot(n, h)), glanz_exp)" in gl_quelle and "visualisierung.licht_werte()" in gl_quelle
   and "horizont + (himmel - horizont) * (2.0 * ry - ry * ry)" in gl_quelle,
   "V1 OpenGL-Shader: dieselbe Formel und dieselben Werte")

# V2
vis.setzen({})
standard = ansicht3d.flaechen_farben()
ok({a: c.name() for a, c in standard.items()} == {a: c.name() for a, c in ansicht3d.FARBE.items()},
   "V2 Standard: Farben wie bisher")
for name in vis.MATERIALIEN:
    vis.setzen({"ansicht3d_material": name})
    f = ansicht3d.flaechen_farben()
    anders = {a for a in f if f[a].name() != standard[a].name()}
    erlaubt = set() if name == vis.STANDARD else {"A", "I", "BL"}
    ok(anders == erlaubt and all(f[a].name() == standard[a].name()
                                 for a in ("K", "G", "EA", "EB", "SN", "NL", "F0", "KO0", "N", "AN")),
       f"V2 {name}: nur Außen-/Innenwand und Blech gefärbt ({sorted(anders)})")

# V3
netz = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art="Kreis", x=150, d=12, seite=0)]),
                   dict(form="Rundrohr", d=42.4, wand=2), 300)
vorher = copy.deepcopy(netz)
a = ansicht3d.Ansicht3D()
a.resize(600, 360)
a.setzen(netz)
a.show()
app.processEvents()


def bild(werte):
    ansicht3d.aussehen_setzen(werte)
    vis.setzen(dict(vis.VORGABEN, **werte))
    a._bild = None
    app.processEvents()
    return a.grab().toImage()


def mitte_farbe(img):
    c = img.pixelColor(img.width() // 2, img.height() // 2 - 4)
    return c.red(), c.green(), c.blue()


farben = {name: mitte_farbe(bild({"ansicht3d_material": name, "ansicht3d_schatten": "nein"}))
          for name in vis.MATERIALIEN}
ok(len(set(farben.values())) == len(farben), f"V3 jedes Material sieht anders aus ({farben})")
lack = farben["Lackiert (RAL 5010)"]
ok(lack[2] > lack[0] + 30, f"V3 Lackiert RAL 5010 ist blau ({lack})")
weiss = bild({"ansicht3d_hintergrund": "Weiß", "ansicht3d_schatten": "nein"})
verlauf = bild({"ansicht3d_hintergrund": "Verlauf", "ansicht3d_schatten": "nein"})
ok(weiss.pixelColor(3, 3).name().upper() == "#FFFFFF" and verlauf.pixelColor(3, 3).name().upper() != "#FFFFFF",
   "V3 Hintergrund Weiß bzw. Verlauf (oben blaugrau)")
stil.anwenden(app, "Dunkel")
vis.setzen({"ansicht3d_hintergrund": "Weiß"})
ok(ansicht3d.hintergrund_farben()[1].lightness() < 128, "V3 Dunkelmodus: Hintergrund bleibt dunkel")
stil.anwenden(app, "Hell")
ok(netz == vorher, "V3 Netz nach allen Materialien unverändert")

# V4
vis.setzen({"ansicht3d_schatten": "ja"})
lage = a.schatten_lage()
unterste = max(y for _, y in lage) if lage else 0
ok(lage is not None and len(lage) >= 3 and unterste > a.height() / 2, f"V4 Schatten unter dem Modell ({lage})")
mit = bild({"ansicht3d_schatten": "ja", "ansicht3d_hintergrund": "Weiß"})
ohne = bild({"ansicht3d_schatten": "nein", "ansicht3d_hintergrund": "Weiß"})
x, y = max(lage, key=lambda q: q[1])         # unterste Ecke des Schattens (unter dem Modell, nicht verdeckt)
x, y = int(x), min(a.height() - 1, int(y) - 1)
ok(mit.pixelColor(x, y).lightness() < ohne.pixelColor(x, y).lightness() - 5,
   f"V4 Schatten sichtbar ({mit.pixelColor(x, y).name()} statt {ohne.pixelColor(x, y).name()})")
vis.setzen({"ansicht3d_schatten": "nein"})
ok(a.schatten_lage() is None, "V4 Schatten aus: keiner")
vis.setzen({})
a.darstellung_setzen(ansicht3d.DRAHTGITTER)
ok(a.schatten_lage() is None, "V4 Drahtgitter: kein Schatten")
a.darstellung_setzen(ansicht3d.SCHATTIERT)

# V5
leiste = ansicht3d_leiste.Leiste3D(a)
menue = leiste.aussehen.menu()
titel = [act.text() for act in menue.actions()]
ok(titel[:3] == ["Material", "Licht", "Hintergrund"] and "Schatten unter dem Modell" in titel,
   f"V5 Leiste: Menü Aussehen ({titel})")
material_menue = menue.actions()[0].menu()
edel = next(act for act in material_menue.actions() if act.text() == "Edelstahl")
edel.trigger()
ok(vis.aktuell()["ansicht3d_material"] == "Edelstahl", "V5 Auswahl im Menü gilt sofort")
menue.aboutToShow.emit()
ok(edel.isChecked(), "V5 Menü zeigt die aktuelle Wahl")
namen = {e.name for e in EINSTELLUNGEN}
seite = {n for ab in einstellungen_ordnung.SEITE["e_navigation"].abschnitte for n in ab.namen}
ok(set(vis.NAMEN) <= namen and set(vis.NAMEN) <= teilen.LOKAL and set(vis.NAMEN) <= seite,
   "V5 Einstellungen vorhanden, nur dieser Arbeitsplatz, auf der Seite „3D-Ansicht und Navigation“")
ok(all(e.vorgabe == vis.VORGABEN[e.name] for e in EINSTELLUNGEN if e.name in vis.NAMEN),
   "V5 Vorgaben der Einstellungen = Vorgaben der Ansicht")
vis.setzen({})

# V6 (Phase V3 Tempo)
import time  # noqa: E402

from rohrlaser import anhang_vorschau as av, step  # noqa: E402

REF = HIER / "step_referenz"
gross = None
befehl = step.messprogramm(HIER.parent / "programm")
try:
    sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
    from step_geometrie import analysiere_datei
    gross = [t.netz for t in analysiere_datei(REF / "REF15_U50x30x3_Konturen.step", netz=True) if t.netz][0]
except Exception as e:      # noqa: BLE001
    print("--     V6 STEP-Messung nicht verfügbar:", e)
if gross is not None:
    b = ansicht3d.Ansicht3D()
    b.resize(500, 300)
    b.setzen(gross)
    ok(len(b.voll.dreiecke) >= ansicht3d.VORRECHNEN_AB, f"V6 großes Modell ({len(b.voll.dreiecke)} Dreiecke)")
    ansicht3d.vorrechnen_warten()
    ok(b.voll.__dict__.get("_kanten") is not None and b.voll.__dict__.get("_glatt_kanten") is not None,
       "V6 Körperkanten nach dem Laden im Hintergrund vorgerechnet")
    t0 = time.perf_counter()
    b.voll.kanten()
    ok(time.perf_counter() - t0 < 0.01, "V6 erster Klick auf „Mit Kanten“ wartet nicht mehr")
    roh = copy.deepcopy(gross)
    ok(gross == roh, "V6 Netz unverändert")
leer = ansicht3d.Modell(dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t={"A": [0, 1, 2]}))
ok(not ansicht3d.vorrechnen(leer) and leer.kanten() is not None, "V6 kleine Modelle: rechnet sofort, ohne Hintergrund")
quelle = Path(ansicht3d.__file__).read_text(encoding="utf-8")
ok("farb_cache" in quelle and "grundfarbe" in quelle, "V6 Software-Bild: Stift und Pinsel je Farbe nur einmal")
gl_q = Path(ansicht3d.__file__).with_name("ansicht3d_gl.py").read_text(encoding="utf-8")
ok("bewegt = a._maus is not None or a._eilig" in gl_q, "V6 OpenGL: Umriss beim Drehen nicht je Bild neu gerechnet")
if befehl:
    v = av.fenster(None, [dict(name="REF02.step", pfad=REF / "REF02_QR40x40x2_L1000.step")], 0, None, befehl)
    w0 = v.flaeche.currentWidget()
    ok(getattr(w0, "balken", None) is not None and "3D wird berechnet" in w0.meldung,
       "V6 STEP-Viewer: Laufbalken während der Messung")
    v._start -= 3
    v._step_pruefen()
    if v._lauf is not None:
        ok(" s" in w0.text_feld.text(), f"V6 STEP-Viewer: verstrichene Zeit ({w0.text_feld.text()[:30]})")
    v.step_warten()
    ok(type(v.flaeche.currentWidget()).__name__ == "Ansicht3D", "V6 STEP-Viewer: danach das 3D-Modell")
else:
    print("--     V6 STEP-Viewer übersprungen: keine STEP-Messung in dieser Umgebung")

print("\n" + (f"{len(fehler)} Fehler." if fehler else "Alle Prüfungen bestanden."))
sys.exit(1 if fehler else 0)
