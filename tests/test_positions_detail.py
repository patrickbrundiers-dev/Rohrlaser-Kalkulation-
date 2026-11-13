"""UI-Modernisierung U4 (Patrick 13.11.2026, Konzeptbild): Arbeitsgänge je Position und Detailbereich.

Prüft: Kürzel der Arbeitsgänge (P Programmieren, L Laser, G Gewinde zusammengefasst, Vorschläge gelb, abgelehnte
fehlen); Spalte „Arbeitsgänge“ hinter der Stückzahl mit Tooltip; Detailbereich unter der Positionsliste zeigt für die
gewählte Position Arbeitsgänge, Material und Preis je Teil (gleich der Kalkulation) und lässt sich unter Ansicht
abschalten; Kacheln Laserzeit, Arbeitszeit und Deckungsbeitrag in der Übersicht; der Verkaufspreis bleibt gleich.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_fenster  # noqa: E402
from rohrlaser import arbeitsgaenge as ag  # noqa: E402
from rohrlaser import positions_detail as pd  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten():
    for _ in range(3):
        QApplication.processEvents()
        QTest.qWait(20)


# ---------------------------------------------------------------- Kürzel
zeilen = [dict(arbeitsgang="Laser schneiden", status=ag.IM_ANGEBOT),
          dict(arbeitsgang="Gewinde M8", status=ag.IM_ANGEBOT, menge=2.0),
          dict(arbeitsgang="Gewinde M6", status=ag.ZU_PRUEFEN),
          dict(arbeitsgang="Entgraten", status=ag.AUTOMATISCH),
          dict(arbeitsgang="Pulverbeschichten", status=ag.VORSCHLAG),
          dict(arbeitsgang="Verzinken", status=ag.ABGELEHNT)]
e = pd.eintraege(zeilen, prog_min=5, laser_s=11.8)
assert [x["kuerzel"] for x in e] == ["P", "L", "E", "Pb", "G"], e
assert e[0]["text"] == "Programmieren 5 min" and e[1]["text"] == "Laser 11,8 s"
assert e[3]["art"] == pd.VORSCHLAG and e[2]["art"] == pd.GERECHNET
assert e[4]["text"] == "Gewinde 2× M8, M6 · prüfen" and e[4]["art"] == pd.PRUEFEN, e[4]
assert "Verzinken" not in pd.tooltip(e) and "? Pb: Pulverbeschichten · Vorschlag" in pd.tooltip(e)
assert pd.kuerzel("Rohr sägen") == "S" and pd.kuerzel("Xyz") == "X"
ok("Kürzel: P, L, E, Pb, G (Gewinde zusammengefasst), Vorschlag gelb, abgelehnte fehlen")

# ---------------------------------------------------------------- Angebot
po = Path(tempfile.mkdtemp(prefix="pos_detail_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1920, 1040)
f.show()
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
warten()
preis = s._verkauf()
m = s.pos_modell
c = next(i for i, (art, _) in enumerate(m.spalten) if art == "arbeitsgaenge")
c_stueck = next(i for i, (art, x) in enumerate(m.spalten) if art == "feld" and x.name == "stueck")
assert c == c_stueck + 1 and m.headerData(c, Qt.Horizontal) == "Arbeitsgänge"
assert not s.pos_ansicht.isColumnHidden(c)
r = next(i for i, p in enumerate(m.daten) if p.get("profil_id"))
liste = m.data(m.index(r, c), Qt.ItemDataRole.UserRole)
assert [x["kuerzel"] for x in liste][:2] == ["P", "L"], liste
assert "Laser" in m.data(m.index(r, c), Qt.ItemDataRole.ToolTipRole)
assert isinstance(s.pos_ansicht.itemDelegateForColumn(c), pd.ArbeitsgangDelegate)
ok("Spalte „Arbeitsgänge“ hinter der Stückzahl, Kürzel als Kästchen, Namen im Tooltip")

# ---------------------------------------------------------------- Detailbereich
# nach dem Öffnen steht die erste Position im Detailbereich, aktuell aber nicht markiert (Prüfrundgang 13.11.2026)
assert s.pos_detail.isVisible() and s.pos_ansicht.currentIndex().row() == 0
assert not s.pos_ansicht.selectionModel().selectedRows()
s.pos_ansicht.setCurrentIndex(m.index(r, 0))
warten()
d = s.pos_detail
assert d.isVisible()
p = m.daten[r]
assert f"POS. {p['pos']}" in d.titel.text() and "Laser" in d.ag.text() and "+ Arbeitsgang" in d.ag.text()
assert p["profil_id"] in d.material.text()
kalk = s._kalk_zeile(p)
assert kalk and kalk["preis_teil"] > 0
assert pd._z(kalk["preis_teil"]) + " €" in d.preis.text(), (kalk["preis_teil"], d.preis.text())
f.positions_detail(False)
warten()
assert not d.isVisible() and db.einstellung(angebot_fenster.DETAIL_EINSTELLUNG) is False
f.positions_detail(True)
warten()
assert d.isVisible() and db.einstellung(angebot_fenster.DETAIL_EINSTELLUNG) is not False
ok("Detailbereich: Arbeitsgänge, Material, Preis je Teil wie in der Kalkulation; Ansicht schaltet ihn ab und an")

# ---------------------------------------------------------------- Kacheln der Übersicht
k = s.uebersicht_bereich.kennzahl
assert k["laserzeit"].text() and k["arbeitszeit"].text() and "€" in k["deckung"].text(), \
    (k["laserzeit"].text(), k["arbeitszeit"].text(), k["deckung"].text())
assert "%" in k["deckung"].text()
ok(f"Übersicht: Laserzeit {k['laserzeit'].text()}, Arbeitszeit {k['arbeitszeit'].text()}, "
   f"Deckungsbeitrag {k['deckung'].text()}")

s.neu_laden()
warten()
assert s._verkauf() == preis, (s._verkauf(), preis)
ok("Rechnung unverändert")
print("Alle Tests OK")
