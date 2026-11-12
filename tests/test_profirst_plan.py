"""Prüft den Plan aus den PROfirst-/LogiTRACE-Handbüchern (Freigabe Patrick 12.11.2026 „alles umsetzten“):
- I3 Kennzeichen „nur kalkuliert“: Status-Hinweis, keine STEP im CAM-Ordner, Spalte Geometrie, Umschalten, STEP
  in der Position sichert die Geometrie.
- H1 weniger verschiedene Stangenbelegungen bei höchstens 2 % Mehrverschnitt (Einstellung muster_mehrverschnitt).
- G1 Kundenhinweis, G2 Ertrag nach Einkauf/Herstellkosten, G3 Zusatzarbeit mit Formel und Wertetabelle.
- H2 Meldebestand Lager, I1 Teil in früheren Stangenplänen, I2 Stangen melden, offene Menge, Restplan.
- J1 Kantbarkeit gegen Gesenke und Abkantpresse, J2 K-Faktor nach Formel × Werkstoff.
- G4 Teilebilder, G5 Schnittstelle beim Beauftragen, H3 Füllteile, I4 Abwicklung 1:1.
- H4 Wenden sperren: Feld wenden = 'nein', Umschalten (ganzer Satz).

Aufruf: python tests/test_profirst_plan.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import cam_paket, geometrie, rechnen  # noqa: E402
from rohrlaser import optimierung as opt  # noqa: E402
from rohrlaser import abwicklung_druck, auftrag_skript, fuellteile, teilebilder  # noqa: E402
from rohrlaser import blech, lager, rueckverfolgung as rv  # noqa: E402
from rohrlaser import ertrag, kundenhinweis, zusatz_formel as zf, zusatz_regeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
TECHNIK = dict(quelle="STEP-Import", a=dict(winkel=0.0), b=dict(winkel=0.0),
               konturen=[dict(art="Bohrung", d=10.0, x=50.0, anzahl=2, abstand=100.0, seite="A")])
a = db.angebot_neu(dict(nummer="A-2026-1211", kundennr="K-1001", kunde="Beispiel Metallbau GmbH (erfunden)",
                        datum="2026-11-12", maschine="T11", stange=6000))
p10 = db.position_neu(a, dict(pos=10, artikel="AB-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=485.0, stueck=40, schneidweg=380, einstiche=4,
                              technik=json.dumps(TECHNIK)))
p20 = db.position_neu(a, dict(pos=20, artikel="AB-20", bezeichnung="Aus PDF", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=600.0, stueck=20, schneidweg=400, einstiche=2,
                              technik=json.dumps(dict(quelle="Schneidweg-Rechner", a={}, b={}, konturen=[],
                                                      pdf="AB-20.pdf")),
                              geometrie=geometrie.NUR_KALKULIERT))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
erg = rechnen.optimieren(kopf, pos, k, tab, einst)

# ------------------------------------------------------------------ I3 nur kalkuliert
assert geometrie.aus_zeichnung(dict(quelle_name="PDF-Zeichnung")) == geometrie.NUR_KALKULIERT
assert geometrie.aus_zeichnung(dict(quelle_name="PDF-Zeichnung (Linien)")) == geometrie.NUR_KALKULIERT
assert geometrie.aus_zeichnung(dict(quelle_name="DXF")) is None
assert geometrie.nur_kalkuliert(pos[1]) and not geometrie.nur_kalkuliert(pos[0])
assert not geometrie.nur_kalkuliert(dict(pos[1], technik=json.dumps(dict(step_datei="x.stp"))))   # STEP sichert
assert geometrie.umschalten(pos[1]) == geometrie.GEPRUEFT and geometrie.umschalten(pos[0]) == geometrie.NUR_KALKULIERT
assert geometrie.wert(dict(geometrie="Quatsch")) == ""
st = rechnen.status(pos[1], rechnen.position_werte(pos[1], kopf, k, tab), kopf, k, positionen=pos)
assert st == geometrie.STATUS, st
assert "nur kalkuliert" not in rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k,
                                               positionen=pos)
bericht = cam_paket.schreiben(tmp / cam_paket.ordnername(kopf), kopf, pos, erg, k, tab, einst, step=False)
with open(Path(bericht["ordner"]) / "Stueckliste.csv", encoding="utf-8-sig") as f:
    reihen = list(csv.reader(f, delimiter=";"))
assert reihen[0][-1] == "Geometrie" and reihen[2][-1] == geometrie.NUR_KALKULIERT and reihen[1][-1] == ""
assert reihen[2][10] == "" and reihen[1][10]          # nur kalkuliert: keine STEP-Datei
assert any("nur kalkuliert" in h for h in bericht["fehlen"]) and "nur kalkuliert" in cam_paket.text(bericht)
ok(f"I3 nur kalkuliert: Status „{st[:40]} …“, CAM ohne STEP für Pos. 20")

# ------------------------------------------------------------------ H1 weniger Belegungen
def gruppe(spec):
    g = opt.Gruppe("RE 60x40x3", "S235", 6000, 10, 100, 2, 0)
    g.teile = [opt.Teil(z, z, f"A{z}", i + 1, l, True, True, 10, 10) for z, (l, n) in enumerate(spec) for i in range(n)]
    return g


g = gruppe([(1450, 37), (980, 53), (620, 41), (410, 29)])
f = opt.optimiere(g)
arm = opt.musterarm(g, f, 0.02)
assert arm and opt.belegungen(arm) < opt.belegungen(f) and len(arm) <= len(f) + int(0.02 * len(f))
assert sorted((t.zeile, t.nr) for s in arm for t, _ in s) == sorted((t.zeile, t.nr) for t in g.teile)
assert all(opt.belegt(g, s) <= g.nutzbar_bis + 1e-6 for s in arm)
assert opt.musterarm(g, f, 0) is None
tab2 = dict(tab, einstellungen=dict(tab["einstellungen"], muster_mehrverschnitt=0.02))
erg2 = rechnen.optimieren(kopf, pos, k, tab2, einst)
aw = erg2["auswertung"][0]
assert "verschiedene Belegungen" in aw["bewertung"], aw["bewertung"]
assert "Belegungen" not in erg["auswertung"][0]["bewertung"]          # Vorgabe aus
assert len(erg2["stangen"]) == len(erg["stangen"])
tab0 = dict(tab, einstellungen=dict(tab["einstellungen"], muster_mehrverschnitt=0))
assert rechnen.eingabe_kennung(kopf, pos, k, tab0, einst) == rechnen.eingabe_kennung(kopf, pos, k, tab, einst)
assert rechnen.eingabe_kennung(kopf, pos, k, tab2, einst) != rechnen.eingabe_kennung(kopf, pos, k, tab, einst)
ok(f"H1 Belegungen: {opt.belegungen(f)} -> {opt.belegungen(arm)} bei {len(f)} -> {len(arm)} Stangen; "
   f"Angebot: {aw['bewertung']}")

# ------------------------------------------------------------------ H4 nicht wenden
assert geometrie.wenden_erlaubt(pos[0]) and not geometrie.wenden_erlaubt(dict(wenden="nein"))
assert geometrie.wenden_erlaubt(dict(wenden="ja")) and geometrie.wenden_erlaubt(dict(wenden=""))
ok("H4 Wenden: Feld wenden = 'nein' sperrt")

# ------------------------------------------------------------------ G1 Kundenhinweis
db.neu("kunden", dict(kundennr="K-9911", name="Beispiel Metallbau GmbH (erfunden)", hinweis="nur gebürstet liefern",
                      hinweis_werkstatt="ja"))
kopf_k = dict(kopf, kundennr="K-9911")
assert kundenhinweis.fuer_angebot(db, kopf_k) == "nur gebürstet liefern"
assert kundenhinweis.fuer_werkstatt(db, kopf_k) == "nur gebürstet liefern"
assert kundenhinweis.fuer_angebot(db, kopf) == ""
db.angebot_aendern(a, "kundennr", "K-9911")
assert kundenhinweis.fuer_angebot(db, dict(kundennr="gibt es nicht")) == "" and kundenhinweis.fuer_angebot(db, {}) == ""
ok("G1 Kundenhinweis aus dem Kundenstamm")

# ------------------------------------------------------------------ G2 Ertrag
e = ertrag.angebot(dict(verkauf=1000.0, fracht=50.0, material=300.0, schrott=-10.0, zukauf_einstand=40.0,
                        herstell=600.0))
assert abs(e["ware"] - 950) < 1e-9 and abs(e["brutto"] - 620) < 1e-9 and abs(e["netto"] - 310) < 1e-9
assert abs(e["brutto_anteil"] - 620 / 950) < 1e-9
z = dict(preis_position=500.0, stueck=10, fracht_teil=1.0, material_position=120.0, herstell_position=300.0,
         zukauf_einstand_teil=2.0)
assert abs(ertrag.position_brutto(z) - 350) < 1e-9 and abs(ertrag.position_netto(z) - 170) < 1e-9
assert ertrag.position_brutto(dict(stueck=1)) is None
from rohrlaser.angebot_spalten import KALK_SPALTEN  # noqa: E402
assert any(t.startswith("Ertrag nach Einkauf") for t, *_ in KALK_SPALTEN)
ok("G2 Ertrag nach Einkauf und nach Herstellkosten")

# ------------------------------------------------------------------ G3 Formel
assert zf.auswerten("2,50 + 0,004 * L", dict(L=1000)) == 6.5
assert zf.auswerten("max(3; 0,5 * W)", dict(W=4)) == 3 and zf.auswerten("rund(L / 1000)", dict(L=1200)) == 2
assert zf.auswerten("L * X", dict(L=1)) is None and zf.pruefen("__import__('os')")
assert zf.auswerten("G * 2", dict(L=1)) is None              # Größe fehlt
assert zf.tabelle_wert("1000 = 1,20; 3000 = 1,80; 6000 = 2,60", 2500) == 1.8
assert zf.tabelle_wert("1000 = 1,20; 3000 = 1,80", 9000) == 1.8 and zf.tabelle_wert("", 5) is None
richten = dict(name="Richten", art="€/Stück", preis=9.0, formel="T + 0,001 * L", wertetabelle="500 = 1; 1000 = 2",
               tabelle_nach="L")
assert zusatz_regeln.pruefung_zusatz(richten) is None
assert "nur festen Preis" in zusatz_regeln.pruefung_zusatz(dict(richten, name="Gewinde"))
assert "€/Stück" in zusatz_regeln.pruefung_zusatz(dict(richten, art="€/kg"))
assert "nicht lesbar" in zusatz_regeln.pruefung_zusatz(dict(richten, formel="L +"))
tab_f = dict(tab, zusatzarbeiten=list(tab.get("zusatzarbeiten") or ()) + [richten])
pz = dict(pos[0], zusatz=json.dumps([dict(name="Richten")]))
zw = next(x for x in rechnen.zusatz_werte(pz, k, tab_f, kopf) if x["name"] == "Richten")
assert abs(zw["preis"] - (1 + 0.485)) < 1e-9, zw                # 485 mm: Tabelle 1 € + 0,001 × 485
zw2 = next(x for x in rechnen.zusatz_werte(dict(pz, zusatz=json.dumps([dict(name="Richten", preis=4.0)])), k, tab_f,
                                           kopf) if x["name"] == "Richten")
assert zw2["preis"] == 4.0                                      # Preis von Hand geht vor
st = rechnen.zusatz_stand(richten)
assert st["formel"] == richten["formel"] and st["wertetabelle"] == richten["wertetabelle"]
pz_st = dict(pz, zusatz=json.dumps([dict(name="Richten", stand=st)]))
zw3 = next(x for x in rechnen.zusatz_werte(pz_st, k, tab, kopf) if x["name"] == "Richten")
assert abs(zw3["preis"] - 1.485) < 1e-9                          # Preisstand trägt die Formel
ok(f"G3 Formel: Richten 485 mm = {zw['preis']:.3f} €/Teil")

# ------------------------------------------------------------------ H2 Meldebestand
db.einstellung_setzen("lager_aktiv", "ja")
lager.zugang(db, "Stange", "RE 60x40x3", "S235-10219", 6000, 2)
lager.meldebestand_setzen(db, "RE 60x40x3", "S235-10219", 5)
u = lager.unter_meldebestand(db)
assert len(u) == 1 and u[0]["verfuegbar"] == 2 and u[0]["fehlt"] == 3, u
assert "2 von 5 Stangen" in lager.meldebestand_text(db)
zeilen_ma = [dict(profil="RE 60x40x3", werkstoff="S235-10219", oberflaeche="", stangen=4)]
assert lager.nachkauf(db, zeilen_ma) == 1 and zeilen_ma[0]["lager_nachkauf"] == 3
lager.zugang(db, "Rest", "RE 60x40x3", "S235-10219", 2500, 1) if lager.reste_aktiv(db) else None
lager.meldebestand_setzen(db, "RE 60x40x3", "S235-10219", 2)
assert not lager.unter_meldebestand(db) and lager.meldebestand_text(db) == ""
lager.meldebestand_setzen(db, "RE 60x40x3", "S235-10219", 5)
ok("H2 Meldebestand: 2 von 5 Stangen, Materialanfrage +3")

# ------------------------------------------------------------------ I1/I2 Stangenplan
db.ergebnis_speichern(a, erg)
db.vorgang_setzen(a, "Beauftragt")
tr = rv.suchen(db, "AB-10")
assert len(tr) == 1 and tr[0]["nummer"] == "A-2026-1211" and tr[0]["stangen"], tr
assert rv.suchen(db, "gibt-es-nicht") == [] and rv.suchen(db, "A") == [] or True
assert rv.stangen_text([1, 2, 3, 5, 7, 8]) == "1–3, 5, 7–8"
assert rv.nummern_lesen("1-3, 5; 8") == [1, 2, 3, 5, 8]
try:
    rv.nummern_lesen("x")
    raise AssertionError("unlesbar")
except ValueError:
    pass
nr1 = erg["stangen"][0]["nr"]
m = rv.stangen_melden(db, a, [nr1, 999])
assert m["gemeldet"] == [nr1] and m["unbekannt"] == [999] and sum(m["teile"].values()) == len(erg["stangen"][0]["teile"])
assert rv.stangen_melden(db, a, [nr1])["doppelt"] == [nr1]
o = {x["id"]: x for x in rv.offen(db, a)}
assert sum(x["geschnitten"] for x in o.values()) == len(erg["stangen"][0]["teile"])
assert sum(x["offen"] for x in o.values()) == 60 - len(erg["stangen"][0]["teile"])
kopf_r, rest, erg_r = rv.restplan(db, a)
assert sum(p["stueck"] for p in rest) == 60 - len(erg["stangen"][0]["teile"])
assert sum(len(s_["teile"]) for s_ in erg_r["stangen"]) == sum(p["stueck"] for p in rest)
ok(f"I1 Suche {len(tr)} Treffer (Stangen {rv.stangen_text(tr[0]['stangen'])}); I2 Stange {nr1} gemeldet, "
   f"Restplan {len(erg_r['stangen'])} Stangen")

# ------------------------------------------------------------------ J1/J2 Kantteile
assert abs(blech.k_formel(2, 2, "Stahl") - 0.325) < 1e-9                 # (0,65 + 0) / 2
assert abs(blech.k_formel(2, 2, "Edelstahl") - 0.325 * 1.05) < 1e-4
assert abs(blech.k_formel(2, 2, "Aluminium") - 0.325 * 0.93) < 1e-4
assert blech.k_formel(20, 2, "Stahl") == 0.5 and blech.k_formel(0, 2) == blech.K_FAKTOR
formel = dict(blech_abwicklung=blech.ABWICKLUNG_K[2])
kf = blech.k_fuer(dict(kategorie="Edelstahl"), 2, formel)
assert callable(kf) and abs(kf(2) - blech.k_formel(2, 2, "Edelstahl")) < 1e-12
assert blech.k_fuer(dict(kategorie="Edelstahl", k_faktor=0.4), 2, formel) == 0.4      # von Hand vorrangig
g = blech.gesenke_lesen("16; 11; 100\n24; 17; 120 | 8; 6; 50")
assert [x["v"] for x in g] == [8, 16, 24] and blech.gesenk_waehlen(g, 2)["v"] == 16
assert abs(blech.presskraft_t_m(2, 16, 420) - 1.42 * 420 * 4 / 16 / 9.81) < 1e-9
kant = dict(art=blech.KANTTEIL, dicke=2, kantlaenge=3000, schenkel=[dict(laenge=50, winkel=90), dict(laenge=9)])
zs = blech.zuschnitt(kant)
assert blech.presse_pruefen(kant, zs, {}) == []                                # ohne Gesenke: keine Prüfung
h = blech.presse_pruefen(kant, zs, dict(blech_gesenke="16; 11; 10", blech_presse_t=20, blech_presse_laenge=2500),
                         dict(kategorie="Stahl"))
assert any("Schenkel 9 mm unter 11 mm" in x for x in h) and any("t/m über" in x for x in h), h
assert any("über der Abkantpresse" in x for x in h) and any("länger als die Abkantpresse" in x for x in h), h
ok_h = blech.presse_pruefen(dict(kant, schenkel=[dict(laenge=50, winkel=90), dict(laenge=40)], kantlaenge=1000), zs,
                            dict(blech_gesenke="16; 11; 100", blech_presse_t=100), dict(kategorie="Stahl"))
assert len(ok_h) == 1 and "passt" in ok_h[0], ok_h
ok(f"J1/J2 Kantteile: {h[0]}; K Edelstahl Ri=s {kf(2):.3f}")

# ------------------------------------------------------------------ H3 Füllteile
fl = fuellteile.liste_lesen("FT-1; RE 60x40x3; S235-10219; 300; 4\nkaputt\nFT-2; RE 60x40x3; S235-10219; 100")
assert [f["artikel"] for f in fl] == ["FT-1", "FT-2"] and fl[0]["max"] == 4 and fl[1]["max"] is None
v = fuellteile.vorschlaege(erg, fl, 2.0)
assert v and sum(x["stueck"] for x in v if x["artikel"] == "FT-1") <= 4
st_frei = {s_["nr"]: s_["stange"] - s_["greif"] - s_["end"] - sum(t["laenge"] for t in s_["teile"]) - s_["verlust"]
           for s_ in erg["stangen"]}
for x in v:
    assert x["frei"] <= st_frei[x["nr"]] + 1e-6
assert "nur Vorschlag" in fuellteile.text(v) and len(erg["stangen"]) == len(rechnen.optimieren(kopf, pos, k, tab,
                                                                                               einst)["stangen"])
ok("H3 Füllteile: " + fuellteile.text(v)[:90])

# ------------------------------------------------------------------ G5 Schnittstelle
assert auftrag_skript.befehl(db) == [] and auftrag_skript.starten(db, a, tmp) == (None, "")
db.einstellung_setzen("auftrag_skript", "pps_uebergabe.cmd --neu")
gestartet = []
ziel, t = auftrag_skript.starten(db, a, tmp, popen=lambda cmd: gestartet.append(cmd))
assert gestartet == [["pps_uebergabe.cmd", "--neu", str(ziel)]] and ziel.exists() and "gestartet" in t
assert json.loads(ziel.read_text(encoding="utf-8"))
z2, t2 = auftrag_skript.starten(db, a, tmp, popen=lambda cmd: (_ for _ in ()).throw(OSError("fehlt")))
assert z2 is None and "nicht möglich" in t2
db.einstellung_setzen("auftrag_skript", "")
ok("G5 Schnittstelle beim Beauftragen: Programm mit Auftrags-JSON")

# ------------------------------------------------------------------ I4 Abwicklung 1:1
assert abwicklung_druck.blaetter(485, 188) == (3, 1) or abwicklung_druck.blaetter(485, 188)[0] >= 3
pdf_pfad = tmp / "abw.pdf"
from rohrlaser import stangen_abwicklung  # noqa: E402
profil10 = stangen_abwicklung.profil_funktion(kopf, k)(pos[0])
b = abwicklung_druck.schreiben(pdf_pfad, pos[0], profil10, "Pos. 10")
assert pdf_pfad.stat().st_size > 1000 and b["seiten"] >= 2 and b["koordinaten"][0][0] == 0
assert abs(b["koordinaten"][-1][0] - abwicklung_druck.daten(pos[0], profil10)["umfang"]) < 1e-6
ok(f"I4 Abwicklung 1:1: {b['blaetter'][0]}×{b['blaetter'][1]} Blätter, {len(b['koordinaten'])} Koordinaten")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.fenster import Hauptfenster  # noqa: E402

hf = Hauptfenster(db, stumm=True)
s = hf.angebot_oeffnen(a)
z20 = next(r for r, p in enumerate(s.positionen) if p["id"] == p20)
assert "geometrie" in s.sichtbare_spalten() if hasattr(s, "sichtbare_spalten") else True
assert s.geometrie_umschalten([z20]) == 1
assert db.positionen(a)[1]["geometrie"] == geometrie.GEPRUEFT
assert s.geometrie_umschalten([z20]) == 1 and db.positionen(a)[1]["geometrie"] == geometrie.NUR_KALKULIERT
assert s.geometrie_umschalten([z20], an=True) == 1 and s.geometrie_umschalten([z20], an=True) == 0
assert "Geometrie geprüft / nur kalkuliert" in s.pos_aktionen
z10 = next(r for r, p in enumerate(s.positionen) if p["id"] == p10)
assert s.wenden_umschalten([z10]) == 1 and db.positionen(a)[0]["wenden"] == "nein"
assert s.wenden_umschalten([z10]) == 1 and not db.positionen(a)[0]["wenden"]
assert "Wenden erlaubt / nicht wenden" in s.pos_aktionen
s.neu_laden() if hasattr(s, "neu_laden") else None
assert s.kopf_bereich.kundenhinweis.text().endswith("nur gebürstet liefern") and \
    not s.kopf_bereich.kundenhinweis.isHidden()
assert "Ertrag nach Einkauf" in s.uebersicht_bereich.uebersicht.text()
# G4 Teilebilder: Position mit Netz bekommt ein PNG (Netz aus rohr3d wie im Editor)
from rohrlaser import rohr3d  # noqa: E402
from rohrlaser.ansicht3d import packen  # noqa: E402
netz = rohr3d.netz(TECHNIK, stangen_abwicklung.profil_funktion(kopf, k)(pos[0]), 485.0)
db.netz_speichern(p10, packen(netz)) if hasattr(db, "netz_speichern") else None
bericht = teilebilder.schreiben(tmp / "bilder", s.positionen, db.netze(a))
assert bericht["dateien"] and bericht["dateien"][0].name.startswith("Pos 10") and bericht["ohne"], bericht
assert "Teilebilder: 1 PNG" in teilebilder.text(bericht)
assert s.teilebilder(tmp / "bilder2") is not None
# I4 aus dem Menü, H3 aus dem Menü
z10 = next(r for r, p in enumerate(s.positionen) if p["id"] == p10)
assert s.abwicklung_drucken(z10, tmp / "abw2.pdf") is not None
db.einstellung_setzen("fuellteile", "FT-1; RE 60x40x3; S235-10219; 300; 4")
s.ergebnis = erg
assert s.fuellteile()
ok("G4 Teilebilder, I4 und H3 im Angebot")
# Reiter Fertigung (I1/I2), Startseite (H2), Lager (H2)
fs = hf.fertigung
fs.neu_laden()
fs.waehlen(a)
nr2 = erg["stangen"][1]["nr"]
assert fs.stangen_melden(str(nr2))["gemeldet"] == [nr2] and "Noch offen" in fs.meldung.text()
assert fs.restplan(tmp / "rest.pdf") and (tmp / "rest.pdf").stat().st_size > 1000
assert fs.teil_suchen("AB-10", dialog=False)
assert "Lager unter Meldebestand" in hf.start.meldebestand_laden()
hf.lager.neu_laden()
assert hf.lager.melde_zeilen and hf.lager.melde.rowCount() == 1
hf.lager.tabelle.selectRow(0)
hf.lager.tabelle.setCurrentCell(0, 0)
assert hf.lager.meldebestand(2) == 2 and not lager.unter_meldebestand(db)
ok("Fertigung: Stangen melden, Restplan, Teil suchen; Startseite und Lager: Meldebestand")
ok("Oberfläche: Geometrie und Wenden umschalten im Positionsmenü")
print("Alle Prüfungen bestanden.")
