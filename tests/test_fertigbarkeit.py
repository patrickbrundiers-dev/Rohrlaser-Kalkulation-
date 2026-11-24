"""Fertigbarkeit beim STEP-Import (Laserhub-Vergleich L1/L3/L6, Patrick 20.11.2026 „Alles einbauen nach
Empfehlungen“): Konstruktionsregeln je Maschine, Gravur-Grenzwert, Dateianforderungen.

- F1 Testteil I07 (gemessen): Loch Ø 1,5 < 0,7 × Wand, Steg 1 mm zwischen zwei Löchern, Steg 1 mm zum Ende A,
  Gravur 0,8 mm tief; scharfe Ecken nur mit Grenzwert; Teil bleibt Quadratrohr
- F2 Grenzwerte der Maschine: leer = Vorgabe, 0 = aus, eigene Faktoren; Länge, kürzestes Teil, Hüllkreis;
  Markierloch Ø 0,5 nie
- F3 Ampel: gelb mit Grund „Fertigbarkeit: …“ (nie rot), „Passt“ macht grün; fertiges Teil bleibt grün
- F4 Bauteilanalyse: Merkmale „Fertigbarkeit“ mit Lage, Kennzahl fertigbar, keine Bearbeitung „prüfen“
- F5 Oberfläche: Spalte „Fertigbar“ in der Importanalyse, Reiter Dateien mit Anforderungen (Volumenkörper, Einheit)
- F6 Stammdaten: Felder der Maschine in der Gruppe „Fertigbarkeit beim Import“
- F7 Bestand: kein Befund an den Teilen aus tests/step und tests/step_regression (keine Fehlalarme)

Aufruf: python tests/test_fertigbarkeit.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from rohrlaser import bauteil_analyse as ba  # noqa: E402
from rohrlaser import fertigbarkeit as fb  # noqa: E402
from rohrlaser import step  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            import traceback
            fehler += 1
            print(f"FEHLER {name}: {e} ({traceback.extract_tb(e.__traceback__)[-1].line})")
        return fn
    return deko


TMP = Path(tempfile.mkdtemp())


def messen(dateien):
    """Messung als eigener Prozess wie im Programm (STEP-Import.exe)."""
    import subprocess
    aus = TMP / f"m{len(list(TMP.iterdir()))}.txt"
    subprocess.run([sys.executable, str(HIER.parent / "programm" / "step_messung" / "step_messen.py"), "--ausgabe",
                    str(aus), "--json", str(aus.with_suffix(".json"))] + [str(p) for p in dateien],
                   check=True, capture_output=True, timeout=900)
    return step.lies_messwerte(aus)


I07 = messen([HIER / "step_importengine" / "I07_QR40x3_L800_Fertigbarkeit.step"])[0]
# alle Messungen vor dem ersten Qt-Fenster (die Messung startet Prozesse)
BESTAND = messen(sorted((HIER / "step").glob("*.step")) + sorted((HIER / "step_regression").glob("*.step")))
MASCHINE = dict(maschinen_id="T11", max_stange=6500, endbeschnitt=20, greiferrest=80, min_teil=10,
                max_huellkreis=200, min_huellkreis=13)


@fall("F1 Testteil I07: Loch, Steg zwischen Löchern, Steg zum Ende, Gravur; Ecken nur mit Grenzwert")
def _():
    b = fb.pruefen(I07, MASCHINE)
    regeln = sorted(x["regel"] for x in b)
    assert regeln == sorted([fb.LOCH, fb.STEG, fb.STEG_ENDE, fb.GRAVUR]), b
    loch = next(x for x in b if x["regel"] == fb.LOCH)
    assert loch["x"] == 100 and loch["wert"] == 1.5 and loch["grenze"] == 2.1 and loch["seite"], loch
    steg = next(x for x in b if x["regel"] == fb.STEG)
    assert abs(steg["wert"] - 1.0) < 0.05 and steg["x"] == 300, steg
    ende = next(x for x in b if x["regel"] == fb.STEG_ENDE)
    assert abs(ende["wert"] - 1.0) < 0.05 and "Ende A" in ende["text"], ende
    gr = next(x for x in b if x["regel"] == fb.GRAVUR)
    assert gr["wert"] == 0.8 and "0,5 mm" in gr["text"], gr
    mit_ecke = fb.pruefen(I07, dict(MASCHINE, fb_eckradius=0.3))
    ecke = [x for x in mit_ecke if x["regel"] == fb.ECKE]
    assert len(ecke) == 1 and ecke[0]["x"] == 650 and "4 Innenecke" in ecke[0]["text"], ecke
    assert I07["profilform"] == "Quadratrohr" and ba.kategorie(I07)[0] == ba.VIERKANT    # Gravur: Rohr bleibt Rohr


@fall("F2 Grenzwerte: leer = Vorgabe, 0 = aus, eigene Faktoren; Länge, kürzestes Teil, Hüllkreis; Markierloch")
def _():
    aus = dict(MASCHINE, fb_loch_faktor=0, fb_steg_faktor=0, fb_gravur_tiefe=0)
    assert fb.pruefen(I07, aus) == [], fb.pruefen(I07, aus)
    streng = fb.pruefen(I07, dict(MASCHINE, fb_loch_faktor=0.4, fb_steg_faktor=0.5, fb_gravur_tiefe=1))
    assert sorted(x["regel"] for x in streng) == [fb.STEG, fb.STEG_ENDE], streng    # Loch 1,5 > 1,2; Steg 1 < 1,5
    assert fb.pruefen(I07, None) and fb.grenzen(None)["loch"] == 0.7 and fb.grenzen(None)["eckradius"] == 0
    lang = dict(I07, laenge=7000.0, konturen_liste="[]")
    t = [x["text"] for x in fb.pruefen(lang, MASCHINE)]
    assert t == ["Teil 7000 mm länger als die Maschine aus einer Stange schneidet (6400 mm)"], t
    kurz = dict(I07, laenge=8.0, konturen_liste="[]")
    assert [x["regel"] for x in fb.pruefen(kurz, MASCHINE)] == [fb.KURZ]
    dick = dict(I07, abm_a=200.0, abm_b=200.0, konturen_liste="[]")
    assert [x["regel"] for x in fb.pruefen(dick, MASCHINE)] == [fb.HUELLE]
    klein = dict(I07, profilform="Rundrohr", abm_a=10.0, abm_b=0.0, konturen_liste="[]")
    assert "kleiner als die Maschine spannt" in fb.pruefen(klein, MASCHINE)[0]["text"]
    mark = dict(I07, konturen_liste=json.dumps([dict(art="Bohrung", z=50, durchmesser=0.5, seite="0°",
                                                     umriss=[[0, 49.75], [0.5, 50], [0, 50.25]])]))
    assert fb.pruefen(mark, MASCHINE) == []
    assert fb.pruefen(dict(I07, profilform="Blech", bauteiltyp="Blech"), MASCHINE) == []
    assert fb.pruefen(dict(I07, fehler="kaputt"), MASCHINE) == []


@fall("F3 Ampel: gelb mit Grund, nie rot; „Passt“ macht grün; fertiges Teil bleibt grün")
def _():
    m = dict(I07)
    fb.markieren([m], MASCHINE)
    farbe, gruende = step.ampel(m)
    assert farbe == "gelb" and any(g.startswith("Fertigbarkeit: Loch Ø 1,5") for g in gruende), (farbe, gruende)
    assert "1 weitere" in gruende[-1] or len(m["_fertigbarkeit"]) <= 3, gruende
    m["_geprueft"] = True
    assert step.ampel(m)[0] == "gruen"
    ok = dict(I07, konturen_liste="[]")
    fb.markieren([ok], MASCHINE)
    assert ok["_fertigbarkeit"] == [] and step.ampel(ok)[0] == "gruen"


@fall("F4 Bauteilanalyse: Merkmale Fertigbarkeit mit Lage, Kennzahl fertigbar")
def _():
    m = dict(I07)
    fb.markieren([m], MASCHINE)
    a = ba.analyse(m)
    f = [x for x in a["merkmale"] if x["merkmal"] == ba.M_FERTIG]
    assert len(f) == 4 and all(x.get("x") is not None for x in f), f
    assert a["kennzahlen"]["fertigbar"] is False and "prüfen" not in a["bearbeitungen"], a["bearbeitungen"]
    assert a["stufe"] == "prüfen" and 50 <= a["konfidenz"] < 90, (a["stufe"], a["konfidenz"])
    assert ba.analyse(dict(I07, konturen_liste="[]", _fertigbarkeit=[]))["kennzahlen"]["fertigbar"] is True


@fall("F5 Oberfläche: Spalte Fertigbar, Reiter Dateien mit Anforderungen")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import importanalyse_dialog as iad
    app = QApplication.instance() or QApplication([])
    m = dict(I07)
    fb.markieren([m], MASCHINE)
    inch = dict(I07, datei="Zoll.step", einheit="inch", koerperart="aus Flächenmodell genäht", _fertigbarkeit=[])
    d = iad.ImportanalyseDialog(None, [m, inch])
    sp = iad.ImportanalyseDialog.BAUTEIL_SPALTEN.index("Fertigbar")
    texte = sorted(d.bauteile.item(r, sp).text() for r in range(d.bauteile.rowCount()))
    assert texte == ["ja", "prüfen (4)"], texte
    zeilen = {z["datei"]: z for z in iad.datei_anforderungen([m, inch])}
    assert zeilen[m["datei"]]["ok"] and zeilen[m["datei"]]["bewertung"] == "erfüllt: Volumenkörper in mm"
    z = zeilen["Zoll.step"]
    assert not z["ok"] and "inch" in z["bewertung"] and "genäht" in z["bewertung"], z
    assert d.datei_tabelle.rowCount() == 2 and d.reiter.tabText(2).startswith("Dateien (2"), d.reiter.tabText(2)
    bilder = os.environ.get("IMPORTENGINE_BILDER")
    if bilder:
        Path(bilder).mkdir(parents=True, exist_ok=True)
        d.resize(1400, 640)
        d.show()
        r = next(r for r in range(d.bauteile.rowCount()) if d.bauteile.item(r, sp).text() != "ja")
        d.bauteile.selectRow(r)
        app.processEvents()
        d.grab().save(str(Path(bilder) / "fertigbarkeit_importanalyse.png"))
        d.reiter.setCurrentIndex(2)
        app.processEvents()
        d.grab().save(str(Path(bilder) / "fertigbarkeit_dateien.png"))
    d.reject()


@fall("F6 Stammdaten: Maschinenfelder in der Gruppe Fertigbarkeit")
def _():
    from rohrlaser import maschinen_editor as me
    from rohrlaser.stammdaten import MASCHINEN
    for n in fb.FELDER:
        assert MASCHINEN.feld(n) is not None and me.gruppe_von(n) == "fertigbarkeit", n


@fall("F7 Bestand: kein Fehlalarm an den Teilen aus tests/step und tests/step_regression")
def _():
    assert len(BESTAND) >= 15, len(BESTAND)
    funde = {m["datei"]: [x["text"] for x in fb.pruefen(m, MASCHINE)] for m in BESTAND}
    funde = {k: v for k, v in funde.items() if v}
    assert not funde, funde


print("ALLE OK" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
