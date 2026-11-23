"""Fenster „Kunde aus der Anfrage“ und Ablauf von der .msg bis zum Kundenstamm (Patrick 23.11.2026, MSG-Auftrag).

  14 Erkennung über die E-Mail des Ansprechpartners (nicht nur kunden.email) – im Hauptfenster wie beim Abruf
  15 Knopf „Kunde ändern …“: Fenster mit Kandidaten, Gegenüberstellung Feld | Datenbank | Neue E-Mail, nur Neues
     vorgehakt, Abweichungen nicht
  16 „Zuordnen und übernehmen“: nur die angehakten Werte, E-Mail ergänzt, Ansprechpartner der Anfrage gesetzt
  17 „Nur zuordnen“: Kundenstamm bleibt unverändert; „Anderen Kunden suchen …“
  18 „Neuen Kunden anlegen …“ aus der Mail (Eingabemaske der Kundenverwaltung, Ansprechpartner, Nummer K-…),
     zweites Mal gleiche Firma: Dublette, nichts angelegt
  19 Lesemodus: Fehler sichtbar, nichts zugeordnet; kaputte .msg in der Anfrage: Meldung statt Absturz

Aufruf: python tests/test_anfrage_kunde_ui.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien as t  # noqa: E402
from rohrlaser import anfrage_kunde as ak  # noqa: E402
from rohrlaser import anfragen_akten as akt  # noqa: E402
from rohrlaser import kunden_daten as kd  # noqa: E402
from rohrlaser import mail  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 23, 9, 0)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Laser Brundiers GmbH")
db.einstellung_setzen("eigene_domains", "laser.example")
db.einstellung_setzen("kunden_nummer_praefix", "K-")

WEISS = kd.anlegen(db, dict(name="Weiss und Soehne Stahlbau GmbH", strasse="", plz="58099", ort="Hagen",
                            email="info@weiss-stahlbau.de", telefon="+49 2331 99999"),
                   [dict(vorname="Jürgen", nachname="Weiß", email="j.weiss@weiss-stahlbau.de", haupt="ja")])
KRUEGER = kd.anlegen(db, dict(name="Metallbau Krüger GmbH", email="h.krueger@krueger-metall.de", ort="Lünen"))
EIGEN = {"laser.example"}
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
abl = seite.ablage()
ein = tmp / "ein"
ein.mkdir()

SIGNATUR = """Guten Tag,

bitte 200 Stück anbieten.

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


def akte_aus_mail(name, daten, schluessel):
    p = ein / name
    p.write_bytes(daten)
    # wie outlook_abrufen: Kunden mit Ansprechpartnern, Telefonen, USt-ID
    k = akt.mail_kopf(dict(quelle="ordner", eingang=D), mail.lesen(p), kd.mit_kontakten(db), EIGEN,
                      "Laser Brundiers GmbH", wurzel=abl.wurzel)
    a, _ = abl.anlegen(k, [p], schluessel, jetzt=D)
    abl.zuordnung_protokollieren(a)
    seite.neu_laden()
    seite.waehlen(a.nr)
    return abl.neu_lesen(a)


# ------------------------------------------------------------------ 14 Erkennung über den Ansprechpartner
a = akte_aus_mail("weiss.msg", t.msg("Anfrage Rohrteile", SIGNATUR, "Jürgen Weiß", "j.weiss@weiss-stahlbau.de", D,
                                     anhaenge=[("Teil 1.stp", b"ISO-10303-21;")]), "w1")
vorschlaege = [v["kundennr"] for v in a.zuordnung.get("vorschlaege") or []]
assert a.kunde == WEISS or WEISS in vorschlaege, a.zuordnung
ok("14 Mail des Ansprechpartners (nicht kunden.email): Kunde erkannt bzw. vorgeschlagen")

# ------------------------------------------------------------------ 15/16 Fenster: Gegenüberstellung, übernehmen
gesehen = {}


def bedienen(d):
    gesehen["kandidat"] = d.kandidaten[0]
    gesehen["fenster"] = d.windowTitle()
    assert d.kundennr == WEISS, d.kundennr
    z = {(x["bereich"], x["feld"]): x for x in d.zeilen}
    assert z[("kunde", "strasse")]["status"] == ak.NEU and z[("kunde", "strasse")]["vorschlag"]
    assert z[("kunde", "telefon")]["status"] == ak.ANDERS and not z[("kunde", "telefon")]["vorschlag"]
    assert z[("kunde", "ort")]["status"] == ak.GLEICH
    gesehen["kopf"] = [d.tabelle.horizontalHeaderItem(c).text() for c in range(d.tabelle.columnCount())]
    vorher = d.auswahl()
    assert ("kunde", "strasse") in vorher and ("kunde", "telefon") not in vorher, vorher
    assert d.haken("kunde", "website", False)          # Website bewusst nicht übernehmen
    assert d.haken("kunde", "ust_id", True)
    assert d.person.currentData() not in (None, "__neu__"), "vorhandener Ansprechpartner nicht vorgeschlagen"
    d.speichern()


r = seite.kunde_zuordnen(im_fenster=bedienen)
assert r is not None
k = kd.kunde(db, WEISS)
assert gesehen["kandidat"]["kundennr"] == WEISS and gesehen["kandidat"]["stufe"] == ak.EINDEUTIG, gesehen
assert gesehen["kopf"] == ["Übernehmen", "Feld", "Datenbank", "Neue E-Mail", "Stand"], gesehen["kopf"]
ok("15 Fenster „Kunde aus der Anfrage“: Kandidat eindeutig über die Kontakt-Mail; Neues vorgehakt, Abweichungen und "
   "Gleiches nicht")
assert k["strasse"] == "Industriestraße 12" and k["ust_id"].replace(" ", "") == "DE123456789", k
assert k["telefon"] == "+49 2331 99999", "abweichendes Telefon still überschrieben"
assert not (k.get("website") or ""), "Website trotz entferntem Haken"
p = next(x for x in kd.ansprechpartner(db, WEISS) if x["nachname"] == "Weiß")
assert p.get("mobil") == "0171 555 66 77" and p.get("position") == "Leiter Einkauf", p
assert len(kd.ansprechpartner(db, WEISS)) == 1, "Ansprechpartner doppelt angelegt"
a = abl.neu_lesen(a)
assert a.kunde == WEISS and "Weiß" in (a.zuordnung.get("ansprechpartner") or ""), a.zuordnung
assert any(h.get("feld") == "Straße und Hausnummer" and h.get("neu") == "Industriestraße 12"
           for h in kd.historie(db, WEISS, False)), \
    "Änderung nicht in der Kunden-Historie"
ok("16 Zuordnen und übernehmen: nur angehakte Werte, Telefon (abweichend) bleibt, Ansprechpartner ergänzt "
   "(Mobil, Position) und in der Anfrage gesetzt, Historie")

# ------------------------------------------------------------------ 17 Nur zuordnen, Suchen
vorher = kd.kunde(db, KRUEGER)


def nur(d):
    assert d.suchen(KRUEGER) == KRUEGER and d.kundennr == KRUEGER
    assert d.auswahl(), "keine neuen Werte vorgehakt"
    d.speichern(nur_zuordnen=True)


assert seite.kunde_zuordnen(im_fenster=nur) is not None
assert abl.neu_lesen(a).kunde == KRUEGER
nachher = kd.kunde(db, KRUEGER)
assert {f: nachher.get(f) for f in ("strasse", "telefon", "ust_id", "email")} == \
       {f: vorher.get(f) for f in ("strasse", "telefon", "ust_id", "email")}, "Nur zuordnen hat Kundendaten geändert"
assert not kd.ansprechpartner(db, KRUEGER)
ok("17 „Anderen Kunden suchen …“ + „Nur zuordnen“: Anfrage umgehängt, Kundenstamm unverändert")

# ------------------------------------------------------------------ 18 Neuer Kunde aus der Mail
NEU = SIGNATUR.replace("Jürgen Weiß", "Anna Berg").replace("Weiß & Söhne Stahlbau GmbH & Co. KG", "Berg Gerätebau GmbH") \
    .replace("Industriestraße 12", "Am Hafen 3").replace("D-58099 Hagen", "44147 Dortmund") \
    .replace("www.weiss-stahlbau.de", "www.berg-geraetebau.de").replace("DE 123 456 789", "DE 987 654 321") \
    .replace("+49 2331 123 45-0", "0231 44 55 66").replace("0171 555 66 77", "0160 1234567")
b = akte_aus_mail("berg.msg", t.msg("Anfrage Gestell", NEU, "Anna Berg", "a.berg@berg-geraetebau.de", D), "b1")
assert not b.kunde
neu_nr = {}


def anlegen(d):
    assert not d.kandidaten or d.kandidaten[0]["stufe"] != ak.EINDEUTIG, d.kandidaten
    neu_nr["nr"] = d.neu_anlegen(dubletten_ok=False)


assert seite.kunde_zuordnen(im_fenster=anlegen) is not None
nr = neu_nr["nr"]
assert nr and nr.startswith("K-"), nr
kb = kd.kunde(db, nr)
assert kb["name"] == "Berg Gerätebau GmbH" and kb["strasse"] == "Am Hafen 3" and kb["ort"] == "Dortmund", kb
pp = kd.ansprechpartner(db, nr)
assert len(pp) == 1 and pp[0]["nachname"] == "Berg" and pp[0]["email"] == "a.berg@berg-geraetebau.de", pp
assert abl.neu_lesen(b).kunde == nr
anzahl = len(db.zeilen("kunden"))
b2 = akte_aus_mail("berg2.msg", t.msg("Noch eine Anfrage", NEU, "Anna Berg", "a.berg@berg-geraetebau.de", D), "b2")
zweit = {}


def doppelt(d):
    assert d.kandidaten and d.kandidaten[0]["kundennr"] == nr, d.kandidaten
    zweit["nr"] = d.neu_anlegen(dubletten_ok=False)


seite.kunde_zuordnen(im_fenster=doppelt)
assert zweit["nr"] is None and len(db.zeilen("kunden")) == anzahl, "Dublette angelegt"
ok("18 Neuen Kunden aus der Mail anlegen (Nummer K-…, Anschrift, Ansprechpartner, zugeordnet); gleiche Firma "
   "nochmal: als Kandidat erkannt, keine Dublette angelegt")

# ------------------------------------------------------------------ 19 Lesemodus, kaputte Datei
c = akte_aus_mail("weiss2.msg", t.msg("Anfrage 2", SIGNATUR.replace("Industriestraße 12", "Industriestraße 14"),
                                      "Jürgen Weiß", "j.weiss@weiss-stahlbau.de", D), "w2")
db.nur_lesen = "Test"
fehl = {}


def lesemodus(d):
    d.kunde_waehlen(WEISS)
    assert d.haken("kunde", "strasse", True)
    fehl["erg"] = d.speichern()
    fehl["fehler"] = getattr(d, "fehler", None)


try:
    seite.kunde_zuordnen(im_fenster=lesemodus)
finally:
    db.nur_lesen = False
assert fehl["erg"] is None and fehl["fehler"], fehl
assert kd.kunde(db, WEISS)["strasse"] == "Industriestraße 12"
kaputt = ein / "kaputt.msg"
kaputt.write_bytes(b"\xd0\xcf\x11\xe0 kaputt")
seite._mail_pfad = lambda _a: kaputt           # Anfrage, deren .msg beschädigt ist
assert seite._mail_daten(abl.neu_lesen(c)) in (None, {}) or not seite._mail_daten(abl.neu_lesen(c)).get("name")
ok("19 Lesemodus: Fehler gezeigt, nichts gespeichert; beschädigte .msg: Meldung statt Absturz")
print("\nAlle Prüfungen bestanden.")
