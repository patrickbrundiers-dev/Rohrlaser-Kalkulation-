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

from rohrlaser import ausgabe, optimierung as opt, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import ALTE_MASCHINEN, MASCHINE_WERTE, TABELLE, pruefen  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
# T03 mit den Werten der früheren Beispielmaschine RL-1 (die Rechenbeispiele unten beziehen sich darauf):
# Endbeschnitt 20, Greiferrest 80, Schnittverlust 0,3, max. 6.500, Stangenwechsel 30 s
_t03 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
for _feld, _wert in zip(MASCHINE_WERTE, ALTE_MASCHINEN["RL-1"][1]):
    db.aendern("maschinen", _t03["id"], _feld, _wert)
einst = db.einstellungen()
assert einst["laenge_vergleich"] == "nein"      # Vorgabe: kein Vergleich (Patrick 22.10.2026)
einst["laenge_vergleich"] = "ja"                # die Tests unten prüfen den Vergleich
kopf = dict(maschine="T03", stange=6000)


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
# kein Werkstück länger als die Maschine: eine Maschine mit 8.500 mm Beladelänge
g = gruppe(teile(4, 2700))
st = opt.zuschnitt(g, 12000, 8500, 3)
assert max(l for s in st for l, _ in s) <= 8500
opt.pruefe_zuschnitt(g, st, 12000, 8500, 3)
# Raster der Ziel-Längen (Patrick 28.10.2026, optimale Zuschnittslänge): gemischte Teile passen in 3 statt 4
# 12-m-Stangen, weil auch Werkstücke wie 5.851 mm (keine feste Teilung von 12 m) ausprobiert werden
g = opt.Gruppe("QR 40x40x3", "S235-10219", 6000, 20, 80, 0.3, 2)
g.teile = [opt.Teil(13, 10, "A", i, l, True, True, 100, 100)
           for i, l in enumerate([850, 850, 850, 1240, 2350, 2980, 3600, 3600, 3600, 4150, 4150, 5200])]
st = opt.zuschnitt(g, 12000, 6500, 3, 2500, 50)
assert len(st) == 3, werkstuecke(st)
opt.pruefe_zuschnitt(g, st, 12000, 6500, 3, 2500)
assert 5851 in opt.zuschnitt_ziele(g, 12000, 6500, 3, 2500, 50) and 5998 in opt.zuschnitt_ziele(g, 12000, 6500, 3,
                                                                                              2500, 50)
_viele = opt.replace(g, teile=g.teile * 30)                  # über 300 Teile: nur die festen Teilungen (Rechenzeit)
assert 5851 not in opt.zuschnitt_ziele(_viele, 12000, 6500, 3, 2500, 50)
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

# Vergleich in den Einstellungen aus (Vorgabe): keine Lieferlängen, Planung wie mit 6 m; andere Prüfsumme
_aus = rechnen.optimieren(kopf, [pos(3100, 30)], db.kontext(), db.tabellen(), dict(einst, laenge_vergleich="nein"))
assert "laengen" not in _aus and _aus["stangen"] == erg0["stangen"]

# 7) 3.100 mm: 1 Teil je 6-m-Stange, 3 je 12-m-Stange -> 12 m wirtschaftlich sinnvoll
erg, (b,) = vergleich([pos(3100, 30)])
assert erg["kennung"] != kenn0                                  # Lieferlängen gehören zur Prüfsumme
assert erg["stangen"] == erg0["stangen"]                        # Planung selbst unverändert (Übernahme fehlt)
basis, alt = b["varianten"]
assert (basis["laenge"], basis["lieferstangen"], basis["werkstuecke"]) == (6000, 30, 30), basis
assert (alt["laenge"], alt["zuschnitt"], alt["lieferstangen"], alt["werkstuecke"]) == (12000, True, 10, 30), alt
# Stange 3.201 + 50 mm Puffer; 2 Schnitte je Lieferstange, die Restlänge hängt an der letzten Stange
# (12.000 − 2 × 3.251 − 2 × 3 = 5.492)
assert alt["werkstueck_laengen"] == [5492, 3251] and alt["zuschnitte"] == 20, alt
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
# auch mit ausgeschaltetem Vergleich wird dann mit 12 m geplant
_aus = rechnen.optimieren(kopf, [pos(3100, 30)], db.kontext(), db.tabellen(), dict(einst, laenge_vergleich="nein"))
assert {s["stange"] for s in _aus["stangen"]} == {12000} and _aus["laengen"][0]["gewaehlt"] == 12000, _aus["laengen"]
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
m = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
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

# 9) Vergleich und Optimierung ändern die Datenbank nicht. Lager und Reststücke (lager.py, Patrick 27.10.2026:
# optional, Vorgabe aus) bleiben ohne Einstellung aus und leer; der Vergleich rechnet keinen Reststückwert an
vorher = {t: db.anzahl(t) for t in ("lieferlaengen", "preise", "profile")}
con = sqlite3.connect(db.pfad)
assert db.einstellung("lager_aktiv") == "nein" and db.einstellung("reste_aktiv") == "nein"
assert all(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
           for t in ("lager_bestand", "lager_reservierung", "lager_auftraege", "lager_buchungen"))
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

# ------------------------------------------------------------------ Übernahme einer Lieferlänge
db.aendern("lieferlaengen", z12, "preis", 1.50)
k, tab = db.kontext(), db.tabellen()
P = [pos(3100, 30)]
ohne = rechnen.optimieren(kopf, P, k, tab, einst)
schl = ohne["laengen"][0]["schluessel"]
assert schl == "QR 40x40x3|S235-10219||6000" and ohne["laengen"][0]["gewaehlt"] is None
kopf12 = dict(kopf, laengenwahl={schl: 12000})
erg = rechnen.optimieren(kopf12, P, k, tab, einst)
assert erg["kennung"] != ohne["kennung"] and erg["laengen"][0]["gewaehlt"] == 12000
assert len(erg["stangen"]) == 10 and all(s["stange"] == 12000 and s["grundlaenge"] == 6000 for s in erg["stangen"])
s0 = erg["stangen"][0]
assert [w["laenge"] for w in s0["werkstuecke"]] == [3251, 3251, 5492] and [t["werkstueck"] for t in s0["teile"]] == [1, 2, 3]
assert [w["von"] for w in s0["werkstuecke"]] == [0, 3254, 6508], s0["werkstuecke"]
assert s0["teile"][1]["von"] == 3254 + 20 and s0["zuschnitt"].startswith("Zuschnitt beim Lieferanten: 3.251 + 3.251")
assert rechnen.beladungen(erg["stangen"]) == 30
sw = rechnen.stangen_werte(erg, kopf12, P, k, tab)
assert all(w["pruefung"] == "OK" for w in sw), sw
assert abs(sum(w["rest"] for w in sw) - (120000 - 93000 - sum(s["end"] + s["verlust"] for s in erg["stangen"]))) < 1e-6
zk, su = rechnen.kalkulation(kopf12, P, erg, k, tab, einst)
_, su6 = rechnen.kalkulation(kopf, P, ohne, k, tab, einst)
b = rechnen.laengen_bewerten(ohne["laengen"][0], kopf, P, k, tab, einst)
assert abs(su["material"] - b["varianten"][1]["material"]) < 0.01 and abs(su6["material"] - b["varianten"][0]["material"]) < 0.01
assert (su["stangen"], su["beladungen"], su6["beladungen"]) == (10, 30, 30)
assert su["stangenwechsel_kosten"] == su6["stangenwechsel_kosten"] and su["verkauf"] < su6["verkauf"]
assert zk[0]["eingeplant"] == 30 and not zk[0]["nicht_eingeplant"]
a = erg["auswertung"][0]
assert (a["stange"], a["grundlaenge"], a["stangen"]) == (12000, 6000, 10) and a["bewertung"] == "Lieferlänge 12 m"
z = rechnen.auswertung_zeilen(erg, sw)[0]
assert z["bedarf"] == 120 and z["laenge"] == 93
# Schnittplan, Stangenbild, Werkstattpapiere: jedes Werkstück wie eine eigene Stange, kein Zuschnitt sichtbar
anz = rechnen.anzeige_stangen(erg, sw)
assert len(anz) == 30 and [s["nr"] for s, _ in anz] == list(range(1, 31))
assert sorted(s["stange"] for s, _ in anz) == [3251] * 20 + [5492] * 10
for s, w in anz:
    assert (s["end"], s["greif"]) == (20, 80) and "zuschnitt" not in s and "werkstuecke" not in s
    assert len(s["teile"]) == 1 and s["teile"][0]["von"] == 20 and "werkstueck" not in s["teile"][0]
    assert w["pruefung"] == "OK" and abs(w["rest"] - 80) < 1e-6
    assert abs(w["belegt"] + w["rest"] - s["stange"]) < 1e-6
assert abs(sum(w["kosten"] for _, w in anz) - sum(w["kosten"] for w in sw)) < 1e-6
# Gewicht nach Länge: die Stücke einer Lieferstange sind zusammen 12.000 − 2 × 3 mm Sägeschnitt (kein Abfall)
assert abs(sum(w["gewicht"] for _, w in anz) * 12000 / 11994 - sum(w["gewicht"] for w in sw)) < 1e-6
assert [s["nr"] for s in rechnen.anzeige_stangen(ohne)] == list(range(1, 31))      # normale Stangen unverändert
wp = ausgabe.werkstatt(kopf12, P, erg, k, tab)
assert sorted((m["stange"], m["stangen"]) for m in wp["material"]) == [(3251, 20), (5492, 10)], wp["material"]
assert sorted(m["anzahl"] for m in wp["muster"]) == [10, 20] and all(m["teile"][0]["von"] == 20 for m in wp["muster"])
# Stückzahl ändern: Wahl bleibt (Schlüssel = Gruppe), Planung neu
erg = rechnen.optimieren(kopf12, [pos(3100, 31)], k, tab, einst)
assert len(erg["stangen"]) == 11 and sum(len(s["werkstuecke"]) for s in erg["stangen"]) == 31
# übernommene Länge, die es nicht mehr gibt: wieder die Stangenlänge des Angebots
erg = rechnen.optimieren(dict(kopf, laengenwahl={schl: 9000}), P, k, tab, einst)
assert all(s["stange"] == 6000 and "grundlaenge" not in s for s in erg["stangen"])
# Lieferlänge bis zur Beladelänge (6.500 mm bei T03): ohne Zuschnitt direkt geladen
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=6500))
k, tab = db.kontext(), db.tabellen()
erg = rechnen.optimieren(dict(kopf, laengenwahl={schl: 6500}), [pos(3100, 4)], k, tab, einst)
assert all(s["stange"] == 6500 and not s.get("werkstuecke") for s in erg["stangen"]) and len(erg["stangen"]) == 2
assert all(w["pruefung"] == "OK" for w in rechnen.stangen_werte(erg, kopf, [pos(3100, 4)], k, tab))
# Staffelpreise (auto): je Menge die empfohlene Lieferlänge; 6,5 m (2 Teile je Stange, 97,5 m) schlägt hier 12 m
erg = rechnen.optimieren(kopf, P, k, tab, einst, auto=True)
assert erg["laengen"][0]["gewaehlt"] == 6500 and len(erg["stangen"]) == 15
for z in db.zeilen("lieferlaengen"):
    if z["laenge"] == 6500:
        db.loeschen("lieferlaengen", [z["id"]])
k, tab = db.kontext(), db.tabellen()
erg = rechnen.optimieren(kopf, P, k, tab, einst, auto=True)
assert erg["laengen"][0]["gewaehlt"] == 12000 and len(erg["stangen"]) == 10
erg = rechnen.optimieren(kopf, [pos(2900, 20)], k, tab, einst, auto=True)       # kein Vorteil: 6 m
assert erg["laengen"][0]["gewaehlt"] is None and all(s["stange"] == 6000 for s in erg["stangen"])
# nur 12 m lieferbar: ohne Übernahme mit 12 m geplant
db.aendern("preise", preis["id"], "lieferlaenge", None)
k, tab = db.kontext(), db.tabellen()
erg = rechnen.optimieren(kopf, P, k, tab, einst)
assert erg["laengen"][0]["gewaehlt"] == 12000 and all(s["stange"] == 12000 for s in erg["stangen"])
db.aendern("preise", preis["id"], "lieferlaenge", 6000)
print("Übernahme OK")

# ------------------------------------------------------------------ ohne Eintrag: ab Hüllkreis-Ø 70 mm auch 12 m
k, tab = db.kontext(), db.tabellen()
gross = [pos(3100, 30, profil="RE 120x60x4", werkstoff="S355-10219")]      # Hüllkreis 134 mm, keine Zeile
assert not [z for z in db.zeilen("lieferlaengen") if z["profil_id"] == "RE 120x60x4"]
erg = rechnen.optimieren(kopf, gross, k, tab, einst)
(vg,) = erg["laengen"]
assert vg["automatisch"] and vg["basis_lieferbar"] and [v["laenge"] for v in vg["varianten"]] == [6000, 12000]
b = rechnen.laengen_bewerten(vg, kopf, gross, k, tab, einst)
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE, b                  # Preis wie 'Preise' bzw. Tonnenpreis
assert all(s["stange"] == 6000 for s in erg["stangen"])                 # geplant erst nach Übernahme
# Einstellung 0 = aus, andere Grenze, Profil ausgenommen; kleine Profile (RR 48,3, QR 40) nie automatisch
assert "laengen" not in rechnen.optimieren(kopf, gross, k, tab, dict(einst, laenge_auto_huellkreis=0))
assert "laengen" not in rechnen.optimieren(kopf, gross, k, tab, dict(einst, laenge_auto_huellkreis=150))
assert "laengen" not in rechnen.optimieren(kopf, [pos(3100, 30, profil="RR 48,3x2,6")], k, tab, einst)
pid = next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == "RE 120x60x4")
db.aendern("profile", pid, "laengenvergleich", "nein")
(vg,) = rechnen.optimieren(kopf, gross, db.kontext(), db.tabellen(), einst)["laengen"]
assert vg["ausgenommen"] and [v["laenge"] for v in vg["varianten"]] == [6000]
db.aendern("profile", pid, "laengenvergleich", None)
# eigene Zeile geht vor: nur die eingetragenen Längen
db.neu("lieferlaengen", dict(profil_id="RE 120x60x4", werkstoff_id="S355-10219", laenge=8000))
(vg,) = rechnen.optimieren(kopf, gross, db.kontext(), db.tabellen(), einst)["laengen"]
assert not vg["automatisch"] and [v["laenge"] for v in vg["varianten"]] == [8000]     # 6 m nicht eingetragen
print("Hüllkreis-Regel OK")

# ------------------------------------------------------------------ Mindest-Stangenlänge der Stangenladung
# Patrick 21.10.2026: kein Stück aus dem Zuschnitt kürzer als 2.500 mm (je Maschine, Vorgabe 2.500)
assert all(z["min_stange"] == 2500 for z in db.zeilen("maschinen"))
g = gruppe(teile(2, 980))     # ein kurzes Stück (2.061 mm), der Rest der 12-m-Stange passt nicht dran (> 6.500)
st = opt.zuschnitt(g, 12000, 6500, 3)
assert min(l for s in werkstuecke(st) for l in s) < 2500, werkstuecke(st)
st = opt.zuschnitt(g, 12000, 6500, 3, 2500)
assert min(l for s in werkstuecke(st) for l in s) == 2500, werkstuecke(st)
opt.pruefe_zuschnitt(g, st, 12000, 6500, 3, 2500)
try:
    opt.pruefe_zuschnitt(g, [[(2400, [(t, False) for t in g.teile[-2:]])]] + st[:-1], 12000, 6500, 3, 2500)
    raise SystemExit("Kontrolle hätte das zu kurze Werkstück finden müssen")
except AssertionError:
    pass
# Restlänge an die letzte Stange (Patrick 21.10.2026: 2 × 4.000 + 2.900 -> 4.153 + 4.153 + Restlänge, ein
# Sägeschnitt weniger); T03: Endbeschnitt 10, Greiferrest 142, Schnittverlust 0,2
gr = opt.Gruppe("QR 40x40x3", "S235-10219", 6000, 10, 142, 0.2, 5)
gr.teile = teile(2, 4000) + teile(1, 2900)
st = opt.zuschnitt(gr, 12000, 6500, 3, 2500)
assert werkstuecke(st) == [[4153, 4153, 3688]] and opt.zuschnitt_belegt(werkstuecke(st)[0], 3) == 12000, st
opt.pruefe_zuschnitt(gr, st, 12000, 6500, 3, 2500)
v = rechnen.variante_kennzahlen(gr, dict(laenge=12000, zuschnitt=True, stangen=st, fehler=None), 3)
assert v["zuschnitte"] == 2 and v["lieferstangen"] == 1, v      # kein Schnitt für einen Abfall-Rest
# mit 50 mm Puffer (Vorgabe): 4.203 + 4.203 + Restlänge 3.588 (Patrick: 2 × 4.200 + ca. 3.600)
st = opt.zuschnitt(gr, 12000, 6500, 3, 2500, 50)
assert werkstuecke(st) == [[4203, 4203, 3588]], st
opt.pruefe_zuschnitt(gr, st, 12000, 6500, 3, 2500)
assert rechnen.einstellung_wert({}, "zuschnitt_puffer") == 50
# passt der Rest nicht dran (Stange würde länger als 6.500), bleibt er Abfall
assert opt.restlaenge_anhaengen([[(6401, None), (2061, None)]], 12000, 6500, 3) == [[(6401, None), (5596, None)]]
assert opt.restlaenge_anhaengen([[(6401, None)]], 12000, 6500, 3) == [[(6401, None)]]
# Ziel-Werkstücklängen unter der Mindestlänge (12 m / 5 und / 6) werden nicht ausprobiert
assert min(opt.zuschnitt_ziele(gruppe(teile(1, 500)), 12000, 6500, 3, 2500)) >= 2500
v = rechnen.variante_planen(g, 12000, dict(max_stange=6500, min_stange=2500), 3)
assert not v["fehler"] and min(l for s in v["stangen"] for l, _ in s) == 2500, v
v = rechnen.variante_planen(g, 12000, dict(max_stange=6500), 3)          # leer = keine Grenze
assert min(l for s in v["stangen"] for l, _ in s) < 2500, v
print("Mindest-Stangenlänge OK")
print("Alle Tests Lieferlängen OK")
