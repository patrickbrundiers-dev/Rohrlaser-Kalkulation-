"""Vergleicht zwei Messwert-Dateien von tools/step_messen.py (z. B. Python gegen STEP-Import.exe).

Aufruf: python tests/vergleiche_messung.py REFERENZ.txt PRUEFLING.txt
"""
import sys


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [z.rstrip("\n").split("\t") for z in f if z.strip()]


def zahl(s):
    try:
        return float(s)
    except ValueError:
        return None


def main(ref, neu):
    a, b = lies(ref), lies(neu)
    assert a[0] == b[0], f"Spalten verschieden: {a[0]} / {b[0]}"
    assert len(a) == len(b), f"{len(a) - 1} Zeilen gegen {len(b) - 1}"
    for za, zb in zip(a[1:], b[1:]):
        for name, x, y in zip(a[0], za, zb):
            if name in ("bohrungen", "innen_liste"):
                x = [[zahl(v) for v in t.split(":")] for t in x.split("|") if t]
                y = [[zahl(v) for v in t.split(":")] for t in y.split("|") if t]
                ok = len(x) == len(y) and all(abs(p - q) < 1e-6 for s, t in zip(x, y) for p, q in zip(s, t))
            elif zahl(x) is not None and zahl(y) is not None:
                ok = abs(zahl(x) - zahl(y)) < 1e-6
            else:
                ok = x == y
            assert ok, f"{za[0]} {name}: {x!r} gegen {y!r}"
    print(f"OK: {len(a) - 1} Messzeilen gleich")


if __name__ == "__main__":
    main(*sys.argv[1:3])
