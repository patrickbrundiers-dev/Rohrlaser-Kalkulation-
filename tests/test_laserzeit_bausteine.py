"""Laserzeit je Baustein kalibrieren (Phase 4 E7, Patrick 16.11.2026 „Alle Empfehlungen alle Phasen nacheinander“):
- Die Nachkalkulation speichert je Laserteil die Zeit je Baustein (Schneiden, Einstechen, Ecken, Verfahren,
  Nebenzeit), die Faktoren der Maschine und den Faktor Laserzeit.
- Je Maschine ab 10 Teilen: Faktoren je Baustein ≥ 0 nach kleinsten Quadraten; nur Vorschau, übernommen wird nur mit
  dem Knopf; Historie unter Kennwerte, zurücknehmbar.
- Faktoren in der Maschine wirken auf die Zeitanteile ihres Bausteins; leer = 1 (unverändert).

Aufruf: python tests/test_laserzeit_bausteine.py
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
from rohrlaser.kalibrierung_dialog import KalibrierDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# Anpassung mit verschiedenen Teilen: findet die wahren Faktoren (Schneiden 1,1, Einstechen 2, Neben 0,8)
import random  # noqa: E402
rnd = random.Random(7)
wahr = {"schneiden": 1.1, "einstechen": 2.0, "ecken": 1.0, "bewegen": 1.0, "neben": 0.8}
fl = []
for i in range(30):
    roh = {"schneiden": rnd.uniform(5, 60), "einstechen": rnd.uniform(0.5, 8), "ecken": rnd.uniform(0, 3),
           "bewegen": rnd.uniform(1, 10), "neben": rnd.uniform(2, 12)}
    soll = sum(roh.values()) + 1.0
    ist = 1.0 + sum(wahr[b] * roh[b] for b in roh)
    fl.append(dict(soll=soll, ist=ist * rnd.uniform(0.99, 1.01), roh=roh, f_laser=1.0, rest=1.0))
g, frei = kb._anpassen(fl, {b: 1.0 for b in wahr})
assert set(frei) == set(wahr) and all(abs(g[b] - wahr[b]) < 0.1 for b in wahr), g
assert kb._abweichung(fl, g) < 0.01 < kb._abweichung(fl, {b: 1.0 for b in wahr})
# Faktor Laserzeit 1,2 im Angebot: die Faktoren je Baustein kommen ohne ihn heraus
fl12 = [dict(f, f_laser=1.2, soll=f["rest"] + 1.2 * sum(f["roh"].values())) for f in fl]
g12, _ = kb._anpassen(fl12, {b: 1.0 for b in wahr})
assert all(abs(g12[b] * 1.2 - g[b]) < 0.1 for b in wahr), (g12, g)
# nur positive Faktoren
fl0 = [dict(f, ist=f["rest"] + 0.01) for f in fl]
assert all(x >= kb.GRENZEN[0] for x in kb._anpassen(fl0, {b: 1.0 for b in wahr})[0].values())
ok(f"E7 Anpassung: {', '.join(f'{b} {g[b]:.2f}' for b in g)}")

# Bausteine decken alle Zeitanteile genau einmal ab
assert sorted(rechnen.BAUSTEIN_VON) == sorted(rechnen.ZEITANTEILE)
m0 = db.kontext().maschinen["T11"]
assert rechnen.baustein_faktoren(m0) == {b: 1.0 for b in rechnen.BAUSTEINE}
a = {"gross": 10.0, "einstiche": 2.0, "neben": 3.0}
assert rechnen.baustein_faktoren_anwenden(a, m0) is a
assert rechnen.baustein_faktoren_anwenden(a, dict(m0, faktor_einstechen=2)) == {"gross": 10.0, "einstiche": 4.0,
                                                                                "neben": 3.0}
ok("Bausteine: alle Zeitanteile zugeordnet, Faktor leer = 1")

# ------------------------------------------------------------------ Nachkalkulation: Einstechen dauert doppelt so lang
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s.optimieren()
maschine = s.kopf["maschine"]
teile = s.nachkalk._teile_soll()
assert teile and all(isinstance(t["bausteine"], dict) and t["f_laser"] == 1.0 for t in teile)
for t in teile:
    nah = sum(t["bausteine"].values())
    assert nah <= t["soll_s"] * 1.5 + 1, (nah, t["soll_s"])
assert kb.vorschlaege_bausteine(db) == []


def ist_zeiten(tt):
    return {t["id"]: t["soll_s"] + t["bausteine"]["einstechen"] for t in tt}     # Einstechen × 2


s.nachkalk.setzen(teile=ist_zeiten(teile))
gespeichert = db.angebot(s.id)["nachkalkulation"]["soll"]["laufzeit"]
assert all(len(e) == 6 and isinstance(e[3], dict) for e in gespeichert)
v = kb.vorschlaege_bausteine(db)
assert len(v) == 1 and v[0]["status"] == "zu wenig Daten" and v[0]["n"] == len(teile)
while sum(x["n"] for x in kb.vorschlaege_bausteine(db)) < kb.MINDESTENS_BAUSTEINE:
    s2 = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    assert s2.optimieren()
    s2.nachkalk.setzen(teile=ist_zeiten(s2.nachkalk._teile_soll()))
v = kb.vorschlaege_bausteine(db)[0]
assert v["maschine"] == maschine and v["status"] == "ok", v
# das Beispielangebot hat nur wenige verschiedene Teile: Einstechen deutlich länger, Abweichung fast weg
assert "einstechen" in v["frei"] and v["neu"]["einstechen"] > 1.3, v["neu"]
assert v["nachher"] < v["vorher"] and v["nachher"] < 0.03, (v["vorher"], v["nachher"])
assert all(x >= kb.GRENZEN[0] for x in v["neu"].values())
ok(f"E7 {v['n']} Teile: Faktor Einstechen {v['neu']['einstechen']:.3f}, Abweichung "
   f"{100 * v['vorher']:.1f} % → {100 * v['nachher']:.1f} %")

# nur Vorschau: nichts geändert
assert not db.kontext().maschinen[maschine].get("faktor_einstechen")
b = kb.bericht_bausteine(db)
assert {x["baustein"] for x in b} == set(rechnen.BAUSTEINE) and abs(sum(x["anteil"] for x in b) - 1) < 1e-9

# ------------------------------------------------------------------ Knopf „Faktoren übernehmen“ und Zurücknehmen
k, tab, e = db.kontext(), db.tabellen(), db.einstellungen()
z1, _ = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, k, tab, e)
d = KalibrierDialog(None, db)
r = next(i for i, x in enumerate(d.bausteine) if x["maschine"] == maschine)
assert "→" in d.btab.item(r, 4).text()
hid = d.uebernehmen_bausteine(r)
assert hid and d.geaendert
k2 = db.kontext()
assert abs(k2.maschinen[maschine]["faktor_einstechen"] - v["neu"]["einstechen"]) < 1e-9
z2, _ = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, k2, db.tabellen(), db.einstellungen())
for a1, a2 in zip(z1, z2):
    if a1.get("laser_netto") and a1.get("zeit_einstiche"):
        assert abs(a2["zeit_einstiche"] - v["neu"]["einstechen"] * a1["zeit_einstiche"]) < 1e-6
        b1, b2 = rechnen.bausteine(a1), rechnen.bausteine(a2)
        assert all(abs(b2[b] - v["neu"][b] * b1[b]) < 1e-6 for b in rechnen.BAUSTEINE), (b1, b2)
h = next(x for x in kennwerte.historie(db) if x["id"] == hid)
assert h["quelle"] == kb.QUELLE_BAUSTEINE and "Abweichung" in h["begruendung"]
# danach: alte Faktoren = übernommene, die Abweichung mit ihnen ist schon klein
v2 = next(x for x in kb.vorschlaege_bausteine(db) if x["maschine"] == maschine)
assert v2["alt"]["einstechen"] == v["neu"]["einstechen"] and abs(v2["vorher"] - v["nachher"]) < 1e-6
assert kennwerte.zuruecknehmen(db, hid) >= 1
assert not db.kontext().maschinen[maschine].get("faktor_einstechen")
ok("E7 übernommen nur per Knopf, wirkt auf Einstechen, zurücknehmbar")

# alte Nachkalkulationen (Laufzeit ohne Bausteine) zählen nicht und stören nicht
kopf = db.angebot(s.id)
nk = dict(kopf["nachkalkulation"])
nk["soll"] = dict(nk["soll"], laufzeit=[e_[:3] for e_ in nk["soll"]["laufzeit"]])
db.nachkalkulation_speichern(s.id, nk)
n_neu = next(x for x in kb.vorschlaege_bausteine(db) if x["maschine"] == maschine)["n"]
assert n_neu == v["n"] - len(teile)
from rohrlaser import nachkalkulation  # noqa: E402
assert nachkalkulation.faelle_laserzeit_teil(db)
ok("E7 Nachkalkulationen vor dem 16.11.2026 ohne Bausteine zählen nicht")
print("Alle Prüfungen bestanden.")
