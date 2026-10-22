"""Maschinenplanung, Rechnung ohne Datenbank: Schichtmodell, Feiertage, Stillstände, Ende einer Belegung über
Schicht-, Tages- und Wochengrenzen, Auslastung, freie Kapazität, Terminrisiko, Überschneidungen.

Aufruf: python tests/test_planung_kalender.py
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from planung import kalender as k  # noqa: E402

T = k.zeit
# Testmodell (keine echten Schichten des Betriebs): T03 Mo–Fr 06:00–14:00 und 14:30–22:00 (30 min Pause, Maschine
# steht), LT7 nur Mo–Fr 06:00–14:00, T11 ohne Schichtmodell
SCHICHTEN = [dict(maschine="T03", wochentag=w, beginn=b, ende=e) for w in range(5)
             for b, e in (("06:00", "14:00"), ("14:30", "22:00"))] + \
            [dict(maschine="LT7", wochentag=w, beginn="06:00", ende="14:00") for w in range(5)]

# 2026-10-19 ist ein Montag
fenster = k.verfuegbare_fenster("T03", "2026-10-19T00:00", "2026-10-26T00:00", SCHICHTEN)
assert len(fenster) == 10, fenster
assert k.summe(fenster) == 5 * (480 + 450), k.summe(fenster)
assert fenster[0] == (T("2026-10-19T06:00"), T("2026-10-19T14:00")), fenster[0]
assert k.verfuegbare_fenster("T11", "2026-10-19T00:00", "2026-10-26T00:00", SCHICHTEN) == []

# Zeitraum schneidet Fenster ab
f = k.verfuegbare_fenster("T03", "2026-10-19T10:00", "2026-10-19T16:00", SCHICHTEN)
assert f == [(T("2026-10-19T10:00"), T("2026-10-19T14:00")), (T("2026-10-19T14:30"), T("2026-10-19T16:00"))], f

# Nachtschicht über Mitternacht (Ende ≤ Beginn) ragt in den nächsten Tag, auch aus dem Vortag des Zeitraums
nacht = [dict(maschine="T11", wochentag=0, beginn="22:00", ende="06:00")]
f = k.verfuegbare_fenster("T11", "2026-10-20T00:00", "2026-10-21T00:00", nacht)
assert f == [(T("2026-10-20T00:00"), T("2026-10-20T06:00"))], f
assert k.summe(k.verfuegbare_fenster("T11", "2026-10-19T00:00", "2026-10-21T00:00", nacht)) == 480

# Gültigkeit: Schichtmodell ab einem Datum
ab = [dict(maschine="LT7", wochentag=w, beginn="06:00", ende="14:00", gueltig_ab="2026-10-21") for w in range(5)]
assert k.summe(k.verfuegbare_fenster("LT7", "2026-10-19T00:00", "2026-10-26T00:00", ab)) == 3 * 480

# Ausnahmen: Feiertag für alle (Maschine leer), Zusatzschicht nur für LT7 am Samstag
aus = [dict(datum="2026-10-21", art="frei"), dict(datum="2026-10-24", maschine="LT7", art="zusatz",
                                                   beginn="08:00", ende="12:00")]
assert k.summe(k.verfuegbare_fenster("LT7", "2026-10-19T00:00", "2026-10-26T00:00", SCHICHTEN, aus)) == 4 * 480 + 240
assert k.summe(k.verfuegbare_fenster("T03", "2026-10-19T00:00", "2026-10-26T00:00", SCHICHTEN, aus)) == 4 * 930

# Stillstand schneidet aus dem Fenster heraus, über eine Pause hinweg
still = [dict(maschine="T03", beginn="2026-10-19T13:00", ende="2026-10-19T15:30")]
f = k.verfuegbare_fenster("T03", "2026-10-19T00:00", "2026-10-20T00:00", SCHICHTEN, (), still)
assert f == [(T("2026-10-19T06:00"), T("2026-10-19T13:00")), (T("2026-10-19T15:30"), T("2026-10-19T22:00"))], f

# Ende einer Belegung: Pause, Feierabend und Wochenende werden übersprungen
woche = k.verfuegbare_fenster("T03", "2026-10-19T00:00", "2026-11-02T00:00", SCHICHTEN)
assert k.ende_berechnen("2026-10-19T12:00", 180, woche) == (T("2026-10-19T12:00"), T("2026-10-19T15:30"))
assert k.ende_berechnen("2026-10-19T21:00", 120, woche) == (T("2026-10-19T21:00"), T("2026-10-20T07:00"))
assert k.ende_berechnen("2026-10-23T21:00", 120, woche) == (T("2026-10-23T21:00"), T("2026-10-26T07:00"))
# Beginn außerhalb der Schicht: Start mit der nächsten Schicht
assert k.ende_berechnen("2026-10-24T09:00", 60, woche) == (T("2026-10-26T06:00"), T("2026-10-26T07:00"))
# genau bis Schichtende
assert k.ende_berechnen("2026-10-19T06:00", 480, woche)[1] == T("2026-10-19T14:00")
# reicht nicht: Ende None
assert k.ende_berechnen("2026-10-30T06:00", 10000, woche)[1] is None

# Belegte Minuten nur in Fenstern und im Zeitraum (Tagesgrenze)
assert k.belegte_minuten("2026-10-19T21:00", "2026-10-20T07:00", woche) == 120
assert k.belegte_minuten("2026-10-19T21:00", "2026-10-20T07:00", woche, "2026-10-20T00:00", "2026-10-21T00:00") == 60

# Auslastung: Woche T03 = 4.650 min verfügbar, geplant 930 + 480 min (14:00–14:15 liegt in der Pause) = 30,3 %
bel = [dict(maschine="T03", beginn="2026-10-19T06:00", ende="2026-10-19T22:00"),
       dict(maschine="T03", beginn="2026-10-20T06:00", ende="2026-10-20T14:15"),
       dict(maschine="LT7", beginn="2026-10-19T06:00", ende="2026-10-19T14:00")]
a = k.auslastung("T03", "2026-10-19T00:00", "2026-10-26T00:00", bel, SCHICHTEN)
assert (a["verfuegbar_min"], a["geplant_min"], a["auslastung"]) == (4650, 1410, 30.3), a
assert a["frei_min"] == 4650 - 1410 and not a["ohne_schicht"]
a = k.auslastung("T11", "2026-10-19T00:00", "2026-10-26T00:00", bel, SCHICHTEN)
assert a["auslastung"] is None and a["ohne_schicht"], a
# Überlast: freie Kapazität negativ möglich, wenn Belegungen über die Woche hinaus gerechnet werden – hier Tag
a = k.auslastung("LT7", "2026-10-19T00:00", "2026-10-20T00:00", bel, SCHICHTEN)
assert a["auslastung"] == 100.0 and a["frei_min"] == 0, a

# Zeiträume: Woche beginnt Montag, Monat ganz
w = k.zeitraeume("2026-10-22", "2026-10-28", "woche")
assert [n for n, _, _ in w] == ["KW 43/2026", "KW 44/2026"], w
assert w[0][1] == T("2026-10-19T00:00")
m = k.zeitraeume("2026-12-15", "2027-01-02", "monat")
assert [(n, b) for n, b, _ in m] == [("12/2026", T("2026-12-01T00:00")), ("01/2027", T("2027-01-01T00:00"))], m
assert len(k.zeitraeume("2026-10-19", "2026-10-25", "tag")) == 7

# Terminrisiko in Arbeitstagen (Liefertermin bis Tagesende)
tage = {datetime.date(2026, 10, d) for d in (19, 20, 21, 22, 23, 26, 27)}
assert k.terminrisiko("2026-10-19T15:00", "2026-10-23", tage, 2) == ("ok", 4)
assert k.terminrisiko("2026-10-22T15:00", "2026-10-23", tage, 2) == ("kritisch", 1)
assert k.terminrisiko("2026-10-23T22:00", "2026-10-23", tage, 2) == ("kritisch", 0)
assert k.terminrisiko("2026-10-24T00:00", "2026-10-23", tage, 2) == ("kritisch", 0)   # endet um Mitternacht
assert k.terminrisiko("2026-10-26T07:00", "2026-10-23", tage, 2) == ("überschritten", -1)
assert k.terminrisiko(None, "2026-10-23", tage, 2) == ("überschritten", None)
assert k.terminrisiko("2026-10-26T07:00", None, tage, 2) == ("ohne Termin", None)

# Überschneidungen je Maschine
ue = k.ueberschneidungen([dict(id=1, maschine="T03", beginn="2026-10-19T06:00", ende="2026-10-19T10:00"),
                          dict(id=2, maschine="T03", beginn="2026-10-19T09:00", ende="2026-10-19T11:00"),
                          dict(id=3, maschine="T03", beginn="2026-10-19T11:00", ende="2026-10-19T12:00"),
                          dict(id=4, maschine="LT7", beginn="2026-10-19T06:00", ende="2026-10-19T10:00")])
assert ue == [(1, 2)], ue

# Feiertage: Ostern 2026 = 5. April, 2027 = 28. März
assert k.ostersonntag(2026) == datetime.date(2026, 4, 5) and k.ostersonntag(2027) == datetime.date(2027, 3, 28)
ft = dict((n, d) for d, n in k.bundesweite_feiertage(2026))
assert ft["Karfreitag"] == datetime.date(2026, 4, 3) and ft["Christi Himmelfahrt"] == datetime.date(2026, 5, 14)
assert ft["Pfingstmontag"] == datetime.date(2026, 5, 25) and len(ft) == 9

# Uhrzeiten
assert k.uhrzeit("6:00") == 360 and k.uhrzeit("24:00") == 1440
for falsch in ("25:00", "12:60", "abc"):
    try:
        k.uhrzeit(falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass

print("OK: Kalender, Schichten, Ausnahmen, Stillstände, Belegungsende, Auslastung, Terminrisiko")
