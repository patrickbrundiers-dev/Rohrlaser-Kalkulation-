"""Stabilitäts-Auftrag 18.11.2026 (Patrick, Paket A „Doppelrechnungen vermeiden“): gleiche Eingaben werden einmal
gerechnet, das Ergebnis bleibt gleich.

Geprüft wird ohne Bildschirm:
- rechenmerker.Merker: Treffer/Neu zählen, Größe begrenzt (älteste fallen heraus), nicht hashbarer Schlüssel rechnet,
  mehrere Threads gleichzeitig ohne Fehler,
- zeit_zusatz._lagen (D3): gleiches Ergebnis wie neu gerechnet, eigene Liste je Aufruf, andere Kontur oder Länge
  rechnet neu, Konturdaten nur einmal gelesen,
- rechnen._schneidzeit_teile (D2): im Merker einmal je Eingabe, jeder Aufrufer eine eigene Kopie, ohne Merker wie
  bisher,
- maschinen_vergleich.vergleich (D1): gleiche Eingaben = Treffer (auch mit anderer Änderungszeit), geänderte Position
  rechnet neu, Ergebnis gleich wie ohne Merker,
- Angebot: Zelle ändern + Check mit 3 Maschinen rechnet den Vergleich einmal; zweiter Check ohne Änderung rechnet
  nichts; Werkstatt-PDF danach ohne Vergleich; im Programm (Hintergrund) kommt der Hinweis nach, gleich wie sofort.
Aufruf: python tests/test_doppelrechnung_1811.py
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import maschinen_vergleich, rechenmerker, rechnen, schneidweg, zeit_zusatz  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ Merker
m = rechenmerker.Merker("Test", 3)
gerechnet = []
for s in (1, 2, 1, 3, 4, 1):
    assert m.holen(("x", s), lambda s=s: gerechnet.append(s) or s * 10) == s * 10
assert gerechnet == [1, 2, 3, 4], gerechnet        # 2 fiel nach 4 heraus (Größe 3, 1 zuletzt benutzt)
assert (m.treffer, m.neu, len(m)) == (2, 4, 3), (m.treffer, m.neu, len(m))
assert m.holen(["nicht", "hashbar"], lambda: 7) == 7 and m.neu == 4
assert m.nur_holen(("x", 4)) == 40 and m.nur_holen(("x", 99)) is None
assert any(z["name"] == "Test" and z["treffer"] == 3 for z in rechenmerker.stand())
fehler = []


def last():
    try:
        for i in range(2000):
            m.holen(i % 7, lambda i=i: i % 7)
    except Exception as e:      # noqa: BLE001
        fehler.append(e)


ts = [threading.Thread(target=last) for _ in range(4)]
for t in ts:
    t.start()
for t in ts:
    t.join()
assert not fehler and len(m) <= 3, fehler
ok("Merker: zählt Treffer und Neuberechnungen, begrenzt, nicht hashbar rechnet, 4 Threads gleichzeitig")


# ------------------------------------------------------------------ D3 Konturen mit Lage
def technik(*konturen):
    return json.dumps(dict(quelle="Schneidweg-Rechner", konturen=list(konturen)))


K1 = dict(art="Bohrung", d=12, anzahl=4, abstand=30, x=300, seite="oben")
K2 = dict(art="Rechteck", b=150, h=30, anzahl=1, x=900, seite="vorne")
p = dict(laenge=1200.0, technik=technik(K1, K2))
neu = zeit_zusatz._lagen_rechnen(p["technik"], 1200.0)
a, b = zeit_zusatz._lagen(p), zeit_zusatz._lagen(dict(p))
assert a == b == neu and a is not b and len(a) == 5, (len(a), len(neu))
a.clear()
assert zeit_zusatz._lagen(p) == neu                     # eigene Liste: Leeren ändert den Merker nicht
assert zeit_zusatz._lagen(dict(p, laenge=1000.0)) == zeit_zusatz._lagen_rechnen(p["technik"], 1000.0)
p2 = dict(p, technik=technik(K1))
assert len(zeit_zusatz._lagen(p2)) == 4 and zeit_zusatz._lagen(dict(laenge=500)) == []
gelesen = []
alt_lesen = schneidweg.lesen
schneidweg.lesen = lambda t: gelesen.append(1) or alt_lesen(t)
try:
    p3 = dict(laenge=800.0, technik=technik(K2, dict(K1, x=100)))
    for _ in range(20):
        zeit_zusatz.seiten(p3), zeit_zusatz.innenkonturen(p3)
finally:
    schneidweg.lesen = alt_lesen
assert len(gelesen) == 1, len(gelesen)
ok("D3: Konturen mit Lage gleich wie neu gerechnet, eigene Liste, 40 Zugriffe lesen die Konturdaten einmal")

# ------------------------------------------------------------------ D2 Laserzeit je Position
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
k, tab = db.kontext(), db.tabellen()
assert len(k.maschinen) >= 2, sorted(k.maschinen)
kopf = dict(maschine="T11", stange=6000)
pz = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1200.0, stueck=4, schneidweg=300.0,
          technik=technik(K1, K2))
ohne = rechnen._schneidzeit_teile(pz, kopf, 2.0, tab, k)
zaehler = []
alt_r = rechnen._schneidzeit_teile_rechnen
rechnen._schneidzeit_teile_rechnen = lambda *a: zaehler.append(1) or alt_r(*a)
try:
    with rechnen.merker():
        e1 = rechnen._schneidzeit_teile(pz, kopf, 2.0, tab, k)
        e1["anteile"]["gross"] = -1                    # Aufrufer ändert seine Kopie
        e2 = rechnen._schneidzeit_teile(pz, kopf, 2.0, tab, k)
        rechnen._schneidzeit_teile(pz, kopf, 3.0, tab, k)
    assert len(zaehler) == 2, len(zaehler)
    assert repr(e2) == repr(ohne), "Merker muss dasselbe liefern wie ohne"
    rechnen._schneidzeit_teile(pz, kopf, 2.0, tab, k)
    rechnen._schneidzeit_teile(pz, kopf, 2.0, tab, k)
    assert len(zaehler) == 4                           # ohne Merker: jedes Mal wie bisher
finally:
    rechnen._schneidzeit_teile_rechnen = alt_r
ok("D2: Laserzeit je Position im Merker einmal je Eingabe, eigene Kopie, ohne Merker wie bisher")

# ------------------------------------------------------------------ D1 Maschinenvergleich
pos = [dict(pz, id=i + 1, pos=i + 1, laenge=600.0 + 50 * i, stueck=3 + i) for i in range(4)]
kopf_v = dict(kopf, geaendert="2026-11-18 10:00:00")
einst = db.einstellungen()
maschinen_vergleich._MERK.leeren()
ohne_merker = maschinen_vergleich._vergleich(kopf_v, pos, k, tab, einst, db.zeitbasis_vorgabe)
t0 = maschinen_vergleich._MERK.neu
l1 = maschinen_vergleich.vergleich(kopf_v, pos, k, tab, einst, db.zeitbasis_vorgabe)
l2 = maschinen_vergleich.vergleich(dict(kopf_v, geaendert="2026-11-18 10:05:00"), [dict(p) for p in pos], k, tab,
                                   dict(einst), db.zeitbasis_vorgabe)
assert maschinen_vergleich._MERK.neu == t0 + 1, "zweiter Vergleich mit gleichen Eingaben muss ein Treffer sein"
assert json.dumps(l1, sort_keys=True) == json.dumps(l2, sort_keys=True) == json.dumps(ohne_merker, sort_keys=True)
l2[0]["verkauf"] = -1
assert maschinen_vergleich.vergleich(kopf_v, pos, k, tab, einst, db.zeitbasis_vorgabe)[0]["verkauf"] != -1
anders = [dict(p) for p in pos]
anders[1]["stueck"] = 40
l3 = maschinen_vergleich.vergleich(kopf_v, anders, k, tab, einst, db.zeitbasis_vorgabe)
assert maschinen_vergleich._MERK.neu == t0 + 2 and l3 != l1
assert maschinen_vergleich.gemerkt(kopf_v, anders, k, tab, einst, db.zeitbasis_vorgabe) == l3
assert maschinen_vergleich.gemerkt(dict(kopf_v, maschine="LT7"), pos, k, tab, einst, db.zeitbasis_vorgabe) is None
ok("D1: Maschinenvergleich je Eingabe einmal (Änderungszeit zählt nicht), geänderte Position rechnet neu, "
   "Ergebnis gleich wie ohne Merker")

# ------------------------------------------------------------------ Angebot: Zelle ändern + Check
AngebotSeite.CHECK_SOFORT = False
f = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Doppelt", kundennr="K-1", maschine="T11", stange=6000))
for q in pos:
    db.position_neu(aid, {n: w for n, w in q.items() if n not in ("id", "pos")})
s = f.angebot_oeffnen(aid)
s.optimieren()
app.processEvents()
spalte = next(i for i, (_, fd) in enumerate(s.pos_modell.spalten) if fd is not None and getattr(fd, "name", None) == "stueck")
vergleiche = []
alt_v = maschinen_vergleich._vergleich
maschinen_vergleich._vergleich = lambda *a, **kw: vergleiche.append(1) or alt_v(*a, **kw)


def check():
    uhr = s.__dict__.get("_check_uhr")
    if uhr is not None:
        uhr.stop()
    s._check_jetzt()


try:
    s.pos_modell.setData(s.pos_modell.index(0, spalte), "7")
    app.processEvents()
    check()
    assert len(vergleiche) == 1, len(vergleiche)
    punkte_sofort = list(s._punkte)
    s.neu_laden()
    check()
    assert len(vergleiche) == 1, "Neuladen ohne Änderung darf den Vergleich nicht neu rechnen"
    s.maschinen_vergleich_liste()
    assert len(vergleiche) == 1
    # im Programm: Vergleich im Hintergrund, Hinweis kommt nach (gleich wie sofort gerechnet)
    s.MASCHINEN_HINTERGRUND = True
    s.pos_modell.setData(s.pos_modell.index(1, spalte), "9")
    app.processEvents()
    t = time.perf_counter()
    check()
    dauer_check = time.perf_counter() - t
    ende = time.monotonic() + 60
    while (s.__dict__.get("_mv_lauf") is not None) and time.monotonic() < ende:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert len(vergleiche) == 2, len(vergleiche)
    mit_hinter = list(s._punkte)
    s.MASCHINEN_HINTERGRUND = False
    maschinen_vergleich._MERK.leeren()
    s.neu_laden()
    check()
    assert len(vergleiche) == 3
    assert mit_hinter == list(s._punkte), (mit_hinter, s._punkte)
finally:
    maschinen_vergleich._vergleich = alt_v
    s.MASCHINEN_HINTERGRUND = None
assert punkte_sofort is not None
ok(f"Angebot: Zelle + Check rechnet den Maschinenvergleich einmal, Neuladen/Liste danach nichts; im Hintergrund "
   f"(Check {dauer_check:.2f} s) gleicher Hinweis wie sofort")
print("ALLE TESTS BESTANDEN")
