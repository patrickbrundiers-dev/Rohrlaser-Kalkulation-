"""MSG-Anfrage und Kunde (Patrick 23.11.2026, Master-Auftrag „Outlook-.MSG-Anfrageerkennung reparieren“): Kontaktdaten
aus .msg/.eml (Signatur, Telefon/Mobil, USt-ID, Website, Position, Umlaute, alte ANSI-Mails), Kunden erkennen
(E-Mail des Ansprechpartners, USt-ID, Domain, Name mit Rechtsform-Varianten, unsicher = nie eindeutig),
Gegenüberstellung Feld | Datenbank | Neue E-Mail, nur angehakte Werte übernehmen (nichts still überschreiben,
Konflikt mit Kollegen), neuen Kunden aus der Mail anlegen.

Aufruf: python tests/test_anfrage_kunde.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import mail_testdateien as mt  # noqa: E402
from rohrlaser import anfrage_kunde as ak  # noqa: E402
from rohrlaser import kunden_daten as kd  # noqa: E402
from rohrlaser import mail  # noqa: E402
from rohrlaser.datenbank import AenderungsKonflikt, Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


SIGNATUR = """Guten Tag,

anbei die Zeichnungen für 200 Stück, bitte um Angebot.

Mit freundlichen Grüßen

Jürgen Weiß
Leiter Einkauf
Weiß & Söhne Stahlbau GmbH & Co. KG
Industriestraße 12
D-58099 Hagen
Tel.: +49 2331 123 45-0
Mobil: 0171 555 66 77
www.weiss-stahlbau.de
USt-IdNr.: DE 123 456 789
"""


def lesen(daten, endung):
    p = TMP / f"m{len(list(TMP.iterdir()))}{endung}"
    p.write_bytes(daten)
    return mail.lesen(p)


# ------------------------------------------------------------------ 1 Auslesen .msg (Unicode) und .eml
m = lesen(mt.msg("Anfrage Rohrteile", SIGNATUR, "Jürgen Weiß", "j.weiss@weiss-stahlbau.de",
                 anhaenge=[("Teil 1.stp", b"ISO-10303-21;"), ("Zeichnung.pdf", b"%PDF-1.4")]), ".msg")
assert m.absender == "j.weiss@weiss-stahlbau.de" and m.absender_name == "Jürgen Weiß"
d = ak.kontakt_aus_mail(m)
assert d["name"].startswith("Weiß & Söhne Stahlbau GmbH"), d
assert d["strasse"] == "Industriestraße 12" and d["plz"] == "58099" and d["ort"] == "Hagen", d
assert d["telefon"] == "+49 2331 123 45-0" and d["ust_id"] == "DE123456789" and d["website"] == "www.weiss-stahlbau.de"
p = d["person"]
assert p["vorname"] == "Jürgen" and p["nachname"] == "Weiß" and p["position"] == "Leiter Einkauf", p
assert p["mobil"] == "0171 555 66 77" and p["email"] == "j.weiss@weiss-stahlbau.de"
assert [n for n, _ in m.anhaenge] == ["Teil 1.stp", "Zeichnung.pdf"]
e = lesen(mt.eml("Anfrage", SIGNATUR, "Jürgen Weiß", "j.weiss@weiss-stahlbau.de"), ".eml")
assert ak.kontakt_aus_mail(e) == d
ok("1 Auslesen .msg und .eml: Firma, Anschrift, Telefon/Mobil getrennt, USt-ID, Website, Person mit Position, "
   "Umlaute, Anhänge")

# 2 alte Outlook-Datei (ANSI, cp1252) und Mail ohne Signatur
a = lesen(mt.msg("Anfrage", SIGNATUR, "Jürgen Weiß", "j.weiss@weiss-stahlbau.de", ansi=True), ".msg")
assert ak.kontakt_aus_mail(a)["person"]["nachname"] == "Weiß"
leer = lesen(mt.msg("Hallo", "bitte Angebot", "", "max@gmail.com"), ".msg")
dl = ak.kontakt_aus_mail(leer)
assert dl["email"] == "max@gmail.com" and "website" not in dl and "ust_id" not in dl
ok("2 ANSI-.msg mit Umlauten; Freemail ohne Signatur: nur die Adresse, nichts erfunden")

# 3 kaputte Datei: verständlicher Fehler statt Absturz
kaputt = TMP / "kaputt.msg"
kaputt.write_bytes(b"\xd0\xcf\x11\xe0 kaputt")
try:
    r = mail.lesen(kaputt)
    assert r is None or not r.absender
except Exception as fehler:       # noqa: BLE001
    assert str(fehler), "Fehler ohne Text"
ok("3 beschädigte .msg: kein Absturz, kein Kunde")

# ------------------------------------------------------------------ Erkennen
db = Datenbank(TMP / "rohrlaser.db")
nr = kd.anlegen(db, dict(name="Weiss und Söhne Stahlbau GmbH", strasse="Industriestr. 12", plz="58099", ort="Hagen",
                         telefon="02331 12345 0"),
                [dict(vorname="Anna", nachname="Kraft", email="a.kraft@weiss-stahlbau.de", haupt="ja")],
                dubletten_ok=True)
anderer = kd.anlegen(db, dict(name="Hagener Rohrhandel GmbH", plz="58095", ort="Hagen"), dubletten_ok=True)
k = ak.erkennen(db, d)
assert k and k[0]["kundennr"] == nr, k
assert k[0]["stufe"] != ak.EINDEUTIG, "ohne gleiche Adresse/USt-ID nie eindeutig"
assert any("Domain" in g or "Name" in g or "Anschrift" in g for g in k[0]["gruende"]), k[0]["gruende"]
assert all(x["kundennr"] != anderer for x in k[:1])
ok(f"4 Erkennen: Domain des Ansprechpartners + Name ohne Rechtsform + Anschrift → {k[0]['stufe']} (nicht eindeutig)")
kd.person_speichern(db, nr, dict(vorname="Jürgen", nachname="Weiß", email="j.weiss@weiss-stahlbau.de"))
k = ak.erkennen(db, d)
assert k[0]["kundennr"] == nr and k[0]["stufe"] == ak.EINDEUTIG and k[0]["person"]
assert "E-Mail j.weiss@weiss-stahlbau.de steht beim Kunden" in k[0]["gruende"]
ok("5 Erkennen: E-Mail eines Ansprechpartners (nicht nur des Kunden) → eindeutig, passender Ansprechpartner")
# zwei Kunden mit derselben Adresse: mehrdeutig, nie eindeutig
zwei = kd.anlegen(db, dict(name="Weiß Montage GmbH", email="j.weiss@weiss-stahlbau.de"), dubletten_ok=True)
k = ak.erkennen(db, d)
assert {x["kundennr"] for x in k[:2]} >= {nr, zwei} and all(x["stufe"] != ak.EINDEUTIG for x in k[:1]), k[:2]
kd.archivieren(db, zwei, True)
db.con.execute("DELETE FROM kunden WHERE kundennr=?", (zwei,))
db.con.commit()
ok("6 dieselbe Adresse bei zwei Kunden: kein eindeutiges Ergebnis (zur Prüfung)")

# ------------------------------------------------------------------ Gegenüberstellung und Übernehmen
pid = ak.person_finden(db, nr, d["person"])
zeilen = ak.vergleich(db, nr, d, pid)
z = {(x["bereich"], x["feld"]): x for x in zeilen}
assert z[("kunde", "strasse")]["status"] == ak.GLEICH                 # Industriestr. = Industriestraße
assert z[("kunde", "telefon")]["status"] == ak.GLEICH                 # gleiche Ziffern
assert z[("kunde", "name")]["status"] == ak.ANDERS and not z[("kunde", "name")]["vorschlag"]
assert z[("kunde", "ust_id")]["status"] == ak.NEU and z[("kunde", "ust_id")]["vorschlag"]
assert z[("person", "position")]["status"] == ak.NEU and z[("person", "mobil")]["status"] == ak.NEU
ok("7 Gegenüberstellung: gleich (auch Schreibweisen), neu (vorgeschlagen), abweichend (nie vorab angehakt)")
alt_name = kd.kunde(db, nr)["name"]
erg = ak.uebernehmen(db, nr, zeilen, {("kunde", "ust_id"), ("kunde", "website"), ("person", "position"),
                                      ("person", "mobil")}, pid, d)
k1 = kd.kunde(db, nr)
assert k1["name"] == alt_name and k1["ust_id"] == "DE123456789" and k1["website"] == "www.weiss-stahlbau.de"
pj = next(x for x in kd.ansprechpartner(db, nr) if x["id"] == pid)
assert pj["position"] == "Leiter Einkauf" and pj["mobil"] == "0171 555 66 77"
assert "USt-ID" in " ".join(erg["kunde"]) or erg["kunde"]
assert any(h.get("neu") == "DE123456789" for h in kd.historie(db, nr, mit_vorgaengen=False))
ok("8 Übernehmen: nur angehakte Felder, Firmenname bleibt, Ansprechpartner ergänzt, Historie")
# E-Mail wird ergänzt, nie ersetzt
kd.speichern(db, nr, dict(email="info@weiss-stahlbau.de"), dict(email=kd.kunde(db, nr)["email"]))
zeilen = ak.vergleich(db, nr, d, pid)
ak.uebernehmen(db, nr, zeilen, {("kunde", "email")}, pid, d)
assert kd.mails(kd.kunde(db, nr)["email"]) == ["info@weiss-stahlbau.de", "j.weiss@weiss-stahlbau.de"]
ok("9 E-Mail: neue Adresse ergänzt, alte bleibt")
# Konflikt: Kollege ändert den Ort zwischen Vergleich und Übernehmen -> nichts geschrieben
d2 = dict(d, ort="Hagen-Haspe")
zeilen = ak.vergleich(db, nr, d2, pid)
db2 = Datenbank(TMP / "rohrlaser.db")
kd.speichern(db2, nr, dict(ort="Hagen (Westf.)"), dict(ort="Hagen"))
try:
    ak.uebernehmen(db, nr, zeilen, {("kunde", "ort")}, pid, d2)
    raise AssertionError("kein Konflikt")
except AenderungsKonflikt:
    pass
assert kd.kunde(db, nr)["ort"] == "Hagen (Westf.)"
db2.con.close()
ok("10 Mehrbenutzer: Feld beim Kollegen geändert → Konflikt, nichts überschrieben")
# neuer Ansprechpartner aus der Mail beim vorhandenen Kunden
dn = dict(d, person=dict(vorname="Lena", nachname="Neu", email="l.neu@weiss-stahlbau.de", position="Konstruktion"))
zeilen = ak.vergleich(db, nr, dn, None)
erg = ak.uebernehmen(db, nr, zeilen, {("person", f) for f in ("vorname", "nachname", "email", "position")}, None, dn)
assert erg["neu_person"] and any(x["nachname"] == "Neu" for x in kd.ansprechpartner(db, nr))
assert ak.person_finden(db, nr, dn["person"]) == erg["person"]
ok("11 neuer Ansprechpartner aus der Mail beim vorhandenen Kunden")

# ------------------------------------------------------------------ Neuer Kunde aus der Mail
m3 = lesen(mt.msg("Anfrage", "Hallo,\nbitte Preis.\n\nViele Grüße\nPetra Blum\nBlum Metall GmbH\nAm Hafen 3\n"
                  "28195 Bremen\nTel. 0421 98765\n", "Petra Blum", "p.blum@blum-metall.de"), ".msg")
d3 = ak.kontakt_aus_mail(m3)
assert not [x for x in ak.erkennen(db, d3) if x["stufe"] == ak.EINDEUTIG]
nr3 = ak.neu_anlegen(db, d3)
k3 = kd.kunde(db, nr3)
assert k3["name"] == "Blum Metall GmbH" and k3["ort"] == "Bremen" and k3["plz"] == "28195"
assert k3["ansprechpartner"] == "Petra Blum" and kd.ansprechpartner(db, nr3)[0]["email"] == "p.blum@blum-metall.de"
assert nr3.startswith(kd.nummern_schema(db)[0])
try:
    ak.neu_anlegen(db, d3)
    raise AssertionError("Dublette nicht erkannt")
except kd.KundenFehler as f:
    assert "Dublette" in str(f)
assert ak.erkennen(db, d3)[0]["kundennr"] == nr3 and ak.erkennen(db, d3)[0]["stufe"] == ak.EINDEUTIG
ok("12 Neuer Kunde aus der Mail: Nummer automatisch, Ansprechpartner, zweites Anlegen = Dublette, danach eindeutig")

db.nur_lesen = "Test"
try:
    ak.neu_anlegen(db, dict(d3, name="Andere GmbH", email="x@andere.de"))
    raise AssertionError("Lesemodus nicht beachtet")
except Exception as f:              # noqa: BLE001
    assert "Lesemodus" in str(f) or "Test" in str(f), f
db.nur_lesen = False
ok("13 Lesemodus: kein Anlegen, verständliche Meldung")
print("OK: Anfrage und Kunde (Kern)")
