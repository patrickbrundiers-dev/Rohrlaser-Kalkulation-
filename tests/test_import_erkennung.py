"""Erkennung beim Import in den Editor (Patrick 10.11.2026: „mit Editor war der komplette Import in den Editor gemeint,
die Erkennung der Konturen“). Messreihe an 18 echten Baugruppen von Patrick (2.748 Körper): jedes Teil gemessen,
übernommen, das Modell des Editors gegen die STEP verglichen. Gefunden und behoben:

E1a Gegenprobe offener Profile richtete das Modell falsch aus: der Schwerpunkt der Linienpunkte hängt an der Teilung
    (gewalzte Radien der STEP sind fein geteilt), und der größte Abstand ist bei 3 mm gekappt – falsche Lagen waren
    nicht zu unterscheiden. Winkel mit Gehrung galten als „3 mm neben der STEP“, obwohl sie stimmten. Jetzt zusätzlich
    Start über die Mitte des Hüllquaders, Wahl nach dem mittleren Abstand, Ende B und Konturen entscheiden mit.
E1b komplexes Ende am Winkel: die Stelle s = Umfang (anderes Schenkelende) fiel im Raster auf s = 0 – eine Zacke
    bis zur ganzen Ausklinkung im Editor (gespiegeltes Teil eines Rahmens).
E2  Rohr, das ein unsicher erkanntes Blech/einen Bolzen (eigener Körper) berührt: wird übernommen (Ampel bleibt gelb,
    Anbauteile stehen offen in der Position). Verschmolzene Anbauteile sperren weiter.
E3  sehr dicke Wand (ab 25 % des kleineren Außenmaßes): gelb, erst nach Bestätigen (Dreh-/Frästeil?).
E4  Flachstahl mit Längsfasen, der so in den Stammdaten steht: ohne Anhaken.
E5  Meldung des STEP-Lesers zur Datei allein macht einen gültigen Körper nicht „prüfen“.

Aufruf: python tests/test_import_erkennung.py
"""
import json
import math
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung")]

from rohrlaser import step, step_gegenprobe as gp  # noqa: E402

FAELLE = []


def fall(name):
    def deko(f):
        FAELLE.append((name, f))
        return f
    return deko


def _winkel_ende(fein=False, zacke=0.0):
    """Linien eines Winkels 50 × 50 × 4 an Ende A mit Gehrung 45° über einen Schenkel (wie rohr3d: Schenkel 1 flach
    bei z = 0, Schenkel 2 steigt mit y). fein: der Bogen an der Ecke in 40 Stücken (wie ein STEP-Netz)."""
    def z(y):
        return y + 25.0
    aussen = [(-25, 25), (-25, -25), (25, -25)]
    innen = [(25, -21), (-21, -21), (-21, 25)]
    pts = []
    for (x0, y0), (x1, y1) in zip(aussen + innen + [aussen[0]], (aussen + innen + [aussen[0]])[1:] + [aussen[0]]):
        n = 40 if fein and (x0, y0) == (-25, 25) else 4
        for i in range(n):
            a = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
            b = (x0 + (x1 - x0) * (i + 1) / n, y0 + (y1 - y0) * (i + 1) / n)
            pts.append(((a[0], a[1], z(a[1]) if a[0] < -20.9 else 0.0), (b[0], b[1], z(b[1]) if b[0] < -20.9 else 0.0)))
    return [s for s in pts if math.dist(*s) > 1e-9]


@fall("E1a Gegenprobe: Winkel mit Gehrung wird richtig ausgerichtet (fein geteilte STEP, gedreht und verschoben)")
def _():
    mod = _winkel_ende()
    # STEP: dasselbe Ende, um 270° gedreht, verschoben, eine Kante fein geteilt (Schwerpunkt der Punkte verschoben)
    st = gp._bewegen(_winkel_ende(fein=True), 0, -1, 1, (11.4, -11.4, 0.0))
    dd, c, s, sp, sh = gp._ausrichten(mod, st, 0.0)
    assert dd < 0.05, dd
    assert (c, s, sp) == (0, -1, 1), (c, s, sp)
    # gespiegeltes Gegenstück: Ende A passt in zwei Lagen, Ende B (nur auf einer Seite) entscheidet
    b_mod = [((-25.0, 25.0, 400.0), (-25.0, -25.0, 400.0))]
    for spiegel in (1, -1):
        st = gp._bewegen(mod, 1, 0, spiegel, (3.0, 2.0, 0.0))
        b_st = gp._bewegen(b_mod, 1, 0, spiegel, (3.0, 2.0, 0.0))
        d = gp._abweichung_offen(st, [], b_st, mod, [], b_mod, 4.0, 0.0)
        assert d is not None and d[0] <= gp.GRENZE, (spiegel, d)


@fall("E1b Umriss eines komplexen Endes am Winkel: Schenkelende bei s = Umfang fällt nicht auf s = 0")
def _():
    # Zug über den ganzen Umfang 100: bei s = 0 liegt die Kante 28 mm hinter dem Ende, fällt bis s = 30 auf 0
    zug = [(0.0, 28.0), (30.0, 0.0), (100.0, 0.0)]
    um = step._ende_umriss(dict(umriss=zug + [None]), False, 400.0, lambda s: s, 100.0, offen=True)
    assert um and abs(um[0][0]) < 1e-6 and abs(um[0][1] - 28.0) < 0.05, um[:3]
    assert all(a < 0.05 for s, a in um if s > 30.5), um
    # geschlossenes Rohr: s = Umfang ist wieder s = 0 (unverändert)
    um = step._ende_umriss(dict(umriss=zug), False, 400.0, lambda s: s, 100.0, u_umfang=100.0)
    assert um and um[0][1] < 0.05, um[:3]


def _rohr(**werte):
    m = dict(datei="t.step", artikel="t-K1", profilform="Quadratrohr", abm_a="40", abm_b="0", wandstaerke="3",
             laenge="500", hinweise="", pruefstatus="plausibel",
             sicherheit="achse=sicher;laenge=sicher;profil=sicher;wandstaerke=sicher;konturen=sicher")
    m.update(werte)
    return m


def _anbau(quelle, vertrauen="prüfen"):
    return json.dumps([dict(nr=1, art="Sonstiges", quelle=quelle, z=250.0, vertrauen=vertrauen, gravur_laenge=20.0)])


@fall("E2 Rohr mit unsicherem Anbauteil: eigener Körper sperrt nicht, verschmolzen sperrt, Ampel bleibt gelb")
def _():
    si = "achse=sicher;laenge=sicher;profil=sicher;wandstaerke=sicher;konturen=sicher;anbauteile=unsicher"
    m = _rohr(sicherheit=si, anbauteile=_anbau("Körper 7"), pruefstatus="prüfen",
              hinweise="Anbauteil 1 (Sonstiges) bei z = 250 mm nicht sicher erkannt, prüfen")
    assert step.unsicher(m) == ["anbauteile"] and step.sperrt(m) == [] and step.gewaehlt(m)
    assert step.ampel(m)[0] == "gelb"
    v = _rohr(sicherheit=si, anbauteile=_anbau("verschmolzen"), pruefstatus="prüfen")
    assert step.sperrt(v) == ["anbauteile"] and not step.gewaehlt(v)
    lang = dict(m, hinweise="Anbau über (fast) die ganze Länge angenommen: Rohrprofil aus Innenkontur + Wandstärke, prüfen")
    assert not step.gewaehlt(lang)
    assert step.gewaehlt(dict(v, _uebernehmen=True)) and not step.gewaehlt(dict(m, _uebernehmen=False))
    # anderes unsicheres Merkmal sperrt weiter
    assert not step.gewaehlt(dict(m, sicherheit=si.replace("profil=sicher", "profil=unsicher")))


@fall("E3 sehr dicke Wand: gelb und erst nach Bestätigen, normale Rohre unverändert")
def _():
    for form, a, b, w, dick in (("Quadratrohr", 80, 0, 25, True), ("Rundrohr", 30, 0, 10, True),
                                ("Rechteckrohr", 100, 40, 10, True), ("Quadratrohr", 80, 0, 8, False),
                                ("Rundrohr", 60.3, 0, 5, False), ("Rechteckrohr", 100, 50, 12, False)):
        m = _rohr(profilform=form, abm_a=str(a), abm_b=str(b), wandstaerke=str(w))
        assert bool(step.dickwandig(m)) == dick, (form, a, b, w)
        assert step.gewaehlt(m) == (not dick), (form, a, b, w)
        assert (step.ampel(m)[0] == "gelb") == dick
        assert step.gewaehlt(dict(m, _uebernehmen=True))
    assert not step.dickwandig(_rohr(profilform="Flachstahl", abm_a="60", abm_b="20", wandstaerke="20"))


@fall("E4 Flachstahl mit Längsfasen: mit Flachstahl in den Stammdaten ohne Anhaken, sonst weiter bestätigen")
def _():
    si = "achse=sicher;laenge=sicher;profil=unsicher;wandstaerke=sicher;konturen=wahrscheinlich"
    hin = "Querschnitt mit Längsfasen an den Kanten: 4 × 4 mm, 4 × 4 mm – Querschnitt wie in der STEP, Werkstoff/Profil prüfen"
    profile = {"FL 60x20": dict(profil_id="FL 60x20", form="Flachstahl", a=60.0, b=20.0, wand=20.0)}
    bekannt = _rohr(profilform="Flachstahl", abm_a="60", abm_b="20", wandstaerke="0", sicherheit=si, hinweise=hin)
    fremd = _rohr(profilform="Flachstahl", abm_a="65", abm_b="19", wandstaerke="0", sicherheit=si, hinweise=hin)
    if step.finde_profil(bekannt, profile) is None:      # Flachstahl der Stammdaten: Dicke als Wand oder als b
        profile["FL 60x20"]["wand"] = step._wand(bekannt)
    assert step.finde_profil(bekannt, profile) is not None
    assert not step.gewaehlt(bekannt) and not step.gewaehlt(fremd)
    assert step.fasen_vorbelegen([bekannt, fremd], profile) == 1
    assert step.gewaehlt(bekannt) and not step.gewaehlt(fremd)
    assert step.ampel(bekannt)[0] == "gelb"         # Hinweis bleibt sichtbar


@fall("E5 Meldung des STEP-Lesers allein: gültiger Körper bleibt plausibel")
def _():
    import step_geometrie as g
    t = g.Teil(datei="t.step", koerper=1)
    t.profilform, t.laenge, t.gueltig = "Quadratrohr", 500.0, True
    t.hinweise.append(f"{g.LESER_HINWEIS}: Fehler: Parameter n0.1 (dimensions) not an Entity")
    assert t.pruefstatus == "plausibel", t.pruefstatus
    t.gueltig = False
    assert t.pruefstatus == "prüfen"
    t.gueltig = True
    t.hinweise.append("Wandstärken verschieden: senkrecht 3 mm, waagerecht 4 mm")
    assert t.pruefstatus == "prüfen"


if __name__ == "__main__":
    fehler = 0
    for name, f in FAELLE:
        try:
            f()
            print("OK    ", name)
        except Exception as e:  # noqa: BLE001
            fehler += 1
            print("FEHLER", name, "->", type(e).__name__, e)
    print(f"{len(FAELLE) - fehler} von {len(FAELLE)} Fällen bestanden")
    sys.exit(1 if fehler else 0)
