"""Test: Packkern 3.0 (Patrick 25.11.2026, Master-Auftrag „Ladegutberechnung und Verpackungsvisualisierung“).

Abnahmekriterien:
1. Überstand auf der 1.200-mm-Seite wird genutzt (einstellbar, je Packmittel), lange Teile bis zur max. Teillänge
   der Maschine (6.500 mm) stehen über.
2. Die 800-mm-Seite wird nie überschritten (auch mit Sicherheitsabstand).
3. Mindestabstände werden eingehalten (geometrische Prüfung jeder Packung).
4. Gleiche Artikel zusammen (Variante A), 5. sinnvoll gemischt, wenn es Packstücke spart.
6. Verschachtelung: U in U, Winkel ineinander, NIE Rohr in Rohr (Patrick 25.11.2026).
7. Ansicht 2D/3D zeichnet, Klick wählt ein Teil.
8. Varianten A–D mit Kennzahlen, genau eine beste.
9. Schnell (80.000 Teile), reproduzierbar, ohne Packkern-Schlüssel bitgleich wie bisher.
Dazu: Zufallsmischungen ohne Prüffehler, nie Teile verloren, Gewichtsgrenze, Änderungen von Hand.
"""
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import packkern, paletten  # noqa: E402


def ok(text):
    print("OK    ", text)


EUR = dict(lht_id="EUR", bezeichnung="Europalette", art="Palette", laenge=1200, breite=800, hoehe=144,
           eigengewicht=25, nutzlast=1000, max_laenge=1160, aktiv="ja")
GB = dict(lht_id="GB", bezeichnung="Gitterbox", art="Gitterbox", laenge=1200, breite=800, hoehe=800, eigengewicht=70,
          nutzlast=1500, aktiv="ja")
KM = dict(lht_id="K-M", bezeichnung="Karton M", art="Karton", laenge=600, breite=400, hoehe=400, eigengewicht=0.5,
          nutzlast=31.5, aktiv="ja")
LHT = [EUR, GB, KM]
K3 = {"palette_packkern": "ja"}


def pos(nr, form, a, b, w, laenge, n, kg):
    return (dict(id=nr, pos=nr * 10, artikel=f"A{nr}", stueck=n, laenge=laenge),
            dict(gewicht=kg, profil_abm=(form, a, b, w)))


def packen(teile, einst=None, lht="EUR", lht_zeilen=LHT):
    return paletten.packen([t[0] for t in teile], [t[1] for t in teile], lht_zeilen, lht, None,
                           dict(K3, **(einst or {})) if einst is not False else {})


def alle_teile(r):
    return [t for p in r["paletten"] for t in p.get("teile") or ()]


def stueck(r):
    return sum(n for p in r["paletten"] for _, n in p["inhalt"])


# 1. Überstand an der langen Seite
for u, soll, achse in ((50, 40, "längs"), (0, 30, "quer")):
    r = packen([pos(1, "Quadratrohr", 40, 40, 2, 640, 80, 1.5)], {"palette_ueberstand": u})
    lg = r["paletten"][0]["lagen"][0]
    assert lg["stueck"][0] == soll and lg["achse"] == achse, (u, lg)
    assert all(-u - 1e-6 <= t["x0"] and t["x1"] <= 1200 + u + 1e-6 for t in alle_teile(r))
ok("640-mm-Teile: mit 50 mm Überstand je Seite 2 × 20 längs (1.280 mm) je Lage, ohne Überstand nur 30 quer")
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 640, 40, 1.5)], {"palette_ueberstand": 50},
           lht_zeilen=[dict(EUR, pack_ueberstand=0.0), GB, KM])
assert r["paletten"][0]["grenzen"]["ueberstand"] == 0 and max(t["x1"] for t in alle_teile(r)) <= 1200 + 1e-6
ok("Überstand je Packmittel (Spalte Überstand je Stirnseite) geht vor die Einstellung")
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 640, 40, 1.5)], lht="GB")
assert max(t["x1"] for t in alle_teile(r)) <= 1200 + 1e-6 and min(t["x0"] for t in alle_teile(r)) >= -1e-6
ok("Gitterbox: nie Überstand")
for laenge in (2500, 6500):
    r = packen([pos(1, "Rechteckrohr", 60, 40, 3, laenge, 20, laenge / 1000 * 4.5)])
    assert r["je_lht"] == {"EUR": 1} and not r["paletten"][0]["pruefung"], r["hinweise"]
    t = alle_teile(r)
    assert abs(min(x["x0"] for x in t) + (laenge - 1200) / 2) < 1e-6
r = packen([pos(1, "Rechteckrohr", 60, 40, 3, 7000, 2, 30)])
assert stueck(r) == 2 and any("Sonderladung" in h for h in r["hinweise"])
ok("lange Teile bis 6.500 mm (max. Teillänge) mittig auf der Europalette, Überstand nur an der langen Seite; "
   "7.000 mm: Hinweis Sonderladung, kein Teil verloren")

# 2. kurze Seite nie überschritten, 3. Mindestabstand
for rand, abstand in ((0, 0), (15, 0), (10, 5)):
    r = packen([pos(1, "Quadratrohr", 60, 60, 3, 1100, 80, 6), pos(2, "Rundrohr", 48.3, 0, 2.6, 900, 50, 2.7),
                pos(3, "Flachstahl", 80, 0, 10, 700, 60, 4.4)], {"palette_rand": rand, "palette_abstand": abstand})
    for t in alle_teile(r):
        assert rand - 1e-6 <= t["y0"] and t["y1"] <= 800 - rand + 1e-6, (rand, t)
    for v in r["varianten"]:
        assert not v["fehler"], (rand, abstand, v["code"], v["fehler"][:3])
ok("Breite 800 mm nie überschritten, Sicherheitsabstand am Rand und Mindestabstand zwischen den Teilen "
   "eingehalten (geometrische Prüfung aller Varianten)")

# 4./5. sortenrein und sinnvoll mischen
teile = [pos(1, "Quadratrohr", 40, 40, 2, 1150, 30, 2.6), pos(2, "Quadratrohr", 30, 30, 2, 1150, 30, 1.9),
         pos(3, "Rundrohr", 33.7, 0, 2, 1150, 30, 1.8)]
r = packen(teile, {"palette_sortenrein": "stark"})
a = next(v for v in r["varianten"] if v["code"] == "A")
assert all(len(lg["stueck"]) == 1 for p in a["paletten"] for lg in p["lagen"])
assert r["anzahl"] == 1, r["anzahl"]
ok("Variante A: jede Lage sortenrein; alles auf einer Palette statt drei (Reste zusammen)")
r = packen([pos(i, "Quadratrohr", 40, 40, 2, 1150, 7, 2.6) for i in range(1, 6)])
assert r["anzahl"] == 1 and len(r["paletten"][0]["inhalt"]) == 5
ok("kleine Mengen verschiedener Artikel gemischt auf ein Packstück")
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 1150, 200, 2.6), pos(2, "Quadratrohr", 40, 40, 2, 1150, 200, 2.6)],
           {"palette_max_artikel": 1})
assert all(len(p["inhalt"]) == 1 for p in r["paletten"])
ok("max. Artikel je Packstück = 1: kein Packstück mit zwei Artikeln")

# 6. Verschachtelung
r = packen([pos(1, "Rundrohr", 88.9, 0, 3.2, 1200, 20, 8), pos(2, "Rundrohr", 60.3, 0, 2.9, 1000, 20, 4),
            pos(3, "Quadratrohr", 80, 80, 4, 1200, 20, 11), pos(4, "Quadratrohr", 40, 40, 2, 1000, 20, 2.5)])
assert not any(t["innen_von"] is not None for t in alle_teile(r))
ok("nie Rohr in Rohr (rund und eckig)")
r = packen([pos(1, "U-Profil", 120, 55, 7, 1200, 30, 15), pos(2, "U-Profil", 80, 40, 6, 1100, 30, 9)])
innen = [t for t in alle_teile(r) if t["innen_von"] is not None]
assert len(innen) == 30 and all(t["k"] == 1 for t in innen) and not r["paletten"][0]["pruefung"]
r2 = packen([pos(1, "U-Profil", 120, 55, 7, 1200, 30, 15), pos(2, "U-Profil", 80, 40, 6, 1100, 30, 9)],
            {"palette_verschachteln": "nein"})
assert not any(t["innen_von"] is not None for t in alle_teile(r2))
assert r["paletten"][0]["hoehe"] < r2["paletten"][0]["hoehe"], (r["paletten"][0]["hoehe"], r2["paletten"][0]["hoehe"])
r3 = packen([pos(1, "U-Profil", 100, 50, 6, 1000, 5, 15), pos(2, "U-Profil", 80, 45, 6, 1100, 5, 12)])
assert not any(t["innen_von"] is not None for t in alle_teile(r3))
ok("U 80 in U 120 (alle 30 im Inneren, niedriger als ohne Verschachteln); längeres Teil nie im kürzeren")
r = packen([pos(1, "L-Profil", 60, 60, 6, 1000, 100, 5.4)])
assert sum(t.get("stapel") or 1 for t in alle_teile(r)) == 100 and any((t.get("stapel") or 1) > 1 for t in alle_teile(r))
ok("gleiche Winkel ineinander gestapelt (alle 100 Stück in Stapeln)")

# 8. Varianten
r = packen([pos(i, "Rechteckrohr", 30 + 10 * i, 20 + 5 * i, 2, 300 + 150 * i, 15 * i, 0.4 * i) for i in range(1, 7)])
assert [v["code"] for v in r["varianten"]] == ["A", "B", "C", "D"] and sum(v["beste"] for v in r["varianten"]) == 1
for v in r["varianten"]:
    assert {"anzahl", "flaeche", "volumen", "artikel_mittel", "ueberstand", "fehler"} <= set(v)
    assert sum(n for p in v["paletten"] for _, n in p["inhalt"]) == sum(15 * i for i in range(1, 7))
beste = next(v for v in r["varianten"] if v["beste"])
assert all(beste["anzahl"] <= v["anzahl"] for v in r["varianten"])
assert r["variante"] == beste["code"]
r_a = packen([pos(1, "Quadratrohr", 40, 40, 2, 1150, 30, 2.6)], {"palette_modus": packkern.MODI[1]})
assert r_a["variante"] == "A"
ok(f"Varianten A–D mit Kennzahlen, beste {beste['code']} ({beste['anzahl']} Packstücke), Variante fest wählbar")

# Zufall: keine Prüffehler, nie Teile verloren, Gewicht, reproduzierbar
zufall = random.Random(2511)
formen = ("Quadratrohr", "Rechteckrohr", "Rundrohr", "U-Profil", "L-Profil", "Flachstahl")
for lauf in range(25):
    teile = []
    for i in range(1, zufall.randint(1, 7)):
        f = zufall.choice(formen)
        a_ = zufall.choice((20, 30, 40, 50, 60, 80, 100, 120))
        b_ = zufall.choice((20, 30, 40, 60)) if f in ("Rechteckrohr", "U-Profil", "L-Profil") else 0
        teile.append(pos(i, f, a_, b_, zufall.choice((2, 3, 5)), zufall.choice((150, 400, 640, 900, 1199, 1300,
                                                                                 2400, 4000)),
                         zufall.randint(1, 120), round(zufall.uniform(0.2, 20), 2)))
    if not teile:
        continue
    einst = {"palette_abstand": zufall.choice((0, 0, 3)), "palette_rand": zufall.choice((0, 0, 10)),
             "palette_zwischenlage": zufall.choice((0, 0, 20))}
    lht = zufall.choice(("EUR", "EUR", "GB"))
    r = packen(teile, einst, lht)
    soll = sum(t[0]["stueck"] for t in teile)
    for v in r["varianten"]:
        assert not v["fehler"], (lauf, v["code"], v["fehler"][:3])
        assert sum(n for p in v["paletten"] for _, n in p["inhalt"]) == soll, (lauf, v["code"])
        for p in v["paletten"]:
            last = (1000 if p["lht_id"] == "EUR" else 1500)
            einzel = max((t[1]["gewicht"] for t in teile), default=0)
            assert p["netto"] <= last + 1e-6 or einzel > last, (lauf, p["netto"])
    assert packen(teile, einst, lht)["paletten"] == r["paletten"]
ok("25 Zufallsmischungen (Europalette/Gitterbox, Abstände, Zwischenlage): jede Variante ohne Prüffehler, alle Teile "
   "gepackt, Nutzlast eingehalten, zweimal gerechnet gleich")

# Prüfung erkennt Fehler
t = [dict(e=0, k=0, x0=0, x1=100, y0=0, y1=50, z0=0, z1=50, rund=None, lage=1, innen_von=None, quer=False),
     dict(e=0, k=0, x0=50, x1=150, y0=40, y1=90, z0=0, z1=50, rund=None, lage=1, innen_von=None, quer=False),
     dict(e=0, k=0, x0=0, x1=100, y0=770, y1=820, z0=0, z1=50, rund=None, lage=1, innen_von=None, quer=False)]
pk = packkern.Packer(EUR, packkern.parameter(EUR, paletten.vorgaben(K3)), 1000, 975, [], [])
f = packkern.pruefen(pk, [], t)
assert any("Überschneidung" in x for x in f) and any("über die Breite" in x for x in f), f
ok("Prüfung meldet Überschneidung und Überschreiten der Breite")

# Von Hand
teile = [pos(1, "Quadratrohr", 40, 40, 2, 1150, 5, 2.6), pos(2, "Quadratrohr", 40, 40, 2, 1150, 5, 2.6)]
r = packen(teile)
assert r["anzahl"] == 1
r = packen(teile, {"palette_hand": {"artikel": {"1": {"allein": True}}}})
assert r["anzahl"] == 2 and all(len(p["inhalt"]) == 1 for p in r["paletten"])
ok("von Hand: Position allein auf ein Packstück")
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 1150, 200, 2.6)], {"palette_sortenrein": "stark"})
n0 = r["anzahl"]
lagen0 = len(r["paletten"][0]["lagen"])
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 1150, 200, 2.6)],
           {"palette_sortenrein": "stark", "palette_hand": {"variante": r["variante"], "verschieben": [[1, lagen0, 0]]}})
assert r["anzahl"] == n0 + 1 and stueck(r) == 200 and not r["paletten"][-1]["pruefung"]
ok("von Hand: oberste Lage auf ein neues Packstück verschoben, Packliste neu geprüft")
r = packen([pos(1, "Quadratrohr", 40, 40, 2, 300, 50, 2.6)],
           {"palette_hand": {"artikel": {"1": {"achse": "q"}}}})
assert all(t["quer"] for t in alle_teile(r))
ok("von Hand: Lage quer gelegt")

# 9. Tempo und bitgleich ohne Packkern
werte_k = [dict(gewicht=0.8, profil_abm=("Quadratrohr", 40.0, 40.0, 2.0))]
for n, soll in ((20, 1), (1000, 26), (10000, 257)):
    e = paletten.packen([dict(id=1, pos=10, stueck=n, laenge=300.0)], werte_k, LHT, "K-M", None, K3)
    assert e["anzahl"] == soll, (n, e["anzahl"])
    alt = paletten.packen([dict(id=1, pos=10, stueck=n, laenge=300.0)], werte_k, LHT, "K-M", None, {})
    assert alt["anzahl"] == soll and "kern" not in alt and "varianten" not in alt
t0 = time.time()
e = paletten.packen([dict(id=1, pos=10, stueck=40000, laenge=300.0), dict(id=2, pos=20, stueck=40000, laenge=200.0)],
                    werte_k * 2, LHT, "K-M", None, K3)
dauer = time.time() - t0
assert stueck(e) == 80000 and dauer < 10, dauer
ok(f"Kartons wie bisher (20/1.000/10.000 Teile); 80.000 Teile in {e['anzahl']} Kartons mit allen Varianten und "
   f"Prüfung in {dauer:.1f} s; ohne Einstellung Packkern unverändert")
assert paletten.vorgaben({}) == paletten.vorgaben({"palette_mischen": "Reste zusammenpacken"})
assert "kern" not in paletten.vorgaben({"palette_packkern": "nein"})
ok("gespeicherte Frachtberechnungen ohne Packkern-Schlüssel rechnen wie bisher")

# 7. Ansicht
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser.pack_ansicht import PackAnsicht  # noqa: E402

geaendert = []
r = packen([pos(1, "Quadratrohr", 50, 50, 3, 1290, 40, 5), pos(2, "U-Profil", 120, 55, 7, 1200, 12, 15),
            pos(3, "U-Profil", 100, 50, 6, 1100, 12, 12), pos(4, "Rundrohr", 60.3, 0, 3, 600, 30, 3),
            pos(5, "L-Profil", 50, 50, 5, 900, 40, 3.8)])
w = PackAnsicht(geaendert.append)
w.resize(1000, 760)
w.setzen(r)
w.show()
app.processEvents()
assert w.kennzahlen.rowCount() == 4 and w.variante.count() == 4 and w.packstueck.count() == r["anzahl"]
w.grab()
assert w.leinwand._treffer
form, i = w.leinwand._treffer[-1]
mitte = form.center() if hasattr(form, "center") else form.boundingRect().center()
for typ in (QMouseEvent.MouseButtonPress, QMouseEvent.MouseButtonRelease):
    w.leinwand.mousePressEvent(QMouseEvent(typ, QPointF(mitte), QPointF(mitte), Qt.LeftButton, Qt.LeftButton,
                                           Qt.NoModifier)) if typ == QMouseEvent.MouseButtonPress else \
        w.leinwand.mouseReleaseEvent(QMouseEvent(typ, QPointF(mitte), QPointF(mitte), Qt.LeftButton, Qt.NoButton,
                                                 Qt.NoModifier))
assert w.leinwand.wahl is not None and "Pos." in w.info.text()
w.k3d.click()
app.processEvents()
w.grab()
assert w.leinwand._treffer
w.allein.click()
assert geaendert and geaendert[-1]["artikel"]
ok("Ansicht: 2D und 3D gezeichnet, Klick zeigt das Teil, Kennzahlen je Variante, Änderung von Hand rechnet neu")

print("OK: Packkern 3.0")
