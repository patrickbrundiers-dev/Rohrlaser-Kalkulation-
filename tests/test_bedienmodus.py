"""Einfacher Modus neben dem Experten-Pro-Modus (Patrick 25.11.2026, Master-Auftrag „Vereinfachten Bedienmodus
implementieren“).

Abnahme (Abschnitt 10 des Auftrags): Wechsel einfach ↔ Experte ohne Datenverlust, Einstellung je Arbeitsplatz und
Benutzer dauerhaft gespeichert (auch nach Neustart), mehrere Mitarbeiter mit verschiedenen Modi, dieselbe Kalkulation
in beiden Modi (gleiche Seite, gleiche Zahlen), STEP-Import im einfachen Modus, vollständige Berechnung,
Angebots-PDF, Fehlerbehandlung bei unvollständigen Bauteildaten, Expertenmodus unverändert, gemeinsamer Rechenkern
(die Kostengruppen ergeben genau den Verkaufspreis der Kalkulation).

Aufruf: python tests/test_bedienmodus.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import (admin_schutz, bedienmodus as bm, einfach_seite as es, rechnen, stammdaten, teilen,  # noqa: E402
                       werkzeugleiste as wl, werkzeugleiste_qt)
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ ohne Fenster
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert bm.modus(db) == bm.EXPERTE, "Vorgabe: Experten-Pro-Modus (wer nichts wählt, arbeitet wie bisher)"
assert bm.setzen(db, bm.EINFACH, k="") and bm.modus(db, k="") == bm.EINFACH
assert bm.modus(db, k="AB") == bm.EINFACH, "ohne eigene Wahl gilt die Wahl des Arbeitsplatzes"
bm.setzen(db, bm.EXPERTE, k="AB")
bm.setzen(db, bm.EINFACH, k="CD")
assert (bm.modus(db, k="AB"), bm.modus(db, k="CD"), bm.modus(db, k="")) == (bm.EXPERTE, bm.EINFACH, bm.EINFACH)
try:
    bm.setzen(db, "irgendwas")
    raise AssertionError("unbekannter Modus muss abgelehnt werden")
except ValueError:
    pass
assert bm.SPEICHER not in stammdaten.EINSTELLUNG and bm.SPEICHER not in teilen.EINSTELLUNGEN_GETEILT, \
    "der Modus geht nie über den gemeinsamen Ordner (keine gegenseitige Beeinflussung)"
assert bm.SPEICHER.startswith("leiste_"), "persönliches Profil nimmt ihn mit (wie Meine Werkzeugleiste)"
assert "e_bedienmodus" in admin_schutz.NIE, "jeder Mitarbeiter wählt seine Oberfläche selbst (nie gesperrt)"
ok("Modus je Benutzer und Arbeitsplatz, Vorgabe Experte, nicht abgeglichen, nie durch Admin-Schutz gesperrt")

alle = [n for _, _, namen in bm.GRUPPEN for n in namen]
assert len(alle) == len(set(alle)), "jede Kostenart in höchstens einer Gruppe"
fehlt = sorted(set(bm.einzel_kostenarten()) - set(alle))
assert not fehlt, f"Kostenarten ohne Gruppe im einfachen Modus: {fehlt}"
assert set(alle) <= set(bm.einzel_kostenarten()), sorted(set(alle) - set(bm.einzel_kostenarten()))
ok(f"alle {len(alle)} Einzel-Kostenarten der Kalkulation genau einer der {len(bm.GRUPPEN)} Gruppen zugeordnet")

text, aktion = bm.loesung("FEHLER: Stückzahl fehlt")
assert aktion == "stueck" and "Stückzahl" in text
assert bm.loesung("WARNUNG: kein gültiger Materialpreis")[1] == "material"
assert bm.loesung("FEHLER: Profil unbekannt")[1] == "editor"
text, aktion = bm.loesung("WARNUNG: etwas ganz Neues")
assert aktion == "experte" and text.startswith("Etwas ganz Neues") and "Expertenmodus" in text
h = bm.hinweise([], {"kundennr": None})
assert [x[2] for x in h] == ["import", "kunde"], h
ok("verständliche Hinweise mit Lösungsvorschlag (Stückzahl, Material, Editor, Expertenmodus, Import, Kunde)")

# Einfacher Modus 2.0 (27.11.2026): Stand je Schritt, Bereitschaft, Führung
assert [x[1] for x in bm.SCHRITTE] == ["Übersicht", "Anfrage und Kunde", "Bauteile", "Material und Fertigung",
                                       "Kalkulation", "Angebot"]
assert (bm.BEARBEITUNG, bm.ERGEBNIS) == (bm.MATERIAL, bm.KALKULATION)
bt_ok = [dict(stufe="OK")]
b = bm.bereitschaft([], {"kundennr": "K1"}, bt_ok, "aktuell", {"verkauf": 100})
assert b["bereit"] and b["stufe"] == "ok" and set(b["je_schritt"].values()) == {"ok"}, b
b = bm.bereitschaft([("HINWEIS", "kein Kunde", "kunde", None), ("FEHLER", "x: Stück", "stueck", 0)], {},
                    bt_ok, "aktuell", {"verkauf": 100})
assert not b["bereit"] and b["text"] == "2 Angaben fehlen" and b["je_schritt"][bm.KUNDE] == "fehlt"
assert b["je_schritt"][bm.BAUTEILE] == "fehlt" and b["je_schritt"][bm.MATERIAL] == "ok"
b = bm.bereitschaft([], {"kunde": "X"}, bt_ok, "VERALTET", {"verkauf": 100})
assert not b["bereit"] and b["text"] == "Noch nicht berechnet" and b["je_schritt"][bm.MATERIAL] == "offen"
b = bm.bereitschaft([("WARNUNG", "Staffeln veraltet", "experte", None)], {"kunde": "X"}, bt_ok, "aktuell",
                    {"verkauf": 100})
assert b["je_schritt"][bm.KALKULATION] == "fehlt" and b["text"] == "1 Angabe fehlt"
assert bm.schritt_von(("WARNUNG", "t", "experte", 3)) == bm.BAUTEILE
assert "Kunden wählen" in bm.naechster_schritt(bm.KUNDE, [], True, kunde=False)
assert "rot markierte" in bm.naechster_schritt(bm.BAUTEILE, [("FEHLER", "x", "stueck", 0)], True)
assert not bm.hilfe_an(db), "Hilfe auf Abruf (Vorgabe aus)"
hexwerte = set(__import__("re").findall(r"#[0-9A-Fa-f]{6}", es.STIL))
from rohrlaser import stil as _stil  # noqa: E402
assert hexwerte <= set(_stil.UMSETZUNG["Dunkel"]), sorted(hexwerte - set(_stil.UMSETZUNG["Dunkel"]))
assert "border-radius: 10px" not in es.STIL and "e_riesig" not in es.STIL, "nur Ecken aus design.py"
ok("Einfacher Modus 2.0: fünf Schritte, Stand je Schritt und „Bereit zur Ausgabe“, Führung als Satz, Stylesheet nur "
   "aus Klar-Farben mit Dunkel-Entsprechung")
db.schliessen() if hasattr(db, "schliessen") else None

# ------------------------------------------------------------------ Hauptfenster
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
f.resize(1400, 860)
f.show()
app.processEvents()
reiter_vorher = [f.reiter.tabText(i) for i in range(f.reiter.count())]
assert f.modus == bm.EXPERTE and f.modus_stapel.currentWidget() is f.reiter and f.menuBar().isVisible()
assert f.meine_leiste.isVisible() == f.meine_leiste.aufbau.get("sichtbar", True)
seite_e = next(s for s in (f.bereich.unter.widget(i) for i in range(f.bereich.unter.count()))
               if getattr(s, "schluessel", "") == "e_bedienmodus")
assert seite_e.wahl[bm.EXPERTE].isChecked() and seite_e.isEnabled()
ok("Start im Experten-Pro-Modus: Reiter, Menü und Werkzeugleiste wie bisher; Seite „Darstellung und "
   "Bedienoberfläche“ unter Einstellungen")

aid = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(aid)
seite_e.wahl[bm.EINFACH].setChecked(True)          # Umschalten in den Einstellungen
app.processEvents()
assert f.modus == bm.EINFACH and bm.modus(db) == bm.EINFACH
assert f.modus_stapel.currentWidget() is f.einfach and not f.menuBar().isVisible()
assert not f.meine_leiste.isVisible() and not f.info_dock.isVisible()
e = f.einfach
assert e.seite is s and e.schritt == bm.BAUTEILE, "geöffnete Kalkulation wird im einfachen Modus weiterbearbeitet"
werkzeugleiste_qt.aendern(f)                        # z. B. Benutzerwechsel, Abgleich: Leiste bleibt aus
assert not f.meine_leiste.isVisible() and not f.info_dock.isVisible() and not f.menuBar().isVisible()
ok("Wechsel Experte → einfach: gleiche Angebotsseite, Menü/Leiste/Info-Panel aus, auch nach Leistenänderung")

# alle Schritte füllen sich; Ergebnis aus derselben Rechnung
for i in range(6):
    e.zu_schritt(i)
    app.processEvents()
assert s.stand_optimierung() == "aktuell", "Ergebnis-Schritte rechnen den Schnittplan selbst"
zeilen, summen = s._rechnung()
erg = e.daten["ergebnis"]
assert abs(sum(erg["gruppen"].values()) - summen["verkauf"]) < 0.005, (erg["gruppen"], summen["verkauf"])
assert abs(erg["verkauf"] - summen["verkauf"]) < 1e-9 and erg["verkauf"] > 0
from rohrlaser import marge  # noqa: E402
assert abs(erg["gewinn"] - marge.werte(summen)["gewinn"]) < 1e-9 and erg["stufe"] in ("gut", "knapp", "kritisch")
assert e.kz_leiste.werte["verkauf"].text() == bm.euro(summen["verkauf"])
assert abs((db.angebot(aid) or {}).get("vk_netto") - round(summen["verkauf"], 2)) < 0.006, \
    "Kennzahl der Angebotsliste = Verkaufspreis im einfachen Modus"
assert e.preis_tab.rowCount() == len(s.positionen) and e.ang_tab.rowCount() == len(s.positionen)
assert len(e.mat_gruppen) == 4 and all(g["preis_m"] for g in e.mat_gruppen)
ok(f"fünf Schritte und Übersicht: Verkaufspreis {bm.euro(summen['verkauf'])} = Kalkulation des Expertenmodus, Kostengruppen "
   "ergeben genau den Preis, Marge/Ampel wie die Kachel „Gewinn und Marge“")

# Stückzahl im einfachen Modus ändern -> dieselben Daten im Expertenmodus
e.zu_schritt(bm.BAUTEILE)
vorher = summen["verkauf"]
assert e.stueck_setzen(0, 48)
app.processEvents()
assert db.positionen(aid)[0]["stueck"] == 48 and s.positionen[0]["stueck"] == 48
e.aktualisieren()
es.umschalten(f, bm.EXPERTE)
app.processEvents()
assert f.modus_stapel.currentWidget() is f.reiter and f.reiter.currentWidget() is s and f.menuBar().isVisible()
assert [f.reiter.tabText(i) for i in range(f.reiter.count())][:len(reiter_vorher)] == reiter_vorher
assert s.positionen[0]["stueck"] == 48
s.optimieren()
_, summen2 = s._rechnung()
assert summen2["verkauf"] > vorher
# im Expertenmodus ändern -> der einfache Modus zeigt es
db.position_aendern(s.positionen[1]["id"], "stueck", 80)
s.neu_laden()
es.umschalten(f, bm.EINFACH)
e.zu_schritt(bm.ANGEBOT)
assert e.ang_tab.item(1, 2).text() == "80" and e.ang_tab.item(0, 2).text() == "48", "Stück nur in Schritt 2, im Angebot angezeigt"
ok("dieselbe Kalkulation in beiden Modi: Änderung im einfachen Modus im Expertenmodus sichtbar und umgekehrt")

# Fracht und Marge im einfachen Modus (Patrick 25.11.2026): dieselben Kopffelder und dieselbe Rechnung
from rohrlaser import fracht_angebot as fa  # noqa: E402
e.zu_schritt(bm.BEARBEITUNG)
assert e.fr_modus.currentText() == fa.modus(s.kopf) and e.fr_betrag.isEnabled()
_, vor_fracht = s._rechnung()
assert e.fracht_setzen(150)
assert (db.angebot(aid) or {}).get("fracht") == 150 and s.kopf.get("fracht") == 150
_, mit_fracht = s._rechnung()
assert abs(mit_fracht["fracht"] - 150) < 0.005, mit_fracht["fracht"]
assert mit_fracht["verkauf"] > vor_fracht["verkauf"] + 140
assert e.daten["summen"]["verkauf"] == mit_fracht["verkauf"] and "150,00" in e.fr_text.text(), e.fr_text.text()
assert e.fracht_modus_setzen(fa.KEINE) and s._rechnung()[1]["fracht"] == 0 and not e.fr_betrag.isEnabled()
assert e.fracht_setzen(80) and fa.modus(s.kopf) == fa.MANUELL and s.kopf.get("fracht") == 80, \
    "Betrag bei „keine Fracht“: Frachtart wird manuell"
andere = fa.JE_STUECK if fa.umlage(s.kopf) == fa.NACH_GEWICHT else fa.NACH_GEWICHT
assert e.fracht_umlage_setzen(andere) and s.kopf.get("fracht_umlage") == andere and e.fr_umlage.currentText() == andere
assert e.fracht_berechnen() is not None, "Dialog „Fracht berechnen“ des Expertenmodus"
ok("Fracht im einfachen Modus: Betrag, Frachtart und Verteilung in denselben Angebotsfeldern, Verkaufspreis "
   "steigt um die Fracht, Dialog „Fracht berechnen“ wie im Expertenmodus")

e.zu_schritt(bm.ERGEBNIS)
g = e.marge_setzen(20)
assert g is not None and abs(s.kopf.get("gewinn") - round(100 * g, 2)) < 1e-9
m = marge.werte(s._rechnung()[1])["marge"]
assert 0.2 - 1e-6 <= m < 0.202, m
assert abs(e.daten["ergebnis"]["marge"] - m) < 1e-9 and "Marge 20" in e.mg_text.text(), e.mg_text.text()
assert s.auf_marge_setzen(0.2, rueckgaengig=False) == g, "gleiche Rechnung wie die Preisleiter"
assert e.marge_setzen(0) is None
_optimieren = s.optimieren
s.optimieren = lambda **_k: False                   # Schnittplan veraltet und nicht neu rechenbar
s.stand_optimierung, _stand = (lambda: "veraltet"), s.stand_optimierung
gewinn_vorher = s.kopf.get("gewinn")
assert e.marge_setzen(30) is None and s.kopf.get("gewinn") == gewinn_vorher, "nie auf veraltetem Schnittplan"
s.optimieren, s.stand_optimierung = _optimieren, _stand
db.einstellung_setzen("zielmarge", 0.25)
s.neu_laden()
e.aktualisieren()
assert e.mg_ziel.isVisibleTo(e) and "25" in e.mg_ziel.text()
assert e.marge_setzen(e._satz("zielmarge") * 100) is not None
assert 0.25 - 1e-6 <= marge.werte(s._rechnung()[1])["marge"] < 0.252
ok(f"Marge im einfachen Modus: 20 % ergibt Gewinnzuschlag {bm.zahl(100 * g, 2)} % (wie Preisleiter), Knopf "
   "Zielmarge aus den Einstellungen")

# Schritt 1 Anfrage und Kunde: Felder des Angebotskopfs, Kunde anlegen nur mit Kundennummer von Hand
e.zu_schritt(bm.KUNDE)
assert e.feld_setzen("projekt", "Hallentor Nord") and s.kopf.get("projekt") == "Hallentor Nord"
assert e.feld_setzen("kundenreferenz", "AN-118") and (db.angebot(aid) or {}).get("kundenreferenz") == "AN-118"
assert e.lieferzeit_setzen("3 Wochen") and s.kopf.get("lieferzeit_wert")
assert "Hallentor Nord" in e.untertitel.text() and e.an_projekt.text() == "Hallentor Nord"
assert e.kunde_anlegen({"name": "Neukunde Rohrbau GmbH"}) is None and "Kundennummer" in e.kn_fehler.text()
assert e.kunde_anlegen({"kundennr": "K-77001", "name": "Neukunde Rohrbau GmbH", "ort": "Münster"}) == "K-77001"
assert s.kopf.get("kundennr") == "K-77001" and s.kopf.get("kunde") == "Neukunde Rohrbau GmbH"
assert any("Neukunde Rohrbau GmbH · K-77001" in t for t in e._kd_modell.stringList()), "Kunde in der Vervollständigung"
assert e.bereit["je_schritt"][bm.KUNDE] == "ok" and "Neukunde" in e.titel.text()
ok("Schritt 1: Projekt, Zeichen und Lieferzeit in denselben Angebotsfeldern; neuer Kunde nur mit Kundennummer, "
   "danach übernommen und in der Suche")

# Schritt 5: Vorschau der ersten PDF-Seite ohne Ablage und ohne Versandvermerk
versand_vorher = (db.angebot(aid) or {}).get("versand")
e.zu_schritt(bm.ANGEBOT)
assert e.vorschau_aktualisieren() >= 1 and not e.pdf_bild.pixmap().isNull()
assert (db.angebot(aid) or {}).get("versand") == versand_vorher and (db.angebot(aid) or {}).get("vorgang") in (None, "", "Entwurf")
assert [t for t, _, _ in e.pruefliste()][0] == "Kunde gewählt"
ok("Schritt 5: Vorschau der ersten PDF-Seite im Programm (Entwurf, nichts abgelegt), Prüfliste")

# kleine Bildschirme: Zusammenfassung als Zeile, kurze Schrittleiste, kein waagerechter Rollbalken
for breite in (1600, 1280, 1100):
    f.resize(breite, 760)
    app.processEvents()
    for i in range(1, 6):
        e.zu_schritt(i)
        app.processEvents()
        rolle = e.stapel.currentWidget()
        assert rolle.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert rolle.widget().minimumSizeHint().width() <= rolle.viewport().width() + 1, \
            (breite, i, rolle.widget().minimumSizeHint().width(), rolle.viewport().width())
    breit = e.width() >= es.BREIT_AB
    e.zu_schritt(bm.KALKULATION)
    assert e._zus_aussen.isVisible() == breit and e.streifen.isVisible() == (not breit), breite
f.resize(1400, 860)
app.processEvents()
ok("schmale Bildschirme (1600, 1280, 1100 px): Zusammenfassung als Zeile, Seiten ohne waagerechten Rollbalken")

# Angebot erstellen (PDF) im einfachen und im Expertenmodus
pfad = e.pdf_erstellen()
assert pfad and Path(pfad).is_file(), pfad
es.umschalten(f, bm.EXPERTE)
assert s.angebot_pdf(oeffnen=False)
ok("Angebots-PDF im einfachen und im Expertenmodus")

# Neustart: Einstellung bleibt erhalten
es.umschalten(f, bm.EINFACH)
f.close()
f2 = Hauptfenster(db, tmp, stumm=True)
f2.resize(1400, 860)
f2.show()
app.processEvents()
assert f2.modus == bm.EINFACH and f2.modus_stapel.currentWidget() is f2.einfach and f2.einfach.schritt == bm.START
assert f2.modus_aktion.isChecked() and "Einfacher" in f2.modus_knopf.text()
ok("Neustart: einfacher Modus bleibt, Menü Ansicht und Statusleiste zeigen ihn")

# mehrere Mitarbeiter auf diesem Platz
echt = wl.benutzer
try:
    wl.benutzer = lambda _db: "AB"
    bm.setzen(db, bm.EXPERTE)
    wl.benutzer = lambda _db: "CD"
    bm.setzen(db, bm.EINFACH)
    wl.benutzer = lambda _db: "AB"
    es.benutzer_pruefen(f2)
    assert f2.modus == bm.EXPERTE and f2.menuBar().isVisible()
    wl.benutzer = lambda _db: "CD"
    f2.rechte_anwenden()                    # An-/Abmelden ruft rechte_anwenden
    assert f2.modus == bm.EINFACH and not f2.menuBar().isVisible()
finally:
    wl.benutzer = echt
ok("mehrere Mitarbeiter: AB arbeitet im Expertenmodus, CD im einfachen Modus, Wechsel bei der Anmeldung")

# STEP-Import im einfachen Modus
e2 = f2.einfach
quelle = tmp / "Rohr_K04.step"
shutil.copy(HIER / "step_konturen" / "K04_RE60x40x3_Senkung_Flowdrill.step", quelle)
anzahl = len(db.angebote())
neu = e2.neu_aus_step([str(quelle)], kundennr="")
assert neu is not None and e2.seite is neu and neu.positionen and e2.schritt == bm.BAUTEILE
b = e2.daten["bauteile"][0]
assert b["art"] == "rohr" and b["profil"] and b["laenge"] and b["konturen"], b
assert e2.bt.rowCount() == len(neu.positionen) and len(db.angebote()) == anzahl + 1
hinw = e2.daten["hinweise"]
assert any(x[2] == "kunde" for x in hinw), "ohne Kunde: gezielte Nachfrage statt Annahme"
assert [x[0] for x in hinw if x[2] == "stueck"] == ["FEHLER"], "Stückzahl aus der STEP unbekannt: nachfragen"
assert e2.stueck_setzen(0, 25)
app.processEvents()
e2.aktualisieren()
assert not [x for x in e2.daten["hinweise"] if x[2] == "stueck"]
e2.zu_schritt(bm.ERGEBNIS)
assert neu.stand_optimierung() == "aktuell" and e2.daten["ergebnis"]["verkauf"] > 0
es.umschalten(f2, bm.EXPERTE)
assert f2.reiter.currentWidget() is neu
ok(f"STEP-Import im einfachen Modus: {b['form']} {b['profil']}, {b['konturen']} Konturen erkannt, vollständig "
   "gerechnet, im Expertenmodus dieselbe Seite")

# Neue Kalkulation: beginnt mit Schritt 1 (Anfrage und Kunde), Stand „Noch keine Bauteile“
es.umschalten(f2, bm.EINFACH)
leer = e2.neu_anlegen()
assert leer is not None and e2.schritt == bm.KUNDE and e2.seite is leer and not leer.positionen
assert e2.bereit["text"] in ("2 Angaben fehlen", "1 Angabe fehlt", "Noch keine Bauteile"), e2.bereit
assert e2.bereit["je_schritt"][bm.KUNDE] == "fehlt" and "Kunden wählen" in e2.fuehrung.text()
f2.angebot_schliessen(leer.id)
db.angebot_loeschen(leer.id, trotz_schutz=True)
e2.oeffnen(neu.id)
ok("Neue Kalkulation beginnt beim Kunden; Schrittleiste und Kopf zeigen, was fehlt")

# unvollständige Bauteildaten und abgebrochene Neuanlage
es.umschalten(f2, bm.EINFACH)
db.position_neu(neu.id, dict(pos=99, bezeichnung="Ohne Stückzahl", profil_id=neu.positionen[0]["profil_id"],
                             werkstoff_id=neu.positionen[0]["werkstoff_id"], laenge=500.0))
neu.neu_laden()
e2.zu_schritt(bm.BAUTEILE)
fehlend = [x for x in e2.daten["hinweise"] if x[2] == "stueck"]
assert fehlend and fehlend[0][0] == "FEHLER" and "Ohne Stückzahl" in fehlend[0][1], e2.daten["hinweise"]
assert "rot markierte" in e2.fuehrung.text()
assert e2.loesen("stueck", fehlend[0][3]) and e2.bt.currentRow() == fehlend[0][3]
anzahl = len(db.angebote())
assert e2.neu_aus_cad([]) is None and len(db.angebote()) == anzahl, "abgebrochen: kein leeres Angebot bleibt"
assert e2.neu_aus_vorlage() is None and len(db.angebote()) == anzahl, "leere Bibliothek: Hinweis, nichts angelegt"
ok("fehlende Stückzahl: roter Hinweis mit Lösung (springt ins Feld), Führung unten; abgebrochene Neuanlage "
   "hinterlässt nichts")

# Expertenmodus vollständig erhalten
es.umschalten(f2, bm.EXPERTE)
assert f2.modus_stapel.currentWidget() is f2.reiter and f2.menuBar().isVisible()
assert f2.meine_leiste.isVisible() == f2.meine_leiste.aufbau.get("sichtbar", True)
assert rechnen.kalkulation is not None and hasattr(f2, "einstellungen") and f2.bereich.unter.count() > 30
ok("zurück im Expertenmodus: alle Reiter, Menüs, Einstellungen unverändert")
f2.close()
print("OK: Bedienmodus")
