"""Roadmap Kalkulation, Phase 2 Paket 2c Kalkulation (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“).

CALC-006  Werkzeugkosten je Einheit der Zusatzarbeit.
CALC-007  Lernkurve nach Stückzahl (nicht für Gewinde/Senken/Flowdrill/Bohren).
CALC-008  Preisstaffel nach der Menge im ganzen Angebot.
CALC-016  Fremdleistung: Fracht je Angebot umgelegt, zusätzliche Lieferzeit als Hinweis.
CALC-019  Sperrgut-Zuschlag ab Teillänge/-gewicht.
CALC-024  Folge-Vorschläge und Hinweise zu Paaren von Zusatzarbeiten.
CALC-015  Handling-Zuschlag je Teil ab Länge/Gewicht (Maschine).
CALC-018  Ausschuss nach Regel (Werkstoff/Wand).
CALC-020  Programmierzeit je schrägem Ende.
CALC-026  Bündeln/Umreifen je Packmittel.
CALC-010  Sägen statt Lasern als Hinweis.
CALC-027  Preis je Bohrungsart in der Auswahl.
Leer = wie bisher (alle neuen Felder und Einstellungen).

Aufruf: python tests/test_phase2c_1311.py
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

import beispiel_angebot as B  # noqa: E402
from rohrlaser import bohrbild, kalk_mehr, preisschicht, rechnen, zeit_zusatz, zusatz_erkennung, zusatz_mehr  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import TABELLE  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[1])          # RR 42,4x2,0 S235, 860 mm, 2 Einstiche (nur die Enden)
K1 = db.zeilen("kunden")[0]["kundennr"]


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def kalk(s, **einst):
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, dict(s.einst, **einst))


def zus(namen):
    return json.dumps([dict(name=n) for n in namen], ensure_ascii=False)


def eintrag(zeile, name):
    return next(e for e in zeile["zusatzarbeiten"] if e["name"] == name)


def katalog(name):
    return next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == name)


def setzen(name, **werte):
    z = katalog(name)
    for f, w in werte.items():
        db.aendern("zusatzarbeiten", z["id"], f, w)


# ------------------------------------------------------------------ Schema und Vorgaben leer
for t, felder in (("zusatzarbeiten", {"werkzeug", "lernkurve", "staffel", "fracht_fremd", "tage_fremd", "sperr_ab_m",
                                      "sperr_ab_kg", "sperr_zuschlag", "folge", "hinweis_mit"}),
                  ("maschinen", {"handling_laenge", "handling_kg", "zeit_handling"}),
                  ("verpackung", {"zeit_bund", "material_bund"})):
    assert felder <= {f.name for f in TABELLE[t].felder}, t
    assert all(z.get(f) in (None, "") for z in db.zeilen(t) for f in felder), t
for n in ("programmierung_ende", "saege_satz", "saege_s_schnitt", "saege_ruesten_min"):
    assert not db.einstellung(n), n
assert not db.einstellung("ausschuss_regeln")
ok("Schema: neue Felder und Einstellungen vorhanden und leer")

# ------------------------------------------------------------------ reine Funktionen
assert zusatz_mehr.ab_tabelle("11 = 0,9; ab 51=0.8; Unsinn") == [(11.0, 0.9), (51.0, 0.8)]
assert zusatz_mehr.lernfaktor(dict(lernkurve="11 = 0,9; 51 = 0,8"), 10) == 1.0
assert zusatz_mehr.lernfaktor(dict(lernkurve="11 = 0,9; 51 = 0,8"), 11) == 0.9
assert zusatz_mehr.lernfaktor(dict(lernkurve="11 = 0,9; 51 = 0,8"), 400) == 0.8
assert zusatz_mehr.sperr_faktor(dict(sperr_ab_m=3, sperr_zuschlag=20), 3200, None) == 1.2
assert zusatz_mehr.sperr_faktor(dict(sperr_ab_m=3, sperr_zuschlag=20), 2900, None) == 1.0
assert zusatz_mehr.sperr_faktor(dict(sperr_ab_kg=50, sperr_zuschlag=10), 1000, 60) == 1.1
assert kalk_mehr.ausschuss_regeln("Edelstahl bis 1,5 = 2; Aluminium = +1 %") == [("edelstahl", 1.5, 2.0),
                                                                                   ("aluminium", None, 1.0)]
assert bohrbild.option_preis(bohrbild.NUR_LASER, "M8", {}, {}) == 0.0
assert bohrbild.option_preis(bohrbild.GEWINDE_SCHNEIDEN, "M8", {"M8": 1.2}, {}) == 1.2
assert bohrbild.option_preis(bohrbild.GEWINDE_SCHNEIDEN, "M8", {}, {}) is None
fd = bohrbild.ZUSATZ_AUS[bohrbild.FLOWDRILL]
assert abs(bohrbild.option_preis(bohrbild.FLOWDRILL, "M8", {"M8": 1.2}, {fd: 0.6}) - 1.8) < 1e-9
ok("Funktionen: Ab-Tabellen, Lernkurve, Sperrgut, Ausschuss-Regeln, Preis je Bohrungsart")

# ------------------------------------------------------------------ CALC-006/007/019 an einer Position
s = angebot(dict(ROHR, stueck=20, zusatz=zus(["Entgraten", "Feuerverzinken"])))
z0, _ = kalk(s)
e0, v0 = eintrag(z0[0], "Entgraten"), eintrag(z0[0], "Feuerverzinken")
setzen("Entgraten", werkzeug=0.1)
setzen("Feuerverzinken", lernkurve="11 = 0,9", sperr_ab_m=0.8, sperr_zuschlag=25)
s.neu_laden()
z1, _ = kalk(s)
e1, v1 = eintrag(z1[0], "Entgraten"), eintrag(z1[0], "Feuerverzinken")
assert abs(e1["betrag"] - (e0["betrag"] + 0.1)) < 1e-6, (e0["betrag"], e1["betrag"])
assert abs(v1["faktor_mehr"] - 0.9 * 1.25) < 1e-9 and abs(v1["betrag"] - v0["betrag"] * 1.125) < 1e-6, v1
ok(f"CALC-006/007/019: Werkzeug +0,10 € je Stück, Verzinken × 0,9 Lernkurve × 1,25 Sperrgut "
   f"({rechnen.zahl(v0['betrag'], 3)} → {rechnen.zahl(v1['betrag'], 3)} € je Teil)")

# nie für Gewinde/Senken/Flowdrill/Bohren (nur € je Stück)
setzen("Senken", lernkurve="2 = 0,5")
s = angebot(dict(ROHR, stueck=20, zusatz=json.dumps([dict(name="Senken", menge=2)])))
z, _ = kalk(s)
assert eintrag(z[0], "Senken")["faktor_mehr"] == 1.0
ok("CALC-007: Senken bleibt € je Stück ohne Lernkurve")

# ------------------------------------------------------------------ CALC-008 Staffel, CALC-016 Fracht
setzen("Feuerverzinken", lernkurve=None, sperr_zuschlag=None, staffel="0 = 0,80; 50 = 0,55", fracht_fremd=90,
       tage_fremd=4)
s = angebot(dict(ROHR, stueck=20, zusatz=zus(["Feuerverzinken"])),
            dict(ROHR, pos=30, stueck=40, zusatz=zus(["Feuerverzinken"])))
z, sm = kalk(s)
a, b = eintrag(z[0], "Feuerverzinken"), eintrag(z[1], "Feuerverzinken")
menge = a["menge"] * 20 + b["menge"] * 40
assert abs(a["staffel_menge"] - menge) < 1e-6
assert a["preis"] == (0.55 if menge >= 50 else 0.80), (menge, a["preis"])
assert abs(a["fracht_teil"] - 90 / 60) < 1e-6 and abs(b["fracht_teil"] - 90 / 60) < 1e-6
tage, name = zusatz_mehr.lieferzeit_tage(s.positionen, s.tabellen)
assert (tage, name) == (4, "Feuerverzinken")
t = [p.text for p in s._kalk_mehr_punkte(z)]
assert any("verlängert die Lieferzeit um 4 Arbeitstage" in x for x in t), t
ok(f"CALC-008/016: Staffel nach {rechnen.zahl(menge, 1)} kg im Angebot = {rechnen.zahl(a['preis'], 2)} €/kg, "
   "Fracht 90 € auf 60 Teile, +4 Arbeitstage im Angebots-Check")

# ------------------------------------------------------------------ CALC-024 Folge und Hinweis
setzen("Pulverbeschichten", folge="Strahlen", hinweis_mit="Feuerverzinken = Duplex-Beschichtung: Haftung prüfen")
p = dict(ROHR, zusatz=zus(["Pulverbeschichten", "Feuerverzinken"]))
assert zusatz_mehr.folge_vorschlaege(p, s.tabellen) == []          # Tabellen von vor der Änderung
s.neu_laden()
assert zusatz_mehr.folge_vorschlaege(p, s.tabellen) == ["Strahlen"]
assert zusatz_mehr.hinweise(p, s.tabellen) == [("Pulverbeschichten", "Feuerverzinken",
                                                "Duplex-Beschichtung: Haftung prüfen")]
assert zusatz_mehr.folge_vorschlaege(dict(p, zusatz=zus(["Pulverbeschichten", "Strahlen"])), s.tabellen) == []
assert zusatz_erkennung.FOLGE
ok("CALC-024: Pulvern schlägt Strahlen vor, Verzinken + Pulvern nennt Duplex")

# ------------------------------------------------------------------ CALC-015 Handling
m = dict(handling_laenge=800, zeit_handling=40)
assert zeit_zusatz.handling_s(dict(ROHR), m, s.k) == 40
assert zeit_zusatz.handling_s(dict(ROHR, laenge=700), m, s.k) == 0
assert zeit_zusatz.handling_s(dict(ROHR), dict(m, zeit_handling=None), s.k) == 0
assert zeit_zusatz.handling_s(dict(ROHR, laenge=700), dict(handling_kg=0.5, zeit_handling=20), s.k) == 20
ok("CALC-015: Handling-Zuschlag ab Länge bzw. Gewicht, ohne Zeit aus")

# ------------------------------------------------------------------ CALC-018 Ausschuss nach Regel
s = angebot(dict(ROHR, stueck=20))
z0, s0 = kalk(s, ausschuss=0.02)
z1, s1 = kalk(s, ausschuss=0.02, ausschuss_regeln="S235 bis 2 = 3")
z2, _ = kalk(s, ausschuss=0.02, ausschuss_regeln="S235 bis 1,5 = 3")
assert z1[0]["ausschuss_plus"] == 3.0 and z2[0]["ausschuss_plus"] == 0.0
assert z1[0]["ausschuss_teil"] > z0[0]["ausschuss_teil"] * 2 and abs(z2[0]["ausschuss_teil"] - z0[0]["ausschuss_teil"]) < 1e-9
assert s1["ausschuss_regel_n"] == 1
ok(f"CALC-018: Regel „S235 bis 2 = 3“ → Ausschuss {rechnen.zahl(z0[0]['ausschuss_teil'], 3)} → "
   f"{rechnen.zahl(z1[0]['ausschuss_teil'], 3)} € je Teil; Wand 2 > 1,5 = keine Regel")

# ------------------------------------------------------------------ CALC-020 Programmierzeit je schrägem Ende
gehrung = json.dumps(dict(winkel=45, richtung=90))
p = dict(ROHR, a_ende=gehrung, b_ende=gehrung)
e = dict(programmierung_zeit=5, programmierung_kontur=0.5)
assert kalk_mehr.schraege_enden(p) == 2
assert rechnen.programmier_zeit(p, e)[0] == 5
assert rechnen.programmier_zeit(p, dict(e, programmierung_ende=1.5))[0] == 8
ok("CALC-020: zwei Gehrungen × 1,5 min = 3 min mehr Programmierzeit")

# ------------------------------------------------------------------ CALC-026 Bündeln
vp = [dict(name="Bund", preis=2.0, max_kg=500, aktiv="ja", zeit_bund=6, material_bund=1.5)]
assert abs(preisschicht.stueckpreis(vp[0], 40.0) - (2.0 + 1.5 + 4.0)) < 1e-9
assert preisschicht.stueckpreis(dict(preis=2.0), 40.0) == 2.0
assert preisschicht.packmittel([dict(name="nur Umreifen", preis=None, zeit_bund=5, aktiv="ja")], 10, 1000, 40.0)
ok("CALC-026: Packmittel 2 € + Umreifung 1,50 € + 6 min × 40 €/h = 7,50 € je Bund")

# ------------------------------------------------------------------ CALC-010 Sägen statt Lasern
s = angebot(dict(ROHR, stueck=40), dict(B.POSITIONEN[0], stueck=24))
z, _ = kalk(s)
assert kalk_mehr.saege_vergleich(s.positionen, z, s.einst) == []          # aus
e = dict(s.einst, saege_satz=30.0, saege_s_schnitt=2.0)
v = kalk_mehr.saege_vergleich(s.positionen, z, e)
assert [x[1] for x in v] == [20], v          # Pos. 10 hat 4 Einstiche (Innenkonturen)
s.einst = e
t = [p.text for p in s._kalk_mehr_punkte(z)]
assert any("Sägen wäre günstiger" in x and "Pos. 20" in x for x in t), t
ok(f"CALC-010: Pos. 20 sägen {rechnen.zahl(v[0][3], 3)} € statt lasern {rechnen.zahl(v[0][2], 3)} € je Teil (Hinweis)")

# ------------------------------------------------------------------ CALC-027 Preis je Option im Fenster
from rohrlaser.bohrbild_dialog import BohrbildDialog  # noqa: E402
pos = dict(ROHR, profil_id="QR 40x40x3", schneidweg=400.0, einstiche=4, gewinde_vorschlag="2xM8")
gew = [(g["gewinde"], g["kernloch"]) for g in db.zeilen("gewinde")]
d = BohrbildDialog(None, pos, gew, wand=3.0, katalog=db.zeilen("zusatzarbeiten"),
                   saetze=rechnen.stundensaetze(s.tabellen), gewinde_preise={"M8": 1.2})
assert d.zeilen
texte = [d.zeilen[0].aus.itemText(i) for i in range(d.zeilen[0].aus.count())]
assert any("Gewinde schneiden" in x and "1,20 €" in x for x in texte), texte
assert any("Flowdrill" in x and "€" in x and "fehlt" not in x for x in texte), texte
ok("CALC-027: Auswahl zeigt € je Stück je Ausführung: " + " | ".join(texte))
d.close()

fenster.close()
db.schliessen()
print("Alle Prüfungen Paket 2c bestanden.")
