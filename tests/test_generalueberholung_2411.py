"""Generalüberholung 24.11.2026 (Master-Auftrag „UI, Performance & System Stability Overhaul“), Paket 1.

Geprüft:
- Datenschicht: Sicherungspunkt je Anweisung bleibt bis zur nächsten Anweisung stehen (ein Weg statt zwei). Wirkung
  wie vorher: ein Fehler verwirft nur die eine Anweisung, die Transaktion läuft weiter, COMMIT speichert alles
  andere, ROLLBACK verwirft alles; weniger Steueranweisungen je geschriebener Zeile.
- Öffnen der Datendatei: Protokoll-Trigger bleiben stehen (kein Löschen und Neuanlegen bei jedem Öffnen), derselbe
  Bestand an Triggern, Änderungen werden weiter protokolliert; überzählige alte Trigger fallen weg.
- Oberfläche: Hinweis in leeren Tabellen automatisch (STANDARD), eigener Text über leerhinweis.setzen, abschaltbar;
  Ereignisfilter von stil.py färbt Beschriftungen im Dunkelmodus weiter um; Schnellzugriffe behalten ihre Höhe,
  wenn sich die Spaltenzahl verdeckt ändert.
Aufruf (PostgreSQL nötig, nicht als root): python werkzeuge/mit_pg.py -- python tests/test_generalueberholung_2411.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QVBoxLayout, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])

import beispiel_angebot  # noqa: E402

from rohrlaser import db_trigger, db_verbindung, leerhinweis, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Datenschicht
pfad = Path(tempfile.mkdtemp(prefix="gu2411_")) / "Daten" / "rohrlaser.db"
pfad.parent.mkdir(parents=True)
db = Datenbank(pfad)
con = db.con
pg = con.art == "postgres"
if pg:
    steuer = []
    roh_alt, folge_alt = con.v._roh, con.v._roh_folge
    con.v._roh = lambda sql: (steuer.append(sql), roh_alt(sql))[1]
    con.v._roh_folge = lambda *a: (steuer.append("; ".join(a)), folge_alt(*a))[1]

con.execute("CREATE TABLE IF NOT EXISTS gu_probe (id INTEGER PRIMARY KEY, wert TEXT NOT NULL)")
con.commit()
with con:
    con.execute("INSERT INTO gu_probe (id, wert) VALUES (1, 'a')")
    con.execute("INSERT INTO gu_probe (id, wert) VALUES (2, 'b')")
    try:
        con.execute("INSERT INTO gu_probe (id, wert) VALUES (1, 'doppelt')")       # Schlüssel doppelt
        raise AssertionError("doppelter Schlüssel ohne Fehler")
    except db_verbindung.DbFehler:
        pass
    try:
        con.execute("INSERT INTO gu_probe (id, wert) VALUES (3, NULL)")           # NOT NULL verletzt
        raise AssertionError("NULL ohne Fehler")
    except db_verbindung.DbFehler:
        pass
    con.execute("INSERT INTO gu_probe (id, wert) VALUES (4, 'd')")             # Transaktion läuft weiter
    con.execute("UPDATE gu_probe SET wert = 'B' WHERE id = 2")
assert [tuple(r) for r in con.execute("SELECT id, wert FROM gu_probe ORDER BY id")] == [(1, "a"), (2, "B"), (4, "d")]
ok("Fehler in der Transaktion verwirft nur die eine Anweisung, COMMIT speichert den Rest")

try:
    with con:
        con.execute("INSERT INTO gu_probe (id, wert) VALUES (5, 'e')")
        con.execute("DELETE FROM gu_probe WHERE id = 1")
        raise RuntimeError("Abbruch")
except RuntimeError:
    pass
assert [r[0] for r in con.execute("SELECT id FROM gu_probe ORDER BY id")] == [1, 2, 4]
ok("Abbruch verwirft die ganze Transaktion (auch mit stehendem Sicherungspunkt)")

con.commit()
con.execute("INSERT INTO gu_probe (id, wert) VALUES (6, 'f')")
con.rollback()
con.execute("INSERT INTO gu_probe (id, wert) VALUES (7, 'g')")
con.commit()
assert [r[0] for r in con.execute("SELECT id FROM gu_probe ORDER BY id")] == [1, 2, 4, 7]
ok("commit()/rollback() von Hand wie bisher")

if pg:
    steuer.clear()
    a = db.angebot_neu(dict(beispiel_angebot.KOPF, nummer="GU-1", kunde="Probe"))
    for p in beispiel_angebot.POSITIONEN:
        db.position_neu(a, p)
    n_pos = len(beispiel_angebot.POSITIONEN)
    steuer.clear()
    db.angebot_kopieren(a)
    sp = sum(1 for s in steuer if "SAVEPOINT anweisung" in s and not s.startswith("ROLLBACK"))
    release_einzeln = sum(1 for s in steuer if s == "RELEASE SAVEPOINT anweisung")
    assert release_einzeln == 0, steuer[:10]
    kopie = max(r[0] for r in con.execute("SELECT id FROM angebote"))
    assert len(db.positionen(kopie)) == n_pos
    ok(f"Angebot kopieren: {sp} Wege für Sicherungspunkte statt doppelt so vielen (kein einzelnes RELEASE mehr)")
    con.v._roh, con.v._roh_folge = roh_alt, folge_alt

# ------------------------------------------------------------------ Öffnen: Protokoll-Trigger bleiben stehen
if pg:
    bestand1 = sorted(db_trigger.namen(con, "_protokoll"))
    db.schliessen()
    zaehler = [0]
    db_verbindung.zaehler = lambda dt: zaehler.__setitem__(0, zaehler[0] + 1)
    try:
        db = Datenbank(pfad)
    finally:
        db_verbindung.zaehler = None
    con = db.con
    bestand2 = sorted(db_trigger.namen(con, "_protokoll"))
    assert bestand1 == bestand2 and len(bestand1) > 50, (len(bestand1), len(bestand2))
    assert zaehler[0] < 600, zaehler[0]         # vorher rund 950 Anweisungen beim Öffnen
    vorher = con.execute("SELECT COALESCE(MAX(nr), 0) FROM teilen_aenderungen").fetchone()[0]
    db.position_aendern(db.positionen(a)[0]["id"], "stueck", 99)
    nachher = con.execute("SELECT COALESCE(MAX(nr), 0) FROM teilen_aenderungen").fetchone()[0]
    assert nachher > vorher, (vorher, nachher)
    ok(f"zweites Öffnen: {len(bestand2)} Protokoll-Trigger unverändert, {zaehler[0]} Anweisungen, "
       "Änderungen werden weiter protokolliert")
    # ein veralteter Trigger (gibt es nicht mehr) fällt beim Öffnen weg
    db_trigger.trigger(con, "gu_alt_protokoll", "gu_probe", "INSERT", ["SELECT 1"])
    con.commit()
    db.schliessen()
    db = Datenbank(pfad)
    con = db.con
    assert ("gu_alt_protokoll", "gu_probe") not in db_trigger.namen(con, "_protokoll")
    assert sorted(db_trigger.namen(con, "_protokoll")) == bestand1
    ok("veralteter Protokoll-Trigger wird beim Öffnen entfernt")
db.schliessen()

# ------------------------------------------------------------------ Oberfläche
stil.anwenden(app, "Hell")
w = QWidget()
lay = QVBoxLayout(w)
t1, t2, t3 = QTableWidget(0, 2), QTableWidget(0, 2), QTableWidget(0, 2)
leerhinweis.setzen(t2, "Noch keine Aufträge.")
for t in (t1, t2, t3):
    lay.addWidget(t)
w.show()
QApplication.processEvents()
leerhinweis.setzen(t3, "")
assert leerhinweis.text(t1) == leerhinweis.STANDARD, leerhinweis.text(t1)
assert leerhinweis.text(t2) == "Noch keine Aufträge."
assert leerhinweis.text(t3) == ""
bild_leer = t1.viewport().grab().toImage()
t1.setRowCount(1)
QApplication.processEvents()
assert bild_leer != t1.viewport().grab().toImage()
ok("leere Tabelle: Hinweis automatisch, eigener Text bleibt, abschaltbar")
w.close()

stil.anwenden(app, "Dunkel")
lab = QLabel("<span style='color:#1F4E78'>x</span>")
lab.show()
QApplication.processEvents()
assert "#1F4E78" not in lab.text(), lab.text()
lab.close()
stil.anwenden(app, "Hell")
ok("Ereignisfilter (schneller Vorabtest): Beschriftungen im Dunkelmodus weiter umgefärbt")

from PySide6.QtWidgets import QToolButton  # noqa: E402

from rohrlaser import startseite_karten  # noqa: E402


class _F:
    pass


karte = startseite_karten.SchnellKarte.__new__(startseite_karten.SchnellKarte)
QWidget.__init__(karte)
from rohrlaser.angebot_oben import karte as karte_bauen  # noqa: E402

karte.f = _F()
k_lay = QVBoxLayout(karte)
karte.karte, kl = karte_bauen("Schnellzugriffe")
k_lay.addWidget(karte.karte)
from PySide6.QtWidgets import QGridLayout  # noqa: E402

karte.raster = QGridLayout()
kl.addLayout(karte.raster)
karte.knoepfe = {}
for n in range(8):
    b = QToolButton()
    b.setText(f"Eine längere Funktion Nummer {n} …")
    b.setMinimumWidth(max(150, b.sizeHint().width()))
    karte.knoepfe[n] = b
karte._spalten = 0
karte.zustand = lambda: None     # Knöpfe ohne Aktionsbibliothek (nur das Layout wird geprüft)
huelle = QWidget()
h_lay = QVBoxLayout(huelle)
h_lay.addWidget(karte)
huelle.resize(1400, 600)
huelle.show()
QApplication.processEvents()
karte.anordnen()
huelle.resize(420, 600)         # schmal: eine Spalte, Karte muss höher werden
QApplication.processEvents()
QApplication.processEvents()
hoehen = {b.height() for b in karte.knoepfe.values()}
assert all(h >= b.sizeHint().height() for h, b in zip(hoehen, karte.knoepfe.values())), hoehen
ok(f"Schnellzugriffe: {karte._spalten} Spalte(n), alle Knöpfe in voller Höhe {sorted(hoehen)}")
huelle.close()

# Meine Werkzeugleiste: Neuaufbau (jeder Reiterwechsel) lässt keine alten Menüs/Aktionen/Titel zurück
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QMenu  # noqa: E402

from rohrlaser.fenster import Hauptfenster  # noqa: E402

po = Path(tempfile.mkdtemp(prefix="gu2411_f_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
leiste = f.meine_leiste


def kinder():
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    return (len(leiste.findChildren(QMenu)), len(leiste.findChildren(QAction)), len(leiste.findChildren(QLabel)))


# Paket 2: Einstellungsseiten erst bei Bedarf bauen
seiten = f.einstellungen.seiten
assert not any(s.gebaut for s in seiten), [s.titel for s in seiten if s.gebaut]
s0, s1, s2 = seiten[0], seiten[1], seiten[2]
assert s0.liste and not s0.gebaut                         # Suche kennt die Einstellungen ohne Bau
e1 = s1.liste[0]
assert f.einstellungen.seite_von(e1.name) is s1 and not s1.gebaut
feld = s1.felder[e1.name]                                 # Zugriff baut die Seite
assert s1.gebaut and feld is s1.felder[e1.name]
e2 = s2.liste[-1]
s2.filtern(e2.titel)                                      # Suche vor dem Bau gilt beim Bau
f.show()
f.bereich.zeigen(s2)
f.zeigen(f.bereich)
QApplication.processEvents()
assert s2.gebaut and s2.widget().isVisible()
sichtbar = [e.name for e, form, zeile, box in s2.zeilen if form.isRowVisible(zeile) and box.isVisible()]
assert e2.name in sichtbar, sichtbar
s2.filtern("")
f.bereich.schutz_anwenden()                               # Schutz/Admin auf gebaute und ungebaute Seiten
assert not s0.gebaut or s0 is f.bereich.unter.currentWidget()
assert set(f.einstellungen.felder) == {e.name for e in f.einstellungen.liste}
assert all(s.gebaut for s in seiten)
ok(f"Einstellungen: {len(seiten)} Seiten erst bei Bedarf gebaut (Zugriff, Zeigen, Suche vorher, alle Felder)")

leiste.neu_bauen()
vorher = kinder()
for _ in range(5):
    leiste.neu_bauen()
assert kinder() == vorher, (vorher, kinder())
f.close()
db.schliessen()
ok(f"Meine Werkzeugleiste: 5× neu aufgebaut, Menüs/Aktionen/Titel gleich viele {vorher}")
# B9: ein gemeinsamer Ereignisfilter der Anwendung
from PySide6.QtCore import QObject  # noqa: E402

from rohrlaser import ereignis_verteiler  # noqa: E402


class _Probe(QObject):
    def __init__(self, name, schlucken=False, eltern=None):
        super().__init__(eltern)
        self.name, self.schlucken, self.gesehen = name, schlucken, []

    def eventFilter(self, obj, e):
        self.gesehen.append(e.type())
        return self.schlucken


ziel = QWidget()
alt_a, neu_b = _Probe("a"), _Probe("b", schlucken=True)
ereignis_verteiler.anmelden(alt_a, (QEvent.Show, QEvent.Hide))
ereignis_verteiler.anmelden(neu_b, (QEvent.Hide,))
assert ereignis_verteiler.angemeldet()[:2] == [neu_b, alt_a]       # zuletzt angemeldet zuerst (wie Qt)
ziel.show()
QApplication.processEvents()
ziel.hide()
QApplication.processEvents()
assert QEvent.Show in alt_a.gesehen and QEvent.Hide not in alt_a.gesehen, alt_a.gesehen   # b verschluckt Hide
assert set(neu_b.gesehen) == {QEvent.Hide}, neu_b.gesehen                                      # nur seine Arten
eltern = QObject()
kurz = _Probe("kurz", eltern=eltern)
ereignis_verteiler.anmelden(kurz, (QEvent.Show,))
assert kurz in ereignis_verteiler.angemeldet()
eltern.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
assert all(f.__class__ is not _Probe or f.name != "kurz" for f in ereignis_verteiler.angemeldet())
ereignis_verteiler.abmelden(alt_a)
ereignis_verteiler.abmelden(neu_b)
n_show = len(alt_a.gesehen)
ziel.show()
QApplication.processEvents()
assert len(alt_a.gesehen) == n_show, alt_a.gesehen                                             # abgemeldet
ok("Ereignisverteiler: Reihenfolge wie Qt, Verschlucken, nur angemeldete Arten, Abmelden auch beim Löschen")

# ---- Paket 3 (Phase 4): weiße Schrift auf umgesetzter Akzentfläche bleibt im Dunkelmodus lesbar
for roh in ("QToolButton#weiter { color: white; background: #1F4E78; border: none; }",
            "QPushButton#ansicht:checked { background: #1F5FAD; color: white; } QPushButton { color: #1F2937; }"):
    assert stil.umsetzen(roh, "Hell") == roh                                     # Hell Zeichen für Zeichen gleich
    dunkel = stil.umsetzen(roh, "Dunkel")
    block = dunkel.split("}")[0]
    grund = re.search(r"background: (#[0-9A-F]{6})", block).group(1)
    schrift = re.search(r"(?<![-\w])color: (#[0-9A-Fa-f]{6})", block).group(1)
    assert stil.kontrast(schrift, grund) >= 4.5, (roh, dunkel, stil.kontrast(schrift, grund))
assert "color: white" in stil.umsetzen("QToolButton:checked { background: #2F6FB3; color: white; }", "Dunkel")
assert stil.umsetzen("border-color: white; background: #1F4E78", "Dunkel") == "border-color: white; background: #6CA6DE"
assert "#E6EAF0" in stil.umsetzen("QToolButton#weiter { color: white; background: #1F4E78; } QLabel { color: #1F2937; }",
                                  "Dunkel")
ok("Dunkelmodus: weiße Schrift auf Akzentfläche wird lesbar (mind. 4,5 : 1), Hell unverändert")
print("Alle Prüfungen bestanden.")
