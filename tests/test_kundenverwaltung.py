"""Kundenverwaltung (Patrick 23.11.2026, Master-Auftrag „Kundenverwaltung mit eigenem Menü“, Punkt 11 Tests):
Kunden anlegen, bearbeiten, archivieren, Ansprechpartner, Dubletten, Kunde im Angebot (Ansprechpartner,
Lieferadresse, Rabatt), Angebot -> Auftrag, Kundendaten im PDF, Mehrbenutzer (zweite Verbindung, Konflikt),
Migration der Altdaten (Schema 101 -> 102) und die Oberfläche (Menü KUNDEN, Übersicht, Profil, Eingabemaske).

Aufruf: python tests/test_kundenverwaltung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import kunden_daten as kd  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, AenderungsKonflikt, Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def fehler(f, text):
    try:
        f()
    except kd.KundenFehler as e:
        assert text in str(e), (text, str(e))
        return
    raise AssertionError(f"kein Fehler: {text}")


db = Datenbank(TMP / "rohrlaser.db")
assert SCHEMA_VERSION >= 102

# ------------------------------------------------------------------ Namenskern, Kundennummer
assert kd.namenskern("Muster GmbH") == kd.namenskern("Muster Gesellschaft mbH") == \
    kd.namenskern("Muster GmbH & Co. KG") == kd.namenskern("MUSTER gmbh u. Co. KG") == "muster"
assert kd.namenskern("Beispiel Metallbau GmbH") == "beispiel metallbau"
assert kd.namenskern("Müller Stahl AG") == "mueller stahl"
assert kd.plz_ort_teilen("12345 Musterstadt") == ("12345", "Musterstadt")
assert kd.name_teilen("Herr Max Mustermann") == ("Herr", "Max", "Mustermann")
ok("Namenskern ohne Rechtsform (GmbH, Gesellschaft mbH, GmbH & Co. KG gleich), PLZ/Ort und Namen teilen")

assert kd.nummern_schema(db)[0] == "K-" and "zuletzt vergeben K-1002" in kd.nummer_hinweis(db)
try:                                # Patrick 23.11.2026: Kundennummer bei Neukunden immer von Hand
    kd.anlegen(db, dict(name="Ohne Nummer GmbH"))
    raise AssertionError("Kunde ohne Kundennummer angelegt")
except kd.KundenFehler as e:
    assert "Kundennummer" in str(e), e
ok("Kundennummer immer von Hand: ohne Nummer kein Kunde, Hinweis „zuletzt vergeben K-1002“")

# ------------------------------------------------------------------ 1 Kunden anlegen
nr = kd.anlegen(db, dict(kundennr="K-2001", name="Nordhaus Rohrtechnik GmbH", firmenzusatz="Werk Nord", rechtsform="GmbH",
                         kundentyp="Firma", branche="Metallbau", website="www.nordhaus-rohr.de",
                         kundengruppe="A-Kunden", strasse="Hauptstraße 5", plz="45127", ort="Essen", land="de",
                         telefon="0201 123456", email="info@nordhaus-rohr.de", ust_id="de 123 456 789",
                         zahlungsziel="30", skonto="2", skonto_tage="10", waehrung="EUR", kreditlimit="50000",
                         notizen="zahlt pünktlich", preisvereinbarung="Rahmenpreis Rohr 40x40 bis 12/2026"),
                ansprechpartner_=[dict(vorname="Max", nachname="Mustermann", position="Einkaufsleiter",
                                       telefon="0201 123456-12", email="Max.Mustermann@nordhaus-rohr.de",
                                       haupt="ja", einkauf="ja"),
                                  dict(vorname="Erika", nachname="Technik", technik="ja",
                                       email="e.technik@nordhaus-rohr.de")],
                adressen_=[dict(art=kd.LIEFERUNG, bezeichnung="Werk 2", strasse="Industriestr. 9", plz="44135",
                                ort="Dortmund", land="DE", standard="ja"),
                           dict(art=kd.RECHNUNG, strasse="Postfach 100", plz="45001", ort="Essen")],
                vorgaben_=dict(rabatt="3", mindestwert="150"))
k = db.kunde(nr)
assert k["name"] == "Nordhaus Rohrtechnik GmbH" and k["plz_ort"] == "45127 Essen" and k["land"] == "DE"
assert k["ust_id"] == "DE123456789" and k["status"] == "Aktiv" and k["zahlungsziel"] == 30 and k["skonto"] == 2
assert k["kreditlimit"] == 50000 and k["ansprechpartner"] == "Max Mustermann" and k["angelegt"]
assert k["liefer_plz"] == "44135", "Standard-Lieferadresse bestimmt wie bisher die Frachtzone"
assert kd.vorgaben(db, nr)["rabatt"] == 3 and kd.vorgaben(db, nr)["mindestwert"] == 150
ps = kd.ansprechpartner(db, nr)
assert [kd.name_voll(p) for p in ps] == ["Max Mustermann", "Erika Technik"] and ps[0]["haupt"] == "ja"
assert ps[0]["email"] == "max.mustermann@nordhaus-rohr.de" and ps[0]["uid"]
assert [a["art"] for a in kd.adressen(db, nr)] == [kd.RECHNUNG, kd.LIEFERUNG]
assert kd.historie(db, nr)[0]["art"] == kd.H_ANGELEGT
fehler(lambda: kd.anlegen(db, dict(kundennr=nr, name="Andere AG")), "schon vergeben")
fehler(lambda: kd.anlegen(db, dict(kundennr="K-2999", name="")), "Firmenname fehlt")
fehler(lambda: kd.anlegen(db, dict(kundennr="K-2999", name="X GmbH", ust_id="123")), "Umsatzsteuer-ID")
fehler(lambda: kd.anlegen(db, dict(kundennr="K-2999", name="X GmbH", zahlungsziel="dreißig")), "keine Zahl")
fehler(lambda: kd.anlegen(db, dict(kundennr="K-2999", name="X GmbH", land="DE", plz="123")), "5 Ziffern")
ok("1 Kunde anlegen: alle Bereiche (Allgemein, Anschrift, Kaufmännisch, Konditionen) in einer Transaktion, "
   "Ansprechpartner und Adressen, Historie; Prüfungen")

# ------------------------------------------------------------------ 5 Dubletten
d = kd.dubletten(db, dict(name="Nordhaus Rohrtechnik Gesellschaft mbH"))
assert d and d[0][0]["kundennr"] == nr and "gleicher Firmenname" in d[0][1]
d = kd.dubletten(db, dict(name="Ganz anders KG", ust_id="DE123456789"))
assert d and "gleiche Umsatzsteuer-ID" in d[0][1]
d = kd.dubletten(db, dict(name="Irgendwer", email="max.mustermann@nordhaus-rohr.de"))
assert d and any("gleiche E-Mail-Adresse" in g for g in d[0][1]), "auch Mail des Ansprechpartners"
d = kd.dubletten(db, dict(name="Neu GmbH", strasse="Hauptstrasse 5", plz="45127"))
assert d and "gleiche Anschrift" in d[0][1]
assert kd.dubletten(db, dict(name="Neu GmbH", email="a@gmail.com")) == []
assert kd.dubletten(db, dict(name="Nordhaus Rohrtechnik GmbH"), ohne=nr) == []
fehler(lambda: kd.anlegen(db, dict(kundennr="K-2002", name="Nordhaus Rohrtechnik GmbH & Co. KG")),
       "Mögliche Dublette")
nr_d = kd.anlegen(db, dict(kundennr="K-2002", name="Nordhaus Rohrtechnik GmbH & Co. KG"), dubletten_ok=True)
assert db.kunde(nr_d) and nr_d != nr
ok("5 Dubletten: Name ohne Rechtsform, USt-ID, E-Mail (auch Ansprechpartner), Anschrift; Freemail zählt nicht; "
   "Anlegen nur nach Bestätigung, nie automatisch zusammengeführt")

# ------------------------------------------------------------------ 2 Kunden bearbeiten (mit Konflikt)
alt = kd.kunde(db, nr)
g = kd.speichern(db, nr, dict(alt, telefon="0201 999", kundengruppe="B-Kunden"), alt,
                 vorgaben_neu=dict(rabatt="5"), vorgaben_alt=dict(rabatt=3))
assert set(g) == {"Telefon (Zentrale)", "Kundengruppe", "Kundenrabatt [%]"}, g
assert db.kunde(nr)["telefon"] == "0201 999" and kd.vorgaben(db, nr)["rabatt"] == 5
h = [e for e in kd.historie(db, nr, mit_vorgaengen=False) if e["art"] == kd.H_GEAENDERT]
assert any(e["feld"] == "Telefon (Zentrale)" and e["alt"] == "0201 123456" and e["neu"] == "0201 999" for e in h)
# zweiter Benutzer: zweite Verbindung auf dieselbe Datenbank ändert dasselbe Feld
db2 = Datenbank(TMP / "rohrlaser.db")
kd.speichern(db2, nr, dict(alt, branche="Stahlbau"), alt)
try:
    kd.speichern(db, nr, dict(alt, branche="Maschinenbau"), alt)
    raise AssertionError("Konflikt nicht erkannt")
except AenderungsKonflikt:
    pass
assert db.kunde(nr)["branche"] == "Stahlbau"
kd.speichern(db, nr, dict(alt, website="www.neu.de"), alt)        # anderes Feld: kein Konflikt
assert db.kunde(nr)["website"] == "www.neu.de" and db.kunde(nr)["branche"] == "Stahlbau"
db2.con.close()
# Teiländerung (nur Ort): PLZ bleibt, „PLZ Ort“ stimmt, kein Pflichtfeld-Fehler, kein Schein-Konflikt
k_vor = kd.kunde(db, nr)
kd.speichern(db, nr, dict(ort="Essen-Kray"), dict(ort=k_vor["ort"]))
k_nach = kd.kunde(db, nr)
assert k_nach["plz"] == k_vor["plz"] and k_nach["plz_ort"] == f"{k_vor['plz']} Essen-Kray" and k_nach["name"] == k_vor["name"]
kd.speichern(db, nr, dict(ort=k_vor["ort"]), dict(ort="Essen-Kray"))
ok("2 Kunden bearbeiten: nur geänderte Felder, Historie alt -> neu, Konditionen in den Kundenvorgaben; "
   "Mehrbenutzer: gleiches Feld beim Kollegen geändert = Konflikt ohne Schreiben, anderes Feld geht")

# ------------------------------------------------------------------ 4 Ansprechpartner verwalten
pid = kd.person_speichern(db, nr, dict(vorname="Tina", nachname="Buch", buchhaltung="ja", haupt="ja",
                                       email="buchhaltung@nordhaus-rohr.de"))
ps = kd.ansprechpartner(db, nr)
assert kd.name_voll(ps[0]) == "Tina Buch" and sum(p.get("haupt") == "ja" for p in ps) == 1
assert db.kunde(nr)["ansprechpartner"] == "Tina Buch", "Hauptansprechpartner gespiegelt (PDF z. Hd.)"
kd.person_speichern(db, nr, dict(ps[0], position="Leitung Buchhaltung"), pid)
assert kd.ansprechpartner(db, nr)[0]["position"] == "Leitung Buchhaltung"
fehler(lambda: kd.person_speichern(db, nr, dict(vorname="", nachname="")), "Namen")
assert kd.person_loeschen(db, nr, pid)
assert db.kunde(nr)["ansprechpartner"] == "Erika Technik", "ohne Haupt: erster aktiver (nach Name)"
ok("4 Ansprechpartner: anlegen, ein Hauptansprechpartner, ändern, löschen, Spiegel in kunden.ansprechpartner")

# ------------------------------------------------------------------ 3 Archivieren, Duplizieren
kd.archivieren(db, nr_d)
assert nr_d not in {z["kundennr"] for z in kd.uebersicht(db)} and nr_d in {z["kundennr"]
                                                                         for z in kd.uebersicht(db, archiv=True)}
kd.archivieren(db, nr_d, an=False)
assert nr_d in {z["kundennr"] for z in kd.uebersicht(db)}
nr_k = kd.duplizieren(db, nr, "K-2003")
kk = db.kunde(nr_k)
assert kk["name"].endswith("(Kopie)") and not kk.get("ust_id") and len(kd.ansprechpartner(db, nr_k)) == 2
ok("3 Archivieren und zurückholen (Übersicht/Archiv), Kunden duplizieren mit Ansprechpartnern, ohne USt-ID")

# ------------------------------------------------------------------ Übersicht, Suche
z = kd.filtern(kd.uebersicht(db), "rohrtechnik essen")
assert {x["kundennr"] for x in z} == {nr, nr_k}
assert kd.filtern(kd.uebersicht(db), "MUSTERMANN")[0]["kundennr"] in (nr, nr_k)
assert all(x["status"] == "Aktiv" for x in kd.filtern(kd.uebersicht(db), "", status="Aktiv"))
assert kd.filtern(kd.uebersicht(db), "", gruppe="B-Kunden")[0]["kundennr"] == nr
ok("Übersicht: Live-Suche über mehrere Felder ohne Groß-/Kleinschreibung, Filter Status und Gruppe")

# ------------------------------------------------------------------ 10 Migration: Datenbank mit Schema 101 (ohne CRM)
sys.path.insert(0, str(HIER))
import db_roh  # noqa: E402

alt_pfad = TMP / "alt" / "rohrlaser.db"
alt_db = Datenbank(alt_pfad)
alt_db.con.close()
con = db_roh.verbinden(alt_pfad)
for t in ("kunden_ansprechpartner", "kunden_adressen", "kunden_historie"):
    con.execute(f"DROP TABLE IF EXISTS {t}")
for sp in ("ort", "status", "kundentyp", "angelegt", "archiviert", "ust_id", "notizen"):
    con.execute(f'ALTER TABLE kunden DROP COLUMN IF EXISTS "{sp}"')
for sp in ("kunde_ansprech_uid", "kunde_ansprech", "liefer_uid", "lieferadresse"):
    con.execute(f'ALTER TABLE angebote DROP COLUMN IF EXISTS "{sp}"')
con.execute("DELETE FROM einstellungen WHERE name='kunden_crm_stand'")
con.execute("INSERT INTO kunden (kundennr, name, strasse, plz_ort, ansprechpartner, telefon, email, liefer_plz, "
            "liefer_land) VALUES ('K-7001', 'Altbestand Metall GmbH', 'Alte Gasse 1', '12345 Altstadt', "
            "'Herr Karl Alt', '030 1234', 'info@altbestand.de', '54321', 'DE')")
db_roh.schema_version_setzen(con, 101)
con.commit()
con.close()
neu_db = Datenbank(alt_pfad)
assert db_roh.schema_version(neu_db.con) == SCHEMA_VERSION
k7 = kd.kunde(neu_db, "K-7001")
assert k7["ort"] == "Altstadt" and k7["plz"] == "12345" and k7["status"] == kd.AKTIV and k7["kundentyp"] == "Firma"
assert k7["plz_ort"] == "12345 Altstadt" and k7["ansprechpartner"] == "Herr Karl Alt" and k7["telefon"] == "030 1234"
ps = kd.ansprechpartner(neu_db, "K-7001")
assert len(ps) == 1 and ps[0]["nachname"] == "Alt" and ps[0]["vorname"] == "Karl" and ps[0]["haupt"] == "ja"
assert ps[0]["email"] == "info@altbestand.de"
li = kd.adressen(neu_db, "K-7001", kd.LIEFERUNG)
assert len(li) == 1 and li[0]["plz"] == "54321"
assert len([k for k in neu_db.zeilen("kunden") if k["kundennr"] == "K-7001"]) == 1
assert "kunde_ansprech" in db_roh.spalten(neu_db.con, "angebote")
neu_db.con.close()
# zweites Öffnen: Migration läuft nicht noch einmal (keine doppelten Ansprechpartner/Adressen)
neu_db = Datenbank(alt_pfad)
assert len(kd.ansprechpartner(neu_db, "K-7001")) == 1 and len(kd.adressen(neu_db, "K-7001")) == 1
neu_db.con.close()
ok("10 Migration Schema 101 -> 102: Spalten und Tabellen ergänzt, PLZ/Ort geteilt, Ansprechpartner und Lieferadresse "
   "übernommen, nichts verloren, nur einmal")

print("OK: Kundenverwaltung (Kern)")
