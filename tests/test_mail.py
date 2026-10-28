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
# ------------------------------------------------------------------ robuster und intelligenter (0.9.166)
RTF = (b"{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}\\pard Bitte 5 Stk MG-01\\par Material 1.4301\\par Gr\\'fc\\'dfe\\par}")
r = mail.aus_bytes(bau.msg_rtf("Alt", bau.rtf_mela(RTF), [("A.stp", b"x")]))
assert r.text == "Bitte 5 Stk MG-01\nMaterial 1.4301\nGrüße" and r.anhaenge == [("A.stp", b"x")], r.text
spez = bytes.fromhex("2d0000002b0000004c5a4675f1c5c7a703000a007263706731323542320af32068656c090020627705b06c647d0a800fa0")
assert mail.rtf_entpacken(spez) == b"{\\rtf1\\ansi\\ansicpg1252\\pard hello world}\r\n"        # Beispiel aus MS-OXRTFCP
assert mail.rtf_text(b"{\\rtf1\\ansi\\fromhtml1{\\*\\htmltag <p>}Menge 7 Stk{\\*\\htmltag </p>}\\htmlrtf{\\par}"
                     b"\\htmlrtf0}") == "Menge 7 Stk"
ok("alte Outlook-Datei nur mit RTF-Text (komprimiert und unkomprimiert, auch aus HTML)")

winmail = bau.tnef([("MG-01 Stiel lang.stp", STEP)])
assert mail.tnef_anhaenge(winmail) == [("MG-01 Stiel lang.stp", STEP)]
assert mail.tnef_anhaenge(bau.tnef([("Teil.stp", b"S")], lang=False)) == [("TEIL~1.STP", b"S")]
assert [n for n, _ in mail.aus_bytes(bau.eml("A", "s. Anhang", "K", "k@x.de", None, [("winmail.dat", winmail)]),
                                     ".eml").anhaenge] == ["MG-01 Stiel lang.stp"]
assert [n for n, _ in mail.aus_bytes(bau.msg("A", "s. Anhang", "K", "k@x.de", None,
                                             [("winmail.dat", winmail)])).anhaenge] == ["MG-01 Stiel lang.stp"]
assert mail.tnef_anhaenge(winmail[:40]) == []                                        # abgeschnitten: nichts
assert mail.sauber("CON.stp") == "_CON.stp" and mail.sauber("x" * 300 + ".step").endswith(".step")
assert len(mail.sauber("x" * 300 + ".step")) <= 150
ok("winmail.dat in .eml und .msg ausgepackt (langer Name), Windows-Sondernamen und lange Namen")

pfad = tmp / "zwischen.msg"
pfad.write_bytes(roh)
assert mail.lesen(pfad) is mail.lesen(pfad)                     # zwischengespeichert
pfad.write_bytes(bau.msg("Neu", "anders"))
os.utime(pfad, (alt_s + 60, alt_s + 60))
assert mail.lesen(pfad).betreff == "Neu"                        # geändert: neu gelesen
ok("Mail wird je Datei nur einmal gelesen, nach Änderung neu")

VERLAUF = "Neu: bitte Liefertermin KW 50\n\n-----Ursprüngliche Nachricht-----\nVon: x\nLiefertermin KW 46"
assert mail.termin(VERLAUF, HEUTE)[:2] == (KALENDERWOCHE, "50/2026")            # neueste Nachricht zählt
assert mail.termin("Lieferung in 3 Wochen", HEUTE)[:2] == ("Wochen", "3")
assert mail.termin("Liefertermin innerhalb von 10 Arbeitstagen", HEUTE)[:2] == ("Arbeitstage", "10")
assert mail.werkstoff("Material 1.4301\n\n-----Ursprüngliche Nachricht-----\nMaterial S355", ws)[0] == "1.4301"
ok("Antwortverlauf: neueste Nachricht zuerst; Lieferzeit auch als Dauer (Wochen, Arbeitstage)")

kd = [dict(kundennr="1", name="Schmitz Stahlbau GmbH", email=""), dict(kundennr="2", name="Anders", email="")]
assert mail.kunde_aus_domain(mail.Mail(absender="a@schmitz-stahlbau.de"), kd)[0] == "1"
assert mail.kunde_aus_domain(mail.Mail(absender="a@ganz-anders.de"), kd)[0] is None
assert mail.staffel_mengen("Bitte Preise für 10 / 50 / 100 Stk") == [10, 50, 100]
assert mail.staffel_mengen("MG-01 20 Stk") == []
assert mail.zusatz_erwaehnt("Teile bitte verzinkt und entgratet", ["Verzinken", "Entgraten", "Lackieren"]) == \
    [("Verzinken", "verzinkt"), ("Entgraten", "entgratet")]
ok("Kunde über Domain im Namen (nur eindeutig), Mengenstaffel und Zusatzarbeiten nur als Hinweis")

SIG = ("Hallo,\nAnfrage anbei.\n\nMit freundlichen Grüßen\nJens Neu\nNeu Blechtechnik GmbH\nIndustriestr. 12\n"
       "58093 Hagen\nTel. +49 2331 12345-0\n")
neu_m = mail.Mail(absender="jens@neu-blech.de", absender_name="Jens Neu", text=SIG)
assert mail.kunde_daten(neu_m) == dict(email="jens@neu-blech.de", ansprechpartner="Jens Neu",
                                       name="Neu Blechtechnik GmbH", telefon="+49 2331 12345-0", plz="58093",
                                       plz_ort="58093 Hagen", land="DE", strasse="Industriestr. 12"), \
    mail.kunde_daten(neu_m)
assert mail.kunde_daten(mail.Mail(absender="info@stahl-otto.de", text="Gruß"))["name"] == "Stahl Otto"
assert mail.kunde_daten(mail.Mail(absender="patrick@laser.example"), "", {"laser.example"}) is None
assert mail.neue_kundennr(["10417", "10500", "K-0099"]) == "10501" and mail.neue_kundennr([]) == "10001"
assert mail.neue_kundennr(["K-0099"]) == "K-0100"
ok("neuer Kunde: Firma, Ansprechpartner, Straße, PLZ/Ort, Telefon aus Signatur; nächste Kundennummer")

_, _, wf = anfragen.werte(db, [dict(text="Anfrage-Nr. 4711\nLiefertermin KW 50\nMengen 10/20/50 Stk", ocr=False,
                                    unsicher=set())], [], "10417")
assert wf["kopf"]["lieferzeit_wert"] == f"50/{HEUTE.year}" or wf["kopf"]["lieferzeit_art"] == KALENDERWOCHE, wf
assert any("10 / 20 / 50" in h for h in wf["hinweis"]), wf["hinweis"]
assert any("A-4711" in h and "gibt es schon" in h for h in anfragen.werte(db, [], [m])[2]["hinweis"])
kaputt = mail.Mail(absender="x@y.de")
kaputt.volltext = None                                          # Fehler in der Auswertung: kein Absturz
k3, n3, w3 = anfragen.werte(db, [], [kaputt], "10417")
assert k3 == "10417" and "teilweise" in w3["hinweis"][0], w3
ok("Anfrageformular wie die Mail ausgewertet (Lieferzeit, Staffel), doppelte Anfrage-Nr., Fehler abgefangen")

neu_ordner = tmp / "Kunden" / "Irgendwo"
neu_ordner.mkdir(parents=True)
(neu_ordner / "Anfrage.msg").write_bytes(bau.msg("Anfrage Gestell", SIG, "Jens Neu", "jens@neu-blech.de", GESENDET,
                                                  [("Teil 9.stp", STEP)]))
vorher = {k["kundennr"] for k in db.zeilen("kunden")}
AngebotSeite.step_importieren = lambda self, *a, **kw: None     # abgebrochen
assert fenster.angebote.neu_aus_step([str(neu_ordner)]) is None
assert {k["kundennr"] for k in db.zeilen("kunden")} == vorher, "Kunde nach Abbruch nicht entfernt"
AngebotSeite.step_importieren = step_importieren
seite3 = fenster.angebote.neu_aus_step([str(neu_ordner)])
AngebotSeite.step_importieren = orig
neu_k = [k for k in db.zeilen("kunden") if k["kundennr"] not in vorher]
assert len(neu_k) == 1 and neu_k[0]["name"] == "Neu Blechtechnik GmbH" and neu_k[0]["email"] == "jens@neu-blech.de"
assert neu_k[0]["bemerkung"].startswith("Kunde prüfen") and neu_k[0]["plz_ort"] == "58093 Hagen", neu_k[0]
assert str(seite3.kopf.get("kundennr")) == neu_k[0]["kundennr"] == "10702", seite3.kopf
assert any("Neuer Kunde" in h for h in aufrufe[-1][2]["hinweis"])
ok("unbekannter Absender: Kunde angelegt mit „Kunde prüfen“, bei Abbruch wieder entfernt")
print("Alle Tests bestanden.")
