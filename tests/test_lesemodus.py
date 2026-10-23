"""Lesemodus (Lizenz): Schreibschutz in der Datenbank (S1–S3).

S1 jede schreibende Datenbank-Methode löst im Lesemodus die Ausnahme Lesemodus aus, nichts ändert sich (auch nicht
   über db.con direkt: PRAGMA query_only); S2 Lesen, Export, Sicherung und Wiederherstellen gehen weiter;
S3 jede öffentliche Methode der Klasse Datenbank ist als liest, schreibt oder erlaubt eingeordnet – eine neue
   Methode ohne Einordnung macht diesen Test rot.
Aufruf: python tests/test_lesemodus.py
"""
import hashlib
import inspect
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser.__main__ import BEISPIEL  # noqa: E402
from rohrlaser.datenbank import Datenbank, Lesemodus  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="lesemodus_"))
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def methoden():
    return {n: m for n, m in inspect.getmembers(Datenbank, inspect.isfunction) if not n.startswith("_")}


# ------------------------------------------------------------------ S3 Einordnung
ohne = [n for n, m in methoden().items() if getattr(m, "zugriff", None) not in ("liest", "schreibt", "erlaubt")]
pruefe(not ohne, f"S3 jede öffentliche Datenbank-Methode ist eingeordnet (@liest/@schreibt/@erlaubt) {ohne or ''}")
schreibend = sorted(n for n, m in methoden().items() if m.zugriff == "schreibt")
pruefe({"neu", "aendern", "loeschen", "angebot_neu", "angebot_aendern", "angebot_kopieren", "angebot_loeschen",
        "position_neu", "position_aendern", "positionen_loeschen", "einstellung_setzen", "zukauf_speichern",
        "staffel_neu", "kunden_importieren", "stammdaten_ersetzen", "kunde_uebernehmen",
        "zukauf_angebot_aktualisieren"} <= set(schreibend), f"wichtige Methoden schreiben ({len(schreibend)})")
pruefe({"angebote", "angebot", "positionen", "einstellung", "sicherung", "exportieren"}
       <= {n for n, m in methoden().items() if m.zugriff == "liest"}, "Lesen, Sicherung und Export lesen nur")

# ------------------------------------------------------------------ Daten anlegen
db = Datenbank(tmp / "rohrlaser.db")
aid = db.angebot_neu(dict(kunde="Lesemodus-Test"))
for p in BEISPIEL:
    db.position_neu(aid, p)
db.staffel_neu(aid, dict(schluessel="10", menge=10))
db.sicherung()                       # Sicherung vor dem Lesemodus (für Wiederherstellen)
vorher_sicherung = sorted((tmp / "Sicherung").glob("*.db"))[-1]
db.position_neu(aid, dict(BEISPIEL[0], pos=40))


def fingerabdruck():
    return hashlib.sha256("\n".join(str(tuple(r)) for t in ("angebote", "positionen", "staffeln", "einstellungen",
                                                               "kunden", "profile", "werkstoffe")
                                    for r in db.con.execute(f"SELECT * FROM {t} ORDER BY 1")).encode()).hexdigest()


stand = fingerabdruck()
db.lesemodus("Lizenz abgelaufen am 01.01.2026")
pruefe(db.nur_lesen == "Lizenz abgelaufen am 01.01.2026", "Lesemodus eingeschaltet")

# ------------------------------------------------------------------ S1 schreibende Methoden
gesperrt, durch = [], []
for name in schreibend:
    m = getattr(db, name)
    n = sum(1 for p in inspect.signature(m).parameters.values()
            if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))
    try:
        m(*[None] * n)
        durch.append(name)
    except Lesemodus as e:
        gesperrt.append(name)
        if name == "angebot_aendern":
            text = str(e)
    except Exception as e:  # noqa: BLE001
        durch.append(f"{name} ({type(e).__name__})")
pruefe(not durch, f"S1 alle {len(schreibend)} schreibenden Methoden lösen Lesemodus aus {durch or ''}")
pruefe("Lizenz abgelaufen" in text and "Hilfe → Lizenz" in text, f"Meldung mit Grund ({text})")
for sql in ("INSERT INTO kunden (kundennr, name) VALUES ('X1', 'Direkt')", "UPDATE angebote SET kunde='weg'",
            "DELETE FROM positionen"):
    try:
        db.con.execute(sql)
        db.con.commit()
        pruefe(False, f"SQLite verweigert direktes Schreiben: {sql[:20]}")
    except sqlite3.OperationalError:
        pruefe(True, f"SQLite verweigert direktes Schreiben: {sql[:20]}")
pruefe(fingerabdruck() == stand, "S1 Daten unverändert")

# ------------------------------------------------------------------ S2 Lesen, Export, Sicherung
try:
    gelesen = dict(angebote=len(db.angebote()), angebot=db.angebot(aid)["kunde"], positionen=len(db.positionen(aid)),
                   staffeln=len(db.staffeln(aid)), stufen=len(db.staffel_stufen(aid)), netze=len(db.netze(aid)),
                   protokoll=len(db.protokoll(aid)), stand=bool(db.angebot_stand(aid)), einst=len(db.einstellungen()),
                   kontext=bool(db.kontext()), tabellen=len(db.tabellen()), blech=bool(db.blech_daten()),
                   fracht=bool(db.fracht_daten()), fk=len(db.fracht_kalkulationen()), zk=len(db.zukauf_kategorien()),
                   zl=len(db.zukauf_artikel_liste()), zh=len(db.zukauf_historie()), zp=len(db.zukauf_positionen()),
                   zus=len(db.zusatz_haeufigkeit()), vorg=bool(db.kalkulation_vorgaben()),
                   liefer=db.lieferzeit_vorgabe(), zahl=bool(db.zahlungsbedingungen()),
                   kunden=len(db.zeilen("kunden")), profile=db.anzahl("profile"), fremd=db.fracht_zonen_fremd(),
                   zeit=bool(db.zeitbasis_vorgabe(db.angebot(aid)["maschine"])))
    pruefe(gelesen["positionen"] == 4 and gelesen["angebot"] == "Lesemodus-Test", f"S2 Lesen geht ({len(gelesen)} Abfragen)")
except Exception as e:  # noqa: BLE001
    pruefe(False, f"S2 Lesen geht ({type(e).__name__}: {e})")
info = db.exportieren(tmp / "Export.zip")
pruefe((tmp / "Export.zip").stat().st_size > 1000 and info["anzahl"]["positionen"] == 4, "S2 Daten exportieren geht")
s = db.sicherung()
pruefe(s.exists(), "S2 Sicherung anlegen geht")
pfade, _ = db.sicherungen()
pruefe(all(p.exists() for p in pfade), "S2 Sicherungen (Hilfe → Sicherung) gehen")
db.wiederherstellen(vorher_sicherung)
pruefe(len(db.positionen(aid)) == 3 and db.nur_lesen, "S2 Sicherung wiederherstellen geht, Lesemodus bleibt")
try:
    db.con.execute("DELETE FROM positionen")
    pruefe(False, "nach dem Wiederherstellen weiter schreibgeschützt")
except sqlite3.OperationalError:
    pruefe(True, "nach dem Wiederherstellen weiter schreibgeschützt")

# ------------------------------------------------------------------ wieder frei
db.lesemodus("")
pid = db.position_neu(aid, dict(BEISPIEL[1], pos=50))
db.einstellung_setzen("lizenz_zuletzt", "2026-11-15")
pruefe(pid and len(db.positionen(aid)) == 4 and db.einstellung("lizenz_zuletzt") == "2026-11-15",
       "Lesemodus aus: Ändern geht wieder")
db.schliessen()

neu = Datenbank(tmp / "zweite.db")
pruefe(neu.nur_lesen == "" and neu.angebot_neu(dict(kunde="frei")), "ohne Lizenzangabe: voller Zugriff (Tests, Entwicklung)")
neu.schliessen()

print(f"\n{len(fehler)} Fehler" if fehler else "\nAlle Lesemodus-Prüfungen bestanden.")
sys.exit(1 if fehler else 0)
