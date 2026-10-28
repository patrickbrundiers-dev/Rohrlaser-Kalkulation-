"""Prüft die Erreichbarkeit der Nähte aus STEP (Plan Schweißbaugruppen 28.10.2026, Schritt 4 = V3):
- E1 Messung: Rohr auf Platte = gut, Naht unter einer Haube = nicht erreichbar, Wände halb innen = schlecht;
  Felder zugang, erreichbar, seiten (STEP-JSON 1.21)
- E2 Vorschläge: Stufen getrennt, Nahtgruppe mit zugang_step und seiten, Warnung „nicht erreichbar“ im Status
- E3 Wendevorgänge aus den Lagen je Nahtpunkt (kleinste Zahl Lagen − 1)
- E4 Vorkalkulation: Zugänglichkeit und Wenden gelb vorgeschlagen, von Hand bleibt, ohne Faktorzeile ein Hinweis
- E5 Editor: Spalte Zugänglichkeit und Wendevorgänge gelb, nicht erreichbare Naht orange im 3D

Aufruf: python tests/test_bg_erreichbar.py
"""
import contextlib
import io
import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(HIER), str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ E1 Messung
if find_spec("OCP") is None:
    print("OCP fehlt: E1 übersprungen")
else:
    import step_ergebnis
    import step_geometrie as sg
    from erzeuge_testteile import baugruppe as zusammen, kastenrohr, schreibe
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    tmp = Path(tempfile.mkdtemp())

    def box(x, y, z, dx, dy, dz):
        return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()

    def messen(name, *koerper):
        with contextlib.redirect_stdout(io.StringIO()):
            schreibe(zusammen(*koerper), name, tmp)
        return {tuple(sorted(n["teile"])): n for n in sg.analysiere_datei(tmp / f"{name}.step")[0].naehte}

    assert step_ergebnis.SCHEMA_VERSION == "1.21"
    t = messen("rohr_platte", box(-150, -150, -10, 300, 300, 10), kastenrohr(60, 40, 3, 500, 4))
    n = t[(1, 2)]
    assert n["zugang"] == "gut" and n["erreichbar"] == 1.0, n
    assert len(n["seiten"]) == sg.ERREICH_PUNKTE and all("+Z" in s for s in n["seiten"]), n["seiten"]
    # Haube: Platte, Klotz 40×40×5, darüber ein Deckel auf vier Wänden: Naht Platte–Klotz ganz eingeschlossen
    t = messen("haube", box(-150, -150, -10, 300, 300, 10), box(-20, -20, 0, 40, 40, 5), box(-60, -60, 5, 120, 120, 5),
               box(-60, -60, 0, 120, 5, 5), box(-60, 55, 0, 120, 5, 5), box(-60, -55, 0, 5, 110, 5),
               box(55, -55, 0, 5, 110, 5))
    assert t[(1, 2)]["zugang"] == "nicht erreichbar" and t[(1, 2)]["erreichbar"] == 0 and t[(1, 2)]["seiten"] == []
    assert t[(1, 4)]["zugang"] == "schlecht" and 0 < t[(1, 4)]["erreichbar"] < 1, t[(1, 4)]
    ok("E1 Rohr auf Platte gut (+Z an jedem Punkt), Naht unter der Haube nicht erreichbar, Wand halb innen schlecht")

# ------------------------------------------------------------------ E2 Vorschläge
bg = baugruppe.leer()
kand = [dict(teile=[1, 2], laenge_mm=100, stossart="Kehlnaht", dicke_mm=3, zugang="gut", erreichbar=1.0,
             seiten=[["+Z", "+X"], ["+Z"]]),
        dict(teile=[1, 3], laenge_mm=100, stossart="Kehlnaht", dicke_mm=3, zugang="gut", erreichbar=1.0,
             seiten=[["+Z"]]),
        dict(teile=[1, 4], laenge_mm=100, stossart="Kehlnaht", dicke_mm=3, zugang="nicht erreichbar", erreichbar=0,
             seiten=[]),
        dict(teile=[1, 5], laenge_mm=100, stossart="Kehlnaht", dicke_mm=3)]               # alte Messung (1.20)
v = {x.get("zugang"): x for x in baugruppe.vorschlaege_aus_step(bg, kand)}
assert set(v) == {"gut", "nicht erreichbar", None} and v["gut"]["anzahl"] == 2
assert v["gut"]["seiten"] == [["+Z", "+X"], ["+Z"], ["+Z"]] and "seiten" not in v[None]
n = baugruppe.vorschlag_naht(v["gut"])
assert n["zugang_step"] == "gut" and n["seiten"] == v["gut"]["seiten"] and "zugang" not in n
assert "zugang_step" not in baugruppe.vorschlag_naht(v[None])
bg["vorschlaege"] = list(v.values())
assert "nicht erreichbar" in baugruppe.nicht_erreichbar(bg)
bg["vorschlaege"] = [v["gut"]]
assert baugruppe.nicht_erreichbar(bg) is None
ok("E2 Vorschläge je Stufe, Nahtgruppe mit zugang_step/seiten, alte Messung ohne; Warnung nur bei nicht erreichbar")

# ------------------------------------------------------------------ E3 Wenden
for seiten, soll in (([["+Z", "+X"], ["+Z"]], 0), ([["+Z"], ["-Z"]], 1), ([["+Z", "-Y"], ["-Z", "-Y"], ["+X"]], 1),
                     ([["+Z"], ["-Z"], ["+X"]], 2), ([], None)):
    g = baugruppe.leer()
    g["naehte"] = [dict(id="n1", seiten=seiten)] if seiten else [dict(id="n1")]
    assert baugruppe.wenden_aus_step(g)[0] == soll, (seiten, baugruppe.wenden_aus_step(g))
assert "(+X, -Y oben)" in baugruppe.wenden_aus_step(dict(naehte=[dict(seiten=[["+Z", "-Y"], ["-Z", "-Y"], ["+X"]])]))[1]
ok("E3 Wendevorgänge: eine Lage für alle = 0, oben und unten = 1, drei Richtungen ohne gemeinsame = 2")

# ------------------------------------------------------------------ E4 Vorkalkulation
TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=0, status="geprüft")],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=2.0, status="geprüft")],
           schweiss_faktoren=[dict(art="Zugänglichkeit", wert=w, faktor=f, status="geprüft")
                              for w, f in (("gut", 1.0), ("eingeschränkt", 1.25), ("schlecht", 1.6))],
           schweiss_regeln=[dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE])


def gruppe(wenden=None):
    g = baugruppe.leer()
    g["stamm"] = dict(gewicht="20")
    g["naehte"] = [dict(id="a", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, dicke=3,
                        zugang_step="eingeschränkt", seiten=[["+Z"], ["+Z", "-Y"]]),
                   dict(id="b", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, dicke=3,
                        zugang_step="nicht erreichbar"),
                   dict(id="c", nr="3", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, dicke=3,
                        zugang_step="gut", seiten=[["-Z"]]),
                   dict(id="d", nr="4", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, dicke=3)]
    if wenden is not None:
        g["wenden"] = wenden
    return dict(pos=1, art=BAUGRUPPE, stueck=2, baugruppe=baugruppe.speichern(g))


p = gruppe()
r = vorkalk.vorkalkulieren(p, [p], TAB)
nt = {x["id"]: x for x in r["bg"]["naehte"]}
assert nt["a"]["zugang"] == "eingeschränkt" and vorkalk.naht_status(nt["a"], "zugang") == vorkalk.VORSCHLAG
assert "STEP: Brenner eingeschränkt" in nt["a"]["vk"]["zugang"]["text"]
assert nt["b"]["zugang"] == "schlecht" and "Konstruktion prüfen" in nt["b"]["vk"]["zugang"]["text"]
assert "zugang" not in nt["d"]
assert r["bg"]["wenden"] == 1 and vorkalk.wenden_status(r["bg"]) == vorkalk.VORSCHLAG
ag = next(a for a in r["bg"]["arbeitsgaenge"] if a["vk"]["art"] == vorkalk.WENDEN)
assert ag["menge"] == 1
assert vorkalk.offen(r["bg"]) >= 4 and vorkalk.bestaetigen(r["bg"]) >= 4 and vorkalk.offen(r["bg"]) == 0
assert vorkalk.wenden_status(r["bg"]) == vorkalk.BESTAETIGT
st = baugruppe.status(dict(p, baugruppe=baugruppe.speichern(r["bg"])), dict(bg_tabellen=TAB, saetze={"Schweißen": 60.0}))
assert "nicht erreichbar" in st, st
# von Hand: Wenden 3 und Zugänglichkeit gut bleiben stehen
p = gruppe(wenden=3)
g = baugruppe.lesen(p["baugruppe"])
g["naehte"][0]["zugang"] = "gut"
p["baugruppe"] = baugruppe.speichern(g)
r = vorkalk.vorkalkulieren(p, [p], TAB)
assert r["bg"]["wenden"] == 3 and vorkalk.wenden_status(r["bg"]) == vorkalk.HAND
assert r["bg"]["naehte"][0]["zugang"] == "gut" and vorkalk.naht_status(r["bg"]["naehte"][0], "zugang") == vorkalk.HAND
# Vorschlag geändert = von Hand, eine neue Vorkalkulation lässt ihn
p = gruppe()
r = vorkalk.vorkalkulieren(p, [p], TAB)
r["bg"]["wenden"] = 2
r2 = vorkalk.vorkalkulieren(dict(p, baugruppe=baugruppe.speichern(r["bg"])), [p], TAB)
assert r2["bg"]["wenden"] == 2 and vorkalk.wenden_status(r2["bg"]) == vorkalk.HAND
# ohne Faktorzeile „eingeschränkt“: kein Vorschlag, ein Hinweis; ohne STEP-Angaben keine Felder
tab2 = dict(TAB, schweiss_faktoren=[z for z in TAB["schweiss_faktoren"] if z["wert"] != "eingeschränkt"])
r = vorkalk.vorkalkulieren(gruppe(), [gruppe()], tab2)
assert "zugang" not in r["bg"]["naehte"][0] and any("eingeschränkt" in h for h in r["hinweise"]), r["hinweise"]
g = baugruppe.leer()
g["naehte"] = [dict(id="x", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, dicke=3)]
q = dict(pos=1, art=BAUGRUPPE, stueck=1, baugruppe=baugruppe.speichern(g))
r = vorkalk.vorkalkulieren(q, [q], TAB)
assert "wenden" not in r["bg"] and "vk" not in r["bg"] and "zugang" not in r["bg"]["naehte"][0]
ok("E4 Zugänglichkeit und Wenden 1 gelb, nicht erreichbar = schlecht mit Hinweis, von Hand bleibt, Faktor fehlt = Hinweis")

# ------------------------------------------------------------------ E5 Editor
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.stil import GELB_FLAECHE  # noqa: E402
eltern = QWidget()
p = dict(gruppe(), id=1)
g = baugruppe.lesen(p["baugruppe"])
g["naehte"][1]["linien"] = [[0, 0, 0, 100, 0, 0]]
g["naehte"][2]["linien"] = [[0, 50, 0, 100, 50, 0]]
p["baugruppe"] = baugruppe.speichern(g)
d = BaugruppeDialog(eltern, p, [p], TAB, {"Schweißen": 60.0})
d.vorkalkulation()
sp = [x.schluessel for x in d.naht_tab.spalten]
f = d.naht_tab.cellWidget(0, sp.index("zugang"))
assert f.currentText() == "eingeschränkt" and GELB_FLAECHE in f.styleSheet()
assert d.wenden.value() == 1 and GELB_FLAECHE in d.wenden.styleSheet() and "STEP" in d.wenden.toolTip()
d.wenden.setValue(2)
assert d.wenden.styleSheet() == "" and vorkalk.wenden_status(d.bg) == vorkalk.HAND
linien = d.naht_linien()
assert linien.get("SX") == [[0, 0, 0, 100, 0, 0]] and linien.get("SN") == [[0, 50, 0, 100, 50, 0]], linien
d.reject()
ok("E5 Editor: Zugänglichkeit und Wendevorgänge gelb, Änderung von Hand, nicht erreichbare Naht orange (SX)")
print("Alle Erreichbarkeits-Tests bestanden.")
