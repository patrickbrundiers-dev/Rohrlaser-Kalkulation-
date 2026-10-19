"""Realistische Testangebote für die Abnahme (tests/test_abnahme.py).

Je Angebot: Kopf (Maschine, Standard-Stangenlänge) und Positionen.
Felder je Position: pos, artikel, bezeichnung, profil, werkstoff, laenge, stueck, und optional
schneidweg, einstiche, stange (abweichend), a_gerade/b_gerade ("nein" = schräges Ende, Gehrung),
erwartet ("nicht eingeplant" = Teil darf nicht auf eine Stange, z. B. zu lang).
Stammdaten: Beispieldaten des Programms (RL-1: Endbeschnitt 20, Greiferrest 80, Schnittverlust 0,3,
max. 6500 mm; RL-2: 15/120/0,3, max. 8500 mm; RE 120x60x4 mit Endbeschnitt 30 und Greiferrest 120).
"""


def pos(nr, artikel, bez, profil, werkstoff, laenge, stueck, **extra):
    return dict(pos=nr, artikel=artikel, bezeichnung=bez, profil=profil, werkstoff=werkstoff,
                laenge=laenge, stueck=stueck, **extra)


RR42, RR48, QR40, RE60, RE120 = "RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"
S235, S355, VA = "S235-10219", "S355-10219", "1.4301"

ANGEBOTE = [
    dict(name="Geländer Treppenhaus", nummer="ABN-01", kunde="Metallbau Krüger", maschine="RL-1", stange=6000,
         positionen=[
             pos(10, "GL-100", "Handlauf", RR42, S235, 3480, 6, schneidweg=420, einstiche=2,
                 a_gerade="nein", b_gerade="nein"),
             pos(20, "GL-110", "Pfosten", RR42, S235, 1050, 24, schneidweg=380, einstiche=4, b_gerade="nein"),
             pos(30, "GL-120", "Knieleiste", RR42, S235, 1180, 18, schneidweg=300, einstiche=2),
             pos(40, "GL-130", "Wandhalter", RR42, S235, 95, 30, schneidweg=270, einstiche=2),
         ]),
    dict(name="Maschinengestell", nummer="ABN-02", kunde="Anlagenbau Hessler", maschine="RL-1", stange=6000,
         positionen=[
             pos(10, "MG-01", "Stiel", QR40, S235, 1960, 8, schneidweg=640, einstiche=6),
             pos(20, "MG-02", "Riegel lang", QR40, S235, 1160, 8, schneidweg=560, einstiche=4),
             pos(30, "MG-03", "Riegel kurz", QR40, S235, 760, 16, schneidweg=480, einstiche=4),
             pos(40, "MG-04", "Strebe", QR40, S235, 445, 32, schneidweg=400, einstiche=2,
                 a_gerade="nein", b_gerade="nein"),
             pos(50, "MG-05", "Holm Gehrung", RE60, S355, 2340, 4, schneidweg=820, einstiche=4,
                 a_gerade="nein", b_gerade="nein"),
             pos(60, "MG-06", "Traverse", RE60, S355, 1385.5, 6, schneidweg=610, einstiche=2),
         ]),
    dict(name="Edelstahl-Möbel", nummer="ABN-03", kunde="Objekteinrichtung Weber", maschine="RL-1", stange=6000,
         positionen=[
             pos(10, "VM-10", "Tischbein", RR42, VA, 720, 40, schneidweg=290, einstiche=2),
             pos(20, "VM-20", "Zarge", RR42, VA, 380, 80, schneidweg=310, einstiche=4),
             pos(30, "VM-30", "Fußstrebe", RR42, VA, 295, 40, schneidweg=260, einstiche=2, a_gerade="nein"),
             pos(40, "VM-40", "Rückenlehne", RR42, VA, 1415, 12, schneidweg=350, einstiche=2),
         ]),
    dict(name="Fahrzeugrahmen", nummer="ABN-04", kunde="Anhängerbau Rehm", maschine="RL-1", stange=6000,
         positionen=[
             pos(10, "FR-01", "Längsträger", RE120, S355, 5480, 4, schneidweg=1100, einstiche=8),
             pos(20, "FR-02", "Querträger", RE120, S355, 2830, 6, schneidweg=900, einstiche=6),
             pos(30, "FR-03", "Deichselstrebe", RE120, S355, 1215, 10, schneidweg=760, einstiche=4,
                 a_gerade="nein"),
             pos(40, "FR-04", "Konsole", RE120, S355, 640, 12, schneidweg=700, einstiche=4),
         ]),
    dict(name="Großserie Distanzrohre", nummer="ABN-05", kunde="Gerätebau Lindner", maschine="RL-1", stange=6000,
         positionen=[
             pos(10, "DR-145", "Distanzrohr lang", RR48, S235, 145, 500, schneidweg=310, einstiche=2),
             pos(20, "DR-098", "Distanzrohr kurz", RR48, S235, 98.5, 300, schneidweg=310, einstiche=2),
             pos(30, "DR-310", "Abstandshülse", RR48, S235, 310, 120, schneidweg=330, einstiche=3),
         ]),
    dict(name="Gemischte Qualitäten und Stangenlängen", nummer="ABN-06", kunde="Stahlbau Ostermann",
         maschine="RL-2", stange=6000,
         positionen=[
             pos(10, "GM-01", "Pfette S235", QR40, S235, 2480, 9, schneidweg=500, einstiche=2),
             pos(20, "GM-02", "Pfette S355", QR40, S355, 2480, 9, schneidweg=500, einstiche=2),
             pos(30, "GM-03", "Sparren 8 m", QR40, S235, 3950, 6, schneidweg=520, einstiche=2, stange=8000),
             pos(40, "GM-04", "Kopfband", QR40, S235, 610, 14, schneidweg=420, einstiche=2,
                 a_gerade="nein", b_gerade="nein"),
             pos(50, "GM-05", "Kopfband 8 m", QR40, S235, 610, 4, schneidweg=420, einstiche=2,
                 a_gerade="nein", b_gerade="nein", stange=8000),
         ]),
    dict(name="Grenzfälle Stangenlänge", nummer="ABN-07", kunde="Prüfangebot", maschine="RL-1", stange=6000,
         positionen=[
             # Nutzlänge RL-1: 6000 - 20 Endbeschnitt - 80 Greiferrest = 5900, davon 0,3 Schnittverlust
             pos(10, "GF-01", "Teil genau Nutzlänge", RR42, S235, 5899.7, 2, schneidweg=270, einstiche=2),
             pos(20, "GF-02", "Teil 0,1 mm zu lang", RR42, S235, 5899.8, 1, schneidweg=270, einstiche=2,
                 erwartet="nicht eingeplant"),
             pos(30, "GF-03", "Hälfte mit Trennschnitt", RR42, S235, 2949.7, 4, schneidweg=270, einstiche=2),
             pos(40, "GF-04", "Gehrungspaar", RR42, S235, 2900, 4, schneidweg=300, einstiche=2,
                 a_gerade="nein", b_gerade="nein"),
             pos(50, "GF-05", "Profil unbekannt", "XY 10x10", S235, 500, 3, erwartet="nicht eingeplant"),
         ]),
    dict(name="Nachbestellung Kleinmengen", nummer="ABN-08", kunde="Metallbau Krüger", maschine="RL-1",
         stange=6500,
         positionen=[
             pos(10, "GL-110", "Pfosten", RR42, S235, 1050, 3, schneidweg=380, einstiche=4, b_gerade="nein"),
             pos(20, "MG-03", "Riegel kurz", QR40, S235, 760, 2, schneidweg=480, einstiche=4),
             pos(30, "VM-20", "Zarge", RR42, VA, 380, 5, schneidweg=310, einstiche=4),
             pos(40, "FR-04", "Konsole", RE120, S355, 640, 1, schneidweg=700, einstiche=4),
         ]),
]

FELD = dict(profil="profil_id", werkstoff="werkstoff_id")   # Feldnamen im Programm


def programm_positionen(angebot):
    """Positionen des Angebots mit den Feldnamen des Programms (ohne Testangaben wie 'erwartet')."""
    return [{FELD.get(k, k): v for k, v in p.items() if k != "erwartet"} for p in angebot["positionen"]]
