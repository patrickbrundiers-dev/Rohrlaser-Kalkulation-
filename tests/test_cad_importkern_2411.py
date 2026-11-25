"""Geometrieprüfung, Toleranzverwaltung, Reparatur-Protokoll und CAD-Prüfwerte des STEP-Imports (Master-Auftrag Patrick
24.11.2026 „CAD-Importkern auf höchstem technischem Niveau“, step_qualitaet.py).

Prüft mit den Prüfteilen aus tests/erzeuge_pruefteile_2411.py (Sollwerte aus der Konstruktion):
- Kopf der Datei: Schema, CAD-System, Einheit, Genauigkeit (UNCERTAINTY), Prüfwerte des CAD (GVP) samt Umrechnung Zoll
- Abgleich mit den Prüfwerten: richtig = bestätigt, 2 % zu viel Volumen = Abweichung (rot, Hinweis, Prüfstatus prüfen)
- grobe Genauigkeit der Datei = unsicher; deckungsgleiche Körper = doppelt (Anzahl prüfen, kein Verbundkern)
- offene Schale = fehlerhaft; Reparatur-Probe an Kopie: Klasse 1 (verdrehte Fläche), Klasse 3 (fehlende Fläche),
  das Original bleibt unverändert; gescheiterte Messung + Klasse 1 = mit reparierter Kopie gemessen
- Ergebnis reproduzierbar (zweimal messen = gleiches JSON), Messwerte der Prüfteile wie ohne Prüfung
- Importanalyse: Reiter Geometrieprüfung mit Farben und Prüfprotokoll

Aufruf: python tests/test_cad_importkern_2411.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
import step_geometrie as g  # noqa: E402
import step_qualitaet as sq  # noqa: E402

P = HIER / "step_pruefung"
fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except Exception as e:  # noqa: BLE001
            import traceback
            fehler += 1
            print(f"FEHLER {name}: {type(e).__name__}: {e} ({traceback.extract_tb(e.__traceback__)[-1].line})")
        return fn
    return deko


def messen(name):
    return g.analysiere_datei(P / f"{name}.step")


@fall("Kopf: Schema, System, Einheit, Genauigkeit, Prüfwerte (auch Zoll)")
def _():
    k = sq.datei_kopf(P / "P01_RE60x40x2_Pruefwerte_richtig.step", "mm")
    assert k["schema"] == "AP214" and "Open CASCADE" in k["system"] and k["unsicherheit_mm"] == 1e-7, k
    (ref,) = k["gvp"].values()
    assert set(ref) == {"volumen", "flaeche", "schwerpunkt"}, ref
    z = sq.datei_kopf(P / "P03_RE60x40x2_Zoll_Pruefwerte.step", "inch")
    (rz,) = z["gvp"].values()
    assert abs(rz["volumen"] - ref["volumen"]) < 1e-6 * ref["volumen"], (rz, ref)       # in mm³ umgerechnet
    assert abs(z["unsicherheit_mm"] - 2.54e-6) < 1e-12, z["unsicherheit_mm"]
    assert sq.datei_kopf(P / "P04_RE60x40x2_Genauigkeit_005.step", "mm")["unsicherheit_mm"] == 0.05
    assert sq.datei_kopf(HIER / "gibt_es_nicht.step")["gvp"] == {}          # nie eine Ausnahme


@fall("Prüfwerte des CAD: richtig = bestätigt, Zoll = bestätigt")
def _():
    for name in ("P01_RE60x40x2_Pruefwerte_richtig", "P03_RE60x40x2_Zoll_Pruefwerte"):
        (t,) = messen(name)
        c = t.qualitaet["cad_referenz"]
        assert c["status"] == "bestätigt" and c["volumen_rel"] < 1e-9 and c["schwerpunkt_mm"] < 1e-6, (name, c)
        assert t.qualitaet["status"] == "korrekt" and t.profilform == "Rechteckrohr", t.qualitaet
        assert t.pruefung_datei["cad_abgleich"] == {"bestätigt": 1}, t.pruefung_datei


@fall("Prüfwerte des CAD: 2 % Volumen Abweichung = rot, Hinweis, prüfen")
def _():
    (t,) = messen("P02_RE60x40x2_Pruefwerte_falsch")
    c = t.qualitaet["cad_referenz"]
    assert c["status"] == "abweichung" and abs(c["volumen_rel"] - 0.02 / 1.02) < 1e-9, c
    assert t.qualitaet["status"] == "fehlerhaft" and t.pruefstatus == "prüfen", (t.qualitaet, t.pruefstatus)
    assert any("Original-CAD" in h for h in t.hinweise), t.hinweise


@fall("Genauigkeit der Datei 0,05 mm = unsicher mit Hinweis, Messung unverändert")
def _():
    (t,) = messen("P04_RE60x40x2_Genauigkeit_005")
    (r,) = messen("P01_RE60x40x2_Pruefwerte_richtig")
    assert t.qualitaet["status"] == "unsicher" and any("Genauigkeit der STEP-Datei" in h
                                                        for h in t.qualitaet["hinweise"]), t.qualitaet
    assert (t.abm_a, t.abm_b, t.wandstaerke, t.laenge, t.schneidweg) == (r.abm_a, r.abm_b, r.wandstaerke, r.laenge,
                                                                          r.schneidweg)


@fall("Doppelter Körper: erkannt, Anzahl prüfen, kein Verbundkern")
def _():
    a, b = messen("P05_RE60x40x2_doppelt")
    assert a.profilform == b.profilform == "Rechteckrohr", (a.profilform, b.profilform)
    assert b.qualitaet["doppelt_zu"] == 1 and b.pruefstatus == "prüfen", b.qualitaet
    assert any("deckungsgleich" in h for h in b.hinweise) and not a.qualitaet.get("doppelt_zu")
    assert a.pruefung_datei["doppelte_koerper"] == 1


@fall("Offene Schale = fehlerhaft (nicht geschlossen), nichts erfunden")
def _():
    (t,) = messen("P08_Quader_offen")
    assert t.qualitaet["status"] == "fehlerhaft" and t.qualitaet["fehler"] == {"nicht_geschlossen": 1}, t.qualitaet
    assert not t.profilform and t.pruefung_datei["status"]["fehlerhaft"] == 1


@fall("Verdrehte Fläche und kreuzende Kontur: OpenCascade heilt beim Einlesen, Körper gültig")
def _():
    for name in ("P06_Quader_Flaeche_verdreht", "P07_Prisma_Kontur_kreuzt"):
        (t,) = messen(name)
        assert t.gueltig and t.qualitaet["status"] == "korrekt", (name, t.qualitaet)


def _flaechen(s):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    ex, out = TopExp_Explorer(s, TopAbs_FACE), []
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _schale(fl):
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.TopoDS import TopoDS, TopoDS_Shell
    b, sh = BRep_Builder(), TopoDS_Shell()
    b.MakeShell(sh)
    for f in fl:
        b.Add(sh, f)
    return BRepBuilderAPI_MakeSolid(TopoDS.Shell(sh)).Solid()


def _quader():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return BRepPrimAPI_MakeBox(100, 40, 6).Shape()


@fall("Reparatur-Probe Klasse 1: verdrehte Fläche, Original bleibt unverändert")
def _():
    fl = _flaechen(_quader())
    k = _schale([fl[0].Reversed()] + fl[1:])
    vorher = sq._kenndaten(k)
    q, rep = sq.koerper_pruefen(k, "Volumenkörper", sq._gueltig(k))
    assert q["status"] == "reparierbar" and q["fehler"].get("falsch_orientiert"), q
    r = q["reparatur"]
    assert r["klasse"] == 1 and r["vorher"]["gueltig"] is False and r["nachher"]["gueltig"] is True, r
    assert r["abweichung"]["huelle_mm"] <= sq.SICHER_HUELLE and rep is not None and sq._gueltig(rep)
    assert sq._kenndaten(k) == vorher and not sq._gueltig(k), "Original verändert"
    assert abs(sq._kenndaten(rep)["volumen"] - 100 * 40 * 6) < 1e-6


@fall("Reparatur-Probe Klasse 3: fehlende Fläche, keine Reparatur übernommen")
def _():
    k = _schale(_flaechen(_quader())[1:])
    q, rep = sq.koerper_pruefen(k, "Volumenkörper", sq._gueltig(k), volumen=1.0)
    assert q["status"] == "fehlerhaft" and q["fehler"].get("offene_kanten") == 4, q
    assert q["reparatur"]["klasse"] == 3 and rep is None, q["reparatur"]


@fall("Messung gescheitert + Klasse 1: mit reparierter Kopie gemessen, mit Hinweis")
def _():
    fl = _flaechen(_quader())
    k = _schale([fl[0].Reversed()] + fl[1:])
    gel = g.Gelesen("test", [("Volumenkörper", k)], dict(kopf={}, phasen={}), {})
    t = g.Teil(datei="test", koerper=1)
    t.hinweise.append("Messung fehlgeschlagen: Test")
    neu = g._geometrie_pruefen(t, k, "Volumenkörper", gel, 1, False, g.FLACHSTAHL_BIS)
    assert neu is not t and neu.qualitaet["gemessen_mit_reparatur"], neu.qualitaet
    assert neu.bauteiltyp == "Blech" and "reparierter Kopie" in neu.hinweise[0], (neu.bauteiltyp, neu.hinweise)
    gemessen = g.Teil(datei="test", koerper=1, profilform="Rechteckrohr")       # Messung gelang: nichts ersetzen
    assert g._geometrie_pruefen(gemessen, k, "Volumenkörper", gel, 1, False, g.FLACHSTAHL_BIS) is gemessen


@fall("Toleranzstufen und Kurztext")
def _():
    assert [sq.toleranz_stufe(x) for x in (1e-7, 0.005, 0.05, 0.5)] == ["fein", "normal", "grob", "kritisch"]
    assert "Klasse 1" in sq.kurztext(dict(reparatur=dict(klasse=1, text="x"), fehler={"luecken": 2}))


@fall("JSON 1.31 reproduzierbar, Spalte pruefung in den Messwerten")
def _():
    tmp = Path(tempfile.mkdtemp())
    js = []
    for n in (1, 2):
        aus = tmp / f"m{n}.txt"
        subprocess.run([sys.executable, str(HIER.parent / "programm" / "step_messung" / "step_messen.py"),
                        "--ausgabe", str(aus), "--json", str(tmp / f"m{n}.json"), "--prozesse", "1",
                        "--netze", str(tmp / f"netze{n}"),
                        str(P / "P02_RE60x40x2_Pruefwerte_falsch.step"), str(P / "P05_RE60x40x2_doppelt.step")],
                       check=True, capture_output=True, timeout=600)
        d = json.loads((tmp / f"m{n}.json").read_text(encoding="utf-8"))
        d.pop("erzeugt")
        js.append(d)
    assert js[0] == js[1], "zweimal gemessen, anderes Ergebnis"
    assert js[0]["schema_version"] == "1.31"
    d2, d5 = js[0]["dateien"]
    assert d2["genauigkeit"]["cad_abgleich"] == {"abweichung": 1} and d5["genauigkeit"]["doppelte_koerper"] == 1
    assert d5["koerper"][1]["geometriepruefung"]["doppelt_zu"] == 1
    from rohrlaser import step
    mw = step.lade_netze(step.lies_messwerte(tmp / "m1.txt"), tmp / "netze1")
    assert json.loads(mw[0]["pruefung"])["cad_referenz"]["status"] == "abweichung", mw[0]["pruefung"]
    assert json.loads(mw[0]["pruefung_datei"])["schema"] == "AP214"
    globals()["MW"] = mw


@fall("Importanalyse: Reiter Geometrieprüfung mit Farben und Protokoll")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import importanalyse_dialog as iad
    app = QApplication.instance() or QApplication([])  # noqa: F841
    mw = globals()["MW"]
    zeilen = iad.geometrie_zeilen(mw)
    assert [z["status"] for z in zeilen] == ["fehlerhaft", "korrekt", "unsicher"], [z["status"] for z in zeilen]
    assert "abweichung" in zeilen[0]["werte"][7], zeilen[0]["werte"]
    html = iad.pruefung_kopf_html(iad.geometrie_dateien(mw))
    assert "AP214" in html and "1 doppelte Körper" in html and iad.STATUS_FARBE["fehlerhaft"] in html, html
    p = iad.protokoll_html(zeilen[2])
    assert "deckungsgleich auf Körper 1" in p, p
    mw[1]["_normteil"] = True
    assert iad.geometrie_zeilen(mw)[1]["status"] == "Zukauf"
    mw[1].pop("_normteil")
    d = iad.ImportanalyseDialog(None, mw)
    titel = [d.reiter.tabText(i) for i in range(d.reiter.count())]
    assert "Geometrieprüfung (2 prüfen)" in titel, titel
    d.pruefung_tabelle.selectRow(0)
    assert "Prüfwerte des Original-CAD" in d.pruefung_text.toHtml()
    assert d.pruefung_tabelle.item(0, 3).foreground().color().name().lower() == \
        iad.stil.farbe(iad.STATUS_FARBE["fehlerhaft"]).name().lower()


@fall("STEP-Viewer: Prüfwerte beim Anklicken, Übersicht, Farben nach Prüfung im 3D")
def _():
    from types import SimpleNamespace
    from rohrlaser import step_viewer as sv
    from rohrlaser.ansicht3d import baugruppe
    mw = globals()["MW"]
    z = dict(sv.pruef_zeilen(mw[0]))
    assert z["Geometrieprüfung"] == "fehlerhaft" and z["CAD-Prüfwerte"].startswith("abweichung"), z
    assert dict(sv.pruef_zeilen(mw[2]))["Doppelt"] == "liegt deckungsgleich auf Körper 1"
    assert ("Geometrieprüfung", "fehlerhaft") in sv.erkennung(mw[0])
    u = dict(sv.pruef_uebersicht(SimpleNamespace(messwerte=mw)))
    assert u["Geometrieprüfung"] == "1 korrekt, 1 unsicher, 1 fehlerhaft", u
    netze = [m.get("_netz") for m in mw]
    assert all(netze), "keine Netze"
    farbe = {n: sv.PRUEF_ART[sv.pruef_status(m)] for n, m in enumerate(mw)}
    netz, _ = baugruppe(netze, pruefung=farbe)
    assert {"QF", "QK", "QU"} <= set(netz["t"]), set(netz["t"])
    netz, _ = baugruppe(netze, pruefung=farbe, normteile={0})
    assert "QF" not in netz["t"] and "NT" in netz["t"]                   # Zukauf bleibt ausgeschlossen (grau)
    netz, _ = baugruppe(netze)
    assert not {"QF", "QK", "QU"} & set(netz["t"])                       # ohne Schalter wie bisher


print("Alles in Ordnung" if not fehler else f"{fehler} Fehler")
sys.exit(1 if fehler else 0)
