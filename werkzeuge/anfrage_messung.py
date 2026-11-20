"""Messwerte der Anfrage-Erkennung (Patrick 20.11.2026, Plan K11). Nur lesen, ändert nichts.

Aufruf:
  python werkzeuge/anfrage_messung.py                  Mail-Art an den festen Beispielen (rohrlaser.anfrage_messung)
  python werkzeuge/anfrage_messung.py AKTEN-ORDNER     dazu Kennzahlen aus dem Anfragen-Ordner (Korrekturen, Phasen,
                                                       Kunde, Abruf, gelerntes Modell)
  … --json                                             Ergebnis als JSON
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import anfrage_messung as m  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ordner", nargs="?", help="Anfragen-Ordner (gemeinsamer Ordner der Akten)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    k = m.korpus_messen()
    akten = m.akten_messen(ak.OrdnerAblage(a.ordner, "MESSUNG")) if a.ordner else None
    if a.json:
        print(json.dumps(dict(korpus=k, akten=akten), ensure_ascii=False, indent=1, default=str))
    else:
        print(m.bericht(k, akten))
    return 0 if k["quote"] is not None and k["quote"] >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
