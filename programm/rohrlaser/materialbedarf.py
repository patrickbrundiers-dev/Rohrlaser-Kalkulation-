"""Wöchentlicher Sammelbedarf an Material (MAT-018, Plan Phase 3 und 4, Paket D, Patrick 13.11.2026 „Alles einbauen“;
kein Restelager).

Über alle beauftragten Aufträge, deren Material noch nicht bereit ist (Fertigungsstatus vor „Material bereit“ bzw.
noch nicht freigegeben), je Woche des Liefertermins (ohne Termin: eigene Zeile) und je Abmessung (Profil, Werkstoff,
Oberfläche, Stangenlänge): Stangen und Gewicht laut Schnittplan der Aufträge, die Aufträge selbst und der Rest, der
auf den Stangen übrig bleibt. Kundenmaterial zählt nicht. Reste werden nur gemeldet (Länge in m), nicht eingelagert
und nicht verrechnet. Nur Anzeige und CSV, bestellt wird wie bisher über die Materialanfrage. Ohne Qt."""
import datetime

from . import fertigung

OHNE_TERMIN = "ohne Termin"
FERTIG_AB = "Material bereit"   # ab diesem Status (und allen danach) ist das Material da


def _woche(iso):
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return OHNE_TERMIN, None
    j, kw, _ = d.isocalendar()
    montag = d - datetime.timedelta(days=d.weekday())
    return f"KW {kw:02d}/{j}", montag


def _offen(db, angebot_id):
    """Material noch nicht bereit: kein Status, freigegeben oder Arbeitsvorbereitung (vor FERTIG_AB)."""
    liste = fertigung.status_liste(db)
    z = fertigung.aktuell(db, angebot_id)
    if not z:
        return True
    if FERTIG_AB not in liste or z["status"] not in liste:
        return True
    return liste.index(z["status"]) < liste.index(FERTIG_AB)


def bedarf(db, alle=False):
    """[dict(woche, montag, profil, werkstoff, oberflaeche, stange, stangen, gewicht, rest_m, auftraege [Nummern])]
    nach Woche (ohne Termin zuletzt), dann Profil. alle=True: auch Aufträge mit Material bereit."""
    from . import preis_simulator, rechnen
    aktuell = (db.kontext(), db.tabellen())
    out = {}
    for a in db.angebote():
        if a.get("vorgang") != "Beauftragt" or a.get("fremd") or (not alle and not _offen(db, a["id"])):
            continue
        kopf = db.angebot(a["id"])
        erg = (kopf or {}).get("ergebnis") or {}
        if not erg.get("stangen"):
            continue
        pos = db.positionen(a["id"])
        try:
            k, tab, _ = preis_simulator.grundlage(db, kopf, aktuell)
            werte = rechnen.stangen_werte(erg, kopf, pos, k, tab)
        except Exception:           # noqa: BLE001 – ohne Werte: Stangen ja, Gewicht und Rest leer
            werte = [None] * len(erg["stangen"])
        woche, montag = _woche(kopf.get("liefertermin"))
        for s, w in zip(erg["stangen"], list(werte) + [None] * len(erg["stangen"])):
            if s.get("beistellung"):
                continue
            schl = (woche, s["profil"], s["werkstoff"], s.get("oberflaeche") or "", s["stange"])
            z = out.setdefault(schl, dict(woche=woche, montag=montag, profil=s["profil"], werkstoff=s["werkstoff"],
                                          oberflaeche=s.get("oberflaeche") or "", stange=s["stange"], stangen=0,
                                          gewicht=0.0, rest_m=0.0, auftraege=[]))
            z["stangen"] += 1
            g = (w or {}).get("gewicht")
            z["gewicht"] = z["gewicht"] + g if isinstance(g, (int, float)) and z["gewicht"] is not None else None
            belegt = (w or {}).get("belegt")
            z["rest_m"] = (z["rest_m"] + max(0.0, s["stange"] - belegt) / 1000
                           if isinstance(belegt, (int, float)) and z["rest_m"] is not None else None)
            if a.get("nummer") not in z["auftraege"]:      # Reihenfolge der Angebotsliste (neueste zuerst)
                z["auftraege"].append(a.get("nummer"))
    return sorted(out.values(), key=lambda z: (z["montag"] is None, z["montag"] or datetime.date.min, z["profil"],
                                               z["werkstoff"], z["stange"]))


def csv_text(zeilen):
    """CSV (Semikolon, Komma als Dezimalzeichen) für Excel."""
    def zahl(w, n):
        return "" if w is None else f"{w:.{n}f}".replace(".", ",")
    kopf = "Woche;Profil;Werkstoff;Oberfläche;Stangenlänge [mm];Stangen;Gewicht [kg];Rest [m];Aufträge"
    return "\n".join([kopf] + [";".join((z["woche"], z["profil"], z["werkstoff"], z["oberflaeche"],
                                         zahl(z["stange"], 0), str(z["stangen"]), zahl(z["gewicht"], 1),
                                         zahl(z["rest_m"], 2), ", ".join(str(x) for x in z["auftraege"])))
                               for z in zeilen]) + "\n"
