"""Synthetische BLM-BPF-Dateien im Aufbau der echten (keine Kundendaten im Repo) für die Tests der
Produktionsdaten-Intelligenz. Schreiber wie in test_blm_import (Gegenstück zu step_blm._dokument)."""
import math
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))
from step_messung import step_blm  # noqa: E402


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


def _pkt(eltern, tag, p):
    ET.SubElement(eltern, tag, x=f"{p[0]:.10f}", y=f"{p[1]:.10f}", z=f"{p[2]:.10f}")


def bpf(ziel, name="Teil-1", laenge=400.0, b=60.0, h=40.0, wand=3.0, bohrungen=2, rechtecke=1, eilgaenge=True,
        ang_out=90.0, werkstoff="S235", maschine="LT8"):
    """BPF eines Rechteckrohrs b × h × wand mit Trennschnitten an beiden Enden, Bohrungen (Ø 10) und rechteckigen
    Ausschnitten (40 × 10) schreiben."""
    pr = ET.Element("Progetto", prj="CAM")
    ET.SubElement(pr, "versione_output_xml").text = "3.10"
    ET.SubElement(pr, "sw").text = "Artube"
    ET.SubElement(pr, "versione_sw").text = "22.2.3"
    it = ET.SubElement(pr, "info_tubo")
    sez = ET.SubElement(it, "sezione")
    ET.SubElement(sez, "nome_sezione").text = "Rettangolare"
    for k, v in (("tipo", 3), ("dim_x", b), ("dim_y", h), ("spessore", wand), ("raggiatura", 0),
                 ("superficie", 2 * wand * (b + h - 2 * wand))):
        ET.SubElement(sez, k).text = str(v)
    ET.SubElement(it, "materiale").text = werkstoff
    pz = ET.SubElement(pr, "info_pezzo")
    ET.SubElement(pz, "nome").text = name
    ET.SubElement(pz, "data_partprogram").text = "2026/11/24"
    ET.SubElement(pz, "lunghezza").text = f"{laenge:.6f}"
    ET.SubElement(pz, "volume").text = "1000.0"
    ET.SubElement(pz, "microgiunzioni").text = "0"
    ET.SubElement(ET.SubElement(pz, "angoli"), "ang_conico_max").text = "0.0"
    mv = ET.SubElement(ET.SubElement(pz, "macchine", n="1"), "macchina_valida", id="1")
    ET.SubElement(mv, "famiglia").text = maschine
    ET.SubElement(pz, "unbekanntes_feld").text = "42"
    z = h / 2
    konturen = []

    def ring(x):
        pk = [(x, 0, z), (x, b / 2, z), (x, b / 2, -z), (x, -b / 2, -z), (x, -b / 2, z), (x, 0, z)]
        return ("2", [(10, [(p, (0, 0, 1)) for p in pk])])
    konturen.append(ring(0.0))
    for i in range(bohrungen):
        x = 50.0 + 40.0 * i
        kreis = [((x + 5 * math.cos(2 * math.pi * k / 36), 5 * math.sin(2 * math.pi * k / 36), z), (0, 0, 1))
                 for k in range(37)]
        konturen.append(("1", [(2, [((x, 0, z), (0, 0, 1)), kreis[0]]), (10, kreis)]))
    for i in range(rechtecke):
        x0 = 250.0 + 60.0 * i
        pk = [(x0, -5, z), (x0 + 40, -5, z), (x0 + 40, 5, z), (x0, 5, z), (x0, -5, z)]
        konturen.append(("1", [(2, [((x0 + 20, 0, z), (0, 0, 1)), (pk[0], (0, 0, 1))]), (10, [(p, (0, 0, 1)) for p in pk])]))
    konturen.append(ring(laenge))
    geos = ET.SubElement(pr, "geometrie", n=str(len(konturen)))
    for i, (tipogeo, flaechen) in enumerate(konturen):
        g = ET.SubElement(geos, "info_geo", id=str(i + 1))
        ET.SubElement(g, "tipogeo").text = tipogeo
        lg = sum(math.dist(a[0], c[0]) for art, pk in flaechen if art != 2 for a, c in zip(pk, pk[1:]))
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
    if eilgaenge:
        r = ET.SubElement(pr, "rapidi", n=str(len(konturen) + 1))
        for i in range(len(konturen) + 1):
            ET.SubElement(r, "info_rapido", id=str(i + 1))
    roh = bytearray(b"\xe7>(c) Adige S.p.A. BLMGroup 2008 \x00\x03\x01" + bytes(380))
    for bl in bpf_block(pr):
        roh += zlib.compress(bl, 9)
    ns = ET.Element("nesting", version="1.0")
    for k, v in (("Length", laenge), ("AngIn", 0), ("AngOut", ang_out), ("XCutMax", laenge)):
        ET.SubElement(ns, k).text = str(v)
    for bl in bpf_block(ns):
        roh += zlib.compress(bl, 9)
    Path(ziel).write_bytes(bytes(roh))
    return Path(ziel)
