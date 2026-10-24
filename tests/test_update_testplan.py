"""Testplan Online-Update (Absicherungsplan Phase 9): Fälle, die test_update*.py noch nicht abdeckt –
Update ohne Änderung, bösartige ZIP-Einträge (../, absolute Pfade, Laufwerk, UNC, doppelte Einträge), zu viele Einträge,
abgebrochener Download, fehlendes Paket (404), Daten/Angebote/Portabel.ini bleiben bei jedem Fehler unberührt.

Aufruf: python tests/test_update_testplan.py
"""
import hashlib
import io
import shutil
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import update  # noqa: E402

warnings.filterwarnings("ignore", "Duplicate name", UserWarning)
update.update_schluessel = lambda: {}      # unsignierte Testlisten; Signatur: tests/test_update_signatur.py


def ok(text):
    print("OK    ", text)


def fehler_erwartet(f, *a, text=None, **k):
    try:
        f(*a, **k)
    except update.UpdateFehler as e:
        assert text is None or text in str(e), e
        return e
    raise AssertionError(f"UpdateFehler erwartet: {f.__name__}{a}")


tmp = Path(tempfile.mkdtemp(prefix="update_testplan_"))
NUTZER = {"Daten/rohrlaser.db": b"DATEN", "Angebote/A-1.pdf": b"ANGEBOT", "Portabel.ini": b"[Portabel]"}


def programm(name, inhalt):
    o = tmp / name
    for rel, daten in {**inhalt, **NUTZER}.items():
        (o / rel).parent.mkdir(parents=True, exist_ok=True)
        (o / rel).write_bytes(daten)
    return o


def stand(o):
    return {p.relative_to(o).as_posix(): p.read_bytes() for p in sorted(o.rglob("*"))
            if p.is_file() and not p.relative_to(o).as_posix().startswith(update.ARBEITSORDNER + "/")}


def nutzer_unberuehrt(o):
    for rel, daten in NUTZER.items():
        assert (o / rel).read_bytes() == daten, rel


alt = {"Rohrlaser-Angebotskalkulation.exe": b"MZ-alt" * 100, "_internal/a.dll": b"a-alt" * 50}
neu = {"Rohrlaser-Angebotskalkulation.exe": b"MZ-neu" * 100, "_internal/a.dll": b"a-alt" * 50}

# Fall 3: Update ohne geänderte Dateien – nichts laden, nichts ändern
quelle_neu = tmp / "quelle_neu"
bau = tmp / "bau"
for rel, daten in neu.items():
    (bau / rel).parent.mkdir(parents=True, exist_ok=True)
    (bau / rel).write_bytes(daten)
liste = update.erstellen(bau, quelle_neu, 2)
q = str(quelle_neu / update.DATEILISTE)
gleich = programm("gleich", neu)
vorher = stand(gleich)
online, plan = update.aktualisieren(gleich, q)
assert plan is None and stand(gleich) == vorher and not (gleich / update.ARBEITSORDNER / "pakete").exists()
ok("Fall 3: Update ohne geänderte Dateien lädt nichts und ändert nichts")

# Fall 4 + 21: eine geänderte Datei, Nutzerdaten bleiben
eine = programm("eine", alt)
online, plan = update.aktualisieren(eine, q)
assert plan["neu"] == ["Rohrlaser-Angebotskalkulation.exe"]
assert (eine / "Rohrlaser-Angebotskalkulation.exe").read_bytes() == neu["Rohrlaser-Angebotskalkulation.exe"]
nutzer_unberuehrt(eine)
ok("Fall 4/21: nur die geänderte Datei ausgetauscht, Daten, Angebote, Portabel.ini unverändert")

# Fall 11/12: ZIP mit bösartigen Einträgen – benutzt werden nur Einträge, deren Name die erwartete Prüfsumme ist,
# geschrieben wird nur nach _update/neu/<sha256>; nichts landet außerhalb
inhalt = b"MZ-neu" * 100
sha = hashlib.sha256(inhalt).hexdigest()
boese = tmp / "boese_quelle"
boese.mkdir()
paket = "p-" + "c" * 40 + ".zip"
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as z:
    for name in ("../../ausbruch.txt", "/etc/ausbruch", "C:/Windows/ausbruch.dll", "//server/freigabe/x",
                 "..\\..\\ausbruch2.txt", "Daten/rohrlaser.db"):
        z.writestr(name, b"BOESE")
    z.writestr(sha, inhalt)                                   # doppelter Eintrag: zuerst richtig …
    z.writestr(sha, b"untergeschoben")                       # … dann falsch (zipfile nimmt den letzten)
(boese / paket).write_bytes(puffer.getvalue())
(boese / update.DATEILISTE).write_text("{}", encoding="utf-8")
o = dict(format=1, stand=3, dateien={"Rohrlaser-Angebotskalkulation.exe": dict(sha256=sha, groesse=len(inhalt),
                                                                             paket=paket)},
         pakete={paket: dict(groesse=len(puffer.getvalue()), sha256=update.pruefsumme(boese / paket))})
update.liste_pruefen(o)
ziel = programm("zip_boese", alt)
fehler_erwartet(update.laden, ziel, str(boese / update.DATEILISTE), o, update.planen(ziel, o))   # Größe passt nicht
update.verwerfen(ziel)
assert not any(p.name.startswith("ausbruch") for p in tmp.rglob("*")), "Eintrag außerhalb geschrieben"
nutzer_unberuehrt(ziel)
# nur der passende Eintrag (letzter gleichen Namens, Größe und Prüfsumme stimmen) wird verwendet
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as z:
    for name in ("../../ausbruch.txt", "/etc/ausbruch", "C:/Windows/ausbruch.dll", "Daten/rohrlaser.db"):
        z.writestr(name, b"BOESE")
    z.writestr(sha, inhalt)
(boese / paket).write_bytes(puffer.getvalue())
o["pakete"][paket] = dict(groesse=len(puffer.getvalue()), sha256=update.pruefsumme(boese / paket))
plan = update.planen(ziel, o)
neu_ordner = update.laden(ziel, str(boese / update.DATEILISTE), o, plan)
assert sorted(p.name for p in neu_ordner.iterdir()) == [sha]
update.einspielen(ziel, o, plan, neu_ordner)
assert (ziel / "Rohrlaser-Angebotskalkulation.exe").read_bytes() == inhalt
assert not any(p.name.startswith("ausbruch") for p in tmp.rglob("*"))
nutzer_unberuehrt(ziel)
ok("Fall 11/12: ../, absolute, Laufwerks- und UNC-Einträge und Daten/ im ZIP ignoriert, doppelter Eintrag geprüft")

# Fall 11 (Dateiliste): dieselben Pfade als Ziel in der Liste werden vorher abgelehnt
for rel in ("../ausbruch.txt", "/etc/x", "C:/x.dll", "//server/x", "Daten/rohrlaser.db", "portabel.ini"):
    falsch = dict(o, dateien={rel: o["dateien"]["Rohrlaser-Angebotskalkulation.exe"]})
    fehler_erwartet(update.liste_pruefen, falsch, text="ungültigen Eintrag")
ok("Fall 11: Zielpfade ../, absolut, Laufwerk, UNC, Daten, Portabel.ini in der Dateiliste abgelehnt")

# Fall 13: zu viele Einträge in der Dateiliste
viele = dict(o, dateien={f"x/{i}.dll": o["dateien"]["Rohrlaser-Angebotskalkulation.exe"]
                         for i in range(update.DATEIEN_MAX + 1)})
fehler_erwartet(update.liste_pruefen, viele, text="unplausibel")
ok("Fall 13: Dateiliste mit zu vielen Einträgen abgelehnt")

# Fall 14: abgebrochener Download – Programm unverändert, neuer Versuch klappt
abbruch = programm("abbruch", alt)
vorher = stand(abbruch)


def abbrechen(_n):
    raise update.Abbruch("Benutzer hat abgebrochen")


fehler_erwartet(update.aktualisieren, abbruch, q, fortschritt=abbrechen)
assert stand(abbruch) == vorher
update.verwerfen(abbruch)
online, plan = update.aktualisieren(abbruch, q)
assert plan and (abbruch / "Rohrlaser-Angebotskalkulation.exe").read_bytes() == neu["Rohrlaser-Angebotskalkulation.exe"]
nutzer_unberuehrt(abbruch)
ok("Fall 14: abgebrochener Download ändert nichts, der nächste Versuch spielt das Update ein")

# Fall 15: Paket fehlt (404) bzw. Dateiliste fehlt – klare Meldung, Programm unverändert
fehlt = tmp / "quelle_fehlt"
shutil.copytree(quelle_neu, fehlt)
for p in fehlt.glob("*.zip"):
    p.unlink()
kaputt = programm("paket_fehlt", alt)
vorher = stand(kaputt)
e = fehler_erwartet(update.aktualisieren, kaputt, str(fehlt / update.DATEILISTE), text="lässt sich nicht laden")
assert stand(kaputt) == vorher and not (kaputt / update.ARBEITSORDNER / "neu").exists()
fehler_erwartet(update.online_liste, str(tmp / "gibt_es_nicht" / update.DATEILISTE), text="lässt sich nicht laden")
ok("Fall 15: fehlendes Paket oder fehlende Dateiliste: verständliche Meldung, Programm unverändert")

# Fall 20: Fehler beim Austausch (Datei lässt sich nicht ersetzen) – alter Stand automatisch zurück
rueck = programm("rueckfall", alt)
vorher = stand(rueck)
online = update.online_liste(q)
plan = update.planen(rueck, online)
neu_ordner = update.laden(rueck, q, online, plan)
echt = shutil.copyfile


def kaputt_kopieren(von, nach):
    raise OSError(28, "Kein Speicherplatz mehr")


shutil.copyfile = kaputt_kopieren
try:
    try:
        update.einspielen(rueck, online, plan, neu_ordner)
        raise AssertionError("Fehler erwartet")
    except (OSError, update.UpdateFehler):
        pass
finally:
    shutil.copyfile = echt
update.aufraeumen(rueck)
assert stand(rueck) == vorher, "alter Stand nicht wiederhergestellt"
ok("Fall 20: Fehler mitten im Austausch (Platte voll): alter Stand zurückgestellt, Daten unberührt")
print("Testplan Online-Update: alle Fälle bestanden.")
