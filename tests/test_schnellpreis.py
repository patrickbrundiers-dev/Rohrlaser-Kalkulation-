"""Prüft den Schnellpreis für Telefonanfragen (Vorschlag V5, 31.10.2026, schnellpreis.py):
- S1 Schneidweg: zwei gerade Trennschnitte + Bohrungen π·Ø + Konturen; Gehrung 45° länger; Einstiche
- S2 Preis = genau der Preis eines gleichen, gespeicherten Angebots (gleiche Vorgaben, optimiert); Staffel fällt
- S3 nichts gespeichert, Nummernkreis unverändert; Fehler (Profil unbekannt, Länge fehlt, Teil zu lang)
- S4 Fenster: Zeile wie die Schnellzeile, Rechnen, Staffel; „Als Angebot übernehmen“ legt das Angebot an
- S5 Menü Datei → Schnellpreis, Funktion schaltbar

Aufruf: python tests/test_schnellpreis.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import funktionen, rechnen, schnellpreis  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
k = db.kontext()

# ------------------------------------------------------------------ S1 Schneidweg
rr = dict(k.profile["RR 42,4x2,0"], profil_id="RR 42,4x2,0")
u = math.pi * 42.4
weg, ein = schnellpreis.schneidweg(rr)
assert nah(weg, round(2 * u, 1), 1e-3) and ein == 2
weg, ein = schnellpreis.schneidweg(rr, bohrungen=4, bohr_d=8.5, konturen=1, kontur_mm=120)
assert nah(weg, round(2 * u + 4 * math.pi * 8.5 + 120, 1), 1e-3) and ein == 7
weg_g, _ = schnellpreis.schneidweg(rr, gehrung=1)
assert weg_g > 2 * u
p = schnellpreis.position(k, "RR 42,4x2,0", "S235-10219", 800, 20, gehrung=2)
assert p["a_gerade"] == p["b_gerade"] == "nein"
ok("S1 Schneidweg = 2 Trennschnitte + Bohrungen π·Ø + Konturen, Gehrung länger, Einstiche")

# ------------------------------------------------------------------ S2 gleich wie ein Angebot
n_vorher = len(db.angebote())
ein = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1250, stueck=20, bohrungen=2, bohr_d=10)
erg = schnellpreis.berechnen(db, ein)
h = erg["haupt"]
assert not h["fehler"] and h["preis_stueck"] > 0 and nah(h["verkauf"], h["preis_stueck"] * 20), h
a = db.angebot_neu()
db.position_neu(a, {n: v for n, v in erg["position"].items() if n != "bezeichnung"})
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
zeilen, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
assert nah(summen["verkauf"], h["verkauf"], 1e-9), (summen["verkauf"], h["verkauf"])
fenster.angebot_schliessen(a)
staffel = {x["stueck"]: x["preis_stueck"] for x in erg["staffel"] + [h] if not x.get("fehler")}
assert set(staffel) >= {1, 10, 20, 50, 100}
assert staffel[1] > staffel[10] > staffel[100], staffel          # Rüsten/Programmieren verteilt sich
ok("S2 Preis wie ein gespeichertes Angebot mit gleicher Position; Staffel 1/10/50/100/500 fällt mit der Menge")

# ------------------------------------------------------------------ S3 nichts gespeichert, Fehler
nr, n = db.einstellung("letzte_angebotsnummer"), len(db.angebote())
schnellpreis.berechnen(db, ein)
assert db.einstellung("letzte_angebotsnummer") == nr and len(db.angebote()) == n == n_vorher + 1
assert schnellpreis.berechnen(db, dict(ein, profil_id="XY 1"))["fehler"] == "Profil unbekannt"
assert schnellpreis.berechnen(db, dict(ein, laenge=None))["fehler"] == "Länge und Stückzahl angeben"
zu_lang = schnellpreis.berechnen(db, dict(ein, laenge=30000))
assert zu_lang["haupt"]["fehler"], zu_lang["haupt"]
ok("S3 berechnen speichert nichts; Fehler für unbekanntes Profil, fehlende Länge, zu langes Teil")

# ------------------------------------------------------------------ S4 Fenster
d = fenster.schnellpreis()
d.zeile.setText("QR 40x3 S235 1250 20")
assert "QR 40x40x3" in d.erkannt.text()
d.bohrungen.setValue(2)
d.bohr_d.setValue(10)
e = d.rechnen()
assert nah(e["haupt"]["verkauf"], h["verkauf"], 1e-9) and "je Stück" in d.preis.text()
assert d.staffel.rowCount() >= 5 and d.uebernehmen_knopf.isEnabled()
n = len(db.angebote())
i = d.uebernehmen()
assert len(db.angebote()) == n + 1 and db.positionen(i)[0]["profil_id"] == "QR 40x40x3"
assert db.angebot(i)["ergebnis"]                                 # gleich optimiert
d2 = fenster.schnellpreis()
d2.zeile.setText("gibtsnicht 1000 5")
d2.rechnen()
assert d2.preis.text() == "–" and "Kein Preis" in d2.info.text() and not d2.uebernehmen_knopf.isEnabled()
ok("S4 Fenster: Zeile wie die Schnellzeile, Preis + Staffel, Als Angebot übernehmen (optimiert), Fehler ohne Preis")

# ------------------------------------------------------------------ S5 Menü und Funktion
assert "Schnellpreis …" in fenster.datei_aktionen
assert fenster.datei_aktionen["Schnellpreis …"].shortcut().toString() == "Ctrl+Alt+P"
assert "Schnellpreis …" in funktionen.FUNKTION["funktion_schnellpreis"].datei
ok("S5 Datei → Schnellpreis (Strg+Alt+P), Funktion schaltbar")
print("Alle Prüfungen bestanden.")
