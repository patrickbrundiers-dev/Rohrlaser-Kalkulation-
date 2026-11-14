"""Plan Phase 3 und 4, Paket C (Patrick 13.11.2026 „Alles einbauen“): Normteile und Verbindungselemente.

- C1 CALC-017 Montage: Schrauben/Muttern unter den Zukaufteilen ergeben den Vorschlag „Montage Verbindungselemente“
  mit Menge = Elemente je Teil (gelb, kostet erst mit Übernehmen)
- C2 CALC-012 Schweißbolzen -> „Bolzenschweißen“, Einpressmuttern -> „Einpressmuttern setzen“ (je €/Stück)
- C3 PART-006 Lochbild: Löcher ohne Gewinde mit Ø der Einpressbohrung -> „Einpressmuttern setzen“ (Herkunft Lochbild)
- C4 PART-010 Satz mit Bohrungen ohne Schraube: Hinweis im Angebots-Check
- C5 PART-012 gerade Rohrteile ohne Endkappe: Hinweis (abschaltbar)
- C6 ASM-008 Gewicht und Schwerpunkt im Satz in 3D (Näherung, Herkunft genannt)
- C7 ASM-005 Varianten je Satz und je Baugruppe (ohne Oberfläche/Zukauf), nur Anzeige

Aufruf: python tests/test_paket_c.py   (QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import bg_schwerpunkt, satz_varianten, schneidweg as sw, verbindungselemente as ve, zukauf  # noqa: E402
from rohrlaser import zusatz_erkennung  # noqa: E402
from rohrlaser.ansicht3d import packen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.satz3d import Satz3dDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "c.db")
f = Hauptfenster(db, stumm=True)
katalog = db.tabellen()["zusatzarbeiten"]
namen = {z["name"]: z for z in katalog}
assert {ve.MONTAGE, ve.BOLZEN, ve.EINPRESS, ve.ENDKAPPE} <= set(namen), sorted(namen)
assert namen[ve.MONTAGE]["art"] == "€/Stück" and namen[ve.BOLZEN]["art"] == "€/Stück"
assert namen[ve.MONTAGE]["preis"] == namen[ve.BOLZEN]["preis"] == 1.0      # Patrick 14.11.2026


def artikel(nr, bez, preis):
    return db.zukauf_speichern(None, dict(artikelnr=nr, bezeichnung=bez, einheit="Stück",
                                          aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                          aufschlag_wert=0),
                               [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=preis)])])


def eintrag(aid, menge, je="Teil"):
    return dict(artikel_id=aid, menge=menge, je=je, stand=db.zukauf_stand(aid))


schraube = artikel("Z-M8", "Sechskantschraube ISO 4017 M8x25 8.8 verzinkt", 0.12)
mutter = artikel("Z-M8M", "Sechskantmutter ISO 4032 M8", 0.05)
bolzen = artikel("Z-SB", "Schweißbolzen ISO 13918 M6x20", 0.20)
einpress = artikel("Z-EP", "Einpressmutter M5 Stahl verzinkt", 0.15)
kappe = artikel("Z-EK", "Endkappe für QR 40x40", 0.30)

# ------------------------------------------------------------------ C1/C2 Vorschläge aus den Zukaufteilen
p = dict(bezeichnung="Halter", zukauf=json.dumps([eintrag(schraube, 4), eintrag(mutter, 4), eintrag(bolzen, 2),
                                                   eintrag(einpress, 3), eintrag(kappe, 1, "Satz")]))
v = {x["name"]: x for x in zusatz_erkennung.erkannt(p, katalog)}
assert v[ve.MONTAGE]["menge"] == 8 and v[ve.MONTAGE]["quelle"] == ve.QUELLE_ZUKAUF, v
assert "8 × Sechskantschraube" in v[ve.MONTAGE]["wort"]
assert v[ve.BOLZEN]["menge"] == 2 and v[ve.EINPRESS]["menge"] == 3, v
assert ve.ENDKAPPE not in v                     # Endkappe nur je Satz: keine Menge je Teil
assert ve.art("Rohr 40x40") is None and ve.art("Lamellenstopfen 40x40") == ve.ENDKAPPE
ok("C1/C2 Vorschläge aus Zukaufteilen: Montage 8 (4 Schrauben + 4 Muttern), Bolzenschweißen 2, Einpressen 3")

# ------------------------------------------------------------------ C3 Lochbild
blech = dict(bezeichnung="Blech", technik=json.dumps(dict(konturen=[
    dict(art=sw.BOHRUNG, d=5.41, anzahl=4), dict(art=sw.BOHRUNG, d=8.75, anzahl=2),
    dict(art=sw.BOHRUNG, d=5.41, anzahl=2, gewinde="M6"), dict(art=sw.BOHRUNG, d=12.0, anzahl=1)])))
assert ve.einpress_loecher(blech) == {"M4": 4, "M6": 2}
v = {x["name"]: x for x in zusatz_erkennung.erkannt(blech, katalog)}
assert v[ve.EINPRESS]["menge"] == 6 and v[ve.EINPRESS]["quelle"] == ve.QUELLE_LOCH and "prüfen" in v[ve.EINPRESS]["wort"]
ok("C3 Lochbild: 4 × Ø 5,41 (M4) + 2 × Ø 8,75 (M6) = 6 Einpressmuttern als Vorschlag, Gewindeloch zählt nicht")

# ------------------------------------------------------------------ Angebot: C4, C5, C6, C7
a = db.angebot_neu(dict(kunde="Beispiel GmbH", maschine="T03", stange=6000, skonto=0))
loecher = json.dumps(dict(konturen=[dict(art=sw.BOHRUNG, d=9.0, anzahl=2)]))
oel = json.dumps([dict(name="Ölen/Konservieren")])
basis = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", schneidweg=320, einstiche=2)
db.position_neu(a, dict(basis, pos=10, artikel="Holm", laenge=1000, stueck=2, satz="S1", je_satz=1, zusatz=oel,
                        technik=loecher))
db.position_neu(a, dict(basis, pos=20, artikel="Strebe", laenge=500, stueck=2, satz="S1", je_satz=1, technik=loecher,
                        zukauf=json.dumps([eintrag(schraube, 2)])))
db.position_neu(a, dict(basis, pos=30, artikel="Lasche", laenge=200, stueck=4, satz="S2", je_satz=2, technik=loecher))
db.position_neu(a, dict(pos=40, artikel="Stange", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                        stueck=10, schneidweg=270, einstiche=0))
s = f.angebot_oeffnen(a)
assert s.optimieren()
s.neu_laden()
punkte = s._verbinder_punkte()
c4 = [t for _a, t, _z in punkte if "Satz „S2“" in t]
assert len(c4) == 1 and "4 Bohrungen" in c4[0], punkte
assert not any("Satz „S1“" in t for _a, t, _z in punkte)          # S1 hat Schrauben
c5 = [t for _a, t, _z in punkte if "Endkappe" in t]
assert len(c5) == 1 and "Pos. 40" in c5[0] and "Pos. 10" not in c5[0], punkte
s.einst["endkappen_hinweis"] = "nein"
assert not any("Endkappe" in t for _a, t, _z in s._verbinder_punkte())
s.einst["endkappen_hinweis"] = "ja"
assert all(x[0] == "HINWEIS" for x in punkte)
ok("C4/C5 Angebots-Check: Satz S2 mit 4 Bohrungen ohne Schraube, Pos. 40 ohne Endkappe (abschaltbar), nur Hinweise")

# C6 Gewicht und Schwerpunkt: zwei Quader in Einbaulage
ids = {q["pos"]: q["id"] for q in s.positionen}


def quader(lx, ly, lz):
    p = [0, 0, 0, lx, 0, 0, lx, ly, 0, 0, ly, 0, 0, 0, lz, lx, 0, lz, lx, ly, lz, 0, ly, lz]
    t = [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
    return dict(p=p, t={"F": t})


netze = {ids[10]: packen(dict(quader(40, 40, 1000), lage=[0, 0, 0, 0, 0, 1, 1, 0, 0])),
         ids[20]: packen(dict(quader(40, 40, 500), lage=[500, 0, 0, 0, 0, 1, 1, 0, 0]))}
e = bg_schwerpunkt.rechnen([(ids[10], [0, 0, 0, 0, 0, 1, 1, 0, 0], quader(40, 40, 1000)),
                            (ids[20], [500, 0, 0, 0, 0, 1, 1, 0, 0], quader(40, 40, 500))], s.positionen, s.k)
g10 = bg_schwerpunkt.bg_mengen.teil_werte(s.positionen[0], s.k)["gewicht"]
g20 = bg_schwerpunkt.bg_mengen.teil_werte(s.positionen[1], s.k)["gewicht"]
assert g10 > 0 and abs(g10 - 2 * g20) < 1e-6 and abs(e["kg"] - g10 - g20) < 1e-9
x, y, z = e["schwerpunkt"]
assert abs(x - (20 * g10 + 520 * g20) / (g10 + g20)) < 1e-6 and abs(y - 20) < 1e-6
assert abs(z - (500 * g10 + 250 * g20) / (g10 + g20)) < 1e-6, e
wert, tipp = bg_schwerpunkt.text(e)
assert wert.endswith(" kg") and "Schwerpunkt X" in tipp and "Näherung" in tipp
d = Satz3dDialog(s, "S1", s.positionen, s.k.profile, {}, netze, None)
d.zeigen()
kachel = d._masse_kachel()
assert kachel[0] == "Gewicht (Näherung)" and kachel[1] == wert, kachel
ok(f"C6 Gewicht und Schwerpunkt: Satz S1 {wert}, Schwerpunkt X {x:.0f} / Y {y:.0f} / Z {z:.0f} mm (Näherung)")

# C7 Varianten je Satz
assert d.varianten_feld is not None
vv = {n: (p_, d_) for n, p_, d_ in d.varianten_feld.varianten}
assert set(vv) == {"wie angeboten", "ohne Oberfläche", "ohne Zukauf", "ohne Oberfläche und Zukauf"}, vv
assert vv["ohne Oberfläche"][0] < vv["wie angeboten"][0] and vv["ohne Zukauf"][0] < vv["wie angeboten"][0]
assert vv["ohne Oberfläche und Zukauf"][0] < min(vv["ohne Oberfläche"][0], vv["ohne Zukauf"][0])
assert "keine Staffel" in d.varianten_feld.text()
assert [q.get("zusatz") for q in db.positionen(a)][0] == oel        # nichts geändert
assert not db.staffeln(a) if hasattr(db, "staffeln") else True
d.close()
ok("C7 Varianten je Satz: " + ", ".join(f"{n} {p_:.2f} €" for n, (p_, _d) in vv.items()) + " – nur Anzeige")

# C7 Varianten je Baugruppe (Rahmen R1 mit Schraube an der BG und Lasche als Zukaufteil)
import beispiel_baugruppe  # noqa: E402
db2 = Datenbank(tmp / "bg.db")
f2 = Hauptfenster(db2, stumm=True)
a2 = beispiel_baugruppe.anlegen(db2)
s2 = f2.angebot_oeffnen(a2)
bi = next(i for i, q in enumerate(s2.positionen) if q.get("art") == "Schweißbaugruppe" or q.get("baugruppe"))
v2 = satz_varianten.fuer_baugruppe(s2.kopf, s2.positionen, s2.ergebnis, s2.k, s2.tabellen, s2.einst, bi)
n2 = {n: p_ for n, p_, _d in v2}
assert set(n2) == {"wie angeboten", "ohne Zukauf"} and n2["ohne Zukauf"] < n2["wie angeboten"], v2
ok(f"C7 Varianten je Baugruppe: wie angeboten {n2['wie angeboten']:.2f} €, ohne Zukauf {n2['ohne Zukauf']:.2f} €")
# Beispielpreise von 0.9.336 (0,50/0,60 €) werden einmalig 1,00 €, eigene Preise bleiben
from rohrlaser import datenbank as dbm  # noqa: E402
db3 = Datenbank(tmp / "alt.db")
db3.con.execute("UPDATE zusatzarbeiten SET preis=0.5 WHERE name=?", (ve.MONTAGE,))
db3.con.execute("UPDATE zusatzarbeiten SET preis=0.75 WHERE name=?", (ve.BOLZEN,))
db3.einstellung_setzen("rohrlaser_zusatz_stand", "2026-11-13b")
db3._rohrlaser_zusatz_ergaenzen()
p3 = {z["name"]: z["preis"] for z in db3.zeilen("zusatzarbeiten")}
assert p3[ve.MONTAGE] == 1.0 and p3[ve.BOLZEN] == 0.75 and db3.einstellung("rohrlaser_zusatz_stand") == dbm.ROHRLASER_ZUSATZ_STAND
ok("Beispielpreise 1,00 € (Patrick 14.11.2026): unveränderte 0,50 € werden 1,00 €, eigener Preis bleibt")
print("Alle Prüfungen bestanden.")
