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

# ------------------------------------------------------------------ A10 Paket 2: ergänzen, lösen, Filter
wert_vorher = au.auftrag(db, uid)["wert"]
pu = s.position_ergaenzen(dict(artikel="ZK-1", bezeichnung="Muster Kappe", menge="10", preis_teil="2,50",
                               bemerkung="Zukauf", grund="Kunde wünscht Kappen"))
a = au.auftrag(db, uid)
pz = next(p for p in a["positionen"] if p["uid"] == pu)
assert pz["menge"] == 10 and pz["preis"] == 25 and pz["angebot"] is None and pz["nr"] == 6
assert round(a["wert"] - wert_vorher, 2) == 25.0
assert any(x["ereignis"] == "Position im Auftrag ergänzt ZK-1" and x["bemerkung"] for x in au.historie(db, uid))
fehler(lambda: au.position_hinzufuegen(db, uid, "X", menge="0"), "größer 0")
fehler(lambda: au.position_hinzufuegen(db, uid, ""), "Artikel oder Bezeichnung")
assert au.aendern(db, uid, "menge", "12", "mehr", position=pu)
u2 = au.angebot_uid(db, a2)
fehler(lambda: au.angebot_entfernen(db, uid, u2, ""), "Grund")
au.status_setzen(db, uid, au.PRODUKTION)
fehler(lambda: au.angebot_entfernen(db, uid, u2, "falsch"), "nur vor der Produktion")
au.status_setzen(db, uid, au.AV, "zurück für Test")
assert s.angebot_loesen(u2, "falscher Auftrag")
a = au.auftrag(db, uid)
assert len(a["angebote"]) == 1 and len(a["positionen"]) == 3 and au.von_angebot(db, a2) is None
u_neu = au.uebernehmen(db, [a2])                                     # danach in einen eigenen Auftrag
assert u_neu != uid and au.von_angebot(db, a2) == u_neu
vorher_sicht = au.auftrag(db, uid)
au.aufbauen(db)
assert au.auftrag(db, uid) == vorher_sicht
# Terminfilter (Montag 16.11.2026)
h = "2026-11-18"
assert au.termin_passt("2026-11-17", "Überfällig", h) and not au.termin_passt("2026-11-18", "Überfällig", h)
assert au.termin_passt("2026-11-22", "Diese Woche", h) and not au.termin_passt("2026-11-23", "Diese Woche", h)
assert au.termin_passt("2026-11-23", "Nächste Woche", h) and au.termin_passt("2026-11-30", "Später", h)
assert au.termin_passt("2026-11-30", "Dieser Monat", h) and not au.termin_passt("2026-12-01", "Dieser Monat", h)
assert au.termin_passt("", "Ohne Termin", h) and not au.termin_passt("", "Diese Woche", h)
au.aendern(db, u_neu, "verantwortlich", "MK")
assert [z["uid"] for z in au.liste(db, status="Alle", wer="MK")] == [u_neu]
n = au.anzahl_je_filter(au.alle_zeilen(db))
assert n["Alle"] == len(au.liste(db, status="Alle")) and n[au.AV] >= 1
s.filter_setzen(au.AV, "Alle Termine", "")
assert s.status_leiste.tabText(au.FILTER.index(au.AV)).startswith(f"{au.AV} (")
assert all(z["status"] == au.AV for z in s.zeilen) and s.zeilen
s.filter_setzen("Alle", "Alle Termine", "MK")
assert [z["uid"] for z in s.zeilen] == [u_neu] and s.wer.findData("MK") > 0
s.filter_setzen("Alle", "Alle Termine", "")
assert s.tabelle.item(0, 2).text() in ("–", "100 %")
ok("A10 Paket 2: Position ergänzen, Angebot lösen und neu zuordnen, Filter Status/Termin/Zuständig mit Anzahl")

# ------------------------------------------------------------------ A11 Paket 3: Arbeitsvorbereitung
from rohrlaser import auftrag_av as av  # noqa: E402

assert av.schritte(db)[:2] == ["Materialbereitstellung", "Rohrlaser"] and len(av.schritte(db)) == 8
a11 = angebot(kunde="AV GmbH", kundennr="10500")
ordner_mit_dateien(a11)
db.vorgang_setzen(a11, "Beauftragt")
u11 = au.uebernehmen(db, [a11], ordner_von=lambda i: f.angebot_ordner(db.angebot(i)))
au.position_hinzufuegen(db, u11, "ZK-9", "Schutzkappe", 100, 0.2, grund="Kunde wünscht Kappen")
a = au.auftrag(db, u11)
p1, p2, p3 = a["positionen"]
liste, vor = av.arbeitsgaenge(db, a, p1)
aktiv = {x["name"]: x for x in liste if x["aktiv"]}
assert vor and set(aktiv) == {"Materialbereitstellung", "Rohrlaser", "Qualitätskontrolle", "Verpackung"}, aktiv
assert aktiv["Rohrlaser"]["sollzeit"] > 0 and aktiv["Rohrlaser"]["maschine"] == "T03"
assert aktiv["Rohrlaser"]["sollmenge"] == p1["menge"]
assert not any(x["aktiv"] for x in av.arbeitsgaenge(db, a, p3)[0] if x["name"] == "Rohrlaser")   # Zukauf
pl = {x["punkt"]: x["ampel"] for x in av.pruefliste(db, a)}
assert pl == {"zeichnungen": av.GELB, "material": av.ROT, "zukauf": av.GELB, "fertigungsinfo": av.GRUEN,
              "arbeitsgaenge": av.ROT}, pl
fehler(lambda: av.freigeben(db, u11), "Noch nicht alles grün")
fehler(lambda: au.status_setzen(db, u11, au.BEREIT), "Noch nicht alles grün")
assert au.auftrag(db, u11)["status"] == au.NEU

# Oberfläche: Reiter Arbeitsvorbereitung, jede Eingabe sofort gespeichert
f.auftrag_zeigen(u11)
seite = f.auftraege
r = seite.av
assert seite.reiter.tabText(1) == "Arbeitsvorbereitung" and r.position.count() == 3
assert r.vorschlag and r.ag.rowCount() == 8
montage = [x["name"] for x in r.liste].index("Montage")
assert r.aktiv_setzen(montage, True)
a = au.auftrag(db, u11)
assert a["status"] == au.AV                                        # AV begonnen
assert [x["name"] for x in a["positionen"][0]["arbeitsgaenge"] if x["aktiv"]][-3:] == [
    "Montage", "Qualitätskontrolle", "Verpackung"]
assert not r.vorschlag
assert r.verschieben(-1, zeile=montage)
assert [x["name"] for x in au.auftrag(db, u11)["positionen"][0]["arbeitsgaenge"]][montage - 1] == "Montage"
assert r.hinzufuegen("Pulverbeschichten") and "Pulverbeschichten" in [x["name"] for x in r.liste]
assert r.entfernen([x["name"] for x in r.liste].index("Pulverbeschichten"))
assert r.feld_setzen(1, "mitarbeiter", "MK") and r.feld_setzen(1, "start", "2026-11-16 07:00")
assert not r.feld_setzen(1, "ende", "2026-11-15")                   # Ende vor Start
assert au.auftrag(db, u11)["positionen"][0]["arbeitsgaenge"][1]["mitarbeiter"] == "MK"
h = au.historie(db, u11)
ag = [x for x in h if x["ereignis"] == "Arbeitsgänge festgelegt"]
assert len(ag) == 6 and "Montage" in ag[0]["neu"] and ag[0]["feld"] == "Pos. 1 BG-100: Arbeitsgänge", ag
assert ag[1]["feld"].endswith("Reihenfolge") and "Montage → Schweißbaugruppe" in ag[1]["neu"], ag[1]
assert ag[4]["feld"].endswith("Rohrlaser: Mitarbeiter") and (ag[4]["alt"], ag[4]["neu"]) == ("", "MK"), ag[4]
assert any(x["neu"] == au.AV and "automatisch" in x["bemerkung"] for x in h)

# Vorschläge für die übrigen Positionen, Auswahl für alle
assert r.vorschlaege_uebernehmen() == 2
assert {x["punkt"]: x["ampel"] for x in av.pruefliste(db, au.auftrag(db, u11))}["arbeitsgaenge"] == av.GRUEN
assert av.fuer_alle(db, u11, p1["uid"]) >= 1
p2_neu = au.auftrag(db, u11)["positionen"][1]["arbeitsgaenge"]
assert "Montage" in [x["name"] for x in p2_neu if x["aktiv"]]
assert next(x for x in p2_neu if x["name"] == "Rohrlaser")["sollzeit"] == next(
    x for x in av.vorschlag(p2, av.schritte(db), "T03") if x["name"] == "Rohrlaser")["sollzeit"]

# Material: fehlt -> Status Material fehlt; bestellt -> zurück in die AV
assert r.material_setzen("fehlt", "Rohr 42,4 nicht am Lager")
assert au.auftrag(db, u11)["status"] == au.MATERIAL_FEHLT
assert r.material_setzen("bestellt", "Lieferant Muster, KW 47")
assert au.auftrag(db, u11)["status"] == au.AV
# Zeichnungen mit Lücke: geklärt nur mit Bemerkung
fehler(lambda: av.bestaetigen(db, u11, "zeichnungen", av.OK), "nur mit Bemerkung")
assert r.bestaetigen("zeichnungen", "BG-101 Zeichnung liegt in Papierform vor")
assert r.bestaetigen("zukauf", "Kappen am Lager")
assert av.ampel(av.pruefliste(db, au.auftrag(db, u11))) == av.GRUEN
assert r.freigeben()
a = au.auftrag(db, u11)
assert a["status"] == au.BEREIT and not a["kopf"]["_freigabe"]["sonder"]
fehler(lambda: av.freigeben(db, u11), "freigeben geht nur aus der Arbeitsvorbereitung")
assert any(x["ereignis"] == "Für die Produktion freigegeben" for x in au.historie(db, u11))
assert any(x["ereignis"] == "Arbeitsvorbereitung geprüft" and x["feld"] == "Material verfügbar oder bestellt"
           for x in au.historie(db, u11))

# Sonderfreigabe mit Grund
a12 = angebot(kunde="Sonder AG", kundennr="10501", artikel=("S-1",))
db.vorgang_setzen(a12, "Beauftragt")
u12 = au.uebernehmen(db, [a12])
assert av.freigeben(db, u12, "Eilauftrag, Chef hat freigegeben") is True
a = au.auftrag(db, u12)
assert a["status"] == au.BEREIT and a["kopf"]["_freigabe"]["sonder"] and a["kopf"]["_freigabe"]["offen"]
assert a["kopf"]["_freigabe"]["grund"] == "Eilauftrag, Chef hat freigegeben"

# eigene Produktionsschritte aus den Einstellungen; Ereignisse bleiben prüfbar, Sicht = Ereignisse
db.einstellung_setzen("produktionsschritte", "Rohrlaser\nPulverbeschichten; Verpackung")
assert av.schritte(db) == ["Rohrlaser", "Pulverbeschichten", "Verpackung"]
db.einstellung_setzen("produktionsschritte", "")
assert len(av.schritte(db)) == 8
vorher_sicht = au.auftrag(db, u11)
au.aufbauen(db)
assert au.auftrag(db, u11) == vorher_sicht and au.pruefen(db) == []
ok("A11 Paket 3: Arbeitsgänge aus der Kalkulation, an-/abwählen, sortieren, ergänzen; Prüfliste mit Ampel; "
   "Material fehlt; Freigabe nur grün oder Sonderfreigabe; Historie")

# ------------------------------------------------------------------ A12 Paket 4: Produktion und Rückmeldung
from rohrlaser import auftrag_produktion as pr  # noqa: E402

fehler(lambda: pr.rueckmelden(db, u_neu, au.auftrag(db, u_neu)["positionen"][0]["uid"], "x", pr.BEGONNEN),
       "produktionsbereit")                                          # Auftrag aus A10 ist nicht freigegeben
a = au.auftrag(db, u11)
nr11 = a["nummer"]
assert a["status"] == au.BEREIT and au.fortschritt(a) == 0.0
ps = f.produktion
assert f.reiter.indexOf(ps) >= 0
ps.filter_setzen("Alle", "", nr11)
n_ag = sum(1 for p in a["positionen"] for x in p["arbeitsgaenge"] if x["aktiv"])
assert len(ps.zeilen) == n_ag and all(z["status"] == pr.OFFEN or z["status"] == pr.EINGEPLANT for z in ps.zeilen)
assert ps.waehlen(nr11, "Rohrlaser", 1)
z = ps.zeile()
soll = z["soll"]
assert soll == a["positionen"][0]["menge"] and z["status"] == pr.EINGEPLANT          # Start geplant aus A11
assert ps.melden(pr.BEGONNEN) and not ps.melden(pr.BEGONNEN)                         # zweiter Klick: nichts
assert au.auftrag(db, u11)["status"] == au.PRODUKTION
assert ps.zeile()["status"] == pr.LAEUFT
assert ps.mit_menge(pr.TEILMENGE, dict(menge=soll * 0.6, ausschuss=0, minuten=None, bemerkung=""))
z = ps.zeile()
assert z["gut"] == soll * 0.6 and abs(z["fortschritt"] - 0.6) < 1e-9, z                 # Teilfertigung 60 %
assert ps.melden(pr.UNTERBROCHEN) and ps.zeile()["status"] == pr.PAUSE
assert ps.problem("Maschinenstillstand", "Spindel klemmt") and ps.zeile()["status"] == pr.GESTOERT
assert "Maschinenstillstand" in ps.zeile()["problem"]
fehler(lambda: pr.rueckmelden(db, u11, z["position"], z["ag"], pr.PROBLEM), "was das Problem ist")
assert ps.melden(pr.FORTGESETZT) and ps.zeile()["status"] == pr.LAEUFT
assert ps.mit_menge(pr.AUSSCHUSS, dict(menge=2, art=pr.AUSSCHUSS, bemerkung="Maß"))
assert ps.zeile()["ausschuss"] == 2
assert ps.mit_menge(pr.ABGESCHLOSSEN, dict(menge=soll * 0.4, ausschuss=0, minuten=25, bemerkung=""))
z = ps.zeile()
assert z["status"] == pr.FERTIG and z["gut"] == soll and z["istzeit"] == 25 and z["ist_ende"], z
# Storno einer falschen Rückmeldung: Menge zählt nicht mehr, Eintrag bleibt sichtbar
assert ps.stornieren(zeile=0, grund="Menge vertippt")
z = ps.zeile()
assert z["gut"] == soll * 0.6 and z["status"] != pr.FERTIG, z
assert any(x["storniert"] for x in ps._rm) and ps.verlauf.rowCount() == len(ps._rm)
assert ps.mit_menge(pr.ABGESCHLOSSEN, dict(menge=soll * 0.4, ausschuss=0, minuten=None, bemerkung=""))
assert ps.zeile()["status"] == pr.FERTIG
# Fortschritt: Position gewichtet mit Sollzeit, Auftrag gewichtet mit den Positionen
a = au.auftrag(db, u11)
zeilen1, f1 = pr.position_stand(a["positionen"][0])
gew = [(x["sollzeit"], z["fortschritt"]) for x, z in zeilen1]
assert 0 < f1 < 1 and abs(f1 - pr._gewichtet(gew)) < 1e-9
assert 0 < au.fortschritt(a) < f1
assert next(z for z in au.alle_zeilen(db) if z["uid"] == u11)["fortschritt"] == au.fortschritt(a)
f.auftrag_zeigen(u11)
assert f.auftraege.fort.rowCount() == n_ag and "Gesamtfortschritt" in f.auftraege.fort_text.text()
h = au.historie(db, u11)
assert any(x["ereignis"] == "Teilmenge fertig" and x["feld"].endswith("Rohrlaser") for x in h)
assert any(x["ereignis"] == "Rückmeldung storniert" and x["bemerkung"] == "Menge vertippt" for x in h)
assert any(x["neu"] == au.PRODUKTION and "erste Rückmeldung" in x["bemerkung"] for x in h)

# zwei Arbeitsplätze melden gleichzeitig Teilmengen: nach dem Abgleich die Summe, nichts doppelt
kopie = tmp / "werkstatt.db"
db.con.commit()
shutil.copy(tmp / "rohrlaser.db", kopie)
dbw = Datenbank(kopie)
p2 = au.auftrag(db, u11)["positionen"][1]
mat = next(x for x in p2["arbeitsgaenge"] if x["name"] == "Materialbereitstellung")
assert pr.rueckmelden(dbw, u11, p2["uid"], mat["uid"], pr.TEILMENGE, menge=5)
assert pr.rueckmelden(db, u11, p2["uid"], mat["uid"], pr.TEILMENGE, menge=7)
bekannt = {r[0] for r in db.con.execute("SELECT uid FROM auftrag_ereignisse")}
fremd = [dict(r) for r in dbw.con.execute("SELECT * FROM auftrag_ereignisse") if r["uid"] not in bekannt]
assert au.ereignisse_einlesen(db, fremd) == 1 and au.ereignisse_einlesen(db, fremd) == 0
p2 = au.auftrag(db, u11)["positionen"][1]
assert pr.zustand(mat, pr.rueckmeldungen(p2, mat["uid"]))["gut"] == 12
dbw.schliessen()
# Sicht = Ereignisse; „Änderung übernehmen“ behält Arbeitsgänge und Rückmeldungen
vorher_sicht = au.auftrag(db, u11)
au.aufbauen(db)
assert au.auftrag(db, u11) == vorher_sicht and au.pruefen(db) == []
db.con.execute("UPDATE positionen SET stueck=stueck+1 WHERE angebot_id=?", (a11,))
db.con.commit()
x11 = au.auftrag(db, u11)["angebote"][0]["uid"]
au.aktualisieren(db, u11, x11, "Nachtrag")
p1 = au.auftrag(db, u11)["positionen"][0]
assert p1["arbeitsgaenge"] and pr.rueckmeldungen(p1), "Arbeitsgänge/Rückmeldungen verloren"
# Rückmeldung aus der Rohrlaser Auslastung (Format 2, je Angebotsnummer, Arbeitsgang leer = Laser)
nr_a11 = db.angebot(a11)["nummer"]
r = dict(auftraege=[dict(nummer=nr_a11, pos=None, arbeitsgang=None, status="fertig", tatsaechlich=40.0,
                         bediener="MK"),
                    dict(nummer=nr_a11, pos=None, arbeitsgang="Montage", status="läuft", tatsaechlich=None,
                         bediener="JS"),
                    dict(nummer="fremd", pos=None, arbeitsgang=None, status="fertig", tatsaechlich=9.0)])
a = au.auftrag(db, u11)
p2 = a["positionen"][1]
laser2 = next(x for x in p2["arbeitsgaenge"] if x["name"] == "Rohrlaser")
mont = [(p, x) for p in a["positionen"] if p.get("angebot") for x in p["arbeitsgaenge"]
        if x["name"] == "Montage" and x["aktiv"]]
assert pr.auslastung_uebernehmen(db, r) == 1 + len(mont)     # Pos. 1 Laser ist schon fertig
assert pr.auslastung_uebernehmen(db, r) == 0                 # nur einmal
p2 = au.auftrag(db, u11)["positionen"][1]
z = pr.zustand(laser2, pr.rueckmeldungen(p2, laser2["uid"]))
assert z["status"] == pr.FERTIG and z["gut"] == z["soll"] and 0 < z["istzeit"] <= 40, z
rm = pr.rueckmeldungen(p2, laser2["uid"])[-1]
assert rm["daten"]["quelle"] == pr.AUSLASTUNG and "Bediener MK" in rm["bemerkung"]
ps.neu_laden()
ok("A12 Paket 4: Rückmeldungen (Beginnen, Teilmenge 60 %, Unterbrechen, Problem, Ausschuss, Abschluss, Storno), "
   "Fortschritt gewichtet, Seite Produktion, zwei Arbeitsplätze ohne Doppel")

# ------------------------------------------------------------------ A7 zwei Arbeitsplätze
gemeinsam = tmp / "gemeinsam"
gemeinsam.mkdir()
db.einstellung_setzen("teilen_ordner", str(gemeinsam))
assert teilen.aktiv(db)
n_vorher = au.neue_nummer(db)
assert au.zaehler(n_vorher) == max(au.zaehler(z["nummer"]) for z in au.liste(db, status="Alle")) + 1
db2 = Datenbank(tmp / "kollege.db")
db2.einstellung_setzen("benutzer_kuerzel", "MK")
db2.einstellung_setzen("teilen_ordner", str(gemeinsam))
assert au.zaehler(au.neue_nummer(db2)) == au.zaehler(n_vorher) + 1   # gemeinsamer Nummernkreis
au.ordner_schreiben(db)
assert (gemeinsam / "Auftraege" / "PB.json").is_file()
assert au.ordner_lesen(db2) == db.con.execute("SELECT COUNT(*) FROM auftrag_ereignisse").fetchone()[0]
b = au.auftrag(db2, uid)
assert b is not None and b["kopf"] == au.auftrag(db, uid)["kopf"] and b["positionen"] == au.auftrag(db, uid)["positionen"]
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
con.execute("PRAGMA user_version=86")                                 # Datei vor diesem Paket
con.execute("DROP TABLE auftrag_positionen")
con.commit()
con.close()
neu = Datenbank(kopie)
assert neu.con.execute("PRAGMA user_version").fetchone()[0] >= 87
assert list((tmp2).rglob("*vor_Schema_*")), "keine Sicherung vor dem Schema-Schritt"
assert len(au.liste(neu)) == 3 and all(au.auftrag(neu, z["uid"])["positionen"] for z in au.liste(neu))
neu.lesemodus("Test")
fehler(lambda: au.aendern(neu, au.liste(neu)[0]["uid"], "projekt", "X"), "Lesemodus")
neu.lesemodus("")
ok("A9 Schema 87 mit Sicherung, fehlende Sicht beim Öffnen aus den Ereignissen neu gebaut, Lesemodus")

print("test_auftraege OK")
