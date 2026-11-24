"""Maschine je Position (MACH-006 Variante B, Patrick 13.11.2026 „Alle Empfehlungen“), Paket 3:

- N1 Nachkalkulation: Laufzeit je Teil mit der Schneiddaten-Zeile der Maschine der Position (Schlüssel LT7 für die
  abweichende Position), Soll-Laserzeit je Maschine, Ist-Stunden mit dem mittleren Satz des Solls bewertet;
  ohne abweichende Maschine unverändert
- N2 Kennwerte und Kalibrierung: Fälle je Teil zählen für die Schneiddaten ihrer Maschine (Vorschlag für LT7);
  die Laserzeit des ganzen Auftrags (Maschine, Kategorie; Bandbreite; Rüsten) zählt nur bei einer Maschine
- N3 Auswertung nach Maschine: ein Auftrag mit zwei Maschinen zählt in beiden Gruppen

Aufruf: python tests/test_maschine_position_p3.py   (QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import kalibrierung as kb, nachkalkulation as nk, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
f = Hauptfenster(db, tmp, stumm=True)


def angebot(m_b):
    a = db.angebot_neu(dict(kunde="Beispiel GmbH", maschine="T03", stange=6000, skonto=0))
    db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                            stueck=40, schneidweg=200, einstiche=1))
    db.position_neu(a, dict(pos=20, artikel="B", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                            stueck=30, schneidweg=250, einstiche=2, maschine=m_b))
    s = f.angebot_oeffnen(a)
    assert s.optimieren()
    return s


# ------------------------------------------------------------------ N1
s0 = angebot(None)
t0 = s0.nachkalk._teile_soll()
assert {t["schluessel"][0] for t in t0} == {"T03"}
v0 = nk.vergleich(s0.kopf, s0.positionen, s0.ergebnis, s0.k, s0.tabellen, s0.einst, {}, kalk=s0._rechnung())
assert list(v0["laser_je_maschine"]) == ["T03"] and abs(v0["satz"] - s0._rechnung()[1]["satz_laser"]) < 1e-12

s1 = angebot("LT7")
t1 = s1.nachkalk._teile_soll()
assert {t["artikel"]: t["schluessel"][0] for t in t1} == {"A": "T03", "B": "LT7"}, t1
v1 = nk.vergleich(s1.kopf, s1.positionen, s1.ergebnis, s1.k, s1.tabellen, s1.einst, {"laser_h": 1.0},
                  kalk=s1._rechnung())
je = v1["laser_je_maschine"]
assert set(je) == {"T03", "LT7"} and all(h > 0 for h in je.values())
laser = next(z for z in v1["zeilen"] if z["text"] == "Laserzeit")
assert abs(laser["soll_menge"] - sum(je.values())) < 1e-9
assert abs(laser["ist"] - laser["soll"] / laser["soll_menge"]) < 1e-9          # 1 h × mittlerer Satz des Solls
s1.nachkalk.setzen(teile={t["id"]: t["soll_s"] * 1.2 for t in t1})
assert "Soll-Laserzeit je Maschine" in s1.nachkalk.ergebnis.text()
ok(f"N1 Nachkalkulation: Laufzeit je Teil B mit Schneiddaten der LT7, Soll-Laserzeit T03 {je['T03']:.3f} h + "
   f"LT7 {je['LT7']:.3f} h, Ist mit mittlerem Satz")

# ------------------------------------------------------------------ N2
st = db.angebot(s1.id)["nachkalkulation"]["soll"]
assert st["maschinen"] == ["T03", "LT7"]
assert db.angebot(s0.id).get("nachkalkulation") in (None, {}) or \
    not (db.angebot(s0.id)["nachkalkulation"].get("soll") or {}).get("maschinen")
faelle = nk.faelle_laserzeit_teil(db)
assert {x["schluessel"][0] for x in faelle} == {"T03", "LT7"}, faelle
for _ in range(4):               # genug Fälle für einen Vorschlag
    s = angebot("LT7")
    s.nachkalk.setzen(teile={t["id"]: t["soll_s"] * 1.2 for t in s.nachkalk._teile_soll()}, werte={"laser_h": 1.0})
vs = [v for v in kb.vorschlaege(db) if v["quelle"] == kb.QUELLE_TEIL]
assert any(v["schluessel"][0] == "LT7" and v["status"] == "ok" for v in vs), [(v["schluessel"], v["status"]) for v in vs]
assert not any(x["schluessel"][0] == "LT7" for x in nk.faelle_laserzeit(db))
assert not nk.faelle_ruesten(db) and not nk.laserzeit_je_maschine(db, 1)
assert kb.laserzeit_band(db, "T03") is None
ok(f"N2 Kalibrierung: Vorschlag für die Schneiddaten der LT7 aus {len([x for x in nk.faelle_laserzeit_teil(db) if x['schluessel'][0] == 'LT7'])} "
   "Teilen; Auftrags-Laserzeit mit zwei Maschinen zählt nicht für Kategorie, Band und Rüsten")

# ------------------------------------------------------------------ N3
gr = {z["gruppe"] for z in nk.auswertung(db, "maschine")["zeilen"]}
assert {"T03", "LT7"} <= gr, gr
ok("N3 Auswertung nach Maschine: Aufträge mit zwei Maschinen in beiden Gruppen")
assert rechnen  # Import für die Lesbarkeit der Schlüssel
print("Alle Prüfungen bestanden.")
