"""Abschnitte einer Stange des Schnittplans (Endbeschnitt, Teile, Schnitte, Rest, Greiferrest), ohne Qt.
Software-Audit 26.11.2026 (Architektur A-01): vorher in stangen_ansicht.py (Stangenbild der Oberfläche); die
Nesting-Abwicklung (Rechnung, 3D, PDF) lud dadurch PySide6 nach. stangen_ansicht.py führt die Namen weiter."""


def letzter_schnitt(s):
    """Schnittfuge hinter dem letzten Teil [mm]: Schnittverlust der Stange minus der Trennungen zwischen den Teilen."""
    teile = s["teile"]
    zwischen = sum(max(0.0, b["von"] - a["bis"]) for a, b in zip(teile, teile[1:]))
    return max(0.0, float(s.get("verlust") or 0.0) - zwischen) if teile else 0.0


def bereiche(s):
    """Abschnitte einer Stange des Schnittplans: [(art, von, bis, Teil-Dict oder None)] mit art 'end' | 'teil' |
    'schnitt' | 'rest' | 'greif', lückenlos von 0 bis zur Stangenlänge (Maße wie gespeichert)."""
    out = [("end", 0.0, float(s["end"]), None)]
    pos = float(s["end"])
    for t in s["teile"]:
        if t["von"] > pos + 1e-6:
            out.append(("schnitt", pos, float(t["von"]), None))
        out.append(("teil", float(t["von"]), float(t["bis"]), t))
        pos = float(t["bis"])
    ende = float(s["stange"] - s["greif"])
    if s["teile"]:
        k = min(letzter_schnitt(s), max(0.0, ende - pos))
        if k > 0:
            out.append(("schnitt", pos, pos + k, None))
            pos += k
    if ende > pos + 1e-6:
        out.append(("rest", pos, ende, None))
    out.append(("greif", max(pos, ende), float(s["stange"]), None))
    return out
