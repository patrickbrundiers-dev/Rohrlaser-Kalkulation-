"""Arbeitsgänge je Position und regelbasierte Vorschläge (Wettbewerbsvergleich P1-4).

Übersicht je Position: was das Angebot schon rechnet (Laser, Gewinde, Zusatzarbeiten, Zukauf) und was Regeln
(Stammdaten Arbeitsgang-Regeln) zusätzlich vorschlagen. Jede Zeile hat Arbeitsgang, Menge je Teil, Einheit, eigene
Zeit je Teil, Kostenart (Fertigung, Fremdleistung, Zukauf), Status und Herkunft:
  im Angebot – wird gerechnet (Gewinde aus 'Gewinde geprüft', Zusatzarbeiten der Position, Zukaufteil/-artikel)
  Vorschlag  – Regel trifft zu, wird NICHT gerechnet, bis er angenommen ist (betrag = voraussichtlich je Teil)
  abgelehnt  – Vorschlag, den jemand abgelehnt hat (bleibt sichtbar, kann zurückgenommen werden)
  zu prüfen  – Hinweis ohne Annahme per Knopf (z. B. Gewinde-Vorschlag aus dem Kernloch: in 'Bohrungen prüfen')

Doppelte Kosten gibt es nicht: Eine Zusatzarbeit, die die Position schon hat, wird nie vorgeschlagen; schlagen
mehrere Regeln dieselbe Zusatzarbeit vor, entsteht ein Vorschlag mit allen Regeln als Herkunft. Annehmen trägt die
Zusatzarbeit mit Preisstand (rechnen.zusatz_stand) und quelle 'Regel: …' in positionen.zusatz ein, die Rechnung
bleibt die der Zusatzarbeiten. Abgelehnte Vorschläge stehen in positionen.arbeitsgaenge als {"abgelehnt": [Name]}.
"""
import json

from . import rechnen, zukauf
from . import zusatz_regeln as zr
from .angebot import ist_baugruppe, ist_zukaufteil, kein_laserteil

IM_ANGEBOT, VORSCHLAG, ABGELEHNT, ZU_PRUEFEN = "im Angebot", "Vorschlag", "abgelehnt", "zu prüfen"
AUTOMATISCH = "automatisch"     # Regel mit Zuordnung automatisch: wird gerechnet, abwählbar (Ablehnen)
FERTIGUNG, FREMD, ZUKAUF = "Fertigung", "Fremdleistung", "Zukauf"
QUELLE = "Regel: "


def lesen(p):
    """{'abgelehnt': [Zusatzarbeit]} der Position (leer bei fehlenden oder kaputten Daten)."""
    try:
        d = json.loads(p.get("arbeitsgaenge") or "{}")
    except (TypeError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    d["abgelehnt"] = [x for x in d.get("abgelehnt") or () if isinstance(x, str)]
    return d


# Bedingungen und Mengen stehen in zusatz_regeln.py (auch für Preisregeln und automatische Zusatzarbeiten)
anzahl_gewinde, anzahl_bohrungen, anzahl_innen = zr.anzahl_gewinde, zr.anzahl_bohrungen, zr.anzahl_innen
trifft, regel_menge = zr.trifft, zr.regel_menge


def _zeile(p, arbeitsgang, status, kostenart, herkunft, menge=None, einheit="", zeit=0.0, betrag=None, regeln=()):
    return dict(position_id=p.get("id"), pos=p.get("pos"), artikel=p.get("artikel"), arbeitsgang=arbeitsgang,
                menge=menge, einheit=einheit, zeit=zeit, kostenart=kostenart, status=status, herkunft=herkunft,
                betrag=betrag, regeln=list(regeln))


def position(p, kopf, k, tabellen, regeln):
    """Zeilen der Übersicht für eine Position (siehe Moduldoku)."""
    out = []
    gewinde = tabellen.get("gewinde") or ()
    if not kein_laserteil(p) and p.get("profil_id"):
        out.append(_zeile(p, "Laser schneiden", IM_ANGEBOT, FERTIGUNG, "Angebot", 1.0, "Stück"))
    if ist_zukaufteil(p):
        out.append(_zeile(p, "Zukaufteil", IM_ANGEBOT, ZUKAUF, "Angebot", 1.0, "Stück"))
    elif zukauf.json_liste(p.get("zukauf")):
        out.append(_zeile(p, "Zukaufartikel", IM_ANGEBOT, ZUKAUF, "Angebot",
                          float(len(zukauf.json_liste(p.get("zukauf")))), "Artikel"))
    if ist_baugruppe(p):
        out.append(_zeile(p, "Schweißbaugruppe", IM_ANGEBOT, FERTIGUNG, "Angebot", 1.0, "Stück"))
    preise = rechnen.gewinde_preise_position(p)
    for g in gewinde:
        n = rechnen.gewinde_anzahl(p.get("gewinde"), [g]).get(g.get("gewinde"), 0) if p.get("gewinde") else 0
        if n:
            out.append(_zeile(p, f"Gewinde {g['gewinde']}", IM_ANGEBOT, FERTIGUNG, "Gewinde geprüft", n, "Stück",
                              betrag=n * rechnen._n(preise.get(g["gewinde"], g.get("preis")))))
    if p.get("gewinde_vorschlag") and not p.get("gewinde"):
        out.append(_zeile(p, f"Gewinde {p['gewinde_vorschlag']}", ZU_PRUEFEN, FERTIGUNG,
                          "Kernloch im STEP (in „Bohrungen prüfen“ bestätigen)"))
    vorhanden = set()
    for z in rechnen.zusatz_werte(p, k, tabellen, kopf):
        vorhanden.add(z["name"])
        herkunft = (z["quelle"] or "Zusatzarbeiten") + (f" · Preis: Regel {z['regel']}" if z["regel"] and
                                                       not z["auto"] else "")
        out.append(_zeile(p, z["name"], AUTOMATISCH if z["auto"] else IM_ANGEBOT, FREMD if z["fremd"] else FERTIGUNG,
                          herkunft, z["menge"], z["einheit"], z["arbeit_s"], z["betrag"] + z["pauschal"],
                          [z["regel"]] if z["auto"] and z["regel"] else ()))
    vorhanden |= {e["name"] for e in rechnen.zusatz_liste(p)}
    abgelehnt = set(lesen(p)["abgelehnt"])
    katalog = {z.get("name"): z for z in tabellen.get("zusatzarbeiten") or ()}
    vorschlaege = {}
    for r in regeln or ():
        name = r.get("zusatzarbeit")
        if zr.zuordnung(r) == zr.NUR_PREIS or name in vorhanden or name not in katalog \
                or katalog[name].get("aktiv") == "nein" or not trifft(r, p, kopf, k, gewinde):
            continue
        # automatisch und nicht abgewählt steht schon oben; abgewählt bleibt als abgelehnt sichtbar
        if zr.zuordnung(r) == zr.AUTOMATISCH and name not in abgelehnt:
            continue
        vorschlaege.setdefault(name, []).append(r)
    for name, rs in vorschlaege.items():
        menge = regel_menge(rs[0], p, gewinde)
        probe = dict(p, zusatz=json.dumps([eintrag(name, rs[0], menge, katalog, tabellen)], ensure_ascii=False),
                     arbeitsgaenge=None)
        z = (rechnen.zusatz_werte(probe, k, dict(tabellen, arbeitsgang_regeln=[r for r in tabellen.get(
            "arbeitsgang_regeln") or () if zr.zuordnung(r) != zr.AUTOMATISCH]), kopf) or [None])[0]
        out.append(_zeile(p, name, ABGELEHNT if name in abgelehnt else VORSCHLAG,
                          FREMD if katalog[name].get("fremd") == "ja" else FERTIGUNG,
                          ", ".join(QUELLE + r["name"] for r in rs), z and z["menge"], z and z["einheit"] or "",
                          z["arbeit_s"] if z else 0.0, z and (z["betrag"] + z["pauschal"]), [r["name"] for r in rs]))
    return out


def uebersicht(kopf, positionen, k, tabellen, regeln):
    """Zeilen für alle Positionen des Angebots."""
    return [z for p in positionen for z in position(p, kopf, k, tabellen, regeln)]


def eintrag(name, regel, menge, katalog, tabellen):
    """Zusatzarbeit-Eintrag für positionen.zusatz (mit Preisstand und Herkunft der Regel)."""
    e = dict(name=name, menge=menge, preis=None, text=None, quelle=QUELLE + (regel or {}).get("name", ""),
             stand=rechnen.zusatz_stand(katalog[name], rechnen.stundensaetze(tabellen)))
    return e


def annehmen(p, name, regeln, tabellen, kopf=None, k=None):
    """Neuer Inhalt für positionen.zusatz mit der angenommenen Zusatzarbeit; unverändert (None), wenn sie schon da ist
    oder unbekannt ist. Menge und Herkunft aus der ersten Regel, die auf die Position zutrifft (wie im Vorschlag);
    ohne Kontext k die erste Regel mit dieser Zusatzarbeit."""
    liste = rechnen.zusatz_liste(p)
    katalog = {z.get("name"): z for z in tabellen.get("zusatzarbeiten") or ()}
    if name in {e["name"] for e in liste} or name not in katalog:
        return None
    gewinde = tabellen.get("gewinde") or ()
    passend = [r for r in regeln or () if r.get("zusatzarbeit") == name]
    regel = next((r for r in passend if k is None or trifft(r, p, kopf, k, gewinde)), None)
    menge = regel_menge(regel or {}, p, gewinde)
    return json.dumps(liste + [eintrag(name, regel, menge, katalog, tabellen)], ensure_ascii=False)


def ablehnen(p, name, zurueck=False):
    """Neuer Inhalt für positionen.arbeitsgaenge: Vorschlag abgelehnt bzw. Ablehnung zurückgenommen."""
    d = lesen(p)
    liste = [x for x in d["abgelehnt"] if x != name] + ([] if zurueck else [name])
    d["abgelehnt"] = liste
    return json.dumps(d, ensure_ascii=False) if liste or len(d) > 1 else None


def summen(zeilen):
    """{Kostenart: € je Teil} der gerechneten Zeilen (im Angebot, auch automatische) und der offenen Vorschläge
    getrennt."""
    out = {IM_ANGEBOT: {}, VORSCHLAG: {}}
    for z in zeilen:
        st = IM_ANGEBOT if z["status"] == AUTOMATISCH else z["status"]
        if st in out and isinstance(z["betrag"], (int, float)):
            out[st][z["kostenart"]] = out[st].get(z["kostenart"], 0.0) + z["betrag"]
    return out
