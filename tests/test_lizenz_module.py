"""Lizenz 2.0, Paket L2-4 (programm/rohrlaser/module.py, Lizenzprotokoll, Prüfstellen): Fälle M1–M16.

Eigene Test-Schlüssel (K9). Aufruf: python tests/test_lizenz_module.py
"""
import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PW = b"test-passwort-lizenz-module"

import lizenz2_werkzeug as L2  # noqa: E402
import lizenz_werkzeug as W  # noqa: E402
from rohrlaser import aktivierung as A  # noqa: E402
from rohrlaser import funktionen, lizenz  # noqa: E402
from rohrlaser import module as M  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="lizenz_module_"))
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
ROH = dict(guid="aaaa-1111", platte="0A0B0C0D", board="ASUS|PRIME B550|AMD Ryzen 7")

# ------------------------------------------------------------------ Katalog
pruefe(len(M.MODULE) == 7 and set(M.NAMEN) == {"blech", "baugruppen", "auftrag", "vertrieb", "einkauf", "auslastung",
                                                "ki"}, "M1 sieben Module laut Patrick 26.11.")
bekannt = {f.name for f in funktionen.FUNKTIONEN}
pruefe(set(M.ZU_MODUL) <= bekannt, f"M2 jede Modul-Funktion gibt es ({set(M.ZU_MODUL) - bekannt})")
pruefe(len(M.ZU_MODUL) == sum(len(m.funktionen) for m in M.MODULE), "M3 keine Funktion in zwei Modulen")
pruefe(M.normal(None) == ["alle"] and M.normal(["KI", "blech"]) == ["blech", "ki"] and M.normal(["basis"]) == ["basis"]
       and M.normal(list(M.NAMEN)) == ["alle"], "M4 Schreibweise: leer = alle, sortiert, nur Basis, alle sieben = alle")

# ------------------------------------------------------------------ Prüfstelle funktionen.an
M.setzen(["blech"])
pruefe(funktionen.an("funktion_blech") and not funktionen.an("funktion_schweissen")
       and funktionen.an("funktion_fracht") and not funktionen.zukauf_stamm(),
       "M5 nur Modul Blech: Blech an, Schweißen aus, Basis (Fracht) an, Zukauf (Einkauf) aus")
M.setzen(["basis"])
pruefe(not any(funktionen.an(f) for f in M.ZU_MODUL) and funktionen.an("funktion_schnellpreis"),
       "M6 nur Basis: alle Modul-Funktionen aus, Basis an")
M.setzen(None)
pruefe(all(funktionen.an(f) for f in M.ZU_MODUL), "M7 ohne Einschränkung (alte Lizenz, Hauptadmin): alles an")

# ------------------------------------------------------------------ Zertifikat mit Modulen
pruefe("Unbekannte Module" in wirft(L2.zertifikat_ausstellen, WZ, "X", "einzelplatz", module=["blech", "raketen"],
                                    pw=PW), "M8 unbekanntes Modul wird beim Ausstellen abgelehnt")
schl, _ = L2.zertifikat_ausstellen(WZ, "Klein GmbH", "einzelplatz", module=["vertrieb", "blech"],
                                   bis=HEUTE + datetime.timedelta(days=365), pw=PW)
P1 = tmp / "pc1" / "Lizenz"
P1.mkdir(parents=True)
stelle = lizenz.LizenzStelle(P1, None, SCHL, "RL-TEST", durchsetzung=True)
anf = A.anfrage_erstellen(P1, schl, "PC1", roh=ROH)
antw, _, _ = L2.aktivieren(WZ, anf, pw=PW)
alt_m, MERK = A.merkmale, A.merkmale(ROH)
A.merkmale = lambda roh=None: MERK
try:
    z = stelle.aktivierung_laden(A.als_code(antw))
    pruefe(z.stufe == "gueltig" and z.inhalt["funktionen"] == ["blech", "vertrieb"],
           f"M9 Aktivierung trägt die Module ({z.inhalt.get('funktionen')})")
    pruefe(funktionen.an("funktion_angebot_mail") and not funktionen.an("funktion_lernen")
           and not funktionen.an("funktion_auslastung"), "M10 nach der Prüfung: Vertrieb an, KI und Auslastung aus")
    pruefe(M.text() == "Basis, Blech, Vertrieb" and "Vertrieb" in M.text(z.inhalt["funktionen"]),
           f"M11 Text im Lizenz-Dialog ({M.text()})")
    # ------------------------------------------------------------------ Lizenzprotokoll
    zeilen = stelle.protokoll()
    pruefe(any("Aktivierung übernommen" in z_ for z_ in zeilen) and any("Zustand: gueltig" in z_ and "Vertrieb" in z_
                                                                          for z_ in zeilen),
           "M12 Protokoll: Aktivierung übernommen und Zustand mit Modulen")
    n = len(stelle.protokoll())
    stelle.pruefen()
    stelle.pruefen()
    pruefe(len(stelle.protokoll()) == n, "M13 gleiche Prüfung schreibt keine neue Zeile")
    for i in range(lizenz.PROTOKOLL_ZEILEN + 5):
        lizenz.protokoll_schreiben(P1, f"Zeile {i}")
    pruefe(len(lizenz.protokoll_lesen(P1, 5000)) == lizenz.PROTOKOLL_ZEILEN, "M14 Protokoll höchstens 1000 Zeilen")

    # ------------------------------------------------------------------ Auslastung: Modul fehlt
    from rl_auslastung import lizenzen as AL
    za = AL.Stelle(tmp / "ausl", SCHL, "RL-TEST", durchsetzung=True, kalkulation=P1).pruefen()
    pruefe(za.stufe == "lesemodus" and "Modul Auslastung" in za.grund,
           f"M15 Auslastung ohne Modul Auslastung: nur ansehen ({za.grund})")
finally:
    A.merkmale = alt_m
    M.setzen(None)

# ------------------------------------------------------------------ Werkzeug-Dialog: Haken
from PySide6.QtWidgets import QApplication  # noqa: E402

import lizenz2_fenster as F  # noqa: E402

app = QApplication.instance() or QApplication([])
d = F.LizenzDialog2(None, "Test", dict(module=["ki"]))
erst = d.module_liste()
d.modul_haken["ki"].setChecked(False)
leer = d.module_liste()
d.modul_alle.setChecked(True)
pruefe(erst == ["ki"] and leer == ["basis"] and d.module_liste() == ["alle"],
       f"M16 Haken im Lizenz-Werkzeug: KI, nur Basis, alle ({erst}, {leer})")

shutil.rmtree(tmp, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
