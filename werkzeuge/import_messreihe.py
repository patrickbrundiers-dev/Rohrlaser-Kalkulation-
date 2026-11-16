"""Messreihe „Import in den Editor“ an echten Baugruppen (Patrick 10.11.2026, Plan E6): jede STEP-Datei eines Ordners
messen, übernehmen (ohne Prüfdialog, wie ein Import ohne Anhaken) und das Modell des Editors gegen die STEP legen
(step_gegenprobe). Zwei Kennzahlen zeigen, wie gut der Import ist:

- Rohre/Profile, die ohne Anhaken nicht übernommen werden (unsichere Erkennung)
- verglichene Rohre/Profile, deren Editor-Modell mehr als 0,1 mm neben der STEP liegt

Die Baugruppen selbst liegen nicht im Repository (Kundendateien); der Lauf dauert je nach Größe Minuten bis eine
halbe Stunde je Datei. Vor einem Sammel-Update laufen lassen und mit dem letzten Stand vergleichen.

Aufruf:
    python werkzeuge/import_messreihe.py ORDNER_MIT_STEP ERGEBNIS_ORDNER [--zeitlimit 120]
    python werkzeuge/import_messreihe.py --vergleich ERGEBNIS_ALT ERGEBNIS_NEU

Je Datei entsteht ERGEBNIS_ORDNER/<Name>.json (Körper mit Art, Prüfstatus, Hinweisen; Positionen mit Abweichung);
am Ende steht die Zusammenfassung auf der Ausgabe und in ERGEBNIS_ORDNER/zusammenfassung.json.
"""
import argparse
import collections
import json
import os
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(WURZEL / "programm"), str(WURZEL / "programm" / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROFILE = ("Quadratrohr", "Rechteckrohr", "Rundrohr", "L-Profil", "U-Profil", "C-Profil", "Flachstahl")
GRENZE = 0.1


def datei_messen(datei, zeitlimit):
    """Eine Datei messen und übernehmen; Ergebnis dict(datei, messzeit, koerper=[…], positionen=[…])."""
    import step_messen
    from rohrlaser import step
    from rohrlaser.datenbank import Datenbank
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        step_messen.main(["--ausgabe", str(tmp / "r.csv"), "--netze", str(tmp), "--flachstahl-bis", "0",
                          "--zeitlimit", str(zeitlimit), str(datei)])
        messzeit = time.time() - t0
        ms = step.lade_netze(step.lies_messwerte(tmp / "r.csv"), tmp)
        db = Datenbank(tmp / "rohrlaser.db")
        k = db.kontext()
        koerper = [{x: v for x, v in m.items() if not x.startswith("_") and len(str(v)) < 400} for m in ms]
        erg = step.uebernehmen(ms, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True, d3=True,
                               zukauf_liste=[])
        positionen = [{x: v for x, v in p.items() if not x.startswith("_netz") and len(str(v)) < 300}
                      for p in erg["positionen"]]
    return dict(datei=datei.name, messzeit=round(messzeit), koerper=koerper, positionen=positionen)


def kennzahlen(ergebnis):
    """Kennzahlen einer Datei (dict)."""
    c = collections.Counter(koerper=len(ergebnis["koerper"]), positionen=len(ergebnis["positionen"]))
    artikel = {p.get("artikel") for p in ergebnis["positionen"]}
    for m in ergebnis["koerper"]:
        c["pruefen"] += m.get("pruefstatus") == "prüfen"
        if m.get("profilform") in PROFILE:
            c["profile"] += 1
            c["nicht_uebernommen"] += m.get("artikel") not in artikel
    for p in ergebnis["positionen"]:
        if p.get("_step_abweichung") is not None:
            c["verglichen"] += 1
            c["daneben"] += p["_step_abweichung"] > GRENZE
    return dict(c)


SPALTEN = ("koerper", "profile", "nicht_uebernommen", "pruefen", "verglichen", "daneben")


def tabelle(zeilen):
    kopf = f"{'Datei':32s}" + "".join(f"{s:>19s}" for s in SPALTEN)
    out = [kopf, "-" * len(kopf)]
    summe = collections.Counter()
    for name, kz in zeilen:
        summe.update({s: kz.get(s, 0) for s in SPALTEN})
        out.append(f"{name[:32]:32s}" + "".join(f"{kz.get(s, 0):19d}" for s in SPALTEN))
    out.append(f"{'Summe':32s}" + "".join(f"{summe[s]:19d}" for s in SPALTEN))
    return "\n".join(out), dict(summe)


def lesen(ordner):
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(ordner).glob("*.json"))
            if f.name != "zusammenfassung.json"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ordner", help="Ordner mit STEP-Dateien (bzw. mit --vergleich: Ergebnis alt)")
    ap.add_argument("ergebnis", help="Ordner für die Ergebnisse (bzw. mit --vergleich: Ergebnis neu)")
    ap.add_argument("--zeitlimit", type=float, default=120, help="Sekunden je Körper")
    ap.add_argument("--vergleich", action="store_true", help="zwei Ergebnis-Ordner vergleichen")
    a = ap.parse_args(argv)
    if a.vergleich:
        alt, neu = lesen(a.ordner), lesen(a.ergebnis)
        gemeinsam = [n for n in alt if n in neu]
        for titel, quelle in (("ALT", alt), ("NEU", neu)):
            text, _ = tabelle([(n, kennzahlen(quelle[n])) for n in gemeinsam])
            print(titel + "\n" + text + "\n")
        return 0
    ziel = Path(a.ergebnis)
    ziel.mkdir(parents=True, exist_ok=True)
    dateien = sorted(f for f in Path(a.ordner).iterdir() if f.suffix.lower() in (".step", ".stp", ".igs", ".iges"))
    zeilen = []
    for f in dateien:
        aus = ziel / (f.stem + ".json")
        if aus.exists():        # schon gemessen (Lauf fortsetzen)
            erg = json.loads(aus.read_text(encoding="utf-8"))
        else:
            erg = datei_messen(f, a.zeitlimit)
            aus.write_text(json.dumps(erg, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        zeilen.append((f.stem, kennzahlen(erg)))
        print(f"{f.name}: {zeilen[-1][1]}", flush=True)
    text, summe = tabelle(zeilen)
    print("\n" + text)
    (ziel / "zusammenfassung.json").write_text(json.dumps(dict(dateien=dict(zeilen), summe=summe), ensure_ascii=False,
                                                          indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
