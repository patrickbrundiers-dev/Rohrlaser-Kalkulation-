"""Zusatzarbeit für ganzen Satz repariert (Patrick 04.11.2026: „Satzauswahl Zusatzarbeiten funktioniert nicht“,
Freigabe „Alle Empfehlungen“, F2a): Schweißbaugruppen zählen mit ihren Einzelteilen (Stück je Baugruppe × Baugruppen
je Satz), Rechtsklick auf Baugruppe oder Einzelteil öffnet das Fenster statt einer Fehlermeldung, die Kopfzeile eines
zugeklappten Satzes steht bei „Zusatzarbeiten …“ für den ganzen Satz, Rechtsklick auch im Reiter Kalkulation.

Aufruf: python tests/test_satz_zusatz.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import baugruppe, rechnen, satz_flaeche, satz_menge  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Z1 Rechnen ohne Oberfläche
BG = dict(art=BAUGRUPPE, baugruppe=json.dumps(dict(id="b1", name="Gestell")), satz="Gestell", je_satz=1,
          stueck=3, pos=100)
TEILE = [dict(art="Rohr", bg_knoten="b1", satz="Gestell", je_satz=2, stueck=6, pos=110),
         dict(art="Rohr", bg_knoten="b1/k1", satz="Gestell", je_satz=4, stueck=12, pos=120)]
LOSE = [dict(art="Rohr", satz="Regal", je_satz=4, stueck=20, pos=10), dict(art="Rohr", satz="Regal", je_satz=1,
                                                                            stueck=5, pos=20),
        dict(art="Rohr", pos=30, stueck=7)]
alle = [BG] + TEILE + LOSE
assert satz_menge.von(TEILE[0], alle) == "Gestell" and satz_menge.von(BG, alle) == "Gestell"
assert satz_menge.von(LOSE[0], alle) == "Regal" and satz_menge.von(LOSE[2], alle) == ""
assert satz_menge.von(dict(art="Rohr", bg_knoten="b1"), alle) == "Gestell"      # Teil ohne eigenen Satznamen
assert satz_menge.satz_positionen(alle, "Gestell") == []                          # früher: nichts gefunden
assert satz_menge.zusatz_positionen(alle, "Gestell") == [(1, 2), (2, 4)]           # Baugruppe selbst nicht
assert satz_menge.zusatz_positionen(alle, "Regal") == [(3, 4), (4, 1)]
assert satz_menge.zusatz_positionen(alle, "") == [] and satz_menge.zusatz_positionen(alle, "Fehlt") == []
ok("Z1 Satz einer Schweißbaugruppe: Einzelteile mit Stück je Baugruppe, Baugruppe selbst nicht; lose Sätze wie bisher")

# ------------------------------------------------------------------ Z2 Fenster im Programm
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
aid = beispiel_angebot.anlegen(db)
rohre = [p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil"]
for p, je in zip(rohre[:2], (2, 1)):
    db.position_aendern(p["id"], "satz", "Regal")
    db.position_aendern(p["id"], "je_satz", je)
    db.position_aendern(p["id"], "stueck", je * 4)
    db.position_aendern(p["id"], "zusatz", None)
bg_id = "bgtest01"
db.position_neu(aid, dict(art=BAUGRUPPE, pos=900, bezeichnung="Gestell", stueck=2,
                          baugruppe=json.dumps(dict(id=bg_id, name="Gestell"))))
for k, q in enumerate(rohre[2:4]):
    db.position_aendern(q["id"], "bg_knoten", bg_id)
    db.position_aendern(q["id"], "zusatz", None)
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
pos = s.positionen
i_bg = next(i for i, p in enumerate(pos) if rechnen.ist_baugruppe(p))
teile = baugruppe.teile(pos, bg_id)
name_bg = satz_menge.von(pos[teile[0]], pos)
assert name_bg and satz_menge.von(pos[i_bg], pos) == name_bg, (name_bg, pos[i_bg].get("satz"))
gesehen = []


def fenster_pruefen(d):
    gesehen.append(dict(titel=d.windowTitle(), pos=[p["id"] for p in d.satz["positionen"]], je=d.satz["je"],
                        info=d.satz_info.text()))
    r = d.hinzufuegen("Pulverbeschichten")
    assert r is not None
    d._ok()
    return d.result()


import rohrlaser.angebot_fenster as af  # noqa: E402
af.ZusatzDialog.exec = fenster_pruefen
for zeile in (i_bg, teile[0]):
    s.pos_ansicht.selectionModel().clearSelection()
    s.pos_ansicht.selectRow(zeile)
    s._pos_menue_anpassen()
    assert s.pos_aktionen["Zusatzarbeit für ganzen Satz …"].isVisible()
    gesehen.clear()
    assert s.zusatz_satz(zeile), fenster.statusBar().currentMessage()
    g = gesehen[0]
    assert g["titel"].startswith(f"Zusatzarbeiten für Baugruppe {name_bg}"), g
    assert sorted(g["pos"]) == sorted(s.positionen[t]["id"] for t in teile) and g["je"] == [1] * len(teile), g
for t in teile:
    assert "Pulverbeschichten" in [x["name"] for x in rechnen.zusatz_liste(s.positionen[t])]
assert not rechnen.zusatz_liste(s.positionen[i_bg])
m = satz_flaeche.mengen(s.positionen, name_bg, s.k)
assert m["flaeche"] > 0 and m["saetze"] == 2, m
ok("Z2 Rechtsklick auf Baugruppe bzw. Einzelteil: Fenster für alle Einzelteile (keine Fehlermeldung), Fläche je "
   "Baugruppe, 2 Baugruppen")

# ------------------------------------------------------------------ Z3 zugeklappter Satz und Kalkulation
s.satz_zu.add("Regal")
s.neu_laden()
kopf = next(r for r, n in s.satz_zeilen.items() if n == "Regal")
s.pos_ansicht.selectionModel().clearSelection()
s.pos_ansicht.selectionModel().select(s.pos_modell.index(kopf, 0),
                                      QItemSelectionModel.Select | QItemSelectionModel.Rows)
assert s._zusatz_zeilen()[1] == "Regal" and len(s._zusatz_zeilen()[0]) == 2
gesehen.clear()
assert s.zusatzarbeiten()
assert gesehen[0]["titel"].startswith("Zusatzarbeiten für Satz Regal (2 Positionen)") and gesehen[0]["je"] == [2, 1]
for p in s.positionen:
    if p.get("satz") == "Regal":
        assert "Pulverbeschichten" in [x["name"] for x in rechnen.zusatz_liste(p)]
s.satz_zu.discard("Regal")
s.neu_laden()
kopf = next(r for r, n in s.satz_zeilen.items() if n == "Regal")
s.pos_ansicht.selectionModel().clearSelection()
s.pos_ansicht.selectRow(kopf)
assert s._zusatz_zeilen() == ([kopf], None)                    # aufgeklappt: nur die Position
for ansicht, liste in ((s.kompakt_ansicht, s.kompakt), (s.kalk_ansicht, s.kalk)):
    r = next(r for r, z in enumerate(liste.zeilen) if isinstance(z, dict) and z.get("zeile") == kopf)
    ansicht.selectRow(r)
    zeilen = s.kalk_positionen(ansicht, liste)
    assert zeilen == [kopf], zeilen
    texte = [t for t, _ in s.kalk_menue_aktionen(zeilen)]
    assert texte == ["Zur Position", "Zusatzarbeiten …", "Zusatzarbeit für ganzen Satz …"], texte
assert s.kalk_menue_aktionen([]) == []
ok("Z3 Kopfzeile eines zugeklappten Satzes = ganzer Satz (aufgeklappt nur die Position); Rechtsklick in der "
   "Kalkulation (kompakt und alle Spalten)")
print("OK: Zusatzarbeit für ganzen Satz")
