"""Bohrungsart nachträglich ändern (Patrick 03.11.2026, „Option Bohrungen zu ändern z. B. Gewinde in Flowdrill oder
umgekehrt, mehrere Optionen vorschlagen“; Freigabe „alle Empfehlungen“):
- Rechenkern bohrbild: Ausführung je Zeile (Gewinde schneiden, Flowdrill, Einnietmutter, Senkung, Bohren, nur
  lasern), Ø am Laser nach Gewindegröße, Schneidweg/Einstiche/Gravur, Zusatzarbeiten, Gewinde, „weicht von STEP ab“
- Vorschläge ★ nach Gewindegröße, Wandstärke, Werkstoff und Grenzen aus den Einstellungen
- Dialog „Bohrungen prüfen“ (eine Position, mehrere Positionen = ganzes Angebot): Auswahl, „Alle M8 → …“,
  „★ Vorschläge übernehmen“, Übernehmen ins Angebot
- Editoren: Eigenschaft Ausführung (Rohr: über das Bohrbild, Blech: im Richtpreis)

Aufruf: python tests/test_bohrungsart.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import bohrbild as bb, rechnen, schneidweg as sw  # noqa: E402

PI = math.pi
GEW = [("M6", 5.0), ("M8", 6.8), ("M10", 8.5)]


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return abs(float(a) - float(b)) <= tol


# ------------------------------------------------------------------ 1 Rechenkern
m8 = dict(art="Bohrung", d=6.8, anzahl=4, gewinde="M8", status="offen")
v = bb.vorschlaege(m8, 2.0, "S235-10219", GEW)
assert v[0]["aus"] == bb.FLOWDRILL and v[0]["rang"] == 0, v               # 2 mm Wand: 1,6 Gänge M8 zu wenig
assert next(x for x in v if x["aus"] == bb.GEWINDE_SCHNEIDEN)["rang"] == 2
assert "1,6 Gänge" in next(x for x in v if x["aus"] == bb.GEWINDE_SCHNEIDEN)["grund"]
assert next(x for x in v if x["aus"] == bb.EINNIET)["rang"] == 1
assert bb.vorschlag_bester(m8, 5.0, "S235", GEW)["aus"] == bb.GEWINDE_SCHNEIDEN          # 4 Gänge: Gewinde
assert bb.vorschlag_bester(m8, 5.0, "AlMg3", GEW)["aus"] == bb.EINNIET     # Alu: 4 < 4,5 Gänge, Flowdrill zu dick
assert bb.vorschlag_bester(m8, 7.0, "S235", GEW)["aus"] == bb.GEWINDE_SCHNEIDEN
v7 = {x["aus"]: x for x in bb.vorschlaege(m8, 7.0, "S235", GEW)}
assert v7[bb.FLOWDRILL]["rang"] == 2 and "zu dick" in v7[bb.FLOWDRILL]["grund"]
assert v7[bb.EINNIET]["rang"] == 2 and "passt nicht" in v7[bb.EINNIET]["grund"]
# Grenzen aus den Einstellungen: ab 1 Gang gilt Gewinde schneiden auch bei 2 mm Wand
g = bb.grenzen_aus({"bohr_gewinde_gaenge": 1.0, "bohr_flowdrill_min": None})
assert g["bohr_gewinde_gaenge"] == 1.0 and g["bohr_flowdrill_min"] == bb.GRENZEN["bohr_flowdrill_min"]
assert bb.vorschlag_bester(m8, 2.0, None, GEW, g)["aus"] == bb.GEWINDE_SCHNEIDEN
# Flowdrill (STEP) ist ★, solange er passt; ohne Gewindegröße nur lasern / Bohren
fl = dict(art="Fließloch", d=7.3, anzahl=2, gewinde="M8", status="offen", laser=bb.GRAVUR)
assert bb.vorschlag_bester(fl, 2.0, None, GEW)["aus"] == bb.FLOWDRILL
klein = dict(art="Bohren", d=2.0, anzahl=2, status="offen", laser=bb.GRAVUR)
vk = {x["aus"]: x for x in bb.vorschlaege(klein, 4.0, None, GEW)}
assert vk[bb.AUFBOHREN]["rang"] == 0 and vk[bb.NUR_LASER]["rang"] == 2 and vk[bb.EINNIET]["rang"] == 2
ok("Vorschläge ★: Gewinde bei genug Gängen, sonst Flowdrill/Einnietmutter; Alu mehr Gänge; Grenzen einstellbar")

# Gewinde -> Flowdrill: gemessenes Kernloch fällt weg, Laser markiert (Gravur), Zusatzarbeit Flowdrill, Gewinde bleibt
f = bb.ausfuehrung_setzen(dict(m8, status="bestätigt"), bb.FLOWDRILL, GEW)
zu = bb.zusatz([f])
assert nah(zu["schneidweg"], -4 * PI * 6.8) and zu["einstiche"] == -4 and nah(zu["gravur"], 4 * PI * 0.5)
assert bb.arbeiten([f]) == {"Flowdrill": 4} and bb.gewinde_text([f]) == "4xM8"
assert bb.abweichend(f) and "weicht von STEP ab" in bb.text([f])
# Gewinde -> Einnietmutter: Laser schneidet Ø11 statt 6,8, kein Gewinde, Zusatzarbeit Einnietmuttern mit Größe
e = bb.ausfuehrung_setzen(dict(m8, status="bestätigt"), bb.EINNIET, GEW)
assert e["d_laser"] == 11.0 and bb.gewinde_text([e]) is None and bb.vorschlag_text([e]) is None
zu = bb.zusatz([e])
assert nah(zu["schneidweg"], 4 * PI * (11 - 6.8)) and zu["einstiche"] == 0 and len(zu["konturen"]) == 4
assert bb.arbeiten([e]) == {"Einnietmuttern setzen": 4} and bb.arbeit_groessen([e]) == {"Einnietmuttern setzen": "4× M8"}
# Flowdrill -> Gewinde schneiden: Kernloch Ø6,8 aus den Stammdaten wird geschnitten
gs = bb.ausfuehrung_setzen(dict(fl, status="bestätigt"), bb.GEWINDE_SCHNEIDEN, GEW)
assert gs["d_laser"] == 6.8 and bb.gewinde_text([gs]) == "2xM8" and bb.arbeiten([gs]) == {}
zu = bb.zusatz([gs])
assert nah(zu["schneidweg"], 2 * PI * 6.8) and zu["einstiche"] == 2 and zu["gravur"] == 0
# Senkung aus einer Gewindebohrung: Durchgang Ø9, Senk-Ø 16,4, Zusatzarbeit Senken
sk = bb.ausfuehrung_setzen(dict(m8, status="bestätigt"), bb.SENKEN, GEW)
assert sk["d_laser"] == 9.0 and sk["D"] == 16.4 and bb.arbeiten([sk]) == {"Senken": 4}
# abgelehnt = nur lasern wie gemessen; Zeilen ohne Ausführung rechnen wie bisher
assert bb.zusatz([dict(e, status="abgelehnt")])["schneidweg"] == 0 and not bb.abweichend(dict(e, status="abgelehnt"))
alt = dict(art="Bohren", d=2.0, anzahl=2, status="bestätigt", laser=bb.LOCH)
assert bb.ausfuehrung(alt) == bb.AUFBOHREN and bb.arbeiten([alt]) == {"Bohren": 2}
assert bb.zusatz([alt])["einstiche"] == 0 and nah(bb.zusatz([alt])["schneidweg"], 2 * PI * (0.5 - 2))
ok("Ausführung: Gewinde↔Flowdrill, Einnietmutter Ø11, Senkung Ø9/16,4; Schneidweg, Einstiche, Zusatzarbeiten, Gewinde")

# anwenden: Spalte Bohrungen mit Hinweis, Zusatzarbeit mit Größen im Angebotstext
p = dict(schneidweg=500.0, innen=100.0, einstiche=8, bohrungen="4xØ6,8", gewinde_vorschlag="4xM8",
         bohrbild=bb.schreiben([m8]))
kat = [dict(name="Einnietmuttern setzen", art="€/Stück", preis=0.6), dict(name="Flowdrill", art="€/Stück", preis=0.6)]
felder = bb.anwenden(p, [e], "", kat)
assert nah(felder["schneidweg"], 500 + 4 * PI * 4.2, 0.1) and felder["gewinde"] is None, felder
assert "Einnietmutter M8 Ø11 statt Gewinde (weicht von STEP ab)" in felder["bohrungen"], felder["bohrungen"]
assert '"text": "4× M8"' in felder["zusatz"] and "Einnietmuttern setzen" in felder["zusatz"], felder["zusatz"]
assert "Weicht von STEP ab" in bb.step_hinweis([e])
ok("Übernehmen: Schneidweg, Gewinde, Spalte Bohrungen „weicht von STEP ab“, Zusatzarbeit „4× M8“")

# Schneidweg-Rechner/Editoren: Eigenschaft aus der Konturzeile -> Bohrbild-Zeile mit Ausführung
erg = dict(schritte=[{}, {}, dict(art="Bohrung", anzahl=4, eingabe=dict(art="Bohrung", d=6.8, aus=bb.EINNIET)),
                     dict(art="Senkung", anzahl=2, eingabe=dict(art="Senkung", d=6.6, D=12.4, aus=bb.EINNIET,
                                                                 groesse="M6"))])
bild = bb.aus_rechner(erg, [], GEW, 3.0)
assert [(z["art"], z.get("aus"), z.get("gewinde"), z.get("d_laser")) for z in bild] == [
    ("Bohrung", bb.EINNIET, "M8", 11.0), ("Senkung", bb.EINNIET, "M6", 9.0)], bild
assert bb.arbeiten(bild) == {"Einnietmuttern setzen": 6}
ok("Schneidweg-Rechner: Ausführung aus der Eigenschaft der Konturzeile (alle Editoren)")

# Blech: Ausführung im Richtpreis (Gewinde, Nacharbeit), Flowdrill nur markiert
from rohrlaser import blech  # noqa: E402

wst = {"S235": dict(blech_werkstoff_id="S235", kategorie="Stahl", dichte=7.85, preis_kg=1.2)}
laser = [dict(kategorie="Stahl", dicke_bis=3, vorschub=4000, vorschub_innen=2000, einstechzeit=0.5, gas="O₂",
              vorschub_gravur=8000)]
e0 = dict(art=blech.ZUSCHNITT, dicke=2, werkstoff="S235", laenge=200, breite=100, stueck=10,
          konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=6.8, x=50, y=50)])
einst = dict(gewinde_preise={"M8": 0.9}, bohr_preise={"Flowdrill": 0.6, "Einnietmuttern setzen": 0.5})
r0 = blech.rechnen(e0, wst, laser, einst)
assert not r0["fehler"] and "Gewinde" not in r0["kosten"], r0
e1 = dict(e0, konturen=[dict(e0["konturen"][0], aus=bb.FLOWDRILL)])
r1 = blech.rechnen(e1, wst, laser, einst)
assert nah(r1["kosten"]["Gewinde"], 4 * 0.9) and nah(r1["kosten"]["Nacharbeit"], 4 * 0.6), r1["kosten"]
assert nah(r0["schneidweg"] - r1["schneidweg"], 4 * PI * 6.8, 0.01) and r1["einstiche"] == r0["einstiche"] - 4
assert r1["richtpreis"] > r0["richtpreis"] and nah(r1["gravur"], 4 * PI * 0.5)
e2 = dict(e0, konturen=[dict(e0["konturen"][0], aus=bb.EINNIET, groesse="M8")])
r2 = blech.rechnen(e2, wst, laser, einst)
assert "Gewinde" not in r2["kosten"] and nah(r2["kosten"]["Nacharbeit"], 2.0)
assert nah(r2["schneidweg"] - r0["schneidweg"], 4 * PI * (11 - 6.8), 0.01)
ok("Blech: Ausführung im Richtpreis (Gewinde, Nacharbeit), Flowdrill markiert, Einnietmutter Ø11")

# ------------------------------------------------------------------ 2 Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.bohrbild_dialog import BohrbildDialog, BohrbildSammelDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert db.einstellung("bohr_gewinde_gaenge") == 3.0 and db.einstellung("bohr_flowdrill_faktor") == 0.5
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Test"))
for pos, art in ((10, "Halter"), (20, "Lasche")):
    db.position_neu(a, dict(pos=pos, artikel=art, profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                            stueck=10, schneidweg=600, einstiche=9, innen=4 * PI * 6.8, konturen="4x6,8",
                            bohrungen="4xØ6,8", gewinde_vorschlag="4xM8",
                            bohrbild=bb.schreiben([dict(m8, status="offen")])))
seite = fenster.angebot_oeffnen(a)
wand = rechnen.wand_position(seite.positionen[0], seite.k)
assert wand == 2
tab = [(g["gewinde"], g["kernloch"]) for g in seite.tabellen["gewinde"]]
d = BohrbildDialog(None, seite.positionen[0], tab, wand, None, seite.tabellen["zusatzarbeiten"],
                   rechnen.stundensaetze(seite.tabellen), {g["gewinde"]: g.get("preis") for g in seite.tabellen["gewinde"]},
                   grenzen=bb.grenzen_aus(db.einstellung))
au = d.ausfuehrung[0]
assert au.currentData() == bb.GEWINDE_SCHNEIDEN and au.itemText(0).startswith("★ " + bb.FLOWDRILL), au.itemText(0)
assert "(nicht empfohlen)" in au.itemText(au.currentIndex())
vt = d.zeilen[0].vorschlag.text()
assert "★ Flowdrill" in vt and "nicht empfohlen" in vt, vt
d.setzen(0, ausfuehrung=bb.FLOWDRILL)
assert d.zeilen[0].status() == "bestätigt"                  # selbst gewählt = bestätigt
assert d.laser[0].isEnabled() and d.laser[0].currentText() == bb.GRAVUR
t = d.auswirkung.text()
assert "4× Flowdrill" in t and "Einstiche 9 → 5" in t and "Weicht von STEP ab" in t, t
assert d.umstellen.umstellen("M8", bb.EINNIET) == 1 and d.zeilen[0].ausfuehrung() == bb.EINNIET
assert d.laser[0].currentText() == "schneidet Ø11" and not d.laser[0].isEnabled()
assert "4× Einnietmuttern setzen" in d.auswirkung.text()
d.umstellen.vorschlaege()
assert d.zeilen[0].ausfuehrung() == bb.FLOWDRILL
d.accept()
assert seite.bohrungen_pruefen([0], werte=d.ergebnis)
p0 = db.positionen(a)[0]
assert p0["gewinde"] == "4xM8" and p0["einstiche"] == 5 and "Flowdrill" in p0["zusatz"], p0
assert "weicht von STEP ab" in p0["bohrungen"], p0["bohrungen"]
assert rechnen.bohrbild_offen(p0) is False
ok("Dialog: Ausführung mit ★, Vorschlag mit Grund, selbst gewählt = bestätigt, Alle M8 → …, ★ übernehmen, Übernehmen")

# Ganzes Angebot: Fenster für mehrere Positionen, alle M8 -> Einnietmutter
s = BohrbildSammelDialog(None, [(r, seite.positionen[r], wand) for r in (0, 1)], tab, None,
                         bb.grenzen_aus(db.einstellung))
assert s.umstellen.umstellen("M8", bb.EINNIET) == 2
assert "weichen von STEP ab" in s.info.text() and s.info.text().startswith("Alle Zeilen geprüft."), s.info.text()
s.accept()
assert seite.bohrungen_alle_pruefen([0, 1], werte=s.ergebnis)
for p_ in db.positionen(a):
    assert p_["gewinde"] is None and "Einnietmuttern setzen" in (p_["zusatz"] or ""), p_
    assert nah(p_["schneidweg"], 600 + 4 * PI * (11 - 6.8), 0.2), p_["schneidweg"]
ok("Ganzes Angebot: Bohrungen prüfen für mehrere Positionen, Alle M8 → Einnietmutter")

# ------------------------------------------------------------------ 3 Editoren: Eigenschaft Ausführung
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

k = db.kontext()
pr = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500, stueck=10,
          technik=sw.speichern(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=6.8, x=100)])))
sd = SchneidwegDialog(None, pr, k.profile["RR 42,4x2,0"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = sd.editor
ed.waehlen("kontur:0")
ei = ed.eigenschaften
f = ei.felder["Ausführung"]
assert f.itemText(1).startswith("★ " + bb.FLOWDRILL) and "★ Flowdrill" in ei.felder["Vorschlag"].text()
f.setCurrentIndex(f.findData(bb.FLOWDRILL))
f.activated.emit(f.currentIndex())
assert sd.eingaben()["konturen"][0]["aus"] == bb.FLOWDRILL
sd2 = SchneidwegDialog(None, dict(pr, technik=sw.speichern(sd.eingaben())), k.profile["RR 42,4x2,0"],
                       dict(maschine="T11", stange=6000), k, db.tabellen(), db)
assert sd2.eingaben()["konturen"][0]["aus"] == bb.FLOWDRILL           # bleibt beim erneuten Öffnen
db.position_neu(a, dict(pos=30, artikel="Editor", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500,
                        stueck=10))
seite.neu_laden()
assert seite.schneidweg_berechnen(2, eingaben=sd.eingaben(), ueberschreiben=True)
p2 = db.positionen(a)[2]
assert p2["gewinde"] == "4xM8" and "Flowdrill" in p2["zusatz"], p2
assert any(z.get("aus") == bb.FLOWDRILL for z in bb.lesen(p2["bohrbild"]))
ok("Rohr-Editor: Eigenschaft Ausführung mit ★, bleibt gespeichert, Position rechnet Flowdrill")

bd = BlechDialog(None, db)
be = bd.editor
be.kontur_einfuegen(sw.BOHRUNG)
r = bd.tabelle.rowCount() - 1
be.eigenschaften.felder["Ø d"].setText("6,8")
be.eigenschaften.felder["Ø d"].uebernehmen()
be.waehlen(f"kontur:{r}")
f = be.eigenschaften.felder["Ausführung"]
f.setCurrentIndex(f.findData(bb.EINNIET))
f.activated.emit(f.currentIndex())
assert "Gewindegröße" in be.eigenschaften.felder
g = be.eigenschaften.felder["Gewindegröße"]
g.setCurrentIndex(g.findData("M8"))
g.activated.emit(g.currentIndex())
z = bd.eingaben()["konturen"][r]
assert z["aus"] == bb.EINNIET and z["groesse"] == "M8", z
ok("Blech-Editor: Eigenschaft Ausführung und Gewindegröße")

seite.close()
db.con.close()
print("Alle Tests bestanden.")
