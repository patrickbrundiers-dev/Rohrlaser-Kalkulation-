"""Prüft den gemeinsamen Angebotsnummernkreis (nummern.py, Patrick 23.10.2026, Freigabe 1a 2c 3a 4a 5a): Format
2026-00001 ohne Kürzel, Reservierung im gemeinsamen Ordner (zwei Arbeitsplätze gleichzeitig: keine Nummer doppelt),
Zähler läuft über den Jahreswechsel weiter, gelöschte Nummern werden nicht wieder vergeben, vorläufige Nummer ohne
erreichbaren Ordner und endgültige beim Abgleich, alte Nummern bleiben, ohne Ordner lokal im gleichen Format,
doppelte Nummer beim Abgleich gemeldet, Angebots-PDF erst mit endgültiger Nummer.

Aufruf: python tests/test_nummern.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import nummern, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(k, ordner=gemeinsam):
    db = Datenbank(tmp / k / "rohrlaser.db")
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(ordner))
    return db


# ---------------------------------------------------------------- Format und Zähler
assert nummern.zaehler("2026-00042") == 42 and nummern.zaehler("2027-123456") == 123456
assert nummern.zaehler("PB-2026-0007") == 0 and nummern.zaehler("A-2026-0001") == 0 and nummern.zaehler(None) == 0
assert nummern.nummer("2026", 7) == "2026-00007"
assert nummern.vorlaeufig("V-PB-3") and not nummern.vorlaeufig("2026-00003")
ok("Format Jahr-Zähler 2026-00001; alte Nummern mit Kürzel und A-… zählen nicht mit")

# ---------------------------------------------------------------- zwei Arbeitsplätze, ein Nummernkreis
pb, mk = arbeitsplatz("PB"), arbeitsplatz("MK")
pb.einstellung_setzen("letzte_angebotsnummer", "PB-2026-0012")      # alte Nummer mit Kürzel: neuer Kreis beginnt bei 1
alt = pb.angebot_neu(dict(nummer="PB-2026-0012", kunde="alt"))
n = [pb.angebot(pb.angebot_neu(dict(datum="2026-10-23")))["nummer"],
     mk.angebot(mk.angebot_neu(dict(datum="2026-10-23")))["nummer"],
     pb.angebot(pb.angebot_neu(dict(datum="2026-10-23")))["nummer"]]
assert n == ["2026-00001", "2026-00002", "2026-00003"], n
assert pb.angebot(alt)["nummer"] == "PB-2026-0012"
assert sorted(p.name for p in (gemeinsam / nummern.ORDNER).iterdir()) == ["00001.nummer", "00002.nummer", "00003.nummer"]
assert (gemeinsam / nummern.ORDNER / "00002.nummer").read_text(encoding="utf-8").splitlines()[:2] == ["2026-00002", "MK"]
ok("PB und MK zählen gemeinsam (2026-00001, -00002, -00003), Reservierung je Nummer im Ordner Nummern, "
   "alte Nummer PB-2026-0012 bleibt")

# gleichzeitig: 4 Arbeitsplätze legen je 25 Nummern an (eigene Datenbank je Thread, wie an getrennten PCs)
ergebnis, fehler = [], []


def anlegen(k):
    try:
        db = arbeitsplatz(k)
        for _ in range(25):
            ergebnis.append(nummern.reservieren(db, "2026"))
    except Exception as e:     # noqa: BLE001
        fehler.append(e)


threads = [threading.Thread(target=anlegen, args=(k,)) for k in ("AA", "BB", "CC", "DD")]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert not fehler, fehler
assert len(ergebnis) == 100 and len(set(ergebnis)) == 100, "keine Nummer doppelt"
assert sorted(nummern.zaehler(x) for x in ergebnis) == list(range(4, 104))
ok("4 Arbeitsplätze gleichzeitig je 25 Nummern: 100 verschiedene, lückenlos 2026-00004 … 2026-00103")

# ---------------------------------------------------------------- Jahreswechsel, Löschen
a = pb.angebot_neu(dict(datum="2027-01-02"))
assert pb.angebot(a)["nummer"] == "2027-00104", pb.angebot(a)["nummer"]
pb.angebot_loeschen(a)
b = mk.angebot_neu(dict(datum="2027-01-02"))
assert mk.angebot(b)["nummer"] == "2027-00105"
ok("Jahreswechsel: Zähler läuft weiter (2027-00104); gelöschte Nummer wird nicht wieder vergeben")

# ---------------------------------------------------------------- Ordner nicht erreichbar: vorläufig
weg = tmp / "Netz" / "Gemeinsam"
pb.einstellung_setzen("teilen_ordner", str(weg))
v1, v2 = pb.angebot_neu(dict(datum="2027-01-03")), pb.angebot_neu(dict(datum="2027-01-03"))
assert pb.angebot(v1)["nummer"] == "V-PB-1" and pb.angebot(v2)["nummer"] == "V-PB-2"
assert pb.einstellung("letzte_angebotsnummer") == "2027-00104", "vorläufige Nummer zählt nicht als vergeben"
try:
    nummern.endgueltig(pb)
    raise AssertionError("ohne Ordner endgültig vergeben")
except OSError:
    pass
pb.einstellung_setzen("teilen_ordner", str(gemeinsam))
mk.angebot_neu(dict(datum="2027-01-03"))                       # Kollege war inzwischen dran: 2027-00106
umn = nummern.endgueltig(pb)
assert umn == [("V-PB-1", "2027-00107"), ("V-PB-2", "2027-00108")], umn
assert pb.angebot(v1)["nummer"] == "2027-00107" and pb.einstellung("letzte_angebotsnummer") == "2027-00108"
ok("Ordner nicht erreichbar: vorläufige Nummern V-PB-1, V-PB-2; beim Abgleich endgültig (2027-00107, -00108)")

pb.einstellung_setzen("teilen_ordner", str(weg))
v3 = pb.angebot_neu(dict(datum="2027-01-04"))
assert pb.angebot(v3)["nummer"] == "V-PB-1"
pb.einstellung_setzen("teilen_ordner", str(gemeinsam))
teilen.lesen(pb, teilen.UEBERNEHMEN)
teilen.schreiben(pb)
assert nummern.zaehler(pb.angebot(v3)["nummer"]) == 109
ok("Schreiben in den gemeinsamen Ordner vergibt vorläufige Nummern vorher endgültig")

# ---------------------------------------------------------------- ohne gemeinsamen Ordner: lokal
lokal = Datenbank(tmp / "lokal" / "rohrlaser.db")
lokal.einstellung_setzen("letzte_angebotsnummer", "A-2026-0099")
x = [lokal.angebot(lokal.angebot_neu(dict(datum="2026-11-02")))["nummer"] for _ in range(2)]
assert x == ["2026-00001", "2026-00002"], x
lokal.einstellung_setzen("letzte_angebotsnummer", "2026-00500")       # Startwert von Hand
assert lokal.angebot(lokal.angebot_neu(dict(datum="2027-01-02")))["nummer"] == "2027-00501"
ok("ohne gemeinsamen Ordner: gleiches Format lokal (2026-00001), Startwert über 'Letzte Angebotsnummer'")

# ---------------------------------------------------------------- doppelte Nummer beim Abgleich gemeldet
mk.angebot_neu(dict(nummer="2026-09999", kunde="von Hand"))
pb.angebot_neu(dict(nummer="2026-09999", kunde="auch von Hand"))
teilen.lesen(mk, teilen.UEBERNEHMEN)
teilen.schreiben(mk)
b = teilen.lesen(pb)
assert any("2026-09999" in h and "doppelte" in h for h in b["hinweise"]), b["hinweise"]
ok("von Hand doppelt vergebene Nummer: Hinweis beim Abgleich")

# ---------------------------------------------------------------- Oberfläche: Titel und Angebots-PDF
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import teilen_fenster  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
f = Hauptfenster(pb, tmp, stumm=True)
pb.einstellung_setzen("teilen_ordner", str(weg))
v = pb.angebot_neu(dict(kunde="unterwegs"))
seite = f.angebot_oeffnen(v)
assert seite.titel().endswith("(vorläufige Nummer)"), seite.titel()
assert seite.nummer_endgueltig("Angebots-PDF") is False and seite.angebot_pdf() is None
assert "endgültiger Angebotsnummer" in f.statusBar().currentMessage()
pb.einstellung_setzen("teilen_ordner", str(gemeinsam))
assert seite.nummer_endgueltig("Angebots-PDF") is True
assert not nummern.vorlaeufig(seite.kopf["nummer"]) and "vorläufig" not in seite.titel()
w = pb.angebot_neu(dict(kunde="unterwegs 2", nummer="V-PB-7"))
b = teilen_fenster.abgleichen(f)
assert b and b["nummern"] and b["nummern"][0][0] == "V-PB-7" and "endgültige Nummer" in teilen.bericht_text(b)
assert not nummern.vorlaeufig(pb.angebot(w)["nummer"])
ok("Oberfläche: Titel '(vorläufige Nummer)', Angebots-PDF erst mit endgültiger Nummer, Abgleich meldet neue Nummer")
print("OK: gemeinsamer Angebotsnummernkreis")
