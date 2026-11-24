"""Supportpaket 24.11.2026: Hänger nach dem ERP-Einkauf.

Mit vielen eingelesenen Käufen erkannte erp_preise.artikel() bei jedem Aufruf (Optimieren, Material …, Seite
Material, STEP-Import, ERP-Import) alle EK-Artikel neu; profil_finden ging je Artikel alle Profile mit regulären
Ausdrücken durch. Geprüft:
- zerlegen() merkt sich die Erkennung je Stammdaten-Kontext, Ergebnis gleich und als eigene Kopie,
- ein neues Profil (neuer Kontext) wird sofort erkannt, der Merker liefert nichts Altes,
- profil_finden mit Vorfilter findet dasselbe wie vorher (längste wörtliche Profil-ID gewinnt),
- die Prüfliste ERP-Artikel legt Auswahlfelder erst beim Wählen der Zeile an; setzen() und Merken gehen weiter,
- Tempo: zweiter Aufruf von artikel() mit 2.000 Käufen deutlich schneller als der erste.

Aufruf: python tests/test_support_2411.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from rohrlaser import erp_preise as E  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.erp_preise_dialog import ErpPreiseDialog  # noqa: E402
from rohrlaser.profil_neu import profil_id  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
HEUTE = datetime.date.today()


def ok(text):
    print("OK    ", text)


db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
with db.con:
    for a in (21.3, 26.9, 33.7, 42.4, 48.3, 60.3, 76.1, 88.9):
        for w in (2.0, 2.6, 3.2, 4.0):
            pid = profil_id("Rundrohr", a, None, w)
            if pid not in k.profile:
                db.neu("profile", dict(profil_id=pid, form="Rundrohr", a=a, wand=w))
k = db.kontext()
TEXTE = ["RR 42,4x2,6 S235JRH EN 10219", "QR 40x40x3 S235JRH EN 10219", "Rundrohr 60,3x3,2 S355J2H EN10210",
         "Sechskantschraube M8x20 DIN 933 8.8 verzinkt", "RR 88,9x4 1.4301 geschliffen", "Blech 3mm S235JR 2000x1000"]
kaeufe = []
for i in range(2000):
    t = TEXTE[i % len(TEXTE)] + ("" if i % 7 else f" Pos{i % 300}")
    kaeufe.append(dict(zeile=i, datum=HEUTE - datetime.timedelta(days=i % 400), menge=6 + i % 90, preis=2 + i % 17,
                       artikelnr=f"A{i % 700}", bezeichnung=t, schluessel=E.schluessel(f"A{i % 700}", t)))
E.speichern(db, kaeufe, "ek.csv")

# ------------------------------------------------------------------ Merker je Kontext
e1 = E.zerlegen("RR 42,4x2,6 S235JRH EN 10219", k)
e2 = E.zerlegen("RR 42,4x2,6 S235JRH EN 10219", k)
assert e1 == e2 == E._zerlegen("RR 42,4x2,6 S235JRH EN 10219", k) and e1 is not e2
assert e1["profil_id"] == profil_id("Rundrohr", 42.4, None, 2.6), e1
e1["kandidaten"].append("X")
assert "X" not in E.zerlegen("RR 42,4x2,6 S235JRH EN 10219", k)["kandidaten"]
ok("zerlegen: gleiches Ergebnis aus dem Merker, jede Ausgabe eine eigene Kopie")

neu = E.zerlegen("RR 101,6x5 S235JRH EN 10219", k)
assert neu["profil_id"] is None and neu["vorschlag"]
db.neu("profile", dict(profil_id=neu["vorschlag"]["profil_id"], form="Rundrohr", a=101.6, wand=5.0))
k2 = db.kontext()
assert k2 is not k and E.zerlegen("RR 101,6x5 S235JRH EN 10219", k2)["profil_id"] == neu["vorschlag"]["profil_id"]
k2.profile["RR 999x9"] = dict(profil_id="RR 999x9", form="Rundrohr", a=999, wand=9)   # Kontext von Hand geändert
assert E.zerlegen("Rohr RR 999x9 S235JRH", k2)["profil_id"] == "RR 999x9"
del k2.profile["RR 999x9"]
ok("neues Profil wird sofort erkannt (neuer Kontext bzw. geänderte Profil-Tabelle leert den Merker)")

# ------------------------------------------------------------------ profil_finden wie vorher
prof = {"QR 40": dict(form="Quadratrohr"), "QR 40x40x3": dict(form="Quadratrohr", a=40, b=40, wand=3),
        "IPE 200": dict(form="IPE")}
assert E.profil_finden("QR 40x40x3 S235", prof)[0] == "QR 40x40x3"         # längste wörtliche ID
assert E.profil_finden("IPE 2000 S235", prof)[0] is None                    # Ziffer dahinter: kein Treffer
assert E.profil_finden("Träger IPE200 S235JR", prof)[0] == "IPE 200"
prof["IPE 220"] = dict(form="IPE")
assert E.profil_finden("IPE 220 S235", prof)[0] == "IPE 220"               # neue ID gilt sofort
ok("profil_finden mit Vorfilter: längste ID, Ziffer-Grenzen, neue Profile wie bisher")

# ------------------------------------------------------------------ Tempo
liste = E.gespeicherte(db)
k3 = db.kontext()
t0 = time.perf_counter()
a1 = E.artikel(liste, E.zuordnungen(db), k3, E.nummern_von(db))
t1 = time.perf_counter()
a2 = E.artikel(liste, E.zuordnungen(db), k3, E.nummern_von(db))
t2 = time.perf_counter()
assert a1 == a2 and len(a1) > 300
assert t2 - t1 < max(0.5, (t1 - t0) * 0.6), (t1 - t0, t2 - t1)
ok(f"artikel(): {len(a1)} EK-Artikel, erster Aufruf {t1 - t0:.2f} s, zweiter {t2 - t1:.2f} s")

# ------------------------------------------------------------------ Prüfliste: Auswahlfelder bei Bedarf
w = QWidget()
d = ErpPreiseDialog(w, db, "Test", heute=HEUTE)
t = d.artikel_tab
assert t.rowCount() == len(d.artikel) and all(t.cellWidget(r, 5) is None for r in range(t.rowCount()))
r = next(i for i, a in enumerate(d.artikel) if a["bezeichnung"].startswith("Sechskantschraube"))
assert t.item(r, 5).text() == "" and t.item(r, 8).text()
t.setCurrentCell(r, 2)
assert t.cellWidget(r, 5) is not None and t.cellWidget(r, 6) is not None
schraube = d.artikel[r]["schluessel"]
d.setzen(r, profil="– überspringen –")
assert E.zuordnungen(db)[schraube]["ignorieren"] == 1
r = next(i for i, a in enumerate(d.artikel) if a["schluessel"] == schraube)
assert t.item(r, 5).text() == "– überspringen –" and d.artikel[r]["hinweis"] == "übersprungen (gemerkt)"
ok("Prüfliste: Text statt Auswahlfelder, Felder beim Wählen der Zeile, Überspringen wird gemerkt")
print("Alle Prüfungen bestanden.")
