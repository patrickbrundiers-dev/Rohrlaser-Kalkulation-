"""Lizenz 2.0, Paket L2-1 (programm/rohrlaser/aktivierung.py, werkzeuge/lizenz2_werkzeug.py): Fälle A1–A24.

Jeder Lauf erzeugt eigene Test-Schlüssel (Schlüssel-ID K9); der echte Lizenzschlüssel kommt nicht vor.
Aufruf: python tests/test_aktivierung.py
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
PW = b"test-passwort-aktivierung"
os.environ["ROHRLASER_LIZENZ_PASSWORT"] = PW.decode()

import lizenz2_werkzeug as L2  # noqa: E402
import lizenz_werkzeug as W  # noqa: E402

from rohrlaser import aktivierung as A  # noqa: E402
from rohrlaser import lizenz  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="aktivierung_"))
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


HEUTE = datetime.date(2026, 11, 26)
WZ = tmp / "werkzeug"
SID = "K9"
oeff = W.schluessel_erzeugen(WZ, SID, PW, ausgabe=False)
SCHL = {SID: oeff}
ROH1 = dict(guid="aaaa-1111", platte="0A0B0C0D", board="ASUS|PRIME B550|AMD Ryzen 7")
ROH2 = dict(guid="bbbb-2222", platte="11223344", board="Dell|OptiPlex|Intel i5")
M1, M2 = A.merkmale(ROH1), A.merkmale(ROH2)


def platz(name):
    o = tmp / name / "Lizenz"
    o.mkdir(parents=True, exist_ok=True)
    return o


def zustand(o, merk=M1, heute=HEUTE, **k):
    """lizenz.zustand_im_ordner mit Test-Schlüssel und festen Merkmalen."""
    alt = A.merkmale
    A.merkmale = lambda roh=None: merk
    try:
        z, _ = lizenz.zustand_im_ordner(o, heute, "RL-TEST", SCHL, durchsetzung=True, merken=False, **k)
    finally:
        A.merkmale = alt
    return z


# ------------------------------------------------------------------ Lizenzschlüssel
s = A.schluessel_neu()
pruefe(s.startswith("LZ-") and len(s) == 26 and A.schluessel_normal(s) == s, f"A1 Lizenzschlüssel-Format ({s})")
pruefe(A.schluessel_normal(s.lower().replace("-", " ")) == s, "A2 Schreibweise egal (klein, Leerzeichen)")
falsch = s[:-1] + ("0" if s[-1] != "0" else "1")
pruefe(A.schluessel_normal(falsch) == "", "A3 Tippfehler im letzten Zeichen erkannt (Prüfzeichen)")
treffer = sum(1 for i in range(3, 26) if s[i] != "-" and A.schluessel_normal(
    s[:i] + ("2" if s[i] != "2" else "3") + s[i + 1:]))
pruefe(treffer <= 2, f"A3b einzelne Tippfehler fast immer erkannt ({treffer} von 20 durchgerutscht)")

# ------------------------------------------------------------------ Zertifikat
schl1, zdatei = L2.zertifikat_ausstellen(WZ, "Max Muster", "mehrplatz", 2, firma="Musterbau GmbH", reserve=1,
                                         bis=HEUTE + datetime.timedelta(days=365), heute=HEUTE, pw=PW)
zert = json.loads(zdatei.read_text("utf-8"))
z_inhalt = A.zertifikat_pruefen(zert, SCHL)
pruefe(z_inhalt["plaetze"] == 2 and z_inhalt["aktivierungen_max"] == 3 and schl1 not in zdatei.read_text("utf-8"),
       "A4 Zertifikat: 2 Plätze + 1 Reserve, Lizenzschlüssel steht nicht im Klartext darin")
manip = json.loads(json.dumps(zert))
manip["inhalt"]["plaetze"] = 50
pruefe("Signatur" in wirft(A.zertifikat_pruefen, manip, SCHL), "A5 Plätze im Zertifikat erhöht → Signatur ungültig")

# ------------------------------------------------------------------ Anfrage → Antwort → laden
P1 = platz("pc1")
anfrage = A.anfrage_erstellen(P1, schl1, "PC-BUERO", roh=ROH1)
pruefe(A.anfrage_pruefen(A.als_code(anfrage))["merkmale"] == M1, "A6 Anfrage als Code hin und zurück, Signatur gültig")
pruefe("guid" not in json.dumps(anfrage) or "aaaa-1111" not in json.dumps(anfrage),
       "A7 Anfrage enthält keine Klartext-Merkmale")
anf_m = json.loads(json.dumps(anfrage))
anf_m["inhalt"]["merkmale"]["guid"] = "0" * 16
pruefe("verändert" in wirft(A.anfrage_pruefen, anf_m), "A8 veränderte Anfrage wird abgelehnt")
pruefe(wirft(A.anfrage_erstellen, P1, falsch) != "", "A9 Lizenzschlüssel mit Tippfehler: keine Anfrage")

antwort, adatei, text = L2.aktivieren(WZ, A.als_code(anfrage), heute=HEUTE, pw=PW)
pruefe(antwort["inhalt"]["aktivierung_id"] == "AK-2026-00001" and "1 von 3" in text, f"A10 Aktivierung ({text})")
A.antwort_laden(P1, A.als_code(antwort), SCHL, ist_merkmale=M1, heute=HEUTE)
z = zustand(P1)
pruefe(z.stufe == "gueltig" and z.inhalt["typ"] == "mehrplatz" and z.inhalt["aktivierung_id"] == "AK-2026-00001",
       f"A11 Zustand nach Aktivierung gültig ({z.stufe} {z.grund})")

# ------------------------------------------------------------------ Kopieren und Manipulation
P2 = platz("pc2")
for f in (A.DATEI_AKTIVIERUNG, A.DATEI_GERAET):
    shutil.copy2(P1 / f, P2 / f)
z = zustand(P2, merk=M2)
pruefe(z.stufe == "lesemodus" and "passt nicht" in z.grund, f"A12 Lizenzordner auf anderen Rechner kopiert → Lesemodus "
                                                            f"({z.grund})")
gemischt = dict(M2, board=M1["board"])
pruefe(zustand(P1, merk=gemischt).stufe == "lesemodus", "A13 nur 1 von 3 Merkmalen gleich → Lesemodus")
pruefe(zustand(P1, merk=dict(M1, platte="ffff")).stufe == "gueltig", "A14 neue Festplatte (2 von 3) → weiter gültig")
P3 = platz("pc3")
shutil.copy2(P1 / A.DATEI_AKTIVIERUNG, P3 / A.DATEI_AKTIVIERUNG)
A.geraet_erzeugen(P3)
z = zustand(P3, merk=M1)
pruefe(z.stufe == "lesemodus" and "anderen Rechner" in z.grund,
       f"A15 Aktivierung mit fremdem Geräteschlüssel (gleiche Merkmale gefälscht) → Lesemodus ({z.grund})")
d = json.loads((P1 / A.DATEI_AKTIVIERUNG).read_text("utf-8"))
d["inhalt"]["zertifikat"]["inhalt"]["gueltig_bis"] = "2099-12-31"
(P3 / A.DATEI_AKTIVIERUNG).write_text(json.dumps(d), "utf-8")
shutil.copy2(P1 / A.DATEI_GERAET, P3 / A.DATEI_GERAET)
pruefe(zustand(P3).stufe == "lesemodus", "A16 Ablaufdatum in der Aktivierung geändert → Lesemodus")
pruefe(wirft(A.geraet_laden, P1, plattform="win32") != "",
       "A17 unter Windows wird ein ungeschützter Geräteschlüssel nicht angenommen")

# ------------------------------------------------------------------ Plätze zählen, Neuinstallation, Freigabe
antwort_b, _, _ = L2.aktivieren(WZ, anfrage, heute=HEUTE, pw=PW)
pruefe(antwort_b["inhalt"]["aktivierung_id"] == "AK-2026-00001" and len(L2.aktive(L2.register_lesen(WZ),
                                                                                    "LN-2026-0001")) == 1,
       "A18 gleiche Anfrage noch einmal: kein zusätzlicher Platz")
P4 = platz("pc1_neu")       # Windows neu installiert: neuer Geräteschlüssel, neue GUID, gleiche Platte/Board
roh_neu = dict(ROH1, guid="neu-guid")
a4 = A.anfrage_erstellen(P4, schl1, "PC-BUERO", roh=roh_neu)
antw4, _, text4 = L2.aktivieren(WZ, a4, heute=HEUTE, pw=PW)
pruefe("neu installiert" in text4 and len(L2.aktive(L2.register_lesen(WZ), "LN-2026-0001")) == 1,
       f"A19 Neuinstallation gleicher Rechner: alter Platz frei, keine Reserve verbraucht ({text4})")
plaetze = []
for n, roh in enumerate(({"guid": "g2", "platte": "p2", "board": "b2"}, {"guid": "g3", "platte": "p3", "board": "b3"})):
    p = platz(f"weiter{n}")
    plaetze.append(p)
    L2.aktivieren(WZ, A.anfrage_erstellen(p, schl1, f"PC{n}", roh=roh), heute=HEUTE, pw=PW)
p5 = platz("zu_viel")
meldung = wirft(L2.aktivieren, WZ, A.anfrage_erstellen(p5, schl1, "PC9", roh=dict(guid="g9", platte="p9", board="b9")),
                heute=HEUTE, pw=PW)
pruefe("belegt" in meldung, "A20 vierte Aktivierung bei 2 Plätzen + 1 Reserve abgelehnt")
A.antwort_laden(P4, antw4, SCHL, ist_merkmale=A.merkmale(roh_neu), heute=HEUTE)
beleg = A.freigabe_erstellen(P4, SCHL)
pruefe(not (P4 / A.DATEI_AKTIVIERUNG).exists() and not (P4 / A.DATEI_GERAET).exists(),
       "A21 Platz freigeben: Aktivierung und Geräteschlüssel entfernt")
aid = L2.freigeben(WZ, A.als_code(beleg), heute=HEUTE)
pruefe(aid == antw4["inhalt"]["aktivierung_id"] and len(L2.aktive(L2.register_lesen(WZ), "LN-2026-0001")) == 2,
       "A22 Freigabebeleg im Werkzeug verbucht, Platz wieder frei")
beleg_m = json.loads(json.dumps(beleg))
beleg_m["inhalt"]["aktivierung_id"] = "AK-2026-00003"
pruefe(wirft(L2.freigeben, WZ, beleg_m, heute=HEUTE) != "", "A22b gefälschter Freigabebeleg für fremden Platz abgelehnt")

# ------------------------------------------------------------------ Sperrliste, Ablauf, alte Lizenz
sperr = lizenz.sperrliste_signieren(1, ["AK-2026-00001"], W.privat_laden(WZ, SID, PW), SID)
lizenz.sperrliste_uebernehmen(P1, sperr, SCHL)
z = zustand(P1)
pruefe(z.stufe == "lesemodus" and "deaktiviert" in z.grund, f"A23 Platz über die Sperrliste deaktiviert ({z.grund})")
(P1 / lizenz.SPERRLISTE).unlink()
z = zustand(P1, heute=HEUTE + datetime.timedelta(days=364 + 10))
pruefe(z.stufe == "kulanz", f"A24 nach Ablauf erst Kulanz ({z.stufe})")
z = zustand(P1, heute=HEUTE + datetime.timedelta(days=364 + 20))
pruefe(z.stufe == "lesemodus" and z.nur_lesen, "A24b nach Kulanz Lesemodus, Daten bleiben lesbar")

alt_privat = W.privat_laden(WZ, SID, PW)
alt_inhalt = dict(lizenz_id="L-2026-0042", art="benutzer", inhaber="Max", firma="Musterbau", ausgestellt="2026-11-01",
                  gueltig_ab="2026-11-01", gueltig_bis="2027-02-01", rechner=["RL-TEST"], funktionen=["alle"],
                  test=False, schluessel_id=SID, hinweis="")
alte = dict(format=1, inhalt=alt_inhalt, signatur=lizenz.signieren(alt_inhalt, alt_privat))
lizenz.lizenz_laden(P2, alte, HEUTE, "RL-TEST", SCHL)
z = zustand(P2, merk=M2)
pruefe(z.stufe == "gueltig" and z.inhalt["lizenz_id"] == "L-2026-0042",
       "A25 ungültige Aktivierung, aber alte Lizenzdatei gültig → alte Lizenz gilt weiter")

schl_k, _ = L2.zertifikat_ausstellen(WZ, "Kauf AG", "einzelplatz", heute=HEUTE, pw=PW)
P6 = platz("kauf")
antw6, _, _ = L2.aktivieren(WZ, A.anfrage_erstellen(P6, schl_k, roh=ROH2), heute=HEUTE, pw=PW)
A.antwort_laden(P6, antw6, SCHL, ist_merkmale=M2, heute=HEUTE)
z = zustand(P6, merk=M2, heute=HEUTE + datetime.timedelta(days=4000))
pruefe(z.stufe == "gueltig" and z.inhalt["plaetze"] == 1, "A26 Kauflizenz ohne Ablauf bleibt gültig")
anfr_neu = A.anfrage_erstellen(P6, schl_k, roh=ROH2)
pruefe(zustand(P6, merk=M2).stufe == "gueltig", "A27 neue Anfrage (z. B. Verlängerung) macht die laufende Aktivierung "
                                                 "nicht ungültig")
pruefe(A.ist_format2(A.als_code(antw6)) and not A.ist_format2(alte), "A28 Antwortdatei wird als Lizenz 2.0 erkannt")

# ------------------------------------------------------------------ LizenzStelle und Dialog
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.lizenz_dialog import LizenzDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
P7 = platz("dialog")
stelle = lizenz.LizenzStelle(P7, None, SCHL, "RL-TEST", durchsetzung=True)
dlg = LizenzDialog(None, stelle, stumm=True)
anf7, code7 = dlg.aktivieren(schl1)
pruefe(code7.startswith("ANFRAGE-") and (P7 / A.DATEI_GERAET).exists(), "A29 Dialog erstellt Anfrage und Code")
antw7, _, _ = L2.aktivieren(WZ, anf7, heute=HEUTE, pw=PW)
alt_m = A.merkmale
A.merkmale = lambda roh=None: anf7["inhalt"]["merkmale"]
try:
    ok = dlg.aktivierung_einfuegen(A.als_code(antw7))
    pruefe(ok and stelle.zustand.stufe == "gueltig" and dlg.freigeben_knopf.isVisibleTo(dlg),
           "A30 Dialog übernimmt Aktivierungscode, Knopf „Platz freigeben“ sichtbar")
    pruefe("Mehrplatz-Lizenz LN-2026-0001" in stelle.text(), f"A31 Text für Hilfe → Über ({stelle.text()})")
    pruefe(not dlg.aktivierung_einfuegen("AKTIVIERUNG-KAPUTT"), "A32 kaputter Code wird abgelehnt, nichts geändert")
    beleg7 = dlg.platz_freigeben(bestaetigt=True)
    pruefe(beleg7 and stelle.zustand.stufe == "lesemodus" and not dlg.freigeben_knopf.isVisibleTo(dlg),
           "A33 Dialog gibt den Platz frei")
finally:
    A.merkmale = alt_m

# ------------------------------------------------------------------ Werkzeug-Befehle
os.environ["ROHRLASER_LIZENZ_ORDNER"] = str(WZ)
pruefe(W.main(["liste2"]) == 0, "A34 lizenz_werkzeug liste2 läuft")

shutil.rmtree(tmp, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
