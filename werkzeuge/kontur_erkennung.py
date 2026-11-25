"""Erkennungsquote Endkonturen und Sonderkonturen (Patrick 25.11.2026 „Erkennung weiter verbessern und optimieren“,
„Sonderkonturen müssen auch erkannt werden“).

Liest STEP-Dateien wie das Programm (Messung, step.uebernehmen) und zählt je Ende und je Sonderkontur, was erkannt
wurde: Gerade, Gehrung, Gegenrohr, Konturart (endkontur.erkennen) bzw. Form (form_erkennung.erkennen), mit Abweichung
und Zeit. Mit --pruefsatz werden die erzeugten Prüfsätze (tests/erzeuge_endkonturen.py, tests/erzeuge_sonderkonturen.py)
mit ihren Sollwerten verglichen.

Aufruf (Datenbank: über werkzeuge/mit_pg.py, nicht als root):
  python werkzeuge/mit_pg.py -- python werkzeuge/kontur_erkennung.py --pruefsatz
  python werkzeuge/mit_pg.py -- python werkzeuge/kontur_erkennung.py ORDNER_MIT_STEPS [--csv DATEI]
"""
import argparse
import csv
import json
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
for p in (WURZEL / "programm", WURZEL / "programm" / "step_messung", WURZEL / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def einlesen(dateien):
    """STEP-Dateien wie der Import im Programm: [dict(artikel, a, b, konturen, zeit)] (Eingaben des Schneidweg-Rechners
    je Position)."""
    import step_messen
    from rohrlaser import schneidweg as sw, step
    from rohrlaser.datenbank import Datenbank
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        t0 = time.perf_counter()
        step_messen.main(["--ausgabe", str(tmp / "m.csv")] + [str(p) for p in dateien])
        t_mess = time.perf_counter() - t0
        ms = step.lies_messwerte(tmp / "m.csv")
        t0 = time.perf_counter()
        erg = step.uebernehmen(list(ms), [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 1,
                               neue_profile=True)
        t_ueb = time.perf_counter() - t0
        db.profile_anlegen(erg["profile"])
        profile = db.kontext().profile
        out = []
        for p in erg["positionen"]:
            e = sw.lesen(p.get("technik"))
            out.append(dict(artikel=p.get("artikel"), a=e.get("a") or {}, b=e.get("b") or {},
                            konturen=e.get("konturen") or [], position=p, profil=profile.get(p.get("profil_id"))))
        return out, dict(messung=t_mess, uebernahme=t_ueb)


def ende_art(e):
    """Kurzbezeichnung, als was ein Ende erkannt wurde."""
    from rohrlaser import endkontur
    if not e:
        return "gerade"
    if e.get("gegen"):
        return "Gegenrohr"
    if e.get("winkel"):
        return "Gehrung"
    er = e.get("kontur_erkannt") or {}
    if endkontur.lesen(er.get("kontur")):
        return er["kontur"]["typ"]
    return e.get("form") or "gerade"


def auswerten(teile):
    """Zeilen [dict(artikel, was, ergebnis, text, abweichung)] je komplexem Ende und je Sonderkontur."""
    from rohrlaser import endkontur
    zeilen = []
    for t in teile:
        for s in ("a", "b"):
            e = t[s]
            if not e or not (e.get("umriss") or e.get("winkel") or e.get("gegen")):
                continue
            er = e.get("kontur_erkannt") or {}
            zeilen.append(dict(artikel=t["artikel"], was=f"Ende {s.upper()}", ergebnis=ende_art(e),
                               text=endkontur.text(er.get("kontur")) if er else "",
                               abweichung=er.get("abweichung")))
        for k in t["konturen"]:
            if k.get("art") != "Sonderkontur":
                continue
            f = k.get("form_erkannt") or {}
            zeilen.append(dict(artikel=t["artikel"], was="Sonderkontur", ergebnis=f.get("typ") or "–",
                               text=f.get("text") or "", abweichung=f.get("abweichung")))
    return zeilen


def pruefsatz(ziel):
    """Prüfsätze erzeugen: {Artikel: Soll} – Endkontur: dict(typ, Maße) oder None (= Gehrung), Sonderkontur: (typ,
    Text-Anfang)."""
    import erzeuge_endkonturen as ee
    import erzeuge_sonderkonturen as es
    import erzeuge_testteile as et
    soll = {}
    for mod, unter in ((ee, "endkonturen"), (es, "sonderkonturen")):
        ordner = Path(ziel) / unter
        ordner.mkdir(parents=True, exist_ok=True)
        for n, (form, s) in mod.teile().items():
            et.schreibe(form, n, ordner)
            soll[n] = s
    return soll


def vergleich(teile, soll):
    """[(Artikel, ok, Text)] Ist gegen Soll der Prüfsätze."""
    from rohrlaser import endkontur
    out = []
    for t in teile:
        n = t["artikel"]
        if n not in soll:
            continue
        s = soll[n]
        if n.startswith("EK_"):
            e = t["b"]
            if s is None:
                ok = ende_art(e) == "Gehrung"
                out.append((n, ok, f"Ende B {ende_art(e)} (soll Gehrung)"))
                continue
            er = (e.get("kontur_erkannt") or {}).get("kontur") or {}
            ok = er.get("typ") == s["typ"] and _masse_ok(er, s)
            out.append((n, ok, f"Ende B {endkontur.text(er) or ende_art(e)} (soll {endkontur.text(s)}), "
                               f"± {(e.get('kontur_erkannt') or {}).get('abweichung')} mm"))
        else:
            ks = [k for k in t["konturen"] if k.get("art") == "Sonderkontur"]
            f = (ks[0].get("form_erkannt") or {}) if ks else {}
            typ, text = s
            ok = f.get("typ") == typ and (str(f.get("text") or "") + ", ").startswith(text + ", ")
            if not ks and typ == "Langloch":    # gerades Langloch: erkennt schon die Messung (Zeile Langloch)
                ok = any(k.get("art") == "Langloch" for k in t["konturen"])
                f = dict(text="Zeile Langloch")
            out.append((n, ok, f"{f.get('text') or 'nicht erkannt'} (soll {text})"))
    return out


def _masse_ok(ist, soll, tol=0.3):
    for k in ("tiefe", "breite"):
        if k in soll and abs(float(ist.get(k) or 0) - float(soll[k])) > tol:
            return False
    if "stufen" in soll:
        a, b = ist.get("stufen") or [], soll["stufen"]
        return len(a) == len(b) and all(abs(x[0] - y[0]) <= tol and abs(x[1] - y[1]) <= tol for x, y in zip(a, b))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ordner", nargs="?")
    ap.add_argument("--pruefsatz", action="store_true")
    ap.add_argument("--csv")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        soll = {}
        if args.pruefsatz:
            soll = pruefsatz(tmp)
            dateien = sorted(Path(tmp).rglob("*.step"))
        elif args.ordner:
            dateien = sorted(p for p in Path(args.ordner).rglob("*") if p.suffix.lower() in (".step", ".stp"))
        else:
            ap.print_help()
            return 2
        teile, zeit = einlesen(dateien)
    zeilen = auswerten(teile)
    for z in zeilen:
        print(f"{z['artikel'][:34]:34s} {z['was']:13s} {z['ergebnis']:14s} {z['text'][:60]:60s} "
              f"{'' if z['abweichung'] is None else z['abweichung']}")
    komplex = [z for z in zeilen if z["was"].startswith("Ende")]
    sonder = [z for z in zeilen if z["was"] == "Sonderkontur"]
    erk_e = sum(1 for z in komplex if z["text"] or z["ergebnis"] in ("Gehrung", "Gegenrohr"))
    erk_s = sum(1 for z in sonder if z["ergebnis"] not in ("–", "Freiform"))
    print(f"\nEnden (nicht gerade): {len(komplex)}, davon erkannt (Gehrung, Gegenrohr, Konturart) {erk_e}")
    print(f"Sonderkonturen: {len(sonder)}, davon Grundform {erk_s}, Freiform "
          f"{sum(1 for z in sonder if z['ergebnis'] == 'Freiform')}")
    print(f"Zeit: Messung {zeit['messung']:.1f} s, Übernahme (mit Erkennung) {zeit['uebernahme']:.1f} s")
    rot = 0
    if soll:
        print("\nPrüfsatz:")
        for n, ok, text in vergleich(teile, soll):
            rot += not ok
            print(f"  {'OK    ' if ok else 'FEHLER'} {n}: {text}")
        print(f"Prüfsatz: {len(soll) - rot} von {len(soll)} richtig")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(zeilen[0]) if zeilen else ["artikel"], delimiter=";")
            w.writeheader()
            w.writerows(zeilen)
        print("CSV:", args.csv)
    print(json.dumps(dict(enden=len(komplex), enden_erkannt=erk_e, sonder=len(sonder), sonder_grundform=erk_s,
                          pruefsatz_fehler=rot)))
    return 1 if rot else 0


if __name__ == "__main__":
    sys.exit(main())
