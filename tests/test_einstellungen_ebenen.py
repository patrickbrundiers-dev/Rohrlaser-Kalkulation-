"""Einstellungen in drei Ebenen (Patrick 26.11.2026 „Einstellungsbereiche radikal vereinfachen“):
Grundeinstellungen, Erweiterte Einstellungen, Expertenbereich (einstellungen_ordnung.EBENEN).

- E1 Ordnung: jede Seite der Navigation hat eine Ebene, jeder Ausnahme-Abschnitt existiert, Expertenabschnitte sind
     Experte; Grundeinstellungen zeigen nur einen kleinen Teil
- E2 Anzeige: Vorgabe Grundeinstellungen, höhere Seiten und Abschnitte unsichtbar, Hinweis auf weitere Seiten; die
     Suche findet trotzdem alles; Einstellung zeigen stellt die Ebene um; Wahl je Benutzer gemerkt
- E3 Nichts verloren: Werte aller Einstellungen sind nach dem Umschalten gleich, verborgene Werte gelten weiter

Aufruf: python tests/test_einstellungen_ebenen.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import bedienmodus, einstellungen_nav  # noqa: E402
from rohrlaser import einstellungen_ordnung as o  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ E1 Ordnung
alle = {k for _, ks in einstellungen_nav.GRUPPEN for k in ks}
assert alle == set(o.SEITEN_EBENE), alle ^ set(o.SEITEN_EBENE)
for (s, t), e in o.ABSCHNITT_EBENE.items():
    assert any(a.titel == t for a in o.SEITE[s].abschnitte), (s, t)
    assert e in o.EBENEN
for s in o.SEITEN:
    for a in s.abschnitte:
        if a.experte:
            assert o.abschnitt_ebene(s.schluessel, a.titel, True) == o.EXPERTE
n = {e: o.zaehlen(e) for e in o.EBENEN}
assert n[o.GRUND] < n[o.ERWEITERT] < n[o.EXPERTE] and n[o.GRUND] <= n[o.EXPERTE] // 4, n
assert o.ebene_von("gewinn") == o.GRUND and o.ebene_von("step_tol_profil") == o.EXPERTE
assert o.zeigen(o.GRUND, o.ERWEITERT) and not o.zeigen(o.EXPERTE, o.ERWEITERT)
ok(f"E1 jede Seite mit Ebene; sichtbare Einstellungen: Grund {n[o.GRUND]}, Erweitert {n[o.ERWEITERT]}, "
   f"Experte {n[o.EXPERTE]}")

# ------------------------------------------------------------------ E2 Anzeige
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
vorher = db.einstellungen()
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
nav = f.bereich.unter
assert nav.ebene == o.GRUND and nav.ebene_wahl.currentData() == o.GRUND        # Vorgabe
sichtbar = [nav.tabText(i) for i in range(nav.count()) if not nav.items[i].isHidden()]
alle_seiten = [i for i in range(nav.count()) if i not in nav.verborgen]
assert len(sichtbar) < len(alle_seiten) / 2, (len(sichtbar), len(alle_seiten))
for i in range(nav.count()):
    if not nav.items[i].isHidden():
        assert o.seite_ebene(einstellungen_nav.schluessel(nav.widget(i))) == o.GRUND, nav.tabText(i)
assert "weitere Seite" in nav.ebene_info.text()
schneid = next(i for i in range(nav.count()) if einstellungen_nav.schluessel(nav.widget(i)) == "schneiddaten")
assert nav.items[schneid].isHidden()
# Abschnitte über der Ebene auf einer Grund-Seite
arbeitsplatz = f.einstellungen.seiten[[s.schluessel for s in f.einstellungen.seiten].index("e_arbeitsplatz")]
arbeitsplatz._bauen() if not arbeitsplatz.gebaut else None
titel = {b.title(): b for b in arbeitsplatz.boxen}
assert not titel["Leistung STEP-Messung"].isVisibleTo(arbeitsplatz) and titel["Benutzer"].isVisibleTo(arbeitsplatz)
# Suche findet alles
nav.suche.setText("Schneiddaten")
assert not nav.items[schneid].isHidden() and nav.ebene == o.GRUND
nav.suche.setText("STEP-Messung")
assert titel["Leistung STEP-Messung"].isVisibleTo(arbeitsplatz)
nav.suche.setText("")
assert nav.items[schneid].isHidden() and not titel["Leistung STEP-Messung"].isVisibleTo(arbeitsplatz)
# Seite bzw. Einstellung zeigen: Ebene wird passend umgestellt
assert f.einstellung_zeigen("step_tol_profil") is not None and nav.ebene == o.EXPERTE
assert bedienmodus.einstellungen_ebene(db) == o.EXPERTE                         # gemerkt
nav.ebene_wahl.setCurrentIndex(nav.ebene_wahl.findData(o.ERWEITERT))
assert nav.ebene == o.ERWEITERT and bedienmodus.einstellungen_ebene(db) == o.ERWEITERT
assert nav.items[schneid].isHidden()                                             # Experte bleibt aus
assert titel["Gemeinsamer Ordner"].isVisibleTo(arbeitsplatz) and not titel["Leistung STEP-Messung"].isVisibleTo(arbeitsplatz)
nav.setCurrentIndex(schneid)                                                     # z. B. Knopf „Schneiddaten …“
assert nav.ebene == o.EXPERTE and nav.currentIndex() == schneid
f2 = Hauptfenster(db, HIER.parent / "programm", stumm=True)
assert f2.bereich.unter.ebene == o.EXPERTE                                       # je Benutzer gemerkt
ok("E2 Vorgabe Grundeinstellungen, höhere Seiten/Abschnitte aus, Suche findet alles, Aufruf stellt Ebene um, gemerkt")

# ------------------------------------------------------------------ E3 Nichts verloren
nachher = {k: v for k, v in db.einstellungen().items() if not k.startswith("leiste_")}
assert nachher == {k: v for k, v in vorher.items() if not k.startswith("leiste_")}
assert "leiste_einstellungen_ebene" not in {e.name for e in __import__("rohrlaser.stammdaten").stammdaten.EINSTELLUNGEN}
ok("E3 Umschalten ändert keinen Wert, die Wahl bleibt am Arbeitsplatz (leiste_*, kein Abgleich)")
print("Alle Prüfungen bestanden.")
