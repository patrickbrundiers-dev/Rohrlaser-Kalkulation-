"""Prüft Serieneffekt, Rüsten je Los und das Lernen der Vorkalkulation (Plan Schweißbaugruppen 28.10.2026, Schritt 3):
- S1 Lernkurve: 10 % je Verdopplung = 90 % bei 2, 81 % bei 4, 72,9 % bei 8 Stück, Untergrenze 70 % bzw. eingetragen
- S2 Serieneffekt nur auf eigene laufende Zeiten (nicht Fremdleistung, Material, Einmalkosten)
- S3 Rüsten je Los: Rüstzeit × Lose, Einmalbetrag einmal je Auftrag
- S4 Staffelstufen: größere Stufe = weniger Zeit je Stück; ohne Eintrag bitgleich
- S5 Nachkalkulation: Soll davon Rüsten/Positionieren/Verputzen, Kennwert-Vorschlag und Freigabe der Regeln
- S6 Editor: Stammdatenfelder rechnen sofort, Summe nennt Faktor und Lose; Zeiten Schweißen/Arbeitsgänge getrennt

Aufruf: python tests/test_bg_serie.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, kennwerte, nachkalkulation, rechnen  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ S1 Lernkurve
def bg_mit(**stamm):
    g = baugruppe.leer()
    g["stamm"] = dict(stamm)
    return g


g = bg_mit(serie="10")
for n_, soll in ((1, 1.0), (2, 0.9), (4, 0.81), (8, 0.729)):
    nah(baugruppe.serie_faktor(g, n_)[0], soll, f"10 % bei {n_} Stück")
nah(baugruppe.serie_faktor(g, 64)[0], 0.7, "Untergrenze 70 %")                  # 0,9^6 = 0,53 → 0,70
assert "Untergrenze" in baugruppe.serie_faktor(g, 64)[1]
nah(baugruppe.serie_faktor(bg_mit(serie="10 %", serie_min="50"), 64)[0], 0.9 ** 6, "Untergrenze 50 %")
nah(baugruppe.serie_faktor(bg_mit(serie="7,5"), 2)[0], 0.925, "Komma")
for leer in (bg_mit(), bg_mit(serie=""), bg_mit(serie="0"), bg_mit(serie="abc"), bg_mit(serie="100")):
    assert baugruppe.serie_faktor(leer, 50) == (1.0, "")
assert baugruppe.lose(bg_mit(los="5"), 12) == 3 and baugruppe.lose(bg_mit(los="5"), 10) == 2
assert baugruppe.lose(bg_mit(), 12) == baugruppe.lose(bg_mit(los="0"), 12) == 1
ok("S1 Lernkurve 90/81/72,9 %, Untergrenze 70 % bzw. eingetragen, leer/ungültig = aus; Lose aufgerundet")

# ------------------------------------------------------------------ S2/S3 Rechnung
TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=0, status="geprüft",
                                   dichte=7.85, draht_eur_kg=2.0)],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=2.0, status="geprüft")])
SAETZE = {"Schweißen": 60.0}


def gruppe(**stamm):
    g = bg_mit(**stamm)
    g["naehte"] = [dict(id="n1", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1)]
    g["arbeitsgaenge"] = [dict(id="a1", name="Schleifen", satz=60, zeit_min=5, kosten_einheit=2.0),
                          dict(id="a2", name="Rüsten", satz=60, ruest_min=30, einmal_eur=100),
                          dict(id="a3", name="Verzinken", fremd=True, kosten_einheit=10.0)]
    return dict(stueck=12, baugruppe=baugruppe.speichern(g))


r0 = baugruppe.rechnen(gruppe(), TAB, SAETZE, 8)
r1 = baugruppe.rechnen(gruppe(serie="10"), TAB, SAETZE, 8)
f = 0.729
naht0, naht1 = (next(z for z in r["zeilen"] if z["id"] == "n1") for r in (r0, r1))
nah(naht1["zeit_min"], naht0["zeit_min"] * f, "Naht: Zeit × 0,729")
mat = naht0["werte"]["material"]
assert mat > 0
nah(naht1["kosten"], (naht0["kosten"] - mat) * f + mat, "Naht: Schweißzusatz bleibt")
schl0, schl1 = (next(z for z in r["zeilen"] if z["id"] == "a1") for r in (r0, r1))
nah(schl1["kosten"], 5 * f + 2.0, "Schleifen: 5 min × 0,729 × 60 €/h + 2 € Material")
nah(r1["fremd"], r0["fremd"], "Fremdleistung bleibt")
nah(r1["einmal_gesamt"], r0["einmal_gesamt"], "Einmalkosten bleiben")
nah(r1["serie"], f, "Faktor")
assert "72,9 %" in r1["serie_text"], r1["serie_text"]
r2 = baugruppe.rechnen(gruppe(los="5"), TAB, SAETZE, 12)
nah(r0["einmal_gesamt"], 30 + 100, "ein Los: 30 min × 60 €/h + 100 €")
nah(r2["einmal_gesamt"], 3 * 30 + 100, "3 Lose: 3 × 30 € + 100 € Vorrichtung")
assert r2["lose"] == 3
ok("S2/S3 Serieneffekt nur auf eigene Zeiten (Zusatz, Fremd, Einmal bleiben), 3 Lose = 3 × Rüsten + 1 × Vorrichtung")

# ------------------------------------------------------------------ S4 Stufen
je = [baugruppe.rechnen(gruppe(serie="10"), TAB, SAETZE, n_)["eigen"] for n_ in (1, 10, 100)]
assert je[0] > je[1] > je[2], je
ohne = [baugruppe.rechnen(gruppe(), TAB, SAETZE, n_) for n_ in (1, 10)]
assert ohne[0]["serie"] == ohne[1]["serie"] == 1.0
nah(ohne[0]["zeit_min"] - 30, ohne[1]["zeit_min"] - 3, "ohne Serieneffekt: laufende Zeit gleich")
ok(f"S4 Stufen mit Serieneffekt: {je[0]:.2f} / {je[1]:.2f} / {je[2]:.2f} € je Baugruppe bei 1/10/100")

# ------------------------------------------------------------------ S5 Nachkalkulation und Lernen
db = Datenbank(Path(tempfile.mkdtemp()) / "s.db")
nummern = []
for q in (1.2, 1.2, 1.1, 1.3, 1.25):
    g = baugruppe.leer()
    g["arbeitsgaenge"] = [
        dict(id="r", name="Rüsten Schweißplatz", satz=60, ruest_min=18, vk=dict(art="ruesten", status="bestätigt")),
        dict(id="p", name="Teile positionieren", satz=60, zeit_min=6, vk=dict(art="positionieren", status="bestätigt")),
        dict(id="v", name="Verputzen", satz=60, zeit_min=3, vk=dict(art="verputzen", status="bestätigt"))]
    g["naehte"] = [dict(id="n", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, zeit_hand=2)]
    aid = db.angebot_neu(dict(kunde="Lernen", maschine="T11"))
    db.position_neu(aid, dict(pos=10, art=BAUGRUPPE, artikel="L", stueck=10, baugruppe=baugruppe.speichern(g)))
    db.nachkalkulation_speichern(aid, dict(am="2026-10-28", baugruppen={g["id"]: dict(
        ruesten_h=0.3 * q, positionieren_h=1.0 * q)}))
    nummern.append(db.angebot(aid)["nummer"])
kopf = db.angebot(aid)
pos = db.positionen(aid)
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
zeilen, summen = rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k, tab, einst), k, tab, einst)
z_bg = next(z for z in summen["zeiten"] if z["schritt"] == "Schweißbaugruppen")
assert "davon Schweißen 20 min" in z_bg["formel"], z_bg["formel"]
soll = nachkalkulation.baugruppen_soll(pos, zeilen)[0]
nah(soll["teile"]["ruesten_h"], 0.3, "Soll Rüsten 18 min")
nah(soll["teile"]["positionieren_h"], 1.0, "Soll Positionieren 6 min × 10")
nah(soll["teile"]["verputzen_h"], 0.5, "Soll Verputzen 3 min × 10")
faelle = [x for x in kennwerte.faelle_vorkalkulation(db) if x["angebot"] in nummern]
assert sorted({x["schluessel"] for x in faelle}) == [("Positionieren",), ("Rüsten",)]
v = next(x for x in kennwerte.vorschlaege(db) if x["quelle"] == "vorkalkulation" and x["schluessel"] == ("Rüsten",))
nah(v["faktor"], 1.2, "Median Rüsten")
from rohrlaser import vorkalk  # noqa: E402
for z in vorkalk.richtwerte():
    db.neu("schweiss_regeln", z)
alt = {z["id"]: (z["art"], z["zahl"]) for z in db.zeilen("schweiss_regeln")}
hid = kennwerte.freigeben(db, v, "Test Rüsten", "x")
for z in db.zeilen("schweiss_regeln"):
    a_, w_ = alt[z["id"]]
    nah(z["zahl"], round(w_ * 1.2, 2) if a_ == "Rüsten" else w_, f"Regel {a_} {z['wert']}")
assert kennwerte.zuruecknehmen(db, hid) == sum(1 for a_, _ in alt.values() if a_ == "Rüsten")
ok("S5 Zeiten: davon Schweißen; Soll davon Rüsten 0,3 h / Positionieren 1,0 h / Verputzen 0,5 h, Vorschlag Rüsten × 1,2, Freigabe und zurück")

# ------------------------------------------------------------------ S6 Editor und Zeiten
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
eltern = QWidget()
eltern.k = k
p = dict(gruppe(), id=1, pos=1, art=BAUGRUPPE, stueck=8)
d = BaugruppeDialog(eltern, p, [p], TAB, SAETZE)
vorher = d.erg["eigen"]
d.stamm_felder["serie"].setText("10")
nah(d.erg["serie"], f, "Editor Faktor")
assert "72,9 %" in d.summe.text()
assert d.erg["eigen"] < vorher
d.stamm_felder["los"].setText("4")
assert d.erg["lose"] == 2 and "2 Lose" in d.summe.text()
assert d.daten()["stamm"]["serie"] == "10"
assert d.stamm_felder["serie_min"].placeholderText() == "leer = 70"
d.reject()
ok("S6 Editor: Serieneffekt und Losgröße rechnen sofort, Summe nennt 72,9 % und 2 Lose")
print("Alle Serien-Tests bestanden.")
