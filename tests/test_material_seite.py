"""Prüft die Seite „Material“ in der Seitenleiste (Materialplattform, Patrick 23.11.2026): Liste, Suche, Filter,
Favoriten, Matrix, Detail-Reiter, Lieferantenpreis anlegen und übernehmen, Vergleich mit Verschnitt aus dem offenen
Angebot, Zuweisen an markierte Positionen, Mehrfach ändern, Archivieren, Export/Import, Prüfvorschläge.

Aufruf: python tests/test_material_seite.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import materialplattform as mp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.navigation import GRUPPE, SYMBOL, TIPP  # noqa: E402
from rohrlaser.symbole import PFADE  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
m = f.material
assert m.titel == "Material" and f.reiter.indexOf(m) >= 0
assert GRUPPE["Material"] == "Pflege" and SYMBOL["Material"] in PFADE and TIPP["Material"]
ok("Seite Material in der Seitenleiste (Pflege, eigenes Symbol, Tooltip)")

an = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(an)
m.neu_laden(erzwingen=True)
n_alle = len(m.alle_zeilen)
assert n_alle > 0 and m.modell.rowCount() == min(n_alle, 500)
assert any(mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219") for z in m.alle_zeilen)
ok(f"Liste: {n_alle} Materialien (mit Preis, Lieferant oder Verwendung)")

m.suche.setText("42,4x2")
m.anwenden()
assert m.sichtbar and all(z["profil_id"].startswith("RR 42,4") for z in m.sichtbar), [z["profil_id"] for z in m.sichtbar]
m.suche.setText("Rundrohr 42x2 S235")
m.anwenden()
assert any(z["profil_id"] == "RR 42,4x2,0" for z in m.sichtbar)
m.suche.setText("")
m.anwenden()
assert len(m.sichtbar) == n_alle
ok("Live-Suche: 42,4x2 und 'Rundrohr 42x2 S235' finden RR 42,4x2,0")

m.filter_setzen("form", {"Quadratrohr"})
assert m.sichtbar and all(z["form"] == "Quadratrohr" for z in m.sichtbar)
assert m.filter_baum.topLevelItemCount() > 0
m.filter_setzen("form", set())
assert len(m.sichtbar) == n_alle
ok("Filter Profilart mit Anzahl je Wert")

z = next(z for z in m.alle_zeilen if mp.schluessel(z) == ("QR 40x40x3", "S235-10219"))
assert m.auswaehlen("QR 40x40x3", "S235-10219")
m.favorit(m.aktuelle())
m.neu_laden(erzwingen=True)
m.modus_setzen("fav")
assert [mp.schluessel(z) for z in m.sichtbar] == [("QR 40x40x3", "S235-10219")]
m.modus_setzen("haeufig")
assert m.sichtbar and m.sichtbar[0]["nutzung"] >= 1
m.modus_setzen(None)
ok("Favorit setzen, Favoriten und Häufig")

assert m.auswaehlen("RR 42,4x2,0", "S235-10219")
assert "RR 42,4x2,0" in m.ueber.text() and "kg/m" in m.ueber.text()
assert m.verwendung.count() == 1                  # im Beispielangebot verwendet
ok("Detail: Übersicht mit Gewicht und Preis, Verwendung im Angebot")

# Lieferantenpreis anlegen und als aktiven Preis übernehmen
i = m.lieferant_neu(dict(lieferant="Stahlhandel Nord", basis="€/kg", preis="1,11", laenge="6000",
                         gueltig_bis="31.12.2026", lieferzeit="5", artikelnr="SN-4242"), dialog=lambda d: True)
assert i and m.lief_tabelle.rowCount() == 1 and m.detail.currentIndex() == 1
lz = db.zeilen(mp.LIEFERANTEN_TABELLE)[0]
assert (lz["lieferant"], lz["preis"], lz["laenge"], lz["artikelnr"]) == ("Stahlhandel Nord", 1.11, 6000, "SN-4242")
assert "Stahlhandel Nord" in db.kontext().zukauf_lieferanten
assert m.lieferant_uebernehmen(lz) in ("Preise", "Lieferlängen")
z = next(z for z in m.alle_zeilen if mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219"))
assert abs(z["preis_kg"] - 1.11) < 1e-9 and z["lieferant"] == "Stahlhandel Nord", z
ok("Lieferantenpreis angelegt (Lieferant in den Stamm) und als aktiver Preis übernommen")

# Vergleich mit Verschnitt bei den Teilen des offenen Angebots
m.tabelle.clearSelection()
paar = [z for z in m.alle_zeilen if z["profil_id"] == "RR 42,4x2,0"][:1] + \
       [z for z in m.alle_zeilen if z["profil_id"] == "QR 40x40x3"][:1]
v = m.vergleichen(paar, dialog=lambda d: d.tabelle.rowCount() > 3)
assert v and v["spalten"] and any(t.startswith("Verschnitt") for t, *_ in v["zeilen"]), v["zeilen"]
ok("Vergleich: zwei Materialien mit Verschnitt aus dem offenen Angebot")

# Zuweisen an markierte Positionen
assert m.offenes_angebot() is s
assert m.auswaehlen("QR 40x40x3", "S235-10219")
assert m.zuweisen(s, zeilen=[0]) == 1
assert s.positionen[0]["profil_id"] == "QR 40x40x3" and db.positionen(an)[0]["profil_id"] == "QR 40x40x3"
ok("Material an die markierte Position des offenen Angebots zugewiesen")

# Sprung aus dem Angebot: Positionsmenü „Material suchen und zuweisen …“
assert "Material suchen und zuweisen …" in s.pos_aktionen
s.pos_ansicht.selectRow(1)
assert s.material_plattform() is m and f.reiter.currentWidget() is m
assert m.auswahl.get("form") == {"Rundrohr"} and mp.schluessel(m.aktuelle()) == ("RR 42,4x2,0", "S235-10219")
assert m.offenes_angebot() is s
m.filter_setzen("form", set())
ok("Aus dem Angebot: Seite Material gefiltert auf die Profilart, Material der Position markiert")

# Mehrfach ändern (Preis +10 %)
m.tabelle.clearSelection()
assert m.auswaehlen("RR 42,4x2,0", "S235-10219")
vorher = next(z for z in m.alle_zeilen if mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219"))["preis_kg"]


def zehn_prozent(d):
    d.feld.setCurrentIndex(0)
    d.prozent.setValue(10)
    return True


assert m.mehrfach(dialog=zehn_prozent) == 1
nach = next(z for z in m.alle_zeilen if mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219"))["preis_kg"]
assert abs(nach - vorher * 1.1) < 1e-6, (vorher, nach)
ok("Mehrfach ändern: Preis +10 %")

# Duplizieren und Archivieren
assert m.auswaehlen("RR 48,3x2,6", "S235-10219")
assert m.duplizieren("RR 48,3x3,2", wand=3.2) == "RR 48,3x3,2"
assert "RR 48,3x3,2" in db.kontext().profile and db.kontext().profile["RR 48,3x3,2"]["wand"] == 3.2
assert m.archivieren("profile", "RR 48,3x3,2", True, frage=False)
assert "RR 48,3x3,2" not in db.kontext().auswahl("profil") and "RR 48,3x2,6" in db.kontext().auswahl("profil")
m.archiv_box.setChecked(True)
m.alle_box.setChecked(True)
assert any(z["profil_id"] == "RR 48,3x3,2" and z["archiviert"] for z in m.alle_zeilen)
m.archiv_box.setChecked(False)
assert not any(z["profil_id"] == "RR 48,3x3,2" for z in m.alle_zeilen)
m.alle_box.setChecked(False)
ok("Abmessung dupliziert (Wand 3,2) und archiviert (nur mit 'Archivierte zeigen')")

# Matrix
m.umschalter.setCurrentText("Matrix")
m.matrix_form.setCurrentText("Rundrohr")
m.matrix_fuellen()
assert m.matrix.rowCount() >= 2 and m.matrix.columnCount() >= 1
m._matrix_doppelklick(0, next(c for c in range(m.matrix.columnCount()) if m.matrix.item(0, c)))
assert m.umschalter.currentText() == "Liste" and m.aktuelle()["form"] == "Rundrohr"
ok("Matrix Abmessung × Werkstoff, Doppelklick springt in die Liste")

# Export und Preisliste importieren
pfad = tmp / "material.csv"
assert m.exportieren(pfad=str(pfad)) and pfad.read_text(encoding="utf-8-sig").count("\n") >= len(m.sichtbar)
liste = tmp / "preisliste.csv"
liste.write_text("Profil;Werkstoff;Preis;Basis;Länge;Gültig bis\nRR 42,4x2,0;S235-10219;1,05;€/kg;6000;31.12.2026\n"
                 "XY 1x1;S235-10219;1;€/kg;6000;\n", encoding="utf-8")
r = m.preisliste_importieren(str(liste), "Stahlhandel Süd", frage=False)
assert r["neu"] == 1 and len(r["fehler"]) == 1, r
assert m.auswaehlen("RR 42,4x2,0", "S235-10219") and m.lief_tabelle.rowCount() == 2
ok("CSV-Export und Preisliste importieren (unbekanntes Profil gemeldet, nicht angelegt)")

# Prüfvorschläge: günstigerer Lieferant wird vorgeschlagen, Übernehmen nur per Klick
befunde = m.pruefen(dialog=lambda d: True)
g = [b for b in befunde if "|guenstiger|" in b["schluessel"]]
assert not any("|dublette|RP " in b["schluessel"] or "|dichte|1.4016" in b["schluessel"] for b in befunde)
assert g, [b["schluessel"] for b in befunde]
assert next(z for z in m.alle_zeilen if mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219"))["lieferant"] == "Stahlhandel Nord"
ergebnis = []
m.pruefen(dialog=lambda d: ergebnis.append(d.uebernehmen(next(i for i, b in enumerate(d.befunde)
                                                               if "|guenstiger|" in b["schluessel"]))) or True)
assert ergebnis[0]
z = next(z for z in m.alle_zeilen if mp.schluessel(z) == ("RR 42,4x2,0", "S235-10219"))
assert z["lieferant"] == "Stahlhandel Süd" and abs(z["preis_kg"] - 1.05) < 1e-9
assert z["werkstoff_id"] == "S235-10219"
ok("Prüfvorschlag günstigerer Lieferant: erst nach Übernehmen geändert, Werkstoff bleibt")

# Spalten ein/aus bleibt gemerkt
from rohrlaser.material_seite import SPALTEN  # noqa: E402
i_norm = next(i for i, sp in enumerate(SPALTEN) if sp[0] == "norm")
m.spalte_setzen(i_norm, True)
assert "norm" in db.einstellung("material_spalten")
m.spalten_zuruecksetzen()
assert m.tabelle.isColumnHidden(i_norm)
ok("Spalten ein/aus gemerkt, 'wie ab Werk' setzt zurück")

# Tempo: 30.000 Varianten in der Liste (nur ein Block geladen)
viele = [dict(m.alle_zeilen[0], profil_id=f"RR {i}x2") for i in range(30000)]
t = time.perf_counter()
m.alle_zeilen = viele
m.suche.setText("S235")
m.anwenden()
dauer = time.perf_counter() - t
assert m.modell.rowCount() == 500 and len(m.sichtbar) == 30000 and dauer < 2.0, (dauer, len(m.sichtbar))
ok(f"30.000 Varianten: Suche und Liste {dauer:.2f} s, {m.modell.rowCount()} Zeilen geladen")

print("\nAlle Prüfungen der Seite Material bestanden.")
