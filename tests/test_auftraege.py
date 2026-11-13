"""Angebot in Auftrag übernehmen und Auftragsverwaltung (Plan Auftragsworkflow 13.11.2026, Paket 1, auftraege.py):
Übernahme mit Zusammenfassung (Positionen, Zeiten, Kosten, Preise, Zeichnungen/CAD), eigener Nummernkreis, kein
Doppelauftrag, mehrere Angebote in einem Auftrag, Angebot bleibt unverändert und Änderungen werden erkannt, Historie
mit alt/neu und Prüfsumme, zwei Arbeitsplätze über den gemeinsamen Ordner, Migration bestehender Aufträge, Lesemodus,
Wiederherstellung aus der Sicherung, Seite Aufträge und Menü in der Angebotsliste.

Aufruf: python tests/test_auftraege.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import auftraege as au, fertigung, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def fehler(f, text):
    try:
        f()
    except au.AuftragFehler as ex:
        assert text in str(ex), ex
        return
    raise AssertionError(f"kein Fehler: {text}")


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
assert f.auftraege_an() and f.reiter.indexOf(f.auftraege) >= 0


def angebot(kunde="Becker GmbH", kundennr="10023", artikel=("BG-100", "BG-101"), nummer=None, optimieren=True):
    k = dict(kunde=kunde, kundennr=kundennr, stange=6000, maschine="T03", kundenreferenz="Projekt Halle 3",
             bemerkung="Kanten entgratet, Teile einzeln gekennzeichnet")
    if nummer:
        k["nummer"] = nummer
    a = db.angebot_neu(k)
    for n, art in enumerate(artikel):
        db.position_neu(a, dict(pos=n + 1, artikel=art, bezeichnung=f"Teil {art}", profil_id="RR 42,4x2,0",
                                werkstoff_id="S235-10219", laenge=1250 - 300 * n, stueck=50 + 10 * n, schneidweg=300,
                                einstiche=2))
    if optimieren:
        s = f.angebot_oeffnen(a)
        s.optimieren()
        s.neu_laden()
        f.angebot_schliessen(a)
    return a


def ordner_mit_dateien(a):
    o = f.angebot_ordner(db.angebot(a))
    (o / "BG-100.step").write_text("ISO-10303-21;")
    (o / "BG-100.pdf").write_bytes(b"%PDF-1.4")
    (o / "Anfrage.msg").write_bytes(b"x")
    return o


# ------------------------------------------------------------------ A1 Zusammenfassung und Übernahme
a1 = angebot()
ordner_mit_dateien(a1)
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a1, auftrag=("PO-4711", "2026-11-27"))
assert au.von_angebot(db, a1) is None                       # stumm: keine Übernahme ohne Klick
vorher = (db.angebot(a1), db.positionen(a1))
z = au.zusammenfassung(db, [a1], lambda i: f.angebot_ordner(db.angebot(i)))
assert len(z["positionen"]) == 2 and z["summen"]["preis"] > 0 and z["summen"]["laser_min"] > 0, z["summen"]
assert z["kopf"]["bestellnr"] == "PO-4711" and z["kopf"]["liefertermin"] == "2026-11-27"
assert z["kopf"]["projekt"] == "Projekt Halle 3" and "entgratet" in z["kopf"]["anforderungen"]
p0 = z["positionen"][0]
assert p0["artikel"] == "BG-100" and p0["menge"] == 50 and p0["material"] > 0 and p0["preis"] > 0
assert p0["werkstoff"] == "S235-10219" and p0["profil"] == "RR 42,4x2,0" and p0["laenge"] == 1250
assert set(p0["zeichnungen"]) == {"BG-100.step", "BG-100.pdf"}, p0["zeichnungen"]
assert {d["art"] for d in z["angebote"][0]["angebot"]["dateien"]} >= {"CAD", "Zeichnung"}
ok("A1 Zusammenfassung: Kopf, Positionen, Zeiten, Kosten, Preise, Zeichnungen und CAD-Dateien")

# Fenster (Doppelklick: zweiter Klick legt keinen zweiten Auftrag an)
klicks = []


def zweimal(d):
    d.felder["projekt"].setText("Halle 3 Ost")
    klicks.append(d.anlegen())
    klicks.append(d.anlegen())          # zweiter Klick auf den (gesperrten) Knopf
    return True


uid = f.angebote.in_auftrag([a1], dialog=zweimal)
assert uid and klicks[0] == uid and klicks[1] is None, klicks
assert db.con.execute("SELECT COUNT(*) FROM auftrag_kopf").fetchone()[0] == 1
assert f.angebote.in_auftrag([a1], dialog=zweimal) == uid           # schon im Auftrag: derselbe
assert au.uebernehmen(db, [a1]) == uid
assert db.con.execute("SELECT COUNT(*) FROM auftrag_kopf").fetchone()[0] == 1
a = au.auftrag(db, uid)
assert au.MUSTER.match(a["nummer"]) and a["status"] == au.NEU, a["nummer"]
assert a["kopf"]["projekt"] == "Halle 3 Ost" and a["kopf"]["bestellnr"] == "PO-4711"
assert len(a["positionen"]) == 2 and a["wert"] == round(sum(p["preis"] for p in z["positionen"]), 2)
assert (db.angebot(a1), db.positionen(a1)) == vorher                # Angebot unverändert
assert a["angebote"][0]["kennung"] == fertigung.kennung(*vorher)
ok("A1 Übernahme: Nummer AU, Doppelklick ohne zweiten Auftrag, Angebot unverändert")

# ------------------------------------------------------------------ A2 mehrere Angebote, Hinweise, fremd
a2 = angebot(artikel=("BG-200", "BG-201", "BG-202"))
db.vorgang_setzen(a2, "Beauftragt")
au.uebernehmen(db, [a2], auftrag=uid)
a = au.auftrag(db, uid)
assert len(a["angebote"]) == 2 and len(a["positionen"]) == 5
assert [p["nr"] for p in a["positionen"]] == [1, 2, 3, 4, 5]
assert au.uebernehmen(db, [a2], auftrag=uid) == uid and len(au.auftrag(db, uid)["positionen"]) == 5
a3 = angebot(kunde="Andere AG", kundennr="20001", artikel=("X-1",), optimieren=False)
z3 = au.zusammenfassung(db, [a1 and a3])
assert any("noch nicht optimiert" in h for h in z3["hinweise"])
assert any("keine Zeichnungen" in h for h in z3["hinweise"])
db.con.execute("UPDATE angebote SET fremd='MK' WHERE id=?", (a3,))
fehler(lambda: au.zusammenfassung(db, [a3]), "übernehmen kann es nur der Bearbeiter")
db.con.execute("UPDATE angebote SET fremd=NULL WHERE id=?", (a3,))
db.con.commit()
ok("A2 mehrere Angebote in einem Auftrag, Hinweise, fremde Angebote nicht")

# ------------------------------------------------------------------ A3 Änderungen und Historie
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("benutzer_name", "Patrick")
assert au.aendern(db, uid, "liefertermin", "2026-12-04", "Kunde verschiebt")
assert not au.aendern(db, uid, "liefertermin", "2026-12-04")        # nichts geändert: kein Eintrag
pos1 = a["positionen"][0]["uid"]
assert au.aendern(db, uid, "menge", "55", "Kunde braucht 5 mehr", position=pos1)
fehler(lambda: au.aendern(db, uid, "menge", "-1", position=pos1), "Zahl ab 0")
fehler(lambda: au.aendern(db, uid, "preis", "1"), "lässt sich nicht ändern")
au.status_setzen(db, uid, au.AV)
fehler(lambda: au.status_setzen(db, uid, au.NEU), "nur mit Grund")
h = au.historie(db, uid)
arten = [x["ereignis"] for x in h]
assert arten[0] == "Auftrag angelegt" and arten[1].startswith("Angebot übernommen"), arten
t = next(x for x in h if x["feld"] == "Liefertermin")
assert t["alt"] == "2026-11-27" and t["neu"] == "2026-12-04" and t["wer"] == "PB (Patrick)" and t["bemerkung"]
m = next(x for x in h if "Menge" in x["feld"])
assert m["alt"] == "50" and m["neu"] == "55" and "Pos. 1" in m["feld"], m
a = au.auftrag(db, uid)
assert a["positionen"][0]["menge"] == 55 and a["kopf"]["liefertermin"] == "2026-12-04" and a["status"] == au.AV
assert db.positionen(a1)[0]["stueck"] == 50                          # Kalkulation unberührt
assert au.pruefen(db, uid) == []
db.con.execute("UPDATE auftrag_ereignisse SET neu='2026-11-01' WHERE feld='liefertermin'")
db.con.commit()
assert len(au.pruefen(db, uid)) == 1                                 # nachträglich geändert: fällt auf
db.con.execute("UPDATE auftrag_ereignisse SET neu='2026-12-04' WHERE feld='liefertermin'")
db.con.commit()
au.status_setzen(db, uid, au.ABGESCHLOSSEN)
fehler(lambda: au.aendern(db, uid, "projekt", "X"), "abgeschlossen")
au.status_setzen(db, uid, au.AV, "versehentlich abgeschlossen")
ok("A3 Änderungen mit alt/neu, Benutzer, Grund; Prüfsumme erkennt Manipulation; Abschluss schützt")

# ------------------------------------------------------------------ A4 Angebot nach Übernahme geändert
assert au.angebot_geaendert(db, au.auftrag(db, uid)) == []
p = db.positionen(a1)[1]
db.position_setzen(p["id"], "stueck", 80) if hasattr(db, "position_setzen") else db.con.execute(
    "UPDATE positionen SET stueck=80 WHERE id=?", (p["id"],))
db.con.commit()
nr1 = db.angebot(a1)["nummer"]
assert au.angebot_geaendert(db, au.auftrag(db, uid)) == [nr1]
v = au.vergleich(db, uid, au.angebot_uid(db, a1))
assert any(x["was"] == "Menge" and x["neu"] == 80 for x in v), v
au.aktualisieren(db, uid, au.angebot_uid(db, a1), "Nachtrag")
a = au.auftrag(db, uid)
assert au.angebot_geaendert(db, a) == []
mengen = {p["artikel"]: p["menge"] for p in a["positionen"]}
assert mengen["BG-101"] == 80 and mengen["BG-100"] == 55, mengen    # von Hand geänderte Menge bleibt
assert len(a["positionen"]) == 5
ok("A4 Änderung am Angebot erkannt, Vergleich, übernommen; Ergänzung im Auftrag bleibt")

# ------------------------------------------------------------------ A5 Sicht = Ereignisse
vorher_sicht = au.auftrag(db, uid)
au.aufbauen(db)
assert au.auftrag(db, uid) == vorher_sicht
ok("A5 Sicht aus den Ereignissen neu gebaut: gleich")

# ------------------------------------------------------------------ A6 Liste, Suche, Filter, Seite
assert [z["nummer"] for z in au.liste(db, "BG-201")] == [a["nummer"]]
assert au.liste(db, "Halle 3 Ost") and au.liste(db, "PO-4711") and not au.liste(db, "gibt es nicht")
assert au.liste(db, status=au.AV) and not au.liste(db, status=au.PRODUKTION)
assert au.liste(db, status=au.VERZOEGERT, heute="2027-01-01") and not au.liste(db, status=au.VERZOEGERT,
                                                                                heute="2026-11-01")
f.auftraege.neu_laden()
assert f.auftrag_zeigen(uid)
s = f.auftraege
assert s.gewaehlt() == uid and s.pos.rowCount() == 5 and s.hist.rowCount() == len(au.historie(db, uid))
assert s.angebote.rowCount() == 2 and "BG-100.step" in s.angebote.item(0, 4).text()
assert s.bearbeiten({"ansprechpartner": "Frau Weber"}, "Telefonat") == 1
assert au.auftrag(db, uid)["kopf"]["ansprechpartner"] == "Frau Weber"
assert s.position_aendern(s.pos.model().index(0, 15), "Erstmuster beilegen", "Kunde")
assert s.status_aendern(au.MATERIAL_FEHLT)
ok("A6 Liste mit Suche (Artikel, Projekt, Bestellnummer) und Filtern, Seite mit Detail und Bearbeiten")

# ------------------------------------------------------------------ A7 zwei Arbeitsplätze
gemeinsam = tmp / "gemeinsam"
gemeinsam.mkdir()
db.einstellung_setzen("teilen_ordner", str(gemeinsam))
assert teilen.aktiv(db)
n_vorher = au.neue_nummer(db)
assert au.zaehler(n_vorher) == au.zaehler(a["nummer"]) + 1
db2 = Datenbank(tmp / "kollege.db")
db2.einstellung_setzen("benutzer_kuerzel", "MK")
db2.einstellung_setzen("teilen_ordner", str(gemeinsam))
assert au.zaehler(au.neue_nummer(db2)) == au.zaehler(n_vorher) + 1   # gemeinsamer Nummernkreis
au.ordner_schreiben(db)
assert (gemeinsam / "Auftraege" / "PB.json").is_file()
assert au.ordner_lesen(db2) == db.con.execute("SELECT COUNT(*) FROM auftrag_ereignisse").fetchone()[0]
b = au.auftrag(db2, uid)
assert b is not None and b["kopf"] == au.auftrag(db, uid)["kopf"] and len(b["positionen"]) == 5
# beide ändern gleichzeitig verschiedene Dinge; nach dem Abgleich hat jeder beide Änderungen, nichts doppelt
import socket  # noqa: E402
echt = socket.gethostname
socket.gethostname = lambda: "KOLLEGE-PC"
au.aendern(db2, uid, "projekt", "Halle 4", "vom Kollegen")
au.ordner_schreiben(db2)
socket.gethostname = echt
au.aendern(db, uid, "verantwortlich", "PB")
au.ordner_schreiben(db)
au.ordner_lesen(db)
au.ordner_lesen(db2)
au.ordner_lesen(db)                                                  # zweimal lesen: nichts doppelt
for d in (db, db2):
    k = au.auftrag(d, uid)["kopf"]
    assert k["projekt"] == "Halle 4" and k["verantwortlich"] == "PB", k
n1 = db.con.execute("SELECT COUNT(*) FROM auftrag_ereignisse").fetchone()[0]
assert n1 == db2.con.execute("SELECT COUNT(*) FROM auftrag_ereignisse").fetchone()[0]
assert au.pruefen(db) == [] and au.pruefen(db2) == []
ok("A7 zwei Arbeitsplätze: gemeinsamer Nummernkreis, Ereignisse ohne Doppel und ohne Konflikt")

# vorläufige Nummer, wenn der Ordner fehlt; endgültig beim nächsten Schreiben
weg = tmp / "weg"
db.einstellung_setzen("teilen_ordner", str(weg / "nicht da"))
a4 = angebot(artikel=("V-1",))
db.vorgang_setzen(a4, "Beauftragt")
u4 = au.uebernehmen(db, [a4])
assert au.vorlaeufig(au.nummer(db, u4)) and au.nummer(db, u4).startswith("AU-V-PB-"), au.nummer(db, u4)
db.einstellung_setzen("teilen_ordner", str(gemeinsam))
au.ordner_schreiben(db)
assert au.MUSTER.match(au.nummer(db, u4)), au.nummer(db, u4)
assert any(x["ereignis"] == "Endgültige Auftragsnummer" for x in au.historie(db, u4))
ok("A7 vorläufige Nummer ohne Ordner, endgültig beim nächsten Abgleich")

# ------------------------------------------------------------------ A8 Migration bestehender Aufträge
tmp2 = Path(tempfile.mkdtemp())
alt = Datenbank(tmp2 / "alt.db")
f.db = db
ids = []
for n, st in enumerate((None, "In Fertigung", "Fertig gemeldet")):
    i = alt.angebot_neu(dict(kunde=f"Kunde {n}", kundennr=f"9{n}", stange=6000, maschine="T03"))
    alt.position_neu(i, dict(pos=1, artikel=f"M-{n}", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                             laenge=500, stueck=10, schneidweg=100, einstiche=1))
    alt.vorgang_setzen(i, "Beauftragt")
    if st:
        fertigung.setzen(alt, i, "Freigegeben", wer="PB")
        fertigung.setzen(alt, i, st)
    ids.append(i)
entwurf = alt.angebot_neu(dict(kunde="Entwurf", stange=6000))
assert au.migrieren(alt) == 3 and au.migrieren(alt) == 0
st = {au.auftrag(alt, au.von_angebot(alt, i))["kopf"]["kunde"]: au.auftrag(alt, au.von_angebot(alt, i))["status"]
      for i in ids}
assert st == {"Kunde 0": au.NEU, "Kunde 1": au.PRODUKTION, "Kunde 2": au.ABGESCHLOSSEN}, st
assert au.von_angebot(alt, entwurf) is None
assert any(x["ereignis"] == "Aus bestehendem Auftrag übernommen" for x in au.historie(alt, au.von_angebot(alt, ids[0])))
ok("A8 Migration: laufende mit Stand, fertige als abgeschlossen, Entwürfe nicht, nur einmal")

# ------------------------------------------------------------------ A9 Datenbank: Schema, Sicherung, Lesemodus
alt.schliessen()
kopie = tmp2 / "kopie.db"
shutil.copy(tmp2 / "alt.db", kopie)
con = sqlite3.connect(kopie)
con.execute("PRAGMA user_version=85")                                 # Datei vor diesem Paket
con.execute("DROP TABLE auftrag_positionen")
con.commit()
con.close()
neu = Datenbank(kopie)
assert neu.con.execute("PRAGMA user_version").fetchone()[0] >= 86
assert list((tmp2).rglob("*vor_Schema_*")), "keine Sicherung vor dem Schema-Schritt"
assert len(au.liste(neu)) == 3 and all(au.auftrag(neu, z["uid"])["positionen"] for z in au.liste(neu))
neu.lesemodus("Test")
fehler(lambda: au.aendern(neu, au.liste(neu)[0]["uid"], "projekt", "X"), "Lesemodus")
neu.lesemodus("")
ok("A9 Schema 86 mit Sicherung, fehlende Sicht beim Öffnen aus den Ereignissen neu gebaut, Lesemodus")

print("test_auftraege OK")
