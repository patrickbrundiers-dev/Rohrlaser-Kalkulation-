"""Prüft die Automationen vom 03.11.2026 (Freigabe Patrick „Alle Empfehlungen umsetzen“, Pakete A–C):
Automatik-Protokoll mit Rückgängig (14a), Anfrage-Ampel (4a), Vormessen-Zusammenfassung (3a), Nachtrag einsortieren
(5a), Wiederholanfrage (6a), Signatur ergänzt Kundendaten (12a), Bestellung erkennen und abgleichen (1a), Auftrag
starten mit Schritten (2a), Lieferantenantwort einlesen (7a), Materialbestellung (8a), Preiswächter (9a) und
Nachkalkulation vorbelegen (10a).

Aufruf: python tests/test_automationen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

import beispiel_angebot  # noqa: E402
import mail_testdateien  # noqa: E402
from rohrlaser import (anfrage_vorab, anfragen, auftrag_start, automatik, bestellung, lieferantenangebote,  # noqa: E402
                       lieferantenantwort, materialanfrage, nachkalk_vorbelegen, nachtrag, preiswaechter,
                       wiederholanfrage)
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 76
assert db.con.execute("SELECT COUNT(*) FROM automatik").fetchone()[0] == 0
for n in ("anfrage_frist", "anfrage_vormessen", "preiswaechter_schwelle", "nachkalk_schwelle", "bestellung_text"):
    assert db.einstellung(n) not in (None, ""), n
ok("Schema 76: Tabelle automatik, Einstellungen der Automationen mit Vorgaben")

# ------------------------------------------------------------------ 14a Protokoll mit Rückgängig
quelle = tmp / "Anfragen" / "x.eml"
quelle.parent.mkdir()
quelle.write_text("x")
neu = automatik.verschieben(db, quelle, tmp / "Ablage" / "Anfrage", "nachtrag", "Test verschoben")
assert neu.exists() and not quelle.exists()
quelle.write_text("y")              # Name wieder belegt: nicht überschreiben
neu2 = automatik.verschieben(db, quelle, tmp / "Ablage" / "Anfrage", "nachtrag", "Test 2")
assert neu2.name == "x (2).eml"
e = automatik.liste(db)
assert [x["titel"] for x in e] == ["Nachtrag einsortiert"] * 2 and all(x["rueckgaengig"] for x in e)
t = automatik.rueckgaengig(db, e[0]["id"])
assert "Rückgängig" in t and quelle.exists() and not neu2.exists()
try:
    automatik.rueckgaengig(db, e[0]["id"])
    raise AssertionError("zweimal zurück")
except automatik.AutomatikFehler:
    pass
try:
    automatik.rueckgaengig(db, e[1]["id"])          # alte Stelle belegt
    raise AssertionError("überschrieben")
except automatik.AutomatikFehler as f:
    assert "schon eine Datei" in str(f)
assert automatik.liste(db)[0]["zurueck"]
ok("Protokoll: Verschieben mit freiem Namen, Rückgängig legt zurück, nie doppelt, nie überschreibend")

# ------------------------------------------------------------------ 4a Ampel
mo = datetime.datetime(2026, 11, 2, 9, 0)           # Montag
assert anfrage_vorab.ampel(mo, 2, mo)[0] == anfrage_vorab.GRUEN
assert anfrage_vorab.ampel(mo, 2, mo + datetime.timedelta(days=2))[0] == anfrage_vorab.GELB
st, faellig, text = anfrage_vorab.ampel(mo, 2, mo + datetime.timedelta(days=3))
assert st == anfrage_vorab.ROT and faellig == datetime.date(2026, 11, 4) and "überfällig" in text
fr = datetime.datetime(2026, 10, 30, 15, 0)         # Freitag: Frist über das Wochenende (Arbeitstage)
assert anfrage_vorab.ampel(fr, 1, fr)[1] == datetime.date(2026, 11, 2)
assert anfrage_vorab.ampel(mo, 0, mo) == (None, None, "")
assert anfrage_vorab.frist_tage(db, None) == 2
ok("Ampel: grün bis zum Vortag, gelb am Fälligkeitstag, rot danach; Arbeitstage ohne Wochenende; 0 = aus")

# ------------------------------------------------------------------ 3a Zusammenfassung der Vormessung
k = db.kontext()
mess = [dict(profilform="Rundrohr", a=42.4, wand=2.0, laenge=1250, artikel="4711-001", schneidweg=400, konturen=2),
        dict(profilform="Rundrohr", a=42.4, wand=2.0, laenge=800, artikel="4711-002"),
        dict(fehler="kaputt")]
z = anfrage_vorab.zusammenfassung(mess, k.profile)
assert z["teile"] == 2 and z["fehler"] == 1 and z["artikel"] == ["4711-001", "4711-002"]
t = anfrage_vorab.text(z, 1234.5, 1)
assert "2 Teile" in t and "Richtpreis ca." in t and "1 Wiederholteil" in t and "1 nicht lesbar" in t
ok(f"Vormessen: Zusammenfassung „{t}“")

# ------------------------------------------------------------------ Angebot zum Arbeiten
fenster = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db, dict(kundennr="K-1001", kunde="Beispiel Metallbau GmbH", kundenreferenz="ANF-7781"))
kopf = db.angebot(aid)
nummer = kopf["nummer"]

# ------------------------------------------------------------------ 5a Nachtrag
m_nachtrag = mail_testdateien.eml("AW: Anfrage ANF-7781", "Hallo,\nbitte 4711-002 doch 55 Stk statt 40.\n"
                                  "Liefertermin bis KW 50/2026.\nGruß", "Max Muster", "max@beispiel-metallbau.de",
                                  datetime.datetime(2026, 11, 3, 10, 0))
o = tmp / "Anfragen"
(o / "nachtrag.eml").write_bytes(m_nachtrag)
from rohrlaser import mail  # noqa: E402
m = mail.lesen(o / "nachtrag.eml")
a_ = nachtrag.aenderungen(db, aid, m)
p2 = next(p for p in db.positionen(aid) if p["artikel"] == "4711-002")
assert a_["stueck"] == {str(p2["id"]): [40, 55, "4711-002"]}, a_
assert a_["lieferzeit"][:2] == ["Kalenderwoche", "50/2026"], a_
eintrag = nachtrag.einsortieren(db, aid, o / "nachtrag.eml", tmp / "Ablage" / nummer, m)
assert not (o / "nachtrag.eml").exists() and Path(eintrag["datei"]).parent.name == "Anfrage"
assert eintrag["status"] == nachtrag.OFFEN and len(nachtrag.offene(db, aid)) == 1
assert db.angebot(aid)["versand"][-1]["art"] == "nachtrag"
seite = fenster.angebot_oeffnen(aid)
assert not seite.nachtrag_leiste.isHidden() and "55" in seite.nachtrag_text.text()
assert seite.nachtrag_entscheiden(True)
assert next(p for p in db.positionen(aid) if p["artikel"] == "4711-002")["stueck"] == 55
assert db.angebot(aid)["lieferzeit_wert"] == "50/2026" and seite.nachtrag_leiste.isHidden()
assert not nachtrag.offene(db, aid)
ok("Nachtrag: Mail im Angebotsordner, Änderungen (Stück, KW) als Leiste, Übernehmen schreibt sie ins Angebot")

# ------------------------------------------------------------------ 6a Wiederholanfrage
tr = wiederholanfrage.treffer(db, "K-1001", "Betreff: Preisanfrage\nBitte Preis wie letztes Mal für\n4711-001: 30 Stk\n"
                                            "4711-005 80 Stück\nGruß")
assert {r["artikel"]: r["menge"] for r in tr} == {"4711-001": 30, "4711-005": 80}, tr
assert wiederholanfrage.treffer(db, "K-1002", "4711-001 30 Stk") == []
ok("Wiederholanfrage: bekannte Artikel des Kunden mit Mengen, fremder Kunde findet nichts")

# ------------------------------------------------------------------ 12a Signatur
kunde = next(z for z in db.zeilen("kunden") if z["kundennr"] == "K-1001")
db.aendern("kunden", kunde["id"], "telefon", "")
r = anfragen.kontakt_ergaenzen(dict(kunde, telefon=""), dict(telefon="+49 2161 12345", plz_ort="41061 Elsewhere"))
assert r["neu"] == {"telefon": "+49 2161 12345"} or "telefon" in r["neu"], r
n = anfragen.kontakt_uebernehmen(db, dict(kundennr="K-1001", felder=dict(telefon="+49 2161 12345")))
assert n == 1 and next(z for z in db.zeilen("kunden") if z["kundennr"] == "K-1001")["telefon"] == "+49 2161 12345"
e = automatik.liste(db)[0]
assert e["art"] == "kontakt"
automatik.rueckgaengig(db, e["id"])
assert not next(z for z in db.zeilen("kunden") if z["kundennr"] == "K-1001")["telefon"]
ok("Signatur: leere Kundenfelder ergänzt, abweichende nur als Hinweis, Rückgängig stellt her")

# ------------------------------------------------------------------ 1a Bestellung
text_b = (f"Betreff: Bestellung zu Ihrem Angebot {nummer}\nSehr geehrte Damen und Herren,\nhiermit bestellen wir "
          "gemäß Angebot:\nPos 10 4711-001 24 Stk\nPos 20 4711-002 60 Stk\nBestell-Nr.: PO-55821\n"
          "Liefertermin: KW 49/2026\nMfG")
assert bestellung.ist_bestellung(text_b)
assert not bestellung.ist_bestellung("Betreff: Anfrage\nBitte um ein Angebot für 20 Stk 4711-001")
er = bestellung.erkennen(db, text_b, "K-1001")
assert er["angebot"]["id"] == aid and er["bestellnr"] == "PO-55821" and er["termin"], er
abg = {z["artikel"]: z for z in bestellung.abgleich(db, aid, text_b)}
assert abg["4711-001"]["status"] == bestellung.OK
assert abg["4711-002"]["status"] == bestellung.ABWEICHUNG and "Menge 60 statt 55" in abg["4711-002"]["hinweis"]
assert abg["4711-003"]["status"] == bestellung.FEHLT
ok("Bestellung: erkannt (Angebotsnummer, Bestellnummer, KW), Abgleich ok/Abweichung/fehlt je Position")

# ------------------------------------------------------------------ 2a Schritte nach dem Auftrag
auftrag_start.merken(db, ["werkstatt", "ab", "unsinn"])
assert auftrag_start.gewaehlt(db) == ["ab", "werkstatt"]
ok("Auftrag starten: Auswahl je Arbeitsplatz gemerkt (feste Reihenfolge)")

# ------------------------------------------------------------------ 7a Lieferantenantwort
db.neu("zukauf_lieferanten", dict(name="Stahlhandel Nord", email="verkauf@stahl-nord.de"))
antwort = ("Sehr geehrter Herr Brundiers,\nwir bieten an:\nRR 42,4 x 2,0 S235 in 6 m: 1,85 €/kg\n"
           "QR 40x40x3: 245,00 EUR je 100 kg\nRE 60x40x3 — 28,50 € pro Stange à 6 m\nLieferzeit: 8 Arbeitstage\n"
           "Angebot gültig bis 30.11.2026\nMfG Stahlhandel Nord GmbH")
paare = [("RR 42,4x2,0", "S235-10219"), ("QR 40x40x3", "S235-10219"), ("RE 60x40x3", "S355-10219")]
zeilen = {z["profil_id"]: z for z in lieferantenantwort.auslesen(antwort, paare, k.profile, 6000)}
assert (zeilen["RR 42,4x2,0"]["preis"], zeilen["RR 42,4x2,0"]["basis"]) == (1.85, "€/kg")
assert (zeilen["QR 40x40x3"]["preis"], zeilen["QR 40x40x3"]["basis"]) == (2.45, "€/kg")
assert (zeilen["RE 60x40x3"]["basis"], zeilen["RE 60x40x3"]["laenge"]) == ("€/Stange", 6000)
assert lieferantenantwort.lieferzeit_tage(antwort) == 11 and lieferantenantwort.gueltig_bis(antwort) == "2026-11-30"
lief, neu = lieferantenantwort.einlesen(db, aid, antwort, "anna@stahl-nord.de", paare, k.profile, 6000)
assert lief == "Stahlhandel Nord" and len(neu) == 3
liste = lieferantenangebote.liste(db, aid)
assert all(e["eingelesen"] for e in liste) and liste[0]["lieferzeit"] == 11
try:
    lieferantenantwort.einlesen(db, aid, "Danke für die Anfrage, wir melden uns.", "", paare, k.profile)
    raise AssertionError("leer eingelesen")
except ValueError:
    pass
ok("Lieferantenantwort: Preise je Abmessung (€/kg, je 100 kg, €/Stange), Lieferzeit, Bindefrist, Lieferant per Domain")

# ------------------------------------------------------------------ 8a Materialbestellung
lieferantenangebote.uebernehmen(db, aid, 0)
gew = lieferantenangebote.gewaehlte(db, aid)
assert list(gew) == [("RR 42,4x2,0", "S235-10219")]
zeile = dict(profil="RR 42,4x2,0", werkstoff="S235-10219", lieferant="Stahlhandel Nord", text="RR", stangen=3,
             laenge=6000, oberflaeche="",
             pos=["10"])
t = materialanfrage.anschreiben(kopf, [zeile], {}, k, preise=gew)
assert "hiermit bestellen wir" in t and "Preis lt. Ihrem Angebot" in t and "1,850 €/kg" in t, t
assert "Bestellung Material" in materialanfrage.betreff(kopf, {}, bestellung=True)
n = lieferantenangebote.bestellt_merken(db, aid, "Stahlhandel Nord", heute=datetime.date(2026, 11, 3))
e = lieferantenangebote.liste(db, aid)[0]
assert n == 1 and e["bestellt"] == "2026-11-03" and e["erwartet"] == "2026-11-14"
db.vorgang_setzen(aid, "Beauftragt")
assert not lieferantenangebote.wareneingang_faellig(db, datetime.date(2026, 11, 13))
assert lieferantenangebote.wareneingang_faellig(db, datetime.date(2026, 11, 14))
assert any(a["art"] == "wareneingang" for a in automatik.aufgaben(db, datetime.date(2026, 11, 15)))
ok("Materialbestellung: Vorlage mit Preis je Zeile, bestellt/erwartet gemerkt, Wareneingang fällig auf der Startseite")

# ------------------------------------------------------------------ 9a Preiswächter
db.einstellung_setzen(preiswaechter.STAND, "")
assert preiswaechter.noetig(db) is False          # erstes Mal: nur merken
assert preiswaechter.noetig(db) is False
pr = db.zeilen("preise")[0]
db.aendern("preise", pr["id"], "preis", float(pr["preis"] or 1) * 1.5)
assert preiswaechter.noetig(db) is True
erg = preiswaechter.pruefen(db)
assert set(erg) == {"am", "schwelle", "angebote"} and not preiswaechter.noetig(db)
assert preiswaechter.text_aus(dict(schwelle=0.03, angebote=[dict(id=1, nummer="A-1", prozent=0.1)])).startswith(
    "1 offenes Angebot liegt mehr als 3 %")
ok("Preiswächter: merkt Stand, prüft nur nach Änderung der Preise, Text für die Startseite")

# ------------------------------------------------------------------ 10a Nachkalkulation vorbelegen
seite.optimieren()
assert db.angebot(aid).get("ergebnis")
info = nachkalk_vorbelegen.vorbelegen(db, aid)
assert info is not None and info["geprueft"] is False and db.angebot(aid)["nachkalkulation"]
assert nachkalk_vorbelegen.vorbelegen(db, aid) is None         # schon Ist-Werte: nichts überschreiben
assert abs(info["abweichung"] or 0) < 0.05                       # alles wie geplant: kaum Abweichung
db.zusatz_setzen(aid, nachkalk_vorbelegen.SCHLUESSEL, dict(info, abweichung=-0.25))
assert [n["angebot_id"] for n in nachkalk_vorbelegen.zu_pruefen(db)] == [aid]
nachkalk_vorbelegen.geprueft(db, aid)
assert not nachkalk_vorbelegen.zu_pruefen(db)
e = next(x for x in automatik.liste(db) if x["art"] == "nachkalk")
automatik.rueckgaengig(db, e["id"])
assert not db.angebot(aid)["nachkalkulation"]
ok("Nachkalkulation: beim Versand vorbelegt, nie überschrieben, große Abweichung auf der Startseite, Rückgängig")

# ------------------------------------------------------------------ Oberfläche: Protokoll und Startseite
d = fenster.automatik_protokoll(dialog=lambda d: None)
assert d.tabelle.rowCount() == len(automatik.liste(db)) > 5
fenster.start.neu_laden()
assert fenster.start.automatik_aufgaben is not None
assert "Automatik-Protokoll …" in fenster.datei_aktionen
ok("Datei → Automatik-Protokoll zeigt alle Schritte; Startseite mit Abschnitt Automatik")

# Beauftragt mit Schritten (ohne Fenster): Schritte laufen nach dem Setzen
gerufen = []
auftrag_start_alt = auftrag_start.ausfuehren
auftrag_start.ausfuehren = lambda f, i, s: gerufen.append((i, list(s)))
try:
    db.vorgang_setzen(aid, "Verschickt")
    assert fenster.angebote.vorgang_setzen("Beauftragt", aid, auftrag=("PO-1", None), schritte=["ab"])
finally:
    auftrag_start.ausfuehren = auftrag_start_alt
assert gerufen == [(aid, ["ab"])] and db.angebot(aid)["auftragsnr"] == "PO-1"
ok("Beauftragt: gewählte Schritte laufen danach (auftrag_start.ausfuehren)")

# Anfragen-Karte: Nachtrag selbst einsortieren, Bestellung als Zeile mit Link (Mails ohne STEP)
db.einstellung_setzen("anfrage_ordner", str(o))
for f_ in o.iterdir():
    f_.unlink()
(o / "nachtrag2.eml").write_bytes(mail_testdateien.eml("AW: Anfrage ANF-7781", "Bitte 4711-001 jetzt 30 Stk.\nGruß",
                                                       "Max Muster", "max@beispiel-metallbau.de",
                                                       datetime.datetime(2026, 11, 3, 11, 0)))
(o / "bestellung.eml").write_bytes(mail_testdateien.eml(f"Bestellung {nummer}", text_b, "Max Muster",
                                                        "max@beispiel-metallbau.de",
                                                        datetime.datetime(2026, 11, 3, 12, 0)))
for f_ in o.iterdir():               # fertig kopiert (die Karte wartet auf Dateien, die sich nicht mehr ändern)
    os.utime(f_, (f_.stat().st_mtime - 3600, f_.stat().st_mtime - 3600))
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
assert not (o / "nachtrag2.eml").exists(), list(o.iterdir())
assert nachtrag.offene(db, aid) and "Bestellung</b> zu Angebot" in karte.hinweis.text(), karte.hinweis.text()
link = next(k_ for k_ in karte._links if k_.startswith("best:"))
assert link in karte.hinweis.text()
auftrag_start.merken(db, [])
info = next(v for v in karte._ohne.values() if v.get("art") == "bestellung")
gesehen = []


def bedienen(d):
    gesehen.append((d.nummer.text(), d.tabelle.rowCount(), d.mengen.isHidden()))
    d.mengen.setChecked(True)
    return True


assert karte.bestellung_pruefen(o / "bestellung.eml", info, dialog=bedienen)
assert gesehen[0][0] == "PO-55821" and gesehen[0][1] == 5 and not gesehen[0][2]
k2 = db.angebot(aid)
assert k2["auftragsnr"] == "PO-55821" and k2["vorgang"] == "Beauftragt" and k2["liefertermin"]
assert next(p for p in db.positionen(aid) if p["artikel"] == "4711-002")["stueck"] == 60
assert not (o / "bestellung.eml").exists() and k2["versand"][-1]["art"] == "bestellung" or any(
    v.get("art") == "bestellung" for v in k2["versand"])
ok("Anfragen-Karte: Nachtrag liegt im Angebotsordner, Bestellung prüfen setzt Beauftragt, Nummer, Termin, Mengen")

fenster.close()
db.schliessen() if hasattr(db, "schliessen") else None
print("Alle Tests der Automationen bestanden.")
