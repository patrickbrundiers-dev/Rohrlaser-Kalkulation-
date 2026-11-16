"""Zeitbild in 7 Zeitarten (Plan X2, Patrick 12.11.2026): Gliederung ohne geänderte Zahl, Schneidzeit von Hand,
Dynamik als „Bewegung“, „nicht berücksichtigt“ bei leerem Feld, Summen über das Angebot. Die Summenprobe gegen
echte Kalkulationen steht in test_referenz_kalkulation.py.

Aufruf: python tests/test_zeitbild.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))
from rohrlaser import zeitbild  # noqa: E402


def nahe(a, b, text):
    assert abs(a - b) < 1e-9, f"{text}: {a} statt {b}"
    print(f"OK     {text}")


def zeile(**w):
    z = dict(zeit_gross=10.0, zeit_mittel=2.0, zeit_klein=1.0, zeit_gravur=0.5, zeit_d3=0.0, zeit_ecken=0.8,
             zeit_doppel=0.0, zeit_anfahrweg=0.2, zeit_abfall=0.0, zeit_einstiche=3.0, zeit_anfahren=1.5,
             zeit_drehen=0.0, zeit_neben=2.0, zeit_messen=0.0, zeit_entnahme=0.0, zeit_extra=0.0, zeit_pruefung=0.0,
             einsparung=1.0, zeit_ruest_maschine=6.0, zeit_ruest_abm=9.0, zeit_stangenwechsel=4.0, stueck=10,
             einstechzeit=0.5, zeit_manuell="", zeit_dynamik="")
    z["laser_brutto"] = sum(z[n] for n in ("zeit_gross", "zeit_mittel", "zeit_klein", "zeit_gravur", "zeit_ecken",
                                           "zeit_anfahrweg", "zeit_einstiche", "zeit_anfahren", "zeit_neben"))
    z.update(w)
    z.setdefault("laser_netto", max(0.0, z["laser_brutto"] - z["einsparung"]) + z["zeit_extra"] + z["zeit_pruefung"])
    return z


def teil(b, art, name):
    a = next(x for x in b["arten"] if x["art"] == art)
    return next(t for t in a["teile"] if t["name"] == name)


def main():
    z = zeile()
    b = zeitbild.zeitbild(z)
    nahe(b["s"]["laser"], 10 + 2 + 1 + 0.5 + 0.8 + 0.2 - 1.0, "Laserbearbeitung mit Einsparung gemeinsamer Schnitt")
    nahe(b["s"]["einstich"], 3.0, "Einstich")
    nahe(b["s"]["positionieren"], 1.5, "Positionieren = Anfahren je Kontur ohne Dynamik")
    nahe(b["s"]["bewegung"], 0.0, "Bewegung 0 ohne Dynamik")
    nahe(b["s"]["neben"], 2.0, "Nebenzeit")
    nahe(b["s"]["ruesten"], 19.0, "Rüsten = Maschine + Abmessung + Stangenwechsel")
    nahe(sum(b["s"][a] for a in ("laser", "einstich", "positionieren", "bewegung", "neben")), z["laser_netto"],
         "Summe 1–5 = Laserzeit netto")
    nahe(b["belegung"], z["laser_netto"] + 19.0, "Maschinenbelegung = Summe 1–6")

    # Dynamik: Anfahren ist die Verfahrzeit der Dynamik und steht unter Bewegung, nicht doppelt unter Positionieren
    z = zeile(zeit_dynamik="ja", zeit_drehen=2.0)
    z["laser_brutto"] += 2.0
    z["laser_netto"] += 2.0
    b = zeitbild.zeitbild(z)
    nahe(b["s"]["bewegung"], 1.5, "Dynamik: Leerwege unter Bewegung")
    nahe(b["s"]["positionieren"], 2.0, "Dynamik: Positionieren nur noch Drehen je Seitenwechsel")
    nahe(sum(b["s"][a] for a in ("laser", "einstich", "positionieren", "bewegung", "neben")), z["laser_netto"],
         "Dynamik: Summe 1–5 = Laserzeit netto")

    # Schneidzeit von Hand ersetzt Laser bis Bewegung, Zusatz- und Prüfzeit bleiben Nebenzeit
    z = zeile(zeit_manuell="ja", zeit_extra=5.0, zeit_pruefung=3.0, laser_netto=30.0 + 5.0 + 3.0)
    b = zeitbild.zeitbild(z)
    nahe(b["s"]["laser"], 30.0, "von Hand: Schneidzeit als Laserbearbeitung")
    nahe(b["s"]["einstich"] + b["s"]["positionieren"] + b["s"]["bewegung"], 0.0, "von Hand: keine berechneten Anteile")
    nahe(b["s"]["neben"], 8.0, "von Hand: Zusatzzeit und Prüfzeit als Nebenzeit")
    nahe(b["belegung"] - b["s"]["ruesten"], 38.0, "von Hand: Summe 1–5 = Laserzeit netto")

    # nicht berücksichtigt: Feld leer und Anteil 0; bei gesetztem Feld „kommt nicht vor“; Richtwert nie „nicht ber.“
    z = zeile(zeit_neben=0.0)
    m = dict(zeit_kontur=1.5, zeit_drehen=None, zeit_teil=None, anfahrweg=2, ruestzeit=30, stangenwechsel=24)
    b = zeitbild.zeitbild(z, m, dict(ruesten_abmessung=15))
    assert teil(b, "neben", "Nebenzeit je Teil")["status"] == "nicht berücksichtigt"
    assert teil(b, "positionieren", "Drehen je Seitenwechsel")["status"] == "nicht berücksichtigt"
    assert teil(b, "neben", "Messzyklen")["status"] == "kommt nicht vor", "Messzyklus hat einen Richtwert"
    assert teil(b, "laser", "Anfahrweg")["status"] == "gerechnet"
    print("OK     Status gerechnet / nicht berücksichtigt / kommt nicht vor")
    nb = dict(zeitbild.nicht_beruecksichtigt([z, zeile()], m))
    assert "Drehen je Seitenwechsel" in nb and "Nebenzeit je Teil" not in nb, nb
    print("OK     nicht berücksichtigt nur, wenn in keiner Zeile gerechnet")

    # ohne Laserzeit (Zukaufteil, keine Schneiddaten): kein Zeitbild, Felder leer
    assert zeitbild.zeitbild(dict(laser_netto=None)) is None
    assert all(v is None for v in zeitbild.felder(dict(laser_netto=None)).values())
    print("OK     ohne Laserzeit kein Zeitbild")
    s = zeitbild.summen([zeile(), zeile(stueck=5), dict(laser_netto=None)])
    nahe(s["ruesten"], 19.0 * 15, "Summe über das Angebot: Zeit je Teil × Stück")
    print("Zeitbild stimmt.")


if __name__ == "__main__":
    main()
