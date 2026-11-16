"""Prüft „Angebot per E-Mail“ (Vorschlag V1, 31.10.2026, angebot_mail.py):
- Ohne Anfrage-Mail: neue E-Mail an die E-Mail des Kunden, Anrede aus dem Ansprechpartner, Betreff/Text aus der
  Vorlage mit Angebotsnummer, Anfrage-Nr. und Gültigkeit, Angebots-PDF im Anhang, Outlook nur Display (nie Send).
- Mit Anfrage-Mail (.msg im Ordner „Anfrage“): „Allen antworten“ (OpenSharedItem + ReplyAll), An = Absender,
  Betreff „AW: …“; .eml lässt sich nicht beantworten -> neue E-Mail an den Absender.
- Ohne Outlook: E-Mail-Datei mit PDF-Anhang. Versandverlauf art 'mail', zählt für das Nachfassen, Text im Verlauf.
- Funktion „Angebot per E-Mail“ schaltbar, Seite der Einstellungen eingeordnet.

Aufruf: python tests/test_angebot_mail.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import email
import json
import os
import subprocess
import sys
import tempfile
from email import policy
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
import mail_testdateien as mt  # noqa: E402
from rohrlaser import angebot_mail as am  # noqa: E402
from rohrlaser import cockpit, einstellungen_ordnung, funktionen  # noqa: E402
from rohrlaser.angebot_oben import _versand_text  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Muster Laser GmbH")
db.neu("kunden", dict(kundennr="K-77", name="Metallbau Schulz", ansprechpartner="Frau Schulz",
                      email="einkauf@schulz.example"))
heute = datetime.date.today().isoformat()
a = db.angebot_neu(dict(kunde="Metallbau Schulz", kundennr="K-77", nummer="2026-00500", datum=heute,
                        kundenreferenz="AF-4711"))
db.position_neu(a, dict(pos=10, artikel="T1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1450,
                        stueck=8, schneidweg=200, einstiche=2))
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
geoeffnet = []
s.f.datei_oeffnen = geoeffnet.append

# ------------------------------------------------------------------ E1 Bausteine ohne Qt
assert am.anrede({"ansprechpartner": "Frau Schulz"}) == "Sehr geehrte Frau Schulz,"
assert am.anrede({"ansprechpartner": "herr Meier"}) == "Sehr geehrter Herr Meier,"
assert am.anrede({"ansprechpartner": "Einkauf"}) == am.anrede(None) == "Sehr geehrte Damen und Herren,"
kopf = db.angebot(a)
assert am.betreff(kopf, {}) == "Angebot 2026-00500 zu Ihrer Anfrage AF-4711"
t = am.text(kopf, {"gueltigkeit": 30}, db.kunde("K-77"))
gueltig = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%d.%m.%Y")
assert t.startswith("Sehr geehrte Frau Schulz,") and "Angebot 2026-00500 zu Ihrer Anfrage AF-4711" in t and gueltig in t
assert am.empfaenger(db.kunde("K-77")) == "einkauf@schulz.example"
assert am.antwort_moeglich("x.msg") and not am.antwort_moeglich("x.eml") and not am.antwort_moeglich(None)
ok("E1 Anrede aus dem Ansprechpartner, Betreff/Text aus der Vorlage (Nummer, Anfrage-Nr., gültig bis), Empfänger")

# ------------------------------------------------------------------ E2 neue E-Mail an den Kunden
aufrufe = []


def outlook_ok(befehl):
    skript = Path(befehl[befehl.index("-File") + 1]).read_text(encoding="utf-8-sig")
    daten = json.loads(Path(befehl[-1]).read_text(encoding="utf-8"))
    aufrufe.append((skript, daten))
    return subprocess.CompletedProcess(befehl, 0, "", "")


gesehen = {}


def bedienen(d):
    gesehen["antwort_sichtbar"] = not d.antwort.isHidden()
    gesehen["an"], gesehen["betreff"], gesehen["text"] = d.mail()
    d.in_outlook()
    return d.result()


d = s.angebot_mail(dialog=bedienen, ausfuehren=outlook_ok)
assert d.ergebnis == "outlook" and not gesehen["antwort_sichtbar"]
assert gesehen["an"] == "einkauf@schulz.example" and gesehen["betreff"] == "Angebot 2026-00500 zu Ihrer Anfrage AF-4711"
skript, daten = aufrufe[-1]
assert "Display" in skript and ".Send" not in skript and "Send(" not in skript
assert daten["antwort"] == "" and len(daten["anhaenge"]) == 1 and daten["anhaenge"][0].endswith(".pdf")
assert Path(daten["anhaenge"][0]).exists() and not geoeffnet          # PDF erstellt, aber nicht angezeigt
v = db.angebot(a)["versand"]
assert v[-1]["art"] == "mail" and v[-1]["an"] == "einkauf@schulz.example" and not v[-1].get("antwort")
assert any(not e.get("art") and e.get("datei", "").endswith(".pdf") for e in v)       # PDF wie bisher vermerkt
assert "per E-Mail an einkauf@schulz.example" in _versand_text(v[-1])
assert db.angebot(a)["vorgang"] == "Verschickt"
assert cockpit.verlauf(db.angebot(a))[0] == datetime.date.today()
ok("E2 ohne Anfrage-Mail: PDF erstellt (nicht angezeigt), neue E-Mail an den Kunden mit PDF, nur Display; "
   "Verlauf 'mail', Verschickt, zählt fürs Nachfassen")

# ------------------------------------------------------------------ E3 Antwort auf die Anfrage-Mail (.msg)
ordner = fenster.angebot_ordner(db.angebot(a)) / "Anfrage"
ordner.mkdir(parents=True, exist_ok=True)
alt = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=datetime.timezone.utc)
neu = datetime.datetime(2026, 10, 28, 9, 0, tzinfo=datetime.timezone.utc)
(ordner / "Anfrage alt.eml").write_bytes(bytes(mt.eml("Alte Anfrage", "x", "Alt", "alt@schulz.example", alt)))
(ordner / "Anfrage.msg").write_bytes(mt.msg("Anfrage Rohrteile AF-4711", "Bitte um Angebot", "Petra Schulz",
                                            "p.schulz@schulz.example", neu))
(ordner / "Anfrage (alt).msg").write_bytes(mt.msg("Ganz neu, aber alt", "x", "", "x@schulz.example",
                                                  datetime.datetime(2026, 10, 30, tzinfo=datetime.timezone.utc)))
assert [p.name for p in am.anfrage_mails(fenster.angebot_ordner(db.angebot(a)))] == ["Anfrage.msg", "Anfrage alt.eml"]


def antwort_bedienen(d):
    gesehen["antwort"] = d.antwort.isChecked() and d.antwort.isEnabled()
    gesehen["antwort_text"] = d.antwort.text()
    gesehen["an"], gesehen["betreff"], _ = d.mail()
    d.in_outlook()
    return d.result()


d = s.angebot_mail(dialog=antwort_bedienen, ausfuehren=outlook_ok)
skript, daten = aufrufe[-1]
assert gesehen["antwort"] and "p.schulz@schulz.example" in gesehen["antwort_text"], gesehen
assert gesehen["an"] == "p.schulz@schulz.example" and gesehen["betreff"] == "AW: Anfrage Rohrteile AF-4711"
assert daten["antwort"].endswith("Anfrage.msg") and "OpenSharedItem" in skript and "ReplyAll()" in skript
assert skript.index("ReplyAll") < skript.index("$m.Display") < skript.index("Insert(")    # Text vor den Verlauf
assert db.angebot(a)["versand"][-1].get("antwort") is True
assert "(Antwort auf die Anfrage)" in _versand_text(db.angebot(a)["versand"][-1])
ok("E3 Anfrage-Mail .msg im Angebotsordner: Allen antworten, An = Absender, Betreff AW:, neueste Mail, „(alt)“ nicht")

# ------------------------------------------------------------------ E4 nur .eml, ohne Outlook: E-Mail-Datei
(ordner / "Anfrage.msg").unlink()


def ohne_outlook(befehl):
    return subprocess.CompletedProcess(befehl, 1, "", "Die COM-Klasse Outlook.Application ist nicht registriert.")


def eml_bedienen(d):
    gesehen["antwort"] = d.antwort.isEnabled()
    gesehen["an"], gesehen["betreff"], _ = d.mail()
    d.in_outlook()
    return d.result()


d = s.angebot_mail(dialog=eml_bedienen, ausfuehren=ohne_outlook)
assert not gesehen["antwort"] and gesehen["an"] == "alt@schulz.example" and gesehen["betreff"] == "AW: Alte Anfrage"
assert d.ergebnis == "eml" and geoeffnet and geoeffnet[-1].suffix == ".eml"
m = email.message_from_bytes(geoeffnet[-1].read_bytes(), policy=policy.default)
anh = [t.get_filename() for t in m.iter_attachments()]
assert m["To"] == "alt@schulz.example" and len(anh) == 1 and anh[0].endswith(".pdf"), anh
assert "Muster Laser GmbH" in m.get_body().get_content()            # eigene Signatur in der Datei
assert db.angebot(a)["versand"][-1]["art"] == "mail" and db.angebot(a)["versand"][-1]["datei"].endswith(".eml")
ok("E4 nur .eml: neue E-Mail an den Absender; ohne Outlook E-Mail-Datei mit PDF und eigener Signatur, vermerkt")

# ------------------------------------------------------------------ E5 Abbrechen, Funktion, Einstellungen
n = len(db.angebot(a)["versand"])
d = s.angebot_mail(dialog=lambda d: d.reject(), ausfuehren=outlook_ok)
assert d.eintrag is None and len(db.angebot(a)["versand"]) == n + 1      # nur das PDF, keine Mail vermerkt
assert "funktion_angebot_mail" in funktionen.FUNKTION
assert any(s_.schluessel == "e_angebot_mail" for s_ in einstellungen_ordnung.SEITEN)
akt = next(x for x, f in s.funktion_aktionen if f == "funktion_angebot_mail")
assert akt.text() == "Angebot per E-Mail …"
ok("E5 Schließen ohne Vermerk der E-Mail; Funktion schaltbar, Seite „Angebot per E-Mail“, Menüpunkt unter Ausgaben")
fenster.close()
db.schliessen() if hasattr(db, "schliessen") else None
print("Alle Prüfungen bestanden.")
