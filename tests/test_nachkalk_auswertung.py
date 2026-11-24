"""Nachkalkulation verbessert (Wettbewerbsvergleich P0-2): Fracht und Ausschuss getrennt, Soll-Stand je
Nachkalkulation, Auswertung über alle Aufträge nach Kostenart/Maschine/Werkstoff/Profil/Stückzahl mit unabhängiger
Kontrollrechnung, leere Ist-Werte nie als 0 €, Kennwert-Vorschläge Laserzeit (Freigabe und Rücknahme) und Rüsten
(nur Vorschlag); ältere Nachkalkulationen ohne Soll-Stand bleiben unverändert.

Aufruf: python tests/test_nachkalk_auswertung.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import kennwerte, nachkalkulation as nk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# ------------------------------------------------------------------ alte Nachkalkulation ohne Soll-Stand
alt_id = beispiel_angebot.anlegen(db)
db.nachkalkulation_speichern(alt_id, dict(laser_h=3.0, am="2026-10-01T10:00:00"))
alt_vorher = db.angebot(alt_id)["nachkalkulation"]

# ------------------------------------------------------------------ fünf Aufträge mit Ist-Werten
FAKTOREN = (1.2, 1.25, 1.3, 1.2, 1.25)
seiten = []
for i, f in enumerate(FAKTOREN):
    s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    assert s.optimieren()
    v0 = nk.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, {}, kalk=s._rechnung())
    z0 = {z["text"]: z for z in v0["zeilen"]}
    assert "Fracht" in z0 and "Ausschuss" in z0 and z0["Ausschuss"]["soll"] == 0
    laser_soll = z0["Laserzeit"]["soll_menge"]
    werte = dict(laser_h=laser_soll * f, ruest_min=z0["Rüsten + Stangenwechsel"]["soll_menge"] + 10, fracht=z0["Fracht"]["soll"] + 50.0, ausschuss=12.5 * (i + 1),
                 ausschuss_stk=i + 1)
    s.nachkalk.setzen(werte)
    seiten.append((s, laser_soll, z0))
ist = db.angebot(seiten[0][0].id)["nachkalkulation"]
soll = ist["soll"]
assert soll["maschine"] and soll["kategorien"] and soll["teile"] > 0
zeilen = {z[0]: z for z in soll["zeilen"]}
assert zeilen["Laserzeit"][7] and not zeilen["Gewinde und Zusatzarbeiten"][7]       # nicht erfasst bleibt nicht erfasst
assert abs(zeilen["Fracht"][6] - (seiten[0][2]["Fracht"]["soll"] + 50.0)) < 1e-9 and zeilen["Fracht"][7]
assert zeilen["Ausschuss"][6] == 12.5
# Fracht und Ausschuss gehen in die Einzelkosten ein
v = nk.vergleich(seiten[0][0].kopf, seiten[0][0].positionen, seiten[0][0].ergebnis, seiten[0][0].k,
                 seiten[0][0].tabellen, seiten[0][0].einst, ist, kalk=seiten[0][0]._rechnung())
assert abs(v["summe"]["ist"] - sum(z["ist"] for z in v["zeilen"])) < 1e-9

# ------------------------------------------------------------------ Auswertung: unabhängige Kontrolle
e = nk.auswertung(db, "kostenart")
assert e["auftraege"] == 5 and e["ohne_soll"] == 1
lz = next(z for z in e["zeilen"] if z["kostenart"] == "Laserzeit")
assert lz["n"] == 5
kontrolle_soll = kontrolle_ist = 0.0
for s, laser_soll, z0 in seiten:
    z = {x[0]: x for x in db.angebot(s.id)["nachkalkulation"]["soll"]["zeilen"]}["Laserzeit"]
    kontrolle_soll += z0["Laserzeit"]["soll"]
    kontrolle_ist += z0["Laserzeit"]["soll"] / laser_soll * z[4]           # Ist-Stunden × Stundensatz des Solls
assert abs(lz["soll"] - kontrolle_soll) < 1e-6 and abs(lz["ist"] - kontrolle_ist) < 1e-6, (lz, kontrolle_ist)
assert abs(lz["median"] - 1.25) < 1e-9 and abs(lz["prozent"] - 100 * (kontrolle_ist / kontrolle_soll - 1)) < 1e-9
# nicht erfasste Kostenarten fehlen (keine Nullkosten)
assert not any(z["kostenart"] == "Gewinde und Zusatzarbeiten" for z in e["zeilen"])
# Ausschussquote = Σ Stück / Σ Teile
teile = sum(db.angebot(s.id)["nachkalkulation"]["soll"]["teile"] for s, _, _ in seiten)
assert e["ausschuss"]["stueck"] == 15 and e["ausschuss"]["teile"] == teile
for m in nk.MERKMALE:
    assert nk.auswertung(db, m)["zeilen"], m
mk = nk.auswertung(db, "menge")["zeilen"]
assert {z["gruppe"] for z in mk} <= {t for _, t in nk.MENGEN_KLASSEN}
# reproduzierbar
assert nk.auswertung(db, "maschine") == nk.auswertung(db, "maschine")

# ------------------------------------------------------------------ Kennwerte: Laserzeit mit Freigabe, Rüsten nur Vorschlag
vs = [x for x in kennwerte.vorschlaege(db, 5) if x["quelle"] == "laserzeit"]
assert len(vs) == 1 and vs[0]["status"] == "ok" and vs[0]["n"] == 5, vs
assert abs(vs[0]["faktor"] - 1.25) < 1e-9
maschine, kat = vs[0]["schluessel"]
vorher = {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten") if z["maschinen_id"] == maschine}
hid = kennwerte.freigeben(db, vs[0], "Test: Ist 25 % länger", "test")
nachher = {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten") if z["maschinen_id"] == maschine}
geaendert = [i for i in vorher if vorher[i] != nachher[i]]
assert geaendert and all(abs(nachher[i] - round(vorher[i] / 1.25)) < 1e-9 for i in geaendert)
assert kennwerte.zuruecknehmen(db, hid) > 0
assert {z["id"]: z["vorschub_gross"] for z in db.zeilen("schneiddaten") if z["maschinen_id"] == maschine} == vorher
vr = [x for x in kennwerte.vorschlaege(db, 5) if x["quelle"] == "ruesten"]
assert vr
try:
    kennwerte.freigeben(db, dict(vr[0], status="ok", faktor=vr[0]["faktor"] or 1.0), "x", "test")
    raise AssertionError("Rüsten-Vorschlag ließ sich anwenden")
except ValueError as ex:
    assert "nur Vorschläge" in str(ex)
# zu wenig Daten: keine Freigabe
assert all(x["status"] == "zu wenig Daten" for x in kennwerte.vorschlaege(db, 6) if x["quelle"] == "laserzeit")

# ------------------------------------------------------------------ Altbestand unverändert, Fenster
assert db.angebot(alt_id)["nachkalkulation"] == alt_vorher
d = seiten[0][0].nachkalk.auswertung(dialog=lambda d: None)
assert d.tabelle.rowCount() == len(d.ergebnis["zeilen"]) and "ohne gespeichertes Soll" in d.info.text()
d.merkmal.setCurrentIndex(1)
assert d.ergebnis["zeilen"][0]["gruppe"] == maschine
print("test_nachkalk_auswertung OK")
