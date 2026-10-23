"""Cockpit der Startseite (Layout-Plan L21): Pipeline, Wiedervorlagen, Kennzahlen nur für Admin."""
import datetime
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import cockpit  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


heute = datetime.date(2026, 10, 23)
zeilen = [dict(id=1, vorgang="Entwurf", vk_netto=100.0, datum="2026-10-20"),
          dict(id=2, vorgang=None, vk_netto=50.5, datum="2026-10-01"),
          dict(id=3, vorgang="Verschickt", vk_netto=200.0, datum="2026-09-20"),
          dict(id=4, vorgang="Verschickt", vk_netto=300.0, datum="2026-10-15"),
          dict(id=5, vorgang="Verschickt", vk_netto=400.0, datum="2026-10-22"),
          dict(id=6, vorgang="Beauftragt", vk_netto=1000.0, datum="2026-10-10"),
          dict(id=7, vorgang="Abgelehnt", vk_netto=None, datum="2026-10-11"),
          dict(id=8, vorgang="Verschickt", vk_netto=999.0, datum="2026-09-01", fremd=True),
          dict(id=9, vorgang="Beauftragt", vk_netto=5000.0, datum="2025-01-01")]
p = cockpit.pipeline(zeilen)
assert p == [("Entwurf", 2, 150.5), ("Verschickt", 3, 900.0), ("Beauftragt", 2, 6000.0), ("Abgelehnt", 1, 0.0)], p
ok("Pipeline: Anzahl und Summe je Vorgang, ohne Vorgang = Entwurf, fremde Angebote nicht")

w = cockpit.wiedervorlagen(zeilen, 30, heute)
assert [z["id"] for z, _, _ in w] == [3], w      # 20.09.+30 = 20.10. abgelaufen; 15.10.+30 = 14.11. noch zu weit
w = cockpit.wiedervorlagen(zeilen, 15, heute)
assert [(z["id"], r) for z, _, r in w] == [(3, -18), (4, 7)], w
ok("Wiedervorlage: verschickte, abgelaufene oder in 7 Tagen ablaufende Angebote nach Datum")

k = cockpit.kennzahlen(zeilen, heute)
assert k["angebote"] == 7 and k["beauftragt"] == 1 and k["auftragswert"] == 1000.0, k
assert k["trefferquote"] == 0.5 and k["summe"] == 2050.5 and k["durchschnitt"] == round(2050.5 / 6, 2), k
assert cockpit.kennzahlen([], heute)["trefferquote"] is None
assert cockpit.kennzahlen(zeilen + [dict(id=10, vorgang="Entwurf", vk_netto=7.0, datum="2026-11-30")], heute) == k
ok("Kennzahlen: 90 Tage (ohne vordatierte), Trefferquote beauftragt / (beauftragt + abgelehnt)")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
aid = beispiel_angebot.anlegen(db)
db.vorgang_setzen(beispiel_angebot.anlegen(db), "Verschickt")
f.alles_neu_laden()
s = f.start
summe = {v: (n, b) for v, n, b in s.pipeline_werte}
for v, (n, b) in summe.items():
    s.vorgang_zeigen(v)
    liste = f.angebote.modell.zeilen
    assert f.reiter.currentWidget() is f.angebote
    assert len(liste) == n and round(sum(z.get("vk_netto") or 0 for z in liste), 2) == b, (v, n, b, len(liste))
ok("Pipeline-Klick: Angebotsliste mit Filter, Anzahl und Summe stimmen überein")

assert not s.kennzahlen.isVisibleTo(s)
f.bereich.admin = True
s.neu_laden()
assert s.kennzahlen.isVisibleTo(s) and "Trefferquote" in s.kennzahlen.text()
ok("Kennzahlen nur mit Admin-Lizenz")
print("OK: Cockpit")
