"""Prüft die Fracht im Angebot und in den Staffelpreisen (fracht_angebot.py, Test 11 und Regression).

- Regression: Frachtart manuell + Verteilung je Stück (alle älteren Angebote) rechnet wie bisher
- Verteilung nach Gewicht, fehlendes Gewicht (je Stück mit Hinweis), Frachtart keine Fracht / im Artikelpreis
- Neue Angebote verteilen nach Gewicht, Kopien behalten ihren Wert, Prüfsumme älterer Staffeln unverändert
- Dialog 'Fracht berechnen …': Übernahme mit Tarif-Snapshot und Historie
- Test 11: Staffel 10/50/100/500 Stück mit eigenem Gewicht, eigenen Ladungsträgern und eigener Fracht je Stufe
- Test 13 (Angebot): Tarifänderung nach der Übernahme ändert die Fracht des Angebots nicht
- Angebots-PDF: Hinweis zur Fracht

Aufruf: python tests/test_fracht_angebot.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import ausgabe, fracht_angebot, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=EPS):
    return abs(a - b) < eps


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)


def rechnung(aid):
    a = db.angebot(aid)
    pos = db.positionen(aid)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(a, pos, k)
    einst = rechnen.einstellungen_angebot(a, db.einstellungen())
    return a, pos, rechnen.kalkulation(a, pos, erg, k, tab, einst)


# --- Regression: manuell + je Stück wie bisher (Betrag gleichmäßig je Teil)
aid = beispiel_angebot.anlegen(db)
assert db.angebot(aid)["fracht_umlage"] == fracht_angebot.NACH_GEWICHT      # neue Angebote: nach Gewicht
db.angebot_aendern(aid, "fracht_umlage", None)                             # wie ein älteres Angebot
db.angebot_aendern(aid, "fracht", 220.0)
a, pos, (zeilen, summen) = rechnung(aid)
teile = sum(p["stueck"] for p in pos)
for z in zeilen:
    assert nah(z["fracht_teil"], 220.0 / teile)
assert summen["fracht"] == 220.0 and summen["fracht_umlage"] == fracht_angebot.JE_STUECK
preis_alt = summen["verkauf"]
ok("Regression: manuell + je Stück = Fracht gleichmäßig je Teil (220 € / 152 Teile), wie bisher")

# --- nach Gewicht: Anteil des Teilegewichts, Summe = Fracht
db.angebot_aendern(aid, "fracht_umlage", fracht_angebot.NACH_GEWICHT)
a, pos, (zeilen, summen) = rechnung(aid)
werte = [rechnen.position_werte(p, a, db.kontext(), db.tabellen()) for p in pos]
gesamt = sum(w["gewicht"] * p["stueck"] for w, p in zip(werte, pos))
for z, w in zip(zeilen, werte):
    assert nah(z["fracht_teil"], 220.0 * w["gewicht"] / gesamt)
assert nah(sum(z["fracht_teil"] * z["stueck"] for z in zeilen), 220.0)
schwer = max(range(len(pos)), key=lambda i: werte[i]["gewicht"])
leicht = min(range(len(pos)), key=lambda i: werte[i]["gewicht"])
assert zeilen[schwer]["fracht_teil"] > 220.0 / teile > zeilen[leicht]["fracht_teil"]
assert nah(summen["verkauf"], preis_alt, 0.05)       # Gesamtpreis bleibt (bis auf Skonto-Rundung) gleich
ok("nach Gewicht: Fracht je Teil = 220 € × Teilegewicht / Gesamtgewicht, schwere Teile tragen mehr, Summe 220 €")

# --- Gewicht fehlt: je Stück mit Hinweis
pos_ohne = [dict(p) for p in pos]
pos_ohne[0]["werkstoff_id"] = "UNBEKANNT"
werte_ohne = [rechnen.position_werte(p, a, db.kontext(), db.tabellen()) for p in pos_ohne]
anteile, hinweis, art = fracht_angebot.anteile(pos_ohne, werte_ohne, 220.0, fracht_angebot.NACH_GEWICHT)
assert art == fracht_angebot.JE_STUECK and "Gewicht fehlt bei Pos. 10" in hinweis
assert all(nah(x, 220.0 / teile) for x in anteile)
# Position ohne Stückzahl und ohne Gewicht stört die Verteilung nach Gewicht nicht
pos_leer = [dict(p) for p in pos]
pos_leer[0].update(stueck=None, werkstoff_id="UNBEKANNT")
werte_leer = [rechnen.position_werte(p, a, db.kontext(), db.tabellen()) for p in pos_leer]
anteile, hinweis, art = fracht_angebot.anteile(pos_leer, werte_leer, 220.0, fracht_angebot.NACH_GEWICHT)
assert art == fracht_angebot.NACH_GEWICHT and not hinweis
assert nah(sum(x * (p["stueck"] or 0) for x, p in zip(anteile, pos_leer)), 220.0)
ok("Gewicht fehlt (Pos. 10 ohne Werkstoff): Fracht je Stück verteilt, mit Hinweis")

# --- keine Fracht / im Artikelpreis enthalten: 0 € in der Kalkulation, Hinweis im PDF
for m, text in ((fracht_angebot.KEINE, "ab Werk"), (fracht_angebot.ENTHALTEN, "in den Preisen enthalten")):
    db.angebot_aendern(aid, "fracht_modus", m)
    a, pos, (zeilen, summen) = rechnung(aid)
    assert summen["fracht"] == 0 and all(z["fracht_teil"] == 0 for z in zeilen)
    assert text in fracht_angebot.angebotstext(a)
    ang = ausgabe.angebot(a, pos, zeilen, db.kontext(), rechnen.einstellungen_angebot(a, db.einstellungen()), None)
    assert text in ang["fracht"]
db.angebot_aendern(aid, "fracht_modus", None)
assert fracht_angebot.angebotstext(db.angebot(aid)) == ""        # manuell: Angebot wie bisher
ok("keine Fracht / im Artikelpreis enthalten: 0 € Fracht, Hinweis im Angebot; manuell ohne Hinweis wie bisher")

# --- Kopie eines älteren Angebots behält 'je Stück'; Prüfsumme älterer Staffeln ohne Frachtfelder unverändert
db.angebot_aendern(aid, "fracht_umlage", None)
kopie = db.angebot_kopieren(aid)
assert db.angebot(kopie)["fracht_umlage"] is None
alt = {k: v for k, v in db.angebot(aid).items()}
g = staffeln._gemeinsam(alt, pos, db.kontext(), db.tabellen(), {})
assert set(g[0]) == {"maschine", "stange", "fracht", "skonto", "zeitbasis"}
ok("Kopie eines älteren Angebots bleibt bei je Stück; Prüfsumme der Staffeln älterer Angebote unverändert")

# --- Dialog 'Fracht berechnen …' und Übernahme
aid2 = beispiel_angebot.anlegen(db)
seite = fenster.angebot_oeffnen(aid2)
assert seite.kopf_bereich.fracht_modus.currentText() == fracht_angebot.MANUELL
d = seite.fracht_berechnen()
r = d.rechner
r.plz.setText("25980")
r.versandart.setCurrentText("Stückgut")
e = r.rechnen()
assert e["gesamt"] is not None, e["fehler"]
netto = r.netto.value()
assert nah(netto, fracht_angebot.ware(seite.positionen, [rechnen.position_werte(p, seite.kopf, seite.k, seite.tabellen)
                                                        for p in seite.positionen])[0], 0.05)
assert r.lht_eintraege(), "Packvorschlag aus dem Angebot"
assert d.uebernehmen()
a = db.angebot(aid2)
dd = fracht_angebot.daten(a)
assert a["fracht_modus"] == fracht_angebot.BERECHNET and a["fracht"] == e["gesamt"] and dd["snapshot"]["tarif"]
assert any(h["angebot_id"] == aid2 for h in db.fracht_kalkulationen())
assert seite.kopf_bereich.fracht_modus.currentText() == fracht_angebot.BERECHNET
assert seite.kopf_bereich.felder["fracht"].isReadOnly()
assert "Berechnet" in seite.kopf_bereich.fracht_text.text()
ok(f"Fracht berechnen …: {e['gesamt']:.2f} € mit Tarif-Snapshot übernommen (Frachtart berechnet), in der Historie")

# --- Test 13 (Angebot): Tarifänderung nach der Übernahme ändert die Fracht des Angebots nicht
with db.con:
    db.con.execute("UPDATE fracht_preise SET preis = preis * 3")
a = db.angebot(aid2)
pos2 = db.positionen(aid2)
werte2 = [rechnen.position_werte(p, a, db.kontext(), db.tabellen()) for p in pos2]
betrag, _, fehler = fracht_angebot.stufe(a, pos2, werte2)
assert not fehler and nah(betrag, e["gesamt"], 0.005)
ok("Tarif danach verdreifacht: das Angebot rechnet mit dem gespeicherten Snapshot unverändert")

# --- Test 11: Staffel 10/50/100/500 Stück, eigenes Gewicht, eigene Ladungsträger und eigene Fracht je Stufe
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(a, db.einstellungen())
stufen = [dict(id=i, schluessel="30", menge=m) for i, m in enumerate((10, 50, 100, 500), 1)]
zeilen = staffeln.rechnen_alle(a, pos2, stufen, k, tab, einst)
fr = [z["preis"]["fracht"] for z in zeilen]
# gleiche Gewichtsstufe mit Festpreis (50 und 100 Stück) ergibt dieselbe Fracht, sonst steigt sie
assert all(z["preis"] for z in zeilen) and fr == sorted(fr) and fr[0] < fr[1] and fr[-2] < fr[-1], fr
for z, st in zip(zeilen, stufen):
    assert z["hinweis"] and "kg brutto" in z["hinweis"], z["hinweis"]
gew = [float(z["hinweis"].split(": ", 1)[1].split(" kg")[0].replace(".", "").replace(",", ".")) for z in zeilen]
assert gew == sorted(gew) and len(set(gew)) == 4
# Fracht je Stück sinkt mit der Menge (Fixanteil der Fracht verteilt sich)
je = [f / st["menge"] for f, st in zip(fr, stufen)]
assert je == sorted(je, reverse=True)
# die Stufe mit 500 Stück braucht mehr Ladungsträger als die mit 10 Stück
lht = [z["hinweis"].split("kg brutto, ")[1] for z in zeilen]
assert lht[0] != lht[-1], lht
ok("11 Staffel 10/50/100/500: Fracht " + " / ".join(f"{x:.2f}" for x in fr) + " € je Stufe, Gewicht und "
   "Ladungsträger je Stufe (" + " | ".join(lht) + ")")

# Prüfsumme: geänderte Frachtberechnung meldet die Stufen als neu zu rechnen
kenn = {z["kennung_stufe"] for z in zeilen}
d2 = fracht_angebot.daten(a)
d2["sendung"]["plz"] = "01067"
a3 = dict(a, fracht_sendung=json.dumps(d2))
neu = staffeln.rechnen_alle(a3, pos2, stufen, k, tab, einst, alt=zeilen, ohne_lauf=True)
assert all("VERALTET" in (z["hinweis"] or "") for z in neu) and not kenn & {z.get("kennung_stufe") for z in neu}
gleich = staffeln.rechnen_alle(a, pos2, stufen, k, tab, einst, alt=zeilen, ohne_lauf=True)
assert [z["preis_einheit"] for z in gleich] == [z["preis_einheit"] for z in zeilen]
ok("Prüfsumme je Stufe enthält die Frachteingaben: geänderte Fracht -> Stufen veraltet, unverändert -> übernommen")

# Frachtart manuell: gleicher Betrag in allen Stufen (wie bisher)
am = dict(a, fracht_modus=None, fracht=150.0)
zm = staffeln.rechnen_alle(am, pos2, stufen, k, tab, einst)
assert all(abs(z["preis"]["fracht"] - 150.0) < 1e-6 for z in zm)
# berechnet ohne Frachtberechnung: kein Preis, Hinweis statt still 0 €
ao = dict(a, fracht_sendung=None)
zo = staffeln.rechnen_alle(ao, pos2, stufen[:1], k, tab, einst)
assert zo[0]["preis_einheit"] is None and "Fracht nicht berechnet" in zo[0]["hinweis"]
ok("manuell: gleiche Fracht in allen Stufen; berechnet ohne Frachtberechnung: kein Preis, Hinweis statt 0 €")

# PDF-Hinweis 'berechnet'
assert "frei Haus nach DE 25980" in fracht_angebot.angebotstext(a)
ok("Angebots-PDF: 'Die Preise enthalten die Fracht frei Haus nach DE 25980.'")

# Schweißbaugruppe (Prüfung Preisberechnung 26.10.2026): die Baugruppe hat kein eigenes Gewicht, ihre Einzelteile
# reisen in ihr. Fracht nach Gewicht verteilt sich ohne Hinweis 'Gewicht fehlt', Teile zählen nicht doppelt.
import beispiel_baugruppe  # noqa: E402
db_bg = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
bg_id = beispiel_baugruppe.anlegen(db_bg)
kopf_bg, pos_bg = db_bg.angebot(bg_id), db_bg.positionen(bg_id)
for p in pos_bg:
    if p.get("art") == "Zukaufteil":
        p["gewicht_teil"] = 0.05            # Schrauben mit Gewicht
k_bg, tab_bg = db_bg.kontext(), db_bg.tabellen()
w_bg = [rechnen.position_werte(p, kopf_bg, k_bg, tab_bg) for p in pos_bg]
netto, _, fehlt = fracht_angebot.ware(pos_bg, w_bg)
teile = sum(w["gewicht"] * p["stueck"] for p, w in zip(pos_bg, w_bg) if p.get("art") != "Schweißbaugruppe")
assert not fehlt and nah(netto, teile), (netto, teile, fehlt)
je, hinweis, art = fracht_angebot.anteile(pos_bg, w_bg, 100.0, fracht_angebot.NACH_GEWICHT)
assert art == fracht_angebot.NACH_GEWICHT and not hinweis
assert nah(sum(x * p["stueck"] for x, p in zip(je, pos_bg)), 100.0)
je, _, _ = fracht_angebot.anteile(pos_bg, w_bg, 100.0, fracht_angebot.JE_STUECK)
assert nah(sum(x * p["stueck"] for x, p in zip(je, pos_bg)), 100.0)
db_bg.schliessen()
ok("Schweißbaugruppe: Gewicht aus den Einzelteilen (nicht doppelt), Fracht vollständig verteilt, kein 'Gewicht fehlt'")

fenster.close()
db.schliessen()
print("OK: Fracht im Angebot und in den Staffelpreisen")
