"""Importengine 2.0 (Master-Auftrag Patrick 26.11.2026 „High-Performance-Importengine 2.0 – STEP, TubeX, LST, Artube
und BPF“). Synthetische Dateien im Aufbau der echten (keine Kundendaten im Repo):
- F1 Format am Inhalt: STEP, IGES, TUBX, LST, Fertigungsauftrag, BPF, ARTUBE, ZIP, Herstellerformate, leer;
  Hersteller/Software/Version aus der Datei, Endung passt nicht → Hinweis
- F2 Import: STEP als .txt gemessen (Hinweis), ZIP als .step entpackt, SolidWorks als .step und Fertigungsauftrag
  ohne Schneidweg klar gemeldet; Messung liest IGES unter .stp mit dem IGES-Leser
- N1 Werkzeugnetz direkt statt genäht: Würfel exakt, offenes Netz → Nähen wie bisher, 3.000 Dreiecke schnell
- N2 Offene Kontur mit Bahnstück kürzer als die Fuge (Kerbe): an den Knicken geteilt, jedes Stück gültig; normale
  Kontur unverändert (bitgleich wie streifen)
- N3 Werkzeugtiefe an Rohrecken (60×40×2 R 4: 3 + 1 = 4 = R) begrenzt, auf ebenen Seiten wie bisher
- N4 Öffnung aus zwei offenen Schnitten mit Haltestegen: Abfall entfernt (Volumen wie STEP), Schnittlänge, Einstiche
  und Konturklassen unverändert
- C1 Zwischenspeicher: geänderte LST neben unveränderter TUBX ergibt einen neuen Schlüssel, STEP-Schlüssel gleich

Aufruf: python tests/test_importengine_2611.py
"""
import math
import os
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from rohrlaser import cad_import, dateiformat, lst_bahn  # noqa: E402

fehler = 0
TMP = Path(tempfile.mkdtemp())


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


STEP_TEXT = ("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('x'),'2;1');\nFILE_NAME('teil.step','2026-11-26T10:00:00',"
             "('a'),('b'),'SwSTEP 2.0','SolidWorks 2025','');\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));"
             "\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")


def iges_text():
    s = "Prüfteil".ljust(72) + "S      1"
    glob = "1H,,1H;,4Hteil,8Hteil.igs,9HMeinCAD12,3H1.0,32,38,6,308,15,4Hteil,1.,2,2HMM,1,0.01;"
    g = [glob[i:i + 72].ljust(72) + f"G{i // 72 + 1:7d}" for i in range(0, len(glob), 72)]
    return "\n".join([s, *g, "".ljust(72) + "T      1"]) + "\n"


def lst_text(auftrag=False, programm=True):
    kopf = ("BD\nSET_METRIC\nC\nBEGIN_EINRICHTEPLAN_INFO\nC\nZA,MM,3\nMM,AT,1,  10,1,1,,'Maschine',,'',T\n"
            "MM,AT,1,  20,1,1,,'Steuerung',,'',T\nMM,AT,1,  30,1,1,,'ProgrammingSystemSignature',,'',T\nC\nZA,DA,1\n"
            "DA,'T11',1,'Sin 840D',\n*  'Programming Tube 5.1.1+abc'\nC\nENDE_EINRICHTEPLAN_INFO\nC\n")
    nc = "BEGIN_PROGRAMM\nSTART_TEXT\nTC_LASER_ON(1,\"ST020\",1,100)\nG1 X10\nTC_LASER_OFF(2)\nENDE_PROGRAMM\n"
    job = ("BD\nSET_METRIC\nBEGIN_FERTIGUNG_AUFTRAG_TMP\nC\nZA,MM,4\nMM,AT,1,  10,1,1,,'Jobname',,'',T\nC\nZA,DA,1\n"
           "DA,'2026-1','10186133','PROG_P10','10'\nC\nENDE_FERTIGUNG_AUFTRAG_TMP\nC\nED\n")
    return (job if auftrag else "") + (kopf + (nc if programm else "") + "ED\n" if programm or not auftrag else "")


def tubx_datei(pfad):
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("Task3D/Workpiece1.bson", b"\x05\x00\x00\x00\x00")
        z.writestr("tubeProps/app.xml", "<appProperties><appVersion>TubeCAM (Version: 5.1.1+abc; Link time: x)"
                   "</appVersion><profileType>Rectangular</profileType><machineId>Tube 5000 (T11) 1</machineId>"
                   "</appProperties>")


def artube_datei(pfad):
    with tarfile.open(pfad, "w", format=tarfile.GNU_FORMAT) as t:
        for name, daten in (("__ACF_FILE_SIGNATURE__", b"1"), ("_files/metadata", b"{}"),
                            ("_files/obj/parts/1.obj", b"v 0 0 0\n")):
            info = tarfile.TarInfo(name)
            info.size = len(daten)
            import io
            t.addfile(info, io.BytesIO(daten))


def dateien():
    d = TMP / "formate"
    d.mkdir(exist_ok=True)
    (d / "a.step").write_text(STEP_TEXT)
    (d / "b.igs").write_text(iges_text(), encoding="latin-1")
    tubx_datei(d / "c.tubx")
    (d / "d.lst").write_text(lst_text())
    (d / "e.lst").write_text(lst_text(auftrag=True, programm=False))
    (d / "f.bpf").write_bytes(b"\xe7>(c) Adige S.p.A. BLMGroup 2008 \x00\x03\x01" + b"\x00" * 50)
    artube_datei(d / "g.artube")
    with zipfile.ZipFile(d / "h.zip", "w") as z:
        z.writestr("teil.step", STEP_TEXT)
    (d / "i.sldprt").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    (d / "j.mac").write_bytes(b"MegaCad13\x00" + b"\x00" * 40)
    (d / "k.step").write_bytes(b"")
    (d / "l.lst").write_text(lst_text(auftrag=True))
    return d


D = dateien()


@fall("F1 Format am Inhalt: Art, Hersteller, Software, Version; Endung passt nicht → Hinweis")
def _f1():
    soll = {"a.step": dateiformat.STEP, "b.igs": dateiformat.IGES, "c.tubx": dateiformat.TUBX, "d.lst": dateiformat.LST,
            "e.lst": dateiformat.LST_AUFTRAG, "f.bpf": dateiformat.BPF, "g.artube": dateiformat.ARTUBE,
            "h.zip": dateiformat.ZIP, "i.sldprt": dateiformat.OLE, "j.mac": dateiformat.MEGACAD,
            "k.step": dateiformat.LEER, "l.lst": dateiformat.LST}
    for name, art in soll.items():
        f = dateiformat.erkennen(D / name)
        assert f.art == art, (name, f.art, f)
        assert f.endung_passt or art == dateiformat.LEER, (name, f)
    a = dateiformat.erkennen(D / "a.step")
    assert a.software == "SolidWorks 2025" and a.felder["ap"] == "AP214", a
    c = dateiformat.erkennen(D / "c.tubx")
    assert (c.hersteller, c.software, c.version) == ("TRUMPF", "TubeCAM", "5.1.1+abc"), c
    assert c.felder["maschine"] == "Tube 5000 (T11) 1" and c.felder["profil"] == "Rectangular", c.felder
    d = dateiformat.erkennen(D / "d.lst")
    assert (d.software, d.version) == ("Programming Tube", "5.1.1+abc") and d.felder["steuerung"] == "Sin 840D", d
    e, ll = dateiformat.erkennen(D / "e.lst"), dateiformat.erkennen(D / "l.lst")
    assert e.felder["programme"] == ["PROG_P10"] and not e.messbar, e
    assert ll.felder.get("fertigungsauftrag") and ll.messbar and ll.felder["programme_n"] == 1, ll
    assert dateiformat.erkennen(D / "f.bpf").hersteller.startswith("BLM"), "BPF Hersteller"
    assert dateiformat.erkennen(D / "g.artube").felder["teile_obj"] == 1, "ARTUBE"
    assert dateiformat.erkennen(D / "b.igs").software == "MeinCAD12", dateiformat.erkennen(D / "b.igs")
    (TMP / "falsch.stp").write_text(iges_text(), encoding="latin-1")
    f = dateiformat.erkennen(TMP / "falsch.stp")
    assert f.art == dateiformat.IGES and not f.endung_passt and "passt nicht" in f.hinweis(), f


@fall("F2 Import und Messung nach Inhalt: STEP als .txt, ZIP als .step, SolidWorks als .step, Auftrag ohne Weg")
def _f2():
    d = TMP / "import"
    d.mkdir()
    (d / "teil.txt").write_text(STEP_TEXT.replace("DATA;", "DATA;\n/* aus dem Mailprogramm */"))
    (d / "archiv.step").write_bytes((D / "h.zip").read_bytes())
    (d / "solid.step").write_bytes((D / "i.sldprt").read_bytes())
    (d / "auftrag.lst").write_text(lst_text(auftrag=True, programm=False))
    (d / "notiz.txt").write_text("nur Text")
    (d / "rohr.zip").write_bytes((D / "c.tubx").read_bytes())     # TUBX mit Endung .zip: messen, nicht entpacken
    v = cad_import.vorbereiten([d], basis=TMP / "entpackt")
    namen = sorted(p.name for p in v.dateien)
    assert namen == ["rohr.zip", "teil.step", "teil.txt"], namen
    texte = {Path(b["datei"]).name: (b["stufe"], b["text"]) for b in v.befunde}
    assert texte["teil.txt"][0] == cad_import.HINWEIS and "STEP" in texte["teil.txt"][1], texte
    assert texte["archiv.step"][0] == cad_import.HINWEIS and "ZIP" in texte["archiv.step"][1], texte
    assert texte["solid.step"][0] == cad_import.FEHLER and "OLE" in texte["solid.step"][1], texte
    assert texte["auftrag.lst"][0] == cad_import.FEHLER and "Fertigungsauftrag" in texte["auftrag.lst"][1], texte
    assert "1× .txt" in texte["andere Dateien"][1], texte
    import step_geometrie as sg
    (TMP / "iges_als.stp").write_text(iges_text(), encoding="latin-1")
    assert sg.leser_art(TMP / "iges_als.stp") == "IGES"
    assert sg.leser_art(D / "a.step") == "STEP" and sg.leser_art(D / "c.tubx") == "TUBX"
    try:
        sg.leser_art(D / "e.lst")
        raise AssertionError("Fertigungsauftrag ohne Meldung")
    except ValueError as ex:
        assert "Fertigungsauftrag" in str(ex), ex


def wuerfel(a=10.0):
    p = [(x, y, z) for x in (0, a) for y in (0, a) for z in (0, a)]
    flaechen = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tri = []
    for i, j, k, m in flaechen:
        tri += [(p[i], p[j], p[k]), (p[i], p[k], p[m])]
    return tri


@fall("N1 Werkzeugnetz direkt: Würfel exakt und gültig, offenes Netz → Nähen, 3.000 Dreiecke unter 3 s")
def _n1():
    import step_blm as sb
    from OCP.BRepCheck import BRepCheck_Analyzer
    s = sb._netz_direkt(wuerfel())
    assert s is not None and BRepCheck_Analyzer(s).IsValid() and abs(sb.volumen(s) - 1000.0) < 1e-9, s
    tri = wuerfel()
    tri[0] = (tri[0][0], tri[0][2], tri[0][1])          # ein Dreieck falsch herum: wird angeglichen
    s = sb._netz_direkt(tri)
    assert s is not None and abs(sb.volumen(s) - 1000.0) < 1e-9, "Umlauf angleichen"
    offen = wuerfel()[:-1]
    assert sb._netz_direkt(offen) is None, "offenes Netz muss None geben"
    assert sb._occ_dreiecke_koerper(wuerfel()) is not None
    # Streifen mit 3.000 Dreiecken (wie eine lange offene Kontur): früher Minuten im Nähen
    import step_lst as sl
    n = 374
    links = ([(i * 0.5, -0.1, 20.0) for i in range(n)], [(0.0, 0.0, 1.0)] * n)
    rechts = ([(i * 0.5, 0.1, 20.0) for i in range(n)], [(0.0, 0.0, 1.0)] * n)
    tri = sl.streifen_dreiecke(links, rechts, 3.0)
    t0 = time.perf_counter()
    s = sb._occ_dreiecke_koerper(tri)
    dt = time.perf_counter() - t0
    assert s is not None and BRepCheck_Analyzer(s).IsValid() and dt < 3.0, dt
    assert abs(sb.volumen(s) - 0.5 * (n - 1) * 0.2 * 5.0) < 1e-6, sb.volumen(s)


def kontur_oben(bahn_xy, qs):
    """Offene Kontur auf der oberen Seite (z = h/2) im Format von lst_bahn.programme()."""
    pk = [(x, y, qs.h / 2) for x, y in bahn_xy]
    ss = [qs.punkt(p[1], p[2])[0] for p in pk]
    rk = [(0.0, 0.0, 1.0)] * len(pk)
    return dict(nr=1, art=lst_bahn.KONTUR, punkte=pk, richtung=rk, s=ss, bahn=pk, s_bahn=ss, offen=True,
                laenge=lst_bahn._laenge(pk))


@fall("N2 Kerbe mit Grund 0,08 mm < Fuge 0,2 mm: an den Knicken geteilt, Stücke gültig; normale Kontur unverändert")
def _n2():
    import step_blm as sb
    import step_lst as sl
    from OCP.BRepCheck import BRepCheck_Analyzer
    qs = lst_bahn.Querschnitt(b=60.0, h=40.0, r=4.0, wand=2.0)
    k = kontur_oben([(60.0, 0.0), (55.0, 0.0), (50.0, 0.0), (50.0, 0.08), (55.0, 0.08), (60.0, 0.08)], qs)
    st = lst_bahn.streifen_stuecke(k, qs, 0.1)
    assert len(st) == 3, len(st)
    for links, rechts in st:
        s = sb._occ_dreiecke_koerper(sl.streifen_dreiecke(links, rechts, 3.0, qs))
        assert s is not None and BRepCheck_Analyzer(s).IsValid(), "Stück ungültig"
    k2 = kontur_oben([(60.0, 0.0), (55.0, 0.0), (50.0, 0.0), (50.0, 5.0), (55.0, 5.0)], qs)
    assert lst_bahn.streifen_stuecke(k2, qs, 0.1) == [lst_bahn.streifen(k2, qs, 0.1)], "normale Kontur geändert"


@fall("N3 Werkzeugtiefe: an der Rohrecke R 4 begrenzt (Wand + (R − Wand)/2), auf ebener Seite tiefe + 1 wie bisher")
def _n3():
    import step_lst as sl
    qs = lst_bahn.Querschnitt(b=60.0, h=40.0, r=4.0, wand=2.0)
    eben = [(0.0, 0.0, 20.0), (10.0, 5.0, 20.0)]
    ecke = eben + [(10.0, 26.0 + 4 * math.sin(0.5), 16.0 + 4 * math.cos(0.5))]
    assert sl.innen_tiefe(eben, 3.0, qs) == 4.0
    assert abs(sl.innen_tiefe(ecke, 3.0, qs) - 3.0) < 1e-12, sl.innen_tiefe(ecke, 3.0, qs)
    assert sl.innen_tiefe(ecke, 3.0, None) == 4.0
    gross = lst_bahn.Querschnitt(b=60.0, h=40.0, r=8.0, wand=2.0)        # Radius größer als die Tiefe: unverändert
    assert sl.innen_tiefe(ecke, 3.0, gross) == 4.0


B, H, RE, WAND, L, HALB = 60.0, 40.0, 4.0, 2.0, 200.0, 0.1


def ring_nc(x):
    """Trennschnitt um das Rechteckrohr bei x (wie TubeCAM: Seiten mit G01 in Y, um die Ecken Y, Z und A zusammen)."""
    ay, az = B / 2 - RE, H / 2 - RE
    out = [f"TC_POS({x},{-ay},0,0)", 'TC_LASER_ON(1,"ST020",1,100)']
    for seite in range(4):
        out.append(f"G01 Y{(ay, az)[seite % 2]:.4f} A{90 * seite} ;Processing")
        cy, cz = [(ay, az), (ay, -az), (-ay, -az), (-ay, az)][seite]
        for g in range(1, 91):
            a = math.radians(90 * seite + g)
            y, z = cy + RE * math.sin(a), cz + RE * math.cos(a)
            out.append(f"G01 Y{y * math.cos(a) - z * math.sin(a):.4f} Z{y * math.sin(a) + z * math.cos(a):.4f} "
                       f"A{90 * seite + g}")
    return out + ["TC_LASER_OFF(2)"]


def abschnitt(name, namen, zeilen):
    mm = "\n".join(f"MM,AT,1,{10 * (i + 1):4d},1,1,,'{n}',,'',T" for i, n in enumerate(namen))
    da = ["DA," + ",".join(f"'{w}'" if isinstance(w, str) else str(w) for w in z) for z in zeilen]
    return f"BEGIN_{name}\nC\nZA,MM,{len(namen)}\n{mm}\nC\nZA,DA,{len(zeilen)}\n" + "\n".join(da) + \
        f"\nC\nENDE_{name}\nC\n"


def fenster_lst():
    """Rechteckrohr 60×40×2 R 4, Länge 200, oben ein Fenster x 80–120, y −10…10 (Strahlmitte) aus zwei offenen
    Schnitten mit je 1 mm Haltesteg bei y = 0 (wie TubeCAM, LST 10186133 P30)."""
    info = abschnitt("EINRICHTEPLAN_INFO", ["Maschine", "Programmnummer", "Cutting length"], [["T11", "FENSTER", 900.0]])
    tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke", "Eckenradius (Rechteckrohr)",
                                   "Hoehe (Rechteckrohr)", "Breite (Rechteckrohr)",
                                   "(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)", "Material"],
                     [["1_600X400X20_1_20", 1, 6000.0, WAND, RE, H, B, 0.0, "St37"]])
    teil = abschnitt("TUBE_PART_TECH", ["Tabellenidentifikator", "Work Part Length"], [["TPT-1", L]])
    z = ["BEGIN_PROGRAMM", "START_TEXT", "; BLOCK: TcSeparationCutFeature", *ring_nc(-HALB),
         "; BLOCK: TcToolpathCuttingContour3D", "TC_POS(80,-0.5,0,0)", 'TC_LASER_ON(1,"ST020",2,100)',
         "G01 X80 Y-10 ;Processing", "G01 X120 Y-10", "G01 X120 Y-0.5", "TC_LASER_OFF(2)",
         "; BLOCK: TcToolpathCuttingContour3D", "TC_POS(120,0.5,0,0)", 'TC_LASER_ON(1,"ST020",2,100)',
         "G01 X120 Y10 ;Processing", "G01 X80 Y10", "G01 X80 Y0.5", "TC_LASER_OFF(2)",
         "; BLOCK: TcSeparationCutFeature", *ring_nc(L + HALB), "ENDE_PROGRAMM"]
    return "BD\nSET_METRIC\nC\n" + info + tech + teil + "\n".join(z) + "\nC\nED\n"


def flaeche_rohr():
    def rr(b, h, r):
        return b * h - (4 - math.pi) * r * r
    return rr(B, H, RE) - rr(B - 2 * WAND, H - 2 * WAND, RE - WAND)


@fall("N4 Öffnung aus zwei offenen Schnitten mit Haltestegen: Abfall entfernt, Werte der Kalkulation unverändert")
def _n4():
    import step_lst as sl
    import step_blm as sb
    from OCP.BRepCheck import BRepCheck_Analyzer
    pfad = TMP / "FENSTER.lst"
    pfad.write_text(fenster_lst(), encoding="cp1252")
    (p,) = lst_bahn.lesen(pfad)
    offen = [k for k in p["konturen"] if k.get("offen")]
    assert len(offen) == 2 and abs(p["halbspalt"] - HALB) < 1e-6, (len(offen), p["halbspalt"])
    kt = sl.ketten(p)
    assert len(kt) == 1 and kt[0][0] == [offen[0]["nr"], offen[1]["nr"]], kt
    assert all(abs(s - 1.0) < 1e-6 for s in kt[0][2]), kt[0][2]
    einstiche, schnitt, klassen = p["einstiche"], p["schnittlaenge"], lst_bahn.konturliste(p)
    form, meld = sl.koerper(p)
    assert BRepCheck_Analyzer(form).IsValid(), meld
    # Fenster = Fläche innerhalb der Strahlmitte plus halbe Fuge rundum: (40 + 0,2) × (20 + 0,2); an den beiden
    # Haltestegen (1 mm) bleibt außen die halbe Fuge stehen (0,1 × 1 mm, wie nach dem Ausbrechen)
    soll = flaeche_rohr() * L - (40.2 * 20.2 - 2 * HALB * 1.0) * WAND
    assert abs(sb.volumen(form) - soll) < 0.02, (sb.volumen(form), soll, meld)
    assert any("Öffnung" in m and "Abfall entfernt" in m for m in meld), meld
    assert (p["einstiche"], p["schnittlaenge"], lst_bahn.konturliste(p)) == (einstiche, schnitt, klassen)
    k, info = sl.lies_lst_info(pfad)
    assert len(k) == 1 and info["abfall_offen"] == 0, info


@fall("N5 Nahtsuche mit Hüllquader-Vorprüfung: gleiche Füllungen wie ohne; Körper aus Maschinenprogramm ohne Nahtsuche")
def _n5():
    sys.path.insert(0, str(HIER))
    import erzeuge_testteile as et
    import step_geometrie as sg
    import step_naht_zu as nz
    from OCP.Bnd import Bnd_Box
    from test_step_wie_modell import box
    re = et.kastenrohr(50, 30, 2.6, 244.48, 5.2)
    mit = et.cut(et.cut(re, box(-0.005, 12, -1, 0.01, 5, 247)), box(-30, -10, 100, 60, 30, 40))
    neu = nz.paare(mit)
    alt_kaesten = nz._kaesten

    def ohne_pruefung(eb):     # Hüllquader, die sich immer berühren: Stand ohne Vorprüfung
        out = []
        for _ in eb:
            b = Bnd_Box()
            b.Update(-1e6, -1e6, -1e6, 1e6, 1e6, 1e6)
            out.append(b)
        return out
    nz._kaesten = ohne_pruefung
    try:
        alt = nz.paare(mit)
    finally:
        nz._kaesten = alt_kaesten
    va, vn = sum(sg._volumen(x) for x in alt), sum(sg._volumen(x) for x in neu)
    assert len(neu) == len(alt) >= 1 and va == vn, (len(alt), len(neu), va, vn)
    t = sg.analysiere(mit, "RE_Naht", 1)
    assert any("Naht ohne Spalt" in h for h in t.hinweise), t.hinweise
    t = sg.analysiere(mit, "RE_Naht", 1, aus_programm=True)
    assert not any("Naht ohne Spalt" in h for h in t.hinweise), t.hinweise


@fall("N6 Richtungsraster Dreh-/Frästeilprüfung: gleiche Richtungen wie der Vergleich mit allen (20.000 Normalen)")
def _n6():
    import random
    import step_drehfraes as df
    rnd = random.Random(26112026)
    basis = []
    for _ in range(300):
        v = [rnd.gauss(0, 1) for _ in range(3)]
        lg = math.sqrt(sum(x * x for x in v))
        basis.append(tuple(x / lg for x in v))
    normalen = []
    for _ in range(20000):        # um die Basis gestreut, viele knapp an der Grenze 0,5°, auch Gegenrichtungen
        b = rnd.choice(basis)
        s = rnd.choice((1, -1))
        v = [s * x + rnd.uniform(-0.012, 0.012) for x in b]
        lg = math.sqrt(sum(x * x for x in v))
        normalen.append(tuple(x / lg for x in v))
    normalen += [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1e-17, -1.0)]
    alt = []
    for n in normalen:
        if not any(df._parallel(n, r) for r in alt):
            alt.append(n)
    assert df._richtungen(normalen) == alt, (len(df._richtungen(normalen)), len(alt))
    ri = df._Richtungen()
    for r in alt:
        ri.dazu(r)
    for n in normalen[:3000]:
        assert ri.erste(n) == next((k for k in alt if df._parallel(k, n)), None), n


@fall("C1 Zwischenspeicher: LST neben der TUBX gehört zum Schlüssel, STEP-Schlüssel unverändert")
def _c1():
    import step_messen as sm
    d = TMP / "cache"
    d.mkdir()
    tubx_datei(d / "teil.tubx")
    (d / "teil.lst").write_text(lst_text())
    a = sm.cache_schluessel(d / "teil.tubx", "0.9", {})
    (d / "teil.lst").write_text(lst_text() + "C\n")
    b = sm.cache_schluessel(d / "teil.tubx", "0.9", {})
    assert a != b and sm.begleitdateien(d / "teil.tubx") == [d / "teil.lst"], (a, b)
    (d / "teil.step").write_bytes((d / "teil.tubx").read_bytes())      # TUBX unter .step: LST gehört ebenso dazu
    assert sm.begleitdateien(d / "teil.step") == [d / "teil.lst"], sm.begleitdateien(d / "teil.step")
    import hashlib
    import json
    import step_ergebnis
    h = hashlib.sha256((D / "a.step").read_bytes())
    h.update(json.dumps(["0.9", step_ergebnis.SCHEMA_VERSION, {}], sort_keys=True).encode("utf-8"))
    assert sm.cache_schluessel(D / "a.step", "0.9", {}) == h.hexdigest(), "STEP-Schlüssel geändert"


if __name__ == "__main__":
    if fehler:
        print(f"{fehler} Fehler")
        sys.exit(1)
    print("Alle Tests Importengine 2.0 bestanden.")
