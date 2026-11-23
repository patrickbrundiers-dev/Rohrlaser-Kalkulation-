"""Kundenverwaltung, Oberfläche (Patrick 23.11.2026): Menü KUNDEN, Übersicht (Tabelle/Karten, Live-Suche, Filter,
Export), Eingabemaske mit Dublettenwarnung, Kundenprofil mit acht Reitern (Kennzahlen aus echten Angeboten,
Ansprechpartner, Adressen, Historie, Notizen), Archiv, Duplizieren und neues Angebot aus dem Profil.

Aufruf: python tests/test_kundenverwaltung_ui.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import kunden_daten as kd  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.kunden_seite import PROFIL_REITER, KundenBereich, KundenFormular  # noqa: E402

app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


db = Datenbank(TMP / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(TMP / "ablage"))
f = Hauptfenster(db, stumm=True)
k = f.kunden
assert isinstance(k, KundenBereich) and f.reiter.indexOf(k) >= 0
# Menü KUNDEN mit allen Unterbereichen
menue = [m for m in f.menuBar().actions() if m.text() == "&Kunden"]
assert menue, [m.text() for m in f.menuBar().actions()]
texte = [a.text() for a in menue[0].menu().actions() if a.text()]
for t in ("Kundenübersicht", "Neuen Kunden anlegen …", "Kunden bearbeiten", "Ansprechpartner", "Kundenhistorie",
          "Angebote des Kunden", "Aufträge des Kunden", "Dokumente und Anhänge", "Archivierte Kunden"):
    assert t in texte, (t, texte)
f.kunden_aktionen["uebersicht"].trigger()
assert f.reiter.currentWidget() is k and k.stapel.currentWidget() is k.uebersicht
ok("Menü KUNDEN mit neun Unterbereichen, Kundenübersicht öffnet den Reiter")

# ------------------------------------------------------------------ Neuer Kunde über die Eingabemaske
nr = k.neuer_kunde(stumm=True, werte=dict(
    name="Rheinblick Stahlbau GmbH", strasse="Hafenstraße 4", plz="47119", ort="Duisburg", telefon="0203 55 66 0",
    email="info@rheinblick-stahl.de", kundengruppe="Stahlbau", ust_id="DE811223344", zahlungsziel="30",
    rabatt="3", ansprechpartner=[dict(vorname="Jana", nachname="Sommer", email="j.sommer@rheinblick-stahl.de",
                                      telefon="0203 55 66 12", haupt="ja")]))
assert nr, f.letzte_meldung
kunde = kd.kunde(db, nr)
assert kunde["ort"] == "Duisburg" and kunde["plz_ort"] == "47119 Duisburg" and kunde["status"] == kd.AKTIV
assert kd.vorgaben(db, nr)["rabatt"] == 3
assert [p["nachname"] for p in kd.ansprechpartner(db, nr)] == ["Sommer"] and kunde["ansprechpartner"] == "Jana Sommer"
assert k.stapel.currentWidget() is k.profil and k.profil.kundennr == nr
assert [k.profil.reiter.tabText(i) for i in range(k.profil.reiter.count())] == list(PROFIL_REITER)
ok("Eingabemaske: Kunde mit automatischer Nummer, Ansprechpartner und Rabatt angelegt, Profil mit 8 Reitern offen")

# Dublette: Warnung in der Maske, ohne Freigabe kein zweiter Kunde
d = KundenFormular(k, db, neu=True, vorschlag=dict(name="Rheinblick Stahlbau Gesellschaft mbH", plz="47119"))
assert d.dubletten and d.dubletten[0][0]["kundennr"] == nr and d.dub.isVisibleTo(d)
assert "Rheinblick" in d.dub.text()
vorher = len(db.zeilen("kunden"))
assert k.neuer_kunde(stumm=True, werte=dict(name="Rheinblick Stahlbau GmbH & Co. KG", plz="47119")) is None
assert len(db.zeilen("kunden")) == vorher and "Dublette" in f.letzte_meldung
nr2 = k.neuer_kunde(stumm=True, werte=dict(name="Rheinblick Stahlbau GmbH & Co. KG", plz="47119"), dubletten_ok=True)
assert nr2 and nr2 != nr
ok("Dublettenprüfung: Warnung beim Tippen, ohne Bestätigung kein Anlegen, mit „Trotzdem“ neue Nummer")

# ------------------------------------------------------------------ Bearbeiten (mit Historie)
k.oeffnen(nr)
g = k.kunde_bearbeiten(nr, stumm=True, werte=dict(ort="Duisburg-Ruhrort", status=kd.GESPERRT), vorgaben=dict(rabatt="5"))
assert g and kd.kunde(db, nr)["ort"] == "Duisburg-Ruhrort" and kd.vorgaben(db, nr)["rabatt"] == 5
hist = kd.historie(db, nr, mit_vorgaengen=False)
assert any(e.get("feld") == "Ort" and e.get("neu") == "Duisburg-Ruhrort" for e in hist), hist
assert "Gesperrt" in k.profil.status.text()
ok("Bearbeiten: Ort, Status und Rabatt gespeichert, Historie mit Alt/Neu, Profil zeigt Gesperrt")
k.kunde_bearbeiten(nr, stumm=True, werte=dict(status=kd.AKTIV))

# ------------------------------------------------------------------ Profil: Ansprechpartner, Adressen, Kontakt, Notizen
P = k.profil
pid = P.person_neu(dict(vorname="Tom", nachname="Becker", position="Einkauf", einkauf="ja",
                        email="t.becker@rheinblick-stahl.de"), stumm=True)
assert pid and P.pers_tabelle.rowCount() == 2
P.pers_tabelle.selectRow([P.pers_tabelle.item(r, 0).text() for r in range(2)].index("Tom Becker"))
P.person_bearbeiten(dict(telefon="0203 55 66 30"), stumm=True)
assert next(p for p in kd.ansprechpartner(db, nr) if p["nachname"] == "Becker")["telefon"] == "0203 55 66 30"
assert P.person_mail() == "mailto:t.becker@rheinblick-stahl.de"
assert P.mail() == "mailto:j.sommer@rheinblick-stahl.de"
aid = P.adresse_neu(dict(art=kd.LIEFERUNG, bezeichnung="Werk 2", strasse="Ruhrdeich 9", plz="47138", ort="Duisburg",
                         land="DE", standard="ja"), stumm=True)
assert aid and kd.kunde(db, nr)["liefer_plz"] == "47138"
assert P.adr_tabelle.rowCount() == 1
assert P.kontakt_neu("Telefonat", "Rückfrage Liefertermin KW 50")
assert any("Liefertermin" in (e.get("text") or "") for e in kd.historie(db, nr))
P.notizen.setPlainText("Zahlt immer pünktlich.")
assert P.notizen_speichern() and kd.kunde(db, nr)["notizen"] == "Zahlt immer pünktlich."
datei = TMP / "Rahmenvertrag.pdf"
datei.write_bytes(b"%PDF-1.4 test")
assert P.dokument_neu(str(datei)) and P.dok_tabelle.rowCount() == 1
ok("Profil: Ansprechpartner neu/ändern, E-Mail, Lieferadresse (Frachtzone), Kontakt in Historie, Notizen, Dokument")

# ------------------------------------------------------------------ Kennzahlen aus echten Angeboten
ang = beispiel_angebot.anlegen(db)
db.kunde_uebernehmen(ang, nr)
db.vorgang_setzen(ang, "Beauftragt")
P.zeigen(nr)
z = kd.kennzahlen(db, nr)
assert z["angebote"] >= 1 and z["beauftragt"] == 1 and z["quote"] == 1.0
assert P.kacheln.kacheln["angebote"].wert.text() == str(z["angebote"]) and P.ang_tabelle.rowCount() == z["angebote"]
assert P.kacheln.kacheln["quote"].wert.text() == "100 %"
a = db.angebot(ang)
assert a["kunde_ansprech"] == "Jana Sommer" and a["lieferadresse"] and "Ruhrdeich 9" in a["lieferadresse"]
ok("Kennzahlen aus den Angeboten (Anzahl, beauftragt, Quote), Angebot mit Ansprechpartner und Lieferadresse")

# Neues Angebot aus dem Profil
n_vorher = len(db.zeilen("angebote"))
neu_ang = k.neues_angebot(nr)
assert neu_ang and len(db.zeilen("angebote")) == n_vorher + 1
assert db.angebot(neu_ang)["kundennr"] == nr and db.angebot(neu_ang)["kunde_ansprech"] == "Jana Sommer"
ok("Neues Angebot aus dem Kundenprofil mit Kunde, Ansprechpartner und Lieferadresse")

# ------------------------------------------------------------------ Angebotskopf: Kunde suchen, Ansprechpartner, Lieferadresse
seite = f.angebot_oeffnen(neu_ang)
O = seite.kopf_bereich
assert O.kunde_suchen_knopf is not None and O.kunde_suchen_knopf.toolTip().startswith("Kunde suchen")
texte = [O.ansprech_wahl.itemText(i) for i in range(O.ansprech_wahl.count())]
assert any("Jana Sommer" in t for t in texte) and any("Tom Becker" in t for t in texte), texte
assert O.ansprech_wahl.currentData() == db.angebot(neu_ang)["kunde_ansprech_uid"]
becker = next(p for p in kd.ansprechpartner(db, nr) if p["nachname"] == "Becker")
seite.ansprech_waehlen(becker["uid"])
assert db.angebot(neu_ang)["kunde_ansprech"] == "Tom Becker" and O.ansprech_wahl.currentData() == becker["uid"]
assert any("Werk 2" in O.liefer_wahl.itemText(i) for i in range(O.liefer_wahl.count()))
seite.liefer_waehlen(None)
assert not db.angebot(neu_ang)["lieferadresse"] and O.liefer_wahl.currentIndex() == 0
werk2 = kd.adressen(db, nr, kd.LIEFERUNG)[0]["uid"]
seite.liefer_waehlen(werk2)
assert "Ruhrdeich 9" in db.angebot(neu_ang)["lieferadresse"]
# Kunde über die Suche wechseln: Ansprechpartner/Lieferadresse des neuen Kunden (nr2 hat keine) -> leer
assert seite.kunde_suchen(nr2) == nr2
a2 = db.angebot(neu_ang)
assert a2["kundennr"] == nr2 and not a2["kunde_ansprech"] and not a2["lieferadresse"]
assert not O.ansprech_wahl.isEnabled()
seite.kunde_suchen(nr)
assert db.angebot(neu_ang)["kunde_ansprech"] == "Jana Sommer"
# Archivierte Kunden stehen nicht in der Kundenauswahl des Angebots
kd.archivieren(db, nr2, True)
seite.neu_laden()
cb = O.felder["kundennr"]
assert cb.findData(nr2) < 0 and cb.findData(nr) >= 0
kd.archivieren(db, nr2, False)
ok("Angebotskopf: Kundensuche-Knopf, Ansprechpartner und Lieferadresse wählbar, Kundenwechsel setzt beide neu, "
   "archivierte Kunden ausgeblendet")

# PDF: Anschrift mit „z. Hd.“ des gewählten Ansprechpartners und Lieferanschrift; Auftrag übernimmt beides
from rohrlaser import auftraege  # noqa: E402
seite.liefer_waehlen(werk2)
seite.ansprech_waehlen(becker["uid"])
ang_daten = seite.angebot_daten(staffeln=False)
assert "z. Hd. Tom Becker" in ang_daten["anschrift"], ang_daten["anschrift"]
assert any("Ruhrdeich 9" in z for z in ang_daten["lieferadresse"]), ang_daten["lieferadresse"]
db.vorgang_setzen(neu_ang, "Beauftragt")
auf = auftraege.auftrag(db, auftraege.uebernehmen(db, [neu_ang]))
kopf = auf.get("kopf") or auf
assert kopf.get("ansprechpartner") == "Tom Becker", auf
assert "Ruhrdeich 9" in (kopf.get("lieferadresse") or ""), auf
ok("Angebot -> PDF-Daten und Auftrag mit Ansprechpartner und Lieferadresse")
seite.close()

# ------------------------------------------------------------------ Übersicht: Suche, Filter, Karten, Export
f.kunden_aktionen["uebersicht"].trigger()
U = k.uebersicht
U.suche.setText("rheinblick")
assert U.filter.rowCount() == 2, U.filter.rowCount()
U.suche.setText("sommer duisburg")
assert U.filter.rowCount() == 1
U.suche.setText("")
U.gruppe.setCurrentText("Stahlbau")
assert U.filter.rowCount() == 1
U.gruppe.setCurrentText("Alle Gruppen")
U.status.setCurrentText(kd.GESPERRT)
assert U.filter.rowCount() == 0
U.status.setCurrentText("Alle Status")
U.als_karten.setChecked(True)
assert U.stapel.currentWidget() is U.karten and db.einstellung("kunden_ansicht") == "Karten"
U.als_karten.setChecked(False)
assert U.waehlen(nr) and U.gewaehlt() == nr
csv = U.exportieren("csv", str(TMP / "kunden.csv"))
assert csv and "Rheinblick" in Path(csv).read_text(encoding="utf-8-sig")
xl = U.exportieren("xlsx", str(TMP / "kunden.xlsx"))
assert xl and Path(xl).stat().st_size > 1000
ok("Übersicht: Live-Suche mehrere Wörter, Filter Gruppe/Status, Kartenansicht gemerkt, Export CSV und Excel")

# Kunde aus dem Angebot / der Befehlspalette: kunde_zeigen öffnet bei Kundennummer das Profil
assert f.kunde_zeigen(nr) >= 1 and k.stapel.currentWidget() is k.profil and k.profil.kundennr == nr
ok("kunde_zeigen: Kundennummer öffnet das Kundenprofil")

# ------------------------------------------------------------------ Duplizieren, Archivieren
f.kunden_aktionen["uebersicht"].trigger()
assert U.suche.text() == nr
U.suche.setText("")
nr3 = k.kunde_duplizieren(nr)
assert nr3 and kd.kunde(db, nr3)["name"].endswith("(Kopie)") and not kd.kunde(db, nr3).get("ust_id")
assert k.kunde_archivieren(nr3, bestaetigt=True)
k.zeigen("uebersicht")
assert not U.waehlen(nr3)
k.zeigen("archiv")
assert k.archiv.waehlen(nr3)
assert k.kunde_archivieren(nr3, an=False)
k.zeigen("uebersicht")
assert U.waehlen(nr3)
ok("Duplizieren (neue Nummer, ohne USt-ID), Archivieren und Zurückholen")

# Unterbereiche über das Menü mit gewähltem Kunden
U.waehlen(nr)
f.kunden_aktionen["historie"].trigger()
assert k.stapel.currentWidget() is k.profil and k.profil.reiter.currentIndex() == PROFIL_REITER.index("Historie")
assert P.hist_tabelle.rowCount() >= 3
k.zeigen("uebersicht")
U.waehlen(nr)
f.kunden_aktionen["personen"].trigger()
assert k.profil.reiter.currentIndex() == PROFIL_REITER.index("Ansprechpartner")
f.kunden_aktionen["tabelle"].trigger()
assert k.stapel.currentWidget() is k.tabelle and k.tabelle.filter.rowCount() >= 3
ok("Menü: Historie/Ansprechpartner öffnen das Profil am passenden Reiter, Tabellenansicht mit allen Kunden")

# Lesemodus: Knöpfe gesperrt, Speichern scheitert mit verständlicher Meldung statt stillem Verlust
db.nur_lesen = True
assert k.kunde_bearbeiten(nr, stumm=True, werte=dict(ort="X")) is None and kd.kunde(db, nr)["ort"] != "X"
db.nur_lesen = False
ok("Lesemodus: keine Änderung, Meldung")
f.close()
print("OK: Kundenverwaltung (Oberfläche)")
