"""Prüft die Schweißnaht je Position (naht.py, Dialog 'Schweißnaht …'):
- Winkel: 0° oben, 90° rechts, 180° unten, 270° links (Blick von Ende A); Normierung außerhalb 0–359,9°; Text
  abgewiesen; Ansicht 'Schmalseite oben' wird umgerechnet und nicht gespiegelt.
- Profile: Rechteckrohr Breitseite oben, gedreht (Schmalseite oben), Naht auf Breit-/Schmalseite, Ecke nicht
  eindeutig, A < B im Profil, Quadratrohr (keine Breit-/Schmalseite), Rundrohr, kein Rohr/unvollständig = unbekannt.
- Drehfreigabe: leer/keine Vorgabe frei (RE 0/180, QR und RR 0/90/180/270), feste Position und unbekannt gesperrt.
- Prüfung: Nahtlage der Lieferstange (FEHLER bei falscher Seite, WARNUNG ohne Angabe), Winkel fehlt.
- Datenbank: Schema-Umstellung einer älteren Datei (Felder leer = keine Vorgabe), Speichern über die Angebotsseite,
  Dialog mit Klick in den Querschnitt, Spalte und Status.

Aufruf: python tests/test_naht.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import naht  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.naht_dialog import NahtDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


RE = dict(form="Rechteckrohr", a=100, b=50)
RE_HOCH = dict(form="Rechteckrohr", a=50, b=100)        # A < B: Breitseite trotzdem die 100er Seite
QR = dict(form="Quadratrohr", a=40)
RR = dict(form="Rundrohr", a=42.4)

# ------------------------------------------------------------------ N1 Winkel
for w, r in ((0, "oben"), (90, "rechts"), (180, "unten"), (270, "links")):
    for pr in (RE, QR, RR):
        assert naht.seite(pr, w)["richtung"] == r, (pr, w)
assert [naht.normieren(w) for w in (360, -90, 450, 720, "45,5", 359.96)] == [0, 270, 90, 0, 45.5, 0]
for falsch in (None, "", "oben", float("nan")):
    try:
        naht.normieren(falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
assert naht.seite(RE, -90)["richtung"] == "links" and naht.seite(RE, 450)["richtung"] == "rechts"
ok("N1 Winkel: 0° oben, 90° rechts, 180° unten, 270° links, Normierung, Text abgewiesen")

# ------------------------------------------------------------------ N2 Ansicht ohne Spiegelung
assert naht.aus_ansicht(0, naht.SCHMAL_OBEN) == 90 and naht.in_ansicht(90, naht.SCHMAL_OBEN) == 0
for w in range(0, 360, 15):
    for lage in naht.LAGEN:
        assert naht.in_ansicht(naht.aus_ansicht(w, lage), lage) == w
# hochkant: oben in der Ansicht ist eine Schmalseite, rechts eine Breitseite; Richtung im Uhrzeigersinn wie gezeichnet
s = naht.seite(RE, naht.aus_ansicht(0, naht.SCHMAL_OBEN), naht.SCHMAL_OBEN)
assert (s["richtung"], s["flaeche"], s["ansicht"]) == ("oben", naht.SCHMALSEITE, 0)
s = naht.seite(RE, naht.aus_ansicht(90, naht.SCHMAL_OBEN), naht.SCHMAL_OBEN)
assert (s["richtung"], s["flaeche"]) == ("rechts", naht.BREITSEITE)
assert naht.seite(RE, naht.aus_ansicht(270, naht.SCHMAL_OBEN), naht.SCHMAL_OBEN)["richtung"] == "links"
ok("N2 Querschnitt hochkant: Winkel in der Ansicht, rechts bleibt rechts (keine Spiegelung)")

# ------------------------------------------------------------------ N3 Profile
assert naht.seite(RE, 0)["flaeche"] == naht.BREITSEITE and naht.seite(RE, 180)["flaeche"] == naht.BREITSEITE
assert naht.seite(RE, 90)["flaeche"] == naht.SCHMALSEITE and naht.seite(RE, 270)["flaeche"] == naht.SCHMALSEITE
assert naht.seite(RE, 60)["flaeche"] == naht.BREITSEITE and naht.seite(RE, 67)["flaeche"] == naht.SCHMALSEITE
ecke = naht.seite(RE, 63.4)                              # Ecke 100 × 50 bei atan(2) = 63,4°
assert not ecke["eindeutig"] and ecke["flaeche"] == "" and "Ecke" in ecke["text"]
assert naht.seite(RE_HOCH, 0)["flaeche"] == naht.BREITSEITE and naht.seite(RE_HOCH, 90)["flaeche"] == naht.SCHMALSEITE
q = naht.seite(QR, 90)
assert q["eindeutig"] and q["flaeche"] == "Seite" and not naht.seite(QR, 45)["eindeutig"]
assert naht.seite(dict(form="Rechteckrohr", a=40, b=40), 0)["flaeche"] == "Seite"     # RE mit gleichen Seiten
r = naht.seite(RR, 37)
assert r["eindeutig"] and r["flaeche"] == "" and r["richtung"] == "" and r["text"] == "37°"
for pr in (None, dict(form="U-Profil", a=100, b=50), dict(form="Rechteckrohr", a=60), dict(form="Rundrohr")):
    s = naht.seite(pr, 0)
    assert not s["eindeutig"] and s["flaeche"] == "", pr
ok("N3 Rechteckrohr Breit-/Schmalseite (auch A < B, hochkant), Ecke unklar, Quadrat, Rund, unbekanntes Profil")

# ------------------------------------------------------------------ N4 Drehfreigabe und Prüfung
assert naht.vorgabe({}) == naht.KEINE and naht.drehung_frei({})
assert naht.drehungen({}, RE) == (0, 180) and naht.drehungen({}, QR) == (0, 90, 180, 270)
assert naht.drehungen({}, RR) == (0, 90, 180, 270) and naht.drehungen({}, dict(form="U-Profil", a=1, b=1)) == (0,)
for v in (naht.FEST, naht.UNBEKANNT):
    assert naht.drehungen(dict(naht_vorgabe=v), QR) == (0,) and not naht.drehung_frei(dict(naht_vorgabe=v))
fest = dict(naht_vorgabe=naht.FEST, naht_winkel=90)
assert naht.pruefen(fest, RE).startswith("WARNUNG: Nahtlage der Lieferstange")
assert naht.pruefen(fest, dict(RE, naht_stange=naht.SCHMALSEITE)) is None
assert naht.pruefen(fest, dict(RE, naht_stange=naht.BREITSEITE)).startswith("FEHLER: Naht auf Schmalseite")
assert naht.pruefen(dict(fest, naht_winkel=None), QR).startswith("FEHLER: Nahtwinkel fehlt")
assert naht.pruefen(dict(fest, naht_winkel=45), QR).startswith("WARNUNG: Schweißnaht auf der Ecke")
assert naht.pruefen(fest, QR) is None and naht.pruefen(fest, RR) is None
assert naht.pruefen(fest, dict(form="L-Profil", a=50, b=50)).startswith("WARNUNG")
assert naht.pruefen(dict(naht_vorgabe=naht.UNBEKANNT), RE) is None and naht.pruefen({}, RE) is None
assert naht.text(fest, RE) == "fest 90° rechts, Schmalseite" and naht.text({}, RE) == ""
ok("N4 Drehfreigabe aus der Vorgabe, Prüfung gegen Nahtlage der Lieferstange")

# ------------------------------------------------------------------ N5 Datenbank, Angebot, Dialog
tmp = Path(tempfile.mkdtemp())
alt = tmp / "alt.db"
db = Datenbank(alt)
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
db.position_neu(a, dict(pos=10, artikel="R1", profil_id="RE 60x40x3", werkstoff_id="S355-10219", laenge=800, stueck=4))
db.schliessen()
con = sqlite3.connect(alt)                               # Datei vor Schema 30: Nahtspalten fehlen
for spalte in ("naht_vorgabe", "naht_winkel", "naht_quelle", "querschnitt_lage"):
    con.execute(f'ALTER TABLE positionen DROP COLUMN "{spalte}"')
con.execute('ALTER TABLE profile DROP COLUMN "naht_stange"')
con.execute("PRAGMA user_version=29")
con.commit()
con.close()
db = Datenbank(alt)
assert db.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
p = db.positionen(a)[0]
assert p["naht_vorgabe"] is None and naht.drehung_frei(p) and db.kontext().profile["RE 60x40x3"]["naht_stange"] is None
ok("N5 ältere Datei: Nahtfelder leer angelegt = keine Vorgabe (frei drehbar)")

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1600, 900)
seite = fenster.angebot_oeffnen(a)
spalte = next(i for i, (art, _) in enumerate(seite.pos_modell.spalten) if art == "naht")


def klick(d, ansicht_winkel):
    """Klick in den Querschnitt in Richtung ansicht_winkel (0° oben, im Uhrzeigersinn)."""
    import math
    b = d.bild
    b.resize(300, 300)
    c = b._rahmen().center()
    t = math.radians(ansicht_winkel)
    pkt = QPointF(c.x() + 60 * math.sin(t), c.y() - 60 * math.cos(t))
    b.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, pkt, pkt, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def bedienen(d):
    d.vorgabe.setCurrentText(naht.FEST)
    d.lage.setCurrentText(naht.SCHMAL_OBEN)
    klick(d, 90)                                         # hochkant, rechts geklickt = Breitseite
    assert d.winkel.value() == 90 and "Breitseite" in d.info.text() and "gesperrt" in d.info.text()
    return QDialog.Accepted


assert seite.schweissnaht([0], dialog=bedienen)
p = db.positionen(a)[0]
assert (p["naht_vorgabe"], p["naht_winkel"], p["querschnitt_lage"], p["naht_quelle"]) == \
    (naht.FEST, 180, naht.SCHMAL_OBEN, "Kunde")
assert seite.pos_modell.roh(0, spalte) == "fest 90° rechts, Breitseite"
assert seite.pos_modell.status[0].startswith("WARNUNG: Nahtlage der Lieferstange")
pr = db.kontext().profile["RE 60x40x3"]
db.aendern("profile", pr["id"], "naht_stange", naht.SCHMALSEITE)
fenster2 = Hauptfenster(db, stumm=True)
seite2 = fenster2.angebot_oeffnen(a)
assert seite2.pos_modell.status[0].startswith("FEHLER: Naht auf Breitseite gefordert"), seite2.pos_modell.status[0]
# Dialog öffnet mit gespeicherter Lage und Winkel in der Ansicht
d = NahtDialog(None, p, db.kontext().profile["RE 60x40x3"])
assert d.lage.currentText() == naht.SCHMAL_OBEN and d.winkel.value() == 90 and d.werte()["naht_winkel"] == 180
d.lage.setCurrentText(naht.BREIT_OBEN)                   # Lage umschalten: Naht bleibt am Rohr
assert d.winkel.value() == 180 and d.werte()["naht_winkel"] == 180 and d.werte()["querschnitt_lage"] is None
d.winkel.setValue(-90)                                   # über 0° hinaus gedreht: normiert
assert d.winkel.value() == 270
d.winkel.setValue(47)                                    # Rechteckrohr: nur 0°/90°/180°/270°
assert d.winkel.value() == 90 and d.werte()["naht_winkel"] == 90
klick(d, 130)
assert d.winkel.value() == 90
d.vorgabe.setCurrentText(naht.KEINE)
assert set(d.werte().values()) == {None} and "drehen (0°, 180°)" in d.info.text()
assert seite2.schweissnaht([0], werte=dict(naht_vorgabe=naht.UNBEKANNT, naht_winkel=None, naht_quelle=None,
                                            querschnitt_lage=None))
assert seite2.pos_modell.roh(0, spalte) == "unbekannt – Drehung gesperrt" and seite2.pos_modell.status[0] != "" \
    and not seite2.pos_modell.status[0].startswith(("FEHLER: Naht", "WARNUNG: Naht"))
ok("N6 Dialog 'Schweißnaht …': Klick in den Querschnitt, Lage hochkant, Speichern, Spalte und Status")

# ------------------------------------------------------------------ N7 Gehrungsrichtung (Schneidweg-Rechner, STEP)
import json  # noqa: E402
from rohrlaser import schneidweg as sw, step  # noqa: E402
assert naht.ende_lesen(naht.ende_text(45, 450)) == (45.0, 90.0)
for falsch in (None, "", "kaputt", json.dumps(dict(winkel=0, richtung=0)), json.dumps(dict(winkel=45))):
    assert naht.ende_lesen(falsch) is None, falsch
re60 = db.kontext().profile["RE 60x40x3"]           # A = 60 (Breitseite oben), B = 40
regel = (10, 50)
ein = dict(a=dict(winkel=45, achse="über Breite", richtung=0), b=dict(winkel=45, achse="über Höhe", richtung=90),
           konturen=[])
erg = sw.rechnen(ein, re60, regel)
assert not erg["fehler"] and naht.ende_lesen(erg["felder"]["a_ende"]) == (45, 0) \
    and naht.ende_lesen(erg["felder"]["b_ende"]) == (45, 90)
falsch = sw.rechnen(dict(ein, a=dict(winkel=45, achse="über Höhe", richtung=0)), re60, regel)
assert falsch["fehler"] and "passt nicht" in falsch["fehler"][0] and falsch["felder"]["a_ende"] is None
ohne = sw.rechnen(dict(ein, b=dict(winkel=45, achse="über Höhe")), re60, regel)
assert not ohne["fehler"] and ohne["felder"]["b_ende"] is None                  # ohne Richtung: nicht teilbar
assert sw.rechnen(dict(a=dict(winkel=30, richtung=200), b={}, konturen=[]), dict(form="Rundrohr", a=42.4, wand=2),
                  regel)["felder"]["a_ende"] == naht.ende_text(30, 200)
liste = [dict(art="Ende A", form="gerade", gehrung=0.0, richtung=None),
         dict(art="Ende B", form="Gehrung", gehrung=45.0, richtung=90.0)]
assert step.gehrungen(dict(konturen_liste=json.dumps(liste))) == dict(b_ende=naht.ende_text(45, 90))
liste[1].pop("richtung")                            # ältere STEP-Import.exe ohne Richtung
assert step.gehrungen(dict(konturen_liste=json.dumps(liste))) == {} and step.gehrungen({}) == {}
ok("N7 Gehrungsrichtung: Schneidweg-Rechner (mit Prüfung gegen die Achse), STEP-Konturliste, ohne Richtung leer")
print("Alle Schweißnaht-Tests bestanden.")
