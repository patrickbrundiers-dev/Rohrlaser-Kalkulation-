"""Mehr Platz für die Positionsliste (Optimierungsplan 04.11.2026, Layout B1 + B2).

Geprüft ohne Bildschirm bei 1366 × 728 px (Laptop) mit dem Testangebot M (50 Positionen):
- B1: Angebotskopf, Kalkulation und Fracht zugeklappt in EINER Zeile, Knopfleiste in einer Zeile, die Liste beginnt
  weit oben und zeigt mindestens 12 Zeilen (vorher 9),
- B4: Stand-Kasten nur, wenn nicht optimiert/veraltet; Angebots-Check im Menü nur bei eingeklappter Übersicht,
- B2: » im Titel der Übersicht blendet sie aus, rechts bleibt ein schmaler Streifen mit Verkaufspreis und Stand;
  « bzw. Klick auf den Streifen blendet wieder ein; die Wahl wird gemerkt.
Aufruf: python tests/test_layout_platz.py
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from rohrlaser import angebot_fenster, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


PROFILE = ["RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"]
WERKSTOFFE = ["S235-10219", "S355-10219", "1.4301"]


def anlegen(db, n):
    """Testangebot wie im Leistungstest: gemischte Positionen mit Gehrungen, Zusatzarbeiten und Sätzen."""
    rnd = random.Random(1)
    a = db.angebot_neu(dict(kunde=f"Layout {n}", kundennr="K-10045", maschine="T11", stange=6000))
    for i in range(n):
        p = dict(pos=10 * (i + 1), artikel=f"ART-{i:04d}", bezeichnung=f"Teil {i}",
                 profil_id=PROFILE[i % len(PROFILE)], werkstoff_id=WERKSTOFFE[(i // 5) % len(WERKSTOFFE)],
                 laenge=float(rnd.randint(80, 5800)), stueck=rnd.choice([1, 2, 4, 8, 20]),
                 schneidweg=round(rnd.uniform(250, 1200), 1), einstiche=rnd.randint(2, 10))
        if i % 10 == 3:
            p["zusatz"] = json.dumps([dict(name="Feuerverzinken")])
        if i % 15 == 7:
            p["satz"], p["je_satz"] = f"Satz {i // 15}", 2
        db.position_neu(a, p)
    return a


angebot_fenster.AngebotSeite.CHECK_SOFORT = False
stil.anwenden(app, "hell")
db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
a = anlegen(db, 50)
f = Hauptfenster(db, stumm=True)
f.resize(1366, 728)
f.show()
s = f.angebot_oeffnen(a)
QTest.qWait(300)
s.optimieren()
QTest.qWait(500)


def y(w):
    return w.mapTo(f, QPoint(0, 0)).y()


kb = s.kopf_bereich
assert kb.kompakt and kb.einzeilig, (kb.kompakt, kb.einzeilig)
assert kb.kopf_karte.height() <= 40 and kb.height() <= 45, (kb.kopf_karte.height(), kb.height())
assert not kb.vorgaben_knopf.isVisible() and not kb.fracht_knopf.isVisible()
ok(f"B1 Kopf, Kalkulation und Fracht in einer Zeile ({kb.height()} px hoch)")
assert not s.leiste.zweizeilig and s.leiste.height() <= 34, (s.leiste.zweizeilig, s.leiste.height(), s.leiste._bedarf())
assert "\n" not in s.ablage_klein.text()
assert s.uebersicht_knopf.parent() is s.uebersicht_streifen
ok(f"B1 Knopfleiste in einer Zeile (Bedarf {s.leiste._bedarf()} von {s.leiste.width()} px)")
v = s.pos_ansicht
zeilen = sum(1 for r in range(len(s.positionen)) if 0 <= v.rowViewportPosition(r) < v.viewport().height() - 10)
assert y(v) <= 260 and zeilen >= 12, (y(v), zeilen)
ok(f"B1 Positionsliste ab y={y(v)} mit {zeilen} sichtbaren Zeilen (vorher y=314, 9 Zeilen)")

# ------------------------------------------------------------------ B4 nichts doppelt
assert s.stand.isHidden() and s.stand.text() == "Optimierung abgeschlossen"
ok("B4 Kasten „Optimierung abgeschlossen“ ausgeblendet (zeigt die Schrittanzeige)")
assert all(b.text() in ("▸ Alle zuklappen", "▾ Alle aufklappen") for b in s.gruppen_knoepfe)
ok("B4 Knopf Gruppen kurz")
s.weitere.menu().aboutToShow.emit()
assert not s.check_aktion.isVisible()
ok("B4 Angebots-Check nicht doppelt im Menü Ausgaben, solange die Übersicht offen ist")
assert "Arbeitsgänge vorschlagen …" not in s.pos_aktionen
assert any(a.text() == "Arbeitsgänge vorschlagen …" for a in s.weitere.menu().actions())
ok("B4 Arbeitsgänge vorschlagen nur noch im Menü Ausgaben, nicht im Rechtsklick")

# ------------------------------------------------------------------ B2 Übersicht ausblenden
breit = v.width()
assert s.uebersicht_rahmen.isVisible() and not s.uebersicht_streifen.isVisible()
s.uebersicht_bereich.ausblenden_knopf.click()
QTest.qWait(100)
assert not s.uebersicht_rahmen.isVisible() and s.uebersicht_streifen.isVisible()
assert s.uebersicht_streifen.width() <= 40 and v.width() > breit + 250, (s.uebersicht_streifen.width(), breit, v.width())
vk = s.uebersicht_bereich.preis["verkauf"].text()
assert vk.endswith("€") and vk in s.uebersicht_streifen.text(), (vk, s.uebersicht_streifen.text())
assert s.uebersicht_streifen.farbe() == "#2E8B4A", s.uebersicht_streifen.farbe()       # optimiert: grün
assert db.einstellung(angebot_fenster.UEBERSICHT_EINSTELLUNG) is False
s.uebersicht_streifen.grab()            # Zeichnen (senkrechter Text) ohne Fehler
ok(f"B2 Übersicht aus: Streifen {s.uebersicht_streifen.width()} px mit „{s.uebersicht_streifen.text()}“, "
   f"Liste {breit} → {v.width()} px, gemerkt")
s.uebersicht_bereich.stand_setzen("veraltet")
assert s.uebersicht_streifen.farbe() == "#C0392B"
assert not s.stand.isHidden()
s.weitere.menu().aboutToShow.emit()
assert s.check_aktion.isVisible()
ok("B2 Streifen zeigt veralteten Stand rot; Stand-Kasten wieder da; Angebots-Check im Menü Ausgaben")
QTest.mouseClick(s.uebersicht_streifen, Qt.LeftButton, pos=QPoint(15, 200))
QTest.qWait(50)
assert s.uebersicht_rahmen.isVisible() and not s.uebersicht_streifen.isVisible() and s.uebersicht_knopf.isChecked()
assert db.einstellung(angebot_fenster.UEBERSICHT_EINSTELLUNG) is True
ok("B2 Klick auf den Streifen blendet die Übersicht wieder ein")
s.uebersicht_bereich.ausblenden_knopf.click()
s2 = f.angebot_oeffnen(anlegen(db, 5))
QTest.qWait(100)
assert not s2.uebersicht_rahmen.isVisible() and s2.uebersicht_streifen.isVisible()
ok("B2 nächstes Angebot öffnet mit ausgeblendeter Übersicht (gemerkt)")

# ------------------------------------------------------------------ B3 Spalten-Ansichten
from rohrlaser.angebot_fenster import SPALTEN_ANSICHT_EINSTELLUNG  # noqa: E402

s = s2


def sichtbar():
    m = s.pos_modell
    return {m.name(i) for i in range(m.columnCount()) if not s.pos_ansicht.isColumnHidden(i)}


assert s.spalten_ansicht == "Alle" and s.ansicht_knoepfe["Alle"].isChecked()
assert not s.zeige_step.isVisible() and not s.zeige_berechnet.isVisible()
alle = sichtbar()
s.ansicht_knoepfe["Erfassen"].click()
erfassen = sichtbar()
assert {"artikel", "profil_id", "werkstoff_id", "laenge", "stueck"} <= erfassen, erfassen
assert not erfassen & {"schneidweg", "einstiche", "zeit_manuell", "preis_m"}, erfassen
assert s.ansicht_knoepfe["Erfassen"].isChecked() and not s.ansicht_knoepfe["Alle"].isChecked()
assert db.einstellung(SPALTEN_ANSICHT_EINSTELLUNG) == "Erfassen"
ok(f"B3 Erfassen: {len(erfassen)} statt {len(alle)} Spalten, gemerkt")
s.ansicht_waehlen("Prüfen")
pruefen = sichtbar()
assert {"schneidweg", "einstiche", "zusatz"} <= pruefen and "preis_m" not in pruefen, pruefen
assert "a_schnitt" not in pruefen            # leere STEP-Spalte bleibt weg
ok("B3 Prüfen: Schneidweg, Einstiche, Zusatzarbeiten; leere STEP-Spalten bleiben weg")
s.ansicht_waehlen("Preis")
preis = sichtbar()
assert {"zeit_manuell", "prog_zeit", "preis_m"} <= preis and "profil_id" not in preis, preis
s.spalte_waehlen("oberflaeche", True)
assert "oberflaeche" in sichtbar()
ok("B3 Preis: Zeiten und Materialpreis; eigene Wahl aus „Weitere Spalten“ gilt zusätzlich")
s.spalten_menue.aboutToShow.emit()
step = next(a for a in s.spalten_menue.actions() if a.text() == "STEP-Werte (aus CAD)")
step.setChecked(True)
assert s.zeige_step.isChecked() and "a_schnitt" in sichtbar()
ok("B3 STEP-Werte und Berechnete Werte im Menü „Weitere Spalten“")
s.ansicht_waehlen("Alle")
s.spalte_waehlen(None, None)
step.setChecked(False)
assert sichtbar() == alle
ok("B3 Alle: wieder wie vorher")
s3 = f.angebot_oeffnen(anlegen(db, 3))
QTest.qWait(50)
assert s3.spalten_ansicht == "Alle"
print("Alle Prüfungen Layout-Platz bestanden.")
