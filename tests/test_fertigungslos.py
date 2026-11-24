"""Prüft das Fertigungslos (Plan ArTube-Unterlagen A2, Patrick 12.11.2026): beauftragte Aufträge gemeinsam schneiden.
- L1 3 × 3.000 mm und 3 × 2.800 mm aus zwei Aufträgen: im Los 3 Stangen (je ein Paar) statt 3 + 2 einzeln
- L2 Kundenmaterial und Muster bleiben getrennt, Zukaufteile kommen nicht ins Los
- L3 Preise unverändert (Positionen und Ergebnis der Angebote bleiben wie sie sind)
- L4 verschiedene Maschinen bzw. nur ein Auftrag: verständlicher Fehler
- L5 Werkstattpapiere des Loses als PDF; Dialog im Reiter Fertigung mit Vorauswahl

Aufruf: python tests/test_fertigungslos.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import fertigungslos as fl  # noqa: E402
from rohrlaser.angebot import KUNDENMATERIAL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("fertigung_aktiv", "ja")
fenster = Hauptfenster(db, tmp, stumm=True)


def auftrag(kunde, laenge, stueck=3, extra=(), maschine="T11"):
    a = db.angebot_neu(dict(kunde=kunde, kundennr="1", maschine=maschine, stange=6000))
    db.position_neu(a, dict(pos=10, artikel=f"{kunde}-A", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=laenge, stueck=stueck, schneidweg=320, einstiche=2, a_schnitt=160, b_schnitt=160))
    for i, p in enumerate(extra, start=2):
        db.position_neu(a, dict(dict(pos=10 * i, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                                     stueck=2, schneidweg=320, einstiche=2, a_schnitt=160, b_schnitt=160), **p))
    db.vorgang_setzen(a, "Beauftragt")
    return a


a1 = auftrag("Meier", 3000)
a2 = auftrag("Schulze", 2800, extra=[dict(artikel="KM", material_herkunft=KUNDENMATERIAL), dict(artikel="MU", muster="ja")])
vorher = [(dict(db.angebot(a)), [dict(p) for p in db.positionen(a)]) for a in (a1, a2)]
assert {z["id"] for z in fl.kandidaten(db)} >= {a1, a2}

# ------------------------------------------------------------------ L1
los = fl.zusammenstellen(db, [a1, a2])
assert los["stangen_einzeln"] == 5 and los["stangen_los"] == 3, (los["stangen_einzeln"], los["stangen_los"])
assert all(len(s["teile"]) == 2 for s in los["ergebnis"]["stangen"])
arts = {t["artikel"] for s in los["ergebnis"]["stangen"] for t in s["teile"]}
assert any(x.endswith("/ Meier-A") for x in arts) and any(x.endswith("/ Schulze-A") for x in arts), arts
assert "3 Stangen im Los statt 5 einzeln (2 Stangen gespart)" in fl.zusammenfassung(los)
ok("L1 zwei Aufträge: 3 Stangen im Los statt 5 einzeln, je Stange ein Teil von jedem Auftrag")

# ------------------------------------------------------------------ L2
getrennt = " | ".join(los["getrennt"])
assert "KM: Kundenmaterial bleibt im Auftrag" in getrennt and "MU: Muster bleibt im Auftrag" in getrennt, getrennt
assert not any("KM" in x or "MU" in x for x in arts)
ok("L2 Kundenmaterial und Muster bleiben im eigenen Auftrag")

# ------------------------------------------------------------------ L3
for a, (k0, p0) in zip((a1, a2), vorher):
    assert [dict(p) for p in db.positionen(a)] == p0 and db.angebot(a).get("ergebnis") == k0.get("ergebnis")
ok("L3 Angebote, Positionen und Preise unverändert")

# ------------------------------------------------------------------ L4
for ids, text in (([a1], "mindestens zwei"), ([a1, auftrag("Anders", 1000, maschine="LT7")], "verschiedenen Maschinen")):
    try:
        fl.zusammenstellen(db, ids)
        raise AssertionError("kein Fehler")
    except fl.LosFehler as e:
        assert text in str(e), e
ok("L4 nur ein Auftrag bzw. verschiedene Maschinen: Meldung statt Los")

# ------------------------------------------------------------------ L5
pfad = fl.pdf_schreiben(tmp / "los.pdf", los)
assert pfad.is_file() and pfad.stat().st_size > 2000
from rohrlaser.fertigungslos_dialog import FertigungslosDialog  # noqa: E402
d = FertigungslosDialog(None, db, vorauswahl=(a1,))
assert d.gewaehlt() == [a1]
for i in range(d.liste.count()):
    if d.liste.item(i).data(Qt.UserRole) == a2:
        d.liste.item(i).setCheckState(Qt.Checked)
assert d.rechnen() and "3 Stangen im Los statt 5" in d.ergebnis.text() and d.pdf_knopf.isEnabled()
assert d.pdf(tmp / "los2.pdf", oeffnen=False).is_file()
next(d.liste.item(i) for i in range(d.liste.count()) if d.liste.item(i).data(Qt.UserRole) == a1).setCheckState(
    Qt.Unchecked)
assert not d.pdf_knopf.isEnabled()
ok("L5 Werkstattpapiere des Loses als PDF, Dialog mit Vorauswahl und Vergleich")
print("Alle Fertigungslos-Tests bestanden.")
