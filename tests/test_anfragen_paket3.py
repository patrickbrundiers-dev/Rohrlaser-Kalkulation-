"""Anfragenverwaltung, Paket 3 (Patrick 13.11.2026): Virenprüfung der Anhänge mit dem Windows-Virenschutz,
Antworten des Kunden landen in der vorhandenen Anfrage (Outlook und Anfrage-Ordner), Erinnerung an Anfragen, die
länger als 24 Stunden neu sind. Der Virenschutz und Outlook sind nachgebaut; nur erfundene Testmails.

Aufruf: python tests/test_anfragen_paket3.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from outlook_nachbau import Outlook  # noqa: E402
from rohrlaser import anfragen  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402
from rohrlaser import virenpruefung as vp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


VIRUS = b"X5O!P%@AP-TEST-VIRUS"          # erfundene Kennung, der Nachbau meldet sie als Fund
EXE = Path("C:/Programme/Windows Defender/MpCmdRun.exe")


class Defender:
    """Nachbau von MpCmdRun.exe: 2 = Fund (Datei oder Ordner enthält VIRUS), 0 = sauber."""

    def __init__(self):
        self.aufrufe = []

    def __call__(self, befehl):
        assert befehl[0] == str(EXE) and befehl[1:5] == ["-Scan", "-ScanType", "3", "-File"]
        assert "-DisableRemediation" in befehl
        p = Path(befehl[5])
        self.aufrufe.append(p)
        dateien = [p] if p.is_file() else [x for x in p.rglob("*") if x.is_file()]
        fund = any(VIRUS in x.read_bytes() for x in dateien if not x.name.endswith(".gesperrt"))
        return SimpleNamespace(returncode=2 if fund else 0, stdout="", stderr="")


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)

# ------------------------------------------------------------------ Virenprüfung
d = tmp / "pruef"
d.mkdir()
(d / "a.pdf").write_bytes(b"%PDF sauber")
(d / "b.step").write_bytes(b"ISO-10303-21; sauber")
fake = Defender()
erg = vp.pruefen([d / "a.pdf", d / "b.step"], exe=EXE, ausfuehren=fake)
assert set(erg.values()) == {vp.SAUBER} and fake.aufrufe == [d]              # ein Lauf für alle
(d / "c.pdf").write_bytes(b"%PDF " + VIRUS)
erg = vp.pruefen([d / "a.pdf", d / "b.step", d / "c.pdf"], exe=EXE, ausfuehren=fake)
assert erg == {d / "a.pdf": vp.SAUBER, d / "b.step": vp.SAUBER, d / "c.pdf": vp.FUND}, erg
assert vp.pruefen([d / "a.pdf"], exe=EXE, ausfuehren=lambda b: SimpleNamespace(returncode=5)) == \
    {d / "a.pdf": vp.UNGEPRUEFT}
if sys.platform != "win32":
    assert vp.programm() is None and vp.pruefen([d / "a.pdf"]) == {d / "a.pdf": vp.UNGEPRUEFT}
ok("Virenschutz: alle Dateien in einem Lauf, nur bei einem Fund einzeln; Fehler oder kein Defender = nicht geprüft")

abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
m = tmp / "mail_virus.eml"
m.write_bytes(mail_testdateien.eml("Anfrage Gestell", "Bitte anbieten.", "Max Muster", "max@muster-metall.example",
                                   datetime.datetime(2026, 11, 13, 7, 0),
                                   [("gestell.step", b"ISO-10303-21; Gestell"), ("rechnung.pdf", b"%PDF " + VIRUS)]))
a, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Gestell", absender="max@muster-metall.example"), [m], "v1")
assert len(a.ungeprueft()) == 3 and not abl.viren_pruefen(a)          # ohne Virenschutz: nichts
werte = abl.viren_pruefen(a, exe=EXE, ausfuehren=fake)
assert werte == {"mail_virus.eml": vp.FUND, "Anhaenge/gestell.step": vp.SAUBER, "Anhaenge/rechnung.pdf": vp.FUND} \
    or werte["Anhaenge/rechnung.pdf"] == vp.FUND, werte
a = abl.neu_lesen(a)
r = next(x for x in a.dateien() if x["name"] == "rechnung.pdf")
assert r["gesperrt"] and r["warnung"] == "Virus gefunden: gesperrt" and not r["pfad"].exists()
assert r["pfad"].with_name("rechnung.pdf.gesperrt").exists()                 # nichts gelöscht
assert a.virus() and not a.ungeprueft() and not abl.viren_pruefen(a, exe=EXE, ausfuehren=fake)
try:
    ak.arbeitskopie(a)
    raise AssertionError("Kalkulieren trotz Virus")
except ak.AblageFehler:
    pass
assert any("Virus in" in ak.verlauf_text(e) and "rechnung.pdf" in ak.verlauf_text(e) for e in a.verlauf)
ok("Akte: Fund wird gesperrt (Endung .gesperrt, nichts gelöscht), Warnung, Verlauf, Kalkulieren gesperrt")

# ------------------------------------------------------------------ Antworten des Kunden erkennen
b, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Halter 2026-77", absender="max@muster-metall.example",
                        eingang=JETZT - datetime.timedelta(days=3), konversation="KONV-1"), [], "h1")
alle = abl.alle()
assert ak.betreff_kern("AW: WG: RE[2]:  Anfrage   Halter 2026-77") == "anfrage halter 2026-77"
assert ak.antwort_zu(alle, "AW: Anfrage Halter 2026-77", "einkauf@muster-metall.example").nr == b.nr
assert ak.antwort_zu(alle, "Anfrage Halter 2026-77", "max@muster-metall.example") is None      # kein AW:
assert ak.antwort_zu(alle, "AW: Anfrage Halter 2026-77", "max@andere-firma.example") is None   # andere Firma
assert ak.antwort_zu(alle, "Neue Zeichnung", "x@y.example", konversation="KONV-1").nr == b.nr
assert ak.antwort_zu(alle, "AW: Anfrage Halter 2026-77", "max@muster-metall.example",
                     jetzt=JETZT + datetime.timedelta(days=ak.ANTWORT_TAGE + 5)) is None
ok("Antwort erkannt über Outlook-Konversation oder AW:/RE: mit gleichem Betreff und gleicher Firma (120 Tage)")

# Anfrage-Ordner: Antwort mit neuer STEP kommt in die Akte, Original weg aus dem Ordner
inbox = tmp / "Eingang"
inbox.mkdir()
alt = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
m1 = inbox / "Anfrage Rahmen.eml"
m1.write_bytes(mail_testdateien.eml("Anfrage Rahmen 40x40", "Bitte 10 Rahmen.", "Erika Beispiel",
                                    "erika@beispiel-bau.example", datetime.datetime(2026, 11, 12, 9, 0),
                                    [("rahmen.step", b"ISO-10303-21; Rahmen")]))
os.utime(m1, (alt, alt))
abl2 = ak.OrdnerAblage(tmp / "akten2", "PB")
rahmen = next(iter(ak.aus_ordner(abl2, anfragen.suchen(inbox), inbox=inbox).values()))
rahmen = abl2.uebernehmen(rahmen)
ak.eingang_ablegen(anfragen.suchen(inbox)[0], inbox, rahmen.nr)
sub = inbox / "Antwort Erika"
sub.mkdir()
m2 = sub / "AW Anfrage Rahmen.eml"
m2.write_bytes(mail_testdateien.eml("AW: Anfrage Rahmen 40x40", "Anbei die geänderte Zeichnung.", "Erika Beispiel",
                                    "erika@beispiel-bau.example", datetime.datetime(2026, 11, 13, 8, 0),
                                    [("rahmen_v2.step", b"ISO-10303-21; Rahmen V2")]))
os.utime(m2, (alt, alt))
liste = anfragen.suchen(inbox)
assert len(liste) == 1
erf = ak.aus_ordner(abl2, liste, inbox=inbox)
assert len(abl2.alle()) == 1 and next(iter(erf.values())).nr == rahmen.nr
rahmen = abl2.neu_lesen(rahmen)
assert rahmen.status == ak.BEARBEITUNG and rahmen.stand["antworten"] == 1
namen = {x["name"] for x in rahmen.dateien()}
assert {"AW Anfrage Rahmen.eml", "rahmen_v2.step"} <= namen, namen
assert not m2.exists() and (inbox / ".uebernommen" / rahmen.nr / "AW Anfrage Rahmen.eml").exists()
assert any(ak.verlauf_text(e).split("  ")[-1].startswith("Antwort des Kunden") for e in rahmen.verlauf)
assert not anfragen.suchen(inbox)
ok("Anfrage-Ordner: Antwort des Kunden (AW: mit neuer STEP) kommt in die vorhandene Anfrage, keine neue, "
   "Original weggelegt")

# Outlook: Antwort in derselben Konversation
abl3 = ak.OrdnerAblage(tmp / "akten3", "PB", platz="BUERO1")
ou = Outlook()
ou.mail("<k1@kunde.example>", "Anfrage Konsole", "Bitte 50 Konsolen.", "kauf@kunde.example", konversation="K-77")
ol.abrufen(abl3, ausfuehren=ou, jetzt=JETZT)
konsole = abl3.alle()[0]
assert konsole.kopf["konversation"] == "K-77"
konsole = abl3.uebernehmen(konsole)
ol.abrufen(abl3, ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<k1@kunde.example>") == "In Bearbeitung"
ou.mail("<k2@kunde.example>", "AW: Anfrage Konsole", "Werkstoff bitte 1.4301.", "kauf@kunde.example",
        konversation="K-77", anhaenge=[("konsole_v2.step", b"ISO-10303-21; Konsole V2")])
erg = ol.abrufen(abl3, ausfuehren=ou, jetzt=JETZT)
assert not erg["neu"] and [x.nr for x in erg["antworten"]] == [konsole.nr] and len(abl3.alle()) == 1, erg
konsole = abl3.neu_lesen(konsole)
assert konsole.status == ak.BEARBEITUNG and konsole.stand["mids"] == ["<k2@kunde.example>"]
assert "konsole_v2.step" in {x["name"] for x in konsole.dateien()}
erg = ol.abrufen(abl3, ausfuehren=ou, jetzt=JETZT)                  # Antwort wandert zur Akte, ändert sie nicht
assert ou.wo("<k2@kunde.example>") == "In Bearbeitung" and abl3.neu_lesen(konsole).status == ak.BEARBEITUNG
assert not erg["gefolgt"] and len(abl3.alle()) == 1
abl3.erledigen(abl3.neu_lesen(konsole))
ol.abrufen(abl3, ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<k1@kunde.example>") == "Erledigt" and ou.wo("<k2@kunde.example>") == "Erledigt"
ok("Outlook: Antwort in derselben Konversation kommt in die Anfrage, die Mail wandert mit ihr (In Bearbeitung, "
   "Erledigt), ohne den Status zu ändern")

# ------------------------------------------------------------------ Seite: Hintergrundprüfung, Meldungen, Erinnerung
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
seite.viren_exe, seite.viren_ausfuehren = EXE, Defender()
abl4 = seite.ablage()
mv = tmp / "Anfrage Winkel.eml"
mv.write_bytes(mail_testdateien.eml("Anfrage Winkel", "Bitte 5 Winkel.", "Jan Probe", "jan@probe-anlagen.example",
                                    JETZT - datetime.timedelta(hours=30), [("winkel.step", b"ISO-10303-21; Winkel"),
                                                                           ("info.pdf", b"%PDF " + VIRUS)]))
w, _ = abl4.anlegen(dict(quelle="ordner", betreff="Anfrage Winkel", absender="jan@probe-anlagen.example",
                         eingang=JETZT - datetime.timedelta(hours=30)), [mv], "w1")
seite.neu_laden()
if getattr(seite, "_vp_lauf", None) is not None:
    seite._vp_lauf.result()
    seite._viren_pruefen()
w = abl4.neu_lesen(w)
assert w.virus() and not w.ungeprueft()
assert any("Virus" in t for t, _x, _n in getattr(fenster, "windows_meldungen", [])), fenster.__dict__.get(
    "windows_meldungen")
seite.waehlen(w.nr)
text = seite.inhalt.toPlainText()
assert "Virus gefunden: gesperrt" in text and "✓ geprüft" in text, text
assert seite.kalkulieren(kundennr="10417") is None and w.status == ak.NEU            # gesperrt, nicht übernommen
ok("Seite: Prüfung im Hintergrund, Fund mit Windows-Meldung und rot in der Anhangliste, Kalkulieren gesperrt")

# Antwort des Kunden meldet sich
n_vorher = len(fenster.__dict__.get("windows_meldungen", []))
abl4.dateien_dazu(w, [tmp / "pruef" / "a.pdf"], antwort=True)
seite.neu_laden()
meld = fenster.windows_meldungen[n_vorher:]
assert any(t == "Antwort des Kunden" and w.nr in x for t, x, _n in meld), meld

# Erinnerung einmal am Tag ab 7 Uhr
morgen7 = datetime.datetime.combine(JETZT.date(), datetime.time(7, 5))
db.einstellung_setzen("anfragen_erinnert", "")
assert seite._erinnern(morgen7.replace(hour=6)) == ""
t = seite._erinnern(morgen7)
assert t == "1 Anfrage wartet seit über 24 Stunden", t
assert seite._erinnern(morgen7.replace(hour=15)) == ""                       # heute schon erinnert
assert seite._erinnern(morgen7 + datetime.timedelta(days=1)).startswith("1 Anfrage wartet")
zeile = next(r for r in range(seite.tabelle.rowCount()) if seite.tabelle.item(r, 0).text() == w.nr)
assert seite.tabelle.item(zeile, 7).text().endswith("· wartet")
ok("Antwort des Kunden mit Windows-Meldung; Erinnerung an Anfragen, die über 24 Stunden neu sind: einmal am Tag "
   "ab 7 Uhr, in der Liste rot")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
