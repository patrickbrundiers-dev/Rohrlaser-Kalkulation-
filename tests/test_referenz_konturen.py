"""Testsammlung mit Sollmaßen aus der Konstruktion (Master-Auftrag Patrick 25.11.2026 „Abwicklungskern für den STEP-/
CAD-Import grundlegend erweitern“, Paket P1/P2).

Misst die 10 Referenzteile aus tests/step_referenz_konturen (erzeugt von tests/erzeuge_referenz_konturen.py) mit der
STEP-Messung und vergleicht jede Kontur mit dem Sollwert aus tests/daten/referenz_konturen_soll.json:
- gleiche Anzahl geschnittener Konturen (nichts fehlt, nichts doppelt)
- je Sollkontur genau eine gemessene mit gleicher Rolle (konturrolle.py) und Schnittlänge in der Toleranz
- Schneidbarkeit: Stufe wie im Soll (Standard 1 eindeutig)
- Baugruppe R10: jedes Rohr wie einzeln, die Platte ist ein Blech
Dazu Einzelprüfungen von konturrolle.rolle für Fälle, die kein Referenzteil hat (Fase, fehlende Werte, Gravur).

Aufruf: python tests/test_referenz_konturen.py
"""
import json
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import konturrolle as kr  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

ORDNER = HIER / "step_referenz_konturen"
SOLL = json.loads((HIER / "daten" / "referenz_konturen_soll.json").read_text(encoding="utf-8"))
TOL = SOLL["toleranz"]
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


def tol(soll):
    return max(TOL["laenge_mm"], TOL["laenge_rel"] * abs(soll))


def vergleichen(name, t, soll):
    """Gemessenes Teil t gegen die Sollkonturen; Fehlertext oder None."""
    gemessen = [(d, kr.rolle(d, t.wandstaerke)) for d in t.konturen_liste]
    geschnitten = [(d, r) for d, r in gemessen if r["schnitt"]]
    assert len(geschnitten) == len(soll["konturen"]), \
        f"{name}: {len(geschnitten)} geschnittene Konturen, soll {len(soll['konturen'])}"
    frei = list(geschnitten)
    for s in soll["konturen"]:
        kand = [(d, r) for d, r in frei if r["rolle"] == s["rolle"] and abs(d["schnittlaenge"] - s["schnittlaenge"])
                <= tol(s["schnittlaenge"]) and (s.get("z") is None or abs((d.get("z") or 0) - s["z"]) <= 0.5)]
        assert kand, (f"{name}: keine {s['rolle']} mit {s['schnittlaenge']:.2f} mm ({s['formel']}); gemessen "
                      + ", ".join(f"{r['rolle']} {d['schnittlaenge']}" for d, r in frei))
        d, r = kand[0]
        frei.remove(kand[0])
        stufe = s.get("stufe", kr.EINDEUTIG)
        assert r["stufe"] == stufe, f"{name}: {s['rolle']} Stufe {r['stufe']} ({r['grund']}), soll {stufe}"
        for k in ("durchmesser", "laenge", "gehrung"):
            if s.get(k) is not None:
                assert abs((d.get(k) or 0) - s[k]) <= TOL["winkel"] if k == "gehrung" else \
                    abs((d.get(k) or 0) - s[k]) <= 0.05, f"{name}: {s['rolle']} {k} {d.get(k)}, soll {s[k]}"
        if s.get("gegenrohr"):
            assert abs(float(d["gegenrohr"]["d"]) - s["gegenrohr"]) < 0.05, f"{name}: Gegenrohr {d['gegenrohr']}"


teile = {}
for f in sorted(ORDNER.glob("R*.step")):
    teile[f.stem] = analysiere_datei(str(f))
assert len(teile) == 10, f"{len(teile)} Referenzteile, soll 10 (python tests/erzeuge_referenz_konturen.py)"

for name, soll in SOLL["teile"].items():
    if "konturen" not in soll:
        continue

    @fall(f"{name}: Rollen, Schnittlängen, Stufen wie die Konstruktion")
    def _(name=name, soll=soll):
        ts = teile[name]
        assert len(ts) == 1, f"{len(ts)} Körper"
        assert ts[0].profilform == soll["profil"], f"Profil {ts[0].profilform}, soll {soll['profil']}"
        vergleichen(name, ts[0], soll)


@fall("R10 Baugruppe: jedes Rohr wie einzeln, Platte als Blech")
def _():
    s = SOLL["teile"]["R10_Baugruppe"]
    ts = teile["R10_Baugruppe"]
    rohre = [t for t in ts if t.profilform != "Blech"]
    assert len(rohre) == 3 and len(ts) == 4, [t.profilform for t in ts]
    for t, einzeln in zip(rohre, s["baugruppe"]):
        vergleichen(f"R10/{einzeln}", t, SOLL["teile"][einzeln])
    assert [t.profilform for t in ts if t not in rohre] == ["Blech"]


@fall("R04: 2D-Schnitt länger als die 3D-Schnittkurve (Strahl zur Rohrmitte, innen maßhaltig)")
def _():
    k = SOLL["teile"]["R04_RR60-3x3_Seitenloch20"]["konturen"][2]
    assert k["schnittlaenge"] > k["schnittlaenge_3d"] > math.pi * 20, k


@fall("Rolle: Durchbruch nur mit Gegenseite, Gravur ohne Schnitt, fehlende Werte nicht sicher")
def _():
    assert kr.rolle(dict(art="Bohrung", z=10, durchmesser=8, schnittlaenge=25.1))["rolle"] == kr.INNEN
    assert kr.rolle(dict(art="Bohrung", z=10, durchmesser=8, schnittlaenge=25.1, gegenueber=True))["rolle"] == \
        kr.DURCHBRUCH
    g = kr.rolle(dict(art="Gravur", durchgehend=False, schnittlaenge=40))
    assert not g["schnitt"] and g["stufe"] == kr.EINDEUTIG, g
    for d in (dict(art="Bohrung", z=10, schnittlaenge=0), dict(art="Ende B", form="nicht erkannt", schnittlaenge=50),
              dict(art="???", schnittlaenge=5), dict(art="Bohrung", schnittlaenge=12), None):
        r = kr.rolle(d)
        assert r["stufe"] == kr.NICHT_SICHER and r["grund"], (d, r)
    assert kr.rolle(dict(art="Bohrung", z=5, schnittlaenge="nan"))["stufe"] == kr.NICHT_SICHER


@fall("Rolle: Fase, kleine Öffnung, mehrere Wände, Freiform = problematisch; 3D-Bohrung = wahrscheinlich")
def _():
    assert kr.rolle(dict(art="Ende A", form="komplex", fase=True, schnittlaenge=100))["stufe"] == kr.PROBLEMATISCH
    r = kr.rolle(dict(art="Bohrung", z=5, durchmesser=2, schnittlaenge=6.3), wand=3)
    assert r["stufe"] == kr.PROBLEMATISCH and "kleiner als die Wand" in r["grund"], r
    r = kr.rolle(dict(art="Sonderkontur", z=5, waende=["0°", "90°"], schnittlaenge=80))
    assert r["rolle"] == kr.FREIFORM and r["stufe"] == kr.PROBLEMATISCH, r
    assert kr.rolle(dict(art="Kontur", z=5, schnittlaenge=80))["rolle"] == kr.FREIFORM
    assert kr.rolle(dict(art="Bohrung", z=5, durchmesser=10, schraeg=12, schnittlaenge=33))["stufe"] == \
        kr.WAHRSCHEINLICH
    assert kr.rolle(dict(art="Bohrung", z=5, durchmesser=10, schnittlaenge=31.4), sicher=False)["stufe"] == \
        kr.WAHRSCHEINLICH
    assert kr.rolle(dict(art="Ende B", form="komplex", schnittlaenge=90, kontur_erkannt=dict(kontur="V")))[
        "stufe"] == kr.WAHRSCHEINLICH


@fall("Zusammenfassung: zu prüfen sind Stufe 3 und 4, Konturen ohne Schnitt zählen nicht")
def _():
    b = kr.bewerten([dict(art="Ende A", form="gerade", schnittlaenge=200, z=0),
                     dict(art="Gravur", durchgehend=False, schnittlaenge=30),
                     dict(art="Kontur", z=5, schnittlaenge=80), dict(art="Bohrung", schnittlaenge=0)])
    z = kr.zusammenfassung(b)
    assert z["pruefen"] == [2, 3] and z["schlechteste"] == kr.NICHT_SICHER, z
    assert sum(z["rollen"].values()) == 3, z
    assert kr.text(b[0]).startswith("Anfangsschnitt · 1 eindeutig"), kr.text(b[0])


@fall("Importanalyse: Merkmale tragen Rolle und Schneidbarkeit")
def _():
    from rohrlaser import bauteil_analyse as ba
    t = teile["R06_QR60x3_Durchbrueche"][0]
    m = dict(profilform=t.profilform, wandstaerke=t.wandstaerke, konturen_liste=json.dumps(t.konturen_liste))
    liste = [x for x in ba.merkmale(m) if x.get("rolle")]
    assert [x["rolle"] for x in liste].count(kr.DURCHBRUCH) == 2, [x["rolle"] for x in liste]
    assert all(x["schneidbar"] == 1 and x["rolle_grund"] for x in liste), liste


print(f"\n{'Alle Prüfungen bestanden' if not fehler else f'{fehler} Fehler'}")
sys.exit(1 if fehler else 0)
