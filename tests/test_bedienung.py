"""Plan „Bedienung schneller und einfacher“ (Paket 1):
- B2: Einblendung mit Knopf (Rückgängig, Bericht), Bericht im Meldungsverlauf, Löschen im Angebot ohne Rückfrage mit
  „Rückgängig“ (nimmt nur genau diese Änderung zurück), Hinweise aus Dialogen als Einblendung im Dialog.
- B1: STEP-Prüfdialog mit Kundenwahl, Vorprüfung (fehlende Profile, doppelte Artikel) als Häkchen und Knopf
  „Übernehmen und Angebot (PDF)“.
- B5: Rechtsklick-Menü passend zur Art der markierten Positionen, „Für markierte setzen …“.

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
assert s.pos_aktionen["Positionen löschen"].shortcut().toString() == "Del"
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

f.close()
db.schliessen()
print("Alle Prüfungen bestanden.")
