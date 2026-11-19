"""Großes UI- und Funktionsupdate (Patrick 19.11.2026): die Lücken, die das Update schließt.

U1 3D-Auswahl: alle Körper wählen (Strg+A), Auswahl umkehren (Strg+I), Auswahlgruppen merken/wählen/entfernen
U2 Rechtsklick ohne Ziehen in 3D-Fenstern ohne eigenes Menü: Blick, Darstellung, Auswahl, Messen
U3 Bauteilprüfung in der Fertigungsprüfung: doppelte, überlappende, außerhalb liegende Konturen, fehlende Wand,
   unplausible Abmessung; Konturen ohne Konflikt bleiben ohne Befund
U4 Einstellungen ohne Fenster: Standard, Favoriten, Verlauf, Zurücksetzen, Plausibilität, Export/Import, Profil
U5 Einstellungen im Programm: ☆/↺ je Wert, Seite auf Standard, Favoritenseite, Verlauf-Dialog, Import mit Sperre
U6 Bauteilbibliothek: Kategorie, Favorit, Suche, Kopieren, Dialog mit 3D-Vorschau, Einsetzen als Position
U7 Kalkulationsvergleich: Oberfläche, Geometrie (Konturen), Arbeitsschritte und Kalkulationswerte

Aufruf: python tests/test_ui_update_1911.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import (dfm, einstellungen_extras as X, fassung_vergleich, positionsvorlagen as PV,  # noqa: E402
                       schneidweg as sw)
from rohrlaser.ansicht3d import Ansicht3DMitKnoepfen, baugruppe  # noqa: E402
from rohrlaser.baugruppe_ansicht import teil_kennung  # noqa: E402
from rohrlaser.ansicht3d_leiste import auswahl_menue  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import EinstellungenSeite, Hauptfenster  # noqa: E402
from rohrlaser.satz3d import TEIL  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402

app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def eintraege(menue):
    out = []
    for a in menue.actions():
        if a.menu() is not None:
            out.append(a.text())
            out += [f"{a.text()}/{t}" for t in eintraege(a.menu())]
        elif not a.isSeparator():
            out.append(a.text().split("\t")[0])
    return out


# ------------------------------------------------------------------ U1 Auswahl
def quader(dx, dy, dz):
    p = [c for x in (0, dx) for y in (0, dy) for z in (0, dz) for c in (x, y, z)]
    t = [0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3]
    return dict(p=[float(c) for c in p], t={"A": t}, l={})


LAGE = [0, 0, 0, 0, 0, 1, 1, 0, 0]
bereiche = []
bg, _ = baugruppe([dict(quader(100, 60, 40), lage=[x, 0, 0] + LAGE[3:]) for x in (0, 150, 300)], bereiche=bereiche)
teil_kennung(bg, bereiche, [f"{TEIL}{i}" for i in range(3)])
bg["teile"] = True
w = Ansicht3DMitKnoepfen()
w.resize(900, 600)
w.show()
w.setzen(bg, "Baugruppe")
app.processEvents()
a = w.ansicht
a.wahl.setzen(True)
ids = a.wahl.sichtbare_koerper()
assert len(ids) == 3, ids
assert a.wahl.alle_waehlen() == 3 and a.wahl.koerper_ids() == ids
a.wahl.koerper_setzen([ids[0]])
assert a.wahl.umkehren() == 2 and a.wahl.koerper_ids() == ids[1:]
assert a.wahl.umkehren() == 1 and a.wahl.koerper_ids() == ids[:1]
QTest.keyClick(a, Qt.Key_A, Qt.ControlModifier)
assert a.wahl.koerper_ids() == ids
a.wahl.koerper_setzen([ids[2]])
QTest.keyClick(a, Qt.Key_I, Qt.ControlModifier)
assert a.wahl.koerper_ids() == ids[:2] and not a.wahl.versteckt        # Strg+I kehrt um, I allein isoliert
assert a.wahl.gruppe_merken("Rahmen") == 2 and a.wahl.gruppe_merken(" ") == 0
a.wahl.aufheben()
a.wahl.koerper_setzen([ids[0]])
a.wahl.ausblenden()
assert a.wahl.gruppe_waehlen("Rahmen") == 2 and a.wahl.koerper_ids() == ids[:2] and not a.wahl.versteckt
a.wahl.koerper_setzen([ids[2]])
assert a.wahl.gruppe_waehlen("Rahmen", dazu=True) == 2 and set(a.wahl.koerper_ids()) == set(ids)
m = auswahl_menue(QMenu(), a)
m.aboutToShow.emit()
texte = eintraege(m)
assert {"Alle Körper wählen", "Auswahl umkehren", "Als Auswahlgruppe merken …", "Auswahlgruppen",
        "Auswahlgruppen/Rahmen (2)"} <= set(texte), texte
assert a.wahl.gruppe_entfernen("Rahmen") and not a.wahl.gruppe_entfernen("Rahmen") and a.wahl.gruppen == {}
assert any(t == "Umkehren" for t, _, _ in a.wahl.aktionen_liste())
ok("U1 Auswahl: alle (Strg+A), umkehren (Strg+I), Auswahlgruppen merken/wählen (blendet ein)/entfernen, Menü")

# ------------------------------------------------------------------ U2 Rechtsklick-Menü
a.stumm = True
m = a.standard_menue(zeigen=False)
texte = eintraege(m)
assert "Einpassen" in texte and "Blick" in texte and "Blick/Isometrie" in texte, texte
assert "Darstellung/Drahtgitter" in texte and "Darstellung/Durchsichtig" in texte, texte
assert "Auswahl/Auswahl umkehren" in texte and "Messen" in texte, texte
gesehen = []
a.standard_menue = lambda pos=None, zeigen=True: gesehen.append(pos)
QTest.mouseClick(a, Qt.RightButton, Qt.NoModifier, a.rect().center())
assert len(gesehen) == 1                                                    # Rechtsklick ohne Ziehen öffnet es
w.close()
ok("U2 Rechtsklick ohne Ziehen: Menü mit Einpassen, Blick, Darstellung (Drahtgitter, Durchsichtig), Auswahl, Messen")

# ------------------------------------------------------------------ U3 Bauteilprüfung
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")


def befunde(konturen, laenge=500, profil=QR):
    p = dict(laenge=laenge, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=konturen)))
    return dfm.rohr(p, profil)


def regel(bs, name):
    return [b for b in bs if b.regel == name]


bohr = dict(art=sw.BOHRUNG, anzahl=1, d=8, x=100, seite="oben")
gut = befunde([bohr, dict(bohr, x=300)])
assert not [b for b in gut if b.regel in dfm.KONFLIKT_REGELN], gut
d = regel(befunde([bohr, dict(bohr)]), dfm.DOPPELT)
assert len(d) == 1 and d[0].zeilen == (0, 1) and d[0].stufe == dfm.WARNUNG and "doppelt" in d[0].text, d
u = regel(befunde([bohr, dict(bohr, x=104)]), dfm.UEBERLAPP)
assert len(u) == 1 and u[0].zeilen == (0, 1), u
assert not regel(befunde([bohr, dict(bohr)]), dfm.UEBERLAPP)            # deckungsgleich zählt nur als doppelt
u = regel(befunde([bohr, dict(bohr), dict(bohr, x=104)]), dfm.UEBERLAPP)     # Original gegen die dritte
assert len(u) == 1 and u[0].zeilen == (0, 2), u
au = regel(befunde([bohr, dict(bohr, x=900)]), dfm.AUSSERHALB)
assert len(au) == 1 and au[0].zeilen == (1,) and "500 mm" in au[0].text, au
assert regel(befunde([bohr], profil=dict(QR, wand=None)), dfm.WAND_FEHLT)
assert not regel(befunde([bohr], profil=dict(form="Vollmaterial rund", a=20, profil_id="RD 20")), dfm.WAND_FEHLT)
mu = regel(befunde([], profil=dict(QR, a=10, b=10, wand=6)), dfm.MASS_UNPLAUSIBEL)
assert len(mu) == 1 and "fast voll" in mu[0].text, mu
aus = [dict(regel=r, aktiv="nein") for r in dfm.KONFLIKT_REGELN]
p = dict(laenge=500, technik=json.dumps(dict(quelle=sw.QUELLE, konturen=[bohr, dict(bohr)])))
assert not [b for b in dfm.rohr(p, QR, None, aus) if b.regel in dfm.KONFLIKT_REGELN]
assert set(dfm.KONFLIKT_REGELN) <= set(dfm.REGELN) and dfm.status(befunde([bohr, dict(bohr)])).startswith("WARNUNG")
ok("U3 Bauteilprüfung: doppelt, überlappend, außerhalb, Wand fehlt, unplausibel; abschaltbar, Status WARNUNG")

# ------------------------------------------------------------------ U4 Einstellungen ohne Fenster
db = Datenbank(TMP / "rohrlaser.db")
db.einstellung_setzen("passwort", "")
db.einstellung_setzen("benutzer_kuerzel", "PB")
e = EINSTELLUNG["gewinn"]
assert "Standard: 10 %" in X.beschreibung(e) and "Erlaubt: 0 bis 500 %" in X.beschreibung(e), X.beschreibung(e)
assert X.ist_standard(db, "gewinn")
assert X.favorit_setzen(db, "gewinn") and X.favoriten(db) == ["gewinn"] and not X.favorit_setzen(db, "gewinn")
X.favorit_setzen(db, "ruesten_abmessung", True)
X.favorit_setzen(db, "gibt_es_nicht", True)
assert X.favoriten(db) == ["ruesten_abmessung"]                            # unbekannte Namen fallen weg
db.einstellung_setzen("gewinn", 0.25)
X.verlauf_eintragen(db, "gewinn", 0.10, 0.25, zeit="2026-11-19T10:00:00")
X.verlauf_eintragen(db, "gewinn", 0.25, 0.25)                               # gleich: kein Eintrag
v = X.verlauf(db)
assert len(v) == 1 and v[0]["alt"] == "10 %" and v[0]["neu"] == "25 %" and v[0]["wer"] == "PB", v
assert X.pruefen_fuer({"gewinn": 1.5}, ["gewinn"])[0][0] == X.WARNUNG
assert any(s == X.FEHLER for s, _, _ in X.pruefen({"gewinn_bis_1": 5000.0, "gewinn_bis_2": 3000.0}))
assert any(s == X.FEHLER for s, _, _ in X.pruefen({"ruesten_abmessung": 5000.0}))       # über „bis“
assert not X.pruefen(db.einstellungen()) or all(s != X.FEHLER for s, _, _ in X.pruefen(db.einstellungen()))
geaendert, sicherung = X.zuruecksetzen(db, ["gewinn", "passwort", "benutzer_kuerzel"])
assert geaendert == ["gewinn"] and db.einstellung("gewinn") == 0.10 and Path(sicherung).exists()
assert db.einstellung("benutzer_kuerzel") == "PB"                          # Kürzel bleibt
assert X.zuruecksetzen(db, ["gewinn"]) == ([], None)
db.einstellung_setzen("gewinn", 0.2)
db.einstellung_setzen("ruesten_abmessung", 20.0)
datei = TMP / "einst.json"
assert X.exportieren(db, datei) > 100
inhalt = json.loads(datei.read_text(encoding="utf-8"))
assert "passwort" not in inhalt["werte"] and "benutzer_kuerzel" not in inhalt["werte"]
db.einstellung_setzen("gewinn", 0.1)
db.einstellung_setzen("ruesten_abmessung", 15.0)
inhalt["werte"]["zuschlag_material"] = 99.0                                 # außerhalb 0…500 %: übersprungen
inhalt["werte"]["passwort"] = "geheim"                                      # nie übernommen
datei.write_text(json.dumps(inhalt), encoding="utf-8")
vor = X.import_vorschau(db, datei, gesperrt={"ruesten_abmessung"})
assert {n for n, _, _ in vor["aendern"]} == {"gewinn", "zuschlag_material"} and vor["gesperrt"] == ["ruesten_abmessung"]
erg = X.importieren(db, datei, gesperrt={"ruesten_abmessung"})
assert erg["geaendert"] == ["gewinn"] and "zuschlag_material" in erg["uebersprungen"], erg
assert db.einstellung("gewinn") == 0.2 and db.einstellung("ruesten_abmessung") == 15.0
assert db.einstellung("zuschlag_material") == 0 and db.einstellung("passwort") != "geheim"
try:
    X.importieren(db, TMP / "fehlt.json")
    raise AssertionError("fehlende Datei")
except X.ImportFehler:
    pass
db.einstellung_setzen("ansicht_raster", True)
db.einstellung_setzen("editor_legende", True)
prof = TMP / "profil.json"
assert X.profil_exportieren(db, prof) >= 3
d = json.loads(prof.read_text(encoding="utf-8"))
assert d["werte"]["ansicht_raster"] is True and X.FAVORITEN in d["werte"] and "teilen_ordner" not in d["werte"]
db2 = Datenbank(TMP / "zweiter.db")
d["werte"]["teilen_ordner"] = "X:/fremd"                                    # Ordner nie aus einem Profil
prof.write_text(json.dumps(d), encoding="utf-8")
assert X.profil_importieren(db2, prof) >= 3
assert db2.einstellung("ansicht_raster") is True and X.favoriten(db2) == ["ruesten_abmessung"]
assert not db2.einstellung("teilen_ordner")
ok("U4 Einstellungen: Standard/Bereich, Favoriten, Verlauf, Plausibilität, Zurücksetzen und Import mit Schutz, Profil")

# ------------------------------------------------------------------ U5 Einstellungen im Programm
f = Hauptfenster(db, stumm=True)
f.resize(1400, 900)
seite = f.einstellungen.seite_von("gewinn")
assert isinstance(seite, EinstellungenSeite) and "export" in seite.kopf and "standard" in seite.kopf
assert seite.sterne["gewinn"].text() == "☆" and seite.zurueck["gewinn"].isVisibleTo(seite)    # 20 % ≠ Standard
seite.favorit_setzen("gewinn", True)
assert seite.sterne["gewinn"].text() == "★" and "gewinn" in f.einstellungen_favoriten.felder
fav = f.einstellungen_favoriten
assert f.bereich.unter.indexOf(fav) >= 0 and fav.titel == "★ Favoriten"
assert seite.wert_zuruecksetzen("gewinn") and db.einstellung("gewinn") == 0.1
assert not seite.zurueck["gewinn"].isVisibleTo(seite)
assert X.verlauf(db, "gewinn")[-1]["neu"] == "10 %"
feld = seite.felder["gewinn"]
feld.setValue(150)
feld.editingFinished.emit()
assert db.einstellung("gewinn") == 1.5 and seite.warnung.isVisibleTo(seite) and "100 %" in seite.warnung.text()
geaendert = seite.seite_zuruecksetzen(frage=False)
assert "gewinn" in geaendert and db.einstellung("gewinn") == 0.1 and not seite.warnung.isVisibleTo(seite)
dlg = seite.verlauf_zeigen()
assert dlg.tabelle.rowCount() == len(X.verlauf(db)) >= 3
dlg.suche.setText("Gewinn")
assert 1 <= dlg.sichtbar() <= dlg.tabelle.rowCount()
seite.schutz_setzen({"gewinn"})
assert not seite.zurueck["gewinn"].isEnabled() and not seite.wert_zuruecksetzen("gewinn")
seite.schutz_setzen(set())
assert seite.exportieren(TMP / "aus_fenster.json") > 100
assert seite.importieren(TMP / "aus_fenster.json", frage=False)["geaendert"] == []
seite.favorit_setzen("gewinn", False)
assert "gewinn" not in fav.felder
ok("U5 Einstellungen im Programm: ☆/↺ je Wert, Favoritenseite, Warnung bei 150 % Gewinn, Seite auf Standard, "
   "Verlauf mit Suche, Sperre, Export/Import")

# ------------------------------------------------------------------ U6 Bauteilbibliothek
aid = beispiel_angebot.anlegen(db)
pos = db.positionen(aid)
v1 = PV.speichern(db, pos[0], "Strebe")
v2 = PV.speichern(db, pos[1], "Lasche")
PV.kategorie_setzen(db, v1, "Gestell")
PV.favorit_setzen(db, v2, True)
alle = db.zeilen(PV.TABELLE)
assert PV.kategorien(alle) == ["Gestell"]
assert [v["name"] for v in PV.suchen(alle)] == ["Lasche", "Strebe"]           # Favorit zuerst
assert [v["name"] for v in PV.suchen(alle, kategorie="Gestell")] == ["Strebe"]
assert [v["name"] for v in PV.suchen(alle, kategorie=PV.OHNE_KATEGORIE)] == ["Lasche"]
assert [v["name"] for v in PV.suchen(alle, nur_favoriten=True)] == ["Lasche"]
assert [v["name"] for v in PV.suchen(alle, pos[0]["profil_id"].split()[0].lower())]
k3 = PV.kopieren(db, v1, "Strebe lang")
kopie = next(v for v in db.zeilen(PV.TABELLE) if v["id"] == k3)
assert kopie["kategorie"] == "Gestell" and PV.werte(kopie) == PV.werte(next(v for v in alle if v["id"] == v1))
for name in ("Strebe", " "):
    try:
        PV.kopieren(db, v1, name)
        raise AssertionError(name)
    except ValueError:
        pass
s = f.angebot_oeffnen(aid) if hasattr(f, "angebot_oeffnen") else None
from rohrlaser.bibliothek_dialog import BibliothekDialog  # noqa: E402
b = BibliothekDialog(db, None, db.kontext())
b.stumm = True
assert b.tabelle.rowCount() == 3 and b.anzahl.text() == "3 von 3 Bauteilen"
b.suche.setText("strebe lang")
assert b.tabelle.rowCount() == 1 and b.aktuell()["name"] == "Strebe lang"
b.suche.setText("")
b.nur_fav.setChecked(True)
assert b.tabelle.rowCount() == 1 and b.aktuell()["name"] == "Lasche"
b.nur_fav.setChecked(False)
b.tabelle.selectRow(1)
gew = b.aktuell()
assert b._favorit_umschalten() is True and PV.ist_favorit(next(v for v in db.zeilen(PV.TABELLE) if v["id"] == gew["id"]))
b._kategorie("Halter")
assert "Halter" in [b.kategorie.itemText(i) for i in range(b.kategorie.count())]
assert b._kopieren("Neu aus Bibliothek") and b.tabelle.rowCount() == 4
assert b._loeschen(frage=False) and b.tabelle.rowCount() == 3
b.tabelle.selectRow(0)
b.einsetzen()
assert b.gewaehlt == b.aktuell()["id"]
ok("U6 Bauteilbibliothek: Kategorie, Favorit (zuerst), Suche, Kopieren mit gleichem Inhalt, Dialog mit Vorschau, "
   "Einsetzen")

# ------------------------------------------------------------------ U7 Vergleich
q = dict(pos=10, laenge=500, oberflaeche="", zusatz=json.dumps([dict(name="Entgraten")]),
         technik=json.dumps(dict(quelle=sw.QUELLE, konturen=[bohr])))
p = dict(q, oberflaeche="Verzinkt", zusatz=json.dumps([dict(name="Entgraten"), dict(name="Gewinde M8")]),
         technik=json.dumps(dict(quelle=sw.QUELLE, konturen=[bohr, dict(bohr, x=300)])))
u = fassung_vergleich.unterschiede(q, p, dict(material_teil=1.20, laser_netto=12.0), dict(material_teil=1.45,
                                                                                         laser_netto=12.02))
assert any(t.startswith("Oberfläche") and "Verzinkt" in t for t in u), u
assert "Geometrie: Konturen 1 → 2" in u and "Arbeitsschritte: + Gewinde M8" in u, u
assert any(t.startswith("Material 1,20 € → 1,45 €") for t in u) and not any(t.startswith("Laserzeit") for t in u), u
assert fassung_vergleich.unterschiede(q, dict(q)) == []
ok("U7 Vergleich: Oberfläche, Geometrie (Konturen), Arbeitsschritte, Material/Zeit (unter Grenze nicht)")

f.close()
print("Alle Prüfungen bestanden.")
