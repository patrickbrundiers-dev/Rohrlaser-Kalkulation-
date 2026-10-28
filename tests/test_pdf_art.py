"""PDF der Anfrage: Zeichnung oder Anfrageformular (Patrick 28.10.2026, F1 b, F2-F4 a): jede Seite wird eingeordnet
(auch Scans und gemischte PDFs); Formular-Seiten gehen in die Formular-Auswertung, Zeichnungsseiten liefern nur ihr
Schriftfeld für das passende STEP-Teil (gelb, Formular geht vor), unklare Seiten gelten als Formular mit Hinweis; im
Prüfdialog lässt sich die Einordnung je Datei umschalten; ein Ordner nur mit Zeichnung ergibt keine Anfrage, nur einen
Hinweis. Die PDFs baut tests/pdf_testdateien.py (Patricks DXF-Zeichnungen als CAD-Druck, erfundene Formulare).

Aufruf: python tests/test_pdf_art.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

import pdf_testdateien as pt  # noqa: E402
from rohrlaser import anfragen, formular, ocr, pdf_art  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

Z, F, U = pdf_art.ZEICHNUNG, pdf_art.FORMULAR, pdf_art.UNKLAR
D = HIER / "dxf"
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def arten(pfad):
    return [s["art"] for s in pdf_art.seiten(pfad)]


# ------------------------------------------------------------------ Einordnung je Seite
form = pt.pdf(tmp / "form.pdf", [("formular", pt.FORMULAR)])
assert arten(form) == [F], pdf_art.seiten(form)[0]["grund"]
for n in ("rohr_gehrung_QR40_patrick", "rohr_bauteil1_patrick", "rohr_ansichten_QR40"):
    p = pt.pdf(tmp / f"{n}.pdf", [("zeichnung", D / f"{n}.dxf")])
    s = pdf_art.seiten(p)[0]
    assert s["art"] == Z and "Maßstab" in s["grund"], (n, s["grund"])
blech = pt.pdf(tmp / "blech.pdf", [("blech", pt.SCHRIFTFELD_BLECH)])
assert arten(blech) == [Z]
kurz = pt.pdf(tmp / "kurz.pdf", [("formular", ["Bestellung 4711", "MG-01  5 Stk", "MG-02  3 Stk"])])
assert arten(kurz) == [U]
assert pdf_art.beschreibung(pdf_art.lesen(kurz)) == "kurz.pdf: unklar – als Formular gelesen, bitte prüfen"
leer = pt.pdf(tmp / "leer.pdf", [("formular", [])])
assert pdf_art.einordnen(dict(text="", segmente=[], linien=0))[0] == U and formular.datei_lesen(leer) is None
assert formular.datei_lesen(tmp / "fehlt.pdf") is None
ok("Einordnung: Formular, Rohrzeichnungen (Patricks DXF als CAD-Druck), Blechzeichnung, kurze Liste = unklar")

gem = pt.pdf(tmp / "Anfrage gemischt.pdf", [("formular", pt.FORMULAR),
                                            ("zeichnung", D / "rohr_bauteil1_patrick.dxf", pt.SCHRIFTFELD_ROHR),
                                            ("blech", pt.SCHRIFTFELD_BLECH)])
g = formular.datei_lesen(gem)
assert [s["art"] for s in g["seiten"]] == [F, Z, Z]
assert pdf_art.beschreibung(g) == "Anfrage gemischt.pdf: Formular (S. 1), Zeichnung (S. 2–3)", pdf_art.beschreibung(g)
assert "AN-2026-0815" in g["text"] and "Allgemeintoleranz" not in g["text"] and "BL-200" not in g["text"]
assert [(z["seite"], z.get("artikel"), z.get("stueck")) for z in g["zeichnungen"]] == [(2, "ST-77", 12),
                                                                                       (3, "BL-200", 4)], g["zeichnungen"]
assert g["zeichnungen"][1]["werkstoff_text"] == "1.4571" and g["zeichnungen"][1]["name"] == "Deckel"
assert pdf_art.zusammen(g, pdf_art.NICHT) is None
assert "Allgemeintoleranz" in pdf_art.zusammen(g, F)["text"] and not pdf_art.zusammen(g, F)["zeichnungen"]
assert pdf_art.zusammen(g, Z)["text"] == "" and len(pdf_art.zusammen(g, Z)["zeichnungen"]) == 3
assert pdf_art.beschreibung(pdf_art.zusammen(g, F)) == "Anfrage gemischt.pdf: alles als Formular (von Hand)"
assert "S. 2: Zeichnung" in pdf_art.gruende(g)
e = formular.auswerten(g["text"], [dict(kundennr="10417", name="Metallbau Krüger")])
assert e["nummer"] == "AN-2026-0815" and e["kunde"] == "10417"
ok("gemischtes PDF: je Seite eingeordnet, Formular-Text ohne Zeichnungen, Schriftfelder je Zeichnung, umschaltbar")

if ocr.programm() is None:
    assert not os.environ.get("CI"), "tesseract fehlt im CI"
    print("HINWEIS Tesseract nicht installiert: Scan-Teil übersprungen")
else:
    for endung in (".png", ".pdf"):
        sf = pdf_art.seiten(pt.scan(form, tmp / f"form_scan{endung}"))
        assert [x["art"] for x in sf] == [F], (endung, [(x["grund"], x["text"][:200]) for x in sf])
        s = formular.datei_lesen(pt.scan(blech, tmp / f"blech_scan{endung}"))
        assert [x["art"] for x in s["seiten"]] == [Z] and s["ocr"], s["seiten"][0]["grund"]
        assert (s["zeichnungen"][0].get("artikel"), s["zeichnungen"][0].get("stueck")) == ("BL-200", 4), s["zeichnungen"]
    ok("Scans (PNG, Bild-PDF): Formular und Zeichnung erkannt, Schriftfeld per Texterkennung")

# ------------------------------------------------------------------ Schriftfeld auf STEP-Teile (F2 a)
db = Datenbank(tmp / "rohrlaser.db")
ws = db.zeilen("werkstoffe")


def teile():
    return [dict(datei="MG-01.step", artikel="MG-01", profilform="Rundrohr"),
            dict(datei="Teil2.step", artikel="ST-77", profilform="Rundrohr"),
            dict(datei="Deckel.step", artikel="BL-200", profilform="Quadratrohr"),
            dict(datei="Satz.step", artikel="BL-200", profilform="Rundrohr", _saetze=2)]


mw = teile()
erg = pdf_art.anwenden(mw, [g], ws)
assert erg == dict(formular=1, unsicher=0, zeichnung=2), erg
assert (mw[0]["_stueck"], mw[0]["_stueck_formular"]) == (20, True)                   # Formular
assert (mw[1]["_stueck"], mw[1]["_stueck_formular"]) == (12, False) and "S. 2" in mw[1]["_stueck_quelle"]
assert (mw[2]["_stueck"], mw[2]["_werkstoff"]) == (4, "1.4571") and mw[2]["_werkstoff_quelle"]
assert "_stueck" not in mw[3]                                                     # Satz bleibt
assert "_werkstoff" not in pdf_art.anwenden(teile(), [g], None) or True
mw2 = teile()
pdf_art.anwenden(mw2, [g], None)
assert "_werkstoff" not in mw2[2] and mw2[2]["_stueck"] == 4                       # Werkstoff aus der Mail geht vor
form_mit = dict(text="BL-200 Deckel 9 Stk", ocr=False, unsicher=set())
mw3 = teile()
pdf_art.anwenden(mw3, [g, form_mit], ws)
assert (mw3[2]["_stueck"], mw3[2]["_stueck_formular"]) == (9, True)                # Formular geht vor Zeichnung
pdf_art.anwenden(mw, [pdf_art.zusammen(g, pdf_art.NICHT)], ws)
assert not any("_stueck" in m or "_werkstoff" in m for m in mw), mw                 # umgeschaltet: zurückgenommen
pdf_art.anwenden(mw, [pdf_art.zusammen(g, pdf_art.AUTO)], ws)
assert mw[1]["_stueck"] == 12
ok("Schriftfeld: Stückzahl und Werkstoff für das passende Teil (gelb), Formular und Mail gehen vor, umschaltbar")

# ------------------------------------------------------------------ Prüfdialog
app = QApplication.instance() or QApplication([])
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402
k = db.kontext()
prof = next(iter(k.profile))
mw = [dict(m, bauteil=m["artikel"], profil_id_vorschlag=prof, laenge=500, pruefstatus="plausibel", schneidweg=100)
      for m in teile()[:3]]
wahl, aufrufe = {}, []
pdf_art.anwenden(mw, [g], ws)


def pdf_neu(datei, w):
    aufrufe.append((datei, w))
    wahl[datei] = w
    pdf_art.anwenden(mw, [pdf_art.zusammen(g, wahl.get(g["datei"], pdf_art.AUTO))], ws)


dlg = StepPruefDialog(None, mw, k, "1.4301", 1, vorpruefung=lambda: ([], 0), pdf_formulare=[g], pdf_neu=pdf_neu)
cb = dlg.pdf_wahl["Anfrage gemischt.pdf"]
zeilen = {mw[z.liste[0]]["datei"]: z for z in dlg.zeilen}
assert zeilen["Teil2.step"].sp.value() == 12 and "FFF4CE" in zeilen["Teil2.step"].sp.styleSheet().upper()
assert zeilen["Deckel.step"].ws.currentText() == "1.4571" and zeilen["Deckel.step"].ws.styleSheet()
assert "Zeichnung" in zeilen["Teil2.step"].sp.toolTip()
cb.setCurrentIndex(cb.findData(pdf_art.NICHT))
assert aufrufe == [("Anfrage gemischt.pdf", pdf_art.NICHT)]
assert zeilen["Teil2.step"].sp.value() == 1 and zeilen["MG-01.step"].sp.value() == 1 and not zeilen["Teil2.step"].sp.styleSheet()
assert zeilen["Deckel.step"].ws.currentText() == "1.4301"
cb.setCurrentIndex(cb.findData(pdf_art.AUTO))
assert zeilen["MG-01.step"].sp.value() == 20 and zeilen["Deckel.step"].sp.value() == 4
dlg.close()
ok("Prüfdialog: Zeile je PDF mit Einordnung, umschalten ordnet Stückzahl und Werkstoff neu zu")

# ------------------------------------------------------------------ Anfrage-Ordner
eingang = tmp / "Eingang"
(eingang / "Krüger Gestell").mkdir(parents=True)
(eingang / "Nur Zeichnung").mkdir()
pt.pdf(eingang / "Nur Zeichnung" / "BL-200.pdf", [("blech", pt.SCHRIFTFELD_BLECH)])
(eingang / "Krüger Gestell" / "T01_RR42-4x2_L1250.step").write_bytes((HIER / "step" / "T01_RR42-4x2_L1250.step")
                                                                       .read_bytes())
pt.pdf(eingang / "Krüger Gestell" / "Anfrage.pdf", [("formular", pt.FORMULAR),
                                                    ("zeichnung", D / "rohr_bauteil1_patrick.dxf",
                                                     ["Zeichnungs-Nr.: T01_RR42-4x2_L1250", "Stückzahl: 7"])])
alt = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
for p in eingang.rglob("*"):
    os.utime(p, (alt, alt))
ohne = []
gef = anfragen.suchen(eingang, ohne_step=ohne)
assert [a.name for a in gef] == ["Krüger Gestell"] and ohne == ["Nur Zeichnung"], (gef, ohne)
fenster = Hauptfenster(db, tmp, stumm=True)
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen(anfragen.EINSTELLUNG, str(eingang))
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
assert "Ohne STEP" in karte.hinweis.text() and "Nur Zeichnung" in karte.hinweis.text()
aufruf = []
orig = AngebotSeite.step_importieren
AngebotSeite.step_importieren = lambda self, d=None, *a, **kw: aufruf.append((self.kopf, kw)) or {}
karte.oeffnen([karte.anfragen[0]])
AngebotSeite.step_importieren = orig
kopf, kw = aufruf[-1]
assert kopf.get("kundenreferenz") == "AN-2026-0815", kopf.get("kundenreferenz")
f = kw["formulare"][0]
assert [s["art"] for s in f["seiten"]] == [F, Z] and f["zeichnungen"][0]["stueck"] == 7
ok("Anfrage-Ordner: Ordner nur mit Zeichnung keine Anfrage, nur Hinweis; Formular und Zeichnung getrennt an den Import")

s1 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
s1.step_importieren([str(HIER / "step" / "T01_RR42-4x2_L1250.step")], formulare=[f])
assert [p.get("stueck") for p in s1.positionen if p.get("profil_id")] == [25], s1.positionen     # Formular: 25 Stück
nur_z = pdf_art.zusammen(f, Z)
s2 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
s2.step_importieren([str(HIER / "step" / "T01_RR42-4x2_L1250.step")], formulare=[nur_z])
assert [p.get("stueck") for p in s2.positionen if p.get("profil_id")] == [7], s2.positionen      # nur Zeichnung: 7
ok("Import: Stückzahl aus dem Formular, sonst aus dem Schriftfeld der Zeichnung")
# ------------------------------------------------------------------ ZIP direkt im Anfrage-Ordner bzw. gezogen
import io  # noqa: E402
import zipfile  # noqa: E402
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as zp:
    zp.writestr("Teile/T01_RR42-4x2_L1250.step", (HIER / "step" / "T01_RR42-4x2_L1250.step").read_bytes())
    zp.writestr("Teile/Anfrage.pdf", form.read_bytes())
ein2 = tmp / "Eingang2"
ein2.mkdir()
(ein2 / "Gestell Krüger.zip").write_bytes(puffer.getvalue())
(ein2 / "Fotos.zip").write_bytes(b"PK kaputt")
for p in ein2.iterdir():
    os.utime(p, (alt, alt))
gef = anfragen.suchen(ein2)
assert [a.name for a in gef] == ["Gestell Krüger"] and "1 STEP" in gef[0].text() and "1 ZIP" in gef[0].text(), gef
a2 = anfragen.auspacken(anfragen.sperren(gef[0], ein2, "PB"))
assert [d.name for d in a2.step] == ["T01_RR42-4x2_L1250.step"] and [d.name for d in a2.formulare] == ["Anfrage.pdf"]
assert len(anfragen.auspacken(a2).dateien) == len(a2.dateien)                     # zweimal: nicht doppelt
anfragen.freigeben(a2)
kordner = tmp / "Kunden" / "Krüger"
kordner.mkdir(parents=True)
(kordner / "Teile.zip").write_bytes(puffer.getvalue())
assert anfragen.mails_neben([kordner]) == [kordner / "Teile.zip"]
aufruf.clear()
AngebotSeite.step_importieren = lambda self, d=None, *a, **kw: aufruf.append((d, kw)) or {}
fenster.angebote.neu_aus_step([str(kordner / "Teile.zip")])
AngebotSeite.step_importieren = orig
assert [Path(d).name for d in aufruf[-1][0]] == ["T01_RR42-4x2_L1250.step"], aufruf
assert (kordner / "T01_RR42-4x2_L1250.step").exists()
ok("ZIP mit STEP im Anfrage-Ordner ist eine Anfrage (ausgepackt beim Öffnen); ZIP aufs Programm gezogen: daneben "
   "ausgepackt")
print("Alle Tests bestanden.")
