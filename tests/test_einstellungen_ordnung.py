"""Einstellungen aufräumen und Funktionen ein/aus (Patrick 29.10.2026, Freigabe „Alle a“): jede Einstellung steht auf
einer Themenseite statt auf einer langen Seite „Vorgaben“, Expertenabschnitte sind eingeklappt, Titel ohne doppelte
Vorsilbe; ausgeschaltete Funktionen verschwinden aus Reitern, Menüs, Editoren und Einstellungen, Daten bleiben."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QPushButton, QWidget  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import einstellungen_ordnung as ordnung, funktionen  # noqa: E402
from rohrlaser.befehlspalette import eintraege  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.muster_haken import MusterHaken  # noqa: E402
from rohrlaser.neue_position import BLECH, ROHR, SCHWEISS, ZUKAUF, TypDialog  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG, EINSTELLUNGEN  # noqa: E402
from rohrlaser.teilen import LOKAL  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ---------------------------------------------------------------- Ordnung ohne Fenster
auf_seiten = {n for s in ordnung.SEITEN for a in s.abschnitte for n in a.namen}
fracht = {e.name for e in EINSTELLUNGEN if e.gruppe == ordnung.EIGENER_REITER}
assert auf_seiten <= set(EINSTELLUNG), auf_seiten - set(EINSTELLUNG)
assert set(EINSTELLUNG) - auf_seiten == fracht | ordnung.INTERN, set(EINSTELLUNG) - auf_seiten - fracht
assert len(ordnung.SEITEN) == 23 and len({s.schluessel for s in ordnung.SEITEN}) == 23     # + ERP-Preisimport
assert max(sum(len(a.namen) for a in s.abschnitte) for s in ordnung.SEITEN) <= 25
doppelt = [n for n in auf_seiten if len(ordnung.seiten_von(n)) > 1]
assert sorted(doppelt) == sorted(funktionen.VORHANDEN), doppelt         # Schalter: Funktionen und beim Thema
arbeitsplatz = {n for a in ordnung.SEITE["e_arbeitsplatz"].abschnitte for n in a.namen}
assert arbeitsplatz == LOKAL - {"letzte_angebotsnummer", "csv_ordner"}, arbeitsplatz ^ LOKAL
ok(f"{len(EINSTELLUNGEN)} Einstellungen auf 23 Seiten, jede mindestens einmal, „Mein Arbeitsplatz“ = nur lokale")

assert ordnung.kurztitel(EINSTELLUNG["laenge_mindest_eur"]) == "Mindestersparnis je Gruppe in €"
assert ordnung.kurztitel(EINSTELLUNG["schweiss_a_regel"]).startswith("a-Maß-Regel")
assert ordnung.kurztitel(EINSTELLUNG["gewinn"]) == "Gewinn"
assert sum(ordnung.kurztitel(e) != e.titel for e in EINSTELLUNGEN) >= 80
ok("Titel ohne Vorsilbe, die der Abschnitt schon sagt (voller Titel bleibt Tooltip und Suchwort)")

assert all(EINSTELLUNG[f.name].vorgabe == f.vorgabe and EINSTELLUNG[f.name].gruppe == "Funktionen"
           for f in funktionen.FUNKTIONEN) and len(funktionen.FUNKTIONEN) == 17
assert [f.name for f in funktionen.FUNKTIONEN if f.vorgabe != "ja"] == ["funktion_erp_preise"]      # optional: aus
assert funktionen.an("funktion_blech", None) and funktionen.seite_an("e_blech")       # ohne Datenbank: alles an
ok("17 Funktionsschalter (seit 0.9.208 mit Abruf-/Rahmenangebote, ERP-Preise), Vorgabe ja außer dem optionalen "
   "ERP-Preisimport (nach dem Update ändert sich nichts)")

# ---------------------------------------------------------------- Seiten im Programm
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
db.einstellung_setzen("passwort", "")
f = Hauptfenster(db, stumm=True)
f.resize(1366, 768)
nav = f.bereich.unter
f.zeigen(f.einstellungen)
assert nav.currentWidget() is f.einstellungen.seiten[0] and nav.currentWidget().titel == "Funktionen"
assert [g.text(0) for g in nav.gruppen.values() if not g.isHidden()][:3] == ["Allgemein", "Kalkulation", "Angebot"]
assert "Vorgaben" not in [nav.tabText(i) for i in range(nav.count())]
step = f.einstellung_zeigen("step_tol_profil")
assert step.titel == "STEP-Import" and nav.currentWidget() is step
experte = next(b for b in step.boxen if b.isCheckable())
assert experte.title() == "Toleranzen (Experte)" and not experte.isChecked()
zeile = next(z for e, form, z, b in step.zeilen if e.name == "step_tol_profil")
assert not experte.layout().isRowVisible(zeile)
nav.suche.setText("Toleranz Profil")
assert experte.isChecked() and experte.layout().isRowVisible(zeile)          # Suche klappt den Abschnitt auf
nav.suche.setText("")
assert "Zwischenspeicher leeren" in [k.text() for k in f.einstellungen.findChildren(QPushButton)]
assert f.einstellungen.seite_von("step_cache").titel == "Mein Arbeitsplatz"
nummer = f.einstellungen.seite_von("letzte_angebotsnummer")
assert any("nur dieser Arbeitsplatz" in lbl.text() for lbl in nummer.findChildren(QLabel))
f.einstellungen.felder["gewinn"].setValue(12.5)
f.einstellungen.felder["gewinn"].editingFinished.emit()
assert db.einstellung("gewinn") == 0.125
assert len(f.einstellungen.boxen) == sum(len(s.abschnitte) for s in ordnung.SEITEN)
assert all(isinstance(b, QGroupBox) for b in f.einstellungen.boxen)
ok("Navigation nach Themen, Funktionen zuerst, Experte eingeklappt, Suche klappt auf, Werte speichern wie bisher")

ziel = next(e for e in eintraege(f) if e.art == "Einstellung" and e.titel == EINSTELLUNG["palette_fuellgrad"].titel)
assert ziel.zusatz == "Einstellungen → Versand und Paletten"
ziel.aktion()
assert nav.currentWidget().titel == "Versand und Paletten"
ok("Befehlspalette nennt und öffnet die richtige Seite")

# ---------------------------------------------------------------- Funktionen ausschalten
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
assert f.reiter.isTabVisible(f.reiter.indexOf(f.zukauf)) and s.zukauf_knopf.isVisibleTo(s)
funktions_seite = f.einstellungen.seiten[0]


def schalten(name, an):
    w = funktions_seite.felder[name]
    w.setChecked(an)
    assert db.einstellung(name) == ("ja" if an else "nein"), (name, db.einstellung(name))


for name in ("funktion_zukauf", "funktion_fracht", "funktion_blech", "funktion_schweissen", "funktion_nachkalkulation",
             "funktion_simulator", "funktion_ab", "funktion_muster", "funktion_teuerung", "funktion_knick_steck"):
    schalten(name, False)
assert not f.reiter.isTabVisible(f.reiter.indexOf(f.zukauf)) and not f.reiter.isTabVisible(f.reiter.indexOf(f.fracht))
sichtbar = [nav.tabText(i) for i in nav.treffer("")]
assert "Blech-Richtpreis" not in sichtbar and "Blech-Werkstoffe" not in sichtbar and "Schweißverfahren" not in sichtbar
assert "Knickrahmen und Steckverbindung" not in sichtbar and "Funktionen" in sichtbar
assert nav.gruppen["Blech"].isHidden()                         # alle Seiten der Gruppe aus
assert not f.datei_aktionen["Preis-Simulator …"].isVisible() and f.datei_aktionen["Reklamationen …"].isVisible()
assert not s.zukauf_knopf.isVisibleTo(s) and not s.kopf_bereich.fracht_knopf.isVisibleTo(s)
assert not s.reiter.isTabVisible(s.reiter.indexOf(s._nachkalk))
s.weitere.menu().aboutToShow.emit()
aktionen = {a.text(): a.isVisible() for a in s.weitere.menu().actions()}
assert not aktionen["Auftragsbestätigung (PDF)"] and not aktionen["Varianten vergleichen …"]
assert aktionen["Werkstattpapiere (PDF)"] and aktionen["Etiketten mit QR-Code (PDF) …"]
d = TypDialog(s, ohne=[BLECH, ZUKAUF, SCHWEISS])
texte = [k.text() for k in d.findChildren(QPushButton)]
assert ROHR in texte and BLECH not in texte and ZUKAUF not in texte and SCHWEISS not in texte
halter = QWidget()
assert not MusterHaken(parent=halter).isVisibleTo(halter)
assert MusterHaken({"muster": "ja"}, parent=halter).isVisibleTo(halter)          # vorhandenes Muster bleibt
werkstoffe = next(x for x in f.seiten if x.t.name == "werkstoffe")
spalten = [i for i, (art, fd) in enumerate(werkstoffe.modell.spalten) if art == "feld" and fd.name.startswith("teuerung_")]
assert spalten and all(werkstoffe.ansicht.isColumnHidden(i) for i in spalten)
ok("Ausgeschaltet: Reiter, Seiten, Menü Datei, Knöpfe, Reiter Nachkalkulation, Ausgaben, Typen, Muster, Teuerung")

for name in ("funktion_zukauf", "funktion_fracht", "funktion_blech", "funktion_schweissen", "funktion_nachkalkulation",
             "funktion_simulator", "funktion_ab", "funktion_muster", "funktion_teuerung", "funktion_knick_steck"):
    schalten(name, True)
assert f.reiter.isTabVisible(f.reiter.indexOf(f.zukauf)) and s.zukauf_knopf.isVisibleTo(s)
assert "Blech-Richtpreis" in [nav.tabText(i) for i in nav.treffer("")]
assert f.datei_aktionen["Preis-Simulator …"].isVisible() and s.reiter.isTabVisible(s.reiter.indexOf(s._nachkalk))
assert not any(werkstoffe.ansicht.isColumnHidden(i) for i in spalten)
ok("Wieder eingeschaltet: alles wie vorher, Daten unverändert")

schalten("funktion_nachfassen", False)
f.start.neu_laden()
assert not f.start.wv_titel.isVisibleTo(f.start)
schalten("funktion_nachfassen", True)
ok("Nachfassen aus: keine Wiedervorlage auf der Startseite")
f.close()
db.schliessen()

# ---------------------------------------------------------------- Schalter vor Werten mit „0 = aus“ (Schritt 3)
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
seite = f.einstellung_zeigen("nachfassen_tage")
sw, feld = seite.wert_schalter["nachfassen_tage"], seite.felder["nachfassen_tage"]
assert set(ordnung.WERT_SCHALTER) == {n for s in f.einstellungen.seiten for n in s.wert_schalter}
assert sw.isChecked() and feld.isEnabled() and db.einstellung("nachfassen_tage") == 10
feld.setValue(14)
feld.editingFinished.emit()
sw.setChecked(False)
assert db.einstellung("nachfassen_tage") == 0 and not feld.isEnabled() and feld.value() == 14   # gemerkt, grau
sw.setChecked(True)
assert db.einstellung("nachfassen_tage") == 14 and feld.isEnabled()                         # kommt zurück
m = f.einstellung_zeigen("mindestmarge")
assert not m.wert_schalter["mindestmarge"].isChecked() and db.einstellung("mindestmarge") == 0   # Vorgabe 0 = aus
m.wert_schalter["mindestmarge"].setChecked(True)
assert db.einstellung("mindestmarge") == 0.10
st = f.einstellung_zeigen("staffeln_standard")
st.wert_schalter["staffeln_standard"].setChecked(False)
assert db.einstellung("staffeln_standard") == "" and st.felder["staffeln_standard"].text() == "1; 2; 5"
st.wert_schalter["staffeln_standard"].setChecked(True)
assert db.einstellung("staffeln_standard") == "1; 2; 5"
feld.setValue(0)
feld.editingFinished.emit()
assert not sw.isChecked() and not feld.isEnabled()                                          # 0 von Hand = aus
ok("Werte mit „0 = aus“: Schalter davor, aus merkt den Wert, an holt ihn zurück")
f.close()
db.schliessen()
