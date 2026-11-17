"""Outlook-Ordner wählbar und Kategorie = Mitarbeiter (Patrick 16.11.2026, Freigabe „Alle Empfehlungen“).

Eingang, Neu, In Bearbeitung und Erledigt lassen sich einzeln wählen (Ordnerauswahl von Outlook, auch in einem
anderen Postfach). Eine Outlook-Kategorie steht für einen Mitarbeiter: in Outlook gesetzt = die Anfrage wird ihm
zugewiesen und bleibt in Neu (F1 a); im Programm zugewiesen oder übernommen = das Programm setzt die Kategorie an der
Mail, andere Kategorien bleiben (F2 a); zwei Mitarbeiter-Kategorien: die zuletzt gesetzte gilt, mit Hinweis (F3 a).
Geprüft mit dem nachgebauten Outlook (tests/outlook_nachbau.py), nur erfundene Testmails.

Aufruf: python tests/test_outlook_ordner_kategorien.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from outlook_nachbau import Outlook  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)
MA = {"PB": "Patrick Brundiers", "MK": "Max Kraus", "AS": "Anna Schmidt"}

# ------------------------------------------------------------------ O1 Zuordnung Kategorie -> Mitarbeiter
assert ol.kat_kuerzel("PB", {}, MA) == "PB" and ol.kat_kuerzel("max kraus", {}, MA) == "MK"
assert ol.kat_kuerzel("Kraus", {}, MA) == "MK" and ol.kat_kuerzel("Wichtig", {}, MA) == ""
assert ol.kat_kuerzel("Vertrieb", {"Vertrieb": "AS"}, MA) == "AS" and ol.kat_kuerzel("PB", {"PB": ""}, MA) == ""
assert ol.kuerzel_kat("AS", ["Wichtig", "Vertrieb"], {"Vertrieb": "AS"}, MA) == "Vertrieb"
assert ol.kuerzel_kat("MK", ["Kraus", "Wichtig"], {}, MA) == "Kraus" and ol.kuerzel_kat("XY", ["Kraus"], {}, MA) == ""
assert ol.kat_liste("Kraus; Wichtig") == ["Kraus", "Wichtig"] == ol.kat_liste("Kraus, Wichtig")
ok("O1 Kategorie → Mitarbeiter: von Hand zugeordnet, sonst Kürzel, Name oder Teil des Namens")

# ------------------------------------------------------------------ O2 Ordner frei gewählt
PFADE = {"Neu": "\\\\Team\\Anfragen offen", "In Bearbeitung": "\\\\Team\\In Arbeit",
         "Erledigt": "\\\\Archiv\\Anfragen 2026"}
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
ou = Outlook(pfade=PFADE, kategorien=["Kraus", "PB", "Wichtig", "Vertrieb"])
ou.mail("<a1@muster.example>", "Anfrage Halter", "Bitte 20 Stück.", "max@muster.example")
ou.mail("<b2@muster.example>", "Anfrage Winkel", "Bitte 5 Winkel.", "max@muster.example", kat=["Wichtig", "Kraus"])
pf = [PFADE["Neu"], PFADE["In Bearbeitung"], PFADE["Erledigt"]]


def abruf():
    return ol.abrufen(abl, "Anfragen", (), ausfuehren=ou, jetzt=JETZT, pfade=pf, zu=zu, mitarbeiter=MA)


zu = {}
erg = ol.abrufen(abl, "Anfragen", (), ausfuehren=ou, jetzt=JETZT)          # Vorgabe-Unterordner gibt es hier nicht
assert "nicht gefunden" in erg["fehler"][0] and not abl.alle()
erg = abruf()
assert not erg["fehler"] and len(erg["neu"]) == 2, erg
assert ou.aufrufe[-1]["unter_pfade"] == pf and len(ou.ordner["Neu"]) == 2
assert ol.pfad_name(PFADE["Erledigt"]) == "Anfragen 2026"
assert sorted(ol.kategorien_lesen(abl)) == ["Kraus", "PB", "Vertrieb", "Wichtig"]
ok("O2 Neu, In Bearbeitung, Erledigt als beliebige Outlook-Ordner (auch anderes Postfach); falscher Ordner = Meldung")

a1 = next(a for a in abl.alle() if a.kopf["nachrichten_id"] == "<a1@muster.example>")
b2 = next(a for a in abl.alle() if a.kopf["nachrichten_id"] == "<b2@muster.example>")
# ------------------------------------------------------------------ O3 Kategorie in Outlook = zugewiesen
b2 = abl.neu_lesen(b2)       # kam schon mit Kategorie „Kraus“: beim ersten Sehen zugewiesen
assert b2.status == ak.NEU and b2.stand["zugewiesen"] == "MK", b2.stand
ou.kat("<a1@muster.example>").append("PB")
erg = abruf()
a1 = abl.neu_lesen(a1)
assert a1.status == ak.NEU and a1.stand["zugewiesen"] == "PB" and erg["gefolgt"], erg
assert any("Kategorie „PB“" in n["text"] for n in a1.stand["notizen"])
assert ou.wo("<a1@muster.example>") == "Neu"                                # bleibt in Neu (F1 a)
ok("O3 Kategorie in Outlook gesetzt: Anfrage dem Mitarbeiter zugewiesen, bleibt in Neu, Notiz im Verlauf")

# ------------------------------------------------------------------ O4 Programm -> Outlook
abl.zuweisen(abl.neu_lesen(b2), "PB", jetzt=JETZT)          # im Programm umgehängt: Kraus -> PB
erg = abruf()
assert ou.kat("<b2@muster.example>") == ["Wichtig", "PB"] and erg["kategorien"] == 1, ou.kat("<b2@muster.example>")
assert abl.neu_lesen(b2).stand["zugewiesen"] == "PB"
zu = {"Vertrieb": "AS"}
abl.uebernehmen(abl.neu_lesen(a1), "AS", jetzt=JETZT)       # übernommen von Anna: Kategorie Vertrieb, Mail wandert
abruf()
assert ou.kat("<a1@muster.example>") == ["Vertrieb"] and ou.wo("<a1@muster.example>") == "In Bearbeitung"
n = len(ou.aufrufe)
erg = abruf()
assert not ou.aufrufe[-1]["kategorien"] and not erg["gefolgt"] and len(ou.aufrufe) == n + 1   # nichts mehr zu tun
ok("O4 Zuweisen/Übernehmen im Programm setzt die Kategorie an der Mail, andere Kategorien bleiben; danach Ruhe")

# ------------------------------------------------------------------ O5 zwei Mitarbeiter-Kategorien
ou.kat("<a1@muster.example>").append("Kraus")
erg = abruf()
a1 = abl.neu_lesen(a1)
assert a1.status == ak.BEARBEITUNG and a1.bearbeiter == "MK", (a1.bearbeiter, erg)
assert any("mehrere Mitarbeiter-Kategorien" in n["text"] for n in a1.stand["notizen"])
abruf()
assert ou.kat("<a1@muster.example>") == ["Kraus"]                    # die andere nimmt das Programm weg
ok("O5 zwei Mitarbeiter-Kategorien: die zuletzt gesetzte gilt (Bearbeiter gewechselt), Hinweis, die andere weg")

# ------------------------------------------------------------------ O6 Erledigt bleibt, wie es ist
abl.erledigen(abl.neu_lesen(a1), jetzt=JETZT)
abruf()
ou.kat("<a1@muster.example>")[:] = ["PB"]
erg = abruf()
assert abl.neu_lesen(a1).bearbeiter == "MK" and ou.kat("<a1@muster.example>") == ["PB"]
ok("O6 erledigte Anfragen: Kategorien werden weder gelesen noch gesetzt")

# ------------------------------------------------------------------ O7 Fenster „Outlook …“
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("benutzer_name", "Patrick Brundiers")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
ou2 = Outlook(pfade={"Neu": "\\\\Team\\Offen"}, kategorien=["Patrick", "Wichtig"])
seite.outlook_ausfuehren = ou2
d = seite.outlook_zeigen()
assert set(d.pfade) == {"neu", "bearbeitung", "erledigt"} and not d.pfade["neu"].text()
ou2.gewaehlt = "\\\\Team\\Offen"
assert d.waehlen("neu") == "\\\\Team\\Offen" and ol.unter_pfade(db) == ["\\\\Team\\Offen", "", ""]
assert d.waehlen("bearbeitung") == "" and ol.unter_pfade(db)[1] == ""     # derselbe Ordner zweimal: abgewiesen
ou2.gewaehlt = ""
assert d.waehlen("erledigt") == ""                                        # Auswahl abgebrochen: bleibt
rows = {d.kat_tab.item(r, 0).text(): d.kat_tab.cellWidget(r, 1) for r in range(d.kat_tab.rowCount())}
assert set(rows) == {"Patrick", "Wichtig"} and rows["Patrick"].currentData() == "PB"     # automatisch vorbelegt
rows["Wichtig"].setCurrentIndex(rows["Wichtig"].findData("PB"))
assert ol.zuordnung(db) == {"Wichtig": "PB"}
db.einstellung_setzen(ol.EIN, "ja")
ou2.mail("<x@probe.example>", "Anfrage Rahmen", "Bitte 3 Rahmen.", "jan@probe.example", kat=["Patrick"])
seite.outlook_abrufen(immer=True, warten=True)
x = next(a for a in seite.akten if a.kopf.get("nachrichten_id") == "<x@probe.example>")
assert x.stand["zugewiesen"] == "PB" and ou2.wo("<x@probe.example>") == "Neu", x.stand
d.anzeigen()
assert "Kategorien in Outlook gesetzt" in d.stand.text()
d.reject()
ok("O7 Fenster Outlook …: Ordner über die Outlook-Auswahl, doppelt abgewiesen, Kategorien automatisch vorbelegt "
   "und von Hand zuordenbar; Abruf der Seite nutzt Ordner und Zuordnung")
# ------------------------------------------------------------------ O8 Ordner in einem anderen Postfach (17.11.2026)
assert ol.ordner_waehlen(ou2)[3] == {}                                   # ohne Kennung (abgebrochen)
ou3 = Outlook(pfade={"Neu": "\\\\Vertrieb\\Neu"})
ou3.kennung = {"\\\\Vertrieb\\Neu": "ENTRY-VERTRIEB-NEU"}
ou3.nur_kennung = {"\\\\Vertrieb\\Neu"}           # nur als freigegebener Ordner sichtbar, nicht als Postfach
abl3 = ak.OrdnerAblage(tmp / "akten_o8", "PB", platz="BUERO1")
erg = ol.abrufen(abl3, "Anfragen", ausfuehren=ou3, pfade=["\\\\Vertrieb\\Neu", "", ""])
assert erg["fehler"] and "nicht gefunden" in erg["fehler"][0], erg      # nur über den Pfad: nicht gefunden
seite.outlook_ausfuehren = ou3
d = seite.outlook_zeigen()
ou3.gewaehlt = "\\\\Vertrieb\\Neu"
assert d.waehlen("neu") == "\\\\Vertrieb\\Neu"
assert ol.ordner_ids(db) == {"\\\\Vertrieb\\Neu": {"e": "ENTRY-VERTRIEB-NEU", "s": "store-1"}}
d.reject()
erg = ol.abrufen(abl3, "Anfragen", ausfuehren=ou3, pfade=ol.unter_pfade(db), ids=ol.ordner_ids(db))
assert not erg["fehler"], erg
assert ou3.aufrufe[-1]["ids"]["\\\\Vertrieb\\Neu"]["e"] == "ENTRY-VERTRIEB-NEU"
db.einstellung_setzen(ol.PFAD_EINSTELLUNG["neu"], "")
ol.ordner_id_merken(db, "\\\\Team\\Offen", "")                           # nicht mehr benutzte Kennungen fallen weg
assert ol.ordner_ids(db) == {}
assert "GetFolderFromID" in ol.ABRUF_PS and "EntryID" in ol.WAEHLEN_PS and "StoreID" in ol.WAEHLEN_PS
ok("O8 Ordner aus einem anderen Postfach: die Kennung aus der Outlook-Auswahl wird gemerkt und beim Abruf genutzt, "
   "auch wenn der Ordner nur als freigegebener Ordner sichtbar ist")
print("Alle Tests bestanden.")
