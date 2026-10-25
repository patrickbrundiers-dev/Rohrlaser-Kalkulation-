"""DXF-Import verbessern (Plan kalkulation/3d-editor/Plan_DXF-Import_verbessern.md, Freigabe Patrick 25.10.2026
„a a a a a a“):
- V1 Rohrzeichnung (Patricks test.dxf: QR 40 × 40 × 3, 150 lang, Ansichten, Schnitt, Isometrie): als Rohr erkannt,
  kein Teil angehakt, Hinweis mit Profil und Länge; Layer MASSE (Maßpfeile) fällt weg.
- V2 Blech mit Seitenansicht und Isometrie: nur die Abwicklung angehakt, Seitenansicht gibt die Dicke, Isometrie
  und Splitter (Pfeil auf Layer 0) nicht angehakt mit Grund; weitere Layer aus der Einstellung fallen weg.
- V3 Ansichten einzeln: Gruppen, Isometrie, Seitenansicht, Rohrquerschnitt rund/eckig, ungleiche Wand kein Rohr.
- V4 Importfenster: Hinweis Rohr, 0 Teile, Dicke aus Seitenansicht.

Aufruf: python tests/test_dxf_ansichten.py
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import dxf_ansichten as da, dxf_import as di  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.dxf_import_dialog import DxfImportDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


def datei(*entitaeten):
    return g((0, "SECTION"), (2, "ENTITIES"), *[p for e in entitaeten for p in e], (0, "ENDSEC"), (0, "EOF"))


def lw(pk, layer="0"):
    out = [(0, "LWPOLYLINE"), (8, layer), (90, len(pk)), (70, 1)]
    for x, y in pk:
        out += [(10, x), (20, y)]
    return out


def kreis(c, r, layer="0"):
    return [(0, "CIRCLE"), (8, layer), (10, c[0]), (20, c[1]), (40, r)]


def rechteck(x, y, b, h, layer="0"):
    return lw([(x, y), (x + b, y), (x + b, y + h), (x, y + h)], layer)


# ------------------------------------------------------------------ V1 Rohrzeichnung
text = (HIER / "dxf" / "rohr_ansichten_QR40.dxf").read_text(encoding="utf-8", errors="replace")
erg = di.importieren(text, "test.dxf")
assert erg["rohr"] and erg["rohr"]["form"] == "Quadratrohr", erg["rohr"]
assert (erg["rohr"]["a"], erg["rohr"]["b"], erg["rohr"]["wand"], erg["rohr"]["laenge"]) == (40, 40, 3, 150), erg["rohr"]
assert erg["teile"] and not any(t["aktiv"] for t in erg["teile"])
assert all(t["grund"] == "Rohrzeichnung, kein Blech" for t in erg["teile"])
assert "QR 40 × 40 × 3, Länge 150 mm" in erg["warnungen"][0] and "3E-12" in erg["warnungen"][0]
assert not any(t["zusammenfassung"].startswith("2.3 × 3.1") for t in erg["teile"])        # Maßpfeil (Layer MASSE)
assert di.layer_art("MASSE") == di.layer_art("Maße") == di.layer_art("VERDECKT") == "weg"
assert di.layer_art("SCHRAFFUR") == di.layer_art("Bemaßung") == "weg" and di.layer_art("KONTUR") == "schnitt"
ok("V1 Rohrzeichnung (test.dxf): QR 40 × 40 × 3, Länge 150 erkannt, kein Teil angehakt, Maßpfeile weg")

# ------------------------------------------------------------------ V2 Blech mit Ansichten
iso = [(400, 0), (486.6, 50), (486.6, 90), (400, 140), (313.4, 90), (313.4, 50)]      # Kanten unter 30°/90°/150°
blech = datei(rechteck(0, 0, 200, 100, "KONTUR"), kreis((50, 50), 5, "KONTUR"),
              rechteck(0, -40, 200, 3, "KONTUR"),                                  # Seitenansicht, Dicke 3
              lw(iso, "KONTUR"),
              lw([(0, 120), (3, 121), (0, 122)], "0"),                              # Pfeil auf Layer 0: Splitter
              lw([(0, 130), (3, 131), (0, 132)], "MASSE"),                          # Pfeil auf Layer MASSE: weg
              rechteck(250, 0, 30, 20, "ZUSATZ_XY"))
erg = di.importieren(blech, "platte.dxf")
assert erg["rohr"] is None
aktiv = [t for t in erg["teile"] if t["aktiv"]]
assert len(aktiv) == 2 and aktiv[0]["e"]["laenge"] == 200 and len(aktiv[0]["e"]["konturen"]) == 1, \
    [(t["zusammenfassung"], t["grund"]) for t in erg["teile"]]
gruende = sorted(t["grund"] for t in erg["teile"] if not t["aktiv"])
assert gruende == ["Isometrie, keine Abwicklung", "Seitenansicht (Dicke 3 mm)", "kleiner als 5 mm (Maßpfeil, "
                   "Splitter?)"], gruende
assert erg["dicke"] == 3 and erg["dicke_quelle"] == "Seitenansicht"
assert any("Isometrische Ansicht" in w for w in erg["warnungen"])
erg2 = di.importieren(blech, "platte.dxf", weg=di.weg_worte("zusatz; abc"), splitter=0)
assert len([t for t in erg2["teile"] if t["aktiv"]]) == 2                          # Rechteck weg, Pfeil angehakt
assert not any(t["e"]["laenge"] == 30 for t in erg2["teile"])
ok("V2 Blech: Abwicklung angehakt, Seitenansicht = Dicke 3, Isometrie und Splitter mit Grund, Layer aus Einstellung")

# ------------------------------------------------------------------ V3 Bausteine
ans = da.gruppen([((0, 0), (100, 0)), ((100, 0.5), (100, 50)), ((300, 0), (310, 0))], [((50, 6), 5)])
assert len(ans) == 2 and sorted(len(a.strecken) for a in ans) == [1, 2] and sum(len(a.kreise) for a in ans) == 1
assert da.ist_isometrie(list(zip(iso, iso[1:] + iso[:1])))
assert not da.ist_isometrie([((0, 0), (100, 0)), ((100, 0), (50, 86.6)), ((50, 86.6), (0, 0))])   # Dreieck 60°
rund = da.rohr_querschnitt(dict(bb=(0, 0, 48.3, 48.3), rund=True), dict(bb=(3.2, 3.2, 45.1, 45.1), rund=True))
assert rund == dict(form="Rundrohr", a=48.3, b=48.3, wand=3.2), rund
re_ = da.rohr_querschnitt(dict(bb=(0, 0, 60, 40)), dict(bb=(2, 2, 58, 38)))
assert re_ == dict(form="Rechteckrohr", a=60, b=40, wand=2), re_
assert da.rohr_querschnitt(dict(bb=(0, 0, 60, 40)), dict(bb=(2, 5, 58, 35))) is None         # Wand ungleich
assert da.rohr_querschnitt(dict(bb=(0, 0, 100, 100)), dict(bb=(30, 30, 70, 70))) is None     # Rahmenblech
a1 = da.Ansicht((0, 0, 60, 40), [], [], False)
lang = da.Ansicht((100, 0, 900, 40), [], [], False)
assert da.rohr_erkennen([(a1, re_)], [a1, lang])["laenge"] == 800
assert da.rohr_erkennen([(a1, re_)], [a1]) is None                                 # Querschnitt allein: Blech
ok("V3 Bausteine: Gruppen, Isometrie (nicht bei 60°-Dreieck), Rohrquerschnitt rund/eckig, ungleiche Wand, Rahmen")

# ------------------------------------------------------------------ V4 Importfenster
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    db = Datenbank(Path(tmp) / "r.db")
    d = DxfImportDialog(None, db, text=text, pfad="test.dxf")
    assert d.fehler is None and d.gewaehlt() == []
    assert "Rohr" in d.info.text() and not d.knoepfe.button(QDialogButtonBox.Ok).isEnabled()
    db.einstellung_setzen("dxf_splitter", 0)
    d2 = DxfImportDialog(None, db, text=blech, pfad="platte.dxf")
    assert len(d2.gewaehlt()) == 3 and d2.dicke_vorschlag == 3 and d2.quelle == "aus Seitenansicht"
    d.close()
    d2.close()
    db.con.close()
ok("V4 Importfenster: Rohrhinweis, nichts übernehmbar; Dicke aus Seitenansicht; Splitter-Grenze aus Einstellung")
print("Alle Tests DXF-Ansichten bestanden.")
