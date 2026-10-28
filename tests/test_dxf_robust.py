"""DXF-Import robust (Patrick 28.10.2026: „DXF-Import von Blechen und Rohren deutlich erweitern und die Logik dahinter
verbessern“). Typische Dateien aus verschiedenen CAD-Programmen, synthetisch erzeugt:
- D1 Lesen: Papierbereich (Layout), Schriftfeld als Block mit Attributen, Mehrfach-Block (MINSERT), Linientyp
  „VonLayer“/„VonBlock“, Sonderzeichen (%%c, \\U+00E4, MTEXT-Formatierung), Spline nur mit Stützpunkten.
- D2 Konturen: Lücken bis 0,5 mm geschlossen (mit Hinweis), größere nicht; doppelt und teilweise doppelt gezeichnete
  Linien; zwei Teile mit gemeinsamer Kante; doppelte Bohrung; Kreis auf der Außenkante wird gemeldet; rechteckiges
  Blech mit offener Linie ist kein Zeichnungsrahmen.
- D3 Einheit: Zoll ohne Einheit und sehr kleine Teile werden gemeldet.
- D4 Gleiche Teile (Patrick 28.10.2026 „a“): auch gedreht ein Teil mit Stückzahl, gespiegelt und anders nicht.
- D5 Rohr: Schriftfeld „Werkstoff: S235JR“ / Wert rechts daneben; Patricks Rohrzeichnungen mit Papierbereich und
  CRLF ergeben dasselbe; Importfenster übernimmt die Stückzahl.

Aufruf: python tests/test_dxf_robust.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import dxf_import as di, dxf_rohr as dr, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


def g(*paare):
    return "\n".join(f"{c}\n{v}" for c, v in paare)


def datei(*entitaeten, kopf=(), bloecke=(), layer=()):
    teile = []
    if kopf:
        teile.append(g((0, "SECTION"), (2, "HEADER"), *kopf, (0, "ENDSEC")))
    if layer:
        teile.append(g((0, "SECTION"), (2, "TABLES"), (0, "TABLE"), (2, "LAYER"),
                       *[p for n, lt in layer for p in ((0, "LAYER"), (2, n), (70, 0), (62, 7), (6, lt))],
                       (0, "ENDTAB"), (0, "ENDSEC")))
    if bloecke:
        teile.append(g((0, "SECTION"), (2, "BLOCKS"), *bloecke, (0, "ENDSEC")))
    teile.append(g((0, "SECTION"), (2, "ENTITIES"), *[p for e in entitaeten for p in e], (0, "ENDSEC"), (0, "EOF")))
    return "\n".join(teile)


def lw(pk, layer="0", zu=True, extra=()):
    out = [(0, "LWPOLYLINE"), (8, layer), *extra, (90, len(pk)), (70, 1 if zu else 0)]
    for x, y in pk:
        out += [(10, x), (20, y)]
    return out


def linie(a, b, layer="0", extra=()):
    return [(0, "LINE"), (8, layer), *extra, (10, a[0]), (20, a[1]), (11, b[0]), (21, b[1])]


def kreis(c, r, layer="0", extra=()):
    return [(0, "CIRCLE"), (8, layer), *extra, (10, c[0]), (20, c[1]), (40, r)]


def text(p, t, h=3.5, layer="0", extra=()):
    return [(0, "TEXT"), (8, layer), *extra, (10, p[0]), (20, p[1]), (40, h), (1, t)]


def rechteck(x=0, y=0, b=200, h=100, layer="0"):
    return lw([(x, y), (x + b, y), (x + b, y + h), (x, y + h)], layer)


def aktive(r):
    return [t for t in r["teile"] if t["aktiv"]]


def bohrungen(t):
    return sorted(z["d"] for z in t["e"]["konturen"] if z["art"] == sw.BOHRUNG)


PAPIER = ((67, 1),)

# ------------------------------------------------------------------ D1 Lesen
r = di.importieren(datei(rechteck(), kreis((50, 50), 10),
                         lw([(0, 0), (420, 0), (420, 297), (0, 297)], extra=PAPIER),
                         kreis((300, 150), 30, extra=PAPIER), text((20, 20), "Werkstoff S355", extra=PAPIER),
                         text((20, 30), "Maßstab 1:5", extra=PAPIER)), "papier.dxf")
assert len(r["teile"]) == 1 and bohrungen(r["teile"][0]) == [20] and r["massstab"] == 1, r["teile"]
assert any("Papierbereich" in w for w in r["warnungen"]) and "Werkstoff S355" in r["texte"]
r = di.importieren(datei(lw([(0, 0), (200, 0), (200, 100), (0, 100)], extra=PAPIER)), "nur_papier.dxf")
assert len(r["teile"]) == 1 and any("nur im Papierbereich" in w for w in r["warnungen"])
ok("D1a Papierbereich: Rahmen/Schriftfeld des Layouts nicht als Teil, Texte für Werkstoff, Maßstab nicht")

sf = ((0, "BLOCK"), (8, "0"), (2, "SF"), (10, 0), (20, 0), *rechteck(0, 0, 180, 40, "RAHMEN"),
      (0, "ATTDEF"), (8, "0"), (10, 5), (20, 5), (40, 3), (1, ""), (2, "WERKSTOFF"), (3, "Werkstoff?"), (0, "ENDBLK"))
attr = [(0, "INSERT"), (8, "0"), (66, 1), (2, "SF"), (10, 500), (20, 0),
        (0, "ATTRIB"), (8, "0"), (10, 505), (20, 5), (40, 3), (1, "1.4301"), (2, "WERKSTOFF"), (70, 0),
        (0, "ATTRIB"), (8, "0"), (10, 505), (20, 15), (40, 3), (1, "t=4"), (2, "DICKE"), (70, 0),
        (0, "ATTRIB"), (8, "0"), (10, 505), (20, 25), (40, 3), (1, "geheim"), (2, "INTERN"), (70, 1),
        (0, "SEQEND"), (8, "0")]
r = di.importieren(datei(rechteck(), kreis((50, 50), 10), attr, bloecke=sf), "attrib.dxf")
assert r["dicke"] == 4 and "WERKSTOFF: 1.4301" in r["texte"] and not any("geheim" in t for t in r["texte"]), r["texte"]
assert di.werkstoff_aus(r["texte"], {"1.4301 2B": {}, "S235JR": {}}) == "1.4301 2B"
assert len(aktive(r)) == 1
ok("D1b Schriftfeld als Block mit Attributen: Werkstoff und Dicke gelesen, unsichtbare Attribute nicht")

teil = ((0, "BLOCK"), (8, "0"), (2, "P"), (10, 0), (20, 0), *rechteck(), *kreis((50, 50), 10), (0, "ENDBLK"))
minsert = [(0, "INSERT"), (8, "0"), (2, "P"), (10, 0), (20, 0), (70, 3), (71, 2), (44, 250), (45, 150)]
r = di.importieren(datei(minsert, bloecke=teil), "minsert.dxf")
assert len(r["teile"]) == 1 and r["teile"][0]["anzahl"] == 6 and bohrungen(r["teile"][0]) == [20], r["teile"]
assert "6× gleich" in r["teile"][0]["zusammenfassung"]
minsert_dreh = [(0, "INSERT"), (8, "0"), (2, "P"), (10, 0), (20, 0), (50, 90), (70, 2), (71, 1), (44, 250)]
r = di.importieren(datei(minsert_dreh, bloecke=teil), "minsert90.dxf")
assert r["teile"][0]["anzahl"] == 2
ok("D1c Mehrfach-Block (MINSERT 3×2, auch gedreht): alle Teile, als ein Teil mit Stückzahl")

lay = (("ACHSE", "CENTER"), ("XX", "DASHED"), ("0", "CONTINUOUS"))
r = di.importieren(datei(rechteck(), kreis((50, 50), 10), linie((-10, 50), (210, 50), "ACHSE", ((6, "BYLAYER"),)),
                         linie((0, 20), (200, 20), "XX", ((6, "ByLayer"),)),
                         linie((0, 80), (200, 80), "XX", ((6, "BYLAYER"),)), layer=lay), "bylayer.dxf")
assert len(r["teile"]) == 1 and r["rahmen"] == 0 and r["teile"][0]["aktiv"], r
assert not [z for z in r["teile"][0]["e"]["konturen"] if z["art"] == sw.SONSTIGE]
blk = ((0, "BLOCK"), (8, "0"), (2, "M"), (10, 0), (20, 0), *linie((0, 20), (200, 20), "0", ((6, "BYBLOCK"),)),
       (0, "ENDBLK"))
r = di.importieren(datei(rechteck(), [(0, "INSERT"), (8, "0"), (6, "DASHED"), (2, "M"), (10, 0), (20, 0)],
                         bloecke=blk), "byblock.dxf")
assert not [z for z in r["teile"][0]["e"]["konturen"] if z["art"] == sw.SONSTIGE]
ok("D1d Linientyp „VonLayer“/„VonBlock“: Strich-/Mittellinien fallen weg, Blech bleibt Blech (kein Rahmen)")

assert di.text_klar("%%c20") == "Ø20" and di.text_klar("Blechst\\U+00E4rke 3 mm") == "Blechstärke 3 mm"
assert di.text_klar("30%%d %%p0,1") == "30° ±0,1" and di.text_klar("%%uS235%%u") == "S235"
assert di.text_klar("{\\fArial|b0;Material:}\\PS235JR\\P\\H2.5;t = 2,5", mtext=True) == "Material: S235JR t = 2,5"
assert di.text_klar("\\LWerkstoff\\l; 1\\S1^2;", mtext=True) == "Werkstoff; 11/2"
r = di.importieren(datei(rechteck(), text((300, 0), "Blechst\\U+00E4rke 3 mm")), "x.dxf")
assert r["dicke"] == 3 and "Blechstärke 3 mm" in r["texte"]
ok("D1e Sonderzeichen: %%c -> Ø, \\U+00E4 -> ä, %%d/%%p, MTEXT-Formatierung (Unterstreichen, Brüche)")

fit = [(0, 0), (100, -20), (200, 0), (220, 100), (100, 140), (-20, 100)]
spline = [(0, "SPLINE"), (8, "0"), (70, 1), (71, 3), (74, len(fit))] + [p for x, y in fit for p in ((11, x), (21, y))]
r = di.importieren(datei(spline), "spline.dxf")
pk = sw.punkte(r["teile"][0]["e"]["punkte"])
assert len(pk) > 40 and any("Spline nur mit Stützpunkten" in w for w in r["warnungen"])
ecken = [el[2] for el in di.elemente(di.roh_lesen(datei(spline))) if el[0] == "S"]
assert all(min(math.dist(f, q) for q in ecken) < 1e-6 for f in fit)      # die Kurve geht durch alle Stützpunkte
ok("D1f Spline nur mit Stützpunkten: als Kurve durch die Punkte (nicht als Vieleck), mit Hinweis")

# ------------------------------------------------------------------ D2 Konturen
r = di.importieren(datei(lw([(0, 0), (200, 0), (200, 100), (0, 100), (0, 0.2)], zu=False), kreis((50, 50), 10)),
                   "luecke.dxf")
assert len(aktive(r)) == 1 and r["teile"][0]["e"]["laenge"] == 200 and bohrungen(r["teile"][0]) == [20]
assert any("Lücke" in w and "0,2 mm" in w for w in r["warnungen"]), r["warnungen"]
r = di.importieren(datei(linie((0, 0), (200, 0)), linie((200, 0.1), (200, 100)), linie((200, 100), (0, 100)),
                         linie((0, 100), (0, 0.08))), "luecken.dxf")
assert len(r["teile"]) == 1 and r["teile"][0]["e"]["breite"] == 100
try:
    di.importieren(datei(lw([(0, 0), (200, 0), (200, 100), (0, 100), (0, 2)], zu=False)), "offen.dxf")
    raise AssertionError("Lücke 2 mm darf nicht still geschlossen werden")
except di.DxfFehler as f:
    assert "offene Linienzüge" in str(f)
r = di.importieren(datei(lw([(0, 0), (200, 0), (200, 100), (0, 100), (0, 2)], zu=False), kreis((50, 50), 10)),
                   "offen2.dxf")
assert not any(t["aktiv"] and t["e"]["laenge"] == 200 for t in r["teile"])
ok("D2a Lücken: bis 0,5 mm gerade geschlossen und gemeldet, 2 mm bleibt offen (Fehler bzw. kein Blech)")

r = di.importieren(datei(rechteck(), kreis((50, 50), 10), linie((0, 0), (120, 0)), linie((120, 0), (200, 0)),
                         linie((200, 0), (200, 100)), linie((60, 100), (0, 100)), rechteck(), kreis((50, 50), 10)),
                   "doppelt.dxf")
assert len(r["teile"]) == 1 and r["rahmen"] == 0 and bohrungen(r["teile"][0]) == [20], r["teile"]
assert not r["teile"][0]["warnungen"] and any("doppelt" in w for w in r["warnungen"])
r = di.importieren(datei(linie((0, 0), (150, 0)), linie((60, 0), (200, 0)), linie((200, 0), (200, 100)),
                         linie((200, 100), (0, 100)), linie((0, 100), (0, 0))), "ueberlapp.dxf")
assert len(r["teile"]) == 1 and r["teile"][0]["e"]["laenge"] == 200 and r["teile"][0]["aktiv"]
assert not [z for z in r["teile"][0]["e"]["konturen"] if z["art"] == sw.SONSTIGE]
ok("D2b Doppelt und teilweise doppelt gezeichnete Linien/Konturen/Bohrungen nur einmal (Schnittlänge stimmt)")

r = di.importieren(datei(rechteck(), rechteck(200, 0, 100, 100)), "nachbarn.dxf")
assert sorted(t["e"]["laenge"] for t in aktive(r)) == [100, 200], r["teile"]
ok("D2c Zwei Teile mit gemeinsamer Kante: beide erkannt")

r = di.importieren(datei(rechteck(), kreis((200, 50), 10)), "rand.dxf")
gross = next(t for t in r["teile"] if t["e"]["laenge"] == 200)
klein = next(t for t in r["teile"] if t["e"]["laenge"] == 20)
assert not klein["aktiv"] and "überschneidet" in klein["grund"] and any("überschneidet" in w for w in gross["warnungen"])
r = di.importieren(datei(rechteck(), kreis((50, 50), 10), kreis((60, 50), 10)), "innen.dxf")
assert any("Innenkonturen überschneiden" in w for w in r["teile"][0]["warnungen"])
ok("D2d Kreis auf der Außenkante und sich schneidende Innenkonturen werden gemeldet, nicht still gerechnet")

r = di.importieren(datei(rechteck(), linie((20, 50), (180, 50))), "schlitz.dxf")
assert r["rahmen"] == 0 and len(r["teile"]) == 1
ok("D2e Rechteckiges Blech mit offener Schnittlinie bleibt Blech (kein Zeichnungsrahmen)")

# ------------------------------------------------------------------ D3 Einheit
r = di.importieren(datei(rechteck(0, 0, 8, 4), kopf=((9, "$MEASUREMENT"), (70, 0))), "zoll.dxf")
assert any("Zoll" in w and "1:25,4" in w for w in r["warnungen"])
r = di.importieren(datei(rechteck(0, 0, 8, 4)), "klein.dxf")
assert any("kleiner als 20 mm" in w for w in r["warnungen"])
r = di.importieren(datei(rechteck(0, 0, 8, 4), kopf=((9, "$INSUNITS"), (70, 1))), "inch.dxf")
assert r["teile"][0]["e"]["laenge"] == 203.2 and not any("Einheit" in w for w in r["warnungen"])
ok("D3 Einheit: Zoll ohne Einheit und sehr kleine Teile gemeldet, Zoll mit Einheit umgerechnet")


# ------------------------------------------------------------------ D4 gleiche Teile
def winkel(x, y, w=0, spiegel=False, loch=8):
    """L-Blech mit Bohrung, um w Grad gedreht (und gespiegelt) an x, y."""
    pk = [(0, 0), (120, 0), (120, 30), (30, 30), (30, 80), (0, 80)]
    c = (15, 15)
    if spiegel:
        pk, c = [(-a, b) for a, b in pk], (-c[0], c[1])
    cw, sn = math.cos(math.radians(w)), math.sin(math.radians(w))

    def d(p):
        return (x + p[0] * cw - p[1] * sn, y + p[0] * sn + p[1] * cw)
    return [lw([d(p) for p in pk]), kreis(d(c), loch / 2)]


r = di.importieren(datei(*winkel(0, 0), *winkel(300, 0, 90), *winkel(600, 0, 33)), "gleich.dxf")
assert len(r["teile"]) == 1 and r["teile"][0]["anzahl"] == 3, [(t["name"], t.get("anzahl")) for t in r["teile"]]
assert any("3 gleiche Teile" in w for w in r["warnungen"])
r = di.importieren(datei(*winkel(0, 0), *winkel(300, 0, spiegel=True), *winkel(600, 0, loch=10)), "anders.dxf")
assert len(r["teile"]) == 3 and all(t["anzahl"] == 1 for t in r["teile"])
ok("D4 Gleiche Teile (auch gedreht) ein Teil mit Stückzahl; gespiegelt oder andere Bohrung eigene Teile")

# ------------------------------------------------------------------ D5 Rohr
T = [("0", (0, 0), 2.5, 0, "Werkstoff: S235JR"), ("0", (0, -10), 2.5, 0, "Benennung"),
     ("0", (40, -10), 2.5, 0, "Halter"), ("0", (0, -20), 2.5, 0, "Benennung / Title")]
assert dr.schriftfeld(T, ("werkstoff",)) == "S235JR" and dr.schriftfeld(T, ("benennung",)) == "Halter"
assert dr.schriftfeld([("0", (0, 0), 2, 0, "Werkstoff"), ("0", (0, -4), 3.5, 0, "1.4301")], ("werkstoff",)) == "1.4301"
for name in ("rohr_gehrung_QR40_patrick.dxf", "rohr_bauteil1_patrick.dxf"):
    txt = di.datei_lesen(HIER / "dxf" / name)
    basis = dr.erkennen(txt, name)
    i = txt.index("ENTITIES") + len("ENTITIES")
    papier = "\n" + g(*linie((0, 0), (420, 0), "KONTUR", PAPIER), *kreis((100, 100), 30, "KONTUR", PAPIER),
                      *text((5, 5), "Maßstab 1:10", 3, "TEXT", PAPIER))
    for variante in (txt[:i] + papier + txt[i:], txt.replace("\n", "\r\n")):
        e = dr.erkennen(variante, name)
        assert e["ok"] and e["eingaben"] == basis["eingaben"] and e["profil"] == basis["profil"], name
ok("D5a Rohr: Schriftfeld „Werkstoff: S235JR“ / Wert rechts; Papierbereich und CRLF ändern nichts")

from rohrlaser.dxf_import_dialog import DxfImportDialog  # noqa: E402

d = DxfImportDialog(None, None, text=datei(minsert, bloecke=teil), pfad="minsert.dxf")
assert d.zustand[0]["stueck"] == 6
ok("D5b Importfenster: Stückzahl gleicher Teile vorbelegt")
print("Alle Tests DXF-Import robust bestanden.")
