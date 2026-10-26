"""Stangen von Hand vorgegeben (Patrick 26.10.2026): je Abmessung mehrere Stangenlängen mit Stückzahl, die
Optimierung nutzt genau diese Stangen; was nicht passt, bleibt nicht eingeplant.

Aufruf: python tests/test_stangen_vorgabe.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import optimierung as opt, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import ALTE_MASCHINEN, MASCHINE_WERTE  # noqa: E402


def teile(n, laenge, zeile=13, start=1):
    return [opt.Teil(zeile, zeile, "A", i, laenge, True, True, 100, 100) for i in range(start, start + n)]


def gruppe(t, stange=6000):
    # Endbeschnitt 20, Greiferrest 80, Schnittverlust 0,3: Nutzlänge 6-m-Stange = 5.900 − 20 = 5.880
    return opt.Gruppe("QR 40x40x3", "S235-10219", stange, 20, 80, 0.3, 2, teile=t)


def laengen(folgen):
    return [laenge for laenge, _ in folgen]


# ------------------------------------------------------------------ Vorgabe lesen
assert opt.vorrat_lesen([[6000, 3], ["4500", 2], [6000, 1], [0, 5], [3000, 0], ["x", 1], None]) == [(6000, 4),
                                                                                                    (4500, 2)]
assert opt.vorrat_lesen(None) == [] and opt.vorrat_lesen([]) == []

# ------------------------------------------------------------------ Planen
# 4 Teile à 2.000 mm: je 6-m-Stange 2 Teile (3 passen nicht: 20 + 3 × 2.000 + 3 × 0,3 > 5.920), auf 4.500 mm
# ebenfalls 2 (20 + 4.000 + 0,6 + 80 = 4.100,6). Vorrat 2 × 6.000 + 2 × 4.500: die kürzeren reichen.
g = gruppe(teile(4, 2000))
v = [(6000, 2), (4500, 2)]
f, rest = opt.vorrat_planen(g, v)
opt.pruefe_vorrat(g, v, f, rest)
assert laengen(f) == [4500, 4500] and not rest, (laengen(f), rest)

# Zu wenig Stangen: 1 × 6.000 + 1 × 4.500 reichen nur für 4 von 6 Teilen; 2 bleiben übrig
g = gruppe(teile(6, 2000))
v = [(6000, 1), (4500, 1)]
f, rest = opt.vorrat_planen(g, v)
opt.pruefe_vorrat(g, v, f, rest)
assert sorted(laengen(f)) == [4500, 6000] and len(rest) == 2, (laengen(f), rest)

# Langes Teil nur auf die lange Stange: 5.000 mm passt nicht auf 4.500, also bekommt es die 6.000er;
# die kurzen Teile gehen auf die 4.500er
g = gruppe(teile(1, 5000) + teile(2, 2000, zeile=14))
v = [(4500, 3), (6000, 1)]
f, rest = opt.vorrat_planen(g, v)
opt.pruefe_vorrat(g, v, f, rest)
assert laengen(f) == [6000, 4500] and not rest, laengen(f)
assert [t.laenge for t, _ in f[0][1]] == [5000]

# Gemischte Längen: wenig Stangenlänge insgesamt. 2 × 2.900 passen auf 6.000 (20 + 5.800 + 0,6 + 80 = 5.900,6),
# 1 × 2.900 + 1 × 1.200 auf 4.500 (20 + 4.100 + 0,6 + 80 = 4.200,6)
g = gruppe(teile(3, 2900) + teile(1, 1200, zeile=14))
v = [(6000, 5), (4500, 5), (3000, 5)]
f, rest = opt.vorrat_planen(g, v)
opt.pruefe_vorrat(g, v, f, rest)
assert not rest and sum(laengen(f)) <= 10500, laengen(f)

# Kontrolle schlägt an: mehr Stangen als vorgegeben, Teil doppelt
try:
    opt.pruefe_vorrat(g, [(6000, 1)], f, rest)
    raise SystemExit("Kontrolle hätte anschlagen müssen")
except AssertionError:
    pass

# ------------------------------------------------------------------ Im Angebot
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
_t03 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
for _feld, _wert in zip(MASCHINE_WERTE, ALTE_MASCHINEN["RL-1"][1]):
    db.aendern("maschinen", _t03["id"], _feld, _wert)
k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
kopf = dict(maschine="T03", stange=6000)


def pos(laenge, stueck, nr=10):
    return dict(pos=nr, artikel=f"T{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=laenge,
                stueck=stueck)


positionen = [pos(2000, 6), pos(1500, 2, 20)]
ohne = rechnen.optimieren(kopf, positionen, k, tab, einst)
assert len(ohne["stangen"]) == 3 and not ohne["fehler"]
assert all(s["stange"] == 6000 for s in ohne["stangen"])

schl = rechnen.laengen_schluessel(("QR 40x40x3", "S235-10219", "", 6000))
assert schl == "QR 40x40x3|S235-10219||6000"
kopf_v = dict(kopf, stangen_vorgabe={schl: [[6000, 1], [4500, 3]]})
assert rechnen.stangen_vorgabe(kopf_v, ("QR 40x40x3", "S235-10219", "", 6000)) == [(6000, 1), (4500, 3)]
# Vorgabe gehört zur Prüfsumme; ohne Vorgabe bleibt die Prüfsumme wie bisher
assert rechnen.eingabe_kennung(kopf_v, positionen, k, tab, einst) != ohne["kennung"]
assert rechnen.eingabe_kennung(dict(kopf, stangen_vorgabe={}), positionen, k, tab, einst) == ohne["kennung"]

erg = rechnen.optimieren(kopf_v, positionen, k, tab, einst)
assert not erg["fehler"], erg["fehler"]
lg = sorted(s["stange"] for s in erg["stangen"])
assert sum(len(s["teile"]) for s in erg["stangen"]) == 8
assert lg.count(6000) <= 1 and lg.count(4500) <= 3, lg
assert all(s["grundlaenge"] == 6000 and s["vorgegeben"] for s in erg["stangen"])
(a,) = erg["auswertung"]
assert a["vorgegeben"] == "1 × 6.000 + 3 × 4.500 mm" and "von Hand vorgegeben" in a["bewertung"], a
# Werte und Kosten je Stange: keine Überbelegung, Länge der Stange zählt
for s, w in zip(erg["stangen"], rechnen.stangen_werte(erg, kopf_v, positionen, k, tab)):
    assert w["pruefung"] == "OK", (s, w)
# Material-Fenster zählt die Längen laut Schnittplan
(m,) = rechnen.material_abmessungen(kopf_v, positionen, erg, k, tab)
assert sum(m["laengen"].values()) == len(erg["stangen"]) and set(m["laengen"]) <= {6000, 4500}, m["laengen"]

# Vorrat zu klein: nicht eingeplante Teile mit Grund je Position
kopf_k = dict(kopf, stangen_vorgabe={schl: [[4500, 2]]})
erg = rechnen.optimieren(kopf_k, positionen, k, tab, einst)
assert len(erg["stangen"]) == 2 and all(s["stange"] == 4500 for s in erg["stangen"])
nicht = sum(f["anzahl"] for f in erg["fehler"])
assert nicht == 8 - sum(len(s["teile"]) for s in erg["stangen"]) and nicht > 0, erg["fehler"]
assert all("vorgegebene Stangen reichen nicht (2 × 4.500 mm)" == f["grund"] for f in erg["fehler"]), erg["fehler"]
assert "nicht eingeplant" in erg["auswertung"][0]["bewertung"]

# Teil länger als die Angebotslänge, aber kürzer als eine vorgegebene Stange: wird geplant
lang = [pos(6200, 1)]
assert rechnen.optimieren(kopf, lang, k, tab, einst)["fehler"][0]["grund"] == "Teil länger als Nutzlänge der Stange"
erg = rechnen.optimieren(dict(kopf, stangen_vorgabe={schl: [[6500, 1]]}), lang, k, tab, einst)
assert not erg["fehler"] and [s["stange"] for s in erg["stangen"]] == [6500], erg
# Länge über der max. Stangenlänge der Maschine (6.500) gilt nicht
assert rechnen.stangen_vorgabe(dict(kopf, stangen_vorgabe={schl: [[7000, 1]]}), ("QR 40x40x3", "S235-10219", "", 6000),
                               6500) == []

# Staffeln rechnen ohne Vorgabe (die Stangen gelten nur für die Menge des Angebots)
assert "stangen_vorgabe" not in staffeln.stufe_kopf(kopf_v, None)

# ------------------------------------------------------------------ Datenbank: speichern, laden, kopieren
aid = db.angebot_neu(dict(kopf, kunde="Test"))
db.stangen_vorgabe_speichern(aid, {schl: [[6000, 1], [4500, 3]]})
assert db.angebot(aid)["stangen_vorgabe"] == {schl: [[6000, 1], [4500, 3]]}
neu = db.angebot_kopieren(aid)
assert db.angebot(neu)["stangen_vorgabe"] == {schl: [[6000, 1], [4500, 3]]}
db.stangen_vorgabe_speichern(aid, {})
assert db.angebot(aid)["stangen_vorgabe"] is None

# ------------------------------------------------------------------ Fenster „Material …“: Spalte Stangen vorgegeben
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.meterpreis_dialog import VORGABE  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp2 = Path(tempfile.mkdtemp())
db2 = Datenbank(tmp2 / "rohrlaser.db")
fenster = Hauptfenster(db2, tmp2, stumm=True)
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db2))
assert s.optimieren()
g0 = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)[0]
st0 = [x for x in s.ergebnis["stangen"] if rechnen.gruppe_der_stange(x) == g0["gruppe"]]
teile0 = sum(len(x["teile"]) for x in st0)


def vorgeben(zeilen, nachher=None):
    def f(d):
        assert d.tabelle.cellWidget(0, VORGABE).text() == ("keine …" if not s.kopf.get("stangen_vorgabe") else
                                                           d.tabelle.cellWidget(0, VORGABE).text())

        def ausfuellen(v):
            v.setzen(zeilen)
            v.annehmen()
            return v.result()
        d.vorgabe_bearbeiten(0, ausfuellen)
        if nachher:
            nachher(d)
        d.annehmen()
        return d.result()
    return f


# Vorgabe mit zwei Längen: gespeichert, Prüfsumme veraltet, neu optimiert nur mit diesen Stangen
assert s.material_einstellen(vorgeben([("6.000", 1), ("4500", 50)])) == 1
schl0 = rechnen.laengen_schluessel(g0["gruppe"])
assert s.kopf["stangen_vorgabe"] == {schl0: [[6000, 1], [4500, 50]]}, s.kopf.get("stangen_vorgabe")
assert s.stand_optimierung() != "aktuell"
assert s.optimieren()
st = [x for x in s.ergebnis["stangen"] if rechnen.gruppe_der_stange(x) == g0["gruppe"]]
assert sum(len(x["teile"]) for x in st) == teile0 and all(x["stange"] in (6000, 4500) for x in st)
assert sum(1 for x in st if x["stange"] == 6000) <= 1
# Knopf zeigt die Vorgabe, Kontextmenü hat den Eintrag
seen = {}


def ansehen(d):
    seen["text"] = d.tabelle.cellWidget(0, VORGABE).text()
    seen["menue"] = [t for t, _, _ in d.menue_eintraege(0)]
    d.reject()
    return d.result()


s.material_einstellen(ansehen)
assert seen["text"] == "1 × 6.000 + 50 × 4.500 mm" and "Stangen vorgeben …" in seen["menue"], seen

# Ungültige Zeile: Fehler im Dialog, nichts übernommen
from rohrlaser.stangen_vorgabe_dialog import VorgabeDialog  # noqa: E402
v = VorgabeDialog(None, "Test", [(6000, 2)], 6500, 6000)
v.setzen([("7000", 1)])
v.annehmen()
assert not v.result() and "6.500" in v.fehler.text(), v.fehler.text()
v.setzen([("6000", "1,5")])
v.annehmen()
assert not v.result() and "ganze Zahl" in v.fehler.text()
v.setzen([("6000", 2), ("", ""), ("6000", 1)])
v.annehmen()
assert v.result() and v.vorrat == [[6000, 3]]

# Vorgabe aufheben
assert s.material_einstellen(vorgeben([])) == 1
assert not s.kopf.get("stangen_vorgabe")

print("test_stangen_vorgabe: OK")
