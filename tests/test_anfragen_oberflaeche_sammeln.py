"""Seite „Anfragen“: Herkunft und Kunde, Dokumente & Mails, Chronik, Zusammenführen (Patrick 19./20.11.2026, Paket Z4).

  O1 Kasten „Herkunft und Kunde“ mit Stufe, Weiterleiter, Postfach, Vorschlag; Liste zeigt „⚠ Kunde prüfen“, Filter
  O2 Korrektur von Hand: Vorschlag übernehmen, Kunde ändern mit Lernregel (im Fenster Outlook … sichtbar, löschbar),
     Ansprechpartner, Absender, Intern ohne Kunde, Zurücksetzen; neuer Kunde nur nach Dubletten-Prüfung
  O3 Reiter „Dokumente & Mails“ (nach Kategorie) und „Chronik“; Hinzufügen, Outlook-Auswahl, Kategorie ändern
  O4 Vorschlag „Gehört vielleicht zu …“, Zusammenführen (Liste: „Zusammengeführt in …“), Rückgängig, Verschieben,
     Filter Kunde
  O5 Angebot per E-Mail auf eine intern weitergeleitete Anfrage: neue Mail an den Kunden, nie „Antworten“

Aufruf: python tests/test_anfragen_oberflaeche_sammeln.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien as t  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import angebot_mail  # noqa: E402
from rohrlaser import mail  # noqa: E402
from rohrlaser import mail_zuordnung as mz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 20, 8, 0)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Laser Brundiers GmbH")
db.einstellung_setzen("eigene_domains", "laser.example")
db.neu("kunden", dict(kundennr="10001", name="Metallbau Krüger GmbH", email="h.krueger@krueger-metall.de"))
db.neu("kunden", dict(kundennr="10002", name="Stahlbau Neumann GmbH", email="einkauf@stahlbau-neumann.de"))
EIGEN = {"laser.example"}
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
abl = seite.ablage()
kunden = db.zeilen("kunden")
ein = tmp / "ein"
ein.mkdir()


def akte_aus_mail(name, daten, schluessel):
    p = ein / name
    p.write_bytes(daten)
    k = ak.mail_kopf(dict(quelle="ordner", eingang=D), mail.lesen(p), kunden, EIGEN, "Laser Brundiers GmbH",
                     wurzel=abl.wurzel)
    a, _ = abl.anlegen(k, [p], schluessel, jetzt=D)
    abl.zuordnung_protokollieren(a)
    return abl.neu_lesen(a)


WG = ("Hallo Patrick, bitte anbieten.\nGruß Max\n\n________________________________\n"
      "Von: Otto Neu <o.neu@krueger-metall.de>\nGesendet: Mittwoch, 19. November 2026 16:40\n"
      "An: info@laser.example\nBetreff: Anfrage Gestell G-100\n\nBitte 5 Gestelle anbieten, Projekt-Nr. P-4711.\n")
a = akte_aus_mail("wg.msg", t.msg("WG: Anfrage Gestell G-100", WG, "Max Kollege", "max@laser.example", D), "o1")
seite.neu_laden()
seite.waehlen(a.nr)
assert a.kunde == "" and a.kunde_pruefen() and a.zuordnung["stufe"] == mz.WAHRSCHEINLICH, a.kopf
h = seite.inhalt.toHtml()
assert "Herkunft und Kunde" in h and "Max Kollege" in h and "info@laser.example" in h and "Vorschlag 10001" in h, h
zeile = next(r for r in range(seite.tabelle.rowCount()) if seite.tabelle.item(r, 0).text() == a.nr)
assert seite.tabelle.item(zeile, 1).text().startswith("⚠ Kunde prüfen"), seite.tabelle.item(zeile, 1).text()
seite.filter_daten.setCurrentIndex(seite.filter_daten.findData("pruefen"))
assert [x.nr for x in seite.sichtbare()] == [a.nr]
seite.filter_daten.setCurrentIndex(0)
ok("O1 Herkunft und Kunde: Stufe, Weiterleiter, Postfach, Vorschlag; Liste „⚠ Kunde prüfen“ und Filter")

# ------------------------------------------------------------------ O2
a = seite.kunde_zuordnen("10001", bestaetigen=True)
assert a.kunde == "10001" and not a.kunde_pruefen() and "von Hand" in seite.inhalt.toHtml()
a = seite.kunde_zuordnen("10002", regel=True, grund="Otto arbeitet jetzt bei Neumann")
regeln = mz.regeln_lesen(abl.wurzel)
assert a.kunde == "10002" and regeln and regeln[0]["wert"] == "o.neu@krueger-metall.de" and regeln[0]["von"] == "PB"
assert any("als Regel gemerkt" in ak.verlauf_text(e) for e in a.verlauf)
d = seite.outlook_zeigen()
assert "o.neu@krueger-metall.de" in d.regeln.toPlainText()
d._regel_link(SimpleNamespace(toString=lambda: f"regel_weg:{regeln[0]['id']}"))
assert not mz.regeln_lesen(abl.wurzel) and "Noch keine Regeln" in d.regeln.toPlainText()
d.close()
a = seite.ansprechpartner_setzen("Herr Neu")
a = seite.absender_korrigieren("otto.neu@stahlbau-neumann.de", "Otto Neu")
assert a.zuordnung["ansprechpartner"] == "Herr Neu" and a.absender_adresse == "otto.neu@stahlbau-neumann.de"
assert seite.absender_korrigieren("max@laser.example") is None          # eigene Adresse nie als Kunde
seite._link(SimpleNamespace(toString=lambda: "ohne_kunde:"))
a = seite.akte()
assert a.kunde == "" and a.zuordnung.get("ohne_kunde") and "Intern (ohne Kunde)" in seite.inhalt.toHtml()
seite._link(SimpleNamespace(toString=lambda: "zuruecksetzen:"))
a = seite.akte()
assert a.kunde == "" and a.kunde_pruefen() and a.absender_adresse == "o.neu@krueger-metall.de"
n0 = len(db.zeilen("kunden"))
assert seite.kunde_neu_anlegen() is None                     # Krüger-Domain schon im Stamm: Dublette, nichts angelegt
assert len(db.zeilen("kunden")) == n0
nr = seite.kunde_neu_anlegen(dict(kundennr="10003", name="Neu GmbH", email="otto@neu-gmbh.example"))
assert nr and seite.akte().kunde == nr and len(db.zeilen("kunden")) == n0 + 1
ok("O2 Korrekturen von Hand mit Lernregel (sichtbar, löschbar), Ansprechpartner, Absender, Intern, Zurücksetzen, "
   "neuer Kunde nach Dubletten-Prüfung")

# ------------------------------------------------------------------ O3
pdf = ein / "G-100_Zeichnung.pdf"
pdf.write_bytes(b"%PDF-1.4 zeichnung")
xls = ein / "Stueckliste.xlsx"
xls.write_bytes(b"PK\x03\x04 stueck")
r = seite.dokumente_hinzufuegen([pdf, xls], quelle="drag")
assert r["neu"] == ["G-100_Zeichnung.pdf", "Stueckliste.xlsx"], r
baum = seite.dokumente.baum
gruppen = [baum.topLevelItem(i).text(0) for i in range(baum.topLevelItemCount())]
assert any(g.startswith("Kundenanfrage") for g in gruppen) and any(g.startswith("Technische Zeichnungen")
                                                                     for g in gruppen), gruppen
assert "Mail von" in seite.chronik.toPlainText() and "Datei dazu" in seite.chronik.toPlainText()
weiter = t.msg("AW: Anfrage Gestell G-100", "Noch eine Frage", "Otto Neu", "o.neu@krueger-metall.de",
               D + datetime.timedelta(hours=5))


def outlook(befehl):
    daten = json.loads(Path(befehl[-2]).read_text(encoding="utf-8"))
    ziel = Path(daten["ziel"]) / "outlook_1.msg"
    ziel.write_bytes(weiter)
    Path(befehl[-1]).write_text(json.dumps(dict(neu=[dict(datei=str(ziel), mid="<x>")], fehler=[])),
                                encoding="utf-8-sig")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


seite.outlook_ausfuehren = outlook
r = seite.outlook_auswahl_hinzufuegen()
assert r and r["neu"] == ["outlook_1.msg"], r
seite.kategorie_setzen("Sonstige Dokumente", ["Stueckliste.xlsx"])
a = seite.akte()
from rohrlaser import anfragen_sammeln as sa  # noqa: E402
assert {d["name"]: d["kategorie"] for d in sa.dokumente(a)}["Stueckliste.xlsx"] == "Sonstige Dokumente"
assert "Anfragen zusammengeführt" not in seite.chronik.toPlainText()
ok("O3 Reiter Dokumente & Mails (nach Kategorie) und Chronik, Hinzufügen, Outlook-Auswahl, Kategorie ändern")

# ------------------------------------------------------------------ O4
a = seite.kunde_zuordnen("10001", grund="Test")
b = akte_aus_mail("b.msg", t.msg("Nachtrag Gestell G-100", "Neue Zeichnung, Projekt-Nr. P-4711",
                                 "Hans Krüger", "h.krueger@krueger-metall.de", D + datetime.timedelta(days=1),
                                 [("G-100_Zeichnung.pdf", b"%PDF-1.4 zeichnung")]), "o2")
seite.neu_laden()
seite.waehlen(b.nr)
assert "Gehört vielleicht zu" in seite.inhalt.toHtml() and a.nr in seite.inhalt.toHtml()
assert abl.lesen(b.nr).status == ak.NEU                         # nur Vorschlag
seite.waehlen(a.nr)
assert seite.zusammenfuehren([b.nr]) is None                    # ohne Bestätigung passiert nichts
jid = seite.zusammenfuehren([b.nr], bestaetigt=True)
assert jid and abl.lesen(b.nr).stand["zusammengefuehrt_in"] == a.nr
seite.ordner_waehlen(ak.ERLEDIGT)
zeile = next(r for r in range(seite.tabelle.rowCount()) if seite.tabelle.item(r, 0).text() == b.nr)
assert seite.tabelle.item(zeile, 7).text() == f"Zusammengeführt in {a.nr}"
seite.ordner_waehlen(ak.NEU)
seite.waehlen(a.nr)
assert not seite.dokumente.k_trennen.isHidden()
assert seite.trennen() and abl.lesen(b.nr).status == ak.NEU
c = akte_aus_mail("c.msg", t.msg("Andere", "x", "Hans", "h.krueger@krueger-metall.de", D), "o3")
seite.neu_laden()
seite.waehlen(a.nr)
assert seite.dokumente_verschieben(["outlook_1.msg"], c.nr) is not None
assert "outlook_1.msg" in [d["name"] for d in abl.lesen(c.nr).dateien()]
assert "outlook_1.msg" not in [d["name"] for d in abl.lesen(a.nr).dateien()]
seite._auswahl_fuellen()
seite.filter_kunde.setCurrentIndex(seite.filter_kunde.findData("10001"))
assert {x.nr for x in seite.sichtbare()} == {a.nr, b.nr, c.nr}, [x.nr for x in seite.sichtbare()]
seite.filter_kunde.setCurrentIndex(0)
ok("O4 Vorschlag, Zusammenführen nur nach Bestätigung, Liste „Zusammengeführt in …“, Rückgängig, Verschieben, "
   "Filter Kunde")

# ------------------------------------------------------------------ O5
m = mail.lesen(ein / "wg.msg")
sicher = angebot_mail.anfrage_sicher(m, EIGEN, "Laser Brundiers GmbH")
assert sicher.keine_antwort and sicher.kunde_an == "o.neu@krueger-metall.de"
assert not angebot_mail.antwort_moeglich(ein / "wg.msg", sicher)
assert angebot_mail.empfaenger({}, sicher) == "o.neu@krueger-metall.de"
direkt = mail.lesen(ein / "b.msg")
assert angebot_mail.anfrage_sicher(direkt, EIGEN) is direkt and angebot_mail.antwort_moeglich(ein / "b.msg", direkt)
ok("O5 Angebot per E-Mail auf intern weitergeleitete Anfrage: neue Mail an den Kunden, interne Notizen bleiben intern")
print("Alle Tests bestanden.")
