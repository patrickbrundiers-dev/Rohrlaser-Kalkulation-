"""Angebotsfenster „Klar“ (UI/UX Next Level Phase 3, Freigabe Patrick 26.11.2026, Variante A mit F4).

A1 Kopfband: Nummer, Kunde, Stand und Verkaufspreis; der Preis ist derselbe Text wie in der Übersicht (nichts neu
   gerechnet); Marge als Chip mit Ampel der Preisleiter;
A2 rechte Übersicht ist ab Werk aus (F4), der Knopf „Übersicht“ im Kopfband blendet sie ein und merkt es;
A3 Kalkulation: Kennzahl „Verkaufspreis netto“ = Verkaufspreis des Preisaufbaus, Balken nur aus Gruppen mit Betrag;
A4 Hilfen stand_chip, marge_chip, gruppen ohne Qt-Fenster.
Aufruf: python tests/test_angebot_kopf.py (mit PostgreSQL wie die übrigen Fenster-Tests)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
from rohrlaser import angebot_fenster, angebot_kopfband, kalk_kopf, preisleiter, rechnen, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


# ---------------------------------------------------------------- A4 Hilfen
pruefe(angebot_kopfband.stand_chip("aktuell") == ("Optimiert", "ok")
       and angebot_kopfband.stand_chip("noch nicht optimiert")[1] == "warnung"
       and angebot_kopfband.stand_chip("veraltet") == ("Veraltet", "fehler"), "A4 Stand als Chip")
pruefe(angebot_kopfband.marge_chip(None) == ("Marge –", "neutral")
       and angebot_kopfband.marge_chip(dict(marge=0.182, stufe=preisleiter.GUT)) == ("Marge 18,2 %", "ok")
       and angebot_kopfband.marge_chip(dict(marge=0.05, stufe=preisleiter.KRITISCH))[1] == "fehler",
       "A4 Marge als Chip mit Ampel")
leer = [(n, 0.0, "") for _, n, _ in rechnen.KOSTENARTEN]
pruefe(kalk_kopf.balken_teile(leer) == [] and len(kalk_kopf.gruppen(leer)) == len(rechnen.KOSTEN_GRUPPEN),
       "A4 ohne Kosten kein Balkenteil")

# ---------------------------------------------------------------- Angebot öffnen
angebot_fenster.AngebotSeite.CHECK_SOFORT = False
stil.anwenden(app, "hell")
db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
a = db.angebot_neu(dict(kunde="Kopfband GmbH", kundennr="K-4711", maschine="T11", stange=6000))
for i, profil in enumerate(("RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3")):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"K-{i}", bezeichnung=f"Teil {i}", profil_id=profil,
                            werkstoff_id="S235-10219", laenge=400.0 + 100 * i, stueck=10, schneidweg=500.0,
                            einstiche=4))
f = Hauptfenster(db, stumm=True)
f.resize(1366, 728)
f.show()
s = f.angebot_oeffnen(a)
QTest.qWait(300)
s.optimieren()
QTest.qWait(500)
band = s.kopfband

# ---------------------------------------------------------------- A1 Kopfband
vk = s.uebersicht_bereich.preis["verkauf"].text()
pruefe(band.isVisible() and band.vk.text() == vk and vk.endswith("€"), f"A1 Kopfband zeigt Verkaufspreis {vk}")
pruefe("Kopfband GmbH" in band.unter.text() and "K-4711" in band.unter.text(), "A1 Kunde und Kundennummer")
pruefe(band.stand.text().strip().endswith("Optimiert"), f"A1 Stand nach Optimierung „{band.stand.text()}“")
pruefe("Marge" in band.marge.text(), f"A1 Marge-Chip „{band.marge.text()}“")
pruefe(s.pdf_knopf.parent() is not None and band.isAncestorOf(s.pdf_knopf), "A1 Angebot (PDF) steht im Kopfband")

# ---------------------------------------------------------------- A2 Übersicht ab Werk aus
pruefe(not s.uebersicht_rahmen.isVisible() and not s.uebersicht_streifen.isVisible()
       and not band.uebersicht.isChecked(), "A2 Übersicht rechts ab Werk aus, kein Streifen")
band.uebersicht.click()
QTest.qWait(50)
pruefe(s.uebersicht_rahmen.isVisible() and s.uebersicht_knopf.isChecked()
       and db.einstellung(angebot_fenster.UEBERSICHT_EINSTELLUNG) is True, "A2 Knopf Übersicht blendet ein, gemerkt")
band.uebersicht.click()
QTest.qWait(50)
pruefe(not s.uebersicht_rahmen.isVisible()
       and db.einstellung(angebot_fenster.UEBERSICHT_EINSTELLUNG) is False, "A2 und wieder aus")

# ---------------------------------------------------------------- A3 Kalkulation
kk = s.kalk_kopf
verkauf = kk.kacheln["verkauf"]
werte = [w.text() for w in verkauf.findChildren(type(band.vk))]
pruefe(any(w == vk for w in werte), f"A3 Kachel Verkaufspreis netto = {vk} ({werte})")
pruefe(len(kk.balken.teile) >= 2 and all(b > 0 for _, b in kk.balken.teile),
       f"A3 Preisbalken mit {len(kk.balken.teile)} Teilen")
kk.balken.grab()             # Zeichnen ohne Fehler

f.close()
print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles in Ordnung.")
sys.exit(1 if fehler else 0)
