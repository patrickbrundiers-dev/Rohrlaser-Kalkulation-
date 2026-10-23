"""STEP-Messung schneller (Plan S3): gleiche Körper nur einmal messen, große Dateien auf mehrere Prozesse verteilen,
grobe Stufe der 3D-Ansicht beim Drehen.

Laufzeiten misst tests/benchmark_step.py (nicht Teil der Tests).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER))
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"
GESTELL = HIER / "step_struktur" / "S01_Gestell_verschachtelt.step"
RAHMEN = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
ANBAU = HIER / "step_anbau" / "A08_RE60x40x3_Anbau_eigene_Koerper.step"
tmp = Path(tempfile.mkdtemp())

import step_geometrie  # noqa: E402
import step_messen  # noqa: E402


def messen(name, dateien, *args, umgebung=None):
    aus, js, netze = tmp / f"{name}.txt", tmp / f"{name}.json", tmp / f"{name}_netze"
    env = dict(os.environ, **(umgebung or {}))
    r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), "--json", str(js), "--netze", str(netze),
                        *args, *map(str, dateien)], capture_output=True, text=True, env=env, timeout=900)
    assert r.returncode in (0, 1), r.stderr
    daten = json.loads(js.read_text(encoding="utf-8"))
    daten.pop("erzeugt", None)
    netz = {p.name: p.read_text(encoding="utf-8") for p in sorted(netze.iterdir())}
    zeilen = [dict(zip(step_messen.SPALTEN, z.split("\t"))) for z in aus.read_text(encoding="utf-8").splitlines()[1:]]
    return daten, netz, zeilen, r.stdout


def gleich(a, b, tol=1e-6):
    """Zahlen bis auf Rundung gleich (Kopien liegen an anderer Stelle im Raum: letzte Stellen anders)."""
    try:
        x, y = float(a), float(b)
        return abs(x - y) <= tol * max(1.0, abs(x), abs(y))
    except ValueError:
        return a == b


# 1. Gleiche Körper: nur verschobene Kopien werden übernommen, gedrehte einzeln gemessen
from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from erzeuge_testteile import bohrung_quer, kastenrohr  # noqa: E402

d = Dokument()
rohr = d.teil("Holm QR40x3 L600", bohrung_quer(kastenrohr(40, 40, 3, 600, 4.5), 9, 150))
d.baugruppe("Test", [(rohr, lage()), (rohr, lage(500, 200, 0)), (rohr, lage(0, 900, 0, um_x=1.5707963267948966)),
                     (rohr, lage(1500, 0, 0, um_y=0.4)), (rohr, lage(2000, 0, 0))])
INSTANZEN = tmp / "Instanzen.step"
d.schreiben(INSTANZEN)
gel = step_geometrie.datei_lesen(INSTANZEN)
assert gel.gleich == {2: (1, (500.0, 200.0, 0.0)), 5: (1, (2000.0, 0.0, 0.0))}, gel.gleich
g01 = step_geometrie.datei_lesen(GESTELL).gleich
assert len(g01) == 8 and g01[4] == (1, (1000.0, 0.0, 0.0)) and g01[12] == (9, (600.0, 0.0, 0.0)), g01
print("OK: gleiche Körper erkannt (nur verschobene Kopien, gedrehte werden einzeln gemessen)")

# 2. Kopien gleich der Einzelmessung: Maße, Länge, Schneidweg, Konturen nach Zahl und Länge; Lage im Raum verschoben
VERGLEICH = [GESTELL, INSTANZEN, RAHMEN]
mit = messen("mit", VERGLEICH)
ohne = messen("ohne", VERGLEICH, umgebung={"STEP_MESSEN_EINZELN": "1"})
lagefrei = {"wand_messungen", "konturen_liste", "netz", "huelle", "volumen", "oberflaeche"}
for a, b in zip(ohne[2], mit[2]):
    for spalte in step_messen.SPALTEN:
        if spalte not in lagefrei:
            assert gleich(a[spalte], b[spalte]), (a["artikel"], spalte, a[spalte], b[spalte])
    for spalte in ("huelle", "volumen", "oberflaeche"):
        assert all(gleich(x, y) for x, y in zip(a[spalte].split("|"), b[spalte].split("|"))), (a["artikel"], spalte)
    ka, kb = json.loads(a["konturen_liste"] or "[]"), json.loads(b["konturen_liste"] or "[]")
    assert sorted((k["art"], round(k.get("laenge") or 0, 1)) for k in ka) == \
        sorted((k["art"], round(k.get("laenge") or 0, 1)) for k in kb), a["artikel"]
for datei_a, datei_b in zip(ohne[0]["dateien"], mit[0]["dateien"]):
    for ka, kb in zip(datei_a["koerper"], datei_b["koerper"]):
        assert ka["bauteil"] == kb["bauteil"] and ka["pfad"] == kb["pfad"]
        la, lb = ka["laengsachse"], kb["laengsachse"]
        assert (la is None) == (lb is None) and (la is None or all(
            gleich(x, y, 1e-4) for x, y in zip(la["ende_a"] + la["richtung"], lb["ende_a"] + lb["richtung"]))), \
            (ka["nr"], la, lb)
    assert datei_a["nahtkandidaten"] == datei_b["nahtkandidaten"]
assert len(mit[0]["dateien"][2]["nahtkandidaten"]) == 6
print("OK: Kopien gleich der Einzelmessung (Messwerte, Konturen, Lage, Nahtkandidaten)")

# 3. Verteilt auf mehrere Prozesse: Ergebnis und Netze genau wie in einem Prozess (auch Anbauteile eigener Körper)
for datei in (GESTELL, RAHMEN, ANBAU):
    eins = messen("eins", [datei])
    verteilt = messen("verteilt", [datei], "--zeitlimit", "120", "--prozesse", "3",
                      umgebung={"STEP_MESSEN_TEILEN_AB": "2"})
    assert verteilt[0] == eins[0] and verteilt[1] == eins[1], f"{datei.name}: verteilt anders"
    assert '"koerper": 0,' not in verteilt[3], "Datei wurde nicht verteilt"
anbau = {k["nr"]: k for k in eins[0]["dateien"][0]["koerper"]}
assert any(k["anbauteile"] for k in anbau.values()), "A08: Anbauteile aus eigenen Körpern"
print("OK: Datei auf 3 Prozesse verteilt, Ergebnis und Netze gleich")

# 4. Zeitlimit beim Verteilen: hängender Körper und seine Kopien "nicht gemessen", der Rest gleich
haengt = messen("haengt", [GESTELL], "--zeitlimit", "2", "--prozesse", "3",
                umgebung={"STEP_MESSEN_TEILEN_AB": "2", "STEP_MESSEN_TEST_HAENGT": f"{GESTELL.name}:1"})
normal = {k["nr"]: k for k in mit[0]["dateien"][0]["koerper"]}
k = {x["nr"]: x for x in haengt[0]["dateien"][0]["koerper"]}
for nr in (1, 4):           # Holm und seine Kopie in der zweiten Rahmenseite
    assert any("nicht gemessen: Zeitlimit 2 s überschritten" in h for h in k[nr]["warnungen"]), k[nr]
for nr in (2, 7, 9):
    assert k[nr]["profil_id_vorschlag"] == normal[nr]["profil_id_vorschlag"] and k[nr]["laenge"] == normal[nr]["laenge"]
# Auswertungen über die Baugruppe (Körper n + 1) zu lang: ohne Nahtkandidaten, mit Hinweis
lang = messen("lang", [RAHMEN], "--zeitlimit", "2", "--prozesse", "1",
              umgebung={"STEP_MESSEN_TEST_HAENGT": f"{RAHMEN.name}:7"})
r = lang[0]["dateien"][0]
assert r["nahtkandidaten"] == [] and len(r["koerper"]) == 6
assert any("Nahtkandidaten nicht bestimmt: Zeitlimit 2 s" in h for h in r["koerper"][0]["warnungen"])
assert '"koerper": 6, "koerper_n": 6' in lang[3]
print("OK: Zeitlimit beim Verteilen und bei den Auswertungen über die Baugruppe")

# 5. 3D-Ansicht: grobe Stufe beim Drehen (große Baugruppen), Bild zwischengespeichert
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ansicht3d  # noqa: E402

app = QApplication.instance() or QApplication([])
netze = [json.loads(t) for t in mit[1].values()]
netz, _ = ansicht3d.baugruppe(netze)
m = ansicht3d.Modell(netz)
assert m.grob() is m, "kleines Netz: keine grobe Stufe"
ansicht3d.GROB_DREIECKE = len(m.dreiecke) // 4
m = ansicht3d.Modell(netz)
g = m.grob()
assert g is not m and len(g.dreiecke) == ansicht3d.GROB_DREIECKE and g.linien == []
assert (g.mitte, g.groesse) == (m.mitte, m.groesse) and len(g.punkte) < len(m.punkte)
assert m.grob() is g                                    # nur einmal aufbereitet
w = ansicht3d.Ansicht3D()
w.resize(500, 300)
w.setzen(netz)
w.grab()
fein = w._bild
assert fein[0][0] is w.modell
w.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.LeftButton,
                              Qt.LeftButton, Qt.NoModifier))
w.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, QPointF(30, 10), QPointF(30, 10), Qt.LeftButton, Qt.LeftButton,
                             Qt.NoModifier))
w.grab()
assert w._bild[0][0] is w.modell.grob(), "beim Drehen grob"
w.mouseReleaseEvent(None)
w.grab()
assert w._bild[0][0] is w.modell
bild = w._bild
w.grab()
assert w._bild is bild, "unveränderte Ansicht: Bild aus dem Zwischenspeicher"
print("OK: 3D-Ansicht grob beim Drehen, fein in Ruhe, Bild zwischengespeichert")
