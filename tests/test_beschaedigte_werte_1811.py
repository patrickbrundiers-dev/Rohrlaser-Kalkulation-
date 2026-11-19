"""Stabilitäts-Auftrag 18.11.2026 (Patrick, Paket B „beschädigte Werte“): eine Position mit unbrauchbarem Zahlenwert
(aus einem Import, dem Abgleich, einer fremden oder beschädigten Datei) darf weder das Programm beenden noch das
Optimieren oder die Kalkulation abbrechen lassen.

Geprüft wird ohne Bildschirm:
- datenbank.zahlen_bereinigen: NaN, ±∞, Text, Wahrheitswerte und Mengen über der Feldgrenze werden beim Lesen leer
  (der Status meldet den fehlenden Wert); gültige Werte bleiben unverändert (auch Grenzwerte),
- Schreiben: NaN wird wie bei SQLite als leer gespeichert (PostgreSQL behielt NaN), ∞ und Text weiter abgewiesen,
- jedes Zahlenfeld einer Position mit 0, −5, 10¹², ∞ direkt in der Datei: Positionen lesen, optimieren und
  kalkulieren ohne Absturz und ohne Speicherüberlauf (vorher: Stück 10¹² = MemoryError),
- Angebot mit solcher Position im Fenster öffnen und optimieren,
- Ergebnis für gültige Positionen unverändert (gleiche Kalkulation wie ohne die beschädigte Position daneben).
Aufruf: python tests/test_beschaedigte_werte_1811.py
"""
import json
import math
import os
import resource
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import datenbank, db_verbindung, rechnen  # noqa: E402
from rohrlaser.angebot import POSITIONEN  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

# Speicherüberlauf soll als Fehler auffallen, nicht den Rechner lahmlegen (4 GB Adressraum reichen dem Test)
try:
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 ** 3, resource.getrlimit(resource.RLIMIT_AS)[1]))
except (ValueError, OSError):
    pass


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ Lesen bereinigt
p = dict(laenge=float("nan"), stueck=10 ** 12, schneidweg=float("inf"), einstiche=True, je_satz="7", preis_m=-0.0,
         stange=6000, pos=3, bezeichnung="nan")
datenbank.zahlen_bereinigen(p)
assert p["laenge"] is None and p["stueck"] is None and p["schneidweg"] is None and p["einstiche"] is None, p
assert p["je_satz"] is None and p["preis_m"] == 0 and p["stange"] == 6000 and p["pos"] == 3 and p["bezeichnung"] == "nan"
grenzen = {f.name: f for f in POSITIONEN.felder if f.art in ("zahl", "ganz")}
g = {"stueck": grenzen["stueck"].bis, "laenge": 25000.0, "schneidweg": 0.0}
datenbank.zahlen_bereinigen(g)
assert g == {"stueck": grenzen["stueck"].bis, "laenge": 25000.0, "schneidweg": 0.0}, g    # nur Mengen begrenzt
ok("Lesen: NaN/∞/Text/Wahrheitswert leer, Stück über der Feldgrenze leer, gültige Werte und Grenzwerte bleiben")

# ------------------------------------------------------------------ Schreiben
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
k, tab = db.kontext(), db.tabellen()
aid = db.angebot_neu(dict(kunde="Kaputt", kundennr="K-9", maschine="T11", stange=6000))
GUT = [dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0 + 100 * i, stueck=3 + i,
            schneidweg=200.0) for i in range(3)]
ids = [db.position_neu(aid, q) for q in GUT]
db.position_aendern(ids[0], "schneidweg", float("nan"))
assert db.con.execute("SELECT schneidweg FROM positionen WHERE id=?", (ids[0],)).fetchone()[0] is None
for w in (float("inf"), "abc"):
    try:
        db.position_aendern(ids[0], "laenge", w)
        raise AssertionError(f"{w!r} muss abgewiesen werden")
    except ValueError:
        pass
db.position_aendern(ids[0], "schneidweg", 200.0)
ok("Schreiben: NaN wird leer (wie SQLite, jetzt auch PostgreSQL), ∞ und Text abgewiesen")

# ------------------------------------------------------------------ jedes Zahlenfeld beschädigt in der Datei
kopf = db.angebot(aid)
basis_pos = db.positionen(aid)
erg = rechnen.optimieren(kopf, basis_pos, k, tab, db.einstellungen())
basis = rechnen.kalkulation(kopf, basis_pos, erg, k, tab, db.einstellungen())
schlecht = [0, -5, 10 ** 12, float("inf"), 1e300]
faelle = fehler = 0
for f in POSITIONEN.felder:
    if f.art not in ("zahl", "ganz") or f.name in ("pos",):
        continue
    for w in schlecht:
        try:
            with db.con:
                db.con.execute(f'UPDATE positionen SET "{f.name}"=? WHERE id=?', (w, ids[1]))
        except db_verbindung.DbFehler:      # PostgreSQL nimmt den Wert gar nicht erst an (z. B. 1e300 als Ganzzahl)
            assert db.con.art == "postgres"
            continue
        faelle += 1
        try:
            pos = db.positionen(aid)
            e = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
            rechnen.kalkulation(kopf, pos, e, k, tab, db.einstellungen())
        except MemoryError:
            raise AssertionError(f"Speicherüberlauf bei {f.name}={w!r}") from None
        except Exception as x:      # noqa: BLE001
            fehler += 1
            print("FEHLER", f.name, repr(w), type(x).__name__, x)
        with db.con:
            db.con.execute(f'UPDATE positionen SET "{f.name}"=? WHERE id=?',
                           (GUT[1].get(f.name), ids[1]))
assert fehler == 0, f"{fehler} von {faelle} Fällen brechen ab"
pos = db.positionen(aid)
nachher = rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k, tab, db.einstellungen()), k, tab,
                              db.einstellungen())
assert json.dumps(basis, sort_keys=True, default=str) == json.dumps(nachher, sort_keys=True, default=str)
ok(f"{faelle} beschädigte Zahlenwerte direkt in der Datei: lesen, optimieren, kalkulieren ohne Abbruch; danach "
   "gleiches Ergebnis wie vorher")

# ------------------------------------------------------------------ im Fenster
with db.con:
    db.con.execute("UPDATE positionen SET stueck=?, laenge=? WHERE id=?", (10 ** 12, float("inf"), ids[2]))
f = Hauptfenster(db, tmp, stumm=True)
s = f.angebot_oeffnen(aid)
s.optimieren()
app.processEvents()
assert len(s.positionen) == 3 and s.pos_modell.status[2] != "OK", s.pos_modell.status
assert all(math.isfinite(z.get("preis_teil") or 0) for z in s._kalk_zeilen if z), "Preise müssen endlich sein"
ok(f"Fenster: Angebot mit Stück 10¹² und Länge ∞ öffnet und optimiert, Status meldet „{s.pos_modell.status[2][:60]}“")
print("ALLE TESTS BESTANDEN")
