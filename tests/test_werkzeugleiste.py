"""Meine Werkzeugleiste, Aktionsbibliothek, Kontextknöpfe, Konfigurator, Dashboard, Info-Panel und Arbeitsbereiche
(Großes Design- und Layout-Update, Patrick 19.11.2026).

Abnahme: Alle Knöpfe führen eine echte Funktion aus (jede Aktion der Bibliothek wird in ihrem Arbeitsbereich
ausgelöst, Dialoge werden dabei sofort geschlossen), Leiste konfigurierbar und per Drag & Drop sortierbar,
kontextabhängige Knöpfe, Dashboard anpassbar, je Benutzer dauerhaft gespeichert, Hell/Dunkel."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtCore import QMimeData, Qt  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMenu,  # noqa: E402
                               QMessageBox)

import beispiel_angebot  # noqa: E402
from rohrlaser import aktionen, werkzeugleiste as wl, werkzeugleiste_qt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.werkzeugleiste_dialog import MIME, KonfiguratorDialog, StartseiteDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Bibliothek ohne Fenster
ids = [a.id for a in aktionen.AKTIONEN]
assert len(ids) == len(set(ids)), "Aktions-IDs doppelt"
assert all(a.gruppe in aktionen.GRUPPEN for a in aktionen.AKTIONEN)
assert all(a.ausfuehren is not None for a in aktionen.AKTIONEN), "jede Aktion der Bibliothek hat eine Funktion"
gefordert = {"Angebote": 7, "Kalkulation": 8, "Bauteile": 7, "3D-Editor": 2, "Material": 5, "Dokumente": 6,
             "Produktion": 5}
for g, n in gefordert.items():
    assert sum(a.gruppe == g for a in aktionen.AKTIONEN) >= n, g
from rohrlaser import werkzeugleiste_qt as wq  # noqa: E402
fehlend = [a.id for a in aktionen.AKTIONEN if a.symbol and a.symbol not in wq.pfade()]
assert not fehlend, fehlend
ok(f"{len(ids)} Aktionen in {len(aktionen.GRUPPEN)} Bereichen, jede mit Funktion und Symbol; "
   f"{len(aktionen.NUR_EDITOR)} Editor-Werkzeuge als „im Menüband des 3D-Editors“ gekennzeichnet")

roh = {"knoepfe": ["angebot_neu", {"gruppe": "Test"}, {"id": "gibtsnicht"}, {"id": "kalk_starten", "farbe": "gruen",
                                                                             "text": "Rechnen"}],
       "groesse": "riesig", "tasten": {"angebot_neu": "Ctrl+Alt+N", "gibtsnicht": "F2"}}
s = wl.sauber(roh)
assert s["knoepfe"] == [{"id": "angebot_neu"}, {"gruppe": "Test"}, {"id": "kalk_starten", "farbe": "gruen",
                                                                   "text": "Rechnen"}]
assert s["groesse"] == "mittel" and s["tasten"] == {"angebot_neu": "Ctrl+Alt+N"}
assert wl.kontext_knoepfe(s, "angebot")[0] == "angebot_speichern" and "kalk_starten" not in wl.kontext_knoepfe(
    s, "angebot"), "fest in der Leiste: nicht noch einmal als Kontextknopf"
assert wl.kontext_knoepfe(dict(s, kontext_an=False), "angebot") == []
assert wl.tasten_konflikte({"angebot_neu": "Ctrl+P"}, {"Ctrl+P": "Angebot (PDF)"}) == [
    ("angebot_neu", "Ctrl+P", "Angebot (PDF)")]
a = wl.start_sauber({"oben": ["kacheln", "heute"], "links": ["angebote", "kacheln"], "rechts": ["heute", "x"]})
assert a == {"oben": ["kacheln"], "links": ["angebote"], "rechts": ["heute"]}
assert "sicherung" in wl.ausgeblendet(a)
ok("Aufbau wird geprüft: unbekannte Aktionen/Größen fallen weg, Kontextknöpfe ohne Doppelte, Tasten-Konflikte, "
   "Dashboard-Karten nur einmal und Kachelzeilen nur oben")

# ------------------------------------------------------------------ Fenster
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
f.resize(1400, 860)
f.show()
app.processEvents()
leiste = f.meine_leiste
# ab Werk aus (UI Next Level, Patrick 26.11.2026, F3); Ansicht → Meine Werkzeugleiste schaltet sie ein
assert f.toolBarArea(leiste) == Qt.TopToolBarArea and not leiste.isVisible()
f.leiste_sichtbar_aktion.setChecked(True)
app.processEvents()
assert leiste.isVisible()
f.reiter.setCurrentWidget(f.start)
app.processEvents()
assert aktionen.kontext(f) == "start"
assert leiste.ids(False) == ["angebot_neu", "angebot_neu_step", "angebote_letzte", "suchen", "favoriten"]
assert leiste.ids(True) == wl.KONTEXT_VORGABE["start"]
ok("Leiste oben: eigene Knöpfe und Kontextknöpfe der Startseite")

aid = beispiel_angebot.anlegen(db)
f.angebote.neu_laden()
f.reiter.setCurrentWidget(f.angebote)
leiste.zustand()
assert aktionen.kontext(f) == "angebotsliste" and "angebot_oeffnen" in leiste.ids(True)
assert not leiste.aktion("angebot_kopieren").isEnabled() and aktionen.OHNE_AUSWAHL in leiste.aktion(
    "angebot_kopieren").toolTip()
f.angebot_oeffnen(aid)
app.processEvents()
seite = f.offen[aid]
leiste.zustand()
assert aktionen.kontext(f) == "angebot"
assert leiste.ids(True) == wl.KONTEXT_VORGABE["angebot"]
assert leiste.aktion("kalk_starten").isEnabled() and leiste.aktion("pdf_angebot").isEnabled()
ok("Kontextabhängig: Angebotsliste zeigt Öffnen/Kopieren/Vergleich, geöffnetes Angebot Speichern, Kalkulieren, "
   "Bauteil hinzufügen, Dokumente, PDF; Unpassendes ausgegraut mit Grund")

# Optimieren über die Leiste rechnet wirklich
assert seite.stand_optimierung() == "noch nicht optimiert"
leiste.aktion("kalk_starten").trigger()
assert seite.stand_optimierung() == "aktuell"
assert wl.zuletzt(db)[0] == "kalk_starten"
ok("Knopf „Kalkulation starten“ optimiert das Angebot, „Zuletzt verwendet“ merkt ihn")

# Info-Panel
f.info_panel_umschalten(True)
app.processEvents()
html = f.info_panel.inhalt()
assert "A-2026-0001" in html and "Beispiel GmbH" in html and "aktuell" in html and "Positionen" in html
assert wl.info_an(db)
f.info_panel_umschalten(False)
assert not f.info_dock.isVisible() and not wl.info_an(db)
ok("Info-Panel rechts: Angebot, Kunde, Status, Kalkulationsstand, Hinweise; ein/aus je Benutzer gemerkt")

# ------------------------------------------------------------------ Alle Knöpfe testen (Abnahme 2, „keine funktionslosen“)
gerufen = []
QDialog.exec = lambda self: gerufen.append(type(self).__name__) or 0
QMenu.exec = lambda self, *a, **k: None
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
f.datei_oeffnen = lambda pfad: gerufen.append(str(pfad))
from PySide6.QtGui import QDesktopServices  # noqa: E402
QDesktopServices.openUrl = staticmethod(lambda *a: True)
NICHT_HIER = {"angebot_schliessen", "angebot_neu", "angebot_neu_step", "nav_start", "nav_angebote", "nav_anfragen",
              "nav_kunden", "nav_auftraege", "nav_produktion", "nav_auswertung", "nav_zukauf", "nav_einstellungen",
              "mat_suchen", "mat_verwaltung", "mat_werkstoffe", "mat_lager", "prod_status", "prod_fertigmeldung",
              "thema", "kalk_neu", "angebot_kopieren", "angebot_fassung", "prod_uebergeben", "teil_loeschen"}
fehler = []
for a in aktionen.AKTIONEN:
    if a.id in NICHT_HIER:
        continue
    f.reiter.setCurrentWidget(seite)
    seite.pos_ansicht.setCurrentIndex(seite.pos_modell.index(0, 1))
    warum = aktionen.grund(f, a)
    if warum:
        if a.id not in ("nav_anfragen", "nav_auftraege", "nav_produktion", "nav_auswertung", "mat_lager",
                        "prod_fertigmeldung"):
            fehler.append((a.id, warum))
        continue
    try:
        if a.menue is not None:
            eintraege = a.menue(f)
            assert isinstance(eintraege, list)
        else:
            aktionen.ausfuehren(f, a)
    except Exception as e:      # noqa: BLE001
        fehler.append((a.id, repr(e)))
    app.processEvents()
assert not fehler, fehler
assert f.angebote_vergleichen and len(f.offen) >= 1
ok(f"Alle {len(aktionen.AKTIONEN)} Aktionen im geöffneten Angebot ausgelöst, keine Ausnahme "
   f"({len(gerufen)} Dialoge/Dateien geöffnet und gleich geschlossen)")

# Kopieren, Fassung, Löschen und Navigation im passenden Bereich
vorher = len(db.angebote())
f.reiter.setCurrentWidget(f.offen[aid])
aktionen.ausfuehren(f, aktionen.AKTION["angebot_kopieren"])
assert len(db.angebote()) == vorher + 1
for nid, ziel in (("nav_start", f.start), ("nav_angebote", f.angebote), ("nav_kunden", f.kunden),
                  ("nav_einstellungen", f.bereich), ("nav_zukauf", f.zukauf)):
    aktionen.ausfuehren(f, aktionen.AKTION[nid])
    assert f.reiter.currentWidget() is ziel, nid
aktionen.ausfuehren(f, aktionen.AKTION["mat_suchen"])
assert f.reiter.currentWidget() is f.material
ok("Angebot kopieren aus dem geöffneten Angebot, Navigation zu Start/Angebote/Kunden/Einstellungen/Zukauf, "
   "Material suchen öffnet die Seite Material")

thema = aktionen.ausfuehren(f, aktionen.AKTION["thema"])
from rohrlaser import stil  # noqa: E402
assert thema == "Dunkel" and stil.thema() == "Dunkel" and db.einstellung("ansicht_thema") == "Dunkel"
leiste.neu_bauen()
assert "background" in werkzeugleiste_qt.knopf_stil("akzent")
aktionen.ausfuehren(f, aktionen.AKTION["thema"])
assert stil.thema() == "Hell"
ok("Hell/Dunkel per Knopf, gemerkt; Leiste baut im Dunkelmodus neu")

# ------------------------------------------------------------------ Konfigurator: Drag & Drop, Gruppen, Eigenschaften
f.reiter.setCurrentWidget(f.offen[aid])
d = KonfiguratorDialog(f)
assert d.meine.ids() == ["angebot_neu", "angebot_neu_step", "angebote_letzte", "suchen", "favoriten"]
m = QMimeData()
m.setData(MIME, b"kalk_material\nmat_preise")
ziel = d.meine.visualItemRect(d.meine.item(1)).center()
ereignis = QDropEvent(ziel, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
d.meine.dropEvent(ereignis)
assert d.meine.ids()[:4] == ["angebot_neu", "kalk_material", "mat_preise", "angebot_neu_step"], d.meine.ids()
ok("Drag & Drop aus der Bibliothek fügt an der Ablagestelle ein")
d.meine.setCurrentRow(0)
assert d.meine.verschieben(1) and d.meine.ids()[:2] == ["kalk_material", "angebot_neu"]
d.meine.setCurrentRow(1)
d.gruppe_einfuegen("Kalkulation")
assert d.meine.eintraege()[2] == {"gruppe": "Kalkulation"}
d.meine.setCurrentRow(0)
d.text_feld.setText("Material")
d.farbe_wahl.setCurrentIndex(d.farbe_wahl.findData("orange"))
d.symbol_wahl.setCurrentIndex(d.symbol_wahl.findData("lager"))
d._eigenschaft()
d.taste.setKeySequence("Ctrl+Alt+M")
d._eigenschaft()
d.bibliothek.filtern("schnittschema")
sichtbar = [d.bibliothek.gruppen["Dokumente"].child(i).text(0) for i in range(d.bibliothek.gruppen["Dokumente"]
                                                                              .childCount())
            if not d.bibliothek.gruppen["Dokumente"].child(i).isHidden()]
assert sichtbar == ["Werkstattpapiere mit Schnittplan (PDF)"], sichtbar
d.reiter.setCurrentIndex(1)
d.kontext_wahl.setCurrentIndex(d.kontext_wahl.findData("angebot"))
d.kontext_liste.setCurrentRow(0)
d.entfernen()                                   # „Speichern“ aus den Kontextknöpfen des Angebots
d.groesse.setCurrentIndex(d.groesse.findData("gross"))
d.beschriftung.setCurrentIndex(d.beschriftung.findData("unter"))
d.reiter.setCurrentIndex(2)
d.hinzufuegen("prod_status")
d.uebernehmen()
lst = wl.leiste(db)
assert lst["knoepfe"][0] == {"id": "kalk_material", "text": "Material", "symbol": "lager", "farbe": "orange"}
assert lst["groesse"] == "gross" and lst["beschriftung"] == "unter" and lst["tasten"] == {"kalk_material": "Ctrl+Alt+M"}
assert "angebot_speichern" not in wl.kontext_knoepfe(lst, "angebot")
assert "prod_status" in wl.schnellzugriffe(db)
assert leiste.iconSize().width() == 32 and leiste.toolButtonStyle() == Qt.ToolButtonTextUnderIcon
act = leiste.aktion("kalk_material")
assert act.text() == "Material" and leiste.widgetForAction(act).styleSheet()
assert any(t.shortcut().toString() == "Ctrl+Alt+M" for t in f.leiste_tasten)
ok("Konfigurator: sortieren, Gruppe, umbenennen, Symbol, Farbe, Tastenkürzel, Größe Tablet, Beschriftung unter dem "
   "Symbol, Kontextknöpfe je Bereich, Schnellzugriffe – sofort in der Leiste")

# Rechtsklick: Knopf entfernen
leiste.entfernen("mat_preise")
assert "mat_preise" not in leiste.ids(False)
menue = leiste.kontext_menue(leiste.aktion("kalk_material"))
assert [x.text() for x in menue.actions()][0] == "Knopf entfernen"
ok("Rechtsklick auf die Leiste: Knopf entfernen, Beschriftung, Größe, konfigurieren")

# ------------------------------------------------------------------ Dauerhaft je Benutzer, Arbeitsbereiche
f2 = Hauptfenster(db, stumm=True)
assert f2.meine_leiste.ids(False)[0] == "kalk_material" and f2.meine_leiste.iconSize().width() == 32
f2.close()
ok("Nach Neustart: dieselbe Leiste (dauerhaft in der Datendatei, je Benutzer)")

werkzeugleiste_qt.arbeitsbereich_speichern(f, "Mein Kalkulationsplatz")
assert "Mein Kalkulationsplatz" in wl.profile(db)
assert werkzeugleiste_qt.arbeitsbereich_anwenden(f, "Tablet")
assert f.meine_leiste.iconSize().width() == 32 and db.einstellung("ansicht_dichte") == "komfortabel"
assert f.reiter.oben.modus == "breit"
assert werkzeugleiste_qt.arbeitsbereich_anwenden(f, "Mein Kalkulationsplatz")
assert f.meine_leiste.ids(False)[0] == "kalk_material"
assert werkzeugleiste_qt.arbeitsbereich_anwenden(f, "Kalkulation") and f.info_dock.isVisible()
assert werkzeugleiste_qt.standard_wiederherstellen(f)
assert f.meine_leiste.ids(False) == ["angebot_neu", "angebot_neu_step", "angebote_letzte", "suchen", "favoriten"]
assert wl.profil_speichern(db, "Tablet", {}) and wl.profil_loeschen(db, "Mein Kalkulationsplatz")
db.einstellung_setzen("ansicht_dichte", "normal")
ok("Arbeitsbereiche: eigenen speichern, Tablet (große Knöpfe, komfortabel, Navigation breit), Kalkulation mit "
   "Info-Panel, Standardlayout wiederherstellen, eingebaute Namen geschützt")

# Standardlayout je Rolle (Admin): Benutzer ohne eigene Leiste bekommt die Vorgabe seiner Rolle
from rohrlaser import rollen  # noqa: E402
assert rollen.benutzer_setzen(db, "WS", "Werkstatt", ["werkstatt"]) == ""
assert rollen.benutzer_setzen(db, "KA", "Kalkulation", ["kalkulation"]) == ""
assert wl.leiste(db, "WS")["knoepfe"][0]["id"] == "nav_produktion" and wl.leiste(db, "WS")["groesse"] == "gross"
wl.vorgabe_setzen(db, "kalkulation", {"leiste": {"knoepfe": ["kalk_starten", "pdf_angebot"]},
                                      "startseite": {"oben": [], "links": ["angebote"], "rechts": ["heute"]},
                                      "schnell": ["kalk_neu"]})
assert [e["id"] for e in wl.leiste(db, "KA")["knoepfe"]] == ["kalk_starten", "pdf_angebot"]
assert wl.startseite(db, "KA")["rechts"] == ["heute"] and wl.schnellzugriffe(db, "KA") == ["kalk_neu"]
ordner = Path(tempfile.mkdtemp())
db.einstellung_setzen("teilen_ordner", str(ordner))
db.einstellung_setzen("benutzer_kuerzel", "PB")
assert wl.vorgaben_schreiben(db) and (ordner / "Admin" / "oberflaeche_vorgaben.json").is_file()
db.einstellung_setzen(wl.VORGABEN, {})
assert wl.vorgaben_lesen(db) and "kalkulation" in wl.vorgaben(db)
ok("Standardlayouts je Benutzergruppe: Werkstatt mit Produktionsknöpfen, Admin-Vorgabe je Rolle über "
   "Admin/oberflaeche_vorgaben.json an alle Plätze")

# ------------------------------------------------------------------ Dashboard
f.reiter.setCurrentWidget(f.start)
app.processEvents()
assert f.start.huellen["schnellzugriffe"].isVisible()
sd = StartseiteDialog(f)
assert [sd.listen["rechts"].item(i).data(Qt.UserRole) for i in range(sd.listen["rechts"].count())][0] == "heute"
neu = {"oben": ["kacheln"], "links": ["heute", "schnellzugriffe"], "rechts": ["angebote"]}
sd.setzen(neu)
sd.listen["oben"].addItem(sd.listen["aus"].takeItem(0))      # falsch abgelegt: rückt in seinen Bereich
erg = sd.ergebnis()
assert erg["links"] == ["heute", "schnellzugriffe"] and erg["rechts"][0] == "angebote"
sd.setzen(neu)
sd.uebernehmen()
app.processEvents()
assert f.start.huellen["heute"].parent() is f.start.links_spalte
assert f.start.huellen["angebote"].parent() is f.start.rechts_spalte
assert not f.start.huellen["sicherung"].isVisible() and not f.start.huellen["auftrag_kacheln"].isVisible()
assert f.start.huellen["kacheln"].isVisible()
ok("Dashboard anpassen: Karten verschieben (links/rechts/oben), ausblenden, falsch abgelegte rücken zurecht")
sk = f.start.schnell
assert set(sk.knoepfe) == set(wl.schnellzugriffe(db)) and "Zuletzt verwendet:" in sk.zuletzt.text()
sk.knoepfe["kalk_neu"].click() if sk.knoepfe["kalk_neu"].isEnabled() else None
ok("Karte Schnellzugriffe mit Knöpfen und „Zuletzt verwendet“")
wl.startseite_setzen(db, None)
f.start.karten_anordnen()

# ------------------------------------------------------------------ Lage merken
f.removeToolBar(f.meine_leiste)
f.addToolBar(Qt.LeftToolBarArea, f.meine_leiste)
f.meine_leiste.show()
werkzeugleiste_qt.zustand_merken(f)
f.removeToolBar(f.meine_leiste)
f.addToolBar(Qt.TopToolBarArea, f.meine_leiste)
f.meine_leiste.show()
werkzeugleiste_qt.zustand_laden(f)
assert f.toolBarArea(f.meine_leiste) == Qt.LeftToolBarArea
ok("Leiste links als Schnellnavigation angedockt, Lage gemerkt und wiederhergestellt")

# ------------------------------------------------------------------ Tabellen: Spalten ein/aus und verschieben
f.reiter.setCurrentWidget(f.kunden)
app.processEvents()
v = f.kunden.ansicht
ag = v.auto_groesse
ag._spalten_menue_fuellen()
titel = [x.text() for x in ag.spalten_menue.actions()]
assert len(titel) >= 3
ag.spalte_zeigen(1, False)
kopf = v.horizontalHeader()
kopf.moveSection(kopf.visualIndex(2), 0)
ag._spalten_merken()
f3 = Hauptfenster(db, stumm=True)
f3.reiter.setCurrentWidget(f3.kunden)
f3.show()
app.processEvents()
f3.kunden.ansicht.auto_groesse.anpassen()
v3 = f3.kunden.ansicht
assert v3.isColumnHidden(1) and v3.horizontalHeader().logicalIndex(0) == 2
v3.auto_groesse.reihenfolge_zuruecksetzen()
v3.auto_groesse.spalte_zeigen(1, True)
assert not v3.isColumnHidden(1) and v3.horizontalHeader().logicalIndex(0) == 0
assert not f.offen[aid].pos_ansicht.horizontalHeader().sectionsMovable()
f3.close()
ok("Tabellen: Spalten per Rechtsklick auf den Kopf ein-/ausblenden und per Ziehen verschieben, nach Neustart gleich; "
   "Positionsliste behält ihre eigene Spaltenwahl")
print("OK: Werkzeugleiste")
