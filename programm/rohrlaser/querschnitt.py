"""Profilquerschnitt als Bild (Patrick 22.10.2026: "mit Bild des Querschnitts des Profils daneben"), für den Dialog
Meterpreise und das Kalkulation-PDF.

kontur(profil) liefert den Querschnitt maßstäblich in mm (Nullpunkt unten links, y nach oben):
- flaechen: geschlossene Polygone, mit der Gerade-Ungerade-Regel gefüllt (Außenkontur + Innenkontur = Rohrwand)
- linien: offene Linienzüge, nur gezeichnet (RP-Profile: Linien und Bögen des MegaCAD-Makros)
Rechteckrohr liegt mit der Breitseite oben wie im Naht-Dialog; U- und C-Profil mit dem Steg links, L-Profil mit dem
längeren Schenkel senkrecht, T-Profil mit dem Flansch oben. Eckradien werden nicht gezeichnet. Träger und T-Profile
nehmen die Flanschdicke aus der Normtabelle, sonst 1,5 × Steg. Sonderprofile ohne Maße: None.
"""
import math

from . import normprofile, rp_profile


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def _rechteck(x, y, b, h):
    return [(x, y), (x + b, y), (x + b, y + h), (x, y + h)]


def _kreis(mx, my, r, n=72):
    return [(mx + r * math.cos(2 * math.pi * i / n), my + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def kontur(profil):
    """dict(breite, hoehe, flaechen, linien) in mm oder None (unbekannte Form, Maße fehlen)."""
    if not profil:
        return None
    form, a, b, s = profil.get("form"), _n(profil.get("a")), _n(profil.get("b")), _n(profil.get("wand"))
    e = rp_profile.daten(profil.get("profil_id")) if form == rp_profile.FORM else None
    if e and e.get("elemente"):
        linien = []
        for el in e["elemente"]:
            if el[0] == rp_profile.LINIE:
                linien.append([(el[1], el[2]), (el[3], el[4])])
            elif el[0] == rp_profile.BOGEN:
                linien.append(rp_profile.bogen_punkte(el, sehne=0.05))
        return dict(breite=e["breite"], hoehe=e["hoehe"], flaechen=[], linien=linien)
    if a is None:
        return None
    s = min(s or a / 10, a / 2)
    if form == "Rundrohr":
        r = a / 2
        flaechen = [_kreis(r, r, r)] + ([_kreis(r, r, r - s)] if r - s > 0.01 else [])
        return dict(breite=a, hoehe=a, flaechen=flaechen, linien=[])
    if form in ("Quadratrohr", "Rechteckrohr"):
        br, h = max(a, b or a), min(a, b or a)
        s = min(s, h / 2)
        flaechen = [_rechteck(0, 0, br, h)] + ([_rechteck(s, s, br - 2 * s, h - 2 * s)] if h - 2 * s > 0.01 else [])
        return dict(breite=br, hoehe=h, flaechen=flaechen, linien=[])
    if form == "Flachstahl":
        return dict(breite=a, hoehe=s, flaechen=[_rechteck(0, 0, a, s)], linien=[])
    if form in ("U-Profil", "C-Profil") and b:
        n = normprofile.daten(profil.get("profil_id"))
        tf = n["tf"] if n and n["form"] == form else s
        pts = [(0, 0), (b, 0), (b, tf), (s, tf), (s, a - tf), (b, a - tf), (b, a), (0, a)]
        if form == "C-Profil":          # Abkantung nach innen, Länge geschätzt (nicht in den Maßen)
            c = min(b / 3, a / 4)
            pts = [(0, 0), (b, 0), (b, c), (b - s, c), (b - s, s), (s, s), (s, a - s), (b - s, a - s), (b - s, a - c),
                   (b, a - c), (b, a), (0, a)]
        return dict(breite=b, hoehe=a, flaechen=[pts], linien=[])
    if form == "L-Profil" and b:
        hoch, quer = max(a, b), min(a, b)
        return dict(breite=quer, hoehe=hoch, flaechen=[[(0, 0), (quer, 0), (quer, s), (s, s), (s, hoch), (0, hoch)]],
                    linien=[])
    if form in ("I-/H-Träger", "T-Profil"):
        n = normprofile.daten(profil.get("profil_id"))
        if n and n["form"] == form:
            a, b, s, tf = n["h"], n["b"], n["tw"], n["tf"]
        else:
            tf = 1.5 * s
        if not b:
            return None
        m = b / 2
        if form == "T-Profil":
            pts = [(m - s / 2, 0), (m + s / 2, 0), (m + s / 2, a - tf), (b, a - tf), (b, a), (0, a), (0, a - tf),
                   (m - s / 2, a - tf)]
        else:
            pts = [(0, 0), (b, 0), (b, tf), (m + s / 2, tf), (m + s / 2, a - tf), (b, a - tf), (b, a), (0, a),
                   (0, a - tf), (m - s / 2, a - tf), (m - s / 2, tf), (0, tf)]
        return dict(breite=b, hoehe=a, flaechen=[pts], linien=[])
    return None


def einpassen(q, breite, hoehe, rand=0.0):
    """Maßstab und Versatz, um den Querschnitt q mittig in eine Box breite × hoehe zu setzen: (f, dx, dy)."""
    f = min((breite - 2 * rand) / max(q["breite"], 1e-6), (hoehe - 2 * rand) / max(q["hoehe"], 1e-6))
    return f, (breite - q["breite"] * f) / 2, (hoehe - q["hoehe"] * f) / 2
