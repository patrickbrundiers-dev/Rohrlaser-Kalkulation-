"""Prüft die Laufzeit je Teil in der Nachkalkulation (Vorschlag V3b, 31.10.2026):
- L1 Tabelle je Laserteil mit Soll [s/Teil] und der Schneiddaten-Zeile (Werkstoff/Kategorie, Wandstärke bis, Gas)
- L2 alle Teile eingetragen -> Ist-Laserzeit daraus (ohne Feld „Laserzeit Ist“); nur ein Teil -> Laserzeit wie Soll
- L3 Kennwert-Quelle „laserzeit_teil“: Fall je Teil, Vorschlag je Schneiddaten-Zeile, Freigabe ändert nur diese Zeile
  (Vorschübe ÷ Faktor), Rücknahme stellt sie wieder her
- L4 „Rest wie geplant“ übernimmt die Laserzeit aus den Teilen, nicht das Soll

Aufruf: python tests/test_laufzeit_teil.py
"""
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
from rohrlaser import kennwerte, nachkalkulation as nk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# ------------------------------------------------------------------ L1 Tabelle
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s.optimieren()
teile = s.nachkalk._teile_soll()
assert teile and all(t["soll_s"] > 0 and len(t["schluessel"]) == 4 for t in teile)
s.nachkalk.neu_laden()
assert s.nachkalk.teile.rowCount() == len(teile)
assert "≤" in s.nachkalk.teile.item(0, 4).text()
ok(f"L1 {len(teile)} Laserteile mit Soll je Teil und Schneiddaten-Zeile")

# ------------------------------------------------------------------ L2 Ist-Laserzeit aus den Teilen
v0 = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, {}, kalk=s._rechnung())
laser0 = next(z for z in v0["zeilen"] if z["text"] == "Laserzeit")
it = s.nachkalk.teile.item(0, 1)
it.setText("1")                                         # nur ein Teil: Laserzeit bleibt wie geplant
v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, s.nachkalk.ist, kalk=s._rechnung())
assert next(z for z in v["zeilen"] if z["text"] == "Laserzeit")["erfasst"] == "nein"
s.nachkalk.setzen(teile={t["id"]: t["soll_s"] * 1.2 for t in teile})
v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, s.nachkalk.ist, kalk=s._rechnung())
laser = next(z for z in v["zeilen"] if z["text"] == "Laserzeit")
assert laser["erfasst"] == "ja" and abs(laser["ist_menge"] - 1.2 * laser0["soll_menge"]) < 1e-9, laser
assert db.angebot(s.id)["nachkalkulation"]["soll"]["laufzeit"]
ok("L2 alle Teile eingetragen -> Ist-Laserzeit = Σ Laufzeit × Stück; einzelnes Teil ändert die Laserzeit nicht")

# ------------------------------------------------------------------ L4 Rest wie geplant
ist, _ = nk.rest_wie_geplant(v, s.nachkalk.ist)
assert abs(ist["laser_h"] - 1.2 * laser0["soll_menge"]) < 1e-9
ok("L4 Rest wie geplant übernimmt die Laserzeit aus den Teilen")

# ------------------------------------------------------------------ L3 Kennwert-Vorschlag je Schneiddaten-Zeile
for f in (1.15, 1.2, 1.25, 1.2):                      # mit dem ersten zusammen 5 Aufträge
    s2 = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    assert s2.optimieren()
    s2.nachkalk.setzen(teile={t["id"]: t["soll_s"] * f for t in s2.nachkalk._teile_soll()})
vs = [x for x in kennwerte.vorschlaege(db, 5) if x["quelle"] == "laserzeit_teil"]
schl = {tuple(t["schluessel"]) for t in teile}
assert {x["schluessel"] for x in vs} == schl and all(x["status"] == "ok" for x in vs), vs
v1 = vs[0]
assert abs(v1["faktor"] - 1.2) < 1e-9
maschine, wer, wand, gas = v1["schluessel"]
vorher = {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten")}
hid = kennwerte.freigeben(db, v1, "Test: Laufzeit 20 % länger", "test")
nachher = {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten")}
geaendert = [i for i in vorher if vorher[i] != nachher[i]]
assert len(geaendert) >= 1 and all(abs(nachher[i] - round(vorher[i] / 1.2)) < 1e-9 for i in geaendert)
for i in geaendert:
    z = next(z for z in db.zeilen("schneiddaten") if z["id"] == i)
    assert z["maschinen_id"] == maschine and z["wand_bis"] == wand and (z.get("gas") or "") == gas
assert len(geaendert) < len(vorher)                     # nur diese Zeile, nicht alle der Maschine
assert kennwerte.zuruecknehmen(db, hid) > 0
assert {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten")} == vorher
ok("L3 Vorschlag je Schneiddaten-Zeile (Faktor 1,2), Freigabe ändert nur diese Zeile, Rücknahme")
print("Alle Prüfungen bestanden.")
