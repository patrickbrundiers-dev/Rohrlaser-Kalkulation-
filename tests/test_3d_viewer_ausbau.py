"""3D-Viewer als Arbeitswerkzeug (Plan Patrick 18.11.2026, Befunde F1–F10, Pakete V1–V6).

V1 Stabilität
- S1 Netzprüfung: NaN, unendlich, falscher Typ, zu große Koordinaten, falsche Punktnummern, unlesbare Listen und
  Schnittkörper werden ausgelassen und gemeldet (nie still); ein fehlerfreies Netz bleibt dasselbe Objekt.
- S2 Ansicht: kein Absturz beim Zeichnen beschädigter Netze (vorher Speicherzugriffsfehler bei NaN), Meldung im Bild;
  danach ein gutes Modell wieder normal (Wiederherstellung).
- S3 Editor-Speicher: teile_editor.ausfuehren gibt den Dialog nach dem Schließen frei (vorher blieb jeder Editor am
  Angebotsfenster hängen, +6 MB je Öffnen).
- S4 Feste Maße nach einer Modelländerung: Maße, deren Punkte es noch gibt, bleiben; die anderen fallen weg, mit Hinweis.
- S5 Großes Modell (synthetische Baugruppe mit 40.000 Dreiecken): Netzprüfung schnell, wiederholtes Laden ohne
  Speicherzuwachs.
V5 Kalkulation
- K1 hand_geaendert: Rohr-Merker in den Eingaben, Blech-Vergleich mit e['step'], Texte.
- K2 Rohr-Editor: geänderter STEP-Wert -> EditorRahmen.hand_geaendert nennt ihn; _hand_kennzeichnen schreibt ihn in
  die Eingaben, behält frühere Änderungen.
- K3 Herkunft: Laser „Geometrie aus STEP, von Hand geändert“, Quelle „von Hand“.
- K4 Vorschau: nach Hand-Änderung kommt das 3D aus den Eingaben (nicht das alte STEP-Netz).

Aufruf: python tests/test_3d_viewer_ausbau.py
"""
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, hand_geaendert, herkunft, schneidweg as sw, teile_editor as te  # noqa: E402
from rohrlaser.ansicht3d import Ansicht3D, netz_pruefen  # noqa: E402


def ok(t):
    print("OK    ", t)


GUT = {"p": [0, 0, 0, 10, 0, 0, 0, 10, 0, 0, 0, 10], "t": {"A": [0, 1, 2, 0, 2, 3]}, "l": {"K": [[0, 0, 0, 10, 0, 0]]}}

# ------------------------------------------------------------------ S1 Netzprüfung
n, m = netz_pruefen(GUT)
assert n is GUT and m == ""
FAELLE = {
    "NaN": ({"p": [0, 0, 0, float("nan"), 0, 0, 0, 1, 0, 1, 1, 0], "t": {"A": [0, 1, 2, 0, 2, 3]}}, "1 ungültiger Punkt"),
    "unendlich": ({"p": [0, 0, 0, float("inf"), 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}}, "1 Dreieck mit"),
    "Text": ({"p": [0, 0, "x", 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}}, "ungültiger Punkt"),
    "None": ({"p": [0, 0, None, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}}, "ungültiger Punkt"),
    "zu groß": ({"p": [0, 0, 0, 1e12, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 2]}}, "ungültiger Punkt"),
    "Index zu groß": ({"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 7]}}, "1 Dreieck mit"),
    "Index negativ": ({"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, -5]}}, "1 Dreieck mit"),
    "Index Text": ({"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, "2"]}}, "1 Dreieck mit"),
    "t keine Tabelle": ({"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": [0, 1, 2]}, "Dreiecksliste unlesbar"),
    "Linie kaputt": ({"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "l": {"K": [[0, 0], [0, 0, 0, 1, 1, float("nan")]]}},
                     "2 Linienzüge"),
    "Körper kaputt": (dict(GUT, wk="x"), "Schnittkörper unlesbar"),
}
for name, (netz, erwartet) in FAELLE.items():
    neu, meldung = netz_pruefen(netz)
    assert meldung.startswith("Modell fehlerhaft:") and erwartet in meldung, (name, meldung)
    assert neu is not netz
    for v in neu.get("p") or []:
        assert type(v) in (int, float) and math.isfinite(v) and abs(v) <= ansicht3d.KOORD_MAX, (name, v)
    np_ = len(neu["p"]) // 3
    for idx in (neu.get("t") or {}).values():
        assert len(idx) % 3 == 0 and all(type(i) is int and 0 <= i < np_ for i in idx), name
# Kennungen je Dreieck ('ti') bleiben den richtigen Dreiecken zugeordnet
mit_ti = {"p": [0, 0, 0, 1, 0, 0, 0, 1, 0], "t": {"A": [0, 1, 9, 0, 1, 2]}, "ti": {"A": ["weg", "bleibt"]}}
neu, _ = netz_pruefen(mit_ti)
assert neu["t"]["A"] == [0, 1, 2] and neu["ti"]["A"] == ["bleibt"]
assert netz_pruefen(None) == (None, "") and netz_pruefen([1, 2])[0] is None
assert netz_pruefen({"p": [float("nan")] * 9, "t": {"A": [0, 1, 2]}})[0] is None
ok("S1 Netzprüfung: 11 beschädigte Netze bereinigt und gemeldet, gutes Netz unverändert, Kennungen bleiben richtig")

# ------------------------------------------------------------------ S2 Ansicht ohne Absturz
a = Ansicht3D()
a.resize(640, 400)
a.show()
for name, (netz, _) in FAELLE.items():
    a.setzen(netz, name)
    a.grab()
    assert a.pruef_meldung.startswith("Modell fehlerhaft"), name
    for blick in ("Vorn", "Oben", ansicht3d.ISOMETRIE):
        a.blick(blick)
        a.grab()
    ansicht3d.vorschaubild(netz)
a.setzen(b"\x00kaputt")
a.grab()
assert a.modell is None and a.pruef_meldung == ""
a.setzen(GUT, "gut")
a.grab()
assert a.modell is not None and a.pruef_meldung == "" and a._fehler is None
# Fehler beim Zeichnen selbst: Meldung statt Absturz, danach wieder normal
alt = ansicht3d.zeichnen
ansicht3d.zeichnen = lambda *x, **y: 1 / 0
a._bild = None
a.grab()
assert "Zeichnen gescheitert" in a._fehler
ansicht3d.zeichnen = alt
a.setzen(GUT, "gut")
bild = a.grab().toImage()
assert a._fehler is None and bild.width() > 0
ok("S2 Ansicht: beschädigte Netze ohne Absturz gezeichnet (Meldung im Bild), Fehler beim Zeichnen abgefangen, "
   "danach wieder normal")

# ------------------------------------------------------------------ S3 Editor-Speicher
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
kopf = dict(maschine="T11", stange=6000)
technik = dict(quelle=sw.QUELLE, a=dict(winkel=30, achse="über Höhe", gemessen=70.5), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", gemessen=31.4)])
p = dict(id=1, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik),
         step_merkmale="1 Bohrung", a_schnitt=70.5)
eltern = QWidget()
for _ in range(3):
    d = SchneidwegDialog(eltern, p, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
    QTimer.singleShot(0, d.reject)
    assert te.ausfuehren(d) == QDialog.Rejected
    del d
    app.processEvents()
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
assert len(eltern.findChildren(QDialog)) == 0, eltern.findChildren(QDialog)
ok("S3 Editor nach dem Schließen freigegeben (3 Öffnungen, kein Dialog bleibt am Angebotsfenster)")

# ------------------------------------------------------------------ S4 feste Maße nach Modelländerung
from rohrlaser import rohr3d  # noqa: E402
from rohrlaser.messen3d import ECKE, KREISMITTE  # noqa: E402

profil = k.profile["QR 40x40x3"]
e1 = dict(a=dict(winkel=0), b=dict(winkel=0), konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben")])
n500 = rohr3d.netz(e1, profil, 500)
a.setzen(n500, "Rohr 500")
geo = a.geometrie()
kreis = next(kk for kk in geo.kreise if abs(kk["d"] - 10) < 0.01)
ecke0 = min(geo.ecken, key=lambda q: (q[2], q[0], q[1]))
ecke_b = max(geo.ecken, key=lambda q: (q[2], -q[0], -q[1]))
a.masse_fest = [([kreis["m"], ecke0], "Bohrung–Ende A"), ([ecke0, ecke_b], "Länge 500")]
a._mass_arten = {(tuple(kreis["m"]), tuple(ecke0)): [KREISMITTE, ECKE], (tuple(ecke0), tuple(ecke_b)): [ECKE, ECKE]}
n800 = rohr3d.netz(e1, profil, 800)          # Länge geändert: Ende B liegt woanders
a.setzen(n800, "Rohr 800")
assert [t for _, t in a.masse_fest] == ["Bohrung–Ende A"], a.masse_fest
assert "1 Maß entfernt" in a.tafel.klartext(), a.tafel.klartext()
e2 = dict(e1, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=150, seite="oben")])     # Bohrung verschoben
a.setzen(rohr3d.netz(e2, profil, 800), "Bohrung verschoben")
assert a.masse_fest == []
a.setzen(n800)
a.masse_fest = [([ecke0, ecke0], "x")]
a.setzen(n800)
assert len(a.masse_fest) == 1                  # gleiches Modell: Maß bleibt
ok("S4 feste Maße: bleiben nur, wenn ihre Punkte noch existieren (Länge geändert: Längenmaß weg, Bohrungsmaß bleibt)")

# ------------------------------------------------------------------ S5 großes Modell


def gross(n_teile=100, n=200):
    """Baugruppe aus n_teile Rohren mit je 2·n Dreiecken (Mantel als n-Eck), nebeneinander."""
    p_, t_ = [], []
    for nr in range(n_teile):
        basis = len(p_) // 3
        for i in range(n):
            w = 2 * math.pi * i / n
            for z in (0, 1000):
                p_ += [nr * 60 + 20 * math.cos(w), 20 * math.sin(w), z]
        for i in range(n):
            j = (i + 1) % n
            a0, a1, b0, b1 = basis + 2 * i, basis + 2 * i + 1, basis + 2 * j, basis + 2 * j + 1
            t_ += [a0, b0, b1, a0, b1, a1]
    return dict(p=p_, t={"A": t_}, l={}, **{"global": True})


g = gross()
assert len(g["t"]["A"]) // 3 == 40000
t0 = time.perf_counter()
assert netz_pruefen(g)[0] is g
dauer = time.perf_counter() - t0
assert dauer < 0.5, dauer


import gc  # noqa: E402

a.resize(1200, 800)
for _ in range(2):              # warm: Merker (Kanten, Lagen) einmal gefüllt
    a.setzen(dict(g), "groß")
    a.geometrie()
    a._bild = None
    a.grab()
gc.collect()
vorher = len(gc.get_objects())
for _ in range(8):
    a.setzen(dict(g), "groß")
    a.geometrie()
    a._bild = None
    a.grab()
gc.collect()
nachher = len(gc.get_objects())
assert abs(nachher - vorher) < 50, (vorher, nachher)       # kein Leck: gleich viele Python-Objekte
ok(f"S5 großes Modell 40.000 Dreiecke: Prüfung {dauer * 1000:.0f} ms, 8× neu geladen ohne Zuwachs an Objekten "
   f"({vorher} -> {nachher})")

# ------------------------------------------------------------------ K1 hand_geaendert
e = hand_geaendert.eintragen(dict(konturen=[]), ["1. Bohrung Ø 12"])
assert e["hand"] == dict(merkmale=["1. Bohrung Ø 12"]) and "hand" not in hand_geaendert.eintragen(e, [])
pr = dict(technik=json.dumps(e))
assert hand_geaendert.liste(pr) == ["1. Bohrung Ø 12"] and hand_geaendert.text(pr) == "von Hand geändert: 1. Bohrung Ø 12"
assert hand_geaendert.text(pr, kurz=True) == "von Hand geändert (1 Stelle)"
bl = dict(art="Zuschnitt", laenge=200, konturen=[dict(d=10)], step=dict(laenge=200, konturen=[dict(d=8)]))
assert hand_geaendert.liste(dict(technik=json.dumps(bl))) == ["Innenkonturen"]
bl["step"]["konturen"] = [dict(d=10)]
assert hand_geaendert.liste(dict(technik=json.dumps(bl))) == []
assert hand_geaendert.liste(dict(technik="kaputt")) == [] and hand_geaendert.liste({}) == []
ok("K1 Merker: Rohr in den Eingaben, Blech live gegen die STEP-Werte, beschädigte Technik ohne Fehler")

# ------------------------------------------------------------------ K2 Rohr-Editor -> Eingaben
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402

d = SchneidwegDialog(None, p, profil, kopf, k, db.tabellen(), db)
vorher_e = d.eingaben()
assert d.editor.hand_geaendert() == []
d.tabelle.item(0, 2).setText("12")
d.editor.aktualisieren()
texte = d.editor.hand_geaendert()
assert len(texte) == 1 and "Bohrung" in texte[0] and "12" in texte[0], texte
eing = AngebotSeite._hand_kennzeichnen(None, p, d, vorher_e, d.eingaben())
assert eing["hand"]["merkmale"] == texte
# zweites Öffnen: die alte Änderung bleibt gemerkt, eine neue kommt dazu
p2 = dict(p, technik=sw.speichern(eing))
d2 = SchneidwegDialog(None, p2, profil, kopf, k, db.tabellen(), db)
v2 = d2.eingaben()
d2.winkel["a"].setValue(40)
d2.editor.aktualisieren()
eing2 = AngebotSeite._hand_kennzeichnen(None, p2, d2, v2, d2.eingaben())
assert eing2["hand"]["merkmale"][0].startswith("Ende A") and texte[0] in eing2["hand"]["merkmale"], eing2["hand"]
# ohne STEP-Herkunft: nichts
p_ohne = dict(p, step_merkmale=None, a_schnitt=None, technik=json.dumps(dict(quelle=sw.QUELLE)))
assert "hand" not in AngebotSeite._hand_kennzeichnen(None, p_ohne, d, {}, dict(x=1))
ok("K2 Rohr-Editor: geänderter STEP-Wert wird beim OK gemerkt, beim nächsten Öffnen bleibt er und Neues kommt dazu")

# ------------------------------------------------------------------ K3 Herkunft
z = dict(laser_teil=10.0, sd_sicherheit="hoch")
(b,) = herkunft._laser(z, dict(p, technik=json.dumps(technik)))
assert b["quelle"] == herkunft.STEP and "Geometrie aus STEP" in b["grund"] and "Hand" not in b["grund"], b
(b,) = herkunft._laser(z, p2)
assert b["quelle"] == herkunft.HAND and "Geometrie aus STEP, von Hand geändert (1 Stelle)" in b["grund"], b
ok("K3 Herkunft Laser: STEP-Geometrie von Hand geändert ist als „von Hand“ gekennzeichnet")


# ------------------------------------------------------------------ K4 Vorschau aus den Eingaben
class _Db:
    def netz(self, pid):
        return ansicht3d.packen(rohr3d.netz(dict(technik), profil, 500))


class _Seite:
    db, kopf, k, positionen = _Db(), kopf, k, []
    eingaben_netz = AngebotSeite.eingaben_netz
    hand_netz = AngebotSeite.hand_netz
    _vorschau_netz = AngebotSeite._vorschau_netz


s = _Seite()
s.positionen = [dict(p, technik=json.dumps(technik)), p2]
netz0, titel0 = s._vorschau_netz(0)
assert isinstance(netz0, bytes) and titel0 == "3D aus dem STEP-Import"
netz1, titel1 = s._vorschau_netz(1)
assert isinstance(netz1, dict) and "von Hand geändert" in titel1, titel1
geo1 = ansicht3d.Modell(netz1)
assert geo1.max[2] == 500
# die Bohrung ist im Modell aus den Eingaben Ø 12 (STEP-Netz: Ø 10)
from rohrlaser.messen3d import Geometrie  # noqa: E402

d_bohrung = sorted(round(kk["d"], 2) for kk in Geometrie(geo1, netz1).kreise)
assert 12.0 in d_bohrung and 10.0 not in d_bohrung, d_bohrung
ok("K4 Vorschau: nach Hand-Änderung 3D aus den Eingaben (Bohrung Ø 12 statt STEP Ø 10) mit Hinweis im Titel")
print("Alle Tests bestanden.")
