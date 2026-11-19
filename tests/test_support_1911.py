"""Supportpaket Patrick 19.11.2026 (0.9.399):

S1 „Angebotsdokument erstellen …“ brach dreimal mit „'AkteDialog' object has no attribute 'Accepted'“ ab: das
   Fenster wurde mit exec() geöffnet und mit d.Accepted verglichen (PySide6 kennt das nur an der Klasse). Hier über
   exec (nicht über den Test-Haken dialog=): Erstellen legt die Akte ab, Abbrechen nichts.
S2 „Angebot anlegen“ aus einer Anfrage ohne STEP mit DXF-Zeichnung hing 54–90 s: dxf_ansichten.gruppen prüfte in
   dichten Zeichnungen (Schraffur, viele kurze Striche) fast alle Paare. Neu: feineres Raster, je Zelle die Gruppen
   mit Hüllrechteck, neueste Elemente zuerst. Gleiche Gruppen wie die bisherige Rechnung (hier als Referenz kopiert)
   für zufällige Zeichnungen und die DXF-Testdateien; eine dichte Zeichnung mit 40.000 Strichen in wenigen Sekunden.
S3 Prüfdialog nach „Messen“ (98 Teile) erst nach einer Minute: die 3D-Gegenprobe (step_gegenprobe._weitester)
   überspringt Punkte, die nah an der zuletzt nächsten Strecke liegen (können den größten Abstand nicht erhöhen) –
   gleiche Abweichung und Stelle wie bisher (Referenz kopiert). Ab parallel.GEGENPROBE_AB Rohren rechnen
   Hilfsprozesse die Gegenprobe: gleiche Messwerte wie nacheinander gerechnet, die Merker kommen zurück.

Aufruf: python tests/test_support_1911.py
"""
import copy
import math
import os
import random
import subprocess
import sys
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import dxf_ansichten as da, step_gegenprobe as sg  # noqa: E402


def ok(text):
    print("OK:", text, flush=True)


# ------------------------------------------------------------------ S1 Angebotsdokument über exec
def s1():
    from PySide6.QtWidgets import QApplication, QDialog
    import beispiel_baugruppe as bsp
    from rohrlaser import akte_ablage
    from rohrlaser.akte_dialog import AkteDialog
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "r.db")
    db.einstellung_setzen("pdf_vorschau", "nein")
    a = bsp.anlegen(db)
    f = Hauptfenster(db, tmp, stumm=True)
    db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
    s = f.angebot_oeffnen(a)
    assert s.optimieren()
    alt = AkteDialog.exec
    try:
        AkteDialog.exec = lambda self: QDialog.Rejected
        assert s.angebotsdokument(oeffnen=False) is None
        assert akte_ablage.letzte(s.akte_ordner()) is None, "Abbrechen legt nichts ab"

        def erstellen(self):
            self.vorschau.setChecked(False)
            return QDialog.Accepted
        AkteDialog.exec = erstellen
        b = s.angebotsdokument(oeffnen=False)
    finally:
        AkteDialog.exec = alt
    assert b and b["version"] == 1 and b["dateien"], b
    ok("S1 Angebotsdokument über das Fenster (exec): Erstellen legt Version 1 ab, Abbrechen nichts")


# ------------------------------------------------------------------ S2 Ansichten gruppieren
def gruppen_ref(strecken, kreise, abstand=None):
    """dxf_ansichten.gruppen bis 0.9.400 (unverändert; nur die Gruppen als Indexlisten)."""
    boxen = [da._bb_strecke(p, q) for p, q in strecken] + [da._bb_kreis(c, r) for c, r in kreise]
    if not boxen:
        return []
    x0, y0 = min(b[0] for b in boxen), min(b[1] for b in boxen)
    x1, y1 = max(b[2] for b in boxen), max(b[3] for b in boxen)
    d = abstand if abstand is not None else max(1.0, 0.01 * math.hypot(x1 - x0, y1 - y0))
    zelle = max(10 * d, 1e-6)
    eltern = list(range(len(boxen)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    raster = {}
    for i, b in enumerate(boxen):
        cx0, cy0 = int((b[0] - d - x0) // zelle), int((b[1] - d - y0) // zelle)
        cx1, cy1 = int((b[2] + d - x0) // zelle), int((b[3] + d - y0) // zelle)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                liste = raster.setdefault((cx, cy), [])
                for j in liste:
                    if wurzel(i) != wurzel(j) and da._nah(b, boxen[j], d):
                        eltern[wurzel(i)] = wurzel(j)
                liste.append(i)
    gruppe = {}
    for i in range(len(boxen)):
        gruppe.setdefault(wurzel(i), []).append(i)
    return sorted(sorted(g) for g in gruppe.values())


def gruppen_neu(strecken, kreise, abstand=None):
    n = len(strecken)
    return sorted(sorted(a.strecken + [i + n for i in a.kreise]) for a in da.gruppen(strecken, kreise, abstand))


def zeichnung(rnd, n):
    """Zufällige Zeichnung: einige Ansichten aus Kanten, Schraffur und Kreisen, dazu ein Rahmen."""
    st, kr = [((0, 0), (420, 0)), ((420, 0), (420, 297)), ((420, 297), (0, 297)), ((0, 297), (0, 0))], []
    for _ in range(rnd.randint(1, 6)):
        x, y, w, h = rnd.uniform(10, 300), rnd.uniform(10, 200), rnd.uniform(5, 110), rnd.uniform(3, 90)
        for _ in range(n):
            if rnd.random() < 0.1:
                kr.append(((x + rnd.uniform(0, w), y + rnd.uniform(0, h)), rnd.uniform(0.5, 6)))
            else:
                px, py = x + rnd.uniform(0, w), y + rnd.uniform(0, h)
                lg, wi = rnd.choice((0.4, 2, 15, 60)), rnd.uniform(0, math.pi)
                st.append(((px, py), (px + lg * math.cos(wi), py + lg * math.sin(wi))))
    return st, kr


def s2():
    rnd = random.Random(1911)
    for _ in range(60):
        st, kr = zeichnung(rnd, rnd.randint(1, 120))
        ab = rnd.choice((None, 0.5, 2.0, 8.0))
        assert gruppen_neu(st, kr, ab) == gruppen_ref(st, kr, ab), "andere Gruppen"
    from rohrlaser import dxf_import as di, dxf_rohr
    for pfad in sorted((HIER / "dxf").glob("*.dxf")):
        gesammelt = []
        alt = da.gruppen

        def merken(s_, k_, a_=None):
            gesammelt.append((list(s_), list(k_), a_))
            return alt(s_, k_, a_)
        da.gruppen = merken
        try:
            dxf_rohr.erkennen(di.datei_lesen(pfad), pfad.name)
        finally:
            da.gruppen = alt
        assert gesammelt
        for s_, k_, a_ in gesammelt:
            assert gruppen_neu(s_, k_, a_) == gruppen_ref(s_, k_, a_), pfad.name
    ok("S2 Ansichten gruppieren: gleiche Gruppen wie bisher (60 zufällige Zeichnungen, DXF-Testdateien)")
    # dichte Zeichnung: Schraffur aus 40.000 kurzen Strichen in vier Ansichten (bisher etwa eine halbe Minute)
    st = []
    for vx, vy, w, h in ((100, 600, 600, 40), (100, 450, 600, 60), (800, 450, 60, 40), (100, 150, 500, 200)):
        st += [((vx, vy), (vx + w, vy)), ((vx + w, vy), (vx + w, vy + h)), ((vx + w, vy + h), (vx, vy + h)),
               ((vx, vy + h), (vx, vy))]
        for x in range(vx, vx + w, 6):
            st += [((x, vy + k * 0.5), (x + 0.4, vy + k * 0.5 + 0.4)) for k in range(int(h / 0.5))]
    st = st[:40000]
    t = time.perf_counter()
    g = da.gruppen(st, [])
    dt = time.perf_counter() - t
    assert len(g) >= 3 and dt < 10, (len(g), dt)
    ok(f"S2 dichte Zeichnung {len(st)} Striche: {len(g)} Ansichten in {dt:.2f} s")


# ------------------------------------------------------------------ S3 Gegenprobe
def weitester_ref(a, b_k, b_e, weite, abstand, ohne=()):
    """step_gegenprobe._weitester bis 0.9.400 (unverändert)."""
    if not a:
        return 0.0, None
    if not b_k and not b_e:
        return weite, a[0][0]
    rk, re_ = sg._Raster(b_k, weite + abstand), sg._Raster(b_e, weite)
    weit, wo = 0.0, None
    for p, q in a:
        n = max(1, int(math.dist(p, q) / sg.SCHRITT))
        for k in range(n + 1):
            x = tuple(p[i] + (q[i] - p[i]) * k / n for i in range(3))
            if ohne and any(z0 <= x[2] <= z1 for z0, z1 in ohne):
                continue
            d = min(max(rk.abstand(x) - abstand, 0.0) if b_k else weite, re_.abstand(x) if b_e else weite)
            if d > weit:
                weit, wo = d, x
    return weit, wo


def linien(rnd, n, z_max=400):
    out = []
    for _ in range(n):
        r, w0 = 20, rnd.uniform(0, 2 * math.pi)
        z = rnd.uniform(0, z_max)
        pkt = []
        for k in range(rnd.randint(2, 12)):
            w = w0 + 0.3 * k
            pkt.append((r * math.cos(w), r * math.sin(w), z + rnd.uniform(-3, 3)))
        out += list(zip(pkt, pkt[1:]))
    return out


def stoeren(rnd, strecken, d):
    return [(tuple(c + rnd.uniform(-d, d) for c in p), tuple(c + rnd.uniform(-d, d) for c in q)) for p, q in strecken]


def s3_weitester():
    rnd = random.Random(19)
    for _ in range(40):
        b_k, b_e = linien(rnd, rnd.randint(0, 25)), linien(rnd, rnd.randint(0, 6))
        a = stoeren(rnd, rnd.sample(b_k + b_e, min(len(b_k + b_e), rnd.randint(0, 30))), rnd.choice((0, 0.01, 0.2)))
        a += linien(rnd, rnd.randint(0, 2))                   # Linien, die es im Vergleich nicht gibt
        ohne = rnd.choice(((), ((-0.5, 3.5),), ((100, 140), (380, 401))))
        for ab in (0.0, 0.3):
            assert sg._weitester(a, b_k, b_e, sg.WEITE, ab, ohne) == weitester_ref(a, b_k, b_e, sg.WEITE, ab, ohne)
    ok("S3 Gegenprobe: größter Abstand und Stelle wie bisher (zufällige Linien, mit und ohne Abweichung)")


def s3_parallel():
    if find_spec("OCP") is None:
        print("OpenCascade (OCP) fehlt: S3 Hilfsprozesse übersprungen.")
        return
    from rohrlaser import parallel, step
    from rohrlaser.datenbank import Datenbank
    tmp = Path(tempfile.mkdtemp())
    dateien = [HIER / "step_referenz" / n for n in ("REF01_RE60x40x2_L1000.step", "REF02_QR40x40x2_L1000.step",
                                                     "REF09_RE60x40x2_Gehrung45.step")]
    dateien.append(HIER / "step_konturen" / "K04_RE60x40x3_Senkung_Flowdrill.step")
    aus, netze, js = tmp / "m.txt", tmp / "netze", tmp / "m.json"
    subprocess.run([sys.executable, str(PROGRAMM / "step_messung" / "step_messen.py"), "--ausgabe", str(aus),
                    "--netze", str(netze), "--json", str(js), *map(str, dateien)], check=True, capture_output=True,
                   timeout=900)
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(aus), netze), js)
    assert len(mw) == 4 and all(m.get("_netz") for m in mw), [m.get("profilform") for m in mw]
    mw = [dict(m, laenge=str(float(m["laenge"]) - 0.0)) for m in mw * 4]
    mw = [copy.deepcopy(m) for m in mw]
    k = Datenbank(tmp / "r.db").kontext()
    a, b = copy.deepcopy(mw), copy.deepcopy(mw)
    alt = parallel.GEGENPROBE_AB
    parallel.GEGENPROBE_AB = 10 ** 9
    try:
        step.rohre_gegenprobe(a, k.profile, True)
    finally:
        parallel.GEGENPROBE_AB = alt
    sg._MERKER.clear()
    gesendet = []
    orig = parallel._verteilen

    def zaehlen(auftraege, reihe, n, melden=None):
        r = orig(auftraege, reihe, n, melden)
        gesendet.append(len(r))
        return r
    parallel._verteilen = zaehlen
    try:
        step.rohre_gegenprobe(b, k.profile, True)
    finally:
        parallel._verteilen = orig
        parallel.beenden()
    assert len(b) >= parallel.GEGENPROBE_AB
    assert a == b, "andere Messwerte als nacheinander gerechnet"
    assert sum(m.get("_rohr_gegenprobe") is not None for m in b) >= 12
    if (os.cpu_count() or 1) >= 3:
        assert gesendet and gesendet[0] == len(b), gesendet
        assert sg._MERKER, "Merker der Hilfsprozesse fehlen"
    ok(f"S3 Gegenprobe auf Hilfsprozessen ({gesendet[0] if gesendet else 0} von {len(b)} Teilen): gleiche "
       "Messwerte wie nacheinander, Merker übernommen")


if __name__ == "__main__":
    s1()
    s2()
    s3_weitester()
    s3_parallel()
    print("Alle Tests bestanden.")
