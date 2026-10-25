"""Montagefolge und Montageblatt (Plan „Baugruppen automatisch und innovativ“, P3; Patrick 25.10.2026 „Alle a“):
- Explosion: jedes gesteckte Teil rückt gegen seine Steckrichtung heraus und nimmt den Versatz seines Teils mit;
  Richtung als Achse der Datei
- Satz S03 im Fenster Satz in 3D: Knopf Montage, Schieber Schritt zeigt nur die Teile bis zum Schritt (aktueller blau),
  Explosion verschiebt die Körper, Text nennt Teil, Arbeitsschritt und Richtung
- Werkstattpapiere: je Satz mit Steckverbindungen ein Montageblatt (Skizze, Schritte zum Abhaken)

Aufruf: python tests/test_montagefolge.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import step, steck_montage as sm  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

try:
    from pypdf import PdfReader  # noqa: E402
except ImportError:
    PdfReader = None

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Explosion
def lage(o, z, x):
    return list(o) + list(z) + list(x)


koerper = {"1": ("A", lage((0, 0, 0), (1, 0, 0), (0, 1, 0))), "2": ("A", lage((0, 500, 0), (1, 0, 0), (0, 1, 0))),
           "3": ("Q", lage((50, 0, 0), (0, 1, 0), (1, 0, 0)))}
stoesse = [dict(aufnahme=1, stecker=3, ende="a"), dict(aufnahme=2, stecker=3, ende="b")]
k = sm.kanten(koerper, stoesse, [("A", "Q", "a"), ("A", "Q", "b")])
r = sm.reihenfolge(k)
enden = {"1": ((0, 0, 0), (1000, 0, 0)), "2": ((0, 500, 0), (1000, 500, 0)), "3": ((50, 0, 0), (50, 500, 0))}
v = sm.explosion(r["schritte"], k, enden)
assert r["ok"] and [x for x, _ in r["schritte"]] == ["1", "3", "2"], r
assert v["1"] == (0.0, 0.0, 0.0) and v["3"][1] == 500.0 and v["2"][1] == 1000.0, v      # Kette: 2 nimmt 3 mit
assert sm.richtung_text((0, -1, 0)) == "−Y" and sm.richtung_text(None) == ""
t = sm.schritt_texte(r["schritte"], k, koerper, {"A": "Pos. 1", "Q": "Pos. 2"}, {("1", "3"): "1"})
assert t[0]["text"] == "hinlegen (Anfang)" and t[1]["text"] == "in Pos. 1 stecken (Marke 1)", t
assert t[2]["text"] == "auf Pos. 2 aufstecken" and t[2]["richtung"] == "−Y", t
ok("Explosion gegen die Steckrichtung (Kette nimmt den Versatz mit), Texte je Schritt mit Marke und Richtung")

# ------------------------------------------------------------------ Satz S03
tmp = Path(tempfile.mkdtemp())
datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
ziel = tmp / datei.stem
step_messen.main(["--ausgabe", str(ziel) + ".txt", "--json", str(ziel) + ".json", "--netze", str(ziel), str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(str(ziel) + ".txt"), ziel), str(ziel) + ".json")
for x in mw:
    x.update(_stueck=1, _uebernehmen=True, _saetze=1)
db = Datenbank(tmp / "montage.db")
db.einstellung_setzen("steck_marke", "ja")
f = Hauptfenster(db, stumm=True)
kx = db.kontext()
erg = step.uebernehmen(mw, [], kx, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
for satz, daten in (erg.get("satz_daten") or {}).items():
    db.satz_daten_speichern(a, satz, daten)
seite = f.angebot_oeffnen(a)
gesehen = {}


def bedienen(d):
    d.steck_alle(melden=False)
    gesehen["alle"] = d.zeigen()
    an = d.ansicht3d
    an.montage_knopf.setChecked(True)
    gesehen["n"] = d._montage["n"]
    an.montage_schritt.setValue(1)
    gesehen["eins"] = d.zeigen()
    gesehen["text"] = an.montage_text.text()
    an.montage_schritt.setValue(an.montage_schritt.maximum())
    an.montage_explosion.setValue(100)
    d.zeigen()
    gesehen["lagen"] = [list(lg) for _, lg, _ in d._koerper]
    an.montage_explosion.setValue(0)
    d.zeigen()
    gesehen["lagen0"] = [list(lg) for _, lg, _ in d._koerper]
    an.montage_knopf.setChecked(False)
    gesehen["aus"] = d.zeigen()
    d._ok()
    return d.result()


assert seite.satz_3d(0, dialog=bedienen)
assert gesehen["n"] >= 3 and gesehen["eins"] < gesehen["alle"] and gesehen["aus"] == gesehen["alle"], gesehen
assert gesehen["text"].startswith(f"Schritt 1/{gesehen['n']}: Pos.") and "hinlegen" in gesehen["text"], gesehen["text"]
verschoben = sum(1 for a_, b_ in zip(gesehen["lagen"], gesehen["lagen0"]) if a_[:3] != b_[:3])
assert verschoben >= gesehen["n"] - 1, (verschoben, gesehen["n"])
ok(f"Satz S03: Montage mit {gesehen['n']} Schritten, Schritt 1 zeigt {gesehen['eins']} von {gesehen['alle']} Körpern, "
   f"Explosion verschiebt {verschoben} Körper")

# ------------------------------------------------------------------ Werkstattpapiere mit Montageblatt
seite = f.angebot_oeffnen(a)
blaetter = seite.montageblaetter()
assert len(blaetter) == 1 and blaetter[0]["titel"].startswith("Satz ") and blaetter[0]["ok"], blaetter
assert any("Marke" in s_["text"] for s_ in blaetter[0]["schritte"]), blaetter[0]["schritte"]
assert seite.optimieren()
pfad = seite.werkstatt_pdf()
assert pfad and Path(pfad).exists()
if PdfReader:
    text = "".join(x.extract_text() for x in PdfReader(str(pfad)).pages)
    assert "Montageblatt Satz" in text and "hinlegen" in text, text[-800:]
ok("Werkstattpapiere: Montageblatt je Satz mit Skizze und Schritten (Marke, Richtung)")
db.schliessen()
print("Montagefolge und Montageblatt: alle Tests bestanden.")
