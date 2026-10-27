"""Material- und Fertigungsvarianten vergleichen (Wettbewerbsvergleich P1-5, varianten.py): Lieferlängen 6 m/12 m und
Material aus dem Lager je Gruppe, Kennzahlen Kosten/Verschnitt/Stangen/Wechselzeit, Empfehlung passt zur Zielgröße,
nicht ausführbare Varianten und fehlende Preise nie empfohlen, Status der Optimierung (bewiesen / nicht bewiesen),
Übernahme einer Lieferlänge aus dem Fenster.

Aufruf: python tests/test_varianten.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import lager, varianten as va  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

# ------------------------------------------------------------------ Bewertung ohne Angebot
V = [dict(name="a", kosten=100.0, verschnitt=20.0, stangen=10, zeit=5.0, fehler=None),
     dict(name="b", kosten=90.0, verschnitt=30.0, stangen=5, zeit=5.0, fehler=None),
     dict(name="c", kosten=50.0, verschnitt=1.0, stangen=1, zeit=1.0, fehler="Teil zu lang"),
     dict(name="d", kosten=None, verschnitt=5.0, stangen=8, zeit=4.0, fehler=None)]
for ziel, n, beste in (("Kosten", "kosten", 1), ("Verschnitt", "verschnitt", 3), ("Stangenanzahl", "stangen", 1),
                       ("Wechselzeit", "zeit", 3)):
    b = va.bewerten(V, ziel)
    ok = [i for i, v in enumerate(V) if not v["fehler"] and v[n] is not None]
    assert b["beste"] == min(ok, key=lambda i: V[i][n]) == beste, (ziel, b)
    assert b["punkte"][2] is None                                       # nicht ausführbar: nie bewertet
assert va.bewerten(V, "Kosten")["punkte"][3] is None                    # Preis fehlt: nicht für Kosten
b = va.bewerten(V, "Ausgewogen")
assert b["beste"] in (0, 1) and b["punkte"][3] is None and "Kosten [€] × 0.5" in b["grund"]
# bei Gleichstand: die günstigere
assert va.bewerten([dict(V[0], zeit=5.0), dict(V[1], zeit=5.0)], "Wechselzeit")["beste"] == 1
assert va.bewerten([V[2]], "Kosten")["beste"] is None
assert va.bewerten([dict(V[0], verschnitt=0.0), dict(V[1], verschnitt=0.0)], "Verschnitt")["beste"] == 1

# ------------------------------------------------------------------ Angebot: 3.100 mm, 6 m gegen 12 m
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("laenge_vergleich", "ja")
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=12000))
fenster = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=3100.0,
                          stueck=30, schneidweg=200, einstiche=1))
db.position_neu(aid, dict(pos=20, artikel="B", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1250.0,
                          stueck=10, schneidweg=200, einstiche=1))
s = fenster.angebot_oeffnen(aid)
assert s.varianten_vergleichen() is None                               # nicht optimiert
assert s.optimieren()
gr = s.varianten_gruppen()
qr = next(g for g in gr if g["profil"] == "QR 40x40x3")
rr = next(g for g in gr if g["profil"] == "RR 42,4x2,0")
assert [v["laenge"] for v in qr["varianten"]] == [6000, 12000] and qr["laengen_index"] is not None
v6, v12 = qr["varianten"]
assert v6["geplant"] and v6["stangen"] == 30 and v12["stangen"] == 10 and v6["beladungen"] == v12["beladungen"] == 30
assert v12["kosten"] < v6["kosten"] and v12["verschnitt"] < v6["verschnitt"]
assert v6["status"].startswith("optimal") and v12["status"] == va.NICHT_BEWIESEN
assert len(rr["varianten"]) == 1 and rr["varianten"][0]["geplant"] and rr["varianten"][0]["kosten"] > 0
assert abs(rr["varianten"][0]["verschnitt"] - 100 * (3 * 6000 - 10 * 1250) / 18000) < 1e-9, rr["varianten"]
# Kontrollrechnung Verschnitt 6 m: 30 × 6.000 − 30 × 3.100
assert abs(v6["verschnitt"] - 100 * (180000 - 93000) / 180000) < 1e-9
assert va.bewerten(qr["varianten"], "Kosten")["beste"] == 1
assert va.bewerten(qr["varianten"], "Stangenanzahl")["beste"] == 1

# Fenster: Empfehlung je Ziel, Übernahme der 12 m
d = s.varianten_vergleichen(dialog=lambda d: None)
n = next(i for i, g in enumerate(d.gruppen) if g["profil"] == "QR 40x40x3")
for ziel in va.ZIELE:
    d.ziel.setCurrentText(ziel)
    e = d.empfohlen(n)
    gew = va.GEWICHTE[ziel]
    if len(gew) == 1:
        (krit,) = gew
        assert e[krit] == min(v[krit] for v in d.gruppen[n]["varianten"] if not v["fehler"]), (ziel, e)
assert d.lager_knopf.isHidden()
r = next(i for i, (g, v) in enumerate(d.zeilen) if v and v["laenge"] == 12000)
d.tabelle.selectRow(r)
d.tabelle.setCurrentCell(r, 0)
assert d.uebernehmen_knopf.isEnabled()
assert d.uebernehmen()
qr = next(g for g in s.varianten_gruppen() if g["profil"] == "QR 40x40x3")
assert next(v for v in qr["varianten"] if v["geplant"])["laenge"] == 12000
assert (s.kopf.get("laengenwahl") or {})

# ------------------------------------------------------------------ Lager-Variante
db.einstellung_setzen("lager_aktiv", "ja")
fenster.lager_anwenden()
lager.zugang(db, "Stange", "RR 42,4x2,0", "S235-10219", 6000, 2, lagerort="A1")
s.neu_laden()
rr = next(g for g in s.varianten_gruppen() if g["profil"] == "RR 42,4x2,0")
geplant, lg = rr["varianten"]
assert lg.get("lager") and lg["aus_lager"] == 2 and lg["stangen"] == geplant["stangen"] - 2
assert lg["verschnitt"] == geplant["verschnitt"] and lg["beladungen"] == geplant["beladungen"]
assert lg["kosten"] <= geplant["kosten"] + 1e-9                      # Restwert 1,0: Lagerwert = Neupreis
assert lager.bestand(db)[0]["anzahl"] == 2                            # nur geplant, nichts gebucht
assert not lager.auftrag(db, aid)
d = s.varianten_vergleichen(dialog=lambda d: None)
assert not d.lager_knopf.isHidden()                                  # Knopf zur Reservierung
db.schliessen()
print("test_varianten OK")
