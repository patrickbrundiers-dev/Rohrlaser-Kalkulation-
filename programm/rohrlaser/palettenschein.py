"""Palettenbegleitschein und Versand je beauftragtem Angebot (Plan Palettenbegleitschein, Patrick 24.10.2026,
Freigabe „a a a a a a a a b a“; Vorbild: eigenes Tool „Palettenbegleitschein v97“).

Daten (JSON in angebote.palettenschein, leer = noch nichts erfasst; Kopie und neue Fassung übernehmen sie nicht):
  paletten_auto  True (Vorgabe): Anzahl und Inhalt je Palette aus der Packliste (paletten.packen)
  paletten       Anzahl von Hand (paletten_auto False)
  unbekannt      Anzahl noch nicht bekannt: Schein ohne „Palette x / n“, Menge zum Eintragen
  stueck_text    Stück pro Palette von Hand wie im Tool: '100' (jede Palette), '100, 100, 50', '3x80, 10'
  max_je         {Positions-ID: max. Stück je Palette} (ersetzt den Packraum dieser Position)
  arbeiten       ['Gruppe::Schritt', …] für den Ausdruck; None = Vorschlag aus dem Angebot (vorschlag_arbeiten)
  status         ['Auftrag vollständig', …] (STATUS); 'Versendet' = Abschluss, setzt versendet_am
  hinweis        Text (lange Hinweise werden kleiner gedruckt)
  gedruckt_am, versendet_am (ISO-Datum), archiviert (bool)
Auftrag = Angebotsnummer, Bestellnummer = Auftragsnummer des Kunden (Beauftragt), Lieferdatum = Liefertermin.
"""
import datetime
import json
import re

from . import blech, rechnen
from .angebot import ZUKAUFTEIL, ist_baugruppe, kein_laserteil
from .stammdaten import VERSAND_SCHRITTE

STATUS = ("Auftrag unvollständig", "Nacharbeit erforderlich", "Auftrag vollständig", "Endkontrolle OK",
          "Fertig zur Verladung", "Versendet")
VERLADEBEREIT, VERSENDET = "Fertig zur Verladung", "Versendet"
TRENNER = "::"


def leer():
    return dict(paletten_auto=True, paletten=None, unbekannt=False, stueck_text="", max_je={}, arbeiten=None,
                status=[], hinweis="", gedruckt_am=None, versendet_am=None, archiviert=False)


def lesen(text):
    """Gespeicherte Daten (mit allen Schlüsseln) aus angebote.palettenschein."""
    d = leer()
    try:
        roh = json.loads(text) if isinstance(text, str) and text else text
    except ValueError:
        roh = None
    if isinstance(roh, dict):
        d.update({k: v for k, v in roh.items() if k in d})
    d["status"] = [s for s in d.get("status") or () if s in STATUS]
    d["max_je"] = {str(k): v for k, v in (d.get("max_je") or {}).items() if isinstance(v, int) and v >= 1}
    return d


def speichern(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def schluessel(gruppe, schritt):
    return f"{gruppe}{TRENNER}{schritt}"


def schritte(text=None):
    """Arbeitsschritte aus der Einstellung 'versand_schritte': {Gruppe: [Schritt, …]} in Eingabereihenfolge.
    Zeilen ohne 'Gruppe:' gehören zur Gruppe 'Intern'."""
    out = {}
    for zeile in str(VERSAND_SCHRITTE if text is None else text).splitlines():
        if not zeile.strip():
            continue
        g, sep, s = zeile.partition(":")
        g, s = (g.strip(), s.strip()) if sep else ("Intern", g.strip())
        if s and s not in out.setdefault(g or "Intern", []):
            out[g or "Intern"].append(s)
    return out


def _treffer(name, gruppen):
    """[(Gruppe, Schritt)], deren Schritt im Namen der Zusatzarbeit steht oder umgekehrt."""
    n = name.lower()
    return [(g, s) for g, liste in gruppen.items() for s in liste if s.lower() in n or n in s.lower()]


def _waehlen(treffer, fremd):
    """Oberfläche vor Extern (fremd) bzw. Intern (eigen), sonst der erste Treffer."""
    for g, s in treffer:
        if g.lower().startswith("oberfl"):
            return g, s
    vorrang = "extern" if fremd else "intern"
    for g, s in treffer:
        if g.lower() == vorrang:
            return g, s
    return treffer[0] if treffer else None


def vorschlag_arbeiten(positionen, tabellen, gruppen):
    """Arbeitsschritte aus dem Angebot (F7a): Rohrlaser bei Rohrlaserteilen, Zusatzarbeiten nach ihrem Namen
    (Gewinde, Senken, Flowdrill, Bohren, Biegen, Feuerverzinken …; Fremdleistung -> Extern), Schweißen bei
    Schweißbaugruppen, Blechzukauf bei Blechen. Ergebnis: Liste 'Gruppe::Schritt' in der Reihenfolge der Liste."""
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    gewaehlt = set()

    def setzen(name, fremd=False):
        t = _waehlen(_treffer(name, gruppen), fremd)
        if t:
            gewaehlt.add(schluessel(*t))

    for p in positionen:
        if not kein_laserteil(p) and p.get("profil_id"):
            setzen("Rohrlaser")
        if ist_baugruppe(p):
            setzen("Schweißen")
        if p.get("art") == ZUKAUFTEIL and blech.lesen(p.get("technik")):
            setzen("Blechzukauf", True)
        for z in rechnen.zusatz_liste(p):
            setzen(z["name"], (katalog.get(z["name"]) or {}).get("fremd") == "ja")
    return [schluessel(g, s) for g, liste in gruppen.items() for s in liste if schluessel(g, s) in gewaehlt]


def stammdaten(db):
    """Stammdaten für zusammenstellen (für viele Aufträge nur einmal lesen)."""
    return dict(k=db.kontext(), tab=db.tabellen(), einst=db.einstellungen(), lht=db.fracht_daten().get("lht", []))


def zusammenstellen(db, angebot_id, d=None, stamm=None):
    """Alles für Fenster und Ausdruck eines Angebots: dict(kopf, positionen, werte, schein, packliste, gruppen,
    einst). d = Versanddaten (sonst gespeicherte); ohne gewählte Arbeitsschritte gilt der Vorschlag."""
    from . import paletten
    from .angebot import aktiv
    kopf = db.angebot(angebot_id)
    pos = db.positionen(angebot_id)
    stamm = stamm or stammdaten(db)
    k, tab, einst = stamm["k"], stamm["tab"], stamm["einst"]
    werte = [rechnen.position_werte(p, kopf, k, tab) if aktiv(p) else None for p in pos]
    d = d if d is not None else db.palettenschein(angebot_id)
    gruppen = schritte(einst.get("versand_schritte"))
    if d.get("arbeiten") is None:
        d["arbeiten"] = vorschlag_arbeiten(pos, tab, gruppen)
    packliste = paletten.packen(pos, werte, stamm["lht"], einst.get("fracht_lht_standard"),
                                einst.get("fracht_lht_langgut"), einst, d.get("max_je"))
    return dict(kopf=kopf, positionen=pos, werte=werte, schein=d, packliste=packliste, gruppen=gruppen,
                einst=einst)


# ------------------------------------------------------------------ Stück pro Palette (von Hand)
def stueck_liste(text, total):
    """'100' (jede Palette), '100, 100, 50' (je Palette), '3x80, 10' (3 Paletten à 80, dann 10).
    Ergebnis: None (leer), {'fehler': True} oder {werte (je Palette oder None), anzahl, einzeln, summe}."""
    t = re.sub(r"\s*[x×*]\s*", "x", str(text or "").strip(), flags=re.I)
    if not t:
        return None
    tokens = [x for x in re.split(r"[;,\s]+", t) if x]
    nums = []
    for tok in tokens:
        m = re.fullmatch(r"(\d+)x(\d+)", tok)
        if m:
            n = int(m.group(1))
            if not 1 <= n <= 500:
                return dict(fehler=True)
            nums += [int(m.group(2))] * n
        elif re.fullmatch(r"\d+", tok):
            nums.append(int(tok))
        else:
            return dict(fehler=True)
    if len(tokens) == 1 and re.fullmatch(r"\d+", tokens[0]):
        return dict(werte=[nums[0]] * total, anzahl=1, einzeln=True, summe=nums[0] * total)
    return dict(werte=[nums[i] if i < len(nums) else None for i in range(total)], anzahl=len(nums), einzeln=False,
                summe=sum(nums))


def verteilen(stueck, total):
    """Gleichmäßig verteilen wie im Tool: 250 auf 3 -> '1x84, 2x83' (bzw. '84, 2x83'). ValueError, wenn es nicht geht."""
    if total < 1 or stueck < total:
        raise ValueError(f"{stueck} Stück lassen sich nicht auf {total} Paletten verteilen.")
    basis, rest = divmod(stueck, total)
    if not rest:
        return str(basis)
    text = f"{rest}x{basis + 1}, {total - rest}x{basis}"
    return re.sub(r", 1x", ", ", re.sub(r"^1x", "", text))


# ------------------------------------------------------------------ Druckseiten
def anzahl(d, packliste):
    """Anzahl Paletten (None = noch nicht bekannt)."""
    if d.get("unbekannt"):
        return None
    if d.get("paletten_auto"):
        return packliste["anzahl"] if packliste and packliste["anzahl"] else None
    n = d.get("paletten")
    return n if isinstance(n, int) and n >= 1 else None


def seiten(kopf, d, packliste, gruppen, heute=None):
    """Je Palette ein Schein: [{auftrag, kunde, bestellnummer, lieferdatum, nr, gesamt, stueck (auf der Palette
    oder None), auftragsmenge, inhalt [(Pos., Artikelnummer, Bezeichnung, Stück)], arbeiten {Gruppe: [Schritt]},
    status, hinweis, datum, lht, gewicht (brutto kg oder None)}]. Ohne bekannte Anzahl ein Schein ohne
    Paletten-Nummer."""
    heute = heute or datetime.date.today()
    gesamt = anzahl(d, packliste)
    menge = (packliste or {}).get("gesamt_stueck")
    gewaehlt = set(d.get("arbeiten") or ())
    arbeiten = {g: [s for s in liste if schluessel(g, s) in gewaehlt] for g, liste in gruppen.items()}
    for k in d.get("arbeiten") or ():          # Schritte, die nicht (mehr) in der Liste stehen
        g, _, s = k.partition(TRENNER)
        if s and s not in arbeiten.setdefault(g, []) and s not in (gruppen.get(g) or ()):
            arbeiten[g].append(s)
    arbeiten = {g: liste for g, liste in arbeiten.items() if liste}
    basis = dict(auftrag=kopf.get("nummer") or "", kunde=kopf.get("kunde") or "",
                 bestellnummer=kopf.get("auftragsnr") or "", lieferdatum=kopf.get("liefertermin"),
                 auftragsmenge=menge, arbeiten=arbeiten,
                 status=[s for s in STATUS if s in (d.get("status") or ())], hinweis=d.get("hinweis") or "",
                 datum=heute.isoformat(), gesamt=gesamt)
    if not gesamt:
        return [dict(basis, nr=None, stueck=None, inhalt=[], lht="", gewicht=None)]
    out = []
    pals = (packliste or {}).get("paletten") or []
    hand = stueck_liste(d.get("stueck_text"), gesamt) if not d.get("paletten_auto") else None
    for nr in range(1, gesamt + 1):
        inhalt, stueck, lht, gewicht = [], None, "", None
        if d.get("paletten_auto") and nr <= len(pals):
            pal = pals[nr - 1]
            st = packliste["stuecke"]
            inhalt = [(st[k]["pos"], st[k]["artikel"], st[k]["bezeichnung"], n) for k, n in pal["inhalt"]]
            stueck = sum(n for _, n in pal["inhalt"])
            lht = pal["bezeichnung"]
            gewicht = pal["brutto"] if pal["netto"] > 0 else None
        elif hand and not hand.get("fehler"):
            stueck = hand["werte"][nr - 1]
        elif gesamt == 1:
            stueck = menge
        out.append(dict(basis, nr=nr, stueck=stueck, inhalt=inhalt, lht=lht, gewicht=gewicht))
    return out


def hinweis_stufe(text):
    """Wie groß wird der Hinweis gedruckt: 'leer', 'normal', 'klein', 'sehr klein', 'zu lang' (wie im Tool)."""
    def zeilen(cpl):
        return sum(max(1, -(-len(z) // cpl)) for z in str(text or "").split("\n"))
    if not str(text or "").strip():
        return "leer"
    if zeilen(50) <= 5:
        return "normal"
    if zeilen(62) <= 6:
        return "klein"
    if zeilen(74) <= 8:
        return "sehr klein"
    return "zu lang"


# ------------------------------------------------------------------ Versandübersicht
def ist_versendet(d):
    return VERSENDET in (d.get("status") or ())


def ist_verladebereit(d):
    return VERLADEBEREIT in (d.get("status") or ()) and not ist_versendet(d)


def stand(d):
    """Kurzer Stand für die Liste: letzter erreichter Status oder 'offen'."""
    st = [s for s in STATUS if s in (d.get("status") or ())]
    return st[-1] if st else "offen"


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso) if iso else None
    except ValueError:
        return None


FILTER = ("Aktuell", "Überfällig", "Heute fällig", "Morgen", "Diese Woche", "In Bearbeitung", "Verladebereit",
          "Versendet", "Alle", "Archiviert")


def passt(z, d, filt, heute=None, morgen=None):
    """Zeile z (Angebot mit liefertermin) mit Versanddaten d im Filter filt?"""
    heute = heute or datetime.date.today()
    termin = _datum(z.get("liefertermin"))
    versendet = ist_versendet(d)
    if filt == "Archiviert":
        return bool(d.get("archiviert"))
    if d.get("archiviert"):
        return False
    if filt == "Alle":
        return True
    if filt == "Versendet":
        return versendet
    if versendet:
        return False
    if filt == "Aktuell":
        return True
    if filt == "Überfällig":
        return termin is not None and termin < heute
    if filt == "Heute fällig":
        return termin == heute
    if filt == "Morgen":
        return termin is not None and termin == (morgen or heute + datetime.timedelta(days=1))
    if filt == "Diese Woche":
        return termin is not None and heute <= termin <= heute + datetime.timedelta(days=6 - heute.weekday())
    if filt == "Verladebereit":
        return ist_verladebereit(d)
    if filt == "In Bearbeitung":
        return not ist_verladebereit(d)
    return True


def reihenfolge(z, d, heute=None):
    """Sortierung der Übersicht: überfällig, dann nach Liefertermin (ohne Termin zuletzt), versendet ans Ende."""
    heute = heute or datetime.date.today()
    termin = _datum(z.get("liefertermin"))
    return (ist_versendet(d), termin is None, termin or datetime.date.max, str(z.get("nummer") or ""))


def status_setzen(d, status, an, heute=None):
    """Status an/aus; 'Versendet' setzt bzw. löscht versendet_am. Ändert d."""
    heute = heute or datetime.date.today()
    st = [s for s in d.get("status") or () if s != status]
    if an:
        st.append(status)
    d["status"] = [s for s in STATUS if s in st]
    if status == VERSENDET:
        d["versendet_am"] = heute.isoformat() if an else None
    return d
