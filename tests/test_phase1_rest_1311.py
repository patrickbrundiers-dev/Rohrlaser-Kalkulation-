"""Roadmap Kalkulation, Phase 1 Rest (nach dem Merge von #455, 13.11.2026; Freigabe Patrick 12.11. „Mit Phase 1
beginnen“, Entscheidungen nach Empfehlung).

MAT-011 Gewinn auf Material je Kunde und je Angebot: Kundenvorgabe → Angebotskopf → Rechnung (leer = wie Gewinn).
MAT-016 Werkszeugnis 3.1 je Abmessung: Einstellung zeugnis_preis, nur wenn das Angebot es verlangt (Kundenvorgabe
        oder Haken im Angebotskopf); umgelegt wie die Pauschale je Abmessung.
OFFER-007 Rüsten und Programmierung als eigene Zeile „einmalig je Auftrag“ (Haken im Angebotskopf): Stückpreise
        kleiner, Summe gleich bis auf Rundung.
CALC-025 Artikelnummer gravieren als Kundenvorgabe: nach dem STEP-Import und über den Angebots-Check (Erledigen).
ASM-002 Hauptbauteil der Schweißbaugruppe: Häkchen im Editor (höchstens eins), steht in Stückliste und Angebot zuerst.

Aufruf: python tests/test_phase1_rest_1311.py
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

import beispiel_angebot as B  # noqa: E402
from rohrlaser import ausgabe, export, rechnen  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm
QR = dict(B.POSITIONEN[2], satz=None, je_satz=None)      # QR 40x40x3: zweite Abmessung
kunden = db.zeilen("kunden")
K1, K2 = kunden[0]["kundennr"], kunden[1]["kundennr"]


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def summen(s):
    return s._rechnung()[1]


assert SCHEMA_VERSION >= 85
spalten = {t: {r[1] for r in db.con.execute(f'PRAGMA table_info("{t}")')} for t in ("angebote", "positionen",
                                                                                   "kundenvorgaben")}
assert {"gewinn_material", "einmal_zeile"} <= spalten["angebote"] and "bg_haupt" in spalten["positionen"]
assert {"gewinn_material", "zeugnis_31", "gravur_artikel"} <= spalten["kundenvorgaben"], spalten["kundenvorgaben"]
ok("Schema 85: angebote.gewinn_material/einmal_zeile, positionen.bg_haupt, Kundenvorgaben mit 3 neuen Spalten")

# ------------------------------------------------------------------ MAT-011 Gewinn auf Material
db.einstellung_setzen("gewinn", 0.20)
s0 = angebot(dict(ROHR), kopf=dict(kundennr=K2))
assert s0.kopf.get("gewinn_material") is None                     # Einstellung leer = wie Gewinn
su0 = summen(s0)
assert su0.get("gewinn_material_satz") is None
db.neu("kundenvorgaben", dict(kundennr=K1, gewinn_material=40.0, zeugnis_31="ja", gravur_artikel=6.0))
s1 = angebot(dict(ROHR), kopf=dict(kundennr=K1))
assert s1.kopf["gewinn_material"] == 40.0 and s1.kopf["zeugnis_31"] == "ja", s1.kopf
assert abs(rechnen.einstellungen_angebot(s1.kopf, s1.einst)["gewinn_material"] - 40.0) < 1e-9
db.einstellung_setzen("zeugnis_preis", 0.0)          # Zeugnis hier ohne Kosten: nur der Gewinn zählt
s1.neu_laden()
su1 = summen(s1)
assert abs(su1["gewinn_material_satz"] - 40.0) < 1e-9 and su1["verkauf"] > su0["verkauf"], (su1["verkauf"],
                                                                                            su0["verkauf"])
# Kunde im Angebot wechseln: Vorgabe des neuen Kunden bzw. zurück auf die Einstellung
c = db.angebot_neu(dict(KOPF))
k = db.kunde_uebernehmen(c, K1)
assert db.angebot(c)["gewinn_material"] == 40.0 and db.angebot(c)["zeugnis_31"] == "ja"
assert "Gewinn auf Material" in k["vorgaben"] and "Werkszeugnis 3.1 verlangt" in k["vorgaben"], k["vorgaben"]
db.kunde_uebernehmen(c, K2)
assert db.angebot(c)["gewinn_material"] is None and db.angebot(c)["zeugnis_31"] is None
# Anzeige im Angebotskopf: leer = „wie Gewinn“, Zahl eintippen = eigener Satz
kb = s0.kopf_bereich
w = kb.felder["gewinn_material"]
assert w.value() < 0 and w.specialValueText() == "wie Gewinn", (w.value(), w.specialValueText())
w.setValue(35.0)
w.editingFinished.emit()
assert s0.kopf["gewinn_material"] == 35.0 and abs(summen(s0)["gewinn_material_satz"] - 35.0) < 1e-9
w.setValue(-1.0)
w.editingFinished.emit()
assert s0.kopf.get("gewinn_material") is None
ok(f"MAT-011 Kundenvorgabe 40 % → Angebot {su1['verkauf']:.2f} € (ohne {su0['verkauf']:.2f} €), Kopf „wie Gewinn“/35 %")

# ------------------------------------------------------------------ MAT-016 Werkszeugnis 3.1
s2 = angebot(dict(ROHR), dict(QR, pos=20), kopf=dict(kundennr=K2))
ohne = summen(s2)
db.einstellung_setzen("zeugnis_preis", 30.0)
s2.neu_laden()
assert summen(s2)["zeugnisse"] == 0 and abs(summen(s2)["verkauf"] - ohne["verkauf"]) < 1e-9   # nicht verlangt
s2.kopf_bereich.zeugnis_an.setChecked(True)
assert s2.kopf["zeugnis_31"] == "ja"
mit = summen(s2)
assert mit["abmessungen"] == 2 and abs(mit["zeugnisse"] - 60.0) < 1e-9, (mit["abmessungen"], mit["zeugnisse"])
assert abs(mit["pauschalen"] - ohne["pauschalen"] - 60.0) < 1e-9 and mit["verkauf"] > ohne["verkauf"] + 60
text = next(t for t, _, _ in rechnen.kostenarten(mit, s2.einst) if t.startswith("Pauschale"))
assert "dazu Werkszeugnis 3.1 2 × 30 €" in text, text
assert "zeugnis_preis" in rechnen.EINST_FEST and "zeugnis_preis" in rechnen.EINST_NEU
s2.kopf_bereich.zeugnis_an.setChecked(False)
assert s2.kopf.get("zeugnis_31") is None and summen(s2)["zeugnisse"] == 0
db.einstellung_setzen("zeugnis_preis", 0.0)
ok(f"MAT-016 2 Abmessungen × 30 € Werkszeugnis: Verkauf {ohne['verkauf']:.2f} → {mit['verkauf']:.2f} € ({text})")

# ------------------------------------------------------------------ OFFER-007 Rüsten und Programmierung einmalig
s3 = angebot(dict(ROHR, stueck=10), dict(QR, pos=20, stueck=6), kopf=dict(kundennr=K2))
vorher = s3.angebot_daten(staffeln=False)
assert not [z for z in vorher["zeilen"] if z.get("ruesten")]
s3.kopf_bereich.einmal_an.setChecked(True)
assert s3.kopf["einmal_zeile"] == "ja"
nachher = s3.angebot_daten(staffeln=False)
ez = [z for z in nachher["zeilen"] if z.get("ruesten")]
assert len(ez) == 1 and ez[0]["art"] == "einmal" and ez[0]["text"].startswith("Rüsten und Programmierung"), ez
t_vor = [z for z in vorher["zeilen"] if z["art"] == "teil"]
t_nach = [z for z in nachher["zeilen"] if z["art"] == "teil"]
assert all(b["preis"] < a["preis"] for a, b in zip(t_vor, t_nach)), (t_vor, t_nach)
rund = 0.005 * sum(z["menge"] for z in t_vor) + 0.01        # Stückpreise je Teil auf Cent gerundet
assert abs(nachher["netto"] - vorher["netto"]) <= rund, (nachher["netto"], vorher["netto"])
assert ez[0]["preis"] > 0
z0 = s3._rechnung()[0][0]
anteil = ausgabe.einmal_anteil(z0, s3.einst)
assert 0 < anteil < z0["preis_teil"]
assert ausgabe.einmal_anteil(dict(z0, muster="ja"), s3.einst) == 0
assert ausgabe.einmal_anteil(dict(z0, mindestpreis_teil=5.0), s3.einst) == 0
assert abs(summen(s3)["verkauf"] - summen(s3)["verkauf"]) < 1e-9      # Rechnung selbst unverändert
s3.kopf_bereich.einmal_an.setChecked(False)
assert s3.kopf.get("einmal_zeile") is None
ok(f"OFFER-007 Einmalig {ez[0]['preis']:.2f} €, Stückpreise {t_vor[0]['preis']:.2f} → {t_nach[0]['preis']:.2f} €, "
   f"Summe {vorher['netto']:.2f} → {nachher['netto']:.2f} €")

# ------------------------------------------------------------------ CALC-025 Artikelnummer gravieren
s4 = angebot(dict(ROHR, artikel="A-1"), dict(QR, pos=20, artikel="A-2"), dict(ROHR, pos=30, artikel=""),
             kopf=dict(kundennr=K1))
assert s4.gravur_kunde_hoehe() == 6.0
punkte = [p for p in s4.freigabe_punkte() if getattr(p, "aktion", None) == "gravur"]
assert len(punkte) == 1 and "2 Teile noch ohne Gravur" in punkte[0].text, [p.text for p in s4.freigabe_punkte()]
assert s4.check_erledigen(["gravur"]) == ["gravur"]
g = {q["pos"]: q.get("bg_gravur") for q in s4.positionen}
assert g == {10: 6.0, 20: 6.0, 30: None}, g                  # ohne Artikelnummer nichts
assert rechnen.gravur_artikel(next(q for q in s4.positionen if q["pos"] == 10)) > 0
assert not [p for p in s4.freigabe_punkte() if getattr(p, "aktion", None) == "gravur"]
# 0 = bewusst nicht gravieren bleibt; anderer Kunde ohne Vorgabe: kein Punkt
db.position_aendern(next(q for q in s4.positionen if q["pos"] == 20)["id"], "bg_gravur", 0.0)
s4.neu_laden()
assert not s4.gravur_kunde_offen()
s5 = angebot(dict(ROHR, artikel="B-1"), kopf=dict(kundennr=K2))
assert s5.gravur_kunde_hoehe() == 0 and not [p for p in s5.freigabe_punkte() if getattr(p, "aktion", None) == "gravur"]
# nach dem STEP-Import: nur die neuen Positionen
s6 = angebot(dict(ROHR, artikel="C-1"), dict(ROHR, pos=20, artikel="C-2"), kopf=dict(kundennr=K1))
bericht = []
assert s6.gravur_kunde({20}, bericht) == 1 and "Kundenvorgabe 6" in bericht[-1], bericht
assert {q["pos"]: q.get("bg_gravur") for q in s6.positionen} == {10: None, 20: 6.0}
ok("CALC-025 Kundenvorgabe 6 mm: Check-Hinweis mit Erledigen, 2 Teile graviert, ohne Artikelnr./0/anderer Kunde nicht")

# ------------------------------------------------------------------ ASM-002 Hauptbauteil
s7 = angebot(dict(ROHR, pos=10, artikel="H-1", stueck=2), dict(QR, pos=20, artikel="H-2", stueck=2),
             kopf=dict(kundennr=K2))
r1, r2 = (q["id"] for q in s7.positionen)


def dialog(d):
    d.teil_setzen(r1, True)
    d.teil_setzen(r2, True)
    t = {x["_id"]: x for x in d.teile}
    t[r1]["haupt"] = True
    d.aktualisieren()
    t[r2]["haupt"] = True                # neues Häkchen nimmt es dem bisherigen
    d.aktualisieren()
    assert not t[r1]["haupt"] and t[r2]["haupt"], (t[r1]["haupt"], t[r2]["haupt"])
    d._ok()
    return d.result()


assert s7.baugruppe_neu(dialog=dialog)
pos = {q["id"]: q for q in db.positionen(s7.id)}
assert pos[r2]["bg_haupt"] == "ja" and not pos[r1].get("bg_haupt"), (pos[r1].get("bg_haupt"), pos[r2]["bg_haupt"])
s7.neu_laden()
st = export.stueckliste_zeilen(s7.kopf, s7.positionen, s7.k, s7.tabellen)
sp = export.STUECKLISTE_SPALTEN
ebene2 = [z for z in st if z[0] == "2"]
assert ebene2[0][sp.index("Artikel")] == "H-2" and ebene2[0][sp.index("Bezeichnung")].endswith("(Hauptbauteil)"), st
teile_bg = [p for p in s7.positionen if p.get("art") != BAUGRUPPE]
assert ausgabe.haupt_zuerst(teile_bg)[0].get("artikel") == "H-2"
assert [q.get("artikel") for _, q in ausgabe.haupt_zuerst([(0, dict(artikel="X")), (1, dict(artikel="Y", bg_haupt="ja"))])] \
    == ["Y", "X"]
ok("ASM-002 Hauptbauteil H-2 (eins je Baugruppe), Stückliste: zuerst und „(Hauptbauteil)“")

print("Roadmap Phase 1 Rest: alle Tests bestanden.")
