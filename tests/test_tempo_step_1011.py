"""Plan „schneller bedienen, Ladezeiten, STEP-Import messen und beschleunigen“ (Patrick 10.11.2026).

Geprüft wird ohne Bildschirm:
- Querschnitt-Suche (step_geometrie._profil_messen): gleiche Lagen werden nur einmal geschnitten, das Messergebnis
  ist dasselbe wie ohne Merker (SCHNITTE_MERKEN = False = Ablauf vor dem 10.11.2026),
- Erreichbarkeit der Nähte: ein Punkt-Klassifizierer je Körper statt je Punkt, Ergebnis gleich (alter Ablauf mit
  einem neuen Klassifizierer je Aufruf nachgebaut),
- Tempo-Protokoll der Messung: step_messen._zeiten_melden schreibt eine Zeile „ZEITEN {json}“ mit Lesen, Abschluss
  und den langsamsten Körpern; das Programm macht daraus „Messung STEP-Messung …“ im tempo.log,
- tempo.messung/messungen/auswerten: Messungen zählen nicht als langsame Schritte und stehen im Abschnitt
  „Messungen“ des Support-Pakets; prozess_alter liefert eine plausible Zahl,
- Startseite: verdeckt (Programmstart im Reiter Angebote) wird sie nur als veraltet gemerkt und beim Zeigen gefüllt,
  im Selbsttest (stumm) sofort wie bisher.
Aufruf: python tests/test_tempo_step_1011.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_ergebnis  # noqa: E402
import step_geometrie as g  # noqa: E402
import step_messen  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("ok    " if bedingung else "FEHLER ") + text)
    if not bedingung:
        fehler.append(text)


def ergebnis_text(gel, teile):
    return json.dumps(step_ergebnis.datei("x", teile), sort_keys=True, default=str)


def alle_messen(datei, abschliessen=False):
    gel = g.datei_lesen(datei)
    teile = {k: g.teil_uebergeben(g.koerper_messen(gel, k, True, 0, {}))
             for k in range(1, len(gel.koerper) + 1) if k not in gel.gleich}
    if abschliessen:
        return ergebnis_text(gel, g.datei_abschliessen(gel, teile, True, 0, {}, None))
    return ergebnis_text(gel, [teile[k] for k in sorted(teile)])


# --------------------------------------------------------------------------------------- Querschnitt-Merker
zaehler = []
_orig = g._schnitt


def gezaehlt(shape, z):
    zaehler.append((id(shape), z))
    return _orig(shape, z)


g._schnitt = gezaehlt
for name in ("P04_L40x40x4_L800.step", "P08_FL40x5_L800.step", "P01_U50x30x3_L800.step"):
    datei = HIER / "step_profile" / name
    zaehler.clear()
    g.SCHNITTE_MERKEN = False
    alt = alle_messen(datei)
    n_alt = len(zaehler)
    zaehler.clear()
    g.SCHNITTE_MERKEN = True
    neu = alle_messen(datei)
    n_neu = len(zaehler)
    pruefe(alt == neu, f"{name}: Messergebnis mit Merker gleich")
    pruefe(n_neu < n_alt, f"{name}: weniger Schnitte ({n_alt} -> {n_neu})")
g._schnitt = _orig

# --------------------------------------------------------------------------------------- Erreichbarkeit
import OCP.BRepClass3d as bc  # noqa: E402

_Klassifizierer = bc.BRepClass3d_SolidClassifier


class JeAufrufNeu:
    """Ablauf vor dem 10.11.2026: je Punkt ein neuer Klassifizierer."""
    def __init__(self, k, *rest):
        self.k, self.s = k, None
        if rest:
            self.Perform(*rest)

    def Perform(self, q, tol):     # noqa: N802 – Name wie OpenCascade
        self.s = _Klassifizierer(self.k, q, tol).State()

    def State(self):               # noqa: N802
        return self.s


from erzeuge_testteile import baugruppe as zusammen, kastenrohr, schreibe  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


tmp_bg = Path(tempfile.mkdtemp())
with contextlib.redirect_stdout(io.StringIO()):     # wie test_bg_erreichbar: Rohr auf Platte, Haube über einem Klotz
    schreibe(zusammen(box(-150, -150, -10, 300, 300, 10), kastenrohr(60, 40, 3, 500, 4)), "rohr_platte", tmp_bg)
    schreibe(zusammen(box(-150, -150, -10, 300, 300, 10), box(-20, -20, 0, 40, 40, 5), box(-60, -60, 5, 120, 120, 5),
                      box(-60, -60, 0, 120, 5, 5), box(-60, 55, 0, 120, 5, 5), box(-60, -55, 0, 5, 110, 5),
                      box(55, -55, 0, 5, 110, 5)), "haube", tmp_bg)


def naehte(name):
    return json.dumps(g.analysiere_datei(tmp_bg / f"{name}.step")[0].naehte, sort_keys=True, default=str)


for name in ("rohr_platte", "haube"):
    neu = naehte(name)
    bc.BRepClass3d_SolidClassifier = JeAufrufNeu
    try:
        alt = naehte(name)
    finally:
        bc.BRepClass3d_SolidClassifier = _Klassifizierer
    pruefe(alt == neu, f"{name}: Nahtkandidaten und Erreichbarkeit gleich wie mit Klassifizierer je Punkt")
    pruefe('"zugang"' in neu, f"{name}: Erreichbarkeit wurde gerechnet")

# --------------------------------------------------------------------------------------- Abstand im Nahbereich
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402


def voll(a, b, grenze):
    d = BRepExtrema_DistShapeShape(a, b)
    return d.Value() if d.IsDone() and d.Value() <= grenze else None


gross = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 100, 100, 100).Solid()
faelle = {"innen (ganz im anderen)": box(40, 40, 40, 10, 10, 10), "Spalt 1,5 mm": box(101.5, 0, 0, 20, 20, 20),
          "Berührung": box(100, 20, 20, 20, 20, 20), "durchdringend": box(90, 20, 20, 20, 20, 20),
          "weit weg": box(200, 0, 0, 20, 20, 20), "Spalt 2,9 mm über Eck": box(102.9, 102.9, 0, 10, 10, 10)}
for name, k in faelle.items():
    for a, b in ((gross, k), (k, gross)):
        pruefe(g._abstand(a, b, 3.0) == voll(a, b, 3.0), f"Abstand {name}: {g._abstand(a, b, 3.0)} wie ganz gemessen")
for name in ("rohr_platte", "haube"):
    neu = naehte(name)
    g.ABSTAND_FILTERN = False
    try:
        alt = naehte(name)
    finally:
        g.ABSTAND_FILTERN = True
    pruefe(alt == neu, f"{name}: Nahtkandidaten mit Abstand im Nahbereich gleich")

ring = [[5, 0, 0, 5, 5, 0], [5, 5, 0, 0, 5, 0], [0, 5, 0, 0, 0, 0], [0, 0, 0.1, 5, 0, 0]]     # Rundung: 0,1 mm
pruefe(all(g._zug_ordnen(r[i:] + r[:i]) == g._zug_ordnen(ring) for r in (ring, ring[::-1]) for i in range(4)),
       "geschlossener Nahtzug: immer dieselbe Anfangskante und Richtung")
offen_ = [[5, 0, 0, 5, 5, 0], [0, 0, 0, 5, 0, 0]]
pruefe(g._zug_ordnen(offen_) == offen_, "offener Nahtzug bleibt, wie er ist")

# --------------------------------------------------------------------------------------- Zeiten der Messung
aus = io.StringIO()
with contextlib.redirect_stdout(aus):
    step_messen._zeiten_melden([("datei", "a.step", None, 0.4, "geteilt"), ("koerper", "a.step", 3, 2.5, "teil"),
                                ("koerper", "a.step", 1, 0.7, "teil"), ("abschluss", "a.step", None, 4.2, "fertig"),
                                ("datei", "b.step", None, 1.1, "fertig")], 9.87, 3)
zeile = aus.getvalue().strip()
pruefe(zeile.startswith("ZEITEN "), "step_messen meldet ZEITEN")
z = json.loads(zeile[7:])
pruefe(z["dateien"] == {"a.step": {"lesen": 0.4, "abschluss": 4.2}, "b.step": {"ganz": 1.1}},
       f"Lesen/Abschluss je Datei ({z['dateien']})")
pruefe(z["langsamste"][0] == ["a.step", 3, 2.5] and z["koerper_n"] == 2 and z["gesamt_s"] == 9.9,
       "langsamste Körper zuerst, Anzahl und Gesamtzeit")

# --------------------------------------------------------------------------------------- Tempo-Protokoll
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import tempo  # noqa: E402
from rohrlaser.angebot_fenster import step_messung_protokollieren  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    w = tempo.Waechter(Path(tmp))
    w.starten()
    try:
        liste = Path(tmp) / "liste.txt"
        (Path(tmp) / "a.step").write_bytes(b"x" * 2_000_000)
        liste.write_text(str(Path(tmp) / "a.step"), encoding="utf-8")
        text = step_messung_protokollieren(12.34, 1, dict(zeiten=z), ["x", "--liste", str(liste)])
        pruefe(text and text.startswith("Messung STEP-Messung 12.3 s | 1 Datei, 2.0 MB"), f"Programm: {text}")
        pruefe("langsamste: a.step K3 2.5 s" in text and "Abschluss 4.2 s" in text, "Programm: Abschluss, langsamste")
        tempo.messung("Programmstart", 2.5, "1000 Angebote")
        tempo.messung("Programmstart", 3.5)
    finally:
        w.stoppen()
    m = tempo.messungen(Path(tmp))
    pruefe([(a, s) for _, a, s, _ in m] == [("STEP-Messung", 12.3), ("Programmstart", 2.5), ("Programmstart", 3.5)],
           f"Messungen gelesen ({m})")
    pruefe(tempo.lesen(Path(tmp)) == [], "Messungen zählen nicht als langsame Schritte")
    bericht = tempo.auswerten(Path(tmp))
    pruefe("Messungen (Anzahl, Mittel, längste):" in bericht and "Programmstart: 2 ×, Ø 3.0 s, bis 3.5 s" in bericht,
           "Support-Paket nennt die Messungen")
alter = tempo.prozess_alter()
pruefe(alter is None or 0 <= alter < 3600, f"prozess_alter plausibel ({alter})")

# --------------------------------------------------------------------------------------- Startseite
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    db = Datenbank(Path(tmp) / "rohrlaser.db")
    f = Hauptfenster(db, Path(tmp), stumm=True)
    pruefe(not getattr(f.start, "_veraltet", False) and hasattr(f.start, "pipeline_werte"),
           "stumm: Startseite sofort gefüllt")
    f.close()
    f2 = Hauptfenster(db, Path(tmp), stumm=False)
    pruefe(f2.start._veraltet and not hasattr(f2.start, "pipeline_werte"), "verdeckt: Startseite noch nicht gefüllt")
    f2.reiter.setCurrentWidget(f2.angebote)
    f2.show()
    app.processEvents()
    f2.start.neu_laden()
    pruefe(f2.start._veraltet, "Aktualisieren im verdeckten Zustand merkt nur veraltet")
    f2.reiter.setCurrentWidget(f2.start)
    app.processEvents()
    pruefe(not f2.start._veraltet and hasattr(f2.start, "pipeline_werte"), "beim Zeigen gefüllt")
    f2.close()
    db.schliessen()

print("\n" + ("FEHLER: " + "; ".join(fehler) if fehler else "Alle Prüfungen bestanden."))
sys.exit(1 if fehler else 0)
