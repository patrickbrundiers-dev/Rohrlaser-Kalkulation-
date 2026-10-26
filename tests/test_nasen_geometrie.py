"""Stecknasen als echte Geometrie (Patrick 26.10.2026 „Deine anderen Idee auch einbauen“): der Schneidweg der Enden
mit Nasen aus der Formel des Schneidweg-Rechners muss dem Schnitt entsprechen, den die STEP-Messung am 3D-Körper der
Nasen (step_export.rohr_teil) misst. Quadratrohr mit 1, 2 und 4 Nasen, Rundrohr mit 2 Nasen.

Aufruf: python tests/test_nasen_geometrie.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
sys.path.insert(0, str(PROGRAMM / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import step_messen  # noqa: E402
from rohrlaser import rechnen, schneidweg as sw, step, step_export as se, steckverbindung as stv  # noqa: E402

tmp = Path(tempfile.mkdtemp())
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3", r_aussen=6)
QA = dict(form="Quadratrohr", a=60, b=60, wand=3, profil_id="QR 60x60x3", r_aussen=6)
RR = dict(form="Rundrohr", a=48.3, wand=3, profil_id="RR 48,3x3")
RA = dict(form="Rundrohr", a=88.9, wand=3, profil_id="RR 88,9x3")
fehler = 0

for name, prof, auf, n in (("QR 1 Nase", QR, QA, 1), ("QR 2 Nasen", QR, QA, 2), ("QR 4 Nasen", QR, QA, 4),
                           ("RR 2 Nasen", RR, RA, 2)):
    blk = stv.nasen_block(dict(id="sv1", anzahl=n, bN=12, c=0.2, ueberstand=0), auf, prof)
    e = dict(a=dict(nasen=blk), b={}, konturen=[])
    erg = sw.rechnen(e, prof, rechnen.kontur_regel(None, 3), laenge=300)
    datei = tmp / f"n{n}_{prof['form']}.step"
    r = se.schreiben([se.rohr_teil(e, prof, 300)], datei, PROGRAMM)
    assert r.get("ok") and datei.is_file(), r
    aus = datei.with_suffix(".txt")
    step_messen.main(["--ausgabe", str(aus), str(datei)])
    m = step.lies_messwerte(aus)[0]
    formel, gemessen = erg["felder"]["a_schnitt"], float(m["ende_a"])
    gerade = erg["felder"]["b_schnitt"]
    ok = abs(formel - gemessen) < 0.1 and abs(gerade - float(m["ende_b"])) < 0.1 and formel > gerade + 5
    print(f"{'OK    ' if ok else 'FEHLER'} {name}: Formel Ende A {formel:.2f} mm, gemessen {gemessen:.2f} mm "
          f"(Ende B gerade {gerade:.2f} / {float(m['ende_b']):.2f})")
    fehler += not ok

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
