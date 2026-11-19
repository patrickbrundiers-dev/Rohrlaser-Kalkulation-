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
V7 Navigation (Phase V4): Mausbelegung wie Inventor/SolidWorks/Creo, Zoomrichtung, Stärke des Nachlaufs
V8 Darstellungen (Phase V5): zehn Arten (neu: Verdeckt ausgeblendet, Durchsichtig mit Kanten, Flächentypen, Konturen
   betont, Nur Konturen), lange Dreiecke fürs Sortieren geteilt (nichts scheint durch)
V9 Schnitt und Explosion (Phase V6): bis zu drei Ebenen, nichts jenseits der Ebene, Schnittkanten, Wandstärke an der
   Schnittstelle = Wand; Explosion zieht Körper auseinander; Netz/volles Modell unverändert, Messen in der Explosion
   gesperrt, Knöpfe in allen Editoren, Bild/PDF speichern
V10 Zentrale 3D-Einstellungen (Phase V7): feste Profile gültig, eigene Profile je Arbeitsplatz (nie abgeglichen),
   Export/Import als JSON (Fremdes/Ungültiges abgewiesen), Selbsttest in Ordnung, Knöpfe auf der Einstellungsseite

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

# V7 (Phase V4 Navigation)
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from rohrlaser import navigation3d as nav  # noqa: E402

SW = "wie SolidWorks (Mitte drehen, Strg+Mitte verschieben)"
INV = "wie Inventor (Umschalt+Mitte drehen, Mitte verschieben)"
ok(nav.aktion("links", set(), {}) == "drehen" and nav.aktion("rechts", set(), {}) == "schieben"
   and nav.aktion("mitte", set(), {}) == "schieben", "V7 Vorgabe wie bisher: links drehen, rechts/Mitte verschieben")
ok(nav.aktion("mitte", set(), {"nav_maus": SW}) == "drehen"
   and nav.aktion("mitte", {"strg"}, {"nav_maus": SW}) == "schieben", "V7 SolidWorks-Belegung")
ok(nav.aktion("mitte", {"umschalt"}, {"nav_maus": INV}) == "drehen"
   and nav.aktion("mitte", set(), {"nav_maus": INV}) == "schieben", "V7 Inventor-Belegung")
ok(abs(nav.zoom_faktor(120, {}) - 1.15) < 1e-12 and abs(nav.zoom_faktor(120, {"nav_zoom_umkehren": "ja"}) - 1 / 1.15)
   < 1e-12, "V7 Zoomrichtung umkehren")


class Speicher:
    def __init__(self, werte):
        self.werte = werte

    def einstellung(self, n):
        return self.werte.get(n)


def maus(w, art, x, y, knopf, mods=Qt.NoModifier):
    w.event(QMouseEvent(art, QPointF(x, y), QPointF(x, y), knopf,
                        knopf if art != QEvent.MouseButtonRelease else Qt.NoButton, mods))


alt_speicher = ansicht3d._speicher
ansicht3d._speicher = Speicher({"nav_maus": SW, "nav_nachlauf": "2"})
ok(nav.werte_lesen(ansicht3d._speicher)["nav_nachlauf"] == 0.97, "V7 Nachlauf-Stärke begrenzt")
c = ansicht3d.Ansicht3D()
c.resize(500, 300)
c.setzen(netz)
lage0 = (c.gier, c.nick, c.roll, c.versatz)
maus(c, QEvent.MouseButtonPress, 200, 150, Qt.MiddleButton)
maus(c, QEvent.MouseMove, 260, 170, Qt.MiddleButton)
maus(c, QEvent.MouseButtonRelease, 260, 170, Qt.MiddleButton)
ok((c.gier, c.nick, c.roll) != lage0[:3], "V7 SolidWorks: mittlere Taste dreht")
lage1 = (c.gier, c.nick, c.roll, c.versatz)
maus(c, QEvent.MouseButtonPress, 200, 150, Qt.MiddleButton, Qt.ControlModifier)
maus(c, QEvent.MouseMove, 240, 150, Qt.MiddleButton, Qt.ControlModifier)
maus(c, QEvent.MouseButtonRelease, 240, 150, Qt.MiddleButton, Qt.ControlModifier)
ok((c.gier, c.nick, c.roll) == lage1[:3] and c.versatz != lage1[3], "V7 SolidWorks: Strg+Mitte verschiebt")
ansicht3d._speicher = alt_speicher
namen_v4 = {"nav_maus", "nav_zoom_umkehren", "nav_nachlauf"}
ok(namen_v4 <= {e.name for e in EINSTELLUNGEN} and namen_v4 <= teilen.LOKAL and namen_v4 <= seite | {
    n for ab in einstellungen_ordnung.SEITE["e_navigation"].abschnitte for n in ab.namen},
   "V7 Einstellungen Mausbelegung, Zoomrichtung, Nachlauf je Arbeitsplatz")

# V8 (Phase V5 Darstellungsarten)
ok(len(ansicht3d.DARSTELLUNGEN) == 10 and len(set(ansicht3d.DARSTELLUNGEN)) == 10, "V8 zehn Darstellungsarten")
if gross is not None:
    L = [t.netz for t in analysiere_datei(REF / "REF16_L40x40x4_Bohrung.step", netz=True) if t.netz][0]
    d = ansicht3d.Ansicht3D()
    d.resize(600, 340)
    d.setzen(L)
    d.show()
    vorher_l = copy.deepcopy(L)
    bilder = {}
    for dar in ansicht3d.DARSTELLUNGEN:
        d.darstellung_setzen(dar)
        d._bild = None
        app.processEvents()
        bilder[dar] = d.grab().toImage()
    ok(d._fehler is None and L == vorher_l, "V8 alle Darstellungen zeichnen ohne Fehler, Netz unverändert")
    typen = ansicht3d.flaechentyp_arten(d.modell)
    ok({"FT_Ebene", "FT_Zylinder"} <= set(typen) and len(typen) == len(d.modell.dreiecke),
       "V8 Flächentypen aus dem STEP-Katalog (Ebene, Zylinder der Bohrung)")
    g = d.modell.grob(max(10, len(d.modell.dreiecke) // 2))
    ok(len(g.dreiecke_f) == len(g.dreiecke) and ansicht3d.flaechentyp_arten(g) is not typen,
       "V8 grobe Stufe behält den Flächenkatalog passend")
    def hell(img):
        return sum(img.pixelColor(x, y).lightness() for x in range(0, img.width(), 7)
                   for y in range(0, img.height(), 7))
    ok(hell(bilder[ansicht3d.NUR_KONTUREN]) > hell(bilder[ansicht3d.MIT_KANTEN])
       and hell(bilder[ansicht3d.VERDECKT_AUS]) > hell(bilder[ansicht3d.MIT_KANTEN]),
       "V8 Nur Konturen und Verdeckt ausgeblendet: ohne dunkle Flächen")
    ok(bilder[ansicht3d.FLAECHENTYPEN] != bilder[ansicht3d.MIT_KANTEN]
       and bilder[ansicht3d.KONTUREN_BETONT] != bilder[ansicht3d.MIT_KANTEN], "V8 Flächentypen/Konturen betont: anders")
    # Vordere Wand eines L-Profils: kein Stück des hinteren Schenkels scheint durch (Sortieren in Stücken)
    d.darstellung_setzen(ansicht3d.SCHATTIERT)
    d._bild = None
    app.processEvents()
    img = d.grab().toImage()
    bild = d.bildpunkt()
    mo = d.modell
    farben_wand = []
    for t in (0.3, 0.5, 0.7):
        q = bild((mo.min[0] + 1.0, (mo.min[1] + mo.max[1]) / 2, mo.min[2] + t * (mo.max[2] - mo.min[2])))
        farben_wand.append(img.pixelColor(int(q[0]), int(q[1])).lightness())
    ok(max(farben_wand) - min(farben_wand) < 25, f"V8 L-Profil: Wand gleichmäßig, nichts scheint durch ({farben_wand})")


def flaeche3(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    return 0.5 * math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                           + (u[0] * v[1] - u[1] * v[0]) ** 2)


teile = ansicht3d._sortier_teile((0, 0, 0), (1000, 0, 0), (0, 40, 5), 50.0 ** 2)
ok(len(teile) > 1 and abs(sum(flaeche3(*t) for t in teile) - flaeche3((0, 0, 0), (1000, 0, 0), (0, 40, 5))) < 1e-6
   and all(max(math.dist(t[i], t[(i + 1) % 3]) for i in range(3)) <= 130.0 for t in teile),
   f"V8 lange Dreiecke fürs Sortieren in {len(teile)} Stücke geteilt, gleiche Fläche")
gl_q = Path(ansicht3d.__file__).with_name("ansicht3d_gl.py").read_text(encoding="utf-8")
ok("ROENTGEN_ARTEN" in gl_q and "DRAHT_ARTEN" in gl_q and "flaechentyp_arten" in gl_q and "BETONT_HELL" in gl_q,
   "V8 OpenGL zeichnet dieselben Darstellungen")

# ------------------------------------------------------------------ V9 Schnitt und Explosion (V6)
from rohrlaser import schnitt_explosion as se  # noqa: E402
from rohrlaser import schneidweg as sw  # noqa: E402

QR9 = dict(form="Quadratrohr", a=40, b=40, wand=3)
netz9 = rohr3d.netz(sw.v_ergaenzen(dict(a={}, b={}, laenge=600, konturen=[]), QR9), QR9, 600)
vorher9 = copy.deepcopy(netz9)
m9 = ansicht3d.Modell(netz9)
for achse in "ZXY":
    e = se.ebene(m9, achse, 0.5)
    g, kanten = se.schneiden(m9, [e])
    i = "XYZ".index(achse)
    weg = max(q[i] for q in g.punkte) if g.punkte else None
    wand = se.wandstaerke(kanten)
    ok(weg is not None and weg <= e[0][i] + 1e-6 and kanten and wand and abs(wand[0] - 3.0) < 0.05,
       f"V9 Schnitt {achse}: nichts jenseits der Ebene, {len(kanten)} Schnittkanten, Wand ≈ {wand and round(wand[0], 2)}")
g2, k2 = se.schneiden(m9, [se.ebene(m9, "Z", 0.5), se.ebene(m9, "X", 0.5, 20.0), se.ebene(m9, "Y", 0.5, 0, True)])
ok(len(g2.dreiecke) < len(m9.dreiecke) and all(se._seite(q, e) <= 1e-6 for q in g2.punkte
                                                for e in [se.ebene(m9, "Z", 0.5)]),
   "V9 drei Ebenen (gekippt, umgekehrt) zugleich")
ok(netz9 == vorher9,
   "V9 Schnitt ändert das Netz nicht")
d9 = ansicht3d.Ansicht3D()
d9.resize(700, 420)
d9.setzen(netz9, "QR")
voll9 = d9.voll
d9.schnittebenen_setzen([dict(achse="Z", anteil=0.5)])
ok(d9.voll is voll9 and d9.modell is not voll9 and "SC" in d9.modell.arten and "Wand" in d9.anzeige_hinweis(),
   f"V9 Ansicht: volles Modell bleibt, gezeigt geschnitten ({d9.anzeige_hinweis()})")
d9.schnittebenen_setzen([])
ok(d9.modell is voll9 and not d9.anzeige_hinweis(), "V9 Schnitt aus: wieder das volle Modell")
LAGE9 = [0, 0, 0, 0, 0, 1, 1, 0, 0]
bg9, _ = ansicht3d.baugruppe([dict(netz9, lage=[x, 0, 0] + LAGE9[3:]) for x in (0, 200, 400)])
bg_vorher = copy.deepcopy(bg9)
d9.setzen(bg9, "BG")
breite = d9.voll.max[0] - d9.voll.min[0]
d9.explosion_setzen(1.0)
ex = d9.modell
ok(ex is not d9.voll and ex.max[0] - ex.min[0] > breite * 1.5 and len(ex.dreiecke) == len(d9.voll.dreiecke),
   f"V9 Explosion: Teile auseinander ({breite:.0f} → {ex.max[0] - ex.min[0]:.0f} mm), gleich viele Dreiecke")
d9.messen_setzen(True)
ok(not d9.messen and "Explosion" in d9.anzeige_hinweis(), "V9 Messen in der Explosion gesperrt, Hinweis sichtbar")
d9.explosion_setzen(0)
ok(d9.modell is d9.voll and bg9 == bg_vorher, "V9 Explosion aus: volles Modell, Netz unverändert")
d9.explosion_setzen(1.0)
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    png = ansicht3d_leiste.ansicht_speichern(d9, os.path.join(tmp, "a.png"))
    pdf = ansicht3d_leiste.ansicht_speichern(d9, os.path.join(tmp, "a.pdf"))
    ok(os.path.getsize(png) > 1000 and open(pdf, "rb").read(4) == b"%PDF", "V9 Ansicht als PNG und PDF gespeichert")
d9.explosion_setzen(0)
le9 = ansicht3d_leiste.Leiste3D(d9)
ok(le9.schnitt.text() == "Schnitt" and le9.explosion.text() == "Explosion", "V9 Knöpfe in der 3D-Leiste")
for datei in ("teile_editor.py", "baugruppe_ansicht.py"):
    q = Path(ansicht3d.__file__).with_name(datei).read_text(encoding="utf-8")
    ok("ansicht_knoepfe(" in q, f"V9 Aussehen/Schnitt/Explosion auch in {datei}")

# ------------------------------------------------------------------ V10 Profile, Export/Import, Selbsttest (V7)
import json  # noqa: E402

from rohrlaser import ansicht3d_profile as ap  # noqa: E402


class DbTest:
    def __init__(self):
        self.d = {}

    def einstellung(self, name):
        return self.d.get(name)

    def einstellung_setzen(self, name, wert):
        self.d[name] = wert


ok(all(not ap.pruefen(w)[1] for w in ap.PROFILE.values()), "V10 alle festen Profile gültig")
gut, weg = ap.pruefen({"ansicht3d_material": "Gold", "nav_nachlauf": 5, "xyz": 1, "ansicht3d_licht": "Studio"})
ok(gut == {"ansicht3d_licht": "Studio"} and len(weg) == 3, f"V10 Ungültiges verworfen ({weg})")
db10 = DbTest()
vis_alt = vis.aktuell()
ger = ap.anwenden(db10, ap.PROFILE["Präsentation (Kunde)"])
ok(set(ger) >= {"ansicht3d_material", "ansicht3d_licht"} and vis.aktuell()["ansicht3d_material"] == "Edelstahl",
   "V10 Profil anwenden: gespeichert und sofort im Aussehen")
ap.speichern(db10, "Mein Bild")
ok("Mein Bild" in ap.alle(db10) and ap.eigene(db10)["Mein Bild"]["ansicht3d_material"] == "Edelstahl",
   "V10 eigenes Profil gespeichert")
try:
    ap.speichern(db10, ap.STANDARD)
    ok(False, "V10 feste Profile geschützt")
except ap.ProfilFehler:
    ok(True, "V10 feste Profile geschützt")
ok(ap.EIGENE not in teilen.EINSTELLUNGEN_GETEILT and all(n in teilen.LOKAL for n in ap.NAMEN),
   "V10 3D-Einstellungen und eigene Profile nur dieser Arbeitsplatz (nie abgeglichen)")
with tempfile.TemporaryDirectory() as tmp:
    pfad = os.path.join(tmp, "3d.json")
    ap.exportieren(db10, pfad)
    db11 = DbTest()
    ger, weg = ap.importieren(db11, pfad)
    ok(ap.werte(db11) == ap.werte(db10) and "Mein Bild" in ap.eigene(db11) and not weg,
       "V10 Export/Import: gleiche Werte und eigene Profile")
    fremd = os.path.join(tmp, "f.json")
    with open(fremd, "w", encoding="utf-8") as f:
        json.dump({"art": "anderes"}, f)
    try:
        ap.importieren(db11, fremd)
        ok(False, "V10 fremde Datei abgewiesen")
    except ap.ProfilFehler:
        ok(True, "V10 fremde Datei abgewiesen")
ok(ap.loeschen(db10, "Mein Bild") and "Mein Bild" not in ap.eigene(db10), "V10 eigenes Profil gelöscht")
vis.setzen(vis_alt)
erg = ap.selbsttest(320, 200)
ok(erg and all(g for _, g, _ in erg), f"V10 Selbsttest: {sum(1 for e in erg if e[1])}/{len(erg)} in Ordnung "
   f"{[e for e in erg if not e[1]]}")
fq = Path(ansicht3d.__file__).with_name("fenster.py").read_text(encoding="utf-8")
ok("_profil_zeile" in fq and "selbsttest_3d" in fq and "einst_3d_importieren" in fq,
   "V10 Profil, Export/Import und Selbsttest auf der Einstellungsseite 3D-Ansicht")

print("\n" + (f"{len(fehler)} Fehler." if fehler else "Alle Prüfungen bestanden."))
sys.exit(1 if fehler else 0)
