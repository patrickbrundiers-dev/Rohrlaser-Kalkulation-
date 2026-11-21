"""Geometrisch gleiche Körper ohne gemeinsame CAD-Vorlage nur einmal messen (Master-Auftrag Patrick 21.11.2026
„STEP-Import vollständig weiterentwickeln“: Geometrie-Hash, gleiche Teile nur einmal analysieren, Instanzen über
Transformationen).

Viele CAD-Programme schreiben gleiche Teile mit eigener Geometrie in die STEP-Datei (MASTER TOWER: 383 von 514
eigenen Körpern sind nur verschoben). Bisher wurde jeder davon voll gemessen. Jetzt übernimmt ein genau verschobener
Körper die Messung des ersten (wie eine verschobene Kopie derselben Vorlage, _instanzen).

- G1 erkannt: verschoben mit eingerechneter Lage und mit eigener Lage; nicht: gedreht, gespiegelt, 1 mm anders,
  andere Flächenreihenfolge ist egal nur, wenn sie gleich ist (sonst selbst messen)
- G2 Messwerte jedes Körpers wie einzeln gemessen (außer Name/Lage/Netzdatei); erlaubt ist nur Rechenrauschen ab der
  10. Stelle (eine einzeln gemessene Kopie hat z. B. 7,750000000001364 statt 7,75000000000135 mm) und die Lage z
  der Bohrungen in der Frästeil-Auswahl (Dateikoordinate, wie bei verschobenen Kopien derselben Vorlage)
- G3 verteilt auf mehrere Prozesse dasselbe; Schritte beim Lesen und Zahl der Kopien im Tempo-Protokoll

Aufruf: python tests/test_step_gleiche_geometrie.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_geometrie  # noqa: E402
from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from test_step_gedreht import messen  # noqa: E402
from test_step_wie_modell import box  # noqa: E402

ORT = {"artikel", "koerper", "bauteil", "pfad", "knoten", "netz", "hinweise", "meldungen", "anbauteile", "trennung",
       "verbund"}


def zahlen(text):
    """Text in Teile und Zahlen zerlegen: so vergleicht gleich() Zahl für Zahl, auch in JSON und Listen."""
    import re
    text = re.sub(r'\\"z\\":-?[\d.e-]+', "z", text)   # Lage einer Bohrung im Dreh-/Frästeil: Dateikoordinate
    return re.split(r"(-?\d+\.?\d*(?:e-?\d+)?)", text)


def gleich(a, b, tol=1e-9):
    ta, tb = zahlen(a), zahlen(b)
    if len(ta) != len(tb):
        return False
    for i, (x, y) in enumerate(zip(ta, tb)):
        if i % 2 == 0:
            if x != y:
                return False
        elif abs(float(x) - float(y)) > tol * max(1.0, abs(float(x))):
            return False
    return True


def rohr(bohrung_bei=150):
    return et.bohrung_quer(et.kastenrohr(40, 40, 3, 600, 4.5), 9, bohrung_bei)


def blech():
    b = box(0, 0, 0, 200, 100, 3)
    for x in (20, 180):
        b = et.cut(b, et.zylinder((x, 50, -1), (0, 0, 1), 9, 5))
    return b


def bewegt(shape, trsf):
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def verschiebung(x, y, z):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(x, y, z))
    return t


def main():
    fehler = 0
    tmp = Path(tempfile.mkdtemp())
    spiegel = gp_Trsf()
    spiegel.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
    d = Dokument()
    teile = [
        ("Holm", rohr(), lage()),                                             # 1 Vorbild
        ("Holm-2", bewegt(rohr(), verschiebung(0, 500, 0)), lage()),          # 2 verschoben, Lage eingerechnet
        ("Holm-3", rohr(), lage(0, 0, 800)),                                  # 3 eigene Geometrie, eigene Lage
        ("Holm-4", rohr(), lage(0, 900, 0, um_x=math.pi / 2)),               # 4 gedreht: selbst messen
        ("Holm-5", rohr(151), lage(0, 1800, 0)),                              # 5 Bohrung 1 mm anders: selbst messen
        ("Holm-6", bewegt(rohr(), spiegel), lage(-3000, 0, 0)),               # 6 gespiegelt: selbst messen
        ("Lasche", blech(), lage(3000, 0, 0)),                                # 7 Vorbild
        ("Lasche-2", bewegt(blech(), verschiebung(3000, 400, 50)), lage()),   # 8 verschoben
    ]
    d.baugruppe("Gestell", [(d.teil(n, s), loc) for n, s, loc in teile])
    pfad = tmp / "Gleich.step"
    d.schreiben(pfad)
    gel = step_geometrie.datei_lesen(pfad)
    namen = {i: gel.info["bauteile"].get(i, ("",))[0] for i in range(1, len(gel.koerper) + 1)}
    nr = {n: i for i, n in namen.items()}
    erwartet = {nr["Holm-2"]: nr["Holm"], nr["Holm-3"]: nr["Holm"], nr["Lasche-2"]: nr["Lasche"]}
    ist = {k: v for k, (v, _) in gel.gleich.items()}
    if ist != erwartet or gel.gedreht:
        fehler += 1
        print("FEHLER G1 gleiche Geometrie:", ist, "statt", erwartet, "gedreht", gel.gedreht, namen)
    else:
        v = gel.gleich[nr["Holm-2"]][1]
        if max(abs(a - b) for a, b in zip(v, (0, 500, 0))) > 1e-6:
            fehler += 1
            print("FEHLER G1 Verschiebung", v)
        print("OK     G1 verschobene Körper mit eigener Geometrie erkannt; gedreht, gespiegelt, 1 mm anders nicht")
    ph = gel.info.get("phasen") or {}
    if ph.get("gleich_geometrie") != 3 or not all(k in ph for k in ("lesen_s", "uebertragen_s", "kopien_s")):
        fehler += 1
        print("FEHLER G3 Schritte beim Lesen:", ph)

    einzeln = messen(pfad, tmp / "einzeln", {"STEP_MESSEN_EINZELN": "1"})
    neu = messen(pfad, tmp / "neu")
    verteilt = messen(pfad, tmp / "verteilt", {"STEP_MESSEN_TEILEN_AB": "2"}, "--prozesse", "3")
    for k, z in neu.items():
        for spalte, wert in z.items():
            if spalte not in ORT and not gleich(wert, einzeln[k][spalte], 1e-9):
                fehler += 1
                print(f"FEHLER G2 K{k} {namen.get(k)} {spalte}: {wert[:80]} statt {einzeln[k][spalte][:80]}")
            if spalte != "hinweise" and wert != verteilt[k][spalte]:
                fehler += 1
                print(f"FEHLER G3 K{k} verteilt anders: {spalte}")
    if not fehler:
        print(f"OK     G2 Messwerte aller {len(neu)} Körper wie einzeln gemessen (bis auf Rechenrauschen ab 1e-9)")
        print("OK     G3 verteilt auf 3 Prozesse dasselbe")
    for k in erwartet:          # 3D-Netz der Kopie liegt dort, wo der Körper in der Datei liegt
        n = json.loads((tmp / "neu" / neu[k]["netz"]).read_text(encoding="utf-8"))
        e = json.loads((tmp / "einzeln" / einzeln[k]["netz"]).read_text(encoding="utf-8"))
        if n.get("lage") != e.get("lage") and any(abs(a - b) > 1e-6 for a, b in zip(n.get("lage") or [],
                                                                                     e.get("lage") or [])):
            fehler += 1
            print(f"FEHLER G2 K{k} Einbaulage des 3D-Netzes: {n.get('lage')} statt {e.get('lage')}")
    import contextlib
    import io
    import step_messen
    aus = io.StringIO()
    with contextlib.redirect_stdout(aus):
        step_messen._zeiten_melden([("datei", "Gleich.step", None, 0.4, "geteilt")], 1.0, 2, {"Gleich.step": ph})
    z = json.loads(aus.getvalue().strip()[7:])
    sch = z["dateien"]["Gleich.step"].get("schritte") or {}
    if sch.get("gleich_geometrie") != 3 or "lesen_s" not in sch:
        fehler += 1
        print("FEHLER G3 Schritte im Tempo-Protokoll:", z)
    if [step_messen.phase_text(k, 8) for k in (0, 3, 9)] != ["Datei gelesen, Körper werden verteilt", "Körper messen",
                                                             "Baugruppe auswerten (Anbauteile, Verbund, Nähte)"]:
        fehler += 1
        print("FEHLER G3 Schritt im Fortschritt")
    if fehler:
        print(f"{fehler} Fehler")
        sys.exit(1)
    print("Alle Tests bestanden.")


if __name__ == "__main__":
    main()
