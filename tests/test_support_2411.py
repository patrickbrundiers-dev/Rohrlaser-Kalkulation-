"""Supportpaket 24.11.2026: Hänger nach dem ERP-Einkauf.

Mit vielen eingelesenen Käufen erkannte erp_preise.artikel() bei jedem Aufruf (Optimieren, Material …, Seite
Material, STEP-Import, ERP-Import) alle EK-Artikel neu; profil_finden ging je Artikel alle Profile mit regulären
Ausdrücken durch. Geprüft:
- zerlegen() merkt sich die Erkennung je Stammdaten-Kontext, Ergebnis gleich und als eigene Kopie,
- ein neues Profil (neuer Kontext) wird sofort erkannt, der Merker liefert nichts Altes,
- profil_finden mit Vorfilter findet dasselbe wie vorher (längste wörtliche Profil-ID gewinnt),
- die Prüfliste ERP-Artikel legt Auswahlfelder erst beim Wählen der Zeile an; setzen() und Merken gehen weiter,
- Tempo: zweiter Aufruf von artikel() mit 2.000 Käufen deutlich schneller als der erste,
- gespeicherte() aus dem Merker, neu nach speichern() und kauf_rechnen(),
- Auswahllisten der Prüfspalte (Kontext.auswahl/in_auswahl) gemerkt, neue/archivierte Profile sofort richtig,
- Schweißbaugruppen-Editor baut das 3D-Modell beim Öffnen nur einmal.

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

# ------------------------------------------------------------------ gespeicherte() mit Merker
g1 = E.gespeicherte(db)
g1[0]["preis"] = -1
assert E.gespeicherte(db)[0]["preis"] != -1 and len(E.gespeicherte(db)) == len(g1)
E.speichern(db, [dict(kaeufe[0], datum=HEUTE, menge=999, preis=1.5)], "neu.csv")
g2 = E.gespeicherte(db)
assert len(g2) == len(g1) + 1 and any(k["menge"] == 999 for k in g2)
kid = next(k["id"] for k in g2 if k["menge"] == 999)
E.kauf_rechnen(db, kid, False)
assert next(k for k in E.gespeicherte(db) if k["id"] == kid)["rechnen"] == 0
ok("gespeicherte(): Merker mit eigener Kopie, neu nach speichern() und kauf_rechnen()")

# ------------------------------------------------------------------ Auswahllisten der Prüfspalte
from rohrlaser import stammdaten as S  # noqa: E402

k4 = db.kontext()
liste = k4.auswahl("profil")
assert liste == sorted(n for n, z in k4.profile.items() if not S._archiviert(z))
liste.append("XYZ")
assert "XYZ" not in k4.auswahl("profil") and not k4.in_auswahl("profil", "XYZ")
assert k4.in_auswahl("janein", "ja") and not k4.in_auswahl("janein", "vielleicht")
k5 = S.Kontext(profile={"RR 10x1": dict(profil_id="RR 10x1")})
assert k5.auswahl("profil") == ["RR 10x1"]
k5.profile["RR 12x1"] = dict(profil_id="RR 12x1")
assert k5.in_auswahl("profil", "RR 12x1")
k5.profile = {"RR 10x1": dict(profil_id="RR 10x1", archiviert="ja")}
assert k5.auswahl("profil") == []
z = dict(next(iter(db.zeilen("preise")), {}) or {})
if z.get("profil_id"):
    assert not S.pruefen(S.PREISE, z, k4).endswith("unbekannt")
    assert S.pruefen(S.PREISE, dict(z, profil_id="GIBT ES NICHT"), k4).endswith("unbekannt")
ok("Auswahllisten gemerkt je Stand: Kopie je Aufruf, neue und archivierte Profile sofort richtig")

# ------------------------------------------------------------------ Schweißbaugruppe: 3D beim Öffnen einmal
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import step_messen  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402

t2 = tmp / "bg"
t2.mkdir()
step_messen.main(["--ausgabe", str(t2 / "m.txt"), "--json", str(t2 / "m.json"), "--netze", str(t2 / "netze"),
                  str(HIER / "step_struktur" / "S03_Rahmen_geschweisst.step")])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(t2 / "m.txt"), t2 / "netze"), t2 / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
db2 = Datenbank(t2 / "b.db")
erg = step.uebernehmen(mw, [], db2.kontext(), db2.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                       zukauf_liste=[])
db2.profile_anlegen(erg["profile"])
a2 = db2.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db2.position_neu(a2, q)
    if netz:
        db2.netz_speichern(pid, netz)
positionen = db2.positionen(a2)
bgp = next(q for q in positionen if q.get("art") == BAUGRUPPE)
gezeigt = []
_alt = BaugruppeDialog.zeige_3d
BaugruppeDialog.zeige_3d = lambda self, *a, **kw: gezeigt.append(1) or _alt(self, *a, **kw)
try:
    d = BaugruppeDialog(None, bgp, positionen, db2.tabellen(), {"Schweißen": 75.0}, db=db2, netze=db2.netze(a2),
                        profile=db2.kontext().profile)
finally:
    BaugruppeDialog.zeige_3d = _alt
assert d.ansicht3d is not None and len(gezeigt) == 1, gezeigt
assert d.ansicht3d.ansicht.modell is not None
d.reject()
ok("Schweißbaugruppen-Editor: 3D-Modell beim Öffnen einmal gebaut (vorher zweimal)")
print("Alle Prüfungen bestanden.")
