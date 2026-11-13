"""Roadmap Kalkulation, Phase 2 Paket 2a (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“).

ASM-004   Schweißbaugruppe: Preis lose Einzelteile neben dem Preis geschweißt (Haken im Angebotskopf).
OFFER-003 Teilbestell-Risiko: jede Position bzw. jeder Satz allein gerechnet, Hinweis ab Schwelle, Vorbehalt im PDF.
OFFER-004 Sinnvolle Staffelstufen: Probe-Rechnung mit größeren Mengen, Übernahme nur per Haken.
OFFER-008 Preisabweichung zum Wiederholteil in Ursachen zerlegt, Summe = Unterschied, Satz für den Kunden.
GEO-009   Merkmal-Regeln: Bohrungs-Ø und Wand als Bedingung der Arbeitsgang-Regeln, Übersicht aller Regeln.

Aufruf: python tests/test_phase2a_1311.py
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
import beispiel_baugruppe as BG  # noqa: E402
from rohrlaser import ausgabe, stufen_vorschlag, teilbestellung, wiederhol_erklaerung  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, bedingungen_text  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm
QR = dict(B.POSITIONEN[2], satz=None, je_satz=None)      # QR 40x40x3: zweite Abmessung
K1 = db.zeilen("kunden")[0]["kundennr"]


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


spalten = {r[1] for r in db.con.execute('PRAGMA table_info("angebote")')}
assert {"teilbestell_vorbehalt", "bg_lose"} <= spalten, spalten
assert db.einstellung("teilbestell_schwelle") == 0 and not db.einstellung("teilbestell_text")
ok("Felder angebote.teilbestell_vorbehalt/bg_lose; Einstellungen Teilbestellung 0 bzw. leer (aus)")

# ------------------------------------------------------------------ ASM-004 lose Einzelteile
a = BG.anlegen(db)
s = fenster.angebot_oeffnen(a)
s.optimieren()
zeilen = s._rechnung()[0]
ang = ausgabe.angebot(s.kopf, s.positionen, zeilen, s.k, s.einst)
bgz = next(z for z in ang["zeilen"] if z.get("baugruppe"))
assert bgz.get("preis_lose") is None and "lose Einzelteile" not in bgz["text"]
db.angebot_aendern(a, "bg_lose", "ja")
s.neu_laden()
zeilen = s._rechnung()[0]
ang2 = ausgabe.angebot(s.kopf, s.positionen, zeilen, s.k, s.einst)
bgz2 = next(z for z in ang2["zeilen"] if z.get("baugruppe"))
assert ang2["netto"] == ang["netto"], (ang2["netto"], ang["netto"])           # nur Angabe, Summe gleich
assert 0 < bgz2["preis_lose"] < bgz2["preis"], (bgz2["preis_lose"], bgz2["preis"])
assert "Alternativ als lose Einzelteile (nicht geschweißt)" in bgz2["text"], bgz2["text"]
i_bg = next(i for i, p in enumerate(s.positionen) if p.get("art") == BAUGRUPPE)
schweiss = ausgabe.schweiss_anteil(zeilen[i_bg], s.positionen[i_bg], s.kopf, s.k)
assert schweiss > 0 and abs(bgz2["preis"] - bgz2["preis_lose"] - schweiss) < 0.02, \
    (bgz2["preis"], bgz2["preis_lose"], schweiss)
assert s.kopf_bereich.bg_lose_an.isChecked()
ok(f"ASM-004 Rahmen R1: geschweißt {bgz2['preis']:.2f} €, lose {bgz2['preis_lose']:.2f} € (Schweißen "
   f"{schweiss:.2f} €), Summe unverändert")

# ------------------------------------------------------------------ OFFER-003 Teilbestell-Risiko
s3 = angebot(dict(ROHR, stueck=4), dict(QR, pos=20, stueck=3))
z3 = s3._rechnung()[0]
erg = teilbestellung.rechnen(s3.kopf, s3.positionen, z3, s3.k, s3.st_seite._args()[4], s3.einst)
assert len(erg) == 2 and all(r["allein"] is not None for r in erg), erg
assert all(r["allein"] > r["angebot"] for r in erg), [(r["allein"], r["angebot"]) for r in erg]   # Rüsten geteilt
assert not [p for p in s3.freigabe_punkte(mehrmenge=True) if "Teilbestell" in p.text]       # Schwelle 0 = aus
db.einstellung_setzen("teilbestell_schwelle", 1.0)
s3.neu_laden()
s3.optimieren()
punkte = [p for p in s3.freigabe_punkte(mehrmenge=True) if "Teilbestell" in p.text]
assert len(punkte) == 2 and punkte[0].aktion == "teilbestell", [p.text for p in punkte]
assert s3.check_erledigen(["teilbestell"]) == ["teilbestell"]
assert db.angebot(s3.id)["teilbestell_vorbehalt"] == "ja" and s3.kopf_bereich.teilbestell_an.isChecked()
s3.optimieren()
punkte = [p for p in s3.freigabe_punkte(mehrmenge=True) if "Teilbestell" in p.text]
assert punkte and all(p.aktion is None and "Vorbehalt steht im Angebot" in p.text for p in punkte)
ang3 = ausgabe.angebot(s3.kopf, s3.positionen, s3._rechnung()[0], s3.k, s3.einst)
assert teilbestellung.TEXT in ang3["bedingungen"], ang3["bedingungen"]
assert bedingungen_text(dict(teilbestell_vorbehalt="ja"), "Preise netto.", "Eigener Text.") == "Preise netto.\nEigener Text."
assert bedingungen_text({}, "Preise netto.", "Eigener Text.") == "Preise netto."
assert teilbestellung.text(dict(teilbestell_text=" Eigener Text. ")) == "Eigener Text."
db.einstellung_setzen("teilbestell_schwelle", 0.0)
# eine Position allein: kein Risiko
assert teilbestellung.rechnen(s3.kopf, s3.positionen[:1], z3[:1], s3.k, s3.tabellen, s3.einst) == []
ok("OFFER-003 Teilbestellung: beide Positionen allein teurer, Check ab 1 % mit Erledigen, Vorbehalt im PDF")

# ------------------------------------------------------------------ OFFER-004 Sinnvolle Stufen
s4 = angebot(dict(ROHR, stueck=3))
vs = stufen_vorschlag.vorschlaege(s4.kopf, s4.positionen, s4.k, s4.tabellen, s4.einst)
assert [v["faktor"] for v in vs] == list(stufen_vorschlag.FAKTOREN), [v["faktor"] for v in vs]
assert all(vs[i]["preis_index"] >= vs[i + 1]["preis_index"] - 1e-9 for i in range(len(vs) - 1)), \
    [v["preis_index"] for v in vs]                    # größere Menge: günstiger je Teil
assert vs[0]["preis_index"] < 1 and any(v["empfohlen"] for v in vs)
assert all(v["mengen"]["10"] >= 3 * v["faktor"] for v in vs)
assert any(v["voll"] for v in vs), [(v["faktor"], v["mengen"], v["stangen"]) for v in vs]     # Stange aufgefüllt
assert not db.staffel_stufen(s4.id) if hasattr(db, "staffel_stufen") else True             # nichts von selbst
vorher = len(db.staffeln(s4.id))


def waehlen(d):
    for c in d.haken:
        c.setChecked(False)
    d.haken[0].setChecked(True)
    d.haken[2].setChecked(True)
    return True


ids = s4.st_seite.sinnvolle_stufen(dialog=waehlen)
assert len(ids) == 2 and len(db.staffeln(s4.id)) == vorher + 2, (ids, db.staffeln(s4.id))
assert sorted(z["menge"] for z in db.staffeln(s4.id))[-1] == vs[2]["mengen"]["10"]
assert s4.st_seite.sinnvolle_stufen(dialog=lambda d: False) == []          # Abbrechen: nichts
ok(f"OFFER-004 Sinnvolle Stufen: {len(vs)} Faktoren, Preis je Teil sinkt "
   f"({100 * (vs[0]['preis_index'] - 1):.0f} % … {100 * (vs[-1]['preis_index'] - 1):.0f} %), 2 angehakt angelegt")

# ------------------------------------------------------------------ OFFER-008 Preis erklären
alt_id = db.angebot_neu(dict(KOPF, kundennr=K1, datum="2026-09-12"))
db.position_neu(alt_id, dict(ROHR, artikel="W-1", stueck=10))
db.position_neu(alt_id, dict(QR, pos=20, artikel="W-2", stueck=5))
db.vorgang_setzen(alt_id, "Beauftragt")
s_alt = fenster.angebot_oeffnen(alt_id)
assert s_alt.optimieren() and s_alt.staffelpreise_aktuell() is not None
db.staffel_neu(alt_id, dict(schluessel="10", menge=10))
s_alt.neu_laden()
s_alt.optimieren()
assert s_alt.staffelpreise_rechnen()
db.einstellung_setzen("gewinn", (db.einstellung("gewinn") or 0.2) + 0.05)       # heute 5 Punkte mehr Gewinn
s8 = angebot(dict(ROHR, artikel="W-1", stueck=25, laenge=1300.0), dict(QR, pos=20, artikel="X-9", stueck=5))
r = s8.wiederholpreis_erklaeren(0, zeigen=False)
assert r is not None and not r["nachgerechnet"], r
summe = sum(x["eur"] for x in r["schritte"])
assert abs(r["damals"] + summe - r["heute"]) < 1e-6, (r["damals"], summe, r["heute"])
namen = {x["name"]: x for x in r["schritte"]}
assert "50 mm länger" in namen["Teil oder Eingaben geändert"]["text"], namen
assert "Programm schon vorhanden" in namen["Teil oder Eingaben geändert"]["text"], namen
assert namen["Menge"]["eur"] < 0 and "25 statt 10 Stück" in namen["Menge"]["text"]      # mehr Stück: günstiger
assert namen["Preise und Kalkulationswerte seit damals"]["eur"] > 0      # mehr Gewinn
assert r["satz"].startswith("Gegenüber unserem Angebot") and "Bestellmenge" in r["satz"], r["satz"]
assert "Preis erklären" in s8.uebersicht_bereich.wiederholteile.text()
assert s8.wiederholpreis_erklaeren(1, zeigen=False) is None              # X-9: kein Wiederholteil
s = wiederhol_erklaerung.satz_kunde(5.0, 5.0, 10, 10, [])
assert "gleich geblieben" in s, s
ok(f"OFFER-008 Wiederholteil W-1: damals {r['damals']:.2f} €, heute {r['heute']:.2f} €, 4 Schritte = Unterschied; "
   f"Satz: {r['satz'][:70]}…")

# ------------------------------------------------------------------ GEO-009 Merkmal-Regeln
from rohrlaser import merkmal_regeln, rechnen, zusatz_regeln as zr  # noqa: E402
from rohrlaser.fenster import StammdatenSeite  # noqa: E402
from rohrlaser.stammdaten import TABELLE  # noqa: E402

spalten = {r[1] for r in db.con.execute('PRAGMA table_info("arbeitsgang_regeln")')}
assert {"bohr_von", "bohr_bis", "wand_von", "wand_bis"} <= spalten, spalten
k = db.kontext()
p = dict(ROHR, bohrungen="4xØ8,5; 2xØ5")            # RR 42,4x2,0: Wand 2
r_senk = dict(name="Senken M8", zusatzarbeit="Senken", merkmal="Bohrungen", bohr_von=8.4, bohr_bis=8.6,
              menge_art="Anzahl Bohrungen", aktiv="ja")
assert zr.trifft(r_senk, p, {}, k, ()) and zr.regel_menge(r_senk, p, ()) == 4.0
assert zr.anzahl_bohrungen(p) == 6.0                       # ohne Bereich: alle
assert not zr.trifft(r_senk, dict(p, bohrungen="2xØ5"), {}, k, ())      # keine Bohrung im Bereich
assert zr.trifft(dict(r_senk, wand_von=1.5, wand_bis=2.5), p, {}, k, ())
assert not zr.trifft(dict(r_senk, wand_von=3), p, {}, k, ())
assert zr.genauigkeit(r_senk) > zr.genauigkeit(dict(r_senk, bohr_von=None, bohr_bis=None))
assert zr.pruefung(dict(r_senk, bohr_von=9)) == "FEHLER: Bohrung Ø von ist größer als bis"
assert zr.menge_bezug("Anzahl Bohrungen", "€/Stück", p, k, (), r_senk) == 4.0
# Snapshot: ohne die neuen Werte gleich wie vorher (festgeschriebene Angebote bleiben gleich)
tab = dict(db.tabellen(), arbeitsgang_regeln=[dict(name="A", zusatzarbeit="Senken", zuordnung="automatisch",
                                                    aktiv="ja")])
assert not any(n in tab_r for tab_r in rechnen.zusatz_regeln_aus(tab)["regeln"] for n in ("bohr_von", "wand_bis"))
db.neu("arbeitsgang_regeln", r_senk)
db.neu("angebotsregeln", dict(name="Edelstahl dick", kategorie="Edelstahl", wand_von=4, wirkung="Zuschlag",
                              zuschlag=8, aktiv="nein"))
liste = merkmal_regeln.liste(db.tabellen())
quellen = {x["quelle"] for x in liste}
assert quellen == set(merkmal_regeln.QUELLEN), quellen
senk = next(x for x in liste if x["regel"] == "Senken M8")
assert senk["wenn"] == "Bohrungen, Bohrung Ø 8,4–8,6 mm" and senk["dann"] == "Zusatzarbeit Senken (Anzahl Bohrungen)", senk
assert next(x for x in liste if x["regel"] == "Edelstahl dick")["wenn"] == "Wand ab 4 mm, Edelstahl"
assert any(x["quelle"] == merkmal_regeln.QUELLE_WORT and "verzinkt" in x["wenn"].lower() for x in liste)
pr = merkmal_regeln.probe(p, {}, k, db.tabellen())
assert any(x["regel"] == "Senken M8" for x in pr), pr
seite = StammdatenSeite(db, TABELLE["arbeitsgang_regeln"], lambda *a, **kw: None)
assert seite.merkmal_regeln(zeigen=False) == liste
n = merkmal_regeln.zaehlen(liste)
ok(f"GEO-009 Merkmal-Regeln: Bohrung Ø 8,4–8,6 zählt 4 von 6 Bohrungen, Wand-Bereich; Übersicht {len(liste)} Regeln "
   "aus 5 Quellen (" + ", ".join(f"{q} {g}" for q, (_, g) in n.items()) + ")")

print("Roadmap Phase 2 Paket 2a: alle Tests bestanden.")
