"""Prüft, dass die Bedienungsanleitung (anleitung/erzeuge_anleitung.py) mit dem Programm Schritt hält:
jede Stammdatentabelle, jede Einstellung, jedes sichtbare Eingabefeld der Positionen und des Angebotskopfs,
jeder Reiter und jeder Knopf des Programms muss im Text der Anleitung vorkommen, dazu die Spalten der
Zukauf-CSV und alle Knöpfe, Menüpunkte, Kontrollkästchen und Fenstertitel aus dem Quelltext aller Module
(auch der Dialoge, die beim Test nicht geöffnet werden). Kommt etwas Neues ins Programm, schlägt dieser Test
fehl, bis die Anleitung ergänzt ist.

Aufbau: jedes Kapitel steht in genau einem Teil (TEILE) und hat einen Kasten „Wofür / Wo im Programm“
(STECKBRIEFE).

Außerdem: Verweise stehen nur als [[marke]] im Text (keine fest geschriebenen Kapitelnummern, die beim
Umordnen veralten), und jede Marke gehört zu genau einer Überschrift.

Aufruf: python tests/test_anleitung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton  # noqa: E402

from rohrlaser.angebot import KOPF, POSITIONEN  # noqa: E402
from rohrlaser.angebot_fenster import SICHTBAR  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fracht_daten import FRACHT_TABELLEN  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.rechnen import KOSTENARTEN  # noqa: E402
from rohrlaser.staffel_seite import ERGEBNIS  # noqa: E402
from rohrlaser.staffeln import EINSTELLUNG_FELDER  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNGEN, TABELLEN  # noqa: E402
from rohrlaser import zukauf, zukauf_csv  # noqa: E402

QUELLE = (HIER.parent / "anleitung" / "erzeuge_anleitung.py").read_text(encoding="utf-8")


# Verweise: [[marke]] statt „Kapitel 6.7“; jede Marke genau einmal an einer Überschrift
TEXTTEIL = QUELLE[QUELLE.index("# ---------------------------------------------------------------- Inhalt der Anleitung"):]
fest = [z.strip() for z in TEXTTEIL.splitlines() if re.search(r"\b(Kapitel|Abschnitt)\s*(\d|„)", z)]
assert not fest, "Fest geschriebene Kapitelnummern, bitte [[marke]] verwenden:\n  " + "\n  ".join(fest)
marken = re.findall(r'marke="([a-z0-9_]+)"', TEXTTEIL)
doppelt = sorted({m for m in marken if marken.count(m) > 1})
assert not doppelt, f"Marken doppelt vergeben: {doppelt}"
unbekannt = sorted(set(re.findall(r"\[\[([a-z0-9_]+)\]\]", TEXTTEIL)) - set(marken))
assert not unbekannt, f"Verweise auf unbekannte Marken: {unbekannt}"

# „Was ist neu“: die aktuelle Programmversion braucht einen Eintrag mit Kurzfassung (programm/rohrlaser/neuerungen.py)
from rohrlaser import VERSION  # noqa: E402
from rohrlaser.neuerungen import IN_ANLEITUNG, NEUERUNGEN  # noqa: E402
eintrag = [e for e in NEUERUNGEN if VERSION in e[0].split(" – ")]
assert eintrag, f"Version {VERSION} fehlt in NEUERUNGEN (programm/rohrlaser/neuerungen.py, oben einfügen)"
assert NEUERUNGEN[0] is eintrag[0], f"Version {VERSION} gehört ganz oben in NEUERUNGEN (neueste zuerst)"
assert all(len(e) == 3 and e[2].strip() for e in NEUERUNGEN[:IN_ANLEITUNG]), \
    "Die neuesten Einträge in NEUERUNGEN brauchen eine Kurzfassung: [Version, ausführlich, kurz (eine Zeile)]"
unbekannt = sorted({m for e in NEUERUNGEN[:IN_ANLEITUNG] for m in re.findall(r"\[\[([a-z0-9_]+)\]\]", e[2])} - set(marken))
assert not unbekannt, f"NEUERUNGEN verweist auf unbekannte Marken: {unbekannt}"


# Aufbau: jedes Kapitel in genau einem Teil, jedes Kapitel mit Steckbrief
sys.path.insert(0, str(HIER.parent / "anleitung"))
import erzeuge_anleitung as anl  # noqa: E402

kapitel_fn = [n for n in vars(anl) if n.startswith("kapitel_") and callable(getattr(anl, n))]
in_teilen = [k.__name__ for _, _, _, liste in anl.TEILE for k in liste]
assert sorted(in_teilen) == sorted(set(in_teilen)), "Kapitel mehrfach in TEILE"
fehlt_teil = sorted(set(kapitel_fn) - set(in_teilen))
assert not fehlt_teil, f"Kapitel ohne Teil (in TEILE einsortieren): {fehlt_teil}"
kapitel_marken = re.findall(r'i\.kapitel\("[^"]+", marke="([a-z0-9_]+)"', TEXTTEIL)
assert len(kapitel_marken) == len(kapitel_fn), "Jedes Kapitel braucht eine Marke (i.kapitel(..., marke=...))"
ohne = sorted(set(kapitel_marken) - set(anl.STECKBRIEFE))
assert not ohne, f"Kapitel ohne Kasten „Wofür / Wo im Programm“ (STECKBRIEFE): {ohne}"
uebrig = sorted(set(anl.STECKBRIEFE) - set(kapitel_marken))
assert not uebrig, f"STECKBRIEFE für unbekannte Kapitel: {uebrig}"


def kern(text):
    """'Schneidzeit manuell je Teil [s]' -> 'Schneidzeit manuell je Teil'; 'Zusatzarbeiten …' -> 'Zusatzarbeiten'."""
    t = re.sub(r"\s*[\[(].*?[\])]", "", text).replace("…", "").replace("&", "").strip()
    return re.sub(r"\s+", " ", t)


def kommt_vor(text):
    norm = re.sub(r"</?[a-zA-Z][^<>\n]*>", "", QUELLE).replace("&nbsp;", " ").replace("&", " ")
    norm = re.sub(r'"\s*\n\s*"', "", norm)          # im Quelltext umgebrochene Zeichenketten
    norm = re.sub(r"\s+", " ", re.sub(r"\s*\[[^\[\]\n]{1,12}\]", "", norm))     # Einheiten [mm], [€] …
    return kern(text).lower() in norm.lower()


pruefen = []
pruefen += [("Stammdatentabelle", t.titel) for t in TABELLEN]
pruefen += [("Feld in " + t.titel, f.titel) for t in TABELLEN for f in t.felder]
pruefen += [("Fracht-Tabelle", t.titel) for t in FRACHT_TABELLEN]
pruefen += [("Feld in " + t.titel, f.titel) for t in FRACHT_TABELLEN for f in t.felder]
pruefen += [("Einstellung", e.titel) for e in EINSTELLUNGEN]
pruefen += [("Kostenart", t) for t, _, _ in KOSTENARTEN]
pruefen += [("Angebotskopf", f.titel) for f in KOPF]
pruefen += [("Feld der Staffeln", f.titel) for f in EINSTELLUNG_FELDER if f.name != "meterpreise"]
pruefen += [("Ergebnis der Staffeln", t) for _, t, _, _ in ERGEBNIS if t[:1].isupper()]
pruefen += [("Position", f.titel) for f in POSITIONEN.felder if f.name in SICHTBAR]
pruefen += [("Zukauf-Tabelle", t.titel) for t in zukauf.TABELLEN]
pruefen += [("Spalte der Zukauf-CSV", zukauf_csv.titel(n)) for n in zukauf_csv.ARTIKEL_SPALTEN + zukauf_csv.BEZUG_SPALTEN]
pruefen += [("Feld der Zukaufartikel", f.titel) for f in zukauf.ARTIKEL.felder]

# Texte aus dem Quelltext aller Module: Knöpfe, Kontrollkästchen, Gruppen, Menüs, Reiter, Fenstertitel.
# So zählen auch Dialoge mit, die der Test nicht öffnet. Reine Symbole (◀ ▶) haben keinen Text.
AUFRUFE = re.compile(r"(^|\.)(QPushButton|QToolButton|QCheckBox|QRadioButton|QGroupBox|QAction|addAction|addTab|"
                     r"addMenu|addButton|setWindowTitle)$")
for datei in sorted((HIER.parent / "programm" / "rohrlaser").glob("*.py")):
    for knoten in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Call) and AUFRUFE.search(ast.unparse(knoten.func)):
            texte = [a.value for a in knoten.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if texte and re.search(r"[A-Za-zÄÖÜäöü]", texte[0]):
                pruefen.append((f"Text in {datei.name}", texte[0]))

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
seite = fenster.angebot_oeffnen(db.angebot_neu())
for i in range(fenster.reiter.count()):
    text = fenster.reiter.tabText(i)
    if not text.startswith("Angebot "):
        pruefen.append(("Reiter", text))
pruefen += [("Reiter im Angebot", t) for t in seite.reiter.texte()]
pruefen += [("Unterreiter der Einstellungen", fenster.bereich.unter.tabText(i).removesuffix(" 🔒"))
            for i in range(fenster.bereich.unter.count())]
pruefen += [("Unterreiter der Zuschläge", fenster.fracht.zuschlaege.unter.tabText(i))
            for i in range(fenster.fracht.zuschlaege.unter.count())]
for w in fenster.findChildren(QPushButton) + fenster.findChildren(QCheckBox):
    if w.text():
        pruefen.append(("Knopf", w.text()))
fenster.close()
db.schliessen()

fehlt = sorted({f"{art}: {text}" for art, text in pruefen if not kommt_vor(text)})
assert not fehlt, "In der Bedienungsanleitung fehlt:\n  " + "\n  ".join(fehlt)
print(f"OK: Bedienungsanleitung beschreibt alle {len(set(t for _, t in pruefen))} Tabellen, Felder, Reiter und Knöpfe")
