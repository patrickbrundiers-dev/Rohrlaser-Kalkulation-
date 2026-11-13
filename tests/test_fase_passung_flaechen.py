"""Schweißfase je m, Passung → Reiben und Flächen markieren (GEO-012, GEO-010, CAD-008, Plan Phase 3 und 4, Patrick
13.11.2026 „Alles einbauen“):

- neue Zusatzarbeiten „Schweißfase je m“ (€/m), „Abkleben/Abdecken“ und „Sichtfläche schützen“ (€/m²) auch in
  bestehenden Datenbanken
- Fase an den Enden aus dem STEP: Vorschlag „Schweißfase je m“, Menge = Umfang × angefaste Enden; ohne diese
  Zusatzarbeit „Schweißfase anfasen“ je Ende; erst mit ✓ gerechnet
- Passung aus der Zeichnung („4x Ø10 H7“): an die Bohrungen mit dem Nennmaß, Reiben in € je Stück mit der Anzahl
- Flächen im 3D markieren (Rohr, Blech, Baugruppe, Satz): Zusatzarbeit mit dem Flächeninhalt als Menge

Aufruf: python tests/test_fase_passung_flaechen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from rohrlaser import (flaechen_markieren as fm, schneidweg as sw, step, zeichnung_hinweise as zh,  # noqa: E402
                       zusatz_erkennung as ze)
from rohrlaser.datenbank import ROHRLASER_ZUSATZ_STAND, Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
pfad = Path(tempfile.mkdtemp()) / "r.db"
db = Datenbank(pfad)
katalog = db.zeilen("zusatzarbeiten")
kat = {z["name"]: z for z in katalog}
assert kat["Schweißfase je m"]["art"] == "€/m" and kat["Reiben"]["art"] == "€/Stück"
assert kat["Abkleben/Abdecken"]["art"] == "€/m²" and kat["Sichtfläche schützen"]["art"] == "€/m²"
# bestehende Datenbank (alter Stand, Zusatzarbeit fehlt): wird beim Öffnen ergänzt
db.con.execute("DELETE FROM zusatzarbeiten WHERE name IN ('Schweißfase je m', 'Abkleben/Abdecken')")
db.einstellung_setzen("rohrlaser_zusatz_stand", "2026-11-12")
db.con.commit()
db.schliessen() if hasattr(db, 'schliessen') else db.con.close()
db = Datenbank(pfad)
namen = {z["name"] for z in db.zeilen("zusatzarbeiten")}
assert {"Schweißfase je m", "Abkleben/Abdecken"} <= namen
assert db.einstellung("rohrlaser_zusatz_stand") == ROHRLASER_ZUSATZ_STAND
ok("neue Zusatzarbeiten (Beispielpreise) auch in bestehenden Datenbanken ergänzt")

# ------------------------------------------------------------------ GEO-012 Schweißfase je m
m = dict(profilform="Rundrohr", abm_a=60.3, wandstaerke=3, laenge=800,
         hinweise=f"Ende A: {step.FASE_HINWEIS}; Ende B: {step.FASE_HINWEIS}")
p = step.fase_vorschlag(dict(profil_id="RR 60,3x3"), m, katalog)
e = ze.gemerkt(p)
assert len(e) == 1 and e[0]["name"] == "Schweißfase je m" and e[0]["quelle"] == "STEP", e
assert abs(e[0]["menge"] - round(3.14159265 * 60.3 / 1000 * 2, 3)) < 1e-9, e
assert "Ende A und Ende B" in e[0]["wort"] and "Umfang 189 mm" in e[0]["wort"], e[0]["wort"]
v = ze.offen(dict(p, art="Rohr"), {}, None, dict(zusatzarbeiten=katalog))
assert [x["name"] for x in v] == ["Schweißfase je m"] and abs(v[0]["menge"] - 0.379) < 1e-9, v
assert v[0]["herkunft"].startswith(ze.ERKANNT + "STEP"), v[0]["herkunft"]
x = ze.eintrag(v[0], katalog, dict(zusatzarbeiten=katalog))
assert x["menge"] == 0.379 and x["stand"]["art"] == "€/m", x
ok("Fase an beiden Enden: Vorschlag Schweißfase je m, Menge 2 × Umfang (0,379 m), Herkunft STEP, erst mit ✓")

m1 = dict(m, profilform="Quadratrohr", abm_a=40, abm_b=40, hinweise=f"Ende B: {step.FASE_HINWEIS}")
p1 = step.fase_vorschlag(dict(), m1, katalog)
assert ze.gemerkt(p1)[0]["menge"] < 0.16 and "Ende B" in ze.gemerkt(p1)[0]["wort"]
ohne = [z for z in katalog if z["name"] != "Schweißfase je m"]
p2 = step.fase_vorschlag(dict(), m, ohne)
assert [(y["name"], y["menge"]) for y in ze.gemerkt(p2)] == [("Schweißfase anfasen", 2)]
assert not step.fase_vorschlag(dict(), dict(m, hinweise=""), katalog).get("arbeitsgaenge")
da = dict(zusatz=json.dumps([dict(name="Schweißfase je m", menge=1)]))
assert not step.fase_vorschlag(da, m, katalog).get("arbeitsgaenge")
assert len(ze.gemerkt(step.fase_vorschlag(dict(p), m, katalog))) == 1          # nicht doppelt
ok("ein Ende; ohne €/m-Arbeit je Ende; ohne Fase oder schon eingetragen: kein Vorschlag")

# ------------------------------------------------------------------ GEO-010 Passung → Reiben
h = zh.lesen("4x Ø10 H7\nPassbohrung 8H8\nM8 x 1,25\nØ20 h7 (Welle)\nISO 2768-mK")
assert [(x["art"], x["gewinde"], x["anzahl"]) for x in h] == [
    (zh.PASSUNG, "10 H7", 4), (zh.PASSUNG, "8 H8", None), (zh.GEWINDE, "M8", None)], h
bild = [dict(art="Bohrung", d=9.8, anzahl=4), dict(art="Bohrung", d=8.0, anzahl=2), dict(art="Bohrung", d=6, anzahl=2)]
mess = dict(bohrungen="9.8:4|8.0:2|6.0:2")
meld = zh.bohrbild_abgleich(bild, h, mess, {})
assert bild[0]["passung"] == "H7" and bild[1]["passung"] == "H8" and "passung" not in bild[2], bild
assert any("Passung 4× Ø10 H7 an 4 Bohrungen" in t for t in meld), meld
assert zh.reiben_anzahl(h) == 6
assert zh.zusatz_mengen(h) == {"Reiben": 4}                     # Anzahl der Zeichnung geht vor
assert zh.zusatz_mengen([h[1]], reiben=2) == {"Reiben": 2}       # ohne Anzahl: Bohrungen aus dem STEP
assert zh.zusatz_mengen(zh.lesen("Ø12 H7"), mit_bohrbild=False) == {"Reiben": None}
meld = zh.bohrbild_abgleich([], zh.lesen("2x Ø12 H7"), dict(bohrungen=""), {})
assert meld == ["Zeichnung nennt Passung 2× Ø12 H7, im STEP keine Bohrung mit diesem Maß"], meld
arb = ze.text_merken(None, "4x Ø10 H7", katalog, "Zeichnung", zh.zusatz_mengen(zh.lesen("4x Ø10 H7")))
assert [(y["name"], y.get("menge")) for y in ze.gemerkt(dict(arbeitsgaenge=arb))] == [("Reiben", 4)]
ok("Passung H7/H8 an die Bohrungen mit dem Nennmaß, Reiben € je Stück mit Anzahl; Welle (h7) und Gewinde nicht")

# ------------------------------------------------------------------ CAD-008 Flächen markieren
fl = [dict(art="Fläche", flaeche=12000.0), dict(art="Fläche", flaeche=3000.0)]
assert abs(fm.inhalt_m2(fl) - 0.015) < 1e-12
x = fm.eintrag(fm.ABKLEBEN, katalog, 0.015)
assert x == dict(name="Abkleben/Abdecken", menge=0.015, preis=None, text="aus 3D: abkleben 0,015 m²", quelle="3D"), x
assert fm.eintrag(fm.SCHWEISS, katalog, 0.002)["text"] == "aus 3D: Schweißfläche freihalten 0,002 m²"
assert fm.eintrag(fm.SICHT, katalog, 0)["menge"] is None                  # ganzes Teil: Außenfläche automatisch
assert fm.eintrag(fm.SICHT, [], 0.1) is None and "Sichtfläche schützen" in fm.fehlt_text(fm.SICHT)
ok("Flächeninhalt als Menge (m²), Schweißfläche = abdecken mit „freihalten“, ohne Fläche ganzes Teil")

from rohrlaser.fenster import Hauptfenster  # noqa: E402

technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=2, d=10, x=100, seite="oben")])
ang = db.angebot_neu(dict(kunde="Test", maschine="T11"))
pid = db.position_neu(ang, dict(pos=1, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
                                technik=json.dumps(technik)))
f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(ang)
gesehen = {}


def bedienen(d):
    ed = d.editor
    m_ = ed.kontextmenue("kontur:0")
    gesehen["menue"] = [a.text() for a in m_.actions()]
    gesehen["eintrag"] = ed.flaeche_markieren(fm.SICHT, gewaehlt=fl)
    d._ok() if hasattr(d, "_ok") else d.accept()
    return d.result()


zeile = next(r for r, q in enumerate(s.positionen) if q["id"] == pid)
assert s.schneidweg_berechnen(zeile, dialog=bedienen)
assert any(t.startswith(fm.MENUE) for t in gesehen["menue"]), gesehen["menue"]
from rohrlaser import rechnen  # noqa: E402

zl = rechnen.zusatz_liste(next(q for q in db.positionen(ang) if q["id"] == pid))
assert [(y["name"], y["menge"]) for y in zl] == [("Sichtfläche schützen", 0.015)], zl
ok("Rohr-Editor: Rechtsklick „Fläche markieren als › Sichtfläche“ -> Zusatzarbeit mit 0,015 m² nach OK")

from rohrlaser import blech  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
bd = BlechDialog(None, db, dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=300, breite=200,
                                werkstoff=werkstoff, konturen=[]))
xb = bd.editor.flaeche_markieren(fm.ABKLEBEN, gewaehlt=fl[:1])
assert xb["menge"] == 0.012 and bd.zusatz_neu == [xb]
ok("Blech-Editor: Abkleben 0,012 m²")

from rohrlaser.baugruppe_dialog import AuswahlEditor  # noqa: E402


class Fenster(QWidget, AuswahlEditor):
    def __init__(self):
        super().__init__()
        self.tabellen = dict(zusatzarbeiten=katalog)
        self.teile = [dict(_id=pid, _q=dict(pos=1, artikel="Holm"))]


w = Fenster()
xt = w.flaeche_teil(pid, fm.SCHWEISS, gewaehlt=fl)
assert xt["name"] == "Abkleben/Abdecken" and xt["menge"] == 0.015 and w.zusatz_neu == {pid: [xt]}
assert w.flaeche_teil(999, fm.SICHT, gewaehlt=fl) is None
w.tabellen = dict(zusatzarbeiten=[])
assert w.flaeche_teil(pid, fm.SICHT, gewaehlt=fl) is None and "fehlt" in w.flaeche_hinweis
ok("Baugruppe und Satz in 3D: Schweißfläche freihalten je Teil; fehlt die Arbeit: Hinweis")
print("alle Prüfungen bestanden")
