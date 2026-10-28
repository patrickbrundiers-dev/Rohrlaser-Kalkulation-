"""E-Mail der Anfrage lesen (Patrick 28.10.2026, „Outlook-Datei auslesen“, Freigabe „Alles umsetzen“ = F1-F4 a):
.msg (Outlook) und .eml mit Absender, Datum, Betreff, Text, Anhängen, ZIP und weitergeleiteter Mail; Kunde über
Absenderadresse/Domain (F1), Wunschtermin als Lieferzeit (F2), interne Bemerkung (F3), Werkstoff nur eindeutig (F4);
im Anfrage-Ordner zählt eine Mail mit STEP-Anhang als Anfrage, die Anhänge werden beim Öffnen ausgepackt und die Mail
wandert in den Angebotsordner. Es gibt keine echten Mails: tests/mail_testdateien.py baut sie nach MS-OXMSG.

Aufruf: python tests/test_mail.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien as bau  # noqa: E402
from rohrlaser import anfragen, mail  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import KALENDERWOCHE, LIEFERDATUM  # noqa: E402


def ok(text):
    print("OK    ", text)


HEUTE = datetime.date(2026, 10, 28)
GESENDET = datetime.datetime(2026, 10, 28, 9, 30)
STEP = b"ISO-10303-21;\nHEADER;\n" + b"x" * 5000           # > 4096 Byte: liegt im .msg nicht im Mini-Stream
KW_IN3 = (datetime.date.today() + datetime.timedelta(weeks=3)).isocalendar()        # Wunschtermin in 3 Wochen
TEXT = ("Guten Tag,\n\nbitte um Angebot für folgende Teile:\nMG-01 Stiel  20 Stk\nMG-02 Riegel 8 Stk\n"
        "Material: 1.4301\nLiefertermin KW {kw}\n\nMit freundlichen Grüßen\nMax Muster\nMetallbau Krüger GmbH")
TEXT_HEUTE = TEXT.format(kw=47)
TEXT = TEXT.format(kw=KW_IN3[1])


def zip_mit(*dateien):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for n, d in dateien:
            z.writestr(n, d)
    return puffer.getvalue()


# ------------------------------------------------------------------ .msg lesen
roh = bau.msg("Anfrage Nr. A-4711 Gestell", TEXT, "Max Muster", "Max.Muster@krueger-metall.de", GESENDET,
              [("MG-01 Stiel.stp", STEP), ("Zeichnungen.zip", zip_mit(("Unterordner/MG-02 Riegel.step", b"STEP2"),
                                                                        ("Bestellung.pdf", b"%PDF-1.4"))),
               ("logo.png", b"\x89PNG")])
m = mail.aus_bytes(roh)
assert m.betreff == "Anfrage Nr. A-4711 Gestell" and m.absender == "max.muster@krueger-metall.de", m
assert m.absender_name == "Max Muster" and m.domain == "krueger-metall.de"
assert m.datum is not None and m.datum.date() == GESENDET.date(), m.datum
assert "MG-01 Stiel  20 Stk" in m.text
assert [n for n, _ in m.anhaenge] == ["MG-01 Stiel.stp", "MG-02 Riegel.step", "Bestellung.pdf", "logo.png"], m.anhaenge
assert dict(m.anhaenge)["MG-01 Stiel.stp"] == STEP
assert mail.aus_bytes(b"kein Compound File") is None and mail.aus_bytes(roh[:600]) is None
ok(".msg: Betreff, Absender, Sendezeit, Text, Anhänge (großer Anhang, ZIP mit Unterordner ausgepackt)")

weiter = bau.msg("WG: Anfrage 4711", "Kollege, bitte kalkulieren.", "Patrick", "patrick@laser.example", GESENDET,
                 [("Anfrage 4711", dict(betreff="Anfrage 4711", text=TEXT, absender_name="Max Muster",
                                        absender="max@krueger-metall.de", datum=GESENDET,
                                        anhaenge=[("MG-01 Stiel.stp", STEP)]))])
w = mail.aus_bytes(weiter)
assert [n for n, _ in w.anhaenge] == ["MG-01 Stiel.stp"] and "Weitergeleitete Nachricht" in w.text
assert "max@krueger-metall.de" in w.text and "MG-02 Riegel 8 Stk" in w.text
html = mail.aus_bytes(bau.msg("Anfrage", None, "A", "a@b.de", None, [],
                              html="<html><head><style>p{}</style></head><body><p>Menge&nbsp;5 Stk</p><table><tr>"
                                   "<td>MG-01</td><td>3</td></tr></table></body></html>"))
assert html.text == "Menge 5 Stk\nMG-01\t3", repr(html.text)
alt = mail.aus_bytes(bau.msg("Größe", "Über 10 Stück", ansi=True))
assert alt.betreff == "Größe" and alt.text == "Über 10 Stück"
ok(".msg: weitergeleitete Mail (Anhänge und Text), reine HTML-Mail, alte Datei mit cp1252")

e = mail.aus_bytes(bau.eml("AW: Anfrage RFQ-77", "Bitte 5 Stk MG-01", "Eva Kunde", "Eva@Kunde.de", GESENDET,
                           [("MG-01 Stiel.step", STEP), ("p.zip", zip_mit(("B.stp", b"B")))]), ".eml")
assert e.absender == "eva@kunde.de" and e.betreff == "AW: Anfrage RFQ-77" and e.datum.date() == GESENDET.date()
assert [n for n, _ in e.anhaenge] == ["MG-01 Stiel.step", "B.stp"] and "5 Stk" in e.text
assert mail.aus_bytes(b"irgendein Text ohne Kopf", ".eml") is None
bomb = zip_mit(("gross.step", b"0" * (mail.ZIP_MAX + 1)))
assert mail.zip_inhalt(bomb) == [] and mail.sauber("..\\..\\a:b?.stp") == "a_b_.stp"
ok(".eml: Absender, Datum, Anhänge, ZIP; zu große ZIP-Inhalte übersprungen, Dateinamen ohne Pfad")

# ------------------------------------------------------------------ Auswertung (F1-F4)
kunden = [dict(kundennr="10417", name="Metallbau Krüger GmbH", email="einkauf@krueger-metall.de"),
          dict(kundennr="10500", name="Hessler", email="max.muster@hessler.de; info@hessler.de"),
          dict(kundennr="10600", name="Privat", email="otto@gmail.com"),
          dict(kundennr="10700", name="Zweite Firma", email="a@doppelt.de"),
          dict(kundennr="10701", name="Dritte Firma", email="b@doppelt.de")]
eigen = mail.eigene_domains(["Laser GmbH", "Tel. 0123 / info@laser.example", "patrick@laser.example"])
assert eigen == {"laser.example"}
assert mail.kunde(mail.Mail(absender="max.muster@hessler.de"), kunden, eigen) == ("10500", "Absender max.muster@hessler.de")
assert mail.kunde(m, kunden, eigen) == ("10417", "Domain @krueger-metall.de")
assert mail.kunde(w, kunden, eigen)[0] == "10417"          # weitergeleitet: eigener Absender zählt nicht
assert mail.kunde(mail.Mail(absender="otto@gmail.com"), kunden) == ("10600", "Absender otto@gmail.com")
assert mail.kunde(mail.Mail(absender="fremd@gmail.com"), kunden) == (None, "")      # Freemail: keine Domain
assert mail.kunde(mail.Mail(absender="c@doppelt.de"), kunden) == (None, "")         # zwei Kunden: nicht raten
ok("F1 Kunde: genaue Adresse, sonst Domain (nicht Freemail, nicht mehrdeutig), weitergeleitet ohne eigene Domain")

assert mail.termin(TEXT_HEUTE, HEUTE) == (KALENDERWOCHE, "47/2026", "Liefertermin KW 47")
assert mail.termin("Wir benötigen die Teile bis 20.11.", HEUTE)[:2] == (LIEFERDATUM, "2026-11-20")
assert mail.termin("Liefertermin: 15.01.", HEUTE)[:2] == (LIEFERDATUM, "2027-01-15")
assert mail.termin("Bitte senden Sie uns Ihr Angebot bis 30.10.2026.", HEUTE)[0] is None     # Angebotsfrist
assert mail.termin("Liefertermin KW 46 oder KW 47", HEUTE)[0] is None                     # zwei Termine: offen
assert mail.termin("Liefertermin war der 1.10.", HEUTE)[0] is None                       # vorbei
assert mail.termin("> Liefertermin KW 46", HEUTE)[0] is None                             # zitiert
ok("F2 Wunschtermin: KW bzw. Datum nur aus Liefer-/Bedarfssätzen, eindeutig, nicht vorbei, nicht zitiert")

assert mail.bemerkung(m) == "E-Mail von Max Muster <max.muster@krueger-metall.de> vom 28.10.2026 09:30: " \
    "Anfrage Nr. A-4711 Gestell", mail.bemerkung(m)
ok("F3 interne Bemerkung mit Absender, Zeit und Betreff")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
ws = db.zeilen("werkstoffe")
assert mail.werkstoff("Material: 1.4301", ws)[0] == "1.4301"
assert mail.werkstoff("Edelstahl V2A geschliffen", ws)[0] == "1.4301"
assert mail.werkstoff("Material S235", ws)[0] is None and mail.werkstoff("Material S235", ws)[1] == "S235"
assert mail.werkstoff("Material S235", ws, "S235-10219")[0] == "S235-10219"     # Vorgabe passt: bleibt
assert mail.werkstoff("Rohre S235JRH, Laschen 1.4301", ws, "S235-10219")[0] is None   # zwei Werkstoffe: offen
assert mail.werkstoff("Bitte um Angebot", ws) == (None, "", [])
ok("F4 Werkstoff: nur eindeutig (Nr., V2A, Vorgabe bei mehreren passenden), sonst nur Hinweis")

# ------------------------------------------------------------------ Anfrage-Ordner
tmp = Path(tempfile.mkdtemp())
eingang = tmp / "Eingang"
eingang.mkdir()
alt_s = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
(eingang / "Anfrage Krüger.msg").write_bytes(roh)
(eingang / "Newsletter.msg").write_bytes(bau.msg("Newsletter", "ohne Anhang"))     # ohne STEP: keine Anfrage
for p in eingang.iterdir():
    os.utime(p, (alt_s, alt_s))
gef = anfragen.suchen(eingang, kunden)
assert len(gef) == 1 and [d.name for d in gef[0].mails] == ["Anfrage Krüger.msg"], gef
assert "2 STEP" in gef[0].text() and "1 E-Mail" in gef[0].text(), gef[0].text()
a = anfragen.auspacken(anfragen.sperren(gef[0], eingang, "PB"))
assert sorted(d.name for d in a.step) == ["MG-01 Stiel.stp", "MG-02 Riegel.step"], a.dateien
assert [d.name for d in a.formulare] == ["Bestellung.pdf"] and not (a.ordner / "logo.png").exists()
anfragen.freigeben(a)
spaeter = datetime.datetime.now() + datetime.timedelta(minutes=1)      # ausgepackte Dateien sind ganz neu
a2 = anfragen.auspacken(anfragen.sperren(anfragen.suchen(eingang, kunden, spaeter)[0], eingang, "PB"))
assert sorted(p.name for p in a2.ordner.iterdir() if p.suffix != ".msg" and not p.name.startswith(".")) == \
    ["Bestellung.pdf", "MG-01 Stiel.stp", "MG-02 Riegel.step"], list(a2.ordner.iterdir())
anfragen.freigeben(a2)
for p in a2.ordner.iterdir():
    os.utime(p, (alt_s, alt_s))
ok("Anfrage-Ordner: Mail mit STEP-Anhang ist eine Anfrage (Mail ohne nicht), Anhänge ausgepackt, nach Abbruch "
   "nicht doppelt")

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
db.con.executemany("INSERT OR REPLACE INTO kunden (kundennr, name, email) VALUES (?, ?, ?)",
                   [(k["kundennr"], k["name"], k["email"]) for k in kunden])
db.con.commit()
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("benutzer_email", "patrick@laser.example")
db.einstellung_setzen(anfragen.EINSTELLUNG, str(eingang))
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
assert karte.liste.count() == 1
aufrufe = []


def step_importieren(self, dateien=None, *args, **kw):
    aufrufe.append((self.kopf, dateien, kw))
    return {}


ausp = anfragen.auspacken


def voll(_a):
    raise OSError("Datenträger voll")


anfragen.auspacken = voll                   # Auspacken scheitert: Sperre wird wieder aufgehoben
assert karte.oeffnen([karte.anfragen[0]]) is None
assert anfragen.sperre_lesen(karte.anfragen[0].ordner) is None, "Sperre nach Fehler beim Auspacken"
anfragen.auspacken = ausp
orig = AngebotSeite.step_importieren
AngebotSeite.step_importieren = step_importieren
seite = karte.oeffnen([karte.anfragen[0]])
AngebotSeite.step_importieren = orig
assert seite is not None
kopf, dateien, kw = aufrufe[-1]
assert str(kopf.get("kundennr")) == "10417", kopf.get("kundennr")
assert kopf.get("kundenreferenz") == "A-4711", kopf.get("kundenreferenz")
assert kopf.get("lieferzeit_art") == KALENDERWOCHE and kopf.get("lieferzeit_wert") == f"{KW_IN3[1]}/{KW_IN3[0]}", kopf
assert kopf.get("bemerkung", "").startswith("E-Mail von Max Muster"), kopf.get("bemerkung")
assert any("Domain @krueger-metall.de" in h for h in kw["hinweis"]) and any(f"KW {KW_IN3[1]}" in h for h in kw["hinweis"])
assert "1.4301" in kw["werkstoff_text"] and kw["referenz"] == "A-4711"
assert any(f.get("mail") and "MG-01 Stiel  20 Stk" in f["text"] for f in kw["formulare"])
assert sorted(Path(d).name for d in dateien) == ["MG-01 Stiel.stp", "MG-02 Riegel.step"]
ziel = fenster.angebot_ordner(seite.kopf)
assert sorted(p.name for p in (ziel / "STEP").iterdir()) == ["MG-01 Stiel.stp", "MG-02 Riegel.step"]
assert sorted(p.name for p in (ziel / anfragen.ZIEL_FORMULAR).iterdir()) == ["Anfrage Krüger.msg", "Bestellung.pdf"]
assert (eingang / "Newsletter.msg").exists() and len(list(eingang.iterdir())) == 1
ok("Öffnen: Kunde aus Absender, Anfrage-Nr. aus Betreff, Lieferzeit (KW), Bemerkung, Werkstoff-Text und Mailtext "
   "für Stückzahlen an den Import; STEP und Mail in den Angebotsordner")

kunden_ordner = tmp / "Kunden" / "Unbekannt GmbH"
kunden_ordner.mkdir(parents=True)
(kunden_ordner / "Anfrage.msg").write_bytes(roh)
AngebotSeite.step_importieren = step_importieren
seite2 = fenster.angebote.neu_aus_step([str(kunden_ordner)])
AngebotSeite.step_importieren = orig
kopf2, dateien2, kw2 = aufrufe[-1]
assert seite2 is not None and str(kopf2.get("kundennr")) == "10417" and kopf2.get("kundenreferenz") == "A-4711"
assert sorted(Path(d).name for d in dateien2) == ["MG-01 Stiel.stp", "MG-02 Riegel.step"], dateien2
assert (kunden_ordner / "MG-01 Stiel.stp").read_bytes() == STEP and kw2["hinweis"] and kw2["werkstoff_text"]
AngebotSeite.step_importieren = step_importieren
fenster.angebote.neu_aus_step([str(kunden_ordner / "Anfrage.msg")])            # zweimal: nicht doppelt ausgepackt
AngebotSeite.step_importieren = orig
assert len(list(kunden_ordner.glob("MG-01 Stiel*"))) == 1
from rohrlaser.angebot_fenster import step_neu_pfade  # noqa: E402
from PySide6.QtCore import QMimeData, QUrl  # noqa: E402


class Zug:
    def __init__(self, pfade):
        self.d = QMimeData()
        self.d.setUrls([QUrl.fromLocalFile(str(x)) for x in pfade])

    def mimeData(self):
        return self.d


assert step_neu_pfade(Zug([kunden_ordner / "Anfrage.msg"])) and not step_neu_pfade(Zug([tmp / "x.txt"]))
ok("Kundenordner oder .msg auf das Programm gezogen: STEP-Anhänge neben die Mail, Kopf wie im Anfrage-Ordner")

# echter Import (ohne Dialog): eindeutiger Werkstoff aus dem Mailtext ersetzt die Vorgabe, mehrdeutiger nicht
s1 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr="10417")))
s1.step_importieren([str(HIER / "step" / "T01_RR42-4x2_L1250.step")], werkstoff_text="Werkstoff: V2A (1.4301)")
assert {p.get("werkstoff_id") for p in s1.positionen if p.get("profil_id")} == {"1.4301"}, s1.positionen
s2 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr="10417")))
s2.step_importieren([str(HIER / "step" / "T01_RR42-4x2_L1250.step")], werkstoff_text="S355J2H oder 1.4301")
assert {p.get("werkstoff_id") for p in s2.positionen if p.get("profil_id")} != {"1.4301"}, s2.positionen
ok("Import: Werkstoff aus der Mail nur, wenn eindeutig")

from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
k = db.kontext()
mw = [dict(datei="x.step", artikel="T1", bauteil="T1", profilform="Rundrohr", profil_id_vorschlag=next(iter(k.profile)),
           laenge=500, pruefstatus="plausibel", schneidweg=100)]
dlg = StepPruefDialog(None, mw, k, "1.4301", 1, vorpruefung=lambda: ([], 0), hinweis=kw["hinweis"])
assert dlg.mail_hinweis is not None and "Aus der E-Mail" in dlg.mail_hinweis.text() and "KW" in dlg.mail_hinweis.text()
assert StepPruefDialog(None, [dict(mw[0])], k, "1.4301", 1, vorpruefung=lambda: ([], 0)).mail_hinweis is None
ok("Prüfdialog zeigt „Aus der E-Mail: …“ (nur mit Mail)")
print("Alle Tests bestanden.")
