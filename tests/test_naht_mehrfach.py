"""Prüft die Optimierung, wenn die Schweißnaht bei mehreren Positionen angepasst wird (Patrick 29.10.2026):
- M1 Zwischenspeicher der Anordnung: die Schnittmuster prüfen dasselbe Teil mehrfach ([Typ] * k); danach bekommt eine
  gleiche Folge verschiedener Teile jedes Teil genau einmal (vorher: ein Teil doppelt, eines fehlt, Kontrolle
  „Teile fehlen oder doppelt“ – nur mit fester Naht oder Gehrungen, weil nur dann der Zwischenspeicher rechnet).
- M2 viele Gruppen nacheinander mit fester Naht, unbekannt, frei, Gehrungen: Kontrolle (pruefe, pruefe_vorrat,
  pruefe_zuschnitt) schlägt nie an, gleiches Ergebnis wie mit leerem Zwischenspeicher.
- M3 wirksamer Nahtwinkel: Quadrat- und Rechteckrohr rechnen mit der Mitte der Seite wie Spalte und Prüfung
  (50° bei RE 60x40 = Breitseite, nicht gerundet 90°), Ecke = nicht drehen; Rundrohr unverändert.
- M4 Dialog für mehrere Positionen: verschiedene Winkel bleiben je Position, solange der Winkel nicht geändert wird;
  geänderter Winkel gilt für alle; Querschnittslage nur bei Rechteckrohr; Winkel eines Rundrohrs wird bei Kasten auf
  die Seitenmitte gelegt; danach Optimieren ohne Fehler und aktuell.
- M5 Angebot mit fünf Positionen RE 60x40x3, feste Naht oben bzw. unten: Optimieren ohne Fehler.

Aufruf: python tests/test_naht_mehrfach.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import naht, optimierung as opt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.optimierung import FEST, FREI, UNBEKANNT, Gruppe, Teil  # noqa: E402


def ok(t):
    print("OK    ", t)


def leeren():
    for s in (opt._ANORDNUNG, opt._TRENNSUMME, opt._SPEICHER):
        s.clear()


# ------------------------------------------------------------------ M1 Zwischenspeicher der Anordnung
leeren()
g = Gruppe("RE 60x40x3", "S235", 6000, 10, 50, 0.2, 10, querschnitt=("Kasten", 60, 40))
fest = [Teil(1, 10, "A", i, 700, True, True, 200, 200, drehung=FEST, naht=0.0) for i in range(1, 4)]
assert opt.passt(g, [fest[0]] * 3)             # wie das Startmuster der Schnittmuster: dasselbe Objekt dreimal
folge = opt.anordnen(fest, g)                  # gleiche Enden, also derselbe Eintrag im Zwischenspeicher
assert sorted(t.nr for t, _ in folge) == [1, 2, 3], [(t.nr, r) for t, r in folge]
g.teile = fest + [Teil(2, 20, "B", i, 1210, True, True, 200, 200, drehung=FEST, naht=180.0) for i in range(1, 6)]
erg = opt.optimiere(g)
opt.pruefe([g], [erg])
ok("M1 Zwischenspeicher: dasselbe Teil mehrfach geprüft, danach jedes Teil genau einmal auf den Stangen")

# ------------------------------------------------------------------ M2 viele Gruppen nacheinander
QS = [("Kasten", 60, 40), ("Kasten", 50, 50), ("Rund", 25), ()]


def zufall(seed):
    r = random.Random(seed)
    g = Gruppe("X", "S235", r.choice([3000, 6000]), 10, 50, 0.2, 10, querschnitt=r.choice(QS))
    for z in range(1, r.randint(2, 6)):
        laenge = r.choice([300, 455, 700, 1210, 1730])
        geh = r.random() < 0.6
        dr = r.choice([FREI, FEST, FEST, UNBEKANNT])
        nw = float(r.choice([0, 90, 180, 270])) if dr == FEST else None
        a = (r.choice([45, 30]), r.choice([0, 90, 180, 270])) if geh else None
        b = (r.choice([45, 30]), r.choice([0, 90, 180, 270])) if geh and r.random() < .7 else None
        g.teile += [Teil(z, z, f"P{z}", i, laenge, a is None, b is None, 200, 200, a, b, dr, nw)
                    for i in range(1, r.randint(1, 10))]
    return g


def stangen(g):
    return sorted(tuple(sorted((t.zeile, t.nr) for t, _ in f)) for f in opt.optimiere(g))


leeren()
seeds = range(40)
mit_speicher = {}
for s in seeds:
    g = zufall(s)
    erg = opt.optimiere(g)
    opt.pruefe([g], [erg])
    mit_speicher[s] = len(erg)
    vorrat = [(g.stange, 3), (2500, 2)]
    plan, uebrig = opt.vorrat_planen(g, vorrat)
    opt.pruefe_vorrat(g, vorrat, plan, uebrig)
    z = opt.zuschnitt(g, 12000, 6500, 3)
    if z:
        opt.pruefe_zuschnitt(g, z, 12000, 6500, 3)
for s in (3, 7, 17, 29):
    leeren()
    assert len(opt.optimiere(zufall(s))) == mit_speicher[s], s
ok(f"M2 {len(seeds)} Gruppen nacheinander (feste Naht, unbekannt, frei, Gehrungen, vorgegebene Stangen, "
   "Zuschnitt): Kontrolle nie angeschlagen, Ergebnis wie mit leerem Zwischenspeicher")

# ------------------------------------------------------------------ M3 wirksamer Nahtwinkel
RE = dict(form="Rechteckrohr", a=60, b=40)
QR = dict(form="Quadratrohr", a=40)
RR = dict(form="Rundrohr", a=42.4)
assert naht.wirksamer_winkel(RE, 50) == 0 and naht.wirksamer_winkel(RE, 70) == 90
assert naht.wirksamer_winkel(RE, 200) == 180 and naht.wirksamer_winkel(RE, 300) == 270
assert naht.wirksamer_winkel(RE, 56.3) is None              # Ecke: Seite nicht eindeutig
assert naht.wirksamer_winkel(QR, 40) == 0 and naht.wirksamer_winkel(QR, 45) is None
assert naht.wirksamer_winkel(RR, 50) == 50 and naht.wirksamer_winkel(RE, None) is None
assert naht.seite(RE, 50)["flaeche"] == naht.BREITSEITE     # wie die Optimierung jetzt rechnet
ok("M3 wirksamer Nahtwinkel: Kasten = Seitenmitte wie Spalte und Prüfung, Ecke nicht drehen, Rundrohr unverändert")

# ------------------------------------------------------------------ M4 Dialog für mehrere Positionen, Optimieren
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "a.db")
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
W = "S355-10219"
gehrung = dict(a_gerade="nein", b_gerade="nein", a_ende=naht.ende_text(45, 90), b_ende=naht.ende_text(45, 270))
for pos, artikel, profil, laenge, stk, extra in (
        (10, "R1", "RE 60x40x3", 700, 6, dict(naht_vorgabe=naht.FEST, naht_winkel=0, naht_quelle="Import")),
        (20, "R2", "RE 60x40x3", 455, 8, dict(naht_vorgabe=naht.FEST, naht_winkel=180, naht_quelle="Import")),
        (30, "R3", "RE 60x40x3", 1210, 5, gehrung),
        (40, "Q1", "QR 40x40x3", 830, 6, {}),
        (50, "K1", "RR 42,4x2,0", 620, 6, {})):
    db.position_neu(a, dict(pos=pos, artikel=artikel, profil_id=profil, werkstoff_id=W, laenge=laenge, stueck=stk,
                            **extra))
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
seite = fenster.angebot_oeffnen(a)
gesehen = {}


def nur_quelle(d):
    """Nur die Quelle ändern: verschiedene Winkel bleiben je Position."""
    gesehen["text"] = d.info.text()
    d.quelle.setCurrentText("Zeichnung")
    return QDialog.Accepted


assert seite.schweissnaht([0, 1, 2], dialog=nur_quelle)
assert "verschiedene Nahtwinkel" in gesehen["text"], gesehen
p = {q["artikel"]: q for q in db.positionen(a)}
assert (p["R1"]["naht_winkel"], p["R2"]["naht_winkel"], p["R3"]["naht_winkel"]) == (0, 180, 0)
assert {p[x]["naht_quelle"] for x in ("R1", "R2", "R3")} == {"Zeichnung"}
assert p["R3"]["naht_vorgabe"] == naht.FEST


def winkel_90(d):
    d.winkel.setValue(90)
    return QDialog.Accepted


assert seite.schweissnaht([0, 1], dialog=winkel_90)          # Winkel geändert: gilt für alle markierten
p = {q["artikel"]: q for q in db.positionen(a)}
assert (p["R1"]["naht_winkel"], p["R2"]["naht_winkel"]) == (90, 90)
# Winkel eines Rundrohrs (50°) für Rundrohr, Rechteck- und Quadratrohr: Kasten auf die Seitenmitte (RE 60x40: Ecke
# bei 56,3°, also oben; QR: Ecke bei 45°, also rechts), Lage nur RE
assert seite.schweissnaht([4, 0, 3], werte=dict(naht_vorgabe=naht.FEST, naht_winkel=50.0, naht_quelle="manuell",
                                                querschnitt_lage=naht.SCHMAL_OBEN))
p = {q["artikel"]: q for q in db.positionen(a)}
assert (p["K1"]["naht_winkel"], p["R1"]["naht_winkel"], p["Q1"]["naht_winkel"]) == (50, 0, 90), \
    [(p[x]["naht_winkel"], p[x]["naht_vorgabe"]) for x in ("K1", "R1", "Q1")]
assert p["K1"]["querschnitt_lage"] is None and p["Q1"]["querschnitt_lage"] is None
assert p["R1"]["querschnitt_lage"] == naht.SCHMAL_OBEN
assert seite.optimieren(), "Optimieren mit fester Naht an mehreren Positionen"
assert seite.stand_optimierung() == "aktuell", seite.stand_optimierung()
ok("M4 Dialog für mehrere Positionen: eigene Winkel bleiben, geänderter Winkel gilt für alle, Kasten auf "
   "Seitenmitte, Lage nur Rechteckrohr; Optimieren danach aktuell")

# ------------------------------------------------------------------ M5 Angebot wie gemeldet (nur gerade Teile)
# Fünf Positionen RE 60x40x3 mit fester Naht oben bzw. unten: vorher „Kontrolle hat angeschlagen: Teile fehlen oder
# doppelt“ schon beim ersten Optimieren nach dem Programmstart
a2 = db.angebot_neu(dict(kunde="Test", maschine="T03"))
for pos, laenge, stk in ((10, 830, 12), (20, 620, 8), (30, 1210, 9), (40, 2110, 11), (50, 300, 12)):
    db.position_neu(a2, dict(pos=pos, artikel=f"T{pos}", profil_id="RE 60x40x3", werkstoff_id=W, laenge=laenge,
                             stueck=stk))
seite2 = fenster.angebot_oeffnen(a2)
assert seite2.schweissnaht([1, 3, 4], werte=dict(naht_vorgabe=naht.FEST, naht_winkel=0, naht_quelle="Kunde",
                                                 querschnitt_lage=None))
assert seite2.schweissnaht([0, 2], werte=dict(naht_vorgabe=naht.FEST, naht_winkel=180, naht_quelle="Kunde",
                                              querschnitt_lage=None))
leeren()
assert seite2.optimieren(), "Kontrolle der Optimierung angeschlagen"
assert seite2.stand_optimierung() == "aktuell"
ok("M5 fünf Positionen mit fester Naht oben/unten: Optimieren ohne Fehler (vorher Teile doppelt/fehlend)")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
