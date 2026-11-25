"""Bilder aller Hauptbereiche der Oberfläche (Generalüberholung 24.11.2026, Phase 1 und Vorher-Nachher-Regel).

Startet das echte Hauptfenster ohne Bildschirm mit einem Testangebot (erfundene Daten), besucht alle Hauptreiter,
die Reiter des Angebots und alle Einstellungsseiten und speichert je Ansicht ein PNG. Dazu je Ansicht die Zeit bis
zum fertigen Bild (Reiterwechsel + Aufbau). Nur Entwicklung, nicht im Programm.

Aufruf (nicht als root, braucht PostgreSQL):
  python werkzeuge/mit_pg.py -- python werkzeuge/oberflaeche_bilder.py AUSGABE [--thema Hell,Dunkel] [--groesse 1600x900]
Ergebnis: AUSGABE/<thema>/<nr>_<name>.png und AUSGABE/zeiten.json

--kontrast: zusätzlich je Ansicht jede sichtbare Beschriftung (Labels, Knöpfe, Haken) im fertigen Bild messen:
Hintergrund = häufigste Farbe im Feld, Schrift = die Farbe mit dem größten Abstand dazu (98-%-Wert, ohne
Kantenglättung); Kontrast nach WCAG. AUSGABE/kontrast.json listet alles unter 3:1 (Phase 4, Kontrastprüfung).
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
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QTabWidget  # noqa: E402

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import angebot_fenster, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def _name(text):
    return re.sub(r"[^0-9A-Za-zÄÖÜäöüß]+", "_", text).strip("_")[:40] or "ohne"


KONTRAST = None     # Liste der Funde (nur mit --kontrast)


def _lum(rgb):
    def k(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * k(r) + 0.7152 * k(g) + 0.0722 * k(b)


def kontrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _feld_kontrast(bild, x, y, b, h):
    """(Kontrast, Hintergrund, Schrift) eines Bildausschnitts oder None (zu klein/leer)."""
    from collections import Counter
    if b < 6 or h < 6:
        return None
    farben = Counter()
    schritt = 1 if b * h <= 80000 else 2        # jeder Punkt: dünne Schrift hat nur wenige Kernpunkte
    for yy in range(y, y + h, schritt):
        for xx in range(x, x + b, schritt):
            c = bild.pixel(xx, yy)
            farben[((c >> 16) & 255, (c >> 8) & 255, c & 255)] += 1
    if len(farben) < 2:
        return None
    grund = farben.most_common(1)[0][0]
    lg = _lum(grund)
    gesamt = sum(farben.values())
    # Schrift = die Farbe mit dem größten Abstand zum Grund, die oft genug vorkommt (Kernpunkte der Buchstaben, nicht
    # einzelne Ausreißer); Kantenglättung liegt dazwischen und zählt nicht
    mindest = max(4, 0.003 * gesamt)
    kandidaten = [(abs(_lum(c) - lg), c) for c, n in farben.items() if c != grund and n >= mindest]
    if not kandidaten:
        return None
    schrift = max(kandidaten)[1]
    return kontrast(grund, schrift), grund, schrift


def _kontrast_pruefen(f, name):
    bild = f.grab().toImage()
    for w in f.findChildren(QLabel) + f.findChildren(QAbstractButton):
        text = w.text() if hasattr(w, "text") else ""
        if not text or not w.isVisible() or not w.isEnabled() or w.width() < 6:
            continue
        if len(re.sub(r"<[^>]+>|[^0-9A-Za-zÄÖÜäöüß]", "", text)) < 3:      # Symbole, einzelne Ziffern: zu dünn
            continue
        sichtbar = w.visibleRegion().boundingRect()        # nur der wirklich sichtbare Teil (nicht weggerollt)
        if isinstance(w, QAbstractButton):
            sichtbar = sichtbar.adjusted(4, 4, -4, -4)      # ohne Rahmen und Verlauf des Knopfs
        if sichtbar.width() < 6 or sichtbar.height() < 6:
            continue
        p = w.mapTo(f, sichtbar.topLeft())
        x, y = max(0, p.x()), max(0, p.y())
        b, h = min(sichtbar.width(), bild.width() - x), min(sichtbar.height(), bild.height() - y)
        erg = _feld_kontrast(bild, x, y, b, h)
        if erg and erg[0] < 3.0:
            KONTRAST.append(dict(ansicht=name, art=type(w).__name__, text=re.sub("<[^>]+>", "", text)[:60],
                                 kontrast=round(erg[0], 2), grund="#%02X%02X%02X" % erg[1],
                                 schrift="#%02X%02X%02X" % erg[2], ort=[x, y, b, h]))


def _bild(f, ordner, nr, name, zeiten, t0):
    QApplication.processEvents()
    zeiten[name] = round((time.perf_counter() - t0) * 1000, 1)
    f.grab().save(str(ordner / f"{nr:02d}_{_name(name)}.png"))
    if KONTRAST is not None:
        _kontrast_pruefen(f, f"{ordner.name}: {name}")


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
    ap.add_argument("--kontrast", action="store_true")
    a = ap.parse_args()
    global KONTRAST
    if a.kontrast:
        KONTRAST = []
    b, h = (int(x) for x in a.groesse.split("x"))
    angebot_fenster.AngebotSeite.CHECK_SOFORT = False
    alle = {t: lauf(a.aus, t, b, h) for t in a.thema.split(",")}
    Path(a.aus, "zeiten.json").write_text(json.dumps(alle, indent=1, ensure_ascii=False), encoding="utf-8")
    for t, z in alle.items():
        print(t, len(z), "Ansichten, langsamste:", sorted(z.items(), key=lambda x: -x[1])[:5])
    if KONTRAST is not None:
        Path(a.aus, "kontrast.json").write_text(json.dumps(KONTRAST, indent=1, ensure_ascii=False), encoding="utf-8")
        print("Kontrast unter 3:1:", len(KONTRAST))


if __name__ == "__main__":
    main()
