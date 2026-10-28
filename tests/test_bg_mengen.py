"""Prüft die Mengen der Schweißbaugruppe aus den Einzelteilen (Plan Schweißbaugruppen 28.10.2026, Schritt 1):
- M1 Gewicht, Außenfläche, Länge, Naht und Teile je Baugruppe und je Unterbaugruppe (Handrechnung)
- M2 Arbeitsgang mit Bezug: Preis rechnet mit der Menge aus den Teilen, ändert sich mit der Teilelänge
- M3 anwenden: Menge eintragen, Menge von Hand stellt auf „von Hand“; fehlendes Gewicht = Warnung
- M4 Wenden: Gewicht aus den Stammdaten vor der Summe der Teile
- M5 Aus Zusatzarbeiten: €/kg → Gewicht, €/m² → Oberfläche, €/m → Länge
- M6 Rahmen R1 (ohne Bezug) bitgleich
- M7 Editor: Spalte „Menge aus“, Mengen über der Tabelle, Platzhalter Gewicht

Aufruf: python tests/test_bg_mengen.py
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

from rohrlaser import ausgabe, baugruppe, bg_mengen, rechnen, vorkalk, zukauf  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "m.db")
db.stammdaten_ersetzen({"schweissverfahren": [dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=40, heft_s=6,
                                                   aktiv="ja", status="geprüft")]}, {}, "T")
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-M8", bezeichnung="Schraube M8", einheit="Stück",
                                          aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                          aufschlag_wert=0),
                               [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=0.10)])])
g = baugruppe.leer()
g["id"] = "mengen0001"
g["knoten"] = [dict(id="k1", parent="", name="Querstrebe", menge=2)]
g["naehte"] = [dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, anzahl=4),
               dict(id="n2", knoten="k1", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=50, anzahl=2,
                    beidseitig=True)]
g["arbeitsgaenge"] = [dict(id="a1", knoten="", name="Verzinken", fremd=True, kosten_einheit=1.0, bezug="Gewicht"),
                      dict(id="a2", knoten="", name="Pulvern", fremd=True, kosten_einheit=10.0, bezug="Oberfläche"),
                      dict(id="a3", knoten="k1", name="Prüfen", satz=60, zeit_min=1, bezug="Teile")]
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="R", bezeichnung="Rahmen M", stueck=3,
                        baugruppe=baugruppe.speichern(g)))
p10 = db.position_neu(a, dict(pos=10, artikel="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                              laenge=1000, stueck=1, bg_knoten=g["id"], je_knoten=2))
db.position_neu(a, dict(pos=20, artikel="Strebe", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                        stueck=1, bg_knoten=baugruppe.zuordnung_text(g["id"], "k1"), je_knoten=1))
db.position_neu(a, dict(pos=30, art=ZUKAUFTEIL, artikel="Lasche", bezeichnung="Lasche", stueck=1, gewicht_teil=0.25,
                        bg_knoten=baugruppe.zuordnung_text(g["id"], "k1"), je_knoten=2))
db.position_neu(a, dict(pos=40, art=ZUKAUFTEIL, artikel="Z-M8", bezeichnung="Schraube", stueck=1,
                        zukauf=json.dumps([dict(artikel_id=schraube, menge=1, stand=db.zukauf_stand(schraube))]),
                        bg_knoten=g["id"], je_knoten=4))


def laden():
    kopf = db.angebot(a)
    pos = db.positionen(a)
    for i, feld, wert in baugruppe.abgleich(pos):
        db.position_aendern(pos[i]["id"], feld, wert)
    kopf, pos = db.angebot(a), db.positionen(a)
    return kopf, pos, db.kontext(), db.tabellen(), rechnen.einstellungen_angebot(kopf, db.einstellungen())


# ------------------------------------------------------------------ M1 Mengen
kopf, pos, k, tab, einst = laden()
kgm = rechnen.kg_je_m("QR 40x40x3", "S235-10219", k)
holm = next(p for p in pos if p["pos"] == 10)
strebe = next(p for p in pos if p["pos"] == 20)
m2_holm, m2_strebe = rechnen.oberflaeche(holm, k), rechnen.oberflaeche(strebe, k)
assert kgm and m2_holm and abs(m2_strebe - m2_holm / 2) < 1e-9
m = bg_mengen.mengen(g, pos, k)
# je Baugruppe: 2 Holme 1 m, Querstrebe 2 × (1 Strebe 0,5 m + 2 Laschen 0,25 kg), 4 Schrauben ohne Gewicht
nah(m["gewicht"], 2 * kgm + 2 * 0.5 * kgm + 4 * 0.25, "Gewicht", 1e-3)
nah(m["oberflaeche"], 2 * m2_holm + 2 * m2_strebe, "Oberfläche", 1e-3)
nah(m["laenge"], 2 * 1.0 + 2 * 0.5, "Länge")
nah(m["naht"], 4 * 0.1 + 2 * (2 * 0.05 * 2), "Naht")                  # n2 beidseitig, 2 Querstreben
nah(m["teile"], 2 + 2 * (1 + 2) + 4, "Teile")
assert m["fehlt"] == {"gewicht": ["40"]}, m["fehlt"]                    # Schraube ohne Gewicht, ohne Fläche ok
mk = bg_mengen.mengen(g, pos, k, "k1")                                  # je Querstrebe
nah(mk["gewicht"], 0.5 * kgm + 0.5, "Gewicht Querstrebe", 1e-3)
nah(mk["teile"], 3, "Teile Querstrebe")
nah(mk["naht"], 0.2, "Naht Querstrebe")
assert "unvollständig: Pos. 40" in bg_mengen.text(m) and " kg · " in bg_mengen.text(m)
ok("M1 Gewicht, Oberfläche, Länge, Naht, Teile je Baugruppe und je Unterbaugruppe; Schraube ohne Gewicht gemeldet")

# ------------------------------------------------------------------ M2 Preis mit Bezug
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
i_bg = next(i for i, p in enumerate(pos) if p["pos"] == 100)
z = zeilen[i_bg]
fremd = m["gewicht"] * 1.0 + m["oberflaeche"] * 10.0
nah(z["bg_fremd_teil"], fremd, "Verzinken + Pulvern aus Gewicht und Fläche", 1e-3)
nah(z["bg_eigen_teil"] - next(x["kosten"] for x in z["bg_zeilen"] if x["art"] == "Naht" and x["id"] == "n1")
    - next(x["kosten"] for x in z["bg_zeilen"] if x["art"] == "Naht" and x["id"] == "n2"),
    3 * 2 * 1 / 60 * 60, "Prüfen 3 Teile je Querstrebe × 2 Querstreben × 1 min × 60 €/h")
db.position_aendern(holm["id"], "laenge", 2000)
kopf, pos, k, tab, einst = laden()
zeilen2, _ = rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k, tab, einst), k, tab, einst)
m_neu = bg_mengen.mengen(g, pos, k)
nah(m_neu["gewicht"] - m["gewicht"], 2 * kgm, "Holm doppelt so lang", 1e-3)
nah(zeilen2[i_bg]["bg_fremd_teil"], m_neu["gewicht"] + 10 * m_neu["oberflaeche"], "Preis folgt der Länge", 1e-3)
ok("M2 Verzinken €/kg, Pulvern €/m², Prüfen je Teil rechnen mit den Teilen; Holm länger → Preis höher")

# ------------------------------------------------------------------ M3 anwenden, von Hand, fehlt
bg = baugruppe.lesen(next(p for p in pos if p["pos"] == 100)["baugruppe"])
assert bg_mengen.anwenden(bg, pos, k) == 3
assert bg["arbeitsgaenge"][0]["menge"] == bg["arbeitsgaenge"][0]["menge_auto"] == round(m_neu["gewicht"], 4)
nah(bg["arbeitsgaenge"][2]["menge"], 3, "Prüfen: 3 Teile je Querstrebe")
assert bg_mengen.anwenden(bg, pos, k) == 0                                    # nichts geändert
bg["arbeitsgaenge"][1]["menge"] = 5.0                                         # von Hand
assert bg_mengen.anwenden(bg, pos, k) == 1
assert "bezug" not in bg["arbeitsgaenge"][1] and bg["arbeitsgaenge"][1]["menge"] == 5.0
r = baugruppe.rechnen(dict(stueck=3, baugruppe=baugruppe.speichern(bg)), tab, {}, None,
                      bg_mengen.je_knoten(bg, pos, k))
nah(r["fremd"], m_neu["gewicht"] + 5 * 10.0, "Pulvern mit Menge von Hand", 1e-3)
ohne = [dict(p, gewicht_teil=None) if p["pos"] == 30 else p for p in pos]
ohne = [dict(p, profil_id=None) if p["pos"] in (10, 20) else p for p in ohne]
r = baugruppe.rechnen(dict(stueck=3, baugruppe=baugruppe.speichern(bg)), tab, {}, None,
                      bg_mengen.je_knoten(bg, ohne, k))
assert any("Verzinken: Menge aus Gewicht fehlt" in w for w in r["warnungen"]), r["warnungen"]
nah(r["fremd"], 5 * 10.0, "Verzinken ohne Gewicht: 0, nicht 1 und nicht die alte Menge")
plan = ausgabe.schweissplan([dict(p, baugruppe=baugruppe.speichern(bg)) if p["pos"] == 100 else p for p in pos],
                            tab, k)
nah(plan[0]["arbeitsgaenge"][0]["menge"], round(m_neu["gewicht"], 4), "Schweißplan: Menge aus den aktuellen Teilen")
alt = [dict(p, laenge=1000) if p["pos"] == holm["pos"] else p for p in pos]
alt = [dict(p, baugruppe=baugruppe.speichern(bg)) if p["pos"] == 100 else p for p in alt]
nah(ausgabe.schweissplan(alt, tab, k)[0]["arbeitsgaenge"][0]["menge"], round(bg_mengen.mengen(bg, alt, k)["gewicht"], 4),
    "Schweißplan folgt der Teilelänge")
ok("M3 Menge eingetragen und gemerkt, Menge von Hand stellt auf „von Hand“, fehlendes Gewicht = Warnung und 0, "
   "Schweißplan mit aktuellen Mengen")

# ------------------------------------------------------------------ M4 Wenden nach Gewicht
regeln = vorkalk.Regeln({"schweiss_regeln": vorkalk.richtwerte()})
bg["wenden"] = 2
t, n, text = vorkalk.wenden(bg, regeln, pos, k)
gew = m_neu["gewicht"]
f_soll = 1.0 if gew <= 20 else 1.5 if gew <= 50 else 3.0
nah(t, 1.5 * f_soll, "Wenden aus Gewicht der Teile")
assert "Summe der Einzelteile" in text, text
bg["stamm"]["gewicht"] = "60"
t, n, text = vorkalk.wenden(bg, regeln, pos, k)
nah(t, 1.5 * 3.0, "Wenden: Gewicht der Stammdaten geht vor")
assert "Stammdaten" in text
bg["stamm"].pop("gewicht")
assert vorkalk.wenden(bg, regeln)[0] is None                                  # ohne Teile: Gewicht fehlt
assert vorkalk.gewicht(bg) is None and vorkalk.gewicht(dict(bg, stamm=dict(gewicht="12,5"))) == 12.5
ok(f"M4 Wenden: {round(gew, 1)} kg aus den Teilen, Gewicht der Stammdaten geht vor")

# ------------------------------------------------------------------ M5 Aus Zusatzarbeiten
for art, bez in (("€/kg", "Gewicht"), ("€/m²", "Oberfläche"), ("€/m", "Länge")):
    assert baugruppe.arbeitsgang_vorlage(dict(name="X", art=art, preis=1))["bezug"] == bez
assert "bezug" not in baugruppe.arbeitsgang_vorlage(dict(name="X", art="€/Stück", preis=1))
ok("M5 Aus Zusatzarbeiten: €/kg → Gewicht, €/m² → Oberfläche, €/m → Länge")

# ------------------------------------------------------------------ M6 Rahmen R1 bitgleich (ohne Bezug)
import beispiel_baugruppe  # noqa: E402
r1 = beispiel_baugruppe.rahmen()
assert not any(x.get("bezug") for x in r1["arbeitsgaenge"])
assert bg_mengen.je_knoten(r1, [], k) == {}
ok("M6 Baugruppen ohne Bezug: keine Mengen, Rechnung unverändert (Abnahme R1 in test_baugruppe_abnahme)")

# ------------------------------------------------------------------ M7 Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402


kopf, pos, k, tab, einst = laden()
saetze = rechnen.zeitbasis(kopf, k, tab)["saetze"]
from PySide6.QtWidgets import QWidget  # noqa: E402
eltern = QWidget()
eltern.k = k
pbg = next(p for p in pos if p["pos"] == 100)
d = BaugruppeDialog(eltern, pbg, pos, tab, saetze)
sp = [x.schluessel for x in d.ag_tab.spalten]
assert sp.index("bezug") == sp.index("menge") + 1
assert d.ag_tab.cellWidget(0, sp.index("bezug")).currentText() == "Gewicht"
assert "kg · " in d.mengen_info.text() and "Teile" in d.mengen_info.text()
nah(d.bg["arbeitsgaenge"][0]["menge"], round(bg_mengen.mengen(g, pos, k)["gewicht"], 4), "Editor: Menge eingetragen")
assert d.ag_tab.cellWidget(0, sp.index("menge")).text() != ""
assert "aus den Einzelteilen" in d.stamm_felder["gewicht"].placeholderText()
vorher = d.erg["fremd"]
d.ag_tab.cellWidget(1, sp.index("bezug")).setCurrentText("von Hand")
assert "bezug" not in d.bg["arbeitsgaenge"][1]
d.ag_tab.cellWidget(1, sp.index("menge")).setText("1")
nah(vorher - d.erg["fremd"], (bg_mengen.mengen(g, pos, k)["oberflaeche"] - 1) * 10, "Editor: Menge von Hand", 1e-3)
d.ag_tab.cellWidget(1, sp.index("bezug")).setCurrentText("Oberfläche")
nah(d.erg["fremd"], vorher, "Editor: wieder Oberfläche", 1e-3)
assert d.ag_tab.cellWidget(1, sp.index("menge")).toolTip().startswith("automatisch")
d.reject()
ok("M7 Editor: Spalte „Menge aus“, Mengen über der Tabelle, von Hand und zurück, Platzhalter Gewicht")
print("Alle Mengen-Tests bestanden.")
