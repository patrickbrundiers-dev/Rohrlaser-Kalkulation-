"""Strukturbaum mit 3D im Baugruppen-Editor (Verbesserung D1, Patrick 24.10.2026 „3d baum“):
- STEP-Import: das Netz einer Position trägt die Einbaulage aller gleichen Körper ('lagen') und ihre Körpernummern
  ('koerper'); eine aus einem Nahtkandidaten übernommene Nahtgruppe merkt sich ihre Körper
- Reiter „Strukturbaum und 3D“: Baugruppe → Unterbaugruppen → Teile und Nahtgruppen, ganze Baugruppe in Einbaulage,
  Klick auf Unterbaugruppe, Teil oder Nahtgruppe hebt die Teile hervor
- Ziehen eines Teils auf eine Unterbaugruppe ändert die Zuordnung (Stück je Baugruppe bleibt)
- ohne 3D-Daten nur der Baum mit Hinweis
- Schweißnähte sichtbar (N1): Nahtkandidaten tragen den Nahtverlauf (STEP-JSON 1.16 'linien'), Vorschlag und
  übernommene Nahtgruppe behalten ihn, die 3D-Ansicht zeichnet Nähte (SN), offene Vorschläge (SV), gewählte Naht (SH)
- 3D wie im Rohr-Editor (B1–B3, Patrick 24.10.2026): Rohre aus den Eingaben, Nähte als Raupe, Leiste mit
  Nur Gewähltes, Nähte, Darstellung, Messen
- Naht im 3D zeichnen (N2): Punkte anklicken (Linienzug), Länge, berührte Teile (Körper), Unterbaugruppe und Wanddicke
  ermittelt das Programm, daraus wird eine Nahtgruppe mit Nahtverlauf

Testdatei: tests/step_struktur/S03_Rahmen_geschweisst.step. Aufruf: python tests/test_baugruppe_baum.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import baugruppe, step  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ STEP-Import: Lagen und Körper je Position
datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
db = Datenbank(tmp / "baum.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for p in erg["positionen"]:
    netz = p.pop("_netz", None)
    p.pop("_zukauf", None)
    pid = db.position_neu(a, p)
    if netz:
        db.netz_speichern(pid, netz)
positionen = db.positionen(a)
netze = db.netze(a)
bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
teile = [p for p in positionen if p.get("bg_knoten")]
mehrfach = [p for p in teile if (p.get("je_knoten") or 1) > 1]
assert mehrfach, [(p.get("artikel"), p.get("je_knoten")) for p in teile]
for p in teile:
    n = entpacken(netze[p["id"]])
    assert len(n.get("lagen") or [n["lage"]]) == (p.get("je_knoten") or 1), (p.get("artikel"), n.get("lagen"))
    assert len(n["koerper"]) == (p.get("je_knoten") or 1)
koerper_alle = sum((len(entpacken(netze[p["id"]])["koerper"]) for p in teile), 0)
v = baugruppe.lesen(bgp["baugruppe"])["vorschlaege"]
stumpf = next(x for x in v if x["nahtart"] == "Stumpfnaht")
n = baugruppe.vorschlag_naht(stumpf)
assert len(n["koerper"]) == 2, n
assert stumpf.get("linien") and n["linien"] == stumpf["linien"], stumpf
assert all(len(z) >= 6 and len(z) % 3 == 0 for z in stumpf["linien"])
ok(f"STEP-Import: Netz je Position mit allen Lagen und Körpern ({koerper_alle} Körper), Nahtgruppe kennt ihre Körper")

# ------------------------------------------------------------------ Baum und 3D im Editor
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=netze)
d.vorschlaege_uebernehmen([d.bg["vorschlaege"].index(next(x for x in d.bg["vorschlaege"]
                                                         if x["nahtart"] == "Stumpfnaht"))])
naht = d.bg["naehte"][0]
assert naht["nahtart"] == "Stumpfnaht" and len(naht["koerper"]) == 2
d.reiter.setCurrentIndex(d.BAUM)
assert d.reiter.tabText(d.BAUM) == "Strukturbaum und 3D"
assert d.ansicht3d is not None and d.ansicht3d.ansicht.netz is not None
assert d.zeige_3d() == koerper_alle
wurzel = d.baum.topLevelItem(0)
kinder = [wurzel.child(i).data(0, Qt.UserRole) for i in range(wurzel.childCount())]
assert ("naht", naht["id"]) in kinder and sum(1 for x in kinder if x[0] == "teil") == len(teile), kinder
# Nahtgruppe: die zwei gestoßenen Rohre hervorgehoben (aus den Körpern der Nahtkandidaten)
d.baum.setCurrentItem(d.baum_items[("naht", naht["id"])])
assert len(d.baum_hervor) in (1, 2) and d.baum_hervor <= {p["id"] for p in teile}, d.baum_hervor
koerper_naht = set(naht["koerper"])
assert all(koerper_naht & set(entpacken(netze[pid])["koerper"]) for pid in d.baum_hervor)
assert "S" in d.ansicht3d.ansicht.netz["t"]                     # blau = hervorgehoben
# Schweißnähte: gewählte Naht rot (SH), übrige Vorschläge hellorange (SV), Nahtverlauf liegt am Modell
nl = d.ansicht3d.ansicht.netz["l"]
assert nl.get("SH") == naht["linien"] and "SV" in nl and "SN" not in nl, list(nl)
pk = d.ansicht3d.ansicht.netz["p"]
box = [(min(pk[k::3]) - 1, max(pk[k::3]) + 1) for k in range(3)]
assert all(box[k][0] <= z[i + k] <= box[k][1] for z in nl["SH"] for i in range(0, len(z), 3) for k in range(3))
assert all(x == (0.0, 0.0, 0.0) for x in d.ansicht3d.ansicht.netz["ln"]["SH"])
assert {"SH", "SV"} <= set(d.ansicht3d.ansicht.modell.arten)
# Teil wählen
t0 = mehrfach[0]
d.baum.setCurrentItem(d.baum_items[("teil", t0["id"])])
assert d.baum_hervor == {t0["id"]}
assert "SN" in d.ansicht3d.ansicht.netz["l"] and "SH" not in d.ansicht3d.ansicht.netz["l"]
# Ziehen: Teil in eine neue Unterbaugruppe mit Menge 2 → Stück je Unterbaugruppe halbiert, je Baugruppe gleich
je_alt = next(t for t in d.teile if t["_id"] == t0["id"])["je"]
kid = d.knoten_neu("Seite", 2)
assert d.teil_verschieben(t0["id"], kid)
t = next(t for t in d.teile if t["_id"] == t0["id"])
assert t["knoten"] == kid and t["je"] * 2 == je_alt, (t, je_alt)
it = d.baum_items[("teil", t0["id"])]
assert it.parent() is d.baum_items[("knoten", kid)] and it.text(2) == str(je_alt)
d.baum.setCurrentItem(d.baum_items[("knoten", kid)])
assert d.baum_hervor == {t0["id"]}
assert not d.teil_verschieben(t0["id"], kid)                      # schon dort
w = d.werte()
assert w["teile"][t0["id"]]["bg_knoten"] == baugruppe.zuordnung_text(d.bg["id"], kid)
ok("Reiter Strukturbaum und 3D: ganze Baugruppe in Einbaulage, Nahtgruppe/Teil/Unterbaugruppe hervorgehoben, "
   "Schweißnähte und Vorschläge sichtbar, Ziehen ordnet zu")

# Menge von Hand höher als Körper in der STEP-Datei: Hinweis, welche Teile nicht alle im 3D stehen
assert "Nicht alle Stück" not in d.ansicht3d.info.text()
tt = next(t for t in d.teile if t["_id"] == t0["id"])
je_vorher, kn_vorher = tt["je"], tt.get("knoten") or ""
d.teil_setzen(t0["id"], True, kn_vorher, je_vorher + 3)
d.zeige_3d()
assert "Nicht alle Stück im 3D" in d.ansicht3d.info.text() and f"von {(je_vorher + 3) * 2} Stück" in \
    d.ansicht3d.info.text(), d.ansicht3d.info.text()
d.teil_setzen(t0["id"], True, kn_vorher, je_vorher)
d.zeige_3d()
assert "Nicht alle Stück" not in d.ansicht3d.info.text()
ok("Hinweis, wenn ein Teil öfter vorkommt, als die STEP-Datei Körper hat")

# ------------------------------------------------------------------ Naht im 3D zeichnen (N2)
d.baum.setCurrentItem(d.baum_items[("bg", "")])
a3 = d.ansicht3d.ansicht
assert d.zeichnen_leiste.isVisibleTo(d) and not d.zeichnen_ok.isEnabled()
d.zeichnen_knopf.setChecked(True)
assert a3.messen and a3.mess_max == 0
zug = [tuple(z[i:i + 3]) for z in naht["linien"][:2] for i in range(0, len(z), 3)]
zug = [q for i, q in enumerate(zug) if i == 0 or q != zug[i - 1]]      # Ecke zwischen zwei Kanten nur einmal
assert len(zug) >= 3, zug
a3.messpunkte = list(zug) + [(9999.0, 9999.0, 9999.0)]
a3.punkt_zurueck()                                                      # letzten (falschen) Punkt zurück
assert a3.messpunkte == zug
d._zeichnen_stand()
assert d.zeichnen_ok.isEnabled() and "mm" in d.zeichnen_text.text()
soll = sum(math.dist(x, y) for x, y in zip(zug, zug[1:]))
assert abs(a3.abstand() - soll) < 1e-6
d.zeichnen_art.setCurrentText("Stumpfnaht")
anzahl = len(d.bg["naehte"])
nid = d.naht_aus_punkten()
assert len(d.bg["naehte"]) == anzahl + 1
neu = next(x for x in d.bg["naehte"] if x["id"] == nid)
assert neu["quelle"] == "3D" and neu["nahtart"] == "Stumpfnaht" and abs(neu["laenge"] - round(soll, 1)) < 0.05, neu
assert neu["koerper"] == sorted(naht["koerper"]), (neu, naht)          # dieselben zwei Rohre wie der Kandidat
assert neu.get("dicke") and neu.get("mass") == neu["dicke"], neu       # Wand aus dem Profil
assert len(neu["linien"]) == 1 and len(neu["linien"][0]) == 3 * len(zug)
assert d.baum.currentItem() is d.baum_items[("naht", nid)] and "SH" in a3.netz["l"]
assert a3.messen and a3.messpunkte == []                                # Zeichenmodus bleibt, Zug leer
# Punkte frei im Raum: keine Teile, Nahtgruppe der Baugruppe ohne Körper
nid2 = d.naht_aus_punkten([(9999.0, 0.0, 0.0), (9999.0, 50.0, 0.0)], nahtart="Kehlnaht")
neu2 = next(x for x in d.bg["naehte"] if x["id"] == nid2)
assert neu2["knoten"] == "" and "koerper" not in neu2 and neu2["laenge"] == 50.0
assert d.naht_aus_punkten([(0.0, 0.0, 0.0)]) is None
d.zeichnen_knopf.setChecked(False)
assert not a3.messen
ok("Naht im 3D zeichnen: Linienzug, Teile, Länge und Wand ermittelt, Nahtgruppe mit Nahtverlauf")

# ------------------------------------------------------------------ 3D wie im Rohr-Editor (B1–B3)
d3 = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=netze, profile=k.profile)
d3.reiter.setCurrentIndex(d3.BAUM)
v3 = d3.ansicht3d
rohre = d3._rohr_modelle()
assert rohre and set(rohre) <= {p["id"] for p in teile}, rohre             # B2: Rohre aus den Eingaben
assert "Rohre aus den Eingaben" in v3.info.text(), v3.info.text()
assert any(a in v3.ansicht.netz["t"] for a in ("SN", "SV")), list(v3.ansicht.netz["t"])   # B3: Raupen
neu, _ = d3.steck_alle(melden=False)
if neu:                                                                       # Stöße aus der Datei: Nasen im Modell
    st = {z["_st"] for z in d3.bg["steckverbindungen"] if z.get("_nasen") is not False}
    assert any(d3._rohr_modelle()[pid].get("nasen") for pid in st if pid in d3._rohr_modelle())
alle = d3.zeige_3d()
d3.baum.setCurrentItem(d3.baum_items[("teil", t0["id"])])
v3.nur_knopf.setChecked(True)                                                 # Nur Gewähltes: nur das Teil
assert d3.zeige_3d({t0["id"]}, "") < alle
v3.nur_knopf.setChecked(False)
v3.naehte_knopf.setChecked(False)                                             # Nähte aus
assert not {"SN", "SV", "SH"} & set(v3.ansicht.netz["t"]) and not v3.ansicht.netz["l"]
v3.naehte_knopf.setChecked(True)
v3.darstellung.setCurrentText("Durchsichtig")
assert v3.ansicht.darstellung == "Durchsichtig"
v3.messen_knopf.setChecked(True)                                              # Messen schaltet Naht zeichnen aus
assert v3.ansicht.messen and v3.ansicht.mess_max == 2 and not d3.zeichnen_knopf.isChecked()
d3.zeichnen_knopf.setChecked(True)                                            # und umgekehrt
assert not v3.messen_knopf.isChecked() and v3.ansicht.mess_max == 0
d3.zeichnen_knopf.setChecked(False)
assert v3.wuerfel is not None and v3.blick_knopf.menu() is not None
from rohrlaser.baugruppe_ansicht import in_lage  # noqa: E402
d3.laengsnaht_knopf.setChecked(True)                                          # Längsnaht per Klick (wie im Satz)
assert not d3.zeichnen_knopf.isChecked() and not v3.ansicht.messen
nr = next(i for i, (pid, _, _) in enumerate(d3._koerper_lage) if pid in rohre)
pid, lage, _ = d3._koerper_lage[nr]
w = d3._3d_geklickt(dict(id=f"teil:{nr}", punkt=in_lage((0.0, 30.0, 50.0), lage)))
assert w is not None and d3.laengsnaht_werte()[pid]["naht_winkel"] == w, (w, d3.laengsnaht_werte())
assert d3.werte()["naehte"][pid]["naht_quelle"] == "manuell"
assert v3.ansicht.netz["l"].get("NL"), v3.ansicht.netz["l"].keys()
d3.zeichnen_knopf.setChecked(True)                                            # Naht zeichnen schaltet sie aus
assert not d3.laengsnaht_knopf.isChecked()
d3.zeichnen_knopf.setChecked(False)
# Auswahl im 3D (Patrick 26.10.2026): Klick wählt das Teil (Baum und Teiletabelle mit), Strg+Klick dazu bzw. weg
assert d3.auswahl_leiste.isVisibleTo(d3) and not d3.auswahl_steck.isEnabled()
rohr_nr = [i for i, (p_, _, _) in enumerate(d3._koerper_lage) if p_ in rohre]
p1 = d3._koerper_lage[rohr_nr[0]][0]
p2 = next(d3._koerper_lage[i][0] for i in rohr_nr if d3._koerper_lage[i][0] != p1)
assert d3._3d_geklickt(dict(id=f"teil:{rohr_nr[0]}", punkt=(0, 0, 0)), strg=False) == p1
assert d3.wahl_3d == [p1] and d3.baum.currentItem() is d3.baum_items[("teil", p1)]
assert [d3.teile[r]["_id"] for r in d3.teile_tab.markierte()] == [p1]
assert d3.baum_hervor == {p1} and "blau" in v3.info.text()
nr2 = next(i for i in rohr_nr if d3._koerper_lage[i][0] == p2)
d3._3d_geklickt(dict(id=f"teil:{nr2}", punkt=(0, 0, 0)), strg=True)
assert d3.wahl_3d == [p1, p2] and d3.baum_hervor == {p1, p2} and d3.auswahl_steck.isEnabled()
assert sorted(d3.teile[r]["_id"] for r in d3.teile_tab.markierte()) == sorted([p1, p2])
anz = len(d3.bg["steckverbindungen"])
kennung = d3.steck_aus_3d()
assert kennung and len(d3.bg["steckverbindungen"]) == anz + 1
assert (d3.bg["steckverbindungen"][-1]["_auf"], d3.bg["steckverbindungen"][-1]["_st"]) == (p1, p2)
d3._3d_geklickt(dict(id=f"teil:{nr2}", punkt=(0, 0, 0)), strg=True)          # Strg+Klick nimmt es wieder weg
assert d3.wahl_3d == [p1] and not d3.auswahl_steck.isEnabled()
d3.baum.setCurrentItem(d3.baum.topLevelItem(0))                               # Klick im Baum: Auswahl aus dem Baum
assert d3.wahl_3d == [] and d3.baum_hervor == set()
ok("3D wie im Rohr-Editor: Rohre aus den Eingaben, Nähte als Raupe, Nur Gewähltes, Nähte aus, Darstellung, "
   "Messen, Längsnaht per Klick, Teile per Klick wählen und stecken")

# ------------------------------------------------------------------ ohne 3D-Daten
d2 = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0})
d2.reiter.setCurrentIndex(d2.BAUM)
assert d2.ansicht3d is None and "Keine 3D-Daten" in d2.baum_info.text()
assert not d2.zeichnen_leiste.isVisibleTo(d2)
assert d2.baum.topLevelItem(0).childCount() >= len(teile)
ok("ohne 3D-Daten: Baum mit Hinweis")
print("Strukturbaum mit 3D: alle Tests bestanden.")
