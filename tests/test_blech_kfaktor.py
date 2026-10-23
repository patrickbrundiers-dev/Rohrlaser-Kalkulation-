"""K-Faktor-Tabelle der Abwicklung (Plan S4, Patrick 23.10.2026 „2a“):
- K1 Nachschlagen: Kategorie, kleinste 'Dicke bis' ≥ Dicke, kleinste 'Ri/s bis' ≥ Innenradius ÷ Dicke, größer als
  alle = größte Zeile, keine Zeile = K-Faktor des Werkstoffs.
- K2 Beispielwerte nach DIN 6935; ri = s ergibt wie bisher 0,33, also gleiche Abwicklung wie vor der Tabelle.
- K3 Richtpreis: je Biegung eigener K-Faktor (verschiedene Radien), Einstellung 'je Werkstoff' schaltet die Tabelle
  ab; ältere Datei (Schema 46) bekommt die Tabelle mit Beispielwerten; Blech-Editor zeigt den K-Faktor.

Aufruf: python tests/test_blech_kfaktor.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, stammdaten  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ K1 Nachschlagen
tab = [dict(kategorie="Stahl", dicke_bis=3, ri_s_bis=1, k_faktor=0.3),
       dict(kategorie="Stahl", dicke_bis=3, ri_s_bis=2, k_faktor=0.4),
       dict(kategorie="Stahl", dicke_bis=10, ri_s_bis=1, k_faktor=0.35),
       dict(kategorie="Edelstahl", dicke_bis=10, ri_s_bis=1, k_faktor=0.45)]
assert blech.k_faktor(tab, "Stahl", 2, 2) == 0.3              # Ri/s = 1
assert blech.k_faktor(tab, "Stahl", 2, 3) == 0.4              # Ri/s = 1,5
assert blech.k_faktor(tab, "Stahl", 2, 20) == 0.4             # größer als alle: größte Zeile
assert blech.k_faktor(tab, "Stahl", 5, 5) == 0.35             # Dicke über 3: Zeilen bis 10
assert blech.k_faktor(tab, "Stahl", 12, 12, 0.31) == 0.31     # zu dick: Werkstoff
assert blech.k_faktor(tab, "Aluminium", 2, 2, 0.29) == 0.29   # Kategorie fehlt: Werkstoff
assert blech.k_faktor([], "Stahl", 2, 2) == blech.K_FAKTOR
ok("K1 Nachschlagen nach Kategorie, Dicke und Ri/s, sonst K-Faktor des Werkstoffs")

# ------------------------------------------------------------------ K2 Beispielwerte
bsp = [dict(zip(("kategorie", "dicke_bis", "ri_s_bis", "k_faktor", "bemerkung"), z))
       for z in stammdaten.beispiel_blech_kfaktoren()]
for ri_s in (0.5, 1, 2, 3, 5):
    din = min(0.5, (0.65 + 0.5 * math.log10(ri_s)) / 2)
    assert abs(blech.k_faktor(bsp, "Stahl", 2, 2 * ri_s) - din) < 0.006, (ri_s, din)
assert blech.k_faktor(bsp, "Edelstahl", 3, 3) == 0.33 and blech.k_faktor(bsp, "Aluminium", 4, 40) == 0.5
assert all("DIN 6935" in z["bemerkung"] for z in bsp)
ok("K2 Beispielwerte nach DIN 6935 (ri = s: 0,33 wie bisher), als Beispiel gekennzeichnet")

# ------------------------------------------------------------------ K3 Richtpreis und Datei
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert len(db.zeilen("blech_kfaktoren")) == 18
werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
laser = db.zeilen("blechlaser")
einst = db.blech_einstellungen()
assert einst["blech_abwicklung"] == blech.ABWICKLUNG_K[0] and len(einst["kfaktoren"]) == 18
kant = dict(art=blech.KANTTEIL, werkstoff="S235JR", dicke=2, kantlaenge=300,
            schenkel=[dict(laenge=50, winkel=90, radius=2), dict(laenge=80, winkel=90, radius=8), dict(laenge=40)],
            konturen=[])
erg = blech.rechnen(kant, werkstoffe, laser, einst)
assert erg["k_faktoren"] == [0.33, 0.5] and not erg["fehler"]
v1, v2 = (blech.ausgleich(90, 2, 2, 0.33), blech.ausgleich(90, 8, 2, 0.5))
assert abs(erg["zuschnitt"]["breite"] - (170 - v1 - v2)) < 1e-9
alt = blech.rechnen(kant, werkstoffe, laser, dict(einst, blech_abwicklung=blech.ABWICKLUNG_K[1]))
assert alt["k_faktoren"] == [0.33] and abs(alt["zuschnitt"]["breite"] - (170 - v1 - blech.ausgleich(90, 8, 2))) < 1e-9
ohne = blech.rechnen(kant, werkstoffe, laser, {})
assert ohne["k_faktoren"] == [0.33]
# ri = s überall: gleiche Abwicklung wie ohne Tabelle
gleich = dict(kant, schenkel=[dict(laenge=50, winkel=90), dict(laenge=80, winkel=-90), dict(laenge=40)])
assert blech.rechnen(gleich, werkstoffe, laser, einst)["zuschnitt"] == blech.rechnen(gleich, werkstoffe, laser,
                                                                                     {})["zuschnitt"]
db.schliessen()
ok("K3 Richtpreis: K-Faktor je Biegung aus der Tabelle, abschaltbar, ri = s unverändert")

# ältere Datei (Schema 46) bekommt die Tabelle mit Beispielwerten
alt_pfad = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt_pfad)
con = sqlite3.connect(alt_pfad)
con.execute("DROP TABLE blech_kfaktoren")
con.execute("PRAGMA user_version = 46")
con.commit()
con.close()
db = Datenbank(alt_pfad)
assert db.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 47
assert len(db.zeilen("blech_kfaktoren")) == 18
ok("K3 Ältere Datei (Schema 46) bekommt die K-Faktor-Tabelle mit Beispielwerten")

from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
d = BlechDialog(None, db, kant)
assert d.ergebnis["k_faktoren"] == [0.33, 0.5] and "K-Faktor 0,33 / 0,50" in d.summe.text(), d.summe.text()
db.schliessen()
ok("K3 Blech-Editor zeigt die K-Faktoren der Biegungen")
