"""Prüft Etiketten mit QR-Code und Rückmeldung per Scan (Plan 29.10.2026 Schritt 2a):

- E1 Code nur aus Großbuchstaben und Ziffern (RL202600042P20), lesen verträgt Scanner-Fehler; kein Etikett -> Fehler
- E2 Etiketten-PDF: alle Formate, je Position/je Stück, angebrochener Bogen, Inhalt (Kunde, Auftrag, Pos., Länge)
- E3 Rückmeldung: Scan merkt Schritt und Menge (ganze Position oder Teilmenge), Summe je Position; nicht beauftragt,
  unbekannte Position und unbekannter Schritt werden abgewiesen
- E4 Fertigungsstatus: freigegebener Auftrag geht beim ersten Scan auf „In Fertigung“; alle Positionen im letzten
  Schritt -> Hinweis „fertig melden“
- E5 Oberfläche: Ausgaben-Menü, Etiketten-Dialog, Scan-Fenster (Enter schließt nicht), Reiter Fertigung mit
  Rückmeldungen; Löschen des Angebots löscht die Rückmeldungen

Aufruf: python tests/test_etiketten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pypdfium2 as pdfium  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import etiketten, fertigung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def text(pfad):
    doc = pdfium.PdfDocument(str(pfad))
    try:
        return len(doc), "\n".join(s.get_textpage().get_text_range() for s in doc)
    finally:
        doc.close()


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
f = Hauptfenster(db, stumm=True)

# E1
assert etiketten.code("2026-00042", 20) == "RL202600042P20" and etiketten.code("2026-00042-2", 20.0) == "RL2026000422P20"
assert etiketten.code("V-PB-1", "30") == "RLVPB1P30"
assert etiketten.lesen("rl202600042p20\n") == ("202600042", "20")
assert etiketten.lesen("RL2026ß00042P20") == ("202600042", "20"), "ß statt - (deutsche Belegung)"
assert etiketten.lesen("RLVPB1P30") == ("VPB1", "30")
for falsch in ("", "4006381333931", "RL202600042", "RLP20"):
    try:
        etiketten.lesen(falsch)
        raise AssertionError(falsch)
    except etiketten.ScanFehler:
        pass
ok("E1 Code RL…P…, tolerant gelesen, fremde Codes abgewiesen")

# Angebot mit zwei Positionen
a = db.angebot_neu(dict(kunde="Gestellbau Weber KG", skonto=0, stange=6000))
db.position_neu(a, dict(pos=10, artikel="GR-100", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1250,
                        stueck=4))
db.position_neu(a, dict(pos=20, artikel="GR-110", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=640,
                        stueck=6))
kopf = db.angebot(a)
nr = kopf["nummer"]

# E2
for name in etiketten.FORMATE:
    p = tmp / f"e_{len(name)}.pdf"
    n = etiketten.etiketten_pdf(p, etiketten.etiketten(kopf, db.positionen(a)), name, rahmen=True)
    seiten, t = text(p)
    assert n == 2 and nr in t and "Pos. 10" in t and "L = 1250 mm" in t and "Gestellbau Weber KG" in t, (name, t)
    assert seiten == (2 if name.startswith("Etikettendrucker") else 1), (name, seiten)
assert len(etiketten.etiketten(kopf, db.positionen(a), je_stueck=True)) == 10
assert len(etiketten.etiketten(kopf, db.positionen(a), anzahl=3)) == 6
p = tmp / "voll.pdf"
etiketten.etiketten_pdf(p, etiketten.etiketten(kopf, db.positionen(a), je_stueck=True), etiketten.FORMAT_VORGABE,
                        start=20)
assert text(p)[0] == 2, "20 Felder frei + 10 Etiketten = 2 Bögen à 24"
ok("E2 Etiketten-PDF in allen Formaten, je Stück, angebrochener Bogen")

# E3 Rückmeldung
try:
    etiketten.rueckmelden(db, etiketten.code(nr, 10), "Geschnitten")
    raise AssertionError("nicht beauftragt")
except etiketten.ScanFehler as e:
    assert "nicht beauftragt" in str(e)
db.vorgang_setzen(a, "Beauftragt")
r = etiketten.rueckmelden(db, etiketten.code(nr, 10), "Geschnitten", wer="PB")
assert r["menge"] == 4 and r["summe"] == 4 and r["status"] is None and not r["fertig"], r
r = etiketten.rueckmelden(db, etiketten.code(nr, 20), "Geschnitten", menge=2)
assert r["summe"] == 2 and "gesamt 2 von 6" in r["text"], r["text"]
r = etiketten.rueckmelden(db, etiketten.code(nr, 20), "Geschnitten", menge=4)
assert r["summe"] == 6
for code, schritt in ((etiketten.code(nr, 99), "Geschnitten"), (etiketten.code(nr, 10), "Lackiert"),
                      (etiketten.code("2026-99999", 10), "Geschnitten")):
    try:
        etiketten.rueckmelden(db, code, schritt)
        raise AssertionError(code)
    except etiketten.ScanFehler:
        pass
stand = {z["pos"]: z["schritte"] for z in etiketten.stand_je_position(db, a)}
assert stand == {"10": {"Geschnitten": 4}, "20": {"Geschnitten": 6}}, stand
ok("E3 Rückmeldung je Schritt mit Menge, Fehler abgewiesen")

# E4 Fertigungsstatus
fertigung.setzen(db, a, "Freigegeben", wer="PB")
r = etiketten.rueckmelden(db, etiketten.code(nr, 10), "Verpackt")
assert r["status"] == "In Fertigung" and fertigung.aktuell(db, a)["status"] == "In Fertigung"
assert fertigung.aktuell(db, a)["bemerkung"] == "per Scan"
r = etiketten.rueckmelden(db, etiketten.code(nr, 20), "Verpackt")
assert r["status"] is None and r["fertig"] and "fertig melden" in r["text"], r
ok("E4 erster Scan -> In Fertigung, letzter Schritt vollständig -> Hinweis fertig melden")

# E5 Oberfläche
s = f.angebot_oeffnen(a)
texte = [x.text() for x in s.weitere.menu().actions()]
assert "Etiketten mit QR-Code (PDF) …" in texte, texte
from rohrlaser.etiketten_dialog import EtikettenDialog, ScanDialog  # noqa: E402
d = EtikettenDialog(f, db, db.angebot(a), db.positionen(a))
d.format.setCurrentText("Etikettendrucker 100 × 50 mm")
assert not d.start.isEnabled()
d.je_stueck.setChecked(True)
pfad = s.etiketten_pdf(dialog=d)
assert pfad and Path(pfad).name == f"{nr} Etiketten.pdf" and text(pfad)[0] == 10
assert db.einstellung("etikett_format") == "Etikettendrucker 100 × 50 mm", "Format gemerkt"
f.fertigung.neu_laden()
f.fertigung.waehlen(a)
t = f.fertigung.rueckmeldungen
assert t.rowCount() == 2 and t.horizontalHeaderItem(3).text() == "Geschnitten", t.rowCount()
assert t.item(0, 3).text() == "4 / 4" and t.item(1, 5).text() == "6 / 6"
sd = f.fertigung.scannen()
assert isinstance(sd, ScanDialog)
sd.show()
sd.schritt.setCurrentText("Entgratet")
sd.feld.setFocus()
QTest.keyClicks(sd.feld, etiketten.code(nr, 10))
QTest.keyClick(sd.feld, Qt.Key_Return)
assert sd.isVisible() and len(sd.ergebnisse) == 1 and sd.ergebnisse[0]["schritt"] == "Entgratet"
assert sd.scannen("Unsinn") is None and "Nicht übernommen" in sd.meldung.text() and sd.liste.rowCount() == 2
sd.close()
assert f.fertigung.etiketten(dialog=EtikettenDialog(f, db, db.angebot(a), db.positionen(a)))
f.angebot_schliessen(a)
db.angebot_loeschen(a)
assert db.con.execute("SELECT COUNT(*) FROM rueckmeldungen").fetchone()[0] == 0
ok("E5 Menü, Etiketten-Dialog, Scan-Fenster, Reiter Fertigung, Löschen")
print("Alle Etiketten-Tests bestanden.")
