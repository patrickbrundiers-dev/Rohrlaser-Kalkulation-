"""U-Profile als Standard, Wandstärke ändern und Rohrart je Abmessung (Patrick 31.10.2026, Freigabe „Alle
Empfehlungen“ = 1a 2a 3a 4b 5a 6a 7a):

1. U-Profile nach DIN 1026-1 von UPN 30x15 bis UPN 200 stehen in den Stammdaten „Profile“ (neue und vorhandene
   Datenbanken, einmal je Stand, eigene Zeilen bleiben); Fläche und Gewicht aus der Normtabelle; 'UNP 100' und
   'U 100' werden wie 'UPN 100' erkannt (Schnellzeile, Profilspalte, Abmessung neu).
2. „Wandstärke ändern …“ (Rechtsklick Position, Material-Fenster): gleiche Form und gleiches Außenmaß, Profil aus den
   Stammdaten oder neu angelegt, für markierte oder alle Positionen der Abmessung; Normprofile nicht.
3. Rohrart je Abmessung im Angebot (Material-Fenster) vor der Rohrart des Werkstoffs; neue Rohrart „Naht innen
   geschabt“ (Naht bleibt), im Text von Materialanfrage, Angebot und Werkstattpapier.

Aufruf: python tests/test_u_profile_wand_rohrart.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import (ausgabe, materialanfrage, naht, normprofile, profil_neu, rechnen, schnellzeile,  # noqa: E402
                       tabellen_eingabe, wand_dialog)
from rohrlaser.datenbank import NORMPROFILE_STAND, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import GESCHABT, ROHRARTEN  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ 1. Normtabelle und Schreibweisen
REIHE = ("UPN 30x15", "UPN 30", "UPN 40x20", "UPN 40", "UPN 50x25", "UPN 50", "UPN 60", "UPN 65", "UPN 80",
         "UPN 100", "UPN 120", "UPN 140", "UPN 160", "UPN 180", "UPN 200")
assert normprofile.STANDARD_STAMMDATEN == REIHE, normprofile.STANDARD_STAMMDATEN
# Gewicht je Meter nach DIN 1026-1 (Stahl 7,85 kg/dm³) auf 0,03 kg/m
for name, kg_m in (("UPN 30x15", 1.74), ("UPN 40x20", 2.87), ("UPN 50x25", 3.86), ("UPN 60", 5.07),
                   ("UPN 100", 10.6), ("UPN 200", 25.3)):
    assert abs(normprofile.daten(name)["flaeche"] * 7.85e-3 - kg_m) < 0.03, name
for text, soll in (("UNP 100", "UPN 100"), ("u100", "UPN 100"), ("U 30 x 15", "UPN 30x15"), ("upn 200", "UPN 200"),
                   ("U 100x50x5", "U 100x50x5"), ("UNP 999", "UNP 999"), ("IPE 200", "IPE 200")):
    assert normprofile.normname(text) == soll, (text, normprofile.normname(text))
assert normprofile.daten("UNP 160")["h"] == 160 and normprofile.daten("U 999") is None
assert normprofile.zuordnen("U-Profil", 30, 15, 4.0, 4.5, 221) == "UPN 30x15", "STEP erkennt auch kleine U-Profile"
assert profil_neu.vorschlag("UNP 120")["profil_id"] == "UPN 120"
namen = ["UPN 100", "UPN 30x15", "QR 40x40x3", "U 100x50x5"]
assert tabellen_eingabe.profil_treffer("unp 100", namen) == ["UPN 100"]
assert tabellen_eingabe.profil_aufloesen("U 100", namen) == "UPN 100"
z = schnellzeile.zeile_lesen("UNP 100 S235 1250 20", namen, ["S235JR"])
assert (z["profil_id"], z["laenge"], z["stueck"]) == ("UPN 100", 1250, 20), z
z = schnellzeile.zeile_lesen("U 30 x 15 S235 800 4", namen, ["S235JR"])
assert (z["profil_id"], z["laenge"], z["stueck"]) == ("UPN 30x15", 800, 4), z
z = schnellzeile.zeile_lesen("U 100x50x5 S235 500 2", namen, ["S235JR"])
assert z["profil_id"] == "U 100x50x5" and z["laenge"] == 500, z
ok("Normtabelle UPN 30x15 bis 200 nach DIN 1026-1, 'UNP'/'U' wie 'UPN' (Schnellzeile, Profilspalte, Vorschlag)")

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
for name in REIHE:
    p = k.profile[name]
    n = normprofile.daten(name)
    assert (p["form"], p["a"], p["b"], p["wand"], p["wand_max"], p["flaeche_manuell"]) == \
        ("U-Profil", n["h"], n["b"], n["tw"], n["tf"], n["flaeche"]), (name, p)
assert not any(z["profil_id"] in REIHE for z in db.zeilen("preise")), "kein Materialpreis geraten"
assert "UPN 220" not in k.profile and db.einstellung("normprofile_stand") == NORMPROFILE_STAND
ok("neue Datenbank: 15 U-Profile in den Stammdaten mit Steg, Flansch und Normfläche, ohne Preis")

# vorhandene Datenbank: eigene Zeile (auch 'UNP 100') bleibt, gelöschte kommen erst mit neuem Stand wieder
db.con.execute("DELETE FROM profile WHERE profil_id IN ('UPN 100', 'UPN 120')")
db.con.execute("INSERT INTO profile (profil_id, form, a, b, wand) VALUES ('UNP 100', 'U-Profil', 100, 50, 6)")
db.con.execute("UPDATE profile SET bemerkung='eigen' WHERE profil_id='UPN 80'")
db.con.commit()
db.schliessen() if hasattr(db, "schliessen") else db.con.close()
db = Datenbank(tmp / "rohrlaser.db")
ids = {z["profil_id"]: z for z in db.zeilen("profile")}
assert "UPN 100" not in ids and "UPN 120" not in ids and ids["UPN 80"]["bemerkung"] == "eigen"
con = sqlite3.connect(tmp / "rohrlaser.db")
con.execute("UPDATE einstellungen SET wert=? WHERE name='normprofile_stand'", ('"alt"',))
con.commit()
con.close()
db.con.close()
db = Datenbank(tmp / "rohrlaser.db")
ids = {z["profil_id"]: z for z in db.zeilen("profile")}
assert "UPN 120" in ids and "UPN 100" not in ids and "UNP 100" in ids and ids["UPN 80"]["bemerkung"] == "eigen", \
    "neuer Stand ergänzt, 'UNP 100' zählt als UPN 100, eigene Zeile bleibt"
ok("vorhandene Datenbank: einmal je Stand ergänzt, eigene Zeilen und andere Schreibweise bleiben")

# ------------------------------------------------------------------ 2. Wandstärke ändern
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
f.show()
k = db.kontext()
werkstoff = "S235-10219" if "S235-10219" in k.werkstoffe else next(iter(k.werkstoffe))
aid = db.angebot_neu(dict(kunde="Test"))
for i, (pid, laenge) in enumerate((("QR 40x40x3", 1000), ("QR 40x40x3", 800), ("RE 60x40x3", 500),
                                   ("UPN 80", 700))):
    db.position_neu(aid, dict(pos=10 * (i + 1), profil_id=pid, laenge=laenge, stueck=2, werkstoff_id=werkstoff))
s = f.angebot_oeffnen(aid)
assert "Wandstärke ändern …" in s.pos_aktionen
q = dict(k.profile["QR 40x40x3"], profil_id="QR 40x40x3")
assert wand_dialog.aenderbar("UPN 80", k.profile["UPN 80"]).startswith("UPN 80 ist ein Normprofil")
assert wand_dialog.aenderbar("QR 40x40x3", q) == ""
assert wand_dialog.gleiche_aussenmasse(q, k.profile) == [(3.0, "QR 40x40x3")]
assert wand_dialog.ziel_profil(q, 3.0, k.profile) == ("QR 40x40x3", None)
pid_neu, zeile = wand_dialog.ziel_profil(q, 4.0, k.profile)
assert pid_neu == "QR 40x40x4" and zeile["wand"] == 4.0 and zeile["a"] == 40 and zeile.get("flaeche_manuell") is None

gesehen = {}


def waehlen(d):
    gesehen["liste"] = [d.auswahl.itemText(i) for i in range(d.auswahl.count())]
    gesehen["knoepfe"] = (d.nur.text(), d.alle_knopf.text())
    d.auswahl.setCurrentText("3")
    d.annehmen()
    gesehen["gleich"] = d.fehler.text()
    d.auswahl.setCurrentText("25")
    d.annehmen()
    gesehen["zu_dick"] = d.fehler.text()
    d.auswahl.setCurrentText("4")
    d.annehmen()
    return d.result()


assert s.wand_aendern(zeilen=[0], dialog=waehlen) == 1
assert gesehen["liste"] == ["3 mm  –  QR 40x40x3"] and "(1)" in gesehen["knoepfe"][0] and "(2)" in gesehen["knoepfe"][1]
assert "schon die Wandstärke" in gesehen["gleich"] and "halbe" in gesehen["zu_dick"], gesehen
pos = db.positionen(aid)
assert [p["profil_id"] for p in pos] == ["QR 40x40x4", "QR 40x40x3", "RE 60x40x3", "UPN 80"], pos
neu = next(z for z in db.zeilen("profile") if z["profil_id"] == "QR 40x40x4")
assert (neu["form"], neu["a"], neu["wand"]) == ("Quadratrohr", 40, 4) and "QR 40x40x3" in neu["bemerkung"]
w3 = rechnen.position_werte(pos[1], s.kopf, s.k, s.tabellen)
w4 = rechnen.position_werte(pos[0], s.kopf, s.k, s.tabellen)
assert w4["kg_m"] > w3["kg_m"] * 1.2, (w3["kg_m"], w4["kg_m"])
assert "Wandstärke 4 mm" in f.verlauf.eintraege[0][1] and "Materialpreis fehlt" in f.verlauf.eintraege[0][1]
ok("Wandstärke ändern: markierte Position auf QR 40x40x4, Profil neu angelegt, Gewicht rechnet neu")

# alle Positionen der Abmessung, Wandstärke aus den Stammdaten (jetzt 3 und 4 mm zur Wahl)
assert s.wand_aendern(zeilen=[1], wand=4, alle=True) == 1
assert [p["profil_id"] for p in db.positionen(aid)][:2] == ["QR 40x40x4", "QR 40x40x4"]
assert s.wand_aendern(zeilen=[0], wand=3, alle=True) == 2
assert [p["profil_id"] for p in db.positionen(aid)][:2] == ["QR 40x40x3", "QR 40x40x3"]
assert sum(z["profil_id"] == "QR 40x40x4" for z in db.zeilen("profile")) == 1, "kein zweites Profil"
assert s.wand_aendern(zeilen=[3], wand=6) is None and "Normprofil" in f.verlauf.eintraege[0][1]
assert s.wand_aendern(zeilen=[0, 2], wand=4) is None, "zwei Abmessungen markiert"
ok("Wandstärke ändern: alle Positionen der Abmessung, vorhandenes Profil, Normprofil und zwei Abmessungen abgelehnt")

# Material-Fenster: Eintrag im Kontextmenü, nach dem Schließen alle Positionen der Abmessung
gesehen = {}


def material(d):
    r = next(i for i, g in enumerate(d.gruppen) if g["profil"] == "RE 60x40x3")
    eintraege = {t: a for t, _, a in d.menue_eintraege(r) if t}
    gesehen["aktiv"] = eintraege["Wandstärke ändern …"]
    gesehen["upn"] = next(a for i, g in enumerate(d.gruppen) if g["profil"] == "UPN 80"
                          for t, _, a in d.menue_eintraege(i) if t == "Wandstärke ändern …")
    gesehen["rohrart_upn"] = next(d.rohrarten[i] for i, g in enumerate(d.gruppen) if g["profil"] == "UPN 80")
    d.schliessen_mit("wand", d.gruppen[r])
    return d.result()


echt = s.wand_aendern
s.wand_aendern = lambda **kw: gesehen.setdefault("nachher", kw)     # das Fenster danach nicht zeigen
s.material_einstellen(dialog=material)
s.wand_aendern = echt
assert sorted(gesehen["nachher"]["ids"]) == sorted(p["id"] for p in db.positionen(aid) if p["profil_id"] == "RE 60x40x3")
assert gesehen["aktiv"] and not gesehen["upn"] and gesehen["rohrart_upn"] is None
ok("Material-Fenster: „Wandstärke ändern …“ je Abmessung (nicht bei Normprofilen), Rohrart nur bei Hohlprofilen")
re_ids = [p["id"] for p in db.positionen(aid) if p["profil_id"] == "RE 60x40x3"]
assert s.wand_aendern(ids=re_ids, wand=2.5) == 1
assert db.positionen(aid)[2]["profil_id"] == "RE 60x40x2,5", db.positionen(aid)[2]["profil_id"]
ok("Material-Fenster: Wandstärke für alle Positionen der Abmessung (RE 60x40x2,5)")

# ------------------------------------------------------------------ 3. Rohrart je Abmessung
assert GESCHABT == "Naht innen geschabt" and GESCHABT in ROHRARTEN
gruppe = naht.gruppe_schluessel("QR 40x40x3", werkstoff)
gesehen = {}


def rohrart(d):
    r = next(i for i, g in enumerate(d.gruppen) if g["profil"] == "QR 40x40x3")
    ra = d.rohrarten[r]
    gesehen["eintraege"] = [ra.itemText(i) for i in range(ra.count())]
    ra.setCurrentIndex(ra.findData("nahtlos"))
    d.annehmen()
    return d.result()


assert s.material_einstellen(dialog=rohrart) == 1
assert gesehen["eintraege"][0].startswith("wie Werkstoff (") and gesehen["eintraege"][1:] == list(ROHRARTEN)
assert db.angebot(aid)["rohrarten"] == {gruppe: "nahtlos"} and s.kopf["rohrarten"] == {gruppe: "nahtlos"}
p0 = db.positionen(aid)[0]
assert rechnen.rohrart(werkstoff, s.k, s.kopf, "QR 40x40x3") == "nahtlos"
assert rechnen.ohne_naht(werkstoff, s.k, s.kopf, "QR 40x40x3") and not rechnen.ohne_naht(werkstoff, s.k)
assert rechnen.naht_wirksam(dict(p0, naht_vorgabe=naht.FEST), s.k, s.kopf) == naht.KEINE
assert rechnen.naht_wirksam(dict(p0, naht_vorgabe=naht.FEST), s.k) == naht.FEST
assert "Rohr nahtlos" in ausgabe.angebotstext(p0, s.k, kopf=s.kopf).splitlines()
assert "Rohr nahtlos" not in ausgabe.angebotstext(p0, s.k)
assert materialanfrage.anforderungen(werkstoff, s.k, "nahtlos").endswith("nahtlos")
assert "bitte neu optimieren" in f.verlauf.eintraege[0][1] or "neu optimieren" in str(f.verlauf.eintraege[:3])
ok("Rohrart nahtlos je Abmessung: gespeichert, Naht entfällt nur in diesem Angebot, Text im Angebot")

# Naht innen geschabt: Naht bleibt, Text in Angebot, Anfrage und Werkstattpapier
s.kopf["rohrarten"] = {gruppe: GESCHABT}
db.rohrarten_speichern(aid, s.kopf["rohrarten"])
assert not rechnen.ohne_naht(werkstoff, s.k, s.kopf, "QR 40x40x3")
assert rechnen.naht_wirksam(dict(p0, naht_vorgabe=naht.FEST), s.k, s.kopf) == naht.FEST
assert GESCHABT in ausgabe.angebotstext(p0, s.k, kopf=s.kopf).splitlines()
assert materialanfrage.anforderungen(werkstoff, s.k, GESCHABT).endswith(GESCHABT)
assert ausgabe.rohrart_text(db.positionen(aid)[3], s.k, s.kopf) == "", "U-Profil: keine Rohrart"
s.optimieren() if hasattr(s, "optimieren") else None
if s.ergebnis and s.ergebnis.get("stangen"):
    wp = ausgabe.werkstatt(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)
    assert any(m["profil"] == "QR 40x40x3" and m["werkstoff"].endswith(GESCHABT) for m in wp["material"]), \
        wp["material"]
    zeilen = materialanfrage.bedarf(s.positionen, s.ergebnis, s.k, s.tabellen, None, s.kopf)
    assert any(z["profil"] == "QR 40x40x3" and GESCHABT in z["anforderungen"] for z in zeilen), zeilen
    ok("Werkstattpapier und Materialanfrage nennen „Naht innen geschabt“")
# Kopie des Angebots behält die Rohrart
if hasattr(db, "angebot_kopieren"):
    neu_id = db.angebot_kopieren(aid)
    neu_id = neu_id[0] if isinstance(neu_id, tuple) else neu_id
    assert db.angebot(neu_id)["rohrarten"] == {gruppe: GESCHABT}
# zurück auf „wie Werkstoff“
s.kopf["rohrarten"] = {gruppe: GESCHABT}


def zurueck(d):
    r = next(i for i, g in enumerate(d.gruppen) if g["profil"] == "QR 40x40x3")
    d.rohrarten[r].setCurrentIndex(0)
    d.annehmen()
    return d.result()


assert s.material_einstellen(dialog=zurueck) == 1 and not db.angebot(aid)["rohrarten"]
ok("Naht innen geschabt: Naht bleibt, Angebotstext und Anfrage nennen es; „wie Werkstoff“ nimmt es zurück")
print("Alle Prüfungen bestanden.")
