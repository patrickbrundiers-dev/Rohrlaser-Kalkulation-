"""Verbesserungsplan 06.11.2026, Paket 2 (intuitive Bedienung):
- E1 keine abgeschnittenen Texte: Prüfung texte_pruefen; Hilfetexte enden mit „…“, 3D-Leiste bricht um statt die
     Knöpfe zu quetschen; Hauptfenster mit Angebot und Einstellungen bei 1366 × 768 ohne Funde
- E2 Prüfmeldungen im Editor ohne Meldung nur eine Zeile hoch
- E3 Lieferzeit in einem Feld (lieferzeit_lesen / lieferzeit_eingabe)
- B1 Suchfeld sichtbar oben rechts, Knöpfe der offenen Seite in der Befehlspalette
- B2 Schrittanzeige anklickbar, Knopf „Weiter: …“
- B3 Ursprung zurücksetzen ohne Rückfrage mit „Rückgängig“; Fehlermeldungen in Klartext (klartext.fehler_text)
- B4 Erste Schritte: Stand, einmal beim Start, Hilfe-Menü

Aufruf: python tests/test_bedienung_0611.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import errno
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from rohrlaser import befehlspalette, erste_schritte, hilfe, schritte, texte_pruefen  # noqa: E402
from rohrlaser.angebot import lieferzeit_eingabe, lieferzeit_lesen  # noqa: E402
from rohrlaser.ansicht3d_leiste import FlussLayout  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.klartext import fehler_text  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ E3 Lieferzeit in einem Feld
D = "2026-11-06"
for text, soll in (("3 Wochen", ("Wochen", "3", None)), ("ca. 3 Wochen nach Auftragseingang", ("Wochen", "3", None)),
                   ("10 AT", ("Arbeitstage", "10", None)),
                   ("10 Arbeitstage, Teillieferung möglich", ("Arbeitstage", "10", "Teillieferung möglich")),
                   ("KW 48", ("Kalenderwoche", "48/2026", None)), ("KW48/2027", ("Kalenderwoche", "48/2027", None)),
                   ("15.11.", ("Lieferdatum", "2026-11-15", None)), ("01.03.", ("Lieferdatum", "2027-03-01", None)),
                   ("bis 15.11.26", ("Lieferdatum", "2026-11-15", None)),
                   ("nach Absprache", ("nur Text", None, "nach Absprache")), ("2-3 Wochen", ("nur Text", None, "2-3 Wochen")),
                   ("Lieferzeit: 4 Wochen.", ("Wochen", "4", None)), ("", (None, None, None))):
    assert lieferzeit_lesen(text, D) == soll, (text, lieferzeit_lesen(text, D))
for falsch in ("KW 60", "31.02."):
    try:
        lieferzeit_lesen(falsch, D)
        raise AssertionError(falsch)
    except ValueError:
        pass
k = dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="10", lieferzeit_zusatz="Teillieferung möglich")
assert lieferzeit_eingabe(k) == "10 Arbeitstage, Teillieferung möglich"
assert lieferzeit_lesen(lieferzeit_eingabe(k), D) == ("Arbeitstage", "10", "Teillieferung möglich")
assert lieferzeit_eingabe(dict(lieferzeit_art="Lieferdatum", lieferzeit_wert="2026-11-15")) == "15.11.2026"
ok("E3 Lieferzeit: Wochen, AT, KW, Datum mit und ohne Jahr, Freitext, Spanne; ungültige KW/Datum abgelehnt")

# ------------------------------------------------------------------ E1 Hilfetext mit „…“, 3D-Leiste bricht um
w = QWidget()
w.resize(300, 60)
h = hilfe.Hinweis("Ein sehr langer erster Satz des Hilfetexts, der in dreihundert Pixel nie passt und darum "
                  "gekürzt werden muss. Zweiter Satz.", parent=w)
h.resize(300, 30)
w.show()
app.processEvents()
assert h.label.text() == hilfe.kurztext(h.text), "text() liefert immer den ganzen Text"
gezeigt = super(type(h.label), h.label).text()
assert gezeigt.endswith("…") and len(gezeigt) < len(h.kurz), gezeigt
assert not texte_pruefen.abgeschnitten(w), texte_pruefen.abgeschnitten(w)
h.aufklappen(True)
app.processEvents()
assert super(type(h.label), h.label).text() == h.text
w.close()

leiste = QWidget()
fl = FlussLayout(leiste)
knoepfe = [QPushButton(t) for t in ("Blick", "Schattiert", "Perspektivisch", "Schnittkörper", "Messen", "Winkel",
                                     "Maße löschen")]
for b in knoepfe:
    fl.addWidget(b)
leiste.resize(300, fl.heightForWidth(300))
leiste.show()
app.processEvents()
assert all(b.width() >= b.sizeHint().width() for b in knoepfe), "kein Knopf gequetscht"
assert fl.heightForWidth(300) > fl.heightForWidth(2000), "schmal: mehrere Zeilen"
assert not texte_pruefen.abgeschnitten(leiste)
leiste.close()
ok("E1 Hilfetext eingeklappt mit „…“ (text() ganz), 3D-Leiste bricht um statt zu quetschen")

# ------------------------------------------------------------------ Hauptfenster
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
f.resize(1366, 768)
f.show()
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="T1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                        stueck=4, schneidweg=320, einstiche=2))
s = f.angebot_oeffnen(a)
app.processEvents()

# B1 Suchfeld und Knöpfe in der Palette
assert f.suchknopf.parent() is f.menuBar().cornerWidget() and "Strg+K" in f.suchknopf.text()   # U2: in der Menüecke
e = befehlspalette.eintraege(f)
titel = {x.titel for x in e if x.art == "Knopf"}
assert {"Optimieren", "Zusatzarbeiten …", "Angebot (PDF)"} <= titel, sorted(titel)
assert befehlspalette.treffer(e, "zusatz")[0].titel.startswith("Zusatzarbeiten")
ok("B1 Suchfeld „Suchen … (Strg+K)“ in der Menüleiste; Knöpfe des Angebots in der Befehlspalette")

# B2 Schrittanzeige
sa = s.schritte
assert sa.weiter.isVisibleTo(sa) and sa.weiter.text() == ("Weiter ▸" if sa.stufe >= 1 else "Weiter: Optimieren ▸"), \
    sa.weiter.text()
assert sa.weiter.toolTip().startswith("Weiter: Optimieren"), sa.weiter.toolTip()
gewaehlt = []
sa.gewaehlt.connect(gewaehlt.append)
sa.weiter.click()
assert gewaehlt == [1] and db.angebot(a)["optimiert_am"], "Weiter: Optimieren optimiert"
app.processEvents()
ziel = schritte.WEITER[schritte.aktuell(sa.fertig)]
# schmales Fenster: ab Stufe 1 nur „Weiter ▸“, das Ziel steht dann im Tooltip (Layout-Prüfung 11.11.2026)
assert sa.weiter.text() == ("Weiter ▸" if sa.stufe >= 1 else f"Weiter: {ziel} ▸"), (sa.stufe, sa.weiter.text())
assert sa.weiter.toolTip().startswith(f"Weiter: {ziel}"), sa.weiter.toolTip()
ok("B2 Knopf „Weiter: Optimieren“ optimiert; danach nennt er den nächsten Schritt")

# E1 Prüfung: Angebot und Einstellungen bei 1366 × 768 ohne abgeschnittene Texte
funde = texte_pruefen.abgeschnitten(f)
assert not funde, "\n".join(map(str, funde))
f.zeigen(f.einstellungen)
app.processEvents()
funde = texte_pruefen.abgeschnitten(f)
assert not funde, "\n".join(map(str, funde))
ok("E1 Angebot und Einstellungen bei 1366 × 768: keine abgeschnittenen oder verdeckten Texte")

# ------------------------------------------------------------------ B3 Klartext
fehler = PermissionError(errno.EACCES, "Permission denied", "C:/Ablage/A-2026-0040.pdf")
assert "„A-2026-0040.pdf“" in fehler_text(fehler) and "geöffnet" in fehler_text(fehler)
assert "nicht (mehr) da" in fehler_text(FileNotFoundError(errno.ENOENT, "No such file", "x.csv"))
assert "belegt" in fehler_text(sqlite3.OperationalError("database is locked"))
assert fehler_text(ValueError("Lieferzeit: 31.02. ist kein Datum.")) == "Lieferzeit: 31.02. ist kein Datum."
assert fehler_text(PermissionError("Diese Stammdaten ändert nur der Admin.")) == "Diese Stammdaten ändert nur der Admin."
ok("B3 Fehlermeldungen in Klartext mit Lösung (gesperrte Datei, fehlende Datei, Datenbank belegt); eigene bleiben")

# ------------------------------------------------------------------ B4 Erste Schritte
db2 = Datenbank(tmp / "neu.db")
assert erste_schritte.beim_start_zeigen(db2)
st = erste_schritte.stand(db2)
assert not any(st.values()), st
f2 = Hauptfenster(db2, tmp, stumm=True)
d = f2.erste_schritte()
assert not erste_schritte.beim_start_zeigen(db2), "nur einmal von selbst"
d.haken["preise"].setChecked(True)
assert erste_schritte.stand(db2)["preise"]
db2.einstellung_setzen("briefkopf_1", "Muster GmbH")
db2.einstellung_setzen("benutzer_kuerzel", "MM")
assert erste_schritte.stand(db2)["firma"]
assert any(x.text() == "Erste Schritte …" for m in f2.menuBar().actions() if m.menu() for x in m.menu().actions())
assert erste_schritte.stand(db)["optimieren"] and erste_schritte.stand(db)["step"]
for i in range(erste_schritte.SCHON_ERFAHREN):
    db.angebot_neu(dict(kunde=f"K{i}"))
assert not erste_schritte.beim_start_zeigen(db), "erfahrener Platz: nicht ungefragt"
ok("B4 Erste Schritte: erkannt bzw. abgehakt, einmal beim Start, nicht auf erfahrenen Plätzen, Menü Hilfe")
print("Alle Tests OK")
