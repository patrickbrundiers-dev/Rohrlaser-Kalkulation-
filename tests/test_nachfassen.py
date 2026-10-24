"""Nachfassen und Wiedervorlage (Plan A9): automatische Wiedervorlage nach Tagen ohne Entscheidung, freies Datum,
Nachfassen vermerken im Versandverlauf, Filter der Angebotsliste, Startseite."""
import datetime
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import cockpit  # noqa: E402
from rohrlaser.angebot_oben import _versand_text  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


heute = datetime.date(2026, 10, 24)
z = lambda i, v, datum, versand=(), **kw: dict(id=i, vorgang=v, datum=datum, versand=list(versand), **kw)  # noqa: E731
zeilen = [z(1, "Verschickt", "2026-10-01", [dict(datum="2026-10-02", netto=10, datei="a.pdf")]),
          z(2, "Verschickt", "2026-10-01", [dict(datum="2026-10-02", netto=10, datei="a.pdf"),
                                            dict(art="nachgefasst", datum="2026-10-20", wie="Telefon")]),
          z(3, "Verschickt", "2026-10-20"),
          z(4, "Entwurf", "2026-10-01", [dict(art="wiedervorlage", datum="2026-10-10", am="2026-10-23")]),
          z(5, "Entwurf", "2026-10-01", [dict(art="wiedervorlage", datum="2026-10-10", am="2026-10-30")]),
          z(6, "Verschickt", "2026-10-01", [dict(art="wiedervorlage", datum="2026-10-10", am="2026-11-05")]),
          z(7, "Verschickt", "2026-10-01", [dict(art="wiedervorlage", datum="2026-10-10", am="2026-11-05"),
                                            dict(art="wiedervorlage", datum="2026-10-11", am=None)]),
          z(8, "Beauftragt", "2026-10-01", [dict(art="wiedervorlage", datum="2026-10-10", am="2026-10-20")]),
          z(9, "Verschickt", "2026-10-01", fremd="AB")]
w = cockpit.wiedervorlagen(zeilen, 60, heute, nachfassen=10)
ids = [x.z["id"] for x in w]
assert ids == [7, 1, 4], ids                     # 7 ohne Versanddatum: ab Angebotsdatum
assert w[1].faellig == datetime.date(2026, 10, 12) and "seit 22 Tagen ohne Antwort" in w[1].gruende[0], w[1].gruende
assert w[2].gruende == ["Wiedervorlage 23.10.2026"] and w[2].rest == -1
ok("automatisch 10 Tage nach dem Versand, Nachfassen zählt neu, Wiedervorlage von Hand ersetzt es (auch Entwurf), "
   "entfernte Wiedervorlage = wieder automatisch; Beauftragt und Kollegen nicht")
assert [x.z["id"] for x in cockpit.wiedervorlagen(zeilen, 60, heute)] == [4]
assert {x.z["id"] for x in cockpit.wiedervorlagen(zeilen, 25, heute)} == {1, 2, 4, 6, 7}     # Gültigkeit 26.10. (3 erst 14.11.)
ok("0 = aus; Gültigkeit endet bald bleibt ein Grund")

assert _versand_text(dict(art="nachgefasst", datum="2026-10-20", wie="Telefon")) == "20.10.2026: nachgefasst (Telefon)"
assert _versand_text(dict(art="wiedervorlage", datum="2026-10-20", am="2026-11-01")) == \
    "20.10.2026: Wiedervorlage am 01.11.2026"
assert "entfernt" in _versand_text(dict(art="wiedervorlage", datum="2026-10-20", am=None))
ok("Versandverlauf zeigt Nachfassen und Wiedervorlage")

# Im Programm
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
ablage = Path(tempfile.mkdtemp())
db.einstellung_setzen("ablageordner", str(ablage))
f = Hauptfenster(db, stumm=True)
geoeffnet = []
f.datei_oeffnen = geoeffnet.append
alt = (datetime.date.today() - datetime.timedelta(days=20)).isoformat()
a = beispiel_angebot.anlegen(db)
db.angebot_aendern(a, "datum", alt)
db.vorgang_setzen(a, "Verschickt")
(ablage / "Angebot.pdf").write_bytes(b"%PDF-1.4")
db.versand_merken(a, dict(datum=alt, netto=100.0, datei="Angebot.pdf"))
b = beispiel_angebot.anlegen(db)
liste = f.angebote
liste.vorgang_filter.setCurrentText("Wiedervorlage fällig")
assert [x["id"] for x in liste.modell.zeilen] == [a]
f.start.neu_laden()
assert f.start.wiedervorlage.count() == 1 and "ohne Antwort" in f.start.wiedervorlage.item(0).text()
ok("Filter „Wiedervorlage fällig“ und Startseite: 20 Tage ohne Antwort (Vorgabe 10)")

d = liste.nachfassen(a, dialog=lambda d: d.vermerken())
assert d.ergebnis == "vermerkt" and not hasattr(d, "an")             # keine E-Mail (Patrick 24.10.)
v = db.angebot(a)["versand"][-1]
assert v["art"] == "nachgefasst" and v["wie"] == "Telefon" and v["datum"] == datetime.date.today().isoformat()
assert [x["id"] for x in liste.modell.zeilen] == [] and f.start.wiedervorlage.count() == 0
d = liste.nachfassen(a, dialog=lambda d: (d.wie_auswahl.setCurrentText("persönlich"), d.vermerken()))
assert db.angebot(a)["versand"][-1]["wie"] == "persönlich"
n = len(db.angebot(a)["versand"])
liste.nachfassen(a, dialog=lambda d: d.reject())
assert len(db.angebot(a)["versand"]) == n and not geoeffnet
ok("Nachfassen vermerken (Telefon, persönlich): nicht mehr fällig; Abbrechen vermerkt nichts; keine E-Mail")

morgen = datetime.date.today() + datetime.timedelta(days=1)
liste.wiedervorlage_setzen(b, dialog=lambda d: (d.datum.setDate(morgen), d._ok()))
assert cockpit.verlauf(db.angebot(b))[2] == morgen
assert [x["id"] for x in liste.modell.zeilen] == []
liste.wiedervorlage_setzen(b, dialog=lambda d: (d.datum.setDate(datetime.date.today()), d._ok()))
assert [x["id"] for x in liste.modell.zeilen] == [b] and "Wiedervorlage" in f.start.wiedervorlage.item(0).text()
liste.wiedervorlage_setzen(b, dialog=lambda d: d._keine())
assert cockpit.verlauf(db.angebot(b))[2] is None and [x["id"] for x in liste.modell.zeilen] == []
ok("Wiedervorlage von Hand (auch Entwurf): fällig am Tag, „Keine Wiedervorlage“ entfernt sie")

s = f.angebot_oeffnen(a)
assert {"Nachfassen vermerken …", "Wiedervorlage …"} <= {x.text() for x in s.weitere.menu().actions()}
assert {"Nachfassen vermerken …", "Wiedervorlage …"} <= {x.text() for x in liste.vorgang_knopf.menu().actions()}
liste.wiedervorlage_setzen(a, dialog=lambda d: d._ok())
assert "Wiedervorlage am" in s.uebersicht_bereich.preisstand.toolTip() or not s.kopf.get("preisbasis")
assert s.kopf["versand"][-1]["art"] == "wiedervorlage"
ok("Menüs Vorgang ▾ und Ausgaben; offenes Angebot sieht den neuen Versandverlauf")
print("OK: Nachfassen")
