"""3D-Editor Schritt 3E-6 (Plan kalkulation/3d-editor E1, E3, F1): Kontur-Vorlagen, Auswahl mit Vorschau, Editor aus
der 3D-Ansicht der Positionen.
- V1 Rechnung: speichern (Name je Art und Kunde eindeutig, ersetzen), Liste (Kunde zuerst, fremde Kunden nicht),
  ohne Messwerte, einsetzen (Lage bleibt, außerhalb mittig hinein), Kurztext, Vorschaubild Rohr und Blech;
  Tabelle kontur_vorlagen (Schema 58) wird mit den Stammdaten geteilt.
- V2 Rohr-Editor: markierte Konturen als Vorlage, in ein anderes Teil einsetzen, Menü mit Bild, Kontextmenü.
- V3 Blech-Editor: dasselbe mit x/y in der Abwicklung.
- V4 „Aus Position“ mit Vorschaubild je Position.
- V5 3D-Ansicht der Positionen: Doppelklick auf das Teil bzw. „Im Editor öffnen“ ruft den Editor der Position.

Aufruf: python tests/test_konturvorlagen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import blech, datenbank, konturvorlagen as kv, schneidweg as sw, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()

# ------------------------------------------------------------------ V1 Rechnung
assert datenbank.SCHEMA_VERSION >= 58 and db.anzahl(kv.TABELLE) == 0
assert any(t.name == kv.TABELLE for t in teilen.GETEILT)
bohrbild = [dict(art=sw.BOHRUNG, anzahl=1, d=9, x=40, seite="oben", gemessen=28.3, quelle="Steckverbindung 1"),
            dict(art=sw.BOHRUNG, anzahl=1, d=9, x=80, seite="oben"),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=60, seite="vorne", drehung=90)]
assert kv.inhalt(bohrbild) == "2× Bohrung, Langloch"
assert all("gemessen" not in z and "quelle" not in z for z in kv.sauber(bohrbild))
i1 = kv.speichern(db, "Flansch", kv.ROHR, bohrbild, profilform="Quadratrohr")
for fehler in (lambda: kv.speichern(db, "Flansch", kv.ROHR, bohrbild), lambda: kv.speichern(db, " ", kv.ROHR, bohrbild),
               lambda: kv.speichern(db, "Leer", kv.ROHR, [])):
    try:
        fehler()
        raise AssertionError("ValueError erwartet")
    except ValueError:
        pass
assert kv.speichern(db, "Flansch", kv.ROHR, bohrbild[:2], ueberschreiben=True) == i1
i2 = kv.speichern(db, "Flansch", kv.ROHR, bohrbild, kunde="K-100")            # gleicher Name, nur für Kunde K-100
kv.speichern(db, "Blechlöcher", kv.BLECH, [dict(art=sw.BOHRUNG, anzahl=1, d=8, x=20, y=20)])
assert [z["id"] for z in kv.liste(db, kv.ROHR, "K-100")] == [i2, i1]
assert [z["id"] for z in kv.liste(db, kv.ROHR, "K-200")] == [i1] and len(kv.liste(db, kv.BLECH)) == 1
z1 = next(z for z in kv.liste(db, kv.ROHR) if z["id"] == i1)
assert z1["inhalt"] == "2× Bohrung" and len(kv.konturen(z1)) == 2
assert [z["x"] for z in kv.einsetzbar(z1, kv.ROHR, 500)] == [40, 80]                  # passt: Lage bleibt
assert [z["x"] for z in kv.einsetzbar(z1, kv.ROHR, 70)] == [15, 55]                   # zu kurz: mittig hinein
zb = kv.liste(db, kv.BLECH)[0]
assert kv.einsetzbar(zb, kv.BLECH, 100, 50)[0]["x"] == 20
assert kv.einsetzbar(zb, kv.BLECH, 10, 10)[0]["x"] == 5
assert kv.bild(z1, kv.ROHR) is not None and kv.bild(zb, kv.BLECH) is not None
assert kv.konturen(dict(konturen="kaputt")) == []
ok("V1 Vorlagen speichern/ersetzen/je Kunde, Liste, einsetzen (mittig hinein), Kurztext, Vorschaubild, Schema 58")

# ------------------------------------------------------------------ V2 Rohr-Editor
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402
from rohrlaser import editor_griffe  # noqa: E402
from PySide6.QtWidgets import QMenu  # noqa: E402

eing = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben"),
                                  dict(art=sw.BOHRUNG, anzahl=1, d=10, x=150, seite="oben"),
                                  dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, r=0, x=300, seite="vorne")])
p = dict(id=1, pos=1, artikel="A-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
kopf = dict(maschine="T11", stange=6000, kundennr="K-100")
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
ed = d.editor
assert ed.band.knopf("Kontur-Vorlagen") is not None and ed.band.knopf("Teil-Vorlagen") is not None
assert ed.kunde() == "K-100"
d.tabelle.clearSelection()
d.tabelle.selectRow(0)
d.tabelle.setSelectionMode(d.tabelle.SelectionMode.MultiSelection)
d.tabelle.selectRow(1)
assert ed.markierte_zeilen() == [0, 1]
iv = ed.vorlage_speichern("Zwei Löcher", nur_kunde=True)
zv = next(z for z in db.zeilen(kv.TABELLE) if z["id"] == iv)
assert zv["kunde"] == "K-100" and zv["profilform"] == "Quadratrohr" and zv["inhalt"] == "2× Bohrung"
p2 = dict(p, id=2, laenge=120, technik=json.dumps(dict(a={}, b={}, konturen=[], quelle=sw.QUELLE)))
d2 = SchneidwegDialog(None, p2, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
assert d2.editor.vorlage_einsetzen(iv) == 2
xs = [z["x"] for z in d2.eingaben()["konturen"]]
assert xs == [35, 85], xs                                                   # 100/150 passt nicht in 120: mittig
assert d2.editor.gewaehlt == "kontur:0"
m = QMenu()
d2.editor._vorlagen_menue(m)
texte = [a.text() for a in m.actions()]
assert texte[0].startswith("Markierte Konturen als Vorlage") and any(t.startswith("Zwei Löcher") for t in texte)
assert any(not a.icon().isNull() for a in m.actions() if a.text().startswith("Zwei Löcher"))
km = editor_griffe.menue_bauen(d2.editor, "kontur:0")
assert "Als Kontur-Vorlage speichern …" in [a.text() for a in km.actions()]
ok("V2 Rohr-Editor: markierte Konturen als Vorlage (nur Kunde), einsetzen in kürzeres Teil, Menü mit Bild, Kontextmenü")

# ------------------------------------------------------------------ V3 Blech-Editor
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, werkstoff=werkstoff,
         konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=150, y=80), dict(art=sw.LANGLOCH, anzahl=1, l=20, b=8,
                                                                           x=170, y=80, drehung=45)])
b = BlechDialog(None, db, e)
assert b.editor.band.knopf("Kontur-Vorlagen") is not None and b.editor.kunde() is None
iv_b = b.editor.vorlage_speichern("Ecke oben rechts", zeilen=[0, 1])
b2 = BlechDialog(None, db, dict(e, laenge=100, breite=60, konturen=[]))
assert b2.editor.vorlage_einsetzen(iv_b) == 2
kb = b2.eingaben()["konturen"]
assert [(z["x"], z["y"]) for z in kb] == [(40, 30), (60, 30)] and kb[1]["drehung"] == 45, kb
ok("V3 Blech-Editor: Vorlage mit x/y und Drehwinkel, einsetzen in kleineres Blech mittig")

# ------------------------------------------------------------------ V4 Aus Position mit Vorschau
p3 = dict(p, id=3, pos=3, artikel="B-7")
d4 = SchneidwegDialog(None, p2, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db, [p, p3])
d4.stumm = True
w = d4._kopieren_waehlen()
assert w.liste.count() == 2 and not w.liste.item(0).icon().isNull() and "Zeile" in w.liste.item(0).text()
w.liste.setCurrentRow(1)
w.accept()
assert w.wert == 1
ok("V4 Aus Position: Auswahl mit Vorschaubild je Position")

# ------------------------------------------------------------------ V5 3D-Ansicht der Positionen -> Editor
from rohrlaser import rohr3d  # noqa: E402
from rohrlaser.step_dialog import Positionen3DDialog  # noqa: E402

netz = rohr3d.netz(eing, k.profile["QR 40x40x3"], 500)
gerufen = []
pd = Positionen3DDialog(None, [p, p3], {1: netz}, 0, bearbeiten=gerufen.append)
a3 = pd.ansicht.ansicht
a3.resize(600, 400)
a3.grab()
bp = a3.bildpunkt()
i, j, k_, _, _ = a3.modell.dreiecke[len(a3.modell.dreiecke) // 2]
ecken = [bp(a3.modell.punkte[n]) for n in (i, j, k_)]
assert a3.auf_modell(sum(q[0] for q in ecken) / 3, sum(q[1] for q in ecken) / 3)
assert not a3.auf_modell(-500, -500)
assert a3.doppelklick_ziel is not None
pd.liste.setCurrentCell(0, 0)
pd.editor_oeffnen()
assert gerufen == [0] and pd.geoeffnet == 0
nur = Positionen3DDialog(None, [p], {1: netz}, 0)
assert getattr(nur.ansicht.ansicht, "doppelklick_ziel", None) is None
ok("V5 3D-Ansicht der Positionen: Doppelklick auf das Teil bzw. Knopf öffnet den Editor der Position")
print("Alle Tests Kontur-Vorlagen bestanden.")
