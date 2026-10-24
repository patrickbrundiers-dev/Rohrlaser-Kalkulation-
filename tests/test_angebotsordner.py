"""Prüft den Ordner je Angebot (angebotsordner.py, Patrick 24.10.2026, Freigabe 1a 2a 3b 4a 5a 6a 7a 8a 9a):
- O1 Ordnername 'Nummer Kunde' ohne verbotene Zeichen, vorhandener Ordner gleicher Nummer wird weiterverwendet
- O2 Fassungen als Unterordner 'Fassung 2' im Ordner der Grundnummer
- O3 Ausgaben (Kalkulation, CSV, Werkstattpapiere) landen im Ordner, Nummer bleibt vorne im Dateinamen
- O4 vorläufige Nummer: Ordner und Dateien werden nach dem Endgültig-Werden umbenannt
- O5 lose Dateien aus der Zeit vor den Ordnern werden einmalig verschoben (vorhandene Ziele bleiben unberührt)
- O6 STEP-Dateien kopieren: Unterordner STEP, gleiche Datei nicht doppelt, gleicher Name anderer Inhalt -> (2)
- O7 Knopf „Ordner öffnen“ (Übersicht mit/ohne Markierung)

Aufruf: python tests/test_angebotsordner.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebotsordner as ao, nummern  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())

# ------------------------------------------------------------------ O1 Ordnername
assert ao.ordnername("2026-00042", 'Stahl/Bau "Nord" GmbH.') == "2026-00042 Stahl_Bau _Nord_ GmbH"
assert ao.ordnername("2026-00042", "") == "2026-00042"
assert len(ao.ordnername("2026-00042", "x" * 200)) == len("2026-00042 ") + ao.KUNDE_MAX
abl = tmp / "A1"
abl.mkdir()
o = ao.ordner(abl, dict(nummer="2026-00042", kunde="Müller"))
assert o == abl / "2026-00042 Müller" and o.is_dir()
assert ao.ordner(abl, dict(nummer="2026-00042", kunde="Müller & Söhne")) == o       # Kunde geändert: gleicher Ordner
assert ao.ordner(abl, dict(nummer="2026-00042-2", kunde="Müller")) != o               # ohne fassung_basis: eigenes Angebot
assert ao.finden(abl, "2026-0004") is None                                            # kein Treffer auf Teilnummer
ok("O1 Ordnername 'Nummer Kunde', vorhandener Ordner gleicher Nummer bleibt")

# ------------------------------------------------------------------ O2 Fassungen
assert ao.teile(dict(nummer="2026-00042-3", fassung_basis="2026-00042")) == ("2026-00042", 3)
assert ao.teile(dict(nummer="2026-00042", fassung_basis=None)) == ("2026-00042", None)
f = ao.ordner(abl, dict(nummer="2026-00042-2", fassung_basis="2026-00042", kunde="Müller"))
assert f == o / "Fassung 2" and f.is_dir(), f
ok("O2 Fassung als Unterordner 'Fassung 2'")

# ------------------------------------------------------------------ O3 Ausgaben im Fenster
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
ablage = tmp / "Ablage"
db.einstellung_setzen("ablageordner", str(ablage))
a = db.angebot_neu(dict(nummer="2026-00007", kunde="Stahlbau Ostermann", maschine="T11"))
profil = next(z["profil_id"] for z in db.zeilen("profile") if z["profil_id"].startswith("RE "))
werkstoff = db.zeilen("werkstoffe")[0]["werkstoff_id"]
db.position_neu(a, dict(pos=1, artikel="Rohr-1", profil_id=profil, werkstoff_id=werkstoff, laenge=1200, stueck=4,
                        schneidweg=600, einstiche=2))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
ziel = ablage / "2026-00007 Stahlbau Ostermann"
k = s.kalkulation_pdf()
assert k == ziel / "2026-00007 Kalkulation.pdf" and k.is_file(), k
c = s.csv_export()
assert c == [ziel / "2026-00007 Angebotskopf.csv", ziel / "2026-00007 Angebotspositionen.csv"], c
w = s.werkstatt_pdf()
assert w.parent == ziel and w.name.startswith("2026-00007 "), w
ok("O3 Kalkulation, CSV und Werkstattpapiere im Ordner des Angebots")

fa = db.angebot_fassung(a)
sf = fenster.angebot_oeffnen(fa)
assert sf.optimieren()
kf = sf.kalkulation_pdf()
assert kf == ziel / "Fassung 2" / "2026-00007-2 Kalkulation.pdf", kf
ok("O3 neue Fassung schreibt in 'Fassung 2'")

# ------------------------------------------------------------------ O4 vorläufige Nummer
(tmp / "Gemeinsam").mkdir()
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("teilen_ordner", str(tmp / "Gemeinsam"))
v = db.angebot_neu(dict(nummer="V-PB-1", kunde="Kunde V"))
sv = fenster.angebot_oeffnen(v)
vordner = fenster.angebot_ordner(sv.kopf)
assert vordner == ablage / "V-PB-1 Kunde V"
(vordner / "V-PB-1 Kalkulation.pdf").write_text("x")
(vordner / "Angebot_V-PB-1.zip").write_text("x")
umn = nummern.endgueltig(db, v)
assert umn and umn[0][0] == "V-PB-1", umn
neu = umn[0][1]
assert db.einstellung(ao.UMNUMMERIERT) == [["V-PB-1", neu]]
sv.neu_laden()
o4 = fenster.angebot_ordner(db.angebot(v))
assert o4 == ablage / f"{neu} Kunde V" and not vordner.exists(), (o4, list(ablage.iterdir()))
assert (o4 / f"{neu} Kalkulation.pdf").is_file() and (o4 / f"Angebot_{neu}.zip").is_file(), list(o4.iterdir())
assert db.einstellung(ao.UMNUMMERIERT) == []
ok("O4 vorläufige Nummer: Ordner und Dateien umbenannt")

# ------------------------------------------------------------------ O5 lose Dateien verschieben
(ablage / "2026-00007 Angebot.pdf").write_text("alt")
(ablage / "2026-00007-2 Angebot.pdf").write_text("alt2")
(ablage / "2026-00007 Kalkulation.pdf").write_text("doppelt")        # gibt es im Ordner schon: bleibt liegen
(ablage / "Notizen.txt").write_text("fremd")
(ablage / "2026-99999 Angebot.pdf").write_text("ohne Angebot")
assert fenster.lose_dateien_verschieben() == 2
assert (ziel / "2026-00007 Angebot.pdf").read_text() == "alt"
assert (ziel / "Fassung 2" / "2026-00007-2 Angebot.pdf").read_text() == "alt2"
assert (ablage / "2026-00007 Kalkulation.pdf").is_file() and (ziel / "2026-00007 Kalkulation.pdf").read_bytes()[:4] == b"%PDF"
assert (ablage / "Notizen.txt").is_file() and (ablage / "2026-99999 Angebot.pdf").is_file()
(ablage / "2026-00007 Nachkalkulation.pdf").write_text("später")
assert fenster.lose_dateien_verschieben() == 0          # einmalig je Ablage
assert (ablage / "2026-00007 Nachkalkulation.pdf").is_file()
ok("O5 lose Dateien einmalig in den Ordner ihres Angebots verschoben")

# ------------------------------------------------------------------ O6 STEP kopieren
quelle = tmp / "Kunde"
quelle.mkdir()
(quelle / "Teil.stp").write_text("A")
(quelle / "Rahmen.step").write_text("B")
st = ziel / ao.STEP_ORDNER
assert ao.step_kopieren([quelle / "Teil.stp", quelle / "Rahmen.step"], st) == (2, [])
assert ao.step_kopieren([quelle / "Teil.stp"], st) == (0, [])           # gleiche Datei: nicht doppelt
(quelle / "Teil.stp").write_text("A geändert")
assert ao.step_kopieren([quelle / "Teil.stp"], st) == (1, [])
assert (st / "Teil (2).stp").read_text() == "A geändert" and (st / "Teil.stp").read_text() == "A"
anzahl, fehler = ao.step_kopieren([quelle / "fehlt.stp"], st)
assert anzahl == 0 and len(fehler) == 1
zeile = s._step_kopieren([str(quelle / "Rahmen.step")])
assert "0 STEP-Datei(en)" in zeile and str(st) in zeile, zeile
assert db.einstellung("step_kopieren") == "nein"
ok("O6 STEP-Dateien in den Unterordner STEP, keine Überschreibung")

# ------------------------------------------------------------------ O7 Ordner öffnen
liste = fenster.angebote
liste.neu_laden()
liste.ansicht.clearSelection()
assert liste.ordner_oeffnen() is None           # ohne Markierung: die ganze Ablage
assert fenster.angebot_ordner_oeffnen(db.angebot(a)) == ziel
assert fenster.angebot_ordner_oeffnen(None) is None
ok("O7 Ordner öffnen zeigt den Ordner des Angebots")

fenster.close()
print("Alle Prüfungen bestanden.")
