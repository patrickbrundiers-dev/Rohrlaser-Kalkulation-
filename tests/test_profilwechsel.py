"""Prüft Profilwechsel im STEP-Import und 3D-Enden im Schneidweg-Rechner (Patrick 22.10.2026) sowie die Kalkulation
der RP-Profile (PR 3: Eckzeit, Anschlag mit den Schneiddaten der doppelten Wand, Maschine spannbar/Rüstzuschlag/Düse):
- P1 Schrägschnitt zweiachsig und 3D-Enden (Spitze aus zwei Ebenen, Ausklinkung auf Rundrohr) werden gemessen und
  vom Rechner für dasselbe Profil auf die gemessene Länge nachgerechnet
- P2 Rechner: zweiachsig von Hand (Höhe/Breite), Gesamtwinkel, Gehrung bleibt wie bisher
- P3 Profil im Prüfdialog geändert: WARNUNG mit STEP- und Profilwerten, Enden mit der gemessenen Form für das neue
  Profil gerechnet, Innenkonturen bleiben; der Rechner kommt mit den gespeicherten Eingaben auf dieselben Enden
- P4 nicht rechenbares Ende (komplex ohne Flächen): gemessene Länge + Hinweis
- K1 Eckzeit je Ecke, K2 Anschlag doppelt, K3 Einsparung gemeinsamer Schnitte, K4 Maschine nicht spannbar,
  K5 Rüstzuschlag je RP-Abmessung, K6 Düsenabstand

Aufruf: python tests/test_profilwechsel.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import rechnen, rp_profile, schneidweg as sw, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

ORDNER = HIER / "step_profilwechsel"


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=0.1):
    return abs(a - b) <= tol


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
aus = tmp / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(f) for f in sorted(ORDNER.glob("*.step"))])
mw = {m["artikel"]: m for m in step.lies_messwerte(aus)}
db = Datenbank(tmp / "rohrlaser.db")
for z in db.zeilen("profile"):          # die STEP-Testteile sind scharfkantig: Außenradius 0
    if z["form"] in ("Quadratrohr", "Rechteckrohr"):
        db.aendern("profile", z["id"], "r_aussen", 0)
k = db.kontext()


def ende_b(m):
    return next(d for d in json.loads(m["konturen_liste"]) if d.get("art") == "Ende B")


# ------------------------------------------------------------------ P1 Messung und Nachrechnen
re_, qr, rr = (mw[n] for n in ("PW01_RE60x40x3_schraeg20-10_L800", "PW02_QR40x3_Spitze30_L600",
                               "PW03_RR42-4x2_Ausklinkung60_L530"))
assert ende_b(re_)["form"] == "Schrägschnitt zweiachsig"
assert ende_b(qr)["form"] == ende_b(rr)["form"] == "komplex"
assert ende_b(qr)["huelle"] == "min" and [f[0] for f in ende_b(qr)["flaechen"]] == ["E", "E"]
assert [f[0] for f in ende_b(rr)["flaechen"]] == ["Z"]
for m, pid in ((re_, "RE 60x40x3"), (qr, "QR 40x40x3"), (rr, "RR 42,4x2,0")):
    e = step.rechner_eingaben(m, k.profile[pid]["form"], k.profile[pid]["a"], k.profile[pid]["b"])["b"]
    neu = sw.ende_neu(dict(k.profile[pid], profil_id=pid), e)
    assert neu and nah(neu[0], float(m["ende_b"]), 0.05), (pid, neu, m["ende_b"])
assert nah(sw.ende_3d(dict(k.profile["RR 42,4x2,0"]), ende_b(rr)["flaechen"], "min"), sw.sattel(42.4, 60), 0.05)
ok(f"P1 zweiachsig {re_['ende_b']} mm, Spitze {qr['ende_b']} mm, Ausklinkung {rr['ende_b']} mm aus den Flächen "
   "nachgerechnet")

# ------------------------------------------------------------------ P2 Rechner zweiachsig von Hand
re60 = dict(k.profile["RE 60x40x3"])
e = step.rechner_eingaben(re_, "Rechteckrohr", 60, 40)["b"]
assert e["achse"] == sw.ACHSE_ZWEI and nah(e["winkel_h"], 10, 0.05) and nah(e["winkel_b"], 20.28, 0.05), e
hand = dict(achse=sw.ACHSE_ZWEI, winkel_h=e["winkel_h"], winkel_b=e["winkel_b"],
            winkel=sw.gesamtwinkel(e["winkel_h"], e["winkel_b"]))
erg = sw.rechnen(dict(a={}, b=hand, konturen=[]), re60, (10, 50))
assert nah(erg["felder"]["b_schnitt"], float(re_["ende_b"]), 0.1) and erg["felder"]["b_gerade"] == "nein", erg["felder"]
assert nah(hand["winkel"], float(ende_b(re_)["gehrung"]), 0.05)
assert "Schrägschnitt 10" in erg["schritte"][1]["text"]
g45 = sw.ende(re60, 45, sw.ACHSEN[1])[0]
assert nah(g45, sw.ende(re60, 0, sw.ACHSE_ZWEI, None, (0, 45))[0], 1e-9)
ok(f"P2 Rechner zweiachsig {hand['winkel_h']:.2f}°/{hand['winkel_b']:.2f}° = {erg['felder']['b_schnitt']} mm, "
   f"Gesamtwinkel {hand['winkel']:.2f}°")

# ------------------------------------------------------------------ P3 Profil im Prüfdialog geändert
liste = [dict(re_, _profil="RE 120x60x4", _uebernehmen=True), dict(qr, _profil="RE 60x40x3", _uebernehmen=True),
         dict(rr, _profil="RR 48,3x2,6", _uebernehmen=True), dict(re_, artikel="gleich", _uebernehmen=True)]
erg = step.uebernehmen(liste, [], k, db.zeilen("gewinde"), k.maschinen["T03"], "S235-10219", 1, erneut=True)
pos = erg["positionen"]
b = {p["profil_id"]: p for p in pos}
txt = " | ".join(erg["bericht"])
assert "WARNUNG: STEP weicht vom gewählten Profil ab: STEP 60 × 40 × 3 mm" in txt and "Profil RE 120x60x4 120 × 60 × 4" in txt
p = pos[0]
soll = sw.ende(dict(k.profile["RE 120x60x4"]), 0, sw.ACHSE_ZWEI, None, (e["winkel_h"], e["winkel_b"]))[0]
assert p["profil_id"] == "RE 120x60x4" and nah(p["b_schnitt"], soll, 0.06) and nah(p["a_schnitt"], 360, 0.06), p
assert nah(p["schneidweg"], float(re_["schneidweg"]) + p["a_schnitt"] + p["b_schnitt"] - float(re_["ende_a"])
           - float(re_["ende_b"]), 0.15), p
p = pos[1]
soll = sw.ende_3d(dict(k.profile["RE 60x40x3"]), ende_b(qr)["flaechen"], "min")
assert nah(p["b_schnitt"], soll, 0.06) and nah(p["a_schnitt"], 200, 0.06) and soll > 200, (p, soll)
p = pos[2]
assert nah(p["b_schnitt"], sw.sattel(48.3, 60), 0.1) and nah(p["a_schnitt"], math.pi * 48.3, 0.06), p
assert pos[3]["a_schnitt"] == round(float(re_["ende_a"]), 1)       # Profil nicht geändert: gemessen
assert "Enden für Profil RE 120x60x4 neu gerechnet" in txt
for p in pos[:3]:          # der Rechner rechnet mit den gespeicherten Eingaben dieselben Enden
    r = sw.rechnen(sw.lesen(p["technik"]), dict(k.profile[p["profil_id"]]), (10, 50))
    assert nah(r["felder"]["a_schnitt"], p["a_schnitt"], 0.06) and nah(r["felder"]["b_schnitt"], p["b_schnitt"], 0.06), \
        (p["profil_id"], r["felder"], p)
    assert "für " + p["profil_id"] + " gerechnet" in r["schritte"][1]["text"], r["schritte"][1]["text"]
ok("P3 Profilwechsel: WARNUNG mit STEP- und Profilwerten, zweiachsig/Spitze/Ausklinkung für das neue Profil gerechnet, "
   "Rechner gleich")

# ------------------------------------------------------------------ P4 nicht rechenbar
e4 = dict(gemessen=150.0, form="komplex", messprofil=sw.messprofil_text("Quadratrohr", 40, 40, 3))
r = sw.rechnen(dict(a={}, b=e4, konturen=[]), re60, (10, 50))
assert r["felder"]["b_schnitt"] == 150.0 and any("nicht neu rechenbar" in h for h in r["hinweise"]), r["hinweise"]
assert step.enden_neu({}, dict(re60), dict(a={}, b=e4))["hinweise"][0].startswith("Endschnitt (komplex) nicht")
ok("P4 komplexes Ende ohne Flächen: gemessene Länge mit Hinweis")

# ------------------------------------------------------------------ K Kalkulation RP
fenster = Hauptfenster(db, tmp, stumm=True)
e = rp_profile.daten("RP 0106-35")
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T03"))
db.position_neu(a, dict(pos=10, artikel="R1", profil_id="RP 0106-35", werkstoff_id="S235-10219", laenge=900,
                        stueck=10, schneidweg=2 * e["schnitt"], einstiche=2, a_schnitt=e["schnitt"],
                        b_schnitt=e["schnitt"], a_gerade="ja", b_gerade="ja"))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()


def rechnung():
    s.neu_laden()
    z, su = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
    st = rechnen.status(s.positionen[0], rechnen.position_werte(s.positionen[0], s.kopf, s.k, s.tabellen),
                        s.kopf, s.k)
    return z[0], su, st


# ohne Eckzeit beginnen (seit 0.9.191 haben die Richtwerte eine Zeit je Ecke nach Wandstärke)
db.con.execute("UPDATE schneiddaten SET zeit_ecke=NULL WHERE maschinen_id='T03'")
db.con.commit()
z0, su0, st0 = rechnung()
assert z0["zeit_ecken"] == 0 and st0.startswith(("OK", "HINWEIS")), st0
v2 = rechnen.schneiddaten("T03", "S235-10219", 2, s.tabellen, "Stahl")["vorschub_gross"]
v4 = rechnen.schneiddaten("T03", "S235-10219", 4, s.tabellen, "Stahl")["vorschub_gross"]
assert nah(z0["zeit_doppel"], 60 * 2 * e["schnitt_doppel"] * (1 / v4 - 1 / v2), 1e-6) and z0["zeit_doppel"] > 0
assert nah(z0["laser_brutto"], sum(z0[f"zeit_{n}"] or 0 for n in rechnen.ZEITANTEILE), 1e-6)
ok(f"K2 Anschlag doppelt: 2 × {e['schnitt_doppel']} mm mit {v4:g} statt {v2:g} mm/min = +{z0['zeit_doppel']:.2f} s")

db.con.execute("UPDATE schneiddaten SET zeit_ecke=0.3 WHERE maschinen_id='T03'")
db.con.commit()
z1, su1, _ = rechnung()
assert nah(z1["zeit_ecken"], 2 * e["ecken"] * 0.3, 1e-9) and nah(z1["laser_brutto"] - z0["laser_brutto"], z1["zeit_ecken"], 1e-9)
assert rechnen.ecken_ende(dict(form="Rechteckrohr")) == 4 and rechnen.ecken_ende(dict(form="Rundrohr")) == 0
ok(f"K1 Eckzeit: 2 Enden × {e['ecken']} Ecken × 0,3 s = {z1['zeit_ecken']:.1f} s")
# K3: gemeinsame Schnitte sparen auch Ecken und Anschlag eines Endes
gem = sum(t["eingespart_e"] for st in s.ergebnis["stangen"] for t in st["teile"])
assert gem > 0
je = rechnen.zeit_enden(s.positionen[0], s.kopf, rechnen.schneiddaten("T03", "S235-10219", 2, s.tabellen, "Stahl"),
                        s.tabellen, s.k, v2)["je_ende"]
assert z1["einsparung"] - z0["einsparung"] > 0 and nah(z1["einsparung"] - z0["einsparung"], gem * e["ecken"] * 0.3 / 10,
                                                          1e-6) and je > e["ecken"] * 0.3
ok(f"K3 Einsparung gemeinsamer Schnitte enthält Ecken und Anschlag ({gem} Schnitte)")

mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
db.con.execute("UPDATE maschinen SET sonder_spannbar='nein' WHERE id=?", (mid,))
db.con.commit()
assert rechnung()[2] == "WARNUNG: Maschine prüfen: T03 spannt keine RP-/Sonderprofile"
ok("K4 Maschine spannt keine RP-/Sonderprofile: WARNUNG")
db.con.execute("UPDATE maschinen SET sonder_spannbar='ja', ruest_sonder=20 WHERE id=?", (mid,))
db.con.commit()
db.zeitbasis_speichern(a, None)             # Zeitvorgaben des Angebots = aktuelle Maschine (mit Rüstzuschlag)
z5, su5, st5 = rechnung()
satz = rechnen._schritt_satz(rechnen.zeitbasis(s.kopf, s.k, s.tabellen), None, "Rüsten je Abmessung")[1]
assert nah(su5["ruesten_abmessungen"] - su1["ruesten_abmessungen"], 20 / 60 * satz, 1e-6), (su5, satz)
assert nah((z5["ruesten_teil"] - z1["ruesten_teil"]) * 10, 20 / 60 * satz, 1e-6)
assert "1 × 20 min RP-/Sonderprofil" in dict((t.split(" (")[0], t) for t, _, _ in rechnen.kostenarten(su5, s.einst))[
    "Rüsten je Abmessung"]
ok(f"K5 Rüstzuschlag 20 min je RP-Abmessung = {20 / 60 * satz:.2f} €")
db.con.execute("UPDATE maschinen SET duese_min=10 WHERE id=?", (mid,))
db.con.commit()
assert rechnung()[2].startswith("HINWEIS") or rechnung()[2] == "OK"       # ohne Innenkonturen keine Warnung
db.con.execute("UPDATE positionen SET innen=25.1, klein_n=1, klein_mm=25.1, schneidweg=? WHERE id=?",
               (2 * e["schnitt"] + 25.1, s.positionen[0]["id"]))
db.con.commit()
assert rechnung()[2] == "WARNUNG: Innenkonturen unter dem Anschlag prüfen (Anschlag 12 mm, Düse min. 10 mm)", \
    rechnung()[2]
ok("K6 Düsenabstand: Innenkonturen am RP-Profil mit Anschlag über dem Mindestabstand → WARNUNG")
db.schliessen()
print("Alle Profilwechsel- und RP-Kalkulationsprüfungen bestanden.")
