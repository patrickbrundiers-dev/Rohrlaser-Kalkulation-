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
assert f.auto_l["stueck_min"].text() == "11,5 min"
f.felder["stueck_min"].setText("23")
f.felder["stueck_min"].editingFinished.emit()
nah(d.erg["eigen"] - vorher, 10.5, "Editor rechnet sofort")
assert "von Hand" in f.status.text() and f.abw_l["stueck_min"].text() == "+11,5 min"
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
print("Alle Zeitvorgabe-Tests bestanden.")
