"""Angebotswesen P1 (Patrick 20.11.2026): Staffeln mit Mindestmarge als Preisuntergrenze, Kennzahlen je Staffel
(Deckungsbeitrag, Marge, Einsparung), Staffelrabatt, Preis von Hand mit Protokoll und Zukauf-Einstand je Staffel.

Mengen 1, 5, 10, 25, 50 und 100 Stück einer Position, jede als eigene Stufe (eigener Auftrag). Ohne Mindestmarge
bleibt jeder Preis bitgleich wie bisher."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import ausgabe, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

MENGEN = (1, 5, 10, 25, 50, 100)


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    return abs(a - b) <= eps


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
db.staffel_stufen_loeschen([z["id"] for z in db.staffel_stufen(a)])
for m in MENGEN:
    db.staffel_neu(a, dict(schluessel="10", menge=m))
s.neu_laden()


def rechnen():
    s.neu_laden()
    sp = s.staffelpreise_rechnen()
    assert sp and len(sp) == len(MENGEN), sp
    return sorted(sp, key=lambda z: z["menge"])


# ------------------------------------------------------------------ 1) ohne Mindestmarge: bitgleich
sp = rechnen()
for z in sp:
    p = z["preis"]
    assert nah(p["netto"], z["bausteine"]["verkauf"]), (z["menge"], p["netto"], z["bausteine"]["verkauf"])
    assert z["preis_einheit"] == ausgabe.kaufm_runden(z["bausteine"]["verkauf"] / z["menge"], 2) or \
        p["mindest_anhebung"] > 0, (z["menge"], z["preis_einheit"], z["bausteine"]["verkauf"], p["mindest_anhebung"])
    assert p["mindestmarge_anhebung"] == 0 and not p["unter_mindestmarge"] and p["staffelrabatt"] == 0
    assert nah(p["deckungsbeitrag"], p["selbst"] + p["gewinn_gesamt"] - p["variabel"])
    assert p["variabel"] <= p["selbst"] + 1e-9
preise = [z["preis_einheit"] for z in sp]
assert preise == sorted(preise, reverse=True), preise          # Rüsten verteilt sich: größere Menge billiger
staffeln.einsparung(sp)
assert sp[0]["einsparung"] is None and all(0 <= z["einsparung"] < 1 for z in sp[1:])
assert nah(sp[-1]["einsparung"], 1 - sp[-1]["preis_einheit"] / sp[0]["preis_einheit"])
ok(f"ohne Mindestmarge: 6 Staffeln bitgleich wie bisher, Stückpreise {preise}, Deckungsbeitrag und Einsparung "
   f"({100 * sp[-1]['einsparung']:.0f} % bei 100 Stück)")
ohne = {z["menge"]: z["preis_einheit"] for z in sp}
marge_ohne = {z["menge"]: z["preis"]["marge"] for z in sp}

# ------------------------------------------------------------------ 2) Mindestmarge schützt jede Staffel
M = round(max(marge_ohne.values()) + 0.05, 2)        # sicher über der Marge aller Staffeln
db.einstellung_setzen("mindestmarge", M)
sp = rechnen()
for z in sp:
    p = z["preis"]
    assert p["mindestmarge"] == M and p["mindestmarge_anhebung"] > 0, z["menge"]
    assert p["marge"] >= M - 1e-9, (z["menge"], p["marge"])
    # Formel: Anhebung auf die Ware = m·S/(1−m) − Gewinn − Anhebung auf den Mindestpreis (vor dem Aufrunden)
    soll = M * p["selbst"] / (1 - M) - p["gewinn"] - p["mindest_anhebung"] * (1 - p["skonto_anteil"])
    assert nah(p["mindestmarge_anhebung"] * (1 - p["skonto_anteil"]), soll, 1e-6), (soll, p["mindestmarge_anhebung"])
    assert z["preis_einheit"] >= ohne[z["menge"]]
    assert "Mindestmarge" in (z.get("hinweis") or "")
    assert p["marge"] - M < 0.01 * z["menge"] / p["ware"] + 1e-6 or p["marge"] - M < 0.001   # nur Aufrundung darüber
ok(f"Mindestmarge {100 * M:.0f} %: jede Staffel auf die Mindestmarge angehoben (Anhebung = m·S/(1−m) − G), "
   f"Hinweis je Staffel")

db.einstellung_setzen("mindestmarge_staffel", "nein")
sp = rechnen()
assert {z["menge"]: z["preis_einheit"] for z in sp} == ohne
assert all(z["preis"]["mindestmarge_anhebung"] == 0 for z in sp)
db.einstellung_setzen("mindestmarge_staffel", "ja")
ok("Einstellung „Staffeln: Preis auf die Mindestmarge anheben“ = nein: Preise wie ohne Mindestmarge")

# ------------------------------------------------------------------ 3) Staffelrabatt, von der Mindestmarge begrenzt
db.einstellung_setzen("mindestmarge", 0)
stufe = next(x for x in db.staffel_stufen(a) if any(z["stufe_id"] == x["id"] and z["menge"] == 50
                                                    for z in db.staffeln(a)))
db.staffel_stufe_aendern(stufe["id"], "rabatt_proz", 10)
sp = rechnen()
z50 = next(z for z in sp if z["menge"] == 50)
p = z50["preis"]
assert nah(p["staffelrabatt"], 0.10 * (p["selbst"] + p["gewinn"]))
assert nah(p["netto"], z50["bausteine"]["verkauf"] - p["staffelrabatt"] / (1 - p["skonto_anteil"]))
assert z50["preis_einheit"] < ohne[50]
db.einstellung_setzen("mindestmarge", M)
sp = rechnen()
z50 = next(z for z in sp if z["menge"] == 50)
assert z50["preis"]["marge"] >= M - 1e-9 and z50["preis"]["mindestmarge_anhebung"] > 0
ok("Staffelrabatt 10 % auf die Ware; mit Mindestmarge wird der Rabatt nur so weit gewährt, wie die Marge reicht")
db.staffel_stufe_aendern(stufe["id"], "rabatt_proz", None)

# ------------------------------------------------------------------ 4) Preis von Hand mit Protokoll und Warnung
st = s.st_seite
z10 = next(x for x in db.staffeln(a) if x["menge"] == 10)
stufe10 = next(x for x in st.modell.daten if x["id"] == z10["stufe_id"])
berechnet = next(z for z in st.zeilen if z["menge"] == 10)["preis"]["preis_berechnet"]
werte = {f.name: stufe10.get(f.name) for f in staffeln.EINSTELLUNG_FELDER if f.name != "meterpreise"}
hand = round(berechnet * 0.5, 2)
st.stufe_speichern(stufe10["id"], werte, staffeln.meterpreise(stufe10),
                   [("10", 10, None, dict(zukauf_ek=None, preis_hand=hand, preis_hand_grund="Zielpreis Kunde"))])
z10 = next(x for x in db.staffeln(a) if x["menge"] == 10)
assert z10["preis_hand"] == hand and z10["preis_hand_grund"] == "Zielpreis Kunde"
assert z10["preis_hand_von"] and z10["preis_hand_am"] and nah(z10["preis_hand_alt"] or 0, berechnet), {n: z10.get(n) for n in staffeln.MENGE_PREIS}
sp = rechnen()
z = next(z for z in sp if z["menge"] == 10)
assert z["preis_einheit"] == hand and z["preis_gesamt"] == ausgabe.kaufm_runden(hand * 10, 2)
assert z["preis"]["unter_mindestmarge"] and z["hinweis"].startswith("WARNUNG: Marge")
assert z["preis"]["marge"] < M
ok(f"Preis von Hand {hand} € (berechnet {berechnet:.2f} €): gespeichert mit Grund, Bearbeiter, Zeit und "
   f"berechnetem Preis; unter der Mindestmarge rote Warnung")

from rohrlaser.staffel_seite import ErgebnisBaum, StufeDialog  # noqa: E402

d = StufeDialog(st, stufe10)
r = next(i for i, (schl, _, _) in enumerate(d.auswahl) if schl == "10")
assert d.mengen.item(r, 5).text() and d.mengen.item(r, 6).text() == "Zielpreis Kunde"
d.mengen.item(r, 6).setText("")
try:
    d.werte()
    raise AssertionError("Preis von Hand ohne Grund muss abgelehnt werden")
except ValueError as e:
    assert "Grund" in str(e)
d.mengen.item(r, 5).setText("")
_, _, mengen = d.werte()
st.stufe_speichern(stufe10["id"], werte, staffeln.meterpreise(stufe10), mengen)
z10 = next(x for x in db.staffeln(a) if x["menge"] == 10)
assert all(z10.get(n) is None for n in staffeln.MENGE_PREIS[1:])
ok("Fenster der Stufe: Preis von Hand nur mit Grund; Feld leeren nimmt Preis und Protokollwerte zurück")

# ------------------------------------------------------------------ 5) Zukauf-Einstand je Staffel, ohne Gewinn
sp = rechnen()
z = next(z for z in sp if z["menge"] == 25)
b = dict(z["bausteine"], zukauf_einstand=40.0, zukauf_aufschlag=4.0)
w = dict(z["wirksam"], zukauf_ek=None, mindestmarge=0)
p1 = staffeln.preise(b, 25, w)
p2 = staffeln.preise(b, 25, dict(w, zukauf_ek=3.0))         # 3 € je Stück statt 40 € für 25 Stück
assert nah(p2["zukauf_einstand"], 75.0) and nah(p2["zukauf_aufschlag"], 4.0 * 75 / 40)
assert nah(p1["gewinn"], p2["gewinn"])                       # kein Gewinn auf Zukauf
assert nah(p2["netto"] - p1["netto"], (75 - 40 + 7.5 - 4) / (1 - p1["skonto_anteil"]))
p3 = staffeln.preise(dict(b, zukauf_fehlt=1), 25, dict(w, zukauf_ek=3.0))
assert not p3["fehler"]
ok("Zukauf-Einstand je Staffel: Aufschlag im selben Verhältnis, Gewinn unverändert (kein Gewinn auf Zukauf); "
   "fehlender EK im Angebot wird durch den EK der Staffel ersetzt")

# ------------------------------------------------------------------ 6) Anzeige je Staffel
baum = ErgebnisBaum()
baum.setzen(sp)
titel = [baum.topLevelItem(i).text(0) for i in range(baum.topLevelItemCount())]
for t in ("Anhebung auf die Mindestmarge", "Deckungsbeitrag (Warenwert − variable Kosten)",
          "Deckungsbeitragsquote", "Einsparung je Einheit gegenüber der kleinsten Menge", "Gewinnmarge (vom Warenwert)"):
    assert t in titel, (t, titel)
ok("Ergebnis je Staffel: Selbstkosten, Verkaufspreis, Deckungsbeitrag, Gewinn, Marge, Einsparung, Anhebung")

fenster.close()
print("OK: Staffeln mit Mindestmarge, Kennzahlen, Rabatt, Preis von Hand und Zukauf-EK")
