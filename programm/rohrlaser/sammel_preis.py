"""Sammel-Preisprüfung offener Angebote (Vorschlag H1a, 02.11.2026).

Alle verschickten, noch gültigen, eigenen Angebote mit festgeschriebenen Preisen (preisbasis) werden einmal mit den
festgeschriebenen und einmal mit den aktuellen Stammdaten (Materialpreise, Schneiddaten, Stundensätze) gerechnet;
Abweichung in € und %, größte zuerst. „Neue Fassung für markierte“ legt je markiertem Angebot eine neue Fassung mit
aktuellen Preisen an (Datenbank.angebot_fassung). Ohne Qt."""
import datetime

from . import preis_simulator, rechnen


def _gueltig_bis(a, tage):
    try:
        return datetime.date.fromisoformat(a.get("datum") or "") + datetime.timedelta(days=int(tage or 0))
    except (TypeError, ValueError):
        return None


def pruefen(db, heute=None, fortschritt=None):
    """[dict(id, nummer, kunde, datum, gueltig_bis, alt, neu, abweichung, prozent)] nach |Abweichung| absteigend;
    Angebote ohne Schnittplan fehlen."""
    heute = heute or datetime.date.today()
    tage = db.einstellung("gueltigkeit") or 30
    aktuell, einst = (db.kontext(), db.tabellen()), db.einstellungen()
    kandidaten = [z for z in db.angebote() if z.get("vorgang") == "Verschickt" and not z.get("fremd")
                  and not z.get("ersetzt_durch")]
    out = []
    for i, z in enumerate(kandidaten):
        if fortschritt:
            fortschritt(i, len(kandidaten))
        a = db.angebot(z["id"])
        bis = _gueltig_bis(a, tage)
        if not a or not a.get("preisbasis") or not a.get("ergebnis") or (bis and bis < heute):
            continue
        pos = db.positionen(a["id"])
        try:
            k, tab, e = preis_simulator.grundlage(db, a, aktuell, einst)
            alt = rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)[1]["verkauf"]
            a2 = dict(a, preisbasis=None, zeitbasis=None)
            k2, tab2, e2 = preis_simulator.grundlage(db, a2, aktuell, einst)
            neu = rechnen.kalkulation(a2, pos, a["ergebnis"], k2, tab2, e2)[1]["verkauf"]
        except (ValueError, KeyError, ZeroDivisionError, TypeError):
            continue
        out.append(dict(id=a["id"], nummer=a.get("nummer"), kunde=a.get("kunde"), datum=a.get("datum"),
                        gueltig_bis=bis.isoformat() if bis else "", alt=alt, neu=neu, abweichung=neu - alt,
                        prozent=(neu / alt - 1) if alt else None))
    return sorted(out, key=lambda r: -abs(r["abweichung"]))


def neue_fassungen(db, ids):
    """Je ID eine neue Fassung mit aktuellen Preisen. Ergebnis: [neue IDs]."""
    return [db.angebot_fassung(i) for i in ids]
