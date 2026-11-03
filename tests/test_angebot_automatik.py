"""Prüft die Automationen bei der Angebotserstellung (Paket D, 03.11.2026, Freigabe Patrick „Auch mit einbauen“):
E1 Fertigstellen in einem Zug, E2 nächste Anfrage, E3 günstigste Maschine mit Rückgängig, E5 aus Nacharbeit lernen,
E6 Beistellung und Oberfläche aus der Mail, E7 Anfragen automatisch zuweisen, E8 Rückfrage vorbereiten.

Aufruf: python tests/test_angebot_automatik.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
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

import beispiel_angebot  # noqa: E402
from rohrlaser import anfragen, angebot_automatik as aa, automatik, importprofil, kundenvorgabe, nacharbeit  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import KUNDENMATERIAL  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ E6 Texte
assert aa.beistellung("Hallo,\ndas Material wird beigestellt.\nGruß")
assert aa.beistellung("Rohre kommen von uns (Kundenmaterial).")
assert not aa.beistellung("Bitte mit Material anbieten, keine Beistellung.")
assert not aa.beistellung("Bitte Angebot für 20 Stück.")
assert aa.oberflaeche("Oberfläche: gebeizt und passiviert", ["roh", "gebeizt", "K320"]) == "gebeizt"
assert aa.oberflaeche("Rohre roh, Schliff K320 oder gebeizt", ["roh", "gebeizt", "K320"]) is None    # zwei: unklar
assert aa.oberflaeche("unbehandelt", ["roh", "gebeizt"]) is None
ok("E6: Beistellung erkannt (nicht bei „keine Beistellung“), Oberfläche nur eindeutig, „roh“ zählt nicht")

# ------------------------------------------------------------------ E7 Zuweisung


class A:
    def __init__(self, name, kunde=None, an=None, gesperrt=None):
        self.name, self.kunde, self.gesperrt = name, kunde, gesperrt
        self.zugewiesen = dict(an=an) if an else {}


liste = [A("a", "K-1"), A("b", "K-2"), A("c"), A("d", an="MK"), A("e", gesperrt="PB")]
v = {a.name: an for a, an in anfragen.zuweisung_vorschlag(liste, [dict(kundennr="K-1", zustaendig="mk")],
                                                            {"MK": "Max", "SB": "Sabine"}, "PB")}
assert v == {"a": "MK", "b": "PB", "c": "SB"}, v
assert anfragen.zuweisung_vorschlag(liste, [], {}, "") == []
ok("E7: Zuständiger aus dem Kundenstamm, sonst wer am wenigsten offen hat; zugewiesene und gesperrte bleiben")

# ------------------------------------------------------------------ Datenbank, Angebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert "zustaendig" in {r[1] for r in db.con.execute("PRAGMA table_info(kunden)")}
fenster = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db, dict(kundennr="K-1001", kunde="Beispiel Metallbau GmbH"))
seite = fenster.angebot_oeffnen(aid)

# ------------------------------------------------------------------ E6/E3/E8 nach dem Import
out = aa.nach_import(seite, "Hallo,\nMaterial wird beigestellt. Oberfläche gebeizt.\nGruß")
laser = [p for p in db.positionen(aid) if p.get("profil_id")]
assert all(p["material_herkunft"] == KUNDENMATERIAL for p in laser)
assert all(p["oberflaeche"] == "gebeizt" for p in laser)
assert any("beigestellt" in t for t in out["texte"]) and any("gebeizt" in t for t in out["texte"]), out
assert db.angebot(aid).get("ergebnis"), "optimiert"
eintraege = [e for e in automatik.liste(db) if e["art"] == "angebot_auto"]
assert len(eintraege) >= 2
e = next(x for x in eintraege if "Material = Kunde" in x["text"])
automatik.rueckgaengig(db, e["id"])
assert all(p["material_herkunft"] != KUNDENMATERIAL for p in db.positionen(aid) if p.get("profil_id"))
ok(f"Nach dem Import: {'; '.join(out['texte'])} – Material zurücknehmbar (Protokoll)")

# E3 mit erzwungen günstigerer Maschine: Rückgängig stellt die alte wieder ein
from rohrlaser import maschinen_vergleich  # noqa: E402
alt_m = seite.kopf.get("maschine")
andere = next(m for m in seite.k_aktuell.maschinen if m != alt_m)
echt = maschinen_vergleich.guenstiger
maschinen_vergleich.guenstiger = lambda liste, m, ab=0.05: (dict(maschine=andere, verkauf=1.0), 0.2) \
    if m == alt_m else None
try:
    out = dict(texte=[], aktion=None, bericht=[])
    aa._maschine(seite, out)
finally:
    maschinen_vergleich.guenstiger = echt
assert seite.kopf.get("maschine") == andere and out["aktion"][0] == "Rückgängig" and "20,0 %" in out["texte"][0]
out["aktion"][1]()
assert seite.kopf.get("maschine") == alt_m
e = next(x for x in automatik.liste(db) if "Maschine" in x["text"])
assert e["rueck"]["art"] == "kopf" and e["rueck"]["alt"] == {"maschine": alt_m}
ok("E3: günstigere Maschine eingestellt, Einblendung „Rückgängig“ stellt die alte wieder ein")

# ------------------------------------------------------------------ E5 Nacharbeit
for i in (1, 2):
    assert nacharbeit.merken(db, "K-1001", 100 + i, "werkstoff", "S355-10219") is None
assert nacharbeit.merken(db, "K-1001", 101, "werkstoff", "S355-10219") is None      # gleiches Angebot zählt einmal
v = nacharbeit.merken(db, "K-1001", 103, "werkstoff", "S355-10219")
assert v and v["n"] == 3 and "Künftig automatisch" in nacharbeit.text(v)
nacharbeit.uebernehmen(db, v)
assert importprofil.vorgaben(importprofil.fuer_kunde(db, "K-1001"))["werkstoff"] == "S355-10219"
assert nacharbeit.merken(db, "K-1001", 104, "werkstoff", "S355-10219") is None      # schon Vorgabe
for i in (1, 2, 3):
    v = nacharbeit.merken(db, "K-1001", 200 + i, "stange", 8000)
nacharbeit.uebernehmen(db, v)
assert float(kundenvorgabe.fuer_kunde(db, "K-1001")["stange"]) == 8000
for i in (1, 2, 3):
    v = nacharbeit.merken(db, "K-1002", 300 + i, "zusatz", "Entgraten")
nacharbeit.ablehnen(db, v)
assert nacharbeit.merken(db, "K-1002", 304, "zusatz", "Entgraten") is None
ok("E5: ab drei Angeboten Vorschlag, Übernehmen ins Importprofil/Kundenvorgaben, abgelehnt fragt nicht mehr")

# ------------------------------------------------------------------ E1/E2 Fertigstellen
db.vorgang_setzen(aid, "Entwurf")
aufrufe = []


def outlook_ok(befehl):
    aufrufe.append(befehl)
    return subprocess.CompletedProcess(befehl, 0, "", "")


def bedienen(d):
    d.in_outlook()
    return d.result()


assert seite.fertigstellen(dialog=bedienen, ausfuehren=outlook_ok)
k = db.angebot(aid)
assert k["vorgang"] == "Verschickt" and aufrufe
wv = [v_ for v_ in k["versand"] if v_.get("art") == "wiedervorlage"]
assert wv and wv[-1]["am"] > datetime.date.today().isoformat()
assert any(v_.get("art") == "mail" for v_ in k["versand"])
assert aa.naechste_anfrage(fenster) is None             # kein Anfrage-Ordner
assert not aa.fertigstellen(seite, dialog=lambda d: d.reject(), ausfuehren=outlook_ok)
ok("E1: PDF, Outlook-Antwort, Verschickt, Wiedervorlage in einem Zug; abgebrochen = Kette hält an")

fenster.close()
print("Alle Tests der Angebots-Automationen bestanden.")
