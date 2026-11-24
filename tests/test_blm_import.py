"""BLM/Adige ArTube-Projekte (.artube) und Teileprogramme (.bpf) wie eine STEP-Datei messen (Patrick 24.11.2026,
step_messung/step_blm.py):
- B1 BPF Rechteckrohr 60×40×3, Länge 400, Bohrung Ø10, Rechteckausschnitt und ein vom CAM in zwei Stücke geteilter
  Ausschnitt (Spalt 0,1 mm, Anfahrwege): gleiches Profil, gleiche Länge, gleiche Konturen und Schneidweg wie die STEP,
  Bohrung exakt Ø10, Volumen wie die STEP (Konturen lagegenau)
- B2 Leser: Kopf, Wörterbuch, Struktur, Behälter im Kopf und in eigenen Blöcken; Querschnitt mit Bögen in beliebiger
  Reihenfolge der Topologie (Quadratrohr mit Eckradius, Fläche exakt)
- A1 ARTUBE allein (Dreiecksnetz in m): Profil, Länge, Konturen wie die STEP, Bohrung aus den Netzpunkten exakt
- A2 ARTUBE mit BPF daneben: das BPF gilt (Querschnitt exakt), BPF neben seiner ARTUBE wird nur einmal gemessen
- A3 kaputte Dateien: klare Meldung
- P1 Programm: .artube/.bpf wie .step im Ablegen, in der Dateiauswahl, im Ordner und in Anfragen
Synthetische Dateien im Aufbau der echten (keine Kundendaten im Repo).

Aufruf: python tests/test_blm_import.py
"""
import io
import json
import math
import os
import sys
import tarfile
import tempfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from formen_baukasten import ohne, quader, schreibe, zyl  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

import step_blm  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


# ------------------------------------------------------------------ BPF schreiben (Gegenstück zu step_blm._dokument)
def _vi(v):
    if v < 0x80:
        return bytes([v])
    if v < 0x4000:
        return bytes([0x80 | (v >> 8), v & 0xFF])
    return bytes([0xC0 | (v >> 24), (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])


def _tag(t):
    return bytes([t]) if t < 0x40 else bytes([0x80 | (t >> 8), t & 0xFF])


def _beh(n):
    return bytes([0x40 | n]) if n < 0x40 else bytes([0xA0 | (n >> 8), n & 0xFF])


def bpf_block(wurzel, gross=2048):
    """XML-Element -> (Kopf, Struktur, große Behälter) wie im BPF: Behälter je Element- bzw. Attributname."""
    namen, beh, behnr = [], [], {}

    def name_nr(attr, n):
        k = (attr, n)
        if k not in namen:
            namen.append(k)
        return namen.index(k) + 5

    def wert(schl, text):
        if schl not in behnr:
            behnr[schl] = len(beh)
            beh.append(bytearray())
        b = text.encode("latin-1")
        beh[behnr[schl]] += _vi(len(b)) + b
        return _beh(behnr[schl] + 1)
    st = bytearray()

    def gehe(e):
        st.extend(_tag(name_nr(False, e.tag)))
        for k, v in e.attrib.items():
            st.extend(_tag(name_nr(True, k)) + wert("@" + k, v) + b"\x00")
        if e.text and e.text.strip():
            st.extend(wert(e.tag, e.text.strip()))
        for c in e:
            gehe(c)
        st.extend(b"\x00")
    gehe(wurzel)
    kopf = bytearray(step_blm.KENNUNG)
    for v in (2, 0, 0, 0, 128, 0, 3, len(st), 0, len(beh)):
        kopf += _vi(v)
    for b in beh:
        kopf += _vi(1) + _vi(1) + _vi(len(b))
    kopf += _vi(len(namen))
    for attr, n in namen:
        kopf += bytes([(0x40 if attr else 0) | len(n)]) + n.encode("latin-1")
    kopf += b"\x00"
    gross_ = [bytes(b) for b in beh if len(b) >= gross]
    for b in beh:
        if len(b) < gross:
            kopf += b
    return [bytes(kopf), bytes(st)] + gross_


def bpf_datei(wurzel, ziel):
    roh = bytearray(b"\xe7>(c) Adige S.p.A. BLMGroup 2008 \x00\x03\x01" + bytes(380))
    for b in bpf_block(wurzel):
        roh += zlib.compress(b, 9)
    nesting = ET.Element("nesting", version="1.0")
    ET.SubElement(nesting, "Length").text = "0"
    for b in bpf_block(nesting):
        roh += zlib.compress(b, 9)
    Path(ziel).write_bytes(bytes(roh))


def _pkt(eltern, tag, p):
    ET.SubElement(eltern, tag, x=f"{p[0]:.10f}", y=f"{p[1]:.10f}", z=f"{p[2]:.10f}")


def projekt(name, L, aussen, innen, qs, konturen, volumen=0.0):
    """aussen/innen: Topologie [('s', a, b) | ('b', mitte, r, winkel)], konturen: [(tipogeo, [(art_fläche,
    [(punkt, versore)])])]."""
    pr = ET.Element("Progetto", prj="CAM")
    ET.SubElement(pr, "sw").text = "Artube"
    it = ET.SubElement(pr, "info_tubo")
    sez = ET.SubElement(it, "sezione")
    ET.SubElement(sez, "nome_sezione").text = qs["name"]
    prof = ET.SubElement(sez, "profili")
    for tag, topo in (("profilo_esterno", aussen), ("profilo_interno", innen)):
        tp = ET.SubElement(ET.SubElement(prof, tag), "topologie", n=str(len(topo)))
        for i, t in enumerate(topo):
            top = ET.SubElement(tp, "top", id=str(i + 1))
            if t[0] == "s":
                ET.SubElement(top, "tipot").text = "1"
                _pkt(top, "p_ini", t[1])
                _pkt(top, "p_fin", t[2])
            else:
                ET.SubElement(top, "tipot").text = "4"
                _pkt(top, "normale", (-1, 0, 0))
                _pkt(top, "centro", t[1])
                ET.SubElement(top, "raggio").text = f"{t[2]:.6f}"
                ET.SubElement(top, "angolo").text = f"{t[3]:.6f}"
    for k in ("tipo", "dim_x", "dim_y", "spessore", "raggiatura"):
        ET.SubElement(sez, k).text = str(qs[k])
    ET.SubElement(it, "materiale").text = "S235"
    pz = ET.SubElement(pr, "info_pezzo")
    ET.SubElement(pz, "nome").text = name
    ET.SubElement(pz, "lunghezza").text = f"{L:.6f}"
    ET.SubElement(pz, "volume").text = f"{volumen:.6f}"
    mv = ET.SubElement(ET.SubElement(pz, "macchine", n="1"), "macchina_valida", id="1")
    ET.SubElement(mv, "famiglia").text = "LT8"
    geos = ET.SubElement(pr, "geometrie", n=str(len(konturen)))
    for i, (tipogeo, flaechen) in enumerate(konturen):
        g = ET.SubElement(geos, "info_geo", id=str(i + 1))
        ET.SubElement(g, "tipogeo").text = str(tipogeo)
        lg = sum(math.dist(a[0], b[0]) for art, pk in flaechen if art != 2 for a, b in zip(pk, pk[1:]))
        ET.SubElement(ET.SubElement(g, "dimensioni"), "l").text = f"{lg:.10f}"
        fa = ET.SubElement(g, "facce", n=str(len(flaechen)))
        for j, (art, pk) in enumerate(flaechen):
            f = ET.SubElement(fa, "info_faccia", id=str(j + 1))
            ET.SubElement(f, "tipo_faccia").text = str(art)
            pu = ET.SubElement(f, "punti", n=str(len(pk)))
            for m, (p, v) in enumerate(pk):
                q = ET.SubElement(pu, "punto", id=str(m + 1))
                _pkt(q, "pt_3d", p)
                _pkt(q, "versore", v)
                ET.SubElement(q, "accensione").text = "1" if (j == 0 and m == 0) else "0"
    return pr


# ------------------------------------------------------------------ Testteil: Rechteckrohr 60×40×3 längs x
L, B, H, T = 400.0, 60.0, 40.0, 3.0
OBEN, UNTEN = (0, 0, 1), (0, 0, -1)


def _strecken(pk, v):
    return [(p, v) for p in pk]


def ring(x):
    pk = [(x, 0, H / 2), (x, B / 2, H / 2), (x, B / 2, -H / 2), (x, -B / 2, -H / 2), (x, -B / 2, H / 2), (x, 0, H / 2)]
    nor = [OBEN, (0, 1, 0), UNTEN, (0, -1, 0), OBEN]
    return (2, [(10, [(pk[i], nor[i]), (pk[i + 1], nor[i])]) for i in range(5)])


def bohrung(x, y, r, n=36):
    z = H / 2
    kreis = [((x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n), z), OBEN)
             for k in range(n + 1)]
    return (1, [(2, [((x, y, z), OBEN), kreis[0]]), (10, kreis)])


def rechteck(x0, x1, y0, y1, z, v, offen=False):
    pk = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)] + ([] if offen else [(x0, y0, z)])
    anfahr = [(((x0 + x1) / 2, (y0 + y1) / 2, z), v), (pk[0], v)]
    return (3 if offen else 1, [(2, anfahr), (10, _strecken(pk, v))])


AUSSEN = [("s", (0, -B / 2, -H / 2), (0, B / 2, -H / 2)), ("s", (0, B / 2, -H / 2), (0, B / 2, H / 2)),
          ("s", (0, B / 2, H / 2), (0, -B / 2, H / 2)), ("s", (0, -B / 2, H / 2), (0, -B / 2, -H / 2))]
b_, h_ = B / 2 - T, H / 2 - T
INNEN = [("s", (0, -b_, -h_), (0, b_, -h_)), ("s", (0, b_, -h_), (0, b_, h_)), ("s", (0, b_, h_), (0, -b_, h_)),
         ("s", (0, -b_, h_), (0, -b_, -h_))]
KONTUREN = [ring(0.0), bohrung(200, 10, 5), rechteck(80, 120, -5, 5, H / 2, OBEN),
            rechteck(250, 289.95, -5, 5, -H / 2, UNTEN),
            # vom CAM geteiltes Stück: offen, beginnt 0,1 mm neben dem ersten (die Schnittfuge schließt den Spalt)
            (3, [(2, [((300, 0, -H / 2), UNTEN), ((290.05, -5, -H / 2), UNTEN)]),
                 (10, _strecken([(290.05, -5, -H / 2), (330, -5, -H / 2), (330, 5, -H / 2), (290.05, 5, -H / 2)],
                                UNTEN))]),
            ring(L)]
QS = dict(name="Rettangolare", tipo=3, dim_x=B, dim_y=H, spessore=T, raggiatura=0)

TMP = Path(tempfile.mkdtemp())
ROHR = ohne(quader(L, B, H, 0, -B / 2, -H / 2), quader(L + 2, B - 2 * T, H - 2 * T, -1, -B / 2 + T, -H / 2 + T),
            zyl(5, 10, H / 2 - 5, 200, 10, (0, 0, 1)), quader(40, 10, 10, 80, -5, H / 2 - 5),
            quader(80, 10, 10, 250, -5, -H / 2 - 5))
schreibe({"Rohr": ROHR}, TMP)
(S,) = analysiere_datei(TMP / "Rohr.step")
VOL_STEP = step_blm.volumen(ROHR)
bpf_datei(projekt("Teil-1", L, AUSSEN, INNEN, QS, KONTUREN, VOL_STEP), TMP / "Teil1.bpf")


def obj_text(form, fein=0.02):
    """OBJ wie ArTube (Meter, gemeinsame Punkte)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    BRepMesh_IncrementalMesh(form, fein, False, 0.2, True)
    pk, fl, nr = [], [], {}
    ex = TopExp_Explorer(form, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        tr = loc.Transformation()
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if f.Orientation() == TopAbs_REVERSED:
                b, c = c, b
            ecke = []
            for k in (a, b, c):
                p = tri.Node(k).Transformed(tr)
                s = (round(p.X() / 1000, 6), round(p.Y() / 1000, 6), round(p.Z() / 1000, 6))
                if s not in nr:
                    nr[s] = len(pk) + 1
                    pk.append(s)
                ecke.append(nr[s])
            fl.append(ecke)
        ex.Next()
    return ("# File exported by ArTube 3D CAD/CAM\n" + "".join(f"v {x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in pk) +
            "".join(f"f {a} {b} {c}\n" for a, b, c in fl))


def artube_datei(ziel, form, name, programm=""):
    meta = {"artubeMetadata": {"version": 2, "document": {"assembly": {"parts": [{"part": {
        "key": 4711, "name": name, "material": 1, "length": L / 1000, "section": {
            "type": 3, "width": B / 1000, "height": H / 1000, "thickness": T / 1000, "edgesRadius": 0.0},
        "projects": [{"project": {"name": name, "machines": [{"machine": {"family": "LT8",
                                                                            "partProgram": programm}}]}}]}}]}}}}
    with tarfile.open(ziel, "w") as tf:
        for n, b in (("__ACF_FILE_SIGNATURE__", b"1"), ("_files/metadata", zlib.compress(json.dumps(meta).encode())),
                     ("_files/obj/parts/4711.obj", zlib.compress(obj_text(form).encode())),
                     ("_files/artube", zlib.compress(b"**PARASOLID** nicht lesbar"))):
            ti = tarfile.TarInfo(n)
            ti.size = len(b)
            tf.addfile(ti, io.BytesIO(b))


(TMP / "allein").mkdir()
artube_datei(TMP / "allein" / "Teil1.artube", ROHR, "Teil-1")
artube_datei(TMP / "Teil1.artube", ROHR, "Teil-1", programm=r"S:\Programme\Teil1.bpf")


def gleich_wie_step(t, tol_sw=0.01):
    assert t.profilform == S.profilform == "Rechteckrohr", (t.profilform, S.profilform)
    assert abs(t.abm_a - B) < 0.05 and abs(t.abm_b - H) < 0.05 and abs(t.wandstaerke - T) < 0.05, \
        (t.abm_a, t.abm_b, t.wandstaerke)
    assert abs(t.laenge - S.laenge) < 0.05, (t.laenge, S.laenge)
    assert t.konturen == S.konturen and t.innen_konturen == S.innen_konturen, \
        (t.konturen, S.konturen, t.innen_konturen, S.innen_konturen)
    assert abs(t.schneidweg - S.schneidweg) < tol_sw * S.schneidweg, (t.schneidweg, S.schneidweg)
    assert dict(t.bohrungen) == dict(S.bohrungen) == {10.0: 1}, (t.bohrungen, S.bohrungen)


@fall("B1 BPF wie STEP: Profil, Länge, Konturen, Schneidweg, Bohrung Ø10 exakt, Volumen lagegenau")
def _b1():
    (t,) = analysiere_datei(TMP / "Teil1.bpf")
    gleich_wie_step(t, tol_sw=0.002)
    koerper, info = step_blm.lies_blm_info(TMP / "Teil1.bpf")
    v = step_blm.volumen(koerper[0][1])
    assert abs(v - VOL_STEP) < 0.05, (v, VOL_STEP)
    diff = step_blm._bool("cut", ROHR, [koerper[0][1]])
    assert step_blm.volumen(diff) < 0.05, step_blm.volumen(diff)     # nichts zu viel weg und nichts zu wenig
    assert any("BLM-Programm" in m and "S235" in m and "LT8" in m for m in info["meldungen"]), info["meldungen"]
    assert any("1 Bohrung" in m for m in info["meldungen"]), info["meldungen"]


@fall("B2 Leser: Struktur, Behälter, Querschnitt mit Bögen in beliebiger Reihenfolge exakt")
def _b2():
    z = step_blm.zusammenfassung(TMP / "Teil1.bpf")
    assert z["name"] == "Teil-1" and z["laenge"] == L and z["profil"][1:4] == (B, H, T) and z["konturen"] == 6, z
    assert z["werkstoff"] == "S235", z
    # Quadratrohr 35×35×2, R 3 außen / R 1 innen; Bogen der Ecke links unten steht wie bei ArTube nicht im Umlauf
    a, r, ri, t = 17.5, 3.0, 1.0, 2.0
    i_ = a - t
    aussen = [("s", (0, -a + r, -a), (0, a - r, -a)), ("b", (0, a - r, -a + r), r, 90),
              ("s", (0, a, -a + r), (0, a, a - r)), ("b", (0, a - r, a - r), r, 90),
              ("s", (0, a - r, a), (0, -a + r, a)), ("b", (0, -a + r, a - r), r, 90),
              ("b", (0, -a + r, -a + r), r, 90), ("s", (0, -a, a - r), (0, -a, -a + r))]
    innen = [("b", (0, -a + r, -a + r), ri, 90), ("s", (0, -a + r, -i_), (0, a - r, -i_)),
             ("b", (0, a - r, -a + r), ri, 90), ("s", (0, i_, -a + r), (0, i_, a - r)),
             ("b", (0, a - r, a - r), ri, 90), ("s", (0, a - r, i_), (0, -a + r, i_)),
             ("b", (0, -a + r, a - r), ri, 90), ("s", (0, -i_, a - r), (0, -i_, -a + r))]
    qs = dict(name="Quadratisch", tipo=2, dim_x=35, dim_y=35, spessore=2, raggiatura=3)
    bpf_datei(projekt("Q", 100, aussen, innen, qs, []), TMP / "Q.bpf")
    teil = step_blm.bpf_teil((TMP / "Q.bpf").read_bytes())
    form, _m = step_blm.bpf_koerper(teil)
    soll = ((2 * a) ** 2 - (4 - math.pi) * r * r - ((2 * i_) ** 2 - (4 - math.pi) * ri * ri)) * 100
    assert abs(step_blm.volumen(form) - soll) < 1e-3, (step_blm.volumen(form), soll)
    # Kreisausgleich: Kreis erkannt, Vieleck mit Ecken nicht
    kreis = [(200 + 5 * math.cos(w), 10 + 5 * math.sin(w), 20.0) for w in (2 * math.pi * k / 24 for k in range(24))]
    c, rr, _n = step_blm.kreis_aus_punkten(kreis, (0, 0, 1))
    assert abs(rr - 5) < 1e-9 and math.dist(c, (200, 10, 20)) < 1e-9, (c, rr)
    assert step_blm.kreis_aus_punkten([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)] * 3, (0, 0, 1)) is None


@fall("A1 ARTUBE allein: Netz wie STEP gemessen, Bohrung Ø10 aus den Netzpunkten exakt")
def _a1():
    (t,) = analysiere_datei(TMP / "allein" / "Teil1.artube")
    gleich_wie_step(t)
    z = step_blm.zusammenfassung(TMP / "allein" / "Teil1.artube")
    assert z["name"] == "Teil-1" and abs(z["laenge"] - L) < 1e-6 and z["netz"] > 100, z
    _k, info = step_blm.lies_blm_info(TMP / "allein" / "Teil1.artube")
    assert any("ARTUBE-Netz, 1 Bohrung" in m and "60×40×3" in m for m in info["meldungen"]), info["meldungen"]


@fall("A2 ARTUBE mit BPF daneben: BPF gilt; BPF neben seiner ARTUBE nur einmal gemessen")
def _a2():
    _k, info = step_blm.lies_blm_info(TMP / "Teil1.artube")
    assert any("aus dem BPF daneben (Teil1.bpf)" in m for m in info["meldungen"]), info["meldungen"]
    from rohrlaser import cad_import, step
    v = cad_import.vorbereiten([TMP / "Teil1.artube", TMP / "Teil1.bpf", TMP / "Q.bpf"])
    assert [p.name for p in v.dateien] == ["Teil1.artube", "Q.bpf"], v.dateien
    assert any("gehört zu Teil1.artube" in b["text"] for b in v.hinweise()), v.befunde
    namen = sorted(p.name for p in step.step_dateien([str(TMP)]))
    assert "Teil1.bpf" not in namen and "Teil1.artube" in namen and "Q.bpf" in namen, namen


@fall("A3 kaputte ARTUBE/BPF: klare Meldung")
def _a3():
    for n, inhalt, wort in (("kaputt.artube", b"kein tar", "ARTUBE"), ("kaputt.bpf", b"(c) Adige \x00 nichts", "BPF")):
        (TMP / "kaputt" / n).parent.mkdir(exist_ok=True)
        (TMP / "kaputt" / n).write_bytes(inhalt)
        try:
            step_blm.lies_blm_info(TMP / "kaputt" / n)
            raise AssertionError(f"{n} ohne Fehler")
        except ValueError as e:
            assert wort in str(e), e


@fall("P1 Programm: .artube/.bpf wie .step im Ablegen, in der Dateiauswahl, im Ordner und in Anfragen")
def _p1():
    from rohrlaser import anfrage_art, anfragen, anfragen_akten, anhang_analyse, cad_import, step
    for e in (".artube", ".bpf"):
        assert e in step.CAD_ENDUNGEN and f"*{e}" in step.CAD_FILTER and e in cad_import.CAD_ENDUNGEN, e
        assert e in anfragen.STEP and e in anfragen_akten.ARTEN["step"] and e in anfrage_art.STEP_ENDUNGEN, e
    assert step.step_kandidaten([str(TMP / "Teil1.bpf")]) and cad_import.kandidat(TMP / "Teil1.artube")
    for n in ("Teil1.artube", "Teil1.bpf"):
        assert anhang_analyse.rolle(dict(name=n, groesse=1000)) == anhang_analyse.MODELL, n


print("Alle Tests bestanden." if not fehler else f"{fehler} Fehler")
sys.exit(1 if fehler else 0)
