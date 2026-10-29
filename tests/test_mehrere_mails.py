"""Mehrere Mails zur selben Anfrage (Patrick 28.10.2026, „Was ist wenn ein Kunde 2 oder 3 Mails zur gleichen Anfrage
schickt?“, Freigabe „Alle a“): Mails vom selben Absender mit derselben Anfrage-Nr. oder demselben Betreff innerhalb von
3 Tagen sind eine Anfrage (F1), ein Nachtrag ohne STEP gehört dazu bzw. zu einem schon übernommenen Angebot (F2), bei
verschiedenen Angaben gilt die neueste Mail mit Hinweis (F3), bei gleichem Dateinamen die neueste STEP-Version, die
ältere bleibt als „Name (alt)“ (F4). Es gibt keine echten Mails: tests/mail_testdateien.py baut sie.

Aufruf: python tests/test_mehrere_mails.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien as bau  # noqa: E402
from rohrlaser import anfragen, mail, pdf_art  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import KALENDERWOCHE  # noqa: E402


def ok(text):
    print("OK    ", text)


JAHR = datetime.date.today().year + 1           # Wunschtermine in der Zukunft
V1 = b"ISO-10303-21;\nHEADER;\n/* Version 1 */\n" + b"x" * 3000
V2 = b"ISO-10303-21;\nHEADER;\n/* Version 2 */\n" + b"y" * 3000
RIEGEL = b"ISO-10303-21;\nHEADER;\n/* Riegel */\n" + b"z" * 3000
T0 = datetime.datetime(2026, 10, 26, 9, 0)
VON = ("Max Muster", "max.muster@krueger-metall.de")


def schreiben(ordner, name, daten, zeit=None):
    p = ordner / name
    p.write_bytes(daten)
    t = (zeit or datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
    os.utime(p, (t, t))
    return p


# ------------------------------------------------------------------ Zusammenfassen (F1)
assert anfragen.betreff_kern("AW: WG: Anfrage A-5000 Gestell") == "anfrage a-5000 gestell"
assert anfragen.betreff_kern("RE: Anfrage") is None and anfragen.betreff_kern("Angebotsanfrage") is None
tmp = Path(tempfile.mkdtemp())
eingang = tmp / "Eingang"
eingang.mkdir()
schreiben(eingang, "1 Anfrage.msg", bau.msg(
    "Anfrage A-5000 Gestell", f"Guten Tag,\nbitte Angebot:\nTeil1 20 Stk\nRiegel 5 Stk\nMaterial: S355J2H\n"
    f"Liefertermin KW 50/{JAHR}\nGruß Max Muster", *VON, T0, [("Teil1.stp", V1), ("Riegel.stp", RIEGEL)]))
schreiben(eingang, "2 Nachtrag.msg", bau.msg(            # ohne STEP, Antwort auf die erste Mail
    "AW: Anfrage A-5000 Gestell", f"Hallo,\nTeil1 bitte 30 Stk statt 20.\nLiefertermin KW 51/{JAHR}\nGruß Max",
    *VON, T0 + datetime.timedelta(hours=5)))
schreiben(eingang, "3 Neue Version.msg", bau.msg(        # neue Version von Teil1, Anfrage-Nr. nur im Text
    "Geänderte Zeichnung", "Hallo,\nzu unserer Anfrage-Nr. A-5000 anbei Teil1 in neuer Version.\nMaterial 1.4301\n"
    "Gruß Max", "Eva Muster", "eva.muster@krueger-metall.de", T0 + datetime.timedelta(days=1), [("Teil1.stp", V2)]))
schreiben(eingang, "4 Andere Firma.msg", bau.msg(        # gleicher Betreff, andere Firma: eigene Anfrage
    "Anfrage A-5000 Gestell", "Teil9 3 Stk", "Fremd", "info@andere-firma.de", T0, [("Teil9.stp", V1)]))
schreiben(eingang, "5 Viel spaeter.msg", bau.msg(         # gleiche Nr., aber 5 Tage später ohne STEP: nicht dazu
    "AW: Anfrage A-5000 Gestell", "Wie ist der Stand?", *VON, T0 + datetime.timedelta(days=5)))
schreiben(eingang, "6 Freemail.msg", bau.msg(            # Freemail: nur gleiche Adresse zählt
    "AW: Anfrage A-5000 Gestell", "Teil1 99 Stk", "X", "x@gmail.com", T0))
ohne = []
gef = anfragen.suchen(eingang, [], ohne_step=ohne)
assert len(gef) == 2, gef
haupt = next(a for a in gef if len(a.mails) > 1)
assert sorted(d.name for d in haupt.mails) == ["1 Anfrage.msg", "2 Nachtrag.msg", "3 Neue Version.msg"], haupt.mails
assert haupt.name == "1 Anfrage + Nachtrag" and "3 E-Mail" in haupt.text() and "2 STEP" in haupt.text(), haupt.text()
assert sorted(ohne) == ["5 Viel spaeter.msg", "6 Freemail.msg"], ohne
ok("Zusammenfassen: gleiche Anfrage-Nr. bzw. Betreff (ohne AW:) und Firma innerhalb von 3 Tagen, Nachtrag ohne STEP "
   "dazu; andere Firma, Freemail-Fremde und spätere Mails nicht")

# ------------------------------------------------------------------ neueste STEP-Version (F4)
a = anfragen.auspacken(anfragen.sperren(haupt, eingang, "PB"))
assert sorted(d.name for d in a.step) == ["Riegel.stp", "Teil1.stp"], a.step
assert (a.ordner / "Teil1.stp").read_bytes() == V2 and (a.ordner / "Teil1 (alt).stp").read_bytes() == V1
assert a.ordner / "Teil1 (alt).stp" in a.dateien and anfragen.ist_alt(a.ordner / "Teil1 (alt).stp")
anfragen.freigeben(a)
spaeter = datetime.datetime.now() + datetime.timedelta(minutes=1)
a2 = anfragen.auspacken(anfragen.sperren(next(x for x in anfragen.suchen(eingang, [], spaeter) if len(x.mails) > 1),
                                         eingang, "PB"))
assert sorted(p.name for p in a2.ordner.glob("*.stp")) == ["Riegel.stp", "Teil1 (alt).stp", "Teil1.stp"]
anfragen.freigeben(a2)
ok("Gleicher Dateiname: neueste Version gilt, ältere als „Teil1 (alt).stp“ (nicht importiert); zweites Öffnen legt "
   "nichts doppelt an")

# ------------------------------------------------------------------ neueste Mail gilt (F3)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
db.con.execute("INSERT OR REPLACE INTO kunden (kundennr, name, email) VALUES ('10417', 'Metallbau Krüger GmbH', "
               "'max.muster@krueger-metall.de')")
db.con.commit()
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen(anfragen.EINSTELLUNG, str(eingang))
alt_s = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
for p in a2.ordner.iterdir():           # Sperre war gerade geschrieben
    os.utime(p, (alt_s, alt_s))
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
aufrufe = []


def step_importieren(self, dateien=None, *args, **kw):
    aufrufe.append((self.kopf, dateien, kw))
    return {}


orig = AngebotSeite.step_importieren
AngebotSeite.step_importieren = step_importieren
seite = karte.oeffnen([next(x for x in karte.anfragen if len(x.mails) > 1)])
AngebotSeite.step_importieren = orig
kopf, dateien, kw = aufrufe[-1]
assert sorted(Path(d).name for d in dateien) == ["Riegel.stp", "Teil1.stp"], dateien
assert kopf.get("kundenreferenz") == "A-5000" and str(kopf.get("kundennr")) == "10417", kopf
assert kopf.get("lieferzeit_art") == KALENDERWOCHE and kopf.get("lieferzeit_wert") == f"51/{JAHR}", kopf
h = kw["hinweis"]
assert h[0].startswith("3 E-Mails zu dieser Anfrage") and "27.10. 09:00" in h[0], h
assert any("26.10. 09:00 nennt KW 50" in x and "es gilt die neueste" in x for x in h), h
assert any("nennt Werkstoff S355J2H" in x and "es gilt 1.4301" in x for x in h), h
assert mail.werkstoff(kw["werkstoff_text"], db.zeilen("werkstoffe"))[1] == "1.4301", kw["werkstoff_text"][:80]
ziel = fenster.angebot_ordner(seite.kopf)
assert sorted(p.name for p in (ziel / "STEP").iterdir()) == ["Riegel.stp", "Teil1 (alt).stp", "Teil1.stp"]
assert len(list((ziel / anfragen.ZIEL_FORMULAR).glob("*.msg"))) == 3
ok("Öffnen: Lieferzeit und Werkstoff aus der neuesten Mail, ältere Angaben als Hinweis; nur die neue STEP wird "
   "importiert, alle Mails und die alte Version wandern in den Angebotsordner")

mw = [dict(datei="Teil1.stp", artikel="Teil1"), dict(datei="Riegel.stp", artikel="Riegel")]
pdf_art.anwenden(mw, kw["formulare"])
assert mw[0]["_stueck"] == 30 and "26.10. 14:00" in mw[0]["_stueck_quelle"], mw[0]
assert mw[0]["_stueck_anders"] == "E-Mail vom 26.10. 09:00: 20", mw[0]
assert mw[1]["_stueck"] == 5 and "_stueck_anders" not in mw[1], mw[1]
# neueste Mail nennt die Zahl nur unsicher (ohne „Stk“), die ältere sicher: trotzdem gilt die neueste
unsicher = [dict(text="Betreff: AW\nTeil1 30", mail=True, quelle="der E-Mail vom 27.10. 10:00"),
            dict(text="Betreff: Anfrage\nTeil1 20 Stk", mail=True, quelle="der E-Mail vom 26.10. 09:00")]
mw3 = [dict(datei="Teil1.stp", artikel="Teil1")]
pdf_art.anwenden(mw3, unsicher)
assert mw3[0]["_stueck"] == 30 and mw3[0]["_stueck_anders"] == "E-Mail vom 26.10. 09:00: 20", mw3[0]
mw4 = [dict(datei="Teil1.stp", artikel="Teil1")]           # ein Anfrageformular geht weiter vor
pdf_art.anwenden(mw4, [dict(text="Pos 10 Teil1 12 Stk")] + unsicher)
assert mw4[0]["_stueck"] == 12, mw4[0]
# Mail ohne Sendedatum: zählt mit der Änderungszeit der Datei
ohne_datum = tmp / "ohne_datum.eml"
ohne_datum.write_bytes(bau.eml("AW: Anfrage A-5000", f"Liefertermin KW 52/{JAHR}", *VON))
mit = mail.Mail(*VON, T0, "Anfrage A-5000", f"Liefertermin KW 50/{JAHR}")
_, _, w = anfragen.werte(db, [], [mit, mail.lesen(ohne_datum)])
assert any(f"KW 52/{JAHR}" in h and h.startswith("Lieferzeit") for h in w["hinweis"]), w["hinweis"]
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
k = db.kontext()
mw2 = [dict(datei="Teil1.stp", artikel="Teil1", bauteil="Teil1", profilform="Rundrohr",
            profil_id_vorschlag=next(iter(k.profile)), laenge=500, pruefstatus="plausibel", schneidweg=100)]
pdf_art.anwenden(mw2, kw["formulare"])
dlg = StepPruefDialog(None, mw2, k, "1.4301", 1, vorpruefung=lambda: ([], 0), hinweis=h)
z = dlg.zeilen[0]
assert z.sp.value() == 30 and "Andere Angabe: E-Mail vom 26.10. 09:00: 20" in z.sp.toolTip(), z.sp.toolTip()
assert "background" in z.sp.styleSheet()
ok("Stückzahl aus der neuesten Mail; andere Zahl einer älteren Mail im Tooltip, Feld gelb")

# ------------------------------------------------------------------ Nachtrag zu einem übernommenen Angebot (F2)
schreiben(eingang, "7 Nachtrag spaeter.msg", bau.msg(
    "AW: Anfrage A-5000 Gestell", "Bitte noch Pulverbeschichtung mit anbieten.", *VON,
    datetime.datetime.now() - datetime.timedelta(hours=1)))
karte.neu_laden(erzwingen=True)
assert f"Nachtrag zu Angebot <b>{seite.kopf['nummer']}</b>: 7 Nachtrag spaeter.msg" in karte.hinweis.text(), \
    karte.hinweis.text()
nr = seite.kopf["nummer"]
assert f"Nachtrag zu Angebot <b>{nr}</b>: 5 Viel spaeter.msg" in karte.hinweis.text()
assert "Ohne STEP (nicht in der Liste, z. B. nur Zeichnung als PDF): 6 Freemail.msg –" in karte.hinweis.text(), \
    karte.hinweis.text()       # gleiche Nummer, aber nicht vom Kunden des Angebots
ok("Nachtrag ohne STEP zu einem schon übernommenen Angebot (nur vom Kunden des Angebots): Hinweis „Nachtrag zu "
   "Angebot …“ auf der Startseite")

# ------------------------------------------------------------------ Mails aufs Programm gezogen
ordner = tmp / "Kunden" / "Krüger"
ordner.mkdir(parents=True)
schreiben(ordner, "neu.msg", bau.msg("AW: Gestell", "Teil1 neue Version", *VON, T0 + datetime.timedelta(days=1),
                                     [("Teil1.stp", V2)]))
schreiben(ordner, "alt.msg", bau.msg("Gestell", "Teil1 4 Stk", *VON, T0, [("Teil1.stp", V1)]))
AngebotSeite.step_importieren = step_importieren
fenster.angebote.neu_aus_step([str(ordner / "neu.msg"), str(ordner / "alt.msg")])
AngebotSeite.step_importieren = orig
_, dateien, _ = aufrufe[-1]
assert [Path(d).name for d in dateien] == ["Teil1.stp"], dateien
assert (ordner / "Teil1.stp").read_bytes() == V2 and (ordner / "Teil1 (alt).stp").read_bytes() == V1
AngebotSeite.step_importieren = step_importieren
fenster.angebote.neu_aus_step([str(ordner)])
AngebotSeite.step_importieren = orig
assert [Path(d).name for d in aufrufe[-1][1]] == ["Teil1.stp"], aufrufe[-1][1]
ok("Zwei Mails gezogen (auch in falscher Reihenfolge): neueste STEP gilt, die alte liegt als „(alt)“ daneben und wird "
   "auch beim Ziehen des Ordners nicht importiert")

print("Alle Tests bestanden.")
