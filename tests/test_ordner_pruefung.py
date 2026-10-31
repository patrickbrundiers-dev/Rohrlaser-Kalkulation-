"""Gemeinsamen Ordner ausbauen, Paket A (Patrick 31.10.2026): Uhr des Ordners, Konfliktkopien, Ordner prüfen.

Prüft: Konfliktkopien werden am Namen erkannt (OneDrive „haupt-PC01.sqlite“, „00042 (1).nummer“, Dropbox
„(Konflikt-Kopie …)“, Kopie eines ganzen Mitarbeiter-Ordners), nicht aber normale Dateien, Zwischendateien oder
ähnliche Kürzel; eigene kommen beim Schreiben in den lokalen Ordner Konfliktkopien, fremde und doppelt reservierte
Nummern bleiben und erscheinen in der Prüfung; die Uhr wird beim Schreiben gemessen, eine Abweichung erst nach zwei
übereinstimmenden Messungen und ab 5 s herausgerechnet (nicht über einen Tag), die Zeitpunkte der eigenen Änderungen
verschieben sich entsprechend und die Info nennt die Abweichung; die Prüfung meldet ältere Versionen, lange nicht
abgeglichene Kollegen, falsche Uhr, belegtes Kürzel, vorläufige Nummern und Reste; die Statuszeile nennt die
wichtigsten Warnungen; das Fenster zeigt die Befunde.

Aufruf: python tests/test_ordner_pruefung.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import austausch, ordner_pruefung, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


kv = austausch.kopie_von
P = Path
assert kv(P("haupt-PC01.sqlite"), ["haupt.sqlite"]) == "haupt.sqlite"
assert kv(P("haupt (1).sqlite"), ["haupt.sqlite"]) == "haupt.sqlite"
assert kv(P("haupt (Konflikt-Kopie von PC 2026-10-31).sqlite"), ["haupt.sqlite"]) == "haupt.sqlite"
assert kv(P("Angebote_2026-10-PC01-2.sqlite"), ["Angebote_2026-10.sqlite"]) == "Angebote_2026-10.sqlite"
assert kv(P("00042-PC02.nummer"), ["00042.nummer", "00043.nummer"]) == "00042.nummer"
assert kv(P("Rohrlaser_PB-PC01"), ["Rohrlaser_PB"]) == "Rohrlaser_PB"
assert kv(P("haupt-PC01.sqlite"), ["Angebote_2026-10.sqlite"]) is None        # ohne Original keine Kopie
assert kv(P("Angebote_2026-10.sqlite"), ["Angebote_2026-1.sqlite"]) is None
assert kv(P("Rohrlaser_PBX"), ["Rohrlaser_PB"]) is None
assert kv(P("Rohrlaser_PB.sqlite"), ["Rohrlaser_PB"]) is None                 # Format 1 neben Format 2
assert kv(P("haupt.sqlite.1234.neu"), ["haupt.sqlite"]) is None               # Zwischendatei
assert kv(P("haupt.sqlite"), ["haupt.sqlite"]) is None
ok("Konfliktkopien am Namen erkannt (OneDrive, SharePoint, Dropbox, Ordnerkopie), normale Dateien nicht")

tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


pb = arbeitsplatz("Patrick", "PB")
pb.angebot_neu(dict(kunde="Kunde A", datum="2026-10-10"))
teilen.abgleichen(pb)
mk = arbeitsplatz("Martin", "MK")
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
teilen.abgleichen(pb)
assert (gemeinsam / "Rohrlaser_PB" / austausch.UHR_DATEI).is_file()
v = teilen.uhr_abweichung(pb)
assert v is not None and abs(v) < 3, v
assert teilen.uhr_versatz(pb) == 0
info = teilen.info_lesen(gemeinsam / "Rohrlaser_PB")
assert "uhr_abweichung" in info and info["uhr_versatz"] == 0, info
assert set(teilen.andere_dateien(mk)) == {"PB"}         # Prüfdatei stört das Auflisten nicht
ok("Uhr beim Schreiben gemessen (lokaler Ordner: keine Abweichung), Info nennt sie")

# ---------------------------------------------------------------- Uhr: Regeln für den Versatz
pb.einstellung_setzen(teilen.UHR, {"messungen": [-300.0]})
assert teilen.uhr_versatz(pb) == 0                       # eine Messung reicht nicht
pb.einstellung_setzen(teilen.UHR, {"messungen": [-290.0, -300.0]})
assert teilen.uhr_versatz(pb) == 0                       # nicht einig (10 s)
pb.einstellung_setzen(teilen.UHR, {"messungen": [-298.0, -300.0]})
assert teilen.uhr_versatz(pb) == -299.0
pb.einstellung_setzen(teilen.UHR, {"messungen": [3.0, 2.0]})
assert teilen.uhr_versatz(pb) == 0                       # unter 5 s
pb.einstellung_setzen(teilen.UHR, {"messungen": [200000.0, 200000.0]})
assert teilen.uhr_versatz(pb) == 0                       # über einen Tag: unglaubwürdig
assert teilen.uhr_text(-200) == "3 min 20 s vor" and teilen.uhr_text(45) == "45 s nach"
assert teilen.uhr_text(7300).startswith("2 h 1 min") and teilen.uhr_text(-3 * 86400) == "3 Tage vor"
a = datetime.datetime.fromisoformat(teilen.jetzt("PB", 3600).split("|")[0])
assert abs((a - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)).total_seconds() - 3600) < 5
ok("Versatz erst nach zwei übereinstimmenden Messungen, ab 5 s, höchstens ein Tag; Text „… vor/nach“")

# PC-Uhr von PB geht 5 min vor: die Ordner-Uhr (Zeitstempel der Prüfdatei) zeigt die echte Zeit
echt = time.time
austausch.time.time = lambda: echt() + 300
try:
    pb.einstellung_setzen(teilen.UHR, {"messungen": []})
    teilen.schreiben(pb)
    teilen.schreiben(pb)
finally:
    austausch.time.time = echt
assert abs(teilen.uhr_abweichung(pb) + 300) < 3, teilen.uhr_abweichung(pb)
assert abs(teilen.uhr_versatz(pb) + 300) < 3
pb.einstellung_setzen("gewinn", 17)                      # gemeinsame Einstellung ändern
with pb.con:
    teilen.erfassen(pb.con, teilen.jetzt("PB", teilen.uhr_versatz(pb)))
zeit = pb.con.execute("SELECT zeit FROM teilen_basis WHERE tabelle=? AND uid='gewinn'", (teilen.EINST,)).fetchone()[0]
abstand = (datetime.datetime.fromisoformat(zeit.split("|")[0]) - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)).total_seconds()
assert abs(abstand + 300) < 5, abstand
pb.einstellung_setzen(teilen.UHR, {"messungen": []})
ok("Falsche PC-Uhr: gemessen und beim Erfassen der eigenen Änderungen herausgerechnet")

# ---------------------------------------------------------------- Konfliktkopien
eigen = gemeinsam / "Rohrlaser_PB"
(eigen / "haupt-PC01.sqlite").write_bytes(b"alt")
(eigen / "Angebote_2026-10 (1).sqlite").write_bytes(b"alt")
(gemeinsam / "Rohrlaser_MK" / "haupt-NB07.sqlite").write_bytes(b"alt")
(gemeinsam / "Nummern").mkdir(exist_ok=True)
(gemeinsam / "Nummern" / "00042.nummer").write_text("2026-00042\nPB\nPC01\n", encoding="utf-8")
(gemeinsam / "Nummern" / "00042-NB07.nummer").write_text("2026-00042\nMK\nNB07\n", encoding="utf-8")
(gemeinsam / "Rohrlaser_PB-PC01").mkdir()
(gemeinsam / "Rohrlaser_PB-PC01" / "haupt.sqlite").write_bytes(b"alt")
alt = eigen / "haupt.sqlite.99.neu"
alt.write_bytes(b"x")
os.utime(alt, (time.time() - 7200, time.time() - 7200))
frisch = eigen / "haupt.sqlite.98.neu"
frisch.write_bytes(b"x")
kopien = teilen.konfliktkopien(pb)
namen = {(c["pfad"].name, c["kuerzel"], c["eigene"]) for c in kopien}
assert namen == {("haupt-PC01.sqlite", "PB", True), ("Angebote_2026-10 (1).sqlite", "PB", True),
                 ("haupt-NB07.sqlite", "MK", False), ("00042-NB07.nummer", "MK", False),
                 ("Rohrlaser_PB-PC01", "PB", True)}, namen
assert set(teilen.andere_dateien(mk)) == {"PB"}         # Ordnerkopie gilt nicht als Mitarbeiter
ok("Konfliktkopien im Ordner gefunden: eigene, fremde, doppelte Nummer, Kopie des eigenen Ordners")

befunde = ordner_pruefung.pruefen(pb)
titel = [(b["stufe"], b["titel"]) for b in befunde]
assert (ordner_pruefung.FEHLER, "Doppelte Nummer") in titel, titel
assert sum(1 for t in titel if t[1] == "Konfliktkopie") == 4, titel
assert (ordner_pruefung.HINWEIS, "Abgebrochene Schreibvorgänge") in titel
assert (ordner_pruefung.OK, "Geschwindigkeit") in titel and (ordner_pruefung.OK, "Uhr") in titel
assert (ordner_pruefung.OK, "Kürzel") in titel and (ordner_pruefung.OK, "Kollegen") in titel
assert not list(eigen.glob(austausch.TEST_DATEI))
text = ordner_pruefung.bericht_text(befunde)
assert "✗ Doppelte Nummer" in text and "Zählerstand 42" in text and "MK" in text
assert "2 doppelte" not in " ".join(ordner_pruefung.kurz(pb)) and "1 doppelte Nummer" in ordner_pruefung.kurz(pb)
ok("Prüfung: doppelte Nummer als Fehler, Kopien und Reste als Hinweis, Geschwindigkeit, Uhr, Kürzel, Kollegen")

teilen.schreiben(pb)                                     # räumt eigene Kopien und alte Zwischendateien auf
kopien = teilen.konfliktkopien(pb)
assert {c["pfad"].name for c in kopien} == {"haupt-NB07.sqlite", "00042-NB07.nummer"}, kopien
lokal = tmp / "Patrick" / "Teilen" / teilen.KOPIEN
weg_ = sorted(p.name.split("_", 1)[1] for p in lokal.iterdir())
assert weg_ == ["Rohrlaser_PB-PC01", "haupt-PC01.sqlite"], weg_      # alte Monatsdatei räumt schon die Ablage weg
assert not alt.exists() and frisch.exists()
frisch.unlink()
ok("Beim Schreiben: eigene Kopien nach Daten/Teilen/Konfliktkopien, alte Zwischendateien weg, fremde bleiben")

# ---------------------------------------------------------------- Kollegen: Version, Stand, Uhr; belegtes Kürzel
h = gemeinsam / "Rohrlaser_MK" / "haupt.sqlite"
c = sqlite3.connect(h)
with c:
    for n, w in (("version", '"0.9.100"'), ("stand", '"2026-09-01T08:00:00"'), ("uhr_abweichung", "-400"),
                 ("uhr_versatz", "-400")):
        c.execute("INSERT OR REPLACE INTO info (name, wert) VALUES (?, ?)", (n, w))
c.close()
neu = pb.angebot_neu(dict(kunde="Offline", datum="2026-10-30"))
with pb.con:
    pb.con.execute("UPDATE angebote SET nummer='V-PB-3' WHERE id=?", (neu,))
befunde = ordner_pruefung.pruefen(pb, geschwindigkeit=False)
mk_text = " ".join(b["text"] for b in befunde if b["titel"].startswith("Kollege MK"))
assert "ältere Programmversion (0.9.100)" in mk_text, mk_text
assert "nicht abgeglichen" in mk_text and "6 min 40 s vor (wird herausgerechnet)" in mk_text, mk_text
assert any(b["titel"] == "Vorläufige Nummern" and "V-PB-3" in b["text"] for b in befunde)
assert not any(b["titel"] == "Geschwindigkeit" for b in befunde)
c = sqlite3.connect(gemeinsam / "Rohrlaser_PB" / "haupt.sqlite")
with c:
    c.execute("INSERT OR REPLACE INTO info (name, wert) VALUES ('installation', '\"fremd\"')")
c.close()
befunde = ordner_pruefung.pruefen(pb, geschwindigkeit=False)
assert any(b["stufe"] == ordner_pruefung.FEHLER and b["titel"] == "Kürzel" for b in befunde)
ok("Kollegen: ältere Version, lange nicht abgeglichen, Uhr; vorläufige Nummern; belegtes Kürzel als Fehler")

leer = Datenbank(tmp / "Leer" / "rohrlaser.db")
assert ordner_pruefung.pruefen(leer)[0]["stufe"] == ordner_pruefung.FEHLER
leer.einstellung_setzen("teilen_ordner", str(tmp / "nicht_da"))
assert "Nicht erreichbar" in ordner_pruefung.pruefen(leer)[0]["text"]
assert teilen.konfliktkopien(leer) == [] and teilen.kopien_aufraeumen(leer) == 0
ok("Ohne bzw. mit nicht erreichbarem Ordner: ein Fehler, keine Ausnahme")

# ---------------------------------------------------------------- Oberfläche: Statuszeile und Fenster
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import teilen_fenster  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
pb.einstellung_setzen(teilen.UHR, {"messungen": [-200.0, -200.0]})
f = Hauptfenster(pb, tmp, stumm=True)
teilen_fenster._status_nach(f, {})
assert "PC-Uhr geht 3 min 20 s vor" in f.teilen_status.text() and "doppelte Nummer" in f.teilen_status.text()
assert "Gemeinsamen Ordner prüfen" in f.teilen_status.toolTip()
assert "Gemeinsamen Ordner prüfen …" in [a.text() for a in f.menuBar().actions()[0].menu().actions()]
d = f.ordner_pruefen()
assert d.liste.rowCount() == len(d.befunde) >= 5
assert "Fehler" in d.kopf.text() and d.oeffnen.isEnabled()
d._kopieren()
assert "Doppelte Nummer" in QApplication.clipboard().text()
d.close()
ok("Statuszeile nennt PC-Uhr und doppelte Nummer; Menü Datei → Gemeinsamen Ordner prüfen zeigt alle Befunde")

print("OK: Gemeinsamen Ordner ausbauen, Paket A (Uhr, Konfliktkopien, Ordner prüfen)")
