"""Prüft die Profilerkennung (Teile in tests/step_profile): U-, L-, C-Profil, Flachstahl, auch gedreht und mit
Walz-/Biegeradien, dazu Wandstärke an mehreren Stellen mit Erkennung ungleicher Wände.

Sollwerte aus den Konstruktionsmaßen in tests/erzeuge_testteile.py (Fläche: Polygon, Radien mit (1 − π/4)·r² je Ecke).
Aufruf: python tests/test_step_profile.py
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei  # noqa: E402

ORDNER = HIER / "step_profile"
k = 1 - math.pi / 4   # Flächenanteil, den ein Radius r an einer Ecke wegnimmt bzw. hinzufügt: k·r²


def poly(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


U = [(0, 0), (50, 0), (50, 30), (47, 30), (47, 3), (3, 3), (3, 30), (0, 30)]
C = [(0, 0), (50, 0), (50, 20), (47, 20), (47, 3), (3, 3), (3, 97), (47, 97), (47, 80), (50, 80), (50, 100), (0, 100)]
SOLL = {  # Form, A, B, Wand, Fläche, Länge, Sicherheit Wand, erwarteter Hinweis
    "P01_U50x30x3_L800": ("U-Profil", 50, 30, 3, poly(U), 800, "sicher", None),
    "P02_U50x30x3_Radien_L600": ("U-Profil", 50, 30, 3, poly(U) - 2 * k * 36 + 2 * k * 9, 600, "sicher", None),
    "P03_U60x30_Steg4_Flansch8_L500": ("U-Profil", 60, 30, 4, 60 * 30 - 44 * 26, 500, "wahrscheinlich",
                                       "Wandstärken verschieden"),
    "P04_L40x40x4_L800": ("L-Profil", 40, 40, 4, 40 * 4 + 36 * 4, 800, "sicher", None),
    "P05_L60x40x5_gedreht_L600": ("L-Profil", 60, 40, 5, 60 * 5 + 35 * 5, 600, "sicher", None),
    "P06_L50x50x5_Radien_L600": ("L-Profil", 50, 50, 5, 50 * 5 + 45 * 5 + k * 49 - 2 * k * 6.25, 600, "sicher", None),
    "P07_C100x50x20x3_L700": ("C-Profil", 100, 50, 3, poly(C) - 4 * k * 36 + 4 * k * 9, 700, "sicher",
                              "Abkantung 20.0 mm"),
    "P08_FL40x5_L800": ("Flachstahl", 40, 5, 0, 200, 800, "sicher", None),
    "P09_RR42-4_exzentrisch_L800": ("Rundrohr", 42.4, 0, 1.6, math.pi * (21.2 ** 2 - 19.2 ** 2), 800, "unsicher",
                                    "Wandstärke nicht einheitlich"),
    "P10_RE60x40_Wand2und3_L600": ("Rechteckrohr", 60, 40, 2, 2400 - 56 * 35, 600, "unsicher",
                                   "Wandstärke nicht einheitlich"),
}
OFFEN = ("U-Profil", "L-Profil", "C-Profil", "Flachstahl")


def nah(ist, soll, tol, was, name):
    assert abs(ist - soll) <= tol, f"{name}: {was} ist {ist:.3f}, soll {soll:.3f}"


fehler = 0
for name, (form, a, b, w, fl, lg, sich, hinweis) in SOLL.items():
    try:
        (t,) = analysiere_datei(ORDNER / f"{name}.step")
        assert t.profilform == form, f"{name}: Profilform {t.profilform!r}"
        nah(t.abm_a, a, 0.01, "Abm. A", name)
        nah(t.abm_b, b, 0.01, "Abm. B", name)
        nah(t.wandstaerke, w, 0.01, "Wandstärke", name)
        nah(t.flaeche, fl, 0.5, "Fläche", name)
        nah(t.laenge, lg, 0.01, "Länge", name)
        assert t.sicherheit.get("wandstaerke") == sich, f"{name}: Sicherheit Wand {t.sicherheit}"
        assert t.sicherheit.get("achse") == "sicher" and t.sicherheit.get("profil") == "sicher", t.sicherheit
        if hinweis:
            assert any(hinweis in h for h in t.hinweise), f"{name}: Hinweis fehlt: {t.hinweise}"
        if form in OFFEN:
            assert not any("noch nicht kalkuliert" in h for h in t.hinweise), f"{name}: {t.hinweise}"
            assert t.sicherheit.get("konturen") == "sicher", f"{name}: {t.sicherheit}"
            assert t.konturen_liste[0]["form"] == t.konturen_liste[1]["form"] == "gerade", t.konturen_liste[:2]
        if form not in ("Flachstahl",):
            assert len(t.wand_messungen) >= 6, f"{name}: nur {len(t.wand_messungen)} Wandmessungen"
            assert len({round(m[0], 1) for m in t.wand_messungen}) >= 2, f"{name}: Wand nur an einer Stelle der Länge"
        print(f"OK     {name}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {e}")

# Innenmaße der Hohlprofile
(t,) = analysiere_datei(HIER / "step" / "T04_RE60x40x3_Gehrung.step")
try:
    nah(t.innen_a, 54, 0.01, "Innen A", "T04")
    nah(t.innen_b, 34, 0.01, "Innen B", "T04")
    (t,) = analysiere_datei(HIER / "step" / "T01_RR42-4x2_L1250.step")
    nah(t.innen_a, 38.4, 0.01, "Innen Ø", "T01")
    assert t.sicherheit["wandstaerke"] == "sicher" and len(t.wand_messungen) >= 16, t.wand_messungen
    print("OK     Innenmaße und Wandmessungen T01/T04")
except AssertionError as e:
    fehler += 1
    print(f"FEHLER {e}")

# Programm: offene Profile werden gemeldet, aber (noch) nicht ins Angebot übernommen und nicht als Satz gruppiert
try:
    import os
    import tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(HIER.parent / "programm"))
    from rohrlaser import step  # noqa: E402
    from rohrlaser.datenbank import Datenbank  # noqa: E402
    sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
    import step_messen  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        aus = Path(tmp) / "m.txt"
        step_messen.main(["--ausgabe", str(aus), str(ORDNER / "P01_U50x30x3_L800.step"),
                          str(HIER / "step" / "T01_RR42-4x2_L1250.step"),
                          str(HIER / "step_referenz" / "REF13_T50x40x5_L600.step")])
        mw = step.lies_messwerte(aus)
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        assert step.gleiche_teile(mw) == {0: [0], 1: [1]}, step.gleiche_teile(mw)
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
        assert [p["artikel"] for p in erg["positionen"]] == ["P01_U50x30x3_L800", "T01_RR42-4x2_L1250"], \
            erg["positionen"]
        u = erg["positionen"][0]
        assert u["profil_id"] == "U 50x30x3" and abs(u["schneidweg"] - 2 * (50 + 60 - 3)) < 0.5, u
        # nicht erkanntes offenes Profil (T-Profil): ohne Schneidweg, darf nie als Position entstehen
        assert any("offenes Sonderprofil wird noch nicht kalkuliert" in z for z in erg["bericht"]), erg["bericht"]
        assert mw[0]["sicherheit"].startswith("achse=sicher") and mw[0]["wand_messungen"], mw[0]
    print("OK     Programm: U-Profil übernommen, offenes Sonderprofil gemeldet, nicht übernommen")
except AssertionError as e:
    fehler += 1
    print(f"FEHLER Programm: {e}")

sys.exit(1 if fehler else 0)
