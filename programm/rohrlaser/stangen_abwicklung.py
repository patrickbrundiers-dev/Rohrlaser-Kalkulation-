"""Abwicklung einer ganzen Stange (Lantek-Idee L4, Patrick 24.10.2026 „Alle a“): alle Teile der Stange an ihrem Platz
auf dem abgewickelten Mantel (x = Länge ab Stangenanfang, s = Umfang ab Abwicklungsbeginn, wie skizze.py), mit
Schnittkanten der Enden, Innenkonturen und Gravuren und der Schweißnaht der Stange. Nur Rechnen, ohne Oberfläche:
gezeichnet wird in stangen_ansicht.AbwicklungBild und in den Werkstattpapieren (pdf.StangenAbwicklung).

Ein Teil wird nie gewendet, nur um die eigene Achse gedreht (optimierung.lage): die Drehung verschiebt seine
Abwicklung um Drehung/360 × Umfang (bei Rundrohr jeder Winkel, Quadratrohr 90°-Schritte, Rechteckrohr 180° – bei
diesen Drehungen bildet der Querschnitt sich auf sich selbst ab).
"""
from . import rechnen, schneidweg as sw, skizze as sk

PUNKTE_ENDE = 48            # Stützstellen je Schnittkante


def _linie_bei(linie, s):
    """Wert der Schnittlinie [(s, d)] an der Stelle s (linear zwischen den Stützstellen)."""
    for (s0, d0), (s1, d1) in zip(linie, linie[1:]):
        if s0 <= s <= s1:
            return d0 + (d1 - d0) * ((s - s0) / (s1 - s0) if s1 > s0 else 0.0)
    return linie[-1][1] if linie else 0.0


def verschiebung(qs, drehung):
    """Verschiebung der Abwicklung eines um drehung [°] gedrehten Teils [mm, 0 … Umfang)."""
    return ((drehung or 0) % 360) / 360 * qs.umfang


def position_zum_teil(t, positionen):
    """Position eines Teils der Stange (Index, sonst über den Bezug) oder None."""
    i = t.get("index")
    if isinstance(i, int) and 0 <= i < len(positionen) and rechnen.schluessel(positionen[i], i) == t.get("ref"):
        return positionen[i]
    return next((p for j, p in enumerate(positionen) if rechnen.schluessel(p, j) == t.get("ref")), None)


def grundform(qs, e, L):
    """Lage des Teils ohne Platz auf der Stange: (Schnittlinie A, Schnittlinie B, [(Kontur-Eingabe, x, s, Umriss)]).
    Hängt nur von Querschnitt, Eingaben und Länge ab: gleiche Teile auf mehreren Stangen rechnen sie einmal."""
    la, lb = sk.ende_abwicklung(qs, e.get("a"), PUNKTE_ENDE), sk.ende_abwicklung(qs, e.get("b"), PUNKTE_ENDE)
    konturen = [(d, sk.s_lage(qs, d["eingabe"]), sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)])
                for d in sk.lagen(e.get("konturen"), L)]
    return la, lb, konturen


def teil(qs, t, e, form=None):
    """Ein Teil auf der Stange: dict(ref, pos, von, bis, umriss=[(x, s)] (geschlossen, s im Bereich 0 … Umfang),
    konturen=[dict(art, gravur, punkte=[(x, s)])]); e = Eingaben des Schneidweg-Rechners (aus_position).
    form: schon gerechnete grundform(qs, e, Länge)."""
    U, L, von = qs.umfang, t["laenge"], t["von"]
    ds = verschiebung(qs, t.get("drehung"))
    la, lb, lagen = form or grundform(qs, e, L)
    stellen = [U * i / PUNKTE_ENDE for i in range(PUNKTE_ENDE + 1)]

    def mit_stufen(linie):              # Stützstellen der Schnittlinie dazu (Kanten der Nasen bleiben Stufen)
        return sorted(set(stellen) | {(q + ds) % U for q, _ in linie})
    # auf der Stange an der Stelle s liegt die Stelle s − ds des Teils
    oben = [(von + _linie_bei(la, (s - ds) % U), s) for s in mit_stufen(la)]
    unten = [(von + L - _linie_bei(lb, (s - ds) % U), s) for s in reversed(mit_stufen(lb))]
    konturen = []
    for d, s_lage, umr in lagen:
        s0 = (s_lage + ds) % U
        konturen.append(dict(art=d["art"], gravur=d["art"] in sw.GRAVUREN, verteilt=bool(d.get("verteilt")),
                             punkte=[(von + d["x"] + dx, s0 + dq) for dx, dq in umr]))
    return dict(ref=t["ref"], pos=t.get("pos"), artikel=t.get("artikel"), von=von, bis=t["bis"],
                umriss=oben + unten, konturen=konturen)


def stange(s, positionen, profil_von, merker=None):
    """Abwicklung der Stange s (Schnittplan bzw. rechnen.anzeige_stangen): dict(laenge, umfang, streifen
    [(Name, s0, s1)], naht (s der Schweißnaht oder None), teile=[teil(...)], fehlt=[Pos. ohne Daten]) oder None ohne
    Querschnitt. profil_von(p) = Profil der Position (rechnen.profil_im_angebot). merker: dict, das für mehrere
    Stangen derselben Rechnung die Grundform je Position und Länge behält (Werkstattpapiere: alle Stangen)."""
    qs, teile, fehlt = None, [], []
    for t in s.get("teile") or ():
        p = position_zum_teil(t, positionen)
        profil = profil_von(p) if p else None
        try:
            if qs is None and profil:
                qs = sk.Querschnitt(profil)
            if qs is None or qs.umfang <= 0:
                raise ValueError
            schl = (id(p), repr(profil), t["laenge"])
            if merker is not None and schl in merker and merker[schl][0] is p:
                e, form = merker[schl][1:]
            else:
                e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
                form = grundform(qs, e, t["laenge"])
                if merker is not None:
                    merker[schl] = (p, e, form)
            teile.append(teil(qs, t, e, form))
        except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError):
            fehlt.append(t.get("pos") if t.get("pos") is not None else t.get("artikel"))
    if qs is None or qs.umfang <= 0:
        return None
    lage = rechnen.stange_zeichen(s)[0]
    return dict(laenge=s["stange"], end=s.get("end") or 0, greif=s.get("greif") or 0, umfang=qs.umfang,
                streifen=qs.abwicklung_streifen(), naht=sk.naht_s(qs, lage) if lage is not None else None,
                teile=teile, fehlt=fehlt)


def profil_funktion(kopf, k):
    """profil_von für stange(): Profil der Position mit dem Außenradius des Angebots."""
    def profil_von(p):
        pr = k.profile.get(p.get("profil_id"))
        return rechnen.profil_im_angebot(pr, kopf, p.get("profil_id"), p.get("werkstoff_id"), k) if pr else None
    return profil_von


def kontur_teile(punkte, umfang):
    """Kontur in Stücken, die in den Streifen 0 … Umfang passen: über die Abwicklungsnaht laufende Konturen
    erscheinen oben und unten (verschoben um ±Umfang; das Zeichnen schneidet auf den Streifen zu)."""
    ss = [s for _, s in punkte]
    out = [punkte]
    if min(ss) < 0:
        out.append([(x, s + umfang) for x, s in punkte])
    if max(ss) > umfang:
        out.append([(x, s - umfang) for x, s in punkte])
    return out
