"""Rohrimport: die neun Testfälle des CAD-Entwicklungsplans (Abschnitt 7.2, Paket 2, Patrick 12.11.2026) und die
Ergänzungen des Pakets.

R1 Neun Fälle: Rundrohr, Quadratrohr, Rechteckrohr, U-Profil, Winkelprofil, Rohr mit Bohrungen, mit Gehrung, mit
   Ausschnitt, Datei mit mehreren Profilen. Geprüft: Profilart, Maße, Länge, Wandstärke, Orientierung (das schräg im
   Raum liegende Teil ergibt dasselbe) und Geometriequalität (gültiger Körper, 3D-Gegenprobe: das Editor-Modell liegt
   auf 0,1 mm wie die STEP).
R2 Fase am Rohrende: die Gegenprobe vergleicht die Fase nicht (sie wird nicht gelasert) und nennt das.
R3 Ursache der Abweichung: Körper mit angeschweißtem Teil → „Aufteilen“; Hinweis auf „Wie in der STEP übernehmen“.
R4 Wie in der STEP übernehmen: Position mit gemessenen Werten, ohne Editor-Modell.
R5 Werkstoff aus den Material-Einträgen der STEP: eindeutig = Vorschlag, mehrdeutig/allgemein = nur Hinweis.
R6 Importbericht je Datei.

Aufruf: python tests/test_rohrimport_plan.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

import step_messen  # noqa: E402
import erzeuge_testteile as et  # noqa: E402
from rohrlaser import step, step_material  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def still(f, *a):
    """OpenCascade schreibt beim STEP-Export auf stdout: für die Dauer des Aufrufs stumm."""
    fd, alt = sys.stdout.fileno(), os.dup(sys.stdout.fileno())
    sys.stdout.flush()
    os.dup2(os.open(os.devnull, os.O_WRONLY), fd)
    try:
        return f(*a)
    finally:
        sys.stdout.flush()
        os.dup2(alt, fd)


U = [(0, 0), (60, 0), (60, 30), (56, 30), (56, 4), (4, 4), (4, 30), (0, 30)]
L = [(0, 0), (40, 0), (40, 4), (4, 4), (4, 40), (0, 40)]
ausschnitt = et.cut(et.kastenrohr(60, 60, 3, 500, 6),
                    BRepPrimAPI_MakeBox(gp_Pnt(-10, 20, 200), 20, 20, 60).Shape())
TEILE = {
    "F1_Rundrohr": et.rundrohr(42.4, 2.6, 600),
    "F2_Quadratrohr": et.kastenrohr(40, 40, 3, 500, 6),
    "F3_Rechteckrohr": et.kastenrohr(60, 40, 3, 800, 6),
    "F4_U_Profil": et.profil(U, 500),
    "F5_Winkel": et.profil(L, 800),
    "F6_Bohrungen": et.bohrung_quer(et.bohrung_quer(et.kastenrohr(50, 50, 3, 600, 6), 10, 150), 12, 400, (0, 1, 0)),
    "F7_Gehrung": et.gehrung(et.kastenrohr(40, 40, 3, 500, 6), 450, 45),
    "F8_Ausschnitt": ausschnitt,
    "F9_Mehrere": et.baugruppe(et.rundrohr(30, 2, 300), et.verschiebe(et.kastenrohr(40, 40, 3, 400, 6), 100, 0, 0),
                               et.verschiebe(et.profil(L, 250), 200, 0, 0)),
    "F7_Gehrung_schraeg": et.drehe_beliebig(et.drehe_achse(et.gehrung(et.kastenrohr(40, 40, 3, 500, 6), 450, 45), 0)),
    "F6_Bohrungen_schraeg": et.drehe_beliebig(et.bohrung_quer(et.bohrung_quer(et.kastenrohr(50, 50, 3, 600, 6), 10, 150),
                                                             12, 400, (0, 1, 0))),
    "F10_Fase": et.cut(et.rundrohr(30, 5, 120), et.cut(
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 117), gp_Dir(0, 0, 1)), 20, 3).Shape(),
        BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, 117), gp_Dir(0, 0, 1)), 15, 12, 3).Shape())),
}
for name, form in TEILE.items():
    still(et.schreibe, form, name, TMP)
aus = TMP / "m.txt"
(TMP / "netze").mkdir()
step_messen.main(["--ausgabe", str(aus), "--netze", str(TMP / "netze")] + [str(TMP / f"{n}.step") for n in TEILE])
MW = step.lade_netze(step.lies_messwerte(aus), TMP / "netze")
JE = {}
for m in MW:
    JE.setdefault(Path(m["datei"]).stem, []).append(m)
db = Datenbank(TMP / "r.db")
k = db.kontext()


def z(m, feld):
    return float(m.get(feld) or 0)


def pruefe(name, form, a, b, wand, laenge, i=0, tol=0.15):
    m = JE[name][i]
    assert not m.get("fehler") and m.get("profilform") == form, (name, m.get("profilform"), m.get("fehler"))
    ab = sorted([z(m, "abm_a"), z(m, "abm_b")]) if b else [0.0, z(m, "abm_a")]
    assert abs(ab[1] - max(a, b)) <= tol and (not b or abs(ab[0] - min(a, b)) <= tol), (name, m["abm_a"], m["abm_b"])
    assert abs(z(m, "wandstaerke") - wand) <= tol, (name, m["wandstaerke"])
    assert abs(z(m, "laenge") - laenge) <= 0.5, (name, m["laenge"])
    assert str(m.get("gueltig")) == "1" and m.get("einheit") == "mm", (name, m.get("gueltig"), m.get("einheit"))
    g = step.rohr_gegenprobe(m, k.profile)
    assert g is not None and g[0] and g[2] <= 0.1, (name, g)
    return m


pruefe("F1_Rundrohr", "Rundrohr", 42.4, 0, 2.6, 600)
pruefe("F2_Quadratrohr", "Quadratrohr", 40, 0, 3, 500)
pruefe("F3_Rechteckrohr", "Rechteckrohr", 60, 40, 3, 800)
pruefe("F4_U_Profil", "U-Profil", 60, 30, 4, 500)
pruefe("F5_Winkel", "L-Profil", 40, 40, 4, 800)
ok("R1 Rundrohr, Quadratrohr, Rechteckrohr, U-Profil und Winkel: Profilart, Maße, Wand, Länge, gültiger Körper, "
   "Editor-Modell auf 0,1 mm wie die STEP")
m = pruefe("F6_Bohrungen", "Quadratrohr", 50, 0, 3, 600)
assert int(z(m, "innen_konturen")) == 4 and "10.0:2" in str(m.get("bohrungen")) and "12.0:2" in str(m.get("bohrungen")), \
    (m.get("innen_konturen"), m.get("bohrungen"))
m = pruefe("F7_Gehrung", "Quadratrohr", 40, 0, 3, 470)
enden = step.gehrungen(m)
assert m.get("ende_b_gerade") != "1" and m.get("ende_a_gerade") == "1" and "a_ende" not in enden and \
    abs(json.loads(enden["b_ende"])["winkel"] - 45) < 0.5, (enden, m.get("ende_b_gerade"))
m = pruefe("F8_Ausschnitt", "Quadratrohr", 60, 0, 3, 500)
assert int(z(m, "innen_konturen")) == 1 and abs(z(m, "innen") - 160) <= 1.0, (m.get("innen_konturen"), m.get("innen"))
ok("R1 Rohr mit Bohrungen (4 Konturen, Ø10 und Ø12), mit Gehrung 45° (ein Ende schräg) und mit Ausschnitt "
   "(1 Kontur, 160 mm Schneidweg)")
assert len(JE["F9_Mehrere"]) == 3 and sorted(m["profilform"] for m in JE["F9_Mehrere"]) == \
    ["L-Profil", "Quadratrohr", "Rundrohr"], [m.get("profilform") for m in JE["F9_Mehrere"]]
for i, m in enumerate(JE["F9_Mehrere"]):
    g = step.rohr_gegenprobe(m, k.profile)
    assert g and g[0], (i, g)
ok("R1 Datei mit mehreren Profilen: drei Körper einzeln erkannt (Rundrohr, Quadratrohr, Winkel), jeder geprüft")
for gerade, schraeg in (("F7_Gehrung", "F7_Gehrung_schraeg"), ("F6_Bohrungen", "F6_Bohrungen_schraeg")):
    a, b = JE[gerade][0], JE[schraeg][0]
    assert a["profilform"] == b["profilform"]
    for feld in ("abm_a", "wandstaerke", "laenge", "schneidweg", "innen"):
        assert abs(z(a, feld) - z(b, feld)) <= 0.2, (schraeg, feld, a.get(feld), b.get(feld))
    g = step.rohr_gegenprobe(b, k.profile)
    assert g and g[0] and g[2] <= 0.1, (schraeg, g)
ok("R1 Orientierung: dasselbe Teil schräg im Raum ergibt dieselben Maße, Konturen und Schneidwege")

# ---------------------------------------------------------------- R2 Fase
m = JE["F10_Fase"][0]
assert step.FASE_HINWEIS in str(m.get("hinweise")), m.get("hinweise")
assert step.fase_zonen(m, 120.0), "Fase-Bereich am Ende"
g = step.rohr_gegenprobe(m, k.profile)
assert g and g[0] and "Fase" in g[1] and "nicht verglichen" in g[1], g
ohne = dict(m, hinweise="")
g2 = step.rohr_gegenprobe(ohne, k.profile)
assert g2 and not g2[0], ("ohne den Hinweis der Messung bleibt die Abweichung an der Fase", g2)
ok("R2 Fase am Rohrende: Gegenprobe bestanden, die Fase ist nicht verglichen (wird nicht gelasert); ohne erkannte "
   "Fase bleibt die Abweichung gemeldet")

# ---------------------------------------------------------------- R3 Ursache
assert "Aufteilen" in step.gegenprobe_ursache(dict(profilform="Quadratrohr", hinweise=step.MEHRERE_HINWEIS + "? Rohr"))
assert "Kantteil" in step.gegenprobe_ursache(dict(profilform="U-Profil", hinweise=""))
assert step.gegenprobe_ursache(dict(profilform="Quadratrohr", hinweise="")) == ""
assert "Wie in der STEP übernehmen" in g2[1]
ok("R3 Abweichung mit Ursache: Körper mit angeschweißtem Teil → Aufteilen, offenes Profil → Kantteil prüfen; dazu "
   "der Weg „Wie in der STEP übernehmen“")

# ---------------------------------------------------------------- R4 wie in der STEP
basis = JE["F8_Ausschnitt"][0]
assert step.wie_step_moeglich(basis) and not step.wie_step_moeglich(dict(basis, _normteil="Schraube"))
neu = step.uebernehmen([dict(basis, _uebernehmen=True)], [], k, db.zeilen("gewinde"), None, "S235-10219", 2)
wie = step.uebernehmen([dict(basis, _uebernehmen=True, _wie_step=True)], [], k, db.zeilen("gewinde"), None,
                       "S235-10219", 2)
pn, pw = neu["positionen"][0], wie["positionen"][0]
assert json.loads(pn["technik"])["konturen"] and not pw.get("technik"), (pn.get("technik"), pw.get("technik"))
for feld in ("laenge", "schneidweg", "innen", "a_schnitt", "b_schnitt", "profil_id", "konturen"):
    assert pn.get(feld) == pw.get(feld), (feld, pn.get(feld), pw.get(feld))
assert pw.get("_netz") and any(step.WIE_STEP_HINWEIS in b for b in wie["bericht"]), wie["bericht"]
ok("R4 Wie in der STEP übernehmen: gleiche Länge, Schneidwege und Konturen wie neu aufgebaut, aber ohne "
   "Editor-Modell; die 3D-Daten der STEP bleiben")

# ---------------------------------------------------------------- R5 Werkstoff aus der STEP
KOPF = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
ENDSEC;
DATA;
#1=PRODUCT('P-100','Holm',$,(#90));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('design','',#2,#91);
#4=PRODUCT_DEFINITION_SHAPE('','',#3);
#5=PROPERTY_DEFINITION('material property','material name',#3);
#6=PROPERTY_DEFINITION_REPRESENTATION(#5,#7);
#7=REPRESENTATION('material name',(#8),#92);
#8=DESCRIPTIVE_REPRESENTATION_ITEM('{0}','{0}');
#11=PRODUCT('P-200','Strebe',$,(#90));
#12=PRODUCT_DEFINITION_FORMATION('','',#11);
#13=PRODUCT_DEFINITION('design','',#12,#91);
#15=PROPERTY_DEFINITION('material property','material name',#13);
#16=PROPERTY_DEFINITION_REPRESENTATION(#15,#17);
#17=REPRESENTATION('material name',(#18),#92);
#18=DESCRIPTIVE_REPRESENTATION_ITEM('{1}','{1}');
ENDSEC;
END-ISO-10303-21;
"""
zwei = TMP / "zwei.step"
zwei.write_text(KOPF.format("1.4301 (X5CrNi18-10)", "Steel"), encoding="utf-8")
assert step_material.material_namen(str(zwei)) == {"Holm": "1.4301 (X5CrNi18-10)", "Strebe": "Steel"}
eins = TMP / "eins.step"
eins.write_text(KOPF.format("S235JR", "S235JR"), encoding="utf-8")
assert step_material.material_namen(str(eins)).get("") == "S235JR"
assert step_material.material_namen(str(TMP / "F1_Rundrohr.step")) == {}
v = step_material.vorschlag
assert v("1.4301 (X5CrNi18-10)", k.werkstoffe)[0] == "1.4301" and v("AISI 304", k.werkstoffe)[0] == "1.4301"
assert v("EN AW-6060 T66", k.werkstoffe)[0] == "AW6060-T66"
assert v("S235JR", k.werkstoffe)[0] is None and "mehrere" in v("S235JR", k.werkstoffe)[1]
assert v("S235JR", k.werkstoffe, "S235-10219")[0] == "S235-10219"
assert v("Steel", k.werkstoffe)[0] is None and "allgemeine Angabe" in v("Steel", k.werkstoffe)[1]
assert v("PA6 GF30", k.werkstoffe)[0] is None and "kein passender" in v("PA6 GF30", k.werkstoffe)[1]
mw = [dict(JE["F2_Quadratrohr"][0], bauteil="Holm", _pfad=str(zwei)),
      dict(JE["F1_Rundrohr"][0], bauteil="Strebe:2", _pfad=str(zwei)),
      dict(JE["F3_Rechteckrohr"][0], bauteil="Holm", _pfad=str(zwei), _werkstoff="S355-10219"),
      dict(JE["F4_U_Profil"][0], bauteil="Sonstiges", _pfad=str(zwei))]
assert step_material.anwenden(mw, k.werkstoffe, "S235-10219") == 3
assert mw[0]["_werkstoff"] == "1.4301" and mw[0]["_werkstoff_vorschlag"] == "1.4301"
assert "_werkstoff" not in mw[1] and "allgemeine Angabe" in mw[1]["_werkstoff_text"]
assert mw[2]["_werkstoff"] == "S355-10219", "eigene Wahl bleibt"
assert "_werkstoff_step" not in mw[3]
ok("R5 Werkstoff aus der STEP: 1.4301, AISI 304 und EN AW-6060 werden Vorschlag; S235JR nur mit passender Vorgabe, "
   "„Steel“ und unbekannte Namen bleiben Hinweis; eine eigene Wahl bleibt")

# ---------------------------------------------------------------- R6 Importbericht
alle = [dict(m, _uebernehmen=True) for m in JE["F9_Mehrere"]]
step.rohre_gegenprobe(alle, k.profile)
erg = step.uebernehmen(alle, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
kopf = erg["importbericht"][0]
assert not any(z.startswith("Importbericht") for z in erg["bericht"])      # der Bericht je Teil bleibt, wie er war
assert kopf.startswith("Importbericht F9_Mehrere.step: 3 Körper; 3 Rohre/Profile; übernommen 3, nicht übernommen 0"), kopf
assert "3D-Gegenprobe 3 wie die STEP" in kopf and "alle Körper gültig, Einheit mm" in kopf, kopf
ok("R6 Importbericht je Datei: Körper, Arten, übernommen, Erkennung, 3D-Gegenprobe, Geometrie")
db.con.close()
print("Rohrimport nach Plan: alle Tests bestanden.")
