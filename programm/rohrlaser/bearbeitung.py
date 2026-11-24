"""Bearbeitungsliste je Position (Plan X1–X8, Paket X1, Patrick 12.11.2026, Freigabe „Alle Empfehlungen“).

Jede Bearbeitung eines Rohrteils als eigene Zeile mit Maschinenzeit und Kosten: Anfangs- und Endschnitt, jede
Innenkontur (Bohrung, Langloch, Ausschnitt, Schlitz, Kontur …) und die Zeiten, die keiner einzelnen Kontur gehören
(Gravur, Ecken, 3D-Mehrzeit, Nebenzeit, Drehen, Messen …). Gerechnet wird mit denselben Vorschüben und Zeiten wie
die Laserzeit (rechnen._schneidzeit_teile), es entsteht keine neue Zeit:

    Zeit einer Kontur = 60 × Schnittlänge / Vorschub ihrer Klasse + Einstiche × Einstechzeit
                        + Einstiche × Zeit je Kontur (Anfahren; mit Maschinendynamik unter „Leerwege“)
    Kosten = Zeit / 3600 × Stundensatz Laser schneiden + Schneidgas anteilig (nur Zeit mit Gas)

Die Summe aller Zeilen ist die Laserzeit brutto (bzw. mit Einsparung, Zusatz- und Prüfzeit die Laserzeit netto der
Kalkulation). Was die Konturzeilen nicht genau treffen (Active Tilt, Rand ohne Einstich, gerundete Klassenlängen,
von Hand ergänzter Schneidweg), steht als eigene Zeile „Abgleich“, nie verteilt: keine Doppelzählung. Gewinde,
Senken, Flowdrill und Bohren bleiben €/Stück (Zusatzarbeiten) und stehen hier nicht. Ohne Qt."""
from . import schneidweg as sw

KONTUR, ENDE, REST, ABGLEICH, HAND = "Kontur", "Ende", "ohne Merkmal", "Abgleich", "von Hand"
KLASSEN = {"klein": 0, "mittel": 1, "groß": 2}
KLASSE_NAME = ("klein", "mittel", "groß")
# Zeitanteile ohne eigene Kontur (rechnen.ZEITANTEILE), in dieser Reihenfolge
REST_ANTEILE = (("gravur", "Gravur"), ("gravur_anbau", "Gravur Anbauteile"), ("ecken", "Ecken"),
                ("d3", "Mehrzeit 3D"), ("doppel", "Anschlag doppelt"), ("anfahrweg", "Anfahrweg"),
                ("abfall", "Abfall zerteilen"), ("drehen", "Drehen je Seitenwechsel"), ("messen", "Messzyklen"),
                ("neben", "Nebenzeit je Teil"), ("entnahme", "Entnahme von Hand"))
OHNE_GAS = ("anfahren", "neben", "drehen", "messen", "entnahme")       # wie rechnen.OHNE_GAS
TOL = 0.005             # s: kleinere Abweichungen sind Rundung und erscheinen nicht als Abgleich


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def schritte_der_position(p, profil, grenzen, maschine=None):
    """Schritte des Schneidweg-Rechners einer Position (Eingaben aus positionen.technik, Schneidweg-Rechner oder
    STEP-Import) oder aus der Konturliste ('A:40x149,7; 10x31,4', ohne Art) bzw. [] ohne beides."""
    from . import rechnen
    e = sw.lesen(p.get("technik"))
    if e.get("quelle") in (sw.QUELLE, sw.QUELLE_STEP) and profil:
        try:
            r = sw.rechnen(e, profil, grenzen, maschine=maschine, laenge=p.get("laenge"))
        except Exception:       # unvollständige Eingaben: dann aus der Konturliste
            r = None
        if r and r.get("schritte"):
            return r["schritte"]
    out = []
    form = (profil or {}).get("form")
    if not p.get("konturen"):       # ohne Konturliste: Schneidweg je Klasse (Felder der Position) und Einstiche
        for name, mm in (("groß", rechnen.gross_rest(p)), ("mittel", _n(p.get("mittel_mm"))),
                         ("klein", _n(p.get("klein_mm")))):
            if mm:
                out.append(dict(text=f"Schneidweg {name} (ohne Konturliste)", anzahl=1, laenge=mm, einstiche=0,
                                huelle=None, klasse=name, art="Schneidweg"))
        if _n(p.get("einstiche")):
            out.append(dict(text=f"{rechnen.zahl(_n(p['einstiche']), 0)} Einstiche (ohne Konturliste)", anzahl=1,
                            laenge=0.0, einstiche=_n(p["einstiche"]), huelle=None, klasse="groß", art="Einstiche"))
        return out
    n_ende = rechnen.einstiche_ende(form)
    for art, hk, lg in rechnen.konturen_lesen(p.get("konturen"), True):
        if art:
            out.append(dict(text="Anfangsschnitt" if art == "A" else "Endschnitt", anzahl=1, laenge=lg,
                            einstiche=n_ende, huelle=hk, klasse="Ende", art=ENDE))
        else:
            out.append(dict(text=f"Innenkontur Hüllmaß {rechnen.zahl(hk, 1)} mm", anzahl=1, laenge=lg, einstiche=1,
                            huelle=hk, klasse=KLASSE_NAME[rechnen.kontur_klasse(hk, grenzen)], art="Kontur"))
    return out


def liste(schritte, t, grenzen, satz=0.0, gas_eur_h=0.0):
    """Bearbeitungszeilen eines Teils. t = rechnen._schneidzeit_teile (vorschuebe, anteile, ta, dyn), grenzen =
    Regel der Konturklassen der Position. satz = Stundensatz Laser schneiden [€/h], gas_eur_h = Schneidgas je
    Stunde Gaszeit [€/h]. Ergebnis [dict(nr, art, text, klasse, laenge, einstiche, s, eur, gruppe, schritt)];
    gruppe: Ende, Kontur, ohne Merkmal, Abgleich; schritt = Index in schritte bzw. None. [] ohne Schneiddaten."""
    from . import rechnen
    anteile = (t or {}).get("anteile")
    if not anteile:
        return []
    h, i_, j, kv, l = t["vorschuebe"]
    ta = 0.0 if t.get("dyn") else _n(t.get("ta"))
    v = (j, i_, h)

    def kosten(s, gas=True):
        return s / 3600 * _n(satz) + (s / 3600 * _n(gas_eur_h) if gas else 0.0)
    out = []
    for nr, s in enumerate(schritte or ()):
        k = s.get("klasse")
        if k == "Ende":
            c = rechnen.kontur_klasse(_n(s.get("huelle")), grenzen) if s.get("huelle") else 2
        elif k in KLASSEN:
            c = KLASSEN[k]
        else:       # Gravur, Markierung (Flowdrill): ohne eigene Schnittzeit, Gravur steht unten gesamt
            out.append(dict(nr=nr, art=s.get("art") or k, text=s.get("text") or "", klasse=k or "", laenge=0.0,
                            einstiche=0, s=0.0, eur=0.0, gruppe=KONTUR, schritt=nr))
            continue
        lg, n_e = _n(s.get("laenge")), _n(s.get("einstiche"))
        schnitt = 60 * lg / v[c] if v[c] else 0.0
        zeit = schnitt + n_e * _n(l) + n_e * ta
        out.append(dict(nr=nr, art=s.get("art") or ("Ende" if k == "Ende" else "Kontur"), text=s.get("text") or "",
                        klasse=KLASSE_NAME[c], laenge=lg, einstiche=n_e, s=zeit,
                        eur=kosten(schnitt + n_e * _n(l)) + kosten(n_e * ta, gas=False),
                        gruppe=ENDE if k == "Ende" else KONTUR, schritt=nr))
    if t.get("dyn") and _n(anteile.get("anfahren")):
        out.append(dict(nr=None, art=REST, text="Leerwege und Drehen (Dynamik)", klasse="", laenge=0.0,
                        einstiche=0, s=_n(anteile["anfahren"]), eur=kosten(_n(anteile["anfahren"]), gas=False),
                        gruppe=REST, schritt=None))
    for schl, name in REST_ANTEILE:
        s = _n(anteile.get(schl))
        if s:
            out.append(dict(nr=None, art=REST, text=name, klasse="", laenge=0.0, einstiche=0, s=s,
                            eur=kosten(s, gas=schl not in OHNE_GAS), gruppe=REST, schritt=None))
    rest = sum(_n(x) for x in anteile.values()) - sum(x["s"] for x in out)
    if abs(rest) >= TOL:
        out.append(dict(nr=None, art=ABGLEICH, text="Abgleich (Active Tilt, Rand ohne Einstich, Rundung, "
                                                    "Schneidweg von Hand)", klasse="", laenge=0.0, einstiche=0,
                        s=rest, eur=kosten(rest), gruppe=ABGLEICH, schritt=None))
    return out


def mit_kalkulation(zeilen_b, z, satz=0.0, gas_eur_h=0.0):
    """Bearbeitungszeilen um die Werte der Kalkulationszeile z ergänzt: Einsparung gemeinsamer Schnitte (negativ),
    Zusatzzeiten je Stück, Prüfzeit Anbauteile; Schneidzeit von Hand ersetzt alle berechneten Zeilen. Summe = Laserzeit
    netto je Teil."""
    def kosten(s, gas=True):
        return s / 3600 * _n(satz) + (s / 3600 * _n(gas_eur_h) if gas else 0.0)
    if z.get("zeit_manuell") == "ja":
        hand = _n(z.get("laser_netto")) - _n(z.get("zeit_extra")) - _n(z.get("zeit_pruefung"))
        out = [dict(nr=None, art=HAND, text="Schneidzeit von Hand (ersetzt die berechneten Zeilen)", klasse="",
                    laenge=0.0, einstiche=0, s=hand, eur=kosten(hand), gruppe=HAND, schritt=None)]
    else:
        out = list(zeilen_b)
        brutto = _n(z.get("laser_brutto"))
        gespart = min(_n(z.get("einsparung")), brutto)
        if gespart:
            out.append(dict(nr=None, art=REST, text="Einsparung gemeinsamer Schnitt", klasse="", laenge=0.0,
                            einstiche=0, s=-gespart, eur=kosten(-gespart), gruppe=REST, schritt=None))
    for schl, name in (("zeit_extra", "Zusatzzeiten je Stück"), ("zeit_pruefung", "Prüfzeit Anbauteile")):
        if _n(z.get(schl)):
            out.append(dict(nr=None, art=REST, text=name, klasse="", laenge=0.0, einstiche=0, s=_n(z[schl]),
                            eur=kosten(_n(z[schl]), gas=False), gruppe=REST, schritt=None))
    return out


def fuer_position(p, z, kopf, k, tabellen):
    """Bearbeitungsliste einer Position der Kalkulation (z = Kalkulationszeile) mit Laser-Stundensatz und Gas:
    Summe der Zeilen = Laserzeit netto je Teil, Summe der Kosten = Laser schneiden + Schneidgas je Teil."""
    from . import rechnen
    if not z or z.get("laser_netto") is None:
        return []
    pr = k.profile.get(p.get("profil_id")) if k else None
    m = rechnen.maschine(kopf, k) if k else None
    wand = rechnen.wand_position(p, k)
    grenzen = rechnen.grenzen_lesen(p.get("kontur_grenzen")) or rechnen.kontur_regel(m, wand)
    t = rechnen._schneidzeit_teile(p, kopf, rechnen.wand_schneiden(pr) if pr else wand, tabellen, k)
    netto = _n(z.get("laser_netto"))
    satz = _n(z.get("laser_schneiden_teil")) / netto * 3600 if netto else 0.0
    gas_s = _n(z.get("zeit_gas"))
    gas_h = _n(z.get("schneidgas_teil")) / gas_s * 3600 if gas_s else 0.0
    profil = dict(pr, profil_id=p.get("profil_id")) if pr else None
    return mit_kalkulation(liste(schritte_der_position(p, profil, grenzen, m), t, grenzen, satz, gas_h), z, satz,
                           gas_h)


def summe(zeilen):
    """(Zeit [s], Kosten [€]) aller Zeilen."""
    return sum(x["s"] for x in zeilen), sum(x["eur"] for x in zeilen)
