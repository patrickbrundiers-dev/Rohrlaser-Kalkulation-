"""Regelbasierte Arbeitsgang-Vorschläge (Wettbewerbsvergleich P1-4, arbeitsgaenge.py): Rohrteil mit Gewinde und
Verzinkung laut Bezeichnung, Zukaufteil; keine doppelten Arbeitsgänge, Summen stimmen mit der Rechnung überein,
unbestätigte Vorschläge kosten nichts, Ablehnen bleibt gespeichert, alte Dateien bekommen die Beispielregeln.

Aufruf: python tests/test_arbeitsgaenge.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import arbeitsgaenge as ag, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
regeln = db.zeilen("arbeitsgang_regeln")
assert {r["name"] for r in regeln} >= {"Verzinkt laut Bezeichnung", "Pulver laut Bezeichnung"}
fenster = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db)
pos = db.positionen(aid)
rohr = next(p for p in pos if p.get("profil_id") and p.get("art") != "Zukaufteil")
db.position_aendern(rohr["id"], "bezeichnung", "Riegel feuerverzinkt")
db.position_aendern(rohr["id"], "gewinde", "2xM6")
zk = db.position_neu(aid, dict(art="Zukaufteil", artikel="ZK-1", bezeichnung="Scharnier verzinkt", stueck=4))
s = fenster.angebot_oeffnen(aid)
kosten_vorher = s._rechnung()

# ------------------------------------------------------------------ Übersicht
z = s.arbeitsgaenge_zeilen()
von = [x for x in z if x["position_id"] == rohr["id"]]
namen = [(x["arbeitsgang"], x["status"]) for x in von]
assert ("Laser schneiden", ag.IM_ANGEBOT) in namen and ("Gewinde M6", ag.IM_ANGEBOT) in namen, namen
fvz = [x for x in von if x["arbeitsgang"] == "Feuerverzinken"]
assert len(fvz) == 1 and fvz[0]["status"] == ag.VORSCHLAG and fvz[0]["kostenart"] == ag.FREMD
assert fvz[0]["betrag"] > 0 and fvz[0]["herkunft"] == "Regel: Verzinkt laut Bezeichnung"
g = next(x for x in von if x["arbeitsgang"] == "Gewinde M6")
m6 = next(x for x in db.zeilen("gewinde") if x["gewinde"] == "M6")
assert g["menge"] == 2 and abs(g["betrag"] - 2 * m6["preis"]) < 1e-9
# Zukaufteil: Zukauf im Angebot; Regel 'Stahl' trifft ohne Werkstoff nicht (Bedingung Kategorie)
vz = [x for x in z if x["position_id"] == zk]
assert [(x["arbeitsgang"], x["kostenart"]) for x in vz] == [("Zukaufteil", ag.ZUKAUF)], vz
# unbestätigt: Preis unverändert
assert s._rechnung() == kosten_vorher

# zwei Regeln für dieselbe Zusatzarbeit: ein Vorschlag mit beiden Regeln als Herkunft
db.neu("arbeitsgang_regeln", dict(name="FVZ Kunde", zusatzarbeit="Feuerverzinken", stichwort="riegel", aktiv="ja"))
z = s.arbeitsgaenge_zeilen()
fvz = [x for x in z if x["position_id"] == rohr["id"] and x["arbeitsgang"] == "Feuerverzinken"]
assert len(fvz) == 1 and len(fvz[0]["regeln"]) == 2, fvz

# ------------------------------------------------------------------ Annehmen: genau einmal gerechnet
dlg = s.arbeitsgaenge_vorschlagen(dialog=lambda d: None)
dlg.waehlen(rohr["id"], "Feuerverzinken")
assert dlg.annehmen_knopf.isEnabled()
assert dlg.ausfuehren("annehmen")
p = next(x for x in db.positionen(aid) if x["id"] == rohr["id"])
liste = rechnen.zusatz_liste(p)
assert [e["name"] for e in liste].count("Feuerverzinken") == 1 and liste[-1]["quelle"].startswith("Regel: ")
assert isinstance(liste[-1]["stand"], dict)
assert not s.arbeitsgang_annehmen(rohr["id"], "Feuerverzinken")          # nie doppelt
z = s.arbeitsgaenge_zeilen()
fvz = [x for x in z if x["position_id"] == rohr["id"] and x["arbeitsgang"] == "Feuerverzinken"]
assert len(fvz) == 1 and fvz[0]["status"] == ag.IM_ANGEBOT
kosten_nach = s._rechnung()
assert kosten_nach != kosten_vorher
# Summe der Übersicht = Zusatzarbeiten und Gewinde der Rechnung je Teil
werte = rechnen.zusatz_werte(p, s.k, s.tabellen)
summe_z = sum(x["betrag"] + x["pauschal"] for x in werte)
uebers = sum(x["betrag"] for x in z if x["position_id"] == rohr["id"] and x["status"] == ag.IM_ANGEBOT
             and x["betrag"] is not None and not x["arbeitsgang"].startswith("Gewinde"))
assert abs(summe_z - uebers) < 1e-9
assert abs(sum(x["betrag"] for x in z if x["position_id"] == rohr["id"] and x["arbeitsgang"].startswith("Gewinde"))
           - rechnen.gewinde_preis(p["gewinde"], db.zeilen("gewinde"))) < 1e-9

# ------------------------------------------------------------------ Ablehnen und zurücknehmen
db.position_aendern(rohr["id"], "bezeichnung", "Riegel verzinkt pulverbeschichtet RAL 7016")
s.neu_laden()
dlg.laden()
dlg.waehlen(rohr["id"], "Pulverbeschichten")
assert dlg.ausfuehren("ablehnen")
p = next(x for x in db.positionen(aid) if x["id"] == rohr["id"])
assert ag.lesen(p)["abgelehnt"] == ["Pulverbeschichten"]
assert next(x for x in dlg.zeilen if x["arbeitsgang"] == "Pulverbeschichten")["status"] == ag.ABGELEHNT
assert s._rechnung() == kosten_nach                                       # abgelehnt kostet nichts
db.schliessen()
db = Datenbank(tmp / "rohrlaser.db")                                      # bleibt nach erneutem Öffnen
p = next(x for x in db.positionen(aid) if x["id"] == rohr["id"])
assert ag.lesen(p)["abgelehnt"] == ["Pulverbeschichten"]
assert ag.lesen(dict(arbeitsgaenge="kaputt"))["abgelehnt"] == []
assert json.loads(ag.ablehnen(p, "Pulverbeschichten", zurueck=True) or "{}").get("abgelehnt", []) == []

# Bedingungen: Kunde, Stückzahl, Merkmal, inaktiv, unbekannte Zusatzarbeit
k = db.kontext()
basis = dict(profil_id=rohr["profil_id"], werkstoff_id=rohr["werkstoff_id"], stueck=10, bezeichnung="x",
             gewinde="", klein_n=2)
r = dict(name="R", zusatzarbeit="Entgraten", aktiv="ja")
assert ag.trifft(r, basis, {}, k, [])
assert not ag.trifft(dict(r, aktiv="nein"), basis, {}, k, [])
assert not ag.trifft(dict(r, kundennr="K-1001"), basis, dict(kundennr="K-1002"), k, [])
assert ag.trifft(dict(r, kundennr="K-1001"), basis, dict(kundennr="K-1001"), k, [])
assert not ag.trifft(dict(r, min_stueck=11), basis, {}, k, []) and ag.trifft(dict(r, min_stueck=10), basis, {}, k, [])
assert ag.trifft(dict(r, merkmal="Innenkonturen"), basis, {}, k, [])
assert not ag.trifft(dict(r, merkmal="Gewinde"), basis, {}, k, [])
assert ag.regel_menge(dict(menge_art="Anzahl Innenkonturen"), basis, []) == 2
tab = db.tabellen()
# zwei Regeln für dieselbe Zusatzarbeit, nur die zweite trifft: Annehmen nimmt Menge und Herkunft der zutreffenden
rs = [dict(name="R1", zusatzarbeit="Entgraten", aktiv="ja", min_stueck=99999, menge_art="Anzahl Gewinde"),
      dict(name="R2", zusatzarbeit="Entgraten", aktiv="ja", menge_art="automatisch")]
e = json.loads(ag.annehmen(basis, "Entgraten", rs, tab, {}, k))[-1]
assert e["menge"] is None and e["quelle"] == "Regel: R2", e
assert not [x for x in ag.position(basis, {}, k, tab, [dict(r, zusatzarbeit="Gibt es nicht")])
            if x["status"] == ag.VORSCHLAG]

db.schliessen()

# ------------------------------------------------------------------ alte Datei (Schema 64) bekommt die Beispielregeln
alt = tmp / "alt.db"
Datenbank(alt).schliessen()
con = sqlite3.connect(alt)
con.execute("DELETE FROM arbeitsgang_regeln")
con.execute("PRAGMA user_version=64")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.anzahl("arbeitsgang_regeln") == 3
db2.schliessen()
print("test_arbeitsgaenge OK")
