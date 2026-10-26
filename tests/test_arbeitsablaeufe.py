"""Prüft die Arbeitsabläufe aus dem Plan „Arbeitsabläufe effizienter“ (Schritt AB1): Standard-Staffeln (W3),
Stückzahl gemeinsam ändern (W4), Nachkalkulation „Rest wie geplant“ und Filter „Nachkalkulation offen“ (W9) und die
neuen Tastenkürzel (W12).

Aufruf: python tests/test_arbeitsablaeufe.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import nachkalkulation as nk, staffeln, tastatur  # noqa: E402
from rohrlaser.angebot_fenster import VORGANG_FILTER  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.mengen_dialog import neue_stueckzahl  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ W3 reine Funktionen
assert staffeln.standard_faktoren("1; 2; 5") == [1, 2, 5]
assert staffeln.standard_faktoren("2 0,5;2; x; -1; 0; inf; nan") == [2, 0.5]
assert staffeln.standard_faktoren("") == [] and staffeln.standard_faktoren(None) == []
assert staffeln.standard_faktoren(" ".join(str(i) for i in range(1, 20))) == list(range(1, 11))
assert staffeln.standard_menge(10, 2) == 20 and staffeln.standard_menge(3, 0.5) == 2 and staffeln.standard_menge(1, 0.1) == 1
ok("W3 Faktoren '1; 2; 5' gelesen, ungültige/doppelte entfallen, höchstens 10; Menge × Faktor gerundet, mindestens 1")

# ------------------------------------------------------------------ W4 reine Funktionen
assert neue_stueckzahl(10, faktor=2) == 20 and neue_stueckzahl(3, faktor=0.5) == 2 and neue_stueckzahl(1, faktor=0.1) == 1
assert neue_stueckzahl(None, faktor=2) is None and neue_stueckzahl("", faktor=2) is None
assert neue_stueckzahl(None, wert=7) == 7 and neue_stueckzahl(5, wert=10 ** 9) == 100000
assert neue_stueckzahl(60000, faktor=2) == 100000 and neue_stueckzahl(5, faktor=float("inf")) is None
ok("W4 Stückzahl × Faktor (gerundet, 1 … 100.000) bzw. = Wert; ohne Stückzahl bleibt die Position leer")

# ------------------------------------------------------------------ mit Datenbank und Oberfläche
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
db.staffel_stufen_loeschen([st["id"] for st in db.staffel_stufen(a)])
s = fenster.angebot_oeffnen(a)
assert not staffeln.gueltige(s.stufen)
mengen = {schl: m for schl, _, m in staffeln.auswahl(s.positionen) if m}
assert mengen

# W3: das Angebots-PDF legt keine Staffeln an und rechnet keine (Patrick 26.10.2026: nie automatisch)
assert db.einstellung("staffeln_standard") == "1; 2; 5"
assert s.angebot_pdf()
assert not db.staffel_stufen(a) and not s.kopf.get("staffelpreise")
ok("W3 Angebots-PDF ohne Stufe: legt keine Standard-Staffeln an, rechnet nichts")

# Knopf „Standard-Staffeln“ legt sie jederzeit an; leere Einstellung = aus
assert len(s.st_seite.standard()) == 3 and len(db.staffel_stufen(a)) == 3
stufen = db.staffel_stufen(a)
for st, f in zip(stufen, (1, 2, 5)):
    zeilen = {z["schluessel"]: z["menge"] for z in s.stufen if z["stufe_id"] == st["id"]}
    assert zeilen == {schl: m * f for schl, m in mengen.items()}, (f, zeilen)
assert not s.kopf.get("staffelpreise") and s.st_seite.anzahl_veraltet() == 3    # angelegt, nicht gerechnet
assert s.angebot_pdf() and not s.kopf.get("staffelpreise")                    # auch das PDF rechnet sie nicht
assert len(s.staffelpreise_rechnen()) >= 3 and s.st_seite.anzahl_veraltet() == 0
db.einstellung_setzen("staffeln_standard", "")
assert s.st_seite.standard() == [] and len(db.staffel_stufen(a)) == 3
db.einstellung_setzen("staffeln_standard", "1; 2; 5")
ok("W3 Knopf Standard-Staffeln; Einstellung leer = keine Standard-Staffeln")

# ------------------------------------------------------------------ W4 im Angebot
vorher = [p.get("stueck") for p in s.positionen]
s.pos_ansicht.clearSelection()
n = s.stueck_aendern(faktor=2)
nachher = [p.get("stueck") for p in s.positionen]
assert n == sum(1 for x in vorher if x) and all((y == x * 2) if x else (y == x) for x, y in zip(vorher, nachher))
assert s.rueckgaengig() and [p.get("stueck") for p in s.positionen] == vorher
assert s.stueck_aendern(zeilen=[0], wert=7) == 1 and s.positionen[0]["stueck"] == 7
assert [p.get("stueck") for p in s.positionen][1:] == vorher[1:]
s.rueckgaengig()


def bedienen(d, text="3", gleich=False):
    (d.gleich if gleich else d.mal).setChecked(True)
    (d.wert_feld if gleich else d.faktor_feld).setText(text)
    d.accept()
    return d.result()


assert s.stueck_aendern(zeilen=[0], dialog=lambda d: bedienen(d, "abc")) is None and s.positionen[0]["stueck"] == vorher[0]
assert s.stueck_aendern(zeilen=[0], dialog=lambda d: bedienen(d, "2,5", gleich=True)) is None
assert s.stueck_aendern(zeilen=[0], dialog=lambda d: bedienen(d, "3")) == 1 and s.positionen[0]["stueck"] == vorher[0] * 3
s.rueckgaengig()
ok(f"W4 Stückzahl × 2 für alle {n} Positionen mit Stückzahl, = 7 für eine markierte, Rückgängig in einem Schritt, "
   "Dialog prüft die Eingabe")

# ------------------------------------------------------------------ W9 Nachkalkulation
assert s.optimieren()
nks = s.nachkalk
nks.setzen(werte=dict(laser_h=1.5))
gesetzt = nks.rest_wie_geplant()
assert gesetzt and gesetzt > 3
ist = s.kopf["nachkalkulation"]
assert ist["laser_h"] == 1.5 and ist["sonstiges"] == 0.0
v = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, ist, kalk=s._rechnung())
assert all(z["erfasst"] == "ja" for z in v["zeilen"]), [(z["text"], z["erfasst"]) for z in v["zeilen"]]
assert v["db"]["erfasst"] == "ja"
assert abs(v["zeilen"][0]["ist"] - v["zeilen"][0]["soll"]) < 1e-6         # Material wie geplant
assert abs(v["erloes"]["ist"] - v["erloes"]["soll"]) < 1e-6
assert nks.rest_wie_geplant() == 0
ok(f"W9 Rest wie geplant: {gesetzt} leere Ist-Werte = Soll, eingetragene (Laserzeit 1,5 h) bleiben, alles erfasst")

# Zwei Baugruppen mit gleichem Namen: Werte gehen nach ID, nicht nach Anzeigetext
def _z(text, menge, soll, **x):
    return dict(text=text, soll_menge=menge, soll=soll, **x)


v2 = dict(gruppen=[], erloes=dict(soll=100.0), baugruppen=[dict(id="A", name="Rahmen"), dict(id="B", name="Rahmen")],
          zeilen=[_z("Material", 0, 0), _z("Laserzeit", 1, 10), _z("Rüsten + Stangenwechsel", 5, 4),
                  _z("Gewinde und Zusatzarbeiten", None, 0), _z("Zukaufteile (Einstand)", None, 0)]
          + [_z(f"Rahmen: {t}", m, b_, bg_id=i, bg_feld=n) for i, f in (("A", 1), ("B", 3))
             for n, t, e, _ in nk.BG_FELDER for m, b_ in [((f if e == "h" else None), 10.0 * f)]])
ist2, _ = nk.rest_wie_geplant(v2, {})
assert ist2["baugruppen"]["A"] == dict(schweiss_h=1, arbeit_h=1, material=10.0, fremd=10.0), ist2["baugruppen"]
assert ist2["baugruppen"]["B"] == dict(schweiss_h=3, arbeit_h=3, material=30.0, fremd=30.0), ist2["baugruppen"]
ok("W9 Rest wie geplant: gleichnamige Schweißbaugruppen bekommen je eigene Soll-Werte (nach ID)")

# Filter „Nachkalkulation offen“: beauftragt und noch ohne Ist-Werte
passt = VORGANG_FILTER["Nachkalkulation offen"]
assert passt("Beauftragt", False, dict(ist_erfasst=False)) and not passt("Beauftragt", False, dict(ist_erfasst=True))
assert not passt("Verschickt", False, dict(ist_erfasst=False))
b = beispiel_angebot.anlegen(db)
c = beispiel_angebot.anlegen(db)
db.nachkalkulation_speichern(c, dict(bemerkung="nur Bemerkung"))       # zählt nicht als nachkalkuliert
for x in (a, b, c):
    db.vorgang_setzen(x, "Beauftragt")
liste = fenster.angebote
liste.vorgang_filter.setCurrentText("Nachkalkulation offen")
liste.neu_laden()
ids = [z["id"] for z in liste.modell.zeilen]
assert b in ids and c in ids and a not in ids, ids
liste.vorgang_filter.setCurrentText("Alle Angebote")
ok("W9 Filter „Nachkalkulation offen“ zeigt beauftragte Angebote ohne Ist-Werte (nur Bemerkung zählt nicht)")

# ------------------------------------------------------------------ W12 Tastenkürzel
fenster.reiter.setCurrentWidget(s)
for name, taste in (("werkstatt", "Ctrl+Shift+P"), ("kalkulation", "Ctrl+Shift+K"), ("staffeln", "F8"),
                    ("stueck", "Ctrl+Shift+S"), ("material", "Ctrl+Shift+M")):
    a_ = fenster.kuerzel_aktionen[name]
    assert a_.shortcut().toString() == taste, (name, a_.shortcut().toString())
    assert name in type(s).KUERZEL
texte = {t for t, _, _ in tastatur.UEBERSICHT}
assert {"Strg+Umschalt+P", "Strg+Umschalt+K", "F8", "Strg+Umschalt+S", "Strg+Umschalt+M"} <= texte
alle = [t.shortcut().toString() for t in fenster.findChildren(type(a_)) if t.shortcut().toString()]
assert len(alle) == len(set(alle)), sorted(alle)
assert fenster.kuerzel("staffeln") and fenster.kuerzel("werkstatt")
db.nur_lesen = "Test Lesemodus"
fenster.lesemodus_anwenden()
assert not fenster.kuerzel_aktionen["staffeln"].isEnabled() and not fenster.kuerzel_aktionen["stueck"].isEnabled()
assert s.staffelpreise_rechnen() is None and s.stueck_aendern(faktor=2) is None
db.nur_lesen = None
ok("W12 Kürzel Strg+Umschalt+P/K/S/M und F8 im Menü, in der Übersicht, ohne Doppelbelegung; F8 und Strg+Umschalt+S "
   "im Lesemodus aus")

print("Alle Prüfungen bestanden.")
