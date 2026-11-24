"""STEP-Viewer (Master-Auftrag STEP Import Engine 2.0, 24.11.2026): echte Messung von Test-STEPs,
- Messung liefert je 3D-Linie die Konturnummer (netz["lk"]), die Messwerte bleiben dabei gleich
- Konturliste: Summe = Schneidweg der Messung, Gegenprobe über die 3D-Linien (offene Profile halbe Länge,
  Rundrohr-Bohrungen 2D-Schnitt), Kontur im 3D anklickbar (li = "kontur:n")
- Viewer-Fenster: öffnen, Gesamtansicht/Einzelteil, Kontur wählen, Art ändern, Expertenstufe (feineres Netz)

Aufruf: python tests/test_step_viewer.py   (QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step, step_viewer as sv  # noqa: E402
from rohrlaser.step_viewer_fenster import StepViewer  # noqa: E402

app = QApplication.instance() or QApplication([])
ORDNER = HIER.parent / "programm"
BEFEHL = step.messprogramm(ORDNER)
assert BEFEHL, "STEP-Messung fehlt"

# Kopf ohne Messung
k01 = HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step"
kopf = sv.kopf(k01)
assert sv.schema_name("AUTOMOTIVE_DESIGN").startswith("AP214") and sv.schema_name("CONFIG_CONTROL_DESIGN").startswith("AP203")
assert sv.schema_name("AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF").startswith("AP242")
assert any("Format" in z[0] for z in sv.kopf_zeilen(kopf)), sv.kopf_zeilen(kopf)
print("OK: Dateikopf (Format/Schema) ohne Messung")


def gemessen(pfad, stufe=sv.STANDARD):
    mes = sv.messen(BEFEHL, pfad, ["--prozesse", "0"], stufe)
    assert not mes.fehler and mes.messwerte, (pfad, mes.fehler, mes.rc)
    return mes


for datei in ("step_konturen/K01_RE60x40x3_Konturen.step", "step_konturen/K03_RR42-4x2_Konturen.step",
              "step_konturen/K10_T60x60x5x7_Lage.step", "step_regression/R06_RE40x30x3_L920_Langloecher.step"):
    mes = gemessen(HIER / datei)
    m, netz = mes.messwerte[0], mes.netz(0)
    assert netz and "lk" in netz, (datei, list((netz or {}).keys()))
    for art, nummern in netz["lk"].items():
        assert len(nummern) == len(netz["l"][art]), (datei, art)              # je Linienzug eine Nummer
    zeilen = sv.konturen(m, netz)
    s = sv.summen(m, zeilen)
    sw = float(m.get("schneidweg") or 0)
    assert zeilen and s["gleich"] and abs(s["schneidweg"] - sw) < 1e-6, (datei, s, sw)
    assert s["gegenprobe_ok"] == s["gegenprobe_n"] and s["gegenprobe_n"] > 0, (datei, s,
                                                                                [z.get("gegenprobe") for z in zeilen])
    li = sv.mit_konturkennung(netz)["li"]
    assert any(x and x.startswith(sv.KONTUR) for v in li.values() for x in v), (datei, li)
    print(f"OK: {Path(datei).name}: {len(zeilen)} Konturen, Summe = Schneidweg {sw:.1f} mm, Gegenprobe "
          f"{s['gegenprobe_ok']}/{s['gegenprobe_n']}")
    mes.aufraeumen()

# Blech: Konturen aus der Blechmessung (Außenkontur + Innenkonturen), Summe = Schneidweg
mes = gemessen(HIER / "step_bleche" / "B02_Blech_400x200x4_Bohrungen.step")
m = mes.messwerte[0]
zeilen = sv.konturen(m, mes.netz(0))
s = sv.summen(m, zeilen)
assert s["gleich"] and [z["art"] for z in zeilen][0] == "Außenkontur" and len(zeilen) == 6, (s, zeilen)
print(f"OK: Blech B02: Außenkontur + {len(zeilen) - 1} Innenkonturen = Schneidweg {s['schneidweg']:.1f} mm")
mes.aufraeumen()
# Ende mit Innensteg: Schnitt durch den Steg zählt (ende_a), Gegenprobe gegen die Außenlinie
m = dict(schneidweg="359.4", ende_a="179.7", ende_b="179.7", konturen_liste=json.dumps(
    [dict(art="Ende A", durchgehend=True, form="gerade", schnittlaenge=162.0),
     dict(art="Ende B", durchgehend=True, form="gerade", schnittlaenge=162.0)]))
zeilen = sv.konturen(m)
assert sv.summen(m, zeilen)["gleich"] and "Innensteg" in zeilen[0]["hinweis"], zeilen
print("OK: Ende mit Innensteg")

# Experte: feineres Netz, gleiche Messwerte
std, exp = gemessen(k01), gemessen(k01, sv.EXPERTE)
assert std.messwerte[0].get("schneidweg") == exp.messwerte[0].get("schneidweg")
assert [str(sorted(x.items())) for x in std.messwerte] == [str(sorted(x.items())) for x in exp.messwerte]


def dreiecke(netz):
    t = netz["t"]
    return sum(len(x) for x in t.values()) if isinstance(t, dict) else len(t)


assert dreiecke(exp.netz(0)) > dreiecke(std.netz(0)), (dreiecke(exp.netz(0)), dreiecke(std.netz(0)))
print(f"OK: Experte: {dreiecke(exp.netz(0))} statt {dreiecke(std.netz(0))} Dreiecks-Einträge, Messwerte gleich")
std.aufraeumen()
exp.aufraeumen()

# Fenster
v = StepViewer(None, None, programmordner=ORDNER)
assert v.oeffnen(k01)
v.warten()
assert v.mes and not v.mes.fehler and v.zeilen, "Viewer ohne Konturen"
assert v.konturen.rowCount() >= len(v.zeilen)
v.kontur_waehlen(v.zeilen[0]["nr"])
assert v.konturen.currentRow() >= 0
ziel = [a for a in sv.arten_moeglich(v.mes.messwerte[0]) if a != sv.gruppe(v.mes.messwerte[0])]
assert ziel, sv.arten_moeglich(v.mes.messwerte[0])
v.art_aendern(0, ziel[0])
assert sv.gruppe(v.mes.messwerte[0]) == ziel[0], (sv.gruppe(v.mes.messwerte[0]), ziel[0])
assert sv.leistung_zeilen(v.mes, v.anzeige)
print("OK: Viewer öffnet, misst, wählt Kontur, ändert Art")
r08 = HIER / "step_regression" / "R08_Rahmen_4xRE80x40x3_Gehrung.step"
if r08.is_file():
    assert v.oeffnen(r08)
    v.warten()
    assert len(v.mes.messwerte) > 1 and v.ansicht_art == "Gesamtansicht", (len(v.mes.messwerte), v.ansicht_art)
    v.zeigen(1)
    print(f"OK: Baugruppe {r08.name}: {len(v.mes.messwerte)} Körper, Gesamtansicht und Einzelteil")
v.close()
print("Alle Tests bestanden.")
