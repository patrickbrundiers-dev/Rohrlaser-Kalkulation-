"""Lesemodus (Lizenz): Schreibschutz in der Datenbank (S1–S3) und Oberfläche (S4–S6).

S1 jede schreibende Datenbank-Methode löst im Lesemodus die Ausnahme Lesemodus aus, nichts ändert sich (auch nicht
   über db.con direkt: PRAGMA query_only); S2 Lesen, Export, Sicherung und Wiederherstellen gehen weiter;
S3 jede öffentliche Methode der Klasse Datenbank ist als liest, schreibt oder erlaubt eingeordnet – eine neue
   Methode ohne Einordnung macht diesen Test rot;
S4 Oberfläche im Lesemodus: ändernde Knöpfe und Kürzel aus, Hinweis sichtbar, Angebot nur ansehen, kein Fehler;
S5 Admin-Lizenz: Einstellungen ohne Passwort; S6 Testlizenz: PDF mit Aufdruck TESTVERSION.
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
    return {n: m for n, m in inspect.getmembers(Datenbank, inspect.isroutine) if not n.startswith("_")}


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

# ------------------------------------------------------------------ S4–S6 Oberfläche
import datetime  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import lizenz, pdf  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
PRIVAT = Ed25519PrivateKey.generate()
SCHL = {"T1": lizenz.oeffentlich_text(PRIVAT)}
RECHNER = lizenz.rechner_id("test-rechner")
fehler_ui = []
sys.excepthook = lambda art, wert, tb: fehler_ui.append(f"{art.__name__}: {wert}")


def lizenzdatei(art, tage=200):
    inhalt = dict(lizenz_id="L-2026-0042", art=art, inhaber="Test", firma="", ausgestellt="2026-01-01",
                  gueltig_ab="2026-01-01", gueltig_bis=None if art == "admin" else
                  (datetime.date.today() + datetime.timedelta(days=tage)).isoformat(),
                  rechner=[RECHNER], funktionen=["alle"], test=art == "test", schluessel_id="T1", hinweis="")
    return dict(format=1, inhalt=inhalt, signatur=lizenz.signieren(inhalt, PRIVAT))


def fenster(name, lizenzdaten=None, durchsetzung=True):
    d = Datenbank(tmp / name / "rohrlaser.db")
    a = d.angebot_neu(dict(kunde="UI-Test"))
    for p in BEISPIEL:
        d.position_neu(a, p)
    stelle = lizenz.LizenzStelle(lizenz.ordner(tmp / name), d, SCHL, RECHNER, durchsetzung)
    if lizenzdaten:
        lizenz.lizenz_laden(stelle.ordner, lizenzdaten, rechner=RECHNER, schluessel=SCHL)
    stelle.pruefen()
    f = Hauptfenster(d, stumm=True, lizenz=stelle)
    f.show()
    app.processEvents()
    return d, a, f, stelle


def knopf(w, text):
    return next((k for k in w.findChildren(QPushButton) if k.text() == text), None)


d, a, f, stelle = fenster("ohne")
pruefe(d.nur_lesen and stelle.zustand.stufe == "lesemodus", "S4 ohne Lizenz (Stufe 2): Lesemodus")
pruefe(f.lizenz_hinweis.isVisible() and "Lesemodus" in f.lizenz_hinweis.text() and RECHNER in f.lizenz_hinweis.text(),
       f"S4 Hinweis in der Statusleiste ({f.lizenz_hinweis.text()[:60]} …)")
pruefe("Lesemodus" in f.windowTitle(), "S4 Fenstertitel zeigt Lesemodus")
pruefe(not knopf(f.angebote, "Neues Angebot").isEnabled() and not knopf(f.angebote, "Löschen").isEnabled()
       and knopf(f.angebote, "Öffnen").isEnabled(), "S4 Angebote: Neu/Löschen aus, Öffnen geht")
pruefe(not f.kuerzel_aktionen["neu"].isEnabled() and not f.kuerzel_aktionen["optimieren"].isEnabled()
       and f.kuerzel_aktionen["kopieren"].isEnabled(), "S4 Kürzel Neu/Optimieren aus, Kopieren geht")
pruefe(f.datei_aktionen["Daten exportieren …"].isEnabled() and f.datei_aktionen["Datensicherung erstellen"].isEnabled()
       and not f.datei_aktionen["Mit den Kollegen abgleichen"].isEnabled(), "S4 Export und Sicherung im Menü frei")
seite = f.angebot_oeffnen(a)
for i in range(seite.reiter.count()):
    seite.reiter.setCurrentIndex(i)
    app.processEvents()
for i in range(f.reiter.count()):
    f.reiter.setCurrentIndex(i)
    app.processEvents()
pruefe(seite.fremd_leiste.isVisible() and "Lesemodus" in seite.fremd_text.text() and not seite.kopf_bereich.isEnabled(),
       "S4 Angebot: Hinweis Lesemodus, Kopf gesperrt")
pruefe(not knopf(seite, "Optimieren").isEnabled() and not knopf(seite, "Angebot (PDF)").isEnabled()
       and knopf(seite, "3D-Ansicht …").isEnabled(), "S4 Angebot: Optimieren und PDF aus, 3D-Ansicht geht")
pruefe(not fehler_ui, f"S4 Ansehen aller Reiter ohne Fehler {fehler_ui or ''}")
d2 = f.lizenz_zeigen()
pruefe(RECHNER == d2.rechner.text() and "Lesemodus" in d2.status.text(), "Lizenzdialog zeigt Rechner-ID und Zustand")
pruefe(RECHNER in d2.email_adresse() and "mailto:" in d2.email_adresse(), "fertige E-Mail mit Rechner-ID")
schlecht = tmp / "schlecht.lizenz"
schlecht.write_text("{}", encoding="utf-8")
pruefe(not d2.laden(schlecht) and d.nur_lesen, "ungültige Datei im Dialog abgelehnt")
gut = tmp / "gut.lizenz"
gut.write_text(__import__("json").dumps(lizenzdatei("benutzer")), encoding="utf-8")
pruefe(d2.laden(gut) and not d.nur_lesen and "Lizenz gültig" in d2.status.text(), "Lizenz im Dialog geladen: frei")
pruefe(d.angebot_neu(dict(kunde="wieder frei")), "nach dem Laden: Ändern geht")
f.close()
d.schliessen()

d, a, f, stelle = fenster("stufe1", durchsetzung=False)
pruefe(not d.nur_lesen and f.lizenz_hinweis.isVisible() and "braucht das Programm eine Lizenz" in f.lizenz_hinweis.text()
       and knopf(f.angebote, "Neues Angebot").isEnabled(), "Stufe 1: ohne Lizenz nur Hinweis, alles frei")
f.close()
d.schliessen()

d, a, f, stelle = fenster("admin", lizenzdatei("admin"))
d.einstellung_setzen("passwort", "geheim")
stelle.admin_sperren()
f.lizenz_anwenden()
f.bereich.sperren()
pruefe(not stelle.zustand.admin and f.bereich.gesperrt() and f.lizenz_hinweis.isVisible()
       and "Admin-Passwort" in f.lizenz_hinweis.text(), "S5 Admin ohne Admin-Passwort: Einstellungen gesperrt, Hinweis")
pruefe(stelle.admin_freigeben("geheim"), "S5 Admin-Passwort eingegeben")
f.lizenz_anwenden()
pruefe(stelle.zustand.admin and not f.bereich.gesperrt() and not f.lizenz_hinweis.isVisible(),
       "S5 Admin: Einstellungen ohne Passwort, kein Hinweis")
pruefe("Admin-Lizenz" in stelle.text(), f"Über …: {stelle.text()}")
f.close()
d.schliessen()

d, a, f, stelle = fenster("test", lizenzdatei("test", 20))
pruefe(stelle.zustand.test and pdf.AUFDRUCK == "TESTVERSION" and "TESTVERSION" in f.windowTitle(),
       "S6 Testlizenz: Aufdruck TESTVERSION eingeschaltet")
d.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
seite = f.angebot_oeffnen(a)
seite.optimieren()
datei = seite.angebot_pdf()
import base64  # noqa: E402
import re  # noqa: E402
import zlib  # noqa: E402


def pdf_inhalt(pfad):
    """Seiteninhalte einer reportlab-PDF entpackt (ASCII85 + Flate), ohne pypdf (fehlt in der CI)."""
    roh, teile = Path(pfad).read_bytes(), []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", roh, re.S):
        daten = m.group(1).strip()
        try:
            if daten.endswith(b"~>"):
                daten = base64.a85decode(daten[:-2].replace(b"\n", b"").replace(b"\r", b""))
            teile.append(zlib.decompress(daten))
        except (ValueError, zlib.error):
            teile.append(daten)
    return b"".join(teile).decode("latin-1")


text = pdf_inhalt(datei) if datei else ""
pruefe("TESTVERSION" in text, "S6 Angebots-PDF trägt TESTVERSION")
pruefe(f.lizenz_hinweis.isVisible() and "Testlizenz" in f.lizenz_hinweis.text(), "Testlizenz läuft bald ab: Hinweis")
f.close()
d.schliessen()
pdf.AUFDRUCK = ""
pruefe(not fehler_ui, f"keine unerwarteten Fehler {fehler_ui or ''}")

print(f"\n{len(fehler)} Fehler" if fehler else "\nAlle Lesemodus-Prüfungen bestanden.")
sys.exit(1 if fehler else 0)
