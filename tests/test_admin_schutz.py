"""Admin-Schutz der Einstellungen (Plan 30.10.2026, Freigabe „1c 2a 3a 4b 5a 6a 7a 8a“): Einstellungen frei, geschützte
Seiten und Tabellen ändert nur der Admin (grau bzw. nicht bearbeitbar, Schloss), Freischalten mit dem Admin-Passwort
an jedem Platz, Sperre nach 15 Minuten ohne Eingabe, Häkchen je Bereich; Admin-Vorgaben gelten an allen Plätzen
über den gemeinsamen Ordner, ein Nicht-Admin kann sie nicht überschreiben. Hauptadmin und weitere Admins mit eigenem Passwort (Seite Arbeitsplätze
und Rechte).

Aufruf: QT_QPA_PLATFORM=offscreen python tests/test_admin_schutz.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import admin_schutz, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()

# ---------------------------------------------------------------- ohne Fenster: Bereiche, Vorschlag, Sitzung
keys = {k for k, _, _ in admin_schutz.bereiche()}
assert set(admin_schutz.VORGABE) <= keys | {admin_schutz.SEITE_ADMIN}, set(admin_schutz.VORGABE) - keys
assert "e_arbeitsplatz" not in keys and "kunden" not in keys and "profile" in keys
db0 = Datenbank(tmp / "x" / "rohrlaser.db")
schutz = admin_schutz.geschuetzt_liste(db0)
assert "profile" not in schutz and "e_zuschlaege" in schutz and admin_schutz.SEITE_ADMIN in schutz
namen = admin_schutz.einstellungen_geschuetzt(db0)
assert {"gewinn", "passwort", "versand_aktiv"} <= namen, "Schalter der Seite Funktionen zählt auch beim Thema"
assert "teilen_ordner" not in namen and "letzte_angebotsnummer" not in namen and "step_ordner" not in namen
assert {"preise", "maschinen", "schneiddaten", "stundensaetze"} <= admin_schutz.tabellen_geschuetzt(db0)
assert "profile" not in admin_schutz.tabellen_geschuetzt(db0)
db0.einstellung_setzen(admin_schutz.ADMIN_SEITEN, ["profile"])
assert admin_schutz.geschuetzt_liste(db0) == {"profile", *admin_schutz.HAUPT_SEITEN}
ok("Bereiche: Vorschlag nach Risiko, Häkchen je Bereich, Mein Arbeitsplatz und Kunden nie geschützt")

uhr = [0.0]
s = admin_schutz.Sitzung(uhr=lambda: uhr[0])
s.freischalten()
uhr[0] = admin_schutz.MINUTEN * 60 - 1
assert not s.ablauf_pruefen() and s.freigeschaltet
s.eingabe()
uhr[0] += admin_schutz.MINUTEN * 60 - 1
assert not s.ablauf_pruefen(), "jede Eingabe verlängert"
uhr[0] += 2
assert s.ablauf_pruefen() and not s.freigeschaltet and s.jemals
ok("Sitzung: sperrt nach 15 Minuten ohne Eingabe, jede Eingabe verlängert")

# ---------------------------------------------------------------- Fenster: frei, Schloss, Freischalten
db = Datenbank(tmp / "pb" / "rohrlaser.db")
db.einstellung_setzen("passwort", "geheim")
f = Hauptfenster(db, stumm=True)
b = f.bereich
assert b.gesperrt() and not b.offen
titel = [b.unter.tabText(i) for i in range(b.unter.count())]
assert any(t.startswith("Zuschläge") and t.endswith("🔒") for t in titel), titel
assert any(t == "Mein Arbeitsplatz" for t in titel) and any(t == "Profile" for t in titel), titel
seite = {s.schluessel: s for s in f.einstellungen.seiten}
assert not seite["e_zuschlaege"].felder["gewinn"].isEnabled(), "geschützt: grau"
assert seite["e_arbeitsplatz"].felder["benutzer_name"].isEnabled(), "Mein Arbeitsplatz frei"
assert seite["e_step"].felder["step_kopieren"].isEnabled(), "freie Seite"
assert not seite["e_versand"].felder["versand_aktiv"].isEnabled(), "Funktionsschalter auch beim Thema gesperrt"
st = {s.t.name: s for s in f.seiten}
assert st["preise"].admin_gesperrt and not st["profile"].__dict__.get("admin_gesperrt")
i = st["preise"].modell.index(0, next(n for n, (a, _) in enumerate(st["preise"].modell.spalten) if a == "feld"))
assert not (st["preise"].modell.flags(i) & Qt.ItemIsEditable) and not st["preise"].modell.setData(i, "1")
neu = next(k for k in st["preise"].findChildren(QPushButton) if k.text() == "Neue Zeile")
assert not neu.isEnabled()
n = len(db.zeilen("preise"))
st["preise"].zeile_neu()
assert len(db.zeilen("preise")) == n, "Tastenkürzel neue Zeile gesperrt"
assert f.zusatz.admin_gesperrt and f.zusatz.neu() is None
assert f.fracht.zonen.admin_gesperrt and f.fracht.historie.admin_gesperrt, "Frachtpflege gesperrt"
assert not f.fracht.historie.einstellungen.felder[next(iter(f.fracht.historie.einstellungen.felder))].isEnabled()
assert f.fracht.pflegen_knopf.isEnabled(), "Rechner und Sprung in die Pflege frei"
ok("Nicht-Admin: Einstellungen offen, geschützte Seiten mit Schloss grau, Tabellen nicht bearbeitbar")

assert not b.oeffnen("falsch") and b.fehler.text() == "Passwort falsch."
assert b.oeffnen("geheim") and b.offen and not b.gesperrt()
assert seite["e_zuschlaege"].felder["gewinn"].isEnabled() and not st["preise"].admin_gesperrt and neu.isEnabled()
assert st["preise"].modell.flags(i) & Qt.ItemIsEditable
assert not f.fracht.zonen.admin_gesperrt
b.sperren()
assert b.gesperrt() and not seite["e_zuschlaege"].felder["gewinn"].isEnabled() and not neu.isEnabled()
ok("Als Admin freischalten mit dem Admin-Passwort, Admin sperren")

b.oeffnen("geheim")
f.admin_seite.haken["e_step"].setChecked(True)
f.admin_seite.haken["preise"].setChecked(False)
assert "e_step" in admin_schutz.geschuetzt_liste(db) and "preise" not in admin_schutz.geschuetzt_liste(db)
b.sperren()
assert not seite["e_step"].felder["step_kopieren"].isEnabled() and not st["preise"].admin_gesperrt
assert not f.admin_seite.haken["e_step"].isEnabled(), "Seite Admin-Schutz immer geschützt"
b.oeffnen("geheim")
f.admin_seite.vorschlag_setzen()
assert admin_schutz.geschuetzt_liste(db) == set(admin_schutz.VORGABE) | set(admin_schutz.HAUPT_SEITEN)
ok("Häkchen je Bereich (Seite Admin-Schutz), Vorschlag wiederherstellen")

ohne = Datenbank(tmp / "ohne" / "rohrlaser.db")
ohne.einstellung_setzen("passwort", "")
f2 = Hauptfenster(ohne, stumm=True)
assert not f2.bereich.gesperrt() and not f2.bereich.leiste.isVisible()
assert {s.schluessel: s for s in f2.einstellungen.seiten}["e_zuschlaege"].felder["gewinn"].isEnabled()
assert all("🔒" not in f2.bereich.unter.tabText(i) for i in range(f2.bereich.unter.count()))
ok("Ohne Admin-Passwort ist nichts gesperrt")

# ---------------------------------------------------------------- Admin-Vorgaben für alle Plätze
def platz(name, k):
    d = Datenbank(tmp / name / "rohrlaser.db")
    d.einstellung_setzen("benutzer_name", name)
    d.einstellung_setzen("benutzer_kuerzel", k)
    d.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return d


admin = admin_schutz.Sitzung()
kein = admin_schutz.Sitzung()
pb, ma = platz("Patrick", "PB"), platz("Max", "MA")
pb.einstellung_setzen("passwort", "geheim")
admin_schutz.SITZUNG = kein
teilen.abgleichen(pb, teilen.ZUSAMMENFUEHREN)
teilen.abgleichen(ma, teilen.UEBERNEHMEN)
assert ma.passwort_pruefen("geheim"), "Passwort (Hash) kommt über den Ordner"
assert not (gemeinsam / admin_schutz.ORDNER / admin_schutz.DATEI).exists(), "ohne Admin kein Paket"

admin.freischalten()
admin_schutz.SITZUNG = admin
pb.einstellung_setzen("gewinn", 0.21)
preis = pb.zeilen("preise")[0]
pb.aendern("preise", preis["id"], "preis", 9.99)
teilen.abgleichen(pb)
paket = json.loads((gemeinsam / admin_schutz.ORDNER / admin_schutz.DATEI).read_text("utf-8"))
assert paket["von"] == "Hauptadmin (PB)" and "gewinn" in paket["inhalt"]["einstellungen"]
admin_schutz.SITZUNG = kein
bericht = teilen.abgleichen(ma)
assert ma.einstellung("gewinn") == 0.21, "Admin-Wert gilt am anderen Platz"
uid = pb.con.execute("SELECT uid FROM preise WHERE id=?", (preis["id"],)).fetchone()[0]
assert ma.con.execute("SELECT preis FROM preise WHERE uid=?", (uid,)).fetchone()[0] == 9.99
ok("Admin-Vorgaben: Werte des Admins gelten an jedem Arbeitsplatz (Einstellungen und Tabellen)")

ma.einstellung_setzen("gewinn", 0.5)             # Nicht-Admin (alter Weg, Datei …) ändert einen geschützten Wert
ma.einstellung_setzen("step_kopieren", "nein")   # freier Wert
teilen.abgleichen(ma)
assert ma.einstellung("gewinn") == 0.21, "Nicht-Admin: geschützter Wert wird wiederhergestellt"
admin_schutz.SITZUNG = admin
teilen.abgleichen(pb)
assert pb.einstellung("gewinn") == 0.21, "Änderung des Nicht-Admins kommt nicht beim Admin an"
assert pb.einstellung("step_kopieren") == "nein", "freie Werte gleichen weiter ab"
ok("Nicht-Admin kann geschützte Werte nicht überschreiben, freie Werte gleichen wie bisher ab")

pb.einstellung_setzen(admin_schutz.ADMIN_SEITEN, sorted(set(admin_schutz.VORGABE) | {"e_step"}))
teilen.abgleichen(pb)
admin_schutz.SITZUNG = kein
teilen.abgleichen(ma)
assert "e_step" in admin_schutz.geschuetzt_liste(ma), "Häkchen gelten an allen Plätzen"
(gemeinsam / admin_schutz.ORDNER / admin_schutz.DATEI).write_text('{"inhalt": {}, "hash": "x"}', "utf-8")
p = admin_schutz.paket_lesen(ma)
assert p and p.get("hinweis") and not admin_schutz.gueltig(p)
assert admin_schutz.ausfiltern({("einstellungen", "gewinn"): (1, {})}, p) == {("einstellungen", "gewinn"): (1, {})}
ok("Schutzliste kommt mit, beschädigtes Paket wird übergangen")

# ---------------------------------------------------------------- Hauptadmin und weitere Admins (Freigabe 1a-5a)
admin_schutz.SITZUNG = kein
ma.einstellung_setzen(admin_schutz.LIZENZ_INFO, {"art": "benutzer", "stufe": "gueltig", "gueltig_bis": "2027-01-31"})
teilen.abgleichen(ma)
admin_schutz.SITZUNG = admin
assert admin_schutz.recht_setzen(pb, "MA", admin_schutz.ADMIN, "Max") == "Für einen Admin bitte ein Startpasswort vergeben."
assert admin_schutz.recht_setzen(pb, "MA", admin_schutz.ADMIN, "Max", "kurz") .startswith("Das Startpasswort")
assert admin_schutz.recht_setzen(pb, "MA", admin_schutz.ADMIN, "Max", "Start-123") == ""
teilen.abgleichen(pb)
pl = {p["kuerzel"]: p for p in admin_schutz.plaetze(pb)}
assert pl["MA"]["name"] == "Max" and pl["MA"]["recht"] == admin_schutz.ADMIN and pl["PB"]["ich"]
assert admin_schutz.lizenz_text(pl["MA"]["lizenz"]) == ("Lizenz bis 31.01.2027", "gruen")
assert admin_schutz.lizenz_text({"stufe": "lesemodus", "gueltig_bis": "2026-01-01"})[1] == "rot"
v = admin_schutz.verlauf(pb)
assert v and v[-1]["wer"].startswith("Hauptadmin") and "Rechte" in v[-1]["was"], v
admin_schutz.SITZUNG = kein
teilen.abgleichen(ma)
assert admin_schutz.recht(ma, "MA") == admin_schutz.ADMIN, "Rechte kommen über den Ordner"
ok("Hauptadmin vergibt Admin mit Startpasswort; Übersicht mit Name, Lizenz-Ampel, Recht; Verlauf")

fm = Hauptfenster(ma, stumm=True)
bm = fm.bereich
assert bm.gesperrt()
bm.lizenz_gueltig = lambda: False
assert not bm.oeffnen("Start-123") and "gültige Lizenz" in bm.fehler.text()
bm.lizenz_gueltig = lambda: True
assert bm.oeffnen("Start-123") and bm.neues_passwort_noetig == "MA" and bm.sitzung.wer == "MA"
assert not bm.sitzung.haupt and not bm.gesperrt()
assert bm.bereich_gesperrt(admin_schutz.SEITE_PLAETZE) and bm.bereich_gesperrt(admin_schutz.SEITE_ADMIN)
assert not bm.bereich_gesperrt("e_zuschlaege") and fm.plaetze_seite.admin_gesperrt
assert not fm.admin_seite.haken["e_step"].isEnabled(), "Admin-Schutz nur Hauptadmin"
assert not fm.plaetze_seite.recht_waehlen("MA", admin_schutz.GESPERRT), "Rechte nur Hauptadmin"
assert bm.mein_passwort("Mein-Pass-1") and not bm.neues_passwort_noetig
assert not admin_schutz.admins(ma)["MA"]["neu"]
ma.einstellung_setzen("gewinn", 0.3)
admin_schutz.SITZUNG = bm.sitzung
teilen.abgleichen(ma)
paket = json.loads((gemeinsam / admin_schutz.ORDNER / admin_schutz.DATEI).read_text("utf-8"))
assert paket["von"] == "Max (MA)" and paket["verlauf"][-1]["wer"] == "Max (MA)", paket["verlauf"][-1]
bm.sperren()
assert not bm.oeffnen("Start-123") and bm.oeffnen("Mein-Pass-1"), "Startpasswort gilt nicht mehr"
ok("Weiterer Admin: eigenes Passwort, nur mit gültiger Lizenz, ändert geschützte Seiten, nicht Admin-Schutz/Rechte")

admin_schutz.SITZUNG = admin
teilen.abgleichen(pb)
assert pb.einstellung("gewinn") == 0.3, "Admin-Wert des weiteren Admins gilt beim Hauptadmin"
fp = Hauptfenster(pb, stumm=True)
assert fp.bereich.oeffnen("geheim") and fp.bereich.sitzung.haupt
assert not fp.bereich.bereich_gesperrt(admin_schutz.SEITE_PLAETZE) and not fp.plaetze_seite.admin_gesperrt
fp.plaetze_seite.neu_laden()
assert fp.plaetze_seite.recht_waehlen("MA", admin_schutz.GESPERRT)
admin_schutz.SITZUNG = fp.bereich.sitzung
teilen.abgleichen(pb)
admin_schutz.SITZUNG = bm.sitzung
teilen.abgleichen(ma)
assert bm.gesperrt() and not bm.sitzung.freigeschaltet, "gesperrter Admin verliert die Freischaltung"
assert not bm.oeffnen("Mein-Pass-1") and "gesperrt" in bm.fehler.text()
assert fp.plaetze_seite.startpasswort("MA", "Neu-Start-9")
assert fp.plaetze_seite.recht_waehlen("MA", admin_schutz.ADMIN)
assert admin_schutz.admins(pb)["MA"]["neu"], "Passwort vergessen: neues Startpasswort"
assert fp.plaetze_seite.recht_waehlen("MA", admin_schutz.MITARBEITER) and "MA" not in admin_schutz.admins(pb)
ok("Hauptadmin sperrt Admins (gilt nach dem Abgleich), neues Startpasswort, Recht entziehen")
admin_schutz.SITZUNG = None
print("Alle Prüfungen bestanden.")
