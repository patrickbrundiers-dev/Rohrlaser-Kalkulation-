"""Rückmeldungen füllen die Nachkalkulation (Plan Angebotskalkulation 16.11.2026, Paket K1): Faktor Ist ÷ Soll je
Arbeitsgang, Laserzeit und Rüsten aus dem Soll der Nachkalkulation, Laufzeit je Teil, Ausschuss, Zeit je
Arbeitsgang, Soll-Stand für Auswertung und Kalibrierung, von Hand Eingetragenes geht vor, Anzeige der Herkunft.

Aufruf: python tests/test_nachkalk_rueckmeldung.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import auftraege as au, auftrag_av as av, auftrag_produktion as pr  # noqa: E402
from rohrlaser import nachkalk_rueckmeldung as nr, nachkalkulation as nk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)

a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", stange=6000, maschine="T03"))
for n, (art, stueck) in enumerate((("R-1", 40), ("R-2", 20))):
    db.position_neu(a, dict(pos=n + 1, artikel=art, bezeichnung=f"Teil {art}", profil_id="RR 42,4x2,0",
                            werkstoff_id="S235-10219", laenge=1000 - 200 * n, stueck=stueck, schneidweg=300,
                            einstiche=2))
s = f.angebot_oeffnen(a)
s.optimieren()
s.neu_laden()
f.angebot_schliessen(a)
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("PO-1", "2026-12-01"))
uid = au.uebernehmen(db, [a])
assert av.alle_uebernehmen(db, uid) >= 1
assert av.freigeben(db, uid, "Test ohne Prüfliste") is True

# Rohrlaser Pos. 1 braucht 50 % länger als geplant, Pos. 2 genau wie geplant; 2 Teile Ausschuss an Pos. 1
auf = au.auftrag(db, uid)
for i, p in enumerate(auf["positionen"]):
    laser = next(x for x in p["arbeitsgaenge"] if x["aktiv"] and nr._art(x) == "laser")
    soll, menge = laser["sollzeit"], laser["sollmenge"]
    assert soll > 0 and menge > 0, laser
    faktor = 1.5 if i == 0 else 1.0
    aus = 2 if i == 0 else 0
    assert pr.rueckmelden(db, uid, p["uid"], laser["uid"], pr.ABGESCHLOSSEN, menge=menge - aus, ausschuss=aus,
                          minuten=round(soll * faktor, 1))

w = nr.werte(db, au.auftrag(db, uid))
ang = au.angebot_uid(db, a)
assert set(w) == {ang} and w[ang]["ausschuss"] == 2, w
fk = sorted(x["laser"] for x in w[ang]["positionen"].values())
assert abs(fk[0] - 1.0) < 0.01 and abs(fk[1] - 1.5) < 0.01, fk
assert w[ang]["arbeitsgaenge"]["laser"]["faelle"] == 2
ok("Faktor Ist ÷ Soll je Teil aus den fertigen Arbeitsgängen, Ausschuss gezählt")

# von Hand eingetragene Rüstzeit bleibt
db.nachkalkulation_speichern(a, dict(ruest_min=33))
n = nr.uebernehmen(db, uid)
ist = db.angebot(a)["nachkalkulation"]
assert n >= 3 and ist["ruest_min"] == 33 and not nr.aus_rueckmeldung(ist, "ruest_min"), ist
assert ist["ausschuss_stk"] == 2 and nr.aus_rueckmeldung(ist, "ausschuss_stk")
assert nr.aus_rueckmeldung(ist, "laser_h") and ist["aus_auftrag"] == au.auftrag(db, uid)["nummer"]
assert isinstance(ist.get("soll"), dict), "Soll-Stand fehlt (Auswertung und Kalibrierung zählen den Fall nicht)"
soll_laser = next(z for z in ist["soll"]["zeilen"] if z[0] == "Laserzeit")[3]
gesamt = sum(s_ for s_, _ in w[ang]["laser"])
erwartet = soll_laser * sum(i_ for _, i_ in w[ang]["laser"]) / gesamt
assert abs(ist["laser_h"] - erwartet) < 0.002 and ist["laser_h"] > soll_laser, (ist["laser_h"], soll_laser)
ok("Laserzeit = Soll × Faktor, Soll-Stand festgehalten, von Hand eingetragene Rüstzeit bleibt")

# Laufzeit je Teil: Pos. 1 × 1,5, Pos. 2 × 1,0 -> Kalibrierung zählt die Teile
lz = ist["laufzeit"]
teile = {t[0]: t[1] for t in ist["soll"]["laufzeit"]}
assert len(lz) == 2 and all(nr.aus_rueckmeldung(ist, "", position_id=p) for p in teile)
quoten = sorted(lz[str(p)] / s_ for p, s_ in teile.items())
assert abs(quoten[0] - 1.0) < 0.01 and abs(quoten[1] - 1.5) < 0.01, quoten
faelle = nk.faelle_laserzeit_teil(db)
assert len(faelle) == 2 and nk.faelle(db)[1] == 0, faelle
ok("Laufzeit je Teil aus der Rückmeldung, Kalibrierung der Schneiddaten zählt die Fälle")

# zweimal übernehmen ändert nichts; geänderte Rückmeldung überschreibt nur Werte aus Rückmeldungen
vorher = db.angebot(a)["nachkalkulation"]
nr.uebernehmen(db, uid)
nach = db.angebot(a)["nachkalkulation"]
assert {k: v for k, v in nach.items() if k != "am"} == {k: v for k, v in vorher.items() if k != "am"}
ok("Übernahme wiederholbar ohne Doppel")

# Anzeige im Angebot: Herkunft markiert, von Hand geändert -> geht vor
s = f.angebot_oeffnen(a)
seite = s.nachkalk
seite.neu_laden()
assert "Rückmeldung" in seite.felder["laser_h"].toolTip()
assert "Rückmeldung" not in seite.felder["ruest_min"].toolTip()
seite.felder["laser_h"].setText("1,25")
seite._feld_geaendert("laser_h", seite.felder["laser_h"])
ist = db.angebot(a)["nachkalkulation"]
assert ist["laser_h"] == 1.25 and not nr.aus_rueckmeldung(ist, "laser_h")
nr.uebernehmen(db, uid)
assert db.angebot(a)["nachkalkulation"]["laser_h"] == 1.25
f.angebot_schliessen(a)
ok("Nachkalkulation zeigt die Herkunft; von Hand geänderter Wert geht danach vor")

print("test_nachkalk_rueckmeldung OK")
