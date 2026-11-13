"""Zwölf Referenzaufträge (Plan X7, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“): Material, Zeiten und Preis
werden hier von Hand nachgerechnet, nicht mit den Funktionen des Programms.

Fälle (Master-Prompt Abschnitt 14):
  1 Rundrohr mit einfachen Bohrungen            7 mehrere Teile auf einer Stange
  2 Vierkantrohr mit mehreren Ausschnitten      8 gemeinsamer Schnitt zwischen zwei Teilen
  3 Rechteckrohr mit Langlöchern                9 Reststücke (Regel: kein Restelager, nur gemeldet)
  4 Rohr mit Schrägschnitten                   10 unterschiedliche Wandstärken (Schneiddaten interpoliert)
  5 Rohr mit Gewinden und Senkungen            11 unterschiedliche Losgrößen (1, 10, 100)
  6 Rohr mit Markierung                        12 Fremdleistung (Feuerverzinken mit Mindestbetrag)
dazu Grenzfälle: Teil länger als die Stange, fehlende Schneiddaten (Hinweis statt 0 €), Wand über der Tabelle.

Der Weg ist der des Programms: Datenbank mit Beispiel-Stammdaten, Konturen über den Schneidweg-Rechner, Angebot
optimieren, Ergebnis speichern und kalkulieren. Die Stammdaten werden vorher auf feste TESTWERTE gesetzt. Das sind
Testwerte, keine Maschinenwerte. Nachgerechnet wird je Fall:
  - Geometrie: Schnittlänge je Kontur und Ende (π × d, Langloch, Rechteck mit Radius, Rohrumfang mit Eckradius,
    Gehrung als Ellipse bzw. gestreckte Seiten) und die Konturklassen klein/mittel/groß
  - Stangen, gemeinsame Schnitte, Rest je Stange
  - Laserzeit je Teil = Schneiden je Klasse + Einstiche × (Einstechzeit + Anfahren) + Ecken + Nebenzeit
    − Einsparung gemeinsamer Schnitte
  - Kostenarten: Material, Laser, Gewinde, Rüsten, Stangenwechsel, Zusatzarbeiten, Programmierung, Gewinn,
    Verkaufspreis je Angebot und je Teil

Aufruf: python tests/test_referenz_kalkulation.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import bearbeitung, rechnen, schneidweg, zeitbild  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TOL = 1e-6
TOL_RUND = 1e-6         # Schneidweg und Konturklassen speichert das Programm auf 0,1 mm gerundet

# ------------------------------------------------------------------ Testwerte (keine echten Maschinenwerte)
MASCHINE = "T11"
SATZ = 150.0                    # €/h Maschine
RUEST_MIN = 5.0                 # Rüsten Maschine je Angebot [min]
WECHSEL_S = 24.0                # Stangenwechsel je Stange [s]
ANFAHREN_S = 0.5                # Anfahren/Drehen je Einstich [s]
NEBEN_S = 2.0                   # Nebenzeit je Teil [s]
ENDE, GREIF, KERF, ABSTAND = 10.0, 142.0, 0.2, 5.0
KLEIN_BIS, MITTEL_BIS, KLEIN_WAND, MITTEL_WAND = 10.0, 50.0, 3.0, 8.0
RUEST_ABM_MIN = 15.0            # Rüsten je Abmessung [min], Satz der Maschine
PROG_GRUND, PROG_KONTUR, PROG_SATZ = 5.0, 0.5, 60.0     # min je Position, min je Innenkontur, €/h
GEWINN = 0.20
ZUSCHLAG_FREMD = 0.10
STANGE = 6000.0
S235, VA = "S235-10219", "1.4301"
# Schneiddaten je Werkstoff: Wand bis [mm], Vorschub groß/mittel/klein [mm/min], Einstechzeit [s], Zeit je Ecke [s]
SCHNEIDDATEN = {S235: ((2.0, 6000.0, 3600.0, 1800.0, 0.2, 0.3), (3.0, 5000.0, 3000.0, 1500.0, 0.3, 0.35),
                       (4.0, 4000.0, 2400.0, 1200.0, 0.4, 0.4)),
                VA: ((2.0, 5000.0, 3000.0, 1500.0, 0.25, 0.3),)}
GRAVUR_V = 3000.0               # Vorschub Gravur [mm/min]
DICHTE = {S235: 7.85, VA: 7.9}  # kg/dm³
# Profile mit festem Eckradius (r = 0 bei Rundrohr): Profil-ID -> (Form, a, b, Wand, r)
PROFILE = {"RR 42,4x2,0": ("Rundrohr", 42.4, None, 2.0, None), "QR 40x40x3": ("Quadratrohr", 40.0, None, 3.0, 6.0),
           "RE 60x40x3": ("Rechteckrohr", 60.0, 40.0, 3.0, 6.0), "QR 40x40x2": ("Quadratrohr", 40.0, None, 2.0, 4.0),
           "QR 40x40x2,6": ("Quadratrohr", 40.0, None, 2.6, 5.2), "QR 40x40x5": ("Quadratrohr", 40.0, None, 5.0, 10.0)}
# Materialpreise: (Profil, Werkstoff) -> (Basis, Preis)
PREISE = {("RR 42,4x2,0", S235): ("€/kg", 1.50), ("RR 42,4x2,0", VA): ("€/kg", 4.80),
          ("QR 40x40x3", S235): ("€/m", 4.00), ("RE 60x40x3", S235): ("€/m", 5.20),
          ("QR 40x40x2", S235): ("€/m", 3.00), ("QR 40x40x2,6", S235): ("€/m", 3.60),
          ("QR 40x40x5", S235): ("€/m", 6.50)}
GEWINDE_PREIS = {"M8": 1.10, "M10": 1.30}        # wie die Beispiel-Stammdaten (€ je Gewinde)
SENKEN, ENTGRATEN, VERZINKEN, VERZINKEN_MIN = 0.40, 0.50, 0.65, 120.0     # Beispiel-Zusatzarbeiten


def ok(text):
    print("OK    ", text)


def nahe(a, b, text, tol=TOL):
    assert abs(float(a) - float(b)) <= tol * max(1.0, abs(a), abs(b)), f"{text}: Programm {a}, von Hand {b}"


# ------------------------------------------------------------------ Datenbank mit Testwerten
def datenbank():
    db = Datenbank(Path(tempfile.mkdtemp()) / "referenz.db")
    for n, w in dict(gewinn=GEWINN, zuschlag_material=0.0, zuschlag_fertigung=0.0,
                     zuschlag_fremdleistung=ZUSCHLAG_FREMD, ruesten_abmessung=RUEST_ABM_MIN,
                     programmierung_zeit=PROG_GRUND, programmierung_kontur=PROG_KONTUR, angebotsaufschlag=0.0,
                     mindestpreis=0.0, haendler_mehr_kurz=0, haendler_mehr_lang=0, ausschuss=0.0, gas_rechnen="nein",
                     laenge_vergleich="nein", skonto=0.0, pauschale_abmessung=0.0).items():
        db.einstellung_setzen(n, w)
    m = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == MASCHINE)
    for n, w in dict(stundensatz=SATZ, ruestzeit=RUEST_MIN, stangenwechsel=WECHSEL_S, stangenwechsel_sn=WECHSEL_S,
                     zeit_kontur=ANFAHREN_S, zeit_teil=NEBEN_S, endbeschnitt=ENDE, greiferrest=GREIF,
                     schnittverlust=KERF, abstand=ABSTAND, kontur_klein=KLEIN_BIS, kontur_mittel=MITTEL_BIS,
                     kontur_klein_wand=KLEIN_WAND, kontur_mittel_wand=MITTEL_WAND, max_stange=6500).items():
        db.aendern("maschinen", m["id"], n, w)
    for z in db.zeilen("stundensaetze"):
        if z["satz_id"] == "Programmierung":
            db.aendern("stundensaetze", z["id"], "satz", PROG_SATZ)
    # nur die Testwerte gelten: Beispiel-Schneiddaten der Maschine (Kategorien) entfernen
    db.loeschen("schneiddaten", [z["id"] for z in db.zeilen("schneiddaten") if z["maschinen_id"] == MASCHINE])
    for werkstoff, zeilen in SCHNEIDDATEN.items():
        for wand, g, mi, kl, ein, ecke in zeilen:
            db.neu("schneiddaten", dict(maschinen_id=MASCHINE, werkstoff_id=werkstoff, gas="N₂", wand_bis=wand,
                                        vorschub_gross=g, vorschub_mittel=mi, vorschub_klein=kl, einstechzeit=ein,
                                        zeit_ecke=ecke, vorschub_gravur=GRAVUR_V, bemerkung="Testwert"))
    vorhanden = {z["profil_id"]: z for z in db.zeilen("profile")}
    for pid, (form, a, b, wand, r) in PROFILE.items():
        werte = dict(form=form, a=a, b=b, wand=wand, r_aussen=r, endbeschnitt=None, greiferrest=None,
                     flaeche_manuell=None)
        if pid in vorhanden:
            for n, w in werte.items():
                db.aendern("profile", vorhanden[pid]["id"], n, w)
        else:
            db.neu("profile", dict(werte, profil_id=pid, bemerkung="Testwert"))
    preise = {(z["profil_id"], z["werkstoff_id"]): z for z in db.zeilen("preise")}
    for (pid, wid), (basis, preis) in PREISE.items():
        if (pid, wid) in preise:
            for n, w in dict(basis=basis, preis=preis, lieferlaenge=6000).items():
                db.aendern("preise", preise[(pid, wid)]["id"], n, w)
        else:
            db.neu("preise", dict(profil_id=pid, werkstoff_id=wid, basis=basis, preis=preis, lieferlaenge=6000,
                                  gueltig_ab="2026-01-01", bemerkung="Testwert"))
    return db


# ------------------------------------------------------------------ Geometrie von Hand
def ellipse(a, b):
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def umfang(pid):
    form, a, b, _, r = PROFILE[pid]
    if form == "Rundrohr":
        return math.pi * a
    return 2 * (a + (b or a)) - (8 - 2 * math.pi) * r


def ende_mm(pid, winkel=0.0):
    """Schnittlänge eines Endes: gerade = Umfang; Gehrung über Höhe: Rundrohr Ellipse r, r / cos α; Vierkant- und
    Rechteckrohr die geraden Stücke über Höhe / cos α, über Breite unverändert, die vier Eckbögen als Ellipse."""
    form, a, b, _, r = PROFILE[pid]
    if not winkel:
        return umfang(pid)
    c = math.cos(math.radians(winkel))
    if form == "Rundrohr":
        return ellipse(a / 2, a / 2 / c)
    return 2 * (a - 2 * r) / c + 2 * ((b or a) - 2 * r) + ellipse(r, r / c)


def bohrung_rundrohr(d, D, wand, n=4000):
    """Bohrung Ø d im Rundrohr Ø D, 2D-Schnitt (Strahl zur Rohrmitte): innen hat das Loch Ø d, auf der Außenhaut
    liegt jeder Punkt der Innenkante auf demselben Umfangswinkel. Umriss außen (Bogen am Umfang R × asin(x / Ri),
    längs y) als Vieleck mit n Punkten, Länge = Summe der Sehnen."""
    r, R = d / 2, D / 2
    ri = R - wand
    pkt = [(R * math.asin(r * math.cos(2 * math.pi * i / n) / ri), r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    return sum(math.dist(a, b) for a, b in zip(pkt, pkt[1:] + pkt[:1]))


def kontur_mm(k, pid):
    art = k["art"]
    if art in ("Bohrung", "Senkung"):
        form, a = PROFILE[pid][:2]
        return bohrung_rundrohr(k["d"], a, PROFILE[pid][3]) if form == "Rundrohr" else math.pi * k["d"]
    if art == "Langloch":
        return 2 * (k["l"] - k["b"]) + math.pi * k["b"]
    if art == "Rechteck":
        return 2 * (k["b"] + k["h"]) - 8 * k["r"] + 2 * math.pi * k["r"]
    raise ValueError(art)


def huelle(k):
    return {"Bohrung": lambda: k["d"], "Senkung": lambda: k["d"], "Langloch": lambda: k["l"],
            "Rechteck": lambda: max(k["b"], k["h"])}[k["art"]]()


def klasse(h, wand):
    """0 klein, 1 mittel, 2 groß: mm-Grenze und Vielfaches der Wand, die strengere gilt."""
    c = 0 if h <= KLEIN_BIS else 1 if h <= MITTEL_BIS else 2
    return min(c, 0 if h <= KLEIN_WAND * wand else 1 if h <= MITTEL_WAND * wand else 2)


def hand_teil(pid, werkstoff, konturen=(), a=0.0, b=0.0, gravur=0.0):
    """Erwartete Werte eines Teils: Schneidweg, Einstiche, mm je Klasse, Innenkonturen, Laserzeit brutto [s]."""
    form, pa, pb, wand, _ = PROFILE[pid]
    mm = [0.0, 0.0, 0.0]
    hk_ende = max(pa, pb or 0)
    for w in (a, b):
        mm[klasse(hk_ende, wand)] += ende_mm(pid, w)
    n_innen = 0
    for k in konturen:
        mm[klasse(huelle(k), wand)] += k.get("anzahl", 1) * kontur_mm(k, pid)
        n_innen += k.get("anzahl", 1)
    einstiche = 2 + n_innen
    zeile = sd(werkstoff, wand)
    g, mi, kl, ein, ecke = zeile
    ecken = 0 if form == "Rundrohr" else 4
    # das Programm speichert Schneidweg und Konturklassen auf 0,1 mm; groß = Schneidweg − klein − mittel
    kl_r, mi_r = round(mm[0], 1), round(mm[1], 1)
    gr_r = max(0.0, round(sum(mm), 1) - kl_r - mi_r)
    zeit = (60 * gr_r / g + 60 * mi_r / mi + 60 * kl_r / kl + 60 * gravur / GRAVUR_V
            + einstiche * (ein + ANFAHREN_S) + 2 * ecken * ecke + NEBEN_S)
    # gespart je gemeinsamem Schnitt; die Endlänge steht auf 0,1 mm gerundet in der Konturliste der Position
    je_ende = 60 * round(ende_mm(pid), 1) / (g, mi, kl)[2 - klasse(hk_ende, wand)] + ein + ANFAHREN_S + ecken * ecke
    return dict(schneidweg=sum(mm), einstiche=einstiche, klein=mm[0], mittel=mm[1], gross=mm[2], innen=n_innen,
                zeit=zeit, je_ende=je_ende, einstechzeit=ein)


def sd(werkstoff, wand):
    """Schneiddaten von Hand: Stufe 'Wand bis' ≥ Wand, zwischen zwei Stufen linear (Vorgabe des Programms)."""
    zeilen = sorted(SCHNEIDDATEN[werkstoff])
    oben = next(z for z in zeilen if z[0] >= wand - 1e-9)
    unten = [z for z in zeilen if z[0] < wand - 1e-9]
    if oben[0] == wand or not unten:
        return oben[1:]
    u = unten[-1]
    t = (wand - u[0]) / (oben[0] - u[0])
    return tuple(x + t * (y - x) for x, y in zip(u[1:], oben[1:]))


def stangenpreis(pid, werkstoff, laenge=STANGE):
    basis, preis = PREISE[(pid, werkstoff)]
    if basis == "€/m":
        return preis * laenge / 1000
    form, a, b, wand, _ = PROFILE[pid]
    assert form == "Rundrohr"
    flaeche = math.pi / 4 * (a ** 2 - (a - 2 * wand) ** 2)          # mm²
    return flaeche * laenge / 1e6 * DICHTE[werkstoff] * preis


def teilgewicht(pid, werkstoff, laenge):
    form, a, b, wand, _ = PROFILE[pid]
    flaeche = math.pi / 4 * (a ** 2 - (a - 2 * wand) ** 2)
    return flaeche * laenge / 1e6 * DICHTE[werkstoff]


def stangen_von_hand(laengen, gerade=True):
    """Teile (absteigend, alle Enden gerade) auf Stangen: nutzbar bis Stange − Greiferrest, ab Endbeschnitt;
    zwei gerade Enden teilen einen Schnitt (1 × Schnittverlust), letzter Schnitt 1 × Schnittverlust. First Fit
    Decreasing reicht für diese Fälle und ist hier gleich der Untergrenze."""
    frei = []
    for lg in sorted(laengen, reverse=True):
        for s in frei:
            luecke = KERF if gerade else 2 * KERF + ABSTAND
            if s["pos"] + luecke + lg + KERF <= STANGE - GREIF + 1e-9:
                s["pos"] += luecke + lg
                s["n"] += 1
                break
        else:
            frei.append(dict(pos=ENDE + lg, n=1))
    return frei


# ------------------------------------------------------------------ Angebot über den Weg des Programms
KONTEXT = []        # Kopf, Kontext und Tabellen des zuletzt gerechneten Angebots (Bearbeitungsliste X1)


def angebot(db, positionen, nummer):
    """positionen: [dict(pos, profil, werkstoff, laenge, stueck, eingaben (Schneidweg-Rechner), extra)]."""
    k = db.kontext()
    m = k.maschinen[MASCHINE]
    a = db.angebot_neu(dict(nummer=nummer, kunde="Referenz", maschine=MASCHINE, stange=STANGE))
    for n, w in (("skonto", 0), ("fracht_modus", "keine Fracht")):
        db.angebot_aendern(a, n, w)
    for p in positionen:
        pr = dict(k.profile[p["profil"]], profil_id=p["profil"])
        werte = dict(pos=p["pos"], artikel=f"REF-{nummer}-{p['pos']}", profil_id=p["profil"],
                     werkstoff_id=p["werkstoff"], laenge=p["laenge"], stueck=p["stueck"])
        if p.get("eingaben") is not None:
            r = schneidweg.rechnen(p["eingaben"], pr, rechnen.kontur_regel(m, pr["wand"]))
            assert not r["fehler"], r["fehler"]
            werte.update(r["felder"], technik=json.dumps(dict(p["eingaben"], quelle=schneidweg.QUELLE)))
        werte.update(p.get("extra") or {})
        db.position_neu(a, werte)
    kopf, pos = db.angebot(a), db.positionen(a)
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    db.ergebnis_speichern(a, erg)
    kopf = db.angebot(a)
    e = rechnen.einstellungen_angebot(kopf, einst)
    zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
    KONTEXT[:] = [kopf, k, tab]
    return pos, kopf["ergebnis"], zeilen, summen


def eingaben(konturen=(), a=0.0, b=0.0, gravur=None):
    e = dict(a=dict(winkel=a), b=dict(winkel=b), konturen=[dict(x) for x in konturen])
    if gravur:
        e["konturen"].append(dict(art="Gravur", anzahl=1, laenge=gravur))
    return e


def gemeinsame(erg):
    return sum(1 for s in erg["stangen"] for t in s["teile"] if t["trennung"] == "gemeinsamer Schnitt")


def preis_pruefen(name, positionen, erg, zeilen, summen, hand, abmessungen, zusatz=0.0, zusatz_fremd=0.0,
                  gewinde=0.0):
    """Kostenarten des Angebots von Hand: hand = je Position dict(zeit netto je Teil [s], innen)."""
    n_stangen = len(erg["stangen"])
    laser = sum(h["netto"] * p["stueck"] for h, p in zip(hand, positionen)) / 3600 * SATZ
    nahe(summen["laser_schneiden"], laser, f"{name}: Laser schneiden", TOL_RUND)
    material = 0.0
    gruppen = {}
    for s in erg["stangen"]:
        gruppen.setdefault((s["profil"], s["werkstoff"]), []).append(s)
        material += stangenpreis(s["profil"], s["werkstoff"], s["stange"])
    nahe(summen["material"], material, f"{name}: Material")
    nahe(summen["ruesten_maschine"], RUEST_MIN / 60 * SATZ, f"{name}: Rüsten Maschine")
    nahe(summen["ruesten_abmessungen"], abmessungen * RUEST_ABM_MIN / 60 * SATZ, f"{name}: Rüsten je Abmessung")
    nahe(summen["stangenwechsel_kosten"], n_stangen * WECHSEL_S / 3600 * SATZ, f"{name}: Stangenwechsel")
    prog = sum((PROG_GRUND + PROG_KONTUR * h["innen"]) / 60 * PROG_SATZ for h in hand)
    nahe(summen["programmierung"], prog, f"{name}: Programmierung")
    nahe(summen["gewinde"], gewinde, f"{name}: Gewinde")
    nahe(summen["zusatz"], zusatz + zusatz_fremd, f"{name}: Zusatzarbeiten")
    herstell = (material + laser + gewinde + RUEST_MIN / 60 * SATZ + abmessungen * RUEST_ABM_MIN / 60 * SATZ
                + n_stangen * WECHSEL_S / 3600 * SATZ + zusatz + zusatz_fremd * (1 + ZUSCHLAG_FREMD))
    nahe(summen["herstell"], herstell, f"{name}: Herstellkosten", TOL_RUND)
    selbst = herstell + prog
    nahe(summen["selbst"], selbst, f"{name}: Selbstkosten", TOL_RUND)
    nahe(summen["verkauf"], selbst * (1 + GEWINN), f"{name}: Verkaufspreis", TOL_RUND)
    nahe(sum(z["preis_teil"] * z["stueck"] for z in zeilen if z), summen["verkauf"], f"{name}: Summe der Positionen")
    # Zeitbild in 7 Zeitarten (Plan X2): Rüsten als Zeit je Teil, Summe über die Teile = Rüstzeit von Hand
    zb_r = [(zeitbild.zeitbild(z), p["stueck"]) for z, p in zip(zeilen, positionen)]
    nahe(sum(b["s"]["ruesten"] * c for b, c in zb_r),
         RUEST_MIN * 60 + abmessungen * RUEST_ABM_MIN * 60 + n_stangen * WECHSEL_S, f"{name}: Zeitbild Rüsten [s]")
    nahe(sum(b["belegung"] * c for b, c in zb_r),
         sum(h["netto"] * p["stueck"] for h, p in zip(hand, positionen)) + RUEST_MIN * 60
         + abmessungen * RUEST_ABM_MIN * 60 + n_stangen * WECHSEL_S, f"{name}: Zeitbild Maschinenbelegung [s]", TOL_RUND)
    for z, p in zip(zeilen, positionen):       # nur Arbeitsablauf-Hinweis erlaubt, kein Rechenfehler
        assert z["hinweis"] in ("", "Bohrungen ungeprüft"), f"{name} Pos. {p['pos']}: {z['hinweis']}"
    return dict(stangen=n_stangen, material=material, laser=laser, verkauf=summen["verkauf"])


def geometrie_pruefen(name, p, h):
    nahe(p["schneidweg"], h["schneidweg"], f"{name}: Schneidweg", tol=0.06 / max(1.0, h["schneidweg"]))
    assert p["einstiche"] == h["einstiche"], f"{name}: Einstiche {p['einstiche']}, von Hand {h['einstiche']}"
    for n in ("klein", "mittel"):
        nahe(p[f"{n}_mm"], h[n], f"{name}: Konturen {n}", tol=0.06 / max(1.0, h[n]))


def zeit_netto(h, eingespart_enden, stueck):
    return h["zeit"] - eingespart_enden * h["je_ende"] / stueck


# ------------------------------------------------------------------ die zwölf Fälle
def fall(db, nr, name, teile, pruef=None, nummer=None):
    """Ein Angebot mit den Teilen rechnen und vollständig von Hand nachprüfen. teile: [dict(profil, werkstoff,
    laenge, stueck, konturen, a, b, gravur, extra)]. Ergebnis dict mit Kennzahlen."""
    pos, hand = [], []
    for i, t in enumerate(teile):
        pos.append(dict(pos=10 * (i + 1), profil=t["profil"], werkstoff=t.get("werkstoff", S235), laenge=t["laenge"],
                        stueck=t["stueck"], eingaben=eingaben(t.get("konturen", ()), t.get("a", 0.0),
                                                              t.get("b", 0.0), t.get("gravur")),
                        extra=t.get("extra")))
        hand.append(hand_teil(t["profil"], t.get("werkstoff", S235), t.get("konturen", ()), t.get("a", 0.0),
                              t.get("b", 0.0), t.get("gravur") or 0.0))
    positionen, erg, zeilen, summen = angebot(db, pos, nummer or f"REF-{nr:02d}")
    for p, h in zip(positionen, hand):
        geometrie_pruefen(f"Fall {nr} Pos. {p['pos']}", p, h)
    # gemeinsame Schnitte je Position (beide anliegenden Enden sparen je einen Schnitt, gezählt am folgenden Teil)
    gespart = {}
    for s in erg["stangen"]:
        for t in s["teile"]:
            if t["trennung"] == "gemeinsamer Schnitt":
                gespart[t["index"]] = gespart.get(t["index"], 0) + 1
    for i, (p, h) in enumerate(zip(positionen, hand)):
        h["netto"] = zeit_netto(h, gespart.get(i, 0), p["stueck"])
        nahe(zeilen[i]["laser_brutto"], h["zeit"], f"Fall {nr} Pos. {p['pos']}: Laserzeit brutto je Teil",
             TOL_RUND)
        nahe(zeilen[i]["laser_netto"], h["netto"], f"Fall {nr} Pos. {p['pos']}: Laserzeit netto je Teil",
             TOL_RUND)
        # Zeitbild (X2): Einstich = Einstiche × Einstechzeit, Positionieren = Einstiche × Anfahren, Nebenzeit je Teil
        b = zeitbild.zeitbild(zeilen[i])
        nahe(b["s"]["einstich"], h["einstiche"] * h["einstechzeit"], f"Fall {nr} Pos. {p['pos']}: Zeitbild Einstich")
        nahe(b["s"]["positionieren"], h["einstiche"] * ANFAHREN_S, f"Fall {nr} Pos. {p['pos']}: Zeitbild Positionieren")
        nahe(b["s"]["neben"], NEBEN_S, f"Fall {nr} Pos. {p['pos']}: Zeitbild Nebenzeit")
        nahe(sum(b["s"][a] for a in ("laser", "einstich", "positionieren", "bewegung", "neben")), h["netto"],
             f"Fall {nr} Pos. {p['pos']}: Zeitbild 1–5 = Laserzeit netto", TOL_RUND)
        # Bearbeitungsliste (X1): Summe der Zeilen = Laserzeit netto, Kosten = Laser schneiden je Teil; jede
        # Innenkontur = 60 × Länge / Vorschub ihrer Klasse + Einstiche × (Einstechzeit + Anfahren)
        bl = bearbeitung.fuer_position(p, zeilen[i], *KONTEXT)
        zeit_bl, eur_bl = bearbeitung.summe(bl)
        nahe(zeit_bl, h["netto"], f"Fall {nr} Pos. {p['pos']}: Bearbeitungsliste Σ Zeit = Laserzeit netto", 0.01)
        nahe(eur_bl, zeilen[i]["laser_schneiden_teil"], f"Fall {nr} Pos. {p['pos']}: Bearbeitungsliste Σ Kosten", 1e-4)
        g, mi, kl, ein, _ = sd(p["werkstoff_id"], PROFILE[p["profil_id"]][3])
        for x in (x for x in bl if x["gruppe"] == "Kontur" and x["laenge"]):
            v_ = dict(klein=kl, mittel=mi)[x["klasse"]] if x["klasse"] != "groß" else g
            nahe(x["s"], 60 * x["laenge"] / v_ + x["einstiche"] * (ein + ANFAHREN_S),
                 f"Fall {nr} Pos. {p['pos']}: Zeile {x['text'][:30]}")
    abm = len({(t["profil"], t.get("werkstoff", S235)) for t in teile})
    extra = (pruef or (lambda *_: {}))(positionen, erg, zeilen, summen, hand) or {}
    k = preis_pruefen(f"Fall {nr} {name}", positionen, erg, zeilen, summen, hand, abm, **extra)
    ok(f"Fall {nr:2d} {name}: {k['stangen']} Stangen, Material {k['material']:.2f} €, Laser {k['laser']:.2f} €, "
       f"Verkauf {k['verkauf']:.2f} €")
    return dict(k, erg=erg, zeilen=zeilen, summen=summen, positionen=positionen, hand=hand)


def stangen_pruefen(nr, erg, laengen, gerade=True):
    hand = stangen_von_hand(laengen, gerade)
    assert len(erg["stangen"]) == len(hand), f"Fall {nr}: {len(erg['stangen'])} Stangen, von Hand {len(hand)}"
    for s in erg["stangen"]:
        belegt = max(t["bis"] for t in s["teile"]) + KERF
        assert belegt <= s["stange"] - GREIF + 1e-9, f"Fall {nr}: Stange {s['nr']} überlastet"
    return hand


def main():
    db = datenbank()
    rr, qr, re_ = "RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3"
    bohr = lambda d, n: dict(art="Bohrung", d=d, anzahl=n)       # noqa: E731

    # 1 Rundrohr mit einfachen Bohrungen: Ø 8,5 (klein, ≤ 3 × Wand? 8,5 > 6 → nach mm klein), Ø 12 (mittel)
    f1 = fall(db, 1, "Rundrohr mit Bohrungen", [dict(profil=rr, laenge=800, stueck=20,
                                                     konturen=[bohr(8.5, 2), bohr(12, 2)])])
    stangen_pruefen(1, f1["erg"], [800] * 20)

    # 2 Vierkantrohr mit mehreren Ausschnitten (Rechtecke mit Eckradius, eins groß über 50 mm)
    fall(db, 2, "Vierkant mit Ausschnitten", [dict(profil=qr, laenge=1200, stueck=8, konturen=[
        dict(art="Rechteck", b=20, h=15, r=2, anzahl=2), dict(art="Rechteck", b=30, h=30, r=3, anzahl=1),
        dict(art="Rechteck", b=60, h=25, r=2, anzahl=1)])])

    # 3 Rechteckrohr mit Langlöchern (30 × 10 mittel, 8 × 4 klein)
    fall(db, 3, "Rechteck mit Langlöchern", [dict(profil=re_, laenge=950, stueck=12, konturen=[
        dict(art="Langloch", l=30, b=10, anzahl=4), dict(art="Langloch", l=8, b=4, anzahl=2)])])

    # 4 Schrägschnitte: Rundrohr 30°/45°, Vierkant 15° über Höhe; Gehrungen teilen keinen Schnitt
    def kein_gemeinsamer(positionen, erg, *_):
        assert gemeinsame(erg) == 0, "Fall 4: Gehrung darf keinen gemeinsamen Schnitt haben"
    fall(db, 4, "Schrägschnitte", [dict(profil=rr, laenge=640, stueck=10, a=30.0, b=45.0),
                                   dict(profil=qr, laenge=500, stueck=6, a=15.0, b=15.0)], kein_gemeinsamer)

    # 5 Gewinde und Senkungen: Gewinde und Senken nur € je Stück (Regel), Laser schneidet die Kernlöcher
    def gewinde_senken(positionen, erg, zeilen, summen, hand):
        g = sum(p["stueck"] * (4 * GEWINDE_PREIS["M8"] + 2 * GEWINDE_PREIS["M10"]) for p in positionen)
        s = sum(p["stueck"] * 2 * SENKEN for p in positionen)
        assert all(z["gewinde_zeit_teil"] == 0 for z in zeilen if z), "Gewinde ohne Zeit"
        return dict(gewinde=g, zusatz=s)
    fall(db, 5, "Gewinde und Senkungen", [dict(
        profil=qr, laenge=700, stueck=10, konturen=[bohr(6.8, 4), bohr(8.5, 2), dict(art="Senkung", d=6.6, D=12,
                                                                                    anzahl=2)],
        extra=dict(gewinde="4xM8; 2xM10", zusatz=json.dumps([dict(name="Senken", menge=2)])))], gewinde_senken)

    # 6 Markierung: Gravur 120 mm mit Vorschub Gravur, kein Schneidweg
    fall(db, 6, "Markierung", [dict(profil=re_, laenge=1500, stueck=5, konturen=[bohr(10, 2)], gravur=120.0)])

    # 7 mehrere Teile auf einer Stange: drei Längen derselben Abmessung gemeinsam optimiert
    lg7 = [1800] * 4 + [1150] * 6 + [430] * 9
    f7 = fall(db, 7, "Mehrere Teile je Stange", [dict(profil=qr, laenge=1800, stueck=4),
                                                 dict(profil=qr, laenge=1150, stueck=6),
                                                 dict(profil=qr, laenge=430, stueck=9)])
    stangen_pruefen(7, f7["erg"], lg7)

    # 8 gemeinsamer Schnitt: zwei gerade Enden teilen einen Schnitt, je Schnitt eine Endlänge + Einstich gespart
    f8 = fall(db, 8, "Gemeinsamer Schnitt", [dict(profil=qr, laenge=2000, stueck=2)])
    assert gemeinsame(f8["erg"]) == 1, f"Fall 8: {gemeinsame(f8['erg'])} gemeinsame Schnitte, richtig 1"
    h = f8["hand"][0]
    nahe(f8["summen"]["laser_schneiden"], (2 * h["zeit"] - h["je_ende"]) / 3600 * SATZ, "Fall 8: ein Ende gespart", TOL_RUND)

    # 9 Reststücke: kein Restelager (Regel), der Rest wird nur gemeldet; Rest je Stange von Hand
    f9 = fall(db, 9, "Reststück gemeldet", [dict(profil=qr, laenge=2500, stueck=3)])
    hand9 = stangen_pruefen(9, f9["erg"], [2500] * 3)
    reste = sorted(round(STANGE - GREIF - (s["pos"] + KERF), 6) for s in hand9)
    prog = sorted(round(s["stange"] - GREIF - (max(t["bis"] for t in s["teile"]) + KERF), 6)
                  for s in f9["erg"]["stangen"])
    assert reste == prog, f"Fall 9: Reste {prog}, von Hand {reste}"
    ok(f"Fall  9 Rest je Stange {', '.join(f'{r:.1f}' for r in reste)} mm, nichts eingelagert")

    # 10 unterschiedliche Wandstärken: 2 / 2,6 (zwischen den Stufen interpoliert) / 5 mm (über der Tabelle)
    fall(db, 10, "Wandstärken 2 und 2,6 mm", [dict(profil="QR 40x40x2", laenge=900, stueck=6, konturen=[bohr(9, 2)]),
                                              dict(profil="QR 40x40x2,6", laenge=900, stueck=6,
                                                   konturen=[bohr(9, 2)])])
    pos, erg, zeilen, summen = angebot(db, [dict(pos=10, profil="QR 40x40x5", werkstoff=S235, laenge=900, stueck=6,
                                                 eingaben=eingaben([bohr(9, 2)]))], "REF-10B")
    assert zeilen[0]["hinweis"] == "keine Schneiddaten" and zeilen[0]["laser_netto"] is None, zeilen[0]["hinweis"]
    ok("Fall 10 Wand 5 mm über der Tabelle: Hinweis 'keine Schneiddaten', keine Laserzeit als 0 € ausgegeben")

    # 11 Losgrößen 1 / 10 / 100: Rüsten und Programmierung verteilen sich, Stückpreis fällt
    stueck_preise = []
    for n in (1, 10, 100):
        f = fall(db, 11, f"Losgröße {n}", [dict(profil=qr, laenge=600, stueck=n, konturen=[bohr(12, 2)])],
                 nummer=f"REF-11-{n}")
        stueck_preise.append(f["verkauf"] / n)
    assert stueck_preise[0] > stueck_preise[1] > stueck_preise[2], stueck_preise
    ok("Fall 11 Stückpreis fällt mit der Losgröße: " + " > ".join(f"{p:.2f} €" for p in stueck_preise))

    # 12 Fremdleistung: Feuerverzinken €/kg, unter dem Mindestbetrag auf den Mindestbetrag angehoben, + Zuschlag
    def verzinken(positionen, erg, zeilen, summen, hand):
        betrag = sum(teilgewicht(p["profil_id"], p["werkstoff_id"], p["laenge"]) * VERZINKEN * p["stueck"]
                     for p in positionen)
        assert betrag < VERZINKEN_MIN, betrag
        return dict(zusatz_fremd=VERZINKEN_MIN)
    fall(db, 12, "Fremdleistung Verzinken", [dict(profil=rr, laenge=1000, stueck=10,
                                                  extra=dict(zusatz=json.dumps([dict(name="Feuerverzinken")])))],
         verzinken)

    # Grenzfall: Teil länger als die Stange wird nicht eingeplant und nicht still mit 0 € gerechnet
    pos, erg, zeilen, summen = angebot(db, [dict(pos=10, profil=qr, werkstoff=S235, laenge=6200, stueck=1,
                                                 eingaben=eingaben())], "REF-GR")
    # ohne jede Stange im Angebot meldet die Zeile 'kein Schnittplan oder Preis', mit Stangen 'nicht vollständig
    # eingeplant'; beides ist ein sichtbarer Hinweis statt eines stillen 0-€-Preises
    assert erg["fehler"] and erg["fehler"][0]["anzahl"] == 1, erg["fehler"]
    assert zeilen[0]["hinweis"] in ("nicht vollständig eingeplant", "kein Schnittplan oder Preis"), zeilen[0]["hinweis"]
    ok(f"Grenzfall Teil 6.200 mm > nutzbare Stange: nicht eingeplant, Hinweis '{zeilen[0]['hinweis']}'")
    db.schliessen()
    print("Alle Referenzaufträge stimmen.")


if __name__ == "__main__":
    main()
