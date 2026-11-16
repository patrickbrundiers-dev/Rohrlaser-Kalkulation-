"""STEP-Prüfsammlung (Optimierungsplan 04.11.2026, C2): echte STEP-Dateien aus dem Betrieb mit festgehaltenen,
geprüften Werten (tests/step_sammlung/X.step + X.soll.json, siehe LIESMICH.txt). Jede Datei wird neu gemessen und je
Körper mit den Sollwerten verglichen: Art, Profilform, Profil, Maße, Länge, Schneidweg, Anzahl und Lage der Konturen.
Ohne Dateien prüft der Test nur sich selbst (mit einem Teil aus tests/step_anbau).

Aufruf: python tests/test_step_sammlung.py                     alle Dateien prüfen
        python tests/test_step_sammlung.py --festhalten X.step  Sollwerte aus der heutigen Messung schreiben
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import step_messen  # noqa: E402

ORDNER = HIER / "step_sammlung"
TEXT = ("profilform", "profil_id_vorschlag", "bauteiltyp", "pruefstatus")
ZAHL = {"abm_a": 0.05, "abm_b": 0.05, "wandstaerke": 0.05, "laenge": 0.1, "konturen": 0, "innen": 0.1,
        "schneidweg_rel": 0.005}
LAGE_MM = 0.1           # Lage einer Kontur entlang der Achse bzw. um das Profil


def _zahl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _konturen(m):
    """Konturen als [(Art, Form, z, u)] sortiert (aus konturen_liste; z entlang der Achse, u um das Profil)."""
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except ValueError:
        return []
    out = []
    for k in liste if isinstance(liste, list) else ():
        if isinstance(k, dict):
            out.append((str(k.get("art") or ""), str(k.get("form") or ""), round(float(k.get("z") or 0), 2),
                        round(float(k.get("u") or 0), 2)))
    return sorted(out)


def messen(pfad):
    netze = Path(tempfile.mkdtemp())
    try:
        zeilen = [dict(zip(step_messen.SPALTEN, z)) for z in step_messen.zeilen(Path(pfad), netze)]
    finally:
        shutil.rmtree(netze, ignore_errors=True)
    return zeilen


def werte(m):
    """Die geprüften Werte eines Körpers."""
    w = {k: m.get(k) or "" for k in TEXT}
    for k in ("abm_a", "abm_b", "wandstaerke", "laenge", "konturen", "innen", "schneidweg"):
        w[k] = _zahl(m.get(k))
    w["fehler"] = m.get("fehler") or ""
    w["konturen_lage"] = _konturen(m)
    return w


def festhalten(pfad):
    soll = {str(m.get("koerper")): werte(m) for m in messen(pfad)}
    ziel = Path(pfad).with_suffix(".soll.json")
    ziel.write_text(json.dumps(dict(datei=Path(pfad).name, koerper=soll), indent=1, ensure_ascii=False),
                    encoding="utf-8")
    return ziel


def vergleichen(pfad, soll_datei=None):
    """Abweichungen der heutigen Messung gegen X.soll.json: Liste von Texten (leer = alles gleich)."""
    soll = json.loads(Path(soll_datei or Path(pfad).with_suffix(".soll.json")).read_text(encoding="utf-8"))["koerper"]
    ist = {str(m.get("koerper")): werte(m) for m in messen(pfad)}
    out = []
    for k in sorted(set(soll) | set(ist), key=lambda x: (len(x), x)):
        s, i = soll.get(k), ist.get(k)
        if s is None or i is None:
            out.append(f"Körper {k}: {'neu' if s is None else 'fehlt'}")
            continue
        for f in TEXT + ("fehler",):
            if (s.get(f) or "") != (i.get(f) or ""):
                out.append(f"Körper {k} {f}: soll {s.get(f)!r}, ist {i.get(f)!r}")
        for f, tol in ZAHL.items():
            if f == "schneidweg_rel":
                a, b = s.get("schneidweg"), i.get("schneidweg")
                if (a is None) != (b is None) or (a and abs(b - a) > tol * abs(a)):
                    out.append(f"Körper {k} schneidweg: soll {a}, ist {b}")
                continue
            a, b = s.get(f), i.get(f)
            if (a is None) != (b is None) or (a is not None and abs(b - a) > tol + 1e-9):
                out.append(f"Körper {k} {f}: soll {a}, ist {b}")
        ks, ki = [tuple(x) for x in s.get("konturen_lage") or ()], i.get("konturen_lage") or []
        if len(ks) != len(ki) or any(a[:2] != tuple(b[:2]) or abs(a[2] - b[2]) > LAGE_MM or abs(a[3] - b[3]) > LAGE_MM
                                     for a, b in zip(ks, ki)):
            out.append(f"Körper {k} Konturen: soll {ks}, ist {ki}")
    return out


def main(argv):
    if argv[:1] == ["--festhalten"]:
        for p in argv[1:]:
            print("geschrieben:", festhalten(p))
        return 0
    rot = 0
    # Selbstprüfung: festhalten, vergleichen (gleich), verfälschen (Abweichung erkannt)
    tmp = Path(tempfile.mkdtemp())
    probe = tmp / "probe.step"
    shutil.copy(HIER / "step_anbau" / "A06_RE60x40x3_Bohrungen_ohne_Anbau.step", probe)
    soll = festhalten(probe)
    assert vergleichen(probe) == [], vergleichen(probe)
    d = json.loads(soll.read_text(encoding="utf-8"))
    k0 = next(iter(d["koerper"]))
    d["koerper"][k0]["laenge"] += 1
    d["koerper"][k0]["profil_id_vorschlag"] = "RE 60x40x4"
    if d["koerper"][k0]["konturen_lage"]:
        d["koerper"][k0]["konturen_lage"][-1][2] += 1
    soll.write_text(json.dumps(d), encoding="utf-8")
    abw = vergleichen(probe)
    assert any("laenge" in a for a in abw) and any("profil_id_vorschlag" in a for a in abw), abw
    print("OK     Selbstprüfung: gleiche Messung grün, Länge/Profil/Konturlage verändert = rot")
    dateien = sorted(ORDNER.glob("*.step")) + sorted(ORDNER.glob("*.stp"))
    for p in dateien:
        if not p.with_suffix(".soll.json").exists():
            print(f"FEHLER {p.name}: keine Sollwerte (--festhalten)")
            rot += 1
            continue
        abw = vergleichen(p)
        print(("OK    " if not abw else "FEHLER") + f" {p.name}" + "".join(f"\n        {a}" for a in abw))
        rot += bool(abw)
    print(f"{len(dateien)} Datei(en) der Prüfsammlung" + (" (noch keine echten Dateien)" if not dateien else ""))
    print("Alle Prüfungen STEP-Sammlung bestanden." if not rot else f"{rot} Datei(en) weichen ab.")
    return 1 if rot else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
