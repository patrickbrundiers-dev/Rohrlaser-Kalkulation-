"""Prüft 'EK eintragen …' im Angebot: Bleche aus dem STEP-Import ohne EK bekommen ihren Einkaufspreis direkt im
Angebot; er wird im Zukaufartikel beim Lieferanten als Staffelzeile 'ab Stückzahl der Position' gespeichert und die
Position rechnet mit dem neuen Preisstand. Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_ek.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import rechnen, zukauf, zukauf_ek  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


db = Datenbank(tmp / "e.db")
B = dict(laenge=500.0, breite=300.0, dicke=5.0, kontur="rechteckig", fingerabdruck="x")
blech = db.zukauf_speichern(None, *zukauf.blech_artikel(B, "S235-10219", "Rahmen.step"))
blech2 = db.zukauf_speichern(None, *zukauf.blech_artikel(dict(B, laenge=400), None))
assert zukauf.ek_fehlt(db.zukauf_artikel(blech))


def eintrag(aid):
    return json.dumps([dict(artikel_id=aid, menge=1, stand=db.zukauf_stand(aid))])


a = db.angebot_neu(dict(kunde="Test"))
db.position_neu(a, dict(pos=10, artikel="R", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2, satz="Rahmen", je_satz=1))
pb = db.position_neu(a, dict(pos=20, art=ZUKAUFTEIL, artikel="B1", bezeichnung="Blech", stueck=40, satz="Rahmen",
                             je_satz=4, zukauf=eintrag(blech)))
pb2 = db.position_neu(a, dict(pos=30, art=ZUKAUFTEIL, artikel="B2", bezeichnung="Blech 2", stueck=10,
                              zukauf=eintrag(blech2)))
k, tab = db.kontext(), db.tabellen()


def zeile(pid):
    kopf, pos = db.angebot(a), db.positionen(a)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    z, _ = rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k), k, tab, einst)
    return z[[p["id"] for p in pos].index(pid)]


assert zeile(pb)["zukauf_fehlt"], "vorher: EK fehlt"

# ------------------------------------------------------------------ Datenbank: Staffelzeile ab Stückzahl
db.zukauf_ek_eintragen(blech2, 3, "Technik", ab=50)
db.zukauf_ek_eintragen(blech2, 4, "Technik", ab=10)
pr = db.zukauf_artikel(blech2)["bezuege"][0]["preise"]
assert [(float(e["ab"]), float(e["preis"])) for e in zukauf.staffel_sortiert(pr)] == [(10, 4), (50, 3)], pr
db.zukauf_ek_eintragen(blech2, 3.5, "Technik", ab=50)
pr = zukauf.staffel_sortiert(db.zukauf_artikel(blech2)["bezuege"][0]["preise"])
assert [float(e["preis"]) for e in pr] == [4, 3.5], "gleiche Stückzahl wird ersetzt"
db.zukauf_ek_eintragen(blech2, 5, "Technik")
assert len(zukauf.json_liste(db.zukauf_artikel(blech2)["bezuege"][0]["preise"])) == 1, "ohne Stückzahl: eine Zeile ab 1 (wie bisher)"
db.zukauf_ek_eintragen(blech2, 0.01, "Technik")       # zurück auf fast nichts, Zeile bleibt gültig
ok("zukauf_ek_eintragen: Staffelzeile ab Stückzahl, gleiche Stückzahl ersetzt, ohne Stückzahl wie bisher")

# ------------------------------------------------------------------ Angebot: Menü und Dialog
f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
seite = f.angebot_oeffnen(a)
app.processEvents()
assert "EK eintragen …" in [x.text() for x in seite.zukauf_knopf.menu().actions()]
liste = zukauf_ek.zeilen([(r, p) for r, p in enumerate(seite.positionen)], nur_fehlend=True)
assert [z["artikel_id"] for z in liste] == [blech, blech2], "ohne Markierung: Zukaufteile, deren Preisstand keinen EK hat"
assert liste[0]["menge"] == 40 and liste[0]["lieferant"] == "Technik", liste


def bedienen(d):
    assert d.tabelle.rowCount() == 2 and d.tabelle.item(0, 4).text() == "fehlt"
    d.accept()
    assert "mindestens" in d.info.text()
    d.setzen(0, "abc")
    d.accept()
    assert "keine Zahl" in d.info.text()
    d.setzen(0, "0")
    d.accept()
    assert "über 0" in d.info.text()
    d.setzen(0, "12,50 €")
    d.accept()
    return d.result()


assert seite.zukauf_ek(dialog=bedienen) == 1
art = db.zukauf_artikel(blech)
pr = zukauf.staffel_sortiert(art["bezuege"][0]["preise"])
assert [(float(e["ab"]), float(e["preis"])) for e in pr] == [(40, 12.5)], pr
assert art["bezuege"][0]["lieferant"] == "Technik" and not zukauf.ek_fehlt(art)
hist = db.zeilen("zukauf_historie")
assert any("EK aus Angebot" in (h.get("bemerkung") or "") and "ab 40 St" in (h.get("bemerkung") or "")
           for h in hist), hist[-1:]
st = zukauf.json_liste(next(p for p in db.positionen(a) if p["id"] == pb)["zukauf"])[0]["stand"]
assert zukauf.ek_je_einheit(st["bezug"], 40)[0] == 12.5, "Position hat den neuen Preisstand"
assert not zeile(pb)["zukauf_fehlt"], "nachher: EK vorhanden"
ok("EK im Angebot eintragen: Artikel ab 40 St = 12,50 €, Historie, Preisstand der Position, EK fehlt weg")

# kleinere Menge in anderem Angebot nimmt die erste Staffelzeile
assert zukauf.ek_je_einheit(st["bezug"], 5)[0] == 12.5

# ------------------------------------------------------------------ Markierte Position: bisheriger EK wird überschrieben
r2 = [p["id"] for p in seite.positionen].index(pb2)
assert seite.zukauf_ek(zeilen=[r2], preise=[2]) == 1
pr = zukauf.staffel_sortiert(db.zukauf_artikel(blech2)["bezuege"][0]["preise"])
assert [(float(e["ab"]), float(e["preis"])) for e in pr] == [(1, 0.01), (10, 2)], pr
assert seite.zukauf_ek(zeilen=[0]) == 0, "Rohrposition ohne Zukaufteile"
ok("markierte Position mit EK: neue Staffelzeile ab 10 St, Rohrposition ohne Zukaufteile meldet")

d = zukauf_ek.EkDialog(None, liste)
assert d.tabelle.columnCount() == len(zukauf_ek.SPALTEN)
d.reject()
assert d.result() == QDialog.Rejected
f.close()
print("Alle Prüfungen bestanden.")
