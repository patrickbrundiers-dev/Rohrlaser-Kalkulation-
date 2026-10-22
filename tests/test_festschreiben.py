"""Prüft, dass das Angebots-PDF alle Preisgrundlagen festschreibt (Prüfbericht 22.10.2026, B-4): nach dem
Festschreiben ändern Gewindepreis, Zuschlag Material, Mindestpreis, Händler-Mehrlänge, Profil- und Maschinenwerte den
Preis eines verschickten Angebots nicht mehr; die Übersicht nennt die Änderungen, und eine Änderung am Angebot selbst
erscheint als Abweichung vom verschickten Stand.

Aufruf: python tests/test_festschreiben.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Test", kundennr="1"))
db.position_neu(a, dict(pos=10, artikel="T10", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                        stueck=30, schneidweg=320, einstiche=2, gewinde="4xM6"))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()


def vk():
    s.neu_laden()
    return round(s._verkauf(), 2)


vk0 = vk()
s.preise_festschreiben()                    # wie nach dem Angebots-PDF
pb = db.angebot(a)["preisbasis"]
assert {"gewinde", "einstellungen", "profile", "maschinen", "verschickt"} <= set(pb), set(pb)
assert pb["verschickt"]["netto"] == vk0 and vk() == vk0
ok(f"Angebots-PDF schreibt Gewinde, Einstellungen, Profil, Maschine und Nettosumme ({vk0:.2f} €) fest")

g = next(z for z in db.zeilen("gewinde") if z["gewinde"] == "M6")
db.aendern("gewinde", g["id"], "preis", 1.80)
db.einstellung_setzen("zuschlag_material", 0.10)
db.einstellung_setzen("mindestpreis", 2000)
db.einstellung_setzen("haendler_mehr_kurz", 500)
pr = next(z for z in db.zeilen("profile") if z["profil_id"] == "QR 40x40x3")
db.aendern("profile", pr["id"], "flaeche_manuell", 900)
s = fenster.angebot_oeffnen(a)
assert vk() == vk0, (vk(), vk0)
abw = rechnen.preisbasis_abweichung(s.kopf, s.k_aktuell, s.tabellen_aktuell)
text = "\n".join(abw)
for teil in ("Gewinde", "Zuschlag Material", "Mindestpreis", "Mehrlänge", "Profil QR 40x40x3"):
    assert teil in text, (teil, abw)
assert "Stammdaten seitdem geändert" in s.uebersicht_bereich.preisstand.text()
ok(f"Gewinde 0,90 → 1,80 €, Zuschlag Material 10 %, Mindestpreis 2.000 €, Mehrlänge, Profilfläche: Preis bleibt {vk0:.2f} €, "
   f"{len(abw)} Änderungen genannt")

db.position_aendern(s.positionen[0]["id"], "stueck", 40)
s.neu_laden()
assert s.optimieren()
t = s.uebersicht_bereich.preisstand.text()
assert "Weicht vom verschickten Angebot" in t and "+" in t, t
ok("Stückzahl nach dem PDF geändert: 'Weicht vom verschickten Angebot (Datum: Betrag) ab: +… €'")

assert s.preise_aktualisieren()
assert vk() >= 2000 - 0.01                  # jetzt mit Mindestpreis 2.000 € der aktuellen Einstellungen
ok("Aktuelle Preise übernehmen: rechnet wieder mit den Stammdaten (Mindestpreis 2.000 €)")
print("OK: Festschreiben beim Angebots-PDF (Prüfbericht B-4)")
