"""Gleichheitsfälle für die Android-App: Eingaben und Ergebnisse des PC-Programms als Datei, die der Kotlin-Rechenkern
(android/kern) in seinen Tests nachrechnen muss – Stange für Stange gleich.

Aufruf:
    python tests/android_paritaet.py            prüft, ob die Datei zum aktuellen Python-Stand passt (Linux-Check)
    python tests/android_paritaet.py --schreiben schreibt sie neu (nach einer Änderung an der Rechnung)

Schlägt die Prüfung fehl, wurde die Rechnung im PC-Programm geändert: Datei neu schreiben und dieselbe Änderung im
Kotlin-Rechenkern nachziehen, bis die Android-Tests (Workflow Android) wieder grün sind.
"""
import json
import random
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import optimierung as opt  # noqa: E402
from rohrlaser.optimierung import FEST, FREI, UNBEKANNT, Gruppe, Teil  # noqa: E402

DATEI = HIER.parent / "android" / "kern" / "src" / "test" / "resources" / "optimierung_faelle.json"


def teile(n, laenge, a=True, b=True, zeile=13, **extra):
    return [Teil(zeile, 10, "A", i, laenge, a, b, 100, 100, **extra) for i in range(1, n + 1)]


def gruppe(tl, stange=1000, end=20, greif=80, kerf=0.3, abstand=2, querschnitt=()):
    g = Gruppe("P", "W", stange, end, greif, kerf, abstand, querschnitt=querschnitt)
    g.teile = tl
    return g


def faelle_einfach():
    """Feste Fälle aus tests/test_optimierung.py und Zufallsangebote mit geraden und schrägen Enden."""
    yield gruppe(teile(2, 449))
    yield gruppe(teile(2, 449, a=False, b=False))
    yield gruppe(teile(2, 449, a=False, b=True))
    yield gruppe(teile(1, 449, a=False, b=True, zeile=13) + teile(1, 449, a=True, b=False, zeile=14))
    yield gruppe(teile(1, 200, a=False, b=True, zeile=13) + teile(3, 150, zeile=14)
                 + teile(1, 200, a=True, b=False, zeile=15))
    rnd = random.Random(2210)
    for _ in range(45):
        stange = rnd.choice([3000, 6000, 6500])
        tl = []
        for z in range(rnd.randint(1, 6)):
            lang = rnd.random() < 0.15
            laenge = round(rnd.uniform(40, stange - 101), 1) if lang else round(rnd.uniform(40, 1900), 1)
            tl += teile(rnd.randint(1, 25), laenge, a=rnd.random() < 0.8, b=rnd.random() < 0.8, zeile=13 + z)
        yield gruppe(tl, stange, rnd.choice([10, 20]), rnd.choice([80, 120, 142]), rnd.choice([0.2, 0.3]),
                     rnd.choice([0, 2]))


def faelle_schwer():
    """Knappe Längen (knapp über Bruchteilen der Stange): Schnittmuster, exakte Suche und Suchgrenzen werden gebraucht."""
    rnd = random.Random(31)
    for lauf in range(14):
        stange = 6000
        nutz = stange - 142 - 10
        tl = []
        for z in range(rnd.randint(2, 5)):
            teiler = rnd.choice([2, 3, 4, 5, 7])
            laenge = round(nutz / teiler - rnd.uniform(-60, 25), 1)
            tl += teile(rnd.randint(2, 14 if lauf % 2 else 30), laenge, a=rnd.random() < 0.85, b=rnd.random() < 0.85,
                        zeile=13 + z)
        yield gruppe(tl, stange, 10, 142, 0.2, 2)


def faelle_gehrung():
    """Gehrungen zum Ineinanderlegen, Rechteck-, Quadrat- und Rundrohr, Drehung frei, fest (Naht) und unbekannt."""
    rnd = random.Random(4711)
    for lauf in range(30):
        art = rnd.choice(["RE", "QR", "RR"])
        q = ("Kasten", 60.0, 40.0) if art == "RE" else ("Kasten", 40.0, 40.0) if art == "QR" else ("Rund", 21.2)
        stange = rnd.choice([3000, 6000])
        tl = []
        for z in range(rnd.randint(1, 4)):
            a_geh = (float(rnd.choice([15, 30, 45])), float(rnd.choice([0, 90, 180, 270]))) if rnd.random() < 0.7 else None
            b_geh = (float(rnd.choice([15, 30, 45])), float(rnd.choice([0, 90, 180, 270]))) if rnd.random() < 0.7 else None
            drehung = rnd.choice([FREI, FREI, FEST, UNBEKANNT])
            naht = float(rnd.choice([0, 90, 180, 270])) if drehung == FEST else None
            tl += teile(rnd.randint(1, 8 if lauf % 3 else 20), round(rnd.uniform(150, 1400), 1),
                        a=a_geh is None, b=b_geh is None, zeile=13 + z,
                        a_gehrung=a_geh, b_gehrung=b_geh, drehung=drehung, naht=naht)
        yield gruppe(tl, stange, 10, 142, 0.2, rnd.choice([0, 2]), q)


def faelle_gehrung_knapp():
    """Gehrungen mit knappen Längen: keine Schranke der Schnittmuster, also exakte Suche bis zur Suchgrenze."""
    rnd = random.Random(2)
    for _ in range(12):
        tl = []
        for z in range(rnd.randint(2, 4)):
            geh = (float(rnd.choice([30, 45])), float(rnd.choice([0, 90])))
            tl += teile(rnd.randint(3, 12), round(5848 / rnd.choice([2, 3, 4]) - rnd.uniform(-40, 20), 1), a=False,
                        b=True, zeile=13 + z, a_gehrung=geh)
        yield gruppe(tl, 6000, 10, 142, 0.2, 2, ("Kasten", 60.0, 40.0))


def faelle_zuschnitt():
    rnd = random.Random(1200)
    for _ in range(8):
        tl = []
        for z in range(rnd.randint(1, 4)):
            tl += teile(rnd.randint(1, 12), round(rnd.uniform(200, 3000), 1), a=rnd.random() < 0.8,
                        b=rnd.random() < 0.8, zeile=13 + z)
        g = gruppe(tl, 6500, 10, 142, 0.2, 2)
        yield g, dict(lieferlaenge=12000.0, max_werkstueck=6500.0, saege=rnd.choice([3.0, 4.0]),
                      min_werkstueck=rnd.choice([0.0, 2500.0]), puffer=rnd.choice([0.0, 10.0]))


def teil_json(t):
    return dict(zeile=t.zeile, nr=t.nr, artikel=t.artikel, laenge=t.laenge, a_gerade=t.a_gerade,
                b_gerade=t.b_gerade, a_schnitt=t.a_schnitt, b_schnitt=t.b_schnitt,
                a_gehrung=list(t.a_gehrung) if t.a_gehrung else None,
                b_gehrung=list(t.b_gehrung) if t.b_gehrung else None, drehung=t.drehung, naht=t.naht)


def gruppe_json(g):
    return dict(profil=g.profil, werkstoff=g.werkstoff, stange=g.stange, endbeschnitt=g.endbeschnitt,
                greiferrest=g.greiferrest, kerf=g.kerf, abstand=g.abstand, querschnitt=list(g.querschnitt),
                teile=[teil_json(t) for t in g.teile])


def folge_json(f):
    return [[t.zeile, t.nr, d] for t, d in f]


def ergebnis(g):
    folgen = opt.optimiere(g)
    opt.pruefe([g], [folgen])
    return dict(folgen=[folge_json(f) for f in folgen], verbrauch=[opt.verbrauch(g, f) for f in folgen],
                bewiesen=g.bewiesen, schranke=g.schranke, untergrenze=opt.untergrenze(g),
                bewertung=opt.bewertung(g, len(folgen)), manuell=len(opt.manuell(g)),
                ohne_drehung=opt.ohne_drehung(g), gemeinsame_schnitte=[opt.gemeinsame_schnitte(f) for f in folgen],
                ineinander=[opt.gehrungen_ineinander(g, f) for f in folgen],
                ansicht=[opt.ansicht(g, f) for f in folgen])


def faelle():
    out = dict(optimierung=[], zuschnitt=[], profile=[])
    for g in [*faelle_einfach(), *faelle_schwer(), *faelle_gehrung(), *faelle_gehrung_knapp()]:
        eingabe = gruppe_json(g)
        out["optimierung"].append(dict(gruppe=eingabe, ergebnis=ergebnis(g)))
    for g, z in faelle_zuschnitt():
        eingabe = gruppe_json(g)
        st = opt.zuschnitt(g, **z)
        if st is not None:
            opt.pruefe_zuschnitt(g, st, z["lieferlaenge"], z["max_werkstueck"], z["saege"], z["min_werkstueck"])
        out["zuschnitt"].append(dict(gruppe=eingabe, **z, ergebnis=None if st is None else [
            [[laenge, folge_json(f)] for laenge, f in s] for s in st]))
    for form, a, b, wand, fl in [("Rundrohr", 42.4, None, 2.0, None), ("Quadratrohr", 40, None, 3, None),
                                 ("Rechteckrohr", 60, 40, 3, None), ("I-/H-Träger", 200, 100, 5.6, 2850),
                                 ("T-Profil", 50, 50, 6, 566), ("U-Profil", 100, 50, 6, 1350),
                                 ("Flachstahl", 50, None, 8, 400)]:
        out["profile"].append(dict(form=form, a=a, b=b, wand=wand, flaeche=fl, umfang=opt.umfang(form, a, b, wand, fl),
                                   schnittlaenge=opt.schnittlaenge(form, a, b, wand, fl)))
    return out


def main():
    text = json.dumps(faelle(), ensure_ascii=False, separators=(",", ":")) + "\n"
    if "--schreiben" in sys.argv:
        DATEI.parent.mkdir(parents=True, exist_ok=True)
        DATEI.write_text(text, encoding="utf-8")
        print(f"geschrieben: {DATEI} ({len(text) // 1024} KB)")
        return 0
    if not DATEI.exists() or DATEI.read_text(encoding="utf-8") != text:
        print("FEHLER: Die Rechnung des PC-Programms passt nicht mehr zu den Gleichheitsfällen der Android-App.\n"
              "  python tests/android_paritaet.py --schreiben\n"
              "ausführen und dieselbe Änderung im Kotlin-Rechenkern (android/kern) nachziehen.")
        return 1
    print("OK: Gleichheitsfälle der Android-App passen zur Rechnung des PC-Programms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
