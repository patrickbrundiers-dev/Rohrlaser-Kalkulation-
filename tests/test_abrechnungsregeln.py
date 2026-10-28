"""Eigene Abrechnungsregeln für Zusatzarbeiten (Plan 28.10.2026, Freigabe alle a, zusatz_regeln.py): Strahlen €/kg
vorbelegt, Preis je Werkstoff über Regeln (genaueste gewinnt), Mindestbetrag je Teil, Menge aus Innen- + Außenfläche
und Faktor, automatische Zuordnung (gerechnet, abwählbar, in Arbeitsgänge und Unterzeilen), Gewinde/Senken/Flowdrill/
Bohren nur € je Stück, Oberflächen-Aufpreis €/kg, alte Preisstände und festgeschriebene Angebote unverändert.

Aufruf: python tests/test_abrechnungsregeln.py
"""
import json
import math
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
from rohrlaser import arbeitsgaenge as ag, rechnen, unterzeilen, zusatz_regeln as zr  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import ZUSATZ_STRAHLEN, pruefen, TABELLE  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")


def ok(text):
    print("OK  ", text)


# ------------------------------------------------------------------ 1 Stammdaten: Strahlen €/kg, Beispielregeln aus
strahlen = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == ZUSATZ_STRAHLEN)
assert strahlen["art"] == "€/kg" and strahlen["fremd"] == "ja" and strahlen["kategorie"] == "Oberfläche"
beispiele = [r for r in db.zeilen("arbeitsgang_regeln") if r["zusatzarbeit"] == ZUSATZ_STRAHLEN]
assert len(beispiele) == 3 and all(r["aktiv"] == "nein" for r in beispiele)
ok("1  Strahlen €/kg vorbelegt, drei Beispielregeln (aus)")

fenster = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db)
rohr = next(p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil")
s = fenster.angebot_oeffnen(aid)
k, tab = s.k, s.tabellen
p = next(x for x in s.positionen if x["id"] == rohr["id"])
kg = rechnen.zusatz_menge_auto("€/kg", p, k)
assert kg and kg > 0
stand = rechnen.zusatz_stand(strahlen, rechnen.stundensaetze(tab))
assert stand["regeln"] == "ja"


def mit(p, *eintraege, **w):
    return dict(p, zusatz=json.dumps(list(eintraege), ensure_ascii=False), **w)


e_neu = dict(name=ZUSATZ_STRAHLEN, menge=None, preis=None, text=None, stand=stand)
e_alt = dict(e_neu, stand={x: y for x, y in stand.items() if x != "regeln"})      # Preisstand vor 28.10.2026
z = rechnen.zusatz_werte(mit(p, e_neu), k, tab)[0]
assert abs(z["menge"] - kg) < 1e-9 and abs(z["betrag"] - kg * 0.40) < 1e-9 and z["regel"] is None
ok(f"2  Strahlen ohne Regel: {kg:.3f} kg × 0,40 € = {z['betrag']:.2f} € je Teil")

# ------------------------------------------------------------------ 3 Preisregeln: Werkstoff, genaueste gewinnt
kat = rechnen.kategorie(p["werkstoff_id"], k)
regeln = [dict(name="alle", zusatzarbeit=ZUSATZ_STRAHLEN, zuordnung="nur Preis", aktiv="ja", preis=0.50, art="€/kg"),
          dict(name="Kategorie", zusatzarbeit=ZUSATZ_STRAHLEN, zuordnung="nur Preis", aktiv="ja", kategorie=kat,
               preis=0.35, art="€/kg", mindest_teil=999.0),
          dict(name="andere", zusatzarbeit=ZUSATZ_STRAHLEN, zuordnung="nur Preis", aktiv="ja", kategorie="Gibt es nicht",
               preis=9.0)]
t2 = dict(tab, arbeitsgang_regeln=regeln)
z = rechnen.zusatz_werte(mit(p, e_neu), k, t2)[0]
assert z["regel"] == "Kategorie" and z["preis"] == 0.35 and z["betrag"] == 999.0, z     # Mindestbetrag je Teil
z = rechnen.zusatz_werte(mit(p, e_neu), k, dict(t2, arbeitsgang_regeln=[regeln[0], dict(regeln[1], mindest_teil=None)]))[0]
assert z["regel"] == "Kategorie" and abs(z["betrag"] - kg * 0.35) < 1e-9
assert zr.beste([dict(name="a"), dict(name="b")])["name"] == "a"                      # Gleichstand: die obere
z_alt = rechnen.zusatz_werte(mit(p, e_alt), k, t2)[0]
assert z_alt["regel"] is None and abs(z_alt["betrag"] - kg * 0.40) < 1e-9             # alter Preisstand: ohne Regeln
z = rechnen.zusatz_werte(mit(p, dict(e_neu, preis=0.77)), k, t2)[0]
assert z["preis"] == 0.77                                                             # von Hand geht vor
ok("3  genaueste Regel gewinnt, Mindestbetrag je Teil, alte Preisstände und Preis von Hand unverändert")

# ------------------------------------------------------------------ 4 Menge aus Innen- + Außenfläche, Faktor
pr = k.profile[p["profil_id"]]
aussen = rechnen.oberflaeche(p, k)
beide = rechnen.flaeche_innen_aussen(p, k)
if pr["form"] == "Rundrohr":
    erwartet = aussen * (2 * pr["a"] - 2 * pr["wand"]) / pr["a"]
else:
    a, b = pr["a"], pr.get("b") or pr["a"]
    erwartet = aussen * (4 * (a + b) - 8 * pr["wand"]) / (2 * (a + b))
assert abs(beide - erwartet) < 1e-9 and beide > aussen
r_fl = dict(name="Fläche", zusatzarbeit=ZUSATZ_STRAHLEN, zuordnung="nur Preis", aktiv="ja", art="€/m²", preis=6.0,
            menge_art="Innen- + Außenfläche", faktor=1.05)
z = rechnen.zusatz_werte(mit(p, e_neu), k, dict(tab, arbeitsgang_regeln=[r_fl]))[0]
assert z["art"] == "€/m²" and z["einheit"] == "m²" and abs(z["menge"] - beide * 1.05) < 1e-9
assert abs(z["betrag"] - beide * 1.05 * 6.0) < 1e-9
# Zusatzarbeit selbst mit Menge aus und Faktor (ohne Regel)
kat_z = dict(strahlen, bezug=None, faktor=1.1)
z = rechnen.zusatz_werte(mit(p, dict(e_neu, stand=rechnen.zusatz_stand(kat_z))), k, tab)[0]
assert abs(z["menge"] - kg * 1.1) < 1e-9
ok(f"4  Innen- + Außenfläche {beide:.4f} m² (außen {aussen:.4f}), Faktor 1,05 bzw. 1,1")

# ------------------------------------------------------------------ 5 Gewinde/Senken/Flowdrill/Bohren nur € je Stück
senken = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Senken")
r_s = dict(name="S", zusatzarbeit="Senken", zuordnung="nur Preis", aktiv="ja", art="€/kg", preis=3.0)
z = rechnen.zusatz_werte(mit(p, dict(name="Senken", menge=None, preis=None, text=None,
                                     stand=rechnen.zusatz_stand(senken))), k, dict(tab, arbeitsgang_regeln=[r_s]))[0]
assert z["art"] == "€/Stück" and z["menge"] == 1.0 and z["preis"] == 3.0
assert pruefen(TABELLE["arbeitsgang_regeln"], r_s, k).startswith("FEHLER")
assert pruefen(TABELLE["zusatzarbeiten"], dict(senken, art="€/kg"), k).startswith("FEHLER")
assert zr.nur_stueck("Bohren") and zr.nur_stueck("flowdrill") and not zr.nur_stueck("Strahlen")
ok("5  Senken bleibt € je Stück trotz Regel €/kg (Prüfung FEHLER)")

# ------------------------------------------------------------------ 6 automatisch zuordnen
vorher = s._rechnung()
r_auto = db.zeilen("arbeitsgang_regeln")
auto = next(r for r in r_auto if r["name"] == "Strahlen laut Bezeichnung")
db.aendern("arbeitsgang_regeln", auto["id"], "aktiv", "ja")
db.position_aendern(rohr["id"], "bezeichnung", "Riegel gestrahlt")
s.neu_laden()
p = next(x for x in s.positionen if x["id"] == rohr["id"])
werte = rechnen.zusatz_werte(p, s.k, s.tabellen, s.kopf)
a = [x for x in werte if x["name"] == ZUSATZ_STRAHLEN]
assert len(a) == 1 and a[0]["auto"] and a[0]["regel"] == "Strahlen laut Bezeichnung", werte
nachher = s._rechnung()
assert nachher[1]["verkauf"] > vorher[1]["verkauf"]
zeile = nachher[0][next(i for i, x in enumerate(s.positionen) if x["id"] == rohr["id"])]
texte = unterzeilen.schritte(p, zeile, s.tabellen.get("zusatzarbeiten"))
st = next((t, w) for t, w in texte if t.startswith(ZUSATZ_STRAHLEN))
assert "automatisch" in st[0] and st[1] == unterzeilen.AUTO, texte                     # gelb markiert
z_ag = [x for x in s.arbeitsgaenge_zeilen() if x["position_id"] == rohr["id"] and x["arbeitsgang"] == ZUSATZ_STRAHLEN]
assert len(z_ag) == 1 and z_ag[0]["status"] == ag.AUTOMATISCH
assert s.pos_modell._zusatz_auto(p) == "Strahlen (automatisch)"
dlg = s.arbeitsgaenge_vorschlagen(dialog=lambda d: None)
dlg.waehlen(rohr["id"], ZUSATZ_STRAHLEN)
assert dlg.ablehnen_knopf.isEnabled() and dlg.ablehnen_knopf.text() == "Abwählen"
assert dlg.ausfuehren("ablehnen")
p = next(x for x in s.positionen if x["id"] == rohr["id"])
assert not [x for x in rechnen.zusatz_werte(p, s.k, s.tabellen, s.kopf) if x["name"] == ZUSATZ_STRAHLEN]
assert abs(s._rechnung()[1]["verkauf"] - vorher[1]["verkauf"]) < 1e-6                                  # abgewählt kostet nichts
z_ag = [x for x in s.arbeitsgaenge_zeilen() if x["position_id"] == rohr["id"] and x["arbeitsgang"] == ZUSATZ_STRAHLEN]
assert len(z_ag) == 1 and z_ag[0]["status"] == ag.ABGELEHNT
assert s.arbeitsgang_ablehnen(rohr["id"], ZUSATZ_STRAHLEN, zurueck=True)
assert s.arbeitsgang_annehmen(rohr["id"], ZUSATZ_STRAHLEN)                          # fest übernehmen: einmal
p = next(x for x in s.positionen if x["id"] == rohr["id"])
w = [x for x in rechnen.zusatz_werte(p, s.k, s.tabellen, s.kopf) if x["name"] == ZUSATZ_STRAHLEN]
assert len(w) == 1 and not w[0]["auto"]
assert abs(s._rechnung()[1]["verkauf"] - nachher[1]["verkauf"]) < 1e-6
ok("6  automatisch: gerechnet, gelb in Unterzeilen und Positionsliste, abwählen kostet nichts, Annehmen einmal")

# ------------------------------------------------------------------ 7 Oberflächen-Aufpreis €/kg
ob = next(z for z in db.zeilen("oberflaechen") if z["oberflaeche"] == "gestrahlt")
kgm = rechnen.kg_je_m(p["profil_id"], p["werkstoff_id"], s.k)
assert rechnen.oberflaeche_aufpreis_m("gestrahlt", p["profil_id"], p["werkstoff_id"], s.k) == ob["aufpreis_m"]
db.aendern("oberflaechen", ob["id"], "aufpreis_m", 0.30)
db.aendern("oberflaechen", ob["id"], "aufpreis_basis", "€/kg")
k2 = db.kontext()
assert abs(rechnen.oberflaeche_aufpreis_m("gestrahlt", p["profil_id"], p["werkstoff_id"], k2) - 0.30 * kgm) < 1e-9
db.aendern("oberflaechen", ob["id"], "aufpreis_m", 10.0)
db.aendern("oberflaechen", ob["id"], "aufpreis_basis", "€/m²")
k2 = db.kontext()
u = rechnen.oberflaeche(dict(p, laenge=1000), k2)
assert abs(rechnen.oberflaeche_aufpreis_m("gestrahlt", p["profil_id"], p["werkstoff_id"], k2) - 10.0 * u) < 1e-9
ok(f"7  Oberfläche gestrahlt: 0,30 €/kg × {kgm:.3f} kg/m bzw. 10 €/m² × {u:.4f} m²/m")

# ------------------------------------------------------------------ 8 festgeschrieben: Regeln eingefroren, alt ohne
pb = rechnen.preisbasis_aus(s.kopf, s.positionen, s.k, s.tabellen)
assert [r["name"] for r in pb["zusatz_regeln"]["regeln"]] == ["Strahlen laut Bezeichnung"]
assert ZUSATZ_STRAHLEN in pb["zusatz_regeln"]["staende"] and "aufpreis_basen" in pb
_, t_fest = rechnen.preisbasis_anwenden(dict(s.kopf, preisbasis=pb), s.k, dict(s.tabellen, arbeitsgang_regeln=[]))
assert [r["name"] for r in t_fest["arbeitsgang_regeln"]] == ["Strahlen laut Bezeichnung"]
alt = {x: y for x, y in pb.items() if x not in ("zusatz_regeln", "aufpreis_basen")}
alt["aufpreise"] = {"gestrahlt": 1.5}                       # Angebot mit gestrahltem Rohr, vor dem 28.10.
k_alt, t_alt = rechnen.preisbasis_anwenden(dict(s.kopf, preisbasis=alt), k2, s.tabellen)
assert t_alt["arbeitsgang_regeln"] == [] and k_alt.oberflaechen["gestrahlt"]["aufpreis_basis"] == "€/m"
assert rechnen.preisbasis_gleich(pb, rechnen.preisbasis_aus(s.kopf, s.positionen, s.k, s.tabellen, datum="2030-01-01"))
assert any("Regeln der Zusatzarbeiten" in t for t in rechnen.preisbasis_abweichung(
    dict(s.kopf, preisbasis=pb), s.k, dict(s.tabellen, arbeitsgang_regeln=[])))
ok("8  festgeschrieben: Regeln und Preisstand im Angebot, vor dem 28.10.2026 ohne Regeln und Aufpreis €/m")

# ------------------------------------------------------------------ 9 alte Datei bekommt Strahlen und Beispielregeln
db.schliessen()
alt_db = tmp / "alt.db"
Datenbank(alt_db).schliessen()
con = sqlite3.connect(alt_db)
con.execute("DELETE FROM zusatzarbeiten WHERE name=?", (ZUSATZ_STRAHLEN,))
con.execute("DELETE FROM arbeitsgang_regeln WHERE zusatzarbeit=?", (ZUSATZ_STRAHLEN,))
con.execute("DELETE FROM einstellungen WHERE name='strahlen_stand'")
con.commit()
con.close()
db2 = Datenbank(alt_db)
assert any(z["name"] == ZUSATZ_STRAHLEN for z in db2.zeilen("zusatzarbeiten"))
assert len([r for r in db2.zeilen("arbeitsgang_regeln") if r["zusatzarbeit"] == ZUSATZ_STRAHLEN]) == 3
db2.schliessen()
assert math.isfinite(kg)
ok("9  ältere Datendatei: Strahlen und Beispielregeln ergänzt (nur hinzugefügt, Regeln aus)")
print("test_abrechnungsregeln OK")
