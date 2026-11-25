"""Universelle Endkonturen + Konturverschachtelung (Master-Auftrag Patrick 25.11.2026, endkontur.py).

Geprüft: alle Konturarten (Verlauf, Spitze bei 0, Tiefe, Schnittlänge, Prüfung), Darstellung über skizze, Verschachteln
beliebiger Konturen (V/U/Bogen/Stufen, Rund-, Quadrat- und Rechteckrohr), Kollisionsprüfung (Gegenprobe über alle
Zellpaare und an der feinen echten Kante: nie enger als 2 × Schnittverlust + Abstand), Mindestabstand, Drehungen nur
wie erlaubt, Nasen und offene Profile nie verschachtelt, ebene Gehrungen bitgleich wie bisher, Strategie P nie
schlechter als A, Vergleich „ohne Konturverschachtelung“, Schneidweg-Rechner und Optimierung über rechnen.

Aufruf: python tests/test_endkontur.py
"""
import dataclasses
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import endkontur as ek, nesting as ne, nesting_vergleich as nv, optimierung as opt  # noqa: E402
from rohrlaser import rechnen, schneidweg as sw, skizze as sk  # noqa: E402

QR60 = dict(form="Quadratrohr", a=60, b=60, wand=3)
RE80 = dict(form="Rechteckrohr", a=80, b=40, wand=3)
RR60 = dict(form="Rundrohr", a=60.3, wand=3)
fehler = []


def pruef(bed, text):
    if not bed:
        fehler.append(text)
        print("FEHLER", text)


def qs_von(profil):
    return sk.Querschnitt(sw.mit_radius(profil, {}))


def ende(k):
    return {"kontur": k}


V_K = dict(typ=ek.V_KERBE, tiefe=25, breite=40)
V_S = dict(typ=ek.V_SPITZE, tiefe=25)
U_K = dict(typ=ek.U_KERBE, tiefe=20, breite=30)
U_Z = dict(typ=ek.U_ZUNGE, tiefe=20, breite=30)
B_X = dict(typ=ek.BOGEN_VEX, tiefe=10)
B_K = dict(typ=ek.BOGEN_KAV, tiefe=10)


def test_arten():
    beispiele = [dict(typ=ek.SCHRAEG, tiefe=20), V_S, V_K, U_K, U_Z, dict(typ=ek.S_KURVE, tiefe=15), B_X, B_K,
                 dict(typ=ek.STUFEN, stufen=[[20, 10], [40, 20]]),
                 dict(typ=ek.FREI, punkte=[[-30, 0], [0, 15], [30, 5]]),
                 dict(typ=ek.FREI_S, punkte=[[0, 0], [60, 12], [120, 0], [180, 12]]),
                 dict(typ=ek.KOMBI, teile=[dict(typ=ek.SCHRAEG, tiefe=10), V_K])]
    for profil in (QR60, RE80, RR60):
        qs = qs_von(profil)
        for k in beispiele:
            um = ek.umriss(qs, k)
            ds = [d for _, d in um]
            pruef(um and abs(min(ds)) < 1e-6, f"{profil['form']} {k['typ']}: Spitze nicht bei 0")
            pruef(ek.tiefe(qs, k) > 0, f"{profil['form']} {k['typ']}: Tiefe 0")
            sl = ek.schnittlaenge(qs, k)
            pruef(sl > qs.umfang - 1e-6, f"{profil['form']} {k['typ']}: Schnittlänge {sl} < Umfang {qs.umfang}")
            # Darstellung: skizze liest denselben Verlauf
            s = ek.text(k)
            pruef(bool(s), f"{k['typ']}: kein Text")
            pruef(sk.ende_umriss_von(qs, ende(k)), f"{k['typ']}: skizze kennt die Kontur nicht")
    # Schräg über die volle Höhe = Gehrung mit tan(w) * Höhe: Länge wie die Ellipse/Gehrung
    qs = qs_von(QR60)
    k = dict(typ=ek.SCHRAEG, tiefe=60)
    pruef(abs(ek.tiefe(qs, k) - 60) < 0.6, f"Schräg Tiefe {ek.tiefe(qs, k)}")
    # V-Kerbe auf dem Quadratrohr: Schnittlänge = 2 Seiten + 2 × schräge Flanken (Wände links/rechts gerade)
    sl = ek.schnittlaenge(qs, V_K)
    pruef(sl > qs.umfang + 2 * (math.hypot(20, 25) - 20) * 1.8, f"V-Kerbe Schnittlänge {sl} zu kurz")
    # Stufen von beiden Seiten richtig (Fehler vom 25.11.: d = 0 auf der Oberseite)
    st = ek.umriss(qs, dict(typ=ek.STUFEN, stufen=[[30, 0], [30, 15]]))
    pruef(max(d for _, d in st) > 14, "Stufe fehlt im Verlauf")
    print("OK     Konturarten: Spitze bei 0, Tiefe, Schnittlänge ≥ Umfang, Darstellung über skizze, je Profil")


def test_pruefen():
    qs = qs_von(QR60)
    f = ek.pruefen(qs, dict(typ=ek.V_KERBE, tiefe=20, breite=0.1), kerf=0.3, laenge=500, wand=3)
    pruef(any(x[0] == ek.FEHLER for x in f), f"Schlitz schmaler als die Fuge nicht gemeldet: {f}")
    f = ek.pruefen(qs, dict(typ=ek.V_SPITZE, tiefe=300), kerf=0.2, laenge=200, wand=3)
    pruef(any(x[0] == ek.FEHLER for x in f), "Kontur tiefer als das Teil nicht gemeldet")
    f = ek.pruefen(qs, V_S, kerf=0.2, laenge=500, wand=3)
    pruef(not any(x[0] == ek.FEHLER for x in f), f"V-Spitze fälschlich Fehler: {f}")
    pruef(not any("Zunge" in x[1] for x in f), f"V-Spitze fälschlich dünne Zunge: {f}")
    print("OK     Prüfung: Schlitz < Fuge und Kontur tiefer als das Teil = Fehler, normale V-Spitze ohne Befund")


def gruppe(profil, enden, n=10, laenge=500, kerf=0.2, abstand=2.5, zugabe=0.5, drehung=opt.FREI):
    """Gruppe mit n Teilen; enden = (Ende A, Ende B) als Kontur-Dicts oder None (gerade)."""
    qs = qs_von(profil)
    gk = ek.geo_schluessel(qs)
    g = opt.Gruppe(profil="P", werkstoff="S235", stange=6000, endbeschnitt=10, greiferrest=142, kerf=kerf,
                   abstand=abstand)
    g.kontur_geo, g.kontur_zugabe = gk, zugabe
    ka = ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, ende(enden[0]))) if enden[0] else None
    kb = ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, ende(enden[1]))) if enden[1] else None
    g.teile = [opt.Teil(zeile=13, pos=10, artikel="K", nr=i + 1, laenge=laenge, a_gerade=enden[0] is None,
                        b_gerade=enden[1] is None, a_schnitt=300, b_schnitt=300, a_kontur=ka, b_kontur=kb,
                        drehung=drehung) for i in range(n)]
    return g, qs


def test_verschachteln():
    for profil, a, b in ((QR60, V_K, V_S), (QR60, U_K, U_Z), (RE80, V_K, V_S), (RR60, B_K, B_X), (RR60, V_K, V_S)):
        g, qs = gruppe(profil, (a, b), n=23)
        mit = opt.optimiere(g)
        opt.pruefe([g], [mit])
        for f in mit:
            opt.pruefe_drehungen(g, f)
        n_k = sum(opt.konturen_ineinander(g, f) for f in mit)
        ohne = nv.ohne_konturen(g)
        o = opt.optimiere(ohne)
        pruef(n_k > 0, f"{profil['form']} {a['typ']}/{b['typ']}: keine Konturverschachtelung")
        pruef(len(mit) <= len(o), f"{profil['form']}: mit Konturen mehr Stangen ({len(mit)} > {len(o)})")
        # Gegenprobe je Nachbarpaar: kleinster Abstand über alle Zellpaare und an der echten feinen Kante
        soll = opt.kontur_abstand(g)
        geprueft = 0
        for f in mit:
            for (t1, r1), (t2, r2) in zip(f, f[1:]):
                if not (opt.kontur_paar(g, t1, t2) and opt.ineinander(g, t1, r1, t2, r2)):
                    continue
                x = opt.kontur_trennung(g, t1, r1, t2, r2)
                d = ek.kleinster_abstand(g.kontur_geo, t1.b_kontur, r1, t2.a_kontur, r2, x)
                pruef(d >= soll - 1e-6, f"{profil['form']}: Zellen-Gegenprobe {d:.3f} < {soll}")
                if geprueft < 2:
                    e = ek.echter_abstand(qs, ende(b), r1, ende(a), r2, x, n=360)
                    pruef(e >= 2 * g.kerf + g.abstand - 0.05, f"{profil['form']}: echter Abstand {e:.3f} < Soll")
                geprueft += 1
        pruef(geprueft == n_k, "nicht alle Stellen geprüft")
    # 26 Teile 450 mm V-Kerbe/V-Spitze auf QR 60 (Fuge 0,2, Abstand 2,5, Sicherheit 0,5): 3 Stangen ohne, 2 mit
    g, _ = gruppe(QR60, (V_K, V_S), n=26, laenge=450)
    pruef(len(opt.optimiere(g)) == 2 and len(opt.optimiere(nv.ohne_konturen(g))) == 3, "26 Teile: 2 statt 3 Stangen")
    print("OK     Verschachteln V/U/Bogen auf Quadrat-, Rechteck- und Rundrohr, Gegenprobe Zellen + echte Kante, "
          "26 Teile 3 → 2 Stangen")


def test_abstand_kollision():
    qs = qs_von(QR60)
    gk = ek.geo_schluessel(qs)
    kb = ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, ende(V_S)))
    ka = ek.profil_schluessel(ek.ende_verlauf_zellen(qs, gk, ende(V_K)))
    x1 = ek.trennung(gk, 1.0, kb, 0, ka, 0)
    x5 = ek.trennung(gk, 5.0, kb, 0, ka, 0)
    pruef(x5 > x1, f"größerer Abstand muss weiter trennen: {x1} / {x5}")
    pruef(x1 < 0, f"V in V muss sich überlappen: {x1}")
    # etwas enger als berechnet = Kollision bzw. zu eng
    pruef(ek.kleinster_abstand(gk, kb, 0, ka, 0, x5 - 3) < 5.0 - 1e-6, "zu eng nicht erkannt")
    pruef(ek.kleinster_abstand(gk, kb, 0, ka, 0, x5 - 30) <= 0, "Durchdringung nicht erkannt")
    # Drehung 90° auf dem Quadrat: V-Spitze passt nicht mehr in die Kerbe -> weniger Überlappung
    x90 = ek.trennung(gk, 5.0, kb, 0, ka, 90)
    pruef(x90 is not None and x90 > x5, f"gedreht passt die Spitze nicht in die Kerbe: {x90} / {x5}")
    # pruefe_drehungen bemerkt eine zu enge Folge (Abstand nachträglich vergrößert)
    g, _ = gruppe(QR60, (V_K, V_S), n=6)
    f = opt.optimiere(g)[0]
    echt = opt.trennung_teile
    opt.trennung_teile = lambda *a: echt(*a) - 3.0      # Rechnung absichtlich 3 mm zu eng: Prüfung muss es merken
    try:
        opt.pruefe_drehungen(g, f)
        pruef(False, "zu enge Endkonturen nicht gemeldet")
    except AssertionError as e:
        pruef("enger" in str(e), f"falsche Meldung: {e}")
    finally:
        opt.trennung_teile = echt
    print("OK     Mindestabstand (mehr Abstand = weiter), Kollision und zu enge Lage erkannt, Drehung 90° berücksichtigt")


def test_sonderfaelle():
    # Nasen und offene Profile: keine Verschachtelung
    qs = qs_von(QR60)
    gk = ek.geo_schluessel(qs)
    pruef(ek.ende_verlauf_zellen(qs, gk, dict(nasen=[1], kontur=V_K)) is None, "Nasen verschachtelt")
    pruef(ek.geo_schluessel(sk.Querschnitt(dict(form="U-Profil", a=60, b=30, wand=4))) == "", "offenes Profil")
    # feste Naht: keine Drehung außer der Nahtlage, Konturen trotzdem nur wie erlaubt
    g, _ = gruppe(QR60, (V_K, V_S), n=8, drehung=opt.FEST)
    g.teile = [dataclasses.replace(t, naht=0.0) for t in g.teile]
    for f in opt.optimiere(g):
        opt.pruefe_drehungen(g, f)
        pruef(all(r % 360 == 0 for _, r in f), "Teil mit fester Naht gedreht")
    # Gerade Enden + Konturen gemischt: gerade Nachbarn teilen weiter den Schnitt
    g, _ = gruppe(QR60, (None, None), n=4)
    pruef(not any(t.a_kontur or t.b_kontur for t in g.teile), "gerade Enden mit Verlauf")
    print("OK     Nasen und offene Profile nie verschachtelt, feste Naht nie gedreht, gerade Enden ohne Verlauf")


def test_gehrung_bitgleich():
    # Gruppe nur mit ebenen Gehrungen: _konturen_nur_wo_noetig nimmt die Verläufe weg -> alte Rechnung
    g = opt.Gruppe(profil="QR 60x60x3", werkstoff="S235", stange=6000, endbeschnitt=10, greiferrest=142, kerf=0.2,
                   abstand=0.0)
    g.kontur_geo = "Gx"
    g.teile = [opt.Teil(zeile=13, pos=10, artikel="G", nr=i + 1, laenge=400, a_gerade=False, b_gerade=False,
                        a_schnitt=200, b_schnitt=200,
                        a_gehrung=(45, 0), b_gehrung=(45, 0), a_kontur="P1", b_kontur="P2") for i in range(4)]
    rechnen._konturen_nur_wo_noetig([g])
    pruef(g.kontur_geo == "" and all(t.a_kontur is None and t.b_kontur is None for t in g.teile),
          "Gehrungsgruppe behält Verläufe")
    pruef(ek.lesen({"typ": "gibt es nicht"}) is None and ek.lesen(None) is None, "ungültige Kontur gelesen")
    print("OK     Nur ebene Gehrungen: Verläufe fallen weg (bitgleich wie bisher), ungültige Eingaben ignoriert")


def test_strategie_p():
    g, _ = gruppe(QR60, (V_K, V_S), n=30, laenge=420)
    laengen = [ne.Laenge(6000, 60.0)]
    pa = ne.planen(g, ne.A, laengen)
    pp = ne.planen(g, ne.P, laengen)
    pruef(pp is not None and pp.werte["stangen"] <= pa.werte["stangen"], "P schlechter als A (Stangen)")
    pruef(pp.werte["gekauft_mm"] <= pa.werte["gekauft_mm"] + 1e-6, "P kauft mehr als A")
    ne.pruefe(g, pp.stangen, pp.uebrig, laengen)
    pruef(pp.werte.get("konturen", 0) > 0, "P ohne Konturverschachtelung")
    pruef(not opt.praezision_an(), "Präzisionsmodus bleibt an")
    pruef(ne.P in ne.REIHE and ne.STRATEGIEN.get(ne.P), "P fehlt in der Reihe")
    print("OK     Strategie P (Präzision): nie schlechter als A, geprüft, Modus danach aus")


def test_vergleich():
    g, _ = gruppe(QR60, (V_K, V_S), n=26, laenge=450)
    laengen = [ne.Laenge(6000, 60.0)]
    mit = [(6000, f, "") for f in opt.optimiere(g)]
    ohne_g = nv.ohne_konturen(g)
    ohne = [(6000, f, "") for f in opt.optimiere(ohne_g)]
    v = dict(plaene={nv.BISHER: ne.Plan(nv.BISHER, mit, [], ne.kennzahlen(g, mit, [], laengen)),
                     nv.OHNE_KONTUR: ne.Plan(nv.OHNE_KONTUR, ohne, [], ne.kennzahlen(ohne_g, ohne, [], laengen))})
    e = nv.kontur_einsparung(v)
    pruef(e and e["stangen"] == 1 and e["mm"] == 6000 and abs(e["eur"] - 60) < 1e-6, f"Einsparung falsch: {e}")
    pruef(e["stellen"] > 0 and e["ausnutzung_nachher"] > e["ausnutzung_vorher"], f"Kennzahlen falsch: {e}")
    pruef(nv.ohne_konturen(ohne_g) is None, "Gruppe ohne Konturen liefert Vergleich")
    pruef(("konturen", "davon Endkonturen") in nv.SPALTEN, "Spalte fehlt")
    print("OK     Vergleich ursprünglich/optimiert: 1 Stange, 6 m, 60 € gespart, Ausnutzung steigt, Spalte vorhanden")


def test_schneidweg_rechnen():
    eing = dict(a=dict(kontur=V_K), b=dict(kontur=V_S), konturen=[], quelle=sw.QUELLE)
    r = sw.rechnen(eing, QR60, (20, 60), laenge=500)["felder"]
    pruef(r["a_gerade"] == "nein" and r["b_gerade"] == "nein", "Kontur-Enden als gerade gerechnet")
    qs = qs_von(QR60)
    gerade = sw.rechnen(dict(a={}, b={}, konturen=[], quelle=sw.QUELLE), QR60, (20, 60), laenge=500)["felder"]
    soll = ek.schnittlaenge(qs, V_K, gerade["a_schnitt"])     # Verhältnis Kurve/Umfang auf die gerade Länge
    pruef(abs(r["a_schnitt"] - soll) < 0.2, f"Schnittlänge A {r['a_schnitt']} ≠ {soll}")
    pruef(r["a_schnitt"] > gerade["a_schnitt"] + 10, "Kontur nicht länger als gerade")
    # Optimierung über rechnen: Position mit diesen Enden bekommt Verläufe
    import json
    p = dict(technik=json.dumps(eing), a_schnitt=r["a_schnitt"], b_schnitt=r["b_schnitt"])
    ka, kb, gk = rechnen.kontur_enden(p, QR60, False, False)
    pruef(ka and kb and gk, f"kontur_enden ohne Verläufe: {ka} {kb} {gk}")
    print("OK     Schneidweg-Rechner: Kontur-Enden mit Kurvenlänge, Optimierung bekommt die Verläufe")


def test_kennung():
    import json
    eing = dict(a=dict(kontur=V_K), b=dict(kontur=V_S), konturen=[], quelle=sw.QUELLE)
    g = opt.Gruppe(profil="P", werkstoff="S", stange=6000, endbeschnitt=10, greiferrest=142, kerf=0.2, abstand=2.5)
    g.kontur_geo, g.kontur_zugabe = "Gx", 0.5
    g2 = dataclasses.replace(g, kontur_zugabe=2.0)
    echt = rechnen.gruppen_bilden
    from types import SimpleNamespace
    K = SimpleNamespace(maschinen={}, profile={}, werkstoffe={})
    try:
        werte = []
        for gr in (g, g2):
            rechnen.gruppen_bilden = lambda *a, gr=gr: ([gr], [], [])
            werte.append(rechnen.eingabe_kennung({}, [dict(technik=json.dumps(eing))], K, {}, {}))
    finally:
        rechnen.gruppen_bilden = echt
    pruef(werte[0] != werte[1], "Sicherheitsabstand nicht in der Kennung des gespeicherten Plans")
    print("OK     Kennung des gespeicherten Plans enthält den Sicherheitsabstand der Endkonturen")


for t in (test_kennung, test_arten, test_pruefen, test_verschachteln, test_abstand_kollision, test_sonderfaelle,
          test_gehrung_bitgleich, test_strategie_p, test_vergleich, test_schneidweg_rechnen):
    try:
        t()
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        fehler.append(f"{t.__name__}: {e}")
if fehler:
    print(f"FEHLER: {len(fehler)}")
    sys.exit(1)
print("OK: Endkonturen und Konturverschachtelung")
