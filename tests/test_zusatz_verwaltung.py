"""Prüft die Verwaltung der Zusatzarbeiten (Einstellungen → Zusatzarbeiten) und den Preisstand je Position.

Testplan 1–12: Anlegen, Bearbeiten, Abbrechen, Duplizieren, Aktivieren/Deaktivieren, Löschen (unbenutzt und
benutzt), Rechnung (Zeit, Stundensatz, Material, Zuschläge, €/Angebot), ungültige Eingaben, Darstellung bei
1920 und 1024 Pixel Breite, Datei der Vorversion (Schema 14) und unveränderte Staffelpreise.

Aufruf: python tests/test_zusatz_verwaltung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import TABELLE  # noqa: E402
from rohrlaser.zusatz_dialog import ZusatzDialog  # noqa: E402
from rohrlaser.zusatz_verwaltung import SPALTEN, kopie_name, rechenzeilen  # noqa: E402

tmp = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
NEU = [f.name for f in TABELLE["zusatzarbeiten"].felder][7:]       # Felder ab Schema 15


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-9):
    return abs(a - b) < eps


def antwort(seite, text):
    """Rückfragen ohne Bildschirm beantworten; die Fragen werden mitgeschrieben."""
    seite.fragen = []

    def frage(titel, inhalt, knoepfe, standard):
        seite.fragen.append((titel, inhalt, knoepfe, standard))
        return text
    seite._frage = frage


def nach_name(db, name):
    return next((z for z in db.zeilen("zusatzarbeiten") if z["name"] == name), None)


def ausfuellen(fo, **werte):
    for n, w in werte.items():
        widget = getattr(fo, n)
        if hasattr(widget, "setChecked"):
            widget.setChecked(w)
        elif n == "art":
            widget.setCurrentIndex(widget.findData(w))
        elif hasattr(widget, "setCurrentText"):
            widget.setCurrentText(w)
        else:
            widget.setText(w)
    fo._geaendert()


db = Datenbank(tmp / "a" / "rohrlaser.db")
f = Hauptfenster(db, tmp / "a", stumm=True)
f.resize(1920, 1080)
f.show()
assert f.bereich.oeffnen(db.einstellung("passwort"))
f.zeigen(f.zusatz)
app.processEvents()
s = f.zusatz
assert f.bereich.unter.currentWidget() is s and s.titel == "Zusatzarbeiten"
f.zeigen(next(x for x in f.seiten if x.t.name == "zusatzarbeiten"))     # alter Weg (Anleitung) zeigt die neue Seite
assert f.bereich.unter.currentWidget() is s
n0 = len(db.zeilen("zusatzarbeiten"))
assert len(s.sichtbar) == n0 == 12

# 1) Neue Zusatzarbeit anlegen
fo = s.neu()
assert fo is s.formular and s.rechts.isVisible() and fo.zeilen_id is None and fo.name.text() == ""
assert fo.art.currentData() == "€/Stück" and fo.zeit_einheit.currentText() == "min" and fo.aktiv.isChecked()
ausfuellen(fo, name="Entgraten von Hand", kategorie="Nachbearbeitung", beschreibung="Kanten brechen", zeit="5",
           satz="60", material="2", zuschlag_material="10")
assert len(db.zeilen("zusatzarbeiten")) == n0                       # erst mit Speichern
assert fo.speichern()
z = nach_name(db, "Entgraten von Hand")
assert z and z["kategorie"] == "Nachbearbeitung" and z["bemerkung"] == "Kanten brechen" and z["art"] == "€/Stück"
assert z["zeit"] == 5 and z["zeit_einheit"] == "min" and z["satz"] == 60 and z["satz_id"] is None
assert z["material"] == 2 and z["zuschlag_material"] == 10 and z["zuschlag_material_art"] == "%" and z["aktiv"] == "ja"
assert not s.rechts.isVisible() and s.gewaehlt() == z["id"] and len(s.sichtbar) == n0 + 1
ok("1  neue Zusatzarbeit angelegt, erst beim Speichern in der Datenbank, danach in der Übersicht markiert")

# 2) Bestehende Zusatzarbeit bearbeiten: alle Werte geladen, Vorschau sofort, Speichern übernimmt
fo = s.bearbeiten(z["id"])
assert fo.zeilen_id == z["id"] and fo.name.text() == "Entgraten von Hand" and fo.zeit.text() == "5"
assert fo.satz.text() == "60,00" and fo.material.text() == "2,00" and fo.zuschlag_material.text() == "10"
assert fo.kategorie.currentText() == "Nachbearbeitung" and fo.beschreibung.text() == "Kanten brechen"
assert ("Selbstkosten je Stk", "7,20 €", True) in fo.ergebnis_zeilen
ausfuellen(fo, zeit="6")
assert ("Selbstkosten je Stk", "8,20 €", True) in fo.ergebnis_zeilen     # Vorschau während der Eingabe
assert nach_name(db, "Entgraten von Hand")["zeit"] == 5                  # noch nicht gespeichert
assert fo.speichern() and nach_name(db, "Entgraten von Hand")["zeit"] == 6
ok("2  bearbeiten: Werte vollständig geladen, Vorschau 7,20 € -> 8,20 € beim Tippen, gespeichert erst mit Speichern")

# 3) Änderungen abbrechen
vorher = nach_name(db, "Entgraten von Hand")
fo = s.bearbeiten(vorher["id"])
ausfuellen(fo, name="Anders", zeit="99")
fo.abbrechen()
assert nach_name(db, "Entgraten von Hand") == vorher and not s.formular_offen()
fo = s.bearbeiten(vorher["id"])
assert fo.name.text() == "Entgraten von Hand" and fo.zeit.text() == "6"
# Wechsel auf einen anderen Eintrag mit ungespeicherten Änderungen fragt nach
ausfuellen(fo, zeit="7")
antwort(s, "Abbrechen")
assert s.bearbeiten(nach_name(db, "Entgraten")["id"]) is None and s.fragen and fo.zeit.text() == "7"
antwort(s, "Verwerfen")
assert s.bearbeiten(nach_name(db, "Entgraten")["id"]).name.text() == "Entgraten"
s.formular.abbrechen()
assert nach_name(db, "Entgraten von Hand")["zeit"] == 6
ok("3  abbrechen: Datenbank unverändert; ungespeicherte Änderungen nur nach Rückfrage verworfen")

# 4) Duplizieren: alle Einstellungen, Name '(Kopie)', angelegt erst beim Speichern
original = nach_name(db, "Entgraten von Hand")
fo = s.duplizieren(original["id"])
assert fo.zeilen_id is None and fo.name.text() == "Entgraten von Hand (Kopie)" and fo.zeit.text() == "6"
assert len(db.zeilen("zusatzarbeiten")) == n0 + 1
assert fo.speichern()
kopie = nach_name(db, "Entgraten von Hand (Kopie)")
assert kopie["id"] != original["id"]
assert all(kopie[x.name] == original[x.name] for x in TABELLE["zusatzarbeiten"].felder if x.name != "name")
assert s.duplizieren(original["id"]).name.text() == "Entgraten von Hand (Kopie 2)"
s.formular.abbrechen()
assert kopie_name("A", ["a (kopie)"]) == "A (Kopie 2)" and len(db.zeilen("zusatzarbeiten")) == n0 + 2
ok("4  duplizieren: alle Felder übernommen, Name '(Kopie)' bzw. '(Kopie 2)', angelegt erst beim Speichern")

# 5) Deaktivieren und wieder aktivieren
s.aktiv_umschalten(kopie["id"])
assert nach_name(db, kopie["name"])["aktiv"] == "nein" and s.k_aktiv.text() == "Aktivieren"
s.status_filter.setCurrentText("Aktive")
assert kopie["id"] not in [x["id"] for x in s.sichtbar]
s.status_filter.setCurrentText("Inaktive")
assert [x["id"] for x in s.sichtbar] == [kopie["id"]]
s.status_filter.setCurrentText("Alle")
a = db.angebot_neu(dict(kunde="Test", skonto=0, maschine="T11"))
db.position_neu(a, dict(pos=1, artikel="T1", profil_id=db.zeilen("profile")[0]["profil_id"],
                        werkstoff_id=db.zeilen("werkstoffe")[0]["werkstoff_id"], laenge=500, stueck=10))
seite = f.angebot_oeffnen(a)
d = ZusatzDialog(seite, seite.positionen[0], 1, seite.k, seite.tabellen, {"Entgraten": 3})
r = d.zeile_neu()
eintraege = [d.tabelle.cellWidget(r, 0).itemText(i) for i in range(d.tabelle.cellWidget(r, 0).count())]
assert kopie["name"] not in eintraege and "Entgraten von Hand" in eintraege
assert "— Häufig verwendet —" in eintraege and eintraege.index("Entgraten") < eintraege.index("Feuerverzinken")
assert d.tabelle.cellWidget(r, 0).currentText() == eintraege[1]          # Überschrift nicht gewählt
d.tabelle.cellWidget(r, 0).setCurrentText("Entgraten von Hand")
assert seite.zusatzarbeiten([0], d.werte())
p = seite.positionen[0]
e = json.loads(p["zusatz"])[0]
assert e["stand"]["art"] == "€/Stück" and nah(e["stand"]["preis"], 8.2)
preis_vorher = seite._rechnung()[0][0]["zusatz_teil"]
assert nah(preis_vorher, 8.2)
s.aktiv_umschalten(original["id"])                                    # deaktiviert: Angebot rechnet weiter
seite.neu_laden()
assert nah(seite._rechnung()[0][0]["zusatz_teil"], preis_vorher) and "unbekannt" not in seite.pos_modell.status[0]
d = ZusatzDialog(seite, seite.positionen[0], 1, seite.k, seite.tabellen)
assert d.tabelle.cellWidget(0, 0).currentText() == "Entgraten von Hand"   # bleibt in der Position wählbar
s.aktiv_umschalten(original["id"])
s.aktiv_umschalten(kopie["id"])
assert nach_name(db, original["name"])["aktiv"] == "ja" == nach_name(db, kopie["name"])["aktiv"]
ok("5  deaktivieren/aktivieren: Filter Status, inaktive nicht im Angebotsdialog wählbar, Angebot rechnet weiter")

# 6) Löschen einer nicht verwendeten Zusatzarbeit (mit Sicherheitsabfrage)
antwort(s, "Abbrechen")
assert s.loeschen(kopie["id"]) is None and nach_name(db, kopie["name"])
assert s.fragen[0][2] == ("Löschen", "Abbrechen") and s.fragen[0][3] == "Abbrechen"
antwort(s, "Löschen")
assert s.loeschen(kopie["id"]) == "gelöscht" and nach_name(db, kopie["name"]) is None
ok("6  unbenutzte Zusatzarbeit: Sicherheitsabfrage (Vorgabe Abbrechen), danach gelöscht")

# 7) Verwendete Zusatzarbeit: Deaktivieren empfohlen; Preisstand schützt alte Angebote
db.position_neu(a, dict(pos=2, artikel="T2", profil_id=p["profil_id"], werkstoff_id=p["werkstoff_id"], laenge=800,
                        stueck=4, zusatz=json.dumps([dict(name="Entgraten von Hand")])))      # ältere Position ohne Stand
seite.neu_laden()
v = db.zusatz_verwendung("Entgraten von Hand")
assert v == dict(angebote=[seite.kopf["nummer"]], positionen=2, ohne_stand=1)
antwort(s, "Deaktivieren")
assert s.loeschen(original["id"]) == "deaktiviert" and nach_name(db, original["name"])["aktiv"] == "nein"
titel, text, knoepfe, standard = s.fragen[0]
assert knoepfe == ("Deaktivieren", "Trotzdem löschen", "Abbrechen") and standard == "Deaktivieren"
assert seite.kopf["nummer"] in text and "1 ältere Position" in text
# Stammdaten ändern: Position mit Preisstand bleibt, Position ohne Stand folgt den Stammdaten
fo = s.bearbeiten(original["id"])
ausfuellen(fo, satz="90", aktiv=True)
assert fo.speichern()
seite.neu_laden()
zeilen = seite._rechnung()[0]
assert nah(zeilen[0]["zusatz_teil"], 8.2) and nah(zeilen[1]["zusatz_teil"], 6 / 60 * 90 + 2.2)
# Umbenennen ändert den Namen in den Positionen mit, Preise bleiben
fo = s.bearbeiten(original["id"])
ausfuellen(fo, name="Entgraten Hand")
assert fo.speichern()
seite.neu_laden()
assert [json.loads(x["zusatz"])[0]["name"] for x in seite.positionen] == ["Entgraten Hand"] * 2
assert nah(seite._rechnung()[0][0]["zusatz_teil"], 8.2) and not any("unbekannt" in t for t in seite.pos_modell.status)
# 'Preise aus Stammdaten übernehmen' holt bewusst den neuen Stand
d = ZusatzDialog(seite, seite.positionen[0], 1, seite.k, seite.tabellen)
assert "Preisstand" in d.tabelle.cellWidget(0, 3).placeholderText()
d.stand_verwerfen()
assert "Stammdaten" in d.tabelle.cellWidget(0, 3).placeholderText()
assert seite.zusatzarbeiten([0], d.werte())
assert nah(seite._rechnung()[0][0]["zusatz_teil"], 11.2)
# Trotzdem löschen: Positionen mit Stand rechnen weiter, ohne Stand wie bisher 'unbekannt'
antwort(s, "Trotzdem löschen")
assert s.loeschen(original["id"]) == "gelöscht" and nach_name(db, "Entgraten Hand") is None
seite.neu_laden()
zeilen = seite._rechnung()[0]
assert nah(zeilen[0]["zusatz_teil"], 11.2) and nah(zeilen[1]["zusatz_teil"], 0)
assert "unbekannt" not in seite.pos_modell.status[0] and "unbekannt" in seite.pos_modell.status[1]
ok("7  verwendete Zusatzarbeit: Abfrage nennt Angebote, Deaktivieren empfohlen; Preisstand schützt alte Angebote, "
   "Umbenennen folgt, 'Preise aus Stammdaten übernehmen' aktualisiert bewusst")

# 8) Rechnung: Zeit, Stundensatz, Material, Zuschläge (Beispiel aus dem Auftrag: 7,20 €)
saetze = rechnen.stundensaetze(db.tabellen())
pr = rechnen.zusatz_preis(dict(art="€/Stück", zeit=5, zeit_einheit="min", satz=60, material=2, zuschlag_material=10))
assert nah(pr["arbeit"], 5) and nah(pr["material_inkl"], 2.2) and nah(pr["preis"], 7.2)
for zeit, einheit in ((300, "s"), (5, "min"), (5 / 60, "h")):
    assert nah(rechnen.zusatz_preis(dict(art="€/Stück", zeit=zeit, zeit_einheit=einheit, satz=60))["arbeit"], 5)
pr = rechnen.zusatz_preis(dict(art="€/m²", preis=3, material=2, zuschlag_material=0.5, zuschlag_material_art="€"))
assert nah(pr["material_inkl"], 2.5) and nah(pr["preis"], 5.5)
z = dict(art="€/Stück", zeit=6, zeit_einheit="min", satz_id="Nachbearbeitung", material=10, zuschlag_weitere=10)
assert nah(rechnen.zusatz_preis(z, saetze)["arbeit"], 6 / 60 * saetze["Nachbearbeitung"])
for basis, soll in (("Arbeit", 4.5 * 1.1 + 10), ("Material", 4.5 + 11), ("Arbeit und Material", 14.5 * 1.1)):
    assert nah(rechnen.zusatz_preis(dict(z, zuschlag_weitere_basis=basis), saetze)["preis"], soll)
alt = dict(name="X", art="€/kg", preis=0.65, mindest=120, fremd="ja")     # Eintrag vor Schema 15: nur Festpreis
assert rechnen.zusatz_preis(alt)["preis"] == 0.65
assert rechnen.zusatz_preis(dict(art="s/Stück", preis=20, zeit=5, material=3))["preis"] == 20
# Vorschau = Verkaufspreis mit den Vorgaben, Nullzeilen ausgeblendet
vg = dict(zuschlag_fertigung=0.15, zuschlag_fremdleistung=0.10, gewinn=0.10)
zeilen = rechenzeilen(dict(art="€/Stück", zeit=5, zeit_einheit="min", satz=60, material=2, zuschlag_material=10), {}, vg)
assert [t for t, _, _ in zeilen] == ["Arbeitskosten: 5 min × 60,00 €/h", "Materialkosten", "Materialzuschlag 10 %",
                                     "Material inklusive Zuschlag", "Selbstkosten je Stk",
                                     "Zuschlag Fertigung 15 % (Vorgabe)", "Gewinn 10 % (Vorgabe)",
                                     "Verkaufspreis je Stk (mit Vorgaben)"]
assert zeilen[-1][1] == "9,11 €"                                           # 7,20 × 1,15 × 1,10
# im Angebot: Zuschlag Fertigung bzw. Fremdleistung auf den Preis je Einheit, einmal (nicht doppelt)
db.zusatz_speichern(None, dict(name="Prüfprotokoll", art="€/Angebot", preis=40, aktiv="ja", fremd="nein"))
db.zusatz_speichern(None, dict(name="Montage", art="€/Stück", zeit=2, zeit_einheit="min", satz=60, material=1,
                               zuschlag_material=50, aktiv="ja", fremd="nein"))
for x in seite.positionen:
    db.position_aendern(x["id"], "zusatz", json.dumps([dict(name="Prüfprotokoll"), dict(name="Montage")]))
seite.neu_laden()
zeilen, summen = seite._rechnung()
assert all(nah(zl["zusatz_teil"], 40 / 14 + 3.5) for zl in zeilen)       # 40 € einmal auf 14 Teile, Montage 2 + 1,50
assert nah(summen["zusatz"], 40 + 3.5 * 14)
zf = seite.einst["zuschlag_fertigung"]
assert nah(zeilen[0]["zuschlag_fertigung_teil"] - (zeilen[0]["laser_teil"] + zeilen[0]["ruesten_teil"]
                                                  + zeilen[0]["arbeit_teil"]) * zf, (40 / 14 + 3.5) * zf)
db.zusatz_speichern(nach_name(db, "Prüfprotokoll")["id"], dict(nach_name(db, "Prüfprotokoll"), mindest=60))
seite.neu_laden()
assert nah(seite._rechnung()[1]["zusatz"], 60 + 3.5 * 14)                 # Mindestbetrag gilt auch pauschal
# verschiedene Preisstände derselben Zusatzarbeit im Angebot: ein Mindestbetrag für alle (hier 100 €)
alt_stand = dict(art="€/Stück", preis=1.0, mindest=100.0, fremd="nein", angebotstext=None, datum="2026-01-01")
neu_stand = dict(alt_stand, preis=0.1, mindest=None, datum="2026-10-20")
for x, st in zip(seite.positionen, (alt_stand, neu_stand)):
    db.position_aendern(x["id"], "zusatz", json.dumps([dict(name="Altpreis", stand=st)]))
seite.neu_laden()
zeilen, summen = seite._rechnung()
assert [zl["stueck"] for zl in zeilen] == [10, 4] and nah(summen["zusatz"], 100)    # 10 × 1 + 4 × 0,1 = 10,40 -> 100
ok("8  Rechnung: 5 min × 60 €/h + 2 € + 10 % = 7,20 €; s/min/h, € und %, Basis des weiteren Zuschlags, €/Angebot "
   "einmal umgelegt, Zuschlag Fertigung einmal")

# 9) Leere, ungültige und negative Eingaben
fo = s.neu()
fehler = {}
for werte, teil in ((dict(), "Namen"), (dict(name="Neu"), "Festpreis, einen Zeitaufwand"),
                    (dict(name="Neu", preis="abc"), "keine Zahl"), (dict(name="Neu", preis="-3"), "negative"),
                    (dict(name="Montage", preis="3"), "gibt es schon"), (dict(name="montage", preis="3"), "gibt es schon"),
                    (dict(name="Neu", zeit="5"), "Stundensatz"), (dict(name="Neu", zuschlag_material="1,2,3"), "keine Zahl"),
                    (dict(name="Neu", art="s/Stück"), "Maschinenzeit")):
    fo.laden()
    ausfuellen(fo, **werte)
    try:
        fo.werte()
        raise AssertionError(f"nicht abgewiesen: {werte}")
    except ValueError as x:
        assert teil in str(x), (werte, str(x))
    assert not fo.speichern() and teil in fo.fehler.text()
fo.laden()
ausfuellen(fo, preis="-3")
assert "border" in fo.preis.styleSheet() and "negative" in fo.fehler.text()     # sofort rot markiert
ausfuellen(fo, preis="3")
assert fo.preis.styleSheet() == "" and fo.fehler.text() == ""
s.formular.abbrechen()
assert len(db.zeilen("zusatzarbeiten")) == n0 + 2
ok("9  leere, ungültige, negative und doppelte Eingaben: verständliche Meldung, rotes Feld, nichts gespeichert")

# 10) Darstellung: breit (Formular neben der Tabelle) und schmal 1024 px (Formular als eigenes Fenster)
f.angebot_schliessen(a)
f.zeigen(s)
app.processEvents()
assert s.tabelle.horizontalScrollBar().maximum() == 0 and not s.schmal()
assert not s.spalte_sichtbar("Weitere Zuschläge") and s.spalte_sichtbar("Material")     # Nullwert-Regel
assert s.spalte_sichtbar("Preis je Einheit") and s.spalte_sichtbar("Status")
fo = s.neu()
app.processEvents()
assert fo is s.formular and s.rechts.isVisible() and s.dialog is None
assert s.tabelle.horizontalScrollBar().maximum() == 0
f.resize(1520, 800)          # knapp breit genug (mit Navigation links): Formular daneben, Tabelle schmal
app.processEvents()
assert not s.schmal() and s.rechts.isVisible()
assert s.tabelle.horizontalScrollBar().maximum() == 0, s.tabelle.horizontalScrollBar().maximum()
f.resize(1920, 1080)
app.processEvents()
s.formular.abbrechen()
f.resize(1024, 700)
app.processEvents()
assert s.schmal() and f.minimumSizeHint().width() <= 1024, (s.width(), f.minimumSizeHint())
assert s.tabelle.horizontalScrollBar().maximum() == 0, s.tabelle.horizontalScrollBar().maximum()
fo = s.neu()
app.processEvents()
assert s.dialog is not None and fo is s.dialog.formular and not s.rechts.isVisible()
assert s.dialog.width() <= 1024 and fo.speichern_knopf.isVisible()
ausfuellen(fo, name="Schmal", preis="1")
assert fo.speichern() and s.dialog is None and nach_name(db, "Schmal")
f.resize(1920, 1080)
app.processEvents()
ok("10 Darstellung: 1920 px Formular neben der Tabelle, 1024 px eigenes Fenster, kein waagrechtes Scrollen")

# Suche, Filter, Sortierung
s.suche.setText("verzink")
assert {x["name"] for x in s.sichtbar} == {"Feuerverzinken", "Galvanisch verzinken"}
s.suche.clear()
s.kat_filter.setCurrentText("Oberfläche")
assert {x["kategorie"] for x in s.sichtbar} == {"Oberfläche"} and len(s.sichtbar) == 3
s.kat_filter.setCurrentText("Alle")
s.sortierung.setCurrentText("Preis")
preise = [x["_preis"]["preis"] for x in s.sichtbar if x["art"] != "s/Stück"]
assert preise == sorted(preise, reverse=True)
s.sortierung.setCurrentText("Zeitaufwand")
assert [x["name"] for x in s.sichtbar[:2]] == ["Montage", "Gravur extra"]     # 120 s vor 20 s
s.sortierung.setCurrentText("Name")
assert [x["name"].lower() for x in s.sichtbar] == sorted(x["name"].lower() for x in s.sichtbar)
ok("   Suche, Filter Kategorie/Status und Sortierung nach Name, Preis, Zeitaufwand")
f.close()
db.schliessen()

# 11) Datei der Vorversion (Schema 14): Sicherung, Einträge unverändert, neue Felder leer
alt = tmp / "alt" / "rohrlaser.db"
d = Datenbank(alt)
with d.con:     # Senken, Flowdrill, Bohren gab es in Schema 14 nicht (Ergänzung gilt hier als schon erledigt)
    d.con.execute("DELETE FROM zusatzarbeiten WHERE name IN ('Senken', 'Flowdrill', 'Bohren')")
vorher = [{k: v for k, v in z.items() if k not in NEU} for z in d.zeilen("zusatzarbeiten")]
d.schliessen()
con = sqlite3.connect(alt)
con.execute('DROP INDEX IF EXISTS "zusatzarbeiten_schluessel"')
for n in NEU:
    con.execute(f'ALTER TABLE zusatzarbeiten DROP COLUMN "{n}"')
con.execute("PRAGMA user_version=14")
con.commit()
con.close()
d = Datenbank(alt)
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert len(list((alt.parent / "Sicherung").glob(f"*vor_Schema_{SCHEMA_VERSION}.db"))) == 1
nachher = d.zeilen("zusatzarbeiten")
assert [{k: v for k, v in z.items() if k not in NEU} for z in nachher] == vorher
assert all(z[n] is None for z in nachher for n in NEU)
assert all(rechnen.zusatz_preis(z)["preis"] == z["preis"] for z in nachher if z["art"] != "€/h")   # €/h (Schweißen) gibt es erst ab 0.8.36
f = Hauptfenster(d, tmp / "alt", stumm=True)
assert all(x == "aktiv" for x in [f.zusatz.zellen(z)["status"] for z in f.zusatz.daten])
fo = f.zusatz.bearbeiten(nachher[0]["id"])
assert fo.name.text() == nachher[0]["name"] and fo.preis.text() == "0,65" and fo.mindest.text() == "120,00"
assert fo.mehr.isChecked() and fo.fremd.isChecked()                       # Mindestbetrag/Fremdleistung sichtbar
assert fo.speichern()
z = d.zeilen("zusatzarbeiten")[0]
assert {k: v for k, v in z.items() if k not in NEU} == vorher[0] and z["aktiv"] == "ja"
f.close()
d.schliessen()
ok("11 Schema 14 -> 15: Sicherung, Einträge unverändert, neue Felder leer, Preis wie bisher; Laden/Speichern verlustfrei")

# 12) Staffelpreise unverändert: Beispielangebot mit Zusatzarbeiten ohne und mit Preisstand
db = Datenbank(tmp / "b" / "rohrlaser.db")
a = beispiel_angebot.anlegen(db)
f = Hauptfenster(db, tmp / "b", stumm=True)
seite = f.angebot_oeffnen(a)
alle = list(range(len(seite.positionen)))
ohne = json.dumps([dict(name="Feuerverzinken"), dict(name="Entgraten")])
assert seite.zusatzarbeiten(alle, (None, ohne))
assert seite.optimieren()
preise_ohne = [(x["menge"], x["preis_einheit"]) for x in seite.staffelpreise_aktuell()]
katalog = {z["name"]: z for z in db.zeilen("zusatzarbeiten")}
mit = json.dumps([dict(name=n, stand=rechnen.zusatz_stand(katalog[n])) for n in ("Feuerverzinken", "Entgraten")])
assert seite.zusatzarbeiten(alle, (None, mit))
assert seite.optimieren()
preise_mit = [(x["menge"], x["preis_einheit"]) for x in seite.staffelpreise_aktuell()]
assert preise_ohne == preise_mit and len(preise_mit) >= 2, (preise_ohne, preise_mit)
f.close()
db.schliessen()
ok(f"12 Staffelpreise mit Zusatzarbeiten ohne und mit Preisstand gleich ({len(preise_mit)} Stufen)")

assert [s[0] for s in SPALTEN][:3] == ["Name", "Kategorie", "Abrechnung"]
print("OK: Verwaltung der Zusatzarbeiten")
