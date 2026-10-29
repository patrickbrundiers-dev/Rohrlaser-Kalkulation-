"""Prüft mehrere Arbeitsplätze mit gemeinsamem Ordner (teilen.py, Patrick 22.10.2026): Kürzel als Bearbeiter, ein
gemeinsamer Nummernkreis (2026-00001, nummern.py; ausführlich in test_nummern.py),
eigene Datei je Mitarbeiter, Stammdaten zeilenweise zusammenführen (neueste Änderung gewinnt, Löschen kommt an,
gleiche Schlüssel werden eine Zeile, Zukaufartikel über die Kennung), Angebote der anderen nur lesen und kopieren,
erster Abgleich (übernehmen), Kürzel belegt, neuere Programmversion, Umstellung älterer Dateien (Schema 43).

Aufruf: python tests/test_teilen.py
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import nummern, teilen  # noqa: E402
from rohrlaser.angebot import kuerzel_sauber  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k, mit_ordner=True):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("benutzer_email", f"{k.lower()}@example.com")
    if mit_ordner:
        db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


POS = dict(pos=10, artikel="T-1", bezeichnung="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
           stueck=5, schneidweg=320, einstiche=2)

# ---------------------------------------------------------------- Kürzel und Nummer
assert kuerzel_sauber(" pb-1 ") == "PB1" and kuerzel_sauber("abcdefg") == "ABCDE"
pb = arbeitsplatz("Patrick", "pb")
a1 = pb.angebot_neu(dict(kunde="Kunde A", datum="2026-10-22"))
a2 = pb.angebot_neu(dict(kunde="Kunde B", datum="2026-10-22"))
assert pb.angebot(a1)["nummer"] == "2026-00001" and pb.angebot(a2)["nummer"] == "2026-00002"
assert pb.angebot(a1)["bearbeiter"] == "PB"
pb.angebot_loeschen(a2)
a2 = pb.angebot_neu(dict(kunde="Kunde B", datum="2026-10-22"))
assert pb.angebot(a2)["nummer"] == "2026-00003", "gelöschte Nummer wird nicht wieder vergeben"
ohne = Datenbank(tmp / "ohne" / "rohrlaser.db")
assert ohne.angebot(ohne.angebot_neu(dict(datum="2026-10-22")))["nummer"] == "2026-00001", "ohne Ordner lokal gezählt"
ok("Nummer ohne Kürzel (2026-00001) im gemeinsamen Ordner reserviert, gelöschte nicht wieder vergeben, Bearbeiter im Kopf")

for p in (POS, dict(POS, pos=20, artikel="T-2", laenge=750, stueck=8)):
    pb.position_neu(a1, p)
pb.staffel_stufe_neu(a1, dict(nr=1))
st = pb.staffel_stufen(a1)[0]
pb.staffel_neu(a1, dict(schluessel="10", menge=50, stufe_id=st["id"]))
pid = pb.positionen(a1)[0]["id"]
pb.netz_speichern(pid, b"NETZ" * 100)
assert all(r[0] for r in pb.con.execute("SELECT uid FROM profile"))
ok("jede Stammdatenzeile hat eine Kennung (uid)")

# ---------------------------------------------------------------- erster Arbeitsplatz schreibt
assert teilen.aktiv(pb)
b = teilen.abgleichen(pb)
datei = gemeinsam / "Rohrlaser_PB" / "haupt.sqlite"
assert datei.exists() and b["eigene"] == 2, b
info = teilen.info_lesen(datei)
assert info["kuerzel"] == "PB" and info["name"] == "Patrick" and info["angebote"] == 2
ok("eigene Daten Rohrlaser_PB/haupt.sqlite im gemeinsamen Ordner (2 Angebote, Stammdaten, Info)")

# ---------------------------------------------------------------- zweiter Arbeitsplatz: erster Abgleich
mk = arbeitsplatz("Martin", "MK")
mk.aendern("profile", mk.zeilen("profile", True)[0]["id"], "bemerkung", "nur bei MK")
try:
    teilen.abgleichen(mk)
    raise AssertionError("erster Abgleich ohne Rückfrage")
except teilen.ErstAbgleich as e:
    assert e.andere == ["PB"]
try:
    teilen.schreiben(mk)
    raise AssertionError("schreiben vor dem ersten Lesen")
except teilen.ErstAbgleich:
    pass
assert not (gemeinsam / "Rohrlaser_MK" / "haupt.sqlite").exists()
pb.aendern("preise", pb.zeilen("preise", True)[0]["id"], "preis", 9.99)
teilen.schreiben(pb)
b = teilen.abgleichen(mk, teilen.UEBERNEHMEN)
assert b["angebote_neu"] == 2 and b["mitarbeiter"] == ["PB"], b
def gleiche(db, tabelle, zeile):
    """Zeile mit derselben Kennung bei einem anderen Arbeitsplatz."""
    return next(z for z in db.zeilen(tabelle, True) if z["uid"] == zeile["uid"])


assert gleiche(mk, "preise", pb.zeilen("preise", True)[0])["preis"] == 9.99
assert {(z["profil_id"], z.get("bemerkung")) for z in mk.zeilen("profile", True)} == \
    {(z["profil_id"], z.get("bemerkung")) for z in pb.zeilen("profile", True)}
assert {z["uid"] for z in mk.zeilen("profile", True)} == {z["uid"] for z in pb.zeilen("profile", True)}
fremd = [a for a in mk.angebote() if a["fremd"] == "PB"]
assert len(fremd) == 2 and all(a["bearbeiter"] == "PB" for a in fremd)
f1 = next(a for a in fremd if a["nummer"] == "2026-00001")
assert len(mk.positionen(f1["id"])) == 2 and len(mk.staffeln(f1["id"])) == 1
assert mk.staffeln(f1["id"])[0]["stufe_id"] == mk.staffel_stufen(f1["id"])[0]["id"]
assert list(mk.netze(f1["id"]).values()) == [b"NETZ" * 100]
ok("erster Abgleich (übernehmen): Stammdaten wie bei PB, gleiche Kennungen, PB-Angebote mit Positionen, "
   "Staffeln (Stufe neu verknüpft) und 3D-Netz")

m1 = mk.angebot_neu(dict(kunde="Kunde M"))
assert nummern.zaehler(mk.angebot(m1)["nummer"]) == 4 and mk.angebot(m1)["bearbeiter"] == "MK"
mk.position_neu(m1, POS)
kopie = mk.angebot_kopieren(f1["id"])
k = mk.angebot(kopie)
assert nummern.zaehler(k["nummer"]) == 5 and k["bearbeiter"] == "MK" and not k.get("fremd")
assert len(mk.positionen(kopie)) == 2
ok("Kollege MK zählt im selben Nummernkreis weiter (2026-00004); Kopie: neue Nummer, Bearbeiter MK, eigenes Angebot")

# ---------------------------------------------------------------- Änderungen in beiden Richtungen
time.sleep(0.01)
preis1 = mk.zeilen("preise", True)[1]
mk.aendern("preise", preis1["id"], "preis", 4.44)
neu_kunde = mk.neu("kunden", dict(kundennr="K-900", name="Neukunde MK"))
weg = mk.zeilen("gewinde", True)[0]
mk.loeschen("gewinde", [weg["id"]])
mk.einstellung_setzen("gewinn", 0.25)
mk.einstellung_setzen("ablageordner", "C:/nur/hier")           # lokal: wird nicht geteilt
teilen.abgleichen(mk)
time.sleep(0.01)
kunde1 = pb.zeilen("kunden", True)[0]
pb.aendern("kunden", kunde1["id"], "bemerkung", "von PB")
b = teilen.abgleichen(pb)
assert gleiche(pb, "preise", preis1)["preis"] == 4.44
assert any(z["kundennr"] == "K-900" for z in pb.zeilen("kunden", True))
assert weg["uid"] not in {z["uid"] for z in pb.zeilen("gewinde", True)}
assert pb.einstellung("gewinn") == 0.25 and pb.einstellung("ablageordner") == ""
assert {a["nummer"] for a in pb.angebote() if a["fremd"] == "MK"} == {mk.angebot(m1)["nummer"], k["nummer"]}
assert b["angebote_neu"] == 2 and b["stammdaten"] >= 4, b
teilen.abgleichen(mk)
assert gleiche(mk, "kunden", kunde1)["bemerkung"] == "von PB"
ok("Änderung, neue Zeile, Löschen und gemeinsame Einstellung kommen beim anderen an; lokale Einstellung nicht")

# ---------------------------------------------------------------- Konflikt: neueste Änderung gewinnt
zid_pb = pb.zeilen("werkstoffe", True)[0]["id"]
zid_mk = next(z["id"] for z in mk.zeilen("werkstoffe", True) if z["uid"] == pb.zeilen("werkstoffe", True)[0]["uid"])
pb.aendern("werkstoffe", zid_pb, "bemerkung", "alt PB")
teilen.schreiben(pb)
time.sleep(0.01)
mk.aendern("werkstoffe", zid_mk, "bemerkung", "neu MK")
teilen.abgleichen(mk)
teilen.abgleichen(pb)
teilen.abgleichen(mk)
assert next(z for z in pb.zeilen("werkstoffe", True) if z["id"] == zid_pb)["bemerkung"] == "neu MK"
assert next(z for z in mk.zeilen("werkstoffe", True) if z["id"] == zid_mk)["bemerkung"] == "neu MK"
ok("gleiche Zeile an zwei Plätzen geändert: die spätere Änderung gilt bei beiden")

# ---------------------------------------------------------------- gleicher Schlüssel getrennt angelegt
time.sleep(0.01)
pb.neu("profile", dict(profil_id="RR 99x9", form="Rundrohr", a=99, wand=9, bemerkung="PB"))
time.sleep(0.01)
mk.neu("profile", dict(profil_id="RR 99x9", form="Rundrohr", a=99, wand=9, bemerkung="MK"))
for _ in range(2):
    teilen.abgleichen(pb)
    teilen.abgleichen(mk)
z_pb = [z for z in pb.zeilen("profile", True) if z["profil_id"] == "RR 99x9"]
z_mk = [z for z in mk.zeilen("profile", True) if z["profil_id"] == "RR 99x9"]
assert len(z_pb) == len(z_mk) == 1 and z_pb[0]["uid"] == z_mk[0]["uid"], (z_pb, z_mk)
assert z_pb[0]["bemerkung"] == z_mk[0]["bemerkung"] == "MK"
ok("gleiche Profil-ID an zwei Plätzen angelegt: eine Zeile mit derselben Kennung, letzte Änderung gilt")

# ---------------------------------------------------------------- Zukaufartikel über die Kennung
aid = pb.zukauf_speichern(None, dict(bezeichnung="Schraube M8", kategorie="Normteile", einheit="Stk"),
                          [dict(lieferant="Würth", preise=json.dumps([dict(ab=1, preis=0.12)]), preiseinheit=1)])
pb.position_neu(a1, dict(art="Zukaufteil", pos=30, bezeichnung="Schraube", stueck=4,
                         zukauf=json.dumps([dict(artikel_id=aid, menge=1)])))
mk.neu("zukauf_artikel", dict(bezeichnung="Platzhalter"))     # andere IDs als bei PB
teilen.abgleichen(pb)
teilen.abgleichen(mk)
art = next(z for z in mk.zeilen("zukauf_artikel", True) if z["bezeichnung"] == "Schraube M8")
bez = [z for z in mk.zeilen("zukauf_bezug", True) if z["artikel_id"] == art["id"]]
assert len(bez) == 1 and bez[0]["lieferant"] == "Würth"
f1 = next(a for a in mk.angebote() if a["nummer"] == "2026-00001")
zk = json.loads(next(p for p in mk.positionen(f1["id"]) if p.get("art") == "Zukaufteil")["zukauf"])
assert zk[0]["artikel_id"] == art["id"], (zk, art["id"])
ok("Zukaufartikel mit Einkauf je Lieferant und Zukaufteil im Angebot zeigen beim anderen auf den richtigen Artikel")

# ---------------------------------------------------------------- fremde Angebote: Stand des Bearbeiters
mk.angebot_aendern(f1["id"], "bemerkung", "hier geändert")
pb.angebot_aendern(a1, "kunde", "Kunde A neu")
teilen.abgleichen(pb)
b = teilen.abgleichen(mk)
assert mk.angebot(f1["id"])["kunde"] == "Kunde A neu" and not mk.angebot(f1["id"]).get("bemerkung")
assert f1["id"] in b["geaenderte_ids"]
b = teilen.abgleichen(mk)
assert b["angebote_geaendert"] == 0, "unverändertes Angebot wird nicht neu eingelesen"
pb.angebot_loeschen(a2)
teilen.abgleichen(pb)
b = teilen.abgleichen(mk)
assert b["angebote_weg"] == 1 and "2026-00003" not in {a["nummer"] for a in mk.angebote()}
ok("fremde Angebote: gleiche ID beim Neueinlesen, örtliche Änderungen überschrieben, gelöschte verschwinden")

# ---------------------------------------------------------------- Kürzel belegt, neuer Rechner
pb2 = arbeitsplatz("Patrick neu", "PB")
try:
    teilen.lesen(pb2, teilen.UEBERNEHMEN)
    teilen.schreiben(pb2)
    raise AssertionError("fremde Datei überschrieben")
except teilen.KuerzelBelegt as e:
    assert e.info["name"] == "Patrick"
teilen.schreiben(pb2, uebernehmen=True)
assert {a["nummer"] for a in pb2.angebote() if not a["fremd"]} >= {"2026-00001"}
hoch = max(nummern.zaehler(a["nummer"]) for a in pb2.angebote())
assert nummern.zaehler(pb2.angebot(pb2.angebot_neu())["nummer"]) > hoch
ok("Kürzel schon belegt: Hinweis; auf neuem Rechner übernehmen holt die eigenen Angebote zurück, Zähler geht weiter")

# ---------------------------------------------------------------- neuere Programmversion
c = sqlite3.connect(gemeinsam / "Rohrlaser_MK" / "haupt.sqlite")
c.execute("UPDATE info SET wert='999' WHERE name='schema'")
c.commit()
c.close()
b = teilen.lesen(pb)
assert any("neueren Programmversion" in h for h in b["hinweise"]), b
ok("Datei einer neueren Programmversion: Stammdaten nicht übernommen, Hinweis")

# ---------------------------------------------------------------- ältere Datei (Schema 43)
alt = tmp / "alt.db"
pb.con.execute(f"VACUUM INTO '{alt}'")
c = sqlite3.connect(alt)
for t in teilen.GETEILT:
    c.execute(f'DROP TRIGGER IF EXISTS "{t.name}_uid"')
    c.execute(f'DROP INDEX IF EXISTS "{t.name}_uid_index"')
    c.execute(f'ALTER TABLE "{t.name}" DROP COLUMN uid')
c.execute("DROP TABLE teilen_basis")
for n in ("fremd", "fremd_stand", "bearbeiter"):
    c.execute(f"ALTER TABLE angebote DROP COLUMN {n}")
c.execute("PRAGMA user_version=43")
c.commit()
c.close()
db41 = Datenbank(alt)
assert all(r[0] for r in db41.con.execute("SELECT uid FROM kunden"))
assert db41.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
ok("Datei Schema 43: Kennungen vergeben, Spalten ergänzt")
print("OK: mehrere Arbeitsplätze mit gemeinsamem Ordner")
