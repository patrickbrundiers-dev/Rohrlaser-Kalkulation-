"""Gemeinsamen Ordner ausbauen, Paket B (Patrick 31.10.2026): Lebenszeichen, Sofort-Schreiben, Übersicht Kollegen.

Prüft: das Lebenszeichen (Rohrlaser_<K>/online.json) wird erst nach dem ersten Abgleich und nur in den eigenen Ordner
geschrieben, nennt die geöffneten Angebote; Kollegen lesen es und sehen „da“ höchstens 2 Minuten nach dem letzten
Lebenszeichen, beim Beenden sofort „nicht mehr da“; geöffnete Angebote kommen aus dem Lebenszeichen (ohne es wie
bisher aus der Hauptdatei); der Takt schreibt Änderungen, sobald die Eingabe einen Takt lang ruht, nicht aber nur
wegen gelesener Lebenszeichen; der Abgleich läuft als Vorgabe jede Minute; die Übersicht der Kollegen zeigt Status,
Version, geöffnete Angebote und offene Vorgänge, das Menü hat den Eintrag.

Aufruf: python tests/test_kollegen_puls.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import kollegen_dialog, teilen, teilen_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


pb, mk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK")
assert teilen_fenster.takt_ms(pb) == 60_000
assert not teilen.lebenszeichen_schreiben(pb, {})            # vor dem ersten Abgleich: kein eigener Ordner
assert not (gemeinsam / "Rohrlaser_PB").exists()
a1 = pb.angebot_neu(dict(kunde="Kunde A", datum="2026-10-20"))
n1 = pb.angebot(a1)["nummer"]
teilen.abgleichen(pb)
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
teilen.abgleichen(pb)
assert teilen.lebenszeichen_schreiben(pb, {n1: "2026-10-31T09:00"})
d = json.loads((gemeinsam / "Rohrlaser_PB" / teilen.ONLINE_DATEI).read_text(encoding="utf-8"))
assert d["kuerzel"] == "PB" and d["offen"] == {n1: "2026-10-31T09:00"} and not d["ende"]
assert set(teilen.andere_dateien(mk)) == {"PB"}
ok("Lebenszeichen erst nach dem ersten Abgleich, im eigenen Ordner, mit geöffneten Angeboten; Vorgabe 1 min")

puls = teilen.lebenszeichen_lesen(mk)
assert puls["PB"]["online"] and puls["PB"]["vor_s"] < 10, puls
assert teilen.kollegen_offen(mk) == {n1: ("PB", "2026-10-31T09:00")}
assert teilen.offen_bei(mk, n1)[0] == "PB"
spaeter = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=teilen.ONLINE_S + 5)
assert not teilen.lebenszeichen(mk, spaeter)["PB"]["online"]
teilen.lebenszeichen_schreiben(pb, {}, ende=True)
teilen.lebenszeichen_lesen(mk)
assert not teilen.lebenszeichen(mk)["PB"]["online"] and teilen.kollegen_offen(mk) == {}
ok("Kollege liest das Lebenszeichen: da (höchstens 2 min alt), geöffnete Angebote; beim Beenden gleich weg")

# Ohne Lebenszeichen (ältere Version beim Kollegen): wie bisher aus der Hauptdatei
(gemeinsam / "Rohrlaser_PB" / teilen.ONLINE_DATEI).unlink()
teilen.lebenszeichen_lesen(mk)
m = dict(mk.einstellung("teilen_mitarbeiter"))
m["PB"] = dict(m["PB"], offen={n1: "2026-10-31T08:00"}, stand=datetime.datetime.now().isoformat(timespec="seconds"))
mk.einstellung_setzen("teilen_mitarbeiter", m)
assert teilen.kollegen_offen(mk) == {n1: ("PB", "2026-10-31T08:00")}
ok("Ohne Lebenszeichen: geöffnete Angebote wie bisher aus der Hauptdatei (20 min)")

# Fremden Ordner nicht beschreiben (Kürzel gehört einem anderen Arbeitsplatz)
fremd = arbeitsplatz("Fremd", "PB")
assert not teilen.lebenszeichen_schreiben(fremd, {})
ok("Gehört das Kürzel einem anderen Arbeitsplatz, schreibt dieser kein Lebenszeichen hinein")

# ---------------------------------------------------------------- Takt: Lebenszeichen und Sofort-Schreiben
f_pb, f_mk = Hauptfenster(pb, tmp, stumm=True), Hauptfenster(mk, tmp, stumm=True)
t = 1000.0
erg = teilen_fenster.puls(f_pb, t)
assert erg["lebenszeichen"] and not erg["geschrieben"]
teilen_fenster.puls(f_mk, t)
assert teilen.lebenszeichen_lesen(pb)["MK"]["online"]
haupt = gemeinsam / "Rohrlaser_PB" / "haupt.sqlite"
vorher = haupt.stat().st_mtime_ns
erg = teilen_fenster.puls(f_pb, t + 15)                  # nichts geändert, Lebenszeichen noch frisch
assert not erg["lebenszeichen"] and not erg["geschrieben"]
teilen_fenster.puls(f_mk, t + 31)                        # MK meldet sich wieder: PB liest das, ist keine Änderung
erg = teilen_fenster.puls(f_pb, t + 31)
assert erg["lebenszeichen"] and not erg["geschrieben"]
erg = teilen_fenster.puls(f_pb, t + 46)
assert not erg["geschrieben"] and haupt.stat().st_mtime_ns == vorher, "gelesene Lebenszeichen sind keine Änderung"
pb.einstellung_setzen("gewinn", 13)                      # eine Eingabe
erg = teilen_fenster.puls(f_pb, t + 61)                  # gerade geändert: erst warten, ob noch mehr kommt
assert not erg["geschrieben"]
erg = teilen_fenster.puls(f_pb, t + 76)                  # Eingabe ruht seit einem Takt: gleich ablegen
assert erg["geschrieben"] and haupt.stat().st_mtime_ns != vorher
erg = teilen_fenster.puls(f_pb, t + 91)
assert not erg["geschrieben"]
ok("Takt: Lebenszeichen alle 30 s; Änderungen gleich ablegen, sobald die Eingabe ruht; Lebenszeichen zählen nicht")

# ---------------------------------------------------------------- Übersicht Kollegen
teilen.notiz_senden(pb, "MK", "Bitte Preis prüfen", None, None)
teilen.lebenszeichen_schreiben(mk, {"2026-00099": "2026-10-31T09:10"})
teilen.lebenszeichen_lesen(pb)
z = {d["kuerzel"]: d for d in kollegen_dialog.zeilen(pb)}
assert list(z)[0] == "PB" and z["PB"]["ich"] and z["PB"]["werte"][2] == "● hier"
assert z["MK"]["online"] and z["MK"]["werte"][2] == "● da" and z["MK"]["werte"][1] == "Martin"
assert z["MK"]["werte"][7] == "2026-00099" and z["MK"]["werte"][8] == "1", z["MK"]["werte"]
teilen.lebenszeichen_schreiben(mk, {}, ende=True)
teilen.lebenszeichen_lesen(pb)
z = {d["kuerzel"]: d for d in kollegen_dialog.zeilen(pb)}
assert z["MK"]["werte"][2] == "zuletzt gerade eben" and not z["MK"]["online"]
assert teilen.zuletzt_text(600) == "vor 10 min" and teilen.zuletzt_text(3 * 86400) == "vor 3 Tagen"
d = f_pb.kollegen_zeigen()
assert d.liste.rowCount() == 2 and "1 Kollegen" in d.kopf.text()
d.liste.selectRow(1)
assert d.notiz.isEnabled()
d.liste.selectRow(0)
assert not d.notiz.isEnabled()
d.close()
assert "Kollegen im gemeinsamen Ordner …" in [a.text() for a in f_pb.menuBar().actions()[0].menu().actions()]
ok("Übersicht Kollegen: eigener Platz oben, da/zuletzt, geöffnete Angebote, offene Vorgänge; Menüeintrag")

print("OK: Gemeinsamen Ordner ausbauen, Paket B (Lebenszeichen, Sofort-Schreiben, Übersicht Kollegen)")
