"""Prüft festgeschriebene Materialpreise und Schneiddaten je Angebot (Schema 18): Snapshot beim Angebots-PDF,
spätere Stammdatenänderungen ändern den Preis des Angebots nicht, Hinweis auf Abweichungen, 'Aktuelle Preise
übernehmen', neue Positionen, Merker ohne Preiszeile, andere Maschine, Kopie und ältere Dateien.

Aufruf: python tests/test_preisbasis.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1600, 1000)


def zeile_id(tabelle, **werte):
    return next(z["id"] for z in db.zeilen(tabelle) if all(z.get(n) == w for n, w in werte.items()))


def verkauf(s):
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)[1]["verkauf"]


def material(s):
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)[1]["material"]


a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
for pos, profil, werkstoff, laenge, stueck, ofl in ((10, "QR 40x40x3", "S235-10219", 800, 4, None),
                                                    (20, "RR 48,3x2,6", "S235-10219", 1000, 10, "gestrahlt"),
                                                    (30, "QR 40x40x3", "S355-10219", 700, 6, None)):
    db.position_neu(a, dict(pos=pos, artikel=f"T{pos}", profil_id=profil, werkstoff_id=werkstoff, laenge=laenge,
                            stueck=stueck, schneidweg=320, einstiche=2, oberflaeche=ofl))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()

# ------------------------------------------------------------------ P1 ohne Snapshot: aktuelle Stammdaten
assert db.angebot(a)["preisbasis"] is None
v0, m0 = verkauf(s), material(s)
assert s.uebersicht_bereich.preise_knopf.isHidden()
assert "aktuelle Stammdaten" in s.uebersicht_bereich.preisstand.text()
ok(f"P1 neues Angebot ohne festgeschriebene Preise, Verkaufspreis {v0:.2f} €")

# ------------------------------------------------------------------ P2 Angebots-PDF schreibt fest
pfad = s.angebot_pdf()
assert pfad is not None and Path(pfad).exists()
pb = db.angebot(a)["preisbasis"]
assert isinstance(pb, dict) and pb["maschine"] == s.kopf["maschine"]
kombis = {(z["profil_id"], z["werkstoff_id"]) for z in pb["preise"]}
assert kombis == {("QR 40x40x3", "S235-10219"), ("RR 48,3x2,6", "S235-10219"), ("QR 40x40x3", "S355-10219")}, kombis
merker = [z for z in pb["preise"] if not z.get("basis")]
assert [(z["profil_id"], z["werkstoff_id"]) for z in merker] == [("QR 40x40x3", "S355-10219")], "ohne Preiszeile"
assert set(pb["tonnenpreise"]) == {"S235-10219", "S355-10219"} and set(pb["aufpreise"]) == {"gestrahlt"}
assert pb["schneiddaten"] and all(z["maschinen_id"] == pb["maschine"] for z in pb["schneiddaten"])
assert abs(verkauf(s) - v0) < EPS, "Festschreiben ändert den Preis nicht"
assert "festgeschrieben am" in s.uebersicht_bereich.preisstand.text() and s.uebersicht_bereich.preise_knopf.isHidden()
ok(f"P2 Angebots-PDF schreibt {len(pb['preise'])} Preise (1 Merker ohne Zeile), {len(pb['schneiddaten'])} "
   "Schneiddaten-Zeilen, Tonnenpreise und Oberflächen-Aufpreis fest; Preis unverändert")

# ------------------------------------------------------------------ P3 Stammdaten ändern: Angebot bleibt
db.aendern("preise", zeile_id("preise", profil_id="QR 40x40x3", werkstoff_id="S235-10219"), "preis", 2.10)
db.aendern("werkstoffe", zeile_id("werkstoffe", werkstoff_id="S355-10219"), "tonnenpreis", 1500)
db.aendern("oberflaechen", zeile_id("oberflaechen", oberflaeche="gestrahlt"), "aufpreis_m", 9.99)
sd = next(z for z in db.zeilen("schneiddaten") if z["maschinen_id"] == pb["maschine"]
          and (z["maschinen_id"], z.get("werkstoff_id"), z.get("kategorie"), z.get("gas"), z["wand_bis"])
          in {(x["maschinen_id"], x.get("werkstoff_id"), x.get("kategorie"), x.get("gas"), x["wand_bis"])
              for x in pb["schneiddaten"]})
db.aendern("schneiddaten", sd["id"], "vorschub_gross", sd["vorschub_gross"] / 2)
# neue Preiszeile für die Kombination ohne Zeile: gilt für das festgeschriebene Angebot nicht
db.neu("preise", dict(profil_id="QR 40x40x3", werkstoff_id="S355-10219", basis="€/kg", preis=9.0, lieferlaenge=6000))
s.neu_laden()
assert abs(verkauf(s) - v0) < EPS and abs(material(s) - m0) < EPS, (verkauf(s), v0)
abw = rechnen.preisbasis_abweichung(s.kopf, s.k_aktuell, s.tabellen_aktuell)
assert len(abw) == 5, abw
assert any("2,1 €/kg" in t for t in abw) and any("Tonnenpreis → 9 €/kg" in t for t in abw), abw
assert any(t.startswith("Tonnenpreis S355-10219") for t in abw) and any("gestrahlt" in t for t in abw)
assert any(t.startswith("Schneiddaten") for t in abw)
assert not s.uebersicht_bereich.preise_knopf.isHidden() and "seitdem geändert (5)" in s.uebersicht_bereich.preisstand.text()
ok("P3 Materialpreis, Tonnenpreis, Aufpreis, Schneiddaten geändert und neue Preiszeile angelegt: "
   f"Angebot bleibt bei {v0:.2f} €, Hinweis mit 5 Abweichungen und Knopf sichtbar")

# ------------------------------------------------------------------ P4 Vergleich: ohne Snapshot wäre es teurer
ohne = dict(s.kopf, preisbasis=None)
v_live = rechnen.kalkulation(ohne, s.positionen, s.ergebnis, s.k_aktuell, s.tabellen_aktuell, s.einst)[1]["verkauf"]
assert v_live > v0 + 1, (v_live, v0)
ok(f"P4 mit aktuellen Stammdaten wären es {v_live:.2f} € statt {v0:.2f} €")

# ------------------------------------------------------------------ P5 neue Position: Werte aus den Stammdaten
db.position_neu(a, dict(pos=40, artikel="T40", profil_id="RE 60x40x3", werkstoff_id="S355-10219", laenge=500,
                        stueck=2, schneidweg=200, einstiche=1))
s.neu_laden()
assert s.optimieren()
z = rechnen.preis_zeile("RE 60x40x3", "S355-10219", s.k, s.tabellen)
assert z is not None and z["preis"] == 1.6
assert rechnen.preis_zeile("QR 40x40x3", "S355-10219", s.k, s.tabellen) is None, "Merker: weiter Tonnenpreis"
assert s.k.werkstoffe["S355-10219"]["tonnenpreis"] == 1050
s.angebot_pdf()
pb2 = db.angebot(a)["preisbasis"]
assert pb2["datum"] and ("RE 60x40x3", "S355-10219") in {(z["profil_id"], z["werkstoff_id"]) for z in pb2["preise"]}
assert next(z for z in pb2["preise"] if z["profil_id"] == "QR 40x40x3" and z["werkstoff_id"] == "S235-10219")["preis"] == 1.5
ok("P5 neue Position rechnet mit aktuellen Stammdaten; nächstes PDF ergänzt den Snapshot, alte Werte bleiben")

# ------------------------------------------------------------------ P6 Aktuelle Preise übernehmen
v_vorher = verkauf(s)
assert s.preise_aktualisieren()
assert db.angebot(a)["preisbasis"] is None and verkauf(s) > v_vorher + 1
assert s.uebersicht_bereich.preise_knopf.isHidden()
ok(f"P6 'Aktuelle Preise übernehmen': {v_vorher:.2f} € → {verkauf(s):.2f} €, nächstes PDF schreibt neu fest")

# ------------------------------------------------------------------ P7 andere Maschine: deren aktuelle Schneiddaten
s.angebot_pdf()
pb3 = db.angebot(a)["preisbasis"]
k_eff, t_eff = rechnen.preisbasis_anwenden(dict(s.kopf, maschine="ANDERE"), s.k_aktuell, s.tabellen_aktuell)
assert t_eff["schneiddaten"] == s.tabellen_aktuell["schneiddaten"]
k_eff, t_eff = rechnen.preisbasis_anwenden(s.kopf, s.k_aktuell, s.tabellen_aktuell)
assert t_eff["schneiddaten"] == s.tabellen_aktuell["schneiddaten"], "unverändert: gleiche Zeilen wie Stammdaten"
assert t_eff["preise"] == s.tabellen_aktuell["preise"] and pb3["maschine"] == s.kopf["maschine"]
ok("P7 andere Maschine nimmt aktuelle Schneiddaten; ohne Änderung bleiben die Stammdaten-Zeilen unverändert")

# ------------------------------------------------------------------ P8 Kopie rechnet mit aktuellen Preisen
kopie = db.angebot_kopieren(a)
assert db.angebot(kopie)["preisbasis"] is None
ok("P8 Kopie eines Angebots übernimmt keine festgeschriebenen Preise")

# ------------------------------------------------------------------ P9 ältere Datei (Schema 17)
db.schliessen()
alt = tmp / "alt.db"
import shutil  # noqa: E402
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("ALTER TABLE angebote DROP COLUMN preisbasis")
con.execute("PRAGMA user_version=17")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert db2.angebot(a)["preisbasis"] is None
assert db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("P9 Datei Schema 17: Spalte ergänzt, alte Angebote ohne Snapshot, Sicherung vor der Umstellung")
print("Alle Prüfungen bestanden.")
