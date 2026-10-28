"""Prüft die Vorkalkulation der Schweißbaugruppe (Plan Vorkalkulation, Patrick 24.10.2026, V1):
- V1a Schema 53: Tabelle schweiss_regeln leer, Spalte positionen.bg_hilfe, Richtwerte nur per 'Richtwerte laden'
- V1b Beispiel aus Abschnitt 6 des Plans (Beispielwerte): Rüsten 18 min, Positionieren 6,8 min, Heften 2 bzw. 4
  Heftpunkte, Verputzen 1,92 min
- V1c Abnahme 2: dasselbe Gestell ohne Steckverbindung und Gravur: Positionieren 16,0 min, 32 Heftpunkte
- V1d Werte von Hand bzw. bestätigt bleiben bei neuer Vorkalkulation, Vorschläge zählen als HINWEIS im Status
- V1e fehlende Regeln: kein Vorschlag, sondern Hinweis; Wenden nach Gewicht; Unterbaugruppen mit Basisteil
- V1f Rahmen R1 und Baugruppen ohne Vorkalkulation rechnen bitgleich
- V2a Editor: Knopf „Vorkalkulation rechnen“, gelbe Vorschläge mit Begründung, Änderung = Hand, Wendevorgänge
- V2b Positionierhilfe je Teil (Vorschlag, bestätigen schreibt bg_hilfe), Sprung vom Status, Kalkulation-PDF
  „(Vorschlag)“, Einstellung „Vorkalkulation beim STEP-Import“

Aufruf: python tests/test_vorkalk.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, POSITIONEN, ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-9):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ V1a Schema und Richtwerte
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "vk.db")
assert SCHEMA_VERSION >= 53
assert db.anzahl("schweiss_regeln") == 0
assert "bg_hilfe" in {r[1] for r in db.con.execute("PRAGMA table_info(positionen)")}
assert POSITIONEN.feld("bg_hilfe").auswahl == "positionierhilfe"
assert db.kontext().auswahl("positionierhilfe") == ["Steckverbindung", "Vorrichtung", "Gravur", "frei"]
fehlt = baugruppe.richtwerte_fehlend(db.tabellen())
assert len(fehlt["schweiss_regeln"]) == len(vorkalk.RICHTWERTE)
assert all(z["status"] == "Richtwert" for z in fehlt["schweiss_regeln"])
for z in fehlt["schweiss_regeln"]:
    db.neu("schweiss_regeln", z)
assert not baugruppe.richtwerte_fehlend(db.tabellen())["schweiss_regeln"]
ok("V1a Schema 53: schweiss_regeln leer, bg_hilfe, Richtwerte nur per Knopf")

# ------------------------------------------------------------------ V1b Beispiel aus dem Plan
BEISPIEL = [("Positionieren", "Basisteil", None, 0.0), ("Positionieren", "frei", None, 2.0),
            ("Positionieren", "Gravur", None, 1.2), ("Positionieren", "Steckverbindung", None, 0.5),
            ("Positionieren", "Vorrichtung", None, 0.8),
            ("Rüsten", "Grundrüstzeit", None, 15.0), ("Rüsten", "je Teilenummer", None, 1.0),
            ("Heftabstand", "bis 4 mm", 4.0, 50.0), ("Heftabstand", "über 4 mm", None, 60.0),
            ("Heften", "Mindestzahl gerade", None, 2.0), ("Heften", "Mindestzahl rundum", None, 3.0),
            ("Heften", "Mindestzahl gesteckt", None, 1.0), ("Heften", "Faktor Abstand gesteckt", None, 2.0),
            ("Nacharbeit", "Spritzer entfernen", None, 1.5),
            ("Wenden", "Zeit je Wenden", None, 2.0), ("Wenden", "Faktor bis 20 kg", 20.0, 1.0),
            ("Wenden", "Faktor über 20 kg", None, 1.5)]
tab = dict(schweiss_regeln=[dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z in BEISPIEL])


def gestell(steck=True, gravur=True):
    """Plan 6: Grundrahmen (Knickrahmen, 1 Teil), 4 Beine gesteckt, 4 Fußplatten mit Gravur-Umriss, pulverbeschichtet."""
    bg = baugruppe.leer()
    bg["stamm"] = dict(oberflaeche="pulverbeschichtet")
    bg["naehte"] = [dict(id="n1", nr=1, verfahren="MAG", nahtart="Kehlnaht", mass=2, laenge=160, anzahl=4, dicke=2,
                         gesteckt=steck or None),
                    dict(id="n2", nr=2, verfahren="MAG", nahtart="Kehlnaht", mass=2, laenge=160, anzahl=4, dicke=2)]
    if steck:
        bg["steckverbindungen"] = [dict(id=f"s{n}", aufnahme="10", stecker="20") for n in range(4)]
    anbau = json.dumps([dict(nr=1, art="Kopfplatte", bearbeitung="Umriss" if gravur else "keine", status="bestätigt")])
    pos = [dict(pos=1, art=BAUGRUPPE, bezeichnung="Gestell", stueck=10, baugruppe=baugruppe.speichern(bg)),
           dict(pos=10, artikel="RAHMEN", bezeichnung="Grundrahmen", bg_knoten=bg["id"], je_knoten=1),
           dict(pos=20, artikel="BEIN", bezeichnung="Bein", bg_knoten=bg["id"], je_knoten=4, anbauteile=anbau),
           dict(pos=30, art=ZUKAUFTEIL, artikel="PLATTE", bezeichnung="Fußplatte", bg_knoten=bg["id"], je_knoten=4)]
    return pos


pos = gestell()
erg = vorkalk.vorkalkulieren(pos[0], pos, tab)
bg = erg["bg"]
assert erg["hinweise"] == [], erg["hinweise"]
assert [h for h, _, _ in (erg["hilfen"][i] for i in (1, 2, 3))] == ["Steckverbindung", "Steckverbindung", "Gravur"]
ag = {a["vk"]["art"]: a for a in bg["arbeitsgaenge"]}
assert set(ag) == {"ruesten", "positionieren", "verputzen"}            # Wenden ohne Wendevorgänge: keiner
nah(ag["ruesten"]["ruest_min"], 18, "Rüsten 15 + 1 × 3")
assert ag["ruesten"]["umlage"] == baugruppe.UMLAGE_AUFTRAG and not ag["ruesten"].get("zeit_min")
nah(ag["positionieren"]["zeit_min"], 6.8, "Positionieren 0 + 4 × 0,5 + 4 × 1,2")
assert "Basisteil" in ag["positionieren"]["vk"]["text"]
n1, n2 = bg["naehte"]
assert n1["heftpunkte"] == 3 and n2["heftpunkte"] == 5, (n1["heftpunkte"], n2["heftpunkte"])   # + 1 Enden (0.9.177)
assert "gesteckt" in n1["vk"]["heftpunkte"]["text"]
assert n1["nacharbeit"] == n2["nacharbeit"] == "Spritzer entfernen"
nah(ag["verputzen"]["zeit_min"], 8 * 0.16 * 1.5, "Verputzen (4 × 0,16 + 4 × 0,16) m × 1,5")
assert all(a["satz_id"] == "Schweißen" for a in ag.values())
assert vorkalk.offen(bg) == 7          # 2 × Heftpunkte, 2 × Nacharbeit, 3 Arbeitsgänge
assert not erg["richtwert"]
ok("V1b Plan-Beispiel: Rüsten 18 min, Positionieren 6,8 min, Heften 3/5, Verputzen 1,92 min")

# ------------------------------------------------------------------ V1c ohne Steckverbindung und Gravur
pos0 = gestell(steck=False, gravur=False)
erg0 = vorkalk.vorkalkulieren(pos0[0], pos0, tab)
ag0 = {a["vk"]["art"]: a for a in erg0["bg"]["arbeitsgaenge"]}
nah(ag0["positionieren"]["zeit_min"], 16.0, "ohne Hilfen 4 × 2,0 + 4 × 2,0")
heft = sum(n["heftpunkte"] * n["anzahl"] for n in erg0["bg"]["naehte"])
assert heft == 40, heft                                                # (4 + 1) × 4 × 2
assert sum(n["heftpunkte"] * n["anzahl"] for n in bg["naehte"]) == 32          # gesteckt: 8 Heftpunkte weniger
ok("V1c ohne Steckverbindung und Gravur: Positionieren 16,0 min, 40 Heftpunkte (gesteckt 9,2 min und 8 weniger)")

# ------------------------------------------------------------------ V1d Hand, bestätigt, Status
pos[0]["baugruppe"] = baugruppe.speichern(bg)
bg2 = baugruppe.lesen(pos[0]["baugruppe"])
bg2["naehte"][1]["heftpunkte"] = 6                                   # von Hand
a_pos = next(a for a in bg2["arbeitsgaenge"] if a["vk"]["art"] == "positionieren")
a_pos["zeit_min"] = 9.5                                              # von Hand
assert vorkalk.naht_status(bg2["naehte"][1], "heftpunkte") == vorkalk.HAND and vorkalk.ag_status(a_pos) == "hand"
a_r = next(a for a in bg2["arbeitsgaenge"] if a["vk"]["art"] == "ruesten")
a_r["vk"]["status"] = vorkalk.BESTAETIGT                             # bestätigt
pos[0]["baugruppe"] = baugruppe.speichern(bg2)
tab2 = dict(schweiss_regeln=[dict(z, zahl=z["zahl"] * 2) if z["art"] in ("Rüsten", "Positionieren", "Heftabstand")
                             else z for z in tab["schweiss_regeln"]])
bg3 = vorkalk.vorkalkulieren(pos[0], pos, tab2)["bg"]
ag3 = {a["vk"]["art"]: a for a in bg3["arbeitsgaenge"]}
assert bg3["naehte"][1]["heftpunkte"] == 6 and ag3["positionieren"]["zeit_min"] == 9.5    # Hand bleibt
assert ag3["ruesten"]["ruest_min"] == 18                                                  # bestätigt bleibt
assert bg3["naehte"][0]["heftpunkte"] == 2                                               # neu: 1 + 1 Ende
assert vorkalk.ag_status(ag3["positionieren"]) == vorkalk.HAND
pos[0]["baugruppe"] = baugruppe.speichern(bg3)
w = dict(bg_tabellen=dict(tab, schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=40, heft_s=6,
                                                       status="geprüft")],
                         schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=1.5,
                                                  status="geprüft")]), saetze={"Schweißen": 75.0})
st = baugruppe.status(pos[0], w)
assert st.startswith("HINWEIS:") and "Vorkalkulation offen" in st, st
assert vorkalk.bestaetigen(bg3) == vorkalk.offen(baugruppe.lesen(pos[0]["baugruppe"])) > 0
assert vorkalk.offen(bg3) == 0
pos[0]["baugruppe"] = baugruppe.speichern(bg3)
assert "Vorkalkulation" not in baugruppe.status(pos[0], w)
# Hand an der Position: Positionierhilfe bestätigt bzw. geändert
pos[3]["bg_hilfe"] = "frei"
erg4 = vorkalk.vorkalkulieren(pos[0], pos, tab)
assert erg4["hilfen"][3][:2] == ("frei", vorkalk.HAND)
ok("V1d Hand und bestätigt bleiben, offene Vorschläge = HINWEIS, Bestätigen leert ihn, bg_hilfe = Hand")

# ------------------------------------------------------------------ V1e fehlende Regeln, Wenden, Unterbaugruppen
leer = vorkalk.vorkalkulieren(pos0[0], pos0, {})
assert not leer["bg"]["arbeitsgaenge"] and any("Richtwerte laden" in h for h in leer["hinweise"])
assert all(n.get("heftpunkte") is None for n in leer["bg"]["naehte"])
assert any("Heftpunkte ohne Vorschlag" in h for h in leer["hinweise"])
ohne_dicke = dict(laenge=100, nahtart="Kehlnaht", mass=3)
assert vorkalk.heftpunkte(ohne_dicke, vorkalk.Regeln(tab)) == (None, "Wanddicke fehlt (Spalte Dicke)")
assert vorkalk.heftpunkte(dict(laenge=100, nahtart="Stumpfnaht", mass=5), vorkalk.Regeln(tab))[0] == 3  # Maß = Dicke
assert vorkalk.heftpunkte(dict(laenge=20, dicke=3, rundum=True), vorkalk.Regeln(tab))[0] == 3
bgw = baugruppe.lesen(pos0[0]["baugruppe"])
bgw["wenden"] = 2
pw = dict(pos0[0], baugruppe=baugruppe.speichern(bgw))
e = vorkalk.vorkalkulieren(pw, pos0, tab)
assert any("Gewicht der Baugruppe fehlt" in h for h in e["hinweise"])
bgw["stamm"]["gewicht"] = "35,5 kg"
pw = dict(pos0[0], baugruppe=baugruppe.speichern(bgw))
aw = next(a for a in vorkalk.vorkalkulieren(pw, pos0, tab)["bg"]["arbeitsgaenge"] if a["vk"]["art"] == "wenden")
assert aw["menge"] == 2 and aw["zeit_min"] == 3.0, aw              # 2 min × 1,5 (über 20 kg)
# Unterbaugruppe: 2 Rahmenhälften je 3 Teile, darin je 1 Basisteil; die Hälften selbst als Teile 'frei'
bgu = baugruppe.leer()
bgu["knoten"] = [dict(id="H", name="Hälfte", menge=2, parent="")]
pu = [dict(pos=1, art=BAUGRUPPE, bezeichnung="Rahmen", stueck=1, baugruppe=baugruppe.speichern(bgu)),
      dict(pos=10, artikel="A", bg_knoten=bgu["id"] + "/H", je_knoten=1),
      dict(pos=20, artikel="B", bg_knoten=bgu["id"] + "/H", je_knoten=2)]
t, text = vorkalk.positionieren(bgu, pu, bgu["id"], vorkalk.Regeln(tab), {1: "frei", 2: "frei"})
nah(t, 2 * (0 + 2 * 2.0) + (0 + 1 * 2.0), "Hälften je 0 + 2 × 2 und Baugruppe 0 + 1 × 2")
ok("V1e fehlende Regeln = Hinweis, Wanddicke, rundum, Wenden nach Gewicht, Unterbaugruppen mit Basisteil")

# ------------------------------------------------------------------ V1f bitgleich ohne Vorkalkulation
p_ohne = gestell()[0]
r1 = baugruppe.rechnen(p_ohne, {}, {"Schweißen": 75.0})
assert baugruppe.status(p_ohne, dict(bg_tabellen={}, saetze={})).find("Vorkalkulation") < 0
assert r1["zeilen"] == [] or all(z["art"] == "Naht" for z in r1["zeilen"])
assert vorkalk.offen(baugruppe.lesen(p_ohne["baugruppe"])) == 0
ok("V1f ohne Vorkalkulation: keine Arbeitsgänge, kein Hinweis (Abnahme R1 siehe test_baugruppe_abnahme)")

# ------------------------------------------------------------------ V2a Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import pdf  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stil import GELB_FLAECHE  # noqa: E402

app = QApplication.instance() or QApplication([])
assert db.einstellung("schweiss_vk_step") == "nein"                     # Vorgabe: nur per Knopf
for t_, zeilen_ in baugruppe.richtwerte_fehlend(db.tabellen()).items():   # Verfahren, Kennwerte (Richtwerte)
    for z_ in zeilen_:
        db.neu(t_, z_)
bg_e = baugruppe.leer()
bg_e["stamm"] = dict(oberflaeche="verzinkt", gewicht="12")
bg_e["naehte"] = [dict(id="e1", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120, anzahl=2, dicke=3)]
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
pb = db.position_neu(a, dict(pos=1, art=BAUGRUPPE, bezeichnung="Konsole", stueck=5, baugruppe=baugruppe.speichern(bg_e)))
pr = db.position_neu(a, dict(pos=10, artikel="ROHR", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                             stueck=5, bg_knoten=bg_e["id"], je_knoten=1))
pz = db.position_neu(a, dict(pos=20, art=ZUKAUFTEIL, artikel="LASCHE", stueck=10, bg_knoten=bg_e["id"], je_knoten=2))
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
p_e = next(q for q in seite.positionen if q["id"] == pb)
d = BaugruppeDialog(None, p_e, seite.positionen, seite.tabellen, {"Schweißen": 75.0})


def zelle(tab, r, schluessel):
    w = tab.cellWidget(r, [s.schluessel for s in tab.spalten].index(schluessel))
    return getattr(w, "feld", w), w


r = d.vorkalkulation()
assert r["richtwert"] and "Richtwerte" in d.vk_info.text()
namen = [x["name"] for x in d.bg["arbeitsgaenge"]]
assert namen == ["Rüsten Schweißplatz", "Teile positionieren", "Verputzen", "Sichtprüfung"], namen     # 0.9.174
nah(d.bg["arbeitsgaenge"][0]["ruest_min"], 15 + 1 * 2, "Rüsten mit Richtwerten 15 + 1 × 2")
nah(d.bg["arbeitsgaenge"][1]["zeit_min"], 0.5 + 2 * 2.0, "Basisteil 0,5 + 2 Laschen frei × 2,0")
assert d.bg["naehte"][0]["heftpunkte"] == 4 and d.bg["naehte"][0]["nacharbeit"] == "Spritzer entfernen"
feld, huelle = zelle(d.naht_tab, 0, "heftpunkte")
assert feld.text() == "4" and GELB_FLAECHE in feld.styleSheet() and "aufrunden" in huelle.toolTip()
assert GELB_FLAECHE in zelle(d.ag_tab, 1, "zeit_min")[0].styleSheet()
assert vorkalk.offen(d.bg) == 6 and "6 Vorschläge der Vorkalkulation offen" in d.status, d.status
assert d.fokus(d.status) == (1, 0)                                     # Sprung zur ersten Nahtgruppe mit Vorschlag
feld.setText("5")                                                      # von Hand
assert vorkalk.naht_status(d.bg["naehte"][0], "heftpunkte") == vorkalk.HAND and feld.styleSheet() == ""
d.wenden.setValue(2)
assert d.bg["wenden"] == 2
d.vorkalkulation()
assert d.bg["naehte"][0]["heftpunkte"] == 5                            # Hand bleibt
aw = next(x for x in d.bg["arbeitsgaenge"] if x["name"] == "Wenden / Umspannen")
assert aw["menge"] == 2 and aw["zeit_min"] == 1.5                     # 12 kg: Faktor 1,0
ok("V2a Editor: Vorkalkulation rechnen, gelb mit Begründung, Sprung vom Status, Hand bleibt, Wendevorgänge")

# ------------------------------------------------------------------ V2b Positionierhilfe, PDF, STEP-Import
i_z = next(i for i, t in enumerate(d.teile) if t["_id"] == pz)
assert d.hilfe_vk[pz][0] == "frei" and d.teile_tab.cellWidget(i_z, [s.schluessel for s in d.teile_tab.spalten]
                                                               .index("_hilfe_vk")).text().startswith("frei")
assert GELB_FLAECHE in zelle(d.teile_tab, i_z, "hilfe")[0].styleSheet()
z = next(x for x in d.erg["zeilen"] if x["art"] == "Arbeitsgang" and x["name"] == "Verputzen")
assert z["vorschlag"]
texte = " ".join(getattr(x, "text", "") for x in pdf._baugruppen_abschnitt(
    [dict(baugruppe=True, pos=1, bg_zeilen=d.erg["zeilen"])], 200) if hasattr(x, "text"))
pdf_tab = next(x for x in pdf._baugruppen_abschnitt([dict(baugruppe=True, pos=1, bg_zeilen=d.erg["zeilen"])], 200)
               if hasattr(x, "_cellvalues"))
assert any("(Vorschlag)" in getattr(c, "text", str(c)) for zeile_ in pdf_tab._cellvalues for c in zeile_), texte
n = d.vorschlaege_bestaetigen()
assert n >= 6 and vorkalk.offen(d.bg) == 0 and "der Vorkalkulation offen" not in d.status
assert d.teile[i_z]["hilfe"] == "frei" and zelle(d.teile_tab, i_z, "hilfe")[0].styleSheet() == ""
assert not next(x for x in d.erg["zeilen"] if x["name"] == "Verputzen")["vorschlag"]
w = d.werte()
assert w["teile"][pz]["bg_hilfe"] == "frei" and w["teile"][pr]["bg_hilfe"] == "frei"
# STEP-Import mit Einstellung: Vorschläge sofort in die neue Baugruppe
bericht = []
seite._vorkalkulieren({1}, bericht)
bg_db = baugruppe.lesen(db.position(pb)["baugruppe"]) if hasattr(db, "position") else baugruppe.lesen(
    next(q for q in db.positionen(a) if q["id"] == pb)["baugruppe"])
assert vorkalk.offen(bg_db) == 6 and "Vorkalkulation" in bericht[0], (vorkalk.offen(bg_db), bericht)
ok("V2b Positionierhilfe bestätigt = bg_hilfe, Kalkulation-PDF „(Vorschlag)“, Vorkalkulation beim STEP-Import")
assert bg_db["stamm"]["vk_auto"] is True, "STEP-Import mit Einstellung: Häkchen Vorkalkulation automatisch"

# ------------------------------------------------------------------ Vorkalkulation automatisch (Patrick 24.10.2026)
VOR = dict(teile=[[1, 2]], knoten="", nahtart="Kehlnaht", laenge=160, anzahl=2, dicke=3)
bg_k = baugruppe.lesen(next(q for q in db.positionen(a) if q["id"] == pb)["baugruppe"])
bg_k["vorschlaege"] = [dict(VOR)]
bg_k["stamm"].pop("vk_auto", None)
db.position_aendern(pb, "baugruppe", baugruppe.speichern(bg_k))
seite.neu_laden()
p_k = next(q for q in seite.positionen if q["id"] == pb)
r = vorkalk.komplett(p_k, seite.positionen, seite.tabellen, dict(schweiss_a_regel=0.7))
neu = r["bg"]["naehte"][-1]
assert r["naehte_neu"] == 1 and not r["bg"]["vorschlaege"], r["naehte_neu"]
assert neu["nahtart"] == "Kehlnaht" and neu["mass"] == neu["mass_regel"] == 3 and neu["verfahren"], neu
assert baugruppe.regel_offen(neu) and vorkalk.naht_status(neu, "heftpunkte") == vorkalk.VORSCHLAG
assert "1 Nahtgruppe(n) aus den STEP-Vorschlägen" in r["aenderungen"][0]
# Editor: Vorgabe aus der Einstellung, ohne Wahl der Baugruppe
d0 = BaugruppeDialog(None, p_k, seite.positionen, seite.tabellen, {"Schweißen": 75.0})
assert not d0.vk_auto.isChecked() and d0.bg["vorschlaege"], "Einstellung nein: aus, Vorschläge bleiben"
d1 = BaugruppeDialog(None, p_k, seite.positionen, seite.tabellen, {"Schweißen": 75.0},
                     einstellungen=dict(schweiss_vk_step="ja"))
assert d1.vk_auto.isChecked() and not d1.bg["vorschlaege"], "Einstellung ja: beim Öffnen alles vorgeschlagen"
assert len(d1.bg["naehte"]) == len(bg_k["naehte"]) + 1 and d1.daten()["stamm"]["vk_auto"] is True
n_vorher = len(d1.bg["naehte"])
d1.anzahl.setValue(7)
d1._vk_nach_eingabe()                                                   # wie nach der Eingabe (Timer)
assert len(d1.bg["naehte"]) == n_vorher and "Vorkalkulation" in d1.vk_info.text()
d1.vk_auto.setChecked(False)
assert d1.daten()["stamm"]["vk_auto"] is False
d1._ok()
w = d1.ergebnis["position"]
assert baugruppe.vk_auto(baugruppe.lesen(w["baugruppe"]), True) is False, "je Baugruppe abgeschaltet bleibt aus"
d2 = BaugruppeDialog(None, dict(p_k, baugruppe=w["baugruppe"]), seite.positionen, seite.tabellen, {"Schweißen": 75.0},
                     einstellungen=dict(schweiss_vk_step="ja"))
assert not d2.vk_auto.isChecked()
ok("Vorkalkulation automatisch: Vorgabe aus der Einstellung, je Baugruppe ja/nein, Nahtvorschläge mit a-Maß-Regel")
print("Vorkalkulation V1 und V2: alle Tests bestanden.")
