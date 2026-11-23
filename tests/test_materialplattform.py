"""Prüft den Kern der Materialplattform (Patrick 23.11.2026, materialplattform.py, Schema 103): Varianten aus den
vorhandenen Stammdaten (Gewicht, Innenmaß, €/kg, €/m, Preisquelle), intelligente Suche, Filter, Favoriten,
Archivieren (nicht mehr in der Auswahl, Angebote rechnen weiter), Duplizieren, Mehrfach ändern, mehrere Lieferanten
mit „Als aktiven Preis übernehmen“, Preisliste lesen/importieren, Vergleich und Alternativen ohne Gütewechsel,
Verschnitt je Handelslänge (keine Überbelegung), Bilanz theoretisch/Einkauf, Dichte im Angebots-Snapshot und
Tempo mit 30.000 Varianten.

Aufruf: python tests/test_materialplattform.py
"""
import datetime
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import materialplattform as mp, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import Kontext  # noqa: E402

EPS = 1e-6
HEUTE = datetime.date(2026, 11, 23)


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Suche zerlegen
s = mp.suche_zerlegen("60x40x3 Edelstahl")
assert s["masse"] == [60, 40, 3] and s["worte"] == ["edelstahl"] and s["form"] is None, s
s = mp.suche_zerlegen("Rundrohr 42,4x2")
assert s["form"] == "Rundrohr" and s["masse"] == [42.4, 2], s
assert mp.suche_zerlegen("40 x 40 x 2")["masse"] == [40, 40, 2]
assert mp.suche_zerlegen("40*40*2")["masse"] == [40, 40, 2]
assert mp.suche_zerlegen("40×40×2")["masse"] == [40, 40, 2]
assert mp.suche_zerlegen("1.4301")["worte"] == ["1.4301"] and not mp.suche_zerlegen("1.4301")["masse"]
s = mp.suche_zerlegen("QR40x40x2")
assert s["form"] == "Quadratrohr" and s["masse"] == [40, 40, 2], s
assert mp.suche_zerlegen("S235")["worte"] == ["s235"]
ok("Suche zerlegt Maße, Profilform und Wörter (×, *, Leerzeichen, Komma, Werkstoffnummer)")

# ------------------------------------------------------------------ Varianten ohne Datenbank
k = Kontext()
k.profile = {
    "QR 40x40x2": dict(profil_id="QR 40x40x2", form="Quadratrohr", a=40, b=40, wand=2),
    "RE 60x40x3": dict(profil_id="RE 60x40x3", form="Rechteckrohr", a=60, b=40, wand=3),
    "RR 42,4x2": dict(profil_id="RR 42,4x2", form="Rundrohr", a=42.4, wand=2),
    "RE 60x40x2": dict(profil_id="RE 60x40x2", form="Rechteckrohr", a=60, b=40, wand=2, archiviert="ja"),
}
k.werkstoffe = {
    "S235JRH": dict(werkstoff_id="S235JRH", kategorie="Stahl", werkstoff="S235JRH", werkstoff_nr="1.0039", dichte=7.85,
                    tonnenpreis=1200),
    "1.4301": dict(werkstoff_id="1.4301", kategorie="Edelstahl", werkstoff="X5CrNi18-10", werkstoff_nr="1.4301",
                   dichte=7.9, tonnenpreis=4200),
}
tab = dict(preise=[dict(profil_id="RE 60x40x3", werkstoff_id="1.4301", basis="€/kg", preis=4.85, lieferant="Nord",
                        gueltig_ab="2026-11-12", mindest_stangen=5, lieferlaenge=6000),
                   dict(profil_id="QR 40x40x2", werkstoff_id="S235JRH", basis="€/Stange", preis=30.0,
                        lieferlaenge=6000, gueltig_ab="2026-09-01")],
           lieferlaengen=[dict(profil_id="RE 60x40x3", werkstoff_id="1.4301", laenge=12000, basis="€/kg", preis=4.70)])
lief = [dict(profil_id="RE 60x40x3", werkstoff_id="1.4301", lieferant="Süd", basis="€/m", preis=20.75, laenge=6000,
             gueltig_ab="2026-11-01", gueltig_bis="2026-12-31", lieferzeit=5),
        dict(profil_id="RE 60x40x3", werkstoff_id="1.4301", lieferant="Alt", basis="€/m", preis=19.0,
             gueltig_bis="2026-10-31")]
zeilen = mp.varianten(k, tab, lief, nutzung={("RR 42,4x2", "S235JRH"): (3, "2026-11-20")}, heute=HEUTE)
assert {mp.schluessel(z) for z in zeilen} == {("RE 60x40x3", "1.4301"), ("QR 40x40x2", "S235JRH"),
                                              ("RR 42,4x2", "S235JRH")}, [mp.schluessel(z) for z in zeilen]
re = next(z for z in zeilen if z["profil_id"] == "RE 60x40x3")
fl = 60 * 40 - 54 * 34
assert abs(re["kgm"] - fl * 7.9 / 1000) < EPS and re["innen"] == "54 × 34"
assert abs(re["preis_m"] - 4.85 * re["kgm"]) < EPS and abs(re["preis_kg"] - 4.85) < EPS and re["quelle"] == mp.QUELLE_PREISE
assert re["handelslaengen"] == [6000, 12000] and re["lieferanten"] == ["Nord", "Süd", "Alt"] and re["mindest"] == 5
assert re["alter_tage"] == 11
qr = next(z for z in zeilen if z["profil_id"] == "QR 40x40x2")
assert abs(qr["preis_m"] - 5.0) < EPS and qr["alter_tage"] == 83
rr = next(z for z in zeilen if z["profil_id"] == "RR 42,4x2")
assert rr["quelle"] == mp.QUELLE_TONNE and rr["nutzung"] == 3 and rr["innen"] == "Ø 38,4"
assert abs(rr["preis_m"] - rr["kgm"] * 1.2) < EPS
# gleiche Zahl wie die Stammdaten-Spalte „Preis €/m automatisch“
from rohrlaser.stammdaten import preis_je_m_automatisch  # noqa: E402
assert abs(preis_je_m_automatisch(dict(profil_id="RR 42,4x2", werkstoff_id="S235JRH"), k) - rr["preis_m"]) < EPS
alle = mp.varianten(k, tab, lief, alle=True, heute=HEUTE)
assert len(alle) == 3 * 2, len(alle)          # 3 aktive Profile × 2 Werkstoffe, archiviertes fehlt
assert len(mp.varianten(k, tab, lief, alle=True, mit_archiv=True, heute=HEUTE)) == 8
ok("Varianten: Gewicht, Innenmaß, €/kg, €/m je Preisbasis, Tonnenpreis wie Stammdaten, Lieferanten, Stand, Archiv")

# ------------------------------------------------------------------ Suche
def ids(text, z=alle):
    return [mp.schluessel(x) for x in mp.suchen(z, text)]


assert ids("40x40x2") == [("QR 40x40x2", "S235JRH"), ("QR 40x40x2", "1.4301")]
assert ids("60x40x3 Edelstahl") == [("RE 60x40x3", "1.4301")]
assert ids("40x60x3 edelstahl") == [("RE 60x40x3", "1.4301")], "Rechteck in beiden Richtungen"
assert ids("Rundrohr 42,4x2") == [("RR 42,4x2", "S235JRH"), ("RR 42,4x2", "1.4301")]
assert ids("42x2") == ids("Rundrohr 42,4x2"), "42 findet 42,4 (unvollständig)"
assert set(ids("S235")) == {("QR 40x40x2", "S235JRH"), ("RE 60x40x3", "S235JRH"), ("RR 42,4x2", "S235JRH")}
assert set(ids("1.4301")) == {(p, "1.4301") for p in ("QR 40x40x2", "RE 60x40x3", "RR 42,4x2")}
assert set(ids("V2A")) == set(ids("1.4301")), "Gleichnamen der Werkstoffliste"
assert set(ids("aisi 304 rund")) == {("RR 42,4x2", "1.4301")}
assert ids("Vierkant 40x2 stahl") == [("QR 40x40x2", "S235JRH")]
assert ids("Nord") == [("RE 60x40x3", "1.4301")], "Lieferant"
assert ids("70x70") == []
assert len(ids("")) == len(alle)
ok("Intelligente Suche: 40x40x2, 60x40x3 Edelstahl, Rundrohr 42,4x2, 42x2, S235, 1.4301, V2A, Lieferant")

# ------------------------------------------------------------------ Filter und Facetten
f = mp.filtern(alle, {"kategorie": {"Edelstahl"}, "form": {"Rechteckrohr"}})
assert [mp.schluessel(z) for z in f] == [("RE 60x40x3", "1.4301")]
assert len(mp.filtern(alle, {"wand": {"2"}})) == 4
fac = mp.facetten(alle)
assert dict(fac["kategorie"]) == {"Stahl": 3, "Edelstahl": 3} and [w for w, _ in fac["wand"]] == ["2", "3"]
assert dict(fac["zustand"])[mp.ZUSTAND_TONNE] == 4 and dict(fac["zustand"])[mp.ZUSTAND_ALT] == 1
assert mp.haeufig(zeilen)[0]["profil_id"] == "RR 42,4x2" and mp.zuletzt(zeilen)[0]["zuletzt"] == "2026-11-20"
ok("Filter mit Anzahl je Wert (Materialgruppe, Profilart, Wand, Lieferant, Zustand), Zuletzt und Häufig")

# ------------------------------------------------------------------ Vergleich, Alternativen
v = mp.vergleich([re, rr])
assert v["spalten"] == ["RE 60x40x3 · 1.4301", "RR 42,4x2 · S235JRH"] and v["hinweise"]
preis = next(z for z in v["zeilen"] if z[0] == "Preis [€/m]")
assert preis[2] == 1                          # Rundrohr Stahl ist günstiger, nur Markierung
alt = mp.alternativen(re, lief, k, tab, heute=HEUTE)
arten = [(a["art"], round(a["preis_m"], 2) if a["preis_m"] else None) for a in alt]
assert ("Lieferant", 20.75) in arten and not any(a["text"].startswith("Alt") for a in alt), arten   # abgelaufen
assert any(a["art"] == "Handelslänge" and abs(a["preis_m"] - 4.70 * re["kgm"]) < EPS for a in alt)
assert all(a["quelle"] is None or mp.schluessel(a["quelle"]) == ("RE 60x40x3", "1.4301") for a in alt), \
    "Alternativen nie mit anderem Werkstoff"
assert alt[0]["preis_m"] <= alt[1]["preis_m"]
ok("Vergleich mit Hinweis bei anderer Güte, Alternativen nur gleicher Werkstoff (Lieferant, Handelslänge), abgelaufene fehlen")

# ------------------------------------------------------------------ Verschnitt je Handelslänge
e = mp.verschnitt_schaetzen([849] * 100 + [749] * 100 + [1049] * 100, 6000, 10, 142, 0.2)
assert e["stangen"] == 46, e                  # wie Patricks Vergleich 06.11.2026 (Programm 46, Excel 49)
e12 = mp.verschnitt_schaetzen([3000] * 10, 12000, 10, 142, 0.2)
e6 = mp.verschnitt_schaetzen([3000] * 10, 6000, 10, 142, 0.2)
assert e6["stangen"] == 10 and e12["stangen"] == 4 and e12["ausnutzung"] > e6["ausnutzung"], (e6, e12)
assert mp.verschnitt_schaetzen([7000], 6000)["passt_nicht"] == 1
txt = mp.verschnitt_text(re, [3000] * 10, dict(endbeschnitt=10, greiferrest=142, kerf=0.2))
assert "6 m: 10 St." in txt and "12 m: 4 St." in txt, txt
ok("Verschnittpotenzial je Handelslänge mit der Programm-Optimierung (46 Stangen wie 06.11., 12 m besser bei 3 m)")

# ------------------------------------------------------------------ Bilanz theoretisch / Einkauf
st = [dict(stange=6000, end=10, greif=142, verlust=1.0, teile=[dict(laenge=2000), dict(laenge=2000), dict(laenge=1500)]),
      dict(stange=6000, end=10, greif=142, verlust=0.4, teile=[dict(laenge=2000)])]
b = mp.bilanz({}, [(x, None) for x in st], kgm=2.0, preis_m=10.0, einkauf_eur=120.0, rest_min=1000, mindest=5)
assert abs(b["theorie_m"] - 7.5) < EPS and abs(b["einkauf_m"] - 12.0) < EPS and b["einkauf_stangen"] == 2
assert abs(b["theorie_eur"] - 75.0) < EPS and abs(b["mehr_eur"] - 45.0) < EPS and abs(b["verschnitt_pct"] - 37.5) < EPS
assert b["reste"] == [round(6000 - 10 - 2000 - 0.4)] and b["mindest_mehr"] == 3, b
ok("Bilanz: theoretischer Verbrauch gegen Einkauf, Verschnitt %, Mindestabnahme, wiederverwendbare Reste nur gemeldet")

# ------------------------------------------------------------------ Preisliste lesen
csv_text = ("Profil-ID;Werkstoff-ID;Preis [€/kg];Lieferlänge;Gültig bis;Lieferzeit;Artikelnummer\n"
            "RE 60x40x3;1.4301;4,60;6000;31.12.2026;7;A-4711\n"
            "RE 99x99x9;1.4301;4,60;6000;;;\n"
            "QR 40x40x2;S235JRH;;6000;;;\n")
r = mp.preisliste_lesen(csv_text, lieferant="Süd", k=k)
assert len(r["zeilen"]) == 1 and len(r["fehler"]) == 2, r
z = r["zeilen"][0]
assert z["basis"] == "€/kg" and abs(z["preis"] - 4.6) < EPS and z["gueltig_bis"] == "2026-12-31" and z["laenge"] == 6000
assert z["artikelnr"] == "A-4711" and z["lieferzeit"] == 7
assert mp.preisliste_lesen("a;b\n1;2")["fehler"][0][1].startswith("Kopfzeile")
ok("Preisliste (CSV/Excel) lesen: Spalten erkennen, Datum/Zahlen deutsch, unbekannte Profile gemeldet, nie angelegt")

# ------------------------------------------------------------------ mit Datenbank
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 103
db.zeilen("material_lieferanten")             # Tabelle angelegt
assert all("archiviert" in z for z in db.zeilen("profile")) and all("archiviert" in z for z in db.zeilen("werkstoffe"))
kk = db.kontext()
pid = next(p for p, z in kk.profile.items() if z.get("form") == "Rechteckrohr")
wid = next(w for w, z in kk.werkstoffe.items() if z.get("kategorie") == "Stahl")
ok(f"Schema {SCHEMA_VERSION}: Tabelle material_lieferanten, Spalte archiviert in profile und werkstoffe")

# Archivieren: aus der Auswahl, Angebote rechnen weiter
assert pid in kk.auswahl("profil")
mp.archivieren(db, "profile", pid)
assert pid not in db.kontext().auswahl("profil") and pid in db.kontext().profile
assert all(mp.schluessel(z)[0] != pid for z in mp.alle_varianten(db, alle=True))
assert any(mp.schluessel(z)[0] == pid for z in mp.alle_varianten(db, alle=True, mit_archiv=True))
mp.archivieren(db, "profile", pid, an=False)
assert pid in db.kontext().auswahl("profil")
mp.archivieren(db, "werkstoffe", wid)
assert wid not in db.kontext().auswahl("werkstoff")
mp.archivieren(db, "werkstoffe", wid, an=False)
ok("Archivieren: Profil/Werkstoff fehlt in neuen Auswahllisten, Stammdaten bleiben, zurückholen geht")

# Duplizieren
neu_id = mp.duplizieren(db, pid, pid + " NEU", wand=4)
z = next(z for z in db.zeilen("profile") if z["id"] == neu_id)
assert z["profil_id"] == pid + " NEU" and z["wand"] == 4
try:
    mp.duplizieren(db, pid, pid)
    raise AssertionError("doppelte Profil-ID")
except ValueError:
    pass
mp.werkstoff_duplizieren(db, wid, wid + "-K", werkstoff_nr="")
assert wid + "-K" in db.kontext().werkstoffe
ok("Duplizieren von Profil und Werkstoff mit neuer ID, doppelte ID abgelehnt")

# Lieferanten und aktiven Preis übernehmen
db.neu("zukauf_lieferanten", dict(name="Lieferant Süd"))
lz_id = db.neu("material_lieferanten", dict(profil_id=pid, werkstoff_id=wid, lieferant="Lieferant Süd", basis="€/m",
                                            preis=7.25, gueltig_ab="2026-11-01", mindest_stangen=3))
lz = next(z for z in db.zeilen("material_lieferanten") if z["id"] == lz_id)
assert mp.lieferant_uebernehmen(db, lz) == "Preise"
pz = next(z for z in db.zeilen("preise") if mp.schluessel(z) == (pid, wid))
assert pz["basis"] == "€/m" and abs(pz["preis"] - 7.25) < EPS and pz["lieferant"] == "Lieferant Süd" \
    and pz["mindest_stangen"] == 3
var = next(z for z in mp.alle_varianten(db) if mp.schluessel(z) == (pid, wid))
assert abs(var["preis_m"] - 7.25) < EPS and var["quelle"] == mp.QUELLE_PREISE
lz2 = dict(lz, laenge=12000, preis=6.9)
db.aendern("preise", pz["id"], "lieferlaenge", 6000)
assert mp.lieferant_uebernehmen(db, lz2) == "Lieferlängen"
assert any(mp.schluessel(z) == (pid, wid) and z["laenge"] == 12000 for z in db.zeilen("lieferlaengen"))
ok("Mehrere Lieferanten je Material; „Als aktiven Preis übernehmen“ schreibt Preise bzw. Lieferlängen")

# Umbenennen der Profil-ID zieht die Lieferantenzeilen mit (Verweise)
db.aendern("profile", next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == pid), "profil_id", pid + " X")
assert all(z["profil_id"] == pid + " X" for z in db.zeilen("material_lieferanten"))
db.aendern("profile", next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == pid + " X"), "profil_id", pid)
ok("Profil umbenennen ändert Preise, Lieferlängen und Material-Lieferanten mit")

# Preisliste importieren: neu und geändert, aktive Preise bleiben
r = mp.preisliste_lesen(f"Profil-ID;Werkstoff-ID;€/m\n{pid};{wid};7,10\n", lieferant="Lieferant Süd", k=db.kontext())
assert mp.preisliste_importieren(db, r["zeilen"]) == dict(neu=0, geaendert=1)
assert abs(next(z for z in db.zeilen("material_lieferanten") if z["id"] == lz_id)["preis"] - 7.10) < EPS
assert abs(next(z for z in db.zeilen("preise") if mp.schluessel(z) == (pid, wid))["preis"] - 7.25) < EPS
ok("Preisliste importieren: bestehende Lieferantenzeile geändert, aktiver Preis unverändert")

# Mehrfach ändern
pids = [z for z in mp.alle_varianten(db) if mp.schluessel(z) == (pid, wid)]
assert mp.mehrfach_aendern(db, pids, "preise", None, None, preis_faktor=1.10) == 1
assert abs(next(z for z in db.zeilen("preise") if mp.schluessel(z) == (pid, wid))["preis"] - 7.975) < 1e-4
assert mp.mehrfach_aendern(db, pids, "preise", "lieferant", "Nord") == 1
try:
    mp.mehrfach_aendern(db, pids, "werkstoffe", "dichte", 1.0)
    raise AssertionError("Dichte darf nicht mehrfach geändert werden")
except ValueError:
    pass
ok("Mehrfach ändern: Preis +10 %, Lieferant; Dichte/Güte/Maße gesperrt")

# Favoriten (nur dieser Arbeitsplatz)
mp.favorit_setzen(db, pid, wid)
assert mp.favoriten(db) == [[pid, wid]] and next(z for z in mp.alle_varianten(db) if mp.schluessel(z) == (pid, wid))["favorit"]
from rohrlaser import teilen  # noqa: E402
assert mp.FAVORITEN in teilen.LOKAL
mp.favorit_setzen(db, pid, wid, an=False)
assert mp.favoriten(db) == []
ok("Favoriten je Arbeitsplatz (nicht im Abgleich)")

# CSV-Export
t = mp.csv_export(mp.alle_varianten(db))
assert t.splitlines()[0].startswith("Profil-ID;Profilform") and pid in t
ok("Export als CSV (Semikolon, deutsche Zahlen)")

# ------------------------------------------------------------------ Dichte im Snapshot
kk, tt = db.kontext(), db.tabellen()
kopf = dict(maschine=next(iter(kk.maschinen)), stange=6000)
pos = [dict(profil_id=pid, werkstoff_id=wid, laenge=1000, stueck=1)]
pb = rechnen.preisbasis_aus(kopf, pos, kk, tt)
assert pb["werkstoff_dichte"] == {wid: kk.werkstoffe[wid]["dichte"]} and "archiviert" not in pb["profile"][pid]
wz = next(z for z in db.zeilen("werkstoffe") if z["werkstoff_id"] == wid)
db.aendern("werkstoffe", wz["id"], "dichte", 9.99)
k2, t2 = db.kontext(), db.tabellen()
kf, _ = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k2, t2)
assert kf.werkstoffe[wid]["dichte"] == wz["dichte"], "festgeschriebene Dichte gilt"
abw = rechnen.preisbasis_abweichung(dict(kopf, preisbasis=pb), k2, t2)
assert any(a.startswith(f"Dichte {wid}") for a in abw), abw
alt_pb = {n: v for n, v in pb.items() if n != "werkstoff_dichte"}
kf, _ = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=alt_pb), k2, t2)
assert kf.werkstoffe[wid]["dichte"] == 9.99, "ältere Snapshots ohne Dichte: aktuelle Dichte wie bisher"
assert not any(a.startswith("Dichte") for a in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=alt_pb), k2, t2))
db.aendern("werkstoffe", wz["id"], "dichte", wz["dichte"])
alt_profil = dict(pb, profile={p: {n: v for n, v in z.items() if n != "archiviert"} for p, z in pb["profile"].items()})
mp.archivieren(db, "profile", pid)
assert not any(a.startswith("Profil") for a in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=alt_profil),
                                                                             db.kontext(), db.tabellen()))
mp.archivieren(db, "profile", pid, an=False)
ok("Angebots-Snapshot hält die Dichte fest; ältere Snapshots unverändert; Archivieren meldet keine Profiländerung")

# ------------------------------------------------------------------ Tempo mit 30.000 Varianten
kg = Kontext()
kg.werkstoffe = {f"W{i}": dict(werkstoff_id=f"W{i}", kategorie=("Stahl", "Edelstahl", "Aluminium")[i % 3],
                               werkstoff=f"Werkstoff {i}", dichte=7.85, tonnenpreis=1000 + i) for i in range(60)}
kg.profile = {}
for a in range(20, 520, 1):
    pid_ = f"QR {a}x{a}x3"
    kg.profile[pid_] = dict(profil_id=pid_, form="Quadratrohr", a=a, b=a, wand=3)
t0 = time.perf_counter()
gross = mp.varianten(kg, dict(preise=[], lieferlaengen=[]), alle=True)
t_bau = time.perf_counter() - t0
assert len(gross) == 30000, len(gross)
t0 = time.perf_counter()
treffer = mp.suchen(gross, "100x100 edelstahl")
t_such = time.perf_counter() - t0
assert len(treffer) == 20 and all(z["a"] == 100 for z in treffer)
t0 = time.perf_counter()
mp.facetten(gross)
mp.filtern(gross, {"kategorie": {"Aluminium"}})
t_filter = time.perf_counter() - t0
assert t_such < 1.0 and t_filter < 1.5 and t_bau < 8.0, (t_bau, t_such, t_filter)
ok(f"30.000 Varianten: aufbauen {t_bau:.2f} s, Suche {t_such:.2f} s, Filter + Facetten {t_filter:.2f} s")

# ------------------------------------------------------------------ lokale Prüfvorschläge (Phase 6)
from rohrlaser import material_ki as mk  # noqa: E402
k3 = Kontext()
k3.werkstoffe = dict(k.werkstoffe)
k3.werkstoffe["AlMgSi"] = dict(werkstoff_id="AlMgSi", kategorie="Aluminium", dichte=7.85)       # Tippfehler
k3.werkstoffe["OHNE"] = dict(werkstoff_id="OHNE", kategorie="Stahl")
k3.profile = dict(k.profile)
k3.profile["QR 40x40x2 alt"] = dict(profil_id="QR 40x40x2 alt", form="Quadratrohr", a=40, b=40, wand=2)
for i, a in enumerate((50, 60, 70, 80)):
    k3.profile[f"QR {a}x{a}x2"] = dict(profil_id=f"QR {a}x{a}x2", form="Quadratrohr", a=a, b=a, wand=2)
tab3 = dict(preise=[dict(profil_id=f"QR {a}x{a}x2", werkstoff_id="S235JRH", basis="€/kg", preis=1.3, lieferant="Nord",
                         gueltig_ab="2026-11-20") for a in (50, 60, 70)]
            + [dict(profil_id="QR 80x80x2", werkstoff_id="S235JRH", basis="€/kg", preis=13.0, lieferant="Nord",
                    gueltig_ab="2026-11-20"),
               dict(profil_id="RE 60x40x3", werkstoff_id="1.4301", basis="€/kg", preis=4.85, gueltig_ab="2026-01-01")],
            lieferlaengen=[])
z3 = mp.varianten(k3, tab3, lief, nutzung={("RE 60x40x3", "1.4301"): (2, "2026-11-20"),
                                          ("RR 42,4x2", "S235JRH"): (4, "2026-11-20")}, heute=HEUTE)
bef = mk.pruefen(z3, k3, tab3, lief, verlauf={("QR 50x50x2", "S235JRH"): [3.0, 4.2]},
                 einst=dict(preisalter_tage=30), heute=HEUTE)
typen = {(b["typ"], b["material"]) for b in bef}
assert ("dichte", "AlMgSi") in typen and ("dichte_fehlt", "OHNE") in typen, typen
assert ("ausreisser", "QR 80x80x2 · S235JRH") in typen
assert ("dublette", "QR 40x40x2 alt") in typen
assert ("lieferant", "RE 60x40x3 · 1.4301") in typen and ("alt", "RE 60x40x3 · 1.4301") in typen
assert ("tonnenpreis", "RR 42,4x2 · S235JRH") in typen and ("sprung", "QR 50x50x2 · S235JRH") in typen
g = next(b for b in bef if b["typ"] == "guenstiger")
assert g["aktion"] == "preis_uebernehmen" and "Süd" in g["text"] and g["material"] == "RE 60x40x3 · 1.4301"
assert all(b["aktion"] in (None, "preis_uebernehmen", "archivieren") for b in bef), "keine Aktion ändert Güte/Dichte"
assert next(b for b in bef if b["typ"] == "dichte")["aktion"] is None
assert [b["art"] for b in bef] == sorted([b["art"] for b in bef], key=lambda a: {"WARNUNG": 0, "VORSCHLAG": 1}.get(a, 2))
ok("Prüfvorschläge: Dichte unüblich/fehlt, Ausreißer €/kg, Dublette, ohne Lieferant, alter Preis, Tonnenpreis, Sprung, "
   "günstigerer Lieferant; nur Preis übernehmen und Archivieren als Aktion")

# mit Datenbank: Übernehmen und Ablehnen werden protokolliert
db.neu("material_lieferanten", dict(profil_id=pid, werkstoff_id=wid, lieferant="Lieferant Süd", basis="€/m",
                                    preis=1.00, laenge=6000, gueltig_ab="2026-01-01"))
bef = mk.alle(db)
g = next(b for b in bef if b["typ"] == "guenstiger" and b["material"] == f"{pid} · {wid}")
assert "übernommen" in mk.anwenden(db, g)
assert abs(next(z for z in db.zeilen("preise") if mp.schluessel(z) == (pid, wid))["preis"] - 1.0) < EPS
from rohrlaser import ki_protokoll  # noqa: E402
assert any(a["agent"] == mk.AGENT and a["aktion"] == "Vorschlag übernommen" for a in ki_protokoll.liste(db))
h = next(b for b in mk.alle(db) if b["art"] in ("HINWEIS", "WARNUNG", "VORSCHLAG"))
mk.ablehnen(db, h)
assert h["schluessel"] not in {b["schluessel"] for b in mk.alle(db)}
ok("Übernehmen nur per Aufruf mit Protokoll; abgelehnte Befunde kommen nicht wieder")

print("Alle Prüfungen der Materialplattform bestanden.")
