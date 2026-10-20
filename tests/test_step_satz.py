"""Prüft den STEP-Import von Baugruppen als Satz (mehrere Körper in einer STEP) und das Sammeln von STEP-Dateien
aus Ordnern (Drag & Drop): gleiche Körper werden eine Position mit 'Stück je Satz', die Stückzahl zählt Sätze.

Aufruf: python tests/test_step_satz.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from rohrlaser import rechnen, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

BAUGRUPPE = HIER / "step_satz" / "T08_Gestell_Baugruppe.step"
tmp = Path(tempfile.mkdtemp())


def koerper(nr, **w):
    m = dict(datei="G.step", artikel=f"G-K{nr}", koerper=str(nr), profilform="Quadratrohr", abm_a="40", abm_b="0",
             wandstaerke="3", flaeche="430", laenge="600", schneidweg="324.5", konturen="3", ende_a="149.7",
             ende_a_gerade="1", ende_b="149.7", ende_b_gerade="1", innen="25.1", innen_konturen="1", gravur="0",
             gravur_konturen="0", bohrungen="8.0:1", innen_liste="8.0:25.1", profil_id_vorschlag="QR 40x40x3",
             hinweise="", fehler="")
    m.update({k: str(v) for k, v in w.items()})
    return m


# 1) Gleiche Teile: Lage und vertauschte Enden egal, kleine Messabweichung erlaubt, andere Maße/Bohrungen nicht
mw = [koerper(1), koerper(2, laenge=600.1), koerper(3, ende_a=120, ende_a_gerade=0),
      koerper(4, ende_b=120, ende_b_gerade=0), koerper(5, laenge=601), koerper(6, bohrungen="10.0:1"),
      koerper(7, datei="H.step", artikel="H"), dict(koerper(8), fehler="defekt")]
assert step.gleiche_teile(mw) == {0: [0, 1], 2: [2, 3], 4: [4], 5: [5], 6: [6]}
assert step.mehrteilig(mw) == {"G.step": (6, 4)}            # H.step hat nur einen Körper
assert step.satzname("Gestell 12.stp") == "Gestell 12"

# 2) Übernahme als Satz: Satz = Dateiname, Stück je Satz = Anzahl gleicher Körper, Stückzahl = Sätze × Stück je Satz
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))     # Messergebnis-JSON nicht neben das Programm
k, gew = db.kontext(), db.zeilen("gewinde")
erg = step.uebernehmen(mw, [], k, gew, None, "S235-10219", 3, saetze=["G.step"])
pos = erg["positionen"]
assert [(p["artikel"], p["satz"], p["je_satz"], p["stueck"]) for p in pos if p.get("satz")] == \
    [("G-K1", "G", 2, 6), ("G-K3", "G", 2, 6), ("G-K5", "G", 1, 3), ("G-K6", "G", 1, 3)]
h = next(p for p in pos if p["artikel"] == "H")
assert not h.get("satz") and h["stueck"] == 3                # Einzelteil-Datei bleibt ohne Satz
assert [p["pos"] for p in pos] == [10, 20, 30, 40, 50]
prot = {z[1] + str(z[2]): z for z in erg["protokoll"]}
assert prot["G.step2"][-2] == 10 and "gleich wie G-K1 (Satz G)" in prot["G.step2"][-1]
assert "Satz G, 2 Stück je Satz (Körper 1, 2)" in prot["G.step1"][-1]
assert len(erg["protokoll"]) == len(mw) and all(len(z) == len(step.PROTOKOLL) for z in erg["protokoll"])
kopf = dict(maschine="T11", stange=6000)
for p in pos:                                                # Stückzahl passt zum Satz
    st = rechnen.status(p, rechnen.position_werte(p, kopf, k, db.tabellen()), kopf, k)
    assert "FEHLER" not in st and "Vielfaches" not in st, st
# Feld „Sätze“ aus dem Prüfdialog: _saetze macht die Datei zum Satz, _je_satz überschreibt die Körperzahl
mw2 = [dict(m, _saetze=5, _stueck=5, **({"_je_satz": 4} if m["artikel"] == "G-K1" else {})) if m["datei"] == "G.step"
       else dict(m, _saetze=0) for m in mw]
pos2 = step.uebernehmen(mw2, [], k, gew, None, "S235-10219", 3)["positionen"]
assert [(p["artikel"], p.get("satz"), p.get("je_satz"), p["stueck"]) for p in pos2] == [
    ("G-K1", "G", 4, 20), ("G-K3", "G", 2, 10), ("G-K5", "G", 1, 5), ("G-K6", "G", 1, 5), ("H", None, None, 3)], pos2
# ohne Stückzahl bleibt sie leer, ohne Satz wie bisher jeder Körper eine Position
assert all(p["stueck"] is None for p in step.uebernehmen(mw, [], k, gew, None, saetze=["G.step"])["positionen"])
einzeln = step.uebernehmen(mw, [], k, gew, None, stueck=3)["positionen"]
assert len(einzeln) == 7 and not any(p.get("satz") for p in einzeln) and all(p["stueck"] == 3 for p in einzeln)
# schon im Angebot: der erste Körper wird übersprungen, die gleichen mit ihm
zweit = step.uebernehmen(mw, pos, k, gew, None, saetze=["G.step"])
assert [p["artikel"] for p in zweit["positionen"]] == []
assert "gleich wie G-K1" in {z[1] + str(z[2]): z for z in zweit["protokoll"]}["G.step2"][-1]

# 2b) Werte je Teil aus dem Prüfdialog: abwählen, Stückzahl, Werkstoff, Profil (gilt bei Sätzen für alle gleichen)
je = [dict(m) for m in mw]
je[0].update(_stueck=4, _werkstoff="S355-10219")
je[1].update(_stueck=4, _werkstoff="S355-10219")
je[2]["_uebernehmen"] = je[3]["_uebernehmen"] = False
je[6].update(_profil="QR 50x50x3", _stueck=7)
e = step.uebernehmen(je, [], k, gew, None, "S235-10219", 3)
w = {p["artikel"]: (p["werkstoff_id"], p["stueck"], p["profil_id"]) for p in e["positionen"]}
assert w == {"G-K1": ("S355-10219", 4, "QR 40x40x3"), "G-K2": ("S355-10219", 4, "QR 40x40x3"),
             "G-K5": ("S235-10219", 3, "QR 40x40x3"), "G-K6": ("S235-10219", 3, "QR 40x40x3"),
             "H": ("S235-10219", 7, "QR 50x50x3")}, w
pr = {z[1] + str(z[2]): z[-1] for z in e["protokoll"]}
assert "im Prüfdialog abgewählt" in pr["G.step3"] and "Profil im Prüfdialog geändert (gemessen QR 40x40x3)" in pr["H.step7"]
assert "Profil fehlt in Stammdaten" in pr["H.step7"]                 # neue ID: ohne Anlegen nur Hinweis
assert step.vorpruefung(je, [], k)[0] == ["QR 50x50x3"]
e = step.uebernehmen(je, [], k, gew, None, neue_profile=True, saetze=["G.step"])
assert [x["profil_id"] for x in e["profile"]] == ["QR 50x50x3"] and e["profile"][0]["a"] == 40.0   # Maße gemessen
assert [(p["artikel"], p["stueck"]) for p in e["positionen"] if p.get("satz")] == [("G-K1", 8), ("G-K5", None),
                                                                                    ("G-K6", None)]
je[6]["_profil"] = "RR 42,4x2,0"                                     # vorhandenes Profil: keine Rückfrage
assert step.vorpruefung(je, [], k)[0] == []

# 3) Dateien sammeln (Drag & Drop): Ordner mit Unterordnern, nur .step/.stp, keine doppelten
o = tmp / "zeichnungen"
(o / "unter").mkdir(parents=True)
for n in ("b.STEP", "a.stp", "unter/c.step", "liesmich.txt"):
    (o / n).write_text("x")
assert step.step_dateien([o, o / "a.stp", tmp / "fehlt.txt"]) == [o / "a.stp", o / "b.STEP", o / "unter" / "c.step"]

# 4) Echte Baugruppe messen und über das Angebotsfenster übernehmen (braucht OpenCascade)
if step.messprogramm(HIER.parent / "programm") is None:
    print("HINWEIS: OpenCascade fehlt, Baugruppe nicht gemessen")
else:
    from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
    from PySide6.QtWidgets import QApplication  # noqa: E402
    from rohrlaser.fenster import Hauptfenster  # noqa: E402
    app = QApplication.instance() or QApplication([])
    fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
    a = db.angebot_neu(dict(kunde="Test"))
    seite = fenster.angebot_oeffnen(a)

    class Ziehen:                                            # wie ein QDropEvent mit gezogenen Dateien
        def __init__(self, pfade):
            self.m = QMimeData()
            self.m.setUrls([QUrl.fromLocalFile(str(p)) for p in pfade])
            self.angenommen = False

        def mimeData(self):
            return self.m

        def acceptProposedAction(self):
            self.angenommen = True

    leer = Ziehen([o / "liesmich.txt"])
    seite.dragEnterEvent(leer)
    assert not leer.angenommen                                # keine STEP-Datei dabei: nicht annehmen
    z = Ziehen([BAUGRUPPE.parent])
    seite.dragEnterEvent(z)
    assert z.angenommen and seite._gezogene_dateien(z) == [BAUGRUPPE]
    seite.dropEvent(z)                                        # ohne Rückfragen: als Satz, Stückzahl leer
    p = db.positionen(a)
    assert [(x["artikel"], x["profil_id"], x["laenge"], x["satz"], x["je_satz"], x["stueck"]) for x in p] == [
        ("T08_Gestell_Baugruppe-K1", "QR 40x40x3", 600.0, "T08_Gestell_Baugruppe", 3, None),
        ("T08_Gestell_Baugruppe-K4", "RR 42,4x2,0", 900.0, "T08_Gestell_Baugruppe", 1, None)], p
    erg = seite.step_importieren([str(BAUGRUPPE)], "S235-10219", 2, als_satz=False)   # Nein: jeder Körper einzeln
    assert [x["artikel"][-2:] for x in erg["positionen"]] == ["K2", "K3"]   # K1 und K4 stehen schon im Angebot
    b = db.angebot_neu(dict(kunde="Test"))
    seite = fenster.angebot_oeffnen(b)
    seite.step_importieren([str(BAUGRUPPE)], "S235-10219", 2, als_satz=False)
    assert [(x["satz"], x["stueck"]) for x in db.positionen(b)] == [(None, 2)] * 4
    c = db.angebot_neu(dict(kunde="Test"))
    seite = fenster.angebot_oeffnen(c)
    seite.step_importieren([str(BAUGRUPPE)], "S235-10219", 2)
    assert [(x["je_satz"], x["stueck"]) for x in db.positionen(c)] == [(3, 6), (1, 2)]
    assert seite.optimieren() and all(st == "OK" or not st.startswith("FEHLER") for st in seite.pos_modell.status)
    # Prüfdialog wie bei der Bedienung: Rohrliste, Werte setzen, Übernehmen
    from PySide6.QtCore import QTimer  # noqa: E402
    from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
    gesehen = {}

    def pruefen():
        d = QApplication.activeModalWidget()
        if not isinstance(d, StepPruefDialog):
            QTimer.singleShot(20, pruefen)
            return
        gesehen["zeilen"] = [(z.it.text(0), z.it.text(1), z.pr.currentText()) for z in d.zeilen]
        gesehen["satzfeld"] = d.satz_feld.isVisibleTo(d) and d.satz_spin.value() == 0
        gesehen["einzeln"] = [z.sp.value() for z in d.zeilen]
        gesehen["vorgabe"] = [(z.ws.currentText(), z.sp.value()) for z in d.zeilen]   # Einstellung, 1 Stück
        d.alle_setzen("S355-10219", 3)
        d.satz_spin.setValue(4)                                       # oben 4 Sätze eintragen
        gesehen["kopf"] = d.baum.headerItem().text(5)
        gesehen["je_satz"] = [z.sp.value() for z in d.zeilen]          # Spalte zeigt jetzt Stück je Satz
        d.zeile_setzen("T08_Gestell_Baugruppe-K4", uebernehmen=False)
        d.baum.setCurrentItem(d.zeilen[0].it)
        gesehen["3d"] = d.ansicht.ansicht.modell is not None
        fenster.stumm = True
        d.accept()
    ap = db.angebot_neu(dict(kunde="Test"))
    sp = fenster.angebot_oeffnen(ap)
    fenster.stumm = False
    QTimer.singleShot(20, pruefen)
    sp.step_importieren([str(BAUGRUPPE)])
    assert gesehen["zeilen"] == [("T08_Gestell_Baugruppe-K1", "3", "QR 40x40x3"),
                                 ("T08_Gestell_Baugruppe-K4", "1", "RR 42,4x2,0")], gesehen
    assert gesehen["3d"] and gesehen["satzfeld"] and gesehen["kopf"] == "Stück je Satz", gesehen
    assert gesehen["je_satz"] == [3, 1], gesehen
    assert gesehen["vorgabe"] == [("S235-10219", 1)] * 2, gesehen
    assert [(x["artikel"], x["werkstoff_id"], x["stueck"], x["je_satz"], x["satz"]) for x in db.positionen(ap)] == [
        ("T08_Gestell_Baugruppe-K1", "S355-10219", 12, 3, "T08_Gestell_Baugruppe")], db.positionen(ap)

    # Sätze leer = Einzelpositionen, ohne Rückfrage; mehrere Dateien: Pfeile wechseln die gezeigte Datei
    def pruefen_mehrere():
        d = QApplication.activeModalWidget()
        if not isinstance(d, StepPruefDialog):
            QTimer.singleShot(20, pruefen_mehrere)
            return
        sichtbar = lambda: [z.it.text(0) for z in d.zeilen if not z.it.parent().isHidden()]
        gesehen["d1"] = (d.datei_text.text(), sichtbar(), d.satz_feld.isVisibleTo(d), d.zurueck.isEnabled())
        d.vor.click()
        gesehen["d2"] = (d.datei_text.text(), sichtbar(), d.satz_feld.isVisibleTo(d), d.vor.isEnabled())
        d.alle_setzen("S235-10219", 5)                                # „Für alle“: auch die andere Datei
        d.zurueck.click()
        gesehen["zurueck"] = d.datei_text.text()
        fenster.stumm = True
        d.accept()
    aq = db.angebot_neu(dict(kunde="Test"))
    sq = fenster.angebot_oeffnen(aq)
    fenster.stumm = False
    QTimer.singleShot(20, pruefen_mehrere)
    einzel = HIER / "step" / "T01_RR42-4x2_L1250.step"
    sq.step_importieren([str(BAUGRUPPE), str(einzel)])
    assert gesehen["d1"] == ("Datei 1 von 2: T08_Gestell_Baugruppe.step",
                             ["T08_Gestell_Baugruppe-K1", "T08_Gestell_Baugruppe-K4"], True, False), gesehen
    assert gesehen["d2"] == ("Datei 2 von 2: T01_RR42-4x2_L1250.step", ["T01_RR42-4x2_L1250"], False, False), gesehen
    assert gesehen["zurueck"].startswith("Datei 1 von 2"), gesehen
    p = db.positionen(aq)
    assert [(x["artikel"][-2:], x["satz"], x["stueck"], x["werkstoff_id"]) for x in p] == [
        ("K1", None, 5, "S235-10219"), ("K2", None, 5, "S235-10219"), ("K3", None, 5, "S235-10219"),
        ("K4", None, 5, "S235-10219"), ("50", None, 5, "S235-10219")], p

    # 3D-Ansicht: jede importierte Position hat ein Netz, Vorschaubild, Dialog; Kopieren nimmt die Netze mit
    from rohrlaser.ansicht3d import ARTEN, entpacken
    netze = db.netze(c)
    assert set(netze) == {x["id"] for x in db.positionen(c)}, netze.keys()
    n = entpacken(netze[db.positionen(c)[0]["id"]])
    assert len(n["p"]) > 300 and "A" in n["t"] and set(n["t"]) <= {a[0] for a in ARTEN}, (len(n["p"]), list(n["t"]))
    assert {"EA", "EB"} <= set(n["l"]), list(n["l"])                    # Schnittkanten als Linien
    c_art = [i for i, (art, x) in enumerate(seite.pos_modell.spalten) if art == "feld" and x.name == "artikel"][0]
    bild = seite.pos_modell.data(seite.pos_modell.index(0, c_art), Qt.DecorationRole)
    assert bild is not None and not bild.isNull() and bild.toImage().pixelColor(32, 9).alpha() > 0
    d = seite.ansicht_3d(1)
    assert d.liste.rowCount() == 2 and d.ansicht.ansicht.modell is not None
    d.ansicht.ansicht.grab()                                            # zeichnet ohne Fehler
    kopie = db.angebot_kopieren(c)
    assert sorted(db.netze(kopie).values()) == sorted(netze.values())
    db.angebot_loeschen(kopie)
    assert not db.netze(kopie) and db.con.execute("SELECT COUNT(*) FROM netze WHERE position_id NOT IN (SELECT id FROM positionen)").fetchone()[0] == 0
    fenster.close()
db.schliessen()
shutil.rmtree(tmp, ignore_errors=True)
print("OK: STEP-Import als Satz und Drag & Drop")
