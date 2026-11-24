"""Gemeinsamen Ordner ausbauen, Teil 2 Paket E (Patrick 01.11.2026): weiche Sperre und Windows-Meldung.

Prüft: eine selbst geänderte Stammdaten-Zeile steht gleich im Lebenszeichen; der Kollege erkennt sie (gleiche Zeile ja,
andere Zeile nein, nach 2 Minuten oder nach dem Beenden nicht mehr); in der Stammdaten-Tabelle fragt das Programm
„trotzdem ändern?“ – nein lässt den Wert stehen, ja ändert und meldet die Zeile selbst; Windows-Meldung bei Notizen,
Übergaben und Anfragen, nicht im Vordergrund und nicht bei abgeschalteter Einstellung; fällige Wiedervorlagen einmal je
Tag; Klick auf die Meldung öffnet das Angebot.

Aufruf: python tests/test_sperre_meldung.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import fenster as fenster_modul  # noqa: E402
from rohrlaser import teilen, teilen_fenster  # noqa: E402
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
pb.neu("kunden", dict(kundennr="10042", name="Muster GmbH"))
pb.neu("kunden", dict(kundennr="10043", name="Weber KG"))
teilen.abgleichen(pb)
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
uid1, uid2 = (pb.con.execute("SELECT uid FROM kunden WHERE kundennr=?", (n,)).fetchone()[0] for n in ("10042", "10043"))

# ---- Kern
assert teilen.zeile_merken(pb, "kunden", uid1)
bei = teilen.zeile_bei_kollegen(mk, "kunden", uid1)
assert bei and bei[0] == "PB" and bei[1] < 60, bei
assert teilen.zeile_bei_kollegen(mk, "kunden", uid2) is None
spaeter = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=teilen.ZEILE_S + 30)
assert teilen.zeile_bei_kollegen(mk, "kunden", uid1, jetzt_=spaeter) is None
ok("Geänderte Zeile im Lebenszeichen: Kollege erkennt sie, andere Zeile nicht, nach 2 Minuten nicht mehr")
teilen.lebenszeichen_schreiben(pb, {}, ende=True)
setattr(mk, teilen.ONLINE_GELESEN, 0)
assert teilen.zeile_bei_kollegen(mk, "kunden", uid1) is None
ok("Nach dem Beenden keine Sperre mehr")

# ---- Stammdaten-Tabelle fragt
teilen.zeile_merken(pb, "kunden", uid1)
setattr(mk, teilen.ONLINE_GELESEN, 0)
f = Hauptfenster(mk, tmp, stumm=True)
seite = next(s for s in f.seiten if getattr(s, "modell", None) is not None and s.modell.t.name == "kunden")
m = seite.modell
zeile = next(r for r, z in enumerate(m.daten) if z.get("kundennr") == "10042")
spalte = next(c for c, (art, fd) in enumerate(m.spalten) if art == "feld" and fd.name == "name")
fenster_modul.ZEILE_ANTWORT = False
assert not m.setData(m.index(zeile, spalte), "Muster AG")
assert mk.con.execute("SELECT name FROM kunden WHERE uid=?", (uid1,)).fetchone()[0] == "Muster GmbH"
ok("Weiche Sperre: „nein“ lässt den Wert stehen")
fenster_modul.ZEILE_ANTWORT = True
assert m.setData(m.index(zeile, spalte), "Muster AG")
assert mk.con.execute("SELECT name FROM kunden WHERE uid=?", (uid1,)).fetchone()[0] == "Muster AG"
assert f"kunden|{uid1}" in getattr(mk, teilen.ZEILEN)
setattr(pb, teilen.ONLINE_GELESEN, 0)
assert teilen.zeile_bei_kollegen(pb, "kunden", uid1)[0] == "MK"
ok("„Trotzdem ändern“ ändert und meldet die Zeile selbst an die Kollegen")
fenster_modul.ZEILE_ANTWORT = None
zeile2 = next(r for r, z in enumerate(m.daten) if z.get("kundennr") == "10043")
assert m.setData(m.index(zeile2, spalte), "Weber GmbH")
ok("Andere Zeile: ohne Rückfrage")

# ---- Windows-Meldung
aid = mk.angebot_neu(dict(kunde="Stahlbau Nord", datum="2026-10-30"))
nummer = mk.angebot(aid)["nummer"]
bericht = dict(notizen=[dict(von="PB", nummer=nummer, notiz="Bitte Preis prüfen", faellig=None)], uebernommen=[],
               abgelehnt=[], anfragen=[])
f.meldung_immer = False
f.show()
f.activateWindow()
app.processEvents()
if f.isActiveWindow():
    teilen_fenster._vorgaenge_zeigen(f, bericht, leise=True)
    assert not f.__dict__.get("windows_meldungen")
    ok("Programm im Vordergrund: keine Windows-Meldung")
f.meldung_immer = True
teilen_fenster._vorgaenge_zeigen(f, bericht, leise=True)
titel, text, ziel = f.windows_meldungen[-1]
assert "Bitte Preis prüfen" in text and ziel == nummer
ok("Notiz eines Kollegen: Windows-Meldung mit Angebot")
mk.einstellung_setzen("teilen_meldung", "nein")
n = len(f.windows_meldungen)
teilen_fenster._vorgaenge_zeigen(f, bericht, leise=True)
assert len(f.windows_meldungen) == n
mk.einstellung_setzen("teilen_meldung", "ja")
ok("Abgeschaltet: keine Windows-Meldung")
bericht2 = dict(bericht, notizen=[], anfragen=[dict(von="PB", nummer=nummer, id="x")])
f.stumm = True
teilen_fenster._vorgaenge_zeigen(f, bericht2, leise=True)
assert "übernehmen" in f.windows_meldungen[-1][1]
ok("Anfrage eines Kollegen: Windows-Meldung")

heute = datetime.date.today()
mk.einstellung_setzen(teilen.NOTIZEN, [dict(id="n1", von="PB", nummer=nummer, notiz="Nachfassen", zeit="",
                                            faellig=heute.isoformat(), erledigt=False),
                                       dict(id="n2", von="PB", nummer=None, notiz="Morgen",
                                            faellig=(heute + datetime.timedelta(days=1)).isoformat(), erledigt=False)])
assert teilen_fenster.wiedervorlagen_melden(f, heute) == 1
assert "Nachfassen" in f.windows_meldungen[-1][1]
assert teilen_fenster.wiedervorlagen_melden(f, heute) == 0
assert teilen_fenster.wiedervorlagen_melden(f, heute + datetime.timedelta(days=1)) == 2
ok("Fällige Wiedervorlagen einmal je Tag")

f._meldung_ziel = nummer
teilen_fenster.meldung_geklickt(f)
assert aid in f.offen
ok("Klick auf die Meldung öffnet das Angebot")

print("\nAlle Prüfungen bestanden.")
