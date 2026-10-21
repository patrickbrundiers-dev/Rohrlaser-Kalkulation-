"""Prüft die Materialanfrage (die Zeichnungsablage je Position ist seit 0.6.28 entfernt):
- Materialanfrage: Bedarf aus der Optimierung je Profil + Werkstoff + Lieferlänge (ohne Kundenmaterial), Lieferant
  aus 'Preise', E-Mail aus den Lieferanten, Text mit Stangen, Mengen änderbar, Zeilen
  abwählbar; Outlook wird nur zum Anzeigen aufgerufen (Display, nie Send); ohne Outlook E-Mail-Datei (.eml, Entwurf).
- Ältere Datei (Schema 26) lässt sich weiter öffnen; früher abgelegte Zeichnungen werden einmalig gelöscht.

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
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import materialanfrage as ma  # noqa: E402
from rohrlaser.angebot import KUNDENMATERIAL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
(tmp / "Z-100.pdf").write_bytes(b"%PDF-1.4 Zeichnung 100")

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

geoeffnet = []
s.f.datei_oeffnen = geoeffnet.append
assert not hasattr(s, "zeichnungen") and not hasattr(s, "dokumente_anhaengen")       # seit 0.6.28 entfernt
assert all(getattr(f, "name", None) != "dokumente" for _, f in s.pos_modell.spalten)
assert "dokumente" not in db.positionen(a)[0]
ok("D Zeichnungsablage entfernt: keine Spalte Zeichnungen, keine Ablage-Funktionen")

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
assert qr["pos"] == ["10", "20"] and "dokumente" not in qr
assert qr["text"].startswith(f"{n_qr} Stangen Quadratrohr 40 x 40 x 3") and "à 6.000 mm (ca." in qr["text"], qr["text"]
assert ma.lieferanten(db.zeilen("zukauf_lieferanten")) == {"Stahlhandel Nord": "anfrage@stahl-nord.example"}
ok("M1 Bedarf: Stangen je Profil + Werkstoff + Lieferlänge aus der Optimierung, Kundenmaterial nicht, Lieferant")

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
    gesehen["an"], _, gesehen["text"] = d.mail()
    gesehen["gewaehlt"] = d.gewaehlt()
    d.mengen[d.gewaehlt()[0]].setValue(qr["stangen"] + 2)                # Menge ändern -> Text neu
    gesehen["text2"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


d = s.material_anfragen(dialog=anfrage_bedienen, ausfuehren=outlook_ok)
assert gesehen["lieferant"] == "Stahlhandel Nord" and gesehen["an"] == "anfrage@stahl-nord.example"
assert len(gesehen["gewaehlt"]) == 1 and "Quadratrohr 40 x 40 x 3" in gesehen["text"] and "Rundrohr" not in gesehen["text"]
assert "Angebot A-2026-0100" in gesehen["text"] and "Muster Laser GmbH" in gesehen["text"]
assert "Zeichnung" not in gesehen["text"]
assert f"{qr['stangen'] + 2} Stangen Quadratrohr" in gesehen["text2"]
prog, skript, daten = aufrufe[0]
assert prog == "powershell" and "Display" in skript and ".Send" not in skript and "Send(" not in skript
assert daten["an"] == "anfrage@stahl-nord.example" and daten["betreff"] == "Materialanfrage zu Angebot A-2026-0100"
assert not daten.get("anhaenge") and "Stangen" in daten["text"]
assert d.ergebnis == "outlook" and "in Outlook geöffnet" in fenster.statusBar().currentMessage()
ok("M2 Vorschau: Lieferant mit E-Mail, nur seine Zeilen, Menge änderbar, ohne Anhang; Outlook nur Display, nie Send")

# ------------------------------------------------------------------ M3 ohne Outlook: E-Mail-Datei
def outlook_fehlt(befehl):
    return subprocess.CompletedProcess(befehl, 1, "", "Die COM-Klasse Outlook.Application ist nicht registriert.")


def ohne_lieferant(d):
    d.lieferant.setCurrentText(ma.OHNE_LIEFERANT)        # Rundrohr ohne Lieferant, Adresse von Hand
    d.an.setText("einkauf@rohr.example")
    d.in_outlook()
    return d.result()


geoeffnet.clear()
d = s.material_anfragen(dialog=ohne_lieferant, ausfuehren=outlook_fehlt)
assert d.ergebnis == "eml" and "nicht ansteuern" in d.meldung and geoeffnet and geoeffnet[0].suffix == ".eml"
mail = email.message_from_bytes(geoeffnet[0].read_bytes(), policy=policy.default)
assert mail["To"] == "einkauf@rohr.example" and mail["X-Unsent"] == "1"
assert "Rundrohr Ø 42,4 x 2" in mail.get_body().get_content() and "Quadratrohr" not in mail.get_body().get_content()
assert not list(mail.iter_attachments())
pfad = ma.eml(tmp / "mit.eml", "a@b.example", "Test", "Text", [tmp / "Z-100.pdf"])
anh = list(email.message_from_bytes(pfad.read_bytes(), policy=policy.default).iter_attachments())
assert [x.get_filename() for x in anh] == ["Z-100.pdf"] and anh[0].get_content() == b"%PDF-1.4 Zeichnung 100"
assert ma.outlook_oeffnen("a", "b", "c") == (False, "Outlook gibt es nur unter Windows.") or sys.platform == "win32"
ok("M3 Ohne Outlook: E-Mail-Datei als Entwurf (X-Unsent) mit Empfänger und Text, geöffnet; eml kann weiter Anhänge")

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
con.execute("PRAGMA user_version=26")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert len(db2.positionen(a)) == 4 and db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("M4 Nur Kundenmaterial: keine Anfrage; Datei mit Schema 26 öffnet, Sicherung vorher")

# ------------------------------------------------------------------ Z Frühere Zeichnungsablage einmalig löschen (Freigabe 1b)
db3 = Datenbank(alt)
if "dokumente" not in {r[1] for r in db3.con.execute("PRAGMA table_info(positionen)")}:
    db3.con.execute("ALTER TABLE positionen ADD COLUMN dokumente TEXT")
db3.einstellung_setzen("zeichnungen_entfernt", None)
ablage = tmp / "Ablage2"
o = ablage / "A-2026-0100"
o.mkdir(parents=True)
(o / "Z-100.pdf").write_bytes(b"x")
(o / "Z-100 (2).pdf").write_bytes(b"y")
o2 = ablage / db3.angebot(b)["nummer"]
o2.mkdir()
(o2 / "Z-9.pdf").write_bytes(b"z")
(o2 / "Angebot.pdf").write_bytes(b"bleibt")           # nicht eingetragen: bleibt liegen
(ablage / "fremd.pdf").write_bytes(b"bleibt")
pos = db3.positionen(a)
db3.con.execute("UPDATE positionen SET dokumente=? WHERE id=?", ('["Z-100.pdf", "Z-100 (2).pdf"]', pos[0]["id"]))
db3.con.execute("UPDATE positionen SET dokumente=? WHERE id=?", ('["../fremd.pdf", "fehlt.pdf"]', pos[1]["id"]))
db3.con.execute("UPDATE positionen SET dokumente=? WHERE id=?", ('["Z-9.pdf"]', db3.positionen(b)[0]["id"]))
db3.con.commit()
assert db3.zeichnungen_entfernen(ablage) == 3
assert not o.exists() and not (o2 / "Z-9.pdf").exists() and (o2 / "Angebot.pdf").is_file()
assert (ablage / "fremd.pdf").is_file()
assert db3.con.execute("SELECT COUNT(*) FROM positionen WHERE dokumente IS NOT NULL").fetchone()[0] == 0
(o2 / "Z-9.pdf").write_bytes(b"neu")
assert db3.zeichnungen_entfernen(ablage) == 0 and (o2 / "Z-9.pdf").is_file()        # nur einmal
db3.schliessen()
ok("Z Frühere Zeichnungen: eingetragene Dateien gelöscht, leerer Ordner entfernt, Fremdes bleibt, nur einmal")
print("OK: Materialanfrage")
