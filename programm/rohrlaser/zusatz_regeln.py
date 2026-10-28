"""Regeln für Zusatzarbeiten (Plan „Eigene Abrechnungsregeln“, Patrick 28.10.2026, Freigabe alle a).

Eine Regel (Stammdaten Arbeitsgang-Regeln) hat Bedingungen aus der Position (Merkmal bzw. Teileart, Stichwort, Profilform,
Abmessung, Werkstoff-Kategorie, Werkstoff, Oberfläche, Kunde, Stückzahl; leer = egal) und sagt, was dann gilt:
  Zuordnung   Vorschlag (wie bisher: „Arbeitsgänge vorschlagen …“, kostet erst nach Annehmen), automatisch (die
              Zusatzarbeit gilt ohne Klick, gelb markiert, abwählbar über Ablehnen) oder nur Preis (ordnet nichts zu)
  Preis       Abrechnung, Preis je Einheit, Menge aus (Bezug), Faktor und Mindestbetrag je Teil; leer = wie die
              Zusatzarbeit. Gilt für die Zusatzarbeit, gleich wie sie an die Position kam.
Passen mehrere Regeln, gewinnt die genaueste (meiste ausgefüllte Bedingungen), bei Gleichstand die obere.
Gewinde, Senken, Flowdrill und Bohren rechnen immer € je Stück (Regel Patrick): eine andere Abrechnung wird dort
nicht übernommen und in den Stammdaten als FEHLER gezeigt.

Alte Angebote bleiben unverändert: Regeln gelten nur für Zusatzarbeiten mit Preisstand ab dieser Version (Merker
'regeln' im Preisstand) und für automatische; festgeschriebene Angebote (Angebots-PDF) rechnen mit den Regeln, die beim
Festschreiben galten (rechnen.preisbasis_aus), Angebote von vorher ganz ohne Regeln.
"""
import json

from .angebot import ist_baugruppe, ist_zukaufteil, kein_laserteil

VORSCHLAG, AUTOMATISCH, NUR_PREIS = "Vorschlag", "automatisch", "nur Preis"
ZUORDNUNGEN = (VORSCHLAG, AUTOMATISCH, NUR_PREIS)
NUR_STUECK = ("gewinde", "senken", "flowdrill", "bohren")       # Regel Patrick: nur € je Stück
QUELLE = "Regel: "
BEDINGUNGEN = ("stichwort", "profilform", "kategorie", "werkstoff_id", "oberflaeche", "kundennr", "min_stueck", "a_von",
               "a_bis")


def nur_stueck(name):
    """True für Gewinde, Senken, Flowdrill und Bohren (immer € je Stück)."""
    return str(name or "").strip().lower() in NUR_STUECK


def _leer(w):
    return w in (None, "")


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def zuordnung(regel):
    return regel.get("zuordnung") if regel.get("zuordnung") in ZUORDNUNGEN else VORSCHLAG


def aktiv(regel):
    return regel.get("aktiv") != "nein" and not _leer(regel.get("zusatzarbeit"))


def _stichworte(text):
    return [w.strip().lower() for w in str(text or "").split(";") if w.strip()]


def anzahl_gewinde(p, gewinde):
    from . import rechnen
    return sum(rechnen.gewinde_anzahl(p.get("gewinde"), gewinde).values()) if p.get("gewinde") else 0.0


def anzahl_bohrungen(p):
    from .bohrbild import bohrungen_lesen
    return float(sum(n for _, n in bohrungen_lesen(p.get("bohrungen"))))


def anzahl_innen(p):
    return float(sum(int(p.get(n) or 0) for n in ("klein_n", "mittel_n", "gross_n")))


def ist_blech(p):
    """Blechteil aus dem Blech-Editor (Zukaufteil mit Blech-Daten)."""
    return ist_zukaufteil(p) and bool(p.get("technik"))


def merkmal_trifft(merkmal, p, gewinde):
    if merkmal in (None, "", "immer"):
        return True
    return {"Gewinde": lambda: anzahl_gewinde(p, gewinde) > 0 or bool(p.get("gewinde_vorschlag")),
            "Bohrungen": lambda: anzahl_bohrungen(p) > 0,
            "Innenkonturen": lambda: anzahl_innen(p) > 0 or float(p.get("innen") or 0) > 0,
            "Schräges Ende": lambda: not kein_laserteil(p) and "nein" in (p.get("a_gerade"), p.get("b_gerade")),
            "Zukaufteil": lambda: ist_zukaufteil(p),
            "Schweißbaugruppe": lambda: ist_baugruppe(p),
            "Rohr/Profil": lambda: not kein_laserteil(p),
            "Blech": lambda: ist_blech(p)}.get(merkmal, lambda: False)()


def abmessung(p, k):
    """Größtes Außenmaß des Profils [mm] (Ø bzw. Höhe a oder Breite b), None ohne Profil."""
    pr = (k.profile.get(p.get("profil_id")) if k else None) or {}
    werte = [w for w in (pr.get("a"), pr.get("b")) if isinstance(w, (int, float))]
    return max(werte) if werte else None


def trifft(regel, p, kopf, k, gewinde):
    """True, wenn die Position alle ausgefüllten Bedingungen der Regel erfüllt (leer = egal)."""
    from . import rechnen
    if not aktiv(regel):
        return False
    pr = (k.profile.get(p.get("profil_id")) if k else None) or {}
    proben = (("profilform", lambda: pr.get("form")),
              ("kategorie", lambda: rechnen.kategorie(p.get("werkstoff_id"), k) if k else None),
              ("werkstoff_id", lambda: p.get("werkstoff_id")), ("oberflaeche", lambda: p.get("oberflaeche")),
              ("kundennr", lambda: (kopf or {}).get("kundennr")))
    if any(not _leer(regel.get(n)) and regel[n] != wert() for n, wert in proben):
        return False
    if regel.get("min_stueck") and float(p.get("stueck") or 0) < float(regel["min_stueck"]):
        return False
    if not _leer(regel.get("a_von")) or not _leer(regel.get("a_bis")):
        a = abmessung(p, k)
        if a is None or not _leer(regel.get("a_von")) and a < _n(regel["a_von"]) \
                or not _leer(regel.get("a_bis")) and a > _n(regel["a_bis"]):
            return False
    worte = _stichworte(regel.get("stichwort"))
    if worte:
        text = " ".join(str(p.get(n) or "") for n in ("bezeichnung", "artikel")).lower()
        if not any(w in text for w in worte):
            return False
    return merkmal_trifft(regel.get("merkmal"), p, gewinde)


def genauigkeit(regel):
    """Anzahl ausgefüllter Bedingungen (Merkmal 'immer' zählt nicht)."""
    return sum(1 for n in BEDINGUNGEN if not _leer(regel.get(n))) + (regel.get("merkmal") not in (None, "", "immer"))


def preisrelevant(regel):
    """Regel mit eigenem Preis, Faktor, Mindestbetrag je Teil oder eigener Menge."""
    return any(not _leer(regel.get(n)) for n in ("preis", "faktor", "mindest_teil")) \
        or regel.get("menge_art") not in (None, "", "automatisch")


def beste(regeln):
    """Genaueste Regel, bei Gleichstand die obere (Reihenfolge der Liste)."""
    regeln = list(regeln)
    return max(regeln, key=genauigkeit) if regeln else None     # max: bei Gleichstand die erste


def preisregel(name, p, kopf, k, gewinde, regeln):
    """Regel, deren Preis für die Zusatzarbeit name an der Position gilt, oder None."""
    return beste(r for r in regeln or () if r.get("zusatzarbeit") == name and preisrelevant(r)
                 and trifft(r, p, kopf, k, gewinde))


def menge_bezug(bezug, art, p, k, gewinde):
    """Menge je Teil nach dem Bezug: None = automatisch nach der Abrechnung (rechnen.zusatz_menge_auto)."""
    from . import rechnen
    if bezug in (None, "", "automatisch"):
        return rechnen.zusatz_menge_auto(art, p, k)
    if bezug == "Innen- + Außenfläche":
        return rechnen.flaeche_innen_aussen(p, k)
    return {"Anzahl Gewinde": lambda: anzahl_gewinde(p, gewinde), "Anzahl Bohrungen": lambda: anzahl_bohrungen(p),
            "Anzahl Innenkonturen": lambda: anzahl_innen(p)}.get(bezug, lambda: None)()


def regel_menge(regel, p, gewinde):
    """Menge je Teil für einen angenommenen Vorschlag: None = automatisch (wie Zusatzarbeiten), sonst die gezählte
    Anzahl (Flächen rechnet die Zusatzarbeit selbst über die Preisregel)."""
    art = (regel or {}).get("menge_art") or "automatisch"
    return {"Anzahl Gewinde": lambda: anzahl_gewinde(p, gewinde), "Anzahl Bohrungen": lambda: anzahl_bohrungen(p),
            "Anzahl Innenkonturen": lambda: anzahl_innen(p)}.get(art, lambda: None)()


def abgelehnt(p):
    """Abgelehnte Vorschläge bzw. abgewählte automatische Zusatzarbeiten der Position."""
    try:
        d = json.loads(p.get("arbeitsgaenge") or "{}")
    except (TypeError, ValueError):
        d = {}
    return {x for x in (d.get("abgelehnt") or ()) if isinstance(x, str)} if isinstance(d, dict) else set()


def automatische(p, kopf, k, tabellen, vorhanden=()):
    """Automatische Zusatzarbeiten der Position: [{name, menge, preis, text, quelle, auto, regel, stand}] für Regeln
    mit Zuordnung 'automatisch', die zutreffen; ohne Namen, die die Position schon hat oder die abgewählt sind, und
    ohne unbekannte oder inaktive Zusatzarbeiten. stand = festgeschriebener Preisstand (Angebots-PDF) oder None."""
    regeln = [r for r in tabellen.get("arbeitsgang_regeln") or () if zuordnung(r) == AUTOMATISCH and aktiv(r)]
    if not regeln or ist_baugruppe(p):      # Baugruppe: Arbeitsgänge im Editor (katalog_mit_regel)
        return []
    katalog = {z.get("name"): z for z in tabellen.get("zusatzarbeiten") or ()}
    staende = tabellen.get("zusatz_auto_staende") or {}
    gewinde = tabellen.get("gewinde") or ()
    weg = set(vorhanden) | abgelehnt(p)
    out = {}
    for r in regeln:
        name = r["zusatzarbeit"]
        kz = katalog.get(name)
        if name in weg or name in out or (name not in staende and (kz is None or kz.get("aktiv") == "nein")):
            continue
        treffer = beste(x for x in regeln if x["zusatzarbeit"] == name and trifft(x, p, kopf, k, gewinde))
        if treffer:
            out[name] = dict(name=name, menge=None, preis=None, text=None, quelle=QUELLE + str(treffer.get("name")),
                             auto=True, regel=treffer.get("name"), stand=staende.get(name))
    return list(out.values())


def katalog_mit_regel(z, p, kopf, k, tabellen):
    """Zusatzarbeit der Stammdaten mit Abrechnung und Preis der passenden Regel (für Arbeitsgänge der
    Schweißbaugruppe aus den Zusatzarbeiten); ohne passende Regel unverändert."""
    r = preisregel(z.get("name"), p, kopf, k, tabellen.get("gewinde") or (), tabellen.get("arbeitsgang_regeln"))
    if not r:
        return z
    out = dict(z)
    if not _leer(r.get("preis")):
        out.update(preis=r["preis"], zeit=None, material=None, zuschlag_material=None, zuschlag_weitere=None)
        if not _leer(r.get("art")) and not nur_stueck(z.get("name")):
            out["art"] = r["art"]
    return out


def pruefung(z, k=None):
    """Prüfspalte der Regeln: Abrechnung ohne Preis, andere Abrechnung als € je Stück für Gewinde/Senken/Flowdrill/
    Bohren, Abmessung von > bis."""
    if not _leer(z.get("art")) and _leer(z.get("preis")):
        return "WARNUNG: Abrechnung ohne Preis je Einheit wird nicht übernommen (Preis eintragen)"
    if not _leer(z.get("art")) and z["art"] != "€/Stück" and nur_stueck(z.get("zusatzarbeit")):
        return f"FEHLER: {z.get('zusatzarbeit')} rechnet nur € je Stück"
    if not _leer(z.get("a_von")) and not _leer(z.get("a_bis")) and _n(z["a_von"]) > _n(z["a_bis"]):
        return "FEHLER: Abmessung von ist größer als bis"
    return None


def pruefung_zusatz(z, k=None):
    """Prüfspalte der Zusatzarbeiten: Gewinde/Senken/Flowdrill/Bohren nur € je Stück."""
    if nur_stueck(z.get("name")) and z.get("art") not in (None, "", "€/Stück"):
        return f"FEHLER: {z.get('name')} rechnet nur € je Stück"
    return None
