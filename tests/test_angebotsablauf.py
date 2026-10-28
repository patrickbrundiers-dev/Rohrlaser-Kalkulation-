"""Plan „Angebotsablauf mit STEP einfacher machen“ (Freigabe Patrick 26.10.2026 „Alle a“):
- V0: Zusatzarbeiten für mehrere markierte Positionen ändern nur das Gemeinsame; eigene Gewinde und Zusatzarbeiten
  (z. B. aus „Bohrungen prüfen“) jeder Position bleiben.
- V1/V2: STEP-Prüfdialog zeigt alle Dateien in einer Liste, Hinweis gleich hinter dem Teil, passt in 1366 px.
- V3: „Bohrungen prüfen“ für alle offenen Positionen in einem Fenster (Status-Doppelklick, Einblendung, Check).
- V4: Zusatzarbeit für alle Teile schon im Prüfdialog, als Importprofil des Kunden merkbar.
- V5: Anfrage-Nr. des Kunden im Prüfdialog, Vorschlag aus dem Ordnernamen.
- V6: Spalte „Gewinde · Zusatzarbeiten“ gleich hinter der Artikelnummer.
- V7: Bis zum automatischen Optimieren „…“ und Stand „… – wird berechnet …“ statt eines Preises ohne Material.
- Rüsten wahlweise als fester Betrag je Angebot bzw. je Abmessung statt Minuten × Stundensatz.

Aufruf: python tests/test_angebotsablauf.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_check, bohrbild, importprofil, rechnen, step_neu, zusatz_dialog  # noqa: E402
from rohrlaser.bohrbild_dialog import BohrbildSammelDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ V0 reine Logik
pos = [dict(gewinde="2xM8", zusatz=json.dumps([dict(name="Senken", menge=2, quelle="Bohrungen prüfen"),
                                               dict(name="Feuerverzinken", menge=None, preis=None)])),
       dict(gewinde="4xM6", zusatz=json.dumps([dict(name="Feuerverzinken", menge=None, preis=None)])),
       dict(gewinde=None, zusatz=None)]
g, z = zusatz_dialog.gemeinsam(pos[:2])
assert g is None and [e["name"] for e in z] == ["Feuerverzinken"], (g, z)
g, z = zusatz_dialog.gemeinsam(pos)
assert g is None and z == []
vorher = zusatz_dialog.gemeinsam(pos[:2])
neu = ("1xM10", json.dumps([dict(name="Feuerverzinken", menge=None, preis=None),
                            dict(name="Pulverbeschichten", menge=None, preis=None, text="RAL 9005")]))
erg = [zusatz_dialog.zusammenfuehren(p, vorher, neu) for p in pos[:2]]
assert erg[0][0] == "2xM8; 1xM10" and erg[1][0] == "4xM6; 1xM10", erg
assert [e["name"] for e in json.loads(erg[0][1])] == ["Senken", "Feuerverzinken", "Pulverbeschichten"]
assert json.loads(erg[0][1])[0]["quelle"] == "Bohrungen prüfen", "eigener Eintrag aus Bohrungen prüfen bleibt"
assert [e["name"] for e in json.loads(erg[1][1])] == ["Feuerverzinken", "Pulverbeschichten"]
weg = [zusatz_dialog.zusammenfuehren(p, vorher, ("", None)) for p in pos[:2]]
assert weg[0] == ("2xM8", json.dumps([json.loads(pos[0]["zusatz"])[0]], ensure_ascii=False)), weg[0]
assert weg[1] == ("4xM6", None), "gemeinsame gelöscht, Gewinde bleiben"
gleich = [dict(gewinde="2xM8"), dict(gewinde="2xM8")]
v = zusatz_dialog.gemeinsam(gleich)
assert v[0] == "2xM8" and zusatz_dialog.zusammenfuehren(gleich[0], v, ("3xM8", None))[0] == "3xM8"
ok("V0: Mehrfachauswahl ändert nur das Gemeinsame, eigene Gewinde und Zusatzarbeiten bleiben")

# ------------------------------------------------------------------ Referenz aus Ordnername (V5)
assert step_neu.referenz_aus_ordner(["/x/Stahlbau Ostermann Anfrage 4711/a.step"]) == "4711"
assert step_neu.referenz_aus_ordner(["/x/Anfrage-Nr. A-123/a.step"]) == "A-123"
assert step_neu.referenz_aus_ordner(["/x/Anfragen/Kunde/a.step"]) is None
ok("V5: Anfrage-Nr. aus dem Ordnernamen")

# ------------------------------------------------------------------ Programm: neues Angebot aus STEP mit Dialog
app = QApplication.instance() or QApplication([])
app.setFont(QFont("Liberation Sans", 9))            # wie Segoe UI 9 unter Windows
tmp = Path(tempfile.mkdtemp())
(tmp / "Daten").mkdir()
db = Datenbank(tmp / "Daten" / "rohrlaser.db")
db.neu("kunden", dict(kundennr="10588", name="Stahlbau Ostermann"))
f = Hauptfenster(db, tmp, stumm=False)
f.resize(1366, 768)
f.show()
f.datei_oeffnen = lambda p: None
mappe = tmp / "Anfragen" / "Stahlbau Ostermann Anfrage 4711"
mappe.mkdir(parents=True)
for p in (HIER / "step" / "T01_RR42-4x2_L1250.step", HIER / "step" / "T07_QR40x3_L1000_Gewinde_Gravur.step",
          HIER / "step_konturen" / "K04_RE60x40x3_Senkung_Flowdrill.step",
          HIER / "step_satz" / "T08_Gestell_Baugruppe.step"):
    shutil.copy(p, mappe)
gesehen = {}


def pruefen():
    d = QApplication.activeModalWidget()
    if not isinstance(d, StepPruefDialog):
        QTimer.singleShot(50, pruefen)
        return
    app.processEvents()
    d.datei_waehlen(len(d.dateien) - 1)            # Baugruppe: Anzahl, Als Satz, Schweißbaugruppe sichtbar
    app.processEvents()
    gesehen["breite"] = d.minimumSizeHint().width()
    gesehen["alle_sichtbar"] = all(not z.it.isHidden() and not z.it.parent().isHidden() for z in d.zeilen)
    gesehen["kunde"] = d.kunde_wahl.currentData()
    gesehen["referenz"] = d.referenz_text()
    gesehen["hinweis_spalte"] = d.SPALTEN[d.SP_HINWEIS]
    d.alle_setzen("S235-10219", 10, zusatz="Feuerverzinken")
    gesehen["zusatz_text"] = {z.it.text(d.SP_ZUSATZ) for z in d.zeilen}
    d.lernen_haken.setChecked(True)
    d.vorpruefung_zeigen()
    gesehen["lernen"] = d.lernen_haken.text()
    d.accept()


QTimer.singleShot(50, pruefen)
seite = step_neu.neues_angebot(f, [str(mappe)])
assert seite is not None and len(seite.positionen) == 7, len(seite.positionen)
assert gesehen["breite"] <= 1366, f"Prüfdialog zu breit: {gesehen['breite']} px"
assert gesehen["alle_sichtbar"] and gesehen["hinweis_spalte"] == "Hinweis"
assert gesehen["kunde"] == "10588" and gesehen["referenz"] == "4711"
assert seite.kopf.get("kundenreferenz") == "4711"
ok("V1/V2/V5: alle Dateien in einer Liste, Dialog ≤ 1366 px, Kunde und Anfrage-Nr. aus dem Ordnernamen")
assert gesehen["zusatz_text"] == {"Feuerverzinken"} and "Zusatzarbeit Feuerverzinken" in gesehen["lernen"]
assert all("Feuerverzinken" in rechnen.zusatz_text(p) for p in seite.positionen)
profil = importprofil.fuer_kunde(db, "10588")
assert importprofil.vorgaben(profil).get("zusatz") == ["Feuerverzinken"], profil
ok("V4: Zusatzarbeit für alle Teile im Prüfdialog, als Importprofil des Kunden gemerkt")
db.neu("kunden", dict(kundennr="10600", name="Metallbau Ohne Profil"))
mw = [dict(artikel="X1", datei="x.step", _zusatz=["Feuerverzinken", "Entgraten"])]
seite._step_zusatz = ["Feuerverzinken"]
assert seite._step_kunde_gewechselt("10600", mw)[1] == [] and mw[0]["_zusatz"] == ["Entgraten"], mw
assert seite._step_kunde_gewechselt("10588", mw)[1] == ["Feuerverzinken"]
assert mw[0]["_zusatz"] == ["Entgraten", "Feuerverzinken"], mw
ok("V4: Kundenwechsel im Prüfdialog ersetzt die Zusatzarbeiten des Importprofils, eigene bleiben")

# V3: Einblendung nach dem Import führt zum Prüfen aller offenen Bohrungen
offen = seite.bohrungen_offen()
assert len(offen) == 2, offen
assert f.letzte_aktion and f.letzte_aktion[0] == "Bohrungen prüfen …"
punkte = seite.freigabe_punkte()
assert any(p.ziel == "bohrungen" for p in punkte), [(p.text, p.ziel) for p in punkte]


def alle(d):
    assert isinstance(d, BohrbildSammelDialog) and len({r for r, *_ in d.zeilen}) == 2
    assert "noch offen" in d.info.text()
    d.alle_bestaetigen()
    assert d.info.text() == "Alle Zeilen geprüft."
    d.accept()


assert seite.bohrungen_alle_pruefen(dialog=alle)
assert seite.bohrungen_offen() == []
k04 = next(p for p in seite.positionen if p["artikel"].startswith("K04"))
t07 = next(p for p in seite.positionen if p["artikel"].startswith("T07"))
assert {"Senken", "Flowdrill", "Feuerverzinken"} <= {e["name"] for e in rechnen.zusatz_liste(k04)}
assert k04["gewinde"] == "2xM8" and t07["gewinde"] == "4xM6", (k04["gewinde"], t07["gewinde"])
assert not any(p.ziel == "bohrungen" for p in seite.freigabe_punkte())
ok("V3: Bohrungen aller Positionen in einem Fenster, Einblendung und Angebots-Check führen dorthin")

# V0 im Programm: Zusatzarbeit für alle markierten Positionen, eigene bleiben
alle_zeilen = list(range(len(seite.positionen)))
vorher = zusatz_dialog.gemeinsam(seite.positionen)
assert vorher[0] is None and [e["name"] for e in vorher[1]] == ["Feuerverzinken"]
assert seite.zusatzarbeiten(alle_zeilen, ("", json.dumps([dict(name="Feuerverzinken"), dict(name="Entgraten")])))
k04 = next(p for p in seite.positionen if p["artikel"].startswith("K04"))
t07 = next(p for p in seite.positionen if p["artikel"].startswith("T07"))
t01 = next(p for p in seite.positionen if p["artikel"].startswith("T01"))
assert k04["gewinde"] == "2xM8" and t07["gewinde"] == "4xM6" and not t01.get("gewinde")
assert [e["name"] for e in rechnen.zusatz_liste(k04)] == ["Feuerverzinken", "Senken", "Flowdrill", "Entgraten"]
assert all("Entgraten" in rechnen.zusatz_text(p) for p in seite.positionen)
ok("V0: Zusatzarbeiten für alle markierten Positionen überschreiben Gewinde und Bohrungsarbeiten nicht mehr")

# V6: Spalte Gewinde · Zusatzarbeiten hinter der Artikelnummer
m = seite.pos_modell
namen = [m.name(c) for c in range(m.columnCount())]
c = namen.index("zusatz")
assert c == namen.index("artikel") + 1 and m.headerData(c, 1) == "Gewinde · Zusatzarbeiten"
r = seite.positionen.index(k04)
assert m.data(m.index(r, c)).startswith("2xM8 · Feuerverzinken; Senken"), m.data(m.index(r, c))
ok("V6: Gewinde und Zusatzarbeiten gleich hinter der Artikelnummer")

# V7: vor dem automatischen Optimieren kein Preis ohne Material
db.position_aendern(t01["id"], "stueck", 12)
seite.neu_laden()
ub = seite.uebersicht_bereich
if seite.auto_optimieren_moeglich():
    # Text nur im Stand, die großen Preisfelder zeigen „…“ (langer Text in 17 pt schnitt den Preisaufbau ab)
    assert ub.preis["verkauf"].text() == "…" and ub.preis["herstell"].text() == "…"
    # Stand behält Wort und Farbe (Veraltet bzw. Noch nicht optimiert) und sagt dahinter „– wird berechnet …“
    assert ub.stand.text().endswith(" – wird berechnet …"), ub.stand.text()
assert seite.auto_optimieren()
assert ub.preis["verkauf"].text().endswith("€") and ub.stand.text() == "Optimierung abgeschlossen"
ok("V7: „… – wird berechnet …“ bis zum automatischen Optimieren")

# V7: scheitert das automatische Optimieren, steht wieder der Stand mit vorläufigen Preisen da (ohne „wird berechnet“)
db.position_aendern(t01["id"], "stueck", 11)
seite.neu_laden()
if seite.auto_optimieren_moeglich():
    assert ub.stand.text().endswith(" – wird berechnet …"), ub.stand.text()
    seite.optimieren = lambda automatisch=False: False
    try:
        assert not seite.auto_optimieren()
    finally:
        del seite.optimieren
    assert "wird berechnet" not in ub.stand.text() and ub.preis["verkauf"].text().endswith("€"), ub.stand.text()
    assert not seite.auto_optimieren_moeglich()          # gleiche Eingaben: kein neuer Versuch, keine Schleife
db.position_aendern(t01["id"], "stueck", 12)
seite.neu_laden()
if seite.auto_optimieren_moeglich():
    assert seite.auto_optimieren()
ok("V7: gescheitertes automatisches Optimieren zeigt wieder Stand und vorläufige Preise")

# ------------------------------------------------------------------ Rüsten als fester Betrag
f.stumm = True
z0, s0 = seite._rechnung()
assert s0["ruesten_maschine"] > 0 and s0["ruesten_abmessungen"] > 0
db.angebot_aendern(seite.id, "ruesten_angebot_eur", 40.0)
db.angebot_aendern(seite.id, "ruesten_abmessung_eur", 12.5)
seite.neu_laden()
seite.optimieren()
z1, s1 = seite._rechnung()
assert abs(s1["ruesten_maschine"] - 40.0) < 1e-9 and abs(s1["ruesten_abmessungen"] - 12.5 * s1["abmessungen"]) < 1e-9
# Rüstzeit folgt aus dem Betrag: € / Stundensatz × 60 (Patrick 27.10.2026: „30 € … wird daraus keine Zeit berechnet“)
s_rm = s0["ruesten_maschine"] * 60 / s0["ruestzeit"]
s_ra = s0["ruesten_abmessungen"] * 60 / (s0["abmessungen"] * s0["ruestzeit_abmessung"])
assert abs(s1["ruestzeit"] - 40.0 / s_rm * 60) < 1e-9 and abs(s1["ruestzeit_abmessung"] - 12.5 / s_ra * 60) < 1e-9, s1
zz = {z["schritt"]: z for z in s1["zeiten"]}
assert abs(zz["Rüsten Maschine"]["gesamt_min"] - s1["ruestzeit"]) < 1e-9 and "≙" in zz["Rüsten Maschine"]["formel"]
assert zz["Rüsten je Abmessung"]["gesamt_min"] > 0 and "≙" in zz["Rüsten je Abmessung"]["formel"]
ruesten = sum(z["ruesten_teil"] * z["stueck"] for z in z1 if z)
assert abs(ruesten - (40.0 + 12.5 * s1["abmessungen"] + s1["stangenwechsel_kosten"])) < 0.01, ruesten
db.angebot_aendern(seite.id, "ruesten_angebot_eur", None)
db.angebot_aendern(seite.id, "ruesten_abmessung_eur", None)
seite.neu_laden()
seite.optimieren()
assert abs(seite._rechnung()[1]["ruesten_maschine"] - s0["ruesten_maschine"]) < 1e-9, "leer = Minuten wie bisher"
assert db.einstellung("ruesten_angebot_eur") is None and "ruesten_abmessung_eur" not in db.kalkulation_vorgaben()
ok("Rüsten je Angebot bzw. je Abmessung als fester Betrag (Rüstzeit = Betrag ÷ Stundensatz), leer = Minuten × Stundensatz")

assert angebot_check and bohrbild      # verwendet über die Seite
f.close()
db.schliessen()
print("Alle Tests bestanden.")
