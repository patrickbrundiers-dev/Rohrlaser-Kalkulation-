"""Leistung im Angebot (Performance-Audit, F7): Regeln, die große Angebote schnell halten, und grobe Zeitgrenzen.

Geprüft wird ohne Bildschirm (QT_QPA_PLATFORM=offscreen):
- verdeckte Tabellen werden erst beim Zeigen eingepasst (spaltenbreite.AutoGroesse),
- die Spaltenbreite misst höchstens die sichtbaren und PRUEF_ZEILEN Zeilen,
- Liste.data antwortet auf Rollen, die sie nicht bedient, sofort,
- rechnen.kalkulation läuft je Neuladen eines Angebots nur einmal, Öffnen lädt nur einmal,
- die Suche der Angebotsliste filtert erst nach der Tipp-Pause (suchen() sofort),
- Zeitgrenzen für ein Angebot mit 200 Positionen und eine Liste mit 300 Angeboten. Die Grenzen sind großzügig
  (etwa das Dreifache der gemessenen Zeit), aber kleiner als vor dem Audit: ein Rückfall fällt auf.

Gemessene Werte (Container, 4 Kerne, 23.10.2026): Öffnen 0,5 s, Zelle ändern 0,4 s, Knopf Angebots-PDF 4,4 s.
Aufruf: python tests/test_angebot_leistung.py
"""
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_fenster, rechnen, spaltenbreite  # noqa: E402
from rohrlaser.angebot_fenster import Liste, _tabelle  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

GRENZE_OEFFNEN = 2.0        # s, Angebot mit 200 Positionen öffnen (optimiert), vor dem Audit 2,4 s
GRENZE_ZELLE = 1.5          # s, Stückzahl ändern bis Anzeige fertig, vorher 1,1 s
GRENZE_PDF = 15.0           # s, Knopf Angebots-PDF mit 6 veralteten Staffelmengen, vorher 21,6 s
GRENZE_SUCHE = 1.0          # s, Liste mit 300 Angeboten nach der Tipp-Pause gefiltert

PROFILE = ["RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"]
WERKSTOFFE = ["S235-10219", "S355-10219", "1.4301"]


def ok(text):
    print("OK    ", text)


def dauer(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def positionen(n, seed=1):
    """Gemischte Positionen wie im Performance-Audit (Gehrungen, Zusatzarbeiten, Sätze)."""
    rnd = random.Random(seed)
    for i in range(n):
        p = dict(pos=10 * (i + 1), artikel=f"ART-{i:04d}", bezeichnung=f"Teil {i}",
                 profil_id=PROFILE[i % len(PROFILE)], werkstoff_id=WERKSTOFFE[(i // 5) % len(WERKSTOFFE)],
                 laenge=float(rnd.choice([rnd.randint(80, 600), rnd.randint(600, 2500), rnd.randint(2500, 5800)])),
                 stueck=rnd.choice([1, 2, 4, 6, 8, 10, 12, 20, 40]),
                 schneidweg=round(rnd.uniform(250, 1200), 1), einstiche=rnd.randint(2, 10))
        if i % 6 == 5:
            p["b_gerade"] = "nein"
        if i % 10 == 3:
            p["zusatz"] = json.dumps([dict(name="Entgraten")])
        if i % 15 == 7:
            p["satz"], p["je_satz"] = f"Satz {i // 15}", 2
        yield p


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ verdeckte Tabelle, Prüfzeilen, Rollen
liste = Liste([("Nr.", "nr", 0, 60), ("Text", "text", None, 60)])
v = _tabelle(liste, sortieren=False)
ag = v.auto_groesse
liste.setzen([dict(nr=i, text=f"Zeile {i}") for i in range(50)])
app.processEvents()
assert not ag.eingepasst and ag._offen, "verdeckte Tabelle wird erst beim Zeigen eingepasst"
v.resize(600, 300)
v.show()
app.processEvents()
assert ag.eingepasst and not ag._offen
ok("verdeckte Tabelle: Einpassen beim Zeigen nachgeholt")
assert v.horizontalHeader().resizeContentsPrecision() == spaltenbreite.PRUEF_ZEILEN
ok(f"Spaltenbreite aus sichtbaren und höchstens {spaltenbreite.PRUEF_ZEILEN} Zeilen")
i = liste.index(0, 1)
assert liste.data(i, Qt.DecorationRole) is None and liste.data(i, Qt.SizeHintRole) is None
assert liste.data(i) == "Zeile 0" and liste.data(i, Qt.UserRole) == "Zeile 0"
ok("Liste.data: nicht bediente Rollen sofort None, Anzeige unverändert")

# ------------------------------------------------------------------ Angebot mit 200 Positionen
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Leistungstest", kundennr="K-10045", maschine="T11", stange=6000))
for p in positionen(200):
    db.position_neu(a, p)
for schl, menge in (("10", 24), ("10", 50), ("10", 100), ("20", 10), ("20", 40), ("20", 100)):
    db.staffel_neu(a, dict(schluessel=schl, menge=menge))
s = f.angebot_oeffnen(a)
s.optimieren()
f.angebot_schliessen(a)
app.processEvents()

zaehler = {"kalkulation": 0, "neu_laden": 0}
original_kalk, original_laden = rechnen.kalkulation, angebot_fenster.AngebotSeite._neu_laden


def kalk_zaehlen(*a, **k):
    zaehler["kalkulation"] += 1
    return original_kalk(*a, **k)


def laden_zaehlen(self, *a, **k):
    zaehler["neu_laden"] += 1
    return original_laden(self, *a, **k)


rechnen.kalkulation = kalk_zaehlen
angebot_fenster.AngebotSeite._neu_laden = laden_zaehlen
try:
    t = dauer(lambda: f.angebot_oeffnen(a))
    s = f.offen[a]
    assert zaehler["neu_laden"] == 1, f"Öffnen lädt {zaehler['neu_laden']}x"
    ok(f"Angebot öffnen lädt einmal ({t:.2f} s, Grenze {GRENZE_OEFFNEN} s)")
    assert t < GRENZE_OEFFNEN, t
    zaehler.update(kalkulation=0, neu_laden=0)
    s.neu_laden()
    assert zaehler["neu_laden"] == 1 and zaehler["kalkulation"] == 1, zaehler
    ok("Neuladen rechnet die Kalkulation einmal")
finally:
    rechnen.kalkulation, angebot_fenster.AngebotSeite._neu_laden = original_kalk, original_laden

m = s.pos_modell
c = next(i for i, (_, fd) in enumerate(m.spalten) if getattr(fd, "name", None) == "stueck")
zeiten = []
for wert in ("7", "9", "11"):
    zeiten.append(dauer(lambda: (m.setData(m.index(0, c), wert, Qt.EditRole), app.processEvents())))
t = sorted(zeiten)[1]
assert t < GRENZE_ZELLE, zeiten
ok(f"Zelle ändern bis Anzeige fertig {t:.2f} s (Grenze {GRENZE_ZELLE} s)")

t = dauer(s.angebot_pdf)
assert t < GRENZE_PDF, t
ok(f"Knopf Angebots-PDF mit Staffeln {t:.2f} s (Grenze {GRENZE_PDF} s)")
f.angebot_schliessen(a)
app.processEvents()

# ------------------------------------------------------------------ Angebotsliste: Suche nach der Tipp-Pause
klein = db.angebot_neu(dict(kunde="Suchkunde", kundennr="K-77", maschine="T11", stange=6000))
for p in positionen(3, seed=2):
    db.position_neu(klein, p)
while len(db.angebote()) < 300:
    db.angebot_kopieren(a if len(db.angebote()) % 2 else klein)
seite = f.angebote
f.reiter.setCurrentWidget(seite)
seite.neu_laden()
app.processEvents()
alle = seite.filter.rowCount()
assert alle >= 300, alle
seite.suche.setText("Suchkunde")
app.processEvents()
assert seite.filter.rowCount() == alle and seite._such_timer.isActive(), "Suche wartet die Tipp-Pause ab"
t0 = time.perf_counter()
while seite._such_timer.isActive():
    QTest.qWait(10)
app.processEvents()
t = time.perf_counter() - t0
treffer = seite.filter.rowCount()
assert 0 < treffer < alle, treffer
assert t < GRENZE_SUCHE + angebot_fenster.SUCHE_PAUSE_MS / 1000, t
ok(f"Suche nach der Tipp-Pause: {treffer} von {alle} Angeboten in {t:.2f} s (inkl. Pause)")
seite.suchen("")
assert seite.filter.rowCount() == alle and not seite._such_timer.isActive()
assert f.kunden_angebote("K-77") == treffer
ok("suchen() und Angebote eines Kunden filtern sofort")
print("Alle Leistungsprüfungen bestanden.")
