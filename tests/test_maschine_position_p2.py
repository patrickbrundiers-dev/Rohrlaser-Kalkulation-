"""Maschine je Position (MACH-006 Variante B, Patrick 13.11.2026 „Alle Empfehlungen“), Paket 2:

- P1 Auslastung: Laserzeit je eingesetzter Maschine (Summe = Laserzeit des Angebots), Bedarf auf beiden Maschinen;
  ohne abweichende Maschine genau wie bisher
- P2 Schnittstelle zur Rohrlaser Auslastung: je Maschine ein Teilauftrag „<Nummer> @ <Maschine>“ (eigene Datei,
  eine Maschine je Datei), Laser + Rüsten über alle Teile = Maschinenzeit; Position zurück auf die Kopf-Maschine:
  Storno des Teilauftrags; Ist-Laserzeit erst, wenn alle Teile fertig sind
- P3 Fertigungslos: Positionen auf einer anderen Maschine bleiben im Auftrag (Hinweis „getrennt“)
- P4 Werkstattpapiere: Material und Stangenmuster nennen die abweichende Maschine, Hinweis oben
- P5 Liefertermin-Vorschlag: je Maschine gerechnet, der späteste zählt

Aufruf: python tests/test_maschine_position_p2.py   (QT_QPA_PLATFORM=offscreen)
"""
import csv
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import (ausgabe, auslastung, auslastung_austausch as aa, einlastung, fertigungslos,  # noqa: E402
                       terminplan)
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def lesen(pfad):
    with open(pfad, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def zahl(t):
    return float(t.replace(",", ".")) if t else 0.0


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
f = Hauptfenster(db, stumm=True)
ordner = tmp / "Auslastung"


def auftrag(nummer, m_b, termin="2026-12-18"):
    a = db.angebot_neu(dict(kunde="Beispiel GmbH", maschine="T03", stange=6000, skonto=0, nummer=nummer))
    db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                            stueck=40, schneidweg=200, einstiche=1))
    db.position_neu(a, dict(pos=20, artikel="B", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                            stueck=30, schneidweg=250, einstiche=2, maschine=m_b))
    s = f.angebot_oeffnen(a)
    assert s.optimieren()
    s.neu_laden()
    f.angebot_schliessen(a)
    assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=(f"K-{nummer}", termin))
    return a


# ------------------------------------------------------------------ P1 Auslastung
ein = auftrag("2026-0901", None)
zwei = auftrag("2026-0902", "LT7")
je1 = auslastung.maschinenzeit_je(db, db.angebot(ein))
h1, g1 = auslastung.maschinenzeit(db, db.angebot(ein))
assert je1 == {"T03": (h1, g1)}, je1
je2 = auslastung.maschinenzeit_je(db, db.angebot(zwei))
h2, _ = auslastung.maschinenzeit(db, db.angebot(zwei))
assert set(je2) == {"T03", "LT7"} and all(h > 0 for h, _g in je2.values()), je2
assert abs(sum(h for h, _g in je2.values()) - h2) < 1e-9
aus = auslastung.berechnen(db)
teile = [x for l in aus["auftraege"].values() for x in l if x["id"] == zwei]
assert {x["maschine"] for x in teile} == {"T03", "LT7"} and all(x.get("teil") for x in teile), teile
assert any(x["nummer"] == "2026-0902 (LT7)" for x in teile)
assert [x for l in aus["auftraege"].values() for x in l if x["id"] == ein][0].get("teil") is None
e = einlastung.rechnen(aus)
assert {a["maschine"] for a in e["auftraege"] if a["id"] == zwei} == {"T03", "LT7"}
ok(f"P1 Auslastung: Auftrag mit LT7-Position auf T03 {je2['T03'][0]:.2f} h + LT7 {je2['LT7'][0]:.2f} h "
   f"(= {h2:.2f} h), Auftrag ohne Abweichung unverändert")

# ------------------------------------------------------------------ P2 Schnittstelle
dateien = sorted(ordner.glob("Auftrag-2026-0902*.csv"))
assert len(dateien) == 2, dateien
nach_nr = {}
for d in dateien:
    z = lesen(d)
    assert len({r["Maschine"] for r in z}) == 1 and len({r["Auftragsnummer"] for r in z}) == 1
    nach_nr[z[0]["Auftragsnummer"]] = z
assert set(nach_nr) == {"2026-0902", "2026-0902 @ LT7"}
assert {r["Maschine"] for r in nach_nr["2026-0902 @ LT7"]} == {"LT7"}
assert [r["Artikel"] for r in nach_nr["2026-0902 @ LT7"] if r["Art"] == aa.POSITION] == ["B"]
assert [r["Artikel"] for r in nach_nr["2026-0902"] if r["Art"] == aa.POSITION] == ["A"]
for nr, z in nach_nr.items():
    assert any(r["Art"] == aa.STANGEN for r in z), nr
    assert zahl([r for r in z if r["Art"] == aa.POSITION][0]["Rüstzeit [min]"]) > 0, nr   # Rüsten je Maschine
summe = sum(zahl(r["Laserzeit [min]"]) + zahl(r["Rüstzeit [min]"]) for z in nach_nr.values() for r in z
            if r["Art"] == aa.POSITION)
assert abs(summe - h2 * 60) < 0.05 * len(nach_nr) * 2, (summe, h2 * 60)
assert len(lesen(sorted(ordner.glob("Auftrag-2026-0901*.csv"))[0])) and \
    {r["Auftragsnummer"] for r in lesen(sorted(ordner.glob("Auftrag-2026-0901*.csv"))[0])} == {"2026-0901"}
# Ist-Laserzeit erst, wenn alle Teile fertig sind
r = dict(auftraege=[dict(nummer="2026-0902", pos=None, arbeitsgang=None, status="fertig", tatsaechlich=60),
                    dict(nummer="2026-0902 @ LT7", pos=None, arbeitsgang=None, status="läuft", tatsaechlich=10)])
assert aa.ist_laser_h(db, "2026-0902", r) is None
r["auftraege"][1].update(status="fertig", tatsaechlich=30)
assert abs(aa.ist_laser_h(db, "2026-0902", r) - 1.5) < 1e-9
assert aa.gehoert_zu("2026/00042 @ LT7", "2026/00042") and not aa.gehoert_zu("2026/000421", "2026/00042")
# Position zurück auf die Kopf-Maschine: Teilauftrag storniert
pid = [p for p in db.positionen(zwei) if p["pos"] == 20][0]["id"]
db.position_aendern(pid, "maschine", None)
s = f.angebot_oeffnen(zwei)
assert s.optimieren()
s.neu_laden()
f.angebot_schliessen(zwei)
aa.schreiben(db, zwei)
storno = [d for d in ordner.glob("Auftrag-2026-0902*.csv") if any(x["Art"] == aa.STORNO for x in lesen(d))]
assert len(storno) == 1 and lesen(storno[0])[0]["Auftragsnummer"] == "2026-0902 @ LT7", storno
db.position_aendern(pid, "maschine", "LT7")
s = f.angebot_oeffnen(zwei)
assert s.optimieren()
s.neu_laden()
f.angebot_schliessen(zwei)
aa.schreiben(db, zwei)
ok("P2 Schnittstelle: Teilauftrag „2026-0902 @ LT7“ als eigene Datei mit Maschine LT7, Laser + Rüsten aller Teile "
   f"= {h2 * 60:.1f} min, Storno bei Rückkehr auf T03, Ist-Zeit erst mit allen Teilen")

# ------------------------------------------------------------------ P3 Fertigungslos
los = fertigungslos.zusammenstellen(db, [ein, zwei])
assert los["kopf"]["maschine"] == "T03"
assert any("läuft auf Maschine LT7" in t and "Pos. 20" in t for t in los["getrennt"]), los["getrennt"]
assert not any(p.get("los_angebot") == "2026-0902" and p.get("los_pos") == 20 for p in los["positionen"])
ok("P3 Fertigungslos auf T03: Pos. 20 (LT7) bleibt im Auftrag")

# ------------------------------------------------------------------ P4 Werkstattpapiere
a = db.angebot(zwei)
wp = ausgabe.werkstatt(a, db.positionen(zwei), a["ergebnis"], db.kontext(), db.tabellen())
assert any("Maschine LT7" in m["werkstoff"] for m in wp["material"]), wp["material"]
assert any(m.get("maschine") == "LT7" for m in wp["muster"]) and any(not m.get("maschine") for m in wp["muster"])
assert any(h["werkstoff"] == "Maschine LT7" and "Pos. 20" in h["text"] for h in wp["hinweise"])
from rohrlaser import pdf  # noqa: E402
pdf.werkstatt_pdf(tmp / "w.pdf", a, wp, True, db.einstellungen())
assert (tmp / "w.pdf").stat().st_size > 1000
ok("P4 Werkstattpapiere: Material, Stangenmuster und Hinweis nennen die Maschine LT7")

# ------------------------------------------------------------------ P5 Liefertermin-Vorschlag
t = terminplan.fruehester(db, zwei)
assert t is not None and abs(t.laser_h - h2) < 1e-6
je2 = auslastung.maschinenzeit_je(db, db.angebot(zwei))
for m_, (h_, _g) in je2.items():
    t_m = terminplan.fruehester(db, zwei, maschine=m_, laser_h=h_)
    assert t.datum is None or t_m.datum <= t.datum, (m_, t_m.datum, t.datum)
assert all(x.split(": ", 1)[0] in je2 for x in t.hinweise), t.hinweise
t1 = terminplan.fruehester(db, ein)
assert t1 is not None
ok(f"P5 Liefertermin-Vorschlag je Maschine: {t.datum} (ohne Abweichung {t1.datum})")
print("Alle Prüfungen bestanden.")
