"""DXF-Import robust für verschiedene Zeichnungen (Plan 3D-Editor 3E-15, Patrick 25.10.2026 „Alle a“): Patricks
Zeichnung (rohr_gehrung_QR40_patrick.dxf) wird im Test umgebaut und muss dasselbe Rohr ergeben.
- V1 um 90° gedreht (Rohr senkrecht, Ende A oben): erkannt mit Drehung 90
- V2 USA (Drittwinkel): Draufsicht über der Vorderansicht und Text THIRD ANGLE PROJECTION; ohne Text gilt das deutsche
  Schriftfeld (DIN), mit Vorgabe Projektion 3 wieder richtig
- V3 Blattrahmen und Schriftfeldrahmen: fallen weg, Ansichten bleiben
- V4 zwei Teile auf einem Blatt: das längste mit Hinweis (unsicher), das andere über die Vorgabe Teil
- V5 ohne Projektionsangabe (englisches Schriftfeld): unsicher; Zuordnungsfenster mit Projektion USA rechnet richtig,
  das Programm merkt sich die Projektion je Zeichnungsstil und fragt beim nächsten Mal nicht
- V6 Zuordnungsfenster: Rolle je Ansicht von Hand; Rohr-Editor und Angebot „Aus DXF“ zeigen das Fenster nur bei
  Unsicherheit, Abbrechen übernimmt nichts
- V7 Profiltext mit Ø, Projektionsmethode aus Text, Fingerabdruck

Aufruf: python tests/test_dxf_varianten.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import dxf_import as di, dxf_rohr as dr, dxf_rohr_dialog as drd  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


PATRICK = HIER / "dxf" / "rohr_gehrung_QR40_patrick.dxf"
TEST = HIER / "dxf" / "rohr_ansichten_QR40.dxf"
tmp = Path(tempfile.mkdtemp())


# ------------------------------------------------------------------ DXF umbauen
def paare(text):
    z = text.splitlines()
    return [[z[i].strip(), z[i + 1]] for i in range(0, len(z) - 1, 2)]


def text_aus(p):
    return "\n".join(f"{c}\n{v}" for c, v in p) + "\n"


def _grenzen(p):
    i = next(k for k in range(len(p)) if p[k][1].strip() == "ENTITIES")
    return i, next(k for k in range(i, len(p)) if p[k][0] == "0" and p[k][1].strip() == "ENDSEC")


def umbauen(text, punkt, winkel=None, wahl=None):
    """Elemente im Abschnitt ENTITIES ändern: punkt(x, y) -> (x, y) für alle Punkte, winkel(w) für Textwinkel;
    wahl(x, y) entscheidet je Element am ersten Punkt (VERTEX gehören zur POLYLINE), ob es geändert wird."""
    p = paare(text)
    i, j = _grenzen(p)
    gruppen, akt = [], None
    for c, v in p[i + 1:j]:
        if c == "0" and (v.strip() not in ("VERTEX", "SEQEND") or akt is None):
            akt = []
            gruppen.append(akt)
        akt.append([c, v])
    for g in gruppen:
        ab = next((k for k, (c, v) in enumerate(g) if c == "0" and v.strip() == "VERTEX"), 0)
        erst = next(((float(v), float(g[k + 1][1])) for k, (c, v) in enumerate(g) if c == "10" and k > ab), None)
        if not erst or (wahl and not wahl(*erst)):
            continue
        art = g[0][1].strip()
        for k, (c, v) in enumerate(g):
            if c in [str(n) for n in range(10, 19)] and k + 1 < len(g) and g[k + 1][0] == str(int(c) + 10):
                x, y = punkt(float(v), float(g[k + 1][1]))
                g[k][1], g[k + 1][1] = repr(x), repr(y)
            elif c == "50" and art in ("TEXT", "MTEXT") and winkel:
                g[k][1] = repr(winkel(float(v)))
    return text_aus(p[:i + 1] + [x for g in gruppen for x in g] + p[j:])


def zusatz(text, *elemente):
    p = paare(text)
    _i, j = _grenzen(p)
    return text_aus(p[:j] + [[c, str(v)] for e in elemente for c, v in e] + p[j:])


def entitaeten(text):
    p = paare(text)
    i, j = _grenzen(p)
    return p[i + 1:j]


def texte_ersetzen(text, tabelle):
    return text_aus([[c, tabelle.get(v.strip(), v) if c == "1" else v] for c, v in paare(text)])


def rechteck(x0, y0, x1, y1):
    return [("0", "LWPOLYLINE"), ("8", "0"), ("90", "4"), ("70", "1"), ("10", x0), ("20", y0), ("10", x1), ("20", y0),
            ("10", x1), ("20", y1), ("10", x0), ("20", y1)]


def kern(e):
    """Was das Rohr ausmacht: Profil, Länge, Enden, Konturen."""
    assert e["ok"], e["warnungen"]
    return (e["profil"], e["laenge"], e["eingaben"]["a"], e["eingaben"]["b"],
            sorted((z["art"], z.get("x"), z.get("seite"), z.get("d"), z.get("b"), z.get("wand"))
                   for z in e["eingaben"]["konturen"]))


ORIGINAL = di.datei_lesen(PATRICK)
erg0 = dr.erkennen(ORIGINAL, PATRICK.name)
K0 = kern(erg0)
assert erg0["drehung"] == 0 and not erg0["unsicher"] and erg0["projektion"] == 1

# ------------------------------------------------------------------ V1 gedreht
gedreht = umbauen(ORIGINAL, lambda x, y: (y, -x), lambda w: w - 90)
e1 = dr.erkennen(gedreht, PATRICK.name)
assert kern(e1) == K0 and e1["drehung"] == 90 and not e1["unsicher"], e1["hinweise"]
assert "um 90° gedreht" in e1["hinweise"][0]
ok("V1 Zeichnung um 90° gedreht (Rohr senkrecht): dasselbe Rohr, Ende A oben")

# ------------------------------------------------------------------ V2 USA
b1, b2 = erg0["ansichten"][1]["bb"], erg0["ansichten"][2]["bb"]       # Vorderansicht oben, Draufsicht unten
assert erg0["ansichten"][1]["rolle"] == "Vorderansicht" and b1[1] > b2[3]
dy = b1[1] - b2[1]


def in_bb(b, x, y):
    return b[0] - 0.5 <= x <= b[2] + 0.5 and b[1] - 0.5 <= y <= b[3] + 0.5


getauscht = umbauen(ORIGINAL, lambda x, y: (x, y - dy if y > (b1[1] + b2[3]) / 2 else y + dy),
                    wahl=lambda x, y: in_bb(b1, x, y) or in_bb(b2, x, y))
usa = zusatz(getauscht, [("0", "TEXT"), ("8", "0"), ("10", 300), ("20", 120), ("40", 2.5),
                         ("1", "THIRD ANGLE PROJECTION")])
e2 = dr.erkennen(usa, PATRICK.name)
assert kern(e2) == K0 and e2["projektion"] == 3 and not e2["unsicher"]
assert e2["hinweise"][0].startswith("Ansichten Projektionsmethode 3"), e2["hinweise"]
rollen = {a["nr"]: a["rolle"] for a in e2["ansichten"]}
assert rollen[1] == "Draufsicht" and rollen[2] == "Vorderansicht", rollen
assert kern(dr.erkennen(getauscht, PATRICK.name)) != K0              # deutsches Schriftfeld: DIN angenommen
assert kern(dr.erkennen(getauscht, PATRICK.name, vorgaben=dict(projektion=3))) == K0
ok("V2 USA (Drittwinkel): Draufsicht über der Vorderansicht, aus dem Text erkannt bzw. als Vorgabe")

# ------------------------------------------------------------------ V3 Rahmen
gerahmt = zusatz(ORIGINAL, rechteck(5, 5, 415, 292), rechteck(10, 10, 410, 287), rechteck(290, 10, 410, 60))
e3 = dr.erkennen(gerahmt, PATRICK.name)
assert kern(e3) == K0 and len(e3["ansichten"]) == len(erg0["ansichten"]) and not e3["unsicher"]
ok("V3 Blattrahmen und Schriftfeldrahmen fallen weg, dasselbe Rohr")

# ------------------------------------------------------------------ V4 zwei Teile
zwei = zusatz(ORIGINAL, entitaeten(umbauen(di.datei_lesen(TEST), lambda x, y: (x, y - 300))))
e4 = dr.erkennen(zwei, "zwei.dxf")
assert e4["teile"] == 2 and kern(e4) == K0 and any("2 Teile auf dem Blatt" in u for u in e4["unsicher"]), e4
e4b = dr.erkennen(zwei, "zwei.dxf", vorgaben=dict(teil=1, teil_gewaehlt=True))
assert e4b["ok"] and e4b["laenge"] == 150 and not e4b["unsicher"]
assert [z["x"] for z in e4b["eingaben"]["konturen"]] == [18.6, 46.8, 79.2, 120.6]
ok("V4 zwei Teile auf einem Blatt: das längste mit Hinweis, das andere über die Vorgabe Teil")

# ------------------------------------------------------------------ V5 ohne Projektionsangabe, Zuordnungsfenster
ENGLISCH = {"Werkstoff": "Material", "Massstab": "Scale", "Benennung": "Title", "Gezeichnet": "Drawn",
            "Zeichnungsnummer": "Drawing No.", "Datum": "Date", "Blatt": "Sheet"}
englisch = texte_ersetzen(getauscht, ENGLISCH)
e5 = dr.erkennen(englisch, "usa.dxf")
assert e5["ok"] and any("Projektionsmethode nicht in der Zeichnung" in u for u in e5["unsicher"]), e5["unsicher"]
assert kern(e5) != K0 and e5["werkstoff_text"] == "Stahl S235JR"
pfad = tmp / "usa.dxf"
pfad.write_text(englisch, encoding="utf-8")
db = Datenbank(tmp / "rohrlaser.db")
gezeigt = []


def usa_waehlen(d):
    gezeigt.append(d)
    assert "Projektionsmethode" in d.grund.text() and d.tabelle.rowCount() == len(e5["ansichten"])
    d.projektion.setCurrentIndex(2)                 # USA
    d.neu_erkennen()
    assert d.erg["projektion"] == 3 and not d.erg["unsicher"]
    d.accept()
    return d.result()


e5b = drd.rohr_erkennen(None, db, pfad, dialog=usa_waehlen)
assert len(gezeigt) == 1 and kern(e5b) == K0
assert db.einstellung(drd.EINSTELLUNG) == {dr.fingerabdruck(englisch): 3}
e5c = drd.rohr_erkennen(None, db, pfad, dialog=lambda d: 1 / 0)          # gemerkt: kein Fenster
assert kern(e5c) == K0 and e5c["projektion"] == 3
ok("V5 ohne Projektionsangabe: Zuordnungsfenster, USA gewählt = richtig; gemerkt je Zeichnungsstil, keine Rückfrage")

# ------------------------------------------------------------------ V6 Rollen von Hand, Oberfläche
db2 = Datenbank(tmp / "zwei.db")
d = drd.DxfZuordnungDialog(None, englisch, "usa.dxf", e5, {})
d.rolle_setzen(1, "oben")
d.rolle_setzen(2, "vorne")
d.accept()
assert d.result() == QDialog.Accepted and kern(d.erg) == K0 and d.vorgaben["rollen"] == {1: "oben", 2: "vorne"}
assert "von Hand zugeordnet" in d.erg["hinweise"][0]
d.vorschau.resize(500, 350)
d.vorschau.grab()                                   # zeichnet ohne Fehler
assert drd.rohr_erkennen(None, db2, pfad, dialog=lambda d: QDialog.Rejected)["abgebrochen"]
assert drd.rohr_erkennen(None, db2, PATRICK, dialog=lambda d: 1 / 0)["ok"]         # sicher: kein Fenster
from rohrlaser.fenster import Hauptfenster  # noqa: E402

a = db2.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db2, stumm=True)
s = fenster.angebot_oeffnen(a)
vorher = len(db2.positionen(a))
assert s.blech_aus_dxf([str(pfad)], dialog=lambda d: 1 / 0, rohr_dialog=lambda d: 1 / 0,
                       zuordnung=lambda d: QDialog.Rejected) == 0 and len(db2.positionen(a)) == vorher
gesehen = {}


def rohr_ok(d):
    gesehen.update(laenge=d.k_laenge.value(), profil=d.k_profil.currentText())
    return QDialog.Accepted


assert s.blech_aus_dxf([str(pfad)], dialog=lambda d: 1 / 0, rohr_dialog=rohr_ok, zuordnung=usa_waehlen) == 1
assert gesehen == dict(laenge=1018.8, profil="QR 40x40x3"), gesehen
pos = db2.positionen(a)[-1]
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

sd = SchneidwegDialog(s, dict(pos, technik=None), s.k.profile["QR 40x40x3"], s.kopf, s.k, s.tabellen, db2, [])
db2.einstellung_setzen(drd.EINSTELLUNG, {})
assert not sd.dxf_importieren(str(pfad), zuordnung=lambda d: QDialog.Rejected)
assert sd.dxf_importieren(str(pfad), zuordnung=usa_waehlen) and sd.eingaben()["a"]["winkel"] == 20
for w in (d, sd, s, fenster):
    w.close()
ok("V6 Rollen von Hand; Angebot „Aus DXF“ und Rohr-Editor fragen nur bei Unsicherheit, Abbrechen übernimmt nichts")

# ------------------------------------------------------------------ V7 Hilfsfunktionen
assert dr.profil_aus_text(["Ø42,4x2"]) == dict(form="Rundrohr", a=42.4, b=42.4, wand=2)
assert dr.projektion(["ISO-E"])[0] == 1 and dr.projektion(["Third angle projection"])[0] == 3
assert dr.projektion(["Benennung", "Werkstoff"])[0] == 1 and dr.projektion(["Title"]) == (None, None)
assert dr.fingerabdruck(ORIGINAL) == dr.fingerabdruck(gedreht) and dr.fingerabdruck("kein dxf") == ""
ok("V7 Profiltext mit Ø, Projektionsmethode aus dem Text, Fingerabdruck des Zeichnungsstils")
print("Alle Tests DXF-Varianten bestanden.")
