"""Lieferlängen: 6-m- gegen 12-m-Stangen (12 m nur als Zuschnittsbasis, max. Beladelänge der Maschine).

Aufruf: python tests/test_lieferlaengen.py
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import optimierung as opt, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import TABELLE, pruefen  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
einst = db.einstellungen()
kopf = dict(maschine="RL-1", stange=6000)     # RL-1: Endbeschnitt 20, Greiferrest 80, Schnittverlust 0,3, max. 6.500


def teile(n, laenge, a=True, b=True):
    return [opt.Teil(13, 10, "A", i, laenge, a, b, 100, 100) for i in range(1, n + 1)]


def gruppe(t):
    g = opt.Gruppe("QR 40x40x3", "S235-10219", 6000, 20, 80, 0.3, 2)
    g.teile = t
    return g


def werkstuecke(st):
    return [[l for l, _ in s] for s in st]


# ------------------------------------------------------------------ 1-5: Zuschnitt einer 12-m-Stange
# Werkstück = 20 + Teil + 0,3 + 80: Teil 3.899,7 -> Werkstück 4.000
st = opt.zuschnitt(gruppe(teile(3, 3899.7)), 12000, 6500, 0)
assert werkstuecke(st) == [[4000, 4000, 4000]], werkstuecke(st)
opt.pruefe_zuschnitt(gruppe(teile(3, 3899.7)), st, 12000, 6500, 0)
# 2 × 6.000
st = opt.zuschnitt(gruppe(teile(2, 5899.7)), 12000, 6500, 0)
assert werkstuecke(st) == [[6000, 6000]], werkstuecke(st)
# Werkstück genau 6.500 mm (= max. Beladelänge) wird angenommen, 6.500 + 5.497 mit 3 mm Zuschnitt
g = gruppe(teile(1, 6399.7) + teile(1, 5396.7))
st = opt.zuschnitt(g, 12000, 6500, 3)
assert werkstuecke(st) == [[6500, 5497]] and opt.zuschnitt_belegt([6500, 5497], 3) == 12000, werkstuecke(st)
opt.pruefe_zuschnitt(g, st, 12000, 6500, 3)
# über 6.500 mm: abgelehnt (kein Werkstück, Variante nicht ausführbar)
assert opt.zuschnitt(gruppe(teile(1, 6400)), 12000, 6500, 3) is None
v = rechnen.variante_planen(gruppe(teile(1, 6400)), 12000, dict(max_stange=6500), 3)
assert v["fehler"] == "Teil passt in kein Werkstück bis 6.500 mm" and not v["stangen"], v
# Kontrolle schlägt bei einem zu langen Werkstück an
g = gruppe(teile(1, 6399.7))
try:
    opt.pruefe_zuschnitt(g, [[(6600, [(g.teile[0], False)])]], 12000, 6500, 3)
    raise SystemExit("Werkstück über 6.500 mm nicht erkannt")
except AssertionError as e:
    assert "länger als die Maschine laden kann" in str(e)
# Schnittverlust des Zuschnitts verhindert die sonst passende Aufteilung 3 × 4.000
g = gruppe(teile(3, 3899.7))
st = opt.zuschnitt(g, 12000, 6500, 3)
assert len(st) == 2 and sum(len(s) for s in st) == 3, werkstuecke(st)
opt.pruefe_zuschnitt(g, st, 12000, 6500, 3)
# kein Werkstück länger als die Maschine: RL-2 lädt 8.500 mm
g = gruppe(teile(4, 2700))
st = opt.zuschnitt(g, 12000, 8500, 3)
assert max(l for s in st for l, _ in s) <= 8500
opt.pruefe_zuschnitt(g, st, 12000, 8500, 3)
print("Zuschnitt OK")


# ------------------------------------------------------------------ Vergleich im Angebot
def pos(laenge, stueck, profil="QR 40x40x3", werkstoff="S235-10219", nr=10):
    return dict(pos=nr, artikel=f"T{nr}", profil_id=profil, werkstoff_id=werkstoff, laenge=laenge, stueck=stueck)


def vergleich(positionen, kopf=kopf):
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, positionen, k, tab, einst)
    rechnen.optimieren(kopf, positionen, k, tab, einst)
    return erg, [rechnen.laengen_bewerten(v, kopf, positionen, k, tab, einst) for v in erg.get("laengen", [])]


# ohne Lieferlängen: kein Vergleich, Ergebnis wie bisher
erg0, b = vergleich([pos(3100, 30)])
assert "laengen" not in erg0 and not b
kenn0 = erg0["kennung"]
assert kenn0 == rechnen.eingabe_kennung(kopf, [pos(3100, 30)], db.kontext())      # ältere Aufrufe: gleiche Kennung

z12 = db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=12000,
                                   bemerkung="Zuschnitt beim Lieferanten"))
assert pruefen(TABELLE["lieferlaengen"], db.zeilen("lieferlaengen")[0], db.kontext()) == "OK"
assert pruefen(TABELLE["lieferlaengen"], dict(db.zeilen("lieferlaengen")[0], basis="€/kg"), db.kontext()).startswith(
    "FEHLER: Preisbasis und Preis")

# 7) 3.100 mm: 1 Teil je 6-m-Stange, 3 je 12-m-Stange -> 12 m wirtschaftlich sinnvoll
erg, (b,) = vergleich([pos(3100, 30)])
assert erg["kennung"] != kenn0                                  # Lieferlängen gehören zur Prüfsumme
assert erg["stangen"] == erg0["stangen"]                        # Planung selbst unverändert (Übernahme fehlt)
basis, alt = b["varianten"]
assert (basis["laenge"], basis["lieferstangen"], basis["werkstuecke"]) == (6000, 30, 30), basis
assert (alt["laenge"], alt["zuschnitt"], alt["lieferstangen"], alt["werkstuecke"]) == (12000, True, 10, 30), alt
assert alt["werkstueck_laengen"] == [3201] and alt["zuschnitte"] == 30, alt     # 2 + Rest abtrennen
assert abs(alt["material"] - basis["material"] * 2 / 3) < 0.01 and not alt["fehlt"]
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE and b["titel"] == "12-m-Stangen wirtschaftlich sinnvoll", b
assert "Grenzen 20 € und 3 % erreicht" in b["begruendung"], b["begruendung"]
assert basis["verschnitt_mm"] == 180000 - 93000 and alt["verschnitt_mm"] == 120000 - 93000

# 10/13) 2.900 mm: 2 Teile je 6 m, 4 je 12 m, gleiche Beladungen -> gleiche Kosten, keine 12-m-Empfehlung
_, (b,) = vergleich([pos(2900, 20)])
basis, alt = b["varianten"]
assert (basis["lieferstangen"], alt["lieferstangen"], basis["werkstuecke"], alt["werkstuecke"]) == (10, 5, 10, 10)
assert abs(basis["gesamt"] - alt["gesamt"]) < 1e-6
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL and "gleiche Gesamtkosten" in b["begruendung"], b

# Ersparnis unter den Grenzen (€ oder %): keine Empfehlung
einst_hoch = dict(einst, laenge_mindest_eur=1000)
k, tab = db.kontext(), db.tabellen()
e = rechnen.optimieren(kopf, [pos(3100, 30)], k, tab, einst_hoch)
b = rechnen.laengen_bewerten(e["laengen"][0], kopf, [pos(3100, 30)], k, tab, einst_hoch)
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL and "unter den Grenzen 1.000 €" not in b["begruendung"]
assert "unter den Grenzen" in b["begruendung"], b["begruendung"]
b = rechnen.laengen_bewerten(e["laengen"][0], kopf, [pos(3100, 30)], k, tab, dict(einst, laenge_mindest_anteil=0.5))
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL, b

# 6) 12 m spart Verschnitt, kostet aber mehr (Längenzuschlag): 6 m empfehlen
db.aendern("lieferlaengen", z12, "basis", "€/kg")
db.aendern("lieferlaengen", z12, "preis", 2.40)
_, (b,) = vergleich([pos(3100, 30)])
basis, alt = b["varianten"]
assert alt["verschnitt_mm"] < basis["verschnitt_mm"] and alt["gesamt"] > basis["gesamt"]
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL and "teurer" in b["begruendung"], b
assert b["titel"] == "Kein ausreichender Kostenvorteil für 12 m"
db.aendern("lieferlaengen", z12, "preis", 1.50)            # gleicher €/kg-Preis wie 'Preise'
_, (b,) = vergleich([pos(3100, 30)])
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE

# Stangenwechsel je Beladung zählt mit: 12 m mit mehr Beladungen als 6 m
_, (b,) = vergleich([pos(3100, 30)])
assert b["varianten"][1]["werkstueck_kosten"] == b["varianten"][0]["werkstueck_kosten"] > 0
print("Empfehlung OK")

# 5/8) Profil ausgenommen: keine 12-m-Planung, Hinweis
pid = next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == "QR 40x40x3")
db.aendern("profile", pid, "laengenvergleich", "nein")
erg, (b,) = vergleich([pos(3100, 30)])
assert b["ausgenommen"] and [v["laenge"] for v in b["varianten"]] == [6000], b
assert b["empfehlung"] == rechnen.LAENGE_STANDARD and "ausgenommen" in b["begruendung"]
db.aendern("profile", pid, "laengenvergleich", None)
# 8) kleines Profil ohne 12-m-Zeile: kein Vergleich, auch nicht im selben Angebot neben einem großen
erg, bs = vergleich([pos(3100, 30), pos(3100, 10, profil="RR 42,4x2,0", nr=20)])
assert [b["profil"] for b in bs] == ["QR 40x40x3"], bs

# 11) Nur 12 m lieferbar: keine künstliche 6-m-Alternative
preis = next(z for z in db.zeilen("preise") if z["profil_id"] == "QR 40x40x3" and z["werkstoff_id"] == "S235-10219")
db.aendern("preise", preis["id"], "lieferlaenge", None)
_, (b,) = vergleich([pos(3100, 30)])
assert not b["basis_lieferbar"] and [v["laenge"] for v in b["varianten"]] == [12000], b
assert b["empfehlung"] == rechnen.LAENGE_NUR_ALTERNATIVE and b["beste"] == 12000, b
assert b["titel"] == "6 m nicht lieferbar – 12-m-Stangen verwenden"
db.aendern("preise", preis["id"], "lieferlaenge", 6000)

# 12) Fehlender Preis: 'Preise' in €/Stange für 6 m, Lieferlänge 12 m ohne Preis -> Vergleich nicht möglich
db.neu("lieferlaengen", dict(profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=12000))
_, (b,) = vergleich([pos(3100, 30, profil="RR 42,4x2,0", werkstoff="1.4301")])
assert b["empfehlung"] == rechnen.LAENGE_ANGABEN_FEHLEN, b
assert b["titel"] == "Vergleich nicht möglich – Angaben fehlen" and "Preis für 12.000 mm fehlt" in b["begruendung"]
# mit Preis je 12-m-Stange: vergleichbar
z = next(z for z in db.zeilen("lieferlaengen") if z["profil_id"] == "RR 42,4x2,0")
db.aendern("lieferlaengen", z["id"], "basis", "€/Stange")
db.aendern("lieferlaengen", z["id"], "preis", 130.0)
_, (b,) = vergleich([pos(3100, 30, profil="RR 42,4x2,0", werkstoff="1.4301")])
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE and abs(b["varianten"][1]["material"] - 10 * 130) < 1e-6, b
# fehlender Stangenwechsel der Maschine, wenn die Beladungen sich unterscheiden: nie still mit 0 rechnen
m = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "RL-1")
db.aendern("maschinen", m["id"], "stangenwechsel", None)
_, (b,) = vergleich([pos(2000, 6)])         # 6 m: 3 Stangen à 2 Teile; 12 m: 2 Stangen mit je 1 Werkstück à 3 Teilen
assert [(v["lieferstangen"], v["werkstuecke"]) for v in b["varianten"]] == [(3, 3), (2, 2)], b["varianten"]
assert b["empfehlung"] == rechnen.LAENGE_ANGABEN_FEHLEN and "Stangenwechsel der Maschine fehlt" in b["begruendung"]
db.aendern("maschinen", m["id"], "stangenwechsel", 30)
print("Verfügbarkeit OK")

# 14) Werkstoffe nie gemischt, mehrere Positionen derselben Gruppe gemeinsam
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="1.4301", laenge=12000))
# ohne Zeile in 'Preise' (Tonnenpreis) ist dann nur 12 m lieferbar ...
assert [len(b["varianten"]) for b in vergleich([pos(3100, 10, werkstoff="1.4301")])[1]] == [1]
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="1.4301", laenge=6000))   # ... mit 6 m beide
erg, bs = vergleich([pos(3100, 10), pos(2800, 5, nr=20), pos(3100, 10, werkstoff="1.4301", nr=30)])
assert sorted((b["werkstoff"], sum(1 for _ in b["varianten"])) for b in bs) == [("1.4301", 2), ("S235-10219", 2)]
s235 = next(b for b in bs if b["werkstoff"] == "S235-10219")
assert s235["varianten"][0]["nutz_mm"] == 10 * 3100 + 5 * 2800
# Reproduzierbar: zweimal gleiches Ergebnis
e1 = rechnen.optimieren(kopf, [pos(3100, 10), pos(2800, 5, nr=20)], db.kontext(), db.tabellen(), einst)
e2 = rechnen.optimieren(kopf, [pos(3100, 10), pos(2800, 5, nr=20)], db.kontext(), db.tabellen(), einst)
assert json.dumps(e1, sort_keys=True, default=str) == json.dumps(e2, sort_keys=True, default=str)

# 9) Keine Reststückverwaltung: Vergleich und Optimierung ändern die Datenbank nicht, keine Bestandstabelle
vorher = {t: db.anzahl(t) for t in ("lieferlaengen", "preise", "profile")}
con = sqlite3.connect(db.pfad)
tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert not {t for t in tabellen if "rest" in t or "bestand" in t or "lager" in t}, tabellen
vergleich([pos(3100, 30)])
assert {t: db.anzahl(t) for t in vorher} == vorher
print("Gruppen OK")

# Festgeschriebene Preise: Lieferlängen gehören zum Snapshot
k, tab = db.kontext(), db.tabellen()
pb = rechnen.preisbasis_aus(kopf, [pos(3100, 30)], k, tab)
assert [z["laenge"] for z in pb["lieferlaengen"]] == [12000], pb["lieferlaengen"]
db.aendern("lieferlaengen", z12, "preis", 1.90)
k2, tab2 = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), db.kontext(), db.tabellen())
assert [z["preis"] for z in tab2["lieferlaengen"] if z["profil_id"] == "QR 40x40x3" and
        z["werkstoff_id"] == "S235-10219"] == [1.50]
assert "Lieferlängen geändert" in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=pb), db.kontext(), db.tabellen())
alt_pb = {n: w for n, w in pb.items() if n != "lieferlaengen"}       # Snapshot vor den Lieferlängen
assert rechnen.preisbasis_abweichung(dict(kopf, preisbasis=alt_pb), db.kontext(), db.tabellen()) == []
print("Preisbasis OK")
print("Alle Tests Lieferlängen OK")
