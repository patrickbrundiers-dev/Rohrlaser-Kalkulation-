"""Prüft das Prüfen der Anbauteile im STEP-Import (anbau.py, Dialog 'Anbauteile prüfen', Spalte Anbauteile im
STEP-Prüfdialog, 3D-Vorschau Original / Rohrgeometrie / Gravurkonturen) mit den Teilen aus tests/step_anbau.

Aufruf: python tests/test_anbau_pruefen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import anbau, step  # noqa: E402
from rohrlaser.ansicht3d import MODI, gefiltert, mit_anbau  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def messwerte(name):
    netze = Path(tempfile.mkdtemp(dir=tmp))
    mw = [dict(zip(step_messen.SPALTEN, z)) for z in step_messen.zeilen(HIER / "step_anbau" / f"{name}.step", netze)]
    return step.lade_netze(mw, netze)


def nah(ist, soll, was, tol=0.01):
    assert abs(float(ist) - soll) <= tol, f"{was}: {ist}, soll {soll}"


# 1) anbau.py: Gravurlänge je Bearbeitung, Unterschied, Kurztext
bolzen = dict(art="Bolzen", aufstand=dict(form="Kreis", umfang=62.83, durchmesser=20), bearbeitung="Positionsmarke",
              gravur_laenge=20.0, vertrauen="sicher", z=300, winkel=0)
kopf = dict(art="Kopfplatte", aufstand=None, bearbeitung="keine", gravur_laenge=0.0, vertrauen="prüfen", seite="Ende A")
liste = anbau.lesen(json.dumps([bolzen, kopf]))
assert [a["status"] for a in liste] == ["offen", "offen"]
assert [anbau.laenge(bolzen, b) for b in anbau.BEARBEITUNGEN] == [62.83, 20.0, 4.0, 0.0]
assert anbau.bearbeitungen(kopf) == ["Positionsmarke", "Punktmarke", "keine"]      # ohne Aufstand kein Umriss
assert anbau.vorgabe(kopf, "Lasche") == "Positionsmarke" and anbau.vorgabe(bolzen, "Mutter") == "Umriss"
assert anbau.kurz(liste) == "1 Bolzen, 1 Kopfplatte – 1 prüfen" and anbau.offen(liste) == 1
assert anbau.lage_text(bolzen) == "z 300 mm, 0°" and anbau.lage_text(kopf) == "Ende A"
assert anbau.aufstand_text(bolzen) == "Kreis Ø 20" and anbau.aufstand_text(kopf) == "keine"
neu = [dict(liste[0], status=anbau.AUSGESCHLOSSEN), dict(liste[1], status=anbau.BESTAETIGT)]
assert anbau.anwenden({"gravur": 120.0, "gravur_anbau": 20.0, "gravur_konturen": 3}, liste, neu) == \
    {"gravur": 100.0, "gravur_anbau": 0.0, "gravur_konturen": 2}
assert anbau.anwenden({"gravur": 5.0}, liste, neu) == {"gravur": 0.0}           # nie negativ, nur vorhandene Felder
assert anbau.kurz(neu) == "1 Kopfplatte, 1 ausgeschlossen" and anbau.offen(neu) == 0
print("OK     anbau.py")

# 2) Messwerte: Gravur um den Unterschied, unsichere entschieden = Anbauteile geprüft
m = messwerte("A11_RE60x40x3_Kopfplatte_Mutter_Ecke")[0]
assert step.unsicher(m) == ["anbauteile"] and not step.gewaehlt(m)
alt = anbau.lesen(m["anbauteile"])
gravur = float(m["gravur"])
ecke = next(i for i, a in enumerate(alt) if anbau.unsicher(a))
w = [dict(a, status=anbau.BESTAETIGT) for a in alt]
w[ecke].update(art="Lasche", bearbeitung="Positionsmarke", gravur_laenge=anbau.MARKE)
step.anbau_setzen(m, w)
nah(m["gravur"], gravur - alt[ecke]["gravur_laenge"] + anbau.MARKE, "Gravur nach Prüfung")
assert step.unsicher(m) == [] and "anbauteile=geprüft" in m["sicherheit"] and step.gewaehlt(m)
assert anbau.lesen(m["anbauteile"])[ecke]["art"] == "Lasche"
print("OK     Messwerte: Gravur um den Unterschied, Erkennung geprüft")

# 3) Messung ohne Trennung als Alternative, Art-Auswahl mit Zusatz
m = messwerte("A02_RE60x40x3_Bolzen")[0]
assert m["profilform"] == "Rechteckrohr" and step.ohne_trennung_text(m).startswith("Sonderprofil")
a2 = step.alternative(m)
assert step.art_text(m, a2) == "Rechteckrohr – Anbauteile abgetrennt" and step.art_text(a2, m) == "Sonderprofil – ohne Trennung"
print("OK     Messung ohne Trennung wählbar")

# 4) 3D-Vorschau: Original mit Anbauteilen, Rohrgeometrie ohne, Gravurkonturen nur Gravurlinien
from rohrlaser.ansicht3d import entpacken  # noqa: E402
netz = entpacken(m["_netz"])
assert mit_anbau(netz) and "AN" in netz["t"] and "GA" in netz["l"]
assert gefiltert(netz, MODI[0]) is netz
rohr, grav = gefiltert(netz, "Rohrgeometrie"), gefiltert(netz, "Gravurkonturen")
assert "AN" not in rohr["t"] and "GA" not in rohr["l"] and "EA" in rohr["l"]
assert "AN" not in grav["t"] and set(grav["l"]) <= {"G", "GA"} and "GA" in grav["l"]
print("OK     3D-Vorschau gefiltert")

# 5) Prüfdialog: Spalte Anbauteile, Dialog 'Anbauteile prüfen', Übernehmen, Messung ohne Trennung, 3D-Knöpfe
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
from rohrlaser.anbau_dialog import OHNE_TRENNUNG  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
mw = messwerte("A11_RE60x40x3_Kopfplatte_Mutter_Ecke") + messwerte("A02_RE60x40x3_Bolzen")
d = StepPruefDialog(None, mw, k, "S235-10219", 1)
z = d.zeilen[0]
assert z.it.text(d.SP_ANBAU) == "1 Sonstiges, 1 Kopfplatte, 1 Mutter – 1 prüfen", z.it.text(d.SP_ANBAU)
assert z.it.background(d.SP_ANBAU).color().name() == "#ffeb9c" and z.it.checkState(0) == Qt.Unchecked
assert d.ansicht.modi.isVisibleTo(d.ansicht)                  # Teil mit Anbauteilen: Knöpfe der Vorschau
d.ansicht.modus_setzen("Rohrgeometrie")
assert "AN" not in d.ansicht.ansicht.modell.arten
d.ansicht.modus_setzen("Original")
dlg = d.anbau_pruefen(0, dialog=True)
assert dlg.tabelle.rowCount() == 3 and dlg.ohne.isEnabled()
nr = next(i for i, a in enumerate(dlg.liste) if anbau.unsicher(a))
dlg.setzen(nr, art="Lasche")                                   # Art -> Vorgabe-Bearbeitung und Länge
assert dlg.bearbeitung[nr].currentText() == "Umriss"
dlg.setzen(nr, bearbeitung="Punktmarke")
assert dlg.laengen[nr].value() == anbau.PUNKT
assert "noch offen" in dlg.auswirkung.text()
dlg.alle_bestaetigen()
assert "noch offen" not in dlg.auswirkung.text()
dlg.accept()
vorher = float(mw[0]["gravur"])
z = d.anbau_uebernehmen(0, dlg.ergebnis)
nah(mw[0]["gravur"], vorher - dlg.alt[nr]["gravur_laenge"] + anbau.PUNKT, "Gravur nach Dialog")
assert z.it.checkState(0) == Qt.Checked and "prüfen" not in z.it.text(d.SP_ANBAU)
# zweite Datei: 'Ist kein Anbauteil' = Messung ohne Trennung gilt
d.datei_waehlen(1)
i = next(i for i, m in enumerate(mw) if m["datei"].startswith("A02"))
z = d.anbau_uebernehmen(i, OHNE_TRENNUNG)
assert mw[i]["profilform"] == "Sonderprofil" and not mw[i]["anbauteile"] and not z.it.text(d.SP_ANBAU)
assert d.baum.itemWidget(z.it, d.SP_ART).currentText() == "Sonderprofil – ohne Trennung"
z = d.art_wechseln(i)                                         # zurück: wieder abgetrennt
assert mw[i]["profilform"] == "Rechteckrohr" and z.it.text(d.SP_ANBAU) == "1 Bolzen"
d.accept()
print("OK     Prüfdialog mit Anbauteilen")

# 6) Angebot: Übernahme mit Anbauteilen, Gravur Anbauteile getrennt (ohne Doppelzählung), Prüfzeit, Status, Dialog
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
mw = messwerte("A11_RE60x40x3_Kopfplatte_Mutter_Ecke")
mw[0]["_uebernehmen"] = True                                   # unsichere Erkennung angehakt (F5 a)
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 10, neue_profile=True)
(p,) = erg["positionen"]
liste = anbau.lesen(p["anbauteile"])
assert len(liste) == 3 and anbau.offen(liste) == 1 and "Anbauteile: " in erg["bericht"][0], erg["bericht"]
nah(rechnen.gravur_anbau(p), anbau.gravur(liste), "Gravur Anbauteile der Position")
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
pid = db.position_neu(a, {n: v for n, v in p.items() if not n.startswith("_")       # Bohrbild hier nicht prüfen
                          and n not in ("bohrbild", "gewinde_vorschlag")})
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
w = rechnen.position_werte(pos[0], kopf, k, tab)
assert rechnen.status(pos[0], w, kopf, k) == "HINWEIS: Anbauteile prüfen (Doppelklick)", rechnen.status(pos[0], w, kopf, k)
erg_opt = rechnen.optimieren(kopf, pos, k, tab)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
(z0,), s0 = rechnen.kalkulation(kopf, pos, erg_opt, k, tab, dict(einst, pruefzeit_anbau=0))
_, _, summe = rechnen.schneidzeit(pos[0], kopf, w["wand_schneiden"], tab, k)
anteile = rechnen.zeitanteile(pos[0], (z0["vorschub_gross"], z0["vorschub_mittel"], z0["vorschub_klein"],
                                       z0["vorschub_gravur"], z0["einstechzeit"]))
nah(anteile["gravur"] + anteile["gravur_anbau"], 60 * pos[0]["gravur"] / z0["vorschub_gravur"], "Gravur gesamt")
nah(sum(anteile.values()), summe, "Summe der Zeitanteile = Schneidzeit (nichts doppelt)")
nah(z0["zeit_gravur_anbau"], 60 * anbau.gravur(liste) / z0["vorschub_gravur"], "Zeit Gravur Anbauteile")
assert z0["zeit_pruefung"] == 0 and s0["pruefung_anbau"] == 0 and s0["gravur_anbau"] > 0
(z1,), s1 = rechnen.kalkulation(kopf, pos, erg_opt, k, tab, dict(einst, pruefzeit_anbau=2))
assert z1["zeit_pruefung"] == 120 and nah(z1["laser_netto"] - z0["laser_netto"], 120, "Prüfzeit in der Laserzeit") is None
nah(s1["laser_schneiden"] - s0["laser_schneiden"], s1["pruefung_anbau"], "Prüfzeit-Kosten in Laser schneiden")
text = next(t for t, w_, _ in rechnen.kostenarten(s1, einst) if t.startswith("Laser schneiden"))
assert "davon Gravur Anbauteile" in text and "Prüfzeit Anbauteile" in text, text
punkte = rechnen.freigabe_punkte(kopf, pos, [rechnen.status(pos[0], w, kopf, k)], "aktuell", s1)
assert ("WARNUNG", "1 Position: Anbauteile ungeprüft") in punkte, punkte
fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
seite = fenster.angebot_oeffnen(a)
pm = seite.pos_modell
c = next(i for i, (art, f) in enumerate(pm.spalten) if art == "anbau")
assert pm.data(pm.index(0, c)) == anbau.kurz(liste) and "Doppelklick: Anbauteile prüfen" in pm.data(pm.index(0, c), Qt.ToolTipRole)
assert not seite.pos_ansicht.isColumnHidden(c)                # optionale Spalte mit Wert sichtbar
neu = [dict(x, status=anbau.AUSGESCHLOSSEN if anbau.unsicher(x) else anbau.BESTAETIGT) for x in liste]
gravur_vorher = db.positionen(a)[0]["gravur"]
assert seite.anbauteile_pruefen([0], werte=neu)
p2 = db.positionen(a)[0]
nah(p2["gravur"], gravur_vorher - next(x["gravur_laenge"] for x in liste if anbau.unsicher(x)), "Gravur nach Ausschließen", 0.06)
assert anbau.offen(anbau.lesen(p2["anbauteile"])) == 0 and "Anbauteile" not in pm.status[0], pm.status
(z2,), _ = rechnen.kalkulation(kopf, db.positionen(a), erg_opt, k, tab, dict(einst, pruefzeit_anbau=2))
assert z2["zeit_pruefung"] == 0                               # unsicheres ausgeschlossen: keine Prüfzeit mehr
seite.close()
print("OK     Angebot: Anbauteile, Gravur Anbauteile, Prüfzeit, Status, Dialog")

# 7) Angeschweißte eigene Körper: Option 'Anbauteile nicht ins Angebot übernehmen' (Vorgabe an)
mw = messwerte("A08_RE60x40x3_Anbau_eigene_Koerper")
assert set(step.anbau_von(mw)) == {1, 2}, step.anbau_von(mw)
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True, zukauf_liste=[])
assert len(erg["positionen"]) == 1 and "Anbauteil von" in erg["bericht"][2], erg["bericht"]
d = StepPruefDialog(None, mw, k, "S235-10219", 1, [])
assert d.anbau_weg.isVisibleTo(d) and d.anbau_weg.isChecked()
blech_zeile = next(z for z in d.zeilen if z.blech)
assert blech_zeile.it.checkState(0) == Qt.Unchecked and "Anbauteil von" in blech_zeile.it.text(d.SP_HINWEIS)
d.anbau_weg.setChecked(False)                                  # aus: Blech wird wieder Zukaufteil
blech_zeile = next(z for z in d.zeilen if z.blech)
assert blech_zeile.it.checkState(0) == Qt.Checked and "Anbauteil von" not in blech_zeile.it.text(d.SP_HINWEIS)
d.werte_schreiben()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True, zukauf_liste=[])
# Rohr, Bolzen (Rundstahl, seit 0.9.121 Zukaufteil wie das Blech) und Blech
assert len(erg["positionen"]) == 3 and "Rundstahl Ø8" in erg["bericht"][1], erg["bericht"]
d.anbau_weg.setChecked(True)
d.werte_schreiben()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True, zukauf_liste=[])
assert len(erg["positionen"]) == 1, erg["bericht"]
d2 = StepPruefDialog(None, messwerte("A02_RE60x40x3_Bolzen"), k, "S235-10219", 1, [])
assert not d2.anbau_weg.isVisibleTo(d2)                        # ohne eigene Anbau-Körper keine Option
print("OK     Option 'Anbauteile nicht ins Angebot übernehmen'")
print("Alle Prüfungen bestanden.")
