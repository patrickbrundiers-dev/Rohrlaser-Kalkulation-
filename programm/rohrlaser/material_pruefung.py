"""Material-Prüfungen der Roadmap Kalkulation Phase 2, Paket 2b (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach
Empfehlung“). Ohne Qt.

MAT-013 Mindestabnahme: 'Preise' bzw. 'Lieferlängen' tragen je Profil + Werkstoff (+ Länge) die Mindestabnahme des
  Lieferanten in Stangen (Bund). Braucht der Schnittplan weniger Stangen, meldet der Angebots-Check die Mehrstangen
  und ihren Preis. Mit der Einstellung 'mindestabnahme_kosten' = ja rechnet das Angebot die Mehrstangen in den
  Materialpreis (die Stangen der Gruppe werden anteilig teurer, rechnen._stangen_werte). Kein Restelager: die
  Mehrstangen werden nie als Bestand geführt.
MAT-014 Vorveredelt kaufen: Hat eine Oberfläche (z. B. „feuerverzinkt“) in den Stammdaten ein Vormaterial (Werkstoff
  des schon veredelten Materials, z. B. sendzimirverzinkt), vergleicht der Check je Stangengruppe Rohmaterial +
  Aufpreis der Oberfläche mit dem Vormaterial ohne Aufpreis, dazu die Arbeitstage für das Veredeln. Nur Vorschlag:
  der Kunde entscheidet (Korrosionsschutz der Schnittkanten ist nicht gleich).
MAT-019 STEP-Gewicht: Gewicht aus dem STEP-Volumen × Dichte gegen das Gewicht aus Profil × Länge; weicht es mehr als
  'step_gewicht_abweichung' % ab (0 = aus), stimmt oft Wand, Profil oder Werkstoff nicht."""
from . import angebot_check as ac

EPS = 1e-9


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


# ---------------------------------------------------------------- MAT-013 Mindestabnahme
def mindest(profil, werkstoff, stange, tabellen):
    """Mindestabnahme [Stangen] für Profil + Werkstoff in der Länge oder 0: Zeile in 'Lieferlängen' mit dieser Länge,
    sonst die Zeile in 'Preise' (Liefer-Stangenlänge leer oder gleich)."""
    t = tabellen or {}
    for z in t.get("lieferlaengen") or ():
        if z.get("profil_id") == profil and z.get("werkstoff_id") == werkstoff and abs(_n(z.get("laenge")) - stange) < 0.5:
            return int(_n(z.get("mindest_stangen")))
    for z in t.get("preise") or ():
        if z.get("profil_id") == profil and z.get("werkstoff_id") == werkstoff and (
                not z.get("lieferlaenge") or abs(_n(z.get("lieferlaenge")) - stange) < 0.5):
            return int(_n(z.get("mindest_stangen")))
    return 0


def bedarf(stangen, tabellen):
    """Gruppen unter der Mindestabnahme: [dict(profil, werkstoff, stange, n, mindest, mehr, indizes)] (Stangen ohne
    Kundenmaterial und ohne Muster-Lauf; Oberflächen zählen zusammen, es ist dasselbe Rohmaterial)."""
    gruppen = {}
    for i, s in enumerate(stangen or ()):
        if s.get("beistellung") or s.get("muster"):
            continue
        gruppen.setdefault((s.get("profil"), s.get("werkstoff"), _n(s.get("stange"))), []).append(i)
    out = []
    for (profil, ws, stange), idx in gruppen.items():
        m = mindest(profil, ws, stange, tabellen)
        if m > len(idx):
            out.append(dict(profil=profil, werkstoff=ws, stange=stange, n=len(idx), mindest=m, mehr=m - len(idx),
                            indizes=idx))
    return out


def kosten_einrechnen(einst):
    return (einst or {}).get("mindestabnahme_kosten") == "ja"


def mindest_punkte(ergebnis, sw, tabellen, einst):
    """Angebots-Check: HINWEIS je Gruppe unter der Mindestabnahme, mit Preis der Mehrstangen."""
    from .stammdaten import zahl_als_text as zahl
    stangen = (ergebnis or {}).get("stangen") or ()
    out = []
    drin = kosten_einrechnen(einst)
    for g in bedarf(stangen, tabellen):
        je = [(sw[i] or {}).get("kosten_mindest_basis", (sw[i] or {}).get("kosten")) for i in g["indizes"]
              if sw and i < len(sw)]
        je = [x for x in je if x is not None]
        eur = sum(je) / len(je) * g["mehr"] if je else None
        preis = f", Mehrkosten {zahl(eur, 2)} €" if eur is not None else ""
        text = (f"Mindestabnahme {g['profil']} {g['werkstoff']} {zahl(g['stange'] / 1000, 1)} m: Lieferant liefert "
                f"mindestens {g['mindest']} Stangen, gebraucht {g['n']}{preis}"
                + (" (im Preis enthalten)" if drin else " (nicht im Preis; Einstellung „Mindestabnahme des Lieferanten“)"))
        out.append(ac.Punkt(ac.HINWEIS, text, None))
    return out


def mindest_anwenden(out, stangen, tabellen, einst):
    """rechnen._stangen_werte: mit 'mindestabnahme_kosten' = ja die Kosten der Stangen einer Gruppe unter der
    Mindestabnahme × Mindestabnahme / gebraucht (kosten_mindest_basis = Kosten vorher)."""
    if not kosten_einrechnen(einst):
        return out
    for g in bedarf(stangen, tabellen):
        f = g["mindest"] / g["n"]
        for i in g["indizes"]:
            w = out[i]
            if w.get("kosten") is not None:
                w["kosten_mindest_basis"] = w["kosten"]
                w["kosten"] *= f
                w["mindest_faktor"] = f
    return out


# ---------------------------------------------------------------- MAT-014 vorveredelt kaufen
def veredeln_vergleich(kopf, positionen, ergebnis, k, tabellen, einst=None):
    """Je Stangengruppe mit Oberfläche, die ein Vormaterial hat: dict(profil, werkstoff, oberflaeche, vormaterial,
    stangen, jetzt, vor, tage, fehlt). jetzt = Rohmaterial + Aufpreis der Oberfläche, vor = Vormaterial ohne Aufpreis
    (je ganzem Angebot, Stangen wie geplant). fehlt = Text, wenn ein Preis fehlt (dann kein Vergleich)."""
    from . import rechnen
    gruppen = {}
    for s in (ergebnis or {}).get("stangen") or ():
        if s.get("beistellung"):
            continue
        gr = rechnen.gruppe_der_stange(s)
        ob = gr[2] if len(gr) > 2 else None
        z = (k.oberflaechen.get(ob or "") or {}) if ob else {}
        if not z.get("vormaterial") or z.get("vormaterial") == s.get("werkstoff"):
            continue
        gruppen.setdefault((s.get("profil"), s.get("werkstoff"), ob, _n(s.get("stange"))), [gr, 0])[1] += 1
    out = []
    for (profil, ws, ob, stange), (gr, n) in gruppen.items():
        z = k.oberflaechen.get(ob) or {}
        vor_ws = z["vormaterial"]
        kgm = rechnen.kg_je_m(profil, ws, k)
        kgm_v = rechnen.kg_je_m(profil, vor_ws, k)
        p_jetzt, f1 = rechnen.lieferstange_preis(gr, stange, stange / 1000 * kgm if kgm else None, kopf, [], k,
                                                 tabellen, einst)
        gr_v = (profil, vor_ws, None) + tuple(gr[3:])
        p_vor, f2 = rechnen.lieferstange_preis(gr_v, stange, stange / 1000 * kgm_v if kgm_v else None, kopf, [], k,
                                               tabellen, einst)
        fehlt = f1 or f2 or (None if vor_ws in k.werkstoffe else f"Werkstoff {vor_ws} fehlt")
        out.append(dict(profil=profil, werkstoff=ws, oberflaeche=ob, vormaterial=vor_ws, stangen=n,
                        jetzt=p_jetzt * n, vor=p_vor * n, tage=int(_n(z.get("veredeln_tage"))), fehlt=fehlt))
    return out


def veredeln_punkte(vergleiche):
    from .stammdaten import zahl_als_text as zahl
    out = []
    for v in vergleiche:
        kopf = f"{v['profil']} {v['oberflaeche']}: statt {v['werkstoff']} + {v['oberflaeche']} nach dem Laser"
        if v["fehlt"]:
            out.append(ac.Punkt(ac.HINWEIS, f"{kopf} wäre Vormaterial {v['vormaterial']} möglich – Vergleich nicht "
                                            f"möglich ({v['fehlt']})", None))
            continue
        d = v["vor"] - v["jetzt"]
        tage = f", spart {v['tage']} Arbeitstage Veredeln" if v["tage"] else ""
        out.append(ac.Punkt(ac.HINWEIS, f"{kopf}: Vormaterial {v['vormaterial']} {zahl(abs(d), 2)} € "
                                        f"{'günstiger' if d < 0 else 'teurer'} ({v['stangen']} {'Stange' if v['stangen'] == 1 else 'Stangen'})"
                                        f"{tage}; "
                                        "Schnittkanten bleiben blank – nur Vorschlag, der Kunde entscheidet", None))
    return out


# ---------------------------------------------------------------- MAT-019 STEP-Gewicht prüfen
def grenze(einst):
    return _n((einst or {}).get("step_gewicht_abweichung"))


def step_gewicht(p, k):
    """(Gewicht STEP [kg], Gewicht gerechnet [kg], Abweichung %) einer Position oder None. STEP-Volumen = beim Import
    gemessenes Volumen des Körpers (technik volumen_step, mm³; ältere Importe haben keins)."""
    from . import rechnen
    tech = p.get("technik")
    if isinstance(tech, str):
        import json
        try:
            tech = json.loads(tech)
        except ValueError:
            tech = None
    vol = _n((tech or {}).get("volumen_step")) if isinstance(tech, dict) else 0.0
    w = k.werkstoffe.get(p.get("werkstoff_id")) or {}
    kgm = rechnen.kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k)
    laenge = _n(p.get("laenge"))
    if vol <= 0 or not kgm or laenge <= 0 or not _n(w.get("dichte")):
        return None
    g_step = vol / 1e6 * _n(w["dichte"])          # mm³ -> dm³ × kg/dm³
    g_rech = kgm * laenge / 1000
    return g_step, g_rech, (g_step / g_rech - 1) * 100 if g_rech else 0.0


def gewicht_punkte(positionen, k, einst):
    """Angebots-Check: HINWEIS je Position, deren STEP-Gewicht mehr als die Grenze vom gerechneten abweicht.
    Konturen nehmen Material weg: das STEP-Gewicht liegt deshalb meist etwas unter dem gerechneten."""
    from .angebot import aktiv
    from .stammdaten import zahl_als_text as zahl
    g = grenze(einst)
    if g <= 0:
        return []
    out = []
    for i, p in enumerate(positionen or ()):
        if not aktiv(p):
            continue
        x = step_gewicht(p, k)
        if x is None or abs(x[2]) <= g + EPS:
            continue
        out.append(ac.Punkt(ac.HINWEIS, f"Pos. {p.get('pos')}: Gewicht aus STEP {zahl(x[0], 2)} kg, aus Profil × Länge "
                                        f"{zahl(x[1], 2)} kg ({'+' if x[2] > 0 else '−'}{zahl(abs(x[2]), 0)} %) – "
                                        "Wand, Profil oder Werkstoff prüfen", f"pos:{i}"))
    return out
