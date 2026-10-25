"""Prüft die Zusatzfenster im Fenster 'Material je Abmessung' (Patrick 23.10.2026, Freigabe 1a–6a): Abmessungs-Fenster
(Stangenbild, Schnittmuster, Bilanz, Teileliste), Preis-Aufbau, Profil-Info, Doppelklick je Spalte, Kontextmenü und
die Schritte nach dem Schließen (zur Position, Positionen markieren, Materialanfrage, Schnittplan drucken).

Aufruf: python tests/test_abmessung_fenster.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import abmessung, rechnen  # noqa: E402
from rohrlaser.abmessung_fenster import AbmessungFenster, PreisFenster, ProfilFenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.meterpreis_dialog import DOPPELKLICK  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))

# --- ohne Schnittplan: Fenster gehen auf, zeigen den Hinweis
offen = []


def bedienen(schritt):
    """Material-Fenster bedienen: schritt(d) öffnet Zusatzfenster (werden nur gebaut, nicht gezeigt)."""
    def f(d):
        d.zeigen = offen.append
        schritt(d)
        if not d.result():
            d.annehmen()
        return d.result()
    return f


s.material_einstellen(bedienen(lambda d: d.oeffnen(0, 7)))
f = offen[-1]
assert isinstance(f, AbmessungFenster) and f.warnung.isVisible() is False and "Noch nicht optimiert" in f.warnung.text()
assert not f.paare and f.k_optimieren.isVisibleTo(f) and not f.k_drucken.isEnabled()
assert all(t["eingeplant"] == 0 for t in f.teile) and f.teile_tab.rowCount() == len(f.teile) > 0
ok("ohne Schnittplan: Abmessungs-Fenster mit Hinweis, Knopf Neu optimieren, Teileliste ohne Stangen")

# --- mit Schnittplan: Rechenwerte
assert s.optimieren()
gruppen = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)
sw = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
zeilen = s._rechnung()[0]
alle = rechnen.anzeige_stangen(s.ergebnis, sw)
assert sum(len(abmessung.stangen(s.ergebnis, g["gruppe"], sw)) for g in gruppen) == len(alle)
# Halbschalen (Teile je Rohrumfang): Teilemeter zählen Rohrstücke, nicht Teile (Fehlersuche 25.10.2026)
p0 = next(p for p in s.positionen if p.get("profil_id") and p.get("stueck"))
halb = dict(p0, stueck=5, je_umfang=2)
g0 = rechnen.material_abmessungen(s.kopf, [halb], None, s.k, s.tabellen)[0]
assert abs(g0["teile_m"] - p0["laenge"] * 3 / 1000) < 1e-9, g0["teile_m"]
for g in gruppen:
    paare = abmessung.stangen(s.ergebnis, g["gruppe"], sw)
    nummern = [x["nr"] for x, _ in paare]
    assert nummern == sorted(nummern) and set(nummern) <= {x["nr"] for x, _ in alle}
    m = abmessung.muster(paare)
    assert sum(x["anzahl"] for x in m) == len(paare)
    b = abmessung.bilanz(paare, rechnen.kg_je_m(g["profil"], g["werkstoff"], s.k))
    assert abs(sum(x["m"] for x in b["posten"]) - b["gesamt_m"]) < 1e-9
    assert abs(b["gesamt_m"] - g["meter"]) < 1e-6, (b["gesamt_m"], g["meter"])
    assert all(x["m"] >= -1e-9 for x in b["posten"]) and abs(b["gesamt_kg"] - g["kg"]) < 0.01 * max(g["kg"], 1)
    assert abs(b["posten"][0]["m"] - g["teile_m"]) < 1e-6
    t = abmessung.teile(g, s.kopf, s.positionen, paare, zeilen, s.k)
    assert [x["pos"] for x in t] == g["positionen"]
    assert all(x["eingeplant"] == x["stueck"] and x["stangen"] for x in t)
    assert abs(sum(x["meter"] for x in t) - g["teile_m"]) < 1e-9
    assert abs(sum(x["anteil"] for x in t) - 1) < 1e-6
    assert abs(sum(x["material_teil"] * x["stueck"] for x in t) - g["kosten"]) < 0.01
    pa = abmessung.preis_aufbau(g, s.kopf, s.positionen, s.ergebnis, sw, zeilen, s.k, s.tabellen, s.einst)
    assert abs(pa["einkauf"] - g["kosten"]) < 1e-6 and sum(z["stangen"] for z in pa["laengen"]) == g["stangen"]
    assert all(z["mehr"] > 0 and z["preis_m"] > 0 for z in pa["laengen"]) and pa["herkunft"]
ok(f"{len(gruppen)} Abmessungen: Stangen, Muster, Bilanz (= Meter, Teile), Teileliste (Anteil 100 %, Material € = "
   "Schnittplan), Preis-Aufbau (Einkauf = Material €)")

assert abmessung.ende_text({}, "a") == "gerade"
assert abmessung.ende_text({"a_gerade": "nein", "a_ende": '{"winkel": 45, "richtung": 90}'}, "a") == "Gehrung 45°"
assert abmessung.ende_text({"b_gerade": "nein"}, "b") == "schräg"
assert abmessung.nummern_text([3, 4, 5, 6]) == "3–6" and abmessung.nummern_text([1, 3]) == "1, 3"
info = abmessung.profil_info(gruppen[1]["profil"], gruppen[1]["werkstoff"], s.k)
assert info["kgm"] > 0 and info["huellkreis"] > 0 and info["maschinen"] and any(m["passt"] for m in info["maschinen"])
assert abmessung.profil_info("gibt es nicht", "S235", s.k) is None
ok("Enden, Stangennummern, Profil-Info mit passenden Maschinen")

# --- Doppelklick je Spalte
offen.clear()


def alle_spalten(d):
    assert not d.ohne_plan and not d.veraltet
    for c in range(len(DOPPELKLICK) + 6):
        d.oeffnen(1, c)
    assert d.oeffnen(1, 2) is None and d.oeffnen(99, 7) is None


s.material_einstellen(bedienen(alle_spalten))
arten = [type(x).__name__ for x in offen]
assert arten == ["ProfilFenster", "ProfilFenster", "AbmessungFenster", "AbmessungFenster", "AbmessungFenster",
                 "AbmessungFenster", "PreisFenster", "PreisFenster"], arten
fokus = [x for x in offen if isinstance(x, AbmessungFenster)]
assert "border" in fokus[2].bilanz_box.styleSheet() and not fokus[1].bilanz_box.styleSheet()
assert "Einkauf gesamt" in offen[-1].ansicht.toPlainText() and "Verteilung" in offen[-1].ansicht.toPlainText()
assert isinstance(offen[0], ProfilFenster) and offen[0].tab.rowCount() == len(s.k.maschinen)
ok("Doppelklick: Querschnitt/Abmessung = Profil-Info, Pos./Stangen/Meter/Gewicht = Abmessung, Material €/€/m = "
   "Preis-Aufbau; Auswahlfelder ohne")

f = fokus[1]
g = gruppen[1]
assert not f.k_optimieren.isVisibleTo(f) and f.k_drucken.isEnabled() and f.k_anfrage.isEnabled()
assert len(f.bild.muster) == f.muster_tab.rowCount() and f.teile_tab.rowCount() == len(g["positionen"])
assert all(any(t["ref"] in {x["ref"] for x in f.teile} for t in m["teile"]) for m, _ in f.bild.muster)
ref = f.teile[-1]["ref"]
f.teil_waehlen(ref)
assert f.bild.markiert == ref and f.teile_tab.currentRow() == len(f.teile) - 1
f.muster_waehlen(0)
assert f.bild.markiert is None
f.teile_tab.setColumnHidden(2, True)
assert "Stangen" in f.windowTitle() or g["profil"] in f.windowTitle()
assert "Teile" in f.summen_text() and g["profil"] in f.kennzahlen()
ok("Abmessungs-Fenster: Stangenbild nur dieser Abmessung, Teil hervorheben in Bild und Liste, Muster anspringen")

# --- Schritte nach dem Schließen
ziel = s.positionen.index(next(p for p in s.positionen if p["pos"] == g["positionen"][-1]))


def zur_position(d):
    d.oeffnen(1, 7)
    w = offen[-1]
    w.zur_position(w.teile[-1]["ref"])
    assert d.nachher[0] == "position" and d.result()


offen.clear()
s.material_einstellen(bedienen(zur_position))
assert s.reiter.currentWidget() is s.pos_seite and s.pos_ansicht.currentIndex().row() == ziel
ok("Doppelklick auf ein Teil: Fenster schließen, Position im Angebot markiert")


def falsch_dann_position(d):
    d.felder[0].setText("abc")
    assert not d.schliessen_mit("position", "id1") and d.fehler.text() and d.nachher is None
    d.felder[0].setText("")
    d.reject()
    return 0


assert s.material_einstellen(falsch_dann_position) == 0
ok("ungültige Eingabe: Fenster bleibt offen, kein Sprung")


def markieren(d):
    eintraege = d.menue_eintraege(0)
    texte = [t for t, _, _ in eintraege if t]
    assert len(texte) == 7 and dict((t, a) for t, _, a in eintraege if t)["Schnittplan dieser Abmessung drucken …"]
    next(f for t, f, _ in eintraege if t and t.startswith("Positionen"))()


s.material_einstellen(bedienen(markieren))
markiert = sorted({i.row() for i in s.pos_ansicht.selectionModel().selectedRows()})
erwartet = sorted(r for r, p in enumerate(s.positionen) if p.get("id") in set(gruppen[0]["ids"]))
assert markiert == erwartet and len(erwartet) == len(gruppen[0]["positionen"]) == 2, (markiert, erwartet)
ok(f"Kontextmenü: 7 Einträge; Positionen dieser Abmessung markiert ({len(erwartet)} Zeilen)")

# Materialanfrage nur dieser Abmessung
gesehen = []


def anfrage(d):
    gesehen.extend(d.zeilen)
    return 0


d = s.material_anfragen(dialog=anfrage, gruppe=g)
assert gesehen and {z["profil"] for z in gesehen} == {g["profil"]}
assert sum(z["stangen"] for z in gesehen) == g["stangen"]
ok("Materialanfrage nur für diese Abmessung")

# Schnittplan dieser Abmessung drucken
pfade = []
s._ziel = lambda name, endung, *a: (pfade.append(name), tmp / f"{len(pfade)}.pdf")[1]
assert s.werkstatt_pdf(gruppe=g) and s.werkstatt_pdf()
klein, gross = (tmp / "1.pdf").stat().st_size, (tmp / "2.pdf").stat().st_size
assert pfade[0].endswith(g["profil"]) and klein < gross, (pfade, klein, gross)
ok("Werkstattpapiere nur dieser Abmessung (eigener Dateiname, kleiner als für das ganze Angebot)")

# 12-m-Vergleich nur einer Abmessung (Filter im HTML)
from rohrlaser.angebot_fenster import laengen_html  # noqa: E402
voll = laengen_html(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen, s.einst)
assert laengen_html(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen, s.einst, nur=[]).count("<table") == 0 \
    or not s.ergebnis.get("laengen")
assert voll
s.laengen_zeigen([0])
assert "eine Abmessung" in s.laengen_dialog.windowTitle()
s.laengen_zeigen()
assert "eine Abmessung" not in s.laengen_dialog.windowTitle()
s.laengen_dialog.close()
ok("12-m-Vergleich lässt sich auf eine Abmessung beschränken")

# Preis-Aufbau bei Kundenmaterial
p0 = next(p for p in s.positionen if p.get("id") in set(gruppen[0]["ids"]))
for pid in gruppen[0]["ids"]:
    db.position_aendern(pid, "material_herkunft", "Kunde beigestellt")
s.neu_laden()
assert s.optimieren()
offen.clear()
s.material_einstellen(bedienen(lambda d: (d.oeffnen(0, 10), d.oeffnen(0, 7))))
assert isinstance(offen[0], PreisFenster) and "Kundenmaterial" in offen[0].ansicht.toPlainText()
assert not offen[1].k_anfrage.isEnabled()
assert abmessung.laengen_indizes(s.ergebnis, dict(gruppen[0], kunde=True)) == []


def werkstoff_dann_anfrage(d):
    d.werkstoffe[1].setCurrentText("S355-10219")
    assert d.schliessen_mit("anfrage", d.gruppen[1])


s.material_einstellen(bedienen(werkstoff_dann_anfrage))
assert s.stand_optimierung() != "aktuell" and "neu optimieren" in fenster.statusBar().currentMessage()
ok("Kundenmaterial: Preis-Aufbau ohne Materialpreis, keine Materialanfrage, kein 12-m-Vergleich; "
   "Materialanfrage nach geändertem Werkstoff erst nach dem Optimieren")

# 12-m-Stangen, vom Lieferanten zugeschnitten: Bilanz mit Zuschnitt, Teile auf den Werkstücken
db.einstellung_setzen("laenge_vergleich", "ja")
db.neu("lieferlaengen", dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=12000, basis="€/m", preis=1.0))
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s.optimieren()
i = next(i for i, vg in enumerate(s.ergebnis.get("laengen") or []) if vg["profil"] == "RR 42,4x2,0")
assert s.laenge_waehlen(f"laenge:{i}:12000")
g = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)[0]
sw = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
paare = abmessung.stangen(s.ergebnis, g["gruppe"], sw)
assert list(g["laengen"]) == [12000] and len(paare) > g["stangen"] and abmessung.laengen_indizes(s.ergebnis, g) == [i]
b = abmessung.bilanz(paare, 1, g["meter"])
namen = [x["name"] for x in b["posten"]]
assert namen[-1] == "Zuschnitt beim Lieferanten" and abs(b["gesamt_m"] - g["meter"]) < 1e-9
assert abs(sum(x["m"] for x in b["posten"]) - g["meter"]) < 1e-9 and all(x["m"] >= -1e-9 for x in b["posten"])
assert abs(b["posten"][0]["m"] - g["teile_m"]) < 1e-6
t = abmessung.teile(g, s.kopf, s.positionen, paare, s._rechnung()[0], s.k)
assert all(x["eingeplant"] == x["stueck"] for x in t)
ok(f"12-m-Stangen mit Zuschnitt: {len(paare)} Stangen an der Maschine, Bilanz mit Zuschnitt "
   f"{b['posten'][-1]['m'] * 1000:.0f} mm, Rest {b['posten'][4]['m']:.2f} m")
print("Alle Prüfungen bestanden.")
