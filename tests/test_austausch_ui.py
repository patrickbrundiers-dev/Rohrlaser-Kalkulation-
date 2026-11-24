"""Austauschordner 2.0, Paket B: Seite „Austausch“ (austausch_seite.py) und Benachrichtigungen/Übersicht/Inhaltssuche.

- B1 Reiter Austausch in der Gruppe Arbeiten, Navigation mit Schnellzugriff/Bereichen/Archiv/Papierkorb
- B2 Hochladen über die Seite (Rückfrage bei gleichem Namen: neue Version), Ordner anlegen, Liste/Kacheln, Pfad
- B3 Suche über alle Bereiche (Name, Kommentar, Inhalt), Filter Typ/Status/Mitarbeiter, Sortierung, Suche merken
- B4 Infobereich: Zuordnung als Vorschlag bestätigen, Verantwortlich/Status/Fällig speichern, Kommentar, Versionen
- B5 Kontextmenü, Umbenennen, Verschieben per Ziehen, Papierkorb mit Wiederherstellen, Archiv
- B6 Bearbeiten mit fremder Sperre: Rückfrage „Nur ansehen / Trotzdem“
- B7 Neu für mich (auch bei alter Änderungszeit der Quelle), Übersicht/Dashboard mit Zahlen, Anpassen
- B8 Benachrichtigungen: erste Prüfung still, dann Zuweisung/Kommentar/neue Datei vom Kollegen, eigene nie,
     abschaltbar, viele neue Dateien als eine Sammelmeldung
- B9 Inhaltssuche: Text aus TXT/CSV/LST im Zwischenspeicher, geänderte Datei wird neu gelesen

Aufruf: python tests/test_austausch_ui.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import austausch_dateien as ad  # noqa: E402
from rohrlaser import navigation, teilen  # noqa: E402
from rohrlaser.austausch_seite import DASHBOARD_KACHELN, MIME, AustauschSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())
gemeinsam = TMP / "Gemeinsam"
gemeinsam.mkdir()


def ok(t):
    print("OK    ", t)


def platz(k, name):
    db = Datenbank(TMP / k / "rohrlaser.db")
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    db.einstellung_setzen("ablageordner", str(TMP / k / "ablage"))
    return db


(TMP / "PB").mkdir()
(TMP / "MK").mkdir()
db = platz("PB", "Patrick")
db2 = platz("MK", "Max")
quelle = TMP / "quelle"
quelle.mkdir()


def datei(name, inhalt="x", alt=False):
    p = quelle / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode())
    if alt:
        os.utime(p, (time.time() - 400 * 86400,) * 2)
    return p


# ------------------------------------------------------------------ B1 Reiter und Navigation
f = Hauptfenster(db, stumm=True)
s = f.austausch
assert isinstance(s, AustauschSeite) and f.reiter.indexOf(s) >= 0
assert navigation.GRUPPE["Austausch"] == "Arbeiten" and navigation.SYMBOL["Austausch"] == "ordner"
f.reiter.setCurrentWidget(s)
s.neu_laden(einlesen=True)
texte = []
for i in range(s.nav.topLevelItemCount()):
    top = s.nav.topLevelItem(i)
    texte += [top.child(j).text(0) for j in range(top.childCount())]
for t in ("Übersicht", "Neu für mich", "Meine Aufgaben", "Favoriten", "Zuletzt verwendet", "Wer arbeitet woran",
          "Gemeinsame Dateien", "Mein Ordner", "Archiv", "Papierkorb"):
    assert any(x.startswith(t) for x in texte), (t, texte)
assert s.stapel.currentWidget() is s.uebersicht_flaeche and not s.k_hoch.isEnabled()
ok("B1 Reiter Austausch (Gruppe Arbeiten), Navigation, Start mit Übersicht")

# ------------------------------------------------------------------ B2 Hochladen, Ordner, Ansicht
s.gehe("bereich", ad.DATEIEN, "")
assert s.k_hoch.isEnabled()
b = s.hochladen([datei("Halter 2026-00042.step", "ISO-10303-21; alt"), datei("Notiz.txt", "Bitte Gehrung 45 Grad"),
                 datei("Zeichnung.pdf", b"%PDF-1.4", alt=True)])
assert b.ok and len(b.neu) == 3, b.text()
assert {e.name for e in s.modell.eintraege} >= {"Halter 2026-00042.step", "Notiz.txt", "Zeichnung.pdf"}
datei("Halter 2026-00042.step", "ISO-10303-21; neu")
s.antworten = [0]                                   # Rückfrage gleicher Name: „Neue Version“
b = s.hochladen([quelle / "Halter 2026-00042.step"])
assert len(b.versionen) == 1 and not s.antworten
assert s.ordner_neu("Projekt Müller") == "dateien:Projekt Müller"
s.gehe("bereich", ad.DATEIEN, "Projekt Müller")
assert s.pfad_zeile.count() >= 3 and s.k_hoch.isEnabled()
s.hochladen([datei("Rohr.dxf")])
assert [e.name for e in s.modell.eintraege] == ["Rohr.dxf"]
s.gehe("bereich", ad.DATEIEN, "")
s.k_kacheln.setChecked(True)
assert s.stapel.currentWidget() is s.kachel and s.modell.kacheln
assert (db.einstellung(ad.L_ANSICHT) or {}).get("kacheln") is True
s.k_kacheln.setChecked(False)
assert s.stapel.currentWidget() is s.liste
ok("B2 Hochladen mit Rückfrage (neue Version), Ordner, Pfadzeile, Liste/Kacheln gemerkt")

# ------------------------------------------------------------------ B4 Infobereich (vor der Suche: Kommentar)
e = s.waehlen("dateien:Halter 2026-00042.step")
assert e is not None and s.info.datei == e.datei
assert s.info.versionen.count() == 1 and s.info.k_version.isEnabled()
m = ad.meta(db, e.datei)
assert m.get("angebot") == "2026-00042" or ad.vorschlaege(m), m
if ad.vorschlaege(m):
    assert s.info.k_bestaetigen.isVisibleTo(s.info)
    s.vorschlag(True)
    assert ad.meta(db, e.datei)["angebot"] == "2026-00042"
s.waehlen(e.datei)
s.info.bearbeiter.setCurrentText("mk")
s.info.status.setCurrentText(ad.BEARBEITUNG)
s.info.faellig_an.setChecked(True)
s.info.aufgabe.setText("Kalkulieren bis Freitag")
assert s.info_speichern() >= 3
m = ad.meta(db, e.datei)
assert m["bearbeiter"] == "MK" and m["status"] == ad.BEARBEITUNG and m["faellig"] and m["aufgabe"]
s.waehlen(e.datei)
s.info.kommentar.setText("@MK Bitte Schweißnaht prüfen")
s.kommentieren()
v = ad.verlauf(db, e.datei)
k = next(x for x in v if x["art"] == ad.E_KOMMENTAR)
assert k["an"] == "MK" and k["text"] == "Bitte Schweißnaht prüfen"
assert "Schweißnaht" in s.info.verlauf.toPlainText()
s.waehlen(e.datei)
s.info.versionen.setCurrentRow(0)
s.antworten = [0]
s.version_zurueck()
assert (ad.pfad(db, e.datei, s.w)).read_text() == "ISO-10303-21; alt"
ok("B4 Infobereich: Zuordnung (Angebot aus Namen), Verantwortlich/Status/Fällig/Aufgabe, Kommentar an MK, Version")

# ------------------------------------------------------------------ B3 Suche und Filter
s.suche.setText("schweissnaht")                     # Kommentar, ohne Umlaut
s.filter_anwenden()
assert s.ansicht[0] == "alle" and [x.name for x in s.modell.eintraege] == ["Halter 2026-00042.step"]
s.suche.setText("gehrung")                          # Dateiinhalt
s.filter_anwenden()
assert [x.name for x in s.modell.eintraege] == ["Notiz.txt"], [x.name for x in s.modell.eintraege]
s.suche.setText("")
s.typ.setCurrentIndex(s.typ.findData("dxf"))
s.filter_anwenden()
assert {x.name for x in s.modell.eintraege} == {"Rohr.dxf"}, [x.name for x in s.modell.eintraege]
s.typ.setCurrentIndex(0)
s.status.setCurrentIndex(s.status.findData(ad.BEARBEITUNG))
s.filter_anwenden()
assert [x.name for x in s.modell.eintraege] == ["Halter 2026-00042.step"]
s.suche_merken("In Bearbeitung")
assert any(x["name"] == "In Bearbeitung" for x in ad.gespeicherte_suchen(db))
s.status.setCurrentIndex(0)
s.mitarbeiter.setCurrentIndex(s.mitarbeiter.findData("MK"))
s.filter_anwenden()
assert [x.name for x in s.modell.eintraege] == ["Halter 2026-00042.step"]
s.mitarbeiter.setCurrentIndex(0)
s.gehe("suche", "In Bearbeitung")
assert s.status.currentData() == ad.BEARBEITUNG and len(s.modell.eintraege) == 1
s.status.setCurrentIndex(0)
s.gehe("bereich", ad.DATEIEN, "")
s.sortieren.setCurrentIndex(s.sortieren.findData("groesse"))
s.absteigend.setChecked(True)
dateien = [x for x in s.modell.eintraege if not x.ordner]
assert [x.groesse for x in dateien] == sorted((x.groesse for x in dateien), reverse=True)
s.sortieren.setCurrentIndex(s.sortieren.findData("name"))
s.absteigend.setChecked(False)
ok("B3 Suche über alle Bereiche (Kommentar ohne Umlaut, Inhalt), Filter Typ/Status/Mitarbeiter, gespeicherte Suche")

# ------------------------------------------------------------------ B5 Menü, Umbenennen, Ziehen, Papierkorb, Archiv
s.waehlen("dateien:Notiz.txt")
texte = [x[0] for x in s.menue_aktionen(s.gewaehlte()) if x]
for t in ("Vorschau", "Bearbeiten (öffnen)", "Herunterladen …", "Kopieren nach …", "Verschieben nach …",
          "Umbenennen …", "Archivieren", "In den Papierkorb …", "Zu Favoriten", "Zuweisen an", "Status",
          "Zuordnung erkennen", "Im Explorer zeigen"):
    assert t in texte, (t, texte)
assert s.umbenennen("Notiz Kunde.txt") == "dateien:Notiz Kunde.txt"
md = QMimeData()
md.setData(MIME, b"dateien:Notiz Kunde.txt")
ziel = next(x for x in s.modell.eintraege if x.ordner and x.name == "Projekt Müller")
s.abgelegt(md, ziel)
assert (s.w[ad.DATEIEN] / "Projekt Müller" / "Notiz Kunde.txt").exists()
md = QMimeData()
md.setUrls([QUrl.fromLocalFile(str(datei("Extern.csv", "a;b")))])
s.abgelegt(md)
assert (s.w[ad.DATEIEN] / "Extern.csv").exists()
s.waehlen("dateien:Extern.csv")
s.antworten = [0]
assert s.loeschen() == 1 and not (s.w[ad.DATEIEN] / "Extern.csv").exists()
s.gehe("papierkorb")
assert s.stapel.currentWidget() is s._korb_box and len(s._korb) == 1
assert s.korb_zurueck(list(s._korb)) == 1 and (s.w[ad.DATEIEN] / "Extern.csv").exists()
s.gehe("bereich", ad.DATEIEN, "")
s.waehlen("dateien:Extern.csv")
assert s.archivieren() == ["dateien:_Archiv/Extern.csv"]
s.gehe("archiv")
assert [x.name for x in s.modell.eintraege] == ["Extern.csv"]
s.waehlen("dateien:_Archiv/Extern.csv")
assert "Aus dem Archiv holen" in [x[0] for x in s.menue_aktionen(s.gewaehlte()) if x]
s.archivieren()
assert (s.w[ad.DATEIEN] / "Extern.csv").exists()
s.gehe("bereich", ad.DATEIEN, "")
s.waehlen("dateien:Zeichnung.pdf")
s._favorit(s.gewaehlt_eins())
s.gehe("favoriten")
assert [x.name for x in s.modell.eintraege] == ["Zeichnung.pdf"]
ok("B5 Kontextmenü, Umbenennen, Ziehen in Ordner und von außen, Papierkorb zurück, Archiv hin und zurück, Favorit")

# ------------------------------------------------------------------ B6 Bearbeiten mit fremder Sperre
geoeffnet = []
f.datei_oeffnen = lambda p: geoeffnet.append(Path(p))
ad.bearbeiten(db2, "dateien:Zeichnung.pdf")             # Max hat sie offen
s.gehe("bereich", ad.DATEIEN, "")
e = s.waehlen("dateien:Zeichnung.pdf")
assert "MK" in (s.sperre_von(e) or {}).get("wer", "") and "MK" in s.info.sperre.text()
s.antworten = [1]                                       # trotzdem bearbeiten
p = s.bearbeiten(e)
assert p is not None and geoeffnet[-1] == p
assert len(ad.versionen(p)) >= 1
ad.entsperren(db2, "dateien:Zeichnung.pdf")
ok("B6 Bearbeiten: fremde Sperre angezeigt, Rückfrage, Sicherung vor dem Öffnen")

# ------------------------------------------------------------------ B7 Neu für mich und Übersicht
teilen.abgleichen(db, teilen.ZUSAMMENFUEHREN)
teilen.abgleichen(db2, teilen.ZUSAMMENFUEHREN)
db2.einstellung_setzen("austausch_erststart", time.time() - 3600)
s2 = AustauschSeite(f)                                  # Max' Sicht mit eigener Datenbank
s2.db = db2
s2.neu_laden(einlesen=True)
s2.gehe("neu")
neu_namen = {x.name for x in s2.modell.eintraege}
assert "Zeichnung.pdf" in neu_namen, neu_namen         # Quelle 400 Tage alt, aber eben hochgeladen
s2.gesehen(s2.modell.eintraege)
s2.gehe("neu")
assert not s2.modell.eintraege
s2.gehe("meine")
assert [x.name for x in s2.modell.eintraege] == ["Halter 2026-00042.step"]
s2.gehe("uebersicht")
assert s2.uebersicht.kacheln["meine"].text().startswith("1") and s2.uebersicht.kacheln["faellig"].text()[0] == "1"
s2.uebersicht.anpassen_dialog(werte={"meine", "wer"})
assert not s2.uebersicht.kacheln["neu"].isVisibleTo(s2.uebersicht) and \
    s2.uebersicht.kacheln["meine"].isVisibleTo(s2.uebersicht)
s2.uebersicht.anpassen_dialog(werte={k for k, _, _ in DASHBOARD_KACHELN})
ok("B7 Neu für mich (auch alte Quelldatei), gesehen, Meine Aufgaben, Übersicht mit Zahlen, Anpassen")

# ------------------------------------------------------------------ B8 Benachrichtigungen
assert ad.benachrichtigungen(db2) == []                 # erste Prüfung: nur Stand merken
s.gehe("bereich", ad.DATEIEN, "")
ad.setzen(db, "dateien:Zeichnung.pdf", bearbeiter="MK")
ad.kommentar(db, "dateien:Zeichnung.pdf", "Neue Revision liegt bei", an="MK")
ad.hochladen(db, [datei("Neu1.pdf", b"%PDF")], ad.DATEIEN)
ad.kommentar(db2, "dateien:Zeichnung.pdf", "Eigener Kommentar")      # eigene nie
teilen.abgleichen(db)
teilen.abgleichen(db2)
liste = ad.benachrichtigungen(db2)
arten = {x["art"] for x in liste}
assert {ad.M_ZUGEWIESEN, ad.M_NACHRICHT, ad.M_DATEI} <= arten, liste
assert not any("Eigener" in x["text"] for x in liste)
assert ad.benachrichtigungen(db2) == []                 # nichts doppelt
ad.meldungen_setzen(db2, {ad.M_DATEI: False})
ad.hochladen(db, [datei(f"Viele{i}.pdf", b"%PDF") for i in range(5)], ad.DATEIEN)
teilen.abgleichen(db)
teilen.abgleichen(db2)
assert ad.benachrichtigungen(db2) == []
ad.meldungen_setzen(db2, {ad.M_DATEI: True})
ad.hochladen(db, [datei(f"Mehr{i}.pdf", b"%PDF") for i in range(5)], ad.DATEIEN)
teilen.abgleichen(db)
teilen.abgleichen(db2)
liste = ad.benachrichtigungen(db2)
assert len([x for x in liste if x["art"] == ad.M_DATEI]) == 1 and "5 neue Dateien" in liste[0]["text"], liste
s2.meldungen_dialog(werte={ad.M_FERTIG: True})
assert ad.meldungen_an(db2)[ad.M_FERTIG]
ok("B8 Benachrichtigungen: erste Prüfung still, Zuweisung/Kommentar/neue Datei, eigene nie, abschaltbar, Sammelmeldung")

# ------------------------------------------------------------------ B9 Inhaltssuche
inh = ad.Inhalt(TMP / "cache")
w = ad.wurzeln(db)
ad.hochladen(db, [datei("Prog.lst", "BEGIN_PROGRAMM\nMATERIAL S235JR\nEND"), datei("Liste.csv", "Teil;Menge\nA4711;5")],
             ad.DATEIEN)
alle = ad.alle(db, w=w)
eintraege = [x for v in alle.values() for x in v]
assert inh.lesen(eintraege, w) >= 2
inh.speichern()
t = inh.text()
assert "S235JR" in t["dateien:Prog.lst"] and "A4711" in t["dateien:Liste.csv"]
inh2 = ad.Inhalt(TMP / "cache")
assert not [x for x in inh2.fehlend(eintraege) if x.datei in ("dateien:Prog.lst", "dateien:Liste.csv")]
p = w[ad.DATEIEN] / "Liste.csv"
p.write_text("Teil;Menge\nB0815;2")
os.utime(p, (time.time() + 5,) * 2)
eintraege = [x for v in ad.alle(db, w=w).values() for x in v]
assert [x.datei for x in inh2.fehlend(eintraege) if x.datei == "dateien:Liste.csv"]
inh2.lesen(eintraege, w)
assert "B0815" in inh2.text()["dateien:Liste.csv"]
ok("B9 Inhaltssuche: LST/CSV gelesen, Zwischenspeicher, geänderte Datei neu gelesen")

f.close()
print("OK: Austauschordner Oberfläche (Paket B)")
