"""Anhänge mit Rolle und Revision, Nachträge als Änderung (Patrick 20.11.2026, Plan K4/K5, „Alles einbauen“).

  B1 Dateityp nach Inhalt (STEP, PDF, ZIP, OLE, PNG, JPG, DXF, DWG, leer); Endung passt nicht -> Hinweis
  B2 Rollen: 3D-Modell, Zeichnung, Stückliste, Anfrageformular, Bild, Archiv, Mail, Unbekannt, Beschädigt, Zu groß
  B3 Revision aus dem Dateinamen; neuer Stand derselben Basis (alt bleibt), STEP + Zeichnung = ein Teil
  B4 Nachträge: geänderte Stückzahl, neue Revision, neuer Wert; nichts wird übernommen
  B5 Seite „Anfragen“: Rolle/Revision in Anhängen und im Reiter Dokumente, Block „Geänderte Angaben aus Nachträgen“,
     „Gesehen“ im Verlauf; beschädigter und unbekannter Anhang halten nichts auf

Aufruf: python tests/test_anhang_analyse.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

import mail_testdateien as t  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import anhang_analyse as an  # noqa: E402
from rohrlaser import mail  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())


def datei(name, daten):
    p = tmp / name
    p.write_bytes(daten)
    return p


# ---------------------------------------------------------------------------------------------- B1
FAELLE = {"a.step": (b"ISO-10303-21;\nHEADER;", "step"), "a.pdf": (b"%PDF-1.7\n", "pdf"),
          "a.xlsx": (b"PK\x03\x04rest", "zip"), "a.msg": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", "ole"),
          "a.png": (b"\x89PNG\r\n", "png"), "a.jpg": (b"\xff\xd8\xff\xe0", "jpg"),
          "a.dxf": (b"  0\nSECTION\n  2\nHEADER\n", "dxf"), "a.dwg": (b"AC1027rest", "dwg"), "leer.pdf": (b"", "leer")}
for name, (daten, soll) in FAELLE.items():
    typ, hinweis = an.dateityp(datei(name, daten))
    assert typ == soll and (not hinweis or soll == "leer"), (name, typ, hinweis)
typ, hinweis = an.dateityp(datei("falsch.pdf", b"PK\x03\x04zip"))
assert typ == "zip" and "passt nicht" in hinweis, hinweis
assert an.dateityp(tmp / "gibtsnicht.pdf") == (None, "Datei nicht lesbar")
ok("B1 Dateityp nach Inhalt, Endung passt nicht -> Hinweis")

# ---------------------------------------------------------------------------------------------- B2
R = {"Halter.step": an.MODELL, "Halter.pdf": an.ZEICHNUNG, "Halter.dxf": an.ZEICHNUNG,
     "Stueckliste.xlsx": an.STUECKLISTE, "Anfrage_4711.pdf": an.FORMULAR, "Formular.docx": an.FORMULAR,
     "Foto.jpg": an.BILD, "Daten.zip": an.ARCHIV, "Mail.msg": an.MAIL, "x.abc": an.UNBEKANNT}
for name, soll in R.items():
    assert an.rolle(dict(name=name, groesse=100)) == soll, (name, an.rolle(dict(name=name, groesse=100)))
assert an.rolle(dict(name="riesig.step", groesse=60 * 1024 * 1024)) == an.GROSS
assert an.rolle(dict(name="kaputt.pdf", groesse=10), "zip") == an.KAPUTT
assert an.rolle(dict(name="leer.step", groesse=0), "leer") == an.KAPUTT
ok("B2 Rollen inkl. beschädigt, zu groß, unbekannt")

# ---------------------------------------------------------------------------------------------- B3
assert an.revision_aus_name("Halter_RevB.pdf") == ("halter", "B")
assert an.revision_aus_name("Halter-v2.step") == ("halter", "2")
assert an.revision_aus_name("Halter_Index_c.dxf") == ("halter", "C")
assert an.revision_aus_name("Halter (Rev. 03).pdf") == ("halter", "03")
assert an.revision_aus_name("Halter (1).pdf") == ("halter", "")
assert an.revision_aus_name("4711-02.step") == ("471102", "")
liste = an.analyse([dict(name=n, pfad=datei(n, d), groesse=len(d)) for n, d in (
    ("Halter_RevA.pdf", b"%PDF-1.4"), ("Halter_RevB.pdf", b"%PDF-1.4"), ("Halter.step", b"ISO-10303-21;"),
    ("Deckel.pdf", b"%PDF-1.4"), ("kaputt.pdf", b""), ("Plan.dwg", b"AC1027"), ("x.abc", b"\x00\x01"))])
x = {e["name"]: e for e in liste}
assert x["Halter_RevB.pdf"]["neuer_stand_von"] == "Halter_RevA.pdf" and not x["Halter_RevA.pdf"]["neuer_stand_von"]
assert x["Halter.step"]["gruppe"] == "halter" and x["Halter_RevB.pdf"]["gruppe"] == "halter"
assert not x["Deckel.pdf"]["gruppe"]
assert x["kaputt.pdf"]["rolle"] == an.KAPUTT and x["kaputt.pdf"]["hinweise"]
assert any("DWG" in h for h in x["Plan.dwg"]["hinweise"]) and x["x.abc"]["rolle"] == an.UNBEKANNT
assert "neuer Stand" in an.zusammenfassung(liste)
ok("B3 Revision, neuer Stand (alt bleibt), STEP + Zeichnung = ein Teil, Hinweise")

# ---------------------------------------------------------------------------------------------- B4
n = an.nachtraege([("a.msg", "19.11.", "Bitte 200 Stück Halter 40x40x3 anbieten."),
                   ("b.msg", "20.11.", "Korrektur: jetzt 250 Stück, Zeichnung Rev. C anbei.\n\n> Bitte 200 Stück")])
w = {(e["feld"], e["alt"], e["neu"]) for e in n}
assert ("stueckzahl", "200", "250") in w and ("revision", "", "C") in w, w
assert not any(e["feld"] == "abmessung" for e in n)
assert an.nachtraege([("a.msg", "", "200 Stück")]) == []
ok("B4 Nachträge: geänderte und neue Werte, mit Fundstelle; zitierter Altteil zählt nicht")

# ---------------------------------------------------------------------------------------------- B5
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

D = datetime.datetime(2026, 11, 20, 8, 0)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
abl = seite.ablage()
p1 = datei("erst.msg", t.msg("Anfrage Halter", "Bitte 200 Stück Halter anbieten.", "Kunde", "k@kunde.example", D,
                             [("Halter_RevA.pdf", b"%PDF-1.4 a"), ("Halter.step", b"ISO-10303-21; x"),
                              ("kaputt.pdf", b"PK\x03\x04"), ("komisch.abc", b"\x00\x01")]))
k = ak.mail_kopf(dict(quelle="ordner", eingang=D), mail.lesen(p1), [], (), "")
a, _ = abl.anlegen(k, [p1], "erst", jetzt=D)
p2 = datei("nach.msg", t.msg("AW: Anfrage Halter", "Korrektur: jetzt 250 Stück, neue Zeichnung Rev. B anbei.",
                             "Kunde", "k@kunde.example", D + datetime.timedelta(hours=3),
                             [("Halter_RevB.pdf", b"%PDF-1.4 b")]))
abl.dateien_dazu(a, [p2], jetzt=D + datetime.timedelta(hours=3), antwort=True)
seite.neu_laden()
seite.waehlen(a.nr)
h = seite.inhalt.toHtml() if hasattr(seite, "inhalt") else ""
teile = "".join(seite._erkannt_html(seite.akte()))
assert "Geänderte Angaben aus Nachträgen" in teile and "200" in teile and "250" in teile, teile
assert "nachtrag-gesehen:" in teile
roll = {x["name"]: x for x in seite.anhaenge(seite.akte())}
assert roll["Halter_RevB.pdf"]["neuer_stand_von"] == "Halter_RevA.pdf", roll
assert roll["kaputt.pdf"]["rolle"] == an.KAPUTT and roll["komisch.abc"]["rolle"] == an.UNBEKANNT
assert "neuer Stand von Halter_RevA.pdf" in h and "Beschädigt" in h, h[:3000]
seite.nachtrag_gesehen()
a2 = abl.neu_lesen(a)
assert a2.stand["nachtrag_gesehen"] >= 2 and "Stückzahl 200 → 250" in ak.verlauf_text(a2.verlauf[-1])
seite.waehlen(a.nr)
teile = "".join(seite._erkannt_html(seite.akte()))
assert "nachtrag-gesehen:" not in teile and "gesehen" in teile
seite.reiter.setCurrentIndex(1)
app.processEvents()
baum = seite.dokumente.baum
texte = [baum.topLevelItem(i).child(j).text(1) for i in range(baum.topLevelItemCount())
         for j in range(baum.topLevelItem(i).childCount())]
assert any("neuer Stand" in x for x in texte) and any("3D-Modell" in x for x in texte), texte
ok("B5 Rolle/Revision in Anhängen und Dokumente, Nachträge mit Gesehen, beschädigt/unbekannt ohne Abbruch")

print("Alle Tests bestanden.")
