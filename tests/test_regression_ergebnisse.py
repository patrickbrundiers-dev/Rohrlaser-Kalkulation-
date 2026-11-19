"""Regressionstest der Rechenergebnisse (Großes System-Update, Patrick 19.11.2026: „Vergleich alter und neuer
Berechnungsergebnisse, identische Eingaben müssen identische Ergebnisse liefern, automatisierter Regressionstest vor
jedem Release“).

Gerechnet werden feste Angebote auf dem Weg des Programms (Datenbank mit Beispiel-Stammdaten, Positionen anlegen,
optimieren, Ergebnis speichern, kalkulieren):
- die Abnahme-Angebote (tests/abnahme_angebote.py: Geländer, Gestell, Edelstahl, Gehrungen, zu lange Teile …),
- Rohre mit Konturen und Lage auf den Beispielmaschinen mit Dynamik (Schneidfolge, Verfahrwege, Ecken, Gravur),
- dieselben Rohre mit Staffeln 1 / 10 / 100.
Jedes Ergebnis (Summen und alle Zahlen je Zeile, auf 6 Stellen nach dem Komma) wird mit dem gespeicherten Stand
tests/daten/regression_ergebnisse.json verglichen. Zusätzlich wird jedes Angebot zweimal gerechnet (einmal mit
leeren Merkern): beide Läufe müssen bitgleich sein.

Weicht ein Wert ab, zeigt der Test die ersten Unterschiede. Ist die Änderung fachlich gewollt (neue Formel,
Fehlerbehebung), den Stand bewusst neu schreiben und im Pull Request begründen:
  python tests/test_regression_ergebnisse.py --neu

Aufruf: python tests/test_regression_ergebnisse.py [--neu]
"""
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from abnahme_angebote import ANGEBOTE, programm_positionen  # noqa: E402
from rohrlaser import dauermerker, dynamik, rechenmerker, rechnen, schneidweg  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

STAND = HIER / "daten" / "regression_ergebnisse.json"
STELLEN = 6

bohr = lambda d, n, x=None, seite=None: dict(art="Bohrung", d=d, anzahl=n, **({"x": x} if x is not None else {}),  # noqa: E731
                                            **({"seite": seite} if seite else {}))
KONTUR_ANGEBOTE = [
    dict(nummer="REG-K1", maschine="T11", positionen=[
        dict(pos=10, profil="RR 42,4x2,0", werkstoff="S235-10219", laenge=820, stueck=14,
             eingaben=dict(a=dict(winkel=0.0), b=dict(winkel=30.0),
                           konturen=[bohr(8.5, 1, 40), bohr(8.5, 1, 260), bohr(12, 1, 410), bohr(8.5, 1, 600),
                                     bohr(10, 1, 780)])),
        dict(pos=20, profil="QR 40x40x3", werkstoff="S235-10219", laenge=1450, stueck=6,
             eingaben=dict(a=dict(winkel=0.0), b=dict(winkel=0.0),
                           konturen=[dict(art="Rechteck", b=20, h=15, r=2, anzahl=1, x=120, seite="oben"),
                                     dict(art="Langloch", l=30, b=10, anzahl=1, x=500, seite="vorne"),
                                     bohr(6.8, 1, 700, "oben"), bohr(6.8, 1, 900, "unten"),
                                     dict(art="Rechteck", b=60, h=25, r=2, anzahl=1, x=1200, seite="hinten"),
                                     dict(art="Gravur", anzahl=1, laenge=80.0)])),
    ]),
    dict(nummer="REG-K3", maschine="T11", positionen=[        # Sattel am Ende: Endabfall aus dem 3D-Netz
        dict(pos=10, profil="RR 42,4x2,0", werkstoff="S235-10219", laenge=640, stueck=12,
             eingaben=dict(a=dict(winkel=0.0, sattel=48.3), b=dict(winkel=0.0),
                           konturen=[bohr(8.5, 1, 120), bohr(8.5, 1, 320), bohr(8.5, 1, 520)])),
    ]),
    dict(nummer="REG-K2", maschine="LT7", positionen=[
        dict(pos=10, profil="RE 60x40x3", werkstoff="S235-10219", laenge=2240, stueck=9,
             eingaben=dict(a=dict(winkel=45.0), b=dict(winkel=45.0),
                           konturen=[bohr(9, 1, 100 + 190 * i, ("oben", "vorne", "unten")[i % 3]) for i in range(11)])),
        dict(pos=20, profil="QR 40x40x3", werkstoff="1.4301", laenge=388, stueck=40,
             eingaben=dict(a=dict(winkel=0.0), b=dict(winkel=0.0),
                           konturen=[bohr(5.5, 1, 30), bohr(5.5, 1, 190), bohr(5.5, 1, 350)])),
    ]),
]


def runden(w):
    if isinstance(w, bool) or w is None or isinstance(w, str):
        return w
    if isinstance(w, (int, float)):
        if isinstance(w, float) and not math.isfinite(w):
            return repr(w)
        r = round(float(w), STELLEN)
        return 0.0 if r == 0 else r
    if isinstance(w, dict):
        return {str(k): runden(v) for k, v in sorted(w.items(), key=lambda kv: str(kv[0]))}
    if isinstance(w, (list, tuple)):
        return [runden(v) for v in w]
    return repr(type(w).__name__)


def zusammenfassen(zeilen, summen, erg):
    return dict(summen=runden(summen),
                zeilen=[runden({k: v for k, v in (z or {}).items() if isinstance(v, (int, float, str, type(None)))})
                        for z in zeilen],
                stangen=[dict(profil=s["profil"], stange=runden(s["stange"]),
                              teile=[(t["index"], runden(t["von"]), runden(t["bis"])) for t in s["teile"]])
                         for s in erg["stangen"]])


def abnahme_rechnen(angebot, db):
    aid = db.angebot_neu({n: angebot[n] for n in ("nummer", "kunde", "maschine", "stange")})
    for p in programm_positionen(angebot):
        db.position_neu(aid, p)
    return kalkulieren(db, aid)


def kontur_rechnen(angebot, db, staffel=None):
    k = db.kontext()
    aid = db.angebot_neu(dict(nummer=angebot["nummer"] + (f"-{staffel}" if staffel else ""), kunde="Regression",
                              maschine=angebot["maschine"], stange=6000))
    m = k.maschinen[angebot["maschine"]]
    for p in angebot["positionen"]:
        pr = dict(k.profile[p["profil"]], profil_id=p["profil"])
        r = schneidweg.rechnen(p["eingaben"], pr, rechnen.kontur_regel(m, pr["wand"]))
        assert not r["fehler"], r["fehler"]
        werte = dict(pos=p["pos"], artikel=f"{angebot['nummer']}-{p['pos']}", profil_id=p["profil"],
                     werkstoff_id=p["werkstoff"], laenge=p["laenge"], stueck=staffel or p["stueck"])
        werte.update(r["felder"], technik=json.dumps(dict(p["eingaben"], quelle=schneidweg.QUELLE)))
        db.position_neu(aid, werte)
    return kalkulieren(db, aid)


def kalkulieren(db, aid):
    kopf, pos = db.angebot(aid), db.positionen(aid)
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    if erg.get("neue_profile"):
        db.profile_anlegen(erg["neue_profile"])
    db.ergebnis_speichern(aid, erg)
    kopf = db.angebot(aid)
    e = rechnen.einstellungen_angebot(kopf, einst)
    zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
    return zusammenfassen(zeilen, summen, kopf["ergebnis"])


def merker_leeren():
    """Alle Merker des Programms leer: der zweite Lauf rechnet alles neu."""
    rechenmerker.alle_leeren()
    dynamik._FOLGE_MERK.clear()
    for name in ("_KALK_MERK",):
        m = getattr(rechnen, name, None)
        if m is not None:
            m.leeren()


def alle_rechnen():
    tmp = Path(tempfile.mkdtemp())
    dauermerker.einrichten(tmp / dauermerker.ORDNER)
    db = Datenbank(tmp / "regression.db")
    out = {}
    for a in ANGEBOTE:
        out["Abnahme " + a["nummer"]] = abnahme_rechnen(a, db)
    for a in KONTUR_ANGEBOTE:
        out["Konturen " + a["nummer"]] = kontur_rechnen(a, db)
        for st in (1, 10, 100):
            out[f"Konturen {a['nummer']} Staffel {st}"] = kontur_rechnen(a, db, st)
    db.schliessen()
    return out


def unterschiede(alt, neu, pfad="", out=None):
    out = [] if out is None else out
    if type(alt) is not type(neu):
        out.append(f"{pfad}: {alt!r} → {neu!r}")
    elif isinstance(alt, dict):
        for k in sorted(set(alt) | set(neu)):
            if k not in alt or k not in neu:
                out.append(f"{pfad}/{k}: {'fehlt jetzt' if k not in neu else 'neu'}")
            else:
                unterschiede(alt[k], neu[k], f"{pfad}/{k}", out)
    elif isinstance(alt, list):
        if len(alt) != len(neu):
            out.append(f"{pfad}: {len(alt)} → {len(neu)} Einträge")
        for i, (x, y) in enumerate(zip(alt, neu)):
            unterschiede(x, y, f"{pfad}[{i}]", out)
    elif alt != neu:
        out.append(f"{pfad}: {alt!r} → {neu!r}")
    return out


def main():
    neu_schreiben = "--neu" in sys.argv
    aufrufe = [0]
    orig = dynamik._folge_rechnen

    def zaehlend(*a, **kw):
        aufrufe[0] += 1
        return orig(*a, **kw)
    dynamik._folge_rechnen = zaehlend
    try:
        erster = alle_rechnen()
        assert aufrufe[0] > 0, "Regression: die Konturen-Angebote rechnen keine Schneidfolge (Testdaten prüfen)"
        merker_leeren()
        zweiter = alle_rechnen()
    finally:
        dynamik._folge_rechnen = orig
    d = unterschiede(erster, zweiter)
    assert not d, "Gleiche Eingaben, anderes Ergebnis (zweiter Lauf mit leeren Merkern):\n" + "\n".join(d[:20])
    print("OK     Zweimal gerechnet (mit leeren Merkern und neuem Rechenmerker): bitgleich,",
          len(erster), "Angebote")
    if neu_schreiben or not STAND.exists():
        STAND.parent.mkdir(parents=True, exist_ok=True)
        STAND.write_text(json.dumps(erster, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("Stand neu geschrieben:", STAND)
        return
    alt = json.loads(STAND.read_text(encoding="utf-8"))
    d = unterschiede(alt, json.loads(json.dumps(erster)))
    assert not d, (f"{len(d)} Rechenergebnisse weichen vom gespeicherten Stand ab:\n" + "\n".join(d[:25])
                   + "\n\nIst die Änderung fachlich gewollt? Dann: python tests/test_regression_ergebnisse.py --neu "
                     "und im Pull Request begründen.")
    print("OK     Alle", len(erster), "Angebote rechnen wie im gespeicherten Stand (Summen, Zeilen, Stangen)")


if __name__ == "__main__":
    main()
