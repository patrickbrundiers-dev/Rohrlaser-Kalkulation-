"""Strukturbaum mit 3D im Baugruppen-Editor (Verbesserung D1, Patrick 24.10.2026 „3d baum“):
- STEP-Import: das Netz einer Position trägt die Einbaulage aller gleichen Körper ('lagen') und ihre Körpernummern
  ('koerper'); eine aus einem Nahtkandidaten übernommene Nahtgruppe merkt sich ihre Körper
- Reiter „Strukturbaum und 3D“: Baugruppe → Unterbaugruppen → Teile und Nahtgruppen, ganze Baugruppe in Einbaulage,
  Klick auf Unterbaugruppe, Teil oder Nahtgruppe hebt die Teile hervor
- Ziehen eines Teils auf eine Unterbaugruppe ändert die Zuordnung (Stück je Baugruppe bleibt)
- ohne 3D-Daten nur der Baum mit Hinweis
- Schweißnähte sichtbar (N1): Nahtkandidaten tragen den Nahtverlauf (STEP-JSON 1.16 'linien'), Vorschlag und
  übernommene Nahtgruppe behalten ihn, die 3D-Ansicht zeichnet Nähte (SN), offene Vorschläge (SV), gewählte Naht (SH)

Testdatei: tests/step_struktur/S03_Rahmen_geschweisst.step. Aufruf: python tests/test_baugruppe_baum.py
"""
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
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, netze=netze)
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

# ------------------------------------------------------------------ ohne 3D-Daten
d2 = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0})
d2.reiter.setCurrentIndex(d2.BAUM)
assert d2.ansicht3d is None and "Keine 3D-Daten" in d2.baum_info.text()
assert d2.baum.topLevelItem(0).childCount() >= len(teile)
ok("ohne 3D-Daten: Baum mit Hinweis")
print("Strukturbaum mit 3D: alle Tests bestanden.")
