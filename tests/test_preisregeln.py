"""Prüft die Preisregeln aus der Prüfung der Preisberechnung (Patrick 26.10.2026, „alle a außer 8“).

1  Zuschnittkosten beim Lieferanten gehen in die Stangenkosten ein
2  Satzpreis im Angebot aus ungerundeten Stückpreisen (gleich dem Staffelpreis derselben Menge)
3  Mindestmarge am Warenwert (Gewinn + Anhebung) ÷ (Selbstkosten + Gewinn + Anhebung)
5  Mindestpreis für die Ware ohne Fracht, nach Abzug des Skontos
6  Pauschale je Abmessung: Vorgabe 0 €
8  Zukaufteile und Bleche ohne Gewinn, nur mit ihrem Aufschlag
9  Stangenwechsel nach Stangenanteil, Rüsten Maschine nach Maschinenzeit (Summen unverändert)
Regression: festgeschriebene Angebote (Merker preisregeln fehlt) rechnen bitgleich wie bis 25.10.2026.

Aufruf: python tests/test_preisregeln.py
"""
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
import beispiel_baugruppe  # noqa: E402
from rohrlaser import angebot_check, ausgabe, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=EPS):
    return abs(a - b) < eps


def angebot(positionen=None, einst_extra=None, kopf_extra=None):
    """Beispielangebot rechnen: (kopf, positionen, k, tabellen, einst, ergebnis, zeilen, summen)."""
    db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
    aid = db.angebot_neu(dict(beispiel_angebot.KOPF, **(kopf_extra or {})))
    for p in positionen or beispiel_angebot.POSITIONEN:
        db.position_neu(aid, p)
    kopf, pos = db.angebot(aid), db.positionen(aid)
    k, tab = db.kontext(), db.tabellen()
    tab["einstellungen"] = dict(tab["einstellungen"], **(einst_extra or {}))
    einst = rechnen.einstellungen_angebot(kopf, dict(db.einstellungen(), **(einst_extra or {})))
    db.schliessen()
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
    return kopf, pos, k, tab, einst, erg, zeilen, summen


ALT = dict(preisregeln=rechnen.PREISREGELN_ALT)

# Regression: Stand bis 25.10.2026 bitgleich (Werte vor der Änderung gemessen, Pauschale je Abmessung damals 22,50 €)
kopf, pos, k, tab, einst, erg, zeilen, summen = angebot(einst_extra=ALT, kopf_extra=dict(pauschale_abmessung=22.5))
assert summen["verkauf"] == 1271.197188369442, summen["verkauf"]
assert ausgabe.angebot(kopf, pos, zeilen, k, einst)["netto"] == 1271.36
assert [z["preis"] for z in ausgabe.angebot(kopf, pos, zeilen, k, einst)["zeilen"] if z["art"] == "satz"] == [168.49]
ok("festgeschrieben vor dem 26.10.2026: Beispielangebot 1.271,20 € kalkuliert, 1.271,36 € netto, Satz 168,49 € (wie bisher)")

# 6) Pauschale je Abmessung: Vorgabe 0 €
assert EINSTELLUNG["pauschale_abmessung"].vorgabe == 0
kopf, pos, k, tab, einst, erg, zeilen, summen = angebot()
assert summen["pauschalen"] == 0
ok("6  Pauschale je Abmessung: Vorgabe 0 € (Rüsten je Abmessung deckt sie)")

# 9) Verteilung: Rüsten Maschine nach Laserzeit, Stangenwechsel nach Stangenanteil; Summen gleich
z = [x for x in zeilen if x]
assert nah(sum(x["ruesten_maschine_teil"] * x["stueck"] for x in z), summen["ruesten_maschine"])
assert nah(sum(x["stangenwechsel_teil"] * x["stueck"] for x in z), summen["stangenwechsel_kosten"])
zeit = sum(x["laser_netto"] * x["stueck"] for x in z)
for x in z:
    assert nah(x["ruesten_maschine_teil"], summen["ruesten_maschine"] * x["laser_netto"] / zeit)
lang = next(x for x in z if x["pos"] == 30)       # QR 40x40x3, 2.150 mm
kurz = next(x for x in z if x["pos"] == 50)       # RR 48,3x2,6, 345 mm
assert lang["stangenwechsel_teil"] > 4 * kurz["stangenwechsel_teil"]
ok("9  Rüsten Maschine nach Maschinenzeit, Stangenwechsel nach Stangenanteil (2.150-mm-Teil trägt > 4 × so viel "
   "wie 345 mm), Summen unverändert")

# 2) Satzpreis aus ungerundeten Stückpreisen = Staffelpreis derselben Menge
a = ausgabe.angebot(kopf, pos, zeilen, k, einst)
satz = next(x for x in a["zeilen"] if x["art"] == "satz")
roh = sum(x["preis_teil"] * p["je_satz"] for x, p in zip(zeilen, pos) if p.get("satz") == "Rahmen")
assert satz["preis"] == ausgabe.kaufm_runden(roh, 2)
nur_satz = [p for p in beispiel_angebot.POSITIONEN if p.get("satz") == "Rahmen"]
kopf2, pos2, k2, tab2, einst2, erg2, zeilen2, _ = angebot(nur_satz)
st = staffeln.stufe_rechnen(kopf2, pos2, "Rahmen", 4, k2, tab2, einst2)
satz2 = next(x for x in ausgabe.angebot(kopf2, pos2, zeilen2, k2, einst2)["zeilen"] if x["art"] == "satz")
assert satz2["preis"] == st["preis_einheit"], (satz2["preis"], st["preis_einheit"])
ok(f"2  Satzpreis aus ungerundeten Stückpreisen: Satz Rahmen 4 × {satz2['preis']} € im Angebot = Staffel „ab 4“")

# 5) Mindestpreis: Ware ohne Fracht nach Skonto erreicht genau den Mindestpreis
klein = [dict(beispiel_angebot.POSITIONEN[0], stueck=3)]
kopf, pos, k, tab, einst, erg, zeilen, summen = angebot(klein, kopf_extra=dict(fracht=30.0))
x = zeilen[0]
sk = summen["skonto_satz"] / 100
ware = (x["preis_teil"] * (1 - sk) - x["fracht_teil"]) * x["stueck"]
assert nah(ware, 200.0) and summen["mindestpreis_gilt"] and nah(summen["fracht"], 30.0)
st = staffeln.stufe_rechnen(kopf, pos, "10", 3, k, tab, einst)
assert nah(st["preis"]["netto"], summen["verkauf"]) and st["preis_einheit"] == ausgabe.aufrunden(x["preis_teil"])
a = ausgabe.angebot(kopf, pos, zeilen, k, einst)
assert a["netto"] * (1 - sk) - 30.0 >= 200.0 - 0.01 and "Warenwert ohne Fracht" in a["mindestpreis"]
ok(f"5  Mindestpreis 200 € für die Ware: mit 30 € Fracht und 2 % Skonto {zeilen[0]['preis_teil']:.2f} € je Teil, "
   "Staffel gleich")

# 3) Mindestmarge am Warenwert: 10 % Gewinn auf Selbstkosten = 9,09 % Marge (nicht 8,9 % am Verkaufspreis)
kopf, pos, k, tab, einst, erg, zeilen, summen = angebot()
m = summen["gewinn"] / (summen["selbst"] + summen["gewinn"])
assert nah(m, 0.1 / 1.1)
pkt = angebot_check.punkte(kopf, pos, ["OK"] * len(pos), "", summen, mindestmarge=0.09, admin=True)
assert not any("Mindestmarge" in p[1] for p in pkt), list(pkt)
pkt = angebot_check.punkte(kopf, pos, ["OK"] * len(pos), "", summen, mindestmarge=0.095, admin=True)
assert any("Marge 9,1 % unter der Mindestmarge 9,5 %" in p[1] for p in pkt)
ok("3  Mindestmarge am Warenwert: 10 % Gewinn = 9,1 % Marge, Warnung erst unter 9,1 %")

# 8) Zukaufteile ohne Gewinn: Zukaufteil-Zeile und Baugruppe
zk = [dict(einstand=Decimal("100"), aufschlag=Decimal("10"), fehler=None)]
neu = rechnen._zukaufteil_zeile({}, 1, zk, 0.0, 0.02, gew=0.1, zk_gewinn=False)
alt = rechnen._zukaufteil_zeile({}, 1, zk, 0.0, 0.02, gew=0.1)
assert neu["gewinn_teil"] == 0 and nah(neu["preis_teil"], 110 / 0.98)
assert nah(alt["preis_teil"], 121 / 0.98)
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
bid = beispiel_baugruppe.anlegen(db)
kopf, pos, k, tab = db.angebot(bid), db.positionen(bid), db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
db.schliessen()
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
for x in zeilen:
    if x:
        assert nah(x["gewinn_teil"], (x["selbst_teil"] - x["zukauf_teil"]) * einst["gewinn"]), x["pos"]
ok("8  Zukaufteile ohne Gewinn: Blech EK 100 € + 10 % Aufschlag = 112,24 € (statt 123,47 €); Gewinn je Zeile nur "
   "auf Selbstkosten ohne Zukaufteile")

# 1) Zuschnittkosten: je Zuschnitt beim Lieferanten in den Stangenkosten
kopf, pos, k, tab, einst, erg, zeilen, summen = angebot()
s = dict(erg["stangen"][0])
s["werkstuecke"] = [dict(nr=1, von=0.0, bis=5000.0, laenge=5000.0, end=s["end"], greif=0.0),
                    dict(nr=2, von=5003.0, bis=11000.0, laenge=5997.0, end=s["end"], greif=0.0)]
s["teile"] = [dict(t, werkstueck=1) for t in s["teile"]]
s["stange"] = 12000.0
assert rechnen.zuschnitte(s, 3.0) == 2          # zwischen den Werkstücken + Rest 1.000 mm
s1 = dict(s, werkstuecke=[s["werkstuecke"][0], dict(s["werkstuecke"][1], bis=11999.0, laenge=6996.0)])
assert rechnen.zuschnitte(s1, 3.0) == 1          # Rest 1 mm < Sägeschnitt: kein zweiter Zuschnitt
e = dict(erg, stangen=[s])
ohne = rechnen.stangen_werte(e, kopf, pos, k, tab)[0]["kosten"]
tab3 = dict(tab, einstellungen=dict(tab["einstellungen"], zuschnitt_kosten=3.0, zuschnitt_verlust=3.0))
mit = rechnen.stangen_werte(e, kopf, pos, k, tab3)[0]["kosten"]
assert nah(mit - ohne, 6.0)
tab4 = dict(tab3, einstellungen=dict(tab3["einstellungen"], preisregeln=rechnen.PREISREGELN_ALT))
assert rechnen.stangen_werte(e, kopf, pos, k, tab4)[0]["kosten"] == ohne
ok("1  Zuschnittkosten: 2 Zuschnitte à 3 € = +6,00 € je Lieferstange (festgeschrieben: wie bisher ohne)")

print("OK: Preisregeln 26.10.2026")
