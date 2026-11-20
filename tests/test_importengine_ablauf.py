"""Importengine im Programm (Laserhub-Vergleich, Patrick 20.11.2026): ganzer Ablauf mit Datenbank und Fenster.

- A1 ZIP-Archiv ins Angebot (stumm wie „STEP importieren“): ZIP entpackt, SolidWorks-Datei als nicht lesbar
  gemeldet, doppelte Datei nur einmal gemessen, Positionen mit gespeicherter Analyse (Kategorie, Konfidenz,
  Merkmale, Kennzahlen) – kein zweites Messen, alle Module lesen sie aus der Position
- A2 Prüfdialog: Schrittleiste oben, Knopf „Importanalyse …“, Erkennungszeile im Infofeld, Fenster mit allen Teilen
- A3 Ablegen eines ZIP mit Herstellerformat: Import startet mit den entpackten Dateien und der Meldung
- A4 Fertigbarkeit (20.11.2026): Grenzwerte als Maschinenfelder in der Datenbank, Import prüft mit der Maschine des
  Angebots, Befunde stehen in der gespeicherten Analyse der Position

Bilder für die Vergleichsseite: IMPORTENGINE_BILDER=Ordner python tests/test_importengine_ablauf.py
Aufruf: python tests/test_importengine_ablauf.py
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import bauteil_analyse as ba  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            import traceback
            fehler += 1
            print(f"FEHLER {name}: {e} ({traceback.extract_tb(e.__traceback__)[-1].line})")
        return fn
    return deko


app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())
BILDER = Path(os.environ["IMPORTENGINE_BILDER"]) if os.environ.get("IMPORTENGINE_BILDER") else None
db = Datenbank(TMP / "rohrlaser.db")
fenster = Hauptfenster(db, TMP, stumm=True)
aid = db.angebot_neu()
seite = fenster.angebot_oeffnen(aid)
T03 = (HIER / "step" / "T03_QR40x3_L2150_Bohrung.step").read_bytes()
R06 = (HIER / "step_regression" / "R06_RE40x30x3_L920_Langloecher.step").read_bytes()
PAKET = TMP / "Anfrage_4711.zip"
with zipfile.ZipFile(PAKET, "w") as zf:
    zf.writestr("Teile/T03_QR40x3.step", T03)
    zf.writestr("Teile/R06_RE40x30x3.step", R06)
    zf.writestr("Teile/T03_QR40x3_Kopie.step", T03)
    zf.writestr("Teile/Halter.SLDPRT", b"\x00" * 100)


@fall("A1 ZIP ins Angebot: entpackt, Herstellerformat gemeldet, Dublette einmal, Analyse in der Position")
def _():
    vorher = len(db.positionen(aid))
    seite.step_importieren([str(PAKET)])
    pos = db.positionen(aid)
    neu = pos[vorher:]
    assert len(neu) == 2, [(p.get("artikel"), p.get("profil_id")) for p in neu]
    v = seite.import_vorbereitung
    assert any("SolidWorks" in b["text"] for b in v.fehler()), v.befunde
    assert any("gleicher Inhalt" in b["text"] for b in v.hinweise()), v.befunde
    kat = sorted(ba.aus_position(p)["kategorie"] for p in neu)
    assert kat == [ba.RECHTECK, ba.VIERKANT], kat
    r06 = next(p for p in neu if ba.aus_position(p)["kategorie"] == ba.RECHTECK)
    a = ba.aus_position(r06)
    assert a["kennzahlen"]["bohrungen"] == 6 and a["kennzahlen"]["ausschnitte"] == 4, a["kennzahlen"]
    assert a["konfidenz"] >= 50 and a["merkmale"], a
    # die entpackte STEP liegt dauerhaft (Kopie in den Angebotsordner, Neu einlesen)
    assert all(Path(d).is_file() for d in seite.step_dateien_zuletzt), seite.step_dateien_zuletzt


@fall("A2 Prüfdialog: Schrittleiste, Knopf Importanalyse, Erkennungszeile")
def _():
    from rohrlaser.step_dialog import StepPruefDialog, _messinfo
    import step_messen
    aus, js = TMP / "m.txt", TMP / "m.json"
    teile = [HIER / "step_importengine" / n for n in ("I01_FO60x30x2_L800_2xBohrung8.step",
                                                      "I06_Baugruppe_gemischt.step")]
    teile.append(HIER / "step_struktur" / "S04_Gestell_Unterbaugruppe_geschweisst.step")
    step_messen.main(["--ausgabe", str(aus), "--json", str(js), "--netze", str(TMP / "netze")] + [str(p) for p in teile])
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(aus), TMP / "netze"), js)
    d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
    text = d.schrittleiste.text()
    for n in ("Import", "Analyse", "Ergebnis", "Kontrolle", "Korrektur", "Kalkulation", "16 Teile", "6 sicher", "2 prüfen"):
        assert n in text, (n, text)
    assert d.analyse_knopf.text().startswith("Importanalyse")
    info = _messinfo(next(m for m in mw if m["profilform"] == "Flachoval"))
    assert "Erkennung: Ovalrohr (Flachoval)" in info and "2 Runde Bohrung" in info, info
    w = d.importanalyse_zeigen(dialog=False)
    assert w.bauteile.rowCount() == 1 + 4 + 3, w.bauteile.rowCount()       # I01, I06 (4 Teile), S04 (3 Teile)
    if BILDER:
        BILDER.mkdir(parents=True, exist_ok=True)
        d.resize(1350, 720)
        d.show()
        app.processEvents()
        d.grab().save(str(BILDER / "pruefdialog_nachher.png"))
        w.resize(1300, 700)
        w.show()
        w.bauteile.selectRow(0)
        app.processEvents()
        w.grab().save(str(BILDER / "importanalyse_ablauf.png"))
        w.close()
    d.reject()


@fall("A3 ZIP mit Herstellerformat ablegen: entpackte Dateien und Herstellerformat gehen in den Import")
def _():
    ordner = TMP / "Ablage"
    ordner.mkdir()
    (ordner / "Rahmen.CATPart").write_bytes(b"V5")
    importe = []
    alt = seite.step_importieren
    seite.step_importieren = lambda dateien=None, **_: importe.append(dateien)
    try:
        seite._drop_importieren([str(PAKET), str(ordner)])
    finally:
        seite.step_importieren = alt
    namen = sorted(Path(p).name for p in importe[0])
    assert "Rahmen.CATPart" in namen and "R06_RE40x30x3.step" in namen and "T03_QR40x3.step" in namen, namen


@fall("A4 Fertigbarkeit: Maschinenfelder in der Datenbank, Prüfung mit der Maschine des Angebots, in der Position")
def _():
    from rohrlaser import db_verbindung, fertigbarkeit
    spalten = set(db_verbindung.spalten(db.con, "maschinen"))
    assert set(fertigbarkeit.FELDER) <= spalten, set(fertigbarkeit.FELDER) - spalten
    vorher = len(db.positionen(aid))
    seite.step_importieren([str(HIER / "step_importengine" / "I07_QR40x3_L800_Fertigbarkeit.step")])
    neu = db.positionen(aid)[vorher:]
    assert len(neu) == 1, len(neu)
    a = ba.aus_position(neu[0])
    regeln = sorted(x["art"] for x in a["merkmale"] if x["merkmal"] == ba.M_FERTIG)
    assert regeln == sorted([fertigbarkeit.LOCH, fertigbarkeit.STEG, fertigbarkeit.STEG_ENDE, fertigbarkeit.GRAVUR]), \
        regeln
    assert a["kennzahlen"]["fertigbar"] is False and a["kategorie"] == ba.VIERKANT
    texte = [p.text for p in seite.freigabe_punkte()]
    assert any("Konstruktionsregel der Maschine" in t for t in texte), texte


print("ALLE OK" if not fehler else f"{fehler} FEHLER")
sys.exit(1 if fehler else 0)
