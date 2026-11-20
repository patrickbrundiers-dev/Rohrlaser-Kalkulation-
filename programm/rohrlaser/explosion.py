"""Explosionsansicht für Baugruppe und Satz (Auftrag Patrick 20.11.2026 „Explosionsansicht erweitern und
professionalisieren“). Ohne Qt.

Nur Anzeige: Aus dem gezeigten Modell entsteht eine Kopie, in der jeder Körper (Teil) um seinen Weg verschoben ist.
Netz, Lage der Teile (= STEP), Export und Kalkulation bleiben genau gleich. Gespeichert wird nur der Zustand der
Ansicht (Stand.als_dict) als eigene Anzeigedaten, z. B. unter bg['explosionen'] bzw. in den Daten des Satzes.

Weg eines Teils = automatischer Weg × Faktor + eigener Versatz (von Hand gezogen oder eingegeben):
- automatisch aus der Struktur: Richtung = Lage der Teilmitte zur Mitte der Baugruppe (frei, waagrecht, senkrecht oder
  nur X/Y/Z); mit Ebenen wandert eine Unterbaugruppe zuerst als Ganzes, ihre Teile danach weniger weit (Normteile
  und Teile ohne Unterbaugruppe zählen als eigene Gruppe)
- keine Überschneidung: Hüllquader, die sich nach dem Verschieben noch schneiden, werden entlang ihrer Wege
  auseinandergeschoben (wächst mit dem Faktor, zusammengesteckt bleibt alles, wie es ist)
- fixierte Teile bleiben stehen
- schrittweise: Teile in der Reihenfolge (außen zuerst) nacheinander, Montagereihenfolge = umgekehrt
"""
import copy
import json
import math

RICHTUNGEN = {"Frei (aus der Mitte)": "frei", "Waagrecht": "h", "Senkrecht": "v", "Nur X": "x", "Nur Y": "y",
              "Nur Z": "z"}
BESCHRIFTUNGEN = ("Aus", "Positionsnummer", "Nummer und Artikel", "Alle Angaben")
EBENE_TEIL = 0.6        # Teil innerhalb seiner Unterbaugruppe: so viel vom Weg der Gruppe dazu
FAKTOR_MAX = 3.0
VERLAUF_MAX = 60
SENKRECHT = 1           # Hochachse des Modells (y, wie die Ansicht „Oben“)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _laenge(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _richtung(v, art):
    """Weg-Richtung v nach der Art einschränken (frei, h = waagrecht, v = senkrecht, x/y/z)."""
    if art == "h":
        return (v[0], 0.0, v[2]) if SENKRECHT == 1 else (v[0], v[1], 0.0)
    if art == "v":
        return (0.0, v[SENKRECHT], 0.0) if SENKRECHT == 1 else (0.0, 0.0, v[2])
    if art in ("x", "y", "z"):
        k = "xyz".index(art)
        return tuple(v[c] if c == k else 0.0 for c in range(3))
    return v


class Stand:
    """Zustand einer Explosionsansicht mit Rückgängig/Wiederholen. versatz: {Kennung: [dx, dy, dz]} in mm, fix:
    Kennungen, die stehen bleiben; schritt: None = alle Teile, sonst Anzahl (auch halbe) der Teile in reihenfolge,
    die schon auseinander sind."""
    FELDER = ("faktor", "richtung", "ebenen", "ueberlappung", "versatz", "fix", "linien", "beschriftung")

    def __init__(self):
        self.faktor, self.richtung, self.ebenen, self.ueberlappung = 0.0, "frei", True, True
        self.versatz, self.fix = {}, set()
        self.linien, self.beschriftung = True, "Positionsnummer"
        self.schritt, self.reihenfolge = None, []
        self._zurueck, self._vor = [], []

    # ------------------------------------------------------------ Daten
    def als_dict(self):
        return dict(faktor=round(float(self.faktor), 4), richtung=self.richtung, ebenen=bool(self.ebenen),
                    ueberlappung=bool(self.ueberlappung),
                    versatz={k: [round(float(c), 3) for c in v] for k, v in sorted(self.versatz.items())},
                    fix=sorted(self.fix), linien=bool(self.linien), beschriftung=self.beschriftung)

    def aus_dict(self, d):
        """Gespeicherten Zustand übernehmen; Ungültiges fällt auf die Vorgabe zurück."""
        d = d if isinstance(d, dict) else {}
        try:
            self.faktor = max(0.0, min(FAKTOR_MAX, float(d.get("faktor") or 0.0)))
        except (TypeError, ValueError):
            self.faktor = 0.0
        self.richtung = d.get("richtung") if d.get("richtung") in RICHTUNGEN.values() else "frei"
        self.ebenen = bool(d.get("ebenen", True))
        self.ueberlappung = bool(d.get("ueberlappung", True))
        self.versatz = {}
        for k, v in (d.get("versatz") or {}).items() if isinstance(d.get("versatz"), dict) else ():
            try:
                w = [float(c) for c in v][:3]
            except (TypeError, ValueError):
                continue
            if len(w) == 3 and all(math.isfinite(c) for c in w):
                self.versatz[str(k)] = w
        self.fix = {str(k) for k in d.get("fix") or () if isinstance(k, (str, int))}
        self.linien = bool(d.get("linien", True))
        self.beschriftung = d.get("beschriftung") if d.get("beschriftung") in BESCHRIFTUNGEN else "Positionsnummer"
        self.schritt = None
        return self

    def aktiv(self):
        return bool(self.faktor or self.versatz)

    # ------------------------------------------------------------ Rückgängig
    def merken(self):
        """Vor jeder Änderung von Hand aufrufen: der alte Stand kommt in den Verlauf."""
        self._zurueck.append(json.dumps(self.als_dict(), sort_keys=True))
        del self._zurueck[:-VERLAUF_MAX]
        self._vor = []

    def rueckgaengig(self):
        if not self._zurueck:
            return False
        self._vor.append(json.dumps(self.als_dict(), sort_keys=True))
        self._wiederherstellen(self._zurueck.pop())
        return True

    def wiederholen(self):
        if not self._vor:
            return False
        self._zurueck.append(json.dumps(self.als_dict(), sort_keys=True))
        self._wiederherstellen(self._vor.pop())
        return True

    def _wiederherstellen(self, text):
        z, v = self._zurueck, self._vor
        self.aus_dict(json.loads(text))
        self._zurueck, self._vor = z, v

    def kann_zurueck(self):
        return bool(self._zurueck)

    def kann_vor(self):
        return bool(self._vor)

    # ------------------------------------------------------------ von Hand
    def verschieben(self, ids, d):
        """Teile um d (mm) verschieben (fixierte nicht). Ergebnis: Anzahl."""
        ids = [k for k in ids if k not in self.fix]
        if not ids or not any(d):
            return 0
        self.merken()
        for k in ids:
            alt = self.versatz.get(k, [0.0, 0.0, 0.0])
            self.versatz[k] = [alt[c] + d[c] for c in range(3)]
        return len(ids)

    def versatz_setzen(self, ids, v):
        """Eigenen Versatz der Teile genau auf v (mm) setzen."""
        ids = [k for k in ids if k not in self.fix]
        if not ids:
            return 0
        self.merken()
        for k in ids:
            if any(v):
                self.versatz[k] = [float(c) for c in v]
            else:
                self.versatz.pop(k, None)
        return len(ids)

    def fixieren(self, ids, an=True):
        ids = list(ids)
        if not ids:
            return 0
        self.merken()
        if an:
            self.fix |= set(ids)
        else:
            self.fix -= set(ids)
        return len(ids)

    def zuruecksetzen(self, ids=None):
        """Eigenen Versatz entfernen (ids None: alle Teile, auch Fixierung)."""
        self.merken()
        if ids is None:
            self.versatz, self.fix = {}, set()
        else:
            for k in ids:
                self.versatz.pop(k, None)


# ---------------------------------------------------------------- Rechnen
def koerper_daten(modell, koerper_von):
    """{Kennung: Mitte}, {Kennung: (min, max)} der Körper aus den Dreiecken."""
    p = modell.punkte
    summe, zahl, huelle = {}, {}, {}
    for nr, (i, j, k, _, _) in enumerate(modell.dreiecke):
        kid = koerper_von[nr]
        s = summe.setdefault(kid, [0.0, 0.0, 0.0])
        h = huelle.setdefault(kid, [list(p[i]), list(p[i])])
        for x in (i, j, k):
            q = p[x]
            for c in range(3):
                s[c] += q[c]
                if q[c] < h[0][c]:
                    h[0][c] = q[c]
                elif q[c] > h[1][c]:
                    h[1][c] = q[c]
        zahl[kid] = zahl.get(kid, 0) + 3
    mitten = {kid: tuple(s[c] / zahl[kid] for c in range(3)) for kid, s in summe.items()}
    return mitten, {kid: (tuple(h[0]), tuple(h[1])) for kid, h in huelle.items()}


def reihenfolge(mitten, gesamt):
    """Teile von außen nach innen (weitester Abstand zur Mitte zuerst): so gehen sie schrittweise auseinander;
    umgekehrt ist es die Montagereihenfolge."""
    return sorted(mitten, key=lambda k: (-_laenge(_sub(mitten[k], gesamt)), str(k)))


def wege(mitten, huellen, gesamt, stand, gruppe_von=None, t=1.0, groesse=None):
    """{Kennung: Weg (dx, dy, dz)} für den Stand. gruppe_von(Kennung) -> Schlüssel der Unterbaugruppe oder None.
    t: 0 … 1 (Animation)."""
    ids = list(mitten)
    if not ids:
        return {}
    f = float(stand.faktor or 0.0)
    gruppen = {}
    if stand.ebenen and gruppe_von is not None:
        for k in ids:
            g = gruppe_von(k)
            if g not in (None, ""):
                gruppen.setdefault(g, []).append(k)
    g_mitte = {g: tuple(sum(mitten[k][c] for k in ks) / len(ks) for c in range(3)) for g, ks in gruppen.items()}
    g_von = {k: g for g, ks in gruppen.items() for k in ks if len(ks) > 1}
    je = {}
    if stand.schritt is not None:
        folge = stand.reihenfolge or reihenfolge(mitten, gesamt)
        for i, k in enumerate(folge):
            je[k] = max(0.0, min(1.0, float(stand.schritt) - i))
    out = {}
    for k in ids:
        if k in stand.fix:
            out[k] = (0.0, 0.0, 0.0)
            continue
        if k in g_von:
            gm = g_mitte[g_von[k]]
            d = tuple(f * (gm[c] - gesamt[c]) + f * EBENE_TEIL * (mitten[k][c] - gm[c]) for c in range(3))
        else:
            d = tuple(f * (mitten[k][c] - gesamt[c]) for c in range(3))
        d = _richtung(d, stand.richtung)
        v = stand.versatz.get(k) or (0.0, 0.0, 0.0)
        out[k] = tuple(d[c] + v[c] for c in range(3))
    if stand.ueberlappung and f > 0 and len(ids) > 1 and len(ids) <= 400:
        _trennen(out, huellen, stand, min(1.0, f), groesse)
    s = max(0.0, min(1.0, float(t)))
    return {k: tuple(w[c] * s * je.get(k, 1.0) for c in range(3)) for k, w in out.items()}


def _trennen(weg, huellen, stand, staerke, groesse=None):
    """Hüllquader, die sich nach dem Verschieben noch schneiden, entlang ihrer Wege auseinanderschieben (nicht die
    fixierten). staerke 0 … 1: so viel der Überschneidung wird aufgelöst (wächst mit dem Faktor)."""
    ids = list(weg)
    luft = 0.02 * (groesse or max(_laenge(_sub(h[1], h[0])) for h in huellen.values()))
    for _ in range(24):
        bewegt = False
        for a_i in range(len(ids)):
            a = ids[a_i]
            ha = huellen[a]
            for b in ids[a_i + 1:]:
                if a in stand.fix and b in stand.fix:
                    continue
                hb = huellen[b]
                lo_a = [ha[0][c] + weg[a][c] for c in range(3)]
                hi_a = [ha[1][c] + weg[a][c] for c in range(3)]
                lo_b = [hb[0][c] + weg[b][c] for c in range(3)]
                hi_b = [hb[1][c] + weg[b][c] for c in range(3)]
                if any(hi_a[c] <= lo_b[c] or hi_b[c] <= lo_a[c] for c in range(3)):
                    continue
                u = _sub(weg[b], weg[a])
                if _laenge(u) < 1e-9:
                    u = _sub(tuple((lo_b[c] + hi_b[c]) / 2 for c in range(3)),
                             tuple((lo_a[c] + hi_a[c]) / 2 for c in range(3)))
                u = _richtung(u, stand.richtung)
                n = _laenge(u)
                if n < 1e-9:
                    continue
                u = tuple(c / n for c in u)
                # Überschneidung entlang u (Projektion der Quader)
                ma = sum((lo_a[c] + hi_a[c]) / 2 * u[c] for c in range(3))
                mb = sum((lo_b[c] + hi_b[c]) / 2 * u[c] for c in range(3))
                ra = sum((hi_a[c] - lo_a[c]) / 2 * abs(u[c]) for c in range(3))
                rb = sum((hi_b[c] - lo_b[c]) / 2 * abs(u[c]) for c in range(3))
                tief = ra + rb + luft - (mb - ma)
                if tief <= luft * 0.5:
                    continue
                schub = tief * staerke
                if a in stand.fix:
                    weg[b] = tuple(weg[b][c] + u[c] * schub for c in range(3))
                elif b in stand.fix:
                    weg[a] = tuple(weg[a][c] - u[c] * schub for c in range(3))
                else:
                    weg[a] = tuple(weg[a][c] - u[c] * schub / 2 for c in range(3))
                    weg[b] = tuple(weg[b][c] + u[c] * schub / 2 for c in range(3))
                bewegt = True
        if not bewegt:
            break


def verschieben(modell, koerper_von, weg):
    """Kopie des Modells mit jedem Körper um weg[Kennung] verschoben (Dreiecksreihenfolge bleibt, die Auswahl findet
    ihre Körper wieder). Konturlinien gehen mit dem Körper, in dessen Hülle sie liegen."""
    from .schnitt_explosion import _kopie
    p = modell.punkte
    neu_p, neu_d = [], []
    null = (0.0, 0.0, 0.0)
    for nr, (i, j, k, art, n) in enumerate(modell.dreiecke):
        w = weg.get(koerper_von[nr], null)
        basis = len(neu_p)
        for x in (i, j, k):
            neu_p.append((p[x][0] + w[0], p[x][1] + w[1], p[x][2] + w[2]))
        neu_d.append((basis, basis + 1, basis + 2, art, n))
    mitten, huellen = koerper_daten(modell, koerper_von)

    def koerper_der_linie(a, b):
        q = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
        drin = [(math.prod(h[1][c] - h[0][c] + 1e-3 for c in range(3)), kid) for kid, h in huellen.items()
                if all(h[0][c] - 0.5 <= q[c] <= h[1][c] + 0.5 for c in range(3))]
        return min(drin)[1] if drin else min(mitten, key=lambda kid: math.dist(q, mitten[kid]))
    linien = []
    for a, b, art, n in modell.linien:
        w = weg.get(koerper_der_linie(a, b), null)
        linien.append(((a[0] + w[0], a[1] + w[1], a[2] + w[2]), (b[0] + w[0], b[1] + w[1], b[2] + w[2]), art, n))
    g = _kopie(modell)
    g.punkte, g.dreiecke, g.linien = neu_p, neu_d, linien
    g.koerper = []          # Schnittkörper der Konturen gehören zum Rohr selbst: in der Explosion weglassen
    if neu_p:
        xs, ys, zs = [q[0] for q in neu_p], [q[1] for q in neu_p], [q[2] for q in neu_p]
        g.min, g.max = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
        g.mitte = tuple((a + b) / 2 for a, b in zip(g.min, g.max))
        g.groesse = max(1e-6, math.dist(g.min, g.max))
    return g


def anwenden(modell, koerper_von, stand, gruppe_von=None, t=1.0):
    """(gezeigtes Modell, [(Kennung, Mitte vorher, Mitte nachher)]) für den Stand; ohne Weg das Modell selbst."""
    if not modell.dreiecke or not koerper_von or len(koerper_von) != len(modell.dreiecke):
        return modell, []
    mitten, huellen = koerper_daten(modell, koerper_von)
    if len(mitten) < 2 and not stand.versatz:
        return modell, []
    weg = wege(mitten, huellen, modell.mitte, stand, gruppe_von, t, modell.groesse)
    if not any(any(abs(c) > 1e-9 for c in w) for w in weg.values()):
        return modell, []
    pfeile = [(k, mitten[k], tuple(mitten[k][c] + weg[k][c] for c in range(3))) for k in mitten]
    return verschieben(modell, koerper_von, weg), pfeile


# ---------------------------------------------------------------- gespeicherte Ansichten
def ansichten_lesen(liste):
    """Gespeicherte Explosionsansichten [dict(name, stand, kamera)] prüfen (Ungültiges fällt weg)."""
    out = []
    for e in liste or ():
        if not isinstance(e, dict) or not str(e.get("name") or "").strip():
            continue
        k = e.get("kamera") if isinstance(e.get("kamera"), dict) else {}
        out.append(dict(name=str(e["name"]).strip()[:80], stand=Stand().aus_dict(e.get("stand")).als_dict(),
                        kamera={n: k[n] for n in ("gier", "nick", "roll", "zoom", "versatz", "perspektive")
                                if n in k}))
    return out


def ansicht_merken(liste, name, stand, kamera=None):
    """Ansicht unter name speichern (gleicher Name wird ersetzt). Ergebnis: neue Liste."""
    neu = [e for e in ansichten_lesen(liste) if e["name"] != name.strip()]
    neu.append(dict(name=name.strip()[:80], stand=stand.als_dict(), kamera=copy.deepcopy(kamera or {})))
    return neu


def stueckliste(teile):
    """Stückliste der Explosionszeichnung aus [(Nummer, Position dict)]: [dict(nr, pos, artikel, bezeichnung,
    werkstoff, profil, wand, laenge, stueck)], gleiche Positionen zusammengefasst (Stück addiert)."""
    zeilen, nach_id = [], {}
    for nr, q in teile:
        q = q or {}
        schl = q.get("id") or (q.get("pos"), q.get("artikel"), q.get("bezeichnung"))
        if schl in nach_id:
            nach_id[schl]["menge"] += 1
            continue
        z = dict(nr=nr, pos=str(q.get("pos") or ""), artikel=str(q.get("artikel") or ""),
                 bezeichnung=str(q.get("bezeichnung") or ""), werkstoff=str(q.get("werkstoff_id") or ""),
                 profil=str(q.get("profil_id") or ""), wand=q.get("wand"), laenge=q.get("laenge"),
                 stueck=q.get("stueck"), menge=1)
        nach_id[schl] = z
        zeilen.append(z)
    return zeilen
