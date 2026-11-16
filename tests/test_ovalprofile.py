"""Profilformen Flachoval, Halbflachoval, Elliptisch (Plan ArTube-Unterlagen G1, Patrick 12.11.2026):
- O1 Umfang (Trennschnitt) und Querschnitt (Gewicht) gegen eigene Rechnung
- O2 Profil-ID 'FO 60x30x2', 'HFO 60x25x2', 'EL 60x30x2' wird erkannt, ungültige Maße nicht
- O3 Umriss für Bilder (außen und innen, im Hüllrechteck), Auswahlliste Profilformen
- O4 Angebot: Profil aus der Profil-ID angelegt, Schnittplan mit Trennschnitt = Umfang

Aufruf: python tests/test_ovalprofile.py
"""
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import optimierung as opt, ovalprofile as ov, rechnen, skizze, stammdaten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    assert abs(a - b) < eps, (a, b)


# ------------------------------------------------------------------ O1
nah(ov.umfang(ov.FLACHOVAL, 60, 30), 2 * 30 + math.pi * 30)
nah(ov.umfang(ov.HALBFLACHOVAL, 60, 25), 60 + 10 + math.pi * 25)
nah(ov.umfang(ov.ELLIPTISCH, 40, 40), math.pi * 40)              # Ellipse mit gleichen Achsen = Kreis
voll = lambda a, b: (a - b) * b + math.pi * b * b / 4             # noqa: E731
nah(ov.flaeche(ov.FLACHOVAL, 60, 30, 2), voll(60, 30) - voll(56, 26))
nah(ov.flaeche(ov.ELLIPTISCH, 60, 30, 2), math.pi / 4 * (60 * 30 - 56 * 26))
assert ov.flaeche(ov.HALBFLACHOVAL, 40, 30, 2) is None and ov.umfang(ov.FLACHOVAL, 20, 30) == 0
ok("O1 Umfang und Querschnitt Flachoval, Halbflachoval, Elliptisch")

# ------------------------------------------------------------------ O2
d = opt.profil_aus_name("FO 60x30x2")
assert d == dict(form=ov.FLACHOVAL, a=60, b=30, wand=2), d
assert opt.profil_aus_name("HFO 60x25x2")["form"] == ov.HALBFLACHOVAL
assert opt.profil_aus_name("EL 60x30x2")["form"] == ov.ELLIPTISCH
assert opt.profil_aus_name("HFO 40x30x2") is None and opt.profil_aus_name("FO 60x30x16") is None
nah(stammdaten.flaeche_berechnet(dict(d, profil_id="FO 60x30x2")), ov.flaeche(ov.FLACHOVAL, 60, 30, 2))
nah(opt.schnittlaenge(ov.FLACHOVAL, 60, 30, 2), ov.umfang(ov.FLACHOVAL, 60, 30))
ok("O2 Profil-IDs FO/HFO/EL erkannt, ungültige Maße abgelehnt")

# ------------------------------------------------------------------ O3
for form, a, b in ((ov.FLACHOVAL, 60, 30), (ov.HALBFLACHOVAL, 60, 25), (ov.ELLIPTISCH, 60, 30)):
    qs = skizze.Querschnitt(dict(form=form, a=a, b=b, wand=2, profil_id="x"))
    assert len(qs.umriss) == 2 and qs.B == a and qs.H == b, (form, len(qs.umriss))
    for poly in qs.umriss:
        assert all(abs(u) <= a / 2 + 1e-6 and abs(v) <= b / 2 + 1e-6 for u, v in poly), form
    assert [f.name for f in qs.flaechen] == ["oben", "vorne", "unten", "hinten"]
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "o.db")
formen = db.einstellung("profilformen").splitlines()
assert all(f in formen for f in ov.FORMEN) and formen.index(ov.ELLIPTISCH) < formen.index("Sonderprofil")
ok("O3 Umriss außen/innen im Hüllrechteck, Auswahlliste mit den drei Formen")

# ------------------------------------------------------------------ O4
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="O1", profil_id="FO 60x30x2", werkstoff_id="S235-10219", laenge=800,
                        stueck=5))
kopf, pos = db.angebot(a), db.positionen(a)
erg = rechnen.optimieren(kopf, pos, db.kontext(), db.tabellen(), db.einstellungen())
neu = [p for p in erg["neue_profile"] if p.get("profil_id") == "FO 60x30x2"] if erg.get("neue_profile") else []
assert neu and neu[0]["form"] == ov.FLACHOVAL, erg.get("neue_profile")
assert erg["stangen"] and not erg["fehler"], erg["fehler"]
ok(f"O4 Angebot mit FO 60x30x2: Profil angelegt, {len(erg['stangen'])} Stange(n)")
print("Alle Tests Profilformen oval bestanden.")
