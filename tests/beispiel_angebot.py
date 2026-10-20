"""Beispielangebot mit Satz und Staffeln für die Tests (Kopf, Positionen, Mengenstufen)."""

KOPF = dict(nummer="A-2026-0001", kundennr="K-10045", kunde="Beispiel GmbH", datum="2026-10-15", maschine="T11",
            stange=6000)
POSITIONEN = [
    dict(pos=10, artikel="4711-001", bezeichnung="Holm links", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
         laenge=1250.0, stueck=24, schneidweg=410.5, einstiche=4),
    dict(pos=20, artikel="4711-002", bezeichnung="Querstrebe", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
         laenge=860.0, stueck=40, schneidweg=302.0, einstiche=2),
    dict(pos=30, artikel="4711-003", bezeichnung="Rahmen oben", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
         laenge=2150.0, stueck=12, schneidweg=520.0, einstiche=3, satz="Rahmen", je_satz=3),
    dict(pos=40, artikel="4711-004", bezeichnung="Stütze", profil_id="RE 60x40x3", werkstoff_id="S355-10219",
         laenge=1795.5, stueck=16, schneidweg=618.2, einstiche=4, satz="Rahmen", je_satz=4),
    dict(pos=50, artikel="4711-005", bezeichnung="Anschlag", profil_id="RR 48,3x2,6", werkstoff_id="S235-10219",
         laenge=345.0, stueck=60, schneidweg=255.0, einstiche=2),
]
STAFFELN = [dict(schluessel="Rahmen", menge=2, bemerkung="Beispiel: Satz aus Pos. 30 und 40"),
            dict(schluessel="Rahmen", menge=4), dict(schluessel="Rahmen", menge=8),
            dict(schluessel="10", menge=24, bemerkung="Beispiel: Einzelposition"),
            dict(schluessel="10", menge=50), dict(schluessel="10", menge=100)]


def anlegen(db, kopf=None):
    """Beispielangebot in der Datenbank anlegen (neue Nummer, wenn die Nummer schon vergeben ist)."""
    kopf = dict(KOPF, **(kopf or {}))
    if any(a["nummer"] == kopf["nummer"] for a in db.angebote()):
        kopf.pop("nummer")
    i = db.angebot_neu(kopf)
    for p in POSITIONEN:
        db.position_neu(i, p)
    for st in STAFFELN:
        db.staffel_neu(i, st)
    return i
