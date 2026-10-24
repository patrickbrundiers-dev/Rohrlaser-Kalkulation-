"""Angebots-Check vor dem Versand (Plan A2, mit W7): jede Prüfregel meldet ihren Punkt mit Ziel, die Übersicht zeigt
die Punkte laufend mit „Hinspringen“, vor dem Angebots-PDF und vor „Verschickt“ kommt höchstens eine Sammelrückfrage,
FEHLER lässt sich nur mit Begründung übergehen (steht im Versandverlauf).

Aufruf: python tests/test_angebot_check.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_check as ac, angebot_check_dialog, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Prüfregeln (reine Funktion)
p = ac.Punkt(ac.WARNUNG, "x", "pos:0", "Pos. 10")
art, text = p
assert p == ("WARNUNG", "x") and (art, text, p.ziel, p.details) == ("WARNUNG", "x", "pos:0", "Pos. 10")
ok("Punkt vergleicht und entpackt wie das Paar (Art, Text), dazu Ziel und Details")

kopf = dict(kunde="Muster GmbH", kundennr="K1", kundenreferenz="Anfrage 7", lieferzeit_art="Arbeitstage",
            lieferzeit_wert=10)
pos = [dict(pos=10, stueck=5, profil_id="QR 40x40x3"), dict(pos=20, stueck=5, profil_id="QR 40x40x3"),
       dict(pos=30, stueck=1)]                          # Pos. 30 ohne Profil: nicht aktiv
summen = dict(verkauf=1000.0, gewinn=100.0)
alles_gut = ac.punkte(kopf, pos, ["OK", "OK", "OK"], "aktuell", summen, kalk_zeilen=[{}, {}, {}],
                      kunde=dict(email="a@b.de"), mindestmarge=0.05)
assert alles_gut == [], alles_gut
ok("vollständiges Angebot: keine Punkte")


def finde(liste, teil):
    return next((x for x in liste if teil in x.text), None)


liste = ac.punkte(dict(), pos, ["FEHLER: Profil fehlt", "WARNUNG: Gewinde M6 ohne Preis", ""], "veraltet",
                  dict(verkauf=1000.0, gewinn=20.0, fracht_fehler="PLZ fehlt", mindestpreis_gilt=True,
                       mindestpreis_anhebung=50.0, zukauf_fehlt=1),
                  staffeln_veraltet=2, kalk_zeilen=[{"hinweis": "keine Schneiddaten"}, {"zukauf_fehlt": 1}, {}],
                  kunde={}, preis_abweichung=["Profil QR 40: 3,10 statt 2,90 €/m"], mindestmarge=0.05, admin=True)
erwartet = {
    "1 Position mit FEHLER": (ac.FEHLER, "pos:0", "Pos. 10"),
    "1 Position mit WARNUNG": (ac.WARNUNG, "pos:1", "Pos. 20"),
    "kein Kunde": (ac.WARNUNG, "kopf:kunde", ""),
    "Schnittplan nicht aktuell": (ac.WARNUNG, "optimieren", ""),
    "Zukaufteil ohne Einkaufspreis": (ac.WARNUNG, "pos:1", "Pos. 20"),
    "Fracht: PLZ fehlt": (ac.WARNUNG, "fracht", None),
    "Marge 2 % unter der Mindestmarge 5 %": (ac.WARNUNG, "kalkulation", ""),
    "2 Staffelstufe(n) veraltet": (ac.HINWEIS, "staffeln", ""),
    "Mindestauftragswert greift": (ac.HINWEIS, "kopf:mindestpreis_anwenden", ""),
    "Stammdaten seit dem Festschreiben geändert (1 Wert)": (ac.HINWEIS, "preise", "Profil QR 40: 3,10 statt 2,90 €/m"),
    "Lieferzeit leer": (ac.HINWEIS, "kopf:lieferzeit", ""),
    "Kundenreferenz": (ac.HINWEIS, "kopf:kundenreferenz", ""),
}
for teil, (art, ziel, details) in erwartet.items():
    x = finde(liste, teil.replace("2 %", "2,0 %").replace("5 %", "5,0 %"))
    assert x is not None, (teil, [y.text for y in liste])
    assert (x.art, x.ziel) == (art, ziel), (teil, x.art, x.ziel)
    assert details is None or x.details == details, (teil, x.details)
assert finde(liste, "Hinweis in der Kalkulation") is None          # Pos. 10 hat schon FEHLER: nicht doppelt
assert finde(liste, "E-Mail") is None                               # ohne Kunde keine E-Mail-Prüfung
assert [x.art for x in liste] == sorted((x.art for x in liste), key=ac.ARTEN.index)
assert ac.blockiert(liste) and len(ac.offen(liste)) == 7
ohne_admin = ac.punkte(dict(kopf), pos[:1], ["OK"], "aktuell", dict(verkauf=1000.0, gewinn=20.0), mindestmarge=0.05)
assert [x.text for x in ohne_admin] == ["Marge unter der Mindestmarge (Einstellungen)"], ohne_admin
liste2 = ac.punkte(dict(kopf, kunde="X"), pos, ["OK", "OK", ""], "aktuell", dict(verkauf=1.0),
                   kalk_zeilen=[{"hinweis": "kein Schnittplan oder Preis"}, {}, {}], kunde=dict(email=""))
assert finde(liste2, "1 Position mit Hinweis in der Kalkulation, z. B. „kein Schnittplan oder Preis“").ziel == "pos:0"
assert finde(liste2, "Kunde ohne E-Mail").ziel == "kunde"
viele = [dict(pos=i * 10, stueck=1, profil_id="QR 40x40x3") for i in range(1, 10)]
x = ac.punkte(kopf, viele, ["FEHLER: x"] * 9, "aktuell", summen)[0]
assert x.details == "Pos. 10, 20, 30, 40, 50, 60 …" and x.text.startswith("9 Positionen mit FEHLER"), x.details
assert ac.versand_eintrag(liste, " weil eilig ") == dict(punkte=[f"{x.art}: {x.text}" for x in ac.offen(liste)],
                                                      begruendung="weil eilig")
assert ac.versand_eintrag(alles_gut, "x") is None
assert rechnen.freigabe_punkte(kopf, pos, ["OK"] * 3, "aktuell", summen) == []      # alte Schnittstelle
ok("Prüfregeln: FEHLER/WARNUNG je Position mit Positionen, Kunde, Schnittplan, Zukauf ohne EK, Fracht, Marge "
   "(Zahlen nur Admin), Staffeln, Mindestauftragswert, Stammdaten geändert, Kunde ohne E-Mail, Lieferzeit, "
   "Kundenreferenz; FEHLER zuerst")

# ------------------------------------------------------------------ Fenster
app = QApplication.instance() or QApplication([])
d = angebot_check_dialog.CheckDialog(None, liste, "Angebot erstellen")
assert d.weiter.text() == "Trotzdem weiter" and not d.weiter.isEnabled() and d.begruendung.isVisibleTo(d)
d.begruendung.setText("   ")
assert not d.weiter.isEnabled()
d.begruendung.setText("Kunde wartet, Profil kommt nach")
assert d.weiter.isEnabled() and d.text_begruendung() == "Kunde wartet, Profil kommt nach"
d.hin_knoepfe[0].click()
assert d.ziel == "pos:0" and d.result() == QDialog.Rejected
d = angebot_check_dialog.CheckDialog(None, [x for x in liste if x.art != ac.FEHLER], "Angebot erstellen")
assert d.weiter.text() == "Angebot erstellen" and d.weiter.isEnabled() and not d.begruendung.isVisibleTo(d)
d = angebot_check_dialog.CheckDialog(None, liste)
assert d.weiter is None
ok("Fenster: FEHLER nur mit Begründung („Trotzdem weiter“), sonst ein Weiter-Knopf; „Hinspringen“ schließt mit Ziel")

# ------------------------------------------------------------------ im Angebot
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(a)
assert s.optimieren()
ue = s.uebersicht_bereich
titel = ue.freigabe_bereich.knopf.text()
assert titel.startswith("Angebots-Check"), titel
assert "href='check:kopf:" in ue.freigabe.text() or "href='check:" in ue.freigabe.text(), ue.freigabe.text()

db.angebot_aendern(a, "kundenreferenz", "")
s.neu_laden()
assert any(x.ziel == "kopf:kundenreferenz" for x in s.freigabe_punkte())
w = s.check_link("check:kopf:kundenreferenz")
assert w is s.kopf_bereich.felder.get("kundenreferenz") or w is s.kopf_bereich.erweitert.get("kundenreferenz"), w
assert s.kopf_bereich.kopf_inhalt.isVisibleTo(s.kopf_bereich)
assert s.check_link("pos:1") == 1 and s.reiter.currentWidget() is s.pos_seite
s.check_link("staffeln")
assert s.reiter.currentWidget() is s.st_seite
ok("Übersicht: Angebots-Check mit Links; Hinspringen zu Kopf-Feld, Position und Staffeln")

# vor dem PDF: nur WARNUNG → eine Rückfrage, Weiter erstellt das PDF; FEHLER → Begründung im Versandverlauf
f.stumm = False
f.datei_oeffnen = lambda pfad: None
fragen = []


def antwort(ergebnis, begruendung=""):
    def ausfuehren(self):
        fragen.append([x.text for x in self.punkte])
        self.begruendung.setText(begruendung)
        return ergebnis
    return ausfuehren


db.angebot_aendern(a, "kunde", "")
s.neu_laden()
alt_exec = angebot_check_dialog.CheckDialog.exec
angebot_check_dialog.CheckDialog.exec = antwort(QDialog.Rejected)
try:
    assert s.angebot_pdf() is None and len(fragen) == 1 and any("kein Kunde" in t for t in fragen[0])
    assert not db.angebot(a).get("versand")
    db.position_aendern(db.positionen(a)[0]["id"], "stueck", 7)      # Schnittplan veraltet: ohne Rückfrage optimiert
    s.neu_laden()
    assert s.stand_optimierung() != "aktuell"
    angebot_check_dialog.CheckDialog.exec = antwort(QDialog.Accepted)
    assert s.angebot_pdf() and len(fragen) == 2 and s.stand_optimierung() == "aktuell"
    assert not any("Schnittplan" in t for t in fragen[1]), fragen[1]
    v = db.angebot(a)["versand"][-1]
    assert v["check"]["punkte"] and v["check"]["begruendung"] is None, v
    # FEHLER: nur mit Begründung
    db.position_aendern(db.positionen(a)[0]["id"], "profil_id", "GIBT ES NICHT")
    s.neu_laden()
    assert ac.blockiert(s.freigabe_punkte())
    angebot_check_dialog.CheckDialog.exec = antwort(QDialog.Accepted, "Kunde braucht Richtpreis")
    s._vor_ausgabe(pruefen=True, weiter="Angebot erstellen")
    assert s.check_uebergangen["begruendung"] == "Kunde braucht Richtpreis"
    # andere Ausgaben fragen nur nach der Fracht
    fragen.clear()
    assert s._vor_ausgabe() and not fragen
finally:
    angebot_check_dialog.CheckDialog.exec = alt_exec
ok("vor dem PDF eine Sammelrückfrage (veralteter Schnittplan wird ohne Rückfrage neu optimiert), übergangene Punkte "
   "und Begründung im Versandverlauf; andere Ausgaben fragen nur nach der Fracht")

# vor „Verschickt“ von Hand
b = beispiel_angebot.anlegen(db, dict(kunde=""))
liste_seite = f.angebote
angebot_check_dialog.CheckDialog.exec = antwort(QDialog.Rejected)
try:
    assert not liste_seite.vorgang_setzen("Verschickt", angebot_id=b)
    assert not db.angebot(b).get("vorgang")
    angebot_check_dialog.CheckDialog.exec = antwort(QDialog.Accepted)
    assert liste_seite.vorgang_setzen("Verschickt", angebot_id=b)
    assert db.angebot(b)["vorgang"] == "Verschickt"
    v = db.angebot(b)["versand"][-1]
    assert v["datei"] is None and v["check"]["punkte"], v
    assert liste_seite.vorgang_setzen("Beauftragt", angebot_id=b, auftrag=(None, None)) and db.angebot(b)["vorgang"] == "Beauftragt"
finally:
    angebot_check_dialog.CheckDialog.exec = alt_exec
from rohrlaser.angebot_oben import _versand_text  # noqa: E402
assert "als verschickt markiert (ohne PDF) – Angebots-Check übergangen" in _versand_text(v), _versand_text(v)
f.stumm = True
ok("vor „Verschickt“ von Hand: Check, Abbrechen lässt den Vorgang; übergangene Punkte im Versandverlauf")

assert any(e.titel == "Angebots-Check …" for e in __import__("rohrlaser.befehlspalette", fromlist=["x"]).eintraege(f))
assert any(x.text() == "Angebots-Check …" for x in s.weitere.menu().actions())
ok("Angebots-Check jederzeit: Menü Ausgaben und Strg+K")
print("OK: Angebots-Check")
