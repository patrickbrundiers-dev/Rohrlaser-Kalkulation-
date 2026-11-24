"""Ähnliche Teile (GEO-014) und Revisionsvergleich mit Preiswirkung (GEO-019), Plan Phase 3 und 4, Patrick
13.11.2026 „Alles einbauen“:

- Fingerabdruck und Ähnlichkeit: gleiche Profilform Pflicht, Maß/Länge/Konturen/Schneidweg je Meter gewichtet,
  anderer Werkstoff × 0,8
- Suche in anderen Angeboten (nicht im eigenen), ähnlichste zuerst, Preis von damals aus den Staffelpreisen
- Preiswirkung je geänderter Eigenschaft (heute gerechnet, Teil allein), nichts wird übernommen
- Fenster mit Tabelle und Preiswirkung der gewählten Zeile, Eintrag im Rechtsklick-Menü

Aufruf: python tests/test_aehnliche_teile.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import aehnliche_teile as at  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40, b=40, wand=3)
basis = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800, schneidweg=400, klein_n=4, mittel_n=1,
             gross_n=0)
f0 = at.fingerabdruck(basis, QR)
assert at.aehnlichkeit(f0, f0) == 1.0
assert at.aehnlichkeit(f0, at.fingerabdruck(basis, dict(QR, form="Rechteckrohr"))) == 0.0
anders_ws = at.aehnlichkeit(f0, at.fingerabdruck(dict(basis, werkstoff_id="1.4301"), QR))
assert abs(anders_ws - 0.8) < 1e-9
etwas = at.aehnlichkeit(f0, at.fingerabdruck(dict(basis, laenge=840, schneidweg=450, klein_n=6), QR))
weit = at.aehnlichkeit(f0, at.fingerabdruck(dict(basis, laenge=2000, schneidweg=2000, klein_n=20), QR))
assert at.GRENZE < etwas < 1.0 and weit < at.GRENZE, (etwas, weit)
assert at.fingerabdruck(dict(basis, laenge=None), QR) is None and at.fingerabdruck(basis, None) is None
ok(f"Ähnlichkeit: gleich 100 %, etwas geändert {round(100 * etwas)} %, weit weg {round(100 * weit)} %, "
   "anderer Werkstoff × 0,8, andere Profilform 0")

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
k = db.kontext()
assert "QR 40x40x3" in k.profile
alt_ang = db.angebot_neu(dict(kunde="Altkunde GmbH", maschine="T11"))
pid_alt = db.position_neu(alt_ang, dict(pos=10, artikel="H-200", **basis, stueck=50, einstiche=5))
db.position_neu(alt_ang, dict(pos=20, artikel="X-1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                              stueck=5, schneidweg=300))
db.staffelpreise_speichern(alt_ang, (dict(zeilen=[
    dict(schluessel="10", menge=50, einheit="Stk", preis_einheit=7.85)])))
neu_ang = db.angebot_neu(dict(kunde="Neukunde", maschine="T11"))
neu = dict(pos=10, artikel="H-200-B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=840, schneidweg=450,
           einstiche=7, klein_n=6, mittel_n=1, gross_n=0, stueck=50)
pid_neu = db.position_neu(neu_ang, neu)
p = next(q for q in db.positionen(neu_ang) if q["id"] == pid_neu)
treffer = at.suchen(db, neu_ang, p, k)
assert len(treffer) == 1 and treffer[0]["position"]["id"] == pid_alt, treffer
t = treffer[0]
assert t["preis"] == (50, 7.85) and t["angebot"]["kunde"] == "Altkunde GmbH"
assert "40 mm länger" in t["unterschiede"] and "2 Konturen mehr" in t["unterschiede"], t["unterschiede"]
assert at.suchen(db, alt_ang, next(q for q in db.positionen(alt_ang) if q["id"] == pid_alt), k)[0]["position"]["id"] \
    == pid_neu                      # umgekehrt findet das alte Angebot das neue, nie sich selbst
ok(f"Suche: ähnliches Teil aus anderem Angebot ({round(100 * t['aehnlichkeit'])} %), Preis damals 7,85 € bei 50 Stk")

kopf = db.angebot(neu_ang)
w = at.preiswirkung(kopf, p, t["position"], k, db.tabellen(), db.einstellungen())
assert w and w["heute"] > 0, w
teile = dict(w["teile"])
assert set(teile) <= {"Länge", "Konturen und Schneidweg"} and teile.get("Konturen und Schneidweg", 0) > 0, w
assert abs(w["gesamt"] - (w["heute"] - w["alt_gerechnet"])) < 1e-9 and w["gesamt"] > 0
assert "je Stück" in at.preiswirkung_text(w)
assert at.preiswirkung(kopf, p, dict(p), k, db.tabellen(), db.einstellungen())["teile"] == []
ok(f"Preiswirkung: {at.preiswirkung_text(w)}")

f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(neu_ang)
gesehen = {}


def bedienen(d):
    gesehen["zeilen"] = d.tabelle.rowCount()
    gesehen["text"] = d.wirkung.text()
    gesehen["knopf"] = d.oeffnen_knopf.isEnabled()
    d.reject()


r = next(i for i, q in enumerate(s.positionen) if q["id"] == pid_neu)
assert s.aehnliche_teile(r, dialog=bedienen)
assert gesehen["zeilen"] == 1 and "Preiswirkung" in gesehen["text"] and gesehen["knopf"], gesehen
assert "Ähnliche Teile und Revisionen …" in s.pos_aktionen
assert db.positionen(neu_ang)[0]["laenge"] == 840           # nichts übernommen
ok("Fenster: Tabelle, Preiswirkung der gewählten Zeile, Angebot öffnen; nichts wird übernommen")
print("alle Prüfungen bestanden")
