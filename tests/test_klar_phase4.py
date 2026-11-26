"""Designsystem „Klar“ Phase 4 (UI/UX Next Level, Freigabe Patrick 26.11.2026): Materialfenster und Einstellungen.

M1 bausteine.kennzahlleiste und wertzeilen: Werte, Titel, rechte Widgets;
M2 Detailbereich Material: Meterpreis mit Herkunft, Verschnitt = Einkauf − Teile, Ausnutzung als Chip (Stufen),
   ohne Schnittplan Hinweis, ohne Markierung leer und Knöpfe aus;
E1 Einstellungen: Knopfreihe Grund · Erweitert · Experte stellt die Ebene um und folgt umgekehrt dem (verborgenen)
   Wahlfeld; Seitentitel über dem Inhalt ohne Schloss.
Aufruf: python tests/test_klar_phase4.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
from rohrlaser import bausteine, material_detail  # noqa: E402
from rohrlaser import einstellungen_ordnung as o  # noqa: E402
from rohrlaser.einstellungen_nav import NavigationsReiter  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


# ---------------------------------------------------------------- M1
chip = bausteine.chip("Alle mit Preis", "ok")
leiste = bausteine.kennzahlleiste((("a", "Abmessungen", "2"), ("m", "Material", "456,10 €")), rechts=(chip,))
pruefe(leiste.werte["a"].text() == "2" and leiste.titel["m"].text() == "Material" and leiste.isAncestorOf(chip),
       "M1 Kennzahlleiste mit Werten, Titeln und Chip rechts")
z = bausteine.wertzeilen([("Gewicht", "3,49 kg/m"), ("Knopf", QLabel("x"))])
pruefe(z.werte["Gewicht"].text() == "3,49 kg/m" and isinstance(z.werte["Knopf"], QWidget), "M1 Wertzeilen")

# ---------------------------------------------------------------- M2
g = dict(profil="QR 40x40x3", werkstoff="S235", oberflaeche="roh", stange=6000, kunde=False, manuell=None,
         berechnet=5.23, fehlt="", kg_m=3.49, teile_m=51.4, stangen=9, meter=54.0, kg=188.2, kosten=284.67,
         nutz_m=51.4, ausnutzung=51.4 / 54.0)
d = material_detail.AbmessungDetail({"Abmessung mit Schnittplan …": lambda r: None})
d.setzen(g, 0, "9 × 6.000 mm")
w = d.werte.werte
pruefe(w["Meterpreis"].text() == "5,23 €/m" and w["Preis"].text() == "berechnet", "M2 Meterpreis und Herkunft")
pruefe(w["Verschnitt"].text() == "2,6 m" and w["Einkauf"].text() == "54,0 m · 188,2 kg"
       and w["Material"].text() == "284,67 €", "M2 Einkauf, Material und Verschnitt aus dem Schnittplan")
pruefe("95,2 %" in d.chip.text() and material_detail.ausnutzung_stufe(0.952) == "ok"
       and material_detail.ausnutzung_stufe(0.75) == "warnung" and material_detail.ausnutzung_stufe(0.5) == "fehler"
       and material_detail.ausnutzung_stufe(None) == "neutral", f"M2 Ausnutzung als Chip „{d.chip.text()}“")
pruefe(material_detail.meterpreis_text(dict(g, manuell=6.0)) == ("6,00 €/m", "eigener Wert")
       and material_detail.meterpreis_text(dict(g, kunde=True))[1] == "Kundenmaterial", "M2 eigener Preis, Kunde")
d.setzen(dict(g, stangen=0, ausnutzung=None), 0)
pruefe(w["Einkauf"].text() == "noch nicht optimiert" and "Optimieren" in d.hinweis.text(), "M2 ohne Schnittplan")
d.setzen(None)
pruefe(not d.knoepfe["Abmessung mit Schnittplan …"].isEnabled() and "Keine" in d.titel.text(), "M2 ohne Markierung")

# ---------------------------------------------------------------- E1
nav = NavigationsReiter()
seite = QWidget()
seite.schluessel = "e_kosten"
nav.addTab(seite, "Kosten und Stundensatz 🔒")
nav.setCurrentIndex(0)
pruefe(nav.seiten_titel.text() == "Kosten und Stundensatz", f"E1 Seitentitel ohne Schloss „{nav.seiten_titel.text()}“")
nav.ebene_segment.knoepfe[0].click()
pruefe(nav.ebene == o.GRUND and nav.ebene_wahl.currentData() == o.GRUND, "E1 Knopf Grund stellt die Ebene um")
nav.ebene_wahl.setCurrentIndex(nav.ebene_wahl.findData(o.EXPERTE))
pruefe(nav.ebene == o.EXPERTE and nav.ebene_segment.currentText() == "Experte", "E1 Knopfreihe folgt dem Wahlfeld")
pruefe(nav.ebene_wahl.isHidden(), "E1 altes Wahlfeld verborgen")

print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles in Ordnung.")
sys.exit(1 if fehler else 0)
