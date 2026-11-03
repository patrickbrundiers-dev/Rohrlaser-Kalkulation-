"""Fläche und Gewicht eines ganzen Satzes für Pulverbeschichten und Verzinken (Patrick 03.11.2026, Freigabe 1a 2a 3a):
Summe je Satz (Außenfläche × Stück je Satz, Bleche beide Seiten ohne Löcher, Zukaufteile mit Gewicht), Tooltip der
Spalte Satz, Rechtsklick „Zusatzarbeit für ganzen Satz …“ (alle Positionen des Satzes, Fenster mit € je Satz),
Rechnung weiter je Teil (Summe gleich).

Aufruf: python tests/test_satz_flaeche.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import blech, rechnen, satz_flaeche  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.zusatz_dialog import BETRAG, ZusatzDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


# ------------------------------------------------------------------ S1 Blech: beide Seiten ohne Löcher
e = dict(quelle=blech.QUELLE, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=200, breite=100, eckradius=0, dicke=3,
         werkstoff="S235", konturen=[dict(art="Bohrung", d=10, anzahl=2), dict(art="Gravur", laenge=50, anzahl=1)])
assert nah(blech.oberflaeche(e), 2 * (20000 - 2 * math.pi * 25) / 1e6)
assert blech.oberflaeche(dict(e, laenge=0)) is None
bp = dict(art="Zukaufteil", technik=blech.speichern(e), gewicht_teil=0.47, stueck=4)
assert nah(rechnen.zusatz_menge_auto("€/m²", bp, None), blech.oberflaeche(e))
assert rechnen.zusatz_menge_auto("€/m²", dict(art="Zukaufteil", stueck=4), None) is None   # Kaufteil ohne Maße
ok("S1 Blech im Satz: Fläche beide Seiten ohne Löcher (Gravur zählt nicht), Pulverbeschichten rechnet damit")

# ------------------------------------------------------------------ S2 Summe je Satz
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
aid = beispiel_angebot.anlegen(db)
pos = [p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil"][:3]
for p, je in zip(pos, (2, 1, 4)):
    db.position_aendern(p["id"], "satz", "Gestell")
    db.position_aendern(p["id"], "je_satz", je)
    db.position_aendern(p["id"], "stueck", je * 3)
    db.position_aendern(p["id"], "zusatz", None)
bid = db.position_neu(aid, dict(bp, satz="Gestell", je_satz=2, stueck=6, pos=990, bezeichnung="Lasche"))
db.position_neu(aid, dict(art="Zukaufteil", satz="Gestell", je_satz=1, stueck=3, pos=995, bezeichnung="Griff"))
k = db.kontext()
alle = db.positionen(aid)
m = satz_flaeche.mengen(alle, "Gestell", k)
satz_pos = [p for p in alle if p.get("satz") == "Gestell"]
soll_f = sum((rechnen.zusatz_menge_auto("€/m²", p, k) or 0) * (p.get("je_satz") or 1) for p in satz_pos)
soll_g = sum((rechnen.zusatz_menge_auto("€/kg", p, k) or 0) * (p.get("je_satz") or 1) for p in satz_pos)
assert nah(m["flaeche"], soll_f) and nah(m["gewicht"], soll_g) and m["saetze"] == 3, m
assert nah(m["flaeche_alle"], 3 * soll_f) and m["ohne_flaeche"] == [995] and m["ohne_gewicht"] == [995], m
assert blech.oberflaeche(e) * 2 < m["flaeche"] and 0.47 * 2 < m["gewicht"]
t = satz_flaeche.text(m)
assert "m² · " in t and "kg je Satz" in t and "(3 Sätze:" in t, t
assert satz_flaeche.fehlt_text(m) == "ohne Fläche: Pos. 995; ohne Gewicht: Pos. 995"
ok("S2 Summe je Satz: Außenfläche bzw. Gewicht × Stück je Satz, mit Blech und Zukaufteil, fehlende werden genannt")

# ------------------------------------------------------------------ S3 Positionsliste und Rechtsklick
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
rz = [r for r, p in enumerate(s.positionen) if p.get("satz") == "Gestell"]
spalte = next(c for c, (art, x) in enumerate(s.pos_modell.spalten) if art == "feld" and x.name == "satz")
tipp = s.pos_modell.data(s.pos_modell.index(rz[0], spalte), Qt.ToolTipRole)
assert "Pulverbeschichten/Verzinken: " + t in tipp and "Zusatzarbeit für ganzen Satz" in tipp, tipp
s.pos_ansicht.selectRow(rz[1])
s._pos_menue_anpassen()
assert s.pos_aktionen["Zusatzarbeit für ganzen Satz …"].isVisible()
vorher = s._rechnung()[0]
d = ZusatzDialog(s, s.positionen[rz[0]], len(rz), s.k, s.tabellen, kopf=s.kopf, positionen=s.positionen,
                 satz=dict(name="Gestell", positionen=[s.positionen[r] for r in rz], mengen=m))
assert not d.satz_info.isHidden() and "Satz Gestell" in d.satz_info.text() and "Pos. 995" in d.satz_info.text()
assert d.tabelle.horizontalHeaderItem(BETRAG).text() == "€ je Satz"
r = d.hinzufuegen("Pulverbeschichten")
preis = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Pulverbeschichten")["preis"]
assert d.tabelle.cellWidget(r, BETRAG).text() == f"{soll_f * preis:,.2f} €".replace(",", "#").replace(".", ",") \
    .replace("#", "."), (d.tabelle.cellWidget(r, BETRAG).text(), soll_f * preis)
assert "Summe je Satz" in d.summe.text() and "3 Sätze" in d.summe.text(), d.summe.text()
assert s.zusatz_satz(rz[1], (None, json.dumps([dict(name="Feuerverzinken")])))
for p in db.positionen(aid):
    if p.get("satz") == "Gestell":
        assert [x["name"] for x in rechnen.zusatz_liste(p)] == ["Feuerverzinken"], p
    else:
        assert "Feuerverzinken" not in [x["name"] for x in rechnen.zusatz_liste(p)]
nachher = s._rechnung()[0]
fvz = 0.0
for zl in nachher:
    for z in zl.get("zusatzarbeiten") or ():
        if z["name"] == "Feuerverzinken":
            fvz += z["betrag"] * zl["stueck"]
fvz_preis = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Feuerverzinken")["preis"]
assert nah(fvz, soll_g * 3 * fvz_preis, 1e-4), (fvz, soll_g * 3 * fvz_preis)
assert vorher != nachher
assert not s.zusatz_satz(next(r for r, p in enumerate(s.positionen) if not p.get("satz")))
ok("S3 Tooltip der Spalte Satz mit m² und kg, Rechtsklick „Zusatzarbeit für ganzen Satz …“: alle Positionen des "
   "Satzes, Fenster mit € je Satz; Verzinken je Teil ergibt in Summe Gewicht aller Sätze × €/kg")
print("OK: Fläche und Gewicht je Satz")
