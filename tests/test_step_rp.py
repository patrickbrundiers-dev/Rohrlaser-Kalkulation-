"""Prüft die STEP-Erkennung der RP-Profile (Teile in tests/step_rp, erzeugt mit tests/erzeuge_rp_teile.py aus den
MegaCAD-Makros): Fingerabdruck aus der Bibliothek, Anschlag (Doppellage) ist keine ungleiche Wand und kein
Anbauteil, Lage im Raum, Gehrung, Bohrungen, Mehrkammerprofil, Verbundprofil (Kern nur gemeldet), Übernahme ins
Angebot mit einmal geschnittener Doppellage und Erkennung selbst geladener RP-Profile.

Aufruf: python tests/test_step_rp.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from step_geometrie import analysiere_datei  # noqa: E402
import step_messen  # noqa: E402

from rohrlaser import rp_profile, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

ORDNER = HIER / "step_rp"


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=0.15):
    return abs(a - b) <= tol


# ------------------------------------------------------------------ S1 Messung
teile = {f.stem: analysiere_datei(f) for f in sorted(ORDNER.glob("*.step"))}
SOLL = {   # Datei: Profil-ID, Breite, Höhe, Fläche, Länge
    "RP01_0106-35_L1000": ("RP 0106-35", 50, 34, 311.4, 1000),
    "RP02_0103-50_schraeg_L800": ("RP 0103-50", 80, 34, 429.7, 800),
    "RP03_0142-34_Gehrung45_L600": ("RP 0142-34", 49, 49, 367.6, 600),
    "RP04_0106-35_2xD8_L700": ("RP 0106-35", 50, 34, 311.4, 700),
}
for name, (pid, b, h, a, lg) in SOLL.items():
    t = teile[name][0]
    assert t.profilform == "RP-Profil" and t.normprofil == pid == t.profil_id_vorschlag, (name, t.profilform, t.normprofil)
    assert (t.abm_a, t.abm_b) == (b, h) and nah(t.flaeche, a, 0.5) and nah(t.laenge, lg, 0.01), (name, t.abm_a, t.flaeche)
    assert nah(t.wandstaerke, 2, 0.01) and t.sicherheit["wandstaerke"] == "sicher", (name, t.sicherheit)
    assert t.kammern == 1 and not t.anbauteile and not any("Anbau" in x or "nicht einheitlich" in x
                                                            for x in t.hinweise), (name, t.hinweise)
    assert "unsicher" not in t.sicherheit.values(), (name, t.sicherheit)
ok("S1 RP-Profile per Fingerabdruck erkannt (auch schräg im Raum), Doppellage keine ungleiche Wand, kein Anbauteil")

t = teile["RP01_0106-35_L1000"][0]
assert any("gleicher Querschnitt: RP 0143-20" in x for x in t.hinweise), t.hinweise
t = teile["RP04_0106-35_2xD8_L700"][0]
assert t.bohrungen == {8.0: 2} or sum(t.bohrungen.values()) == 2, t.bohrungen
t = teile["RP03_0142-34_Gehrung45_L600"][0]
assert t.ende_a_gerade and not t.ende_b_gerade and t.ende_b > t.ende_a * 1.05, (t.ende_a, t.ende_b)
ok("S2 gleiche Querschnitte im Hinweis, Bohrungen gezählt, Gehrung erkannt")

(t,) = teile["RP05_0106-35_Zwischensteg_L500"]
assert t.profilform == "Sonderprofil" and t.kammern == 2, (t.profilform, t.kammern)
assert any("Mehrkammerprofil (2 Kammern)" in x for x in t.hinweise), t.hinweise
assert t.ende_a > 162 + 10 and nah(t.ende_a, t.ende_b, 0.01), t.ende_a      # Zwischenwand (31 mm) mitgeschnitten
ok(f"S3 Mehrkammerprofil gemessen: 2 Kammern, Ende {t.ende_a:.1f} mm mit Zwischenwand")

rohr, kern = teile["RP06_0106-35_Verbund_L500"]
assert rohr.profilform == "RP-Profil" and rohr.verbund and any("Verbundprofil" in x for x in rohr.hinweise)
assert kern.profilform == "Verbundkern" and kern.verbund, (kern.profilform, kern.verbund)
assert rohr.pruefstatus == "prüfen"
ok("S4 Verbundprofil: Kern in der Kammer gemeldet, Rohr zum Prüfen")

# ------------------------------------------------------------------ S5 Übernahme ins Angebot
with tempfile.TemporaryDirectory() as tmp:
    aus = Path(tmp) / "m.txt"
    step_messen.main(["--ausgabe", str(aus)] + [str(ORDNER / f"{n}.step") for n in
                                                ("RP01_0106-35_L1000", "RP03_0142-34_Gehrung45_L600",
                                                 "RP06_0106-35_Verbund_L500")])
    mw = step.lies_messwerte(aus)
    assert [m["profilform"] for m in mw] == ["RP-Profil", "RP-Profil", "RP-Profil", "Verbundkern"], mw
    assert mw[0]["normprofil"] == "RP 0106-35" and mw[0]["kammern"] == "1" and nah(float(mw[0]["kontur_umfang"]), 162)
    db = Datenbank(Path(tmp) / "rohrlaser.db")
    k = db.kontext()
    erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
    pos = {p["artikel"]: p for p in erg["positionen"]}
    assert set(pos) == {"RP01_0106-35_L1000", "RP03_0142-34_Gehrung45_L600", "RP06_0106-35_Verbund_L500-K1"}, \
        erg["bericht"]
    p = pos["RP01_0106-35_L1000"]
    e = rp_profile.daten("RP 0106-35")
    assert p["profil_id"] == "RP 0106-35" and p["a_schnitt"] == p["b_schnitt"] == e["schnitt"], p
    assert nah(p["schneidweg"], 2 * e["schnitt"], 0.2), p["schneidweg"]
    g = pos["RP03_0142-34_Gehrung45_L600"]
    e = rp_profile.daten("RP 0142-34")
    assert g["a_schnitt"] == e["schnitt"] and nah(g["b_schnitt"], float(mw[1]["ende_b"]) * e["schnitt"] / e["umfang"],
                                                   0.1), g
    assert any("Verbundkern wird noch nicht kalkuliert" in z for z in erg["bericht"]), erg["bericht"]
    assert any("Anschlag (Doppellage) einmal geschnitten" in z for z in erg["bericht"]), erg["bericht"]
    assert not erg["profile"]           # Bibliotheksprofile stehen schon in den Stammdaten
    ok(f"S5 Übernahme: RP 0106-35 Schnitt je Ende {p['a_schnitt']} mm (gemessen 162), Gehrung anteilig, Kern "
       "nicht übernommen")

    # ------------------------------------------------------------------ S6 selbst geladenes RP-Profil
    m = dict(mw[0], profilform="Sonderprofil", normprofil="", profil_id_vorschlag="")
    eigen = dict(rp_profile.daten("RP 0106-35"), profil_id="RP 9999-35")
    rp_profile.eigene_setzen({"RP 9999-35": eigen})
    nur = {"RP 9999-35": rp_profile.stammdaten_zeile(eigen), "QR 40x40x3": k.profile.get("QR 40x40x3") or {}}
    assert step.finde_profil(m, nur) == "RP 9999-35"
    assert step.finde_profil(dict(m, flaeche="350"), nur) is None
    m2 = dict(mw[0], profilform="RP-Profil")             # Art im Prüfdialog auf RP-Profil gestellt
    assert step.finde_profil(m2, k.profile) == "RP 0106-35"
    rp_profile.eigene_setzen({})
    db.schliessen()
ok("S6 Sonderprofil findet selbst geladenes RP-Profil per Fingerabdruck, falsche Fläche nicht")
print("Alle STEP-RP-Prüfungen bestanden.")
