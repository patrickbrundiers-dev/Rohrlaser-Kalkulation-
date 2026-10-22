"""Prüft die RP-Profile (Rohre mit Anschlag aus doppelt umgelegtem Blech): MegaCAD-Makros lesen, Querschnitt
(Maße, Fläche, Umfang, Schnittlänge, Doppellage, Ecken), Ablehnung von Zubehör und Zeichnungen ohne Blechdicke,
Gehrung, mitgelieferte Bibliothek RP-ROHRE in neuen und älteren Datendateien, Laden eigener Makros über die
Stammdaten-Seite 'Profile' und Querschnittsanzeige.

Aufruf: python tests/test_rp_profile.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import optimierung as opt, rp_profile, stammdaten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

MAKROS = HIER / "rp"


def ok(text):
    print("OK    ", text)


def nahe(a, b, eps=0.15):
    return abs(a - b) <= eps


# ------------------------------------------------------------------ R1 Makros lesen und Querschnitt
eintraege, meldungen = rp_profile.laden(sorted(str(p) for p in MAKROS.iterdir()))
je = {e["profil_id"]: e for e in eintraege}
assert sorted(je) == ["RP 0103-50", "RP 0106-35", "RP 0142-34", "RP 1691-36"], sorted(je)
SOLL = {   # Breite, Höhe, Wand, Fläche, Außenumfang, Schnitt gerade, davon Doppellage, Ecken
    "RP 0106-35": (50, 34, 2, 311.4, 162.0, 143.7, 15.1, 5),
    "RP 0103-50": (80, 34, 2, 429.7, 221.1, 184.6, 30.3, 6),
    "RP 0142-34": (49, 49, 2, 367.6, 190.4, 142.9, 38.1, 5),
    "RP 1691-36": (42, 36, 1.5, 216.0, 148.7, 148.7, 0.0, 8),
}
for pid, (b, h, t, a, u, s, sd, ecken) in SOLL.items():
    e = je[pid]
    ist = (e["breite"], e["hoehe"], e["wand"], e["flaeche"], e["umfang"], e["schnitt"], e["schnitt_doppel"])
    assert all(nahe(x, y) for x, y in zip(ist, (b, h, t, a, u, s, sd))), (pid, ist)
    assert e["ecken"] == ecken and e["kammern"] == 1 and e["koerper"] == 1, (pid, e["ecken"], e["kammern"])
    assert e["schnitt"] < e["umfang"] + 1e-6, pid        # Doppellage nur einmal geschnitten
assert je["RP 0106-35"]["doppellage"] == 12.0 and je["RP 0103-50"]["doppellagen"] == 2
ok("R1 Querschnitt aus Makros: Maße, Fläche, Umfang, Schnittlänge, Doppellage, Ecken")

assert len(meldungen) == 2 and meldungen[0].startswith("400180.MAC: offenes Profil"), meldungen
assert meldungen[1].startswith("640600.MAC: keine Blechdicke"), meldungen
assert rp_profile.profil_id("C:/RP/0106-35.mac") == "RP 0106-35"
ok("R2 Zubehör (offen) und Zeichnung ohne Blechdicke abgelehnt, Profil-ID 'RP ' + Dateiname")

# ------------------------------------------------------------------ R3 Gehrung
e = je["RP 0106-35"]
assert nahe(rp_profile.schnitt_gehrung(e, 0), e["schnitt"], 0.06)
g30x, g45x, g45y = (rp_profile.schnitt_gehrung(e, w, u) for w, u in ((30, "x"), (45, "x"), (45, "y")))
assert e["schnitt"] < g30x < g45x and e["schnitt"] < g45y and not nahe(g45x, g45y, 1), (g30x, g45x, g45y)
# obere Schranke: alles gestreckt mit 1/cos 45°
assert g45x < e["schnitt"] / 0.7071 + 0.1
ok(f"R3 Gehrung je Richtung: 0° {e['schnitt']:.1f}, 45° über Breite {g45x:.1f}, über Höhe {g45y:.1f} mm")

# ------------------------------------------------------------------ R4 Bibliothek und Stammdaten-Rechnung
bib = rp_profile.bibliothek()
assert len(bib) > 100 and "RP 0106-35" in bib and not any(p.startswith("RP 4001") or p == "RP 640600" for p in bib)
assert all(nahe(bib["RP 0106-35"][k], je["RP 0106-35"][k], 1e-6) for k in ("flaeche", "umfang", "schnitt"))
z = rp_profile.stammdaten_zeile(bib["RP 0106-35"])
assert z["form"] == "RP-Profil" and (z["a"], z["b"], z["wand"]) == (50, 34, 2) and z["bemerkung"] == "RP-ROHRE Serie-34"
assert nahe(stammdaten.flaeche_berechnet(dict(z, flaeche_manuell=None)), 311.4)
assert nahe(stammdaten.huellkreis(z), (50 ** 2 + 34 ** 2) ** 0.5, 0.01)
assert opt.profil_aus_name("RP 0106-35")["form"] == "RP-Profil"
assert nahe(opt.schnittlaenge("RP-Profil", 50, 34, 2, pid="RP 0106-35"), 143.7)
assert nahe(opt.umfang("RP-Profil", 50, 34, 2, pid="RP 0106-35"), 162.0)
ok(f"R4 Bibliothek ({len(bib)} Profile), Fläche, Hüllkreis, Schnittlänge, Umfang, Profil aus Name")

# ------------------------------------------------------------------ R5 Datenbank: neue und ältere Datei
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
assert "RP-Profil" in db.einstellung("profilformen") and "RP 0106-35" in k.profile
assert k.profile["RP 0106-35"]["form"] == "RP-Profil" and db.einstellung("rp_stand")
db.schliessen()
con = sqlite3.connect(tmp / "rohrlaser.db")      # älterer Stand: ohne RP-Profile, ohne Form in der Auswahl
con.execute("DELETE FROM profile WHERE profil_id LIKE 'RP %'")
con.execute("DELETE FROM einstellungen WHERE name IN ('rp_stand', 'profilformen')")
con.execute("INSERT INTO einstellungen (name, wert) VALUES ('profilformen', '\"Rundrohr\\nRechteckrohr\\nSonderprofil\"')")
con.execute("UPDATE profile SET bemerkung='eigene' WHERE rowid=(SELECT min(rowid) FROM profile)")
con.commit()
con.close()
db = Datenbank(tmp / "rohrlaser.db")
assert db.einstellung("profilformen").splitlines() == ["Rundrohr", "Rechteckrohr", "RP-Profil", "Sonderprofil"]
assert len([p for p in db.kontext().profile if p.startswith("RP ")]) == len(bib)
ok("R5 Bibliothek und Profilform in neuen und älteren Datendateien ergänzt")

# ------------------------------------------------------------------ R6 Eigene Makros über die Stammdaten laden
fenster = Hauptfenster(db, tmp, stumm=True)
seite = next(s for s in fenster.seiten if s.t.name == "profile")
db.con.execute("UPDATE profile SET a=1, wand=9 WHERE profil_id='RP 0106-35'")
db.con.commit()
neu, geaendert, mel = seite.rp_laden([str(MAKROS / "0106-35.mac"), str(MAKROS / "400180.MAC")])
assert (neu, geaendert, len(mel)) == (0, 1, 1), (neu, geaendert, mel)
p = db.kontext().profile["RP 0106-35"]
assert (p["a"], p["wand"]) == (50, 2), p
q = tmp / "1234-56.mac"
q.write_bytes((MAKROS / "0106-35.mac").read_bytes())
neu, geaendert, mel = seite.rp_laden([str(q)])
assert (neu, geaendert, mel) == (1, 0, []) and "RP 1234-56" in db.einstellung("rp_eigene")
assert opt.profil_aus_name("RP 1234-56")["form"] == "RP-Profil"
db.schliessen()
rp_profile.eigene_setzen({})
db = Datenbank(tmp / "rohrlaser.db")              # eigene Konturen nach dem Neustart wieder da
assert rp_profile.daten("RP 1234-56") and nahe(stammdaten.flaeche_berechnet(dict(form="RP-Profil", a=50, b=34, wand=2,
                                                                                 profil_id="RP 1234-56")), 311.4)
ok("R6 Makros laden: vorhandene Zeile ersetzt, neue angelegt, Zubehör gemeldet, eigene Kontur bleibt gespeichert")

# ------------------------------------------------------------------ R7 Querschnitt zeigen
fenster = Hauptfenster(db, tmp, stumm=True)
seite = next(s for s in fenster.seiten if s.t.name == "profile")
zeile = next(i for i, z in enumerate(seite.modell.daten) if z["profil_id"] == "RP 0106-35")
seite.ansicht.setCurrentIndex(seite.filter.mapFromSource(seite.modell.index(zeile, 0)))
d = seite.rp_querschnitt(stumm=True)
from PySide6.QtWidgets import QLabel  # noqa: E402
assert d is not None and any("50,0 × 34,0" in w.text() for w in d.findChildren(QLabel))
bild = d.grab()
assert bild.width() > 0
from rohrlaser.rp_dialog import kennwerte_text  # noqa: E402
assert "Doppellage 15,1 mm" in kennwerte_text(rp_profile.daten("RP 0106-35"))
seite.ansicht.setCurrentIndex(seite.filter.mapFromSource(seite.modell.index(
    next(i for i, z in enumerate(seite.modell.daten) if not z["profil_id"].startswith("RP ")), 0)))
assert seite.rp_querschnitt(stumm=True) is None
db.schliessen()
ok("R7 Querschnitt mit Kennwerten für RP-Profile, andere Profile ohne Dialog")
print("Alle RP-Profil-Prüfungen bestanden.")
