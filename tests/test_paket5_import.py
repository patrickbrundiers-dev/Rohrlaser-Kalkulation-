"""CAD-Entwicklungsplan Paket 5 (Patrick 12.11.2026, „Alle, Reihenfolge 5, 6, K, 7“):
1. Übersicht vor dem Messen: step_vorschau zählt aus dem STEP-Text Baugruppen, Bauteile, Einbauten, gleiche Teile,
   Körper, Flächen, vermutete Zukaufteile, Einheit und schätzt die Messzeit.
2. Gewindeeinsätze (Nietmutter, Einpressmutter, Helicoil …) als eigene Zukauf-Kategorie.
3. Außenwände von Hand: im Prüfdialog gewählte Flächen eines Körpers als Außenwand des Rohrs festlegen, alles außerhalb
   (angeschweißtes Rohr, Lasche) wird ein eigenes Teil; beide neu gemessen, Lage wie in der STEP.

Aufruf: python tests/test_paket5_import.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen  # noqa: E402
from formen_baukasten import ohne, plus, quader, schreibe, zyl  # noqa: E402
from rohrlaser import step, step_vorschau, zukaufteile  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ 1. Übersicht
TEXT = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=PRODUCT('BG','Rahmen \\X2\\00FC\\X0\\ber','',(#90));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('design','',#2,#91);
#11=PRODUCT('UB','Halter','',(#90));
#12=PRODUCT_DEFINITION_FORMATION('','',#11);
#13=PRODUCT_DEFINITION('design','',#12,#91);
#21=PRODUCT('R1','Rohr 40x40x3','',(#90));
#22=PRODUCT_DEFINITION_FORMATION('','',#21);
#23=PRODUCT_DEFINITION('design','',#22,#91);
#31=PRODUCT('S1','Sechskantschraube ISO 4017 M8x20','',(#90));
#32=PRODUCT_DEFINITION_FORMATION('','',#31);
#33=PRODUCT_DEFINITION('design','',#32,#91);
#41=PRODUCT('N1','Blindnietmutter M6','',(#90));
#42=PRODUCT_DEFINITION_FORMATION('','',#41);
#43=PRODUCT_DEFINITION('design','',#42,#91);
#51=NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','','',#3,#13,$);
#52=NEXT_ASSEMBLY_USAGE_OCCURRENCE('2','','',#3,#13,$);
#53=NEXT_ASSEMBLY_USAGE_OCCURRENCE('3','','',#3,#23,$);
#54=NEXT_ASSEMBLY_USAGE_OCCURRENCE('4','','',#13,#33,$);
#55=NEXT_ASSEMBLY_USAGE_OCCURRENCE('5','','',#13,#43,$);
#60=MANIFOLD_SOLID_BREP('',#70);
#61=MANIFOLD_SOLID_BREP('',#70);
#62=MANIFOLD_SOLID_BREP('',#70);
#63=ADVANCED_FACE('',(#70),#70,.T.);
#64=ADVANCED_FACE('',(#70),#70,.T.);
#80=( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );
ENDSEC;
END-ISO-10303-21;
"""
p = TMP / "rahmen.stp"
p.write_text(TEXT, encoding="latin-1")
d = step_vorschau.datei(p)
assert "fehler" not in d, d
assert (d["baugruppen"], d["bauteile"], d["einbauten"], d["gleiche"]) == (2, 3, 5, 2), d
assert (d["koerper"], d["flaechen"], d["einheit"]) == (3, 2, "mm"), d
assert d["zukauf"] == {"Schraube": 2, zukaufteile.EINSATZ: 2}, d["zukauf"]
assert d["schema"].startswith("AUTOMOTIVE_DESIGN")
ok("Übersicht: 2 Baugruppen, 3 Bauteile, 5 Einbauten (Halter zweimal), 2 Schrauben + 2 Gewindeeinsätze, Einheit mm")

m = TMP / "meter.step"
m.write_text(TEXT.replace("SI_UNIT(.MILLI.,.METRE.)", "SI_UNIT($,.METRE.)"), encoding="latin-1")
kaputt = TMP / "kaputt.step"
kaputt.write_text("kein STEP", encoding="latin-1")
u = step_vorschau.zusammen([p, m, kaputt])
assert u["einbauten"] == 10 and u["einheiten"] == ["m", "mm"] and len(u["fehler"]) == 1, u
z = step_vorschau.zeilen(u)
assert any("nicht in mm" in t for t in z) and any(t.startswith("Nicht lesbar: kaputt.step") for t in z), z
assert any(t.startswith("Geschätzte Messzeit:") for t in z) and step_vorschau.zeigen_noetig(u)
klein = step_vorschau.zusammen([p])
assert not step_vorschau.zeigen_noetig(klein), klein
assert step_vorschau.dauer_text(5) == "unter 10 s" and step_vorschau.dauer_text(44) == "etwa 40 s" \
    and step_vorschau.dauer_text(200) == "etwa 3 min"
ok("Mehrere Dateien: Summen, Datei in Metern und nicht lesbare Datei gemeldet; kleine Datei ohne Übersicht")

# ------------------------------------------------------------------ 2. Gewindeeinsätze
for name, kat in (("Nietmutter M8", zukaufteile.EINSATZ), ("Einpressmutter M5", zukaufteile.EINSATZ),
                  ("HELICOIL M10", zukaufteile.EINSATZ), ("Rivet nut M6", zukaufteile.EINSATZ),
                  ("Blindniet 4x10", zukaufteile.NIET), ("Sechskantmutter M8", zukaufteile.MUTTER)):
    assert zukaufteile.begriff(name)[0] == kat, (name, zukaufteile.begriff(name))
assert zukaufteile.EINSATZ in zukaufteile.KATEGORIEN
ok("Gewindeeinsätze: Nietmutter, Einpressmutter, Helicoil, Rivet nut erkannt; Blindniet und Mutter bleiben")

# ------------------------------------------------------------------ 3. Außenwände von Hand
haupt = ohne(quader(300, 40, 40), quader(302, 34, 34, -1, 3, 3))
ast = ohne(quader(30, 30, 160, 135, 5, 40), quader(24, 24, 162, 138, 8, 39))
schreibe({"T_Rohr": plus(haupt, ast)}, TMP)
rund = ohne(zyl(20, 300, 20, 0, 200, (1, 0, 0)), zyl(17, 302, 20, -1, 200, (1, 0, 0)))
abzweig = ohne(zyl(10, 150, 38, 150, 200), zyl(8, 170, 30, 150, 200))
schreibe({"T_Rund": plus(rund, abzweig)}, TMP)


def messen(pfad):
    aus = TMP / (pfad.stem + ".txt")
    step_messen.main(["--ausgabe", str(aus), str(pfad)])
    mw = step.lies_messwerte(aus)
    for w in mw:
        w["_pfad"] = str(pfad)
    return mw


def aufteilen_messen(m, punkte=None):
    """Wie AngebotFenster._aufteilen_messen, nur ohne STEP-Import.exe."""
    t = Path(tempfile.mkdtemp())
    argv = ["--ausgabe", str(t / "a.txt"), "--netze", str(t / "netze"), "--aufteilen", str(int(float(m["koerper"]))),
            m["_pfad"]]
    if punkte:
        argv += ["--aufteilen-an", ";".join(",".join(str(x) for x in pp) for pp in punkte)]
    step_messen.main(argv)
    return step.aufteilen_ergebnis(m, t / "a.txt", t / "netze")


WAENDE = [(60, 0, 20), (60, 40, 20), (60, 20, 0), (60, 20, 40)]
mw = messen(TMP / "T_Rohr.step")
assert len(mw) == 1, mw
teile = aufteilen_messen(dict(mw[0]), WAENDE)
assert teile and len(teile) == 2, teile
an, rohr = teile
assert rohr["profilform"] == "Quadratrohr" and round(float(rohr["abm_a"])) == 40 and round(float(rohr["laenge"])) == 300, \
    (rohr["profilform"], rohr["abm_a"], rohr["laenge"])
assert an["profilform"] == "Quadratrohr" and round(float(an["abm_a"])) == 30 and round(float(an["laenge"])) == 160, \
    (an["profilform"], an["abm_a"], an["laenge"])
assert all(t.get("_netz") for t in teile)
ok("Vierkantrohr 40 mit angeschweißtem Rohr 30: vier Wände gewählt -> Rohr 40 × 300 und Anbauteil 30 × 160")

mr = messen(TMP / "T_Rund.step")
teile = aufteilen_messen(dict(mr[0]), [(50, 220, 20)])
assert teile and len(teile) == 2, teile
assert teile[-1]["profilform"] == "Rundrohr" and round(float(teile[-1]["abm_a"])) == 40, teile[-1]["profilform"]
assert teile[0]["profilform"] == "Rundrohr" and round(float(teile[0]["abm_a"])) == 20, teile[0]["profilform"]
ok("Rundrohr Ø40 mit Abzweig Ø20: Mantel gewählt -> Rohr Ø40 und Anbauteil Ø20 (exakter Radius, kein Rest)")

falsch = dict(mw[0])
assert aufteilen_messen(falsch, [(500, 500, 500)]) is None and "Fläche" in falsch.get("_aufteilen_fehler", ""), falsch
ok("Punkt neben dem Körper: nichts getrennt, Grund „" + falsch["_aufteilen_fehler"] + "“")

# ------------------------------------------------------------------ Prüfdialog
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "a.db")
k = db.kontext()
werte = [dict(mw[0])]
dlg = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[], aufteilen=aufteilen_messen)
assert dlg.wand_knopf.isHidden() and dlg.gewaehlte_waende() == (None, [])
assert dlg.an_waenden_trennen(0, [(500, 500, 500)]) == 0 and len(werte) == 1
assert "nicht getrennt" in dlg.aufteil_info.text(), dlg.aufteil_info.text()
assert dlg.an_waenden_trennen(0, WAENDE) == 2 and len(werte) == 2, werte
assert "an den Außenwänden getrennt" in dlg.aufteil_info.text(), dlg.aufteil_info.text()
assert round(float(werte[0]["abm_a"])) == 40 and round(float(werte[1]["abm_a"])) == 30
assert "T_Rohr.step" in dlg.mehrteilig
dlg.werte_schreiben()
ok("Prüfdialog: falsche Fläche mit Grund abgelehnt; vier Wände -> Rohr bleibt an Platz 1, Anbauteil dazu, Datei = Baugruppe")
db.con.close()
print("Paket 5 Import: alle Tests bestanden.")
