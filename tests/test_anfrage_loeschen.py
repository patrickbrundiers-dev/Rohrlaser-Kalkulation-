"""Anfragen zusammenführen ohne Wiederkehr und Anfrage löschen (Patrick 24.11.2026).

  L1 Fehler: nach dem Zusammenführen lagen die Originale der weiteren Anfragen noch im Anfrage-Ordner und kamen beim
     nächsten Blick als neue Anfrage zurück (Dateien ohne Mail). Jetzt: keine neue Akte, Originale nach .uebernommen
  L2 Löschen: Ordner „Gelöscht“ (nicht in Neu/Erledigt/Meine, nicht in der Auswertung), Status Erledigt (Outlook),
     Grund, nicht doppelt, „Wieder öffnen“ greift nicht, Wiederherstellen in den alten Ordner, nicht zusammenführbar;
     kommt aus dem Anfrage-Ordner nicht als neu zurück; eine später neu abgelegte gleiche Datei schon
  L3 Seite „Anfragen“: Zähler „Gelöscht“, Knöpfe Löschen …/Wiederherstellen, Zusammenführen und Löschen legen die
     Originale aus dem Anfrage-Ordner weg, die Karte zeigt sie nicht mehr

Aufruf: python tests/test_anfrage_loeschen.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import anfragen  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import anfragen_sammeln as sa  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
ALT = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()


def ablegen(ordner, name, inhalt):
    """Datei im Anfrage-Ordner (je Anfrage ein Unterordner), 30 Minuten alt."""
    o = ordner / Path(name).stem
    o.mkdir(parents=True, exist_ok=True)
    p = o / name
    p.write_bytes(inhalt)
    os.utime(p, (ALT, ALT))
    return p


def erfassen(abl, inbox):
    return ak.aus_ordner(abl, anfragen.suchen(inbox), inbox=inbox)


# ---------------------------------------------------------------------------------------------- L1
inbox = tmp / "Eingang"
inbox.mkdir()
ablegen(inbox, "rahmen.step", b"ISO-10303-21; Rahmen")
ablegen(inbox, "deckel.step", b"ISO-10303-21; Deckel")
abl = ak.OrdnerAblage(tmp / "akten", "PB")
erf = erfassen(abl, inbox)
assert len(erf) == 2 and len(abl.alle()) == 2, erf
haupt, weitere = sorted(abl.alle(), key=lambda a: a.betreff)[1], sorted(abl.alle(), key=lambda a: a.betreff)[0]
sa.zusammenfuehren(abl, haupt, [weitere])
weitere = abl.neu_lesen(weitere)
assert weitere.stand["zusammengefuehrt_in"] == haupt.nr and weitere.status == ak.ERLEDIGT
abl.uebernehmen(abl.neu_lesen(haupt))           # „Kalkulieren“ übernimmt die Hauptanfrage und legt ihr Original weg
ak.eingang_ablegen(next(x for x in anfragen.suchen(inbox) if ak.akte_zu(abl, x).nr == haupt.nr), inbox, haupt.nr)
for _ in range(2):                              # vorher: jeder Blick legte die Datei der weiteren neu an
    erf = erfassen(abl, inbox)
    assert len(abl.alle()) == 2, [a.nr for a in abl.alle()]
    assert all(a.status != ak.NEU for a in erf.values()), erf
assert not (inbox / "deckel" / "deckel.step").exists() and (inbox / ".uebernommen" / weitere.nr / "deckel.step").exists()
ok("Zusammengeführte Anfrage kommt aus dem Anfrage-Ordner nicht als neu zurück, Original liegt in .uebernommen")

# ---------------------------------------------------------------------------------------------- L2
ablegen(inbox, "halter.step", b"ISO-10303-21; Halter")
ablegen(inbox, "winkel.step", b"ISO-10303-21; Winkel")
erfassen(abl, inbox)
neu = {a.betreff: a for a in abl.alle() if a.status == ak.NEU}
halter, winkel = neu["halter"], neu["winkel"]
winkel = abl.uebernehmen(winkel)
ak.eingang_ablegen(next(x for x in anfragen.suchen(inbox) if ak.akte_zu(abl, x).nr == winkel.nr), inbox, winkel.nr)
h = abl.loeschen(halter, "doppelt geschickt")
assert h.geloescht and h.status == ak.ERLEDIGT and h.stand["geloescht_grund"] == "doppelt geschickt"
assert h.stand["geloescht_von"] == "PB" and h.stand["status_vor_loeschen"] == ak.NEU
try:
    abl.loeschen(h)
    raise AssertionError("doppelt gelöscht")
except ak.AblageFehler:
    pass
alle = abl.alle()
z = ak.zaehlen(alle, "PB")
assert z[ak.GELOESCHT] == 1 and z[ak.NEU] == 0 and z[ak.ERLEDIGT] == 1, z      # erledigt = die zusammengeführte
for o in (None, ak.NEU, ak.ERLEDIGT, "meine", ak.AUSSORTIERT):
    assert h.nr not in [a.nr for a in ak.filtern(alle, o, "PB")], o
assert [a.nr for a in ak.filtern(alle, ak.GELOESCHT)] == [h.nr]
assert sum(x[1] for x in ak.auswertung(alle)["wochen"]) == 3                     # gelöschte zählt nicht
assert "Gelöscht: doppelt geschickt" in ak.verlauf_text([e for e in h.verlauf if e["aktion"] == ak.GELOESCHT][0])
erfassen(abl, inbox)
assert len(abl.alle()) == 4 and not (inbox / "halter" / "halter.step").exists()
ok("Löschen: Ordner „Gelöscht“, aus Listen/Zählern/Auswertung heraus, kommt aus dem Ordner nicht als neu zurück")

abl.ereignis(h, ak.WIEDER)                      # „Wieder öffnen“ holt eine gelöschte nicht zurück
assert abl.neu_lesen(h).geloescht
h = abl.wiederherstellen(h)
assert not h.geloescht and h.status == ak.NEU and h.stand["erledigt_am"] == "" and h.nr in [
    a.nr for a in ak.filtern(abl.alle(), ak.NEU)]
try:
    abl.wiederherstellen(h)
    raise AssertionError("nicht gelöscht wiederhergestellt")
except ak.AblageFehler:
    pass
w = abl.loeschen(winkel)
assert w.stand["status_vor_loeschen"] == ak.BEARBEITUNG
try:
    sa.zusammenfuehren(abl, h, [w])
    raise AssertionError("gelöschte zusammengeführt")
except ak.AblageFehler as e:
    assert "gelöscht" in str(e)
w = abl.wiederherstellen(w)
assert w.status == ak.BEARBEITUNG and w.bearbeiter == "PB" and w.stand["erledigt_von"] == ""
ok("Wiederherstellen: zurück in Neu bzw. In Bearbeitung (mit Bearbeiter); gelöschte nicht zusammenführbar")

ablegen(inbox, "bolzen.step", b"ISO-10303-21; Bolzen")
erfassen(abl, inbox)
b = next(a for a in abl.alle() if a.betreff == "bolzen")
g = abl.loeschen(b, jetzt=datetime.datetime.now() - datetime.timedelta(minutes=20))
assert g.geloescht
ak.eingang_ablegen(next(x for x in anfragen.suchen(inbox) if Path(x.ordner).name == "bolzen"), inbox, g.nr)
p = ablegen(inbox, "bolzen.step", b"ISO-10303-21; Bolzen")
spaeter = (datetime.datetime.now() - datetime.timedelta(minutes=5)).timestamp()
os.utime(p, (spaeter, spaeter))                 # nach dem Löschen neu abgelegt: echte Wiederholung
erfassen(abl, inbox)
neue = [a for a in abl.alle() if a.betreff == "bolzen" and a.status == ak.NEU]
assert len(neue) == 1 and neue[0].nr != g.nr, neue
ok("Gleiche Datei später neu abgelegt: eigene neue Anfrage (Wiederholung)")

# ---------------------------------------------------------------------------------------------- L3
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
inbox2 = tmp / "Eingang2"
inbox2.mkdir()
db.einstellung_setzen(anfragen.EINSTELLUNG, str(inbox2))
ablegen(inbox2, "rohr_a.step", b"ISO-10303-21; Rohr A")
ablegen(inbox2, "rohr_b.step", b"ISO-10303-21; Rohr B")
ablegen(inbox2, "rohr_c.step", b"ISO-10303-21; Rohr C")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
seite = fenster.anfragen_seite
seite.neu_laden()
assert len(karte.anfragen) == 3 and len(seite.akten) == 3, (karte.anfragen, seite.akten)
assert "Gelöscht" in seite.zaehler[ak.GELOESCHT].text()
nr = {a.betreff: a.nr for a in seite.akten}
seite.waehlen(nr["rohr_a"])
assert seite.zusammenfuehren([nr["rohr_b"]], bestaetigt=True)
karte.neu_laden(erzwingen=True)
assert sorted(Path(x.ordner).name for x in karte.anfragen) == ["rohr_a", "rohr_c"], karte.anfragen
seite.waehlen(nr["rohr_c"])
assert seite.k_loeschen.isVisibleTo(seite) and not seite.k_herstellen.isVisibleTo(seite)
assert seite.loeschen("Test") is not None
karte.neu_laden(erzwingen=True)
assert [Path(x.ordner).name for x in karte.anfragen] == ["rohr_a"] and len(seite.akten) == 3
assert seite.zaehler[ak.GELOESCHT].text().endswith("1"), seite.zaehler[ak.GELOESCHT].text()
seite.ordner_waehlen(ak.GELOESCHT)
assert seite.tabelle.rowCount() == 1 and seite.tabelle.item(0, 0).text() == nr["rohr_c"]
seite.waehlen(nr["rohr_c"])
assert "Gelöscht" in seite.inhalt.toHtml() and seite.k_herstellen.isVisibleTo(seite)
assert not seite.k_loeschen.isVisibleTo(seite) and not seite.k_wieder.isVisibleTo(seite)
assert seite.wiederherstellen().status == ak.NEU and seite.ordner == ak.NEU
assert seite.zaehler[ak.GELOESCHT].text().endswith("0")
ok("Seite: Zusammenführen und Löschen legen die Originale weg, Ordner „Gelöscht“, Wiederherstellen")
print("Alle Tests bestanden.")
