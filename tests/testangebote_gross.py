"""Reproduzierbare große Testangebote für Leistungsmessungen des Rechenkerns (Master-Prompt Rechenkerne 21.11.2026).

Fester Zufallsstartwert, keine Kundendaten. Größen (Positionen): S = 5, M = 50, L = 200, XL = 500.
Mischung wie in den Abnahme-Angeboten: 5 Profile der Beispieldaten × 3 Werkstoffe, Längen 80–5800 mm, Stückzahlen
1–40, jede 6. Position mit Gehrung an einem Ende, jede 10. mit Zusatzarbeit, jede 15. in einem Satz, jede 4. mit
echten Konturen (Bohrungen, Rechteck, Langloch) wie aus dem STEP-Import, damit Schneidfolge und Dynamik mitrechnen.
Dazu Staffeln 24/50/100 (Schlüssel 10) und 10/40/100 (Schlüssel 20).
"""
import json
import random

PROFILE = ["RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"]
WERKSTOFFE = ["S235-10219", "S355-10219", "1.4301"]
ZUSATZ = [dict(name="Feuerverzinken"), dict(name="Entgraten"), dict(name="Pulverbeschichten", text="RAL 7016")]
GROESSEN = dict(S=5, M=50, L=200, XL=500)


def _konturen(rnd, laenge, rund):
    n = rnd.randint(2, 8)
    out = []
    for _ in range(n):
        x = round(rnd.uniform(20, max(25.0, laenge - 20)), 1)
        art = rnd.random()
        seite = {} if rund else dict(seite=rnd.choice(["oben", "unten", "vorne", "hinten"]))
        if art < 0.7 or rund:
            out.append(dict(art="Bohrung", d=rnd.choice([5.5, 6.6, 8.5, 10.5, 12.0]), anzahl=1, x=x, **seite))
        elif art < 0.85:
            out.append(dict(art="Rechteck", b=20, h=12, r=2, anzahl=1, x=x, **seite))
        else:
            out.append(dict(art="Langloch", l=30, b=10, anzahl=1, x=x, **seite))
    return out


def positionen(n, seed=1):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        profil = PROFILE[i % len(PROFILE)]
        laenge = float(rnd.choice([rnd.randint(80, 600), rnd.randint(600, 2500), rnd.randint(2500, 5800)]))
        p = dict(pos=10 * (i + 1), artikel=f"ART-{i:04d}", bezeichnung=f"Teil {i}", profil_id=profil,
                 werkstoff_id=WERKSTOFFE[(i // 5) % len(WERKSTOFFE)], laenge=laenge,
                 stueck=rnd.choice([1, 2, 4, 6, 8, 10, 12, 20, 40]),
                 schneidweg=round(rnd.uniform(250, 1200), 1), einstiche=rnd.randint(2, 10))
        if i % 6 == 5:
            p["b_gerade"] = "nein"
        if i % 10 == 3:
            p["zusatz"] = json.dumps([ZUSATZ[i % 3]])
        if i % 15 == 7:
            p["satz"], p["je_satz"] = f"Satz {i // 15}", 2
        if i % 4 == 1:
            p["_konturen"] = _konturen(rnd, laenge, profil.startswith("RR"))
        out.append(p)
    return out


def anlegen(db, groesse, seed=1, staffeln=True, maschine="T11"):
    """Testangebot der Größe S/M/L/XL anlegen. Ergebnis: Angebots-ID."""
    from rohrlaser import rechnen, schneidweg
    k = db.kontext()
    m = k.maschinen[maschine]
    a = db.angebot_neu(dict(kunde=f"Leistungstest {groesse}", kundennr="K-10045", maschine=maschine, stange=6000))
    for p in positionen(GROESSEN[groesse], seed):
        konturen = p.pop("_konturen", None)
        if konturen:
            pr = dict(k.profile[p["profil_id"]], profil_id=p["profil_id"])
            eing = dict(a=dict(winkel=0.0), b=dict(winkel=0.0), konturen=konturen)
            r = schneidweg.rechnen(eing, pr, rechnen.kontur_regel(m, pr["wand"]))
            if not r["fehler"]:
                p.update(r["felder"], technik=json.dumps(dict(eing, quelle=schneidweg.QUELLE)))
        db.position_neu(a, p)
    if staffeln:
        for schl, menge in (("10", 24), ("10", 50), ("10", 100), ("20", 10), ("20", 40), ("20", 100)):
            db.staffel_neu(a, dict(schluessel=schl, menge=menge))
    return a
