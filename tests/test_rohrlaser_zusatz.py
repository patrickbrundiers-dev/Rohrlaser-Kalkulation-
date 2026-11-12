"""Weitere Zusatzarbeiten rund um den Rohrlaser (Patrick 03.11.2026 „Alle Empfehlungen“ + Brünieren, Trennmittel im
Rohr gegen Spritzer, Drehen/Fräsen): fest in der Auswahl mit Beispielpreis und Erkennungswörtern, alte Dateien werden
einmalig ergänzt (eigene gleichen Namens bleiben), Richten/Einpressmuttern/Prüfbericht 3.1 nicht mehr doppelt als
Vorlage.

Aufruf: python tests/test_rohrlaser_zusatz.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import zusatz_erkennung as ze  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import ROHRLASER_ZUSATZ, ZUSATZ_KATEGORIEN, ZUSATZ_VORLAGEN, zusatz_vorlage  # noqa: E402


def ok(t):
    print("OK  ", t)


NAMEN = [z[0] for z in ROHRLASER_ZUSATZ]
tmp = Path(tempfile.mkdtemp())

# R1 neue Datei: alle 15 da (12.11. Reiben), aktiv, mit Preis, Kategorie und Erkennungswörtern
db = Datenbank(tmp / "neu.db")
k = {z["name"]: z for z in db.zeilen("zusatzarbeiten")}
assert len(NAMEN) == len(set(NAMEN)) == 15
for n in ("Brünieren", "Trennmittel innen", "Drehen/Fräsen", "Innengrat entfernen", "Erstmusterprüfbericht"):
    assert n in NAMEN, n
for n in NAMEN:
    z = k[n]
    assert z["aktiv"] == "ja" and z["preis"] > 0 and z["kategorie"] in ZUSATZ_KATEGORIEN and z["erkennung"], z
assert k["Brünieren"]["art"] == "€/kg" and k["Brünieren"]["fremd"] == "ja"
assert k["Erstmusterprüfbericht"]["art"] == k["Prüfbericht 3.1"]["art"] == "€/Angebot"
assert k["Schweißfase anfasen"]["art"] == "€/Stück"
vorl = [v[0] for v in ZUSATZ_VORLAGEN]
assert not set(vorl) & set(NAMEN) and zusatz_vorlage("Richten") is None and zusatz_vorlage("Eloxieren")
ok("R1 neue Datei: 15 Rohrlaser-Zusatzarbeiten aktiv mit Beispielpreis und Erkennung, keine doppelte Vorlage")

# R2 alte Datei: einmalig ergänzt, eigene Zeile gleichen Namens bleibt, keine doppelten
db.schliessen()
con = sqlite3.connect(tmp / "neu.db")
con.execute("DELETE FROM zusatzarbeiten WHERE name IN (%s)" % ",".join("?" * len(NAMEN)), NAMEN)
con.execute("INSERT INTO zusatzarbeiten (name, art, preis, aktiv) VALUES ('Richten', '€/Stück', 3.9, 'ja')")
con.execute("DELETE FROM einstellungen WHERE name='rohrlaser_zusatz_stand'")
con.commit()
con.close()
db = Datenbank(tmp / "neu.db")
alle = [z["name"] for z in db.zeilen("zusatzarbeiten")]
assert all(alle.count(n) == 1 for n in NAMEN), alle
assert {z["name"]: z for z in db.zeilen("zusatzarbeiten")}["Richten"]["preis"] == 3.9
con = db.con
con.execute("DELETE FROM zusatzarbeiten WHERE name='Brünieren'")      # gelöscht bleibt gelöscht (nur einmalig)
con.commit()
db.schliessen()
db = Datenbank(tmp / "neu.db")
assert "Brünieren" not in [z["name"] for z in db.zeilen("zusatzarbeiten")]
ok("R2 alte Datei einmalig ergänzt, eigene 'Richten' bleibt, später gelöschte kommt nicht wieder")

# R3 Erkennung im Text
kat = db.zeilen("zusatzarbeiten") + [dict(k["Brünieren"])]
t = dict(ze.treffer("Rohr innen entgratet, schwarz brüniert, mit Trennmittel, Enden angefast, gedreht, EMPB", kat))
for n in ("Innengrat entfernen", "Brünieren", "Trennmittel innen", "Schweißfase anfasen", "Drehen/Fräsen",
          "Erstmusterprüfbericht"):
    assert n in t, (n, t)
assert "Entgraten" not in t                     # „innen entgratet“ ist länger und gewinnt
t = dict(ze.treffer("Werkstoff S235 mit Zeugnis 3.1, Endkappen einsetzen, Teile etikettiert", kat))
assert {"Prüfbericht 3.1", "Endkappen/Stopfen einsetzen", "Etikettieren/Beschriften"} <= set(t), t
assert not ze.treffer("Rohr 40x40x3, Länge 1200, S235", kat)
db.schliessen()
ok("R3 Erkennungswörter: innen entgratet, brüniert, Trennmittel, angefast, gedreht, EMPB, 3.1, Endkappen, Etikett")
