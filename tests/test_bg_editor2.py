"""Prüft den Schweißbaugruppen-Editor 2.0 (Patrick 19.11.2026): Gesamtzeit von Hand, Bereiche, Protokoll,
Lernvorschläge und Auswertung.
- E1  Automatische Zeitberechnung bleibt, wie sie war (ohne Zeit von Hand kein Unterschied; feine Bereiche)
- E2  Gesamtzeit von Hand: 190 min berechnet, 240 min von Hand = genau 240 min, nichts wird dazugezählt
- E3  Einzelne Bereiche von Hand; Vorrang Gesamtzeit > Stückzeit/Rüstzeit > Bereiche > automatisch
- E4  Zurücksetzen = bitgleich wie automatisch
- E5  Speichern und erneutes Öffnen (Datenbank), alte Einteilung der Bereiche bleibt für alte Baugruppen
- E6  Änderung der Baugruppe nach der Zeit von Hand: Hinweis, Zeit bleibt, Bestätigen nimmt den Hinweis weg
- E7  Erneute Kalkulation ändert die Zeit von Hand nicht
- E8  Übernahme ins Angebot: Kalkulation rechnet mit der Gesamtzeit, Stufen mit anderer Stückzahl ebenso
- E9  Vergleichbare Baugruppen: Ähnlichkeit, andere Werkstoffgruppe / anderes Verfahren getrennt
- E10 Lernvorschlag: ab 3 vergleichbaren, erklärt, nie von allein übernommen; Übernehmen nur mit Knopf
- E11 Ausreißer erkannt und nicht gezählt; ältere Datensätze zählen weniger; Prüfung (Leave-one-out)
- E12 Mehrere Benutzer: Protokoll mit Kürzel, eine Zeile je Angebot und Baugruppe, Tabelle wird geteilt
- E13 Versionierung: jede Änderung ein Protokolleintrag mit laufender Version, alte Stände bleiben
- E14 Nichts doppelt: dieselbe Entscheidung nur einmal, Kopie zählt nicht, gesperrt/zurückgesetzt zählt nicht
- E15 Auswertung: Kennzahlen, Gruppen, Häufigkeit, Verlauf; Fenster mit Grafik

Aufruf: python tests/test_bg_editor2.py
"""
import copy
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import angebot_check, baugruppe, bg_vorgabe as bv, bg_zeitlernen as zl, rechnen, teilen  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=0, status="geprüft")],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=45.0, status="geprüft")])
SAETZE = {"Schweißen": 60.0}


def gruppe(**extra):
    """Patricks Beispiel: Vorbereitung 20, Heften 35, Schweißen 90, Richten 25, Nachbearbeitung 20 = 190 min."""
    g = baugruppe.leer()
    g["naehte"] = [dict(id="n1", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1)]  # 90 min
    g["arbeitsgaenge"] = [dict(id="a1", name="Teile vorbereiten", satz=60, zeit_min=20),
                          dict(id="a2", name="Heften", satz=60, zeit_min=35),
                          dict(id="a3", name="Richten", satz=60, zeit_min=25),
                          dict(id="a4", name="Beizen", satz=60, zeit_min=20),
                          dict(id="a5", name="Verzinken", fremd=True, kosten_einheit=10.0)]
    g.update(extra)
    return g


def pos(g, stueck=1):
    return dict(stueck=stueck, art=BAUGRUPPE, baugruppe=baugruppe.speichern(g))


# ------------------------------------------------------------------ E1
r0 = baugruppe.rechnen(pos(gruppe()), TAB, SAETZE)
z0 = r0["zeiten"]
ber = {x["bereich"]: x["auto_stueck"] for x in z0["bereiche"]}
assert ber == {"Vorbereitung": 20.0, "Heften": 35.0, "Schweißen": 90.0, "Richten": 25.0, "Nachbearbeitung": 20.0}, ber
nah(z0["gesamt_min"], 190.0, "automatisch")
nah(z0["auto_je_bg_min"], 190.0)
assert not z0["hand"] and not z0["hand_gesamt"] and z0["fein"]
nah(r0["eigen"], 190.0, "190 min zu 60 €/h")
assert set(bv.BEREICHE) >= {"Vorbereitung", "Heften", "Schweißen", "Richten", "Schleifen", "Nachbearbeitung",
                            "Qualitätskontrolle", "Montage"}
ok("E1 automatisch: Vorbereitung 20, Heften 35, Schweißen 90, Richten 25, Nachbearbeitung 20 = 190 min")

# ------------------------------------------------------------------ E2
g = gruppe()
bv.vorgabe_setzen(g, auto=z0, gesamt_min=240.0)
r2 = baugruppe.rechnen(pos(g), TAB, SAETZE)
z2 = r2["zeiten"]
nah(z2["gesamt_min"], 240.0, "genau 240, nicht 190 + 240")
nah(z2["je_bg_min"], 240.0)
nah(r2["zeit_min"], 240.0, "zeit_min der Position")
nah(r2["eigen"], 240.0, "Kosten folgen: 240 min zu 60 €/h")
nah(r2["fremd"], r0["fremd"], "Fremdleistung bleibt")
nah(sum(x["zeit_min"] for x in r2["zeilen"] if not x["fremd"]), 240.0, "Summe der Zeilen = 240 (nichts doppelt)")
assert z2["hand"] and z2["hand_gesamt"] and not z2["hand_stueck"]
nah(z2["auto_je_bg_min"], 190.0, "ursprüngliche Berechnung bleibt sichtbar")
assert all("auto" in x for x in r2["zeilen"] if not x["fremd"]), "automatische Einzelzeiten bleiben je Zeile"
nah(sum(x["auto"]["zeit_min"] for x in r2["zeilen"] if not x["fremd"]), 190.0)
assert "240 min" not in bv.gesamt_text(z2) and "4 h 00 min je BG gesamt (+50 min)" in bv.gesamt_text(z2), bv.gesamt_text(z2)
# mit Rüsten und Stückzahl: Gesamtzeit je Baugruppe gilt für jede Stückzahl, Rüsten kommt nicht dazu
gr = gruppe()
gr["arbeitsgaenge"].append(dict(id="a6", name="Rüsten Schweißplatz", satz=60, ruest_min=60))
for n in (1, 5, 20):
    ra = baugruppe.rechnen(pos(gr, n), TAB, SAETZE)
    nah(ra["zeiten"]["auto_je_bg_min"], 190 + 60 / n, f"automatisch je BG bei {n}")
    gh = copy.deepcopy(gr)
    bv.vorgabe_setzen(gh, gesamt_min=240.0)
    rh = baugruppe.rechnen(pos(gh, n), TAB, SAETZE)
    nah(rh["zeiten"]["gesamt_min"], 240.0 * n, f"Gesamt bei {n} Stk.")
    nah(rh["zeit_min"], 240.0, f"je BG bei {n} Stk.")
    nah(rh["eigen"], 240.0, f"Kosten je BG bei {n} Stk.")
    nah(rh["zeiten"]["ruest_min"] + rh["zeiten"]["stueck_min"] * n, 240.0 * n, "Rüsten + Stück = Gesamt")
assert bv.zeit_lesen("240") == 240 and bv.zeit_lesen("4 h") == 240 and bv.zeit_lesen("4:00") == 240
ok("E2 Gesamtzeit von Hand 240 min statt 190: genau 240, Kosten folgen, Rüsten kommt nicht dazu, Minuten oder Stunden")

# ------------------------------------------------------------------ E3
g = gruppe()
bv.vorgabe_setzen(g, bereiche={"Richten": 40.0, "Schweißen": 100.0})
r3 = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r3["zeiten"]["gesamt_min"], 190 + 15 + 10, "nur Richten und Schweißen geändert")
assert r3["zeiten"]["hand_bereiche"] == ["Richten", "Schweißen"] and g["vorgabe"]["fein"] is True
bv.vorgabe_setzen(g, stueck_min=200.0)
nah(baugruppe.rechnen(pos(g), TAB, SAETZE)["zeiten"]["gesamt_min"], 200.0, "Stückzeit vor Bereichen")
bv.vorgabe_setzen(g, gesamt_min=240.0)
r3g = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r3g["zeiten"]["gesamt_min"], 240.0, "Gesamtzeit vor allem")
assert r3g["zeiten"]["hand_bereiche"] == [] and not r3g["zeiten"]["hand_stueck"]
v = bv.vorgabe(g)
assert v["stueck_min"] == 200.0 and v["bereiche"] == {"Richten": 40.0, "Schweißen": 100.0}, "bleiben gespeichert"
bv.vorgabe_setzen(g, gesamt_min=None)
nah(baugruppe.rechnen(pos(g), TAB, SAETZE)["zeiten"]["gesamt_min"], 200.0, "ohne Gesamtzeit gilt wieder die Stückzeit")
bv.vorgabe_setzen(g, stueck_min=None)
nah(baugruppe.rechnen(pos(g), TAB, SAETZE)["zeiten"]["gesamt_min"], 215.0, "dann wieder die Bereiche")
ok("E3 Vorrang: Gesamtzeit > Stückzeit > Bereiche > automatisch; überdeckte Werte bleiben gespeichert")

# ------------------------------------------------------------------ E4
bv.vorgabe_setzen(g, bereiche={})
assert "vorgabe" not in g
r4 = baugruppe.rechnen(pos(g), TAB, SAETZE)
assert r4["eigen"] == r0["eigen"] and r4["zeit_min"] == r0["zeit_min"] and r4["zeiten"] == z0, "bitgleich"
ok("E4 zurück auf automatisch = bitgleich")

# ------------------------------------------------------------------ E5
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser import db_verbindung  # noqa: E402
tmp = tempfile.mkdtemp()
db = Datenbank(Path(tmp) / "t.db")
for z_ in TAB["schweissverfahren"]:
    db.neu("schweissverfahren", z_)
for z_ in TAB["schweiss_kennwerte"]:
    db.neu("schweiss_kennwerte", z_)
if not any(x.get("satz_id") == "Schweißen" for x in db.zeilen("stundensaetze")):
    db.neu("stundensaetze", dict(satz_id="Schweißen", satz=60.0))
else:
    sid = next(x["id"] for x in db.zeilen("stundensaetze") if x.get("satz_id") == "Schweißen")
    db.aendern("stundensaetze", sid, "satz", 60.0)
db.einstellung_setzen("benutzer_kuerzel", "PB")
assert {"angebot", "bg_id", "auto_min", "hand_min", "merkmale", "status", "uid", "id"} <= set(
    db_verbindung.spalten(db.con, "bg_zeiten")), "Tabelle bg_zeiten mit id und Kennung"
assert zl.BG_ZEITEN in teilen.GETEILT


def kalk(aid, stufe=None):
    kopf, ps = db.angebot(aid), db.positionen(aid)
    k, tab = db.kontext(), db.tabellen()
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    zeilen, summen = rechnen.kalkulation(kopf, ps, rechnen.optimieren(kopf, ps, k, tab, einst), k, tab, einst)
    return kopf, ps, zeilen


aid = db.angebot_neu(dict(kunde="Editor 2", maschine="T11"))
g = gruppe()
db.position_neu(aid, dict(pos=10, art=BAUGRUPPE, artikel="E2-1", stueck=2, baugruppe=baugruppe.speichern(g)))
kopf, ps, zeilen_a = kalk(aid)
bv.vorgabe_setzen(g, auto=zeilen_a[0]["bg_zeiten"], gesamt_min=240.0, grund="Erfahrung", von="PB", am="19.11.2026")
db.position_aendern(ps[0]["id"], "baugruppe", baugruppe.speichern(g))
kopf, ps, zeilen_h = kalk(aid)
g_neu = baugruppe.lesen(ps[0]["baugruppe"])
assert bv.vorgabe(g_neu)["gesamt_min"] == 240.0 and bv.vorgabe(g_neu)["von"] == "PB"
nah(zeilen_h[0]["bg_zeiten"]["je_bg_min"], 240.0, "nach dem Öffnen")
# alte Baugruppe mit Bereichen von Hand nach alter Einteilung (ohne 'fein'): rechnet wie vor dem Editor 2.0
ga = gruppe(vorgabe=dict(bereiche={"Nachbearbeitung": 90.0}))
assert not bv.fein(ga) and bv.bereiche_liste(ga) == bv.BEREICHE_ALT
ra = baugruppe.rechnen(pos(ga), TAB, SAETZE)
bera = {x["bereich"]: x for x in ra["zeiten"]["bereiche"]}
nah(bera["Nachbearbeitung"]["auto_stueck"], 45.0, "alt: Richten 25 + Beizen 20 = Nachbearbeitung")
nah(ra["zeiten"]["gesamt_min"], 190 + 45, "90 statt 45 min Nachbearbeitung")
ok("E5 gespeichert und wieder geöffnet; alte Bereiche von Hand rechnen mit der alten Einteilung weiter")

# ------------------------------------------------------------------ E6 + E7
g = gruppe()
m_alt = zl.merkmale(g, [pos(g)], None, r0)
bv.vorgabe_setzen(g, auto=z0, merkmale=m_alt, gesamt_min=240.0)
assert bv.pruefen(g, baugruppe.rechnen(pos(g), TAB, SAETZE)["zeiten"], m_alt) == []
g["naehte"].append(dict(id="n2", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=500, anzahl=2))
r6 = baugruppe.rechnen(pos(g), TAB, SAETZE)
nah(r6["zeiten"]["gesamt_min"], 240.0, "E7: neu gerechnet, Zeit von Hand bleibt")
nah(r6["zeiten"]["auto_je_bg_min"], 280.0, "automatisch jetzt 280")
gruende = bv.pruefen(g, r6["zeiten"], zl.merkmale(g, [pos(g)], None, r6))
assert any("automatische Zeit" in t for t in gruende) and any("Nahtlänge" in t for t in gruende), gruende
assert bv.vorgabe(g)["gesamt_min"] == 240.0, "nie ungefragt gelöscht"
bv.bestaetigen(g, r6["zeiten"], zl.merkmale(g, [pos(g)], None, r6))
assert bv.pruefen(g, r6["zeiten"], zl.merkmale(g, [pos(g)], None, r6)) == [] and bv.vorgabe(g)["gesamt_min"] == 240.0
ok("E6/E7 Baugruppe geändert: Zeit von Hand bleibt, Hinweis mit Gründen, Bestätigen nimmt ihn weg")

# ------------------------------------------------------------------ E8
kopf, ps, zeilen_h = kalk(aid)
preis_auto, preis_hand = zeilen_a[0]["preis_teil"], zeilen_h[0]["preis_teil"]
assert preis_hand > preis_auto
ra2 = baugruppe.rechnen(ps[0], db.tabellen(), rechnen.stundensaetze(db.tabellen()))
nah(ra2["zeit_min"], 240.0, "Position rechnet mit 240 min je BG")
nah(zeilen_h[0]["bg_zeiten"]["gesamt_min"], 480.0, "2 Stück = 480 min, nicht 380 + 480")
for n in (1, 10):
    nah(baugruppe.rechnen(ps[0], db.tabellen(), rechnen.stundensaetze(db.tabellen()), n)["zeit_min"], 240.0, f"Stufe {n}")
g_alt = baugruppe.lesen(ps[0]["baugruppe"])
g_alt["naehte"].append(dict(id="n9", nr="9", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1))
db.position_aendern(ps[0]["id"], "baugruppe", baugruppe.speichern(g_alt))
kopf, ps, zeilen_g = kalk(aid)
punkte = angebot_check.punkte(kopf, ps, ["OK"] * len(ps), "aktuell", {}, kalk_zeilen=zeilen_g)
assert any("Zeit von Hand prüfen" in p_.text for p_ in punkte), [p_.text for p_ in punkte]
nah(zeilen_g[0]["bg_zeiten"]["je_bg_min"], 240.0, "bleibt 240")
ok("E8 Angebot: Preis mit 240 min je Baugruppe, jede Stufe, nichts doppelt; Angebots-Check weist auf Änderung hin")

# ------------------------------------------------------------------ E9
M = dict(naht_m=2.0, teile_n=6, gewicht_kg=25.0, naht_n=8, dicke_mm=4.0, verschiedene=4, gruppe="Stahl", verfahren="MAG")
nah(zl.aehnlichkeit(M, M), 1.0)
assert zl.aehnlichkeit(M, dict(M, gruppe="Edelstahl")) == 0.0, "andere Werkstoffgruppe: nicht vergleichbar"
assert zl.aehnlichkeit(M, dict(M, verfahren="WIG")) == 0.0, "anderes Verfahren: nicht vergleichbar"
assert 0.9 < zl.aehnlichkeit(M, dict(M, naht_m=2.2, gewicht_kg=27.0)) < 1.0
assert zl.aehnlichkeit(M, dict(M, naht_m=20.0, teile_n=60, gewicht_kg=400.0, naht_n=90)) < zl.AEHNLICH_AB
assert zl.aehnlichkeit(M, dict(gruppe="Stahl")) == 0.0, "ohne gemeinsame Merkmale kein Vergleich"
ok("E9 Ähnlichkeit aus Naht, Teilen, Gewicht, Nähten, Dicke; Werkstoffgruppe und Verfahren trennen")

# ------------------------------------------------------------------ E10 + E14
def entscheidung(nr, auto, hand, m=M, kuerzel="PB", bg_id=None, frei=True):
    b = dict(id=bg_id or f"bg{nr}", vorgabe=dict(gesamt_min=hand, **({} if frei else dict(frei=False))))
    return zl.merken(db, f"2026-{nr:05d}", f"Rahmen {nr}", b, dict(hand=True, hand_gesamt=True, anzahl=1,
                                                                 auto_je_bg_min=auto, je_bg_min=hand), m, kuerzel)


assert entscheidung(1, 90, 120) == "neu" and entscheidung(2, 110, 145) == "neu"
assert zl.vorschlag(db, M, 110.0) is None, "zwei Datensätze: noch kein Vorschlag"
assert entscheidung(3, 100, 135) == "neu" and entscheidung(4, 95, 130) == "neu"
assert entscheidung(4, 95, 130) is None, "dieselbe Entscheidung noch einmal gespeichert: nichts Neues"
assert len(zl.faelle(db)) == 4
vs = zl.vorschlag(db, M, 110.0)
assert vs["n"] == 4 and 144 < vs["min"] < 150 and vs["verfahren"] == "Mittel", vs
assert "4 vergleichbare Baugruppen (Stahl · MAG)" in vs["text"] and "keine gemessenen Ist-Zeiten" in vs["text"], vs["text"]
assert zl.vorschlag(db, dict(M, gruppe="Edelstahl"), 110.0) is None, "andere Art: kein pauschaler Aufschlag"
assert zl.vorschlag(db, M, 110.0, ohne=("2026-00004", "bg4"))["n"] == 3, "lernt nicht aus sich selbst"
assert entscheidung(4, 95, 133) == "geändert" and len(zl.faelle(db)) == 4, "geändert ersetzt, zählt nicht doppelt"
assert entscheidung(5, 100, 135, frei=False) == "neu" and zl.vorschlag(db, M, 110.0)["n"] == 4, "nicht freigegeben"
assert zl.merken(db, "2026-00003", "Rahmen 3", dict(id="bg3"), dict(hand=False), M, "PB") == "zurück"
assert zl.vorschlag(db, M, 110.0)["n"] == 3, "zurückgesetzt zählt nicht mehr"
assert entscheidung(3, 100, 135) == "geändert" and zl.vorschlag(db, M, 110.0)["n"] == 4
ok("E10/E14 Vorschlag ab 3 vergleichbaren, erklärt; je Angebot und Baugruppe eine Zeile, gesperrt/zurück zählt nicht")

# ------------------------------------------------------------------ E11
assert entscheidung(6, 100, 400) == "neu"
vs = zl.vorschlag(db, M, 110.0)
assert vs["n"] == 4 and vs["n_ausreisser"] == 1 and "1 Ausreißer nicht gezählt" in vs["text"], vs["text"]
assert [r["angebot"] for r in vs["vergleichbare"] if r["ausreisser"]] == ["2026-00006"]
heute = datetime.date(2026, 11, 19)
assert zl.alter_gewicht("2026-11-19T10:00:00", heute) == 1.0
nah(zl.alter_gewicht("2024-11-19T10:00:00", heute), 0.5, "zwei Jahre alt = halbes Gewicht", 0.01)
daten = [dict(angebot=f"A{i}", bg_id=f"b{i}", m=M, auto_min=a, hand_min=30 + 1.0 * a, faktor=(30 + a) / a, status="",
              geaendert="2026-11-01T00:00:00") for i, a in enumerate((40, 60, 80, 100, 120, 140, 160, 180, 200))]
vg = zl.vorschlag(None, M, 110.0, daten=daten)
assert vg["verfahren"] == "Gerade" and vg["fehler"] is not None and abs(vg["min"] - 140.0) < 0.5, vg
assert "Prüfung" in vg["text"] and "Ausgleichsgerade" in vg["text"]
ok("E11 Ausreißer genannt und nicht gezählt, Alter gewichtet, Prüfung wählt die Ausgleichsgerade nur wenn genauer")

# ------------------------------------------------------------------ E12 + E13
g = gruppe()
z = baugruppe.rechnen(pos(g), TAB, SAETZE)["zeiten"]
alt = bv.vorgabe(g)
bv.vorgabe_setzen(g, auto=z, gesamt_min=240.0, von="PB")
e1 = bv.protokollieren(g, alt, auto_min=190.0, von="PB", am="19.11.2026 10:00", grund="Erfahrung")
assert bv.protokollieren(g, bv.vorgabe(g), auto_min=190.0, von="PB") is None, "ohne Änderung kein Eintrag"
alt = bv.vorgabe(g)
bv.vorgabe_setzen(g, gesamt_min=260.0, von="MK")
e2 = bv.protokollieren(g, alt, auto_min=190.0, von="MK", am="19.11.2026 11:00", vorschlag=dict(min=260.0, n=5))
alt = bv.vorgabe(g)
bv.vorgabe_setzen(g, gesamt_min=None)
e3 = bv.protokollieren(g, alt, auto_min=190.0, von="PB", am="19.11.2026 12:00")
assert "vorgabe" not in g and [e["version"] for e in bv.protokoll(g)] == [1, 2, 3] and bv.version(g) == 3
assert e1["aenderungen"] == [("Gesamtzeit je Baugruppe", None, 240.0)] and e2["von"] == "MK"
assert e3["aenderungen"] == [("Gesamtzeit je Baugruppe", 260.0, None)]
texte = bv.protokoll_text(g)
assert texte[0].startswith("V3") and "automatisch" in texte[0] and "Lernvorschlag" in texte[1] and "Erfahrung" in texte[2]
g2 = baugruppe.lesen(baugruppe.speichern(g))
assert len(bv.protokoll(g2)) == 3, "Protokoll wird mit der Baugruppe gespeichert, auch nach dem Zurücksetzen"
assert entscheidung(7, 100, 131, kuerzel="MK") == "neu"
assert {r["kuerzel"] for r in zl.faelle(db, alle=True)} == {"PB", "MK"}
ok("E12/E13 Protokoll mit Version, Benutzer, Grund und Lernvorschlag; alte Stände bleiben; mehrere Benutzer")

# ------------------------------------------------------------------ E15 Auswertung
a = zl.auswertung(db)
assert a["n"] == 6 and a["n_gesperrt"] == 1 and a["n_zurueck"] == 0, (a["n"], a["n_gesperrt"], a["n_zurueck"])
assert a["nach_art"][0][0] == "Stahl · MAG" and a["nach_gewicht"][0][0] == "10–50 kg"
assert dict(a["haeufig"])["20–50 % mehr"] == 5 and dict(a["haeufig"])["über 50 % mehr"] == 1
assert a["hoch"][0]["angebot"] == "2026-00006" and a["hoch"][0]["weit"] and len(a["verlauf"]) == 6
ok("E15 Auswertung: Anzahl, Mittel, Gruppen nach Art/Material/Gewicht, häufigste Abweichungen, größte Korrekturen")

# ------------------------------------------------------------------ Editor
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser import bg_zeit_dialoge  # noqa: E402
eltern = QWidget()
eltern.k = db.kontext()
eltern.kopf = dict(nummer="2026-00900")
p = dict(pos(gruppe()), id=1, pos=1)
d = BaugruppeDialog(eltern, p, [p], TAB, SAETZE, db=db)
f = d.zeit_feld
assert "automatisch berechnet" in f.status.text() and f.auto_l["gesamt_min"].text() == "automatisch 3 h 10 min"
f.felder["gesamt_min"].setText("240")
f.felder["gesamt_min"].editingFinished.emit()
nah(d.erg["zeit_min"], 240.0, "Editor rechnet sofort mit 240")
assert "Gesamtzeit von Hand" in f.status.text() and f.abw_l["gesamt_min"].text() == "+50 min (+26 %)", f.abw_l["gesamt_min"].text()
assert not f.felder["stueck_min"].isEnabled() and not f.b_feld["Schweißen"].isEnabled(), "überdeckte Felder ruhen"
assert d.daten()["vorgabe"]["von"] == "PB" and len(bv.protokoll(d.daten())) == 1
f.felder["gesamt_min"].setText("4,5 h")
f.felder["gesamt_min"].editingFinished.emit()
nah(d.erg["zeit_min"], 270.0, "Stunden")
assert len(bv.protokoll(d.daten())) == 2 and not f.protokoll_k.isHidden()
# Baugruppe ändern: Hinweis erscheint, Zeit bleibt
d.bg["arbeitsgaenge"][0]["zeit_min"] = 120
d.aktualisieren()
nah(d.erg["zeit_min"], 270.0, "bleibt")
assert not f.pruef_w.isHidden() and "Zeit von Hand prüfen" in f.pruef_l.text()
f.pruef_k.click()
assert f.pruef_w.isHidden() and d.daten()["vorgabe"]["gesamt_min"] == 270.0
d.bg["arbeitsgaenge"][0]["zeit_min"] = 20
f.zurueck["gesamt_min"].click()
nah(d.erg["zeit_min"], 190.0, "↺ = automatisch")
assert len(bv.protokoll(d.daten())) == 3
# Lernvorschlag: nur Anzeige, übernommen wird mit dem Knopf


def merkmale_fest(*_a, **_k):
    return dict(M)


zl_merkmale = zl.merkmale
zl.merkmale = merkmale_fest
try:
    d._zeit_faelle = None
    d.aktualisieren()
    vs = d._zeit_vorschlag
    assert vs and not f.vorschlag_w.isHidden() and "Zeitvorschlag aus vergleichbaren Baugruppen" in f.vorschlag_l.text()
    assert "vergleichbare Datensätze: " + str(vs["n"]) in f.vorschlag_l.text()
    nah(d.erg["zeit_min"], 190.0, "Vorschlag ändert nichts von allein")
    assert "vorgabe" not in d.daten()
    f.vorschlag_k.click()
    nah(d.erg["zeit_min"], vs["min"], "mit Knopf übernommen", 0.05)
    e = bv.protokoll(d.daten())[-1]
    assert e["vorschlag"] == dict(min=vs["min"], n=vs["n"]) and "übernommen" in f.vorschlag_l.text()
    vd = bg_zeit_dialoge.VergleichDialog(d, vs, d.erg["zeiten"])
    assert vd.tab.rowCount() == len(vs["vergleichbare"])
    n_vor = len(zl.faelle(db, alle=True))
    assert d.zeit_lernen_merken() == "neu" and d.zeit_lernen_merken() is None, "einmal je Angebot und Baugruppe"
    zeile = zl.zeile(db, "2026-00900", d.bg["id"])
    assert len(zl.faelle(db, alle=True)) == n_vor + 1 and zeile["quelle"] == "Gesamtzeit" and zeile["kuerzel"] == "PB"
    nah(zeile["vorschlag_min"], vs["min"])
    # Kopie der Baugruppe in ein anderes Angebot: zählt nicht noch einmal
    eltern2 = QWidget()
    eltern2.k = eltern.k
    eltern2.kopf = dict(nummer="2026-00901")
    kop = dict(p, baugruppe=baugruppe.speichern(dict(d.daten(), id="kopie1")))
    d2 = BaugruppeDialog(eltern2, kop, [kop], TAB, SAETZE, db=db)
    assert d2.zeit_lernen_merken() is None and zl.zeile(db, "2026-00901", "kopie1") is None
finally:
    zl.merkmale = zl_merkmale
pd = bg_zeit_dialoge.ProtokollDialog(d, d.daten())
assert pd.liste.count() == 4
ad = bg_zeit_dialoge.AuswertungDialog(d, db)
assert ad.tab.rowCount() == len(ad.a["zeilen"]) and "Schweißbaugruppen mit Zeit von Hand" in ad.kopf.text()
ad.resize(1000, 600)
for i in range(ad.wahl.count()):
    ad.wahl.setCurrentIndex(i)
    assert not ad.diagramm.grab().isNull()
n_frei = ad.a["n"]
ad.tab.selectRow(0)
ad._sperren()
assert ad.a["n"] == n_frei - 1, "gesperrt zählt nicht mehr"
ad.tab.selectRow(0)
ad._sperren()
assert ad.a["n"] == n_frei
ok("Editor: Gesamtzeit sofort, Abweichung, Protokoll, Prüfhinweis, Vorschlag nur mit Knopf, Vergleich, Auswertung mit Grafik")
# Struktur und Stückliste im Editor
from rohrlaser import bg_stueckliste  # noqa: E402
p3 = dict(pos(gruppe()), id=30, pos=3)
teile3 = [dict(id=31, pos=1, artikel="R-1", bezeichnung="Rohr", profil_id="x", stueck=10),
          dict(id=32, pos=2, artikel="B-1", bezeichnung="Lasche", technik="laser", stueck=20)]
d = BaugruppeDialog(eltern, p3, [p3] + teile3, TAB, SAETZE, db=db, vorwahl={31, 32})
d.baum_aufbauen()
arten = [k[0] for k in d.baum_items]
assert arten.count("ag") == len(d.bg["arbeitsgaenge"]) > 0, "Arbeitsgänge stehen in der Struktur"
teil_it = next(it for k, it in d.baum_items.items() if k[0] == "teil")
assert teil_it.toolTip(0).split(":")[0] in (bg_stueckliste.ROHR, bg_stueckliste.BLECH, bg_stueckliste.ZUKAUF)
d.baum.setCurrentItem(next(it for k, it in d.baum_items.items() if k[0] == "ag"))
d.baum_gewaehlt()                                       # Arbeitsgang gewählt: kein Fehler, nichts hervorgehoben
sd = bg_stueckliste.StuecklisteDialog(d, d.daten(), d.teile, 5, "Test")
drin = [t for t in d.teile if t.get("drin")]
assert sd.tab.rowCount() == len(drin) == len(sd.liste) and "Einzelteile" in sd.kopf.text()
z0 = sd.liste[0]
t0 = next(t for t in drin if str(t["_q"].get("pos") or "") == z0[0])
f0 = baugruppe.faktor(d.bg, t0.get("knoten") or "")
nah(float(z0[8].replace(",", ".")), (t0.get("je") or 1) * f0 * 5, "Auftrag = je Baugruppe × Anzahl")
assert bg_stueckliste.teil_art(dict(profil_id="x")) == bg_stueckliste.ROHR
assert bg_stueckliste.teil_art(dict(technik="laser")) == bg_stueckliste.BLECH
import os  # noqa: E402
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as ordner:
    pfad = sd.speichern(os.path.join(ordner, "s.csv"))
    inhalt = open(pfad, encoding="utf-8-sig").read().splitlines()
assert inhalt[0].split(";") == list(bg_stueckliste.SPALTEN) and len(inhalt) == len(drin) + 1
assert d.stueckliste_knopf.text() == "Stückliste …"
ok("Editor: Arbeitsgänge in der Struktur, Teileart im Baum, Stückliste mit Stückzahlen je Baugruppe und Auftrag, CSV")
print("Alle Tests Schweißbaugruppen-Editor 2.0 bestanden.")
