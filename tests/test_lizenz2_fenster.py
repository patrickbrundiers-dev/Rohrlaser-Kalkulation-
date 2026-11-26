"""Lizenz 2.0, Paket L2-2 (werkzeuge/lizenz2_fenster.py, lizenz2_werkzeug.aendern/status): Fälle F1–F16.

Eigene Test-Schlüssel (K9), Fenster offscreen ohne Rückfragen (stumm, Passwort als Parameter).
Aufruf: python tests/test_lizenz2_fenster.py
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PW = b"test-passwort-lizenz2-fenster"

from PySide6.QtWidgets import QApplication  # noqa: E402

import lizenz2_fenster as F  # noqa: E402
import lizenz2_werkzeug as L2  # noqa: E402
import lizenz_werkzeug as W  # noqa: E402
from rohrlaser import aktivierung as A  # noqa: E402
from rohrlaser import lizenz  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp(prefix="lizenz2_fenster_"))
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def wirft(f, *a, **k):
    try:
        f(*a, **k)
    except (lizenz.LizenzFehler, SystemExit) as e:
        return str(e) or "Fehler"
    return ""


HEUTE = datetime.date.today()
WZ = tmp / "werkzeug"
SID = "K9"
SCHL = {SID: W.schluessel_erzeugen(WZ, SID, PW, ausgabe=False)}
ROH1 = dict(guid="aaaa-1111", platte="0A0B0C0D", board="ASUS|PRIME B550|AMD Ryzen 7")
ROH2 = dict(guid="bbbb-2222", platte="11223344", board="Dell|OptiPlex|Intel i5")
ROH3 = dict(guid="cccc-3333", platte="55667788", board="HP|EliteDesk|Intel i7")


def platz(name):
    o = tmp / name / "Lizenz"
    o.mkdir(parents=True, exist_ok=True)
    return o


def zeile(dlg, nr):
    return next(z for z in dlg.zeilen if z["lizenz_nr"] == nr)


# ------------------------------------------------------------------ Status
e = dict(zertifikat=dict(inhalt=dict(gueltig_bis=(HEUTE + datetime.timedelta(days=10)).isoformat())))
pruefe(L2.status(e, HEUTE)[0] == "laeuft_ab", "F1 Status: läuft in 10 Tagen ab")
e["zertifikat"]["inhalt"]["gueltig_bis"] = (HEUTE - datetime.timedelta(days=3)).isoformat()
pruefe(L2.status(e, HEUTE) == ("abgelaufen", "abgelaufen seit 3 Tagen"), "F2 Status: abgelaufen")
e["zertifikat"]["inhalt"]["gueltig_bis"] = ""
pruefe(L2.status(e, HEUTE)[0] == "unbefristet", "F3 Status: unbefristet")

# ------------------------------------------------------------------ Dashboard: neue Lizenz
dlg = F.Lizenzen2(None, WZ, pw=PW, stumm=True)
pruefe(dlg.tabelle.rowCount() == 0, "F4 Dashboard startet mit leerem Register")
schl, nr1 = dlg.neu(dict(lizenznehmer="Max Muster", firma="Musterbau GmbH", typ="mehrplatz", plaetze=2, reserve=1,
                         bis=HEUTE + datetime.timedelta(days=365), module=["alle"], admins=["Max"]))
pruefe(nr1.startswith("LN-") and dlg.tabelle.rowCount() == 1 and dlg.markierte() == nr1
       and QApplication.clipboard().text() == schl, "F5 Neue Lizenz: in der Tabelle markiert, Schlüssel kopiert")
pruefe(dlg.neu(dict(lizenznehmer="", typ="einzelplatz")) is None and "Lizenznehmer" in dlg.letzter_fehler,
       "F6 ohne Lizenznehmer: Hinweis, nichts erstellt")

# ------------------------------------------------------------------ Anfrage beantworten
P1, P2, P3 = platz("pc1"), platz("pc2"), platz("pc3")
anf1 = A.anfrage_erstellen(P1, schl, "PC-BUERO", roh=ROH1)
antwort = dlg.anfrage(A.als_code(anf1))
aid1 = antwort["inhalt"]["aktivierung_id"]
pruefe(zeile(dlg, nr1)["belegt"] == 1 and dlg.plaetze_tabelle.rowCount() == 1
       and QApplication.clipboard().text().startswith("AKTIVIERUNG-"), "F7 Anfrage per Code beantwortet, Platz unten")
A.antwort_laden(P1, A.als_code(antwort), SCHL, ist_merkmale=A.merkmale(ROH1), heute=HEUTE)
anf2 = A.anfrage_erstellen(P2, schl, "PC-WERKSTATT", roh=ROH2)
(tmp / "anfrage2.json").write_text(json.dumps(anf2), "utf-8")
antwort2 = dlg.anfrage(tmp / "anfrage2.json")
aid2 = antwort2["inhalt"]["aktivierung_id"]
A.antwort_laden(P2, A.als_code(antwort2), SCHL, ist_merkmale=A.merkmale(ROH2), heute=HEUTE)
pruefe(zeile(dlg, nr1)["belegt"] == 2 and aid2 != aid1, "F8 zweite Anfrage als Datei: 2 Plätze belegt")
pruefe(dlg.anfrage("ANFRAGE-kaputt") is None and dlg.letzter_fehler, "F9 kaputter Code: Hinweis statt Absturz")

# ------------------------------------------------------------------ Suche
dlg.filter.setText("werkstatt")
sichtbar = [i for i in range(dlg.tabelle.rowCount()) if not dlg.tabelle.isRowHidden(i)]
dlg.filter.setText("gibtsnicht")
leer = [i for i in range(dlg.tabelle.rowCount()) if not dlg.tabelle.isRowHidden(i)]
dlg.filter.setText("")
pruefe(sichtbar == [0] and leer == [], "F10 Suche findet die Lizenz auch über den Rechnernamen")

# ------------------------------------------------------------------ Verlängern / ändern
dlg.markieren(nr1)
neu_bis = HEUTE + datetime.timedelta(days=730)
nr2 = dlg.verlaengern(neu_bis)
d = L2.register_lesen(WZ)
pruefe(nr2 and nr2 != nr1 and d["zertifikate"][nr1]["ersetzt_durch"] == nr2
       and d["zertifikate"][nr2]["lizenzschluessel"] == schl and zeile(dlg, nr2)["belegt"] == 2
       and zeile(dlg, nr2)["gueltig_bis"] == neu_bis.isoformat(),
       "F11 Verlängern: neues Zertifikat, gleicher Schlüssel, beide Plätze ziehen mit")
pruefe(dlg.tabelle.isRowHidden(next(i for i, z in enumerate(dlg.zeilen) if z["lizenz_nr"] == nr1)),
       "F12 ersetzte Lizenz ist ausgeblendet (Haken zeigt sie)")
anf1b = A.anfrage_erstellen(P1, schl, "PC-BUERO", roh=ROH1)
antwort_b = dlg.anfrage(A.als_code(anf1b))
A.antwort_laden(P1, A.als_code(antwort_b), SCHL, ist_merkmale=A.merkmale(ROH1), heute=HEUTE)
pruefe(antwort_b["inhalt"]["aktivierung_id"] == aid1 and antwort_b["inhalt"]["lizenz_nr"] == nr2
       and zeile(dlg, nr2)["belegt"] == 2, "F13 Rechner holt verlängerte Lizenz: gleicher Platz, kein neuer belegt")
dlg.markieren(nr2)
pruefe(dlg.aendern(dict(plaetze=1, reserve=0)) is None and "belegt" in dlg.letzter_fehler,
       "F14 weniger Plätze als belegt: abgelehnt mit Hinweis")
nr3 = dlg.aendern(dict(plaetze=3, firma="Musterbau Nord GmbH"))
pruefe(nr3 and L2.register_lesen(WZ)["zertifikate"][nr3]["zertifikat"]["inhalt"]["plaetze"] == 3
       and zeile(dlg, nr3)["max"] == 4, "F15 Plätze erhöht und übertragen: 3 Plätze + Reserve")

# ------------------------------------------------------------------ Freigabe, deaktivieren, sperren
beleg = A.freigabe_erstellen(P2, SCHL)
frei = dlg.freigabe(A.als_code(beleg))
pruefe(frei == aid2 and zeile(dlg, nr3)["belegt"] == 1, "F16a Freigabebeleg verbucht: Platz wieder frei")
dlg.markieren(nr3)
dlg.plaetze_tabelle.selectRow(next(i for i in range(dlg.plaetze_tabelle.rowCount())
                                   if dlg.plaetze_tabelle.item(i, 0).text() == aid1))
weg = dlg.deaktivieren(bestaetigt=True)
dlg.markieren(nr3)
gesperrt = dlg.sperren(bestaetigt=True)
pruefe(weg == aid1 and gesperrt == nr3 and zeile(dlg, nr3)["status"] == "gesperrt" and zeile(dlg, nr3)["belegt"] == 0,
       f"F16 Platz deaktivieren ({weg}) und Lizenz sperren im Dashboard")
pruefe("gesperrt" in wirft(L2.aendern, WZ, nr3, pw=PW, plaetze=5), "F17 gesperrte Lizenz lässt sich nicht ändern")
sperr = json.loads((WZ / "Sperrliste.json").read_text("utf-8"))
reg = L2.register_lesen(WZ)["zertifikate"]
pruefe({nr1, nr2, nr3} <= set(sperr["gesperrt"]) and all(reg[n]["gesperrt"] for n in (nr1, nr2, nr3)),
       "F17b Sperren trifft auch die Vorgänger (Rechner, die die Verlängerung noch nicht geholt haben)")

# ------------------------------------------------------------------ Hauptfenster-Knopf
import lizenz_werkzeug_fenster as WF  # noqa: E402

haupt = WF.Fenster(WZ)
d2 = haupt.lizenzen2()
pruefe(isinstance(d2, F.Lizenzen2) and d2.tabelle.rowCount() == len(L2.uebersicht(WZ)),
       "F18 Knopf „Lizenzen 2.0 …“ im Lizenz-Werkzeug öffnet das Dashboard")
d2.close()
haupt.close()
dlg.close()

shutil.rmtree(tmp, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
