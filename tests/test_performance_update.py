"""Performance-Update 25.10.2026 (Plan P1-P10, Freigabe „Alles umsetzen“): schnelle Prüfungen, dass die
Beschleunigungen das Ergebnis nicht ändern.
- P1 rohr3d.netz merkt Netze: gleiche Eingaben = gleiches Netz als Kopie, andere Eingaben = neu gerechnet.
- P1 Satz/Baugruppe: Punkte in Einbaulage (ansicht3d._in_lage) gemerkt, Ergebnis wie ohne Merker gerechnet.
- P4 STEP-Export: Werkzeuge mit berührenden Hüllquadern nie in einer Gruppe, große allein; Zeitlimit wächst mit den
  Werkzeugen (300 s + 0,1 s je Werkzeug), Dauer als „etwa x min“.
- P9 Staffeln und Nachkalkulation werden erst beim Zeigen bzw. beim ersten Zugriff gefüllt.
- P10 Systemprüfung: Bewertung je Bereich, einmal je Version beim Start, Text für Release und Anleitung.

Aufruf: python tests/test_performance_update.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, rohr3d, step_export as se, systempruefung as sp  # noqa: E402


def ok(t):
    print("OK    ", t, flush=True)


def pruefe(bed, t):
    if not bed:
        print("FEHLER", t, flush=True)
        sys.exit(1)


# P1 Netz-Merker
profil = dict(form="Rundrohr", d=40.0, s=2.0, a=40.0, b=40.0)
e = dict(konturen=[dict(art="Bohrung", d=6, anzahl=1, lage="0;100;0")])
rohr3d.netz_merker_leeren()
n1 = rohr3d.netz(e, profil, 300.0)
n2 = rohr3d.netz(e, profil, 300.0)
pruefe(n1 is not None and n1 == n2 and n1 is not n2 and n1["p"] is not n2["p"], "P1 gleiches Netz als Kopie")
n2["p"][0] += 5
pruefe(rohr3d.netz(e, profil, 300.0) == n1, "P1 Änderung an der Kopie lässt den Merker unverändert")
pruefe(rohr3d.netz(e, profil, 310.0) != n1, "P1 andere Länge = anderes Netz")
pruefe(rohr3d.netz(e, profil, 300.0) == rohr3d.netz_rechnen(e, profil, 300.0), "P1 Merker = frisch gerechnet")
ok("P1 rohr3d.netz: Merker liefert Kopien, gleich wie frisch gerechnet")

# P1 Einbaulage gemerkt, bitgleich wie die Formel ohne Merker
p = [1.25, -3.5, 7.0, 10.0, 20.0, 30.0]
lage = [100.0, 5.0, -2.0, 0.0, 0.6, 0.8, 1.0, 0.0, 0.0]
o, z, x = lage[0:3], lage[3:6], lage[6:9]
y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
soll = []
for i in range(0, len(p), 3):
    soll += [round(o[k] + p[i] * x[k] + p[i + 1] * y[k] + p[i + 2] * z[k], 2) for k in range(3)]
pruefe(ansicht3d._in_lage(p, lage) == soll and ansicht3d._in_lage(p, lage) is ansicht3d._in_lage(p, lage),
       "P1 Einbaulage gemerkt und bitgleich")
netz, _ = ansicht3d.baugruppe([dict(p=p, t={"A": [0, 1, 1]}, lage=lage)])
pruefe(netz["p"] == soll, "P1 baugruppe nutzt die Einbaulage")
ok("P1 Satz/Baugruppe: Punkte in Einbaulage gemerkt, Ergebnis gleich")

# P4 Werkzeuggruppen (ohne OpenCascade: Hüllquader direkt)
import step_schreiben as ss  # noqa: E402
boxen = {"a": (0, 0, 0, 1, 1, 1), "b": (0.5, 0.5, 0.5, 2, 2, 2), "c": (5, 5, 5, 6, 6, 6), "d": None,
         "e": (1.0, 0, 0, 1.5, 1, 1)}
gruppen = ss.werkzeug_gruppen(list(boxen), huelle=boxen.get)


def beruehrt(a, b):
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


pruefe(sorted(w for g in gruppen for w in g) == sorted(boxen), "P4 jedes Werkzeug genau einmal")
pruefe(["d"] in gruppen, "P4 Werkzeug ohne Hülle (Halbraum) allein")
for g in gruppen:
    for i, a in enumerate(g):
        for b in g[i + 1:]:
            pruefe(not beruehrt(boxen[a], boxen[b]), f"P4 {a} und {b} berühren sich, aber in einer Gruppe")
pruefe(len(gruppen) <= 4, f"P4 nicht berührende Werkzeuge zusammen ({gruppen})")
viele = {i: (i * 10.0, 0, 0, i * 10.0 + 6, 6, 2) for i in range(1000)}
pruefe(len(ss.werkzeug_gruppen(list(viele), huelle=viele.get)) == 1, "P4 1.000 getrennte Bohrungen in einer Gruppe")
ok(f"P4 Werkzeuggruppen: berührende getrennt, Halbraum allein ({len(gruppen)} Gruppen für 5 Werkzeuge)")
plan = dict(teile=[dict(werkzeuge=[dict(art="zylinder")] * 50 + [dict(art="netz", ohne=[dict(art="quader")])],
                        rillen=[dict(art="quader")] * 4)])
pruefe(se.werkzeug_zahl(plan) == 56, f"P4 Werkzeuge gezählt ({se.werkzeug_zahl(plan)})")
pruefe(abs(se.zeitlimit_fuer(plan) - (se.ZEITLIMIT + 5.6)) < 1e-9, "P4 Zeitlimit 300 s + 0,1 s je Werkzeug")
pruefe(se.dauer_text(30) == "etwa 30 s" and se.dauer_text(150) == "etwa 2 min" and se.dauer_text(1) == "etwa 5 s",
       "P4 Dauer als Text")
ok("P4 Zeitlimit wächst mit den Werkzeugen, Dauer „etwa x min“")

# P5a Hinweis vor großen STEP-Dateien
from rohrlaser import step  # noqa: E402
ordner = Path(tempfile.mkdtemp())
klein, gross = ordner / "klein.step", ordner / "gross.step"
klein.write_text("ISO-10303-21;")
with open(gross, "wb") as d:
    d.truncate(int(225e6))         # leer, nur groß
pruefe(step.grosse_dateien([klein]) is None, "P5a kleine Datei ohne Hinweis")
t = step.grosse_dateien([klein, gross])
pruefe(t and "gross.step (225 MB)" in t and "etwa 9 min" in t and "etwa 9 GB" in t, f"P5a Hinweis {t!r}")
ok("P5a große STEP-Datei: Hinweis mit Dauer und Arbeitsspeicher")

# P10 Systemprüfung
zeilen = sp.pruefen(tempfile.gettempdir(), gl=(False, "Test"), bildschirm=(1280, 720))
bereiche = [z[0] for z in zeilen]
pruefe(bereiche == [b for b, _, _ in sp.VORAUSSETZUNGEN], f"P10 alle Bereiche ({bereiche})")
pruefe(dict((z[0], z[4]) for z in zeilen)["Bildschirm"] == sp.ZU_WENIG, "P10 1280 × 720 unter Minimum")
pruefe(dict((z[0], z[4]) for z in zeilen)["Grafik"] == sp.GENUG, "P10 ohne OpenGL = genug (Minimum beliebig)")
pruefe([z[0] for z in sp.unter_minimum(zeilen)].count("Bildschirm") == 1, "P10 unter_minimum")
z2 = dict((z[0], z[4]) for z in sp.pruefen(tempfile.gettempdir(), gl=(True, "GL"), bildschirm=(1920, 1080)))
pruefe(z2["Bildschirm"] == sp.OK and z2["Grafik"] == sp.OK, "P10 Full HD und OpenGL = empfohlen")
pruefe("Arbeitsspeicher: 8 GB / 16 GB" in sp.text() and "Windows" in sp.text(), "P10 Text für Release")
pruefe("<table" in sp.html(zeilen), "P10 Tabelle")
sp._takt_ghz = lambda: 1.6
zp = dict((z[0], z) for z in sp.pruefen(tempfile.gettempdir(), gl=(True, "GL"), bildschirm=(1920, 1080)))["Prozessor"]
pruefe(zp[4] in (sp.ZU_WENIG, sp.UNBEKANNT) and "1,6 GHz" in zp[1], f"P10 Takt 1,6 GHz unter Minimum ({zp})")
yml = (HIER.parent / ".github" / "workflows" / "paket.yml").read_text(encoding="utf-8")
readme = (HIER.parent / "README.md").read_text(encoding="utf-8")
for b, m, e in sp.VORAUSSETZUNGEN:
    pruefe(f"| {b} | {m} | {e} |" in readme, f"P10 README nennt {b} wie systempruefung.py")
    pruefe(m.split(" (")[0] in yml, f"P10 Release-Text nennt {b}: {m}")
pruefe(yml.count("Hilfe → Systemprüfung") >= 2, "P10 Release- und Download-Text verweisen auf die Systemprüfung")
ok("P10 Systemprüfung bewertet je Bereich (Minimum, Empfehlung)")

from rohrlaser import VERSION  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, PROGRAMM, stumm=True)
pruefe(sp.start_pruefung_noetig(db, VERSION), "P10 nach Installation prüfen")
f._start_systempruefung()
pruefe(not sp.start_pruefung_noetig(db, VERSION), "P10 danach nicht mehr")
pruefe(sp.start_pruefung_noetig(db, VERSION + ".neu"), "P10 nach Update wieder")
d = f.systempruefung_zeigen()
pruefe(len(f.systempruefung_ergebnis) == len(sp.VORAUSSETZUNGEN) and d.windowTitle() == "Systemprüfung",
       "P10 Hilfe → Systemprüfung")
menue = [a.text() for m in f.menuBar().actions() if m.menu() for a in m.menu().actions()]
pruefe("Systemprüfung …" in menue, "P10 Menüpunkt im Hilfe-Menü")
ok("P10 Start: einmal je Version, Hilfe → Systemprüfung …")

# P9 Staffeln und Nachkalkulation erst beim Zeigen
aid = db.angebot_neu(dict(kunde="P9"))
S = f.angebot_oeffnen(aid)
S.reiter.setCurrentIndex(0)
S.neu_laden()
offen = set(S.__dict__.get("_offen_fuellen", {}))
pruefe(offen == {"st_seite", "nachkalk"}, f"P9 verdeckte Seiten warten ({offen})")
S.reiter.setCurrentWidget(S._nachkalk)
pruefe("nachkalk" not in S._offen_fuellen, "P9 Nachkalkulation beim Zeigen gefüllt")
pruefe(S.st_seite is S._st_seite and "st_seite" not in S._offen_fuellen, "P9 Zugriff füllt die Staffeln")
S.neu_laden()
pruefe("nachkalk" not in S._offen_fuellen, "P9 sichtbare Seite sofort gefüllt")
ok("P9 Staffeln und Nachkalkulation erst beim Zeigen bzw. Zugriff")
print("Alle Prüfungen Performance-Update bestanden.")
os._exit(0)
