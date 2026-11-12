"""Prüft Zeitvorgabe von Hand, Rüst-/Stückzeit, Bereiche und Komplexitätsfaktor der Schweißbaugruppe (Konzept
„Schweißbaugruppen-Kalkulation flexibel“ 12.11.2026, Paket 1 und 3):
- Z1 Automatische Zeiten nach Bereichen: Stückzeit, Rüstzeit, Gesamtzeit = Rüsten + Stück × Menge (1, 20, 100 Stk.)
- Z2 Stückzeit von Hand: Kosten anteilig, Fremdleistung, Kosten je Einheit, Einmalbetrag und Draht bleiben
- Z3 Rüstzeit von Hand unabhängig von der Stückzeit, einmal je Auftrag
- Z4 Zurück auf automatisch = bitgleich; ohne Vorgabe kein Unterschied zur Rechnung ohne bg_vorgabe
- Z5 Zeit je Bereich von Hand, mehrere Schweiß-Arbeitsgänge, nichts doppelt
- Z6 Schnellkalkulation: Baugruppe ohne Nahtgruppen mit Gesamtzeit und Stundensatz, Status ohne Hinweis
- Z7 Komplexitätsfaktor nur auf automatische Stückzeit, Vorgabe geht vor
- Z8 Zeit lesen: Minuten, Stunden, h:mm, Fehler
- Z9 Angebot: Kalkulation, Speichern/Öffnen, Kopie, Nachkalkulation-Soll, Kennwerte ohne Vorgabe, CSV und PDF-Satz
- Z10 Editor: Feld Kalkulation: Zeit ändert sofort, zeigt automatisch/von Hand/Abweichung, ↺ setzt zurück
- Z11 Kostenübersicht (Paket 2) am Rahmen R1: Material, Fertigung Teile, Zukauf, Bereiche, Einmal, Fremd; jeder Euro
  einmal: Summe = Verkaufspreis der Baugruppe + Anteil ihrer Einzelteile; Zeit von Hand ändert die Übersicht
- Z12 Preis je BG von Hand (Paket 3): Verkaufspreis je BG = Vorgabe, Unterschied in der BG-Zeile, nur bei derselben
  Anzahl, Warnung unter Selbstkosten, ↺ = berechnet
- Z13 Schnellkalkulation: Material und Zukauf pauschal je BG ohne Einzelteile, Material mit Gewinn, Zukauf ohne
- Z14 Gewinn/Zuschlag Fremdleistung des Angebots im Fenster ändern, mit OK im Angebot gespeichert
- Z15 Ablauf-Vorlage (Paket 4): Vorlage merkt Zeitvorgabe und Komplexität (ohne Preis von Hand und Datum), „Ablauf
  einsetzen“ ersetzt nur Arbeitsgänge und Zeiten, Struktur und Nahtgruppen bleiben
- Z16 Erfahrung: letzte Ist-Zeit derselben bzw. einer ähnlichen Baugruppe aus der Nachkalkulation im Fenster
- Z17 Lernvorschlag: ab 5 Baugruppen Faktor Ist ÷ automatisch und von Hand ÷ automatisch, nur Vorschlag
- Z18 Oberfläche (Paket 5): Kopfzeile mit Status und Gesamtpreis; Satz in 3D mit Kalkulation je Satz (Summe =
  Verkaufspreis der Teile je Satz)

Aufruf: python tests/test_bg_zeitvorgabe.py
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, bg_vorgabe as bv, export, nachkalkulation, rechnen  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=6, status="geprüft",
                                   dichte=7.85, draht_eur_kg=2.0)],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=2.0, status="geprüft")])
SAETZE = {"Schweißen": 60.0, "Schleifen": 48.0}


def gruppe(**extra):
    g = baugruppe.leer()
    # Naht: 1 m × 2 min/m ÷ 50 % = 4 min + 5 Heftpunkte × 6 s = 0,5 min Heften
    g["naehte"] = [dict(id="n1", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1,
                        heftpunkte=5)]
    g["arbeitsgaenge"] = [dict(id="a1", name="Schleifen", satz_id="Schleifen", zeit_min=5, kosten_einheit=2.0),
                          dict(id="a2", name="Rüsten Schweißplatz", satz=60, ruest_min=30, einmal_eur=100),
                          dict(id="a3", name="Verzinken", fremd=True, kosten_einheit=10.0),
                          dict(id="a4", name="Teile bereitstellen", satz=60, zeit_min=2, ruest_min=15)]
    g.update(extra)
    return g


def pos(g, stueck=12):
    return dict(stueck=stueck, art=BAUGRUPPE, baugruppe=baugruppe.speichern(g))


# ------------------------------------------------------------------ Z1
r = baugruppe.rechnen(pos(gruppe()), TAB, SAETZE)
z = r["zeiten"]
ber = {x["bereich"]: x for x in z["bereiche"]}
nah(ber["Schweißen"]["auto_stueck"], 4.0, "Schweißen")
nah(ber["Heften"]["auto_stueck"], 0.5, "Heften")
nah(ber["Nachbearbeitung"]["auto_stueck"], 5.0, "Schleifen = Nachbearbeitung")
nah(ber["Vorbereitung"]["auto_stueck"], 2.0, "Bereitstellen = Vorbereitung")
nah(ber["Vorbereitung"]["auto_ruest"], 45.0, "Rüsten 30 + 15")
assert "Fremdleistung" not in ber and not z["hand"]
nah(z["stueck_min"], 11.5, "Stückzeit")
nah(z["ruest_min"], 45.0, "Rüstzeit")
for n in (1, 20, 100):
    rn = baugruppe.rechnen(pos(gruppe()), TAB, SAETZE, n)
    nah(rn["zeiten"]["gesamt_min"], 45 + 11.5 * n, f"Gesamt {n} Stk.")
    # zeit_min (je BG inkl. Rüstanteil) und Rüst/Stück passen zusammen: nichts doppelt
    nah(rn["zeit_min"], 11.5 + 45 / n, f"zeit_min {n}")
ok("Z1 Bereiche, Stückzeit 11,5 min, Rüstzeit 45 min, Gesamt = Rüsten + Stück × Menge bei 1/20/100 Stk.")

# ------------------------------------------------------------------ Z2
g = gruppe()
bv.vorgabe_setzen(g, auto=z, stueck_min=23.0)
r2 = baugruppe.rechnen(pos(g), TAB, SAETZE)
# Lohn Stück automatisch: Naht 4,5 min × 60 + Schleifen 5 min × 48 + Bereitstellen 2 min × 60 = 4,5 + 4 + 2 = 10,5 €
nah(r2["eigen"] - r["eigen"], 10.5, "Faktor 2 auf Lohn")
nah(r2["fremd"], r["fremd"], "Fremdleistung bleibt")
nah(r2["verbrauch"], r["verbrauch"], "Draht bleibt")
nah(r2["einmal"], r["einmal"], "Einmal bleibt")
nah(r2["zeiten"]["stueck_min"], 23.0, "Stück von Hand")
nah(r2["zeit_min"] - r["zeit_min"], 11.5, "zeit_min + 11,5")
nah(r2["zeiten"]["auto_stueck_min"], 11.5, "automatisch bleibt sichtbar")
assert r2["zeiten"]["hand"] and r2["zeiten"]["hand_stueck"]
nah(sum(w for _, w in baugruppe.kostenaufteilung(r2)), r2["eigen"] + r2["fremd"], "Kostenaufteilung = Summe")
nah(g["vorgabe"]["auto_damals"]["stueck_min"], 11.5, "automatische Zeit beim Setzen gemerkt")
z_a1 = next(x for x in r2["zeilen"] if x["id"] == "a1")
nah(z_a1["zeit_min"], 10.0, "Zeile Schleifen × 2")
nah(z_a1["auto"]["zeit_min"], 5.0, "Zeile automatisch gemerkt")
ok("Z2 Stückzeit von Hand 23 min: Lohn × 2 (+10,50 €), Fremd/Draht/Einmal bleiben, Aufteilung stimmt")

# ------------------------------------------------------------------ Z3
g = gruppe()
bv.vorgabe_setzen(g, ruest_min=90.0)
r3 = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r3["einmal_gesamt"] - r["einmal_gesamt"], 45.0, "Rüsten 45 → 90 min × 60 €/h")
nah(r3["einmal"] - r["einmal"], 45.0 / 12, "je BG umgelegt")
nah(r3["zeiten"]["stueck_min"], 11.5, "Stück bleibt automatisch")
nah(r3["zeiten"]["ruest_min"], 90.0, "Rüst von Hand")
r3b = baugruppe.rechnen(pos(g), TAB, SAETZE, 30)
nah(r3b["einmal_gesamt"], r3["einmal_gesamt"], "Rüsten je Auftrag unabhängig von der Menge")
ok("Z3 Rüstzeit von Hand 90 min: einmal je Auftrag, Stückzeit bleibt")

# ------------------------------------------------------------------ Z4
g = gruppe()
bv.vorgabe_setzen(g, stueck_min=30.0, ruest_min=10.0)
bv.vorgabe_setzen(g, stueck_min=None, ruest_min=None)
assert "vorgabe" not in g
r4 = baugruppe.rechnen(pos(g), TAB, SAETZE)
for k in ("eigen", "fremd", "einmal", "einmal_gesamt", "zeit_min", "schweiss_min"):
    assert r4[k] == r[k], k
assert [(x["zeit_min"], x["kosten"], x["einmal"]) for x in r4["zeilen"]] == \
    [(x["zeit_min"], x["kosten"], x["einmal"]) for x in r["zeilen"]]
ok("Z4 zurück auf automatisch = bitgleich")

# ------------------------------------------------------------------ Z5
g = gruppe()
g["arbeitsgaenge"].append(dict(id="a5", name="Schweißen Anbauteile", satz=60, zeit_min=3))
g["arbeitsgaenge"].append(dict(id="a6", name="Sonderarbeit", satz=60, zeit_min=1, bereich="Nachbearbeitung"))
r5a = baugruppe.rechnen(pos(g), TAB, SAETZE)
b5 = {x["bereich"]: x for x in r5a["zeiten"]["bereiche"]}
nah(b5["Schweißen"]["auto_stueck"], 7.0, "Naht + Schweiß-Arbeitsgang")
nah(b5["Nachbearbeitung"]["auto_stueck"], 6.0, "Bereich von Hand gewählt")
bv.vorgabe_setzen(g, bereiche={"Schweißen": 14.0})
r5 = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r5["eigen"] - r5a["eigen"], 7.0, "Schweißen × 2: 4 € Naht + 3 € Arbeitsgang")
nah(r5["zeiten"]["stueck_min"], r5a["zeiten"]["stueck_min"] + 7, "nur Schweißen mehr")
assert r5["zeiten"]["hand_bereiche"] == ["Schweißen"]
bv.vorgabe_setzen(g, bereiche={"Schweißen": 14.0}, stueck_min=20.0)
r5c = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r5c["zeiten"]["stueck_min"], 20.0, "Stückzeit gesamt geht vor den Bereichen")
ok("Z5 mehrere Schweißarbeitsgänge, Zeit je Bereich von Hand, Stückzeit gesamt geht vor")

# ------------------------------------------------------------------ Z6
g = baugruppe.leer()
assert baugruppe.status(pos(g, 4), dict(bg_tabellen=TAB, saetze=SAETZE)).startswith("HINWEIS: keine Nahtgruppen")
bv.vorgabe_setzen(g, stueck_min=45.0, ruest_min=20.0, satz_id="Schweißen")
r6 = baugruppe.rechnen(pos(g, 4), TAB, SAETZE)
nah(r6["eigen"], 45.0 + 20.0 / 4, "45 min + 20/4 min × 60 €/h")
nah(r6["zeiten"]["gesamt_min"], 20 + 45 * 4, "Gesamt")
assert baugruppe.status(pos(g, 4), dict(bg_tabellen=TAB, saetze=SAETZE)) == "OK"
g["vorgabe"].pop("satz_id")
r6b = baugruppe.rechnen(pos(g, 4), TAB, SAETZE)
assert r6b["zeiten"]["satz_id"] == "Schweißen", "ohne Wahl: Stundensatz Schweißen"
r6c = baugruppe.rechnen(pos(g, 4), TAB, {})
assert any("Stundensatz fehlt" in w for w in r6c["warnungen"])
ok("Z6 Schnellkalkulation ohne Nahtgruppen: 45 min + 20 min Rüsten zum Stundensatz, Status OK, fehlender Satz = Warnung")

# ------------------------------------------------------------------ Z7
g = gruppe()
bv.komplex_setzen(g, 1.5, ["viele Einzelteile"])
r7 = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r7["eigen"] - r["eigen"], 10.5 * 0.5, "× 1,5 auf Lohn Stück")
nah(r7["einmal_gesamt"], r["einmal_gesamt"], "Rüsten ohne Faktor")
nah(r7["zeiten"]["auto_komplex_min"], 11.5 * 1.5, "automatisch × Faktor")
assert not r7["zeiten"]["hand"] and r7["zeiten"]["komplex_gruende"] == ["viele Einzelteile"]
bv.vorgabe_setzen(g, stueck_min=11.5)
r7b = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r7b["eigen"], r["eigen"], "Vorgabe geht vor dem Faktor")
bv.komplex_setzen(g, 1.0, [])
assert "komplex" not in g
r7c = baugruppe.rechnen(pos(g), TAB, SAETZE, ohne_hand=True)
assert r7c["eigen"] == r["eigen"] and not r7c["zeiten"]["hand"]
ok("Z7 Komplexität × 1,5 nur auf automatische Stückzeit; Vorgabe geht vor; ohne_hand = nur Automatik")

# ------------------------------------------------------------------ Z8
for t, soll in (("55", 55), ("55 min", 55), ("12,5", 12.5), ("1,5 h", 90), ("1:20", 80), ("1 h 20", 80),
                ("1 h 20 min", 80), ("2 Std", 120), ("90 s", 1.5), ("1:30 h", 90), ("", None), ("  ", None)):
    w = bv.zeit_lesen(t)
    assert (w is None and soll is None) or abs(w - soll) < 1e-9, (t, w)
for t in ("abc", "-5", "5 kg", "1 h x"):
    try:
        bv.zeit_lesen(t)
    except bv.Fehler:
        continue
    raise AssertionError(t)
assert bv.zeit_text(55) == "55 min" and bv.zeit_text(80) == "1 h 20 min" and bv.abweichung_text(15) == "+15 min"
assert bv.bereich(dict(name="Schweißnähte schleifen")) == "Nachbearbeitung"
assert bv.bereich(dict(name="Heftvorbereitung")) == "Vorbereitung"
assert bv.bereich(dict(name="Vorrichtung")) == "Vorbereitung"
assert bv.bereich(dict(name="Montage")) == "Weitere"
assert bv.bereich(dict(name="Pulvern", fremd=True)) == "Fremdleistung"
ok("Z8 Zeit lesen in min/h/h:mm, Fehler bei Unsinn; Bereich aus dem Namen")

# ------------------------------------------------------------------ Z9 Angebot
from rohrlaser.datenbank import Datenbank  # noqa: E402
tmp = tempfile.mkdtemp()
db = Datenbank(Path(tmp) / "t.db")
for z_ in TAB["schweissverfahren"]:
    db.neu("schweissverfahren", z_)
for z_ in TAB["schweiss_kennwerte"]:
    db.neu("schweiss_kennwerte", z_)
for sid, w in SAETZE.items():
    if not any(x.get("satz_id") == sid for x in db.zeilen("stundensaetze")):
        db.neu("stundensaetze", dict(satz_id=sid, satz=w))


def kalk(aid):
    kopf, ps = db.angebot(aid), db.positionen(aid)
    k, tab = db.kontext(), db.tabellen()
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    zeilen, summen = rechnen.kalkulation(kopf, ps, rechnen.optimieren(kopf, ps, k, tab, einst), k, tab, einst)
    return ps, zeilen


aid = db.angebot_neu(dict(kunde="Zeitvorgabe", maschine="T11"))
g = gruppe()
db.position_neu(aid, dict(pos=10, art=BAUGRUPPE, artikel="ZV", stueck=12, baugruppe=baugruppe.speichern(g)))
ps, zeilen0 = kalk(aid)
preis0 = zeilen0[0]["preis_teil"]
bv.vorgabe_setzen(g, auto=z, stueck_min=23.0, ruest_min=60.0, grund="Erfahrung")
db.position_aendern(ps[0]["id"], "baugruppe", baugruppe.speichern(g))
ps, zeilen1 = kalk(aid)
assert zeilen1[0]["preis_teil"] > preis0
g_neu = baugruppe.lesen(ps[0]["baugruppe"])
assert g_neu["vorgabe"]["stueck_min"] == 23.0 and g_neu["vorgabe"]["grund"] == "Erfahrung", "gespeichert"
assert zeilen1[0]["bg_zeiten"]["hand"]
soll = nachkalkulation.baugruppen_soll(ps, zeilen1)[0]
nah(soll["werte"]["schweiss_h"][0] + soll["werte"]["arbeit_h"][0], (23.0 * 12 + 60.0) / 60, "Soll = wirksame Zeit")
kopie = baugruppe.kopie(ps, g_neu["id"])
kg = baugruppe.lesen(kopie[0][1]["baugruppe"])
assert kg["vorgabe"]["stueck_min"] == 23.0 and kg["id"] != g_neu["id"], "Kopie übernimmt Vorgabe"
csv = export.baugruppen_zeilen(ps, zeilen1)
spalten = dict(zip(export.BAUGRUPPE_SPALTEN, csv[0]))
assert spalten["Zeit_von_Hand"] == "ja" and spalten["Stueckzeit_min_je_BG"] == "23.00", spalten
from rohrlaser import pdf  # noqa: E402
satz = pdf._bg_zeit_satz(zeilen1[0]["bg_zeiten"])
assert "Zeit von Hand" in satz and "Erfahrung" in satz and "Rüstzeit 60" in satz, satz
bv.vorgabe_setzen(g, stueck_min=None, ruest_min=None)
db.position_aendern(ps[0]["id"], "baugruppe", baugruppe.speichern(g))
ps, zeilen2 = kalk(aid)
assert zeilen2[0]["preis_teil"] == preis0, "zurück = alter Preis"
ok("Z9 Angebot: Preis steigt, gespeichert, Soll = wirksame Zeit, Kopie, CSV-Spalten, PDF-Satz, zurück = alter Preis")

# ------------------------------------------------------------------ Z10 Editor
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
eltern = QWidget()
eltern.k = db.kontext()
p = dict(pos(gruppe()), id=1, pos=1)
d = BaugruppeDialog(eltern, p, [p], TAB, SAETZE)
f = d.zeit_feld
vorher = d.erg["eigen"]
assert "automatisch berechnet" in f.status.text()
assert f.auto_l["stueck_min"].text() == "automatisch 11,5 min"
f.felder["stueck_min"].setText("23")
f.felder["stueck_min"].editingFinished.emit()
nah(d.erg["eigen"] - vorher, 10.5, "Editor rechnet sofort")
assert "von Hand" in f.status.text() and f.abw_l["stueck_min"].text() == "+11,5 min" and f.auto_l["stueck_min"].text() == "automatisch 11,5 min"
assert d.daten()["vorgabe"]["stueck_min"] == 23.0
assert "(von Hand)" in d.summe.text()
f.felder["ruest_min"].setText("1 h")
f.felder["ruest_min"].editingFinished.emit()
assert d.daten()["vorgabe"]["ruest_min"] == 60.0
f.felder["stueck_min"].setText("quatsch")
f.felder["stueck_min"].editingFinished.emit()
assert d.daten()["vorgabe"]["stueck_min"] == 23.0, "unlesbar ändert nichts"
assert "keine Zeit" in f.hinweis.text()
f.felder["stueck_min"].setText("23")
f.zurueck["stueck_min"].click()
assert "stueck_min" not in d.daten()["vorgabe"] and d.daten()["vorgabe"]["ruest_min"] == 60.0
f.komplex.setText("1,2")
f.komplex.editingFinished.emit()
assert d.daten()["komplex"]["faktor"] == 1.2
f.alles.click()
assert "vorgabe" not in d.daten() and "komplex" not in d.daten()
nah(d.erg["eigen"], vorher, "alles automatisch")
d.reject()
g2 = gruppe()
bv.vorgabe_setzen(g2, stueck_min=30.0)
p2 = dict(pos(g2), id=2, pos=2)
d2 = BaugruppeDialog(eltern, p2, [p2], TAB, SAETZE, nur_lesen=True)
assert d2.zeit_feld.felder["stueck_min"].isReadOnly() and d2.zeit_feld.felder["stueck_min"].text() == "30 min"
d2.reject()
json.dumps(copy.deepcopy(d.daten()))
ok("Z10 Editor: Eingabe rechnet sofort, Abweichung +11,5 min, Fehler bleibt stehen, ↺ und Alles automatisch")
# ------------------------------------------------------------------ Z11 Kostenübersicht
sys.path.insert(0, str(HIER))
import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import bg_kosten  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
tmp2 = Path(tempfile.mkdtemp())
db2 = Datenbank(tmp2 / "rohrlaser.db")
db2.einstellung_setzen("aufschlag_blech", None)
db2.einstellung_setzen("aufschlag_zukauf", None)
fenster = Hauptfenster(db2, tmp2, stumm=True)
a2 = bsp.anlegen(db2)
s2 = fenster.angebot_oeffnen(a2)
assert s2.optimieren()
zeilen_r1, _ = rechnen.kalkulation(s2.kopf, s2.positionen, s2.ergebnis, s2.k, s2.tabellen, s2.einst)
u = bg_kosten.uebersicht(s2.positionen, zeilen_r1, 0)
n_bg = s2.positionen[0]["stueck"]
soll = zeilen_r1[0]["preis_teil"] + sum(zeilen_r1[j]["preis_teil"] * s2.positionen[j]["stueck"] / n_bg
                                        for j in baugruppe.teile(s2.positionen, baugruppe.lesen(
                                            s2.positionen[0]["baugruppe"])["id"]))
nah(u["verkauf"], soll, "Verkaufspreis je BG = BG + Anteil Teile", 1e-6)
nah(u["kosten"] + u["zuschlaege"] + u["gewinn"] + u["fracht"] + u["skonto"] + u["rest"], u["verkauf"], "jeder Euro einmal")
titel = {x["titel"]: x for x in u["posten"]}
for t in ("Material", "Fertigung Einzelteile", "Zukaufteile", "Einmalkosten (umgelegt)", "Fremdleistungen",
          "Schweißen (inkl. Heften)", "Nachbearbeitung"):
    assert t in titel, (t, list(titel))
nah(titel["Fremdleistungen"]["eur"], bsp.FREMD, "Fremd 15 €")
nah(titel["Einmalkosten (umgelegt)"]["eur"], 65.0, "Einmal 130 € ÷ 2")
assert any("Nahtgruppe" in k_[0] and "min/m" in k_[2] for k_ in titel["Schweißen (inkl. Heften)"]["kinder"])
assert u["marge"] and u["db"] < u["verkauf"]
d3 = BaugruppeDialog(s2, s2.positionen[0], s2.positionen, s2.tabellen, s2._saetze(), db=None)
u3 = d3.kosten_neu()
nah(u3["verkauf"], u["verkauf"], "Fenster = Angebot", 1e-6)
assert d3.kosten_feld.baum.topLevelItemCount() == len(u3["posten"]) + 1
assert "Verkaufspreis je BG" in d3.kosten_feld.preis.text() and "Gewinnmarge" in d3.kosten_feld.preis.text()
d3.zeit_feld.felder["stueck_min"].setText("2 h")
d3.zeit_feld.felder["stueck_min"].editingFinished.emit()
u4 = d3.kosten_neu()
assert u4["verkauf"] > u3["verkauf"] and abs(u4["arbeit_min"] - (120 + 30 / n_bg)) < 1e-6, u4["arbeit_min"]
d3.reject()
d4 = BaugruppeDialog(eltern, p, [p], TAB, SAETZE)
u5 = d4.kosten_neu()
assert u5["verkauf"] is None and "nach dem Speichern" in d4.kosten_feld.preis.text()
d4.reject()
ok("Z11 Kostenübersicht R1: Posten, Summe = Verkaufspreis BG + Teile, Fenster = Angebot, Zeit von Hand wirkt")
# ------------------------------------------------------------------ Z12 Preis je BG von Hand
d5 = BaugruppeDialog(s2, s2.positionen[0], s2.positionen, s2.tabellen, s2._saetze(), db=None)
u_b = d5.kosten_neu()
ziel = round(u_b["verkauf"] + 50, 2)
kf = d5.kosten_feld
kf.felder["preis"][1].setText(zahl_txt := f"{ziel:.2f}".replace(".", ","))
kf.felder["preis"][1].editingFinished.emit()
assert d5.daten()["preis_hand"] == dict(preis=ziel, menge=n_bg), d5.daten().get("preis_hand")
u_h = d5.kosten_neu()
nah(u_h["verkauf"], ziel, "Verkaufspreis je BG = Vorgabe", 1e-6)
nah(u_h["kosten"] + u_h["zuschlaege"] + u_h["gewinn"] + u_h["fracht"] + u_h["skonto"] + u_h["rest"], ziel,
    "jeder Euro einmal mit Preis von Hand", 1e-6)
assert u_h["gewinn"] > u_b["gewinn"] and "Preis von Hand" in kf.hand_info.text()
assert kf.felder["preis"][1].text() == zahl_txt and kf.felder["preis"][2].isVisibleTo(kf)
# im Angebot: Preis der BG-Zeile + Anteil Teile = Vorgabe, Teile unverändert
ps_h = [dict(q) for q in s2.positionen]
ps_h[0]["baugruppe"] = baugruppe.speichern(d5.daten())
z_h, sum_h = rechnen.kalkulation(s2.kopf, ps_h, s2.ergebnis, s2.k, s2.tabellen, s2.einst)
for j in range(1, len(ps_h)):
    nah(z_h[j]["preis_teil"], zeilen_r1[j]["preis_teil"], f"Teil {j} unverändert")
nah(z_h[0]["preis_teil"] - zeilen_r1[0]["preis_teil"], 50.0, "Unterschied in der BG-Zeile", 0.006)
assert z_h[0]["bg_preis_hand"]["ziel"] == ziel
# andere Anzahl (Staffel): normal gerechnet
ps_s = [dict(q) for q in ps_h]
ps_s[0]["stueck"] = n_bg * 5
z_s, _ = rechnen.kalkulation(s2.kopf, ps_s, None, s2.k, s2.tabellen, s2.einst)
assert not z_s[0].get("bg_preis_hand"), "andere Anzahl rechnet normal"
# unter Selbstkosten: Warnung
kf.felder["preis"][1].setText("1")
kf.felder["preis"][1].editingFinished.emit()
d5.kosten_neu()
assert "unter den Selbstkosten" in kf.hand_info.text()
kf.felder["preis"][2].click()
assert "preis_hand" not in d5.daten()
nah(d5.kosten_neu()["verkauf"], u_b["verkauf"], "↺ = berechnet", 1e-6)
kf.felder["preis"][1].setText("abc")
kf.felder["preis"][1].editingFinished.emit()
assert "keine gültige Zahl" in kf.hand_info.text() and "preis_hand" not in d5.daten()
d5.reject()
ok("Z12 Preis je BG von Hand: Verkaufspreis = Vorgabe, Teile unverändert, Staffel normal, Warnung, ↺")

# ------------------------------------------------------------------ Z13 Schnellkalkulation
g6 = baugruppe.leer()
bv.vorgabe_setzen(g6, stueck_min=60.0, satz_id="Schweißen")
aid6 = db.angebot_neu(dict(kunde="Schnell", maschine="T11"))
db.position_neu(aid6, dict(pos=10, art=BAUGRUPPE, artikel="S", stueck=4, baugruppe=baugruppe.speichern(g6)))
ps6, z6a = kalk(aid6)
bv.schnell_setzen(g6, material_eur=100.0, zukauf_eur=20.0)
db.position_aendern(ps6[0]["id"], "baugruppe", baugruppe.speichern(g6))
ps6, z6b = kalk(aid6)
nah(z6b[0]["material_teil"], 100.0, "Material pauschal")
nah(z6b[0]["zukauf_teil"] - (z6a[0].get("zukauf_teil") or 0), 20.0, "Zukauf pauschal")
diff = z6b[0]["preis_teil"] - z6a[0]["preis_teil"]
assert diff > 120.0 - 1e-6, ("Material mit Gewinn/Zuschlag", diff)
assert baugruppe.lesen(ps6[0]["baugruppe"])["schnell"] == dict(material_eur=100.0, zukauf_eur=20.0)
W6 = dict(saetze=SAETZE, bg_tabellen=TAB)
assert baugruppe.status(ps6[0], W6, ps6).startswith(("OK", "HINWEIS")), baugruppe.status(ps6[0], W6, ps6)
_st = baugruppe.status(dict(s2.positionen[0], baugruppe=baugruppe.speichern(
    bv.schnell_setzen(baugruppe.lesen(s2.positionen[0]["baugruppe"]), material_eur=5.0))), dict(saetze=s2._saetze(), bg_tabellen=s2.tabellen), s2.positionen)
assert "pauschal und Einzelteile" in _st, _st
p6 = dict(ps6[0])
d6 = BaugruppeDialog(eltern, p6, [p6], TAB, SAETZE)
zf = d6.zeit_feld
assert zf.schnell_w.isVisibleTo(zf) and zf.schnell["material_eur"].text() == "100,00"
zf.schnell["zukauf_eur"].setText("35")
zf.schnell["zukauf_eur"].editingFinished.emit()
assert d6.daten()["schnell"] == dict(material_eur=100.0, zukauf_eur=35.0)
zf.schnell["zukauf_eur"].setText("-3")
zf.schnell["zukauf_eur"].editingFinished.emit()
assert d6.daten()["schnell"]["zukauf_eur"] == 35.0, "negativ ändert nichts"
zf.alles.click()
assert "schnell" not in d6.daten() and "vorgabe" not in d6.daten()
d6.reject()
d7 = BaugruppeDialog(eltern, p, [p], TAB, SAETZE)
assert d7.zeit_feld.schnell_w.isVisibleTo(d7.zeit_feld), "ohne Teile sichtbar"
d7.reject()
d8 = BaugruppeDialog(s2, s2.positionen[0], s2.positionen, s2.tabellen, s2._saetze(), db=None)
assert not d8.zeit_feld.schnell_w.isVisibleTo(d8.zeit_feld), "mit Einzelteilen ausgeblendet"
d8.reject()
ok("Z13 Schnellkalkulation: Material mit Gewinn, Zukauf pauschal, gespeichert, nur ohne Einzelteile sichtbar")

# ------------------------------------------------------------------ Z14 Gewinn des Angebots im Fenster
d9 = BaugruppeDialog(s2, s2.positionen[0], s2.positionen, s2.tabellen, s2._saetze(), db=None)
assert d9.kosten_feld.felder["gewinn"][1].isVisibleTo(d9.kosten_feld)
u_9 = d9.kosten_neu()
g_alt = s2.kopf.get("gewinn")
d9.kosten_feld.felder["gewinn"][1].setText("40")
d9.kosten_feld.felder["gewinn"][1].editingFinished.emit()
u_10 = d9.kosten_neu()
assert u_10["gewinn"] > u_9["gewinn"] and d9.kopf_neu == {"gewinn": 40.0}
assert d9.werte()["kopf"] == {"gewinn": 40.0}
d9.reject()
s2._bg_kopf_anwenden({"gewinn": 40.0})
assert db2.angebot(a2)["gewinn"] == 40.0, "im Angebot gespeichert"
s2._bg_kopf_anwenden({"gewinn": g_alt})
assert db2.angebot(a2)["gewinn"] == g_alt
assert not BaugruppeDialog(eltern, p, [p], TAB, SAETZE).kosten_feld.felder["gewinn"][1].isVisibleTo(eltern), \
    "ohne Angebot kein Gewinnfeld"
ok("Z14 Gewinn des Angebots im Fenster: Übersicht rechnet neu, mit OK im Angebot gespeichert")
# ------------------------------------------------------------------ Z15 Ablauf-Vorlage
from rohrlaser import kennwerte  # noqa: E402
g15 = gruppe()
bv.vorgabe_setzen(g15, auto=dict(stueck_min=11.5), stueck_min=40.0, ruest_min=20.0, grund="Rahmen", am="2026-11-12")
bv.komplex_setzen(g15, 1.3, ["viele Einzelteile"])
g15["preis_hand"] = dict(preis=999.0, menge=12)
v15 = baugruppe.vorlage_aus(g15)
assert "preis_hand" not in v15 and "am" not in v15["vorgabe"] and "auto_damals" not in v15["vorgabe"]
assert v15["vorgabe"]["stueck_min"] == 40.0 and v15["komplex"]["faktor"] == 1.3
assert "Zeitvorgabe" in baugruppe.vorlage_inhalt(v15) and "Komplexität × 1,3" in baugruppe.vorlage_inhalt(v15)
ziel15 = baugruppe.leer()
ziel15["naehte"] = [dict(id="z1", nr="9", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=200, anzahl=1)]
ziel15["knoten"] = [dict(id="k1", name="UB")]
baugruppe.vorlage_einsetzen(ziel15, v15, "Ablauf A", nur_ablauf=True)
assert [n["id"] for n in ziel15["naehte"]] == ["z1"] and ziel15["knoten"][0]["id"] == "k1", "Struktur bleibt"
assert [a["id"] for a in ziel15["arbeitsgaenge"]] == ["a1", "a2", "a3", "a4"] and ziel15["vorlage"] == "Ablauf A"
assert ziel15["vorgabe"]["stueck_min"] == 40.0 and ziel15["komplex"]["faktor"] == 1.3
leer15 = baugruppe.vorlage_aus(gruppe())
baugruppe.vorlage_einsetzen(ziel15, leer15)
assert "vorgabe" not in ziel15 and "komplex" not in ziel15, "Vorlage ohne Zeitvorgabe nimmt sie weg"
db.neu("baugruppen_vorlagen", dict(name="Ablauf A", inhalt=baugruppe.vorlage_inhalt(v15), daten=json.dumps(v15)))
p15 = dict(pos(gruppe(arbeitsgaenge=[])), id=15, pos=15)
d15 = BaugruppeDialog(eltern, p15, [p15], TAB, SAETZE, db=db)
vid = next(z["id"] for z in d15.vorlagen() if z["name"] == "Ablauf A")
assert d15.vorlage_einsetzen(vid, nur_ablauf=True)
assert d15.daten()["vorgabe"]["stueck_min"] == 40.0 and len(d15.daten()["arbeitsgaenge"]) == 4
assert len(d15.daten()["naehte"]) == 1 and d15.zeit_feld.felder["stueck_min"].text() == "40 min"
d15.reject()
ok("Z15 Ablauf-Vorlage: Zeitvorgabe und Komplexität gemerkt, ohne Preis von Hand; nur Ablauf ersetzt Arbeitsgänge")

# ------------------------------------------------------------------ Z16 Erfahrung + Z17 Lernvorschlag
from rohrlaser import bg_erfahrung  # noqa: E402
nr16 = []
for i, q in enumerate((1.2, 1.25, 1.3, 1.2, 1.15)):
    g16 = gruppe()
    g16["vorlage"] = "Ablauf A"
    if i == 4:
        bv.vorgabe_setzen(g16, stueck_min=20.0)
    a16 = db.angebot_neu(dict(kunde="Erfahrung", maschine="T11"))
    db.position_neu(a16, dict(pos=10, art=BAUGRUPPE, artikel="Rahmen X" if i < 4 else "Rahmen Y", stueck=10,
                              baugruppe=baugruppe.speichern(g16)))
    auto_h = (11.5 * 10 + 45) / 60
    db.nachkalkulation_speichern(a16, dict(am=f"2026-11-0{i + 1}", baugruppen={g16["id"]: dict(
        schweiss_h=auto_h * q * 0.5, arbeit_h=auto_h * q * 0.5)}))
    nr16.append(db.angebot(a16)["nummer"])
p16 = dict(pos(gruppe()), id=16, pos=16, artikel="Rahmen X")
e16 = bg_erfahrung.letzte(db, p16, baugruppe.lesen(p16["baugruppe"]))
assert e16 and e16["art"] == "dieselbe" and e16["angebot"] == nr16[3], e16
nah(e16["ist_min"], (11.5 * 10 + 45) * 1.2, "Ist min", 1e-6)
nah(e16["faktor"], 1.2, "Ist ÷ automatisch", 1e-6)
nah(e16["ist_je_bg"], (11.5 * 10 + 45) * 1.2 / 10, "Ist je BG", 1e-6)
g17 = gruppe()
g17["vorlage"] = "Ablauf A"
p17 = dict(pos(g17), id=17, pos=17, artikel="ganz anders")
e17 = bg_erfahrung.letzte(db, p17, g17)
assert e17["art"] == "ähnlich" and e17["angebot"] == nr16[4], e17
assert bg_erfahrung.letzte(db, dict(pos(gruppe()), artikel="nie gesehen"), gruppe()) is None
t16 = bg_erfahrung.text(e16)
assert "dieselbe Baugruppe" in t16 and "+20 %" in t16 and "je BG" in t16, t16
d16 = BaugruppeDialog(eltern, p16, [p16], TAB, SAETZE, db=db)
app.processEvents()
assert d16.zeit_feld.erfahrung.isVisibleTo(d16.zeit_feld) and "+20 %" in \
    d16.zeit_feld.erfahrung.text(), d16.zeit_feld.erfahrung.text()
d16.reject()
ok("Z16 Erfahrung: letzte Ist-Zeit derselben Baugruppe, sonst gleiche Vorlage, im Fenster mit Abweichung")
vs = {v["quelle"]: v for v in kennwerte.vorschlaege(db) if v["quelle"] in ("bg_ist", "bg_vorgabe")}
assert vs["bg_ist"]["status"] == "ok" and vs["bg_ist"]["n"] == 5, vs["bg_ist"]
nah(vs["bg_ist"]["faktor"], 1.2, "Median Ist ÷ automatisch", 1e-6)
assert vs["bg_vorgabe"]["n"] >= 1
try:
    kennwerte.freigeben(db, vs["bg_ist"], "Test", "0")
    raise AssertionError("nur Vorschlag")
except ValueError as e_:
    assert "nur Vorschläge" in str(e_)
ok("Z17 Lernvorschlag: 5 Baugruppen Ist ÷ automatisch = 1,2, Zeit von Hand ÷ automatisch, nur Vorschlag")
# ------------------------------------------------------------------ Z18 Kopfzeile, Satz in 3D
d18 = BaugruppeDialog(s2, s2.positionen[0], s2.positionen, s2.tabellen, s2._saetze(), db=None)
u18 = d18.kosten_neu()
kt = d18.kopf_info.text()
assert "Gesamtpreis" in kt and "je BG" in kt and ("OK" in kt or "Hinweis" in kt or "Warnung" in kt), kt
d18.reject()
d19 = BaugruppeDialog(eltern, p, [p], TAB, SAETZE)
assert "Gesamtpreis" not in d19.kopf_info.text() and "●" in d19.kopf_info.text()
d19.reject()
from rohrlaser.satz3d import Satz3dDialog  # noqa: E402
ps18 = [dict(q) for q in s2.positionen]
idx = [j for j, q in enumerate(ps18) if not baugruppe.ist_baugruppe(q)][:2]
for j in idx:
    ps18[j].update(satz="S18", je_satz=1, stueck=4, bg_knoten=None)
z18, _ = rechnen.kalkulation(s2.kopf, ps18, s2.ergebnis, s2.k, s2.tabellen, s2.einst)
d20 = Satz3dDialog(s2, "S18", ps18)
assert d20.kosten_feld is not None
u20 = d20.kosten_feld.u_satz
nah(u20["verkauf"], sum(z18[j]["preis_teil"] for j in idx), "Verkaufspreis je Satz = Teile", 1e-6)
nah(u20["verkauf_auftrag"], u20["verkauf"] * 4, "4 Sätze")
assert "Kosten je Satz" in d20.kosten_feld.titel.text() and "Verkaufspreis je Satz" in d20.kosten_feld.preis.text()
assert not d20.kosten_feld.felder["preis"][1].isVisibleTo(d20.kosten_feld)
assert {x["titel"] for x in u20["posten"]} <= {"Material", "Fertigung Einzelteile", "Zukaufteile"}
assert all("Stk. je Satz" in k_[2] for x in u20["posten"] for k_ in x["kinder"]), u20["posten"]
d20.reject()
ok("Z18 Kopfzeile mit Status und Gesamtpreis; Satz in 3D: Kalkulation je Satz = Verkaufspreis der Teile")
print("Alle Zeitvorgabe-Tests bestanden.")
