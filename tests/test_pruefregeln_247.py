"""Prüfregeln aus dem 247TailorSteel-Vergleich (Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“), Teil der
Fertigbarkeit beim STEP-Import; Grenzwerte je Maschine (leer = Vorgabe, 0 = aus).

- P1 Gravur: Mindestabstand 1,5 mm zur Schnittlinie, berührt sie nie (I08: Gravur 1 mm neben Loch Ø 10)
- P2 Einnietmuttern aus Zeichnung/Zusatzarbeit: M4–M8, nur Quadrat-/Rechteckrohr bis 150 mm, Wand 0,5–3 mm, Seite
  hoch genug, Loch 2 × Wand von Konturen und Rohrende (I08: Loch Ø 9 bei x 8)
- P3 Umfang an keinem der 5 Prüfpunkte geschlossen (I09: fünf Fenster), I07/I08 nicht
- P4 Schneidtechnik: Position vor Maschine vor 2,5D; bei XY Loch im Rundrohr höchstens 0,5 × Rohr-Ø (I10: Ø 25)
- P5 Stammdaten: Maschinenfelder in der Gruppe Fertigbarkeit, Positionsfeld Schneidtechnik, Auswahl 2,5D/XY

Aufruf: python tests/test_pruefregeln_247.py
"""
import json
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
                str(aus), "--json", str(TMP / "m.json")]
               + [str(HIER / "step_importengine" / n) for n in (
                   "I07_QR40x3_L800_Fertigbarkeit.step", "I08_QR40x3_L600_Gravur_Nietmutter.step",
                   "I09_QR40x3_L400_Umfang_offen.step", "I10_RR40x2_L300_Loch25.step")],
               check=True, capture_output=True, timeout=900)
MW = {m["datei"][:3]: m for m in step.lies_messwerte(aus)}
I07, I08, I09, I10 = MW["I07"], MW["I08"], MW["I09"], MW["I10"]


def regeln(m, maschine=None, technik=None, regel=None):
    b = fb.pruefen(m, maschine, technik)
    return [x for x in b if regel is None or x["regel"] == regel]


@fall("P1 Gravur: Mindestabstand zur Schnittlinie, berührt sie nie")
def _():
    g = regeln(I08, regel=fb.GRAVUR_RAND)
    assert len(g) == 1 and g[0]["text"] == "Gravur 1 mm neben Bohrung (x 311), mindestens 1,5 mm", g
    assert g[0]["x0"] == 300 and g[0]["x1"] == 305, g
    assert not regeln(I08, dict(fb_gravur_abstand=0.8), regel=fb.GRAVUR_RAND)      # eigener Grenzwert
    assert not regeln(I08, dict(fb_gravur_abstand=0), regel=fb.GRAVUR_RAND)        # 0 = aus
    kl = json.loads(I08["konturen_liste"])
    gr = next(d for d in kl if d["art"] == "Gravur")
    beruehrt = dict(I08, konturen_liste=json.dumps([gr, dict(art="Bohrung", z=310, durchmesser=10, seite="0°",
                                                             umriss=[[-5, 305], [5, 305], [5, 315], [-5, 315]])]))
    assert "berührt die Schnittlinie" in regeln(beruehrt, regel=fb.GRAVUR_RAND)[0]["text"]
    assert not regeln(I07, regel=fb.GRAVUR_RAND)          # Gravur frei


@fall("P2 Einnietmuttern: Profil, Wand, Größe, Seite, Abstand zu Konturen und Rohrende")
def _():
    assert not regeln(I08, regel=fb.NIETMUTTER)            # ohne Einnietmuttern keine Prüfung
    m = dict(I08, _zeichnung_text="2x Einnietmutter M6", _zeichnung_quelle="Zeichnung")
    n = regeln(m, regel=fb.NIETMUTTER)
    assert [x["text"] for x in n] == ["Einnietmutter M6 (Loch Ø 9): 3,5 mm zum Ende A, mindestens 2 × Wand = 6 mm"], n
    assert n[0]["x"] == 8
    z = dict(I08, _zusatz=["Einnietmuttern setzen"])        # Zusatzarbeit ohne Größe: nur Profil und Wand
    assert not regeln(z, regel=fb.NIETMUTTER)
    t = [x["text"] for x in regeln(dict(z, wandstaerke=4.0), regel=fb.NIETMUTTER)]
    assert t == ["Einnietmuttern nur für Wand 0,5 bis 3 mm, hier 4 mm – prüfen"], t
    assert not regeln(dict(z, wandstaerke=4.0), dict(fb_nm_wand=5), regel=fb.NIETMUTTER)
    t = [x["text"] for x in regeln(dict(z, profilform="Rechteckrohr", abm_a=160.0, abm_b=80.0), regel=fb.NIETMUTTER)]
    assert t == ["Einnietmuttern nur bis Profil 150 mm, hier 160 × 80 mm – prüfen"], t
    t = [x["text"] for x in regeln(dict(I10, _zusatz=["Einnietmuttern setzen"]), regel=fb.NIETMUTTER)]
    assert t == ["Einnietmuttern (Zusatzarbeit Einnietmuttern setzen) nur in Quadrat- oder Rechteckrohr, hier "
                 "Rundrohr – prüfen"], t
    t = [x["text"] for x in regeln(dict(I08, _zeichnung_text="4x Einnietmutter M10"), regel=fb.NIETMUTTER)]
    assert t == ["Einnietmutter M10: nur M4 bis M8 – prüfen"], t
    t = [x["text"] for x in regeln(dict(I08, abm_a=20.0, abm_b=20.0, konturen_liste="[]",
                                        _zeichnung_text="Einnietmutter M8"), regel=fb.NIETMUTTER)]
    assert t == ["Einnietmutter M8: Seite 20 mm zu schmal (Loch Ø 11 + 2 × 6 mm Rand)"], t


@fall("P3 Umfang an keinem der 5 Prüfpunkte geschlossen")
def _():
    assert fb.pruefpunkte(400) == [10, 100, 200, 300, 390] and fb.pruefpunkte(50)[0] == 5
    assert fb.umfang_mm(I09) == 160 and abs(fb.umfang_mm(I10) - 125.66) < 0.01
    u = regeln(I09, regel=fb.UMFANG)
    assert len(u) == 1 and u[0]["text"].startswith("Umfang an keinem der 5 Prüfpunkte geschlossen") and \
        "21 % offen" in u[0]["text"] and (u[0]["x0"], u[0]["x1"]) == (0, 400), u
    assert not regeln(I09, dict(fb_umfang_offen=25), regel=fb.UMFANG)       # Fenster 21 % < 25 %
    assert not regeln(I09, dict(fb_umfang_offen=0), regel=fb.UMFANG)
    kl = json.loads(I09["konturen_liste"])
    vier = dict(I09, konturen_liste=json.dumps([d for d in kl if d.get("z") != 200]))      # Mitte geschlossen
    assert not regeln(vier, regel=fb.UMFANG)
    assert not regeln(I07, regel=fb.UMFANG) and not regeln(I08, regel=fb.UMFANG)
    assert I09["profilform"] == "Quadratrohr" and ba.kategorie(I09)[0] == ba.VIERKANT      # nichts umgedeutet


@fall("P4 Schneidtechnik: Position vor Maschine, XY begrenzt Löcher im Rundrohr")
def _():
    assert fb.technik_von(None) == fb.ZWEIEINHALB_D
    assert fb.technik_von(dict(schneidtechnik="XY")) == fb.XY
    assert fb.technik_von(dict(schneidtechnik="XY"), dict(schneidtechnik="2,5D")) == fb.ZWEIEINHALB_D
    assert fb.technik_von(dict(schneidtechnik="xy"), dict(schneidtechnik="")) == fb.XY
    assert not regeln(I10, regel=fb.XY_LOCH)                                       # 2,5D: keine Grenze
    x = regeln(I10, dict(schneidtechnik="XY"), regel=fb.XY_LOCH)                   # Standard der Maschine
    assert [b["text"] for b in x] == ["Loch Ø 25 mm größer als 0,5 × Rohr-Ø 40 mm: mit XY nicht zylindrisch "
                                      "schneidbar – 2,5D wählen oder prüfen"] and x[0]["x"] == 150, x
    assert not regeln(I10, dict(schneidtechnik="XY"), technik="2,5D", regel=fb.XY_LOCH)    # Position gilt
    assert regeln(I10, None, technik="XY", regel=fb.XY_LOCH)
    assert not regeln(I10, dict(schneidtechnik="XY", fb_xy_faktor=0.7), regel=fb.XY_LOCH)
    assert not regeln(I08, dict(schneidtechnik="XY"), regel=fb.XY_LOCH)            # nur Rundrohr
    a = ba.analyse(I10)
    assert fb.xy_zu_gross(a) == [25.0] and fb.xy_zu_gross(ba.analyse(I08)) == []


@fall("P5 Stammdaten: Maschinenfelder, Positionsfeld Schneidtechnik, Auswahl")
def _():
    from rohrlaser import maschinen_editor as me
    from rohrlaser.angebot import POSITIONEN
    from rohrlaser.datenbank import SCHEMA_VERSION
    from rohrlaser.stammdaten import MASCHINEN
    for n in fb.FELDER:
        assert MASCHINEN.feld(n) is not None and me.gruppe_von(n) == "fertigbarkeit", n
    f = POSITIONEN.feld("schneidtechnik")
    assert f is not None and f.auswahl == "schneidtechnik" and MASCHINEN.feld("schneidtechnik").auswahl == f.auswahl
    assert SCHEMA_VERSION >= 98


print("ALLE OK" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
