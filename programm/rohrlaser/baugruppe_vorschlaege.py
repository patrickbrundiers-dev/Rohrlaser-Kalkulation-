"""Vorschläge je Schweißbaugruppe bzw. Satz (Plan „Baugruppen automatisch und innovativ“, P1; Patrick 25.10.2026
„Alle a“): das Programm erkennt Knickrahmen, Steckverbindungen und eine günstige Lage der Längsnaht und rechnet je
Vorschlag, was er spart bzw. kostet. Nichts wird von selbst geändert (Frage 1 a): erst „Übernehmen“ im Fenster
Vorschläge setzt die angehakten um.

€-Vergleich (Frage 2 a) nur mit vorhandenen Werten, nichts erfunden; was sich nicht rechnen lässt, steht als offen da:
  Knickrahmen       + Ecknähte, die wegfallen (Nahtgruppe bzw. Nahtkandidat aus dem STEP mit beiden Körpern:
                      Kosten der Gruppe ÷ Anzahl, baugruppe.naht_rechnen), + Positionieren der Teile, die im Rahmen
                      aufgehen (Regeln der Vorkalkulation × Stundensatz schweiss_vk_satz), − Zusatzarbeit Knicken je
                      Knick, ± Laserzeit (Schneidweg-Rechner und Schneiddaten des Angebots × Stundensatz Maschine)
  Steckverbindung   + Positionieren des Steckers (Positionierhilfe bisher statt Steckverbindung), ± Laserzeit von
                      Aufnahme (Schlitze) und Stecker (Nasen)
  Längsnaht         kein €-Betrag: die Naht liegt nur an einer anderen Stelle

Schweißposten gibt es nur im Editor der Schweißbaugruppe; im Satz zählt nur der Laser. Die Laserzeit liefert das
Angebot (AngebotSeite.laser_teil_eur), ohne Angebot bleibt sie offen.

Längsnaht automatisch (Frage 3 a): nur Rohre ohne feste Naht. Kandidaten Quadrat-/Rechteckrohr die Mitten der vier
Wände, Rundrohr alle 15°; belegt ist eine Stelle am Umfang, an der eine Kontur (auch Schlitz, Gravur), eine Nase oder
ein Ende mit Nasen liegt. Unter den freien gewinnt die Stelle, die zur Mitte der Baugruppe zeigt (innen, beim
Schweißen und später verdeckt).
"""
from . import naht, skizze as sk

KNICK, STECK, NAHT = "Knickrahmen", "Steckverbindung", "Längsnaht"
ARTEN = (KNICK, STECK, NAHT)
KASTEN = (0.0, 90.0, 180.0, 270.0)
RUND_SCHRITT = 15.0


def _text(w, stellen=2):
    if not isinstance(w, (int, float)):
        return ""
    return f"{w:.{stellen}f}".replace(".", ",")


def euro(w):
    return f"{_text(w)} €" if isinstance(w, (int, float)) else "–"


def vorschlag(art, titel, teile, daten, posten=(), offen=(), hinweis=""):
    """Ein Vorschlag: posten [(Text, € +spart / −kostet)], offen [Text, was nicht gerechnet werden konnte], saldo =
    Summe der Posten (None ohne Posten)."""
    posten = [(t, round(w, 2)) for t, w in posten if isinstance(w, (int, float))]
    return dict(art=art, titel=titel, teile=list(teile), daten=daten, posten=posten, offen=[o for o in offen if o],
                saldo=round(sum(w for _, w in posten), 2) if posten else None, hinweis=hinweis, an=False)


def rechnung_text(v):
    """Rechenweg eines Vorschlags in einer Zeile."""
    teile = [f"{t} {'+' if w >= 0 else '−'}{_text(abs(w))} €" for t, w in v["posten"]]
    teile += [f"offen: {o}" for o in v["offen"]]
    if v.get("hinweis"):
        teile.insert(0, v["hinweis"])
    return " · ".join(teile)


def sortieren(liste):
    """Größte Ersparnis zuerst, dann Vorschläge ohne Betrag (Längsnaht), Art in fester Reihenfolge."""
    return sorted(liste, key=lambda v: (v["saldo"] is None, -(v["saldo"] or 0.0), ARTEN.index(v["art"])))


def summe(liste, nur_an=False):
    return round(sum(v["saldo"] or 0.0 for v in liste if v["saldo"] is not None and (v["an"] or not nur_an)), 2)


# ------------------------------------------------------------------ Preise
class Preise:
    """Werte für den €-Vergleich: Regeln und Stundensatz der Vorkalkulation, Zusatzarbeiten, Laser je Teil.
    schweissen = False (Satz): keine Schweißposten. laser(q, eingaben, laenge) -> (€ je Teil oder None, Grund)."""

    def __init__(self, tabellen=None, saetze=None, einstellungen=None, laser=None, schweissen=True):
        from .vorkalk import Regeln
        self.tabellen, self.saetze = tabellen or {}, saetze or {}
        self.einst = einstellungen or {}
        self.regeln = Regeln(self.tabellen)
        self.laser, self.schweissen = laser, schweissen
        self.satz_id = self.einst.get("schweiss_vk_satz") or "Schweißen"

    def satz(self):
        s = self.saetze.get(self.satz_id)
        return s if isinstance(s, (int, float)) and s > 0 else None

    def minuten(self, minuten):
        """€ für Minuten zum Stundensatz der Vorkalkulation, None ohne Satz."""
        s = self.satz()
        return minuten / 60 * s if s is not None else None

    def positionieren(self, hilfe):
        """Minuten Positionieren je Teil mit dieser Hilfe (Regel), None ohne Regel."""
        return self.regeln.wert("Positionieren", hilfe or "frei")

    def zusatz(self, name):
        """Preis je Einheit einer Zusatzarbeit der Stammdaten oder None."""
        from .rechnen import zusatz_preis
        z = next((z for z in self.tabellen.get("zusatzarbeiten") or () if z.get("name") == name), None)
        return zusatz_preis(z, self.saetze)["preis"] if z else None

    def naht(self, n):
        """Kosten einer Nahtgruppe (baugruppe.naht_rechnen): (€, Grund oder None)."""
        from .baugruppe import naht_rechnen
        r = naht_rechnen(n, self.tabellen, self.saetze)
        return (None, r["fehlt"]) if r["fehlt"] else (r["kosten"], None)


def laser_posten(preise, vorher, nachher):
    """Posten Laserzeit: vorher/nachher [(Position, Eingaben, Länge)] je Teil. ([(Text, €)], [offen])."""
    if preise.laser is None:
        return [], ["Laserzeit (ohne Angebot nicht rechenbar)"]
    summen = []
    for liste in (vorher, nachher):
        s = 0.0
        for q, e, lg in liste:
            w, grund = preise.laser(q, e, lg)
            if w is None:
                return [], [f"Laserzeit: {grund}"]
            s += w
        summen.append(s)
    d = summen[0] - summen[1]
    return [("Laser weniger" if d >= 0 else "Laser mehr", d)], []


# ------------------------------------------------------------------ Knickrahmen
def ecknaht_kosten(preise, ecken, vorschlaege, naehte, regel=None):
    """Kosten der Ecknähte, die ein Knickrahmen spart: je Ecke (Körperpaar) die Nahtgruppe bzw. der Nahtkandidat mit
    beiden Körpern, Kosten ÷ Anzahl. ([(Text, €)], [offen])."""
    from .baugruppe import vorschlag_naht
    gruppen = []
    for n in naehte or ():
        paare = {tuple(sorted(map(str, p))) for p in n.get("paare") or () if len(p) == 2}
        gruppen.append((n, paare, set(map(str, n.get("koerper") or ()))))
    verfahren = next((n.get("verfahren") for n in naehte or () if n.get("verfahren")), None) or next(
        (z["verfahren"] for z in preise.tabellen.get("schweissverfahren") or ()
         if z.get("verfahren") and z.get("aktiv", True) is not False), None)
    for v in vorschlaege or ():
        n = dict(vorschlag_naht(v, regel), verfahren=verfahren)
        gruppen.append((n, {tuple(sorted(map(str, p))) for p in v.get("teile") or () if len(p) == 2}, set()))
    summe_, offen, ohne = 0.0, [], 0
    for ecke in ecken:
        e = tuple(sorted(map(str, ecke)))
        treffer = next((g for g in gruppen if e in g[1]), None) or next(
            (g for g in gruppen if not g[1] and set(e) <= g[2]), None)
        if treffer is None:
            ohne += 1
            continue
        w, grund = preise.naht(treffer[0])
        if w is None:
            offen.append(f"Ecknaht {e[0]}+{e[1]}: {grund}")
            continue
        anzahl = treffer[0].get("anzahl") if isinstance(treffer[0].get("anzahl"), (int, float)) else 1
        summe_ += w / max(anzahl, 1)
    if ohne:
        offen.append(f"{ohne} Ecke(n) ohne Naht in der Baugruppe")
    return ([(f"{len(ecken) - ohne} Ecknaht/-nähte weniger", summe_)] if len(ecken) > ohne and summe_ else []), offen


def knick_bewerten(preise, rahmen, teile_q, hilfen, vorschlaege=(), naehte=(), regel=None):
    """Vorschlag Knickrahmen. rahmen = dict(koerper [(pid, lage_nr)], leit, eingaben, laenge, ecken, knicke, text);
    teile_q {pid: Position}; hilfen {pid: Positionierhilfe}."""
    from .knickrahmen import ZUSATZ_KNICKEN
    posten, offen = [], []
    n_knicke = rahmen.get("knicke") or 0
    if preise.schweissen:
        p, o = ecknaht_kosten(preise, rahmen.get("ecken") or (), vorschlaege, naehte, regel)
        posten += p
        offen += o
        weg = rahmen["koerper"][1:]
        minuten, fehlt = 0.0, set()
        for pid, _ in weg:
            m = preise.positionieren(hilfen.get(pid))
            if m is None:
                fehlt.add(hilfen.get(pid) or "frei")
            else:
                minuten += m
        if fehlt:
            offen.append("Regel Positionieren fehlt: " + ", ".join(sorted(fehlt)))
        elif weg:
            w = preise.minuten(minuten)
            if w is None:
                offen.append(f"Stundensatz '{preise.satz_id}' fehlt")
            else:
                posten.append((f"{len(weg)} Teil(e) weniger positionieren", w))
    preis = preise.zusatz(ZUSATZ_KNICKEN)
    if preis is None:
        offen.append(f"Zusatzarbeit '{ZUSATZ_KNICKEN}' fehlt")
    elif n_knicke:
        posten.append((f"{n_knicke} × Knicken", -preis * n_knicke))
    leit = teile_q.get(rahmen["leit"]) or {}
    vorher = [(teile_q[pid], None, None) for pid, _ in rahmen["koerper"] if pid in teile_q]
    p, o = laser_posten(preise, vorher, [(leit, rahmen["eingaben"], rahmen.get("laenge"))])
    posten += p
    offen += o
    n = len(rahmen["koerper"])
    titel = f"{n} Rohre zu einem Knickrahmen ({n_knicke} Knick{'e' if n_knicke != 1 else ''})"
    teile = list(dict.fromkeys(pid for pid, _ in rahmen["koerper"]))
    return vorschlag(KNICK, titel, teile, rahmen, posten, offen, rahmen.get("text", ""))


# ------------------------------------------------------------------ Steckverbindung
def steck_bewerten(preise, plan, teile_q, hilfen, eingaben_vorher, eingaben_nachher, text=""):
    """Vorschlag Steckverbindung aus einem Eintrag von SteckEditor.steck_plan (auf, st, ende, x, seite, …).
    eingaben_vorher/-nachher {pid: (Eingaben, Länge)} der beiden Rohre ohne bzw. mit der Verbindung."""
    posten, offen = [], []
    if preise.schweissen:
        alt, neu = preise.positionieren(hilfen.get(plan["st"])), preise.positionieren("Steckverbindung")
        if alt is None or neu is None:
            offen.append("Regel Positionieren fehlt")
        else:
            w = preise.minuten(alt - neu)
            if w is None:
                offen.append(f"Stundensatz '{preise.satz_id}' fehlt")
            elif w:
                posten.append(("Stecker positionieren", w))
    vorher, nachher = [], []
    for pid in (plan["auf"], plan["st"]):
        q = teile_q.get(pid) or {}
        vorher.append((q, *(eingaben_vorher.get(pid) or (None, None))))
        nachher.append((q, *(eingaben_nachher.get(pid) or (None, None))))
    p, o = laser_posten(preise, vorher, nachher)
    posten += p
    offen += o
    titel = f"Pos. {_text(teile_q.get(plan['st'], {}).get('pos'), 0)} in Pos. " \
            f"{_text(teile_q.get(plan['auf'], {}).get('pos'), 0)} stecken (Ende {'A' if plan['ende'] == 'a' else 'E'})"
    return vorschlag(STECK, titel, [plan["auf"], plan["st"]], plan, posten, offen, text)


# ------------------------------------------------------------------ Längsnaht
def _bereich(liste, s, h, umfang):
    liste.append(((s - h) % umfang, 2 * h))


def belegt(qs, e, laenge):
    """Belegte Stellen am Umfang [(Start s, Breite)]: Konturen (auch Schlitze, Gravur), Nasen der Enden."""
    out = []
    for d in sk.lagen((e or {}).get("konturen") or (), laenge or 0.0, qs):
        ein = d["eingabe"]
        pts = sk.umriss_kontur(ein) or [(0.0, 0.0)]
        ss = [sk.s_lage(qs, ein, dq) for _, dq in pts]
        mitte = sk.s_lage(qs, ein)
        weit = max(abs(s - mitte) for s in ss)
        _bereich(out, mitte, max(weit, 0.5), qs.umfang)
    for ende in ("a", "b"):
        n = sk._nasen_abwicklung(qs, (e or {}).get(ende) or {})
        for m, h in (n[1] if n else ()):
            _bereich(out, m, h, qs.umfang)
    return out


def _frei(s, bereiche, umfang):
    return not any((s - a) % umfang < b for a, b in bereiche)


def _abstand(w1, w2):
    d = abs(w1 - w2) % 360.0
    return min(d, 360.0 - d)


def naht_lage(profil, e, laenge, innen=None):
    """Günstige Längsnaht: (Winkel, Grund) oder (None, Grund). innen = Winkel zur Mitte der Baugruppe oder None."""
    form = (profil or {}).get("form")
    if form not in ("Quadratrohr", "Rechteckrohr", "Rundrohr"):
        return None, "kein Quadrat-, Rechteck- oder Rundrohr"
    qs = sk.Querschnitt(profil)
    kandidaten = list(KASTEN) if form != "Rundrohr" else [i * RUND_SCHRITT for i in range(int(360 / RUND_SCHRITT))]
    bereiche = belegt(qs, e, laenge)
    if innen is None and not bereiche:
        return None, "überall frei, keine Mitte der Baugruppe bekannt (keine Vorgabe nötig)"
    frei = [w for w in kandidaten if _frei(sk.naht_s(qs, w) or 0.0, bereiche, qs.umfang)]
    if not frei:
        return None, "keine freie Wand (Konturen, Schlitze oder Nasen überall)"
    if innen is None:
        return frei[0], "frei von Konturen, Schlitzen und Nasen"
    w = min(frei, key=lambda x: (_abstand(x, innen), x))
    grund = "innen (zur Mitte der Baugruppe)" if _abstand(w, innen) <= 45.0 else "nächste freie Stelle zur Mitte"
    return w, grund + ", frei von Konturen, Schlitzen und Nasen"


def mitte(punkte):
    """Schwerpunkt [(x, y, z)] oder None."""
    if not punkte:
        return None
    return tuple(sum(p[k] for p in punkte) / len(punkte) for k in range(3))


def naht_vorschlag(pid, q, profil, e, laenge, innen):
    w, grund = naht_lage(profil, e, laenge, innen)
    if w is None:
        return None
    titel = f"Pos. {_text(q.get('pos'), 0)}: Längsnaht {naht.seite(profil, w)['text']}"
    return vorschlag(NAHT, titel, [pid], dict(pid=pid, winkel=w), hinweis=grund)


def winkel_innen(punkt, lage, netz, form):
    """Winkel (naht.py) der Wand bzw. Stelle, die zum Punkt zeigt, oder None (Punkt auf der Achse)."""
    from .baugruppe_ansicht import laengsnaht_winkel
    if punkt is None or not lage:
        return None
    return laengsnaht_winkel(punkt, lage, netz or {}, form)
