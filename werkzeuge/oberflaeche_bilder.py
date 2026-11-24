"""Bilder aller Hauptbereiche der Oberfläche (Generalüberholung 24.11.2026, Phase 1 und Vorher-Nachher-Regel).

Startet das echte Hauptfenster ohne Bildschirm mit einem Testangebot (erfundene Daten), besucht alle Hauptreiter,
die Reiter des Angebots und alle Einstellungsseiten und speichert je Ansicht ein PNG. Dazu je Ansicht die Zeit bis
zum fertigen Bild (Reiterwechsel + Aufbau). Nur Entwicklung, nicht im Programm.

Aufruf (nicht als root, braucht PostgreSQL):
  python werkzeuge/mit_pg.py -- python werkzeuge/oberflaeche_bilder.py AUSGABE [--thema Hell,Dunkel] [--groesse 1600x900]
Ergebnis: AUSGABE/<thema>/<nr>_<name>.png und AUSGABE/zeiten.json
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import angebot_fenster, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def _name(text):
    return re.sub(r"[^0-9A-Za-zÄÖÜäöüß]+", "_", text).strip("_")[:40] or "ohne"


def _bild(f, ordner, nr, name, zeiten, t0):
    QApplication.processEvents()
    zeiten[name] = round((time.perf_counter() - t0) * 1000, 1)
    f.grab().save(str(ordner / f"{nr:02d}_{_name(name)}.png"))


def lauf(ausgabe, thema, breite, hoehe):
    stil.anwenden(app, thema)
    po = Path(tempfile.mkdtemp(prefix="bilder_")) / "Rohrlaser-Angebotskalkulation"
    (po / "Daten").mkdir(parents=True)
    db = Datenbank(po / "Daten" / "rohrlaser.db")
    f = Hauptfenster(db, po, stumm=True)
    f.resize(breite, hoehe)
    f.show()
    v = ANGEBOTE[0]
    a = db.angebot_neu(dict(nummer="A-2026-0100", kunde="Metallbau Beispiel (erfunden)", kundennr="10417",
                            maschine=v["maschine"], stange=v["stange"]))
    for p in v["positionen"]:
        db.position_neu(a, dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"],
                                profil_id=p["profil"], werkstoff_id=p["werkstoff"], laenge=p["laenge"],
                                stueck=p["stueck"]))
    f.alles_neu_laden()
    f.angebot_oeffnen(a)
    QTest.qWait(1500)
    ordner = Path(ausgabe) / thema
    ordner.mkdir(parents=True, exist_ok=True)
    zeiten, nr = {}, 0
    for i in range(f.reiter.count()):
        t0 = time.perf_counter()
        f.reiter.setCurrentIndex(i)
        nr += 1
        titel = f.reiter.tabText(i)
        _bild(f, ordner, nr, titel, zeiten, t0)
        w = f.reiter.widget(i)
        inner = getattr(w, "reiter", None)
        if isinstance(inner, QTabWidget) and w is not f.bereich:
            for k in range(inner.count()):
                t0 = time.perf_counter()
                inner.setCurrentIndex(k)
                nr += 1
                _bild(f, ordner, nr, f"{titel} - {inner.tabText(k)}", zeiten, t0)
    f.reiter.setCurrentWidget(f.bereich)
    for s in f.einstellungen.seiten:
        t0 = time.perf_counter()
        f.bereich.zeigen(s)
        nr += 1
        _bild(f, ordner, nr, f"Einstellungen - {s.schluessel}", zeiten, t0)
    f.close()
    return zeiten


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("aus")
    ap.add_argument("--thema", default="Hell,Dunkel")
    ap.add_argument("--groesse", default="1600x900")
    a = ap.parse_args()
    b, h = (int(x) for x in a.groesse.split("x"))
    angebot_fenster.AngebotSeite.CHECK_SOFORT = False
    alle = {t: lauf(a.aus, t, b, h) for t in a.thema.split(",")}
    Path(a.aus, "zeiten.json").write_text(json.dumps(alle, indent=1, ensure_ascii=False), encoding="utf-8")
    for t, z in alle.items():
        print(t, len(z), "Ansichten, langsamste:", sorted(z.items(), key=lambda x: -x[1])[:5])


if __name__ == "__main__":
    main()
