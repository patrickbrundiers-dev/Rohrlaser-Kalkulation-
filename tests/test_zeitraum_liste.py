"""Prüft den Zeitraum der Angebotsliste (Patrick 29.10.2026): nur Angebote mit Datum oder Änderung in den letzten
N Tagen; fällige Wiedervorlagen, nicht versendete Aufträge und geöffnete Angebote bleiben sichtbar, die Suche findet
alle, Hinweis „N ältere ausgeblendet“, Vorgabe aus der Einstellung 'angebote_zeitraum' (nur dieser Arbeitsplatz).

Aufruf: python tests/test_zeitraum_liste.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG, ZEITRAUM  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("gueltigkeit", 30)
heute = datetime.date.today()


def tag(n):
    return (heute - datetime.timedelta(days=n)).isoformat()


def anlegen(name, alter, vorgang=None, geaendert=None, liefertermin=None, schein=None):
    a = db.angebot_neu(dict(kunde=name, kundennr=name, datum=tag(alter)))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                            stueck=5))
    with db.con:
        db.con.execute("UPDATE angebote SET vorgang=?, geaendert=?, liefertermin=?, palettenschein=? WHERE id=?",
                       (vorgang, (geaendert if geaendert is not None else tag(alter)) + "T08:00:00", liefertermin,
                        json.dumps(schein) if schein else None, a))
    return a


ids = dict(
    neu=anlegen("Neu", 0),
    alt=anlegen("Alt abgelehnt", 400, "Abgelehnt"),
    geaendert=anlegen("Alt geändert", 400, "Abgelehnt", geaendert=tag(0)),
    wv=anlegen("Alt verschickt", 400, "Verschickt"),                 # Gültigkeit vorbei: Wiedervorlage fällig
    auftrag=anlegen("Auftrag offen", 400, "Beauftragt", liefertermin=tag(10)),
    auftrag_alt=anlegen("Auftrag alt", 400, "Beauftragt", liefertermin=tag(200)),       # Versand: automatisch archiviert
    versendet=anlegen("Auftrag versendet", 400, "Beauftragt", liefertermin=tag(10), schein={"status": ["Versendet"]}),
    entwurf=anlegen("Alt Entwurf", 400),
    offen=anlegen("Alt geöffnet", 400, "Abgelehnt"),
    grenze=anlegen("Grenze", 150, "Abgelehnt"),                       # genau 150 Tage: noch im Zeitraum
)
AUS = {"alt", "auftrag_alt", "versendet", "entwurf"}

# Einstellung: Vorgabe 150 Tage, nur dieser Arbeitsplatz, Auswahl mit allen Stufen
e = EINSTELLUNG["angebote_zeitraum"]
assert e.vorgabe == "150 Tage" and e.gruppe == "Angebot" and "angebote_zeitraum" in teilen.LOKAL
assert list(ZEITRAUM) == ["30 Tage", "60 Tage", "100 Tage", "150 Tage", "365 Tage", "Alle"]
ok("Einstellung angebote_zeitraum: Vorgabe 150 Tage, Gruppe Angebot, nicht geteilt")

# Datenbank: ohne Zeitraum wie bisher alle, mit Zeitraum nur Zeitraum + mögliche Ausnahmen
assert len(db.angebote()) == len(ids) and "_im_zeitraum" not in db.angebote()[0]
mit = {z["id"]: z for z in db.angebote(seit=tag(150))}
assert ids["alt"] not in mit and ids["offen"] not in mit                      # abgelehnt: gar nicht geladen
assert {ids[k] for k in ("neu", "geaendert", "grenze")} == {i for i, z in mit.items() if z["_im_zeitraum"]}
assert len(db.angebote("Alt abgelehnt", seit=tag(150))) == 1                  # Suche: immer alle
assert db.angebote_anzahl() == len(ids)
ok("db.angebote(seit=…) lädt nur Zeitraum und mögliche Ausnahmen; Suche ignoriert den Zeitraum")

fenster = Hauptfenster(db, tmp, stumm=True)
au = fenster.angebote
fenster.offen[ids["offen"]] = object()          # geöffnetes Angebot (sonst AngebotSeite)
au.neu_laden()
assert au.zeitraum_filter.currentText() == "150 Tage"


def sichtbar():
    return {k for k, i in ids.items() if i in {z["id"] for z in au.modell.zeilen}}


assert sichtbar() == set(ids) - AUS, sichtbar()
assert not au.zeitraum_hinweis.isHidden() and "4 ältere Angebote ausgeblendet" in au.zeitraum_hinweis.text()
ok("150 Tage: neu, geändert, Wiedervorlage, offener Auftrag, geöffnet sichtbar; 4 ältere ausgeblendet mit Hinweis")

au.suche.setText("Alt abgelehnt")
au.neu_laden()
assert sichtbar() == {"alt"} and au.zeitraum_hinweis.isHidden()
au.suche.setText("")
ok("Suche findet auch ausgeblendete Angebote")

au.zeitraum_hinweis.linkActivated.emit("alle")              # „Alle zeigen“
assert au.zeitraum_filter.currentText() == "Alle" and sichtbar() == set(ids) and au.zeitraum_hinweis.isHidden()
au.zeitraum_filter.setCurrentText("30 Tage")
assert "grenze" not in sichtbar() and "neu" in sichtbar()
ok("Auswahl im Fenster: Alle zeigen, 30 Tage")

db.einstellung_setzen("angebote_zeitraum", "Alle")      # geänderte Einstellung gilt beim nächsten Neuladen
au.neu_laden()
assert au.zeitraum_filter.currentText() == "Alle" and sichtbar() == set(ids)
ok("Auswahl folgt der Einstellung")

# Vorgang-Filter wirkt zusätzlich: Beauftragt mit 150 Tagen zeigt nur den offenen Auftrag
db.einstellung_setzen("angebote_zeitraum", "150 Tage")
au.vorgang_filter.setCurrentText("Beauftragt")
assert sichtbar() == {"auftrag"}
au.vorgang_filter.setCurrentText("Alle Angebote")
ok("Vorgang-Filter und Zeitraum zusammen")

# Laufzeit: 3.000 alte Angebote (außer Zeitraum) belasten die Liste kaum
with db.con:
    db.con.executemany("INSERT INTO angebote (nummer, kunde, datum, geaendert, vorgang) VALUES (?, ?, ?, ?, ?)",
                       [(f"A-{n}", "Masse", tag(500), tag(500), "Abgelehnt") for n in range(3000)])
t = time.perf_counter()
au.neu_laden()
dauer = time.perf_counter() - t
assert sichtbar() == set(ids) - AUS and "3.004 ältere Angebote ausgeblendet" in au.zeitraum_hinweis.text()
print(f"       Liste mit 3.000 ausgeblendeten Angeboten: {dauer * 1000:.0f} ms")
ok("Viele alte Angebote: ausgeblendet, Hinweis mit Tausenderpunkt")
print("Alles in Ordnung.")
