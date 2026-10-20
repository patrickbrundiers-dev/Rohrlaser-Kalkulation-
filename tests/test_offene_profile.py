"""Prüft U-, C-, L-Profile und Flachstahl im Programm (seit 20.10.2026 kalkuliert): Querschnitt, Hüllkreis, Umfang
und Trennschnitt aus den Stammdaten, Profil-ID aus dem Namen, Angebotstext, Prüfregeln, Erweiterung älterer
Datendateien und eine durchgerechnete Kalkulation mit offenen Profilen.

Sollwerte von Hand aus den Maßen (scharfkantig, ohne Radien).
Aufruf: python tests/test_offene_profile.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import optimierung as opt, rechnen  # noqa: E402
from rohrlaser.ausgabe import profiltext  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import PROFILE, flaeche_berechnet, flaeche_wirksam, huellkreis, pruefen  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def nah(ist, soll, tol=1e-6):
    assert ist is not None and abs(ist - soll) <= tol, f"ist {ist}, soll {soll}"


U = dict(profil_id="U 50x30x3", form="U-Profil", a=50, b=30, wand=3)
L = dict(profil_id="L 40x40x4", form="L-Profil", a=40, b=40, wand=4)
FL = dict(profil_id="FL 40x5", form="Flachstahl", a=40, wand=5)
C = dict(profil_id="C 100x50x3", form="C-Profil", a=100, b=50, wand=3)


@fall("Querschnitt: U = s(a+2(b−s)), L = s(a+b−s), Flachstahl = a·s, C nur über Fläche manuell")
def _():
    nah(flaeche_berechnet(U), 3 * (50 + 54))
    nah(flaeche_berechnet(L), 4 * 76)
    nah(flaeche_berechnet(FL), 200)
    assert flaeche_berechnet(C) is None
    nah(flaeche_wirksam(dict(C, flaeche_manuell=500)), 500)


@fall("Hüllkreis: offene Profile Diagonale A×B, Flachstahl Diagonale Breite×Dicke")
def _():
    nah(huellkreis(U), math.hypot(50, 30))
    nah(huellkreis(FL), math.hypot(40, 5))


@fall("Umfang (beide Seiten) und gerader Trennschnitt (halber Umfang)")
def _():
    nah(opt.umfang("U-Profil", 50, 30, 3, flaeche_berechnet(U)), 2 * 50 + 4 * 30 - 2 * 3)
    nah(opt.schnittlaenge("U-Profil", 50, 30, 3, flaeche_berechnet(U)), 50 + 2 * 30 - 3)
    nah(opt.schnittlaenge("L-Profil", 40, 40, 4, flaeche_berechnet(L)), 80)
    nah(opt.schnittlaenge("Flachstahl", 40, None, 5, 200), 45)
    nah(opt.schnittlaenge("Rechteckrohr", 60, 40), 200)          # Rohre unverändert


@fall("Profil-ID aus dem Namen: U/C/L mit 3 Zahlen, FL mit 2")
def _():
    assert opt.profil_aus_name("U 50x30x3") == dict(form="U-Profil", a=50, b=30, wand=3)
    assert opt.profil_aus_name("L 40x40x4") == dict(form="L-Profil", a=40, b=40, wand=4)
    assert opt.profil_aus_name("C 100x50x3") == dict(form="C-Profil", a=100, b=50, wand=3)
    assert opt.profil_aus_name("FL 40x5") == dict(form="Flachstahl", a=40, b=None, wand=5)
    assert opt.profil_aus_name("FL 5x40") is None


@fall("Prüfregeln: B fehlt, C ohne Fläche, Flachstahl Dicke < Breite")
def _():
    class K:
        def auswahl(self, quelle):
            return ["U-Profil", "C-Profil", "L-Profil", "Flachstahl"]
    k = K()
    assert pruefen(PROFILE, U, k) == "OK"
    assert pruefen(PROFILE, dict(U, b=None), k) == "FEHLER: Abmessung B fehlt"
    assert pruefen(PROFILE, C, k).startswith("FEHLER: Querschnitt fehlt"), pruefen(PROFILE, C, k)
    assert pruefen(PROFILE, dict(C, flaeche_manuell=500), k) == "OK"
    assert pruefen(PROFILE, FL, k) == "OK"
    assert pruefen(PROFILE, dict(FL, a=30, wand=20), k) == "OK"
    assert pruefen(PROFILE, dict(FL, a=10, wand=12), k).startswith("FEHLER: Dicke"), pruefen(PROFILE, dict(FL, a=10, wand=12), k)


tmp = Path(tempfile.mkdtemp())


@fall("Ältere Datendatei: Profilformen um U, C, L, Flachstahl, I-/H-Träger, T-Profil ergänzt, eigene bleiben")
def _():
    pfad = tmp / "alt" / "rohrlaser.db"
    Datenbank(pfad).schliessen()
    con = sqlite3.connect(pfad)
    con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES ('profilformen', ?)",
                ('"Rundrohr\\nOvalrohr\\nSonderprofil"',))
    con.execute("PRAGMA user_version=11")
    con.commit()
    con.close()
    d = Datenbank(pfad)
    assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert d.einstellung("profilformen").splitlines() == ["Rundrohr", "Ovalrohr", "U-Profil", "C-Profil", "L-Profil",
                                                          "Flachstahl", "I-/H-Träger", "T-Profil", "Sonderprofil"], \
        d.einstellung("profilformen")
    d.schliessen()
    # Datei mit Schema 18: nur die Träger kommen dazu, U/C/L/Flachstahl sind schon da
    con = sqlite3.connect(pfad)
    con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES ('profilformen', ?)",
                ('"Rundrohr\\nU-Profil\\nC-Profil\\nL-Profil\\nFlachstahl\\nSonderprofil"',))
    con.execute("PRAGMA user_version=18")
    con.commit()
    con.close()
    d = Datenbank(pfad)
    assert d.einstellung("profilformen").splitlines()[-3:] == ["I-/H-Träger", "T-Profil", "Sonderprofil"], \
        d.einstellung("profilformen")
    d.schliessen()


IPE = dict(profil_id="IPE 200", form="I-/H-Träger", a=200, b=100, wand=5.6)
TG = dict(profil_id="T 60x40x5x7", form="T-Profil", a=60, b=40, wand=5)


@fall("Träger: Querschnitt aus der Normtabelle, sonst Fläche manuell; Umfang, Hüllkreis, Profil-ID aus dem Namen")
def _():
    nah(flaeche_berechnet(IPE), 2850)
    assert flaeche_berechnet(TG) is None and flaeche_berechnet(dict(IPE, profil_id="I 200x100x5,6x8,5")) is None
    nah(flaeche_wirksam(dict(TG, flaeche_manuell=552)), 552)
    nah(huellkreis(IPE), math.hypot(200, 100))
    nah(opt.umfang("I-/H-Träger", 200, 100, 5.6), 2 * 200 + 4 * 100 - 2 * 5.6)
    nah(opt.schnittlaenge("I-/H-Träger", 200, 100, 5.6), 200 + 2 * 100 - 5.6)
    nah(opt.schnittlaenge("T-Profil", 60, 40, 5), 100)
    assert opt.profil_aus_name("HEB 160") == dict(form="I-/H-Träger", a=160, b=160, wand=8, flaeche_manuell=5430)
    assert opt.profil_aus_name("UPN 100") == dict(form="U-Profil", a=100, b=50, wand=6, flaeche_manuell=1350)
    assert opt.profil_aus_name("I 150x80x5x7") == dict(form="I-/H-Träger", a=150, b=80, wand=5,
                                                       flaeche_manuell=2 * 80 * 7 + 136 * 5)
    assert opt.profil_aus_name("T 60x40x5x7") == dict(form="T-Profil", a=60, b=40, wand=5,
                                                      flaeche_manuell=40 * 7 + 53 * 5)
    assert opt.profil_aus_name("I 150x80x5") is None and opt.profil_aus_name("I 10x80x5x7") is None

    class K:
        def auswahl(self, quelle):
            return ["I-/H-Träger", "T-Profil"]
    assert pruefen(PROFILE, IPE, K()) == "OK"
    assert pruefen(PROFILE, TG, K()).startswith("FEHLER: Querschnitt fehlt"), pruefen(PROFILE, TG, K())
    assert pruefen(PROFILE, dict(TG, flaeche_manuell=552), K()) == "OK"


@fall("Kalkulation mit U-Profil, L-Profil (aus dem Namen angelegt) und Flachstahl")
def _():
    db = Datenbank(tmp / "k" / "rohrlaser.db")
    db.neu("profile", U)
    db.neu("profile", FL)
    k, tab = db.kontext(), db.tabellen()
    assert profiltext("U 50x30x3", k) == "U-Profil 50 x 30 x 3"
    assert profiltext("FL 40x5", k) == "Flachstahl 40 x 5"
    kopf = dict(maschine="T11", stange=6000)
    pos = [dict(pos=10, artikel="U", profil_id="U 50x30x3", werkstoff_id="S235-10219", laenge=800, stueck=4,
                schneidweg=2 * 107 + 25.13 + 18.85, einstiche=4),
           dict(pos=20, artikel="L", profil_id="L 40x40x4", werkstoff_id="S235-10219", laenge=500, stueck=2),
           dict(pos=30, artikel="F", profil_id="FL 40x5", werkstoff_id="S235-10219", laenge=300, stueck=3)]
    gruppen, fehl, neue = rechnen.gruppen_bilden(kopf, pos, k)
    assert not fehl and [p["profil_id"] for p in neue] == ["L 40x40x4"], (fehl, neue)
    # Trennschnitt für gemeinsame gerade Schnitte: halber Umfang (U: 107 mm; Schneidweg 2 × 107 + Bohrungen)
    tu = next(g for g in gruppen if g.profil == "U 50x30x3").teile[0]
    nah(tu.a_schnitt, 107)
    for p in neue:
        db.neu("profile", p)
    k = db.kontext()
    erg = rechnen.optimieren(kopf, pos, k)
    assert not erg["fehler"], erg["fehler"]
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, db.einstellungen())
    w = rechnen.position_werte(pos[0], kopf, k, tab)
    dichte = k.werkstoffe["S235-10219"]["dichte"]
    nah(w["kg_m"], 312 * dichte / 1000, 1e-9)                  # 312 mm² × Dichte
    nah(w["huellkreis"], math.hypot(50, 30))
    assert w["wand"] == 3 and w["vorschub"], w
    for z in zeilen:
        assert z and z["material_position"] > 0 and z["preis_position"] > 0, z
    assert zeilen[0]["laser_position"] > 0, zeilen[0]          # nur U hat einen Schneidweg (wie bei Rohren)
    nah(rechnen.oberflaeche(pos[0], k), 214 * 800 / 1e6)
    db.schliessen()


@fall("Kalkulation mit IPE 200 (aus dem Namen angelegt) und T-Profil mit Fläche manuell")
def _():
    db = Datenbank(tmp / "t" / "rohrlaser.db")
    db.neu("profile", dict(TG, flaeche_manuell=552))
    k, tab = db.kontext(), db.tabellen()
    assert profiltext("T 60x40x5x7", k) == "T-Profil 60 x 40 x 5"
    kopf = dict(maschine="T11", stange=6000)
    pos = [dict(pos=10, artikel="I", profil_id="IPE 200", werkstoff_id="S235-10219", laenge=1000, stueck=2,
                schneidweg=2 * 394.4, einstiche=2),
           dict(pos=20, artikel="T", profil_id="T 60x40x5x7", werkstoff_id="S235-10219", laenge=500, stueck=3,
                schneidweg=200, einstiche=2)]
    gruppen, fehl, neue = rechnen.gruppen_bilden(kopf, pos, k)
    assert not fehl and neue == [dict(profil_id="IPE 200", form="I-/H-Träger", a=200, b=100, wand=5.6,
                                      flaeche_manuell=2850, bemerkung="automatisch aus Profil-ID angelegt")], neue
    for p in neue:
        db.neu("profile", p)
    k = db.kontext()
    assert profiltext("IPE 200", k) == "IPE 200"
    erg = rechnen.optimieren(kopf, pos, k)
    assert not erg["fehler"], erg["fehler"]
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, db.einstellungen())
    dichte = k.werkstoffe["S235-10219"]["dichte"]
    w = rechnen.position_werte(pos[0], kopf, k, tab)
    nah(w["kg_m"], 2850 * dichte / 1000, 1e-9)
    nah(rechnen.position_werte(pos[1], kopf, k, tab)["kg_m"], 552 * dichte / 1000, 1e-9)
    for z in zeilen:
        assert z and z["material_position"] > 0 and z["laser_position"] > 0 and z["preis_position"] > 0, z
    db.schliessen()


sys.exit(1 if fehler else 0)
