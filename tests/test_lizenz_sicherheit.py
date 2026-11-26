"""Lizenz 2.0, Paket L2-5: Sicherheitstests (Angriffe und Ausfälle) über L2-1 bis L2-4: Fälle S1–S16.

Ergänzt tests/test_aktivierung.py (Kopieren, Merkmale, Mehrfachaktivierung, Freigabe) um gezielte Angriffe:
Module/Plätze in Antwort oder Zertifikat erhöhen, fremde Antwort, fremder Signaturschlüssel, Zertifikat einer
anderen Lizenz einschmuggeln, alte Aktivierung nach Sperre zurückspielen, Sperrliste zurückdrehen oder kürzen,
Uhr zurückstellen, Werkzeug mit falschem Passwort, Protokoll/Merker fälschen, Betrieb ganz ohne Netz.
Eigene Test-Schlüssel (K9). Aufruf: python tests/test_lizenz_sicherheit.py
"""
import datetime
import json
import shutil
import socket
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
PW = b"test-passwort-lizenz-sicherheit"

import lizenz2_werkzeug as L2  # noqa: E402
import lizenz_werkzeug as W  # noqa: E402
from rohrlaser import aktivierung as A  # noqa: E402
from rohrlaser import funktionen, lizenz  # noqa: E402
from rohrlaser import module as M  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="lizenz_sicherheit_"))
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
MERK = {1: A.merkmale(ROH1), 2: A.merkmale(ROH2)}
_alt_merkmale = A.merkmale
_aktuell = [1]
A.merkmale = lambda roh=None: MERK[_aktuell[0]]


def platz(name):
    o = tmp / name / "Lizenz"
    o.mkdir(parents=True, exist_ok=True)
    return o


def zustand(o, heute=HEUTE):
    z, _ = lizenz.zustand_im_ordner(o, heute, "RL-TEST", SCHL, durchsetzung=True, merken=False)
    return z


def aktivieren(o, schl, roh, nr=1):
    _aktuell[0] = nr
    anf = A.anfrage_erstellen(o, schl, o.parent.name, roh=roh)
    antw, _, _ = L2.aktivieren(WZ, anf, pw=PW)
    A.antwort_laden(o, A.als_code(antw), SCHL, heute=HEUTE)
    return antw


def datei(o):
    return json.loads((o / A.DATEI_AKTIVIERUNG).read_text("utf-8"))


def schreiben(o, d):
    (o / A.DATEI_AKTIVIERUNG).write_text(json.dumps(d), "utf-8")


bis = HEUTE + datetime.timedelta(days=365)
schl_a, _ = L2.zertifikat_ausstellen(WZ, "Kunde A", "einzelplatz", module=["blech"], bis=bis, pw=PW)
schl_b, _ = L2.zertifikat_ausstellen(WZ, "Kunde B", "mehrplatz", 5, module=["alle"], bis=bis, pw=PW)
PA, PB = platz("pc_a"), platz("pc_b")
aktivieren(PA, schl_a, ROH1, 1)
aktivieren(PB, schl_b, ROH2, 2)
_aktuell[0] = 1
pruefe(zustand(PA).stufe == "gueltig", "S0 Ausgangslage: Kunde A gültig mit Modul Blech")
original = datei(PA)

# ------------------------------------------------------------------ Manipulation der gespeicherten Aktivierung
d = json.loads(json.dumps(original))
d["inhalt"]["zertifikat"]["inhalt"]["module"] = ["alle"]
schreiben(PA, d)
pruefe(zustand(PA).stufe == "lesemodus", "S1 Module im Zertifikat auf „alle“ gesetzt → Lesemodus")
d = json.loads(json.dumps(original))
d["inhalt"]["zertifikat"]["inhalt"]["plaetze"] = 99
d["inhalt"]["zertifikat"]["inhalt"]["aktivierungen_max"] = 100
schreiben(PA, d)
pruefe(zustand(PA).stufe == "lesemodus", "S2 Plätze im Zertifikat erhöht → Lesemodus")
d = json.loads(json.dumps(original))
d["inhalt"]["zertifikat"] = datei(PB)["inhalt"]["zertifikat"]      # gültiges Zertifikat einer anderen Lizenz
schreiben(PA, d)
pruefe(zustand(PA).stufe == "lesemodus", "S3 Zertifikat von Kunde B (alle Module, 5 Plätze) eingeschmuggelt → Lesemodus")
schreiben(PA, datei(PB))                                            # komplette Aktivierung von Kunde B
pruefe(zustand(PA).stufe == "lesemodus", "S4 ganze Aktivierung eines anderen Rechners/Kunden → Lesemodus")

# ------------------------------------------------------------------ fremder Signaturschlüssel
FREMD = tmp / "angreifer"
fremd_oeff = W.schluessel_erzeugen(FREMD, SID, b"angreifer-passwort", ausgabe=False)
fs, _ = L2.zertifikat_ausstellen(FREMD, "Raubkopie", "server", 500, module=["alle"], pw=b"angreifer-passwort")
PF = platz("pc_fremd")
_aktuell[0] = 1
anf = A.anfrage_erstellen(PF, fs, "PC", roh=ROH1)
antw_f, _, _ = L2.aktivieren(FREMD, anf, pw=b"angreifer-passwort")
pruefe("Signatur" in wirft(A.antwort_laden, PF, A.als_code(antw_f), SCHL, heute=HEUTE) and fremd_oeff != SCHL[SID],
       "S5 Aktivierung mit eigenem Schlüssel gleicher ID (K9) signiert → abgelehnt")
pruefe(not (PF / A.DATEI_AKTIVIERUNG).exists() and zustand(PF).stufe == "lesemodus",
       "S6 abgelehnte Aktivierung wird nicht gespeichert")

# ------------------------------------------------------------------ Sperre und Zurückspielen
schreiben(PA, original)
pruefe(zustand(PA).stufe == "gueltig", "S7 Original zurück: wieder gültig")
nr_a = original["inhalt"]["lizenz_nr"]
nr_a2, _ = L2.aendern(WZ, nr_a, pw=PW, bis=bis + datetime.timedelta(days=365))      # Verlängerung
L2.lizenz_sperren(WZ, nr_a2, pw=PW)
lizenz.sperrliste_uebernehmen(PA, WZ / W.SPERRLISTE, SCHL)
pruefe(zustand(PA).stufe == "lesemodus", "S8 Verlängerte Lizenz gesperrt: alte, nicht erneuerte Aktivierung ist gesperrt")
alt_sperr = json.loads((PA / lizenz.SPERRLISTE).read_text("utf-8"))
L2.deaktivieren(WZ, datei(PB)["inhalt"]["aktivierung_id"], pw=PW)       # Stand +1
lizenz.sperrliste_uebernehmen(PA, WZ / W.SPERRLISTE, SCHL)
(tmp / "alt.json").write_text(json.dumps(alt_sperr), "utf-8")
pruefe(not lizenz.sperrliste_uebernehmen(PA, tmp / "alt.json", SCHL), "S9 ältere Sperrliste ersetzt keine neuere")
gekuerzt = json.loads((PA / lizenz.SPERRLISTE).read_text("utf-8"))
gekuerzt["gesperrt"] = []
gekuerzt["stand"] += 10
(PA / lizenz.SPERRLISTE).write_text(json.dumps(gekuerzt), "utf-8")
pruefe(lizenz.sperrliste_pruefen(PA / lizenz.SPERRLISTE, SCHL) is None,
       "S10 Sperrliste von Hand gekürzt → Signatur ungültig, wird nicht verwendet")

# ------------------------------------------------------------------ Uhr, Werkzeug, Merker
PU = platz("pc_uhr")
schl_u, _ = L2.zertifikat_ausstellen(WZ, "Uhr", "einzelplatz", bis=HEUTE + datetime.timedelta(days=30), pw=PW)
aktivieren(PU, schl_u, ROH1, 1)
lizenz.zeit_merken(PU, HEUTE + datetime.timedelta(days=60))
z = zustand(PU, HEUTE)
pruefe(z.stufe == "lesemodus" and "Systemzeit" in z.grund, f"S11 Uhr zurückgestellt (nach Ablauf) → Lesemodus ({z.grund})")
vorher = (WZ / L2.REGISTER2).read_text("utf-8")
pruefe("Passwort falsch" in wirft(L2.zertifikat_ausstellen, WZ, "Dieb", "server", 50, pw=b"geraten")
       and (WZ / L2.REGISTER2).read_text("utf-8") == vorher, "S12 Werkzeug mit falschem Passwort: nichts ausgestellt")
pa_alt = original
schreiben(PA, pa_alt)
(PA / lizenz.SPERRLISTE).unlink()
stelle = lizenz.LizenzStelle(PA, None, SCHL, "RL-TEST", durchsetzung=True)
(PA / lizenz.PROTOKOLL_STAND).write_text("gueltig|False|X||alle|", "utf-8")
stelle.pruefen()
pruefe(not funktionen.an("funktion_schweissen") and funktionen.an("funktion_blech"),
       "S13 gefälschter Protokoll-Merker „alle“ ändert die Module nicht (nur Blech)")
(PA / lizenz.PROTOKOLL).unlink(missing_ok=True)
pruefe(stelle.pruefen().stufe == "gueltig", "S14 gelöschtes Lizenzprotokoll ändert den Zustand nicht")
M.setzen(None)

# ------------------------------------------------------------------ ohne Netz
_socket = socket.socket


def kein_netz(*a, **k):
    raise AssertionError("Netzverbindung versucht")


socket.socket = kein_netz
try:
    PO = platz("pc_offline")
    schl_o, _ = L2.zertifikat_ausstellen(WZ, "Offline", "einzelplatz", bis=bis, pw=PW)
    aktivieren(PO, schl_o, ROH1, 1)
    ok = zustand(PO).stufe == "gueltig"
    beleg = A.freigabe_erstellen(PO, SCHL)
    L2.freigeben(WZ, A.als_code(beleg))
    offline = ok
except AssertionError as e:
    offline = False
    print(e)
finally:
    socket.socket = _socket
pruefe(offline, "S15 Anfrage, Antwort, Prüfung und Freigabe ganz ohne Netzverbindung")

# ------------------------------------------------------------------ Hardwaretausch
PH = platz("pc_hw")
schl_h, _ = L2.zertifikat_ausstellen(WZ, "Hardware", "einzelplatz", bis=bis, pw=PW)
aktivieren(PH, schl_h, ROH1, 1)
MERK[3] = _alt_merkmale(dict(ROH1, platte="ffffffff"))
MERK[4] = _alt_merkmale(dict(ROH2, board=ROH1["board"]))
_aktuell[0] = 3
neue_platte = zustand(PH).stufe
_aktuell[0] = 4
neues_board_und_windows = zustand(PH).stufe
pruefe(neue_platte == "gueltig" and neues_board_und_windows == "lesemodus",
       "S16 neue Festplatte gültig; neues Mainboard + neues Windows → Lesemodus (neu aktivieren, Reserve)")

A.merkmale = _alt_merkmale
shutil.rmtree(tmp, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
