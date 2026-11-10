"""Alle Editoren gleich aufgebaut (Vorschlag N1/E4, Patrick 07.11.2026): Schweißbaugruppe und Satz in 3D im selben
Rahmen wie Rohr- und Blech-Editor (gruppen_rahmen): Menüband mit Konstruktion/Ansicht/Ausgabe, links Struktur, Mitte
3D mit den Reitern darunter, rechts Ergebnis, unten Kacheln und Prüfmeldungen; Knöpfe der alten Fußleiste im Band.

Aufruf: python tests/test_editoren_gleich.py
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import baugruppe, dfm, vorkalk  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.gruppen_rahmen import stufe  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


assert stufe("FEHLER: x") == dfm.FEHLER and stufe("hinweis: y") == dfm.HINWEIS and stufe("irgendwas") == dfm.WARNUNG
ok("Stufe einer Meldung aus ihrem Anfang (ohne Kennung: Warnung)")

teile = [dict(id=1, pos=10, artikel="Stiel", profil_id="QR 40x40x3", laenge=1000, stueck=2),
         dict(id=2, pos=20, artikel="Riegel", profil_id="QR 40x40x3", laenge=500, stueck=2)]
d = BaugruppeDialog(None, dict(pos=900, stueck=2), teile, baugruppe.richtwerte(), {"Schweißen": 75.0}, {1, 2})
d.resize(1400, 860)
d.show()
app.processEvents()
r = d.rahmen
assert [r.band.leiste.tabText(i) for i in range(r.band.leiste.count())] == ["Konstruktion", "Ansicht", "Ausgabe"]
kon = r.band.reiter("Konstruktion").gruppen
assert list(kon)[0] == "Bearbeiten" and "Zurücksetzen" in kon["Bearbeiten"].knoepfe
for g, k in (("Vorkalkulation", "Vorkalkulation rechnen"), ("Vorkalkulation", "Vorschläge bestätigen"),
             ("Naht zeichnen", "Naht zeichnen"), ("Auswahl im 3D", "Steckverbindung hinzufügen")):
    assert k in kon[g].knoepfe, (g, list(kon[g].knoepfe))
assert "STEP speichern …" in r.band.reiter("Ausgabe").gruppen["Ausgabe"].knoepfe
ok("Schweißbaugruppe: Menüband Konstruktion/Ansicht/Ausgabe, Bearbeiten zuerst, Fußknöpfe im Band")

w = r.waagerecht
assert w.count() == 3 and w.widget(0) is d.baum_links and w.widget(1) is r.mitte and w.widget(2) is r.rechts
assert d.reiter.isVisible() and r.tabelle_bereich.widget() is d.reiter
assert [d.reiter.tabText(i) for i in range(d.reiter.count())][-1] == "Übersicht"   # kein Reiter „Strukturbaum“
assert d.baum.isVisible() and d.baum.topLevelItemCount() == 1
assert r.platzhalter.isVisible() and d.ansicht3d is None         # ohne STEP: Hinweis statt 3D
assert not d.zeichnen_knopf.isEnabled() and not d.auswahl_steck.isEnabled()
ok("Schweißbaugruppe: Baum links, 3D (ohne STEP: Hinweis) mit Reitern darunter, Ergebnis rechts; 3D-Werkzeuge aus")

r.auffrischen()
titel = [k.titel.text() for k in r.leiste_unten.kacheln if k.isVisible()]
assert titel == ["Je Baugruppe", "Zeit je Baugruppe", "davon Schweißen", "Einzelteile", "Vorschläge offen"], titel
assert r.leiste_unten.kacheln[3].wert.text() == "2"
texte = [r.meldungen_liste.item(i).text() for i in range(r.meldungen_liste.count())]
assert texte and all(stufe(t) in (dfm.FEHLER, dfm.WARNUNG, dfm.HINWEIS) for t in texte), texte
gesprungen = []
r._springen = gesprungen.append
r._meldung_geklickt(r.meldungen_liste.item(0))
assert gesprungen == [texte[0]]
ok(f"Kacheln (Kosten, Zeit, Schweißen, Einzelteile) und {len(texte)} Prüfmeldung(en), Klick springt zur Zeile")

# Plan Schweißbaugruppe 10.11.2026, Schritt 3 (Layout)
from rohrlaser.baugruppe_dialog import BaugruppeDialog as _BD  # noqa: E402

d.show()
app.processEvents()
r.platz_3d()
oben, unten = r.mitte.sizes()
assert oben <= r.PLATZHALTER_HOEHE + 5 < unten, (oben, unten)          # L2: ohne 3D bekommen die Eingaben die Höhe
sp = [x.schluessel for x in d.naht_tab.spalten]
sichtbar = [x for c, x in enumerate(sp) if not d.naht_tab.isColumnHidden(c)]
assert not d.naht_alle.isChecked() and sichtbar == list(_BD.NAHT_GRUND), sichtbar      # L1: Grundansicht
assert "ausgeblendet" in d.naht_spalten_info.text()
d.naht_alle.setChecked(True)
assert not any(d.naht_tab.isColumnHidden(c) for c in range(len(sp))) and d.naht_spalten_info.text() == ""
d.naht_alle.setChecked(False)
assert d.naht_tab.isColumnHidden(sp.index("lage")) and not _BD.NAHT_ALLE_SPALTEN
if d.bg["naehte"]:
    d.naht_tab.selectRow(0)
    assert f"Nahtgruppe {d.bg['naehte'][0].get('nr') or ''}" in d.naht_weg.text()
assert d.balken_rechts.teile and "<table" in d.summe.text() and "Schweißen und Arbeitsgänge" in d.summe.text()   # L3
r.auffrischen()
assert r.leiste_unten.kacheln[4].wert.text() == str(vorkalk.offen(d.bg))                    # L4
ok("Layout: 3D-Fläche ohne STEP zugeklappt, Nahtgruppen in Grundansicht mit Schalter 'Alle Spalten' und Detailfeld, "
   "Ergebnis als Zeilen mit Kostenbalken, Kachel 'Vorschläge offen'")

d.anzahl.setValue(5)
d.knoten_neu("Konsole", 2)
r.auffrischen()
assert d.baum.topLevelItem(0).childCount() >= 1
ok("Strukturbaum zieht nach einer Eingabe nach (Unterbaugruppe erscheint ohne Reiterwechsel)")
d.reject()
print("Alle Editoren gleich aufgebaut: alle Tests bestanden.")
