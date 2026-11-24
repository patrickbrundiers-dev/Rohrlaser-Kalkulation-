"""Importanalyse, zweiter Teil (Laserhub-Vergleich L2/L4/L5, Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“).

- Z1 Ausdehnung längs je Merkmal (x0/x1 aus dem Umriss der Abwicklung) und je Fertigbarkeits-Befund
- Z2 Merkmal im 3D: Teil wählen zeigt das Netz, Merkmal wählen markiert seinen Bereich; „Nächstes zu prüfen“
  springt zu unsicheren Merkmalen und Regelverstößen über alle Teile
- Z3 Gewinde, Senkung, Fließloch aus Modell und Zeichnung: Zeichnung bestätigt (95 %), Anzahl widerspricht (70 %),
  nur in der Zeichnung (60 %, neues Merkmal); ohne Zeichnung wie bisher
- Z4 Zukaufteile des Imports: Hinweis auf die gesammelte Materialanfrage (Blech-, Fräs-, Drehteile)

Aufruf: python tests/test_importanalyse_3d.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
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
aus = TMP / "m.txt"
subprocess.run([sys.executable, str(HIER.parent / "programm" / "step_messung" / "step_messen.py"), "--ausgabe",
                str(aus), "--json", str(TMP / "m.json"), "--netze", str(TMP / "netze"),
                str(HIER / "step_importengine" / "I07_QR40x3_L800_Fertigbarkeit.step"),
                str(HIER / "step" / "T07_QR40x3_L1000_Gewinde_Gravur.step"),
                str(HIER / "step_importengine" / "I06_Baugruppe_gemischt.step")],
               check=True, capture_output=True, timeout=900)
MW = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(aus), TMP / "netze"), TMP / "m.json")
I07 = next(m for m in MW if m["datei"].startswith("I07"))
T07 = next(m for m in MW if m["datei"].startswith("T07"))
fb.markieren(MW, None)


@fall("Z1 Ausdehnung längs je Merkmal und je Befund")
def _():
    a = ba.analyse(I07)
    loch = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_BOHRUNG and x.get("x") == 100)
    assert abs(loch["x0"] - 99.2) < 0.15 and abs(loch["x1"] - 100.8) < 0.15, loch
    steg = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_FERTIG and x["art"] == fb.STEG)
    assert steg["x0"] <= 296 and steg["x1"] >= 315, steg            # beide Löcher Ø 10 (x 300 und 311)
    ende = next(x for x in a["merkmale"] if x["merkmal"] == ba.M_FERTIG and x["art"] == fb.STEG_ENDE)
    assert ende["x0"] == 0 and 8.5 < ende["x1"] < 9.5, ende


@fall("Z2 Merkmal im 3D markiert, Nächstes zu prüfen")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import importanalyse_dialog as iad
    app = QApplication.instance() or QApplication([])
    d = iad.ImportanalyseDialog(None, [I07, T07])
    r = next(i for i, (_, p) in enumerate(d.zeilen) if p["bezeichnung"].startswith("I07"))
    d.bauteile.selectRow(r)
    assert d.ansicht.netz is not None, "kein Netz im 3D"
    i = next(i for i, x in enumerate(d.merkmal_liste) if x["merkmal"] == ba.M_BOHRUNG and x.get("x") == 100)
    d.merkmale.selectRow(i)
    z = d.ansicht.markiert_z
    assert z and z[0] < 99.2 and z[1] > 100.8 and z[1] - z[0] < 3, z
    assert d.ansicht.auswahl_punkte()[0], "nichts markiert"
    d.bauteile.selectRow(r)
    d.merkmale.setCurrentCell(-1, -1)
    assert d.naechstes_pruefen()
    x = d.merkmal_liste[d.merkmale.currentRow()]
    assert x["merkmal"] == ba.M_FERTIG and d.ansicht.markiert_z, x          # Regelverstöße stehen zuerst
    gesehen = set()
    for _ in range(12):
        assert d.naechstes_pruefen()
        gesehen.add(d.bauteile.currentRow())
    assert len(gesehen) == 2, gesehen          # springt auch zum anderen Teil (T07: Gewinde-Vorschlag)
    bilder = os.environ.get("IMPORTENGINE_BILDER")
    if bilder:
        Path(bilder).mkdir(parents=True, exist_ok=True)
        d.bauteile.selectRow(r)
        d.merkmale.selectRow(next(i for i, x in enumerate(d.merkmal_liste) if x["merkmal"] == ba.M_FERTIG and
                                  x["art"] == fb.STEG))
        d.resize(1450, 760)
        d.show()
        app.processEvents()
        d.grab().save(str(Path(bilder) / "importanalyse_3d.png"))
    d.reject()


@fall("Z3 Gewinde, Senkung, Fließloch aus Modell und Zeichnung")
def _():
    ohne = [x for x in ba.analyse(T07)["merkmale"] if x["merkmal"] == ba.M_GEWINDE]
    assert ohne and all(x["konfidenz"] == 70 for x in ohne), ohne
    g = ohne[0]["abmessung"].split()[0]                 # z. B. „M6“
    n = sum(int(x.get("anzahl") or 1) for x in ohne)
    ok = ba.analyse(dict(T07, _zeichnung_text=f"{n}x {g}", _zeichnung_quelle="Zeichnung"))["merkmale"]
    gw = [x for x in ok if x["merkmal"] == ba.M_GEWINDE]
    assert gw and all(x["konfidenz"] == 95 and "bestätigt" in x["hinweis"] for x in gw), gw
    falsch = ba.analyse(dict(T07, _zeichnung_text=f"{n + 2}x {g}"))["merkmale"]
    gw = [x for x in falsch if x["merkmal"] == ba.M_GEWINDE]
    assert gw and all(x["konfidenz"] == 70 and "Anzahl prüfen" in x["hinweis"] for x in gw), gw
    neu = ba.analyse(dict(T07, _zeichnung_text="2x Senkung DIN 74\nFlowdrill M8 (3x)",
                          _zeichnung_quelle="Formular"))["merkmale"]
    sk = [x for x in neu if x["merkmal"] == ba.M_SENKUNG]
    fd = [x for x in neu if x["merkmal"] == ba.M_FLIESS]
    assert len(sk) == 1 and sk[0]["konfidenz"] == 60 and sk[0]["anzahl"] == 2 and "Formular" in sk[0]["hinweis"], sk
    assert len(fd) == 1 and fd[0]["anzahl"] == 3 and fd[0]["bearbeitung"] == ba.FLOWDRILL, fd
    a = ba.analyse(dict(T07, _zeichnung_text="2x Senkung"))
    assert a["stufe"] in ("sicher", "prüfen") and any("Senkung" in u for u in a["unsicherheiten"]), a["unsicherheiten"]


@fall("Z4 Zukaufteile des Imports: Hinweis auf die Materialanfrage")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import importanalyse_dialog as iad
    QApplication.instance() or QApplication([])
    i06 = [m for m in MW if m["datei"].startswith("I06")]
    d = iad.ImportanalyseDialog(None, i06)
    t = d.zukauf_hinweis.text()
    assert "1 Blechteil" in t and "1 Frästeil" in t and "Materialanfrage" in t, t
    assert iad.zukauf_text({ba.VIERKANT: 3}) == ""
    d.reject()


print("ALLE OK" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
