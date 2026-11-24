"""Schneiddaten aus Ist-Zeiten kalibrieren (Plan Phase 3 und 4, Paket D, Patrick 13.11.2026 „Alles einbauen“):

- D1 MACH-005: Vorschlag je Wandstufe aus der Laufzeit je Teil, übernommen nur per Knopf: Vorschübe ÷ Faktor,
  Quelle „Nachkalkulation“, Stand heute; Rücknahme unter Kennwerte stellt auch Quelle und Stand wieder her
- D2 MACH-012: Bandbreite der Laserzeit (10.–90. Perzentil Ist ÷ Soll) als zweite Zeile der Kachel Laserzeit
- D3 MACH-004: Vorschlag je Wandbereich (bis 3 / 3–6 / über 6 mm), gilt für alle Zeilen des Bereichs
- ohne genug Fälle: kein Übernehmen

Aufruf: python tests/test_kalibrierung.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import kalibrierung as kb, kennwerte  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


assert kb.bereich(2) == "bis 3 mm" and kb.bereich(3) == "bis 3 mm" and kb.bereich(4) == "3–6 mm"
assert kb.bereich(8) == "über 6 mm" and kb.band([1.1, 1.2]) is None
u, o = kb.band([1.0, 1.1, 1.2, 1.3, 1.4])
assert abs(u - 1.04) < 1e-9 and abs(o - 1.36) < 1e-9
ok("Wandbereiche, Bandbreite = 10. bis 90. Perzentil (ab 3 Fällen)")

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
assert not kb.vorschlaege(db)
s = None
for f in (1.15, 1.2, 1.25, 1.2, 1.3):
    s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    assert s.optimieren()
    s.nachkalk.setzen(teile={t["id"]: t["soll_s"] * f for t in s.nachkalk._teile_soll()})

vs = kb.vorschlaege(db)
stufen = [v for v in vs if v["quelle"] == kb.QUELLE_TEIL]
bereiche = [v for v in vs if v["quelle"] == kb.QUELLE_BEREICH]
assert stufen and bereiche and all(v["status"] == "ok" for v in vs), [(v["schluessel"], v["status"]) for v in vs]
v1 = stufen[0]
assert abs(v1["faktor"] - 1.2) < 1e-9 and v1["n"] >= 5 and v1["band"][0] < 1.2 < v1["band"][1]
assert v1["zeilen"] and all(n == max(1.0, round(a / 1.2)) for _, _, a, n in v1["zeilen"] if a is not None)
assert {v["schluessel"][2] for v in bereiche} <= {t for _, t in kb.BEREICHE}
ok(f"D1/D3 {len(stufen)} Vorschläge je Wandstufe und {len(bereiche)} je Wandbereich, Faktor 1,2, Bandbreite, "
   "neue Vorschübe in der Vorschau")

# ------------------------------------------------------------------ D1 Übernehmen per Knopf
seite = next(x for x in fenster.seiten if x.t.name == "schneiddaten")
assert seite.kalibrier_knopf.text() == "Kalibrieren …"
gesehen = {}


def bedienen(d):
    r = next(i for i, v in enumerate(d.vorschlaege) if v["quelle"] == kb.QUELLE_TEIL)
    d.tab.selectRow(r)
    assert d.uebernehmen_knopf.isEnabled()
    gesehen["v"] = d.vorschlaege[r]
    gesehen["hid"] = d.uebernehmen()


vorher = {z["id"]: dict(z) for z in db.zeilen("schneiddaten")}
d = seite.kalibrieren(dialog=bedienen)
assert d.geaendert and gesehen["hid"]
ids = {i for i, _, _, _ in gesehen["v"]["zeilen"]}
heute = datetime.date.today().isoformat()
for z in db.zeilen("schneiddaten"):
    if z["id"] in ids:
        assert z["quelle"] == "Nachkalkulation" and z["datum"] == heute, z
        assert z["vorschub_gross"] == max(1.0, round(vorher[z["id"]]["vorschub_gross"] / 1.2))
    else:
        assert z == vorher[z["id"]]
h = next(x for x in kennwerte.historie(db) if x["id"] == gesehen["hid"])
assert f"Kalibrierung aus {gesehen['v']['n']} Fällen" in h["begruendung"] and h["quelle"] == kb.QUELLE_TEIL
assert kennwerte.zuruecknehmen(db, gesehen["hid"]) > 0
assert {z["id"]: dict(z) for z in db.zeilen("schneiddaten")} == vorher
ok("D1 Übernehmen: nur diese Zeile, Vorschübe ÷ 1,2, Quelle Nachkalkulation, Stand heute; Rücknahme stellt alles her")

# ------------------------------------------------------------------ D3 Wandbereich
vb = next(v for v in kb.vorschlaege(db) if v["quelle"] == kb.QUELLE_BEREICH)
hid = kb.uebernehmen(db, vb, "test")
geaendert = [z for z in db.zeilen("schneiddaten") if z != vorher[z["id"]]]
assert geaendert and all(kb.bereich(z["wand_bis"]) == vb["schluessel"][2] and z["quelle"] == "Nachkalkulation"
                         for z in geaendert)
assert len(geaendert) == len(vb["zeilen"])
kennwerte.zuruecknehmen(db, hid)
ok(f"D3 Wandbereich {vb['schluessel'][2]}: {len(geaendert)} Zeilen des Bereichs, zurücknehmbar")

zu_wenig = kb.vorschlaege(db, mindest_n=50)
assert zu_wenig and all(v["status"] != "ok" for v in zu_wenig)
try:
    kb.uebernehmen(db, zu_wenig[0], "test")
    raise AssertionError("ohne genug Fälle übernommen")
except ValueError:
    pass
ok("zu wenig Fälle: kein Übernehmen")

# ------------------------------------------------------------------ D2 Bandbreite in der Kachel
b = kb.laserzeit_band(db, s.kopf.get("maschine"))
assert b and b["n"] == 5 and b["unten"] < b["median"] < b["oben"], b
t = kb.band_text(b, 120)
assert t.startswith("erfahrungsgemäß ") and "(5 Aufträge)" in t, t
assert kb.band_text(None, 120) == "" and kb.laserzeit_band(db, "gibt es nicht") is None
s2 = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s2.optimieren()
kachel = s2.uebersicht_bereich.kennzahl["laserzeit"].text()
assert "erfahrungsgemäß" in kachel and "5 Aufträge" in kachel, kachel
ok("D2 Kachel Laserzeit: zweite Zeile „erfahrungsgemäß von–bis (5 Aufträge)“, keine Zahl ändert sich")
print("Alle Prüfungen bestanden.")
