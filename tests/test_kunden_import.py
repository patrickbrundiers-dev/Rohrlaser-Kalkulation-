"""Kundenlisten-CSV-Import auf der gemeinsamen Importbasis (Master-Auftrag 25.11.2026): Spalten deutsch/englisch,
„Name“ je nach Zusammenhang nur als Vorschlag, Listen ohne Kopfzeile, Dublettenprüfung (Kundennummer, Name in
Varianten, E-Mail, Telefon, Anschrift, USt-ID; ähnliche Namen nicht automatisch gleich), Optionen je Zeile,
Kundennummer nie erfunden und nie geändert (Angebote bleiben verknüpft), Ansprechpartner/Adressen/Rabatt, ergänzen
statt überschreiben, Importlauf mit Rückgängig, Fehlerbericht, Importprofile, 10.000 Zeilen. Alle Kunden sind Testwerte.

Aufruf: python tests/test_kunden_import.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import csv_import, kunden_csv as K, kunden_daten as kd  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


db = Datenbank(tmp / "k.db")
db.con.execute("DELETE FROM kunden")
db.con.commit()
db.neu("kunden", dict(kundennr="10001", name="Muster GmbH", strasse="Hauptstr. 1", plz="33100", ort="Paderborn",
                      plz_ort="33100 Paderborn", email="info@muster.de", telefon="05251 123456", land="DE"))
db.neu("kunden", dict(kundennr="10002", name="Beispiel Metallbau AG", ust_id="DE123456789", plz="33129",
                      ort="Delbrück", plz_ort="33129 Delbrück", telefon="+49 5250 999"))
db.neu("kunden", dict(kundennr="10003", name="Stahl Schmidt KG", strasse="Werkweg 4", plz="59555", ort="Lippstadt"))
kd_alt = {k["kundennr"]: dict(k) for k in db.zeilen("kunden")}

# ------------------------------------------------------------------ 1 Spaltenerkennung deutsch/englisch
csv = ("Customer ID;Company;Contact;Mail;Phone;Street;ZIP;City;Country;VAT ID;Discount\n"
       "10001;MUSTER GmbH.;Max Mustermann;max@muster.de;05251 123456;Hauptstr. 1;33100;Paderborn;Germany;;3\n"
       ";Neu Rohrtechnik GmbH;Erika Neu;e.neu@neu-rohr.de;0521 777;Industriestr. 9;33602;Bielefeld;DE;;\n"
       "20010;Beispiel Metallbau;;;;;;;;DE 123 456 789;\n"
       ";Muster Metallbau GmbH;;;;;;;;;\n"
       "20011;Ganz Neu KG;;kaputt@;;;;;;;\n")
daten = K.lesen(csv.encode("utf-8"), "kunden.csv")
assert daten["mit_kopf"] and daten["trenner"] == ";", daten
erk = K.spalten_erkennen(daten)
sp = csv_import.zuordnung(erk)
for f, s in (("kundennr", 0), ("name", 1), ("ansprechpartner", 2), ("email", 3), ("telefon", 4), ("strasse", 5),
             ("plz", 6), ("ort", 7), ("land", 8), ("ust_id", 9), ("rabatt", 10)):
    assert sp.get(f) == s, (f, sp.get(f), erk)
ok("englische Spaltennamen erkannt (Customer ID, Company, Mail, ZIP, City, VAT ID, Discount)")

# „Name“ mehrdeutig: mit Firmenspalte = Person, ohne = Firma, immer Vorschlag
d2 = K.lesen("Firma;Name;Vorname\nA GmbH;Meier;Jan\n".encode(), "x.csv")
e2 = K.spalten_erkennen(d2)
assert e2["nachname"]["spalte"] == 1 and e2["nachname"]["sicherheit"] == csv_import.VORSCHLAG, e2
d3 = K.lesen("Name;Ort\nA GmbH;Paderborn\n".encode(), "x.csv")
e3 = K.spalten_erkennen(d3)
assert e3["name"]["spalte"] == 0 and e3["name"]["sicherheit"] == csv_import.VORSCHLAG, e3
ok("„Name“: neben „Firma“ der Nachname, allein die Firma, beides nur als Vorschlag")

# Liste ohne Kopfzeile: Firmenname wird nicht als Kopf gelesen
d4 = K.lesen("Muster GmbH;Hauptstr. 1;Paderborn\nB AG;Weg 2;Lippstadt\n".encode("cp1252"), "o.csv")
assert not d4["mit_kopf"] and len(d4["zeilen"]) == 2, d4
ok("Liste ohne Kopfzeile erkannt (Spalten A, B, C zum Zuordnen)")

# ------------------------------------------------------------------ 2 Analyse: Dubletten und Optionen
v = K.analysieren(db, daten, sp)
z = {e["zeile"]: e for e in v}
assert z[2]["gruppe"] == K.G_AENDERN and z[2]["kundennr"] == "10001", z[2]
felder = {f for f, _a, _n in z[2]["aenderungen"]}
assert "name" not in felder and "kundennr" not in felder, z[2]["aenderungen"]
assert "Ansprechpartner" in felder and "rabatt" in felder, z[2]["aenderungen"]
ok("gleiche Kundennummer: aktualisieren, nur neue Werte (Name „MUSTER GmbH.“ bleibt, Kundennummer nie)")
assert z[3]["gruppe"] == K.G_FEHLER and any("von Hand" in f for f in z[3]["fehler"]), z[3]
ok("neuer Kunde ohne Kundennummer: fehlende Pflichtangabe, keine Nummer erfunden")
assert z[4]["option"] == K.AKTUALISIEREN and z[4]["kundennr"] == "10002", z[4]
assert any("Umsatzsteuer" in g for g in z[4]["treffer"][0][1]), z[4]["treffer"]
ok("gleiche USt-ID (anders geschrieben): sicher derselbe Kunde, andere Nummer in der Datei geändert nichts")
assert z[5]["gruppe"] == K.G_DUBLETTE and z[5]["option"] is None, z[5]
ok("„Muster Metallbau GmbH“ ähnlich „Muster GmbH“: nur mögliche Dublette, entscheidet der Anwender")
assert z[6]["gruppe"] == K.G_FEHLER and any("E-Mail" in f for f in z[6]["fehler"]), z[6]
ok("ungültige E-Mail-Adresse: fehlerhafte Zeile")

# Kundennummer von Hand, Entscheidungen von Hand
v = K.analysieren(db, daten, sp, kundennummern={3: "20001"},
                  entscheidungen={5: (K.ZUORDNEN, "10001"), 4: (K.UEBERSPRINGEN,)})
z = {e["zeile"]: e for e in v}
assert z[3]["gruppe"] == K.G_NEU and z[3]["kundennr"] == "20001", z[3]
assert z[3]["person"] and z[3]["person"]["nachname"] == "Neu", z[3]["person"]
assert z[4]["gruppe"] == K.G_UEBERSPRUNGEN and z[5]["kundennr"] == "10001", (z[4], z[5])
v2 = K.analysieren(db, daten, sp, kundennummern={3: "10002"})
assert any("schon vergeben" in f for f in {e["zeile"]: e for e in v2}[3]["fehler"])
ok("Kundennummer von Hand, Überspringen und manuell zuordnen; vergebene Nummer abgelehnt")

# ------------------------------------------------------------------ 3 Ergänzen statt überschreiben
d5 = K.lesen("Kundennummer;Firma;Telefon;Ort\n10001;Muster GmbH;0170 1;Bad Lippspringe\n".encode(), "x.csv")
s5 = csv_import.zuordnung(K.spalten_erkennen(d5))
e5 = K.analysieren(db, d5, s5)[0]
assert e5["gruppe"] == K.G_GLEICH and {f for f, _a, _n in e5["behalten"]} == {"telefon", "ort"}, e5
e5 = K.analysieren(db, d5, s5, modus=K.UEBERSCHREIBEN)[0]
assert {f for f, _a, _n in e5["aenderungen"]} >= {"telefon", "ort", "plz_ort"}, e5["aenderungen"]
ok("fremde Datei: vorhandene Werte bleiben (nur leere Felder), überschreiben nur auf Wunsch")

# ------------------------------------------------------------------ 4 Übernehmen, Historie, Rückgängig
v = K.analysieren(db, daten, sp, kundennummern={3: "20001"}, entscheidungen={5: (K.UEBERSPRINGEN,)})
erg = K.uebernehmen(db, v, "kunden.csv", sichern=False)
assert erg["neu"] == 1 and erg["geaendert"] == 1 and erg["personen"] == 2, erg   # 10002: nur behaltene Werte
neu = kd.kunde(db, "20001")
assert neu["name"] == "Neu Rohrtechnik GmbH" and neu["plz_ort"] == "33602 Bielefeld", neu
assert db.con.execute("SELECT COUNT(*) FROM kunden_ansprechpartner WHERE kundennr='20001'").fetchone()[0] == 1
assert db.con.execute("SELECT rabatt FROM kundenvorgaben WHERE kundennr='10001'").fetchone()[0] == 3
assert kd.kunde(db, "10001")["name"] == "Muster GmbH" and kd.kunde(db, "10002")["kundennr"] == "10002"
hist = db.con.execute("SELECT COUNT(*) FROM kunden_historie WHERE kundennr='10001' AND text='CSV-Import'").fetchone()[0]
assert hist >= 1, hist
ok("übernommen: 1 neu, 1 aktualisiert (10002 unverändert, Name bleibt), Ansprechpartner und Rabatt, Kundenhistorie")
laeufe = csv_import.laeufe(db, csv_import.ART_KUNDEN)
assert laeufe and laeufe[0]["id"] == erg["import_id"], laeufe
n, meld = K.rueckgaengig(db, erg["import_id"])
assert kd.kunde(db, "20001") is None, meld
assert db.con.execute("SELECT COUNT(*) FROM kundenvorgaben WHERE kundennr='10001'").fetchone()[0] == 0
for nr, alt in kd_alt.items():
    jetzt = kd.kunde(db, nr)
    for f in ("name", "telefon", "email", "ust_id", "ansprechpartner", "plz_ort"):
        assert (jetzt.get(f) or None) == (alt.get(f) or None), (nr, f, jetzt.get(f), alt.get(f))
ok("Rückgängig: neuer Kunde, Ansprechpartner, Rabatt weg, alte Werte zurück")

# Kunde mit Angebot bleibt beim Rückgängig
v = K.analysieren(db, daten, sp, kundennummern={3: "20001"}, entscheidungen={5: (K.UEBERSPRINGEN,)})
erg = K.uebernehmen(db, v, "kunden.csv", sichern=False)
db.con.execute("INSERT INTO angebote (nummer, kundennr) VALUES ('T-1', '20001')")
db.con.commit()
n, meld = K.rueckgaengig(db, erg["import_id"])
assert kd.kunde(db, "20001") and any("Angebot" in m for m in meld), meld
ok("Rückgängig lässt Kunden, an denen schon ein Angebot hängt (Verknüpfung bleibt)")

# ------------------------------------------------------------------ 5 Fehlerbericht und Profile
v = K.analysieren(db, daten, sp)
bericht = K.fehlerbericht(v, daten["kopf"])
assert "Zeile" in bericht.splitlines()[0] and "kaputt@" in bericht, bericht
csv_import.profil_speichern(db, K.IMPORTPROFILE, "ERP Export", daten["kopf"], sp)
alle = csv_import.profile(db, K.IMPORTPROFILE)
assert csv_import.profil_kopieren(db, K.IMPORTPROFILE, "ERP Export") and len(csv_import.profile(db, K.IMPORTPROFILE)) == 2
csv_import.profil_loeschen(db, K.IMPORTPROFILE, [n for n in csv_import.profile(db, K.IMPORTPROFILE) if n != "ERP Export"][0])
assert list(csv_import.profile(db, K.IMPORTPROFILE)) == ["ERP Export"]
name, prof, sp2 = csv_import.profil_passend(alle, daten["kopf"], None)
assert name == "ERP Export" and sp2 == sp, (name, sp2)
umgestellt = list(reversed(daten["kopf"]))
name, prof, sp3 = csv_import.profil_passend(alle, umgestellt, None)
assert name == "ERP Export" and sp3["name"] == len(umgestellt) - 1 - sp["name"], sp3
ok("Fehlerbericht als CSV, Importprofil speichern/kopieren/löschen, auch bei anderer Spaltenreihenfolge")

# ------------------------------------------------------------------ 6 Assistent in 5 Schritten
from rohrlaser import kunden_import_assistent as KA  # noqa: E402

pfad = tmp / "liste.csv"
pfad.write_bytes(csv.encode("cp1252"))
a = KA.assistent(None, db, pfad, sichern=False)
assert len(a.schritte) == 5 and a.modus.currentData() == K.ERGAENZEN
assert a.spalten.profilname == "ERP Export"           # gespeichertes Profil passt
assert a.weiter() and a.weiter() and a.nr == 2
p = a.pruef
zeilen_sicht = {e["zeile"] for e in p.sichtbar}
assert {3, 5, 6} <= zeilen_sicht and 2 not in zeilen_sicht, zeilen_sicht   # 2: gleiche Kundennummer, eindeutig
assert not p.setzen(2, K.UEBERSPRINGEN)
assert p.setzen(3, K.NEU_ANLEGEN, "20002") and p.setzen(5, K.UEBERSPRINGEN) and p.setzen(6, K.UEBERSPRINGEN)
assert a.weiter() and a.nr == 3, a.meldung.text()
z = K.zaehlen_import(a.posten)
assert z[K.G_NEU] == 1 and z[K.G_DUBLETTE] == 0 and z[K.G_FEHLER] == 0, z
assert a.vorschau_s.t.rowCount() == len(a.posten)
assert a.weiter() and a.nr == 4 and "Bereit zum Import" in a.abschluss.info.text()
assert a.weiter() and a.fertig, a.meldung.text()
assert kd.kunde(db, "20002")["name"] == "Neu Rohrtechnik GmbH"
assert a.abschluss.rueckgaengig() and kd.kunde(db, "20002") is None
ld = a.datei.laeufe_zeigen(zeigen=False)
assert ld.t.rowCount() >= 3
ok("Assistent: 5 Schritte, Profil automatisch, Entscheidungen je Zeile, Import, Rückgängig, letzte Importe")

# Weg über den Reiter Kunden bleibt: Test-Aufruf mit bestaetigt (alte Vorschau)
from rohrlaser.kunden_csv_dialog import csv_importieren  # noqa: E402
erg_alt, _ = csv_importieren(None, db, str(pfad), bestaetigt=False)
assert erg_alt and "zeilen" in erg_alt
ok("bisheriger Aufruf ohne Fenster (bestaetigt) unverändert")

# ------------------------------------------------------------------ 7 Tempo: 10.000 Zeilen gegen 3.000 Kunden
with db.con:
    for i in range(3000):
        db.con.execute("INSERT INTO kunden (kundennr, name, plz, ort, email) VALUES (?, ?, ?, ?, ?)",
                       (f"5{i:05d}", f"Firma {i} GmbH", "33100", "Paderborn", f"info@firma{i}.de"))
zeilen = ["Kundennummer;Firma;PLZ;Ort;E-Mail"] + [
    f"{'5%05d' % i if i % 2 else '6%05d' % i};Firma {i} GmbH;33100;Paderborn;info@firma{i}.de" for i in range(10000)]
gross = K.lesen("\n".join(zeilen).encode(), "gross.csv")
t0 = time.perf_counter()
vg = K.analysieren(db, gross, csv_import.zuordnung(K.spalten_erkennen(gross)))
dauer = time.perf_counter() - t0
assert len(vg) == 10000 and dauer < 60, dauer
ok(f"10.000 Zeilen gegen 3.000 Kunden geprüft in {dauer:.1f} s ({K.zaehlen_import(vg)})")
print("Alle Prüfungen bestanden.")
