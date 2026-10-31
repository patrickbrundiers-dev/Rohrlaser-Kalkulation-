"""Intern weitergeleitete Anfrage-Mails (Patrick 31.10.2026: „Wenn die Mail intern weitergeleitet wird, muss das
erkannt werden“, Freigabe „Alle a“): Kunde, Signatur, Anfragetext, Staffel, Zusatzarbeiten, Termin, Bemerkung und das
Zusammenfassen kommen aus der Mail des Kunden, nicht vom Kollegen, der sie weitergeleitet hat – inline (Outlook,
Gmail, Thunderbird), als .msg/.eml-Anhang, mehrfach weitergeleitet, Kollege mit zweiter Domain. F1 weitere eigene
Domains in den Einstellungen, F2 Notiz des Kollegen gilt (Hinweis auf den Kundenwert), F3 Bemerkung mit „weitergeleitet
von …“, F4 leitet der Kunde selbst weiter, bleibt er der Absender. Keine echten Mails (mail_testdateien.py).

Aufruf: python tests/test_weiterleitung.py
"""
import datetime
import os
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mail_testdateien as bau  # noqa: E402
from rohrlaser import anfragen, mail  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


KW = (datetime.date.today() + datetime.timedelta(weeks=5)).isocalendar()[1]
KW_NOTIZ = (datetime.date.today() + datetime.timedelta(weeks=3)).isocalendar()[1]
KUNDE = (f"Guten Tag,\n\nbitte um Angebot für 10 / 50 / 100 Stk Rahmen.\nMaterial: 1.4301, Teile verzinkt.\n"
         f"Liefertermin KW {KW}\n\nMit freundlichen Grüßen\nHans Neumann\nStahlbau Neumann GmbH\nIndustriestr. 5\n"
         "44135 Dortmund\nTel. 0231 123456")
INTERN = "Hallo Patrick,\nbitte ein Angebot machen, eilt.\n\nGruß Max\nMax Kollege\nLaser Brundiers GmbH\nTel. 02345 999\n"
STEP = [("Rahmen.stp", b"ISO-10303-21;\n" + b"x" * 5000)]
D1, D2 = datetime.datetime(2026, 10, 27, 9, 12), datetime.datetime(2026, 10, 28, 8, 0)
NEUMANN = "h.neumann@stahlbau-neumann.de"


def kopf_de(name, adr, d, betreff, an="max@laser.example"):
    return f"Von: {name} <{adr}>\nGesendet: Dienstag, {d:%d.%m.%Y %H:%M}\nAn: {an}\nBetreff: {betreff}\n\n"


def outlook(text, absender="max@laser.example", name="Max Kollege", betreff="WG: Anfrage Rahmen R-77", anh=STEP):
    return mail.aus_bytes(bau.msg(betreff, text, name, absender, D2, anh))


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("benutzer_email", "patrick@laser.example")
db.einstellung_setzen("briefkopf_1", "Laser Brundiers GmbH")
EIGENE = anfragen.eigene_domains(db)
assert EIGENE == {"laser.example"}, EIGENE

# ------------------------------------------------------------------ Erkennen der Ursprungsmail
faelle = {
    "Outlook inline": outlook(INTERN + "\n________________________________\n"
                              + kopf_de("Neumann, Hans", NEUMANN, D1, "Anfrage Rahmen R-77") + KUNDE),
    "Gmail inline": mail.aus_bytes(bau.eml(
        "Fwd: Anfrage Rahmen R-77", INTERN + "\n---------- Forwarded message ---------\nFrom: Hans Neumann <"
        + NEUMANN + ">\nDate: Tue, Oct 27, 2026 at 9:12 AM\nSubject: Anfrage Rahmen R-77\nTo: <max@laser.example>\n\n"
        + KUNDE, "Max Kollege", "max@laser.example", D2, STEP), ".eml"),
    "Thunderbird inline": outlook(INTERN + "\n-------- Weitergeleitete Nachricht --------\nBetreff: Anfrage Rahmen R-77\n"
                                  "Datum: Tue, 27 Oct 2026 09:12:00 +0000\nVon: Hans Neumann <" + NEUMANN + ">\n"
                                  "An: max@laser.example\n\n" + KUNDE),
    "als .msg-Anhang": outlook(INTERN, anh=[("Anfrage Rahmen R-77.msg", dict(
        betreff="Anfrage Rahmen R-77", text=KUNDE, absender_name="Hans Neumann", absender=NEUMANN, datum=D1,
        anhaenge=STEP))]),
    "zweimal weitergeleitet": outlook(
        "Patrick, kannst du das übernehmen?\nGruß Eva\n\n" + kopf_de("Max Kollege", "max@laser.example", D2,
                                                                     "WG: Anfrage Rahmen R-77", "eva@laser.example")
        + INTERN + "\n" + kopf_de("Hans Neumann", NEUMANN, D1, "Anfrage Rahmen R-77") + KUNDE,
        "eva@laser.example", "Eva Vertrieb", "WG: WG: Anfrage Rahmen R-77"),
    "Kollege mit zweiter Domain": outlook(INTERN + "\n" + kopf_de("Hans Neumann", NEUMANN, D1, "Anfrage Rahmen R-77")
                                          + KUNDE, "max@brundiers-gruppe.de"),
}
eml_innen = EmailMessage()
eml_innen["From"], eml_innen["Subject"] = f"Hans Neumann <{NEUMANN}>", "Anfrage Rahmen R-77"
eml_innen["Date"] = "Tue, 27 Oct 2026 09:12:00 +0000"
eml_innen.set_content(KUNDE)
faelle["als .eml-Anhang"] = mail.aus_bytes(bau.eml("WG: Anfrage Rahmen R-77", INTERN, "Max Kollege",
                                                   "max@laser.example", D2,
                                                   [("Anfrage.eml", eml_innen)] + STEP), ".eml")
for name, m in faelle.items():
    w = mail.weiterleitung(m, EIGENE, "Laser Brundiers GmbH")
    assert w and w.original is not None, (name, w)
    o = w.original
    assert o.absender == NEUMANN and o.absender_name == "Hans Neumann", (name, o.absender, o.absender_name)
    assert o.datum and o.datum.date() == D1.date(), (name, o.datum)
    assert o.betreff == "Anfrage Rahmen R-77" and "Industriestr. 5" in o.text, (name, o.betreff)
    assert [n for n, _ in o.anhaenge] == ["Rahmen.stp"], (name, o.anhaenge)
    assert w.weiterleiter[0][0] in ("Max Kollege", "Eva Vertrieb"), (name, w.weiterleiter)
assert faelle["Outlook inline"] and mail.weiterleitung(faelle["Outlook inline"], EIGENE).original.datum == D1
w = mail.weiterleitung(faelle["zweimal weitergeleitet"], EIGENE)
assert [k[0] for k in w.weiterleiter] == ["Eva Vertrieb", "Max Kollege"], w.weiterleiter
assert w.text() == "weitergeleitet von Eva Vertrieb am 28.10.2026 08:00, davor Max Kollege", w.text()
assert w.notiz == "Patrick, kannst du das übernehmen?", w.notiz
assert mail.weiterleitung(faelle["Outlook inline"], EIGENE).notiz == "bitte ein Angebot machen, eilt."
ok("Ursprungsmail erkannt: Outlook, Gmail, Thunderbird inline, .msg/.eml-Anhang, zweimal weitergeleitet, Kollege "
   "mit zweiter Domain (Signatur mit eigenem Firmennamen); Weiterleiter und Notiz")

# nicht weitergeleitet bzw. vom Kunden selbst weitergeleitet (F4 a)
direkt = mail.aus_bytes(bau.msg("Anfrage Rahmen", KUNDE, "Hans Neumann", NEUMANN, D1, STEP))
assert mail.weiterleitung(direkt, EIGENE, "Laser Brundiers GmbH") is None
antwort = mail.aus_bytes(bau.msg("AW: Angebot 2026-00042", "Passt, bitte so liefern.\nGruß Hans Neumann\n\n"
                                 + kopf_de("Patrick Brundiers", "patrick@laser.example", D1, "Angebot 2026-00042",
                                           NEUMANN) + "Anbei unser Angebot.\nLaser Brundiers GmbH", "Hans Neumann",
                                 NEUMANN, D2, STEP))
assert mail.weiterleitung(antwort, EIGENE, "Laser Brundiers GmbH") is None
selbst = mail.aus_bytes(bau.msg("WG: Rahmen", "Bitte anbieten.\nGruß Eva Einkauf\nStahlbau Neumann GmbH\n\n"
                                + kopf_de("Karl Konstrukteur", "k.konstrukteur@stahlbau-neumann.de", D1, "Rahmen",
                                          "e.einkauf@stahlbau-neumann.de") + KUNDE, "Eva Einkauf",
                                "e.einkauf@stahlbau-neumann.de", D2, STEP))
assert mail.weiterleitung(selbst, EIGENE, "Laser Brundiers GmbH") is None
assert mail.kunde_daten(selbst, "", EIGENE)["ansprechpartner"] == "Eva Einkauf"
intern_neu = outlook("Hallo Patrick, Teile für unsere Halle.\nGruß Max", betreff="Rahmen Halle 3")
assert mail.weiterleitung(intern_neu, EIGENE) is None
unklar = mail.weiterleitung(outlook("Hallo Patrick, siehe unten.\nGruß Max\n\nKunde hat angerufen."), EIGENE)
assert unklar and unklar.original is None, unklar
nur_name = mail.weiterleitung(outlook(INTERN + "\nVon: Max Kollege\nGesendet: 28.10.2026 07:50\nAn: Eva\nBetreff: x\n\n"
                                      "ok\n\n" + kopf_de("Hans Neumann", NEUMANN, D1, "Anfrage") + KUNDE), EIGENE)
assert nur_name.original.absender == NEUMANN, nur_name
ok("Nicht weitergeleitet: direkte Kundenmail, Antwort des Kunden mit unserem Zitat, Kunde leitet selbst intern weiter "
   "(Einkauf bleibt Ansprechpartner, F4 a), interne Mail ohne WG:; WG: ohne erkennbaren Kunden; Kollege nur mit Namen")

assert mail.betreff_ohne("WG: AW: FW: Anfrage") == "Anfrage"
for t, soll in (("Dienstag, 27. Oktober 2026 09:12", D1), ("Tuesday, October 27, 2026 9:12 AM", D1),
                ("27.10.2026 09:12", D1), ("Tue, Oct 27, 2026 at 9:12 PM", D1.replace(hour=21)),
                ("Mo., 3. Nov. 2026 um 07:30 Uhr", datetime.datetime(2026, 11, 3, 7, 30)), ("irgendwas", None)):
    assert mail.kopf_zeit(t) == soll, (t, mail.kopf_zeit(t))
ok("Datum aus „Gesendet:/Date:“ deutsch und englisch, Betreff ohne WG:/FW:/AW:")

# ------------------------------------------------------------------ Auswerten wie eine Kundenmail
for name, m in faelle.items():
    kunde, _, w = anfragen.werte(db, [], [m])
    h = "\n".join(w.get("hinweis", []))
    assert kunde is None and w["neuer_kunde"]["name"] == "Stahlbau Neumann GmbH", (name, w.get("neuer_kunde"))
    assert w["neuer_kunde"]["email"] == NEUMANN and w["neuer_kunde"]["ansprechpartner"] == "Hans Neumann"
    if name != "Kollege mit zweiter Domain":
        assert w["neuer_kunde"].get("plz_ort") == "44135 Dortmund", (name, w["neuer_kunde"])
    assert "Intern weitergeleitet von" in h and f"Anfrage von Hans Neumann <{NEUMANN}>" in h, (name, h)
    assert "Mengen 10 / 50 / 100" in h and "„verzinkt“ erwähnt" in h, (name, h)
    assert w["kopf"]["lieferzeit_wert"].startswith(f"{KW}/"), (name, w["kopf"])
    assert w["kopf"]["bemerkung"].startswith(f"E-Mail von Hans Neumann <{NEUMANN}> vom 27.10.2026"), w["kopf"]
    assert "(weitergeleitet von " in w["kopf"]["bemerkung"], w["kopf"]
kunde, _, w = anfragen.werte(db, [], [faelle["Outlook inline"]])
assert w["kopf"]["bemerkung"] == (f"E-Mail von Hans Neumann <{NEUMANN}> vom 27.10.2026 09:12: Anfrage Rahmen R-77 "
                                  "(weitergeleitet von Max Kollege am 28.10.2026 08:00)"), w["kopf"]["bemerkung"]
assert "Notiz von Max Kollege: „bitte ein Angebot machen, eilt.“" in w["hinweis"], w["hinweis"]
ok("Auswerten: neuer Kunde mit Signatur des Kunden, Staffel, Zusatzarbeit, Termin aus der Kundenmail; Bemerkung F3 a; "
   "Hinweis „Intern weitergeleitet“ und Notiz des Kollegen")

db.con.execute("INSERT OR REPLACE INTO kunden (kundennr, name, email) VALUES ('10007', 'Stahlbau Neumann GmbH', "
               "'einkauf@stahlbau-neumann.de')")
db.con.execute("INSERT OR REPLACE INTO kunden (kundennr, name, email) VALUES ('10008', 'Brundiers Gruppe', "
               "'info@brundiers-gruppe.de')")
db.con.commit()
for name, m in faelle.items():
    assert anfragen.werte(db, [], [m])[0] == "10007", name
ok("Kunde im Stamm: immer der Kunde, nie die Firma des Kollegen (auch bei zweiter Domain)")

# F2 a: Termin in der Notiz des Kollegen gilt, Hinweis auf den Wert des Kunden
m = outlook(f"Hallo Patrick,\nKunde braucht die Teile schon KW {KW_NOTIZ}, Liefertermin bitte so.\nGruß Max\n\n"
            + kopf_de("Hans Neumann", NEUMANN, D1, "Anfrage Rahmen R-77") + KUNDE)
_, _, w = anfragen.werte(db, [], [m])
assert w["kopf"]["lieferzeit_wert"].startswith(f"{KW_NOTIZ}/"), w["kopf"]
assert any(h.startswith(f"Die weitergeleitete Mail des Kunden nennt KW {KW}") and "es gilt die Notiz von Max Kollege"
           in h for h in w["hinweis"]), w["hinweis"]
ok("F2 a: Termin aus der Notiz des Kollegen gilt, Hinweis auf den abweichenden Termin des Kunden")

# F1 a: weitere eigene Domains in den Einstellungen; Kollegen aus dem gemeinsamen Ordner
db.einstellung_setzen("eigene_domains", "brundiers-gruppe.de; @laser-service.de, x")
db.einstellung_setzen("teilen_mitarbeiter", {"EV": {"name": "Eva", "email": "eva@vertrieb-brundiers.de"}})
assert anfragen.eigene_domains(db) == {"laser.example", "brundiers-gruppe.de", "laser-service.de",
                                       "vertrieb-brundiers.de"}, anfragen.eigene_domains(db)
ohne_sig = outlook("bitte anbieten\n\n" + kopf_de("Hans Neumann", NEUMANN, D1, "Anfrage") + KUNDE,
                   "eva@vertrieb-brundiers.de", "Eva")
assert mail.weiterleitung(ohne_sig, anfragen.eigene_domains(db)).original.absender == NEUMANN
ok("F1 a: Feld „Weitere eigene E-Mail-Domains“ und E-Mail-Adressen der Arbeitsplätze zählen als intern")

# Sicherheitsnetz: eigene Firma nie als neuer Kunde (keine eigene E-Mail eingetragen, nur der Briefkopf)
db2 = Datenbank(tmp / "zwei.db")
db2.einstellung_setzen("briefkopf_1", "Laser Brundiers GmbH")
_, _, w = anfragen.werte(db2, [], [faelle["Outlook inline"]])
assert w["neuer_kunde"]["email"] == NEUMANN, w.get("neuer_kunde")
_, _, w = anfragen.werte(db2, [], [outlook(INTERN, betreff="Rahmen Halle 3")])
assert "neuer_kunde" not in w, w.get("neuer_kunde")
ok("Sicherheitsnetz: Kollege ohne eingetragene Domain über die Signatur erkannt, eigene Firma nie als neuer Kunde")

# Zusammenfassen: weitergeleitete Anfrage + späterer Nachtrag direkt vom Kunden = eine Anfrage
eingang = tmp / "Eingang"
eingang.mkdir()
(eingang / "WG Anfrage Rahmen.msg").write_bytes(bau.msg("WG: Anfrage Rahmen R-77", INTERN + "\n" + kopf_de(
    "Hans Neumann", NEUMANN, D1, "Anfrage Rahmen R-77") + KUNDE, "Max Kollege", "max@laser.example", D2, STEP))
(eingang / "Nachtrag.msg").write_bytes(bau.msg("AW: Anfrage Rahmen R-77", "Nachtrag: bitte auch 200 Stk.",
                                               "Hans Neumann", NEUMANN, D2 + datetime.timedelta(hours=3)))
alt = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
for p in eingang.iterdir():
    os.utime(p, (alt, alt))
anfragen.EIGENE = set()
assert len(anfragen.suchen(eingang)) == 1 and len(anfragen.suchen(eingang)[0].dateien) == 1
anfragen.EIGENE = anfragen.eigene_domains(db)
gef = anfragen.suchen(eingang)
assert len(gef) == 1 and sorted(d.name for d in gef[0].dateien) == ["Nachtrag.msg", "WG Anfrage Rahmen.msg"], gef
anfragen.EIGENE = set()
ok("Zusammenfassen: weitergeleitete Anfrage und Nachtrag direkt vom Kunden sind eine Anfrage")
print("Alle Tests bestanden.")
