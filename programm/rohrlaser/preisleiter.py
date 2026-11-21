"""Preisleiter und Wirtschaftlichkeits-Ampel eines Angebots (Master-Prompt Angebotserstellung, Patrick 21.11.2026,
Punkt 4 „mehrere Preisvarianten“, „Aufschlag und Marge mathematisch korrekt“, „Warnungen bei kritischen Angeboten“).

Die Preisleiter zeigt die Preisstufen eines gerechneten Angebots nebeneinander: Preisuntergrenze kurzfristig und
langfristig (preisschicht J1), Mindestpreis (Mindestmarge), Zielpreis (Zielmarge), Zielpreis des Kunden und den
Angebotspreis. Je Stufe: Netto, Gewinn, Aufschlag auf die Kosten und Marge vom Warenwert, alles aus marge.py (eine
Formel). Die Stufen sind nur Rechnung; „Auf … setzen“ stellt den Gewinn des Angebots über die volle Kalkulation ein
(AngebotSeite.auf_marge_setzen).

Die Ampel bewertet das Angebot: kritisch unter der kurzfristigen Preisuntergrenze, unter den Kosten oder unter der
Mindestmarge; knapp unter der Zielmarge (ohne Ziel- und Mindestmarge: unter RISIKO_MARGE); sonst gut. Ohne Qt."""
from . import marge as mg

RISIKO_MARGE = 0.08         # wie das Preisrisiko (ki_kalkulation): darunter ist die Marge knapp, wenn nichts eingestellt ist
GUT, KNAPP, KRITISCH = "gut", "knapp", "kritisch"
ART_KURZ, ART_LANG, ART_MINDEST, ART_ZIEL, ART_KUNDE, ART_ANGEBOT = ("kurz", "lang", "mindest", "ziel", "kunde",
                                                                     "angebot")
SPALTEN = ("Preisstufe", "Netto [€]", "Gewinn [€]", "Aufschlag auf Kosten [%]", "Marge vom Warenwert [%]",
           "Unterschied zum Angebot [€]")


def _n(w):
    return mg._n(w)


def _anteil(einst, name):
    w = _n((einst or {}).get(name))
    return w if 0 < w < 1 else 0.0


def bei_preis(summen, netto):
    """Gewinn, Aufschlag und Marge, wenn das Angebot netto kostete (gleiche Kosten, Skonto auf den Preis)."""
    s = summen or {}
    sk = _n(s.get("skonto_satz")) / 100
    ohne_skonto = mg.durchgereicht(s) - _n(s.get("skonto"))
    k = mg.kosten(s)
    w = netto * (1 - sk) - ohne_skonto
    g = w - k
    return dict(netto=netto, gewinn=g, aufschlag=g / k if k > 0 else None, marge=g / w if w > 0 else None)


def zeilen(summen, einst, ziel_kunde=None):
    """Preisstufen aufsteigend: [dict(art, titel, netto, gewinn, aufschlag, marge, unterschied, satz)]; satz = Marge
    der Stufe (Mindest-/Zielmarge) für „Auf … setzen“, sonst None."""
    s = summen or {}
    jetzt = mg.werte(s)
    verkauf = jetzt["verkauf"]
    stufen = []
    kurz, lang = _n(s.get("untergrenze_kurz")), _n(s.get("untergrenze_lang"))
    if kurz > 0:
        stufen.append((ART_KURZ, "Preisuntergrenze kurzfristig (nur variable Kosten)", kurz, None))
    if lang > 0:
        stufen.append((ART_LANG, "Preisuntergrenze langfristig (alle Kosten, Fracht, Verpackung)", lang, None))
    m_min, m_ziel = _anteil(einst, "mindestmarge"), _anteil(einst, "zielmarge")
    if m_min:
        stufen.append((ART_MINDEST, f"Mindestpreis (Mindestmarge {_pz(m_min)} %)", mg.preis_bei_marge(s, m_min), m_min))
    if m_ziel:
        stufen.append((ART_ZIEL, f"Zielpreis (Zielmarge {_pz(m_ziel)} %)", mg.preis_bei_marge(s, m_ziel), m_ziel))
    if _n(ziel_kunde) > 0:
        stufen.append((ART_KUNDE, "Zielpreis des Kunden (Zielpreis …)", _n(ziel_kunde), None))
    out = []
    for art, titel, netto, satz in stufen:
        if netto is None:
            continue
        out.append(dict(bei_preis(s, netto), art=art, titel=titel, unterschied=netto - verkauf, satz=satz))
    out.append(dict(netto=verkauf, gewinn=jetzt["gewinn"], aufschlag=jetzt["aufschlag"], marge=jetzt["marge"],
                    art=ART_ANGEBOT, titel="Angebotspreis (jetzt)", unterschied=0.0, satz=None))
    return sorted(out, key=lambda z: (z["netto"], z["art"] == ART_ANGEBOT))


def _pz(anteil, stellen=1):
    return f"{100 * anteil:.{stellen}f}".replace(".", ",")


def bewertung(summen, einst, unsicher=None):
    """Ampel (unsicher = Anteil des Preises auf unsicheren Werten, herkunft.py; None = unbekannt): dict(stufe gut/knapp/kritisch, gruende [Text], marge, gewinn, aufschlag, text) oder None ohne Preis."""
    s = summen or {}
    w = mg.werte(s)
    if w["verkauf"] <= 0:
        return None
    m, g = w["marge"], w["gewinn"]
    m_min, m_ziel = _anteil(einst, "mindestmarge"), _anteil(einst, "zielmarge")
    kritisch, knapp = [], []
    kurz = _n(s.get("untergrenze_kurz"))
    if kurz > 0 and w["verkauf"] < kurz - 0.005:
        kritisch.append(f"Preis unter der kurzfristigen Preisuntergrenze ({_eur(kurz)} €): deckt nicht einmal die "
                        "variablen Kosten")
    if g < -0.005:
        kritisch.append(f"Preis unter den Kosten: Verlust {_eur(-g)} €")
    elif m is not None and m_min and m < m_min - 1e-9:
        kritisch.append(f"Marge {_pz(m)} % unter der Mindestmarge {_pz(m_min)} %")
    if m is not None and not kritisch:
        if m_ziel and m < m_ziel - 1e-9:
            knapp.append(f"Marge {_pz(m)} % unter der Zielmarge {_pz(m_ziel)} %")
        elif not m_ziel and not m_min and m < RISIKO_MARGE:
            knapp.append(f"Marge {_pz(m)} % unter {_pz(RISIKO_MARGE, 0)} % (keine Ziel- oder Mindestmarge eingestellt)")
    unsicher = _n(unsicher)
    if unsicher >= 0.25:
        knapp.append(f"{_pz(unsicher, 0)} % des Preises stehen auf unsicheren Werten")
    stufe = KRITISCH if kritisch else KNAPP if knapp else GUT
    gruende = kritisch + knapp
    text = {GUT: "Wirtschaftlich gut", KNAPP: "Wirtschaftlich knapp", KRITISCH: "Wirtschaftlich kritisch"}[stufe]
    if m is not None:
        text += f": Marge {_pz(m)} %" + (f" (Ziel {_pz(m_ziel)} %)" if m_ziel else
                                          f" (Mindest {_pz(m_min)} %)" if m_min else "")
    return dict(stufe=stufe, gruende=gruende, marge=m, gewinn=g, aufschlag=w["aufschlag"], text=text)


def _eur(w):
    from .stammdaten import zahl_als_text
    return zahl_als_text(round(w, 2), 2)


def umrechnung_text():
    """Erklärung Aufschlag ↔ Marge für die Preisleiter."""
    return ("Aufschlag = Gewinn ÷ Kosten, Marge = Gewinn ÷ Warenwert (Preis ohne Fracht, Verpackung, Finanzierung und "
            "Skonto). Marge = Aufschlag ÷ (1 + Aufschlag): 25 % Aufschlag sind 20 % Marge, 20 % Marge brauchen 25 % "
            "Aufschlag.")
