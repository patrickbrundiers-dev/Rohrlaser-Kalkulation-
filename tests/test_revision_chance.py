"""Plan Neuerungen B1 + B3 (Patrick 10.11.2026, Freigabe „Alle Empfehlungen“): neue Revision eines bekannten Artikels
erkennen (was sich geändert hat, Preis heute/damals) und Auftragschance als Ampel in der Angebotsliste."""
import datetime
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import funktionen, lernen  # noqa: E402
from rohrlaser import wiederholteile as wt  # noqa: E402
from rohrlaser.angebot_fenster import CHANCE_SPALTE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ B1 ohne Datenbank
alt = dict(artikel="4711-001", profil_id="RR 42,4x2,0", werkstoff_id="S235", laenge=1250.0, schneidweg=410.0, klein_n=2)
assert wt.aenderungen(dict(alt), alt) == []
assert wt.aenderungen(dict(alt, laenge=1250.4, schneidweg=413.0), alt) == []            # innerhalb der Toleranzen
assert wt.aenderungen(dict(alt, laenge=1290.0, klein_n=4, schneidweg=492.0), alt) == \
    ["40 mm länger", "2 Konturen mehr", "Schneidweg +20 %"], wt.aenderungen(dict(alt, laenge=1290.0, klein_n=4,
                                                                                 schneidweg=492.0), alt)
assert wt.aenderungen(dict(alt, laenge=1237.5, klein_n=1), alt) == ["12,5 mm kürzer", "1 Kontur weniger"]
assert wt.aenderungen(dict(alt, profil_id="RR 48,3x2,0", werkstoff_id="S355"), alt) == \
    ["Profil RR 48,3x2,0 statt RR 42,4x2,0", "Werkstoff S355 statt S235"]
assert wt.aenderungen(dict(alt, schneidweg=None, laenge=None), alt) == []                # fehlende Werte: kein Befund
ok("B1: Änderungen als Text (Länge, Konturen, Schneidweg, Profil, Werkstoff), Toleranzen wie bei gleicher Geometrie")

# ------------------------------------------------------------------ B1 im Angebot
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
alt_id = beispiel_angebot.anlegen(db, dict(datum="2026-09-12"))
db.vorgang_setzen(alt_id, "Beauftragt")
s_alt = f.angebot_oeffnen(alt_id)
assert s_alt.optimieren() and s_alt.staffelpreise_rechnen()
alt_nr = s_alt.kopf["nummer"]

neu_id = db.angebot_neu(dict(kundennr="K-10045", kunde="Beispiel GmbH"))
db.position_neu(neu_id, dict(beispiel_angebot.POSITIONEN[0], laenge=1290.0, klein_n=2, schneidweg=492.6))
db.position_neu(neu_id, dict(beispiel_angebot.POSITIONEN[1]))                            # unverändert
s = f.angebot_oeffnen(neu_id)
treffer = s.wiederholteile_suchen()
pos = {p["pos"]: p for p in s.positionen}
t10, t20 = treffer[pos[10]["id"]][0], treffer[pos[20]["id"]][0]
assert t10.art == wt.SICHER and t10.geaendert == ["40 mm länger", "2 Konturen mehr", "Schneidweg +20 %"], t10.geaendert
assert t20.art == wt.SICHER and t20.geaendert == []
s.wiederholteile_anzeigen()
text = s.uebersicht_bereich.wiederholteile.text()
assert text.count("Neue Revision") == 1 and f"geändert gegenüber {alt_nr}: 40 mm länger" in text, text
assert "1 geändert" in s.uebersicht_bereich.wiederholteile_bereich.knopf.text()
ok("B1: Wiederholteile zeigen die neue Revision nur am geänderten Artikel, mit Angebot und Änderungen")

punkte = wt.revision_punkte(treffer, s.positionen, s.kopf.get("staffelpreise"))
assert len(punkte) == 1 and punkte[0][0] == "HINWEIS" and punkte[0][2] == 0, punkte
t = punkte[0][1]
assert t.startswith(f"Pos. 10: Artikel 4711-001 geändert gegenüber {alt_nr}: 40 mm länger, 2 Konturen mehr") and \
    "Damals" in t and "bei 24 Stk" in t and "heute" not in t, t
db.staffel_neu(neu_id, dict(schluessel="10", menge=24))
s.neu_laden()
assert s.optimieren() and s.staffelpreise_rechnen()
treffer = s.wiederholteile_suchen()
t = wt.revision_punkte(treffer, s.positionen, s.kopf.get("staffelpreise"))[0][1]
assert "Staffelpreis bei 24 Stk heute" in t and "damals" in t and " %)" in t, t
check = " | ".join(str(p[1]) for p in s.freigabe_punkte())
assert "geändert gegenüber" in check, check
ok("B1: Angebots-Check nennt die Änderung und den Staffelpreis heute und damals: " + t)

# ------------------------------------------------------------------ B3 Rechnung
heute = datetime.date(2026, 11, 8)


def z(i, kunde, vorgang, netto, datum="2026-11-01"):
    return dict(id=i, kundennr=kunde, kunde=kunde, vorgang=vorgang, vk_netto=netto, datum=datum, versand=[])


liste = [z(1, "A", "Beauftragt", 1000), z(2, "A", "Beauftragt", 1200), z(3, "A", "Beauftragt", 900),
         z(4, "B", "Abgelehnt", 1000), z(5, "B", "Abgelehnt", 1100), z(6, "B", "Abgelehnt", 800),
         z(7, "A", "Verschickt", 1000), z(8, "B", "Verschickt", 1000), z(9, "A", "Verschickt", 1000, "2026-05-01")]
g = lernen.chancen_grund(liste, heute)
assert {i: q for i, (q, _) in g.items()} == lernen.chancen(liste, heute)
assert "Kunde: 3 von 3 entschiedenen Angeboten beauftragt" in g[7][1] and "Alle Angebote: 3 von 6" in g[7][1], g[7][1]
assert "Kunde: 0 von 3" in g[8][1] and "Faktor 0,25" in g[9][1], (g[8][1], g[9][1])
assert [lernen.chance_ampel(q) for q in (0.6, 0.5, 0.3, 0.1)] == ["grün", "grün", "gelb", "rot"]
assert lernen.chance_ampel(g[7][0]) == "grün" and lernen.chance_ampel(g[9][0]) == "rot", (g[7][0], g[9][0])
ok(f"B3: Chance mit Begründung, Ampel grün ab 50 %, gelb ab 25 % (Kunde A {100 * g[7][0]:.0f} %, "
   f"Kunde B {100 * g[8][0]:.0f} %)")

# ------------------------------------------------------------------ B3 Angebotsliste
seite = f.angebote
spalte = next(c for c, sp in enumerate(seite.SPALTEN) if sp[0] == CHANCE_SPALTE)
seite.neu_laden()
assert seite.ansicht.isColumnHidden(spalte), "zu wenig entschiedene Angebote: Spalte bleibt weg"
for kunde, vorgang in (("K-10045", "Beauftragt"), ("K-10045", "Beauftragt"), ("K-2", "Abgelehnt"), ("K-2", "Abgelehnt"),
                       ("K-2", "Abgelehnt")):
    i = beispiel_angebot.anlegen(db, dict(kundennr=kunde, kunde=kunde))
    db.vorgang_setzen(i, vorgang)
offen_a = beispiel_angebot.anlegen(db, dict(kundennr="K-10045", kunde="Beispiel GmbH"))
offen_b = beispiel_angebot.anlegen(db, dict(kundennr="K-2", kunde="K-2"))
db.vorgang_setzen(offen_a, "Verschickt")
db.vorgang_setzen(offen_b, "Verschickt")
funktionen.db_setzen(db)
seite.neu_laden()
assert not seite.ansicht.isColumnHidden(spalte)
m = seite.modell
zeile = {zz["id"]: r for r, zz in enumerate(m.zeilen)}
ia, ib = m.index(zeile[offen_a], spalte), m.index(zeile[offen_b], spalte)
wa, wb = m.wert(zeile[offen_a], spalte), m.wert(zeile[offen_b], spalte)
assert wa > wb and m.wert(zeile[alt_id], spalte) is None, (wa, wb)
assert m.data(ia, Qt.ItemDataRole.BackgroundRole) is not None and \
    m.data(ia, Qt.ItemDataRole.BackgroundRole).color() != m.data(ib, Qt.ItemDataRole.BackgroundRole).color()
assert "Geschätzte Auftragschance" in m.data(ia, Qt.ItemDataRole.ToolTipRole)
assert m.data(m.index(zeile[alt_id], spalte), Qt.ItemDataRole.BackgroundRole) is None
ok(f"B3: Angebotsliste Spalte Chance [%] nur bei verschickten Angeboten ({wa} % und {wb} %), Ampelfarbe, Begründung "
   "im Tooltip")

db.einstellung_setzen(funktionen.CHANCE, "nein")
seite.neu_laden()
assert seite.ansicht.isColumnHidden(spalte)
db.einstellung_setzen(funktionen.CHANCE, "ja")
ok("B3: Funktion Auftragschance aus: Spalte ausgeblendet")
print("OK: Revision und Chance")
