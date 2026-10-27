"""Prüfstatus je STEP-Merkmal (Wettbewerbsvergleich P0-3, step_pruefung.py): sicher / prüfen / nicht erkannt,
Sonderprofile nie still als Standardprofil, Gewinde-Vorschlag als Annahme, Rohdaten und Korrekturen bleiben nach
erneutem Öffnen erhalten, defekte STEP-Dateien führen nicht zum Absturz, Angebots-Check nennt offene Merkmale.

Aufruf: python tests/test_step_pruefung.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import angebot_check, step, step_pruefung as sp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

# ------------------------------------------------------------------ Regeln ohne Messung
SICHER = dict(profilform="Quadratrohr", abm_a="40", abm_b="40", wandstaerke="2", laenge="1000", ende_a_gerade="1",
              ende_b_gerade="1", innen_konturen="0", innen="0",
              sicherheit="profil=sicher;wandstaerke=sicher;achse=sicher;laenge=sicher;konturen=sicher")
m = sp.merkmale(SICHER)
assert [x["merkmal"] for x in m] == ["Profilform", "Querschnitt", "Wandstärke", "Länge", "Ende A", "Ende B",
                                     "Innenkonturen"]
assert sp.gesamt(m) == sp.SICHER and sp.kurztext(m) == "alle sicher"
m = sp.merkmale(dict(SICHER, sicherheit="profil=sicher;wandstaerke=unsicher;laenge=wahrscheinlich"))
st = {x["merkmal"]: x["status"] for x in m}
assert st["Wandstärke"] == st["Länge"] == sp.PRUEFEN and st["Profilform"] == sp.SICHER
m = sp.merkmale(dict(SICHER, profilform="Sonderprofil (offen)"))
assert {x["merkmal"]: x["status"] for x in m}["Profilform"] == sp.NICHT          # nie still als Standardprofil
assert sp.gesamt(sp.merkmale(dict(SICHER, profilform=""))) == sp.NICHT
assert sp.merkmale(dict(fehler="Datei defekt"))[0]["status"] == sp.NICHT
m = sp.merkmale(SICHER, "4xM6")
assert m[-1]["merkmal"] == "Gewinde-Vorschlag" and m[-1]["status"] == sp.PRUEFEN and "Kernloch" in m[-1]["grund"]
geh = dict(SICHER, ende_b_gerade="0", konturen_liste=json.dumps(
    [dict(art="Ende B", form="Gehrung", gehrung=45, richtung=0)]))
assert {x["merkmal"]: x for x in sp.merkmale(geh)}["Ende B"]["status"] == sp.SICHER
ausk = dict(SICHER, ende_a_gerade="0", konturen_liste=json.dumps([dict(art="Ende A", form="komplex")]))
assert {x["merkmal"]: x for x in sp.merkmale(ausk)}["Ende A"]["status"] == sp.PRUEFEN
nicht_ausg = dict(SICHER, sicherheit="profil=sicher;konturen=nicht ausgewertet")
assert {x["merkmal"]: x for x in sp.merkmale(nicht_ausg)}["Innenkonturen"]["status"] == sp.PRUEFEN

# Korrektur nur an gemessenen Feldern und nur bei Änderung
w = sp.speicherwert(SICHER)
assert sp.korrektur(w, "bezeichnung", "a", "b") == w and sp.korrektur(w, "laenge", 1000, 1000) == w
w2 = sp.korrektur(w, "laenge", 1000, 998.5)
assert sp.lesen(w2)["korrekturen"][0]["feld"] == "laenge" and sp.lesen(w2)["korrekturen"][0]["neu"] == 998.5
assert sp.korrektur(None, "laenge", 1, 2) is None and sp.lesen("kaputt") is None

# ------------------------------------------------------------------ echte Messung (STEP-Import), auch defekte Datei
tmp = Path(tempfile.mkdtemp())
ordner = tmp / "step"
ordner.mkdir()
for name in ("REF02_QR40x40x2_L1000.step", "REF09_RE60x40x2_Gehrung45.step", "REF18_Z60x40x4_L500.step"):
    (ordner / name).write_bytes((HIER / "step_referenz" / name).read_bytes())
(ordner / "kaputt.step").write_text("ISO-10303-21;\nHEADER;\nDas ist keine STEP-Datei\n", encoding="utf-8")
(ordner / "leer.step").write_bytes(b"")
skript = HIER.parent / "programm" / "step_messung" / "step_messen.py"
r = subprocess.run([sys.executable, str(skript), "--ausgabe", str(tmp / "m.txt"), str(ordner)], capture_output=True,
                   text=True, timeout=600)
assert (tmp / "m.txt").is_file(), r.stderr[-2000:]
mw = step.lies_messwerte(tmp / "m.txt")
nach_datei = {}
for x in mw:
    nach_datei.setdefault(x["datei"], []).append(x)
for name in ("kaputt.step", "leer.step"):          # defekt: gemeldet, kein Absturz, Merkmal nicht erkannt
    assert name in nach_datei and nach_datei[name][0].get("fehler"), nach_datei.get(name)
    assert sp.gesamt(sp.merkmale(nach_datei[name][0])) == sp.NICHT
qr = sp.merkmale(nach_datei["REF02_QR40x40x2_L1000.step"][0])
assert sp.gesamt(qr) == sp.SICHER, qr
geh = {x["merkmal"]: x for x in sp.merkmale(nach_datei["REF09_RE60x40x2_Gehrung45.step"][0])}
assert "Gehrung" in geh["Ende A"]["wert"] + geh["Ende B"]["wert"], geh
z = sp.merkmale(nach_datei["REF18_Z60x40x4_L500.step"][0])
assert sp.gesamt(z) in (sp.PRUEFEN, sp.NICHT), z            # Z-Profil: kein Standardprofil, nicht still sicher

db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
erg = step.uebernehmen([dict(x) for x in mw if not x.get("fehler")], [], k, db.zeilen("gewinde"), None,
                       "S235-10219", 2, neue_profile=True)
pos = {p["artikel"]: p for p in erg["positionen"]}
p_qr = next(p for a, p in pos.items() if a.startswith("REF02"))
d = sp.lesen(p_qr["step_merkmale"])
assert d["roh"]["profilform"] == "Quadratrohr" and d["datei"].startswith("REF02") and d["korrekturen"] == []
aid = db.angebot_neu()
for p in erg["positionen"]:
    db.position_neu(aid, {n: v for n, v in p.items() if not n.startswith("_")})
pid = next(p["id"] for p in db.positionen(aid) if p["artikel"].startswith("REF02"))
db.position_aendern(pid, "laenge", 995.0)          # von Hand korrigiert
db.position_aendern(pid, "bezeichnung", "Riegel")  # kein gemessenes Feld: keine Korrektur
db.schliessen()

# ------------------------------------------------------------------ erneut öffnen: Korrekturen bleiben
db = Datenbank(tmp / "rohrlaser.db")
p = next(p for p in db.positionen(aid) if p["id"] == pid)
d = sp.lesen(p["step_merkmale"])
assert [(x["feld"], x["alt"], x["neu"]) for x in d["korrekturen"]] == [("laenge", 1000.0, 995.0)], d["korrekturen"]
assert p["laenge"] == 995.0

# Z-Profil ist ein Kantteil (Blech): ohne Zukaufliste keine Position, nie still als Rohr
assert not any(a.startswith("REF18") for a in pos)
# Angebots-Check: offene Merkmale als Hinweis, nach Bestätigung nicht mehr
q09 = next(q for q in db.positionen(aid) if q["artikel"].startswith("REF09"))
assert not sp.offen(q09)                          # Gehrung 45° sicher erkannt
db.position_aendern(q09["id"], "step_merkmale", sp.speicherwert(dict(SICHER, sicherheit="profil=wahrscheinlich")))
pos_db = db.positionen(aid)
offen = [q for q in pos_db if sp.offen(q)]
assert offen
pk = angebot_check.punkte(dict(kunde="X"), pos_db, ["OK"] * len(pos_db), "aktuell", {})
hinweis = [x for x in pk if "STEP-Merkmale" in x.text]
assert len(hinweis) == 1 and hinweis[0].art == angebot_check.HINWEIS, pk
for q in offen:
    db.position_aendern(q["id"], "step_merkmale", sp.bestaetigen(q["step_merkmale"], "PB"))
pk = angebot_check.punkte(dict(kunde="X"), db.positionen(aid), ["OK"] * len(pos_db), "aktuell", {})
assert not [x for x in pk if "STEP-Merkmale" in x.text]

# ------------------------------------------------------------------ Fenster im Angebot
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
r = next(i for i, q in enumerate(s.positionen) if q["id"] == pid)
dlg = s.step_merkmale_pruefen([r], dialog=lambda d: None)
assert dlg.merkmale.rowCount() >= 7 and dlg.korrekturen.rowCount() == 1 and dlg.roh.rowCount() > 5
r2 = next(i for i, q in enumerate(s.positionen) if q["artikel"].startswith("REF09"))
db.position_aendern(s.positionen[r2]["id"], "step_merkmale", sp.speicherwert(dict(SICHER, hinweise="Test")))
s.neu_laden()
dlg = s.step_merkmale_pruefen([r2], dialog=lambda d: d.bestaetigen())
assert sp.lesen(next(q for q in db.positionen(aid) if q["id"] == s.positionen[r2]["id"])["step_merkmale"])["geprueft"]
p_ohne = db.position_neu(aid, dict(artikel="von Hand", profil_id="QR 40x40x3", laenge=500, stueck=1))
s.neu_laden()
assert s.step_merkmale_pruefen([next(i for i, q in enumerate(s.positionen) if q["id"] == p_ohne)]) is None
print("test_step_pruefung OK")
