"""Vorher-Nachher-Messung „Zukaufartikelverwaltung optional“ (Patrick 23.11.2026, Master-Auftrag Punkt 7).

Legt eine Prüfdatenbank mit einem großen Artikelstamm (Vorgabe 3.000 Zukaufartikel mit je einem Lieferanten) und einem
Angebot mit 40 Positionen an (20 davon mit Zukaufteilen, halb aus dem Stamm, halb frei) und misst je Vorgang die Zeit
(Median aus mehreren Läufen) und die Datenbankabfragen auf die Zukauf-Tabellen (zukauf_*):
  Angebot öffnen, Angebot neu rechnen, Angebots-Check, Dialog „Zukaufteile …“ öffnen, Rechen-Tabellen neu bauen.
Gemessen wird mit zentraler Verwaltung aus und ein (vor der Änderung gab es den Schalter nicht: beide Läufe gleich).

Aufruf (nicht als root, PostgreSQL-Prüfserver):
  python werkzeuge/mit_pg.py -- python werkzeuge/zukauf_messung.py [--artikel 3000] [--laeufe 5] [--json datei]
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.zukauf_dialog import ZukaufDialog  # noqa: E402

SCHALTER = "funktion_zukauf_stamm"


class Zaehler:
    """Zählt Abfragen, deren SQL eine Zukauf-Tabelle nennt (execute der Verbindungsklasse umgeleitet)."""

    def __init__(self, con):
        self.n, self.klasse = 0, type(con)
        self.alt = self.klasse.execute, self.klasse.executemany
        z = self

        def execute(selbst, sql, *a, **k):
            if "zukauf_" in str(sql):
                z.n += 1
            return z.alt[0](selbst, sql, *a, **k)

        def executemany(selbst, sql, *a, **k):
            if "zukauf_" in str(sql):
                z.n += 1
            return z.alt[1](selbst, sql, *a, **k)
        self.klasse.execute, self.klasse.executemany = execute, executemany

    def ende(self):
        self.klasse.execute, self.klasse.executemany = self.alt


def anlegen(db, n_artikel):
    """Großer Stamm + Angebot mit 40 Positionen (20 mit Zukaufteilen). Ergebnis: Angebots-ID."""
    ids = []
    for i in range(n_artikel):
        ids.append(db.zukauf_speichern(None, dict(artikelnr=f"ZK-{i:05d}", bezeichnung=f"Testartikel {i}",
                                                  kategorie="Kaufteile", einheit="Stück", status="aktiv"),
                                       [dict(lieferant="Lieferant A", bevorzugt="ja", preiseinheit=1,
                                             preise=[dict(ab=1, preis=1 + i % 50 / 10)], lieferzeit=5)]))
    a = db.angebot_neu(dict(kunde="Messung", skonto=0))
    for n in range(40):
        p = dict(pos=10 * (n + 1), artikel=f"Rohr {n}", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                 laenge=400 + 20 * n, stueck=10 + n, schneidweg=300, einstiche=2)
        if n % 2 == 0:
            aid = ids[n * 7 % len(ids)] if ids else None
            liste = [dict(artikel_id=aid, menge=2, stand=db.zukauf_stand(aid))] if aid is not None and n % 4 == 0 \
                else [zukauf.frei_eintrag(f"Freier Artikel {n}", 3, ek=2.5)]
            p["zukauf"] = json.dumps(liste, ensure_ascii=False)
        db.position_neu(a, p)
    return a


def messen(fn, laeufe):
    zeiten = []
    for _ in range(laeufe):
        t = time.perf_counter()
        fn()
        zeiten.append(time.perf_counter() - t)
    return statistics.median(zeiten) * 1000


def lauf(db, a, f, laeufe):
    zaehler = Zaehler(db.con)
    out = {}

    def vorgang(name, fn):
        zaehler.n = 0
        fn()                                    # Abfragen eines Durchlaufs zählen (ohne Wiederholung)
        n = zaehler.n
        out[name] = dict(ms=round(messen(fn, laeufe), 1), abfragen=n)

    def oeffnen():
        if a in f.offen:
            f.angebot_schliessen(a)
        return f.angebot_oeffnen(a)
    try:
        vorgang("Angebot öffnen", oeffnen)
        seite = f.angebot_oeffnen(a)
        vorgang("Angebot neu rechnen", seite.neu_laden)
        vorgang("Angebots-Check", seite.freigabe_punkte)
        p = next(x for x in seite.positionen if x.get("zukauf"))
        vorgang("Dialog Zukaufteile öffnen", lambda: ZukaufDialog(seite, db, p).deleteLater())
        vorgang("Rechen-Tabellen neu bauen", db._tabellen_bauen)
    finally:
        zaehler.ende()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--artikel", type=int, default=3000)
    ap.add_argument("--laeufe", type=int, default=5)
    ap.add_argument("--json")
    arg = ap.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STIL)
    db = Datenbank(Path(tempfile.mkdtemp()) / "messung.db")
    t = time.perf_counter()
    a = anlegen(db, arg.artikel)
    print(f"Prüfdaten: {arg.artikel} Stammartikel, 40 Positionen ({time.perf_counter() - t:.1f} s)")
    f = Hauptfenster(db, stumm=True)
    ergebnis = {}
    for wert in ("nein", "ja"):
        db.einstellung_setzen(SCHALTER, wert)
        ergebnis["aus" if wert == "nein" else "ein"] = lauf(db, a, f, arg.laeufe)
    print(f"{'Vorgang':32} {'aus ms':>9} {'Abfr.':>6} {'ein ms':>9} {'Abfr.':>6}")
    for name in ergebnis["aus"]:
        x, y = ergebnis["aus"][name], ergebnis["ein"][name]
        print(f"{name:32} {x['ms']:9.1f} {x['abfragen']:6d} {y['ms']:9.1f} {y['abfragen']:6d}")
    if arg.json:
        Path(arg.json).write_text(json.dumps(dict(artikel=arg.artikel, laeufe=arg.laeufe, **ergebnis), indent=1,
                                             ensure_ascii=False), encoding="utf-8")
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
