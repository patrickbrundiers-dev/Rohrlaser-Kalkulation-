"""Prüft das Abruf-/Rahmenangebot (Patrick 30.10.2026, Plan „Abruf-Angebot“, Freigabe 1a 2a 3a 4 a und b 5a 6a 7b)
mit dem Beispiel aus dem Plan: Jahresmenge 4.000 bis 6.000 Stück, Abruf 400 bis 600 Stück, Muster vorab.
- A1 ohne Haken oder ohne Mengen rechnet alles wie bisher (bitgleich).
- A2 Programmierung nur anteilig je Abruf (Stückzahl ÷ Jahresmenge), Rüsten und Fracht je Abruf voll.
- A3 Musterteile: Umlage nur zum Anteil des Abrufs; eigene Zeile „Musterkosten einmalig“ bleibt voll.
- A4 Material bevorratet: Lagerzins auf das Material (Zins × Laufzeit ÷ 12 × ½), nicht auf Kundenmaterial und Muster.
- A5 Abrufstufen: Stufe mit den Mengen des Angebots = Angebot; größere Abrufe verteilen die Einmalkosten weiter auf
  die Jahresmenge des Angebots (ungünstigster Fall), sind je Stück günstiger.
- A6 abruf.py: Kennzahlen, Kurzfassung, Abrufstufen-Mengen, Rahmentext.
- A7 Angebot/PDF: Block „Rahmenbedingungen“ (Materialklausel bzw. bevorratet, Muster vorab).
- A8 Datenbank (Schema 70) und Oberfläche: Haken, Fenster, Knopf „Abrufstufen anlegen“, Funktion abschaltbar.

Aufruf: python tests/test_abruf_angebot.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import abruf, ausgabe, pdf, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import ABRUF_LAGER, KUNDENMATERIAL, MUSTER_ZEILE  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
# Beispiel aus dem Plan: Strebe und Halter je 400 Stück (kleinster Abruf), dazu je 5 Muster vorab
a = db.angebot_neu(dict(nummer="A-2026-0400", kunde="Testkunde Abruf GmbH", datum="2026-10-30", maschine="T11",
                        stange=6000))
SERIE = ((10, "Strebe", "RE 60x40x3", 485.0, 4), (20, "Halter", "RR 42,4x2,0", 210.0, 2))
for nr, bez, prof, laenge, konturen in SERIE:
    db.position_neu(a, dict(pos=nr, artikel=f"AB-{nr}", bezeichnung=bez, profil_id=prof, werkstoff_id="S235-10219",
                            laenge=laenge, stueck=400, schneidweg=380, einstiche=konturen))
for nr, bez, prof, laenge, konturen in SERIE:
    db.position_neu(a, dict(pos=nr + 50, artikel=f"AB-{nr}", bezeichnung=f"{bez} Muster", profil_id=prof,
                            werkstoff_id="S235-10219", laenge=laenge, stueck=5, schneidweg=380, einstiche=konturen,
                            muster="ja"))
k, tab = db.kontext(), db.tabellen()
kopf, pos = db.angebot(a), db.positionen(a)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
ABRUF = dict(abruf="ja", abruf_jahr_von=4000, abruf_jahr_bis=6000, abruf_von=400, abruf_bis=600, abruf_laufzeit=12)
ka = dict(kopf, **ABRUF)
kb = dict(ka, abruf_material=ABRUF_LAGER, abruf_lagerzins=8.0)
serie_pos = [p for p in pos if p.get("muster") != "ja"]


def kalk(kp, positionen=pos, e=einst):
    erg = rechnen.optimieren(kp, positionen, k, tab, e)
    return rechnen.kalkulation(kp, positionen, erg, k, tab, e)


def kosten_gehen_auf(s):
    teile = [w for (t, w, _), (_, n, _) in zip(rechnen.kostenarten(s, einst), rechnen.KOSTENARTEN)
             if n in ("herstell", "gewinn", "pauschalen", "programmierung", "angebotsaufschlag", "fracht",
                      "zukauf_einstand", "zukauf_aufschlag", "skonto", "mindestpreis_anhebung", "muster_spaeter")]
    return nah(sum(teile), s["verkauf"], 1e-6)


# ------------------------------------------------------------------ A1 ohne Abruf wie bisher
z0, s0 = kalk(kopf)
for kp in (dict(kopf, abruf_jahr_von=4000, abruf_von=400),            # Mengen ohne Haken
           dict(kopf, abruf="ja"),                                     # Haken ohne Mengen
           dict(kopf, abruf="ja", abruf_jahr_von=4000)):
    zx, sx = kalk(kp)
    assert sx["verkauf"] == s0["verkauf"] and not sx["abruf"], kp
    assert [z["preis_teil"] for z in zx if z] == [z["preis_teil"] for z in z0 if z]
assert s0["lagerzins"] == 0 and s0["programmierung"] == s0["programmierung_voll"]
ok(f"A1 ohne Haken oder ohne Mengen unverändert ({s0['verkauf']:.2f} €)")

# ------------------------------------------------------------------ A2 Programmierung anteilig, Rüsten je Abruf
z1, s1 = kalk(ka)
assert s1["abruf"] and s1["abruf_n"] == 10
serie0 = [z for z in z0 if z and z.get("muster") != "ja"]
serie1 = [z for z in z1 if z and z.get("muster") != "ja"]
for a0, a1 in zip(serie0, serie1):
    assert nah(a1["programmierung_anteil"], a0["programmierung_anteil"] / 10, 1e-9)       # 400 von 4.000
    assert nah(a1["ruesten_teil"], a0["ruesten_teil"]) and nah(a1["fracht_teil"] - a1.get("muster_fracht_teil", 0),
                                                               a0["fracht_teil"] - a0.get("muster_fracht_teil", 0))
assert nah(s1["ruesten"], s0["ruesten"]) and nah(s1["programmierung_voll"], s0["programmierung"])
muster_prog = sum(z["programmierung_anteil"] * z["stueck"] for z in z1 if z and z.get("muster") == "ja")
assert nah(s1["programmierung"], muster_prog + (s0["programmierung"] - muster_prog) / 10, 1e-9)
assert s1["verkauf"] < s0["verkauf"] and kosten_gehen_auf(s1)
text = next(t for t, _, _ in rechnen.kostenarten(s1, einst) if t.startswith("Programmierkosten"))
assert "Anteil je Abruf" in text and "Jahresmenge" in text, text
ok(f"A2 Programmierung je Abruf {s1['programmierung']:.2f} € statt {s0['programmierung']:.2f} €, Rüsten je Abruf "
   f"gleich ({s1['ruesten']:.2f} €)")

# ------------------------------------------------------------------ A3 Muster auf die Jahresmenge
assert s1["muster_positionen"] == 2 and nah(s1["muster_betrag"], s0["muster_betrag"], 1e-6)
assert nah(s1["muster_umgelegt"], s1["muster_betrag"] / 10, 1e-6)          # alle Serienpositionen 400 von 4.000
assert nah(s0["muster_umgelegt"], s0["muster_betrag"], 1e-6)
assert "auf die Jahresmenge umgelegt" in rechnen.muster_text(s1)
assert all(z["preis_teil"] == 0 for z in z1 if z and z.get("muster") == "ja")
z1z, s1z = kalk(dict(ka, muster_darstellung=MUSTER_ZEILE))
assert nah(s1z["muster_einmalig"], s1z["muster_betrag"]) and s1z["muster_einmalig"] > 0      # eigene Zeile: voll
ok(f"A3 Muster {s1['muster_betrag']:.2f} €: je Abruf {s1['muster_umgelegt']:.2f} € umgelegt, eigene Zeile voll")

# ------------------------------------------------------------------ A4 Lagerzins bei Bevorratung
z2, s2 = kalk(kb)
lz = 0.08 * 12 / 12 * 0.5
assert nah(abruf.daten(kb)["lagerzins"], lz)
for a1, a2 in zip(z1, z2):
    if a1 and a1.get("muster") != "ja":
        assert nah(a2["lagerzins_teil"], a2["material_teil"] * lz, 1e-12) and a2["lagerzins_teil"] > 0
    elif a1:
        assert a2["lagerzins_teil"] == 0
assert nah(s2["lagerzins"], sum(z["lagerzins_teil"] * z["stueck"] for z in z2 if z)) and s2["verkauf"] > s1["verkauf"]
assert kosten_gehen_auf(s2)
assert "8 % p. a." in next(t for t, _, _ in rechnen.kostenarten(s2, einst) if t.startswith("Lagerzins"))
# halbe Laufzeit = halber Zins; Kundenmaterial ohne Lagerzins
_, s2h = kalk(dict(kb, abruf_laufzeit=6))
assert nah(s2h["lagerzins"], s2["lagerzins"] / 2, 1e-6)
kunde = [dict(p, material_herkunft=KUNDENMATERIAL) for p in pos]
zk, sk = kalk(kb, kunde)
assert sk["lagerzins"] == 0
ok(f"A4 bevorratet: Lagerzins {s2['lagerzins']:.2f} € (8 % p. a. auf den halben Jahresbedarf), Kundenmaterial ohne")

# ------------------------------------------------------------------ A5 Abrufstufen
for kp, ss in ((ka, s1), (kb, s2)):
    mz = [dict(schluessel="10", menge=400), dict(schluessel="20", menge=400)]
    st = dict(schluessel=None)
    lz_ = staffeln.stufe_lauf(kp, pos, st, mz, k, tab, einst)
    pr = staffeln.stufe_bepreisen(lz_, st, mz, staffeln.stufe_einst(kp, st, einst))
    gesamt = sum(x["preis_gesamt"] for x in pr)
    assert abs(gesamt - ss["verkauf"]) <= 0.005 * 800, (gesamt, ss["verkauf"])        # Stufe = Angebot
    mz6 = [dict(schluessel="10", menge=600), dict(schluessel="20", menge=600)]
    lz6 = staffeln.stufe_lauf(kp, pos, st, mz6, k, tab, einst)
    pr6 = staffeln.stufe_bepreisen(lz6, st, mz6, staffeln.stufe_einst(kp, st, einst))
    for x4, x6 in zip(pr, pr6):
        assert x6["preis_einheit"] < x4["preis_einheit"]
        # Programmierung je Stück gleich: Jahresmenge des Angebots (4.000) bleibt
        assert nah(x6["bausteine"]["programmierung"] / 600, x4["bausteine"]["programmierung"] / 400, 1e-9)
assert staffeln.ABRUF_FELDER[0] == "abruf" and "abruf_lagerzins" in staffeln.ABRUF_FELDER
g1 = staffeln._hash(staffeln._gemeinsam(ka, pos, k, tab, einst))
assert g1 != staffeln._hash(staffeln._gemeinsam(kb, pos, k, tab, einst))       # Abrufwerte machen Stufen veraltet
assert staffeln._hash(staffeln._gemeinsam(kopf, pos, k, tab, einst)) != g1
ok("A5 Abrufstufen: Stufe 400 = Angebot, 600 je Stück günstiger, Programmierung je Stück auf 4.000 Stk. verteilt")

# ------------------------------------------------------------------ A6 abruf.py
ab = abruf.daten(ka)
assert ab["n"] == 10 and abruf.abrufe(ab) == (7, 15) and not ab["bevorraten"] and ab["lagerzins"] == 0
assert abruf.stufen_mengen(ka) == [500, 600]
assert abruf.stufen_mengen(dict(ka, abruf_bis=450)) == [425, 450]
assert abruf.stufen_mengen(dict(ka, abruf_bis=401)) == [401] and abruf.stufen_mengen(dict(ka, abruf_bis=400)) == []
assert abruf.daten(dict(ka, abruf_bis=300))["bis"] == 400            # bis kleiner von = von
assert abruf.daten(dict(ka, abruf_jahr_von=200))["n"] == 1           # nie weniger als ein Abruf
assert abruf.kurz(ka) == "4.000 bis 6.000 Stk./Jahr, Abruf 400 bis 600 Stk., ca. 7 bis 15 Abrufe, 12 Monate"
assert "Lagerzins 8,0 % p. a." in abruf.kurz(kb) and abruf.kurz(kopf) == ""
assert abruf.kurz(dict(kopf, abruf="ja")) == "Jahresmenge und Abrufmenge fehlen"
assert abruf.anteil(dict(stueck=600, abruf_basis=400), ab) == 600 / 4000 and abruf.anteil(dict(stueck=5), None) == 1
e = db.einstellungen()
t = abruf.rahmentext(ka, e, muster=True, datum="30.10.2026")
assert "4.000 bis 6.000 Stück je Jahr" in t and "400 bis 600 Stück" in t and "ca. 7 bis 15 Abrufe" in t, t
assert "12 Monate" in t and "Materialpreisen vom 30.10.2026" in t and "mehr als 5,0 %" in t, t
assert "Musterfreigabe" in t and "{" not in t
tb = abruf.rahmentext(kb, e)
assert "halten es für Ihre Abrufe vor" in tb and "Musterfreigabe" not in tb and "Materialklausel" not in tb
assert abruf.rahmentext(kopf, e) == ""
ok("A6 abruf.py: 7 bis 15 Abrufe, Abrufstufen 500/600, Kurzfassung und Rahmentext mit Platzhaltern")

# ------------------------------------------------------------------ A7 Angebot und PDF
ang = ausgabe.angebot(ka, pos, z1, k, einst)
assert ang["rahmen"] and "Rahmenangebot über 4.000 bis 6.000 Stück" in ang["rahmen"] and "Musterfreigabe" in ang["rahmen"]
assert abs(ang["netto"] - s1["verkauf"]) <= 0.005 * 810       # Stückpreise auf den Cent gerundet
assert ausgabe.angebot(kopf, pos, z0, k, einst)["rahmen"] == ""
assert "Musterfreigabe" not in ausgabe.angebot(ka, serie_pos, kalk(ka, serie_pos)[0], k, einst)["rahmen"]
for ziel, kp, zz in (("abruf.pdf", ka, z1), ("lager.pdf", kb, z2), ("normal.pdf", kopf, z0)):
    pdf.angebot_pdf(tmp / ziel, kp, ausgabe.angebot(kp, pos, zz, k, einst), einst)
    assert (tmp / ziel).stat().st_size > 1000
try:
    from pypdf import PdfReader
    text = "".join(s.extract_text() for s in PdfReader(str(tmp / "abruf.pdf")).pages)
    assert "Rahmenbedingungen" in text and "Abrufe" in text, text[-600:]
    assert "Rahmenbedingungen" not in "".join(s.extract_text() for s in PdfReader(str(tmp / "normal.pdf")).pages)
    ok("A7 Angebots-PDF: Block „Rahmenbedingungen“ nur im Abruf-Angebot")
except ImportError:
    ok("A7 Angebots-PDF erzeugt (pypdf fehlt: Text nicht geprüft)")

# ------------------------------------------------------------------ A8 Datenbank und Oberfläche
assert SCHEMA_VERSION >= 70
for n, w in dict(ABRUF, abruf_material=ABRUF_LAGER, abruf_lagerzins=6.5).items():
    db.angebot_aendern(a, n, w)
gespeichert = db.angebot(a)
assert gespeichert["abruf_jahr_bis"] == 6000 and gespeichert["abruf_material"] == ABRUF_LAGER
assert gespeichert["abruf_lagerzins"] == 6.5
kopie = db.angebot_kopieren(a)
assert db.angebot(kopie)["abruf"] == "ja" and db.angebot(kopie)["abruf_von"] == 400
for n in ABRUF:
    db.angebot_aendern(a, n, None)
db.angebot_aendern(a, "abruf_material", None)
db.angebot_aendern(a, "abruf_lagerzins", None)

from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.abruf_dialog import AbrufDialog  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

d = AbrufDialog(None, {}, db.einstellungen(), stueck=400)
w = d.werte()
assert w["abruf"] == "ja" and w["abruf_von"] == 400 and w["abruf_jahr_von"] == 4000 and w["abruf_laufzeit"] == 12
assert w["abruf_material"] is None and w["abruf_lagerzins"] == 8.0 and not d.zins.isEnabled()
d.material.setCurrentText(ABRUF_LAGER)
d.bis.setValue(300)
assert d.zins.isEnabled() and d.werte()["abruf_material"] == ABRUF_LAGER and d.werte()["abruf_bis"] == 400
assert "Abruf 400 Stk." in d.info.text()

f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(a)
kb_ = s.kopf_bereich
assert not kb_.abruf_wahl.isHidden()
assert not kb_.abruf_an.isChecked() and kb_.abruf_knopf.isHidden()
assert s.abruf_umschalten(True) is False and not s.kopf.get("abruf")      # ohne Mengen: Fenster (stumm: Abbruch)
vk_vorher = s._rechnung()[1]["verkauf"]
assert s.abruf_bearbeiten(dict(ABRUF)) and s.kopf["abruf"] == "ja" and kb_.abruf_an.isChecked()
assert not kb_.abruf_knopf.isHidden()
assert kb_.abruf_kurz.text().startswith("4.000 bis 6.000 Stk./Jahr")
assert s._rechnung()[1]["abruf"] and s._rechnung()[1]["verkauf"] < vk_vorher
st_seite = s.st_seite
st_seite.stand()
assert not st_seite.knoepfe["Abrufstufen anlegen"].isHidden()
vorher = len(s.stufen)
ids = st_seite.abrufstufen()
assert len(ids) == 2 and len(s.stufen) == vorher + 4                      # 2 Stufen × Pos. 10 und 20 (ohne Muster)
neu = [x for x in s.stufen if x.get("stufe_id") in ids]
assert sorted(x["menge"] for x in neu) == [500, 500, 600, 600] and {x["schluessel"] for x in neu} == {"10", "20"}
assert {st["bezeichnung"] for st in s.stufen_daten if st["id"] in ids} == {"Abruf 500 Stk.", "Abruf 600 Stk."}
assert st_seite.abrufstufen() == []                                        # nicht doppelt
assert s.abruf_umschalten(False) and not s.kopf.get("abruf") and s.kopf["abruf_von"] == 400   # Werte bleiben
st_seite.stand()
assert st_seite.knoepfe["Abrufstufen anlegen"].isHidden()
db.einstellung_setzen("funktion_abruf", "nein")
from rohrlaser import funktionen  # noqa: E402
assert not funktionen.an("funktion_abruf", db)
s.neu_laden()
assert kb_.abruf_wahl.isHidden()                                 # Funktion aus, Angebot ohne Abruf
assert s.abruf_bearbeiten({"abruf": "ja"}), s.kopf.get("abruf")
assert not kb_.abruf_wahl.isHidden()                                     # vorhandenes Abruf-Angebot bleibt sichtbar
db.einstellung_setzen("funktion_abruf", "ja")
ok("A8 Schema 70, Fenster, Haken im Kopf, Abrufstufen 500/600 ohne Muster, nicht doppelt, Funktion abschaltbar")
print("Alle Prüfungen des Abruf-Angebots bestanden.")
