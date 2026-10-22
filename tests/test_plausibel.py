"""Prüft, dass Eingaben, bei denen Angebot und Kalkulation auseinanderlaufen könnten, sichtbar werden (Prüfbericht
22.10.2026, B-1, B-2, B-3, B-7, B-9): Satz mit ungleicher Anzahl Sätze, nicht erkannte Gewinde, negative Werte, Text in
Zahlenfeldern, Rüsten ohne Rohrlaserteile, Hinweis zu Staffelpreisen im Angebots-PDF.

Aufruf: python tests/test_plausibel.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import ausgabe, pdf, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)


def P(pos, **x):
    return dict(dict(pos=pos, artikel=f"T{pos}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                     stueck=10, schneidweg=320, einstiche=2), **x)


def angebot(positionen):
    a = db.angebot_neu(dict(kunde="Test", kundennr="1"))
    for p in positionen:
        db.position_neu(a, p)
    s = fenster.angebot_oeffnen(a)
    assert s.optimieren()
    return a, s


def kalk(s):
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)


# ------------------------------------------------------------------ P1 Satz mit ungleicher Anzahl Sätze
a, s = angebot([P(10, laenge=800, stueck=10, satz="A", je_satz=1), P(20, laenge=900, stueck=6, satz="A", je_satz=1)])
assert all(st.startswith("WARNUNG: Satz A: unterschiedliche Anzahl Sätze") for st in s.pos_modell.status), \
    s.pos_modell.status
zeilen, _ = kalk(s)
assert all("unterschiedliche Anzahl Sätze" in z["hinweis"] for z in zeilen)
ang = ausgabe.angebot(s.kopf, s.positionen, zeilen, s.k, s.einst)
assert ang["hinweise"] == 2, ang["hinweise"]
for p, n in zip(s.positionen, (10, 10)):
    db.position_aendern(p["id"], "stueck", n)
s.neu_laden()
assert s.optimieren()
assert all(st == "OK" for st in s.pos_modell.status), s.pos_modell.status
ok("P1 Satz A mit 10 und 6 Sätzen: WARNUNG im Status und Hinweis in der Kalkulation (Rückfrage vor dem PDF); "
   "gleiche Anzahl: OK")

# ------------------------------------------------------------------ P2 Gewinde lesen
tab = s.tabellen["gewinde"]
for text, soll, fehlt in (("4xM6", {"M6": 4}, []), ("4 x M6", {"M6": 4}, []), ("4×M6", {"M6": 4}, []),
                          ("4xM6, 2xM8", {"M6": 4, "M8": 2}, []), ("4xM6;2xM8", {"M6": 4, "M8": 2}, []),
                          ("4xm6; 2XM8;", {"M6": 4, "M8": 2}, []), ("4,0xM6", {}, ["4,0xM6"]),
                          ("M6", {}, ["M6"]), ("4xM7", {}, ["4xM7"]), ("4xM6; 2xM99", {"M6": 4}, ["2xM99"])):
    n, f = rechnen.gewinde_lesen(text, tab)
    assert n == soll and f == fehlt, (text, n, f)
a, s = angebot([P(10, gewinde="4xM6, 2xM8")])
z = kalk(s)[0][0]
assert abs(z["gewinde_preis"] - (4 * 0.90 + 2 * 1.10)) < 1e-9 and s.pos_modell.status[0] == "OK"
db.position_aendern(s.positionen[0]["id"], "gewinde", "4xM7")
s.neu_laden()
assert s.pos_modell.status[0].startswith("WARNUNG: Gewinde '4xM7' nicht erkannt"), s.pos_modell.status[0]
assert "nicht erkannt" in kalk(s)[0][0]["hinweis"]
ok("P2 Gewinde: Komma, ×, Kleinschreibung erkannt (4xM6, 2xM8 = 5,80 €/Teil); 4,0xM6, M6, 4xM7 = WARNUNG statt 0 €")

# ------------------------------------------------------------------ P3 negative Werte und Text in Zahlenfeldern
a, s = angebot([P(10)])
pid = s.positionen[0]["id"]
for feld, titel in (("schneidweg", "Schneidweg"), ("zeit_manuell", "Schneidzeit"), ("einstiche", "Einstiche")):
    db.position_aendern(pid, feld, -5)
    s.neu_laden()
    assert s.pos_modell.status[0].startswith("FEHLER: " + titel) and "negativ" in s.pos_modell.status[0], \
        s.pos_modell.status[0]
    db.position_aendern(pid, feld, None)
try:
    db.position_aendern(pid, "laenge", "abc")
    raise AssertionError("Text in der Länge angenommen")
except ValueError as e:
    assert "Zahl" in str(e)
with db.con:                               # wie eine geänderte oder fremde Datei
    db.con.execute("UPDATE positionen SET laenge='abc' WHERE id=?", (pid,))
s.neu_laden()
assert s.positionen[0]["laenge"] is None and s.pos_modell.status[0] == "FEHLER: Teilelänge fehlt"
kalk(s)                                    # bricht nicht ab
ok("P3 negative Werte = FEHLER; Text in Zahlenfeldern abgelehnt bzw. aus der Datei als leer gelesen, Rechnung "
   "bricht nicht ab")

# ------------------------------------------------------------------ P4 Rüsten nur mit Rohrlaserteilen
a, s = angebot([P(10, stueck=None)])
zeilen, summen = kalk(s)
arten = rechnen.kostenarten(summen, s.einst)
assert summen["ruesten_maschine"] == 0 and abs(sum(b for _, b, f in arten if not f) - summen["verkauf"]) < 1e-9
ok("P4 ohne Rohrlaserteile: kein Rüsten Maschine in der Übersicht, Summe der Kostenarten = Verkaufspreis")

# ------------------------------------------------------------------ P5 Hinweis zu Staffelpreisen im PDF
ang = dict(zeilen=[dict(art="teil", pos=10, artikel="A", text="Rohr", menge=24, preis=6.72, gesamt=161.28,
                        staffeln=[dict(menge=24, preis=11.11)]),
                   dict(art="teil", pos=20, artikel="B", text="Rohr", menge=5, preis=3.0, gesamt=15.0, staffeln=[])],
           staffeln=[])
texte = [getattr(x, "text", "") for zeile in pdf._angebot_positionen(ang)._cellvalues for x in zeile]
assert texte.count(pdf.STAFFEL_HINWEIS) == 1, texte
ok("P5 Angebots-PDF: unter den Staffelpreisen 'Staffelpreise bei Einzelbestellung dieser Position' (einmal je "
   "Position mit Staffeln)")
# ------------------------------------------------------------------ P6 Prüfen vor Freigabe
a = db.angebot_neu(dict(kunde=""))
db.position_neu(a, P(10, gewinde_vorschlag="4xM6"))
db.position_neu(a, P(20, schneidweg=-1))
s = fenster.angebot_oeffnen(a)
texte = [t for _, t in s.freigabe_punkte()]
for teil in ("kein Kunde", "Schnittplan nicht aktuell", "1 Position mit FEHLER", "Gewinde-Vorschlag ungeprüft"):
    assert any(teil in t for t in texte), (teil, texte)
assert "4 offene Punkte" in s.uebersicht_bereich.freigabe_bereich.knopf.text(), s.uebersicht_bereich.freigabe_bereich.knopf.text()
db.angebot_aendern(a, "kunde", "Test")
for p in db.positionen(a):
    db.position_aendern(p["id"], "schneidweg", 320)
    db.position_aendern(p["id"], "gewinde", "4xM6")
s.neu_laden()
assert s.optimieren()
assert not [t for a_, t in s.freigabe_punkte() if a_ != "HINWEIS"], s.freigabe_punkte()
assert "alles erledigt" in s.uebersicht_bereich.freigabe_bereich.knopf.text()
ok("P6 Prüfen vor Freigabe: Kunde, Schnittplan, FEHLER, Gewinde-Vorschlag als Liste in der Übersicht")
# ------------------------------------------------------------------ P7 ein Bearbeitungsdialog
from rohrlaser.zusatz_dialog import ZusatzDialog  # noqa: E402
geoeffnet = []
d = ZusatzDialog(fenster, s.positionen[0], 1, s.k, s.tabellen, weitere={
    "Schweißnaht …": lambda: geoeffnet.append("naht"), "Bohrungen prüfen …": lambda: geoeffnet.append("bohr")})
d.gewinde.setText("")
d.gewinde_anzahl.setValue(4)
d.gewinde_wahl.setCurrentText("M6")
d.gewinde_hinzufuegen()
d.gewinde_anzahl.setValue(2)
d.gewinde_wahl.setCurrentText("M8")
d.gewinde_hinzufuegen()
assert d.gewinde.text() == "4xM6; 2xM8" and "= 5,8 €" in d.gewinde_info.text(), (d.gewinde.text(), d.gewinde_info.text())
d.gewinde.setText("4xM7")
assert "Nicht erkannt: 4xM7" in d.gewinde_info.text()
d.weitere_knoepfe["Schweißnaht …"].click()
d.weitere_knoepfe["Bohrungen prüfen …"].click()
assert geoeffnet == ["naht", "bohr"]
ok("P7 Zusatzarbeiten-Dialog: Gewinde aus der Liste (4xM6; 2xM8 = 5,80 €), Unbekanntes rot, Schweißnaht und "
   "Bohrungen von dort erreichbar")
print("OK: Plausibilität (Prüfbericht B-1, B-2, B-3, B-7, B-9, C-2 Prüfen vor Freigabe)")
