"""Prüft „Zukaufartikelverwaltung optional“ (Master-Auftrag Patrick 23.11.2026): die zentrale Zukaufartikel-Datenbank
ist ein Schalter (Vorgabe aus), Zukaufartikel gehören nur zum Angebot. Die zwölf Szenarien des Auftrags:
 1 Angebot ohne Zukaufartikel, 2 Zukaufartikel direkt im Angebot anlegen, 3 mehrere hinzufügen (auch aus Excel),
 4 bearbeiten, Reihenfolge, löschen, 5 speichern und erneut öffnen, 6 Angebot duplizieren, 7 aus anderem Angebot
 kopieren (unabhängig), 8 zentrale Verwaltung aktivieren, 9 deaktivieren (nichts verloren, Rechnung gleich),
 10 bestehende Angebote nach der Umstellung öffnen, 11 PDFs, 12 Gesamtkalkulation, Margen, MwSt.
Dazu: ohne Stamm keine Abfrage auf die Zukauf-Tabellen beim Öffnen, Rechnen, Prüfen und im Dialog; STEP-Import,
Blech-Editor, EK eintragen und Materialanfrage ohne Stamm; Liste der Blech-IDs gleich wie vorher.
Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_optional.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import (angebot_mehr, ausgabe, blech, blech_preis, funktionen, materialanfragen, pdf, rechnen,  # noqa: E402
                       zukauf, zukauf_bestand, zukauf_kopie)
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.zukauf_dialog import EDIT, HERKUNFT, NUR_ANGEBOT, ZukaufDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())
SPALTE = {name: c for c, name in EDIT.items()}


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


class Zaehler:
    """Abfragen auf die Zukauf-Tabellen (zukauf_*) zählen."""

    def __init__(self, db):
        self.klasse, self.n = type(db.con), 0
        self.alt = self.klasse.execute

    def __enter__(self):
        z = self

        def execute(selbst, sql, *a, **k):
            if "zukauf_" in str(sql):
                z.n += 1
            return z.alt(selbst, sql, *a, **k)
        self.klasse.execute = execute
        return self

    def __exit__(self, *_):
        self.klasse.execute = self.alt


db = Datenbank(tmp / "f.db")
db.einstellung_setzen("aufschlag_blech", None)
db.einstellung_setzen("aufschlag_zukauf", None)
db.einstellung_setzen("zukauf_aufschlag", 10)       # Standardaufschlag Zukaufteile 10 %
k, tab = db.kontext(), db.tabellen()

# ------------------------------------------------------------------ Schalter
assert db.einstellung(funktionen.ZUKAUF_STAMM) == "nein" and not funktionen.zukauf_stamm(db), "Vorgabe: aus"
assert funktionen.zukauf_stamm(), "ohne Datenbank (Tests, Dialoge allein) wie bisher an"
db.einstellung_setzen(funktionen.ZUKAUF_STAMM, "ja")
assert funktionen.zukauf_stamm(db)
db.einstellung_setzen("funktion_zukauf", "nein")
assert not funktionen.zukauf_stamm(db), "Zukaufteile ganz aus nimmt die zentrale Verwaltung mit"
db.einstellung_setzen("funktion_zukauf", "ja")
# Altbestand mit zentraler Verwaltung: ein Stammartikel (Blech) in einem bestehenden Angebot
alt_id = db.zukauf_speichern(None, dict(artikelnr="ST-1", bezeichnung="Stammschraube M10", kategorie="Kaufteile",
                                        einheit="Stück", status="aktiv"),
                             [dict(lieferant="Lieferant Alt", bevorzugt="ja", preiseinheit=1,
                                   preise=[dict(ab=1, preis=0.5)], lieferzeit=12)])
blech_id = db.zukauf_speichern(None, dict(bezeichnung="Blech alt 100x50x3", kategorie="Kaufteile", einheit="Stück",
                                          status="aktiv", artikeltyp=zukauf.BLECH),
                               [dict(lieferant="Blech GmbH", bevorzugt="ja", preiseinheit=1,
                                     preise=[dict(ab=1, preis=4.0)])])
alt = db.angebot_neu(dict(kunde="Altkunde", skonto=0))
db.position_neu(alt, dict(pos=10, artikel="Alt A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                          stueck=10, schneidweg=300, einstiche=2,
                          zukauf=json.dumps([dict(artikel_id=alt_id, menge=2, stand=db.zukauf_stand(alt_id)),
                                             dict(artikel_id=blech_id, menge=1, stand=db.zukauf_stand(blech_id))])))
db.einstellung_setzen(funktionen.ZUKAUF_STAMM, "nein")
n_artikel = len(db.zukauf_artikel_liste())
tab = db._tabellen_bauen()
assert tab["blech_artikel"] == [a["id"] for a in db.zeilen("zukauf_artikel") if a.get("artikeltyp") == zukauf.BLECH] \
    == [blech_id], "Blech-IDs nur über die IDs gelesen: gleiche Liste wie vorher"
ok("Schalter: Vorgabe aus, an/aus jederzeit, Zukaufteile aus = auch zentral aus; Blech-IDs wie vorher")


def rechnung(aid):
    kopf, pos = db.angebot(aid), db.positionen(aid)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    return kopf, pos, einst, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


# ------------------------------------------------------------------ 1 Angebot ohne Zukaufartikel
a = db.angebot_neu(dict(kunde="Test", skonto=0))
db.position_neu(a, dict(pos=10, artikel="Rohr A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2))
db.position_neu(a, dict(pos=20, artikel="Rohr B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                        stueck=20, schneidweg=200, einstiche=2))
_, _, _, (z, s) = rechnung(a)
assert s["zukauf"] == [] and s["verkauf"] > 0
vk_ohne = s["verkauf"]
ok("1 Angebot ohne Zukaufartikel: rechnet ohne Zukaufkosten, keine zentrale Verwaltung nötig")

f = Hauptfenster(db, stumm=True)
f.resize(1600, 950)
f.show()
seite = f.angebot_oeffnen(a)
app.processEvents()
assert not f.zukauf.unter.isTabVisible(f.zukauf.unter.indexOf(f.zukauf.artikel)), "Unterreiter Artikel aus"
assert f.zukauf.unter.isTabVisible(f.zukauf.unter.indexOf(f.zukauf.lieferanten)), "Lieferanten bleiben"
assert f.zukauf.aus_hinweis.isVisibleTo(f.zukauf) and f.zukauf.artikel.daten == [], "Stamm nicht geladen"


def dialog(aid, r=0, s_=None):
    sx = s_ or f.angebot_oeffnen(aid)
    return ZukaufDialog(sx, db, db.positionen(aid)[r])


# ------------------------------------------------------------------ 2 direkt im Angebot anlegen
with Zaehler(db) as zl:
    d = dialog(a, s_=seite)
assert zl.n == 0, f"Dialog ohne zentrale Verwaltung: {zl.n} Abfragen auf den Artikelstamm"
assert d.auswahl.count() == 0 and d.merken_knopf.isHidden() and \
    d.knoepfe_leiste["Aus Stammdaten aktualisieren …"].isHidden(), "keine Stammauswahl, kein Merken"
d.auswahl.setEditText("Schraube M8")
d.menge.setText("4")
d.ek.setText("0,15")
d._hinzufuegen_klick()
assert len(d.eintraege) == 1 and zukauf.ist_frei(d.eintraege[0]) and d.tabelle.item(0, HERKUNFT).text() == NUR_ANGEBOT
d.feld_setzen(0, "lieferant", "Würth")
d.feld_setzen(0, "beschreibung", "verzinkt")
d.feld_setzen(0, "bemerkung", "INTERN nur Würth")
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
assert len(db.zukauf_artikel_liste()) == n_artikel, "nichts im Artikelstamm gespeichert"
ok("2 Zukaufartikel direkt im Angebot: Bezeichnung, Menge, EK, Lieferant, Beschreibung, interne Bemerkung; "
   "0 Stammabfragen")

# ------------------------------------------------------------------ 3 mehrere gleichzeitig
d = dialog(a, s_=seite)
n, fehler = d.mehrere_hinzufuegen("Bezeichnung\tMenge\tEK\tArtikelnr.\tLieferant\n"
                                  "Mutter M8\t4\t0,08\tM8-934\tWürth\nNietmutter M8\t2\t0,25\n\t3\n"
                                  "Griff; 1; 7,90; G-100; Muster GmbH")
assert n == 3 and fehler == ["Zeile 4: Bezeichnung fehlt"], (n, fehler)
assert [e["stand"]["bezeichnung"] for e in d.eintraege] == ["Schraube M8", "Mutter M8", "Nietmutter M8", "Griff"]
assert d.eintraege[1]["stand"]["artikelnr"] == "M8-934" and d.eintraege[3]["stand"]["bezug"]["lieferant"] == \
    "Muster GmbH"
assert d.mehrere(dialog=lambda x: (x.text.setPlainText("Scheibe M8; 8; 0,02"), QDialog.Accepted)[1]) == 1
assert len(d.eintraege) == 5
ok("3 Mehrere Zukaufartikel auf einmal: Liste aus Excel (Tab) und mit Semikolon, Kopfzeile übersprungen, Fehler "
   "je Zeile")

# ------------------------------------------------------------------ 4 bearbeiten, Reihenfolge, löschen
d.tabelle.item(4, SPALTE["menge"]).setText("6")
assert d.eintraege[4]["menge"] == 6
d.feld_setzen(3, "ek", 8.5)
assert zukauf.ek_einheit(d.eintraege[3]["stand"]) == zukauf.dez(8.5)
assert d.verschieben([3], -1) == [2] and d.eintraege[2]["stand"]["bezeichnung"] == "Griff"
assert d.verschieben([0], -1) == [0], "erste Zeile bleibt oben"
assert d.verschieben([1, 2], 1) == [2, 3] and [e["stand"]["bezeichnung"] for e in d.eintraege][:4] == \
    ["Schraube M8", "Nietmutter M8", "Mutter M8", "Griff"]
d.duplizieren([3])
assert len(d.eintraege) == 6 and d.eintraege[5] == d.eintraege[3] and d.eintraege[5] is not d.eintraege[3]
d.entfernen([5, 4])
assert [e["stand"]["bezeichnung"] for e in d.eintraege] == ["Schraube M8", "Nietmutter M8", "Mutter M8", "Griff"]
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
ok("4 Bearbeiten (Menge, EK), Reihenfolge ▲▼, duplizieren, löschen")

# ------------------------------------------------------------------ 5 speichern und erneut öffnen
gespeichert = db.positionen(a)[0]["zukauf"]
f.angebot_schliessen(a)
seite = f.angebot_oeffnen(a)
d = dialog(a, s_=seite)
assert d.eintraege == json.loads(gespeichert) and d.eintraege[0]["stand"]["bemerkung"] == "INTERN nur Würth"
assert [d.tabelle.item(r, 0).text() for r in range(4)] == ["Schraube M8", "Nietmutter M8", "Mutter M8", "Griff"]
d.reject()
ok("5 Speichern und erneut öffnen: alle Felder und die Reihenfolge wiederhergestellt")

# ------------------------------------------------------------------ 6 Angebot duplizieren
_, _, _, (z, s) = rechnung(a)
kopie = db.angebot_kopieren(a)
assert json.loads(db.positionen(kopie)[0]["zukauf"]) == json.loads(gespeichert)
_, _, _, (z2, s2) = rechnung(kopie)
nah(s2["zukauf_einstand"], s["zukauf_einstand"], "Kopie rechnet gleich")
nah(s2["verkauf"], s["verkauf"], "Kopie: gleicher Verkaufspreis")
ok("6 Angebot duplizieren: Zukaufartikel mitkopiert, gleiche Kalkulation")

# ------------------------------------------------------------------ 7 aus anderem Angebot kopieren
quelle = zukauf_kopie.eintraege(db, alt)
assert [x["eintrag"]["stand"]["bezeichnung"] for x in quelle] == ["Stammschraube M10", "Blech alt 100x50x3"]
d = dialog(a, 1, s_=seite)
gewaehlt = {}


def bedienen(x):
    assert x.angebot_waehlen(alt)
    assert x.artikel.rowCount() == 2 and x.artikel.item(0, 1).text() == "Stammschraube M10"
    x.markieren([0])
    x._ok()
    gewaehlt.update(quelle=x.quelle, auswahl=x.auswahl)
    return x.result()


assert d.aus_angebot_waehlen(dialog=bedienen) == 1 and gewaehlt == dict(quelle=alt, auswahl=[0])
neu = d.eintraege[0]
assert zukauf.ist_frei(neu) and "artikel_id" not in neu and neu["stand"]["kopiert_aus"].startswith("Angebot ")
assert "kopiert aus" in d.tabelle.item(0, HERKUNFT).text()
d.feld_setzen(0, "ek", 0.55)               # beim Kopieren unabhängig bearbeitbar
d.feld_setzen(0, "bezeichnung", "Schraube M10 (Kopie)")
d.accept()
assert seite.zukaufteile([1], werte=d.ergebnis)
q = json.loads(db.positionen(alt)[0]["zukauf"])
assert q[0]["stand"]["bezeichnung"] == "Stammschraube M10" and zukauf.ek_einheit(q[0]["stand"]) == zukauf.dez(0.5), \
    "Ursprung unverändert"
q[0]["stand"]["bezug"]["preise"] = [dict(ab=1, preis=9.99)]                 # später im Ursprung geändert
db.position_aendern(db.positionen(alt)[0]["id"], "zukauf", json.dumps(q))
e1 = json.loads(db.positionen(a)[1]["zukauf"])[0]
assert zukauf.ek_einheit(e1["stand"]) == zukauf.dez(0.55), "Kopie ändert sich nicht mit dem Ursprung"
assert zukauf_kopie.kopie(q[0], "X", stamm=True)["artikel_id"] == alt_id, "mit zentraler Verwaltung: Verweis bleibt"
ok("7 Aus anderem Angebot kopieren: unabhängige Kopie (ohne Stammverweis), Ursprung unverändert und ohne Einfluss")

# ------------------------------------------------------------------ 8 zentrale Verwaltung aktivieren
_, _, _, (z_aus, s_aus) = rechnung(alt)
db.einstellung_setzen(funktionen.ZUKAUF_STAMM, "ja")
f.funktionen_anwenden()
assert f.zukauf.unter.isTabVisible(f.zukauf.unter.indexOf(f.zukauf.artikel)) and \
    not f.zukauf.aus_hinweis.isVisibleTo(f.zukauf)
assert len(f.zukauf.artikel.daten) == n_artikel, "beim Einschalten geladen"
d = dialog(a, s_=seite)
assert d.auswahl.count() == n_artikel and not d.merken_knopf.isHidden()
assert not d.knoepfe_leiste["Aus Stammdaten aktualisieren …"].isHidden()
r = d.frei_hinzufuegen("Merkartikel", 1, ek=3)
assert d.merken([r]) == 1 and len(db.zukauf_artikel_liste()) == n_artikel + 1, "Im Artikelstamm merken geht wieder"
d.reject()
bericht = zukauf_bestand.pruefen(db)
assert bericht["ohne_stand"] == [] and bericht["stamm"] >= 2 and bericht["eintraege"] >= 7, bericht
t = zukauf_bestand.text(bericht, True)
assert t.startswith("Zentrale Zukaufartikelverwaltung eingeschaltet") and "nichts geändert" in t
n_artikel += 1
ok("8 Zentrale Verwaltung aktivieren: Artikel-Reiter, Stammauswahl, Merken, Aktualisieren; Bestandsprüfung")

# ------------------------------------------------------------------ 9 deaktivieren
_, _, _, (z_an, s_an) = rechnung(alt)
vorher = {p["id"]: p["zukauf"] for p in db.positionen(alt)}
db.einstellung_setzen(funktionen.ZUKAUF_STAMM, "nein")
f.funktionen_anwenden()
_, _, _, (z_aus2, s_aus2) = rechnung(alt)
for x, y in ((s_aus, s_an), (s_an, s_aus2)):
    for n in ("zukauf_einstand", "zukauf_aufschlag", "verkauf"):
        nah(x[n], y[n], f"{n} gleich vor/nach dem Umschalten")
assert {p["id"]: p["zukauf"] for p in db.positionen(alt)} == vorher, "Angebot nicht verändert"
assert len(db.zukauf_artikel_liste()) == n_artikel, "Stammartikel bleiben erhalten"
assert zukauf_bestand.text(zukauf_bestand.pruefen(db), False).startswith("Zentrale Zukaufartikelverwaltung "
                                                                         "ausgeschaltet")
ok("9 Zentrale Verwaltung deaktivieren: Angebote und Stamm unverändert, Kalkulation bitgleich in beiden Modi")

# ------------------------------------------------------------------ 10 bestehende Angebote nach der Umstellung
with Zaehler(db) as zl:
    s_alt = f.angebot_oeffnen(alt)
    s_alt.neu_laden()
    punkte = s_alt.freigabe_punkte()
assert zl.n == 0, f"Öffnen, Rechnen, Prüfen ohne zentrale Verwaltung: {zl.n} Stammabfragen"
d = dialog(alt, s_=s_alt)
assert d.tabelle.item(0, HERKUNFT).text().startswith(NUR_ANGEBOT + " · Preisstand vom")
assert d.vergleich() == [] and d._vorschau(d.eintraege)[0]["vk"] > 0
d.reject()
tage, name = angebot_mehr.zukauf_lieferzeit(db.positionen(alt), None)
assert (tage, name) == (12, "Stammschraube M10"), "Lieferzeit aus dem Preisstand ohne Stamm"
ok("10 Bestehende Angebote öffnen: rechnen und prüfen ohne Stammabfrage, Lieferzeit aus dem Preisstand")

# ------------------------------------------------------------------ 11 PDF mit Zukaufartikeln
import pypdfium2  # noqa: E402


def pdf_text(pfad):
    dok = pypdfium2.PdfDocument(str(pfad))
    return "\n".join(dok[i].get_textpage().get_text_range() for i in range(len(dok)))


kopf, pos, einst, (z, s) = rechnung(a)
pdf.kalkulation_pdf(tmp / "kalk.pdf", kopf, z, s, einst, positionen=pos)
t = pdf_text(tmp / "kalk.pdf")
assert "Schraube M8" in t and "Würth" in t, "intern nachvollziehbar"
ang = ausgabe.angebot(kopf, pos, z, k, einst)
pdf.angebot_pdf(tmp / "angebot.pdf", kopf, ang, db.einstellungen())
t = pdf_text(tmp / "angebot.pdf")
for intern in ("Würth", "Muster GmbH", "INTERN", "Schraube M8", "Einstand", "Aufschlag", "kopiert"):
    assert intern not in t, f"interne Angabe im Kundenangebot: {intern}: …{t[max(0, t.find(intern) - 80):t.find(intern) + 40]}…"
assert "Rohr A" in t
ok("11 PDF: Kalkulation mit Zukaufartikeln; Kundenangebot ohne EK, Lieferant, Aufschlag und interne Bemerkung")

# ------------------------------------------------------------------ 12 Gesamtkalkulation und Margen
# Pos. 10: 10 Teile; Schraube 4 × 0,15, Nietmutter 2 × 0,25, Mutter 4 × 0,08, Griff 1 × 8,50 = 9,92 € je Teil;
# Pos. 20: 20 Teile mit der Kopie 2 × 0,55 €
nah(s["zukauf_einstand"], 9.92 * 10 + 2 * 0.55 * 20, "Einstand Pos. 10 (10 Teile) + Kopie in Pos. 20 (20 Teile)")
nah(s["zukauf_aufschlag"], s["zukauf_einstand"] * 0.10, "Aufschlag 10 % (Standard), kein Gewinn auf Zukauf")
nah(z[0]["zukauf_teil"], 9.92 * 1.10, "Zukauf je Teil im Stückpreis")
assert s["verkauf"] > vk_ohne + s["zukauf_einstand"]
d = dialog(a, s_=seite)
summe = d.summe.text()
assert "EK 99,20 €" in summe and "VK netto 109,12 €" in summe and "MwSt. 19 % 20,73 €" in summe, summe
assert "VK brutto 129,85 €" in summe and "Aufschlag 9,92 €" in summe, summe
nah(float(d.tabelle.item(0, 6).text().replace(",", ".")), 6.0, "EK gesamt Schraube: 4 × 0,15 × 10")
d.reject()
ok("12 Gesamtkalkulation: Einstand, Aufschlag 10 %, Stückpreis; Summe im Dialog mit EK, VK netto, MwSt., brutto")

# ------------------------------------------------------------------ ohne Stamm: Blech-Editor, EK, STEP-Import
bd = db.blech_daten()
e_bl = dict(werkstoff="S235JR", dicke=3, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=400, breite=300,
            eckradius=0, stueck=25, konturen=[])
erg_bl = blech.rechnen(e_bl, bd["werkstoffe"], bd["laser"], bd["einst"])
assert seite._blech_anlegen(e_bl, erg_bl, dict(bezeichnung="Blech 400 x 300 x 3", artikelnr="BL-55",
                                                lieferant="Blech Ost", stueck=25))
assert len(db.zukauf_artikel_liste()) == n_artikel, "Blech-Editor: kein Stammartikel"
zeile = next(i for i, p in enumerate(seite.positionen) if p.get("artikel") == "BL-55")
p = seite.positionen[zeile]
e = zukauf.eintraege(p)[0]
assert zukauf.ist_frei(e) and e["stand"][zukauf.MERKMALE]["artikeltyp"] == zukauf.BLECH and zukauf.ist_blech(e)
st = blech_preis.stand(p)
assert st and st["artikel_id"] is None and not st["angebot"] and abs(st["ek"] - erg_bl["richtpreis"]) < 1e-6, st
assert seite.blech_preis_setzen(zeile, 3.21, "Blech Ost")
p = seite.positionen[zeile]
st = blech_preis.stand(p)
assert st["angebot"] and abs(st["ek"] - 3.21) < 1e-9, "Angebotspreis des Lieferanten nur in der Position"
assert seite.blech_preis_setzen(zeile, None)
assert not blech_preis.stand(seite.positionen[zeile])["angebot"], "zurück auf den Richtpreis"
zeilen = materialanfragen.zukauf_bedarf([seite.positionen[zeile]], None)
assert zeilen[0]["masse"].startswith("400") and zeilen[0]["artikeltyp"] == zukauf.BLECH, zeilen
# EK eintragen bei einem alten Stammartikel: ohne zentrale Verwaltung nur in der Position
s_alt = f.angebot_oeffnen(alt)
assert s_alt.zukauf_ek([0], preise=[0.77, 5.5]) == 2
e0 = json.loads(db.positionen(alt)[0]["zukauf"])[0]
assert e0.get(zukauf.GEAENDERT) and zukauf.ek_einheit(e0["stand"]) is not None
assert zukauf.json_liste(db.zukauf_artikel(alt_id)["bezuege"][0]["preise"]) == [dict(ab=1, preis=0.5)], \
    "Stammartikel unverändert"
ok("Ohne Stamm: Blech-Editor legt nur im Angebot an (Merkmale, Blech-Aufschlag, EK Blech/Angebotspreis), "
   "Materialanfrage mit Maßen, EK eintragen nur in der Position")

step_bleche = HIER / "step_bleche" / "B02_Blech_400x200x4_Bohrungen.step"
s_step = f.angebot_oeffnen(db.angebot_neu(dict(kunde="STEP")))
erg = s_step.step_importieren([str(step_bleche)], stueck=3)
assert erg and len(erg["positionen"]) == 1, erg and erg["bericht"]
p = db.positionen(s_step.id)[0]
e = zukauf.eintraege(p)[0]
assert p["art"] == "Zukaufteil" and zukauf.ist_frei(e) and e["stand"][zukauf.MERKMALE]["artikeltyp"] == zukauf.BLECH
assert e["stand"][zukauf.MERKMALE]["werkstoff"] == "S235JR" and zukauf.ek_einheit(e["stand"]) is not None
assert len(db.zukauf_artikel_liste()) == n_artikel, "STEP-Import: kein Stammartikel"
assert any("im Angebot" in t for t in erg["bericht"]), erg["bericht"]
ok("Ohne Stamm: STEP-Import legt Bleche nur im Angebot an (Richtpreis als EK, Werkstoff, Merkmale)")

app.processEvents()
f.close()
db.con.close()
print("OK: Zukaufartikelverwaltung optional")
