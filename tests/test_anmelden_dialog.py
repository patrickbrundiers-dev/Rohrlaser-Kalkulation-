"""Start-Login (rollen_seite.AnmeldenDialog): Mitarbeiter aus einer Liste wählen, nur Passwort/PIN eingeben
(Patrick 27.11.2026).

- Mit angelegten Benutzern: Auswahlliste „Name (Kürzel)“, nach Name sortiert, der zuletzt angemeldete vorbelegt;
  _kuerzel() liefert das Kürzel der Auswahl; nur aktive Benutzer mit Passwort/PIN stehen drin.
- Ohne Benutzer: Kürzel wird von Hand eingegeben (wie bisher).
Aufruf: python tests/test_anmelden_dialog.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rollen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.rollen_seite import AnmeldenDialog  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")

# ohne Benutzer: Kürzelfeld
d = AnmeldenDialog(None, db)
assert d.auswahl is None and d.kuerzel is not None, "ohne Benutzer: Kürzel von Hand"
ok("ohne angelegte Benutzer: Kürzel wird von Hand eingegeben")

for k, n, rl, akt, pw_ in (("ZM", "Zoe Maier", rollen.LEITUNG, True, "Geheim-1"),
                           ("AB", "Anna Becker", rollen.WERKSTATT, True, "Geheim-2"),
                           ("XX", "Gesperrt", rollen.WERKSTATT, False, "Geheim-3"),
                           ("OP", "Ohne Passwort", rollen.WERKSTATT, True, None)):
    rollen.benutzer_setzen(db, k, n, [rl], akt)
    if pw_:
        rollen.zugang_setzen(db, k, passwort=pw_)

d = AnmeldenDialog(None, db)
assert d.auswahl is not None, "mit Benutzern: Auswahlliste"
eintraege = [(d.auswahl.itemText(i), d.auswahl.itemData(i)) for i in range(d.auswahl.count())]
assert [k for _t, k in eintraege] == ["AB", "ZM"], f"nur aktive mit Passwort, nach Name sortiert: {eintraege}"
assert eintraege[0][0] == "Anna Becker (AB)", eintraege
assert "XX" not in dict((v, k) for k, v in eintraege) and "OP" not in [k for _t, k in eintraege]
ok("Auswahl zeigt nur aktive Benutzer mit Passwort/PIN, „Name (Kürzel)“, nach Name sortiert")

db.einstellung_setzen("benutzer_kuerzel", "ZM")        # Kürzel dieses Arbeitsplatzes
d = AnmeldenDialog(None, db)
assert d.auswahl.currentData() == "ZM" and d._kuerzel() == "ZM", "Mitarbeiter dieses Platzes vorbelegt"
d.auswahl.setCurrentIndex(d.auswahl.findData("AB"))
assert d._kuerzel() == "AB", "_kuerzel folgt der Auswahl"
ok("Mitarbeiter dieses Arbeitsplatzes vorbelegt; _kuerzel() folgt der Auswahl")

print("alle Prüfungen bestanden")
