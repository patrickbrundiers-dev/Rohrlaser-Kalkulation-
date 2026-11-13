"""Roadmap Kalkulation, Phase 2 Paket 2d Angebot (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“).

OFFER-009  Preisband ähnlicher Teile (beauftragt/abgelehnt) als Hinweis.
OFFER-011  Zielpreis: Hebel mit Wirkung.
OFFER-013  Rabattstaffel je Kunde nach Jahresumsatz als Vorschlag.
OFFER-016  Drei Liefertermine mit Preis (Express, Standard, flexibel) im Check und im PDF-Satz.
PART-007   Lieferzeit der Zukaufteile gegen den Termin.
CALC-009   Arbeitsplan je Position mit Liegezeit.
Neue Einstellungen und Felder leer = aus.

Aufruf: python tests/test_phase2d_1311.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import angebot_mehr as am, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import TABELLE  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[1])
K1 = db.zeilen("kunden")[0]["kundennr"]
HEUTE = datetime.date.today()


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def texte(s):
    z, sm = s._rechnung()
    return [p.text for p in s._angebot_mehr_punkte(z, sm)]


# ------------------------------------------------------------------ Vorgaben leer
assert "rabatt_staffel" in {f.name for f in TABELLE["kundenvorgaben"].felder}
for n in ("express_tage", "flexibel_tage", "flexibel_abschlag", "liegezeit_tage"):
    assert not db.einstellung(n), n
s = angebot(dict(ROHR, stueck=20), kopf=dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10"))
assert texte(s) == [], texte(s)
ok("Vorgaben: alles aus, keine neuen Hinweise")

# ------------------------------------------------------------------ OFFER-013 Rabattstaffel
zeilen = [dict(kundennr=K1, vorgang="Beauftragt", datum=(HEUTE - datetime.timedelta(days=30)).isoformat(),
               vk_netto=30000.0),
          dict(kundennr=K1, vorgang="Beauftragt", datum=(HEUTE - datetime.timedelta(days=400)).isoformat(),
               vk_netto=99999.0),
          dict(kundennr=K1, vorgang="Abgelehnt", datum=HEUTE.isoformat(), vk_netto=5000.0)]
assert am.jahresumsatz(zeilen, K1) == 30000.0
assert am.rabatt_vorschlag("10000 = 2; 25000 = 3", 30000) == 3.0
assert am.rabatt_vorschlag("10000 = 2", 5000) is None
assert "3,0 % Rabatt vorgeschlagen" in am.rabatt_punkt({}, "10000 = 2; 25000 = 3", 30000)
assert am.rabatt_punkt({"rabatt": 3.0}, "10000 = 2; 25000 = 3", 30000) is None
db.neu("kundenvorgaben", dict(kundennr=K1, rabatt_staffel="0 = 1"))
s.neu_laden()
assert any("Rabattstaffel des Kunden" in t and "1,0 % Rabatt" in t for t in texte(s)), texte(s)
ok("OFFER-013: Jahresumsatz der letzten 12 Monate, Staffel schlägt Rabatt vor")

# ------------------------------------------------------------------ OFFER-016 Drei Termine
assert am.standard_tage(dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10")) == 10
assert am.standard_tage(dict(lieferzeit_art="Wochen", lieferzeit_wert="2")) == 10
assert am.termine({}, 10) is None
assert am.termine(dict(express_tage=4, flexibel_tage=5, flexibel_abschlag=3), 10) == (6, 15, 3.0)
for n, w in (("express_tage", 4), ("flexibel_tage", 5), ("flexibel_abschlag", 3.0)):
    db.einstellung_setzen(n, w)
s.neu_laden()
t, preise = s.termine_preise()
assert preise["express"] > preise["standard"] > preise["flexibel"], preise
assert abs(preise["flexibel"] - preise["standard"] * 0.97) < 0.01
tx = [x for x in texte(s) if x.startswith("Liefertermine zur Wahl")]
assert tx and "Express in ca. 6 Arbeitstagen" in tx[0] and "flexibel in ca. 15 Arbeitstagen" in tx[0], tx
ang = s.angebot_daten(staffeln=False)
assert "Liefertermine zur Wahl" in ang["lieferzeit"], ang["lieferzeit"]
ok("OFFER-016: " + tx[0])

# ------------------------------------------------------------------ PART-007 Zukauf-Lieferzeit
aid = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Stopfen", einheit="Stück",
                                     aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                     aufschlag_wert=0),
                          [dict(lieferant="Kunststoff GmbH", preiseinheit=1, preise=[dict(ab=1, preis=0.2)],
                                lieferzeit=30)])
s = angebot(dict(ROHR, stueck=20, zukauf=json.dumps([dict(artikel_id=aid, menge=2)])),
            kopf=dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10"))
assert am.zukauf_lieferzeit(s.positionen, db.zukauf_artikel) == (30, "Stopfen")
assert any("Zukaufteil „Stopfen“ hat 30 Tage Lieferzeit" in t for t in texte(s)), texte(s)
assert am.lieferzeit_punkt(5, "x", HEUTE + datetime.timedelta(days=14)) is None
ok("PART-007: Zukaufteil mit 30 Tagen Lieferzeit gegen 10 Arbeitstage")

# ------------------------------------------------------------------ CALC-009 Arbeitsplan
p = dict(ROHR, zusatz=json.dumps([dict(name="Pulverbeschichten"), dict(name="Entgraten")], ensure_ascii=False))
schritte, tage = am.arbeitsplan(p, s.tabellen, 1)
assert [x[0] for x in schritte] == ["Laser schneiden", "Entgraten", "Pulverbeschichten"], schritte
assert tage == 3, tage
db.einstellung_setzen("liegezeit_tage", 5.0)
s = angebot(p, kopf=dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10"))
assert any("Arbeitsplan Laser schneiden → Entgraten → Pulverbeschichten" in t and "11 Arbeitstage" in t
           for t in texte(s)), texte(s)
ok("CALC-009: " + am.arbeitsplan_text(*am.arbeitsplan(p, s.tabellen, 5)))

# ------------------------------------------------------------------ OFFER-009 Preisband
kw = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=860.0, eur_kg=9.0)
daten = am.band_daten([("Beauftragt", [dict(kennwerte=[dict(kw, eur_kg=5.0)])]),
                       ("Beauftragt", [dict(kennwerte=[dict(kw, eur_kg=6.0, laenge=1000.0)])]),
                       ("Abgelehnt", [dict(kennwerte=[dict(kw, eur_kg=8.0)])]),
                       ("Verschickt", [dict(kennwerte=[dict(kw, eur_kg=1.0)])]),
                       ("Beauftragt", [dict(kennwerte=[dict(kw, eur_kg=2.0, laenge=3000.0)])])])
b = am.band(daten, kw)
assert sorted(b["ja"]) == [5.0, 6.0] and b["nein"] == [8.0], b
t = am.band_punkt(10, kw, b)
assert t and "beauftragt 5,00–6,00 €/kg" in t and "abgelehnt Median 8,00" in t, t
assert am.band_punkt(10, dict(kw, eur_kg=5.5), b) is None
ok("OFFER-009: " + t)

# ------------------------------------------------------------------ OFFER-011 Hebel
h = am.hebel(100.0, 130.0, [("A", 120.0), ("B", 95.0), ("C", None), ("D", 140.0)])
assert [x[0] for x in h] == ["B", "A"] and h[0][3] and not h[1][3]
s = angebot(dict(ROHR, stueck=20, zusatz=json.dumps([dict(name="Feuerverzinken")], ensure_ascii=False)))
z, sm = s._rechnung()
txt = s.zielpreis_hebel(sm["verkauf"] * 0.8)
assert "Gewinn halbiert" in txt and "ohne Fremdleistungen" in txt and "doppelte Menge" in txt, txt
ok("OFFER-011: " + txt[:160] + " …")

fenster.close()
db.schliessen()
print("Alle Prüfungen Paket 2d bestanden.")
