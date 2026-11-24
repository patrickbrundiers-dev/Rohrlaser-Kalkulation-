"""Aluminium genauer (Phase 7, Patrick 16.11.2026: „bei Aluminium passen die Zeiten von PROfirst oder BLM/Adige nicht,
mindestens doppelt“; Freigabe „Faktoren je Werkstoff, Alu 2,0“):
- Faktoren je Baustein zusätzlich je Werkstoffgruppe (Edelstahl, Aluminium, Buntmetall) wirken auf die allgemeinen
- Aluminium vorbelegt: Schneiden, Einstechen, Ecken × 2,0; Stahl unverändert
- Kalibrierung je Maschine und Werkstoffgruppe: Aluminium lernt seine eigenen Faktoren, Übernahme schreibt die
  Aluminium-Felder

Aufruf: python tests/test_aluminium_laserzeit.py
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
from rohrlaser import kalibrierung as kb, kennwerte, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
k = db.kontext()
t11 = k.maschinen["T11"]
assert (t11["faktor_schneiden_alu"], t11["faktor_einstechen_alu"], t11["faktor_ecken_alu"]) == (2, 2, 2)
assert not t11.get("faktor_bewegen_alu") and not t11.get("faktor_schneiden_es")
f_alu = rechnen.baustein_faktoren(t11, "Aluminium")
assert f_alu == {"schneiden": 2, "einstechen": 2, "ecken": 2, "bewegen": 1, "neben": 1}, f_alu
assert rechnen.baustein_faktoren(t11, "Stahl") == {b: 1.0 for b in rechnen.BAUSTEINE}
assert rechnen.baustein_faktoren(dict(t11, faktor_schneiden=1.1), "Aluminium")["schneiden"] == 2.2
ok("Aluminium vorbelegt × 2 (Schneiden, Einstechen, Ecken), wirkt auf die allgemeinen Faktoren")

ALU = "AW6082-T6"
assert ALU in k.werkstoffe and rechnen.kategorie(ALU, k) == "Aluminium"


def kalk(db, werkstoff, extra=None):
    for x in db.zeilen("maschinen"):
        for n_, w in (extra or {}).items():
            db.aendern("maschinen", x["id"], n_, w)
    a = db.angebot_neu(dict(beispiel_angebot.KOPF, nummer=None))
    for p in beispiel_angebot.POSITIONEN:
        db.position_neu(a, dict(p, werkstoff_id=werkstoff, satz=None, je_satz=None))
    kopf, pos = db.angebot(a), db.positionen(a)
    k_, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, pos, k_, tab, db.einstellungen())
    zl, su = rechnen.kalkulation(kopf, pos, erg, k_, tab, rechnen.einstellungen_angebot(kopf, db.einstellungen()))
    return [z for z in zl if z.get("laser_netto")], su


alu2, _ = kalk(Datenbank(tmp / "a2.db"), ALU)
alu1, _ = kalk(Datenbank(tmp / "a1.db"), ALU, {f: None for f in ("faktor_schneiden_alu", "faktor_einstechen_alu",
                                                                     "faktor_ecken_alu")})
st2, _ = kalk(Datenbank(tmp / "s2.db"), "S235-10219")
st1, _ = kalk(Datenbank(tmp / "s1.db"), "S235-10219", {f: None for f in ("faktor_schneiden_alu",
                                                                          "faktor_einstechen_alu", "faktor_ecken_alu")})
for a2, a1 in zip(alu2, alu1):
    b2, b1 = rechnen.bausteine(a2), rechnen.bausteine(a1)
    for b in rechnen.BAUSTEINE:
        assert abs(b2[b] - f_alu[b] * b1[b]) < 1e-6, (b, b1, b2)
assert all(abs(a["laser_netto"] - b["laser_netto"]) < 1e-9 for a, b in zip(st2, st1))
q = sum(a["laser_netto"] for a in alu2) / sum(a["laser_netto"] for a in alu1)
assert 1.4 < q <= 2.0, q
ok(f"Beispielangebot in Aluminium: Laserzeit × {q:.2f} (Schneiden, Einstechen, Ecken × 2), Stahl unverändert")

# Kalibrierung je Werkstoff: Aluminium-Teile mit Ist = Soll + Schneiden (also Schneiden noch 1,5 × länger)
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
for p in db.positionen(s.id):
    db.position_aendern(p["id"], "werkstoff_id", ALU)
s = fenster.angebot_oeffnen(s.id)
assert s.optimieren()
teile = s.nachkalk._teile_soll()
assert teile and all(t["faktoren"]["schneiden"] == 2 for t in teile)


def ist_zeiten(tt):
    return {t["id"]: t["soll_s"] + 0.5 * t["bausteine"]["schneiden"] for t in tt}


s.nachkalk.setzen(teile=ist_zeiten(teile))
v = kb.vorschlaege_bausteine(db)
assert len(v) == 1 and v[0]["kategorie"] == "Aluminium" and v[0]["alt"]["schneiden"] == 2, v
while next(x for x in kb.vorschlaege_bausteine(db) if x["kategorie"] == "Aluminium")["n"] < kb.MINDESTENS_BAUSTEINE:
    s2 = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    for p in db.positionen(s2.id):
        db.position_aendern(p["id"], "werkstoff_id", ALU)
    s2 = fenster.angebot_oeffnen(s2.id)
    assert s2.optimieren()
    s2.nachkalk.setzen(teile=ist_zeiten(s2.nachkalk._teile_soll()))
# dazu Stahl-Teile ohne Abweichung: eigene Zeile „allgemein“
s3 = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s3.optimieren()
s3.nachkalk.setzen(teile={t["id"]: t["soll_s"] for t in s3.nachkalk._teile_soll()})
alle = kb.vorschlaege_bausteine(db)
assert {x["kategorie"] for x in alle} == {None, "Aluminium"}
v = next(x for x in alle if x["kategorie"] == "Aluminium")
assert v["status"] == "ok" and "schneiden" in v["frei"] and v["neu"]["schneiden"] > 2.2, v["neu"]
assert v["nachher"] < v["vorher"] and v["nachher"] < 0.03, (v["vorher"], v["nachher"])
ok(f"Kalibrierung je Werkstoff: Aluminium Schneiden 2,0 → {v['neu']['schneiden']:.2f} aus {v['n']} Teilen, "
   "Stahl eigene Zeile")

from rohrlaser.kalibrierung_dialog import KalibrierDialog  # noqa: E402
d = KalibrierDialog(None, db)
r = next(i for i, x in enumerate(d.bausteine) if x["kategorie"] == "Aluminium")
assert "Aluminium" in d.btab.item(r, 0).text()
hid = d.uebernehmen_bausteine(r)
k2 = db.kontext()
assert abs(k2.maschinen["T11"]["faktor_schneiden_alu"] - v["neu"]["schneiden"]) < 1e-9
assert not k2.maschinen["T11"].get("faktor_schneiden")
h = next(x for x in kennwerte.historie(db) if x["id"] == hid)
assert "Aluminium" in h["begruendung"]
assert kennwerte.zuruecknehmen(db, hid) >= 1
assert db.kontext().maschinen["T11"]["faktor_schneiden_alu"] == 2
ok("Übernahme schreibt nur die Aluminium-Faktoren, Stahl bleibt; zurücknehmbar")
# Zeit je Teil offen gelegt (Detailbereich unter den Positionen)
from rohrlaser.positions_detail import zeit_zeilen, _z  # noqa: E402
zz_ = zeit_zeilen(alu2[0])
texte = [t.strip() for t, *_ in zz_]
assert "Schneiden" in texte and "Einstechen" in texte and "Laserzeit je Teil" in texte, texte
lz = next(w for t, w, *_ in zz_ if t == "Laserzeit je Teil")
assert lz == f"{_z(alu2[0]['laser_netto'], 1)} s"
ein = next(e for t, _, _, e in zz_ if t == "Einstechen")
assert "Einstiche" in ein
bst = rechnen.bausteine(alu2[0])
schn = next(w for t, w, *_ in zz_ if t == "Schneiden")
assert schn == f"{_z(bst['schneiden'] - (alu2[0].get('zeit_gravur_anbau') or 0) + (alu2[0].get('zeit_gravur_anbau') or 0), 1)} s"
assert zeit_zeilen({}) == [] and zeit_zeilen(dict(laser_netto=5, zeit_manuell="ja"))[0][0] == "Laserzeit von Hand"
ok("Zeit je Teil: Bausteine, Laserzeit und umgelegte Zeiten im Detailbereich")
print("Aluminium: alle Tests bestanden.")
