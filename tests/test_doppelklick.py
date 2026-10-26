"""Doppelklick auf den Status einer Position führt zur Lösung: passender Dialog (Schneidweg-Rechner, Zukaufteile,
Bohrungen …) oder die Zelle, in der etwas fehlt, öffnet sich zum Eintragen (STATUS_ZIELE in angebot_fenster).

Aufruf: python tests/test_doppelklick.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402
from rohrlaser import rechnen, step  # noqa: E402
from rohrlaser.angebot_fenster import status_ziel  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

fehler = []


def bearbeitet(app, v, sekunden=3.0):
    """True, sobald die Tabelle eine Zelle bearbeitet. Unter Last (viele Tests gleichzeitig) öffnet der Editor erst
    nach einigen Ereignisrunden, daher bis zu sekunden warten statt nur einmal processEvents."""
    import time
    ende = time.monotonic() + sekunden
    while v.state() != QAbstractItemView.EditingState and time.monotonic() < ende:
        app.processEvents()
        time.sleep(0.01)
    return v.state() == QAbstractItemView.EditingState


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


@fall("Status-Texte: jeder Hinweis, jede Warnung und jeder Fehler mit Lösung hat ein Ziel")
def _():
    erwartet = {
        "FEHLER: Profil unbekannt": "feld:profil_id", "FEHLER: Werkstoff unbekannt": "feld:werkstoff_id",
        "FEHLER: Oberfläche unbekannt": "feld:oberflaeche", "FEHLER: Teilelänge fehlt": "feld:laenge",
        "FEHLER: Stückzahl fehlt": "feld:stueck", "FEHLER: Teil länger als Nutzlänge": "feld:laenge",
        "FEHLER: Stange länger als Maschine zulässt": "feld:stange",
        "FEHLER: Hüllkreis größer als Maschine zulässt": "feld:profil_id",
        "FEHLER: Zukaufartikel fehlt (Zukaufteile …)": "zukaufteile",
        "WARNUNG: EK fehlt (Zukaufteil ohne Einkaufspreis)": "zukauf_ek",
        "FEHLER: Nahtwinkel fehlt (Schweißnaht …)": "schweissnaht",
        "WARNUNG: nicht vollständig eingeplant": "optimieren",
        "WARNUNG: kein gültiger Materialpreis": "feld:preis_m",
        "WARNUNG: Oberfläche verzinkt ist für Edelstahl": "feld:oberflaeche",
        "WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz": "feld:stueck",
        "WARNUNG: Zusatzarbeit 'Entgraten' unbekannt": "zusatzarbeiten",
        "WARNUNG: " + rechnen.KONTUR_ZU_KLEIN: "schneidweg_berechnen",
        "HINWEIS: Schneidweg fehlt": "schneidweg_berechnen",
        "HINWEIS: keine Schneiddaten": "feld:zeit_manuell",
        "HINWEIS: Bohrungen prüfen (Doppelklick)": "bohrungen_pruefen",
        "HINWEIS: Schneidzeit manuell": "feld:zeit_manuell",
        "HINWEIS: Material vom Kunden beigestellt": "feld:material_herkunft",
    }
    for text, ziel in erwartet.items():
        assert (status_ziel(text) or (None,))[0] == ziel, (text, status_ziel(text))
    assert status_ziel("OK") is None and status_ziel("") is None


@fall("Angebot: Doppelklick auf den Status öffnet Zelle bzw. Dialog, ausgeblendete Spalte wird eingeblendet")
def _():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        gut = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000, stueck=4)
        db.position_neu(a, dict(gut, pos=10, laenge=None))                       # Teilelänge fehlt
        db.position_neu(a, dict(gut, pos=20, profil_id="QR 999"))                # Profil unbekannt
        db.position_neu(a, dict(gut, pos=30))                                    # Schneidweg fehlt
        db.position_neu(a, dict(gut, pos=40, schneidweg=330, einstiche=6))       # OK
        seite = fenster.angebot_oeffnen(a)
        fenster.show()
        pm, v = seite.pos_modell, seite.pos_ansicht
        sc = next(c for c in range(pm.columnCount()) if pm.name(c) == "status")
        assert pm.status[0] == "FEHLER: Teilelänge fehlt" and pm.status[1] == "FEHLER: Profil unbekannt", pm.status
        assert pm.status[2] == "HINWEIS: Schneidweg fehlt" and pm.status[3] == "OK", pm.status
        assert "Doppelklick: Teilelänge eintragen" in pm.data(pm.index(0, sc), Qt.ToolTipRole)

        seite._doppelklick(pm.index(0, sc))
        app.processEvents()
        assert pm.name(v.currentIndex().column()) == "laenge" and v.currentIndex().row() == 0
        assert bearbeitet(app, v)
        v.closePersistentEditor(v.currentIndex())
        v.setFocus()
        app.processEvents()

        assert seite.status_beheben(1) == "feld:profil_id" and pm.name(v.currentIndex().column()) == "profil_id"

        aufrufe = []
        seite.schneidweg_berechnen = lambda zeile: aufrufe.append(zeile)
        assert seite.status_beheben(2) == "schneidweg_berechnen" and aufrufe == [2]
        assert seite.status_beheben(3) is None

        seite.spalte_waehlen("stange", False)                                    # ausgeblendete Spalte
        c = next(c for c in range(pm.columnCount()) if pm.name(c) == "stange")
        assert v.isColumnHidden(c)
        assert seite.zelle_bearbeiten(3, "stange") and not v.isColumnHidden(c)
        assert seite.spalten_wahl.get("stange") is True
        fenster.close()
        db.con.close()


@fall("Positionsliste: Schneidweg/Einstiche/STEP-Werte öffnen den Schneidweg-Rechner, Artikel mit 3D die 3D-Ansicht")
def _():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        db.position_neu(a, dict(pos=10, artikel="R1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                                stueck=4, schneidweg=330, einstiche=6, a_schnitt=160))
        db.position_neu(a, dict(pos=20, artikel="Z1", art="Zukaufteil", stueck=2, schneidweg=5))
        seite = fenster.angebot_oeffnen(a)
        fenster.show()
        pm, v = seite.pos_modell, seite.pos_ansicht
        spalte = lambda n: next(c for c in range(pm.columnCount()) if pm.name(c) == n)  # noqa: E731
        rechner, ansicht = [], []
        seite.schneidweg_berechnen = lambda zeile: rechner.append(zeile)
        seite.ansicht_3d = lambda zeile: ansicht.append(zeile)
        for n in ("schneidweg", "einstiche", "a_schnitt"):
            seite._doppelklick(pm.index(0, spalte(n)))
        assert rechner == [0, 0, 0], rechner
        assert "Doppelklick: Schneidweg-Rechner" in pm.data(pm.index(0, spalte("schneidweg")), Qt.ToolTipRole)
        seite._doppelklick(pm.index(1, spalte("schneidweg")))        # Zukaufteil: Zelle bearbeiten
        app.processEvents()
        assert rechner == [0, 0, 0] and bearbeitet(app, v)
        v.closePersistentEditor(v.currentIndex())
        v.setFocus()
        app.processEvents()
        seite._doppelklick(pm.index(0, spalte("artikel")))           # ohne 3D-Daten: Artikelnummer bearbeiten
        app.processEvents()
        assert ansicht == [] and bearbeitet(app, v)
        v.closePersistentEditor(v.currentIndex())
        v.setFocus()
        app.processEvents()
        pm.mit_netz.add(seite.positionen[0]["id"])
        seite._doppelklick(pm.index(0, spalte("artikel")), auf_bild=False)
        assert ansicht == [0] and "Nummer: 3D-Ansicht" in pm.data(pm.index(0, spalte("artikel")), Qt.ToolTipRole)
        seite._doppelklick(pm.index(0, spalte("artikel")), auf_bild=True)      # kleines STEP-Bild: Rechner
        assert ansicht == [0] and rechner[-1] == 0, rechner
        fenster.close()
        db.con.close()


@fall("Schnittplan, Stangenbild und STEP-Protokoll springen zur Position; Kunde im Kopf und Kundenliste")
def _():
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        kunde = db.zeilen("kunden")[0]
        a = db.angebot_neu(dict(kunde=kunde["name"], kundennr=kunde["kundennr"]))
        for pos, laenge in ((10, 1200), (20, 800)):
            db.position_neu(a, dict(pos=pos, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=laenge,
                                    stueck=3, schneidweg=330, einstiche=6))
        seite = fenster.angebot_oeffnen(a)
        fenster.show()
        assert seite.optimieren()
        app.processEvents()
        # Schnittplan: Teile der ersten Stange, Doppelklick auf die zweite Zeile
        seite.stangen_ansicht.setCurrentIndex(seite.stangen_ansicht.model().index(0, 0))
        app.processEvents()
        t = seite.teile.zeilen[-1]
        erwartet = next(r for r, p in enumerate(seite.positionen) if p["pos"] == t["pos"])
        seite.reiter.setCurrentIndex(seite.reiter.indexOf(seite.teile_ansicht.parent().parent()))
        seite.teile_ansicht.doubleClicked.emit(seite.teile.index(len(seite.teile.zeilen) - 1, 0))
        assert seite.reiter.currentWidget() is seite.pos_seite and seite.pos_ansicht.currentIndex().row() == erwartet
        # Stangenbild: Doppelklick mitten auf das erste Teil
        seite.reiter.setCurrentWidget(seite.bild.parent().parent())
        seite.bild.resize(1000, 300)
        seite.bild.grab()
        r, teil = seite.bild.flaechen[0]
        ref = teil["ref"]
        seite.pos_ansicht.setCurrentIndex(seite.pos_modell.index(1 - seite.zur_position(ref), 0))
        seite.reiter.setCurrentWidget(seite.bild.parent().parent())
        QTest.mouseDClick(seite.bild, Qt.LeftButton, Qt.NoModifier, r.center().toPoint())
        zeile = next(z for z, p in enumerate(seite.positionen) if rechnen.schluessel(p, z) == ref)
        assert seite.reiter.currentWidget() is seite.pos_seite and seite.pos_ansicht.currentIndex().row() == zeile
        assert seite.bild.teil_bei(QPoint(1, 1)) is None
        # STEP-Protokoll: Spalte Pos.
        leer = [None] * len(step.PROTOKOLL)
        nr = step.PROTOKOLL.index("Pos.")
        seite.prot.setzen([leer[:nr] + [20] + leer[nr + 1:], leer[:nr] + [99] + leer[nr + 1:]])
        assert seite.protokoll_zur_position(0) == 1 and seite.protokoll_zur_position(1) is None
        # Kunde im Angebotskopf: Doppelklick öffnet ihn im Reiter Kunden
        feld = seite.kopf_bereich.felder["kunde"]
        QTest.mouseDClick(feld, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
        assert fenster.reiter.currentWidget() is fenster.kunden and fenster.kunden.suche.text() == kunde["kundennr"]
        assert fenster.kunden.filter.rowCount() >= 1
        # Kundenliste: Doppelklick zeigt die Angebote des Kunden
        k = fenster.kunden
        k.ansicht.doubleClicked.emit(k.filter.index(0, 0))
        assert fenster.reiter.currentWidget() is fenster.angebote
        assert fenster.angebote.suche.text() == kunde["kundennr"] and fenster.angebote.filter.rowCount() == 1
        assert not k.ansicht.editTriggers() & QAbstractItemView.DoubleClicked
        assert fenster.kunde_zeigen(None) == 0
        fenster.close()
        db.con.close()


@fall("Vorschaubild selbst angelegter Positionen: Rohr (Draufsicht) und Blech (Zuschnitt), neu bei Änderung, "
      "Doppelklick aufs Bild öffnet den Editor")
def _():
    import json
    from rohrlaser import blech, schneidweg as sw
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        a = db.angebot_neu(dict(kunde="Test"))
        tech = json.dumps(dict(quelle=sw.QUELLE, a=dict(form="Gehrung", winkel=45), b={},
                               konturen=[dict(art="Bohrung", d=10, anzahl=2, abstand=200, x=100, seite="oben")]))
        db.position_neu(a, dict(pos=10, artikel="R1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                                stueck=2, technik=tech))
        e = dict(quelle=blech.QUELLE, art=blech.KANTTEIL, dicke=2, kantlaenge=400,
                 schenkel=[dict(laenge=30, winkel=90), dict(laenge=50, winkel=0)])
        db.position_neu(a, dict(pos=20, artikel="B1", art="Zukaufteil", stueck=2, technik=json.dumps(e)))
        db.position_neu(a, dict(pos=30, artikel="Z1", art="Zukaufteil", stueck=2))
        seite = fenster.angebot_oeffnen(a)
        fenster.show()
        pm, v = seite.pos_modell, seite.pos_ansicht
        c = next(c for c in range(pm.columnCount()) if pm.name(c) == "artikel")
        bild = lambda r: pm.data(pm.index(r, c), Qt.DecorationRole)  # noqa: E731
        b0, b1 = bild(0), bild(1)
        assert b0 is not None and not b0.isNull() and b1 is not None and not b1.isNull()
        assert bild(2) is None                                  # Zukaufteil ohne Blech-Editor: kein Bild
        assert bild(0) is b0                                    # einmal gezeichnet
        assert "Schneidweg-Rechner" in pm.data(pm.index(0, c), Qt.ToolTipRole)
        assert "Blech-Editor" in pm.data(pm.index(1, c), Qt.ToolTipRole)
        seite.positionen[0]["laenge"] = 1200                    # geändert: neues Bild
        assert bild(0) is not b0
        rechner, blech_ed = [], []
        seite.schneidweg_berechnen = lambda zeile: rechner.append(zeile)
        seite.blech_bearbeiten = lambda zeile: blech_ed.append(zeile)
        seite._doppelklick(pm.index(0, c), auf_bild=True)
        seite._doppelklick(pm.index(1, c), auf_bild=True)
        assert rechner == [0] and blech_ed == [1], (rechner, blech_ed)
        seite._doppelklick(pm.index(0, c), auf_bild=False)      # Nummer: bearbeiten
        app.processEvents()
        assert rechner == [0] and bearbeitet(app, v)
        v.closePersistentEditor(v.currentIndex())
        fenster.close()
        db.con.close()


sys.exit(1 if fehler else 0)
