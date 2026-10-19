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
kopf = dict(maschine="RL-1", stange=6000)
for p in pos:                                                # Stückzahl passt zum Satz
    st = rechnen.status(p, rechnen.position_werte(p, kopf, k, db.tabellen()), kopf, k)
    assert "FEHLER" not in st and "Vielfaches" not in st, st
# ohne Stückzahl bleibt sie leer, ohne Satz wie bisher jeder Körper eine Position
assert all(p["stueck"] is None for p in step.uebernehmen(mw, [], k, gew, None, saetze=["G.step"])["positionen"])
einzeln = step.uebernehmen(mw, [], k, gew, None, stueck=3)["positionen"]
assert len(einzeln) == 7 and not any(p.get("satz") for p in einzeln) and all(p["stueck"] == 3 for p in einzeln)
# schon im Angebot: der erste Körper wird übersprungen, die gleichen mit ihm
zweit = step.uebernehmen(mw, pos, k, gew, None, saetze=["G.step"])
assert [p["artikel"] for p in zweit["positionen"]] == []
assert "gleich wie G-K1" in {z[1] + str(z[2]): z for z in zweit["protokoll"]}["G.step2"][-1]

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
