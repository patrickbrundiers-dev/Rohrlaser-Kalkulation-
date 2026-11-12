"""Reiter Optimierung (Plan X6, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“, Übernehmen nur als neue Fassung).

- Vorschläge einheitlich: Lieferlänge, Lager, Maschine, Schneiddaten prüfen; nur mit gerechnetem Vorteil
- das Angebot bleibt unverändert, „Als neue Fassung übernehmen“ legt eine Fassung mit der Lieferlänge an
- Schneiddaten prüfen erst ab 3 Aufträgen und 10 % mittlerer Abweichung, ohne Übernehmen

Aufruf: python tests/test_optimierung_seite.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import optimierungsvorschlaege as ov  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


# Schneiddaten prüfen ohne Angebot
schl = ["T11", "S235-10219", 3.0, "O2"]
teile = [dict(schluessel=schl, soll_s=60.0, stueck=10)]
faelle = [dict(schluessel=schl, soll=60.0, ist=72.0, angebot=f"A{i}") for i in range(3)]
v = ov.schneiddaten(teile, faelle)
assert len(v) == 1 and v[0]["aktion"] is None and "20 % länger" in v[0]["nachweis"], v
assert abs(v[0]["zeit_s"] + 60 * 10 * 0.2) < 1e-9          # 2 min mehr Laserzeit (negativ gespart)
assert ov.schneiddaten(teile, faelle[:2]) == []                                     # erst ab 3 Aufträgen
assert ov.schneiddaten(teile, [dict(f, ist=63.0) for f in faelle]) == []            # 5 % < 10 %
ok("Schneiddaten prüfen: ab 3 Aufträgen und 10 % Abweichung, ohne Übernehmen")
liste = [dict(maschine="T11", moeglich=True, verkauf=1000.0, laser_h=2.0),
         dict(maschine="LT7", moeglich=True, verkauf=900.0, laser_h=1.5),
         dict(maschine="T03", moeglich=False, verkauf=500.0, laser_h=1.0)]
m = ov.maschinen(liste, "T11")
assert len(m) == 1 and m[0]["aktion"] == dict(typ="maschine", maschine="LT7") and m[0]["kosten"] == 100.0
assert ov.maschinen(liste, "LT7") == []                                              # schon die günstigste mögliche
ok("Maschine: nur mögliche und günstigere, nicht mögliche nie")

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("laenge_vergleich", "ja")
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=12000))
fenster = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=3100.0,
                          stueck=30, schneidweg=200, einstiche=1))
s = fenster.angebot_oeffnen(aid)
assert s.optimierung_vorschlaege(maschinen=False) == []                              # nicht optimiert
assert s.optimieren()
idx = [s.reiter.tabText(i) for i in range(s.reiter.count())]
assert "Optimierung" in idx, idx
vorher = (db.angebot(aid)["laengenwahl"], len(db.positionen(aid)))
vs = s.optimierung_seite.laden(maschinen=False)
lief = [x for x in vs if x["art"] == ov.LIEFERLAENGE]
assert lief and lief[0]["material"] > 0 and lief[0]["aktion"]["typ"] == "laenge", vs
assert (db.angebot(aid)["laengenwahl"], len(db.positionen(aid))) == vorher          # Original unverändert
alle = s.optimierung_vorschlaege(maschinen=True)          # mit Maschinenvergleich (alle Maschinen neu gerechnet)
assert all(x["kosten"] is None or x["kosten"] > 0 for x in alle if x["art"] != ov.SCHNEIDDATEN)
ok(f"Lieferlänge: {lief[0]['titel']}, {ov.text(lief[0], 'material')} Material gespart")
neu = s.optimierung_seite.uebernehmen(lief[0])
assert neu and neu != aid
k = db.angebot(neu)
assert k["laengenwahl"] and lief[0]["aktion"]["laenge"] in k["laengenwahl"].values(), k["laengenwahl"]
assert db.angebot(aid)["ersetzt_durch"] == k["nummer"] and not db.angebot(aid)["laengenwahl"]
ok(f"als neue Fassung {k['nummer']} übernommen, Original unverändert")
print("Optimierung stimmt.")
