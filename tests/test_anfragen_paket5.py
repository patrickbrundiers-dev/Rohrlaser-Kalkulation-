"""Anfragenverwaltung, Paket 5 (Patrick 13.11.2026, „Alle fünf“): Ampel mit Antwortfrist in Arbeitstagen und
Vormessung auf der Seite Anfragen, Angebot per E-Mail legt die Anfrage nach Erledigt, fester Bearbeiter je Kunde,
„Keine Anfrage“ aussortieren (mit Vorschlag ab dem zweiten Mal), Auswertung. Nur erfundene Testmails.

Aufruf: python tests/test_anfragen_paket5.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime(2026, 11, 13, 10, 0)          # Freitag


def mail(name, betreff, adresse, wann, anhaenge=()):
    p = tmp / name
    p.write_bytes(mail_testdateien.eml(betreff, "Bitte anbieten.", "Test Kunde", adresse, wann, list(anhaenge)))
    return p


abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
# ------------------------------------------------------------------ Keine Anfrage
werbung = []
for i in range(3):
    m = mail(f"werbung{i}.eml", f"Sonderangebot {i}", "news@werbung.example", JETZT)
    a, _ = abl.anlegen(dict(quelle="ordner", betreff=f"Sonderangebot {i}", absender="News@Werbung.example",
                            eingang=JETZT), [m], f"w{i}")
    werbung.append(a)
assert ak.aussortier_vorschlag([abl.neu_lesen(x) for x in werbung], werbung[2]) == (0, "")
for a in werbung[:2]:
    a = abl.aussortieren(a, "Werbung")
    assert a.status == ak.ERLEDIGT and a.aussortiert == "Werbung" and a.stand["erledigt_von"] == "PB"
alle = abl.alle()
assert ak.aussortier_vorschlag(alle, abl.neu_lesen(werbung[2])) == (2, "Werbung")
z = ak.zaehlen(alle)
assert z[ak.AUSSORTIERT] == 2 and z[ak.ERLEDIGT] == 0 and z[ak.NEU] == 1, z
assert [a.nr for a in ak.filtern(alle, ak.AUSSORTIERT)] == [werbung[1].nr, werbung[0].nr] or \
    {a.nr for a in ak.filtern(alle, ak.AUSSORTIERT)} == {werbung[0].nr, werbung[1].nr}
assert not ak.filtern(alle, ak.ERLEDIGT)
try:
    abl.aussortieren(werbung[0], "Werbung")
    raise AssertionError("zweimal aussortiert")
except ak.AblageFehler:
    pass
w0 = abl.wieder_oeffnen(werbung[0])
assert w0.status == ak.NEU and not w0.aussortiert and w0.pfad.exists()
assert "Keine Anfrage: Werbung" in ak.verlauf_text(next(e for e in w0.verlauf if e["aktion"] == ak.AUSSORTIERT))
ok("Keine Anfrage: mit Grund nach „Keine Anfrage“ (nicht Erledigt), nichts gelöscht, wieder öffnen nach Neu; ab dem "
   "zweiten Mal vom selben Absender ein Vorschlag")

# ------------------------------------------------------------------ Ampel
alt_ein = JETZT - datetime.timedelta(days=7)
m = mail("alt.eml", "Anfrage Rahmen", "einkauf@rahmenbau.example", alt_ein, [("rahmen.step", b"ISO-10303-21; R")])
alt, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Rahmen", absender="einkauf@rahmenbau.example",
                          eingang=alt_ein, kundennr="K-1"), [m], "alt")
stufe, faellig, text = ak.ampel(alt, 2, jetzt=JETZT)
assert stufe == "rot" and "überfällig" in text, (stufe, text)
assert ak.ampel(abl.neu_lesen(werbung[2]), 2, jetzt=JETZT)[0] == "grün"
assert ak.ampel(alt, 0, jetzt=JETZT)[0] == "rot"                   # ohne Frist: alte 24-Stunden-Regel
assert ak.ampel(abl.neu_lesen(werbung[2]), 0, jetzt=JETZT) == (None, None, "")
ok("Ampel: Frist in Arbeitstagen ab Eingang (grün/gelb/rot), ohne Frist die 24-Stunden-Regel")

# ------------------------------------------------------------------ Angebot per E-Mail -> Erledigt
alt = abl.angebot_versendet(alt, "2026-00700", "einkauf@rahmenbau.example", jetzt=JETZT)
assert alt.status == ak.ERLEDIGT and alt.bearbeiter == "PB" and alt.stand["angebote"] == ["2026-00700"]
assert alt.stand["versendet"][0]["an"] == "einkauf@rahmenbau.example"
assert ak.ampel(alt, 2, jetzt=JETZT) == (None, None, "")
assert any("Angebot per E-Mail: 2026-00700 an einkauf@" in ak.verlauf_text(e) for e in alt.verlauf)
ok("Angebot per E-Mail: neue Anfrage wird übernommen, verknüpft, vermerkt und erledigt; keine Ampel mehr")

# ------------------------------------------------------------------ Zuständig je Kunde
m = mail("k2.eml", "Anfrage Konsole", "einkauf@konsolen.example", JETZT, [("k.step", b"ISO-10303-21; K")])
k2, _ = abl.anlegen(dict(quelle="outlook", betreff="Anfrage Konsole", kundennr="K-2", eingang=JETZT), [m], "k2")
m = mail("k3.eml", "Anfrage Halter", "einkauf@konsolen.example", JETZT, [("h.step", b"ISO-10303-21; H")])
k3, _ = abl.anlegen(dict(quelle="outlook", betreff="Anfrage Halter", kundennr="K-2", eingang=JETZT), [m], "k3")
abl.ereignis(k3, ak.ZUGEWIESEN, alt="AB", neu="", jetzt=JETZT)       # von Hand aufgehoben
kunden = [dict(kundennr="K-2", zustaendig="ab"), dict(kundennr="K-1", zustaendig="")]
abl2 = ak.OrdnerAblage(tmp / "akten", "CD", platz="BUERO2")
erg = abl.zustaendig_zuweisen(abl.alle(), kunden, jetzt=JETZT)
assert erg == [(k2.nr, "AB")], erg
assert abl2.zustaendig_zuweisen(abl2.alle(), kunden) == []           # zweiter Platz: schon erledigt
k2 = abl.neu_lesen(k2)
assert k2.stand["zugewiesen"] == "AB" and "zuständig für den Kunden" in ak.verlauf_text(k2.verlauf[-1])
assert abl.neu_lesen(k3).stand["zugewiesen"] == ""
ok("Fester Bearbeiter je Kunde (Kundenstamm Zuständig): neue Anfrage gleich zugewiesen, nur ein Platz, von Hand "
   "aufgehoben bleibt aufgehoben")

# ------------------------------------------------------------------ Vormessung (Ablage)
assert abl.vormessung_nehmen(k2, "abc") and not abl2.vormessung_nehmen(abl2.lesen(k2.nr), "abc")
k2 = abl.vormessung_merken(k2, "2 Teile · Richtpreis ca. 120 €", "abc")
assert abl2.lesen(k2.nr).stand["vormessung"] == "2 Teile · Richtpreis ca. 120 €"
n = len(k2.verlauf)
assert len(abl.vormessung_merken(k2, "2 Teile · Richtpreis ca. 120 €", "abc").verlauf) == n     # nur einmal
ok("Vormessung: ein Platz misst (Sperre je Dateistand), Ergebnis im Verlauf für alle")

# ------------------------------------------------------------------ Auswertung
vorgaenge = {"2026-00700": "Beauftragt"}
w = ak.auswertung(abl.alle(), vorgaenge, jetzt=JETZT)
assert len(w["wochen"]) >= 12 and sum(x[1] for x in w["wochen"]) == 6, w["wochen"]
assert sum(x[3] for x in w["wochen"]) == 1 and w["aussortiert"] == 1     # eine wieder geöffnet
assert w["treffer"] == (1, 1) and abs(w["std_bis_angebot"] - 7 * 24) < 0.01, w
pb = w["mitarbeiter"]["PB"]
assert pb["angebote"] == 1 and pb["beauftragt"] == 1 and abs(pb["std_bis_angebot"] - 168) < 0.01
assert ak.quote_text(1, 2) == "50 %" and ak.quote_text(0, 0) == "–"
ok("Auswertung: je Woche (Eingänge, mit Angebot, keine Anfrage), Ø bis Angebot, je Mitarbeiter, Trefferquote")

# ------------------------------------------------------------------ Seite
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.neu("kunden", dict(kundennr="K-9", name="Gestellbau Probe", zustaendig="PB", email="einkauf@gestell.example"))
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
seite.vormess_auftrag = dict(messen=lambda job, anf: [dict(fehler="nicht lesbar")])
abl3 = seite.ablage()
heute = datetime.datetime.now().replace(microsecond=0)
mg = mail("gestell.eml", "Anfrage Gestell", "einkauf@gestell.example", heute - datetime.timedelta(days=9),
          [("gestell.step", b"ISO-10303-21; Gestell")])
g, _ = abl3.anlegen(dict(quelle="outlook", betreff="Anfrage Gestell", absender="einkauf@gestell.example",
                         kundennr="K-9", eingang=heute - datetime.timedelta(days=9)), [mg], "g1")
for i in range(3):
    mw = mail(f"news{i}.eml", f"Newsletter {i}", "news@werbung.example", heute)
    abl3.anlegen(dict(quelle="outlook", betreff=f"Newsletter {i}", absender="news@werbung.example",
                      eingang=heute), [mw], f"n{i}")
seite.neu_laden()
assert seite._vm_lauf is not None
seite._vormessung_pruefen(warten=True)
g = abl3.neu_lesen(g)
assert g.stand["zugewiesen"] == "PB" and "nicht lesbar" in g.stand["vormessung"], g.stand
assert seite.ampeln[g.nr][0] == "rot"
zeile = next(r for r in range(seite.tabelle.rowCount()) if seite.tabelle.item(r, 0).text() == g.nr)
assert "überfällig" in seite.tabelle.item(zeile, 7).text()
assert "Vormessung" in seite.tabelle.item(zeile, 2).toolTip()
seite.waehlen(g.nr)
assert "Vormessung:" in seite.inhalt.toPlainText() and "Antwort überfällig" in seite.kopf.text()
assert not seite.k_keine.isHidden()
ok("Seite: zuständiger Bearbeiter, Vormessung im Hintergrund, Ampel rot in der Liste und im Kopf")

news = [a for a in seite.akten if a.betreff.startswith("Newsletter")]
for a in news[:2]:
    seite.waehlen(a.nr)
    assert seite.aussortieren("Werbung") is not None
seite.waehlen(news[2].nr)
assert "Auch diese aussortieren" in seite.inhalt.toPlainText()
assert seite.zaehler[ak.AUSSORTIERT].text().endswith("2")
seite.ordner_waehlen(ak.AUSSORTIERT)
assert seite.tabelle.rowCount() == 2 and seite.tabelle.item(0, 7).text() == "Keine Anfrage: Werbung"
ok("Seite: Keine Anfrage … mit Grund, eigener Zähler, Vorschlag beim dritten Newsletter")

# Kalkulieren verknüpft auch eine Anfrage aus Outlook; Angebot per E-Mail legt sie nach Erledigt
seite.ordner_waehlen(ak.NEU)
seite.waehlen(g.nr)
importe = []


def step_importieren(self, dateien=None, *a, **kw):
    importe.append(dateien)
    return {}


AngebotSeite.step_importieren = step_importieren
s = seite.kalkulieren(kundennr="K-9")
assert s is not None
g = abl3.neu_lesen(g)
nummer = s.kopf.get("nummer")
assert g.status == ak.BEARBEITUNG and nummer in g.stand["angebote"], g.stand
assert ak.akten_zum_angebot(db, s.id) == [g.nr]
assert ak.anfrage_mail(db, s.id).name == "gestell.eml"
aufrufe = []


def outlook_ok(befehl):
    aufrufe.append(json.loads(Path(befehl[-1]).read_text(encoding="utf-8")))
    return subprocess.CompletedProcess(befehl, 0, "", "")


gesehen = {}


def bedienen(d):
    gesehen["an"], gesehen["betreff"], _t = d.mail()
    d.in_outlook()
    return d.result()


db.position_neu(s.id, dict(pos=10, artikel="G1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1450,
                           stueck=8, schneidweg=200, einstiche=2))
s.neu_laden()
s.f.datei_oeffnen = lambda p: None
MELD = []
_m = fenster.meldung
fenster.meldung = lambda t, *a, **k: (MELD.append(t), _m(t, *a, **k))
d = s.angebot_mail(dialog=bedienen, ausfuehren=outlook_ok)
assert d is not None, MELD
assert d.ergebnis == "outlook" and gesehen["an"] == "einkauf@gestell.example", gesehen
assert gesehen["betreff"] == "AW: Anfrage Gestell", gesehen
g = abl3.neu_lesen(g)
assert g.status == ak.ERLEDIGT and g.stand["versendet"][0]["angebot"] == nummer
assert "erledigt" in d.meldung
ok("Kalkulieren verknüpft auch Anfragen aus Outlook; Angebot per E-Mail antwortet auf die Anfrage-Mail und legt die "
   "Anfrage nach Erledigt")

d = seite.mitarbeiter_zeigen()
assert d.windowTitle() == "Auswertung der Anfragen" and d.tabelle.rowCount() >= 1 and d.wochen.rowCount() >= 12
assert "Trefferquote" in d.kennzahlen.text()
ok("Auswertung: Fenster mit Kennzahlen, je Woche und je Mitarbeiter")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
