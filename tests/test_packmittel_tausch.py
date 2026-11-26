"""Test: Packmittelmanagement und Palettentausch (Patrick 26.11.2026, Frachtkostenberechnung 2.0).

Szenarien aus dem Auftrag (Abschnitt 10):
 1. Anbieter tauscht alle Europaletten (0 € Wiederbeschaffung).
 2. Anbieter tauscht keine Europaletten (3 × 22 € = 66 €).
 3. Anbieter tauscht nur einen Teil (nur die nicht getauschten kosten).
 4. Anbieter verlangt einen festen Tauschzuschlag (je Stück, Freimenge, je Lieferung).
 5. Gitterboxen werden nicht zurückgenommen.
 6. Paletten gegen Pfand (Pfand getrennt, keine Wiederbeschaffung dazu).
 7. Verschiedene Packmittel kombiniert (Kauf, Tausch, Rahmen).
 8. Wiederbeschaffungswerte ändern sich (neue Berechnung nimmt den neuen Wert, die gespeicherte den alten).
 9. Mehrere Anbieter im Vergleich (Tausch zählt zum Vergleichswert; Transportbedingungen nie automatisch).
10. Packmittelkosten in der Angebotskalkulation (getrennt ausgewiesen, nie doppelt, Korrektur mit Begründung).
Dazu: ohne Regel kein kostenloser Tausch, speziellere Regel (Kunde, Gültigkeit), ältere Angebote bitgleich.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import beispiel_angebot  # noqa: E402
from rohrlaser import fracht, fracht_angebot, fracht_vergleich, paletten, rechnen  # noqa: E402
from rohrlaser import packmittel_tausch as pt  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


EUR = dict(lht_id="EUR", bezeichnung="Europalette", art="Europalette", laenge=1200, breite=800, hoehe=144,
           abrechnung="Tausch", wiederbeschaffung=22.0, pfand=15.0, tauschzuschlag=1.5)
GB = dict(lht_id="GB", bezeichnung="Gitterbox", art="Gitterbox", laenge=1200, breite=800, hoehe=800,
          abrechnung="Tausch", wiederbeschaffung=110.0)
EW = dict(lht_id="EW", bezeichnung="Einwegpalette", art="Einwegpalette", laenge=1200, breite=800, hoehe=120,
          abrechnung="Kauf", preis=9.0, sicherung=4.0, wiederbeschaffung=12.0)
LHT = [EUR, GB, EW]


def r(regel_id, regel, dl="SPED-A", **w):
    return dict(regel_id=regel_id, dienstleister=dl, regel=regel, aktiv="ja", **w)


def kosten(eintraege, regeln, dl="SPED-A", **kw):
    return paletten.packmittel_kosten(eintraege, LHT, 0.0, tausch=regeln, dienstleister=dl, **kw)


drei = [dict(lht_id="EUR", anzahl=3)]

# 1. alle getauscht
k = kosten(drei, [r("A-EUR", pt.VOLL, lht_id="EUR")])
assert k["gesamt"] == 0 and k["mit_preis"] and k["tausch_stuecke"][0]["getauscht"] == 3, k
ok("1. Vollständiger Tausch: 3 Europaletten getauscht, 0 € Wiederbeschaffung")

# 2. kein Tausch (Regel) und ohne Regel: nie kostenloser Tausch
k = kosten(drei, [r("B-EUR", pt.KEIN, lht_id="Europalette")])
assert k["gesamt"] == 66.0 and k["posten"] == {pt.WIEDERBESCHAFFUNG: 66.0}, k
k0 = kosten(drei, [], dl="SPED-X")
assert k0["gesamt"] == 66.0 and any("keine Tauschregel für SPED-X" in t for t, _ in k0["zeilen"]), k0["zeilen"]
k1 = kosten(drei, [r("A-EUR", pt.VOLL)], dl="SPED-B")          # Regel eines anderen Dienstleisters gilt nicht
assert k1["gesamt"] == 66.0
ok("2. Kein Tausch: 3 × 22 € = 66 € nicht getauschte Packmittel; ohne Regel ebenso (kein kostenloser Tausch "
   "unterstellt), Regeln anderer Dienstleister gelten nicht")

# 3. teilweiser Tausch
k = kosten(drei, [r("C", pt.TEIL, quote=50)])
st = k["tausch_stuecke"][0]
assert (st["getauscht"], st["wieder"]) == (1, 2) and k["gesamt"] == 44.0, st
k = kosten([dict(lht_id="EUR", anzahl=10)], [r("C", pt.TEIL, quote=80, tausch_max=5)])
assert k["tausch_stuecke"][0]["getauscht"] == 5 and k["gesamt"] == 5 * 22.0
ok("3. Teilweiser Tausch: 50 % von 3 = 1 getauscht (abgerundet), 2 × 22 € = 44 €; 80 % höchstens 5 Stück von 10: "
   "5 × 22 €")

# 4. fester Tauschzuschlag
k = kosten(drei, [r("D", pt.ZUSCHLAG, zuschlag_stueck=2.5)])
assert k["posten"] == {pt.TAUSCHZUSCHLAG: 7.5}, k
k = kosten(drei, [r("D", pt.ZUSCHLAG)])                        # ohne Betrag: Tauschzuschlag des Packmittels
assert k["posten"] == {pt.TAUSCHZUSCHLAG: 4.5}, k
k = kosten(drei, [r("D", pt.ZUSCHLAG, zuschlag_stueck=2.5, frei=2, zuschlag_lieferung=10.0)])
assert k["posten"] == {pt.TAUSCHZUSCHLAG: 12.5}, k              # 1 × 2,50 + 10 je Lieferung
k = kosten(drei + [dict(lht_id="GB", anzahl=1)], [r("D", pt.ZUSCHLAG, zuschlag_stueck=2.5, zuschlag_lieferung=10.0)])
assert k["posten"][pt.TAUSCHZUSCHLAG] == 3 * 2.5 + 2.5 + 10.0, k   # je Lieferung nur einmal je Regel
ok("4. Tauschzuschlag: 3 × 2,50 € = 7,50 €; ohne Betrag 3 × 1,50 € (Packmittel); Freimenge 2 + 10 € je Lieferung "
   "= 12,50 €; Zuschlag je Lieferung nur einmal")

# 5. Gitterboxen werden nicht zurückgenommen, Europaletten getauscht
regeln5 = [r("E-EUR", pt.VOLL, lht_id="Europalette"), r("E-GB", pt.KEIN, lht_id="Gitterbox")]
k = kosten(drei + [dict(lht_id="GB", anzahl=2)], regeln5)
assert k["gesamt"] == 220.0 and k["posten"] == {pt.WIEDERBESCHAFFUNG: 220.0}, k
ok("5. Gitterboxen nicht zurückgenommen: 2 × 110 € = 220 €, Europaletten getauscht 0 €")

# 6. Pfand: getrennt ausgewiesen, nie zusätzlich Wiederbeschaffung oder Zuschlag
k = kosten(drei, [r("F", pt.PFAND)])
assert k["posten"] == {pt.PFAND_K: 45.0} and k["tausch_stuecke"][0]["wieder"] == 0, k
k = kosten(drei, [r("F", pt.PFAND, pfand=18.0)])
assert k["posten"] == {pt.PFAND_K: 54.0}
k = kosten(drei, [r("G", pt.RUECK, rueckfuehrung=4.0)])
assert k["posten"] == {pt.RUECKFUEHRUNG: 12.0}, k
k = kosten(drei, [r("G", pt.RUECK)])                            # ohne Rückführungskosten: Wiederbeschaffung
assert k["posten"] == {pt.WIEDERBESCHAFFUNG: 66.0}
ok("6. Pfand 3 × 15 € = 45 € (eigene Kostenart, keine Wiederbeschaffung dazu), Pfand der Regel 18 €; Rücklieferung "
   "3 × 4 € Rückführung, ohne Betrag Wiederbeschaffung")

# Nie doppelt: je Stück genau eine Abrechnung
for regel in (pt.VOLL, pt.TEIL, pt.KEIN, pt.ZUSCHLAG, pt.PFAND, pt.RUECK):
    k = kosten([dict(lht_id="EUR", anzahl=7)], [r("X", regel, quote=40, zuschlag_stueck=1.0, rueckfuehrung=3.0)])
    s = k["tausch_stuecke"][0]
    assert s["getauscht"] + s["pfand"] + s["rueck"] + s["wieder"] == 7, (regel, s)
    assert not (s["pfand"] and s["wieder"]), (regel, s)
ok("Nie doppelt: je Stück genau eine Abrechnung (getauscht, Pfand, Rückführung oder Wiederbeschaffung) für alle "
   "sechs Regeln")

# 7. kombiniert: Kauf (Einweg) + Tausch + Sicherung
k = kosten(drei + [dict(lht_id="EW", anzahl=2), dict(lht_id="GB", anzahl=1)], regeln5)
assert k["posten"] == {pt.PACKMITTEL: 18.0, pt.VERPACKUNG: 8.0, pt.WIEDERBESCHAFFUNG: 110.0}, k["posten"]
assert abs(k["gesamt"] - 136.0) < 1e-9
ok("7. Kombiniert: 2 Einwegpaletten Kauf 18 € (nie Wiederbeschaffung dazu), Sicherung 8 €, Gitterbox 110 €, "
   "Europaletten getauscht = 136 €")

# Spezieller vor allgemein, Kunde, Gültigkeit, Mindestmenge
regeln = [r("ALLG", pt.KEIN, dl=None), r("DL", pt.VOLL), r("KD", pt.ZUSCHLAG, zuschlag_stueck=1.0, kundennr="K1"),
          r("ALT", pt.PFAND, lht_id="EUR", gueltig_bis="2026-01-31")]
assert pt.regel(regeln, EUR, "SPED-A", None, "2026-11-26")["regel_id"] == "DL"
assert pt.regel(regeln, EUR, "SPED-A", "K1", "2026-11-26")["regel_id"] == "KD"
assert pt.regel(regeln, EUR, "SPED-A", None, "2026-01-15")["regel_id"] == "ALT"
assert pt.regel(regeln, EUR, "SPED-Z", None, "2026-11-26")["regel_id"] == "ALLG"
k = kosten([dict(lht_id="EUR", anzahl=2)], [r("M", pt.VOLL, mindest=5)])
assert k["gesamt"] == 44.0 and "erst ab 5" in k["zeilen"][0][0]
ok("Regelwahl: Kunde vor Dienstleister vor Packmittel vor allgemein, befristete Regel nur im Zeitraum; Tausch erst ab "
   "5 Stück: 2 Stück kosten die Wiederbeschaffung")

# Wert fehlt, Bestand
k = paletten.packmittel_kosten(drei, [dict(EUR, wiederbeschaffung=None, tauschwert=None, preis=None, bestand=2)], 0.0,
                               tausch=[], dienstleister="SPED-A")
assert k["gesamt"] == 0 and k["fehlt"] and not k["mit_preis"]
assert any("Wiederbeschaffungswert fehlt" in h for h in k["hinweise"]) and any("nur 2 verfügbar" in h
                                                                              for h in k["hinweise"])
ok("Wiederbeschaffungswert fehlt: Hinweis statt erfundenem Preis; Verfügbarkeit 2 bei 3 benötigten: Hinweis")

# ------------------------------------------------------------------ Datenbank, Angebot, Vergleich
assert SCHEMA_VERSION >= 108
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
db.einstellung_setzen("absender_plz", "33129")
db.fracht_richtwerte_laden("33129")
aid = beispiel_angebot.anlegen(db)
fd = db.fracht_daten()
assert fd["tauschregeln"] == [] and "wiederbeschaffung" in fd["lht"][0]


def setzen(tabelle, schluessel, wert, **felder):
    rid = next(z["id"] for z in db.zeilen(tabelle) if z.get(schluessel) == wert)
    for f, w in felder.items():
        db.aendern(tabelle, rid, f, w)


def rechnung(a_id):
    a = db.angebot(a_id)
    pos = db.positionen(a_id)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(a, pos, k)
    einst = rechnen.einstellungen_angebot(a, db.einstellungen())
    return a, pos, rechnen.kalkulation(a, pos, erg, k, tab, einst)


a0, _, (_, sum_vor) = rechnung(aid)
setzen("fracht_lht", "lht_id", "EUR", abrechnung="Tausch", wiederbeschaffung=22.0, preis=None, sicherung=None)
s_pal = dict(land="DE", plz="80331", absender_plz="33129", netto=300.0, lht=[dict(lht_id="EUR", anzahl=3)])
e = fracht.rechnen(db.fracht_daten(), s_pal)
dl = e["tarif"]["dienstleister"]
assert e["gesamt"] is not None and e["snapshot"]["tausch"] == []

# 10. ins Angebot: neu berechnet (Snapshot mit Tauschregeln) -> Wiederbeschaffung getrennt
d = dict(sendung=s_pal, snapshot=e["snapshot"], gesamt=e["gesamt"], text="", packmittel_aktiv=True)
db.angebot_aendern(aid, "fracht_sendung", json.dumps(d))
db.angebot_aendern(aid, "fracht_modus", fracht_angebot.BERECHNET)
db.angebot_aendern(aid, "fracht", e["gesamt"])
a, pos, (_, s1) = rechnung(aid)
assert s1["verpackung_posten"] == {pt.WIEDERBESCHAFFUNG: 66.0}, s1.get("verpackung_posten")
assert abs(s1["verpackung"] - 66.0) < 0.01 and "Nicht getauschte Packmittel" in s1["verpackung_text"]
# Regel des Dienstleisters: getauscht -> keine Packmittelkosten, Tabelle Verpackung gilt nicht doppelt
db.neu("fracht_tauschregeln", r("T1", pt.VOLL, dl=dl, lht_id="Europalette"))
e2 = fracht.rechnen(db.fracht_daten(), s_pal)
assert [x["regel_id"] for x in e2["snapshot"]["tausch"]] == ["T1"]
db.angebot_aendern(aid, "fracht_sendung", json.dumps(dict(d, snapshot=e2["snapshot"])))
_, _, (_, s2) = rechnung(aid)
assert not s2.get("verpackung_posten") and abs(s2["verpackung"] - sum_vor["verpackung"]) < 0.01, (
    s2.get("verpackung"), sum_vor.get("verpackung"))
ok(f"10. Angebot: 3 Europaletten ohne Tausch = 66 € Packmittelkosten (Kostenart „Nicht getauschte Packmittel“, ohne "
   f"Gewinn); mit Tauschregel von {dl} 0 € und die Tabelle Verpackung gilt wie bisher (nichts doppelt)")

# 8. Wiederbeschaffungswert ändert sich: neue Berechnung neuer Wert, gespeicherte Berechnung alter Wert
setzen("fracht_tauschregeln", "regel_id", "T1", regel=pt.KEIN)
setzen("fracht_lht", "lht_id", "EUR", wiederbeschaffung=25.0)
db.angebot_aendern(aid, "fracht_sendung", json.dumps(d))         # gespeicherter Snapshot mit 22 €
_, _, (_, s3) = rechnung(aid)
assert abs(s3["verpackung"] - 66.0) < 0.01
e3 = fracht.rechnen(db.fracht_daten(), s_pal)
db.angebot_aendern(aid, "fracht_sendung", json.dumps(dict(d, snapshot=e3["snapshot"])))
_, _, (_, s4) = rechnung(aid)
assert abs(s4["verpackung"] - 75.0) < 0.01, s4["verpackung"]
ok("8. Wiederbeschaffungswert 22 → 25 €: gespeicherte Frachtberechnung rechnet weiter 66 €, neu berechnet 75 €")

# Korrektur von Hand mit Begründung (je Sendung, auch je Staffelstufe)
db.angebot_aendern(aid, "fracht_sendung", json.dumps(dict(d, snapshot=e3["snapshot"],
                                                          korrektur=dict(betrag=-10.0, begruendung="Rahmenvertrag"))))
st = fracht_angebot.stufe_details(db.angebot(aid), db.positionen(aid), [
    rechnen.position_werte(p, db.angebot(aid), db.kontext(), db.tabellen()) for p in db.positionen(aid)])
ohne = fracht.nachrechnen(e3["snapshot"], dict(s_pal))["gesamt"]
assert st["betrag"] is not None and "Korrektur" in st["text"] and "Rahmenvertrag" in st["text"], st
assert fracht_angebot.korrektur(dict(korrektur=dict(betrag=0))) is None
ok("Korrektur von Hand: Betrag mit Begründung im Text jeder Staffelstufe, 0 € = keine Korrektur")

# Ältere Angebote (Snapshot ohne Tauschregeln) wie bisher: Tausch 0 € mit Hinweis
alt = paletten.packmittel_kosten(drei, LHT, 0.0)
assert alt["gesamt"] == 0 and "neu" not in alt and any("Tausch" in h for h in alt["hinweise"])
db.angebot_aendern(aid, "fracht_sendung", json.dumps(dict(d, snapshot={k: v for k, v in e["snapshot"].items()
                                                                       if k != "tausch"})))
_, _, (_, s5) = rechnung(aid)
assert not s5.get("verpackung_posten") and abs(s5["verpackung"] - sum_vor["verpackung"]) < 0.01
db.angebot_aendern(aid, "fracht_sendung", None)
db.angebot_aendern(aid, "fracht_modus", a0.get("fracht_modus"))
db.angebot_aendern(aid, "fracht", a0.get("fracht"))
_, _, (_, s6) = rechnung(aid)
assert abs(s6["verkauf"] - sum_vor["verkauf"]) < 1e-9, (s6["verkauf"], sum_vor["verkauf"])
ok("Ältere Angebote (Frachtberechnung ohne Tauschregeln) rechnen wie bisher, Angebot ohne Fracht bitgleich")

# 9. Anbietervergleich: Tausch zählt, Bedingungen
fd = db.fracht_daten()
tarife = [t for t in fd["tarife"] if t.get("dienstleister") and fracht.aktiv(t)]
v0 = fracht_vergleich.vergleich(dict(fd, tauschregeln=[]), {"Palette": s_pal})
ok_zeilen = [z for z in v0["zeilen"] if z["status"] == "ok"]
assert ok_zeilen and not any("packmittel" in z for z in v0["zeilen"])     # ohne Tauschregeln: Vergleich wie bisher
if ok_zeilen:
    erster = ok_zeilen[0]
    dl1 = next(t["dienstleister"] for t in tarife if t["tarif_id"] == erster["tarif_id"])
    regeln9 = [r("V-KEIN", pt.KEIN, dl=None), r("V-VOLL", pt.VOLL, dl=dl1)]
    v = fracht_vergleich.vergleich(dict(fd, tauschregeln=regeln9), {"Palette": s_pal})
    z1 = next(z for z in v["zeilen"] if z["tarif_id"] == erster["tarif_id"])
    assert z1["packmittel"] == 0 and z1["gesamt_logistik"] == z1["gesamt"]
    andere = [z for z in v["zeilen"] if z["status"] == "ok" and z["tarif_id"] != erster["tarif_id"]
              and next(t["dienstleister"] for t in tarife if t["tarif_id"] == z["tarif_id"]) != dl1]
    assert all(z["packmittel"] == 75.0 and z["gesamt_logistik"] == round(z["gesamt"] + 75.0, 2) for z in andere)
    assert v["empfehlung"]["guenstigster"]["gesamt_logistik"] == min(
        fracht_vergleich.wert(z) for z in v["zeilen"] if z["status"] == "ok")
    # Bedingung: Dienstleister ohne passende Länge nie automatisch
    setzen("fracht_dienstleister", "dienstleister_id", dl1, max_laenge=500)
    vb = fracht_vergleich.vergleich(dict(db.fracht_daten(), tauschregeln=regeln9), {"Palette": dict(s_pal,
                                                                                                    max_laenge=2000)})
    zb = next(z for z in vb["zeilen"] if z["tarif_id"] == erster["tarif_id"])
    assert zb["status"] == fracht_vergleich.BEDINGUNG and "2000 mm lang" in zb["text"], zb
    assert all(x["tarif_id"] != erster["tarif_id"] for x in vb["empfehlung"].values() if isinstance(x, dict))
    setzen("fracht_dienstleister", "dienstleister_id", dl1, max_laenge=None)
ok("9. Anbietervergleich: Tausch je Anbieter im Vergleichswert (tauscht = 0 €, andere 3 × 25 €), Empfehlung nach "
   "Fracht + Tausch; Dienstleister mit zu kurzer max. Länge steht mit Grund in der Liste, nie automatisch")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.fracht_seite import FrachtDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
ds = fenster.fracht.dienstleister
ds.neu_laden()
assert ds.tausch.t.name == "fracht_tauschregeln" and ds.tausch.modell.rowCount() == 1
rech = fenster.fracht.rechner
fenster.fracht.zeigen(rech)
rech.plz.setText("80331")
rech.netto.setValue(300.0)
rech.lht_tabelle.setRowCount(0)
rech.lht_neu("EUR", 3)
rech.rechnen()
pm = rech._packmittel_zeigen()
html = rech.packmittel_anzeige.toHtml()
assert pm.get("neu") and "Kostenaufschlüsselung Logistik" in html and "Reine Frachtkosten" in html, html[:300]
seite = fenster.angebot_oeffnen(aid)
seite.kopf["fracht_sendung"] = None
dlg = FrachtDialog(seite)
dlg.rechner.plz.setText("80331")
dlg.rechner.rechnen()
dlg.korrektur.setValue(-5.0)
assert dlg.uebernehmen() is False                      # ohne Begründung nicht
dlg.begruendung.setText("Rahmenvertrag 2026")
assert dlg.uebernehmen() is True
a = db.angebot(aid)
dd = fracht_angebot.daten(a)
assert dd["korrektur"] == dict(betrag=-5.0, begruendung="Rahmenvertrag 2026")
assert abs(a["fracht"] - (dd["gesamt"] - 5.0)) < 1e-6 and "Rahmenvertrag 2026" in dd["text"]
ok("Oberfläche: Tauschregeln unter Dienstleister, Packmittelkosten mit Kostenaufschlüsselung Logistik, Korrektur von "
   "Hand nur mit Begründung (Fracht = berechnet − 5 €, Begründung im Text)")

print("OK: Packmittelmanagement und Palettentausch")
