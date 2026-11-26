"""Netzdaten der 3D-Ansichten ohne Qt (Software-Audit 26.11.2026, Architektur A-01): packen/entpacken für die
Datenbank, Teile einer Baugruppe in Einbaulage zusammensetzen. Vorher in ansicht3d.py (Qt-Oberfläche); Rechen-,
Import- und Exportmodule (step, rahmen, cam_paket, nesting_abwicklung …) zogen dadurch beim Rechnen PySide6 nach.
ansicht3d.py führt alle Namen unverändert weiter (from .netz_daten import …), Aufrufer bleiben gültig.
Der Lage-Merker ist threadsicher und zählt seine Größe mit (vorher je Aufruf Summe über alle Einträge)."""
import json
import threading
import zlib

# Baugruppen-Ansicht: je Teil (Zeile gleicher Teile) eine Farbe, ohne Eintrag in der Legende
TEILFARBEN = ("#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F",
              "#BAB0AC", "#2F4B7C", "#A05195")


def _katalog_ok(netz, t):
    """Flächenkatalog (Messplan M3: 'fk' je STEP-Fläche, 'tf' je Art und Dreieck die Nummer darin) passt zum Netz:
    gleich viele Einträge wie Dreiecke, Nummern im Katalog. Ohne Katalog: True."""
    tf, fk = netz.get("tf"), netz.get("fk")
    if tf is None and fk is None:
        return True
    if not isinstance(tf, dict) or not isinstance(fk, list) or not all(isinstance(e, dict) for e in fk):
        return False
    n = len(fk)
    for art, nrn in tf.items():
        idx = (t or {}).get(art)
        if not isinstance(nrn, list) or idx is None or len(nrn) != len(idx) // 3 or \
                not all(type(x) is int and 0 <= x < n for x in nrn):
            return False
    return True


def mit_anbau(netz):
    return bool(netz) and ("AN" in (netz.get("t") or {}) or "GA" in (netz.get("l") or {}))


def packen(netz):
    """Netz (dict) -> Bytes für die Datenbank."""
    return zlib.compress(json.dumps(netz, separators=(",", ":")).encode("utf-8"), 6)


def entpacken(daten):
    if not daten:
        return None
    try:
        return json.loads(zlib.decompress(daten).decode("utf-8"))
    except (zlib.error, ValueError):
        return None


_lage_merker = {}        # (id(p), Lage) -> (p, Punkte in Einbaulage): Klicks im Satz/Baugruppe ohne Neurechnen
LAGE_MERKEN = 4_000_000  # so viele Zahlen höchstens merken
_lage_zahl = [0]         # so viele Punkte liegen gerade im Merker (statt je Aufruf über alle Einträge zu zählen)
_lage_sperre = threading.Lock()     # Hintergrund-Threads (Vorschau, Baugruppe) und Oberfläche teilen den Merker


def _in_lage(p, lage):
    """Punkte p (x, y, z flach) in die Einbaulage (Ursprung, z-Achse, x-Achse), auf 0,01 mm gerundet."""
    schl = (id(p), tuple(lage))
    with _lage_sperre:
        alt = _lage_merker.get(schl)
    if alt is not None and alt[0] is p:
        return alt[1]
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    o0, o1, o2 = o
    x0, x1, x2 = x
    y0, y1, y2 = y
    z0, z1, z2 = z
    aus = []
    neu = aus.extend
    for i in range(0, len(p) - 2, 3):
        a, b, c = p[i], p[i + 1], p[i + 2]
        neu((round(o0 + a * x0 + b * y0 + c * z0, 2), round(o1 + a * x1 + b * y1 + c * z1, 2),
             round(o2 + a * x2 + b * y2 + c * z2, 2)))
    with _lage_sperre:
        if not _lage_merker:            # von außen geleert (z. B. Tests: ansicht3d._lage_merker.clear())
            _lage_zahl[0] = 0
        if _lage_zahl[0] + len(aus) > LAGE_MERKEN:
            _lage_merker.clear()
            _lage_zahl[0] = 0
        vorher = _lage_merker.get(schl)
        if vorher is not None:
            _lage_zahl[0] -= len(vorher[1])
        _lage_merker[schl] = (p, aus)
        _lage_zahl[0] += len(aus)
    return aus


def baugruppe(netze, hervor=(), farben=None, fehlend=(), bereiche=None, kosten=None, normteile=(), pruefung=None):
    """Teile einer Baugruppe in ihrer Einbaulage zu einem Netz zusammensetzen. netze: Liste von Netzen (dict oder
    gepackt); farben: je Netz eine Nummer, gleiche Nummer = gleiche Farbe (z. B. gleiche Teile), sonst je Netz eine;
    hervor: Nummern in netze, die als 'gewählte Teile' (Art S) blau, alle anderen hellgrau gefärbt werden;
    fehlend: Nummern der nicht übernehmbaren Teile, immer magenta (Art N), außer sie sind gewählt. Ohne Innenwände und
    Schnittlinien (bei vielen Teilen verdeckt bzw. zu unruhig). Ergebnis: (Netz oder None, Anzahl Teile ohne
    Einbaulage, z. B. aus einer älteren Messung). bereiche: Liste, bekommt je Netz (Nummer, erster Punkt, Ende,
    Dreiecke als Punktnummern) für die Zuordnung eines Modellpunkts zu seinem Teil. kosten: {Nummer in netze: Stufe
    0 … 3} färbt die Teile nach ihrem €-Anteil (kostenfarben.py, Arten KO0 … KO3, mit Legende); gewählte Teile bleiben
    blau. normteile: Nummern der Normteile/Zukaufteile, eigene Farbe (Art NT, mit Legende), außer gewählt.
    pruefung: {Nummer in netze: Art QK/QU/QR/QF} färbt nach der Geometrieprüfung (korrekt, unsicher, reparierbar,
    fehlerhaft); Normteile bleiben NT (ausgeschlossen), gewählte Teile blau."""
    punkte, dreiecke, ohne, wk = [], {}, 0, []
    fk, tf, mit_fk = [], {}, True            # Flächenkatalog der Teile (Messplan M3), nur wenn alle Teile einen haben
    for nr, netz in enumerate(netze):
        if isinstance(netz, (bytes, bytearray, memoryview)):
            netz = entpacken(bytes(netz))
        lage = (netz or {}).get("lage")
        if not netz or not netz.get("p") or not lage or len(lage) != 9:
            ohne += 1
            continue
        p = netz["p"]
        basis = len(punkte) // 3
        punkte += _in_lage(p, lage)
        if netz.get("wk"):              # Schnittkörper der Rohre aus den Eingaben mit in die Einbaulage
            from .schnittkoerper import in_lage
            wk += in_lage(netz["wk"], lage)
        if bereiche is not None:
            bereiche.append((nr, basis, len(punkte) // 3, [basis + i for a, idx in (netz.get("t") or {}).items()
                                                            if a != "I" for i in idx]))
        kat_ok = mit_fk and _katalog_ok(netz, netz.get("t")) and bool(netz.get("tf"))
        mit_fk = kat_ok
        k0 = len(fk)
        if kat_ok:
            fk += netz["fk"]
        for art_teil, idx in (netz.get("t") or {}).items():
            if art_teil == "I":
                continue
            art = "S" if nr in hervor else "N" if nr in fehlend else f"KO{kosten[nr]}" if kosten and nr in kosten \
                else "NT" if pruefung and nr in normteile else pruefung[nr] if pruefung and nr in pruefung \
                else "X" if hervor else "NT" if nr in normteile else \
                f"F{(farben[nr] if farben else nr) % len(TEILFARBEN)}"
            dreiecke.setdefault(art, []).extend(basis + i for i in idx)
            if kat_ok:
                tf.setdefault(art, []).extend(k0 + k for k in netz["tf"][art_teil])
    out = dict(p=punkte, t=dreiecke, l={}, **{"global": True})
    if mit_fk and fk:
        out["fk"], out["tf"] = fk, tf
    if wk:
        out["wk"] = wk
    return (out if punkte else None), ohne
