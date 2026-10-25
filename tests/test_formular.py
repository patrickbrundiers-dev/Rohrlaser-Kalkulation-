"""Anfrageformular lesen (Plan W6b): Anfragenummer, Kunde und Stückzahlen je Artikelnummer aus einem PDF mit Text;
im Anfrage-Ordner wird daraus der Unterordner 'Kunde – Nummer', das Feld „Ihre Anfrage“ und die Stückzahl im
STEP-Import (Formular gilt, unsichere Werte markiert).

Aufruf: python tests/test_formular.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from rohrlaser import formular  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def pdf(pfad, zeilen):
    c = canvas.Canvas(str(pfad), pagesize=A4)
    y = 800
    for z in zeilen:
        c.drawString(50, y, z)
        y -= 16
    c.save()
    return pfad


tmp = Path(tempfile.mkdtemp())
kunden = [dict(kundennr="10233", name="Anlagenbau Hessler"), dict(kundennr="10417", name="Metallbau Krüger"),
          dict(kundennr="1", name="Muster Rohrlaser GmbH")]
FORM = ["Metallbau Krüger GmbH · Hafenstraße 3 · 28195 Bremen", "An: Muster Rohrlaser GmbH",
        "Anfrage-Nr.: AN-2026-0815          Datum: 25.10.2026", "",
        "Pos  Artikel-Nr.        Bezeichnung          Menge",
        "10   MG-01              Stiel                20 Stk", "20   MG 02              Riegel lang          8",
        "30   T02_RR42-4x2_L860_Bohrung   Rundrohr   25 Stück", "40   XY-9               fehlt im STEP        3 Stk"]

# ------------------------------------------------------------------ Auswertung
text = formular.pdf_text(pdf(tmp / "anfrage.pdf", FORM))
assert "AN-2026-0815" in text and "Riegel lang" in text, text
assert formular.anfragenummer(text) == "AN-2026-0815"
assert formular.anfragenummer("Ihre Anfrage vom 12.10.") is None
assert formular.anfragenummer("Bestellnummer: 4500123456") == "4500123456"
assert formular.kunde(text, kunden, eigene=["Muster Rohrlaser GmbH"]) == "10417"
st = formular.stueckzahlen(text, ["MG-01.stp", "MG-02", "T02_RR42-4x2_L860_Bohrung.step", "ZZ-77"])
assert st == {"MG-01.stp": (20, True), "MG-02": (8, False), "T02_RR42-4x2_L860_Bohrung.step": (25, True)}, st
assert formular.pdf_text(tmp / "fehlt.pdf") == "" and formular.pdf_text(pdf(tmp / "leer.pdf", [])) .strip() == ""
m = [dict(datei="MG-01.stp", artikel="MG-01"), dict(datei="b.stp", artikel="MG 02"), dict(datei="c.stp"),
     dict(datei="d.stp", artikel="MG-01", _saetze=2)]
assert formular.stueck_setzen(m, st) == 2
assert (m[0]["_stueck"], m[0]["_stueck_formular"]) == (20, True) and (m[1]["_stueck"], m[1]["_stueck_formular"]) == (8, False)
assert "_stueck" not in m[2] and "_stueck" not in m[3]
ok("Formular mit Text: Anfragenummer, Kunde (nicht die eigene Firma), Stückzahl je Artikel/Datei, sicher/unsicher")

# ------------------------------------------------------------------ Anfrage-Ordner mit Formular und echtem STEP-Import
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
k = db.zeilen("kunden")[0]
o = tmp / "Eingang"
eingang = o / "neu"
eingang.mkdir(parents=True)
shutil.copy(HIER / "step" / "T02_RR42-4x2_L860_Bohrung.step", eingang)
pdf(eingang / "Anfrage.pdf", [f"{k['name']}", "Anfrage-Nr.: AN-77", "Pos Artikel Menge",
                              "1 T02_RR42-4x2_L860_Bohrung 25 Stk"])
alt = time.time() - 120
for d in eingang.iterdir():
    os.utime(d, (alt, alt))
db.einstellung_setzen("anfrage_ordner", str(o))
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
karte = fenster.start.anfragen
karte.neu_laden()
assert karte.liste.count() == 1
seite = karte.oeffnen([karte.anfragen[0]])
assert seite is not None and seite.kopf.get("kundenreferenz") == "AN-77", seite and seite.kopf.get("kundenreferenz")
assert seite.kopf.get("kundennr") == k["kundennr"], seite.kopf.get("kundennr")
pos = [p for p in seite.positionen if p.get("artikel") or p.get("profil")]
assert pos and all(p.get("stueck") == 25 for p in pos), [(p.get("artikel"), p.get("stueck")) for p in pos]
ziel = fenster.angebot_ordner(seite.kopf)
assert (ziel / "STEP" / "T02_RR42-4x2_L860_Bohrung.step").exists() and (ziel / "Anfrage" / "Anfrage.pdf").exists()
assert not any(o.iterdir()), list(o.iterdir())
ok("Anfrage mit Formular: Ordner 'Kunde – Nummer', Kunde vorgeschlagen, Ihre Anfrage = Nummer, Stückzahl 25 aus dem "
   "Formular, Dateien im Angebotsordner")
print("Alle Tests bestanden.")
