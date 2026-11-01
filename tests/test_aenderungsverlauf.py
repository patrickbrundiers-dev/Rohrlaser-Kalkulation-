"""Gemeinsamen Ordner ausbauen, Teil 2 Paket D (Patrick 01.11.2026): Änderungsverlauf.

Prüft: der erste Abgleich merkt nur den Stand (kein Eintrag für den Altbestand); Änderungen an Angebotskopf und
Positionen, neue und gelöschte Positionen, Staffeln, neue Angebote, Stammdaten (geändert, neu, gelöscht) und gemeinsame
Einstellungen kommen mit dem eigenen Kürzel in den Verlauf; die Kollegen sehen sie nach dem Abgleich, ohne die
übernommenen Änderungen sich selbst zuzuschreiben; Einträge älter als 12 Monate fallen weg; alten Wert zurückholen
geht für eigene Angebote und eigene Stammdaten-Änderungen, nicht für Angebote der Kollegen und (ohne Admin) nicht für
Stammdaten-Änderungen der Kollegen; der Admin darf das; das Fenster zeigt den Verlauf und holt zurück.

Aufruf: python tests/test_verlauf.py
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

from rohrlaser import admin_schutz, teilen  # noqa: E402
from rohrlaser import aenderungsverlauf as verlauf  # noqa: E402
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


def alle(db, **filter_):
    return verlauf.eintraege(db.con, **filter_)


pb, mk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK")
alt_id = pb.angebot_neu(dict(kunde="Altbestand GmbH", datum="2026-10-01"))
teilen.abgleichen(pb)
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
assert alle(pb) == [] and alle(mk) == []
ok("Erster Abgleich merkt nur den Stand (kein Eintrag für Altbestand)")

# ---- Angebot: Kopf, Positionen, Staffeln, neues Angebot
uid_alt = pb.con.execute("SELECT uid FROM angebote WHERE id=?", (alt_id,)).fetchone()[0]
pb.angebot_aendern(alt_id, "kunde", "Neuer Name GmbH")
pid = pb.position_neu(alt_id, dict(bezeichnung="Rahmen", stueck=10, laenge=1200))
teilen.abgleichen(pb)
e = alle(pb, tabelle="angebote", uid=uid_alt)
felder = {(x["feld"], x["art"]) for x in e}
assert ("kunde", "geaendert") in felder and ("", "neu") in felder, e
k = next(x for x in e if x["feld"] == "kunde")
assert k["wer"] == "PB" and verlauf.wert(k["alt"]) == "Altbestand GmbH" and verlauf.wert(k["neu"]) == "Neuer Name GmbH"
assert verlauf.feld_titel(k) == "Kundenname"
ok("Kopf geändert und Position neu mit Kürzel, altem und neuem Wert")

pb.position_aendern(pid, "stueck", 25)
teilen.abgleichen(pb)
s = next(x for x in alle(pb, tabelle="angebote", uid=uid_alt) if x["feld"] == "stueck")
assert verlauf.wert(s["alt"]) == 10 and verlauf.wert(s["neu"]) == 25 and verlauf.feld_titel(s) == "Stückzahl"
ok("Positionsfeld geändert (Titel aus der Positionsliste)")

neu_id = pb.angebot_neu(dict(kunde="Neukunde", datum="2026-11-01"))
teilen.abgleichen(pb)
uid_neu = pb.con.execute("SELECT uid FROM angebote WHERE id=?", (neu_id,)).fetchone()[0]
assert [(x["ziel"], x["art"]) for x in alle(pb, tabelle="angebote", uid=uid_neu)] == [("kopf", "neu")]
ok("Neues Angebot: ein Eintrag „Angebot neu“")

pb.positionen_loeschen([pid])
teilen.abgleichen(pb)
assert any(x["art"] == "geloescht" and x["ziel"].startswith("pos:") for x in alle(pb, tabelle="angebote", uid=uid_alt))
ok("Position gelöscht")

# ---- Stammdaten und Einstellungen
kunde_id = pb.neu("kunden", dict(kundennr="10042", name="Muster GmbH"))
teilen.abgleichen(pb)
pb.aendern("kunden", kunde_id, "name", "Muster AG")
pb.einstellung_setzen("gewinn", 17.5)
teilen.abgleichen(pb)
st = alle(pb, ohne_angebote=True)
assert any(x["tabelle"] == "kunden" and x["art"] == "neu" for x in st)
n = next(x for x in st if x["tabelle"] == "kunden" and x["feld"] == "name")
assert verlauf.wert(n["alt"]) == "Muster GmbH" and verlauf.wert(n["neu"]) == "Muster AG" and "10042" in n["bezug"]
g = next(x for x in st if x["tabelle"] == teilen.EINST and x["uid"] == "gewinn")
assert g["art"] == "geaendert" and "Gewinn" in g["bezug"] and verlauf.wert(g["neu"]) == 17.5
assert verlauf.wert_text(g["neu"]) == "17,5"
ok("Stammdaten neu und geändert, gemeinsame Einstellung geändert")

# ---- Kollege sieht alles, schreibt sich nichts davon zu
teilen.abgleichen(mk)
teilen.abgleichen(mk)
e_mk = alle(mk)
assert e_mk and all(x["wer"] == "PB" for x in e_mk), {x["wer"] for x in e_mk}
assert len(e_mk) == len(alle(pb))
ok("Kollege sieht den Verlauf von PB nach dem Abgleich, ohne eigene Scheineinträge")

mk_kunde = mk.con.execute("SELECT id FROM kunden WHERE uid=(SELECT uid FROM kunden WHERE id=?)", (kunde_id,)).fetchone()
mk_kunde = mk.con.execute("SELECT id FROM kunden WHERE kundennr='10042'").fetchone()[0]
mk.aendern("kunden", mk_kunde, "name", "Muster KG")
teilen.abgleichen(mk)
teilen.abgleichen(pb)
w = [x for x in alle(pb, ohne_angebote=True) if x["feld"] == "name" and x["wer"] == "MK"]
assert w and verlauf.wert(w[0]["neu"]) == "Muster KG"
assert not [x for x in alle(pb, ohne_angebote=True) if x["feld"] == "name" and x["wer"] == "PB"
            and verlauf.wert(x["neu"]) == "Muster KG"]
ok("Änderung des Kollegen erscheint bei PB unter MK")

# ---- zurückholen
admin_schutz.SITZUNG = admin_schutz.Sitzung()          # kein Admin
pb.einstellung_setzen("passwort", "geheim")
assert not admin_schutz.ist_admin(pb)
ja, grund = verlauf.darf_zurueckholen(pb, w[0])
assert not ja and "MK" in grund, grund
ok("Ohne Admin: Stammdaten-Änderung des Kollegen nicht zurückholen")
eigene = next(x for x in alle(pb, ohne_angebote=True) if x["feld"] == "name" and x["wer"] == "PB")
assert verlauf.darf_zurueckholen(pb, eigene)[0]
verlauf.zurueckholen(pb, eigene)
assert pb.con.execute("SELECT name FROM kunden WHERE id=?", (kunde_id,)).fetchone()[0] == "Muster GmbH"
ok("Eigene Stammdaten-Änderung zurückgeholt")
s_pb = next(x for x in alle(pb, tabelle="angebote", uid=uid_alt) if x["feld"] == "kunde")
verlauf.zurueckholen(pb, s_pb)
assert pb.angebot(alt_id)["kunde"] == "Altbestand GmbH"
teilen.abgleichen(pb)
assert next(x for x in alle(pb, tabelle="angebote", uid=uid_alt) if x["feld"] == "kunde")["neu"] == '"Altbestand GmbH"'
ok("Alter Wert im eigenen Angebot zurückgeholt, als neue Änderung vermerkt")

teilen.abgleichen(mk)
e_fremd = next(x for x in alle(mk, tabelle="angebote", uid=uid_alt) if x["feld"] == "kunde")
ja, grund = verlauf.darf_zurueckholen(mk, e_fremd)
assert not ja and "PB" in grund
ok("Angebot des Kollegen: nur ansehen")

sitzung = admin_schutz.Sitzung()
sitzung.freischalten()
admin_schutz.SITZUNG = sitzung
assert verlauf.darf_zurueckholen(pb, w[0])[0]
ok("Admin darf auch Stammdaten-Änderungen der Kollegen zurückholen")
verlauf.zurueckholen(pb, g)
assert pb.einstellung("gewinn") == verlauf.wert(g["alt"])
ok("Gemeinsame Einstellung (Admin-Bereich) als Admin zurückgeholt (Wert, nicht Text)")
admin_schutz.SITZUNG = admin_schutz.Sitzung()

# ---- 12 Monate
alt_zeit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=400)).isoformat()
pb.con.execute(f"UPDATE {verlauf.TABELLE} SET zeit=? WHERE id=?", (alt_zeit, eigene["id"]))
pb.con.commit()
verlauf.einrichten(pb.con)
assert not [x for x in alle(pb) if x["id"] == eigene["id"]]
ok("Einträge älter als 12 Monate fallen weg")

# ---- Fenster
f = Hauptfenster(pb)
f.stumm = True
from rohrlaser import aenderungsverlauf_dialog as verlauf_dialog  # noqa: E402
d = verlauf_dialog.zeigen(f, alt_id)
assert d.liste.rowCount() >= 3 and d.windowTitle().startswith("Verlauf Angebot")
texte = [d.liste.item(r, 3).text() for r in range(d.liste.rowCount())]
assert "Kundenname" in texte, texte
d.suche.setText("Rahmen")
assert d.liste.rowCount() >= 1
d.suche.setText("")
r = texte.index("Kundenname")
d.liste.selectRow(r)
assert d.zurueck.isEnabled()
d2 = verlauf_dialog.zeigen(f)
assert d2.liste.rowCount() >= 2 and "Stammdaten" in d2.windowTitle()
d3 = f.angebote.verlauf_zeigen(alt_id)
assert d3.liste.rowCount() == d.liste.rowCount()
from rohrlaser import kollegen_dialog  # noqa: E402
kd = kollegen_dialog.KollegenDialog(f)
assert kd.verlauf.text().startswith("Verlauf")
ok("Fenster Verlauf: Angebot und Stammdaten, Suche, Zurückholen-Knopf")

print("\nAlle Prüfungen bestanden.")
