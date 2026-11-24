"""Zurücksetzen auf den Ursprung in Schweißbaugruppe und Satz in 3D (Patrick 03.11.2026, Freigabe 1a 2a 3a 4a):
- B1 STEP-Import merkt den Stand der Schweißbaugruppe (baugruppe['ursprung'] mit Zuordnung der Teile).
- B2 Editor der Schweißbaugruppe: Unterbaugruppe, Nahtgruppe, Arbeitsgang dazu, Teil herausgenommen, Bezeichnung
  geändert -> „wie aus STEP“ bringt den Importstand (Teile wieder drin), „Zurücksetzen rückgängig“ den Stand davor,
  „wie beim Öffnen“; der Importstand bleibt beim Speichern erhalten.
- B3 Satz in 3D: Steckverbindungen und Längsnaht per Klick -> „wie aus STEP“ ohne beide, rückgängig, wie beim Öffnen.
- B4 Schweißbaugruppe ohne Importstand (von Hand): Eintrag „wie aus STEP“ aus, „wie beim Öffnen“ geht.

Aufruf: python tests/test_editor_ursprung_bg.py
"""
import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if find_spec("OCP") is None:
    print("OCP fehlt: übersprungen")
    sys.exit(0)
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import baugruppe, editor_ursprung as eu, step  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.satz3d import Satz3dDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def einlesen(datei):
    t = tmp / datei.stem
    t.mkdir()
    step_messen.main(["--ausgabe", str(t / "m.txt"), "--json", str(t / "m.json"), "--netze", str(t / "netze"),
                      str(datei)])
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(t / "m.txt"), t / "netze"), t / "m.json")
    for x in mw:
        x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
    db = Datenbank(t / "b.db")
    k = db.kontext()
    erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    db.profile_anlegen(erg["profile"])
    a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
    for p in erg["positionen"]:
        netz = p.pop("_netz", None)
        p.pop("_zukauf", None)
        pid = db.position_neu(a, p)
        if netz:
            db.netz_speichern(pid, netz)
    return db, db.positionen(a), db.netze(a), db.kontext().profile


# ------------------------------------------------------------------ B1 Importstand
db, positionen, netze, profile = einlesen(HIER / "step_struktur" / "S03_Rahmen_geschweisst.step")
bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
bg = baugruppe.lesen(bgp["baugruppe"])
u = bg[eu.URSPRUNG]
teile = [p for p in positionen if baugruppe.zuordnung(p)[0] == bg["id"]]
assert len(u["teile"]) == len(teile) >= 2 and u["kopf"]["bezeichnung"] == bgp["bezeichnung"], u["teile"]
assert u["knoten"] == bg["knoten"] and "ursprung" not in u
ok(f"B1 STEP-Import merkt den Stand der Schweißbaugruppe ({len(teile)} Teile)")

# ------------------------------------------------------------------ B2 Editor der Schweißbaugruppe
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=netze, profile=profile)
start = d.daten()
drin = sorted(t["_id"] for t in d.teile if t["drin"])
d._ursprung_pruefen()
assert not d.ursprung_aktionen[eu.OEFFNEN].isEnabled() and d.ursprung_aktionen[eu.IMPORT].isEnabled()
assert not d.ursprung_aktionen["zurueck"].isEnabled()
d.knoten_neu("Hand")
d.naht_neu()
d.arbeitsgang_neu()
r = next(i for i, t in enumerate(d.teile) if t["drin"])
d.teile[r]["drin"] = False
d.teile_tab.aufbauen()
d.bezeichnung.setText("Von Hand")
d.aktualisieren()
geaendert = d.daten()
assert len(geaendert["naehte"]) == len(start["naehte"]) + 1 and len(geaendert["knoten"]) == len(start["knoten"]) + 1
assert d.ursprung(eu.IMPORT, fragen=False)
e = d.daten()
assert e["knoten"] == u["knoten"] and e["naehte"] == u["naehte"] and e["arbeitsgaenge"] == u["arbeitsgaenge"], e
assert sorted(t["_id"] for t in d.teile if t["drin"]) == drin and d.bezeichnung.text() == u["kopf"]["bezeichnung"]
assert e[eu.URSPRUNG] == u, "Importstand bleibt beim Speichern"
assert d.teile_tab.rowCount() == len(d.teile) and d.naht_tab.rowCount() == len(e["naehte"])
assert d.ursprung_rueckgaengig()
assert d.daten()["naehte"] == geaendert["naehte"] and d.bezeichnung.text() == "Von Hand"
assert not d.teile[r]["drin"]
assert d.ursprung(eu.OEFFNEN, fragen=False)
assert d.daten() == start and sorted(t["_id"] for t in d.teile if t["drin"]) == drin
assert not d.ursprung(eu.OEFFNEN, fragen=False), "nichts geändert"
ok("B2 Schweißbaugruppe: wie aus STEP (Struktur, Nahtgruppen, Arbeitsgänge, Teile, Bezeichnung), rückgängig, "
   "wie beim Öffnen; Importstand bleibt")

# ------------------------------------------------------------------ B3 Satz in 3D
satz = [dict(q, satz="S1") for q in positionen if q.get("art") != BAUGRUPPE]
s = Satz3dDialog(None, "S1", satz, profile=profile, netze=netze, daten={})
s.laengsnaehte[s.teile[0]["_id"]] = 90.0
s.knicke.append(dict(koerper=[], text="Test"))
s.saetze_feld.setValue(4)
s.aktualisieren()
s._ursprung_pruefen()
assert all(a.isEnabled() for w, a in s.ursprung_aktionen.items() if w != "zurueck")
assert s.ursprung(eu.IMPORT, fragen=False)
assert not s.laengsnaehte and not s.knicke and not s.bg["steckverbindungen"] and s.saetze_feld.value() == 4
assert s.ursprung_rueckgaengig() and s.laengsnaehte and s.knicke
assert s.ursprung(eu.OEFFNEN, fragen=False)
assert not s.laengsnaehte and not s.knicke and s.saetze_feld.value() == 1
assert s.werte()["naehte"] == {} and s.werte()["knicke"] == []
ok("B3 Satz in 3D: wie aus STEP ohne Längsnaht/Knickrahmen, rückgängig, wie beim Öffnen (Anzahl Sätze zurück)")

# ------------------------------------------------------------------ B4 Baugruppe von Hand
hand = dict(bgp, baugruppe=baugruppe.speichern({k: v for k, v in bg.items() if k != eu.URSPRUNG}))
h = BaugruppeDialog(None, hand, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db)
h._ursprung_pruefen()
assert not h.ursprung_aktionen[eu.IMPORT].isEnabled() and not h.ursprung(eu.IMPORT, fragen=False)
h.naht_neu()
h.aktualisieren()
assert h.ursprung(eu.OEFFNEN, fragen=False) and h.daten()["naehte"] == bg["naehte"]
h.ursprung_k.menu()
for w in (d, s, h):
    w.close()
ok("B4 Schweißbaugruppe ohne Importstand: nur wie beim Öffnen")
print("Alle Prüfungen bestanden.")
