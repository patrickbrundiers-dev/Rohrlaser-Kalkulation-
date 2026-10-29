"""Prüft den Teuerungs-/Legierungszuschlag je Werkstoff (Plan 29.10.2026 1a, Patrick „4c“: % oder €/kg):

- T1 ohne Zuschlag rechnet alles wie bisher (Meterpreis, Stangenkosten)
- T2 Zuschlag in % auf den Materialpreis (Preise, Lieferlängen, Tonnenpreis), nicht auf den Oberflächen-Aufpreis und
  nicht auf den Preis von Hand
- T3 Zuschlag in €/kg auf das Stangengewicht (mit Händler-Mehrlänge), ohne Gewicht Hinweis „Gewicht fehlt“
- T4 Tooltip „Herkunft …, zzgl. Teuerungszuschlag 8 % (Stand 01.10.2026)“
- T5 festgeschriebene Angebote behalten ihren Zuschlag; ältere Snapshots (vor dem Zuschlag) rechnen ohne; die
  Abweichung nennt den geänderten Zuschlag
- T6 Spalten in den Stammdaten (Auswahl %/€/kg, Prüfung OK), Schema 68

Aufruf: python tests/test_teuerung.py
"""
import dataclasses
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import TABELLE, pruefen  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Test", skonto=0, stange=6000))
for pos, art, ob in ((10, "roh", None), (20, "K240", "K240")):
    db.position_neu(a, dict(pos=pos, artikel=art, profil_id="RR 42,4x2,0", werkstoff_id="1.4301", oberflaeche=ob,
                            laenge=1000, stueck=3, schneidweg=300, einstiche=2))
kopf, pos = db.angebot(a), db.positionen(a)
wid = db.kontext().werkstoffe["1.4301"]["id"]


def werte():
    k, tab = db.kontext(), db.tabellen()
    mp = [rechnen.meterpreis(p, kopf, pos, k, tab) for p in pos]
    gr = rechnen.gruppe_von(pos[0], kopf)
    kgm = rechnen.kg_je_m(gr[0], gr[1], k)
    stange = rechnen.lieferstange_preis(gr, 6000, 6 * kgm, kopf, pos, k, tab)
    return k, tab, mp, stange, kgm


# T1 ohne Zuschlag: wie bisher (Preise: 62 € je 6-m-Stange, K240 + 2,20 €/m)
k, tab, mp, stange0, kgm = werte()
assert nah(mp[0][0], 62 / 6) and nah(mp[1][0], 62 / 6 + 2.20), mp
assert rechnen.teuerung("1.4301", k) is None and rechnen.teuerung_text("1.4301", k) is None
assert nah(stange0[0], 62.0) and stange0[1] is None, stange0
ok("T1 ohne Zuschlag unverändert")

# T2 Zuschlag in %
db.aendern("werkstoffe", wid, "teuerung_art", "%")
db.aendern("werkstoffe", wid, "teuerung_wert", 8)
db.aendern("werkstoffe", wid, "teuerung_stand", "2026-10-01")
k, tab, mp, stange, _ = werte()
assert nah(mp[0][0], 62 / 6 * 1.08), mp[0]
assert nah(mp[1][0], 62 / 6 * 1.08 + 2.20), "Zuschlag nicht auf den Oberflächen-Aufpreis"
assert nah(stange[0], 62 * 1.08), stange
assert nah(rechnen.teuerung_betrag(100.0, None, "1.4301", k)[0], 8.0)
# Preis von Hand: gilt unverändert (kein Zuschlag)
hand = [dict(pos[0], preis_m=10.0)]
gr = rechnen.gruppe_von(pos[0], kopf)
assert nah(rechnen.lieferstange_preis(gr, 6000, 6 * kgm, kopf, hand, k, tab, mehr=False)[0], 60.0)
# Tonnenpreis (Werkstoff ohne Zeile in 'Preise'): Zuschlag auch dort
tab_ohne = dict(tab, preise=[z for z in tab["preise"] if z.get("werkstoff_id") != "1.4301"], lieferlaengen=[])
ws = {w: dict(z, tonnenpreis=5000) for w, z in k.werkstoffe.items()}
kt = dataclasses.replace(k, werkstoffe=ws)
pt = rechnen.lieferstange_preis(gr, 6000, 6 * kgm, kopf, pos, kt, tab_ohne, mehr=False)
assert nah(pt[0], 6 * kgm * 5 * 1.08, 1e-6), pt
ok("T2 Zuschlag in % auf Preise und Tonnenpreis, nicht auf Aufpreis und Preis von Hand")

# T3 Zuschlag in €/kg
db.aendern("werkstoffe", wid, "teuerung_art", "€/kg")
db.aendern("werkstoffe", wid, "teuerung_wert", 0.5)
k, tab, mp, stange, kgm = werte()
mehr = rechnen.haendler_mehrlaenge(6000, tabellen=tab)
assert nah(stange[0], 62 + 6 * kgm * (6000 + mehr) / 6000 * 0.5, 1e-6), stange
assert nah(mp[0][0], 62 / 6 + kgm * 0.5, 1e-6), mp[0]     # Meterpreis ohne Mehrlänge
assert rechnen.teuerung_betrag(100.0, None, "1.4301", k) == (0.0, "Gewicht fehlt")
ok("T3 Zuschlag in €/kg auf das Stangengewicht, ohne Gewicht Hinweis")

# T4 Tooltip
db.aendern("werkstoffe", wid, "teuerung_art", "%")
db.aendern("werkstoffe", wid, "teuerung_wert", 8)
k, tab, *_ = werte()
t = rechnen.preis_herkunft(pos[0], kopf, k, tab)
assert t.startswith("Herkunft:") and t.endswith("zzgl. Teuerungszuschlag 8 % (Stand 01.10.2026)"), t
ok("T4 Tooltip nennt den Zuschlag")

# T5 Snapshot
pb = rechnen.preisbasis_aus(kopf, pos, k, tab)
assert pb["teuerung"] == {"1.4301": dict(teuerung_art="%", teuerung_wert=8, teuerung_stand="2026-10-01")}, pb["teuerung"]
db.aendern("werkstoffe", wid, "teuerung_wert", 12)
k_akt, tab_akt, mp_akt, *_ = werte()
assert nah(mp_akt[0][0], 62 / 6 * 1.12)
k_fest, tab_fest = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k_akt, tab_akt)
assert nah(rechnen.meterpreis(pos[0], kopf, pos, k_fest, tab_fest)[0], 62 / 6 * 1.08), "festgeschrieben: 8 %"
abw = rechnen.preisbasis_abweichung(dict(kopf, preisbasis=pb), k_akt, tab_akt)
assert "Teuerungszuschlag 1.4301: 8 % → 12 %" in abw, abw
alt = {n: v for n, v in pb.items() if n != "teuerung"}           # Snapshot vor dem 29.10.2026
k_alt, tab_alt = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=alt), k_akt, tab_akt)
assert nah(rechnen.meterpreis(pos[0], kopf, pos, k_alt, tab_alt)[0], 62 / 6), "alter Snapshot: ohne Zuschlag"
assert "Teuerungszuschlag 1.4301: ohne → 12 %" in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=alt), k_akt, tab_akt)
assert rechnen.preisbasis_gleich(pb, dict(pb, datum="2000-01-01"))
db.aendern("werkstoffe", wid, "teuerung_wert", None)
k0, tab0, *_ = werte()
pb0 = rechnen.preisbasis_aus(kopf, pos, k0, tab0)
assert pb0["teuerung"] == {} and rechnen.preisbasis_gleich(pb0, alt), "ohne Zuschlag = wie alter Snapshot"
ok("T5 festgeschrieben behält Zuschlag, alter Snapshot ohne, Abweichung nennt ihn")

# T6 Stammdaten
f = {x.name: x for x in TABELLE["werkstoffe"].felder}
assert f["teuerung_art"].auswahl == "teuerung" and f["teuerung_stand"].art == "datum"
z = dict(k.werkstoffe["1.4301"], teuerung_art="€/kg", teuerung_wert=0.35, teuerung_stand="2026-10-01")
assert pruefen(TABELLE["werkstoffe"], z, k) == "OK", pruefen(TABELLE["werkstoffe"], z, k)
assert SCHEMA_VERSION >= 68 and db.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
ok("T6 Stammdaten-Spalten und Schema")
# T7 Angebots-Check: Zuschlag ohne Stand oder älter als 3 Monate
import datetime  # noqa: E402
db.aendern("werkstoffe", wid, "teuerung_wert", 8)
k, *_ = werte()
assert rechnen.teuerung_hinweise(pos, k, datetime.date(2026, 11, 15)) == []
h = rechnen.teuerung_hinweise(pos, k, datetime.date(2027, 3, 1))
assert len(h) == 1 and h[0]["werkstoff"] == "1.4301" and h[0]["zeilen"] == [0, 1], h
assert "älter als 3 Monate" in h[0]["text"], h
db.aendern("werkstoffe", wid, "teuerung_stand", None)
k, *_ = werte()
assert "ohne Stand" in rechnen.teuerung_hinweise(pos, k)[0]["text"]
ok("T7 Hinweis im Angebots-Check bei altem Zuschlag")
print("Alle Teuerungs-Tests bestanden.")
