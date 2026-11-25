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
assert e.ek["verkauf"].zahl.text() == bm.euro(summen["verkauf"])
assert abs((db.angebot(aid) or {}).get("vk_netto") - round(summen["verkauf"], 2)) < 0.006, \
    "Kennzahl der Angebotsliste = Verkaufspreis im einfachen Modus"
assert e.preis_tab.rowCount() == len(s.positionen) and e.ang_tab.rowCount() == len(s.positionen)
assert len(e.mat_gruppen) == 4 and all(g["preis_m"] for g in e.mat_gruppen)
ok(f"sechs Schritte: Verkaufspreis {bm.euro(summen['verkauf'])} = Kalkulation des Expertenmodus, Kostengruppen "
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
assert e.menge_felder[1].value() == 80 and e.menge_felder[0].value() == 48
ok("dieselbe Kalkulation in beiden Modi: Änderung im einfachen Modus im Expertenmodus sichtbar und umgekehrt")

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
