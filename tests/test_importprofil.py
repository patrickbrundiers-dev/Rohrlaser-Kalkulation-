"""STEP-Import mit Bauteilnamen: Artikelnummer aus dem Namen, Normteile abgewählt, Importprofile je Kunde.

Aufruf: python tests/test_importprofil.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import importprofil, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import BENENNUNGEN, EINSTELLUNG, TABELLE  # noqa: E402

GESTELL = HIER / "step_struktur" / "S01_Gestell_verschachtelt.step"
EINZEL = HIER / "step_struktur" / "S02_Einzelteil_benannt.step"
OHNE_NAMEN = HIER / "step_satz" / "T08_Gestell_Baugruppe.step"
tmp = Path(tempfile.mkdtemp())

# 1. Benennung und Muster
m = dict(datei="Gestell.step", artikel="Gestell-K3", bauteil="4711-02 Strebe QR40x3")
assert importprofil.artikel_aus(m, BENENNUNGEN[0]) == ("4711-02", "4711-02 Strebe QR40x3")   # Nummer im Namen
assert importprofil.artikel_aus(m, BENENNUNGEN[1]) == ("Gestell-K3", None)
assert importprofil.artikel_aus(m, BENENNUNGEN[2]) == ("Gestell-4711-02", "4711-02 Strebe QR40x3")
assert importprofil.artikel_aus(m, BENENNUNGEN[0], r"^([\d-]+)") == ("4711-02", "4711-02 Strebe QR40x3")
assert importprofil.artikel_aus(m, BENENNUNGEN[0], r"\d{4}") == ("4711", "4711-02 Strebe QR40x3")
assert importprofil.artikel_aus(m, BENENNUNGEN[0], r"(ungültig") == ("4711-02", "4711-02 Strebe QR40x3")
assert importprofil.artikel_aus(dict(artikel="X-K1", bauteil=""), BENENNUNGEN[0]) == ("X-K1", None)
print("OK: Artikel aus Bauteilname, Dateiname oder beidem; Muster mit Klammerausdruck")

# 2. Normteile: ganze Wörter, Groß-/Kleinschreibung egal
liste = importprofil.begriffe(EINSTELLUNG["step_normteile"].vorgabe)
assert importprofil.normteil("Schraube ISO 4017 M8x20", liste) == "ISO"
assert importprofil.normteil("Sechskantmutter DIN 934", liste) == "DIN"
assert importprofil.normteil("Unterlegscheibe", liste) is None          # nur ganze Wörter
assert importprofil.normteil("scheibe 8,4", liste) == "Scheibe"
assert importprofil.normteil("Strebe QR40x3", liste) is None
assert importprofil.normteil("Dinkelhalter", liste) is None
mw = [dict(datei="a.step", artikel="a-K1", bauteil="Holm"), dict(datei="a.step", artikel="a-K2", bauteil="Mutter M8"),
      dict(datei="a.step", artikel="a-K3", bauteil="Lasche 12")]
assert importprofil.anwenden(mw, dict(normteile="Lasche"), {"step_normteile": "Mutter"}) == 2
assert [m.get("_normteil") for m in mw] == [None, "Mutter", "Lasche"]
assert not step.gewaehlt(mw[1]) and step.gewaehlt(mw[0]) and step.gewaehlt(dict(mw[1], _uebernehmen=True))
importprofil.anwenden(mw, dict(benennung=BENENNUNGEN[1]), {})        # wieder anwenden: vom gemessenen Artikel aus
assert [m["artikel"] for m in mw] == ["a-K1", "a-K2", "a-K3"] and "_normteil" not in mw[1]
print("OK: Normteile (Einstellung + Importprofil), im Prüfdialog abgewählt, erneut anwendbar")

# 3. Importprofil je Kunde (Stammdatentabelle) und Import im Angebot
assert TABELLE["importprofile"].feld("kundennr").auswahl == "kunde"
db = Datenbank(tmp / "rohrlaser.db")
db.neu("kunden", dict(kundennr="20001", name="Gestellbau GmbH"))
db.neu("importprofile", dict(kundennr="20001", benennung=BENENNUNGEN[0], muster=r"^(\S+ \S+)",
                             normteile="Querrohr", werkstoff_id="S235-10219", anbau_weglassen="nein"))
assert importprofil.fuer_kunde(db, "20001")["muster"] == r"^(\S+ \S+)" and importprofil.fuer_kunde(db, "1") is None
assert importprofil.vorgaben(importprofil.fuer_kunde(db, "20001")) == dict(werkstoff="S235-10219",
                                                                          anbau_weglassen=False)

from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
ohne = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Andere")))
erg = ohne.step_importieren([str(GESTELL), str(EINZEL), str(OHNE_NAMEN)], "S235-10219", 1, als_satz=False)
artikel = {p["artikel"] for p in erg["positionen"]}
assert {"Holm RE60x40x3 L800", "Strebe QR40x3 L500", "Querrohr RR42.4x2 L600", "4711"} <= artikel, \
    artikel
assert not any("Schraube" in a for a in artikel), "Normteile werden nicht übernommen"
assert {"T08_Gestell_Baugruppe-K1"} <= artikel, "Dateien ohne Namen wie bisher"
assert any("Normteil (Schraube ISO 4017 M8x20, Begriff ISO)" in b for b in erg["bericht"]), erg["bericht"]
mit = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Gestellbau GmbH", kundennr="20001")))
assert mit.importprofil()["kundennr"] == "20001"
erg = mit.step_importieren([str(GESTELL)], None, 1, als_satz=False)
pos = {p["artikel"]: p for p in erg["positionen"]}
assert set(pos) == {"Holm RE60x40x3", "Strebe QR40x3"}, set(pos)        # Querrohr = Normteil laut Profil
assert pos["Holm RE60x40x3"]["bezeichnung"] == "Holm RE60x40x3 L800"
assert all(p["werkstoff_id"] == "S235-10219" for p in erg["positionen"])  # Werkstoff aus dem Profil
print("OK: Import im Angebot mit Bauteilnamen, Normteilen und Importprofil des Kunden")
