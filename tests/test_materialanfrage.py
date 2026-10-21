"""Prüft Zeichnungen je Position und die Materialanfrage:
- Zeichnungen: Kopie im Ordner des Angebots, gleiche Datei nicht doppelt, gleicher Name mit anderem Inhalt ' (2)',
  Spalte Zeichnungen, Dialog (Entfernen löst nur die Zuordnung), Ziehen auf eine Position.
- Materialanfrage: Bedarf aus der Optimierung je Profil + Werkstoff + Lieferlänge (ohne Kundenmaterial), Lieferant
  aus 'Preise', E-Mail aus den Lieferanten, Text mit Stangen, Zeichnungen als Anhang, Mengen änderbar, Zeilen
  abwählbar; Outlook wird nur zum Anzeigen aufgerufen (Display, nie Send); ohne Outlook E-Mail-Datei (.eml, Entwurf).
- Ältere Datei (Schema 26) bekommt die Spalte dokumente leer.

Aufruf: python tests/test_materialanfrage.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import email
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from email import policy
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import dokumente, materialanfrage as ma  # noqa: E402
from rohrlaser.angebot import KUNDENMATERIAL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
quelle = tmp / "Kunde"
quelle.mkdir()
(quelle / "Z-100.pdf").write_bytes(b"%PDF-1.4 Zeichnung 100")
(quelle / "Z-200.dxf").write_text("0\nSECTION\n")
(quelle / "liesmich.txt").write_text("kein Anhang")
anders = tmp / "anders"
anders.mkdir()
(anders / "Z-100.pdf").write_bytes(b"%PDF-1.4 andere Zeichnung")

db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Muster Laser GmbH")
db.neu("zukauf_lieferanten", dict(name="Stahlhandel Nord", email="anfrage@stahl-nord.example"))
preis = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("QR 40x40x3", "S235-10219"))
db.aendern("preise", preis["id"], "lieferant", "Stahlhandel Nord")
for z in db.zeilen("preise") + db.zeilen("lieferlaengen"):    # Rundrohr ohne Lieferant (Adresse von Hand)
    if z["profil_id"] == "RR 42,4x2,0":
        db.aendern("preise" if "basis" in z and "laenge" not in z else "lieferlaengen", z["id"], "lieferant", None)
a = db.angebot_neu(dict(kunde="Test", nummer="A-2026-0100"))
for i, (pid, laenge, stueck, extra) in enumerate((("QR 40x40x3", 1450, 8, {}), ("QR 40x40x3", 900, 6, {}),
                                                  ("RR 42,4x2,0", 700, 10, {}),
                                                  ("RR 48,3x2,6", 500, 4, dict(material_herkunft=KUNDENMATERIAL)))):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id=pid, werkstoff_id="S235-10219",
                            laenge=laenge, stueck=stueck, schneidweg=200, einstiche=2, **extra))
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1920, 1080)
s = fenster.angebot_oeffnen(a)
ordner = dokumente.ordner(fenster.ablage(), s.kopf)
assert ordner == tmp / "Ablage" / "A-2026-0100"

# ------------------------------------------------------------------ D1 Zeichnungen anhängen
assert s.dokumente_anhaengen(0, [quelle / "Z-100.pdf", quelle / "Z-200.dxf", quelle / "liesmich.txt"]) == 2
p0 = db.positionen(a)[0]
assert dokumente.liste(p0["dokumente"]) == ["Z-100.pdf", "Z-200.dxf"] and (ordner / "Z-100.pdf").is_file()
assert s.dokumente_anhaengen(0, [quelle / "Z-100.pdf"]) == 1                    # gleiche Datei: nicht doppelt
assert dokumente.liste(db.positionen(a)[0]["dokumente"]) == ["Z-100.pdf", "Z-200.dxf"]
assert s.dokumente_anhaengen(1, [anders / "Z-100.pdf"]) == 1                    # gleicher Name, anderer Inhalt
assert dokumente.liste(db.positionen(a)[1]["dokumente"]) == ["Z-100 (2).pdf"]
assert (ordner / "Z-100 (2).pdf").read_bytes() == b"%PDF-1.4 andere Zeichnung"
m = s.pos_modell
c = next(i for i, (art, f) in enumerate(m.spalten) if f is not None and getattr(f, "name", None) == "dokumente")
assert m.data(m.index(0, c)) == "2 Dateien" and m.data(m.index(1, c)) == "Z-100 (2).pdf"
assert "Z-200.dxf" in m.data(m.index(0, c), Qt.ToolTipRole) and not s.pos_ansicht.isColumnHidden(c)
ok("D1 Zeichnungen: Kopie im Ordner des Angebots, keine Dubletten, gleicher Name mit anderem Inhalt ' (2)', Spalte")

# ------------------------------------------------------------------ D2 Dialog und Ziehen
geoeffnet = []
s.f.datei_oeffnen = geoeffnet.append


def bedienen(d):
    assert d.liste.count() == 2
    d.liste.item(1).setSelected(True)
    d._oeffnen()
    d._entfernen()                      # nur die Zuordnung, die Datei bleibt
    d.hinzufuegen([quelle / "liesmich.txt"])          # falsche Endung: nichts
    return QDialog.Accepted


assert s.zeichnungen(0, dialog=bedienen)
assert geoeffnet == [ordner / "Z-200.dxf"] and (ordner / "Z-200.dxf").is_file()
assert dokumente.liste(db.positionen(a)[0]["dokumente"]) == ["Z-100.pdf"]


class Ziehen:                           # wie ein QDropEvent mit gezogenen Dateien an einer Stelle
    def __init__(self, pfade, punkt):
        self.m = QMimeData()
        self.m.setUrls([QUrl.fromLocalFile(str(p)) for p in pfade])
        self.punkt, self.angenommen = punkt, False

    def mimeData(self):
        return self.m

    def position(self):
        return QPointF(self.punkt)

    def acceptProposedAction(self):
        self.angenommen = True


s.show()
app.processEvents()
vp = s.pos_ansicht.viewport()
mitte = s.pos_ansicht.visualRect(m.index(2, 2)).center()
z = Ziehen([quelle / "Z-200.dxf"], vp.mapTo(s, mitte))
s.dragEnterEvent(z)
assert z.angenommen
s.dropEvent(z)
assert dokumente.liste(db.positionen(a)[2]["dokumente"]) == ["Z-200.dxf"]
daneben = Ziehen([quelle / "Z-200.dxf"], QPoint(2, 2))                # nicht auf einer Position: Hinweis
s.dropEvent(daneben)
assert "direkt auf die Position" in fenster.statusBar().currentMessage()
ok("D2 Dialog (öffnen, entfernen), Datei auf eine Position ziehen hängt sie an, daneben nur Hinweis")

# ------------------------------------------------------------------ M1 Bedarf
assert s.material_anfragen() is None and "zuerst optimieren" in fenster.statusBar().currentMessage()
assert s.optimieren()
werte = __import__("rohrlaser.rechnen", fromlist=["x"]).stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
zeilen = ma.bedarf(s.positionen, s.ergebnis, s.k, s.tabellen, werte)
schl = {(z["profil"], z["stange"] if "stange" in z else z["laenge"]): z for z in zeilen}
assert set(schl) == {("QR 40x40x3", 6000), ("RR 42,4x2,0", 6000)}, set(schl)      # ohne Kundenmaterial RR 48,3
qr, rr = schl[("QR 40x40x3", 6000)], schl[("RR 42,4x2,0", 6000)]
n_qr = sum(1 for st in s.ergebnis["stangen"] if st["profil"] == "QR 40x40x3")
assert qr["stangen"] == n_qr >= 3 and qr["lieferant"] == "Stahlhandel Nord" and rr["lieferant"] is None
assert qr["pos"] == ["10", "20"] and qr["dokumente"] == ["Z-100.pdf", "Z-100 (2).pdf"] and rr["dokumente"] == ["Z-200.dxf"]
assert qr["text"].startswith(f"{n_qr} Stangen Quadratrohr 40 x 40 x 3") and "à 6.000 mm (ca." in qr["text"], qr["text"]
assert ma.lieferanten(db.zeilen("zukauf_lieferanten")) == {"Stahlhandel Nord": "anfrage@stahl-nord.example"}
ok("M1 Bedarf: Stangen je Profil + Werkstoff + Lieferlänge aus der Optimierung, Kundenmaterial nicht, Lieferant, Zeichnungen")

# ------------------------------------------------------------------ M2 Dialog und Outlook (nur anzeigen)
aufrufe = []


def outlook_ok(befehl):
    """Statt PowerShell: Skript und Daten prüfen, Erfolg melden."""
    skript = Path(befehl[befehl.index("-File") + 1]).read_text(encoding="utf-8-sig")
    daten = json.loads(Path(befehl[-1]).read_text(encoding="utf-8"))
    aufrufe.append((befehl[0], skript, daten))
    return subprocess.CompletedProcess(befehl, 0, "", "")


gesehen = {}


def anfrage_bedienen(d):
    gesehen["lieferant"] = d.lieferant.currentText()
    gesehen["an"], _, gesehen["text"], gesehen["anhaenge"] = d.mail()
    gesehen["gewaehlt"] = d.gewaehlt()
    d.mengen[d.gewaehlt()[0]].setValue(qr["stangen"] + 2)                # Menge ändern -> Text neu
    gesehen["text2"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


d = s.material_anfragen(dialog=anfrage_bedienen, ausfuehren=outlook_ok)
assert gesehen["lieferant"] == "Stahlhandel Nord" and gesehen["an"] == "anfrage@stahl-nord.example"
assert len(gesehen["gewaehlt"]) == 1 and "Quadratrohr 40 x 40 x 3" in gesehen["text"] and "Rundrohr" not in gesehen["text"]
assert "Angebot A-2026-0100" in gesehen["text"] and "Muster Laser GmbH" in gesehen["text"]
assert "Zeichnungen hängen an" in gesehen["text"]
assert [p.name for p in gesehen["anhaenge"]] == ["Z-100.pdf", "Z-100 (2).pdf"]
assert f"{qr['stangen'] + 2} Stangen Quadratrohr" in gesehen["text2"]
prog, skript, daten = aufrufe[0]
assert prog == "powershell" and "Display" in skript and ".Send" not in skript and "Send(" not in skript
assert daten["an"] == "anfrage@stahl-nord.example" and daten["betreff"] == "Materialanfrage zu Angebot A-2026-0100"
assert [Path(x).name for x in daten["anhaenge"]] == ["Z-100.pdf", "Z-100 (2).pdf"] and "Stangen" in daten["text"]
assert d.ergebnis == "outlook" and "in Outlook geöffnet" in fenster.statusBar().currentMessage()
ok("M2 Vorschau: Lieferant mit E-Mail, nur seine Zeilen, Menge änderbar, Zeichnungen; Outlook nur Display, nie Send")

# ------------------------------------------------------------------ M3 ohne Outlook: E-Mail-Datei
def outlook_fehlt(befehl):
    return subprocess.CompletedProcess(befehl, 1, "", "Die COM-Klasse Outlook.Application ist nicht registriert.")


def ohne_lieferant(d):
    d.lieferant.setCurrentText(ma.OHNE_LIEFERANT)        # Rundrohr ohne Lieferant, Adresse von Hand
    d.an.setText("einkauf@rohr.example")
    for i in range(d.anhaenge.count()):
        d.anhaenge.item(i).setCheckState(Qt.Unchecked)      # Zeichnung abwählen
    d.in_outlook()
    return d.result()


geoeffnet.clear()
d = s.material_anfragen(dialog=ohne_lieferant, ausfuehren=outlook_fehlt)
assert d.ergebnis == "eml" and "nicht ansteuern" in d.meldung and geoeffnet and geoeffnet[0].suffix == ".eml"
mail = email.message_from_bytes(geoeffnet[0].read_bytes(), policy=policy.default)
assert mail["To"] == "einkauf@rohr.example" and mail["X-Unsent"] == "1"
assert "Rundrohr Ø 42,4 x 2" in mail.get_body().get_content() and "Quadratrohr" not in mail.get_body().get_content()
assert not list(mail.iter_attachments())
pfad = ma.eml(tmp / "mit.eml", "a@b.example", "Test", "Text", [ordner / "Z-100.pdf"])
anh = list(email.message_from_bytes(pfad.read_bytes(), policy=policy.default).iter_attachments())
assert [x.get_filename() for x in anh] == ["Z-100.pdf"] and anh[0].get_content() == b"%PDF-1.4 Zeichnung 100"
assert ma.outlook_oeffnen("a", "b", "c") == (False, "Outlook gibt es nur unter Windows.") or sys.platform == "win32"
ok("M3 Ohne Outlook: E-Mail-Datei als Entwurf (X-Unsent) mit Empfänger, Text und gewählten Anhängen, geöffnet")

# ------------------------------------------------------------------ M4 Kundenmaterial allein, ältere Datei
b = db.angebot_neu(dict(kunde="Nur Kunde"))
db.position_neu(b, dict(pos=10, artikel="K", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000, stueck=4,
                        schneidweg=200, einstiche=2, material_herkunft=KUNDENMATERIAL))
sb = fenster.angebot_oeffnen(b)
assert sb.optimieren() and sb.material_anfragen() is None and "kein Eigenmaterial" in fenster.statusBar().currentMessage()
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("ALTER TABLE positionen DROP COLUMN dokumente")
con.execute("PRAGMA user_version=26")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert all(p["dokumente"] is None for p in db2.positionen(a)) and db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("M4 Nur Kundenmaterial: keine Anfrage; Datei mit Schema 26: Spalte dokumente leer ergänzt, Sicherung vorher")
print("OK: Zeichnungen und Materialanfrage")
