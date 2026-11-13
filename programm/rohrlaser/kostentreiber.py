"""Kostentreiber über alle Aufträge (CALC-030, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale).

Wertet die beauftragten Angebote eines Zeitraums aus: je Bearbeitungsart (Bearbeitungsliste X1: Anfangs-/Endschnitt,
Bohrung, Langloch, Ausschnitt …, Gravur, Ecken …) und je Abmessung (Profil) die Laserzeit und die Kosten über alle
Teile, dazu je Abmessung die Abweichung Ist gegen Soll der Laufzeit aus der Nachkalkulation (nur wo Ist-Werte
erfasst sind). Jede Zeile nennt die Anzahl der Aufträge (wenig Daten = wenig Aussage). Top 10 nach Kosten.
Jedes Angebot wird mit seinem festgeschriebenen Stand (preisbasis_anwenden) und seinem gespeicherten Schnittplan
gerechnet; ohne Schnittplan zählt es als „nicht gerechnet“. Ändert nichts. Ohne Qt."""
import datetime

from . import bearbeitung, rechnen

TOP = 10
ZEITRAUM = 365


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _vorgang(z):
    from .cockpit import _vorgang
    return _vorgang(z)


def _art(zeile):
    """Bearbeitungsart einer Zeile der Bearbeitungsliste (ohne Nummer und Maße)."""
    art = zeile.get("art") or "?"
    if art == bearbeitung.ENDE:
        return "Anfangs-/Endschnitt"
    if art in (bearbeitung.REST, bearbeitung.ABGLEICH, bearbeitung.HAND):
        return str(zeile.get("text") or art)
    return str(art)


def auftraege(db, heute=None, zeitraum=ZEITRAUM):
    """Beauftragte eigene Angebote (ohne ersetzte Fassungen) im Zeitraum (Tage, None = alle)."""
    from . import absage
    return [z for z in absage.auswahl(db.angebote(), heute, zeitraum) if _vorgang(z) == "Beauftragt"]


def auswertung(db, heute=None, zeitraum=ZEITRAUM, top=TOP):
    """dict(arten=[dict(name, s, eur, teile, auftraege)], abmessungen=[dict(name, s, eur, teile, auftraege,
    soll_s, ist_s, abweichung, n_ist)], auftraege, gerechnet, nicht_gerechnet, summe_eur, summe_s). arten/abmessungen
    sind die Top-N nach Kosten; die Summen gelten über alle Zeilen (auch außerhalb der Top-N)."""
    from . import nachkalkulation
    liste = auftraege(db, heute or datetime.date.today(), zeitraum)
    k0, t0 = db.kontext(), db.tabellen()
    e0 = db.einstellungen()
    arten, abm = {}, {}
    gerechnet = nicht = 0
    sum_eur = sum_s = 0.0
    for a in liste:
        kopf = db.angebot(a["id"]) or {}
        pos = db.positionen(a["id"])
        erg = kopf.get("ergebnis")
        if not erg or not pos:
            nicht += 1
            continue
        try:
            k, tab = rechnen.preisbasis_anwenden(kopf, k0, t0)
            einst = rechnen.einstellungen_angebot(kopf, rechnen.einstellungen_fest(tab, e0))
            zeilen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)[0]
        except Exception:           # noqa: BLE001 – ein altes Angebot, das nicht mehr rechnet, zählt nicht mit
            nicht += 1
            continue
        gerechnet += 1
        for p, z in zip(pos, zeilen):
            if not z or z.get("laser_netto") is None:
                continue
            c = _n(z.get("stueck"))
            try:
                bl = bearbeitung.fuer_position(p, z, kopf, k, tab)
            except Exception:       # noqa: BLE001
                bl = []
            for b in bl:
                g = arten.setdefault(_art(b), dict(s=0.0, eur=0.0, teile=0.0, ids=set()))
                g["s"] += _n(b.get("s")) * c
                g["eur"] += _n(b.get("eur")) * c
                g["teile"] += c
                g["ids"].add(a["id"])
            s_teil = _n(z.get("laser_netto"))
            eur_teil = _n(z.get("laser_schneiden_teil")) + _n(z.get("schneidgas_teil"))
            sum_s += s_teil * c
            sum_eur += eur_teil * c
            g = abm.setdefault(p.get("profil_id") or "?", dict(s=0.0, eur=0.0, teile=0.0, ids=set(), soll_s=0.0,
                                                               ist_s=0.0, n_ist=0))
            g["s"] += s_teil * c
            g["eur"] += eur_teil * c
            g["teile"] += c
            g["ids"].add(a["id"])
    # Ist gegen Soll je Abmessung aus der Nachkalkulation (Laufzeit je Teil)
    try:
        fl = nachkalkulation.faelle(db)[0]
    except Exception:               # noqa: BLE001
        fl = []
    profil_je_id = {}
    for a in liste:
        for p in db.positionen(a["id"]):
            profil_je_id[str(p.get("id"))] = p.get("profil_id") or "?"
    for f in fl:
        je = f["ist"].get("laufzeit") or {}
        for pid, soll_s, _ in f["soll"].get("laufzeit") or ():
            ist_s = je.get(str(pid))
            name = profil_je_id.get(str(pid))
            if name in abm and isinstance(ist_s, (int, float)) and _n(soll_s):
                abm[name]["soll_s"] += _n(soll_s)
                abm[name]["ist_s"] += float(ist_s)
                abm[name]["n_ist"] += 1

    def fertig(d, mit_ist=False):
        out = []
        for name, g in d.items():
            x = dict(name=name, s=g["s"], eur=g["eur"], teile=g["teile"], auftraege=len(g["ids"]))
            if mit_ist:
                x.update(soll_s=g["soll_s"], ist_s=g["ist_s"], n_ist=g["n_ist"],
                         abweichung=(g["ist_s"] / g["soll_s"] - 1) if g["soll_s"] else None)
            out.append(x)
        return sorted(out, key=lambda x: -x["eur"])
    alle_arten = fertig(arten)
    alle_abm = fertig(abm, True)
    return dict(arten=alle_arten[:top], abmessungen=alle_abm[:top], auftraege=len(liste), gerechnet=gerechnet,
                nicht_gerechnet=nicht, summe_eur=sum_eur, summe_s=sum_s,
                summe_arten_eur=sum(x["eur"] for x in alle_arten), summe_abm_eur=sum(x["eur"] for x in alle_abm))
