"""STEP-Viewer mit Rollen und Abwicklung (Master-Auftrag Patrick 25.11.2026 „Abwicklungskern für den STEP-/CAD-Import
grundlegend erweitern“, Paket P5):
- Kern ohne Qt: Rolle/Stufe je Konturzeile, Farben nach Rolle (Anfang und Ende verschieden) und Schneidbarkeit,
  Konturen ausblenden (ohne_konturen), 2D-Abwicklung mit Treffer, Handkorrektur der Rolle
- Fenster: Spalten Rolle/Schneidbarkeit, Abwicklung unter dem 3D, Auswahl 2D -> Liste, Rolle ein/aus, Rolle ändern

Aufruf: python tests/test_konturen_viewer_2511.py   (QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen as sm  # noqa: E402
from rohrlaser import konturrolle as kr  # noqa: E402
from rohrlaser import step_viewer as sv  # noqa: E402

REF = HIER / "step_referenz_konturen"


def messwerte(name):
    return dict(zip(sm.SPALTEN, sm.zeilen(REF / f"{name}.step")[0]))


# ---------------------------------------------------------------- Kern
m = messwerte("R07_RR42-4x2_Sattel60-3")
zeilen = sv.konturen(m)
assert [(z["rolle"], z["stufe"]) for z in zeilen] == [(kr.ANFANG, 1), (kr.ANSCHLUSS, 2)], zeilen
linien, legende = sv.konturfarben(zeilen, "Rolle")
assert linien["kontur:0"] != linien["kontur:1"] and [t for t, _ in legende][0].startswith("Anfangsschnitt"), legende
_, leg_s = sv.konturfarben(zeilen, "Schneidbarkeit")
assert [t for t, _ in leg_s] == ["1 eindeutig", "2 wahrscheinlich"], leg_s
linien_aus, _ = sv.konturfarben(zeilen, "Rolle", {kr.ANFANG})
assert "kontur:0" not in linien_aus and "kontur:1" in linien_aus
abw = sv.abwicklung_2d(m, zeilen)
assert abs(abw["umfang"] - 3.14159265 * 42.4) < 0.01 and len(abw["linien"]) == 2, abw["umfang"]
assert sv.treffer_2d(abw, 20.0, 0.5) == "kontur:0" and sv.treffer_2d(abw, 60.0, 150.0) is None
assert len(sv.abwicklung_2d(m, zeilen, {kr.ANSCHLUSS})["linien"]) == 1
netz = {"l": {"K": [[0, 0, 0, 1, 0, 0], [0, 1, 0, 1, 1, 0]]}, "li": {"K": ["kontur:0", "kontur:1"]}, "t": {}}
weg = sv.ohne_konturen(netz, {"kontur:0"})
assert weg["l"]["K"] == [[0, 1, 0, 1, 1, 0]] and weg["li"]["K"] == ["kontur:1"] and len(netz["l"]["K"]) == 2
assert sv.ohne_konturen(netz, set()) is netz
assert sv.rolle_setzen(m, 1, kr.ENDE) and sv.konturen(m)[1]["rolle"] == kr.ENDE and sv.konturen(m)[1]["hand"]
assert not sv.rolle_setzen(m, 1, "Quatsch") and not sv.rolle_setzen(m, 9, kr.ENDE)
assert sv.rolle_setzen(m, 1, None) and sv.konturen(m)[1]["rolle"] == kr.ANSCHLUSS and not sv.rolle_setzen(m, 1, None)
# Handkorrektur gemerkt und beim Import (neue Messung) wieder gesetzt
class _Db:
    def __init__(self):
        self.e = {}

    def einstellung(self, k):
        return self.e.get(k)

    def einstellung_setzen(self, k, v):
        self.e[k] = v


db = _Db()
assert sv.rolle_setzen(m, 1, kr.ENDE) and sv.rollen_merken(db, m)
neu = messwerte("R07_RR42-4x2_Sattel60-3")
assert sv.rollen_gelernt_anwenden([neu], db.einstellung(sv.ROLLE_GELERNT)) == 1
assert sv.konturen(neu)[1]["rolle"] == kr.ENDE and sv.konturen(neu)[1]["hand"]
assert sv.rolle_setzen(m, 1, None) and sv.rollen_merken(db, m) and not db.einstellung(sv.ROLLE_GELERNT)
info = dict(sv.kontur_info(zeilen[1], m))
assert info["Rolle"] == kr.ANSCHLUSS and info["Schneidbarkeit"].startswith("2 wahrscheinlich"), info
m6 = messwerte("R06_QR60x3_Durchbrueche")
z6 = sv.konturen(m6)
assert [z["rolle"] for z in z6].count(kr.DURCHBRUCH) == 2 and abs(sv.umfang(m6) - 240) < 1e-6
print("OK: Kern: Rollen, Farben (Anfang ≠ Ende), Ausblenden, Abwicklung 2D, Handkorrektur")

# ---------------------------------------------------------------- Fenster
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.step_viewer_fenster import KONTUR_SPALTEN, SP_ROLLE, StepViewer  # noqa: E402

app = QApplication.instance() or QApplication([])
ORDNER = HIER.parent / "programm"
assert step.messprogramm(ORDNER), "STEP-Messung fehlt"
v = StepViewer(None, None, programmordner=ORDNER)
assert v.oeffnen(REF / "R07_RR42-4x2_Sattel60-3.step")
v.warten()
assert v.zeilen and v.konturen.columnCount() == len(KONTUR_SPALTEN)
assert v.konturen.item(1, SP_ROLLE).text() == kr.ANSCHLUSS, v.konturen.item(1, SP_ROLLE).text()
assert v.farbe_nach.currentText() == "Rolle" and v.abwicklung.abw and len(v.abwicklung.abw["linien"]) == 2
v._2d_gewaehlt("kontur:1")
assert v.konturen.currentRow() == 1 and v.abwicklung.markiert == "kontur:1"
v.rolle_zeigen(kr.ANFANG, False)
assert kr.ANFANG in v.rollen_aus and len(v.abwicklung.abw["linien"]) == 1
v.rolle_zeigen(kr.ANFANG, True)
assert not v.rollen_aus and len(v.abwicklung.abw["linien"]) == 2
assert v.rolle_aendern(1, kr.ENDE) and v.konturen.item(1, SP_ROLLE).text().startswith(kr.ENDE)
assert v.rolle_aendern(1, None) and v.konturen.item(1, SP_ROLLE).text() == kr.ANSCHLUSS
v.farbe_nach.setCurrentText("Schneidbarkeit")
v.zeigen(None)
assert not v.abwicklung.isVisible() and v.abwicklung.abw is None
v.close()
print("OK: Fenster: Spalten, Abwicklung unter dem 3D, Auswahl 2D -> Liste, ein/aus, Rolle ändern")
print("Alle Tests bestanden.")
