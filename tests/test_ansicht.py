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
assert not kopf_sichtbar("fracht", 0) and kopf_sichtbar("fracht", 120) and not kopf_sichtbar("zuschlag_material", 0.0)
assert spalte_sichtbar([None, "", 0]) is False and spalte_sichtbar([None, "MG 1"]) and spalte_sichtbar([None], PFLICHT)
ok("Regeln: optionale Werte mit 0 oder leer ausgeblendet, Pflicht, Stammdaten, Maschine und Summen immer sichtbar")

# ------------------------------------------------------------------ Angebotsseite
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1920, 1080)
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", zuschlag_fremdleistung=0, fracht=None))
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
assert zu_sehen("zuschlag_material") == (True, False)                                       # Fall 2: 10 % da
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
nach = rechnen.KOSTEN_GRUPPEN[len(vor_herstell) + 1:-1]
assert abs(summen["herstell"] + sum(wert[n] for _, ns, _ in nach for n in ns) - summen["verkauf"]) < 1e-6
text = s.uebersicht.text()
for titel in ("Material", "Laser schneiden", "Rüsten", "Herstellkosten", "Programmierkosten", "Verkaufspreis"):
    assert titel in text, titel
assert "Zusätzliche Bearbeitung" not in text and "Gewinde" not in s.uebersicht_bereich.einzeln.text()   # beide 0
assert f"{summen['verkauf']:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") in text
assert "Optimierung abgeschlossen" == s.stand.text()
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
          "zeit_manuell", "status"):
    assert sichtbar_(n), n
assert not any(sichtbar_(n) for n in OPTIONALE_SPALTEN) and not sichtbar_("abweichung")
db.position_aendern(s.positionen[1]["id"], "satz", "MG 1")
s.neu_laden()
assert sichtbar_("satz") and not sichtbar_("je_satz")
s.spalte_waehlen("preis_m", True)
s.spalte_waehlen("satz", False)
assert sichtbar_("preis_m") and not sichtbar_("satz") and db.einstellung(SPALTEN_EINSTELLUNG) == {"preis_m": True,
                                                                                                    "satz": False}
assert db.positionen(a)[1]["satz"] == "MG 1", "Ausblenden darf keine Werte löschen"
s._spalten_menue_fuellen()
texte = [x.text() for x in s.spalten_menue.actions()]
assert any(t.startswith("Satz") for t in texte) and any(t.startswith("Automatisch") for t in texte)
s.spalte_waehlen(None, None)
assert sichtbar_("satz") and not sichtbar_("preis_m") and db.einstellung(SPALTEN_EINSTELLUNG) == {}
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
fenster.close()
db.schliessen()
print("OK: Anzeige der Angebotsseite (Nullwerte, Spalten, Übersicht)")
