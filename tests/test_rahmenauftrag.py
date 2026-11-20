"""Rahmenaufträge und Abrufe (Patrick 20.11.2026, Master-Auftrag Punkt 14): die 14 Testfälle, jede Zahl im Test
von Hand nachgerechnet (eigene Formeln hier, nicht die des Moduls), dazu Zusammenspiel mit der zentralen Rechnung
(Kostenmodell, Gegenprüfung), Dokumente (Kundenangebot ohne interne Begriffe), Schema 98 und die Oberfläche.

Aufruf: python tests/test_rahmenauftrag.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import db_verbindung, rahmen_kalk as rk, rahmenauftrag as ra, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402

M = 30.4375          # Tage je Monat (wie im Modul, hier eigens geschrieben)


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    assert a is not None and abs(a - b) <= tol, (a, b)
    return True


def tage(a, b):
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


# Kostenmodell zum Nachrechnen: eine Position, Losfix 100 €, Fertigung 2 €/Stk., Material 3 €/Stk. (1 kg),
# Programmierung 50 €, Gewinn 10 %, kein Skonto, keine Fracht
MOD = dict(pos={"10": rk.modell_zeile(F=100.0, vf=2.0, m=3.0, z=0.0, P=50.0, kg=1.0)}, gewinn=0.10, skonto=0.0)
PAR0 = dict(rk.VORGABEN, zins=12.0, lagerplatz=0.0, teile_palette=100.0, einlagern=0.0, prog_wiederholung=10.0,
            kommission_min=0.0, verpackung=0.0, abwicklung=10.0, verwaltung=0.0, einmalig=0.0, bestellkosten=0.0,
            moq_kg=0.0, max_lagerdauer=0.0, staffel=[])


def abrufe(termine, menge):
    return [dict(datum=t, mengen={"10": menge}) for t in termine]


def monatlich(n, start="2027-01-15"):
    d = datetime.date.fromisoformat(start)
    return [ra._plus_monate(d, i).isoformat() for i in range(n)]


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 99
assert {"rahmen_ereignisse", "rahmen_kopf"} <= set(db_verbindung.tabellen(db.con))
ok("Schema 99: Tabellen rahmen_ereignisse und rahmen_kopf")

# ------------------------------------------------------------------ 1: 100 Stück, ein Abruf
a1 = abrufe(["2027-01-15"], 100)
v = rk.varianten(a1, MOD, PAR0)
selbst = 100 + 2 * 100 + 50 + 3 * 100 + 10            # Los + Fertigung + Programmierung + Material + Abruf
for x in (rk.A, rk.B, rk.C):
    nah(v[x]["selbst"], selbst)
    assert v[x]["lose"] == 1 and v[x]["lager"] == 0 and v[x]["kapital"] == 0
nah(v[rk.C]["gewinn"], 0.1 * selbst)
nah(v[rk.C]["preis_stueck"], 1.1 * selbst / 100)
ok(f"1 Rahmen 100 Stk., ein Abruf: A = B = C = {selbst:.2f} € Selbstkosten, Preis {1.1 * selbst / 100:.3f} €/Stk.")

# ------------------------------------------------------------------ 2: 1.000 Stück, zehn Abrufe (Verwaltung)
u = ra.anlegen(db, dict(kunde="Muster Metall GmbH", projekt="Gestell", start="2027-01-01", ende="2027-12-31",
                        min_abruf=50, max_abruf=200), [dict(pos="10", bezeichnung="Strebe", menge=1000, preis=8.0)])
z = ra.sicht(db, u)
assert ra.MUSTER.match(z["nummer"]) and z["status"] == ra.ENTWURF
abr = [ra.abruf_neu(db, u, d, {"10": 100})[0] for d in monatlich(10)]
for x in abr[:3]:
    ra.abruf_status(db, u, x, ra.ABGERUFEN)
    ra.lieferung(db, u, x, datum="2027-03-31")
ra.abruf_status(db, u, abr[3], ra.ABGERUFEN)
ra.abruf_status(db, u, abr[4], ra.ABGERUFEN)
k = ra.kennzahlen(ra.sicht(db, u))
p = k["positionen"][0]
assert (p["abgerufen"], p["geplant"], p["geliefert"], p["offen"], p["verfuegbar"]) == (500, 500, 300, 700, 0)
nah(k["restwert"], 700 * 8.0)
assert len(k["offene_abrufe"]) == 7 and k["abrufe_ist"] == 3
assert [a["status"] for a in k["abrufe"][:5]] == [ra.GELIEFERT] * 3 + [ra.ABGERUFEN] * 2
ok("2 Rahmen 1.000 Stk., 10 Abrufe: abgerufen 500, geliefert 300, offen 700, Restwert 5.600 €, 7 offene Abrufe")

# ------------------------------------------------------------------ 3: 5.000 Stück monatlich, optimale Lose
a3 = abrufe(monatlich(12), 5000 / 12)
par3 = dict(PAR0, lagerplatz=15.0)
opt = rk.optimal(a3, MOD, par3)
r_opt = rk.bewerten(opt, a3, MOD, par3)
best, lose_best = rk.vollsuche(a3, MOD, par3)
nah(r_opt["selbst"], best["selbst"], 1e-6)
v3 = rk.varianten(a3, MOD, par3)
nah(v3[rk.C]["selbst"], best["selbst"], 1e-6)
assert v3[rk.C]["selbst"] <= min(v3[rk.A]["selbst"], v3[rk.B]["selbst"]) + 1e-9
nah(sum(los["stueck"] for los in v3[rk.C]["je_los"]), 5000, 1e-6)
ok(f"3 Rahmen 5.000 Stk. monatlich: Wagner-Whitin = Vollsuche über 2.048 Aufteilungen ({len(opt)} Lose, "
   f"{r_opt['selbst']:.2f} €)")

# ------------------------------------------------------------------ 4: Gesamtfertigung mit Lagerung
t4 = ["2027-01-15", "2027-03-17", "2027-05-17"]
a4 = abrufe(t4, 100)
par4 = dict(PAR0, lagerplatz=15.0, einlagern=10.0)
b = rk.bewerten([[0, 1, 2]], a4, MOD, par4)
m1, m2 = tage(t4[0], t4[1]) / M, tage(t4[0], t4[2]) / M
kapital = 100 * (2 + 3) * 0.12 / 12 * (m1 + m2)
lager = 100 / 100 * 15 * (m1 + m2) + 10
nah(b["kapital"], kapital)
nah(b["lager"], lager)
nah(b["selbst"], 100 + 2 * 300 + 50 + 3 * 300 + 3 * 10 + kapital + lager)
ok(f"4 Gesamtfertigung + Lager: Kapitalbindung {kapital:.2f} €, Lagerplatz+Einlagern {lager:.2f} € nach Monaten")

# ------------------------------------------------------------------ 5: Fertigung je Abruf
a_ = rk.bewerten([[0], [1], [2]], a4, MOD, par4)
nah(a_["ruesten"], 3 * 100)
nah(a_["programmierung"], 50 + 2 * 50 * 0.10)
assert a_["lager"] == 0 and a_["kapital"] == 0
nah(a_["selbst"], 300 + 600 + 60 + 900 + 30)
ok("5 Fertigung je Abruf: Rüsten 3 × 100 €, Programmierung 50 € + 2 × 10 % Wiederholung, kein Lager")

# ------------------------------------------------------------------ 6: optimierte Lose
a6 = abrufe(monatlich(6), 50)
par6 = dict(PAR0, lagerplatz=20.0, teile_palette=50.0)
v6 = rk.varianten(a6, MOD, par6)
assert v6[rk.C]["selbst"] < min(v6[rk.A]["selbst"], v6[rk.B]["selbst"]) - 1e-6, v6[rk.C]["plan"]
assert 1 < v6[rk.C]["lose"] < 6 and v6["empfehlung"] == rk.C
festes = dict(v6["feste"])
assert [x["lose"] for x in festes.values()] == [3, 2, 1, 1]       # 100 = 2 Abrufe je Los, 250 = 5 + 1, 500/1000 = alles
ok(f"6 Optimierte Lose: C {v6[rk.C]['selbst']:.2f} € < A {v6[rk.A]['selbst']:.2f} € und B {v6[rk.B]['selbst']:.2f} €"
   f" ({v6[rk.C]['lose']} Lose); feste Losgrößen auf ganze Abrufe gerundet")

# ------------------------------------------------------------------ 7: Materialpreissteigerung während der Laufzeit
z = ra.sicht(db, u)
erg = rk.berechnen(z, MOD, dict(mindestmarge=0))
ra.version_festschreiben(db, u, erg)
ra.preisbindung_setzen(db, u, dict(modell=rk.GLEITKLAUSEL, schwelle=2.0))
z = ra.sicht(db, u)
jp = z["version"]["je_position"]["10"]
offen = [dict(pos="10", preis=8.0, offen=700)]
aw = rk.auswirkung(offen, z["version"]["je_position"], 2.90 / 2.50, z["preisbindung"])
nah(aw["material_alt"], 700 * jp["material_stueck"])
nah(aw["differenz"], 700 * 3.0 * (2.90 / 2.50 - 1))                 # +16 % auf den Materialanteil
nah(aw["gewinn_neu"], aw["gewinn_alt"] - aw["differenz"])
anteil = 3.0 / 8.0
nah(aw["vorschlag"]["10"], round(8.0 * (1 + anteil * 0.16), 2))
assert aw["faellig"]
vid = ra.preis_vorschlagen(db, u, aw["vorschlag"], "Material +16 %")
assert ra.sicht(db, u)["positionen"][0]["preis"] == 8.0            # Vorschlag ändert nichts
ra.status_setzen(db, u, ra.AKTIV)
try:
    ra.position_aendern(db, u, z["positionen"][0]["uid"], "preis", 9.0)
    raise AssertionError("Vertragspreis still geändert")
except ra.RahmenFehler:
    pass
ra.preis_freigeben(db, u, vid)
z = ra.sicht(db, u)
nah(z["positionen"][0]["preis"], round(8.0 * (1 + anteil * 0.16), 2))
assert z["positionen"][0]["preis_verlauf"][0]["alt"] == 8.0 and z["version"]["nr"] == 1
fest = rk.auswirkung(offen, z["version"]["je_position"], 1.16, dict(modell=rk.FEST_LAUFZEIT))
assert not fest["faellig"] and fest["gebunden"]
ok(f"7 Material 2,50 → 2,90 €/kg: +{aw['differenz']:.2f} € auf 700 offene Stk., Gleitpreis {aw['vorschlag']['10']:.2f} €, "
   "Preis erst nach Freigabe; Festpreis: keine Anpassung; Version 1 bleibt")

# ------------------------------------------------------------------ 8: Änderung einer Abrufmenge
warn = ra.abruf_aendern(db, u, abr[5], "mengen", {"10": 150})
assert "überschritten" in warn                                      # 1.050 von 1.000 Stück: Warnung, keine Sperre
k = ra.kennzahlen(ra.sicht(db, u))
assert k["positionen"][0]["verfuegbar"] == -50 and k["ueber"]
assert any(w[0] == rk.ROT and "überschritten" in w[1] for w in rk.warnungen(ra.sicht(db, u), "2027-02-01"))
ra.abruf_aendern(db, u, abr[5], "mengen", {"10": 100})
ra.abruf_aendern(db, u, abr[5], "datum", "2027-07-01")
prot = ra.protokoll(db, u)
assert any("Abruf geändert" in x[3] and "150" in x[4] for x in prot)
ra.aendern(db, u, "menge_sperrt", "ja")
try:
    ra.abruf_aendern(db, u, abr[5], "mengen", {"10": 150})
    raise AssertionError("Sperre wirkt nicht")
except ra.RahmenFehler:
    pass
ok("8 Abrufmenge ändern: Protokoll alt → neu, Warnung bei Überschreitung, Sperre mit „Rahmenmenge sperrt“")

# ------------------------------------------------------------------ 9: Stornierung eines Abrufs
vor = ra.kennzahlen(ra.sicht(db, u))["positionen"][0]["verfuegbar"]
ra.abruf_stornieren(db, u, abr[9], "Kunde braucht weniger")
k = ra.kennzahlen(ra.sicht(db, u))
assert k["positionen"][0]["verfuegbar"] == vor + 100 and k["storniert"] == 1
try:
    ra.abruf_stornieren(db, u, abr[0], "zu spät")
    raise AssertionError("gelieferter Abruf storniert")
except ra.RahmenFehler:
    pass
assert all(sum(a["mengen"].values()) for a in rk.abrufe_ordnen(ra.sicht(db, u)["abrufe"]))
assert len(rk.abrufe_ordnen(ra.sicht(db, u)["abrufe"])) == 9
ok("9 Abruf stornieren: Menge wieder frei, Grund im Protokoll, gelieferte Abrufe nicht stornierbar, nicht mehr geplant")

# ------------------------------------------------------------------ 10: Restmenge zum Vertragsende
los = ra.los_neu(db, u, "2027-04-15", {"10": 300}, [4, 5, 6])
ra.los_gefertigt(db, u, los)
z = ra.sicht(db, u)
w = rk.warnungen(z, "2028-01-10")
assert any(x[0] == rk.ROT and "abgelaufen" in x[1] for x in w)
assert any("überfällig" in x[1] for x in w)
assert rk.ampel(w) == rk.ROT
w_frueh = rk.warnungen(z, "2027-11-15")
assert any("endet in 46 Tagen" in x[1] for x in w_frueh), w_frueh
ab = rk.abschluss(z, "2028-01-10")
p = ab["zeilen"][0]
assert (p["menge"], p["abgerufen"], p["geliefert"], p["gefertigt"], p["bestand"], p["verpflichtung"]) == \
       (1000, 500, 300, 300, 300, 200)                                 # Los für Abrufe 4-6 liegt noch auf Lager
assert p["nicht_abgerufen"] == 500 and nah(ab["umsatz"], 300 * z["positionen"][0]["preis"])
assert any("nicht abgerufen" in h for h in ab["hinweise"]) and any("nicht geliefert" in h for h in ab["hinweise"])
rest = ra.offene_abrufe_fuer_plan(z)
assert sum(a["mengen"]["10"] for a in rest) == 1000 - 300 - 100 - 300   # ohne Storno, Geliefertes, Gefertigtes
ok("10 Vertragsende: rote Ampel, Abschluss (500 nicht abgerufen, 200 abgerufen nicht geliefert), Restplan ohne Gefertigtes")

# ------------------------------------------------------------------ 11: Mindestbestellmenge
a11 = abrufe(monatlich(5), 100)
par11 = dict(PAR0, moq_kg=500.0, bestellkosten=25.0)
r = rk.bewerten([[i] for i in range(5)], a11, MOD, par11)
assert len(r["material_kaeufe"]) == 1 and r["material_kaeufe"][0]["kg"] == 500
nah(r["material"], 500 * 3.0 + 25)
kap = sum(100 * 3.0 * 0.12 / 12 * tage(monatlich(5)[0], t) / M for t in monatlich(5)[1:])
nah(r["material_kapital"], kap)
r2 = rk.bewerten([[i] for i in range(5)], a11, MOD, dict(par11, bestand_kg=250.0, bestand_eur=750.0))
assert r2["material_kaeufe"][0]["datum"] == monatlich(5)[2]           # 250 kg schon gekauft: erst Los 3 kauft
ok(f"11 Mindestbestellmenge 500 kg: ein Kauf statt fünf, Rest auf dem Materialkonto (Kapital {kap:.2f} €); "
   "gekauftes Material wird nicht neu gekauft")

# ------------------------------------------------------------------ 12: Materialpreisstaffeln
par12 = dict(PAR0, staffel=[(500.0, 3.0), (1000.0, 5.0)])
a12 = abrufe(monatlich(4), 250)
g = rk.bewerten([[0], [1], [2], [3]], a12, MOD, par12, material=rk.GESAMT)
nah(g["material"], 1000 * 3.0 * 0.95)
j = rk.bewerten([[0], [1], [2], [3]], a12, MOD, par12, material=rk.JE_LOS)
nah(j["material"], 4 * 250 * 3.0)
mv = rk.materialvergleich(a12, MOD, par12)
assert mv["empfehlung"] in (rk.GESAMT, rk.JE_LOS) and mv["ersparnis"] >= 0
bei = rk.bewerten([[0, 1, 2, 3]], a12, MOD, par12, material=rk.BEISTELLUNG)
assert bei["material"] == 0 and bei["material_kapital"] == 0
ok("12 Materialpreisstaffel: 1.000 kg auf einmal 5 % Rabatt (2.850 €) gegen je Los 3.000 €; Beistellung ohne Material")

# ------------------------------------------------------------------ 13: Unterschreitung der Mindestmarge
r13 = rk.bewerten([[0]], a1, MOD, PAR0, marge_min=0.20)
S, G = r13["selbst"], r13["gewinn"]
nah(r13["anhebung"], 0.2 * S / 0.8 - G)
nah(r13["marge"], 0.20)
assert r13["unter_mindestmarge"]
ps = rk.preisstaffel(a1, MOD, PAR0, mengen=(100, 1000), marge_min=0.20)
assert all(s["unter_mindestmarge"] and nah(s["marge"], 0.2) for z_ in ps for s in z_["szenarien"])
z = ra.sicht(db, u)
assert rk.vertragsmarge(z) is not None
w = rk.warnungen(z, "2027-02-01", marge_min=0.99)
assert any("unter Mindestmarge" in x[1] for x in w)
ok(f"13 Mindestmarge 20 %: Anhebung {r13['anhebung']:.2f} € = 0,2·S/0,8 − G, Marge danach 20 %, Staffel geschützt, "
   "Warnung bei Vertragspreisen darunter")

# ------------------------------------------------------------------ 14: parallele Bearbeitung durch mehrere Benutzer
db2 = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")      # eigener PC = eigener Datenspeicher
u2 = ra.anlegen(db, dict(kunde="Parallel KG", start="2027-01-01", ende="2027-12-31"),
                [dict(pos="10", bezeichnung="Halter", menge=500, preis=4.0)])
x1 = ra.abruf_neu(db, u2, "2027-02-01", {"10": 100})[0]


def zeilen(d):
    return [dict(r) for r in d.con.execute("SELECT * FROM rahmen_ereignisse")]


assert ra.ereignisse_einlesen(db2, zeilen(db)) > 0
assert ra.sicht(db2, u2)["abrufe"][0]["mengen"] == {"10": 100}
ra.abruf_aendern(db, u2, x1, "mengen", {"10": 120})                         # Platz 1
ra.abruf_aendern(db2, u2, x1, "mengen", {"10": 150}, rechner="PLATZ-2")     # Platz 2 gleichzeitig, sah noch 100
ra.abruf_aendern(db2, u2, x1, "lieferort", "Halle 3", rechner="PLATZ-2")
ra.ereignisse_einlesen(db, zeilen(db2))
ra.ereignisse_einlesen(db2, zeilen(db))
s1, s2 = ra.sicht(db, u2), ra.sicht(db2, u2)
assert s1["abrufe"] == s2["abrufe"] and s1["abrufe"][0]["mengen"] == {"10": 150}
assert s1["abrufe"][0]["lieferort"] == "Halle 3"
assert len(s1["konflikte"]) == 1 and s1["konflikte"][0]["war"] == {"10": 120}
assert any("gleichzeitige" in x[1] for x in rk.warnungen(dict(s1, status=ra.AKTIV), "2027-01-10"))
assert len(zeilen(db)) == len(zeilen(db2)) and not ra.pruefen(db) and not ra.pruefen(db2)
db.con.execute("UPDATE rahmen_ereignisse SET neu='999' WHERE id=(SELECT MAX(id) FROM rahmen_ereignisse)")
assert ra.pruefen(db)
ok("14 Zwei Plätze ändern denselben Abruf: beide Stände gleich, spätere Änderung gilt, Konflikt gemeldet, nichts "
   "verloren, nachträgliche Änderung fällt über die Prüfsumme auf")

# ------------------------------------------------------------------ zentrale Rechnung: Kostenmodell und Gegenprüfung
a = db.angebot_neu(dict(nummer="A-RA-1", kunde="Rahmen Test GmbH", datum="2026-11-20", maschine="T11", stange=6000))
db.position_neu(a, dict(pos=10, artikel="RA-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                        werkstoff_id="S235-10219", laenge=485.0, stueck=100, schneidweg=380, einstiche=4))
db.position_neu(a, dict(pos=20, artikel="RA-20", bezeichnung="Halter", profil_id="RR 42,4x2,0",
                        werkstoff_id="S235-10219", laenge=210.0, stueck=100, schneidweg=200, einstiche=2))
ur = ra.aus_angebot(db, a, mengen={"10": 1000, "20": 500})
for i, d in enumerate(monatlich(6, "2027-01-15")):
    ra.abruf_neu(db, ur, d, {"10": (100, 150, 200, 150, 200, 200)[i], "20": (50, 75, 100, 75, 100, 100)[i]})
z = ra.sicht(db, ur)
assert z["angebot_uid"] and [p["pos"] for p in z["positionen"]] == ["10", "20"]
kopf, pos = db.angebot(a), db.positionen(a)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
k_, tab = db.kontext(), db.tabellen()
modell, info = rk.kostenmodell_aus_angebot(kopf, pos, z["positionen"], z["abrufe"], k_, tab, einst)
assert modell and info["q1"] == {"10": 100, "20": 50} and info["q2"] == {"10": 1000, "20": 500}
l1, l2 = info["laeufe"]
for p_ in ("10", "20"):
    x = modell["pos"][p_]
    f = lambda y: y["selbst"] - y["programmierung"] - y["m_gesamt"]       # noqa: E731
    assert x["F"] > 0 and x["vf"] > 0 and x["m"] > 0 and x["kg"] > 0
    nah(x["F"] + x["vf"] * info["q1"][p_], f(l1[p_]), 1e-6)               # Gerade durch beide Läufe
    nah(x["F"] + x["vf"] * info["q2"][p_], f(l2[p_]), 1e-6)
    nah(x["m"] * info["q2"][p_], l2[p_]["m_gesamt"], 1e-6)
# gleiche Mengen = gleiche Kosten wie die Staffel des Angebots (eine Rechnung)
from rohrlaser import staffeln  # noqa: E402
st = staffeln.stufe_rechnen(dict(kopf, abruf=None), pos, "10", 1000, k_, tab, einst)
erg = rk.berechnen(z, modell, db.einstellungen())
gp = rk.gegenpruefung(kopf, pos, erg["ergebnis"], k_, tab, einst, modell)
assert gp and all(abs(x["abweichung"]) < 5 and abs(x["material_abweichung"]) < 5 for x in gp), gp
assert erg["empfehlung"] in (rk.A, rk.B, rk.C) and len(erg["preisstaffel"]) == 6
assert st["preis"]["selbst"] > 0
ok(f"Kostenmodell aus der zentralen Rechnung (Gerade durch beide Läufe), Gegenprüfung je Los "
   f"{max(abs(x['abweichung']) for x in gp):.2f} % Abweichung, Empfehlung {erg['empfehlung']}")

# ------------------------------------------------------------------ Abruf-Angebot im Angebotsfenster (gleiche Rechnung)
ka = dict(kopf, abruf="ja", abruf_jahr_von=1200, abruf_jahr_bis=2400, abruf_von=100, abruf_bis=200, abruf_laufzeit=12)
abr_a, rpos_a, ab_a = rk.abrufplan_aus_angebot(ka, pos, "2027-01-01")
assert len(abr_a) == 12 and abr_a[0]["mengen"] == {"10": 100.0, "20": 100.0} and abr_a[-1]["datum"] == "2027-12-01"
assert {p["pos"]: p["menge"] for p in rpos_a} == {"10": 1200.0, "20": 1200.0}
aw_a = rk.angebot_auswertung(ka, pos, k_, tab, einst, "2027-01-01")
assert not aw_a.get("fehler"), aw_a
va = aw_a["varianten"]
assert va[rk.A]["lose"] == 12 and va[rk.B]["lose"] == 1 and va[aw_a["empfehlung"]]["selbst"] <= va[rk.A]["selbst"] + 1e-9
assert [z["menge"] for z in aw_a["preisstaffel"]] == [2400, 4800] and len(aw_a["preisstaffel"][0]["szenarien"]) == 5
nah(aw_a["losgroesse"], aw_a["ergebnis"]["menge"] / aw_a["ergebnis"]["lose"])
assert "Empfehlung: Variante" in rk.angebot_text(aw_a)
assert db.angebot(a).get("abruf") != "ja"                                 # Auswertung ändert das Angebot nicht
assert rk.angebot_auswertung(kopf, pos, k_, tab, einst)["fehler"]          # ohne Abruf-Angebot: Hinweis
ok(f"Abruf-Angebot: gleiche Rechnung wie der Rahmen (12 Abrufe, Empfehlung {aw_a['empfehlung']}, Lose zu ca. "
   f"{aw_a['losgroesse']:.0f} Stk.), Preisstaffel für kleinste und größte Jahresmenge")

# ------------------------------------------------------------------ Dokumente
from rohrlaser import rahmen_pdf  # noqa: E402
ra.version_festschreiben(db, ur, erg)
z = ra.sicht(db, ur)
for art in rahmen_pdf.ARTEN:
    pf = tmp / f"{art}.pdf"
    rahmen_pdf.schreiben(pf, art, z, erg, db.einstellungen())
    assert pf.stat().st_size > 2000, art
assert rahmen_pdf.kunde_pruefen(tmp / "kunde.pdf") == [] and rahmen_pdf.kunde_pruefen(tmp / "abrufe.pdf") == []
assert "Marge" in rahmen_pdf.kunde_pruefen(tmp / "vergleich.pdf")
ok("7 Dokumente; Kundenangebot und Abrufübersicht ohne Selbstkosten, Gewinn, Marge (Schutztest)")

# ------------------------------------------------------------------ Schema 97 → 98
alt = Path(tempfile.mkdtemp()) / "rohrlaser.db"
d0 = Datenbank(alt)
d0.con.execute("DROP TABLE rahmen_kopf")
d0.con.execute("DROP TABLE rahmen_ereignisse")
db_verbindung.schema_version_setzen(d0.con, 98)
d0.con.commit()
d0.con.close()
d1 = Datenbank(alt)
assert d1.sicherungen(zusatz="vor_Schema_99") and {"rahmen_ereignisse", "rahmen_kopf"} <= set(
    db_verbindung.tabellen(d1.con))
ok("Umstellung von Schema 98: Sicherung vor_Schema_99, Rahmentabellen neu und leer")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
seite = fenster.rahmen
assert fenster.reiter.isTabVisible(fenster.reiter.indexOf(seite))
zeilen_ = seite.neu_laden()
assert len(zeilen_) == 3 and {z["ampel"] for z in zeilen_} <= {rk.GRUEN, rk.GELB, rk.ROT}
seite.kunde.setText("Rahmen Test")
assert len(seite.zeilen) == 1
seite.kunde.setText("")
d = seite.oeffnen(ur)
assert d.reiter.count() == 9
erg_ui = d.berechnen()
assert erg_ui and d.var_t.rowCount() == 17 and d.staffel_t.rowCount() == 30
assert d.preise_uebernehmen() == 2 and all(p.get("preis") for p in d.z["positionen"])
nr = d.festschreiben()
assert nr == 2
a7 = d.auswirkung(faktor=1.16)
assert a7 and a7["differenz"] > 0
vid = d.vorschlagen()
d.freigeben()
assert d.z["vorschlaege"][0]["status"] == "freigegeben"
d.abruf_liefern(abruf=d.k["abrufe"][0], lieferschein="LS-1")
assert d.k["abrufe"][0]["status"] == ra.GELIEFERT
assert d.lose_anlegen() == erg_ui["ergebnis"]["lose"]
pf = d.dokument("kunde", tmp / "ui_kunde.pdf")
assert Path(pf).exists()
d.reiter.setCurrentIndex(2)
d.grafik.resize(800, 160)
assert not d.grafik.grab().isNull()
neu = seite.neu(werte=dict(kunde="Neu GmbH"))
assert ra.sicht(db, neu)["kunde"] == "Neu GmbH"
from rohrlaser.abruf_dialog import AbrufDialog  # noqa: E402
sa = fenster.angebot_oeffnen(a)
assert sa.abruf_bearbeiten(dict(abruf="ja", abruf_jahr_von=1200, abruf_jahr_bis=2400, abruf_von=100, abruf_bis=200,
                                abruf_laufzeit=12))
ad = AbrufDialog(None, sa.kopf, db.einstellungen(), auswerten=sa.abruf_auswertung)
assert ad.auswertung and not ad.auswertung.get("fehler") and ad.w_var.rowCount() == 3 and ad.w_staffel.rowCount() == 10
ad.von.setValue(200)
a2 = ad.neu_rechnen()
assert a2["abrufe"] == 6 and a2["je_abruf"] == 200, (a2.get("abrufe"), a2.get("je_abruf"))
ok("Abruf-Angebot im Angebotsfenster: Fenster zeigt Varianten A/B/C und Preisstaffel, Neu rechnen mit den Werten oben")
db.einstellung_setzen("rahmen_aktiv", "nein")
assert not fenster.rahmen_an()
ok("Oberfläche: Reiter mit Ampel und Filter, Rahmenfenster mit 9 Reitern, Berechnen, Preise, Festschreiben, "
   "Auswirkung + Freigabe, Lieferung, Lose, Kundenangebot, Grafik")

print("Alle Prüfungen der Rahmenaufträge bestanden.")
