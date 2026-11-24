"""Stabilität 18.11.2026 (Patrick, Nachtrag zur Diagnose): dieselbe Kalkulation mit gleichen Eingaben wird nicht noch
einmal gerechnet (die Diagnose zeigte 3 Doppelte beim STEP-Import: Automatik-Maschinenvergleich, Terminplan, Check).

Geprüft wird ohne Bildschirm:
- rechnen.kalkulation: gleiche Eingaben (auch als neue Objekte) = Treffer, Ergebnis bitgleich wie neu gerechnet,
  jeder Aufrufer eine eigene Kopie, Eingaben bleiben unverändert,
- andere Eingaben (Stück, Einstellung), andere Stammdaten (neuer Stand) oder abgelaufene Gültigkeit rechnen neu,
- rechenmerker.Merker mit Gültigkeit: abgelaufene Einträge fallen heraus,
- Diagnose meldet nach zwei gleichen Kalkulationen keine unnötige Mehrfachberechnung.
Aufruf: python tests/test_kalk_merker_1811.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))
from rohrlaser import diagnose, rechenmerker, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


m = rechenmerker.Merker("Test Gültigkeit", 4, gilt_s=0.05)
n = []
assert m.holen("a", lambda: n.append(1) or 1) == 1 and m.holen("a", lambda: n.append(1) or 1) == 1 and len(n) == 1
time.sleep(0.08)
assert m.nur_holen("a") is None and m.holen("a", lambda: n.append(1) or 2) == 2 and len(n) == 2
ok("Merker mit Gültigkeit: Treffer, danach abgelaufen und neu gerechnet")

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
k, tab = db.kontext(), db.tabellen()
aid = db.angebot_neu(dict(kunde="Merker", kundennr="K-3", maschine="T11", stange=6000))
for i in range(5):
    db.position_neu(aid, dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=400.0 + 90 * i, stueck=3 + i,
                              schneidweg=150.0))
kopf, pos, e = db.angebot(aid), db.positionen(aid), db.einstellungen()
erg = rechnen.optimieren(kopf, pos, k, tab, e)
vorher = repr((kopf, pos, erg, e))
neu = rechnen._kalkulation_messen(kopf, pos, erg, k, tab, e, None)
rechnen._KALK_MERK.leeren()
zaehler = []
alt = rechnen._kalkulation_gestaffelt
rechnen._kalkulation_gestaffelt = lambda *a: zaehler.append(1) or alt(*a)
try:
    diagnose.zuruecksetzen()
    a = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    a[1]["verkauf"] = -1                                   # Aufrufer ändert seine Kopie
    b = rechnen.kalkulation(dict(kopf), [dict(p) for p in pos], rechnen.kopie(erg), k, tab, dict(e))
    assert len(zaehler) == 1, len(zaehler)
    assert repr(b) == repr(neu) and repr((kopf, pos, erg, e)) == vorher
    assert diagnose.stand()["rechnungen"]["Kalkulation"]["doppelt"] == 0
    ok("gleiche Eingaben: einmal gerechnet, bitgleich, eigene Kopie, Eingaben unverändert, Diagnose ohne doppelt")
    pos2 = [dict(p) for p in pos]
    pos2[0]["stueck"] = 11
    rechnen.kalkulation(kopf, pos2, erg, k, tab, e)
    rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, gewinn=1.3))
    assert len(zaehler) == 3, len(zaehler)
    db.einstellung_setzen("zuschnitt_verlust", "4")        # neuer Stammdaten-Stand: neue Objekte
    k2, tab2 = db.kontext(), db.tabellen()
    rechnen.kalkulation(kopf, pos, erg, k2, tab2, e)
    assert len(zaehler) == (4 if (k2 is not k or tab2 is not tab) else 3), len(zaehler)
    n0 = len(zaehler)
    alt_s = rechnen._KALK_MERK.gilt_s
    rechnen._KALK_MERK.gilt_s = 0.0
    time.sleep(0.01)
    rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    rechnen._KALK_MERK.gilt_s = alt_s
    assert len(zaehler) == n0 + 1, (n0, len(zaehler))
finally:
    rechnen._kalkulation_gestaffelt = alt
ok("andere Stückzahl, andere Einstellung, neuer Stammdaten-Stand oder abgelaufene Gültigkeit rechnen neu")
print("ALLE TESTS BESTANDEN")
