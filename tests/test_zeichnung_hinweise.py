"""Bearbeitungshinweise aus Zeichnungen (Patrick 03.11.2026, Freigabe 1a 2a 3a 4a): Gewinde, Flowdrill,
Einnietmuttern, Senkungen und Blindniete mit Anzahl aus dem Zeichnungstext; Abgleich mit den Bohrungen des STEP
(Vorschlag im Bohrbild, Hinweis bei Abweichung), Zusatzarbeiten mit Anzahl, ohne STEP als Zusatzarbeit/Gewinde-Vorschlag.
Testzeichnungen selbst gebaut (keine echten Kundenzeichnungen).

Aufruf: python tests/test_zeichnung_hinweise.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import bohrbild, pdf_art, zusatz_erkennung  # noqa: E402
from rohrlaser import zeichnung_hinweise as zh  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Lesen
TEXT = """Maßstab M 1:1
4x M8
M10 (2x)
Flowdrill M6 3x
2 Stk Einnietmutter M5
Senkung DIN 74 4x
6x Blindniet Ø4
Gewinde M8x1,25
Toleranz ISO 2768-m
Werkstoff S235JR"""
h = {(x["art"], x["gewinde"]): x["anzahl"] for x in zh.lesen(TEXT)}
assert h == {("Gewinde", "M8"): 4, ("Gewinde", "M10"): 2, ("Flowdrill", "M6"): 3, ("Einnietmutter", "M5"): 2,
             ("Senkung", None): 4, ("Blindniet", None): 6}, h
assert zh.lesen("FDS M8") == [dict(art="Flowdrill", gewinde="M8", anzahl=None, wort="FDS M8")]
assert [x["art"] for x in zh.lesen("Fließloch Ø7,3 (2x)\nBlindnietmutter M6\nkegelgesenkt 90°")] == \
    ["Flowdrill", "Einnietmutter"] and not zh.lesen("Maßstab M 1:2\nISO 2768-mK\nRAL 7016")
assert zh.lesen("4x M6, 2x M10")[0]["anzahl"] == 4 and len(zh.lesen("4x M6, 2x M10")) == 2
assert zh.gewinde_vorschlag(zh.lesen("4x M8\nM10")) == "4xM8; 1xM10"
assert zh.zusatz_mengen(zh.lesen(TEXT)) == {"Einnietmuttern setzen": 2}
assert zh.zusatz_mengen(zh.lesen(TEXT), mit_bohrbild=False) == {"Flowdrill": 3, "Einnietmuttern setzen": 2,
                                                                  "Senken": 4}
assert "6× Blindniet" in zh.nicht_abgedeckt(zh.lesen(TEXT))
ok("Lesen: 4x M8, M10 (2x), Flowdrill/FDS/Fließloch, Einnietmutter, Senkung, Blindniet mit Anzahl; Maßstab/Toleranz nicht")

# ------------------------------------------------------------------ Abgleich mit dem Bohrbild (1a, 2a)
GEWINDE = [("M6", 5.0), ("M8", 6.8), ("M10", 8.5)]
m = dict(bohrungen="6.8:4|7.3:2|10.0:1")
bild = bohrbild.aus_messung(m, GEWINDE)
assert [(z["art"], z.get("gewinde")) for z in bild] == [("Bohrung", "M8")]
meld = zh.bohrbild_abgleich(bild, zh.lesen("4x M8\nFlowdrill M8 2x\n2x Senkung"), m, GEWINDE, "Zeichnung A.pdf S. 1")
assert bild[0]["zeichnung"] == "Zeichnung A.pdf S. 1: 4x M8" and bild[0]["status"] == bohrbild.OFFEN
fl = [z for z in bild if z["art"] == "Fließloch"]
assert len(fl) == 1 and fl[0]["d"] == 7.3 and fl[0]["anzahl"] == 2 and fl[0]["aus_bohrung"] and fl[0]["gewinde"] == "M8"
assert meld == ["Zeichnung A.pdf S. 1 nennt 2× Senkung, im STEP keine passende Bohrung"], meld
assert zh.bohrbild_abgleich(bohrbild.aus_messung(m, GEWINDE), zh.lesen("6x M8"), m, GEWINDE) == \
    ["Zeichnung nennt 6× M8, im STEP 4 passende Bohrungen"]
b2 = []                                                  # Kernloch etwas daneben (CAD 6,9): Gewinde aus der Zeichnung
assert not zh.bohrbild_abgleich(b2, zh.lesen("M8"), dict(bohrungen="6.9:3"), GEWINDE) and b2[0]["anzahl"] == 3
assert b2[0]["gewinde"] == "M8" and b2[0]["art"] == "Bohrung"                       # 2a: Anzahl aus dem STEP
# Flowdrill aus einer gemessenen Bohrung: offen ändert nichts, bestätigt fällt die gelaserte Bohrung weg
assert bohrbild.zusatz(fl)["schneidweg"] == 0 and bohrbild.zusatz(fl)["einstiche"] == 0
best = [dict(fl[0], status=bohrbild.BESTAETIGT)]
z = bohrbild.zusatz(best)
assert abs(z["schneidweg"] + 2 * math.pi * 7.3) < 1e-6 and z["einstiche"] == -2 and z["weg"] == [(7.3, math.pi * 7.3)] * 2
assert abs(z["gravur"] - 2 * math.pi * bohrbild.MARKE_D) < 1e-6
assert bohrbild.arbeiten(best) == {bohrbild.ZUSATZ_FLOWDRILL: 2}
ok("Abgleich: Gewinde an die Kernloch-Bohrung, Flowdrill auf gemessener Bohrung erst bestätigt wirksam, Hinweis bei "
   "fehlender/abweichender Bohrung, Anzahl aus dem STEP wenn keine dasteht")

# ------------------------------------------------------------------ Text ans Teil (pdf_art)
mw = [dict(datei="T07.step", artikel="T07-100"), dict(datei="X.step", artikel="X-1")]
f = dict(text="", datei="T07.pdf", seiten=[], zeichnungen=[dict(artikel="T07-100", seite=2, datei="T07.pdf",
                                                                text="4x M8")])
pdf_art.anwenden(mw, [f])
assert mw[0]["_zeichnung_text"] == "4x M8" and mw[0]["_zeichnung_quelle"] == "Zeichnung T07.pdf S. 2"
assert "_zeichnung_text" not in mw[1]
pdf_art.anwenden(mw, [])
assert "_zeichnung_text" not in mw[0]                                     # umgeschaltet: zurückgenommen
ok("Zeichnungstext hängt am passenden Teil und wird beim Umschalten zurückgenommen")

# ------------------------------------------------------------------ Zusatzarbeiten mit Anzahl (text_merken)
katalog = [dict(name="Einnietmuttern setzen", erkennung="einnietmutter", aktiv="ja"),
           dict(name="Feuerverzinken", erkennung="verzinkt", aktiv="ja"), dict(name="Flowdrill", aktiv="ja"),
           dict(name="Senken", aktiv="ja")]
ag = zusatz_erkennung.text_merken(None, "2 Stk Einnietmutter M5\nverzinkt", katalog, "Zeichnung A.pdf S. 1",
                                  {"Einnietmuttern setzen": 2})
e = {x["name"]: x for x in json.loads(ag)["erkannt"]}
assert e["Einnietmuttern setzen"]["menge"] == 2 and "menge" not in e["Feuerverzinken"]
ag = zusatz_erkennung.text_merken(None, "Flowdrill M6 3x", katalog, "Zeichnung", dict(Flowdrill=3, Senken=None))
e = {x["name"]: x for x in json.loads(ag)["erkannt"]}
assert e["Flowdrill"]["menge"] == 3 and "Senken" in e and "menge" not in e["Senken"]          # 3a: ohne STEP
p = dict(artikel="T07", arbeitsgaenge=ag)
assert {x["name"]: x.get("menge") for x in zusatz_erkennung.erkannt(p, katalog)} == {"Flowdrill": 3, "Senken": None}
ok("Zusatzarbeiten: Einnietmuttern mit Anzahl aus der Zeichnung, ohne STEP auch Flowdrill und Senken")

# ------------------------------------------------------------------ ganzer Import mit STEP (T07 mit Gewinde)
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
seite = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
z_text = "4x M6\n2 Stk Einnietmutter M6\n6x Blindniet Ø4"
form = dict(text="", ocr=False, unsicher=set(), datei="T07_QR40x3_L1000_Gewinde_Gravur.pdf",
            seiten=[dict(nr=1, art="Zeichnung", grund="", text=z_text, segmente=[], ocr=False)])
seite.step_importieren([str(HIER / "step" / "T07_QR40x3_L1000_Gewinde_Gravur.step")], formulare=[form])
pos = [p for p in seite.positionen if p.get("profil_id")]
assert len(pos) == 1, seite.positionen
p = pos[0]
bild = bohrbild.lesen(p.get("bohrbild"))
print("       Bohrbild T07:", [(z["art"], z.get("d"), z.get("anzahl"), z.get("gewinde"), z.get("zeichnung")) for z in bild])
erk = {x["name"]: x for x in zusatz_erkennung.erkannt(p, db.zeilen("zusatzarbeiten"))}
assert erk["Einnietmuttern setzen"]["menge"] == 2 and "Gravur.pdf S. 1" in erk["Einnietmuttern setzen"]["quelle"], erk
assert [(z["gewinde"], z["anzahl"]) for z in bild if z.get("zeichnung")] == [("M6", 4)], bild
assert bild[0]["zeichnung"] == "Zeichnung T07_QR40x3_L1000_Gewinde_Gravur.pdf S. 1: 4x M6"
ok("Import T07 mit Zeichnung: Gewinde-Hinweis am Bohrbild, Einnietmuttern 2× als Vorschlag")
db.schliessen()
print("Alle Tests bestanden.")
