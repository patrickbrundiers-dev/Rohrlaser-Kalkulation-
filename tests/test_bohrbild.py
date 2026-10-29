"""Senkungen und Fließlochbohrungen (Flowdrill): Erkennung in der STEP-Messung (tests/step_konturen K04-K06),
Übernahme ins Angebot mit Bohrbild und der Dialog 'Bohrungen prüfen' (bestätigen/ablehnen, Senk-Ø gravieren,
Flowdrill als Gravur oder Loch Ø0,5).

Aufruf: python tests/test_bohrbild.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import bohrbild, dreid, rechnen, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

ORDNER = HIER / "step_konturen"
PI = math.pi
fehler = []


def fall(name):
    def deko(f):
        try:
            f()
            print("OK    ", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fehler.append(name)
            print("FEHLER", name, e)
        return f
    return deko


def nah(a, b, tol=0.05):
    return abs(float(a) - float(b)) <= tol


# 1) Bohrbild ohne Messung: Zeilen aus den Messwerten, Auswirkung je Wahl
@fall("Bohrbild: Zeilen aus Messwerten, Gewinde nach Kernloch, Flowdrill-Kernloch eigene Tabelle")
def _():
    m = dict(bohrungen="5.0:4|10.0:1", senkungen="6.6/12.4:2", fliessloecher="7.3:2")
    z = bohrbild.aus_messung(m, [("M6", 5.0), ("M8", 6.8)])
    assert [(x["art"], x["d"], x["anzahl"], x.get("gewinde")) for x in z] == [
        ("Bohrung", 5.0, 4, "M6"), ("Senkung", 6.6, 2, None), ("Fließloch", 7.3, 2, "M8")], z
    assert all(x["status"] == "offen" for x in z) and z[2]["laser"] == bohrbild.GRAVUR
    assert bohrbild.vorschlag_text(z) == "4xM6; 2xM8" and bohrbild.gewinde_text(z) is None
    assert bohrbild.text(z) == "2x Senkung Ø6,6/12,4; 2x Flowdrill Ø7,3 (M8)", bohrbild.text(z)
    zu = bohrbild.zusatz(z)                    # Vorgabe: Flowdrill = Gravur Ø0,5, Senk-Ø nicht graviert
    assert zu["schneidweg"] == 0 and nah(zu["gravur"], 2 * PI * 0.5) and zu["einstiche"] == 0


@fall("Bohrbild anwenden: Senk-Ø gravieren, Flowdrill als Loch Ø0,5 bzw. abgelehnt = Bohrung, Gewinde")
def _():
    m = dict(senkungen="6.6/12.4:2", fliessloecher="7.3:2")
    z = bohrbild.aus_messung(m, [])
    p = dict(schneidweg=441.5, innen=41.5, einstiche=6, gravur=None, kontur_grenzen="10/50",
             konturen="A:60x200; E:60x200; 6,6x20,7; 6,6x20,7")
    p.update(bohrbild.anwenden(p, z))              # wie beim Import
    assert nah(p["gravur"], 3.1) and p["schneidweg"] == 441.5 and p["einstiche"] == 6, p
    assert rechnen.bohrbild_offen(p)
    neu = [dict(x, status="bestätigt") for x in z]
    neu[0]["gravur"], neu[1]["laser"] = True, bohrbild.LOCH
    f = bohrbild.anwenden(p, neu)
    assert nah(f["gravur"], 2 * PI * 12.4, 0.1), f        # Senk-Ø graviert, Flowdrill-Gravur weg
    assert nah(f["schneidweg"], 441.5 + 2 * PI * 0.5, 0.1) and f["einstiche"] == 8, f
    assert f["konturen"].count("0,5x1,6") == 2 and f["klein_n"] == 4, f
    assert f["gewinde"] == "2xM8" and not rechnen.bohrbild_offen(dict(p, **f))
    p.update(f)
    ab = [dict(x, status="abgelehnt") for x in neu]       # Flowdrill abgelehnt: gelaserte Bohrung Ø7,3
    f = bohrbild.anwenden(p, ab)
    assert nah(f["schneidweg"], 441.5 + 2 * PI * 7.3, 0.15) and f.get("einstiche", p["einstiche"]) == 8, f
    assert "0,5x" not in f["konturen"] and f["konturen"].count("7,3x22,9") == 2, f["konturen"]
    assert f["gravur"] is None and f["gewinde"] is None, f
    # Markierloch Ø0,5 ist gewollt kleiner als die Wand: keine Warnung 'Kontur kleiner als 0,7 × Wand'
    assert rechnen.konturen_pruefen(dict(p, konturen="0,5x1,6", klein_n=1, klein_mm=1.6, mittel_mm=0, gross_mm=0,
                                         schneidweg=10), 3) is None
    # von Hand eingetragene Gewinde bleiben stehen
    f = bohrbild.anwenden(dict(p, gewinde="2xM8; 1xM10"), neu)
    assert f["gewinde"] == "2xM8; 1xM10", f


# 2) Messung: Senkungen und Fließlochbohrungen an Rechteckrohr, Rundrohr und U-Profil
try:
    from step_geometrie import analysiere_datei
except ImportError:
    analysiere_datei = None
    print("HINWEIS: OpenCascade fehlt, Messung und Import nicht geprüft")

if analysiere_datei:
    @fall("Messung K04 Rechteckrohr: 2 Senkungen Ø6,6/12,4, 2 Flowdrill M8 (Ø7,3), Bohrung Ø10")
    def _():
        (t,) = analysiere_datei(ORDNER / "K04_RE60x40x3_Senkung_Flowdrill.step")
        assert t.senkungen == {(6.6, 12.4): 2} and t.fliessloecher == {7.3: 2} and t.bohrungen == {10.0: 1}, \
            (t.senkungen, t.fliessloecher, t.bohrungen)
        # Schneidweg: Enden 2 × 200, Senkungen nur die Bohrung (π × 6,6), Flowdrill nichts, Bohrung π × 10
        assert nah(t.schneidweg, 400 + 2 * PI * 6.6 + PI * 10, 0.1), t.schneidweg
        assert t.konturen == 5 and not t.hinweise, (t.konturen, t.hinweise)
        k = [d for d in t.konturen_liste if d["art"] in ("Senkung", "Fließloch")]
        assert [(d["art"], d["z"], d.get("senk_durchmesser"), d.get("kragen_durchmesser")) for d in k] == [
            ("Senkung", 100.0, 12.4, None), ("Senkung", 100.0, 12.4, None), ("Fließloch", 200.0, None, 11.0),
            ("Fließloch", 420.0, None, 11.0)], k

    @fall("Messung K05 Rundrohr und K06 U-Profil: Senkung Ø5,5/10,4 und Flowdrill M6 (Ø5,4)")
    def _():
        for name in ("K05_RR48-3x4_Senkung_Flowdrill", "K06_U60x30x4_Senkung_Flowdrill"):
            (t,) = analysiere_datei(ORDNER / f"{name}.step")
            assert t.senkungen == {(5.5, 10.4): 1} and t.fliessloecher == {5.4: 1} and not t.bohrungen, \
                (name, t.senkungen, t.fliessloecher, t.bohrungen)
            # Rundrohr 2D: Strahl zur Rohrmitte, außen breiter als Ø5,5 (dreid.bohrung_2d_rundrohr)
            soll = dreid.bohrung_2d_rundrohr(5.5, 48.3, 4) if name.startswith("K05") else PI * 5.5
            assert soll > PI * 5.5 * 1.05 or not name.startswith("K05")
            assert nah(t.innen, soll, 0.05), (name, t.innen)

    @fall("Import: Bohrbild offen, Status HINWEIS, Dialog bestätigt (Senk-Ø gravieren, Flowdrill Loch Ø0,5)")
    def _():
        import step_messen
        from PySide6.QtWidgets import QApplication
        from rohrlaser.bohrbild_dialog import BohrbildDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            step_messen.main(["--ausgabe", str(tmp / "m.txt"), str(ORDNER / "K04_RE60x40x3_Senkung_Flowdrill.step")])
            mw = step.lies_messwerte(tmp / "m.txt")
            assert mw[0]["senkungen"] == "6.6/12.4:2" and mw[0]["fliessloecher"] == "7.3:2", mw[0]
            db = Datenbank(tmp / "rohrlaser.db")
            k, gew = db.kontext(), db.zeilen("gewinde")
            erg = step.uebernehmen(mw, [], k, gew, None, "S235-10219", 5, neue_profile=True)
            (p,) = erg["positionen"]
            assert p["bohrungen"] == "1xØ10; 2x Senkung Ø6,6/12,4; 2x Flowdrill Ø7,3 (M8)", p["bohrungen"]
            assert p["gewinde_vorschlag"] == "2xM8" and not p.get("gewinde") and nah(p["gravur"], 3.1), p
            assert "Bohrungen prüfen" in erg["bericht"][0], erg["bericht"]
            kopf = dict(maschine="T11", stange=6000)
            st = rechnen.status(p, rechnen.position_werte(p, kopf, k, db.tabellen()), kopf, k)
            assert st == "HINWEIS: Bohrungen prüfen (Doppelklick)", st
            d = BohrbildDialog(None, p, [(g["gewinde"], g["kernloch"]) for g in gew])
            assert d.tabelle.rowCount() == 2 and "noch offen" in d.auswirkung.text()
            d.setzen(0, "bestätigt", gravur=True)
            d.setzen(1, "bestätigt", laser=bohrbild.LOCH)
            assert "Gewinde: 2xM8" in d.auswirkung.text() and "Einstiche 5 → 7" in d.auswirkung.text(), \
                d.auswirkung.text()
            d.accept()
            p.update(bohrbild.anwenden(p, *d.ergebnis))
            assert p["gewinde"] == "2xM8" and p["einstiche"] == 7 and nah(p["gravur"], 2 * PI * 12.4, 0.1), p
            st = rechnen.status(p, rechnen.position_werte(p, kopf, k, db.tabellen()), kopf, k)
            assert "Bohrungen" not in st and not st.startswith(("FEHLER", "WARNUNG")), st
            db.con.close()


@fall("Angebot: Spalten Gewinde/Bohrungen öffnen den Dialog (nicht direkt editierbar), Speichern ändert Status")
def _():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        db.position_neu(a, dict(pos=10, artikel="Pfosten", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                laenge=1000, stueck=4, schneidweg=330, einstiche=6,
                                bohrungen="4xØ5", gewinde_vorschlag="4xM6"))
        seite = fenster.angebot_oeffnen(a)
        pm = seite.pos_modell
        c = next(i for i, (art, f) in enumerate(pm.spalten) if art != "berechnet" and f and f.name == "gewinde")
        assert pm.spalten[c][0] == "bohrbild" and not pm.flags(pm.index(0, c)) & Qt.ItemIsEditable
        assert "Doppelklick: Bohrungen prüfen" in pm.data(pm.index(0, c), Qt.ToolTipRole)
        assert pm.status[0] == "HINWEIS: Bohrungen prüfen (Doppelklick)", pm.status
        gew = [(g["gewinde"], g["kernloch"]) for g in db.zeilen("gewinde")]
        z = bohrbild.aus_position(db.positionen(a)[0], gew)
        assert [(x["art"], x["d"], x["gewinde"], x["status"]) for x in z] == [("Bohrung", 5.0, "M6", "offen")], z
        assert seite.bohrungen_pruefen([0], werte=([dict(x, status="bestätigt") for x in z], "1xM10"))
        p = db.positionen(a)[0]
        assert p["gewinde"] == "4xM6; 1xM10" and bohrbild.lesen(p["bohrbild"])[0]["status"] == "bestätigt", p
        assert "Bohrungen" not in pm.status[0], pm.status
        seite.close()
        db.con.close()


# 3) Bohren (< 0,7 × Wand) und Arbeitsschritte Senken, Flowdrill, Bohren als Zusatzarbeit
@fall("Bohren: Bohrung Ø5 in 8 mm Wand vorgeschlagen (Ø0,5 und Ø6 nicht), bestätigt = Laser markiert, Zusatzarbeit")
def _():
    m = dict(bohrungen="5.0:4|0.5:1|6.0:2", senkungen="6.6/12.4:2", fliessloecher="7.3:2")
    z = bohrbild.aus_messung(m, [("M6", 5.0)], wand=8)
    assert [(x["art"], x["d"], x["anzahl"]) for x in z] == [
        ("Bohrung", 5.0, 4), ("Senkung", 6.6, 2), ("Fließloch", 7.3, 2), ("Bohren", 5.0, 4)], z
    assert all(x["d"] != 0.5 for x in bohrbild.aus_messung(m, [], wand=7) if x["art"] == "Bohren")
    assert not [x for x in bohrbild.aus_messung(m, [], wand=None) if x["art"] == "Bohren"]
    assert "4x Bohren Ø5" in bohrbild.text(z)
    p = dict(schneidweg=500.0, innen=180.0, a_schnitt=160, b_schnitt=160, einstiche=10, gravur=None, kontur_grenzen="10/50; 3×/8× Wand 8",
             konturen="A:40x160; E:40x160; 5x15,7; 5x15,8; 5x15,7; 5x15,7; 6x18,8; 6x18,8; 6,6x20,7; 6,6x20,7")
    assert rechnen.konturen_pruefen(p, 8) == rechnen.KONTUR_ZU_KLEIN
    p.update(bohrbild.anwenden(p, z))               # wie beim Import: Bohren offen ändert nichts am Schneidweg
    assert p["schneidweg"] == 500.0 and p["einstiche"] == 10, p
    katalog = [dict(name=n, art="€/Stück", preis=1.0) for n in ("Senken", "Flowdrill", "Bohren")]
    best = [dict(x, status="bestätigt") for x in z]
    f = bohrbild.anwenden(p, best, None, katalog)
    assert nah(f["schneidweg"], 500 - 4 * PI * 5, 0.1) and f["einstiche"] == 6, f      # 4 Bohrungen nur graviert
    assert nah(f["gravur"], 2 * PI * 0.5 + 4 * PI * 0.5, 0.1), f       # Flowdrill + Bohren je Gravur Ø0,5
    assert "5x" not in f["konturen"] and f["konturen"].count("6x18,8") == 2, f["konturen"]
    zu = {e["name"]: e for e in rechnen.zusatz_liste(f)}
    assert {n: e["menge"] for n, e in zu.items()} == {"Senken": 2, "Flowdrill": 2, "Bohren": 4}, zu
    assert all(e["quelle"] == bohrbild.QUELLE and e["stand"]["preis"] == 1.0 for e in zu.values())
    assert rechnen.konturen_pruefen(dict(p, **f), 8) is None, rechnen.konturen_pruefen(dict(p, **f), 8)
    p.update(f)
    # Bohren als Loch Ø0,5, Senken abgelehnt: Zusatzarbeit Senken fällt weg, von Hand Eingetragenes bleibt
    p["zusatz"] = json.dumps(rechnen.zusatz_liste(p) + [dict(name="Entgraten", menge=1)])
    neu = [dict(x) for x in best]
    neu[1]["status"], neu[3]["laser"] = "abgelehnt", bohrbild.LOCH
    f = bohrbild.anwenden(p, neu, None, katalog)
    assert nah(f["schneidweg"], 500 - 4 * PI * 5 + 4 * PI * 0.5, 0.1) and f["einstiche"] == 10, f
    assert {e["name"]: e["menge"] for e in rechnen.zusatz_liste(f)} == {"Flowdrill": 2, "Bohren": 4, "Entgraten": 1}
    assert f["konturen"].count("0,5x1,6") == 4, f["konturen"]
    p.update(f)
    # alles wieder offen: Schneidweg wie gemessen, Zusatzarbeiten aus dem Bohrbild weg
    f = bohrbild.anwenden(p, z, None, katalog)
    assert nah(f["schneidweg"], 500, 0.1) and f.get("einstiche", p["einstiche"]) == 10 and f["konturen"].count("5x15,7") == 4, f
    assert [e["name"] for e in rechnen.zusatz_liste(f)] == ["Entgraten"]
    # abgelehnt: der Laser schneidet die Bohrung bewusst, keine Warnung mehr
    ab = [dict(x, status="abgelehnt") if x["art"] == "Bohren" else x for x in z]
    assert rechnen.konturen_pruefen(dict(p, **bohrbild.anwenden(p, ab)), 8) is None
    # fehlende Zusatzarbeit in den Stammdaten wird gemeldet
    f = bohrbild.anwenden(dict(p, zusatz=None), best, None, katalog[:1])
    assert f["_fehlt"] == ["Flowdrill", "Bohren"], f


@fall("Bohren: ältere Position (Bohrbild ohne Bohren) wird ergänzt, Schneidweg-Rechner bildet Bohrbild neu")
def _():
    from rohrlaser import schneidweg
    p = dict(bohrungen="4xØ5; 1xØ10; 2x Senkung Ø6,6/12,4", gewinde_vorschlag="4xM6")
    z = bohrbild.aus_position(p, [("M6", 5.0)], 8)
    assert [(x["art"], x["d"], x["anzahl"]) for x in z] == [("Bohrung", 5.0, 4), ("Bohren", 5.0, 4)], z
    p["bohrbild"] = bohrbild.schreiben([dict(z[0], status="bestätigt")])
    z = bohrbild.aus_position(p, [("M6", 5.0)], 8)
    assert [(x["art"], x["status"]) for x in z] == [("Bohrung", "bestätigt"), ("Bohren", "offen")], z
    profil = dict(form="Quadratrohr", a=60, b=60, wand=8)
    e = dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=4, d=5), dict(art="Senkung", anzahl=2, d=6.6, D=12.4),
                                   dict(art="Bohrung", anzahl=1, d=10)])
    erg = schneidweg.rechnen(e, profil, (10, 50), [("M6", 5.0)])
    alt = [dict(art="Bohren", d=5.0, anzahl=4, status="bestätigt", laser=bohrbild.LOCH),
           dict(art="Fließloch", d=7.3, anzahl=2, status="offen")]
    neu = bohrbild.aus_rechner(erg, alt, [("M6", 5.0)], 8)
    assert [(x["art"], x["d"], x["anzahl"], x["status"]) for x in neu] == [
        ("Bohrung", 5.0, 4, "bestätigt"), ("Senkung", 6.6, 2, "bestätigt"), ("Bohren", 5.0, 4, "bestätigt")], neu
    assert neu[2]["laser"] == bohrbild.LOCH
    f = bohrbild.anwenden(dict(erg["felder"]), neu)
    assert nah(f["schneidweg"], erg["schneidweg"] - 4 * PI * 5 + 4 * PI * 0.5, 0.1), (f, erg["schneidweg"])


@fall("Bohren 3. Option 'Ø schneiden (ohne Bohren)': Schneidweg wie gemessen, kein Bohren, keine Warnung")
def _():
    from rohrlaser import schneidweg
    assert bohrbild.LASER_BOHREN == (bohrbild.GRAVUR, bohrbild.LOCH, bohrbild.SCHNEIDEN)
    m = dict(bohrungen="5.0:4|6.0:2", fliessloecher="7.3:2")
    z = bohrbild.aus_messung(m, [], bohrbild.LOCH, 8, bohrbild.SCHNEIDEN)
    assert [(x["art"], x.get("laser")) for x in z] == [("Fließloch", bohrbild.LOCH), ("Bohren", bohrbild.SCHNEIDEN)], z
    assert bohrbild.aus_messung(m, [], bohrbild.LOCH, 8)[1]["laser"] == bohrbild.LOCH      # ohne Vorgabe wie bisher
    p = dict(schneidweg=500.0, innen=180.0, einstiche=10, gravur=None, kontur_grenzen="10/50; 3×/8× Wand 8",
             konturen="A:40x160; E:40x160; 5x15,7; 5x15,7; 5x15,7; 5x15,7; 6x18,8; 6x18,8")
    assert rechnen.konturen_pruefen(p, 8) == rechnen.KONTUR_ZU_KLEIN
    katalog = [dict(name=n, art="€/Stück", preis=1.0) for n in ("Senken", "Flowdrill", "Bohren")]
    best = [dict(x, status="bestätigt") for x in z if x["art"] == "Bohren"]
    f = bohrbild.anwenden(p, best, None, katalog)
    assert "schneidweg" not in f and "einstiche" not in f and "konturen" not in f, f      # Ø wird geschnitten
    assert not rechnen.zusatz_liste(dict(p, **f)), f                                     # kein Bohren
    assert bohrbild.arbeiten(best) == {} and bohrbild.arbeit_preise([dict(best[0], preis=2.0)]) == {}
    assert rechnen.konturen_pruefen(dict(p, **f), 8) is None
    assert bohrbild.text(best) == "4x Ø5 geschnitten (ohne Bohren)", bohrbild.text(best)
    # von markieren + Bohren auf Ø schneiden umgestellt: Schneidweg, Einstiche, Konturen und Zusatzarbeit zurück
    p.update(bohrbild.anwenden(p, [dict(best[0], laser=bohrbild.GRAVUR)], None, katalog))
    assert nah(p["schneidweg"], 500 - 4 * PI * 5, 0.1) and p["einstiche"] == 6 and rechnen.zusatz_liste(p)
    f = bohrbild.anwenden(p, best, None, katalog)
    assert nah(f["schneidweg"], 500, 0.1) and f["einstiche"] == 10 and f["konturen"].count("5x15,7") == 4, f
    assert not f.get("gravur") and not rechnen.zusatz_liste(dict(p, **f)), f
    # alle Editoren (Schneidweg-Rechner): Vorgabe Ø schneiden, eingegebene kleine Bohrung bleibt im Schneidweg
    profil = dict(form="Quadratrohr", a=60, b=60, wand=8)
    erg = schneidweg.rechnen(dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=4, d=5)]), profil, (10, 50), [])
    neu = bohrbild.aus_rechner(erg, [], [], 8, bohrbild.GRAVUR, bohrbild.SCHNEIDEN)
    assert [(x["art"], x["status"], x["laser"]) for x in neu] == [("Bohren", "bestätigt", bohrbild.SCHNEIDEN)], neu
    f = bohrbild.anwenden(dict(erg["felder"]), neu, None, katalog)
    assert "schneidweg" not in f and not rechnen.zusatz_liste(f), f
    assert rechnen.konturen_pruefen(dict(erg["felder"], **f), 8) is None
    # Vorgabe in den Einstellungen
    from rohrlaser.stammdaten import EINSTELLUNGEN
    e = next(x for x in EINSTELLUNGEN if x.name == "bohren_laser")
    assert e.vorgabe == bohrbild.GRAVUR, e


@fall("Angebot: Bohren im Dialog vorgeschlagen, Bestätigen trägt Zusatzarbeiten ein, Schneidweg-Rechner behält Status")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.bohrbild_dialog import BohrbildDialog
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        assert {"Senken", "Flowdrill", "Bohren"} <= {z["name"] for z in db.zeilen("zusatzarbeiten")}
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        db.position_neu(a, dict(pos=10, artikel="Halter", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                laenge=1000, stueck=4, schneidweg=330, einstiche=6, innen=10.1,
                                konturen="2x6,3; 2x6,3", bohrungen="2xØ2"))
        seite = fenster.angebot_oeffnen(a)
        p = db.positionen(a)[0]
        gew = [(g["gewinde"], g["kernloch"]) for g in db.zeilen("gewinde")]
        d = BohrbildDialog(None, p, gew, 3, None, db.zeilen("zusatzarbeiten"))
        assert d.tabelle.rowCount() == 1 and d.tabelle.item(0, 0).text().startswith("Bohren"), d.liste
        d.setzen(0, "bestätigt")
        assert "Zusatzarbeiten: 2× Bohren" in d.auswirkung.text(), d.auswirkung.text()
        d.accept()
        assert seite.bohrungen_pruefen([0], werte=d.ergebnis)
        p = db.positionen(a)[0]
        (e,) = rechnen.zusatz_liste(p)
        assert e["name"] == "Bohren" and e["menge"] == 2 and e["stand"]["preis"] > 0, e
        assert nah(p["schneidweg"], 330 - 2 * PI * 2, 0.1) and p["einstiche"] == 4, p
        (w,) = rechnen.zusatz_werte(p, seite.k, seite.tabellen)      # 2 × 0,40 € (Einstellungen)
        assert w["menge"] == 2 and nah(w["betrag"], 2 * 0.40, 0.001), w
        # 3. Option im Dialog: Ø schneiden (ohne Bohren) -> Schneidweg zurück, Zusatzarbeit Bohren weg
        d = BohrbildDialog(None, p, gew, 3, bohrbild.SCHNEIDEN, db.zeilen("zusatzarbeiten"))
        ls = d.laser[0]
        assert [ls.itemText(i) for i in range(ls.count())] == list(bohrbild.LASER_BOHREN)
        d.setzen(0, "bestätigt", laser=bohrbild.SCHNEIDEN)
        d.accept()
        assert seite.bohrungen_pruefen([0], werte=d.ergebnis)
        q = db.positionen(a)[0]
        assert not rechnen.zusatz_liste(q) and nah(q["schneidweg"], 330, 0.1) and q["einstiche"] == 6, q
        assert rechnen.konturen_pruefen(q, 3) is None
        d = BohrbildDialog(None, q, gew, 3, None, db.zeilen("zusatzarbeiten"))
        d.setzen(0, "bestätigt", laser=bohrbild.GRAVUR)
        d.accept()
        assert seite.bohrungen_pruefen([0], werte=d.ergebnis)
        p = db.positionen(a)[0]
        # Schneidweg-Rechner: Bohrbild aus den Eingaben, Bohren bleibt bestätigt, Zusatzarbeit bleibt
        assert seite.schneidweg_berechnen(0, eingaben=dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=2, d=2)]),
                                          ueberschreiben=True)
        p = db.positionen(a)[0]
        (z,) = bohrbild.lesen(p["bohrbild"])
        assert z["art"] == "Bohren" and z["status"] == "bestätigt", z
        assert [e["name"] for e in rechnen.zusatz_liste(p)] == ["Bohren"]
        rw = 2 * (160 - (8 - 2 * PI) * 6) + 2 * PI * 2      # Enden QR 40x40x3 (Umfang, Außenradius 6 nach Norm)
        #                                                   + 2 Bohrungen, dann ohne die Bohrungen
        assert nah(p["schneidweg"] + 2 * PI * 2, rw, 2), p["schneidweg"]
        seite.close()
        db.con.close()


@fall("Preise je Stück: Gewinde, Senken, Flowdrill, Bohren aus den Einstellungen, je Position in Bohrungen prüfen änderbar")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.bohrbild_dialog import BohrbildDialog
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        zs = {z["name"]: z for z in db.zeilen("zusatzarbeiten")}
        assert all(zs[n]["art"] == "€/Stück" and zs[n]["zeit"] is None and zs[n]["preis"] > 0
                   for n in ("Senken", "Flowdrill", "Bohren")), zs
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        db.position_neu(a, dict(pos=10, artikel="Winkel", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                laenge=1000, stueck=4, schneidweg=330, einstiche=6, bohrungen="4xØ5",
                                gewinde_vorschlag="4xM6"))
        seite = fenster.angebot_oeffnen(a)
        p = db.positionen(a)[0]
        p["bohrbild"] = bohrbild.schreiben([dict(art="Bohrung", d=5.0, anzahl=4, gewinde="M6", status="offen"),
                                            dict(art="Senkung", d=6.6, D=12.4, anzahl=2, status="offen")])
        tab = seite.tabellen
        gp = {g["gewinde"]: g.get("preis") for g in tab["gewinde"]}
        d = BohrbildDialog(None, p, [(g["gewinde"], g["kernloch"]) for g in tab["gewinde"]], 3, None,
                           tab["zusatzarbeiten"], rechnen.stundensaetze(tab), gp)
        assert d.preise[0][0].placeholderText() == "0,90" and d.preise[0][1] is None
        assert d.preise[1][0] is None and d.preise[1][1].placeholderText() == "0,40"
        d.setzen(0, "bestätigt", gewinde_preis="1,25")
        d.setzen(1, "bestätigt", preis="0,75")
        t = d.auswirkung.text()
        assert "4xM6 = 5,00 €" in t and "2× Senken à 0,75 €" in t, t
        d.accept()
        assert seite.bohrungen_pruefen([0], werte=d.ergebnis)
        p = db.positionen(a)[0]
        (e,) = rechnen.zusatz_liste(p)
        assert e["name"] == "Senken" and e["menge"] == 2 and e["preis"] == 0.75, e
        assert rechnen.gewinde_preise_position(p) == {"M6": 1.25}
        w = rechnen.gewinde_preis(p["gewinde"], tab["gewinde"], rechnen.gewinde_preise_position(p))
        assert nah(w, 5.0), w
        (zw,) = rechnen.zusatz_werte(p, seite.k, tab)
        assert nah(zw["betrag"], 1.5), zw
        # Preis wieder leeren: Einstellungen gelten
        liste = [dict(x, preis=None, gewinde_preis=None) for x in bohrbild.lesen(p["bohrbild"])]
        assert seite.bohrungen_pruefen([0], werte=(liste, ""))
        p = db.positionen(a)[0]
        assert rechnen.gewinde_preise_position(p) == {} and rechnen.zusatz_liste(p)[0]["preis"] is None
        (zw,) = rechnen.zusatz_werte(p, seite.k, tab)
        assert nah(zw["betrag"], 0.8), zw
        seite.close()
        db.con.close()


@fall("Rechner von Hand: Flowdrill, Spalte Gewinde (automatisch/kein/gewählt), sofort bestätigt mit Zusatzarbeiten")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import schneidweg
    from rohrlaser.fenster import Hauptfenster
    from rohrlaser.schneidweg_dialog import GEWINDE_KEIN, GEWINDE_SPALTE, SchneidwegDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    profil = dict(form="Quadratrohr", a=60, b=60, wand=3)
    e = dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=4, d=5), dict(art="Bohrung", anzahl=2, d=6.8, gewinde=""),
                                   dict(art="Bohrung", anzahl=2, d=10.2, gewinde="M10"),
                                   dict(art="Flowdrill", anzahl=3, d=7.3)])
    erg = schneidweg.rechnen(e, profil, (10, 50), [("M6", 5.0), ("M8", 6.8), ("M12", 10.2)])
    assert not erg["fehler"], erg["fehler"]
    assert erg["felder"]["gewinde_vorschlag"] == "4xM6", erg["felder"]       # nur die automatischen
    neu = bohrbild.aus_rechner(erg, None, [("M6", 5.0), ("M8", 6.8), ("M12", 10.2)], 3)
    art = [(x["art"], x["d"], x["anzahl"], x.get("gewinde"), x["status"]) for x in neu]
    assert art == [("Bohrung", 10.2, 2, "M10", "bestätigt"), ("Bohrung", 5.0, 4, "M6", "bestätigt"),
                   ("Fließloch", 7.3, 3, "M8", "bestätigt")], art
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        db.position_neu(a, dict(pos=10, artikel="Halter", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                laenge=1000, stueck=4))
        seite = fenster.angebot_oeffnen(a)
        assert seite.schneidweg_berechnen(0, e)
        p = db.positionen(a)[0]
        assert p["gewinde"] == "2xM10; 4xM6; 3xM8", p["gewinde"]
        assert {z["name"]: z["menge"] for z in rechnen.zusatz_liste(p)} == {"Flowdrill": 3}, rechnen.zusatz_liste(p)
        assert "Bohrungen prüfen" not in seite.pos_modell.status[0], seite.pos_modell.status[0]
        # Dialog: Spalte Gewinde nur für Bohrung/Flowdrill, Wahl kommt in die Eingaben
        d = SchneidwegDialog(seite, p, seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
        g = {d.tabelle.cellWidget(r, 0).currentText() + str(r): d.tabelle.cellWidget(r, GEWINDE_SPALTE)
             for r in range(d.tabelle.rowCount())}
        assert all(w.isEnabled() for w in g.values()), g
        d.zeile_neu(dict(art="Senkung", anzahl=1, d=6.6, D=12.4))
        r = d.tabelle.rowCount() - 1
        assert not d.tabelle.cellWidget(r, GEWINDE_SPALTE).isEnabled()
        k = d.eingaben()["konturen"]
        assert [z.get("gewinde", "auto") for z in k] == ["auto", "", "M10", "auto", "auto"], k
        assert d.tabelle.cellWidget(1, GEWINDE_SPALTE).currentText() == GEWINDE_KEIN
        d.close()
        seite.close()
        db.con.close()


sys.exit(1 if fehler else 0)
