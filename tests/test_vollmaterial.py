"""Vollmaterial (Rund- und Vierkantstahl) als Zukaufartikel (Plan Vollmaterial, Patrick 25.10.2026 „alle a, 4 b“):
- V1 Rechenkern: Gewicht aus Querschnitt × Länge × Dichte, Bezeichnung, EK = Gewicht × €/kg, Dubletten.
- V2 Datenbank: Schema 61 (abmessung, gewicht, preis_kg), Zusatzarbeit Sägen und Kategorie Vollmaterial in neuen und
  älteren Dateien; Speichern rechnet Gewicht und EK (Vorgabe Tonnenpreis des Werkstoffs).
- V3 STEP-Import: Rundstahl wird Zukaufteil-Position mit Zusatzarbeit Sägen, gleiche Teile eine Position, vorhandener
  Artikel wird wiederverwendet, abgewählt bzw. ohne Zukaufliste wie bisher nicht übernommen.
- V4 Kalkulation: Zusatzarbeiten an Zukaufteilen zählen (Zuschlag Fertigung, Gewinn), ohne Zusatzarbeit wie bisher.
- V5 Oberfläche: Schnellanlage im Angebot (Art Rundstahl) und Formular im Reiter Zukaufartikel.
Alle Preise sind Testwerte.

Aufruf: python tests/test_vollmaterial.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen, step, vollmaterial as vm, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


# ------------------------------------------------------------------ V1 Rechenkern
G_RUND = math.pi / 4 * 20 * 20 * 150 * 7.85 / 1e6        # Rundstahl Ø20 × 150, Dichte 7,85
nah(vm.gewicht(vm.RUNDSTAHL, 20, 150, 7.85), G_RUND, "Gewicht Rundstahl", 1e-4)
nah(vm.gewicht(vm.VIERKANTSTAHL, 20, 150, 7.85), 20 * 20 * 150 * 7.85 / 1e6, "Gewicht Vierkantstahl", 1e-4)
assert vm.gewicht(vm.RUNDSTAHL, 20, 150, None) is None and vm.gewicht(vm.RUNDSTAHL, 0, 150, 7.85) is None
assert vm.bezeichnung(vm.RUNDSTAHL, 20, 150, "S235") == "Rundstahl Ø20 × 150 mm S235"
assert vm.bezeichnung(vm.VIERKANTSTAHL, 12.5, 80) == "Vierkantstahl 12,5 × 12,5 × 80 mm"
nah(vm.ek(0.5, 1.2), 0.6, "EK = Gewicht × €/kg")
assert vm.ek(None, 1.2) is None and vm.kg_preis(dict(tonnenpreis=1450)) == 1.45
liste = [dict(id=1, artikeltyp="Rundstahl", abmessung=20, laenge=150.3, werkstoff="S235"),
         dict(id=2, artikeltyp="Rundstahl", abmessung=20, laenge=200, werkstoff="S235"),
         dict(id=3, artikeltyp="Vierkantstahl", abmessung=20, laenge=150, werkstoff="S235"),
         dict(id=4, artikeltyp="Rundstahl", abmessung=20, laenge=150, werkstoff="S235", status="archiviert")]
gleich, aehnlich = vm.dubletten("Rundstahl", 20.02, 150, "S235", liste)
assert [a["id"] for a in gleich] == [1] and [a["id"] for a in aehnlich] == [2], (gleich, aehnlich)
w, b = vm.vorbereiten(dict(artikeltyp="Rundstahl", abmessung=20, laenge=150, werkstoff="S"), [],
                      {"S": dict(dichte=7.85, tonnenpreis=1000)})
assert w["bezeichnung"] == "Rundstahl Ø20 × 150 mm S" and w["preis_kg"] == 1.0
assert b and b[0]["preise"] == [dict(ab=1, preis=round(round(G_RUND, 4) * 1.0, 4))], b
w, _ = vm.vorbereiten(dict(artikeltyp="Rundstahl", abmessung=20, laenge=150, werkstoff=None, gewicht=0.37,
                           preis_kg=1.0), [], {})
assert w["gewicht"] is None, "ohne Werkstoff kein altes Gewicht"
ok("V1 Gewicht, Bezeichnung, EK aus €/kg, Dubletten (Länge ± 0,5, Abmessung ± 0,05, archiviert zählt nicht)")

# ------------------------------------------------------------------ V2 Datenbank
db = Datenbank(tmp / "v.db")
assert SCHEMA_VERSION >= 61
spalten = {r[1] for r in db.con.execute("PRAGMA table_info(zukauf_artikel)")}
assert set(vm.FELDER) <= spalten, set(vm.FELDER) - spalten
assert vm.ZUSATZ_SAEGEN in {z["name"] for z in db.zeilen("zusatzarbeiten")}
assert vm.KATEGORIE in db.zukauf_kategorien()
assert "Rundstahl" in zukauf.ZUKAUF_TYPEN and "Vierkantstahl" in zukauf.ZUKAUF_TYPEN
alt = Datenbank(tmp / "alt.db")              # ältere Datei: Sägen und Kategorie fehlen noch
alt.con.execute("DELETE FROM zusatzarbeiten WHERE name=?", (vm.ZUSATZ_SAEGEN,))
alt.con.execute("DELETE FROM zukauf_kategorien WHERE name=?", (vm.KATEGORIE,))
alt.con.execute("DELETE FROM einstellungen WHERE name='voll_stand'")
alt.con.commit()
alt.con.close()
alt = Datenbank(tmp / "alt.db")
assert vm.ZUSATZ_SAEGEN in {z["name"] for z in alt.zeilen("zusatzarbeiten")} and vm.KATEGORIE in alt.zukauf_kategorien()
alt.con.close()
werte, bez = vm.artikel(vm.RUNDSTAHL, 20, 150, "S235-10219", herkunft="Test", lieferant="Stahlhandel")
aid = db.zukauf_speichern(None, werte, bez)
a = db.zukauf_artikel(aid)
nah(a["gewicht"], G_RUND, "Gewicht gespeichert", 1e-4)
assert a["preis_kg"] == 1.0 and a["kategorie"] == vm.KATEGORIE and a["einheit"] == "Stück", a
assert zukauf.json_liste(a["bezuege"][0]["preise"]) == [dict(ab=1, preis=round(round(G_RUND, 4), 4))], a["bezuege"]
werte = dict(a, preis_kg=1.5)                  # eigener Preis je kg: EK neu
db.zukauf_speichern(aid, werte, a["bezuege"])
a = db.zukauf_artikel(aid)
nah(zukauf.json_liste(a["bezuege"][0]["preise"])[0]["preis"], round(G_RUND, 4) * 1.5, "EK mit 1,50 €/kg", 1e-4)
ok("V2 Schema 61, Sägen + Kategorie (auch ältere Datei), Speichern rechnet Gewicht und EK (Tonnenpreis, eigener €/kg)")

# ------------------------------------------------------------------ V3 STEP-Import
k = db.kontext()


def messung(artikel, form="Rundstahl", abm=20, laenge=150, datei="bolzen.step"):
    return dict(datei=datei, artikel=artikel, profilform=form, abm_a=str(abm), abm_b="0", laenge=str(laenge),
                wandstaerke="0", schneidweg="0", konturen="0", pruefstatus="plausibel", hinweise="")


mw = [messung("BOLZEN"), messung("STIFT", "Vierkantstahl", 12, 80)]
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 4, zukauf_liste=db.zukauf_artikel_liste(),
                       zusatz_katalog=db.zeilen("zusatzarbeiten"))
p1, p2 = erg["positionen"]
assert p1["art"] == ZUKAUFTEIL and p1["werkstoff_id"] == "S235-10219" and p1["laenge"] == 150 and p1["stueck"] == 4
assert p1["_zukauf"] == dict(artikel_id=aid), "vorhandener gleicher Artikel"
nah(p1["gewicht_teil"], G_RUND, "Gewicht je Teil", 1e-4)
z = json.loads(p1["zusatz"])
assert z[0]["name"] == vm.ZUSATZ_SAEGEN and z[0]["menge"] == 1 and z[0]["stand"]["preis"] == vm.SAEGEN_PREIS, z
assert "neu" in p2["_zukauf"] and len(erg["zukauf_neu"]) == 1, erg["zukauf_neu"]
w2 = erg["zukauf_neu"][p2["_zukauf"]["neu"]][0]
assert w2["artikeltyp"] == "Vierkantstahl" and w2["abmessung"] == 12 and w2["bezeichnung"] == \
    "Vierkantstahl 12 × 12 × 80 mm S235-10219", w2
# Satz: zwei gleiche Bolzen einer Baugruppe -> eine Position mit 2 Stück je Satz
mw = [messung("B1", datei="gruppe.step"), messung("B2", datei="gruppe.step")]
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 3, saetze=["gruppe.step"],
                       zukauf_liste=db.zukauf_artikel_liste(), zusatz_katalog=db.zeilen("zusatzarbeiten"))
assert len(erg["positionen"]) == 1 and erg["positionen"][0]["je_satz"] == 2 and erg["positionen"][0]["stueck"] == 6
# abgewählt bzw. ohne Zukaufliste: nicht übernommen (wie bisher)
mw = [dict(messung("BOLZEN"), _uebernehmen=False)]
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, zukauf_liste=[])
assert not erg["positionen"] and "abgewählt" in erg["bericht"][0], erg["bericht"]
erg = step.uebernehmen([messung("BOLZEN")], [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
assert not erg["positionen"] and "noch nicht kalkuliert" in erg["bericht"][0], erg["bericht"]
assert step.teile_gruppen([messung("A"), messung("B"), messung("C", laenge=151)]) == {0: [0, 1], 2: [2]}
ok("V3 STEP-Import: Zukaufteil mit Sägen, vorhandener Artikel, neuer Vierkant, Satz, abgewählt, ohne Zukaufliste")

# ------------------------------------------------------------------ V4 Kalkulation
an = db.angebot_neu(dict(kunde="Test"))
stand = db.zukauf_stand(aid)
pid = db.position_neu(an, dict(pos=10, art=ZUKAUFTEIL, artikel="BOLZEN", stueck=1000, laenge=150,
                               werkstoff_id="S235-10219", gewicht_teil=round(G_RUND, 4),
                               zukauf=json.dumps([dict(artikel_id=aid, menge=1, stand=stand)])))


def zeile():
    kopf, pos = db.angebot(an), db.positionen(an)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    zeilen, _ = rechnen.kalkulation(kopf, pos, erg, k, db.tabellen(), einst)
    return zeilen[0], einst


z0, einst = zeile()
assert z0["zusatz_teil"] == 0 and z0["herstell_teil"] == 0
db.position_aendern(pid, "zusatz", vm.saegen_zusatz(db.zeilen("zusatzarbeiten")))
z1, _ = zeile()
zf, gew = rechnen._n(einst.get("zuschlag_fertigung")), rechnen._n(einst.get("gewinn"))
nah(z1["zusatz_eigen_teil"], vm.SAEGEN_PREIS, "Sägen je Teil")
nah(z1["selbst_teil"] - z0["selbst_teil"], vm.SAEGEN_PREIS * (1 + zf), "Selbstkosten + Sägen mit Zuschlag")
nah(z1["preis_teil"] - z0["preis_teil"], vm.SAEGEN_PREIS * (1 + zf) * (1 + gew)
    / (1 - rechnen._n(db.angebot(an).get("skonto")) / 100), "Preis + Sägen mit Gewinn", 1e-6)
assert "Sägen" in z1["zusatz_text"] and z1["zukaufteil"] is True
ok("V4 Kalkulation: Sägen an der Zukaufteil-Position mit Zuschlag Fertigung und Gewinn, ohne Zusatzarbeit wie bisher")

# ------------------------------------------------------------------ V5 Oberfläche
f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
seite = f.angebot_oeffnen(an)
app.processEvents()


def bedienen(d):
    assert not d.form.isRowVisible(d.v_abm) and d.form.isRowVisible(d.ek)
    d.art.setCurrentIndex(d.art.findData(vm.RUNDSTAHL))
    assert d.form.isRowVisible(d.v_abm) and not d.form.isRowVisible(d.ek)
    assert d.kategorie.currentText() == vm.KATEGORIE, "Kategorie Vollmaterial vorbelegt"
    d.lieferant.setCurrentText("Stahlhandel")
    d.v_abm.setText("30")
    d.v_laenge.setText("250")
    assert d.fertig() is False and "Werkstoff" in d.info.text()
    d.v_werkstoff.setCurrentText("S235-10219")
    assert "EK" in d.info.text() and "Sägen" in d.info.text(), d.info.text()
    d.menge.setText("5")
    assert d.fertig() is True
    return 1


assert seite.zukauf_schnell(zeilen=[], dialog=bedienen, blech=False) == 1
p = db.positionen(an)[-1]
g30 = math.pi / 4 * 30 * 30 * 250 * 7.85 / 1e6
assert p["art"] == ZUKAUFTEIL and p["werkstoff_id"] == "S235-10219" and p["laenge"] == 250 and p["stueck"] == 5, p
nah(p["gewicht_teil"], g30, "Gewicht Schnellanlage", 1e-4)
assert json.loads(p["zusatz"])[0]["name"] == vm.ZUSATZ_SAEGEN
a30 = db.zukauf_artikel(json.loads(p["zukauf"])[0]["artikel_id"])
assert a30["bezeichnung"] == "Rundstahl Ø30 × 250 mm S235-10219" and a30["artikeltyp"] == vm.RUNDSTAHL, a30
nah(zukauf.json_liste(a30["bezuege"][0]["preise"])[0]["preis"], round(g30, 4), "EK Schnellanlage", 1e-4)
ok("V5a Schnellanlage im Angebot: Art Rundstahl, Kategorie, Werkstoff Pflicht, Position mit Gewicht und Sägen")

from rohrlaser.zukauf_seite import ZukaufFormular  # noqa: E402

form = ZukaufFormular(db)
if True:
    a = db.zukauf_artikel(aid)
    form.laden(a, aid, "Artikel")
    app.processEvents()
    assert form.fa.isRowVisible(form.zeile_voll) and not form.fa.isRowVisible(form.zeile_masse)
    assert form.v_abm.text() == "20" and form.v_laenge.text() == "150" and "kg" in form.voll_info.text()
    form.v_laenge.setText("300")
    form.aktualisieren()
    assert "EK" in form.voll_info.text(), form.voll_info.text()
    assert form.speichern(), form.fehler.text()
    a = db.zukauf_artikel(aid)
    assert a["laenge"] == 300 and a["abmessung"] == 20, a
    nah(a["gewicht"], 2 * G_RUND, "Gewicht nach Längenänderung", 1e-3)
    ok("V5b Formular Zukaufartikel: Felder Vollmaterial sichtbar, Länge ändern rechnet Gewicht und EK neu")
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

mw = [messung("BOLZEN", laenge=300), messung("STIFT", "Vierkantstahl", 12, 80)]     # Artikel aid ist jetzt 300 lang
d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 2, zukauf_liste=db.zukauf_artikel_liste())
assert [x for _, x in d.gruppen] == [d.VOLLGRUPPE] and len(d.zeilen) == 2
z = d.zeilen[0]
assert z.blech and z.it.checkState(0) == Qt.Checked and z.ws.currentText() == "S235-10219"
assert z.pr.itemData(1) == aid and "vorhanden" in z.it.text(d.SP_HINWEIS), z.it.text(d.SP_HINWEIS)
z.pr.setCurrentIndex(1)
d.werte_schreiben()
assert mw[0]["_blech_artikel"] == aid and mw[0]["_werkstoff"] == "S235-10219" and "_profil" not in mw[0]
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 2, zukauf_liste=db.zukauf_artikel_liste(),
                       zusatz_katalog=db.zeilen("zusatzarbeiten"))
assert erg["positionen"][0]["_zukauf"] == dict(artikel_id=aid) and "im Prüfdialog gewählt" in erg["bericht"][0]
ok("V5c Prüfdialog: Gruppe Vollmaterial, Werkstoff vorbelegt, vorhandener Artikel wählbar und übernommen")
print("Alle Vollmaterial-Tests bestanden.")
