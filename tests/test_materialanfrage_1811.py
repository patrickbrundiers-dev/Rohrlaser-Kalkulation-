"""Prüft die Materialanfrage-Wünsche vom 18.11.2026 (Patrick):
- S Staffelmengen: sind Staffel-Stufen angelegt, nennt die Anfrage je Material den Bedarf jeder Stufe (Schnittplan
  der Stufe, Stangen und Gewicht); abwählbar.
- L Stangenlänge als Auswahl je Rohrzeile: andere Lieferlänge plant die Positionen der Zeile neu (Stangen, Gewicht,
  Staffelmengen), der Schnittplan des Angebots bleibt; Teil passt nicht = alte Länge mit Hinweis.
- G Menge als Stangen und Gewicht / nur Stangen / nur Gewicht (kg); letzte Wahl gemerkt.
- A Rohrmaterial nie mit Dateien: reine Rohranfrage ohne Zeichnungen und ohne Materialliste-PDF, Zeichnungen von
  Rohrteilen nie vorbelegt.
Outlook wird nie wirklich aufgerufen (ausfuehren ersetzt PowerShell).

Aufruf: python tests/test_materialanfrage_1811.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import materialanfrage as ma, materialanfragen as mv, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Muster Laser GmbH")
db.neu("zukauf_lieferanten", dict(name="Stahlhandel Nord", email="anfrage@stahl-nord.example"))
preis = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("QR 40x40x3", "S235-10219"))
db.aendern("preise", preis["id"], "lieferant", "Stahlhandel Nord")
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=6000, lieferant="Stahlhandel Nord"))
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=8000, lieferant="Stahlhandel Nord"))
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=12000, lieferant="Stahlhandel Nord"))
a = db.angebot_neu(dict(kunde="Test", nummer="A-2026-0400", stange=6000))
db.position_neu(a, dict(pos=10, artikel="T-10", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1450,
                        stueck=8, schneidweg=200, einstiche=2))
db.position_neu(a, dict(pos=20, artikel="T-20", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                        stueck=6, schneidweg=200, einstiche=2))
st = db.staffel_stufe_neu(a, dict(bezeichnung=None))
for schl in ("10", "20"):
    db.staffel_neu(a, dict(schluessel=schl, menge=50, stufe_id=st))
db.staffel_neu(a, dict(schluessel="10", menge=100))          # eigene Stufe nur Pos. 10
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
ordner = fenster.angebot_ordner(s.kopf)
(ordner / "T-10 Zeichnung.pdf").write_bytes(b"%PDF-1.4 Zeichnung")       # Zeichnung des Rohrteils
aufrufe = []


def outlook_ok(befehl):
    daten = json.loads(Path(befehl[-1]).read_text(encoding="utf-8"))
    aufrufe.append(daten)
    return subprocess.CompletedProcess(befehl, 0, "", "")


# ------------------------------------------------------------------ S Staffelmengen
gesehen = {}


def bedienen(d):
    gesehen["zeilen"] = [dict(z) for z in d.zeilen]
    gesehen["text"] = d.text.toPlainText()
    gesehen["sichtbar"] = d.staffel_nennen.isChecked()
    gesehen["anh"] = {d.anhaenge.item(i).text(): d.anhaenge.item(i).checkState() == Qt.Checked
                      for i in range(d.anhaenge.count())}
    gesehen["dateien"], gesehen["pdf"] = d.dateien(), d.mit_pdf()
    gesehen["hinweis"] = d.hinweis.text()
    d.staffel_nennen.setChecked(False)
    gesehen["ohne"] = d.text.toPlainText()
    d.staffel_nennen.setChecked(True)
    d.in_outlook()
    return d.result()


s.anfrage_rueckfrage = lambda titel, text: True
d = s.material_anfragen(dialog=bedienen, ausfuehren=outlook_ok)
qr = gesehen["zeilen"][0]
assert qr["idx"] == [0, 1] and len(qr["staffeln"]) == 2, qr.get("staffeln")
namen = [x["name"] for x in qr["staffeln"]]
assert namen == ["50 Stück", "100 Stück"], namen
# Bedarf der Stufen = eigener Lauf mit den Stückzahlen der Stufe
for name, stueck in (("50 Stück", {0: 50, 1: 50}), ("100 Stück", {0: 100})):
    pos = [dict(s.positionen[i], stueck=n) for i, n in stueck.items()]
    erg = rechnen.optimieren(s.kopf, pos, s.k, s.tabellen, s.einst)
    soll = sum(1 for x in erg["stangen"] if x["profil"] == "QR 40x40x3")
    ist = next(x for x in qr["staffeln"] if x["name"] == name)["teile"][0]["stangen"]
    assert ist == soll, (name, ist, soll)
t = gesehen["text"]
n50 = next(x for x in qr["staffeln"] if x["name"] == "50 Stück")["teile"][0]["stangen"]
n100 = next(x for x in qr["staffeln"] if x["name"] == "100 Stück")["teile"][0]["stangen"]
assert gesehen["sichtbar"] and f"\n  Bitte auch anbieten: {n50} Stangen; {n100} Stangen\n" in t, t
assert "kg" not in t and "6.000" not in t, t                  # Vorgabe: ohne Gewicht, 6 m nicht genannt
# Stückzahlen der Staffel nie in der E-Mail (Patrick 18.11.2026 16:44)
assert "Stück" not in t.split("Bitte auch anbieten:")[1].split("\n")[0] and "50 Stück" not in t and "100 Stück" not in t
assert "Bitte auch anbieten" not in gesehen["ohne"]
assert "Bitte auch anbieten" in aufrufe[-1]["text"] and "50 Stück" not in aufrufe[-1]["text"]
assert ma.staffel_stufen_text(qr) == f"Staffeln: 50 Stück {n50} Stangen, 100 Stück {n100} Stangen"
ok("S Staffeln: je Stufe Materialmenge (Stangen, Gewicht) aus dem Schnittplan der Stufe in der E-Mail, ohne die "
   "Stückzahlen der Staffel; abwählbar")

# ------------------------------------------------------------------ A Rohrmaterial nie mit Dateien
assert gesehen["anh"].get("T-10 Zeichnung.pdf") is False, gesehen["anh"]      # Rohrteil-Zeichnung nicht vorbelegt
assert gesehen["dateien"] == [] and gesehen["pdf"] is False
assert "ohne Anhänge" in gesehen["hinweis"], gesehen["hinweis"]
assert aufrufe[-1]["anhaenge"] == []
assert mv.zeichnungen(ordner, [qr], "A-2026-0400") == [(ordner / "T-10 Zeichnung.pdf", False)]
assert ma.nur_rohr([qr]) and not ma.nur_rohr([qr, dict(art="zukauf")]) and not ma.nur_rohr([])


def von_hand_angehakt(d):
    for i in range(d.anhaenge.count()):           # selbst wenn von Hand angehakt: Rohr geht ohne Dateien
        d.anhaenge.item(i).setCheckState(Qt.Checked)
    gesehen["dateien2"], gesehen["aktiv"] = d.dateien(), d.anhaenge.isEnabled()
    d.in_outlook()
    return d.result()


s.material_anfragen(dialog=von_hand_angehakt, ausfuehren=outlook_ok)
assert gesehen["dateien2"] == [] and not gesehen["aktiv"] and aufrufe[-1]["anhaenge"] == []
ok("A Rohrmaterial nie mit Dateien: keine Zeichnung, kein PDF, Liste gesperrt, auch von Hand angehakt nicht")

# ------------------------------------------------------------------ G Menge als
z0 = dict(qr)
assert "kg" not in ma.zeile_text(z0, s.k) and "mm" not in ma.zeile_text(z0, s.k)       # Vorgabe nur Stangen, 6 m still
assert ma.zeile_text(z0, s.k, als=ma.STANGEN_GEWICHT).endswith(" kg)")
assert "à 12.000 mm" in ma.zeile_text(dict(z0, laenge=12000), s.k)
g = ma.zeile_text(z0, s.k, als=ma.NUR_GEWICHT)
assert g.startswith("ca. ") and " kg Quadratrohr" in g and "mm" not in g and g.endswith(" Stangen)"), g
assert ma.zeile_text(dict(z0, gewicht=None), s.k, als=ma.NUR_GEWICHT).startswith(f"{z0['stangen']} Stange")


def gewicht(d):
    gesehen["vorbelegt"] = d.als()
    d.menge_als.setCurrentText(ma.NUR_GEWICHT)
    gesehen["text_g"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


s.material_anfragen(dialog=gewicht, ausfuehren=outlook_ok)
assert gesehen["vorbelegt"] == ma.NUR_STANGEN
assert "- ca. " in gesehen["text_g"] and "Bitte auch anbieten: ca. " in gesehen["text_g"], gesehen["text_g"]
assert db.einstellung(ma.MENGE_ALS_EINSTELLUNG) == ma.NUR_GEWICHT
assert mv.liste(db, a)[-1]["zeilen"][0].startswith("ca. ")


def wieder(d):
    gesehen["vorbelegt"] = d.als()
    d.menge_als.setCurrentText(ma.STANGEN_GEWICHT)
    gesehen["text_sg"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


s.material_anfragen(dialog=wieder, ausfuehren=outlook_ok)
assert gesehen["vorbelegt"] == ma.NUR_GEWICHT                                  # letzte Wahl gemerkt
assert " kg)" in gesehen["text_sg"]
db.einstellung_setzen(ma.MENGE_ALS_EINSTELLUNG, ma.NUR_STANGEN)
ok("G Menge als Stangen und Gewicht / nur Stangen / nur Gewicht, im Verlauf, letzte Wahl gemerkt")

# ------------------------------------------------------------------ L Stangenlänge als Auswahl
plan_vorher = json.dumps(s.ergebnis["stangen"], sort_keys=True, default=str)
schl = next(v["schluessel"] for v in rechnen.optimieren(s.kopf, s.positionen, s.k, s.tabellen,
                                                         dict(s.einst, laenge_vergleich="ja"))["laengen"])


def soll(stueck, laenge):
    """Vergleich: wie „Übernehmen“ im Vergleich der Lieferlängen (laengenwahl), nur diese Stückzahlen."""
    pos = [dict(s.positionen[i], stueck=n) for i, n in stueck.items()]
    e = rechnen.optimieren(dict(s.kopf, laengenwahl={schl: laenge}), pos, s.k, s.tabellen,
                           dict(s.einst, laenge_vergleich="ja"))
    st = [x for x in e["stangen"] if x["profil"] == "QR 40x40x3"]
    assert st and all(x["stange"] == laenge for x in st)
    return len(st), sum(w["gewicht"] for w in rechnen.stangen_werte(e, s.kopf, pos, s.k, s.tabellen)), st


def laenge(d):
    cb = d.tabelle.cellWidget(0, d.LAENGE)
    gesehen["wahl"] = [cb.itemData(i) for i in range(cb.count())]
    cb.setCurrentIndex(cb.findData(12000))
    gesehen["z12"] = dict(d.zeilen[0])
    gesehen["menge12"] = d.mengen[0].value()
    gesehen["zuschnitt"] = bool(d.tabelle.item(0, d.ZUSCHNITT).flags() & Qt.ItemIsUserCheckable)
    gesehen["text12"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


s.material_anfragen(dialog=laenge, ausfuehren=outlook_ok)
assert gesehen["wahl"] == [6000, 8000, 12000], gesehen["wahl"]
z12 = gesehen["z12"]
n12, kg12, st12 = soll({0: 8, 1: 6}, 12000)
assert z12["laenge"] == 12000 and z12["stangen"] == n12 == gesehen["menge12"], (z12["stangen"], n12)
assert abs(z12["gewicht"] - kg12) < 1e-6
# 12 m länger als die Maschine (6,5 m): Zuschnitt beim Lieferanten wie im Vergleich der Lieferlängen
assert gesehen["zuschnitt"] and "geschnitten auf" in gesehen["text12"] and len(z12["zuschnitte"]) == n12
assert "à 12.000 mm" in gesehen["text12"] and "Bitte auch anbieten: " in gesehen["text12"] and "50 Stück" not in gesehen["text12"]
n50, _, _ = soll({0: 50, 1: 50}, 12000)
assert next(x for x in z12["staffeln"] if x["name"] == "50 Stück")["teile"] == [
    dict(laenge=12000, stangen=n50, gewicht=next(x for x in z12["staffeln"] if x["name"] == "50 Stück")["teile"][0]
         ["gewicht"])]
assert json.dumps(s.ergebnis["stangen"], sort_keys=True, default=str) == plan_vorher   # Angebot unverändert
assert "à 12.000 mm" in mv.liste(db, a)[-1]["zeilen"][0]
# Teil passt nicht auf die Stange: alte Länge bleibt, Hinweis
z = dict(qr)
try:
    ma.neu_planen(z, 1000, s.positionen, s.kopf, s.k, s.tabellen, s.einst)
    raise AssertionError("1.000 mm (nicht lieferbar, Teil zu lang) dürfte nicht gehen")
except ValueError:
    pass
ok("L Stangenlänge je Rohrzeile wählbar: neu geplant (Stangen, Gewicht, Staffelmengen), Angebot unverändert, "
   "zu kurze Stange abgewiesen")
del s.anfrage_rueckfrage
print("OK: Materialanfrage 18.11.2026")
