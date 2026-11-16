"""Teil wenden (Plan ArTube-Unterlagen G6/G8, Patrick 12.11.2026: gewendetes Duplikat, Stückzahl automatisch so
aufgeteilt, dass die wenigsten Stangen nötig sind; das Original bleibt ungedreht):
- T1 Ansicht des Schnittplans: Enden getauscht, Richtung der Gehrung und feste Naht gespiegelt
- T2 Aufteilen: Gehrungen legen sich mit gewendeten Teilen ineinander, weniger Verschnitt bzw. Stangen
- T3 Grenzen: Sichtseite (wenden = nein), Satz, gleiche Enden; Abstand zum Spannbereich von Ende A
- T4 Oberfläche: Teil wenden legt das Duplikat an (gleicher Artikel), Original weniger Stück, Werkstatt-Hinweis
- T5 Prüfregel „Teil löst sich nicht“ bei komplexem Ende B

Aufruf: python tests/test_wenden_artube.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import ausgabe, dfm, rechnen, stangenende, wenden  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


GEHRUNG = json.dumps(dict(winkel=45, richtung=90))

# ------------------------------------------------------------------ T1
p = dict(stueck=4, a_gerade="nein", a_ende=GEHRUNG, b_gerade=None, a_schnitt=180, b_schnitt=120, gewendet="ja")
q = wenden.ansicht(p)
assert q["b_gerade"] == "nein" and q["a_gerade"] is None and q["a_schnitt"] == 120 and q["b_schnitt"] == 180
assert json.loads(q["b_ende"])["richtung"] == 270 and q["a_ende"] is None and q["_gewendet"]
assert wenden.ansicht(dict(p, gewendet=None)) is not None and "_gewendet" not in wenden.ansicht(dict(p, gewendet=None))
assert wenden.spiegeln(0) == 0 and wenden.spiegeln(90) == 270 and wenden.spiegeln(180) == 180
ok("T1 gewendet: Enden getauscht, Gehrung „länger rechts“ wird „länger links“ (von Ende A gesehen)")

# ------------------------------------------------------------------ T2
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "w.db")
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="G1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=730,
                        stueck=16, schneidweg=320, einstiche=2, a_gerade="nein", a_ende=GEHRUNG))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab, ein = db.kontext(), db.tabellen(), db.einstellungen()
assert wenden.erlaubt(pos[0]) == ""
auf = wenden.aufteilen(kopf, pos, 0, k, tab, ein)
assert auf["gewendet"] > 0, auf
assert (auf["stangen"], round(auf["verlust"], 1)) < (auf["stangen_ohne"], round(auf["verlust_ohne"], 1)), auf
ok(f"T2 aufgeteilt: {16 - auf['gewendet']} + {auf['gewendet']} gewendet, {auf['stangen']} statt "
   f"{auf['stangen_ohne']} Stangen (Gehrungen ineinander)")

# ------------------------------------------------------------------ T3
assert "Sichtseite" in wenden.erlaubt(dict(pos[0], wenden="nein"))
assert "Satz" in wenden.erlaubt(dict(pos[0], satz="S1", je_satz=1))
assert "gleich" in wenden.erlaubt(dict(pos[0], a_gerade=None, a_ende=None))
assert "schon" in wenden.erlaubt(dict(pos[0], gewendet="ja"))
tech = json.dumps(dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=1, d=10, x=100, seite="oben")]))
pk = dict(laenge=1000, technik=tech)
assert abs(stangenende.abstand_b(pk) - 895) < 1e-6
assert abs(stangenende.abstand_b(dict(wenden.ansicht(dict(pk, gewendet="ja")))) - 95) < 1e-6
ok("T3 nicht bei Sichtseite, Satz, gleichen Enden; Spannbereich gewendet ab Ende A (95 statt 895 mm)")

# ------------------------------------------------------------------ T4
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(a)
n = s.teil_wenden(0)
assert n == auf["gewendet"], (n, auf)
pos = db.positionen(a)
assert len(pos) == 2 and pos[0]["stueck"] == 16 - n and pos[1]["stueck"] == n and pos[1]["gewendet"] == "ja"
assert pos[1]["artikel"] == "G1" and pos[0].get("gewendet") != "ja"
assert s.teil_wenden(1) == 0                     # das Duplikat wird nicht noch einmal gewendet
erg = rechnen.optimieren(db.angebot(a), pos, k, tab, ein)
wp = ausgabe.werkstatt(db.angebot(a), pos, erg, k, tab)
assert any("gewendet: Ende B vorn" in h["text"] for h in wp["hinweise"]), wp["hinweise"]
ok(f"T4 Teil wenden im Angebot: Pos. 10 {16 - n} Stück, Duplikat {n} Stück gewendet, Werkstatt-Hinweis")

# ------------------------------------------------------------------ T5
t5 = json.dumps(dict(a={}, b=dict(sattel=40), konturen=[]))
p5 = dict(laenge=500, technik=t5, profil_id="RR 40x2")
assert wenden.klemmt(p5) and wenden.klemmt(dict(p5, a_gerade="nein")) is None
bef = dfm.rohr(p5, dict(form="Rundrohr", a=40, b=40, wand=2), None)
assert dfm.KLEMMT in [b.regel for b in bef], bef
ok("T5 Prüfregel „Teil löst sich nicht“ bei Sattel an Ende B mit Vorschlag Teil wenden")
print("Alle Tests Teil wenden (ArTube) bestanden.")
