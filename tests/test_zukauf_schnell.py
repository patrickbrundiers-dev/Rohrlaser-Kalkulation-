"""Prüft die Schnellanlage von Zukaufartikeln im Angebot und die Menge je Satz: Rahmen aus Rohren (Satz) mit
20 Blechen je Rahmen, Lieferant 'Technik' bei Blech vorbelegt, jedes Blech eine eigene Zukaufteil-Position im Satz,
Rechnung mit Sätzen statt Teilen, Staffelpreise je Satz, Dialog Zukaufteile mit 'Neuer Artikel …' und Umschalten je Teil/je Satz. Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_schnell.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import rechnen, staffeln, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.zukauf_dialog import JE, ZukaufDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


db = Datenbank(tmp / "z.db")
a = db.angebot_neu(dict(kunde="Test"))
# Rahmen: 10 Sätze; Pos. 10 4 Rohre je Rahmen, Pos. 20 6 Rohre je Rahmen
p1 = db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                             stueck=40, schneidweg=300, einstiche=2, satz="Rahmen", je_satz=4))
p2 = db.position_neu(a, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                             stueck=60, schneidweg=200, einstiche=2, satz="Rahmen", je_satz=6))
k, tab = db.kontext(), db.tabellen()


def rechnung():
    kopf, pos = db.angebot(a), db.positionen(a)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    return kopf, pos, einst, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


# ------------------------------------------------------------------ Rechenkern
assert zukauf.lieferant_vorgabe("Blechteile") == "Technik"
assert zukauf.lieferant_vorgabe("", "Blech Lasche 80x40") == "Technik"
assert zukauf.lieferant_vorgabe("Normteile", "Schraube") == ""
pos = dict(stueck=40, je_satz=4)
assert zukauf.bezugsmenge(dict(), pos) == 40
assert zukauf.bezugsmenge(dict(je=zukauf.JE_SATZ), pos) == 10
assert zukauf.bezugsmenge(dict(je=zukauf.JE_SATZ), pos, 200) == 50, "Mengenstufe: 50 Sätze"
assert zukauf.bezugsmenge(dict(je=zukauf.JE_SATZ), dict(stueck=7)) == 7, "ohne Satzangabe: jedes Teil ein Satz"
assert zukauf.zukauf_text(dict(zukauf=json.dumps([dict(menge=20, je="Satz", stand=dict(bezeichnung="Blech",
                                                                                        einheit="Stück"))]))) \
    == "20 St/Satz Blech"
ok("Lieferant-Vorgabe Technik für Blech, Bezugsmenge je Satz, Kurztext")

# ------------------------------------------------------------------ Schnellanlage im Angebot
f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
seite = f.angebot_oeffnen(a)
app.processEvents()
assert [x.text() for x in seite.zukauf_knopf.menu().actions()] == ["Zukaufteile bearbeiten …", "Neuer Zukaufartikel …",
                                                                     "EK eintragen …"]


def bedienen(d):
    assert d.je.currentData() == zukauf.JE_SATZ, "Position im Satz: Vorgabe je Satz"
    assert d.kategorie.currentText() == "Blechteile" and d.lieferant.currentText() == "Technik"
    assert d.fertig() is False and "Bezeichnung" in d.info.text(), "Pflichtfelder"
    d.bezeichnung.setText("Blech Lasche 80x40x5")
    d.ek.setText("2,50")
    d.aufschlag.setText("20")
    d.menge.setText("2,5")
    assert d.fertig() is False and "ganze Zahl" in d.info.text(), "eigene Position: ganze Stück"
    d.menge.setText("20")
    assert d.weiter() and d.bezeichnung.text() == "" and d.lieferant.currentText() == "Technik"
    d.bezeichnung.setText("Blech Knotenblech")
    d.ek.setText("abc")
    assert d.fertig() is False and "keine Zahl" in d.info.text()
    d.ek.setText("0")
    assert d.fertig() is False and "größer als 0" in d.info.text(), "0 € ist nie ein Einkaufspreis"
    d.ek.setText("4")
    d.aufschlag.clear()                      # Regel der Kategorie (keine Werte vorbelegt)
    d.menge.setText("2")
    assert d.fertig()
    return d.result()


assert seite.zukauf_schnell([0], dialog=bedienen) == 2
lasche = next(x for x in db.zukauf_artikel_liste() if x["bezeichnung"] == "Blech Lasche 80x40x5")
assert lasche["herkunft"] == "Schnellanlage" and lasche["kategorie"] == "Blechteile" \
    and lasche["bezuege"][0]["lieferant"] == "Technik"
assert lasche["aufschlag_quelle"] == zukauf.INDIVIDUELL and lasche["aufschlag_wert"] == 20
assert "Technik" in {z["name"] for z in db.zeilen("zukauf_lieferanten")}
assert db.zukauf_historie(lasche["id"])[0]["bemerkung"] == "Schnellanlage im Angebot"
ps = db.positionen(a)
assert len(ps) == 4 and zukauf.eintraege(ps[0]) == [], "die markierte Rohrposition bleibt unverändert"
l, kn = ps[2], ps[3]
assert (l["pos"], l["art"], l["bezeichnung"], l["satz"], l["je_satz"], l["stueck"]) \
    == (30, ZUKAUFTEIL, "Blech Lasche 80x40x5", "Rahmen", 20, 200), l
assert (kn["pos"], kn["je_satz"], kn["stueck"]) == (40, 2, 20)
assert [(e["artikel_id"], e["menge"]) for e in zukauf.eintraege(l)] == [(lasche["id"], 1)]

kopf, pos, einst, (z, s) = rechnung()
# 10 Rahmen × 20 Laschen à 2,50 € + 20 % = 500 € Einstand, 100 € Aufschlag; Knotenblech 10 × 2 × 4 € ohne Aufschlag
nah(s["zukauf_einstand"], 500 + 80, "Einstand")
nah(s["zukauf_aufschlag"], 100, "Aufschlag")
gr = {g["stand"]["bezeichnung"]: g for g in s["zukauf"]}
nah(gr["Blech Lasche 80x40x5"]["bestellung"]["verbrauch"], 200, "Verbrauch 20 je Rahmen")
nah(z[2]["zukauf_teil"] * 200, 600, "VK in der eigenen Position")
ok("Schnellanlage: 2 Bleche nacheinander, Lieferant Technik, je als eigene Zukaufteil-Position im Satz Rahmen")

# Staffel je Satz: 50 Rahmen = 1000 Laschen
st = staffeln.stufe_rechnen(kopf, pos, "Rahmen", 50, k, tab, einst)
nah(st["preis"]["zukauf_einstand"], 1000 * 2.5 + 100 * 4, "Stufe 50 Rahmen: Einstand")
nah(st["preis"]["zukauf_aufschlag"], 1000 * 2.5 * 0.2, "Stufe 50 Rahmen: Aufschlag")
ok("Staffelpreise: 50 Rahmen rechnen 1000 Laschen")


def je_teil(d):
    d.je.setCurrentIndex(0)
    d.bezeichnung.setText("Blech Abdeckung")
    d.ek.setText("3")
    d.menge.setText("2")
    return QDialog.Accepted if d.fertig() else QDialog.Rejected


def ohne_bezug(d):
    assert not d.je.isVisibleTo(d), "ohne markierte Position nur Stückzahl"
    d.bezeichnung.setText("Typenschild")
    d.kategorie.setCurrentText("Kaufteile")
    d.lieferant.setCurrentText("Schilder GmbH")
    d.ek.setText("1,20")
    d.menge.setText("5")
    return QDialog.Accepted if d.fertig() else QDialog.Rejected


assert seite.zukauf_schnell([1], dialog=je_teil) == 1
assert seite.zukauf_schnell([], dialog=ohne_bezug) == 1
ps = db.positionen(a)
assert (ps[4]["pos"], ps[4]["stueck"], ps[4]["satz"]) == (50, 120, None), "je Teil: 2 × 60 Rohre, ohne Satz"
assert (ps[5]["pos"], ps[5]["stueck"], ps[5]["art"]) == (60, 5, ZUKAUFTEIL)
ok("je Teil = Menge × Stückzahl der markierten Position; ohne Markierung Stückzahl direkt")
for p in ps[2:]:
    db.positionen_loeschen([p["id"]])

# Menge je Satz direkt an einer Rohrposition (Dialog Zukaufteile)
kn_id = next(x["id"] for x in db.zukauf_artikel_liste() if x["bezeichnung"] == "Blech Knotenblech")
db.position_aendern(p1, "zukauf", json.dumps([dict(artikel_id=lasche["id"], menge=20, je="Satz",
                                                   stand=db.zukauf_stand(lasche["id"])),
                                              dict(artikel_id=kn_id, menge=2, je="Satz", stand=db.zukauf_stand(kn_id))]))
kopf, pos, einst, (z, s) = rechnung()
nah(s["zukauf_einstand"], 500 + 80, "je Satz an der Rohrposition: Einstand")
nah(z[0]["zukauf_teil"] * 40, 680, "VK über die 40 Rohre der Position verteilt")
seite.neu_laden()
ok("Menge je Satz an einer Rohrposition: 10 Rahmen × 20")

# ------------------------------------------------------------------ Dialog Zukaufteile
d = ZukaufDialog(seite, db, db.positionen(a)[0])
assert d.tabelle.cellWidget(0, JE).currentData() == zukauf.JE_SATZ and d.je.currentData() == zukauf.JE_SATZ
vk_satz = d._vorschau(d.eintraege)[0]["vk"]
d.tabelle.cellWidget(0, JE).setCurrentIndex(0)          # je Teil: 20 je Rohr = 4-fach
app.processEvents()
assert "je" not in d.eintraege[0]
nah(d._vorschau(d.eintraege)[0]["vk"], vk_satz * 4, "je Teil = 4 × je Satz")


def schnell(x):
    assert x.je.currentData() == zukauf.JE_SATZ
    x.kategorie.setCurrentText("Normteile")
    assert x.lieferant.currentText() == ""
    x.bezeichnung.setText("Schraube M8")
    x.lieferant.setCurrentText("Würth")
    x.ek.setText("0,10")
    x.menge.setText("8")
    return QDialog.Accepted if x.fertig() else QDialog.Rejected


assert d.schnell(dialog=schnell) == 1 and len(d.eintraege) == 3 and d.eintraege[2].get("je") == "Satz"
assert d.auswahl.findText("Schraube M8") >= 0
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
assert [e.get("je") for e in zukauf.eintraege(db.positionen(a)[0])] == [None, "Satz", "Satz"]
ok("Dialog Zukaufteile: je Teil/je Satz umschalten, 'Neuer Artikel …' hängt den Artikel an")

f.resize(1024, 700)
app.processEvents()
print("OK: Schnellanlage und Menge je Satz")
