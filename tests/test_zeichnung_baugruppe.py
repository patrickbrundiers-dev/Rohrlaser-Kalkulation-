"""Zeichnung einer Schweißbaugruppe lesen (Plan Spalt Naht Gravur S9, Patrick 26.10.2026 „mit einbauen“):
- G1 PDF aus dem CAD: Schweißangaben a4, a 3,5 umlaufend, z7 (a = 4,5), s5, a4 3×100 (200), beidseitig; keine
  Fehltreffer bei Blattformat „A4“, Maßstab, Masse oder Profil „QR 40x40x3“
- G2 Stückliste (Pos., Menge, Benennung) unter der Kopfzeile, Ende der Liste erkannt
- G3 DXF mit TEXT/MTEXT: dieselben Angaben
- G4 a-Maß übernehmen: eine Größe für alle offenen Kehlnähte (sicher), mehrere nach Wanddicke (gelb), gesetzte
  a-Maße bleiben; Abgleich der Stückliste mit den Einzelteilen
- G5 Editor: Knopf „Aus Zeichnung …“ setzt die a-Maße, vergleicht die Stückliste und merkt sich die Zeichnung

Aufruf: python tests/test_zeichnung_baugruppe.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER), str(HIER.parent / "programm")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
from rohrlaser import baugruppe, zeichnung_baugruppe as zb  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
ANGABEN = ["a4", "a 3,5 umlaufend", "z7", "s5", "a4 3x100 (200)", "a3 beidseitig"]
STOERER = ["Blatt A4", "Maßstab 1:5", "Masse 12,5 kg", "QR 40x40x3", "Rohr 1000 lg"]
LISTE = [("Pos.", "Menge", "Benennung"), ("1", "4", "Rohr"), ("2", "1", "Strebe"), ("3", "2", "Blechlasche")]


def ok(t):
    print("OK    ", t)


def pdf(pfad, angaben=ANGABEN, liste=LISTE):
    c = canvas.Canvas(str(pfad), pagesize=landscape(A4))
    c.setFont("Helvetica", 9)
    for i, t in enumerate(list(angaben) + STOERER):
        c.drawString(60 + (i % 3) * 180, 520 - (i // 3) * 40, t)
    for r, zeile in enumerate(liste):
        for k, t in enumerate(zeile):
            c.drawString(520 + k * 60, 200 - r * 14, t)
    c.drawString(520, 200 - len(liste) * 14 - 30, "Werkstoff S235JR")
    c.save()
    return pfad


def dxf(pfad):
    teile = ["0", "SECTION", "2", "ENTITIES"]
    for i, t in enumerate(ANGABEN + STOERER):
        teile += ["0", "TEXT", "8", "TEXT", "10", str(100 + 300 * (i % 3)), "20", str(800 - 60 * (i // 3)), "40", "5",
                  "1", t]
    for r, zeile in enumerate(LISTE):
        for k, t in enumerate(zeile):
            # MTEXT hängt oben links, TEXT auf der Grundlinie: gleiche Zeile = MTEXT eine Schrifthöhe höher
            teile += ["0", "MTEXT" if k == 2 else "TEXT", "8", "STUECKLISTE", "10", str(1000 + 120 * k), "20",
                      str(300 - 20 * r + (5 if k == 2 else 0)), "40", "5", "1", t]
    teile += ["0", "ENDSEC", "0", "EOF"]
    pfad.write_text("\n".join(teile) + "\n", encoding="utf-8")
    return pfad


def pruefen(erg, quelle):
    n = erg["naehte"]
    masse = [(x["nahtart"], x["mass"]) for x in n]
    assert masse == [("Kehlnaht", 4.0), ("Kehlnaht", 3.5), ("Kehlnaht", 4.5), ("Stumpfnaht", 5.0), ("Kehlnaht", 4.0),
                     ("Kehlnaht", 3.0)], (quelle, masse)
    assert n[1]["rundum"] and not n[0]["rundum"] and n[5]["beidseitig"] and not n[1]["beidseitig"], (quelle, n)
    assert (n[4]["anzahl"], n[4]["laenge"], n[4]["abstand"]) == (3, 100.0, 200.0), (quelle, n[4])
    assert zb.a_masse(erg) == [3.0, 3.5, 4.0, 4.5]
    assert erg["stueckliste"] == [dict(pos=1, menge=4, name="Rohr"), dict(pos=2, menge=1, name="Strebe"),
                                  dict(pos=3, menge=2, name="Blechlasche")], (quelle, erg["stueckliste"])


# G1 + G2 PDF
erg = zb.lesen(pdf(tmp / "bg.pdf"))
pruefen(erg, "PDF")
assert erg["hinweise"] == [] and not erg["ocr"], erg["hinweise"]
ok("G1 PDF: Schweißangaben a/z/s, umlaufend, beidseitig, unterbrochen; keine Fehltreffer")
ok("G2 Stückliste unter der Kopfzeile, Ende der Liste erkannt")

# G3 DXF
pruefen(zb.lesen(dxf(tmp / "bg.dxf")), "DXF")
leer = zb.lesen(pdf(tmp / "leer.pdf", angaben=[], liste=[]))
assert leer["naehte"] == [] and leer["stueckliste"] == [] and "Keine Schweißangabe" in leer["hinweise"][0]
ok("G3 DXF mit TEXT/MTEXT: dieselben Angaben; ohne Angaben ein Hinweis")

# G4 a-Maß übernehmen und Abgleich
eins = zb.lesen(pdf(tmp / "eins.pdf", angaben=["a3 umlaufend"]))
bg = baugruppe.leer()
bg["naehte"] = [dict(id="1", nahtart="Kehlnaht", dicke=5), dict(id="2", nahtart="Kehlnaht", mass=2.5, mass_regel=2.5),
                dict(id="3", nahtart="Kehlnaht", mass=5), dict(id="4", nahtart="Stumpfnaht", mass=4)]
assert zb.anwenden(bg, eins) == 2
assert [n.get("mass") for n in bg["naehte"]] == [3.0, 3.0, 5, 4] and "mass_regel" not in bg["naehte"][1]
assert bg["naehte"][0]["mass_quelle"] == "Zeichnung" and "mass_quelle" not in bg["naehte"][2]
bg["naehte"] = [dict(id="1", nahtart="Kehlnaht", dicke=5), dict(id="2", nahtart="Kehlnaht", dicke=8),
                dict(id="3", nahtart="Kehlnaht", dicke=3), dict(id="4", nahtart="Kehlnaht")]
assert zb.anwenden(bg, erg) == 3                      # ohne Wanddicke bleibt offen
assert [n.get("mass") for n in bg["naehte"]] == [3.5, 4.5, 3.0, None], [n.get("mass") for n in bg["naehte"]]
assert all(baugruppe.regel_offen(n) for n in bg["naehte"][:3]), "mehrere Größen: gelb bis bestätigt"
assert zb.abgleich(erg, [dict(name="Rohr", menge=4), dict(name="Strebe", menge=1),
                         dict(name="Blechlasche", menge=2)]) == []
abw = zb.abgleich(erg, [dict(name="Rohr", menge=2), dict(name="Blechlasche", menge=2), dict(name="Schraube M8",
                                                                                           menge=8)])
assert abw == ["Pos. 1 Rohr: Zeichnung 4×, Baugruppe 2×", "Pos. 2 Strebe (1×) fehlt in der Baugruppe",
               "Schraube M8 (8×) steht nicht in der Stückliste der Zeichnung"], abw
ok("G4 a-Maß aus der Zeichnung (eine Größe sicher, mehrere nach Wanddicke gelb), Abgleich der Stückliste")

# G5 Editor
from beispiel_baugruppe import anlegen  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
db = Datenbank(tmp / "e.db")
a = anlegen(db)
positionen = db.positionen(a)
bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 60.0}, db=db)
d.bg["naehte"][0].pop("mass")
d.bg["naehte"][1].update(mass=2.5, mass_regel=2.5)
r = d.aus_zeichnung(tmp / "eins.pdf", melden=False)
assert r["geaendert"] == 2 and r["a_masse"] == [3.0], r
assert [n.get("mass") for n in d.bg["naehte"]] == [3.0, 3.0, 4], [n.get("mass") for n in d.bg["naehte"]]
assert d.bg["zeichnung"]["datei"] == "eins.pdf"
r = d.aus_zeichnung(tmp / "bg.pdf", melden=False)
assert r["abweichungen"] == [], r["abweichungen"]                 # Rohr 4, Strebe 1, Lasche 2 wie R1
assert d.bg["zeichnung"]["stueckliste"] == 3
ok("G5 Editor: „Aus Zeichnung …“ setzt die a-Maße, Stückliste passt zu Rahmen R1")
