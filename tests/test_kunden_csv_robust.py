"""Prüft, dass der Kunden-CSV-Import mit allem zurechtkommt, was Excel und andere Programme aus einer CSV machen, und
verständlich meldet, was nicht geht (Patrick 28.10.2026: „Kundenliste CSV Export Import kommt Fehler“):
Export → Import unverändert (auch mit alten, heute ungültigen Werten), Zeilenumbruch, Semikolon und Anführungszeichen
in Feldern, Schutz vor Excel-Umwandlungen (="…"), Windows-Zeilenenden, UTF-16, Mac-Zeilenende CR, Windows-1252 mit
fehlenden Zeichen, Komma und Tab als Trennzeichen, 'sep=;', Titelzeile, nicht geschlossenes Anführungszeichen,
verrutschte Spalten, Excel-Fehlerwerte, gekürzte Zahlen, verlorene führende Null der Kundennummer, Länder als Name,
österreichische PLZ, Dateifehler (Datei in Excel geöffnet). Keine Ausnahme bei kaputten Dateien. Alle Kunden sind
Testwerte.

Aufruf: python tests/test_kunden_csv_robust.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import kunden_csv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


db = Datenbank(tmp / "k.db")
db.con.execute("DELETE FROM kunden")
db.con.commit()
db.neu("kunden", dict(kundennr="00123", name='Müller "Stahl" GmbH', telefon="+49 5250 123", strasse="Weg 1",
                      bemerkung="Zeile 1\nZeile 2; mit Semikolon", plz_ort="33129 Delbrück", skonto=2.5))
db.neu("kunden", dict(kundennr="10002", name="Ärger & Söhne", plz_ort="1010 Wien", plz="1010", land="AT",
                      lieferbedingung="ab Mond"))             # alter Wert, den es in der Auswahlliste nicht mehr gibt
db.neu("kunden", dict(kundennr="10003", name="Datum-Teile", telefon="-", ansprechpartner="=Chef", strasse="1-2"))
k = db.kontext()
vorhanden = db.zeilen("kunden")


def vorschau(roh, nur_neue=False):
    return kunden_csv.vorschau(roh, vorhanden, k, nur_neue)


def aktionen(v):
    return [(z["nr"], z["aktion"]) for z in v["zeilen"]]


# ------------------------------------------------------------------ Export, Excel-Schutz
text = kunden_csv.exportieren(vorhanden)
assert text.startswith("\ufeffKundennummer;Kundenname;") and "\r\n" in text and "\r\r\n" not in text
assert '"=""00123"""' in text and '"=""+49 5250 123"""' in text, text      # führende Null, +49 für Excel geschützt
assert '"=""1010"""' not in text and ";1010;" in text                         # 4 Ziffern ohne Null: bleibt
assert '"=""=Chef"""' in text and '"=""1-2"""' in text and ";-;" in text      # Formel und Datum geschützt
assert '"Zeile 1\nZeile 2; mit Semikolon"' in text and '"Müller ""Stahl"" GmbH"' in text
assert kunden_csv.spalte(0) == "A" and kunden_csv.spalte(25) == "Z" and kunden_csv.spalte(26) == "AA"
ok("Export: CRLF ohne doppelte Zeilenenden, Excel-Schutz =\"…\" nur wo Excel umwandeln würde, Maskierung")

v = vorschau(text.encode("utf-8"))
assert v["fehler"] == [] and [z["aktion"] for z in v["zeilen"]] == [kunden_csv.GLEICH] * 3, aktionen(v)
z = {z["kundennr"]: z for z in v["zeilen"]}
assert z["00123"]["kunde"]["telefon"] == "+49 5250 123" and z["00123"]["kunde"]["bemerkung"].count("\n") == 1
assert z["10002"]["kunde"]["plz_ort"] == "1010 Wien", "österreichische PLZ ohne Null"
assert any("„ab Mond“ unbekannt" in h for h in z["10002"]["hinweis"]), z["10002"]
ok("Export → Import: alles unverändert, auch alter ungültiger Wert (nur Hinweis), Excel-Schutz wieder entfernt")

# ------------------------------------------------------------------ Kodierungen, Zeilenenden, Trennzeichen
kopf = "Kundennummer;Kundenname;Telefon;Land;PLZ Ort"
zeilen = ["20001;Schäfer Rohrbau;05250 1;DE;33129 Delbrück", "20002;Öztürk Metall;0221 2;;50667 Köln"]
for name, roh in (("Windows (CRCRLF aus alter Version)", "\r\r\n".join([kopf] + zeilen).encode("utf-8")),
                  ("UTF-16 (Excel Unicode-Text, Tab)", "\r\n".join([kopf] + zeilen).replace(";", "\t").encode("utf-16")),
                  ("UTF-16 ohne BOM", "\r\n".join([kopf] + zeilen).encode("utf-16-le")),
                  ("Mac (CR)", "\r".join([kopf] + zeilen).encode("cp1252")),
                  ("Windows-1252", "\n".join([kopf] + zeilen).encode("cp1252")),
                  ("Komma", "\n".join([kopf] + zeilen).replace(";", ",").encode("utf-8")),
                  ("sep=;", ("sep=;\n" + "\n".join([kopf] + zeilen)).encode("utf-8-sig")),
                  ("Titelzeile", ("Kundenliste Stand 28.10.2026;;\n\n" + "\n".join([kopf] + zeilen)).encode("utf-8"))):
    v = vorschau(roh)
    assert v["fehler"] == [] and [z["aktion"] for z in v["zeilen"]] == [kunden_csv.NEU] * 2, (name, v)
    assert [z["name"] for z in v["zeilen"]] == ["Schäfer Rohrbau", "Öztürk Metall"], (name, v["zeilen"])
    assert v["zeilen"][1]["kunde"]["plz_ort"] == "50667 Köln", name
ok("Windows/Mac/UTF-16/Windows-1252, Trennzeichen ; , Tab, 'sep=;', Titelzeile über der Kopfzeile")

v = vorschau(b"Kundennummer;Kundenname\r\n20003;A\x81B GmbH\r\n")
assert aktionen(v) == [(2, kunden_csv.NEU)] and v["zeilen"][0]["name"].startswith("A"), v
ok("Bytes, die es in Windows-1252 nicht gibt: kein Abbruch")

# ------------------------------------------------------------------ verständliche Fehler
v = vorschau('Kundennummer;Kundenname\r\n20004;"Firma A\r\n20005;Firma B\r\n20006;Firma C\r\n'.encode())
assert aktionen(v) == [(2, kunden_csv.FEHLER)], v
assert v["zeilen"][0]["fehler"] == ['Spalte B: Anführungszeichen " nicht geschlossen, die Textzeilen 2–5 der Datei '
                                    "wurden zu einem Feld zusammengezogen"], v["zeilen"][0]["fehler"]
ok("nicht geschlossenes Anführungszeichen: gemeldet statt Zeilen zu verschlucken")

v = vorschau("Kundennummer,Kundenname,Telefon\n20007,Meyer, Hans,0221\n20008,Ok GmbH,0221\n".encode())
assert aktionen(v) == [(2, kunden_csv.FEHLER), (3, kunden_csv.NEU)], v
assert v["zeilen"][0]["fehler"][0].startswith("4 Werte, aber nur 3 Spalten in der Kopfzeile (Werte ab Spalte D): "
                                              "vermutlich ein Komma im Text"), v["zeilen"][0]["fehler"]
ok("verrutschte Spalten (Trennzeichen im Text ohne Anführungszeichen) als Fehler der Zeile")

v = vorschau("Kundennummer;Kundenname;Telefon;Skonto [%];Land;Zahlungsziel netto [Tage]\n"
             "20009;Fehlerwert;#NAME?;2;DE;30\n1,23457E+11;Gekürzt;;;;\n20010;Zahl;;viel;Deutschland;30 Tage\n"
             "123;Null weg;;;;\n20011;Land als Name;;;Österreich;\n".encode("cp1252"))
f = {z["nr"]: z for z in v["zeilen"]}
assert f[2]["fehler"][0].startswith("Spalte C (Telefon): Excel-Fehlerwert #NAME? statt Inhalt"), f[2]
assert f[3]["fehler"][0].startswith("Spalte A (Kundennummer): 1,23457E+11 ist eine von Excel gekürzte Zahl"), f[3]
assert f[4]["fehler"] == ["Spalte D (Skonto [%]): 'viel' ist keine Zahl.",
                          "Spalte F (Zahlungsziel netto [Tage]): '30 Tage' ist keine Zahl."], f[4]["fehler"]
assert f[4]["kunde"]["land"] == "DE" and "Land: Deutschland → DE" in f[4]["hinweis"]
assert f[5]["aktion"] == kunden_csv.AENDERN and f[5]["kundennr"] == "00123" and f[5]["kunden_id"], f[5]
assert "Kundennummer 123 → 00123 (führende Null, die Excel entfernt hat)" in f[5]["hinweis"]
assert f[6]["kunde"]["land"] == "AT" and f[6]["aktion"] == kunden_csv.NEU
ok("Excel-Fehlerwert, gekürzte Zahl, Text in Zahlenspalte mit Spalte A–F, Land als Name, führende Null der Nummer")

v = vorschau("Name;Telefon\nA;1\n".encode())
assert v["fehler"][0].startswith("Zeile 1: Kopfzeile ohne Spalte(n) Kundennummer (gelesen mit Trennzeichen Semikolon: "
                                 "Name, Telefon)"), v
assert vorschau(b"\r\n \r\n")["fehler"] == ["Die Datei ist leer"]
assert vorschau("nur;Text\nohne;Kopf\n".encode())["fehler"][0].startswith("Keine Kopfzeile gefunden")
ok("Kopfzeile fehlt / Datei leer / keine Kopfzeile: allgemeine Meldung statt Absturz")

# österreichische PLZ: Land aus dem vorhandenen Kunden, wenn die Datei keine Spalte Land hat
v = vorschau("Kundennummer;Kundenname;PLZ Ort\n10002;Ärger & Söhne;1020 Wien\n".encode())
assert v["zeilen"][0]["kunde"]["plz_ort"] == "1020 Wien" and not v["zeilen"][0]["hinweis"], v["zeilen"][0]
v = vorschau("Kundennummer;Kundenname;PLZ Ort\n20012;Neu DE;1067 Dresden\n".encode())
assert v["zeilen"][0]["kunde"]["plz_ort"] == "01067 Dresden"
ok("PLZ: führende Null nur für Deutschland, Land vom vorhandenen Kunden")

# ------------------------------------------------------------------ kaputte Dateien: nie eine Ausnahme
for roh in (b"\x00\x01\x02;\xff\xfe", b'"' * 5000, b"Kundennummer;Kundenname\n" + b'1;"' + b"x" * 200000,
            "Kundennummer;Kundenname\n1;A\r2;B\n".encode(), b"\xef\xbb\xbf", b"\xff\xfe"):
    v = vorschau(roh)
    assert isinstance(v["zeilen"], list) and isinstance(v["fehler"], list)
ok("kaputte Dateien (Binärdaten, endlose Anführungszeichen, riesiges Feld): Meldung, keine Ausnahme")

# ------------------------------------------------------------------ Dateifehler verständlich
try:
    from rohrlaser.kunden_csv_dialog import dateifehler
except ImportError:          # ohne Qt (nur Logik) prüfbar
    dateifehler = None
if dateifehler:
    t = dateifehler(PermissionError(13, "Permission denied"), r"C:\Users\Patrick\Kunden.csv")
    assert "noch in Excel geöffnet" in t and r"C:\Users\Patrick\Kunden.csv" in t, t
    assert "nicht gefunden" in dateifehler(FileNotFoundError(2, "x"), r"\\server\freigabe\Kunden.csv")
    ok("Dateifehler: Datei in Excel geöffnet / nicht gefunden verständlich, Windows- und Netzwerkpfad")

db.con.close()
print("Alle Tests Kunden-CSV robust bestanden.")
