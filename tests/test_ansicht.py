"""Prüft die Anzeige der Angebotsseite: Nullwerte und leere optionale Werte ausblenden (sichtbarkeit.py),
Erweiterte Einstellungen, Kostenübersicht, optionale Spalten der Positionsliste ('Weitere Spalten'),
Abweichung Schneidweg zu STEP und dass die Anzeige weder Daten noch Rechnung ändert.

Aufruf: python tests/test_ansicht.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.angebot_fenster import OPTIONALE_SPALTEN, SPALTEN_EINSTELLUNG, schneidweg_abweichung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.sichtbarkeit import (MASCHINE, OPTIONAL, PFLICHT, STAMM, SUMME, ist_null, kopf_sichtbar,  # noqa: E402
                                    sichtbar, spalte_sichtbar, zahl)


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Regeln (ohne Oberfläche)
for text, wert in (("0", 0), ("0.0", 0), ("0.00", 0), ("0,00", 0), ("0,00 €", 0), ("0 %", 0), ("-0,00 €", 0),
                   ("10,00 €", 10), ("10 %", 10), ("1.234,50 €", 1234.5), ("6.000", 6000), ("0,005 €", 0.005),
                   ("100", 100), ("0,10 €", 0.1)):
    assert zahl(text) == wert, (text, zahl(text))
for text in ("2 × 15 min", "OK", "", "abc 0", "A-2026-0010", "10.5.2026"):
    assert zahl(text) is None, text
assert ist_null("0,00 €") and ist_null(0) and ist_null(0.0) and ist_null("0 %") and ist_null(0.004)
assert not ist_null("10,00 €") and not ist_null(10) and not ist_null("100 %") and not ist_null(0.01)
assert not ist_null(None) and not ist_null("") and not ist_null("OK")
ok("Nullwert am Zahlenwert erkannt: '0,00 €' und '0 %' sind null, '10,00 €' und '100' nicht (keine Textsuche)")
assert not sichtbar("0 %", OPTIONAL) and sichtbar("10 %", OPTIONAL)                         # Fall 1 und 2
assert not sichtbar("0,00 €", OPTIONAL) and sichtbar("12,50 €", OPTIONAL)                   # Fall 3 und 4
assert not sichtbar(None, OPTIONAL) and not sichtbar("", OPTIONAL)
assert all(sichtbar(w, r) for w in (0, "0,00 €", None, "") for r in (PFLICHT, STAMM, MASCHINE, SUMME))  # Fall 5
assert kopf_sichtbar("nummer", "") and kopf_sichtbar("stange", 0) and kopf_sichtbar("bemerkung", None)
assert not kopf_sichtbar("fracht", 0) and kopf_sichtbar("fracht", 120) and not kopf_sichtbar("zuschlag_fremdleistung", 0.0)
assert spalte_sichtbar([None, "", 0]) is False and spalte_sichtbar([None, "MG 1"]) and spalte_sichtbar([None], PFLICHT)
ok("Regeln: optionale Werte mit 0 oder leer ausgeblendet, Pflicht, Stammdaten, Maschine und Summen immer sichtbar")

# ------------------------------------------------------------------ Angebotsseite
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1920, 1080)
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", zuschlag_fremdleistung=0, fracht=None,
                         pauschale_abmessung=22.5))       # Pauschale mit Wert (Vorgabe seit 26.10.2026: 0 €)
for i in range(3):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=800 + 100 * i, stueck=4, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
kb = s.kopf_bereich


def zu_sehen(name):
    """(in der Hauptansicht, in den Erweiterten Einstellungen)"""
    return not kb.zeilen[name][1].isHidden(), not kb.zeilen_erweitert[name][1].isHidden()


vorher = dict(db.angebot(a))
assert zu_sehen("zuschlag_fremdleistung") == (False, True)                                  # Fall 1: 0 % weg
assert zu_sehen("gewinn") == (True, False)                                                  # Fall 2: 10 % da
assert zu_sehen("fracht") == (False, True)                                                  # Fall 3: 0,00 € weg
assert "Fracht" not in s.uebersicht_bereich.einzeln.text() and "Zuschlag Fremdleistung" not in s.uebersicht.text()
assert "1 Wert" not in kb.erweitert_bereich.knopf.text() and "2 Werte auf 0" in kb.erweitert_bereich.knopf.text()
assert {k: v for k, v in db.angebot(a).items() if k != "geaendert"} == \
    {k: v for k, v in vorher.items() if k != "geaendert"}, "Ausblenden darf nichts speichern"
ok("Fall 1 und 3: Zuschlag mit 0 % und Fracht mit 0,00 € ausgeblendet, unter Erweiterte Einstellungen änderbar")
for name in ("nummer", "kundennr", "kunde", "datum", "maschine", "stange", "bemerkung"):
    assert not s.felder[name].isHidden(), name
m = dict(db.zeilen("maschinen")[0])
db.aendern("maschinen", m["id"], "endbeschnitt", 0)
s.neu_laden()
assert "Endbeschnitt 0 mm" in kb.maschinen_bereich.knopf.text() and "Endbeschnitt" in s.maschinenwerte.text()
db.aendern("maschinen", m["id"], "endbeschnitt", m["endbeschnitt"])
ok("Fall 5: Pflichtfelder und Stammdaten immer sichtbar, Maschinenparameter auch mit 0 (Endbeschnitt 0 mm)")

# Fall 6 und 4: Wert in den Erweiterten Einstellungen ändern -> sofort oben sichtbar
w = kb.erweitert["fracht"]
w.setValue(120)
w.editingFinished.emit()
assert db.angebot(a)["fracht"] == 120 and zu_sehen("fracht") == (True, False)
assert "Fracht" in s.uebersicht_bereich.einzeln.text() and "Pauschalen und Aufschläge" in s.uebersicht.text()
w = kb.erweitert["zuschlag_fremdleistung"]
w.setValue(10)
w.editingFinished.emit()
assert db.angebot(a)["zuschlag_fremdleistung"] == 10 and zu_sehen("zuschlag_fremdleistung") == (True, False)
assert "Keine weiteren" in kb.erweitert_leer.text() and not kb.erweitert_leer.isHidden()
ok("Fall 4 und 6: Fracht 120 € und Zuschlag 10 % erscheinen nach der Änderung sofort in der Hauptansicht")
# und zurück auf 0: wieder ausgeblendet, Wert 0 bleibt gespeichert (nicht leer = nicht 'wie Einstellungen')
kb.felder["zuschlag_fremdleistung"].setValue(0)
kb.felder["zuschlag_fremdleistung"].editingFinished.emit()
assert db.angebot(a)["zuschlag_fremdleistung"] == 0 and zu_sehen("zuschlag_fremdleistung") == (False, True)

# Fall 7: Kostenübersicht = Rechnung; jede Kostenart genau einmal, Gruppen summieren sich zum Ergebnis
assert s.optimieren()
_, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
kosten = rechnen.kostenarten(summen, s.einst)
wert = {n: w for (_, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
vor_herstell = [g for g in rechnen.KOSTEN_GRUPPEN[:[t for t, _, _ in rechnen.KOSTEN_GRUPPEN].index("Herstellkosten")]]
assert abs(sum(wert[n] for _, ns, _ in vor_herstell for n in ns) - summen["herstell"]) < 1e-6
titel_g = [t for t, _, _ in rechnen.KOSTEN_GRUPPEN]
bis_selbst = rechnen.KOSTEN_GRUPPEN[len(vor_herstell) + 1:titel_g.index("Selbstkosten")]
assert abs(summen["herstell"] + sum(wert[n] for _, ns, _ in bis_selbst for n in ns) - summen["selbst"]) < 1e-6
nach = rechnen.KOSTEN_GRUPPEN[titel_g.index("Selbstkosten") + 1:-1]
assert abs(summen["selbst"] + sum(wert[n] for _, ns, _ in nach for n in ns) - summen["verkauf"]) < 1e-6
text = s.uebersicht.text()
for titel in ("Material", "Laser schneiden", "Rüsten", "Herstellkosten", "Programmierkosten", "Verkaufspreis"):
    assert titel in text, titel
assert "Zusätzliche Bearbeitung" not in text and "Gewinde" not in s.uebersicht_bereich.einzeln.text()   # beide 0
assert f"{summen['verkauf']:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") in text
assert "Optimierung abgeschlossen" == s.stand.text()
assert "Preisaufbau" in text and "= Herstellkosten" in text and "+ Laser schneiden" in text
ub = s.uebersicht_bereich
assert "Rüsten Maschine" not in text
ub._gruppe_umschalten("Rüsten")                 # Gruppe aufklappen: Kostenarten einzeln darunter
assert "Rüsten Maschine" in ub.uebersicht.text() and "▾ Rüsten" in ub.uebersicht.text()
ub._gruppe_umschalten("Rüsten")
assert "Rüsten Maschine" not in ub.uebersicht.text()
# Reiter: Zeiten und Stangenbild liegen als Unterreiter in Kalkulation bzw. Schnittplan
assert s.reiter.count() == 7, s.reiter.texte()
s.reiter.setCurrentWidget(s.zeiten_seite)
assert s.reiter.tabText(s.reiter.currentIndex()) == "Kalkulation" and s.zeiten_seite.isVisibleTo(s.reiter)
s.reiter.waehlen("Stangenbild")
assert s.reiter.tabText(s.reiter.currentIndex()) == "Schnittplan"
s.reiter.setCurrentIndex(0)
ok("Fall 7: Herstellkosten, Gewinn und Verkaufspreis kommen unverändert aus rechnen.kalkulation; Gruppen summieren "
   "sich exakt")

# Meldungen
db.position_aendern(s.positionen[0]["id"], "profil_id", "XX 1x1")
s.neu_laden()
assert "1 Fehler" in s.uebersicht_bereich.meldungen_bereich.knopf.text()
assert "Pos. 10" in s.uebersicht_bereich.meldungen.text() and s.stand.text().startswith("Veraltet")
db.position_aendern(s.positionen[0]["id"], "profil_id", "QR 40x40x3")
s.neu_laden()
assert "keine Fehler" in s.uebersicht_bereich.meldungen_bereich.knopf.text()
ok("Meldungen: Anzahl im Titel, einzelne Meldungen mit Pos. aufklappbar; Stand der Optimierung als Status")

# Optionale Spalten
m = s.pos_modell
spalte = {m.name(i): i for i in range(m.columnCount())}
sichtbar_ = lambda n: not s.pos_ansicht.isColumnHidden(spalte[n])
for n in ("pos", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge", "stueck", "schneidweg", "einstiche",
          "zeit_manuell", "preis_m", "status"):
    assert sichtbar_(n), n
assert not any(sichtbar_(n) for n in OPTIONALE_SPALTEN) and not sichtbar_("abweichung")
db.position_aendern(s.positionen[1]["id"], "satz", "MG 1")
s.neu_laden()
assert sichtbar_("satz") and not sichtbar_("je_satz")
s.spalte_waehlen("gewinde", True)
s.spalte_waehlen("satz", False)
assert sichtbar_("gewinde") and not sichtbar_("satz") and db.einstellung(SPALTEN_EINSTELLUNG) == {"gewinde": True,
                                                                                                     "satz": False}
assert db.positionen(a)[1]["satz"] == "MG 1", "Ausblenden darf keine Werte löschen"
s._spalten_menue_fuellen()
texte = [x.text() for x in s.spalten_menue.actions()]
assert any(t.startswith("Satz") for t in texte) and any(t.startswith("Automatisch") for t in texte)
s.spalte_waehlen(None, None)
assert sichtbar_("satz") and not sichtbar_("gewinde") and db.einstellung(SPALTEN_EINSTELLUNG) == {}
s.zeige_berechnet.setChecked(True)
assert all(sichtbar_(n) for (art, x), n in zip(m.spalten, (m.name(i) for i in range(m.columnCount())))
           if art == "berechnet")
s.zeige_berechnet.setChecked(False)
ok("Optionale Spalten erscheinen mit Werten, 'Weitere Spalten' blendet gezielt ein/aus und merkt die Wahl")

# Abweichung Schneidweg zu STEP (nur wenn der Schneidweg von Hand geändert wurde)
p = dict(schneidweg=300.0, a_schnitt=120.1, b_schnitt=120.1, innen=59.9)
assert schneidweg_abweichung(p) is None and schneidweg_abweichung(dict(p, schneidweg=320)) is not None
assert schneidweg_abweichung(dict(schneidweg=300)) is None
assert abs(schneidweg_abweichung(dict(p, schneidweg=250)) - (250 - 300.1)) < 1e-9
db.position_aendern(s.positionen[2]["id"], "a_schnitt", 100.0)
db.position_aendern(s.positionen[2]["id"], "b_schnitt", 100.0)
db.position_aendern(s.positionen[2]["id"], "innen", 100.0)
s.neu_laden()
assert sichtbar_("abweichung") and m.data(m.index(2, spalte["abweichung"])) == "20,0"
ok("Abweichung Schneidweg zu STEP: erscheint nur, wenn der Schneidweg vom STEP-Wert abweicht")

# Fall 9: viele Positionen und alle optionalen Spalten
for i in range(200):
    db.position_neu(a, dict(pos=1000 + i, artikel=f"V{i}", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                            laenge=300 + i, stueck=2, schneidweg=150, einstiche=1, satz="S" if i % 2 else None,
                            je_satz=1 if i % 2 else None, oberflaeche="roh" if i % 3 else None))
for n in OPTIONALE_SPALTEN:
    s.spalte_waehlen(n, True)
s.zeige_step.setChecked(True)
s.zeige_berechnet.setChecked(True)
s.neu_laden()
assert m.rowCount() == 203 and all(sichtbar_(n) for n in OPTIONALE_SPALTEN)
assert s.optimieren() and s.stand.text() == "Optimierung abgeschlossen"
fenster.show()
QApplication.processEvents()
assert s.pos_ansicht.horizontalHeader().isVisible() and s.teiler.sizes()[1] >= 200
fenster.resize(1280, 720)
QApplication.processEvents()
assert kb._spalten_gruppen == 2 and s.teiler.sizes()[1] >= 200
fenster.resize(1920, 1080)
QApplication.processEvents()
assert kb._spalten_gruppen == 4
ok("Fall 9: 203 Positionen mit allen optionalen Spalten, 1920 × 1080 und 1280 × 720 bedienbar")

# Kalkulation zuklappen, Preise oben in der Übersicht, Zeile über der Positionsliste, Spaltenbreiten
from rohrlaser.angebot_oben import KALK_OFFEN_EINSTELLUNG  # noqa: E402
ub = s.uebersicht_bereich
_, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
assert ub.preis["verkauf"].text().endswith(" €") and summen["verkauf"] > 0
assert ub.preis["verkauf"].text() in ub.uebersicht.text() and ub.preis["herstell"].text() in ub.uebersicht.text()
assert not kb.kalk_offen() and not kb.kalk_kurz.isHidden(), "Vorgabe: zugeklappt (Kurzzeile)"
kb.kalk_knopf.click()
assert kb.kalk_offen() and kb.kalk_kurz.isHidden()
kb.kalk_knopf.click()
assert not kb.kalk_offen() and kb.kalk_inhalt.isHidden() and not kb.kalk_kurz.isHidden()
assert "Gewinn 10,0 %" in kb.kalk_kurz.text() and "Fremdleistung" not in kb.kalk_kurz.text() and "Skontofrist 10 Tage" in kb.kalk_kurz.text()
assert db.einstellung(KALK_OFFEN_EINSTELLUNG) is False
s2 = fenster.angebot_oeffnen(db.angebot_neu(dict(kunde="Zweites")))
assert not s2.kopf_bereich.kalk_offen(), "Wahl gilt für alle Angebote"
assert "vorläufig" in s2.uebersicht_bereich.preis_titel["verkauf"][0].text()
assert ub.preis_titel["verkauf"][0].text() == "Verkaufspreis"
kb.kalk_knopf.click()
assert kb.kalk_offen() and db.einstellung(KALK_OFFEN_EINSTELLUNG) is True
assert s.pos_info.text().startswith("203 Positionen")
assert s.reiter.cornerWidget(Qt.TopRightCorner) is s.schritte and s.spalten_knopf.isVisibleTo(s.pos_seite)
kopf = s.pos_ansicht.horizontalHeader()
fm = kopf.fontMetrics()
for c in range(s.pos_modell.columnCount()):
    if not s.pos_ansicht.isColumnHidden(c) and c < s.pos_modell.columnCount() - 1:
        titel = str(s.pos_modell.headerData(c, Qt.Horizontal, Qt.DisplayRole))
        assert s.pos_ansicht.columnWidth(c) >= min(max(fm.horizontalAdvance(w) for w in titel.split()), 240), titel
ok("Kalkulation zuklappbar mit Kurzfassung (Wahl gespeichert), Preise groß in der Übersicht, Spaltenauswahl über "
   "der Liste statt neben den Reitern, kein Wort im Spaltenkopf abgeschnitten")
# 1366-px-Bildschirm: die Knopfleiste bricht um, das Fenster passt (kein abgeschnittener Knopf rechts)
assert fenster.minimumSizeHint().width() <= 1366, fenster.minimumSizeHint()
fenster.show()
fenster.resize(1366, 728)
QApplication.processEvents()
fenster.reiter.setCurrentWidget(s)
QApplication.processEvents()
assert s.leiste.zweizeilig and s.weitere.isVisible(), (s.leiste.zweizeilig, s.leiste.width(), s.leiste._bedarf())
assert s.weitere.mapTo(fenster, s.weitere.rect().bottomRight()).x() <= fenster.width()
fenster.resize(1920, 1040)
QApplication.processEvents()
# eine Zeile, sobald die Breite reicht (wie breit die Knöpfe sind, hängt von der Schrift des Systems ab)
assert s.leiste.width() > 1366 - 400 and s.leiste.zweizeilig == (s.leiste.width() < s.leiste._bedarf()), \
    (s.leiste.zweizeilig, s.leiste.width(), s.leiste._bedarf())
ok("Angebot bei 1366 px: Angebot (PDF) und Ausgaben in zweiter Zeile, bei 1920 px eine Zeile, wenn die Breite reicht")
# Übersicht rechts über die ganze Höhe, Angebotskopf mit Kunde und Positionen zugeklappt auf eine Zeile
kb = s.kopf_bereich
assert s.spalten.widget(1) is s.uebersicht_rahmen and s.uebersicht_rahmen.widget() is s.uebersicht_bereich
assert kb.kopf_ausgefuellt() and not kb.kopf_offen() and not kb.kopf_inhalt.isVisibleTo(kb)
assert "Test" in kb.kopf_kurz.text() and "4711" in kb.kopf_kurz.text()
kb.kopf_aufklappen(True)
s.neu_laden()
assert kb.kopf_offen(), "Wahl von Hand bleibt beim Neuladen"
neu_id = db.angebot_neu(dict(kunde=""))
s2 = fenster.angebot_oeffnen(neu_id)
assert s2.kopf_bereich.kopf_offen(), "neues Angebot: Kopf offen"
fenster.angebot_schliessen(neu_id)
assert not kb.fracht_inhalt.isVisibleTo(kb) and "Fracht" in kb.fracht_klapp.text()
ok("Übersicht als rechte Spalte, Angebotskopf ausgefüllt zugeklappt (Kurzzeile), neues Angebot offen, Fracht zu")
# Ergebnisreiter: leere Spalten der Kalkulation weg, Schnittplan mit gewählter Stange, Auswertung ohne Leertabelle
assert s.optimieren()
QApplication.processEvents()
# Kompakte Übersicht (Vorgabe): Profil, Stückzahl, Länge, Material, Oberfläche, Laserzeit berechnet/genutzt, VK
assert s.kalk_kompakt.isChecked() and s.kompakt_ansicht.isVisibleTo(s.kalk_seite) \
    and not s.kalk_ansicht.isVisibleTo(s.kalk_seite)
ko = s.kompakt
ks = {sp[1]: c for c, sp in enumerate(ko.spalten)}
z0 = ko.zeilen[0]
assert z0["profil"] and z0["material"] and z0["laenge"] and z0["oberflaeche"]
assert z0["laser_brutto"] > 0 and z0["laser_netto"] > 0 and z0["preis_teil"] > 0
assert abs(z0["laser_position_min"] - z0["laser_netto"] * z0["stueck"] / 60) < 1e-9
assert not s.kompakt_ansicht.isColumnHidden(ks["laser_brutto"]) and s.kompakt_ansicht.isColumnHidden(ks["zeit_manuell"])
assert "kompakt" in s.kalk_info.text()
gesprungen = []
s.zur_position, alt = (lambda ref=None, zeile=None: gesprungen.append(zeile)), s.zur_position
s._kompakt_doppelklick(s.kompakt_ansicht.model().index(0, 0))
s.zur_position = alt
assert gesprungen == [z0["zeile"]]
s.kalk_kompakt.setChecked(False)
assert db.einstellung("ansicht_kalk_kompakt") is False and s.kalk_ansicht.isVisibleTo(s.kalk_seite) \
    and not s.kompakt_ansicht.isVisibleTo(s.kalk_seite)
ok("Kalkulation: kompakte Übersicht je Bauteil als Vorgabe, Doppelklick zur Position, Häkchen aus = alle Spalten")
km = s.kalk
spalte = {sp[1]: c for c, sp in enumerate(km.spalten)}
assert s.kalk_ansicht.isColumnHidden(spalte["gewindezeit"]) and not s.kalk_ansicht.isColumnHidden(spalte["preis_teil"])
assert km.data(km.index(0, spalte["material_teil"])).count(",") == 1
assert len(km.data(km.index(0, spalte["material_teil"])).split(",")[1]) == 2
assert "ausgeblendet" in s.kalk_info.text()
assert s.stangen_ansicht.currentIndex().row() == 0 and s.teile.zeilen and "Stange" in s.teile_titel.text()
sp = {x[1]: c for c, x in enumerate(s.stangen.spalten)}
assert s.stangen_ansicht.isColumnHidden(sp["stange"]) and "6.000" in s.plan_info.text()
assert "Alle Teile eingeplant" in s.fehler_titel.text() and not s.fehler_ansicht.isVisibleTo(s)
# Angebotsliste und Startseite: Status und Verkaufspreis werden beim Anzeigen gemerkt, ohne Rückgängig-Schritt
from rohrlaser.angebot_fenster import angebot_status  # noqa: E402
schritte = len(s.verlauf.zurueck)
s.neu_laden()
assert len(s.verlauf.zurueck) == schritte
zeile = next(z for z in db.angebote() if z["id"] == a)
assert zeile["stand"] == "aktuell" and zeile["vk_netto"] > 0 and angebot_status(zeile) == "Optimiert"
assert angebot_status(dict(optimiert_am=None)) == "Nicht optimiert"
assert angebot_status(dict(optimiert_am="x", stand="veraltet")) == "Veraltet"
fenster.start.neu_laden()
assert any(z["id"] == a for z in fenster.start.zuletzt.zeilen) and fenster.start.zuletzt_ansicht.isVisibleTo(fenster.start)
ok("Angebotsliste: Status Optimiert und Verkaufspreis gemerkt (kein Rückgängig-Schritt), Startseite zeigt es")
ok("Kalkulation ohne Nullspalten mit 2 Stellen, Schnittplan: Gleiches einmal oben, Stange 1 gewählt; "
   "Auswertung: Alle Teile eingeplant")
# Einstellungen und Stammdaten: Hilfetext kurz/aufklappbar/Tooltip, Prüfung OK neutral, Filter, Vorgaben zweispaltig
from rohrlaser import hilfe  # noqa: E402
from rohrlaser.fenster import FARBE_BERECHNET, FARBE_STATUS  # noqa: E402
assert hilfe.kurztext("Abmessung A = Ø bzw. Breite (z. B. 40). Zweiter Satz.") == "Abmessung A = Ø bzw. Breite (z. B. 40)."
assert hilfe.kurztext("Nur ein Satz.") == "Nur ein Satz."
profile = next(x for x in fenster.seiten if x.t.name == "profile")
h = profile.hinweis
assert h.label.text() == hilfe.kurztext(profile.t.hinweis) and h.knopf.text() == "mehr" and not h.offen
assert not h.knopf.icon().isNull()                 # i-Symbol gezeichnet (Zeichen ⓘ fehlt in manchen Schriften)
h.knopf.click()
assert h.offen and h.label.text() == h.text and h.knopf.text() == "weniger"
assert (db.einstellung(hilfe.OFFEN_EINSTELLUNG) or {}).get("tabelle:profile")
neu_h = hilfe.Hinweis(profile.t.hinweis, db, "tabelle:profile")
assert neu_h.offen                                  # gemerkt, auch für neu gebaute Seiten
h.knopf.click()
assert not h.offen and not (db.einstellung(hilfe.OFFEN_EINSTELLUNG) or {}).get("tabelle:profile")
e = fenster.einstellungen
cb = e.felder[hilfe.HILFE_EINSTELLUNG]
assert not cb.isEditable() and [cb.itemText(i) for i in range(cb.count())] == list(hilfe.HILFE_ARTEN)
cb.setCurrentText("nur Tooltip")
assert db.einstellung(hilfe.HILFE_EINSTELLUNG) == "nur Tooltip"
assert not h.label.isVisibleTo(h) and h.knopf.text() == "Hilfe" and h.knopf.toolTip() == h.text
cb.setCurrentText("aufklappbar")
assert h.label.isVisibleTo(h) and h.knopf.text() == "mehr"
assert FARBE_STATUS["OK"] == FARBE_BERECHNET and FARBE_STATUS["FEHLER"] != FARBE_BERECHNET
alle = profile.filter.rowCount()
db.aendern("profile", profile.modell.daten[0]["id"], "a", None)
profile.neu_laden()
profile.nur_fehler.setChecked(True)
auffaellig = [r for r in range(len(profile.modell.daten))
              if str(profile.modell.roh(r, profile.pruefspalte)).startswith(("FEHLER", "WARNUNG"))]
assert auffaellig and profile.filter.rowCount() == len(auffaellig) < len(profile.modell.daten)
assert "mit FEHLER" in profile.anzahl.text() or "mit WARNUNG" in profile.anzahl.text()
profile.nur_fehler.setChecked(False)
assert profile.filter.rowCount() == len(profile.modell.daten) >= alle
fenster.bereich.oeffnen(db.einstellung("passwort"))
fenster.reiter.setCurrentWidget(fenster.bereich)
fenster.bereich.zeigen(e)
fenster.resize(1920, 1040)
QApplication.processEvents()
assert e.zweispaltig and all(sp.count() > 1 for sp in e.spalten)
fenster.resize(1100, 728)
QApplication.processEvents()
assert e.zweispaltig == (e.viewport().width() >= e.ZWEI_SPALTEN)
e._anordnen(False)
assert e.spalten[1].count() == 1 and e.spalten[0].count() == len(e.boxen) + 1     # rechts nur der Abstandhalter
assert all(w.maximumWidth() <= e.BREITE_TEXT + 160 for n, w in e.felder.items() if n != "logo")
ok("Einstellungen: Hilfetext kurz mit „mehr“ (gemerkt) oder nur Tooltip, Prüfung OK neutral, Filter Fehler/"
   "Warnungen, Vorgaben bei 1920 px zweispaltig, bei schmalem Fenster einspaltig")
# Teil 5: Fracht, Zukauf, Dialoge mit kurzen Hilfetexten; Zukauf-Formular in Abschnitten zum Aufklappen
schluessel = {h.schluessel for h in hilfe._alle}
assert {"fracht_dienstleister", "fracht_historie", "zukauf_artikel", "zukauf_preise", "zusatzarbeiten"} <= schluessel
zs = fenster.zukauf.artikel
zs.neu()
fo = zs.formular
assert set(fo.abschnitte) == {"A  Stammdaten", "B  Einkaufspreis", "C  Aufschlag", "Preisvorschau"}
assert fo.abschnitt_offen("A  Stammdaten") and not fo.abschnitt_offen("C  Aufschlag")
assert fo.abschnitte["C  Aufschlag"][2].text()             # Kurzfassung neben dem zugeklappten Titel
fo.abschnitte["C  Aufschlag"][0].click()
assert fo.abschnitt_offen("C  Aufschlag") and "C  Aufschlag" not in db.einstellung(fo.ZU_EINSTELLUNG)
fo.abschnitte["Preisvorschau"][0].click()
assert not fo.abschnitt_offen("Preisvorschau") and "Preisvorschau" in db.einstellung(fo.ZU_EINSTELLUNG)
fo.abschnitte["Preisvorschau"][0].click()
fo.abbrechen()
ok("Fracht, Zukauf und Dialoge mit kurzen Hilfetexten; Zukauf-Formular mit Abschnitten zum Aufklappen (gemerkt)")
fenster.close()
db.schliessen()
print("OK: Anzeige der Angebotsseite (Nullwerte, Spalten, Übersicht)")
