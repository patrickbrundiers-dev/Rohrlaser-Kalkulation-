"""Gewicht und Schwerpunkt einer Baugruppe bzw. eines Satzes (ASM-008, Plan Phase 3 und 4, Paket C, 13.11.2026).

Gewicht je Teil aus bg_mengen.teil_werte (Profil × Länge bzw. Blech, Zukaufteil: Gewicht je Teil); Schwerpunkt jedes
Körpers als flächengewichteter Mittelpunkt seiner Oberfläche (Dreiecke des 3D-Netzes), in Einbaulage gedreht und mit
dem Teilgewicht gewichtet. Für dünnwandige Rohre und Bleche gleicher Wanddicke ist das der Massenschwerpunkt; sonst eine
Näherung – deshalb immer als „Näherung“ gekennzeichnet. Koordinaten im System der STEP-Datei [mm]. Ohne Qt.
"""
import math

from . import bg_mengen

HERKUNFT = "Näherung aus der 3D-Oberfläche und den Teilgewichten"


def _flaechenmitte(netz):
    """(Fläche, (x, y, z)) der Oberfläche eines Netzes in seinen eigenen Koordinaten, None ohne Dreiecke."""
    if isinstance(netz, (bytes, bytearray, memoryview)):
        from .ansicht3d import entpacken
        netz = entpacken(bytes(netz))
    p = (netz or {}).get("p") or ()
    a_sum, sx, sy, sz = 0.0, 0.0, 0.0, 0.0
    for idx in ((netz or {}).get("t") or {}).values():
        for i in range(0, len(idx) - 2, 3):
            a, b, c = idx[i] * 3, idx[i + 1] * 3, idx[i + 2] * 3
            if max(a, b, c) + 2 >= len(p):
                continue
            ux, uy, uz = p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]
            vx, vy, vz = p[c] - p[a], p[c + 1] - p[a + 1], p[c + 2] - p[a + 2]
            f = 0.5 * math.sqrt((uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2)
            if f <= 0:
                continue
            a_sum += f
            sx += f * (p[a] + p[b] + p[c]) / 3
            sy += f * (p[a + 1] + p[b + 1] + p[c + 1]) / 3
            sz += f * (p[a + 2] + p[b + 2] + p[c + 2]) / 3
    return (a_sum, (sx / a_sum, sy / a_sum, sz / a_sum)) if a_sum > 0 else None


def in_lage(punkt, lage):
    """Punkt (x, y, z) in die Einbaulage (Ursprung, z-Achse, x-Achse) wie ansicht3d._in_lage."""
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    a, b, c = punkt
    return tuple(o[i] + a * x[i] + b * y[i] + c * z[i] for i in range(3))


def rechnen(koerper, positionen, k):
    """koerper: [(Positions-ID, Lage, Netz)] wie im Satz-/Baugruppen-3D (je Körper ein Teil). Ergebnis dict(kg,
    schwerpunkt (x, y, z) oder None, teile, ohne_gewicht [Pos.]); kg = Summe der Körper mit Gewicht."""
    nach_id = {p.get("id"): p for p in positionen}
    gewicht, kg, kg3d, s, ohne_g, n = {}, 0.0, 0.0, [0.0, 0.0, 0.0], [], 0
    for pid, lage, netz in koerper:
        p = nach_id.get(pid)
        if p is None:
            continue
        if pid not in gewicht:
            gewicht[pid] = bg_mengen.teil_werte(p, k).get("gewicht")
        g = gewicht[pid]
        if not g:
            if str(p.get("pos")) not in ohne_g:
                ohne_g.append(str(p.get("pos")))
            continue
        m = _flaechenmitte(netz) if lage and len(lage) == 9 else None
        n += 1
        kg += g
        if m is None:
            continue
        x = in_lage(m[1], lage)
        kg3d += g
        for i in range(3):
            s[i] += g * x[i]
    return dict(kg=kg, schwerpunkt=tuple(v / kg3d for v in s) if kg3d > 0 else None, teile=n, ohne_gewicht=ohne_g)


def text(e):
    """Kurztext für die Kachel: („12,3 kg“, Tooltip mit Schwerpunkt und Herkunft)."""
    from .stammdaten import zahl_als_text
    if not e or not e.get("kg"):
        return "–", "Gewicht unbekannt (Teile ohne Profil/Werkstoff oder ohne 3D-Daten)"
    tipp = f"Summe von {e['teile']} Körpern"
    if e.get("schwerpunkt"):
        x, y, z = e["schwerpunkt"]
        tipp += (f"; Schwerpunkt X {zahl_als_text(x, 0)} / Y {zahl_als_text(y, 0)} / Z {zahl_als_text(z, 0)} mm "
                 "(Koordinaten der STEP-Datei)")
    tipp += f". {HERKUNFT}."
    if e.get("ohne_gewicht"):
        tipp += f" Ohne Gewicht: Pos. {', '.join(e['ohne_gewicht'][:6])}."
    return f"{zahl_als_text(e['kg'], 1)} kg", tipp


def zeile(e):
    """Satz für die Zeile unter dem 3D: „Gewicht ≈ 12,3 kg, Schwerpunkt X … / Y … / Z … mm (Näherung).“ oder ""."""
    from .stammdaten import zahl_als_text
    if not e or not e.get("kg"):
        return ""
    t = f" Gewicht ≈ {zahl_als_text(e['kg'], 1)} kg"
    if e.get("schwerpunkt"):
        x, y, z = e["schwerpunkt"]
        t += f", Schwerpunkt X {zahl_als_text(x, 0)} / Y {zahl_als_text(y, 0)} / Z {zahl_als_text(z, 0)} mm"
    return t + " (Näherung)."
