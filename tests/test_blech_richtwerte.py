"""Prüft „Bleche mit Richtwerten anzeigen, die dann geändert werden können“ (Patrick 03.11.2026):
- R1 Eigene Werte je Teil (Gewicht, Material, €/kg, Schneidweg, Einstiche, Laserzeit, Stundensatz, Kantungen,
  € je Kantung, Rüsten, Aufschlag) ersetzen den Richtwert; der Richtpreis wird immer daraus berechnet.
- R2 Blech aus der STEP: Gewicht aus dem Volumen, Schneidweg aus dem gemessenen Umfang, solange die Form unverändert
  ist; geänderte Form = wieder aus den Eingaben. Keine gemeinsamen Schnitte.
- R3 Tafelbelegung je Teil (mit Innenkonturen an ihrer Lage) (Lage ohne Überlappung, innerhalb des Rands) und gemeinsam je Werkstoff/Dicke (nur Ansicht).
- R4 Blech-Editor: Tabelle der Richtwerte, eigener Wert gelb, ↺ setzt zurück, gespeichert in den Eingaben;
  Tafelbild zeigt die Belegung.
- R6 STEP-Import: Position bekommt die Messung, Richtwerte aus der STEP; Prüfdialog zeigt Gewicht und Richtpreis
  (neu bei anderem Werkstoff).
- R7 Gewinde in Blechen (Patrick 03.11.2026, wir schneiden selbst): Kernlöcher der STEP werden offene
  Gewinde-Vorschläge, Status warnt, „Bohrungen prüfen“ bestätigt sie; € je Stück aus Einstellungen › Gewinde kommen
  zum Blech-EK als Fertigung dazu (Gewinn nur darauf), der Blech-EK bleibt.
- R5 Angebot: Spalte „EK Blech“ zeigt den Richtpreis; Angebotspreis per Klick eintragen gilt statt des Richtpreises,
  bleibt beim erneuten Übernehmen aus dem Editor, leeren = wieder Richtpreis; Übersicht Bleche ändert Preis und
  Lieferant.

Aufruf: python tests/test_blech_richtwerte.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import blech, blech_preis, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
daten = db.blech_daten()
werkstoffe, laser, einst = daten["werkstoffe"], daten["laser"], daten["einst"]

# ------------------------------------------------------------------ R1 eigene Werte
e = dict(werkstoff="S235JR", dicke=3, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=400, breite=300, eckradius=0,
         stueck=25, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=10)])
r0 = blech.rechnen(e, werkstoffe, laser, einst)
assert not r0["fehler"] and set(r0["richtwerte"]) == set(blech.RICHTWERT_NAMEN) and not r0["eigene"]
w = r0["werte"]
assert nah(r0["richtpreis"], round((w["material_kg"] * w["preis_kg"] + w["zeit"] / 3600 * w["stundensatz"]
                                    + w["ruesten"] / 25) * (1 + w["aufschlag"] / 100), 2))
assert r0["schneidweg"] == r0["aussen"] + r0["innen"] and nah(r0["aussen"], 1400)   # volle Außenkontur
for n, v in (("zeit", 60), ("preis_kg", 2), ("ruesten", 100), ("aufschlag", 0), ("material_kg", 5),
             ("stundensatz", 200), ("kantungen", 2), ("kantung", 3), ("gewicht", 9)):
    r = blech.rechnen(dict(e, eigene={n: v}), werkstoffe, laser, einst)
    assert r["eigene"] == {n: v} and r["richtwerte"][n] == r0["richtwerte"][n], n
    assert r["werte"][n] == v and (n in ("gewicht", "kantung") or r["richtpreis"] != r0["richtpreis"]), n
assert blech.rechnen(dict(e, eigene=dict(gewicht=9)), werkstoffe, laser, einst)["gewicht"] == 9
r = blech.rechnen(dict(e, eigene=dict(schneidweg=r0["schneidweg"] * 2)), werkstoffe, laser, einst)
assert r["zeit"] > r0["zeit"] and r["richtwerte"]["zeit"] == r0["richtwerte"]["zeit"]
r = blech.rechnen(dict(e, eigene=dict(einstiche=50)), werkstoffe, laser, einst)
assert r["einstiche"] == 50 and r["zeit"] > r0["zeit"]
r = blech.rechnen(dict(e, eigene=dict(zeit=-1, aufschlag="x", unbekannt=3)), werkstoffe, laser, einst)
assert r["eigene"] == {} and r["richtpreis"] == r0["richtpreis"]                   # ungültig = Richtwert
r = blech.rechnen(dict(e, dicke=37, eigene=dict(zeit=100)), werkstoffe, laser, einst)
assert not r["fehler"] and r["zeit"] == 100                                        # ohne Laserdaten: eigene Zeit
assert blech.rechnen(dict(e, dicke=37), werkstoffe, laser, einst)["fehler"]
ok("R1 Eigene Werte je Teil ersetzen den Richtwert, Richtpreis immer berechnet, volle Außenkontur im Schneidweg")

# ------------------------------------------------------------------ R2 STEP-Messung
b = dict(laenge=400, breite=300, dicke=3, kontur="eben", aussen_punkte=[(0, 0), (400, 0), (400, 300), (0, 300)],
         konturen_lage=[dict(art="Bohrung", durchmesser=10, x=200, y=150)], flaeche_netto=119000.0,
         volumen=357000.0, umfang_aussen=1400.0, umfang_innen=31.4)
es = blech.aus_step(b, "S235JR", 25)
assert es["messung"] == dict(flaeche_netto=119000.0, volumen=357000.0, umfang_aussen=1400.0, umfang_innen=31.4)
r = blech.rechnen(es, werkstoffe, laser, einst)
dichte = werkstoffe["S235JR"]["dichte"]
assert set(r["aus_step"]) == {"gewicht", "schneidweg", "zeit"}
assert nah(r["richtwerte"]["gewicht"], 357000 * dichte / 1e6, 1e-6) and nah(r["schneidweg"], 1431.4)
# wie im Editor geöffnet (step = Eingaben wie gemessen): unverändert gilt die Messung, geändert nicht mehr
gemessen = {k: v for k, v in es.items() if k not in ("stueck", "step", "messung")}
assert blech.step_messung(dict(es, step=gemessen)) is not None
assert blech.step_messung(dict(es, step=gemessen, konturen=es["konturen"] + [
    dict(art=sw.TEXT_GRAVUR, anzahl=1, text="A1", hoehe=5)])) is not None            # Gravur ändert die Form nicht
assert blech.step_messung(dict(es, step=gemessen, dicke=4)) is None
assert blech.rechnen(dict(es, step=gemessen, dicke=4), werkstoffe, laser, einst)["aus_step"] == []
assert blech.step_messung(dict(es, step=None)) is None and blech.step_messung(e) is None
ok("R2 STEP: Gewicht aus Volumen, Schneidweg gemessen, nur solange die Form unverändert ist")

# ------------------------------------------------------------------ R3 Tafelbelegung


def ohne_ueberlappung(t, steg=5, rand=10):
    l, br = t["format"]
    for bild in t["bilder"]:
        ts = bild["teile"]
        for i, (x, y, tl, tb, *_r) in enumerate(ts):
            assert x >= rand - 1e-6 and y >= rand - 1e-6 and x + tl <= l - rand + 1e-6 and y + tb <= br - rand + 1e-6
            for (x2, y2, l2, b2, *_s) in ts[i + 1:]:
                assert x + tl + steg <= x2 + 1e-6 or x2 + l2 + steg <= x + 1e-6 or y + tb + steg <= y2 + 1e-6 \
                    or y2 + b2 + steg <= y + 1e-6


formate = blech.tafelformate(einst["blech_tafeln"])
for n in (1, 5, 24, 25, 64, 100):
    t = blech.tafel_belegung(400, 300, n, formate)
    tb = blech.tafelbedarf(400, 300, n, formate)
    assert t["format"] == tb["format"] and sum(b["anzahl"] * len(b["teile"]) for b in t["bilder"]) == n, n
    ohne_ueberlappung(t)
assert blech.tafel_belegung(4000, 3000, 1, formate) is None
g = blech.tafel_gemischt([(400, 300, 25, "1"), (1200, 200, 10, "2"), (100, 50, 40, "3"), (3500, 100, 1, "4")],
                         formate)
assert g["fehlt"] == ["4"] and sum(len(b["teile"]) for b in g["bilder"]) == 75 and 0 < g["ausnutzung"] <= 1
ohne_ueberlappung(g)
assert blech.tafel_gemischt([], formate) is None
fb = blech.form_bild(dict(konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=40),
                                     dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=150, y=40),
                                     dict(art=sw.BOHRUNG, anzahl=2, d=8),                     # ohne Lage: nicht
                                     dict(art=sw.TEXT_GRAVUR, anzahl=1, text="A", hoehe=5, x=1, y=1)]),
                     dict(laenge=200, breite=100, punkte=[(10, 20), (210, 20), (210, 120), (10, 120)]))
assert fb["punkte"][0] == (0, 0) and len(fb["innen"]) == 2 and (fb["laenge"], fb["breite"]) == (200, 100)
assert all(nah(sum(x for x, _ in z[:-1]) / (len(z) - 1), c, 0.5) for z, c in zip(fb["innen"], (40, 140)))
ok("R3 Tafelbelegung je Teil und gemeinsam je Werkstoff/Dicke ohne Überlappung, im Rand, alle Teile")

# ------------------------------------------------------------------ R4 Blech-Editor
app = QApplication.instance() or QApplication([])
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
d = BlechDialog(None, db, dict(e))
t = d.richtwerte
assert t.rowCount() == len(blech.RICHTWERTE) and d.ergebnis["richtpreis"] == r0["richtpreis"]
zeit = [n for n, *_ in blech.RICHTWERTE].index("zeit")
t.item(zeit, 2).setText("60")
assert d.eingaben()["eigene"] == dict(zeit=60) and d.ergebnis["zeit"] == 60
assert d.ergebnis["richtpreis"] == blech.rechnen(dict(e, eigene=dict(zeit=60)), werkstoffe, laser, einst)["richtpreis"]
assert t.item(zeit, 2).background().color().name().upper() == "#FFF2CC" and t.cellWidget(zeit, 3).isEnabled()
t.cellWidget(zeit, 3).click()                     # ↺
assert "eigene" not in d.eingaben() and d.ergebnis["richtpreis"] == r0["richtpreis"]
d.eingaben_setzen(dict(e, eigene=dict(aufschlag=0)))
assert t.eigene() == dict(aufschlag=0) and d.ergebnis["werte"]["aufschlag"] == 0
assert d.tafel_belegung and d.tafel_belegung["format"] == r0["tafel"]["format"]
d.tafel_bild.grab()
d.tafel_bild.gross(False).grab()
d2 = BlechDialog(None, db, dict(es))                 # aus der STEP: Messung bleibt in den Eingaben
assert d2.eingaben()["messung"] == es["messung"] and set(d2.ergebnis["aus_step"]) == {"gewicht", "schneidweg", "zeit"}
assert d2.richtwerte.item(0, 1).font().bold()
ok("R4 Blech-Editor: Richtwerte-Tabelle, eigener Wert gelb, ↺ zurück, gespeichert; Tafelbild; STEP-Werte fett")

# ------------------------------------------------------------------ R5 Angebot
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)


def anlegen(dlg):
    dlg.eingaben_setzen(dict(e, stueck=25))
    return QDialog.Accepted


assert s.blech_neu(dialog=anlegen)
s.neu_laden()
r = len(s.positionen) - 1
m = s.pos_modell
c = next(i for i in range(m.columnCount()) if m.name(i) == "ek_blech")
assert m.headerData(c, Qt.Horizontal) == "EK Blech [€/St]" and not s.pos_ansicht.isColumnHidden(c)
st = blech_preis.stand(s.positionen[r], s.blech_daten)
assert st["ek"] == r0["richtpreis"] and not st["angebot"] and st["richtpreis"] == r0["richtpreis"]
assert m.flags(m.index(r, c)) & Qt.ItemIsEditable and m.data(m.index(r, c)) == blech_preis.text(st)
# Angebotspreis per Klick eintragen
assert m.setData(m.index(r, c), "4,80")
app.processEvents()
p = s.positionen[r]
st = blech_preis.stand(p, s.blech_daten)
assert st["angebot"] and st["ek"] == 4.8 and st["richtpreis"] == r0["richtpreis"]
assert blech.lesen(p["technik"])["angebotspreis"]["preis"] == 4.8
assert m.data(m.index(r, c), Qt.ItemDataRole.FontRole).bold() and "Angebotspreis" in m.data(
    m.index(r, c), Qt.ItemDataRole.ToolTipRole)
s.optimieren()
assert nah(s.zukauf.zeilen[0]["ek"], 4.8)                                   # Angebot rechnet mit dem Angebotspreis
# Editor erneut übernehmen: Angebotspreis bleibt, Richtpreis neu gemerkt


def hoeher(dlg):
    dlg.richtwerte.item(zeit, 2).setText("90")
    return QDialog.Accepted


assert s.blech_bearbeiten(r, dialog=hoeher)
st = blech_preis.stand(s.positionen[r], s.blech_daten)
assert st["angebot"] and st["ek"] == 4.8 and st["richtpreis"] > r0["richtpreis"]
assert blech.lesen(s.positionen[r]["technik"])["eigene"] == dict(zeit=90)
# leeren = wieder Richtpreis
assert m.setData(m.index(r, c), "")
app.processEvents()
st = blech_preis.stand(s.positionen[r], s.blech_daten)
assert not st["angebot"] and st["ek"] == st["richtpreis"] and "angebotspreis" not in blech.lesen(
    s.positionen[r]["technik"])
# Übersicht Bleche: Preis und Lieferant ändern
gesehen = {}


def uebersicht(dlg):
    from rohrlaser.blech_uebersicht import LIEFERANT, PREIS
    gesehen["zeilen"] = dlg.tabelle.rowCount()
    gesehen["reiter"] = dlg.reiter.count()
    dlg.tabelle.item(0, PREIS).setText("3,90")
    dlg.tabelle.item(0, LIEFERANT).setText("Blech Müller")
    dlg.grab()
    return QDialog.Accepted


assert s.bleche_uebersicht(dialog=uebersicht) == 1 and gesehen == dict(zeilen=1, reiter=2)
st = blech_preis.stand(s.positionen[r], s.blech_daten)
assert st["angebot"] and st["ek"] == 3.9 and st["lieferant"] == "Blech Müller"
assert blech.lesen(s.positionen[r]["technik"])["angebotspreis"]["vorher"] == "Technik"
assert s.blech_preis_setzen(r, None)                    # zurück: Lieferant und Richtpreis wie vorher
st = blech_preis.stand(s.positionen[r], s.blech_daten)
assert not st["angebot"] and st["lieferant"] == "Technik"
assert json.loads(s.positionen[r]["zukauf"])[0]["stand"]["bezug"]["lieferant"] == "Technik"
ok("R5 Angebot: EK Blech zeigt Richtpreis, Angebotspreis per Klick gilt und bleibt, leeren = Richtpreis, Übersicht")

# ------------------------------------------------------------------ R6 STEP-Import und Prüfdialog
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
s2 = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Test")))
gemessen = s2.step_messen([str(HIER / "step_bleche" / "B02_Blech_400x200x4_Bohrungen.step")])
mw = [dict(m) for m in gemessen]
bd = dict(werkstoffe=werkstoffe, laserdaten=laser, einst=einst)
dlg = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste(), werkstoffe, blech_daten=bd)
zb = next(z for z in dlg.zeilen if z.blech)
assert "Richtpreis" in zb.it.text(dlg.SP_HINWEIS)      # Werkstoff wie die Rohre bzw. S235 vorbelegt (#383): schon da
zb.ws.setCurrentText("S235JR")
text = zb.it.text(dlg.SP_HINWEIS)
assert " kg, Richtpreis " in text and "€/St" in text, text
dlg.close()
s2.step_messen = lambda *a, **k: (gemessen, None)
for m_ in gemessen:
    m_["_werkstoff"] = "S235JR"
s2.step_importieren(["B02"], stueck=3)
p = db.positionen(s2.id)[0]
e2 = blech.lesen(p["technik"])
assert e2["messung"]["umfang_aussen"] > 0 and e2["messung"]["volumen"] > 0
r2 = blech.rechnen(e2, werkstoffe, laser, einst)
assert set(r2["aus_step"]) == {"gewicht", "schneidweg", "zeit"}
assert nah(r2["gewicht"], e2["messung"]["volumen"] * werkstoffe["S235JR"]["dichte"] / 1e6, 1e-6)
ok("R6 STEP-Import: Messung an der Position, Richtwerte aus der STEP, Prüfdialog mit Gewicht und Richtpreis")

# ------------------------------------------------------------------ R7 Gewinde in Blechen
from rohrlaser import bohrbild, rechnen  # noqa: E402
s3 = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Test")))
gem3 = s3.step_messen([str(HIER / "step_bleche" / "B18_Blech_200x120x6_4xM8_2xM12.step")])
s3.step_messen = lambda *a, **k: (gem3, None)
for m_ in gem3:
    m_["_werkstoff"] = "S235JR"
s3.step_importieren(["B18"], stueck=100)
p = db.positionen(s3.id)[0]
assert p["gewinde_vorschlag"] == "4xM8; 2xM12" and not p.get("gewinde"), p
assert bohrbild.offen(bohrbild.lesen(p["bohrbild"])) == 2 and s3.bohrungen_offen() == [0]
k3 = db.kontext()


def zeile3():
    kopf, pos = db.angebot(s3.id), db.positionen(s3.id)
    einst3 = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k3), k3, db.tabellen(), einst3)[0][0], pos[0]


z0, p = zeile3()
w3 = rechnen.position_werte(p, s3.kopf, s3.k, s3.tabellen)
assert "Gewinde-Vorschlag ungeprüft" in rechnen.status(p, w3, s3.kopf, s3.k, None, [p])
assert z0["gewinde_teil"] == 0
assert s3.bohrungen_pruefen([0], werte=([dict(x, status=bohrbild.BESTAETIGT) for x in bohrbild.lesen(p["bohrbild"])],
                                        ""))
z1, p = zeile3()
preise = {g["gewinde"]: g["preis"] for g in db.zeilen("gewinde")}
gp = 4 * preise["M8"] + 2 * preise["M12"]
assert p["gewinde"] == "4xM8; 2xM12" and nah(z1["gewinde_teil"], gp, 1e-9)
assert nah(z1["zukauf_teil"], z0["zukauf_teil"], 1e-9)                 # Blech-EK bleibt, Gewinde kommen dazu
assert nah(z1["selbst_teil"] - z0["selbst_teil"], z1["herstell_teil"] - z0["herstell_teil"], 1e-9)
assert z1["preis_teil"] > z0["preis_teil"] + gp * 0.99
w3 = rechnen.position_werte(p, s3.kopf, s3.k, s3.tabellen)
assert "Gewinde" not in rechnen.status(p, w3, s3.kopf, s3.k, None, [p])
# Im Blech-Editor gewählte Gewinde (Ausführung „Gewinde schneiden“, Bohrungsart): nicht im Richtpreis, sondern
# bestätigt ins Bohrbild der Position (€ je Stück zum Blech-EK)
s4 = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Test")))
e4 = dict(werkstoff="S235JR", dicke=5, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=200, breite=100, eckradius=0,
          stueck=50, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=6.8, aus=bohrbild.GEWINDE_SCHNEIDEN, groesse="M8")])
r4 = blech.rechnen(e4, werkstoffe, laser, einst)
r4o = blech.rechnen(dict(e4, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=6.8)]), werkstoffe, laser, einst)
assert r4["bohrungen"]["gewinde"] == {"M8": 4} and r4["richtpreis"] == r4o["richtpreis"]     # nicht im Richtpreis
s4.blech_neu(dialog=lambda d: (d.eingaben_setzen(dict(e4)), QDialog.Accepted)[1])
p4 = db.positionen(s4.id)[0]
assert p4["gewinde"] == "4xM8" and bohrbild.offen(bohrbild.lesen(p4["bohrbild"])) == 0, p4.get("gewinde")
assert nah(rechnen.blech_gewinde_preis(p4, db.zeilen("gewinde")), 4 * preise["M8"], 1e-9)
ok("R7 Gewinde in Blechen: Vorschlag aus der STEP, Bohrungen prüfen, Gewinde aus dem Editor, € je Stück zusätzlich "
   "zum Blech-EK")
print("Alle Prüfungen bestanden.")
