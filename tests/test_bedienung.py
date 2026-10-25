"""Plan „Bedienung schneller und einfacher“ (Pakete 1 und 2):
- B2: Einblendung mit Knopf (Rückgängig, Bericht), Bericht im Meldungsverlauf, Löschen im Angebot ohne Rückfrage mit
  „Rückgängig“ (nimmt nur genau diese Änderung zurück), Hinweise aus Dialogen als Einblendung im Dialog.
- B1: STEP-Prüfdialog mit Kundenwahl, Vorprüfung (fehlende Profile, doppelte Artikel) als Häkchen und Knopf
  „Übernehmen und Angebot (PDF)“.
- B5: Rechtsklick-Menü passend zur Art der markierten Positionen, „Für markierte setzen …“.
- B3: ◀ ▶ im Rohr-Editor blättert durch die Positionen derselben Art (ohne Änderung nichts gespeichert).
- B4: Größe, Lage und Teiler der Dialoge gemerkt, offene Angebote beim nächsten Start wieder offen.
- B7: zuletzt benutzte Profile/Werkstoffe oben in Auswahllisten, Tippen findet Teilwörter.

Aufruf: python tests/test_bedienung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import einblendung  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
f.show()
k = db.kontext()
profil = next(iter(k.profile))
werkstoffe = list(k.werkstoffe)

# ------------------------------------------------------------------ B2 Einblendung, Verlauf, Rückgängig
geklickt = []
f.stumm = False                     # Einblendung wirklich zeigen
f.meldung("Test mit Knopf", aktion=("Mach", lambda: geklickt.append(1)))
karte = f.einblendung
assert karte.isVisible() and karte.knopf.isVisible() and karte.knopf.text() == "Mach"
karte.knopf.click()
assert geklickt == [1] and not karte.isVisible()
f.meldung("Mit Bericht", bericht=("Titel", "Zeile 1\nZeile 2"))
assert karte.knopf.text() == "Bericht …"
assert f.verlauf.eintraege[0][3] == ("Titel", "Zeile 1\nZeile 2")
assert any("(Bericht …)" in a.text() for a in f.verlauf.menue.actions())
f.meldung("Ohne Knopf")
assert not karte.knopf.isVisible()
f.stumm = True
ok("Einblendung mit Knopf (Aktion, Bericht), Bericht im Meldungsverlauf")

aid = db.angebot_neu(dict(kunde="Test"))
for i, art in enumerate(("rohr", "rohr", "rohr", "zukauf")):
    werte = dict(pos=(i + 1) * 10, artikel=f"A{i}", stueck=2)
    if art == "rohr":
        werte.update(profil_id=profil, werkstoff_id=werkstoffe[0], laenge=500 + i)
    else:
        werte.update(art=ZUKAUFTEIL, bezeichnung="Schraube")
    db.position_neu(aid, werte)
s = f.angebot_oeffnen(aid)


def markieren(zeilen):
    s.pos_ansicht.clearSelection()
    sel = s.pos_ansicht.selectionModel()
    for r in zeilen:
        sel.select(s.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)


markieren([0])
s.positionen_loeschen()
assert len(db.positionen(aid)) == 3, "ohne Rückfrage gelöscht"
assert f.letzte_aktion and f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
assert len(db.positionen(aid)) == 4, "Rückgängig aus der Einblendung stellt die Position wieder her"
markieren([0])
s.positionen_loeschen()
zurueck = f.letzte_aktion[1]
db.position_aendern(db.positionen(aid)[0]["id"], "stueck", 7)      # weitere Änderung danach
s.neu_laden()
assert zurueck() is None and len(db.positionen(aid)) == 3, "nach weiterer Änderung nimmt der Knopf nichts zurück"
assert "Strg+Z" in f.statusBar().currentMessage()
s.rueckgaengig()
s.rueckgaengig()
assert len(db.positionen(aid)) == 4
ok("Positionen löschen ohne Rückfrage, Rückgängig aus der Einblendung nur für genau diese Änderung")

d = QDialog(f)
d.show()
einblendung.melden(d, "Hinweis im Dialog")
assert d.letzte_meldung == "Hinweis im Dialog" and f.verlauf.eintraege[0][1] == "Hinweis im Dialog"
f.stumm = False
einblendung.melden(d, "sichtbar", fehler=True)
assert d._einblendung.isVisible()
f.stumm = True
einblendung.melden(s, "aus der Angebotsseite")
assert f.verlauf.eintraege[0][1] == "aus der Angebotsseite"
ok("Hinweise aus Dialogen: Einblendung im Dialog, Eintrag im Verlauf des Hauptfensters")

# ------------------------------------------------------------------ B5 Rechtsklick passend zur Art
s.neu_laden()
arten = [s.position_art(p) for p in s.positionen]
rohr = arten.index("rohr")
zuk = arten.index("zukauf")
markieren([zuk])
sichtbar = s._pos_menue_anpassen()
assert "Schneidweg berechnen …" not in sichtbar and "Blech-Editor …" not in sichtbar, sichtbar
assert "Zusatzarbeiten …" in sichtbar and "Positionen löschen" in sichtbar
markieren([rohr])
sichtbar = s._pos_menue_anpassen()
assert "Schneidweg berechnen …" in sichtbar and "Material …" in sichtbar and "Blech-Editor …" not in sichtbar
assert "Für markierte setzen …" not in sichtbar, "erst ab zwei markierten Zeilen"
assert s.pos_aktionen["Positionen löschen"].text().endswith("\tEntf")
zeilen = [r for r, a in enumerate(arten) if a == "rohr"]
markieren(zeilen + [zuk])
assert "Für markierte setzen …" in s._pos_menue_anpassen()
ok("Rechtsklick zeigt nur passende Einträge, Tastenkürzel sichtbar")


def bedienen(dlg):
    dlg.ws.setCurrentText(werkstoffe[1])
    return QDialog.Accepted


assert s.fuer_markierte_setzen(dialog=bedienen) == len(zeilen)
assert {p["werkstoff_id"] for p in db.positionen(aid) if not p.get("art")} == {werkstoffe[1]}
assert f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
assert {p["werkstoff_id"] for p in db.positionen(aid) if not p.get("art")} == {werkstoffe[0]}
assert s.fuer_markierte_setzen(zeilen=[zuk], werkstoff=werkstoffe[1]) is None, "Zukaufteile haben keinen Werkstoff"
ok("Für markierte setzen: Werkstoff für alle Rohrlaserteile, ein Schritt für Rückgängig")

# ------------------------------------------------------------------ B1 Prüfdialog: Kunde, Vorprüfung, PDF-Knopf
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

kunden = db.zeilen("kunden")[:2]
messwerte = [dict(datei="x.step", artikel="T1", bauteil="T1", profilform="Rundrohr", profil_id_vorschlag=profil,
                  laenge=500, pruefstatus="plausibel", schneidweg=100)]
gewechselt = []
dlg = StepPruefDialog(None, messwerte, k, werkstoffe[0], 1, kunden=kunden, kundennr=kunden[0]["kundennr"],
                      kunde_gewechselt=lambda nr: gewechselt.append(nr) or werkstoffe[1],
                      vorpruefung=lambda: (["RR 999x9"], 2))
assert dlg.kunde_wahl is not None and dlg.kunde_wahl.currentData() == str(kunden[0]["kundennr"])
assert not dlg.vor_zeile.isHidden() and not dlg.profile_haken.isHidden() and not dlg.doppelt_haken.isHidden()
assert "RR 999x9" in dlg.profile_haken.text() and "2 Artikel" in dlg.doppelt_haken.text()
assert dlg.neue_profile_anlegen() and not dlg.doppelte_eintragen(), "Vorgabe: Profile anlegen, Doppelte nicht"
dlg.kunde_wahl.setCurrentIndex(dlg.kunde_wahl.findData(str(kunden[1]["kundennr"])))
assert gewechselt == [str(kunden[1]["kundennr"])] and dlg.kundennr == str(kunden[1]["kundennr"])
assert dlg.werkstoff == werkstoffe[1]
dlg.mit_pdf()
assert dlg.pdf_danach and dlg.result() == QDialog.Accepted
ohne = StepPruefDialog(None, [dict(messwerte[0])], k, werkstoffe[0], 1, vorpruefung=lambda: ([], 0))
assert ohne.kunde_wahl is None and ohne.vor_zeile.isHidden() and not ohne.pdf_danach
ok("Prüfdialog: Kunde wählen (Importprofil per Rückruf), Vorprüfung als Häkchen, Übernehmen und Angebot (PDF)")

# ------------------------------------------------------------------ B3 Blättern im Editor
s.neu_laden()
rohre = [r for r, p in enumerate(s.positionen) if s.editor_art(p) == "rohr"]
assert len(rohre) == 3 and s.editor_art(s.positionen[zuk]) is None
titel = []


def weiter(d):
    titel.append(d.windowTitle())
    knopf = d.blaettern_knoepfe[1]
    if knopf.isEnabled():
        knopf.click()                   # nichts geändert: Editor schließt ohne Speichern, der nächste öffnet
    return d.result()


stand = [dict(p) for p in db.positionen(aid)]
s.schneidweg_berechnen(rohre[0], dialog=weiter)
assert len(titel) == 3 and "(1 von 3)" in titel[0] and "(3 von 3)" in titel[2], titel
assert [dict(p) for p in db.positionen(aid)] == stand, "ohne Änderung wird beim Blättern nichts gespeichert"
assert s.pos_ansicht.currentIndex().row() == rohre[2], "die zuletzt geöffnete Position ist markiert"
ok("Blättern im Rohr-Editor: n von m im Titel, ohne Änderung nichts gespeichert")

# ------------------------------------------------------------------ B4 Fenster merken, offene Angebote
from PySide6.QtWidgets import QSplitter, QVBoxLayout  # noqa: E402

from rohrlaser import fenster_merken  # noqa: E402

merker = fenster_merken.FensterMerker(db)


class TestDialog(QDialog):
    def __init__(self):
        super().__init__(f)
        self.teil = QSplitter()
        for _ in range(2):
            self.teil.addWidget(QDialog())
        QVBoxLayout(self).addWidget(self.teil)


app.installEventFilter(merker)
d1 = TestDialog()
d1.resize(640, 410)
d1.show()
app.processEvents()
d1.teil.setSizes([100, 500])
app.processEvents()
d1.close()
app.processEvents()
assert "TestDialog" in db.einstellung(fenster_merken.GEOMETRIE)
d2 = TestDialog()
d2.show()
app.processEvents()
assert (d2.width(), d2.height()) == (640, 410), (d2.width(), d2.height())
assert d2.teil.sizes()[0] < d2.teil.sizes()[1], d2.teil.sizes()
d2.close()
app.removeEventFilter(merker)
ok("Dialoge öffnen mit gemerkter Größe und Teilerstellung")

s.reiter.setCurrentIndex(2)
stand = fenster_merken.sitzung_merken(f)
assert stand["angebote"] == [aid] and stand["aktiv"] in (aid, None) and stand["unterreiter"][str(aid)] == 2
f.angebot_schliessen(aid)
assert aid not in f.offen
assert fenster_merken.sitzung_wiederherstellen(f) == 1 and aid in f.offen
assert f.offen[aid].reiter.currentIndex() == 2
db.einstellung_setzen(fenster_merken.SITZUNG, dict(angebote=[99999]))
assert fenster_merken.sitzung_wiederherstellen(f) == 0, "gelöschte Angebote werden übergangen"
s = f.offen[aid]
ok("Offene Angebote samt Unterreiter beim nächsten Start wieder offen")

# ------------------------------------------------------------------ B7 Auswahllisten lernen
from PySide6.QtWidgets import QComboBox  # noqa: E402

from rohrlaser import fenster as fenster_modul, tabellen_eingabe  # noqa: E402

assert db.zuletzt_benutzt("werkstoff")[0] == werkstoffe[0] and db.zuletzt_benutzt("profil") == [profil]
fenster_modul.zuletzt_quelle = db.zuletzt_benutzt
cb = QComboBox()
fenster_modul.liste_fuellen(cb, k, "werkstoff")
texte = [cb.itemText(i) for i in range(cb.count())]
assert texte[1] == fenster_modul.ZULETZT_TITEL and texte[2] == werkstoffe[0], texte[:5]
assert not cb.model().item(1).isEnabled()
fenster_modul.zuletzt_quelle = None
cb2 = QComboBox()
fenster_modul.liste_fuellen(cb2, k, "werkstoff")
assert fenster_modul.ZULETZT_TITEL not in [cb2.itemText(i) for i in range(cb2.count())]
c = tabellen_eingabe.teilwort(cb2)
teil = werkstoffe[0][2:6]
c.setCompletionPrefix(teil)
treffer = [c.completionModel().index(i, 0).data() for i in range(c.completionModel().rowCount())]
assert werkstoffe[0] in treffer and all(teil.lower() in x.lower() for x in treffer), (teil, treffer[:5])
ok("Zuletzt benutzte Werte oben in der Auswahl, Tippen findet Teilwörter")

f.close()
db.schliessen()
print("Alle Prüfungen bestanden.")
