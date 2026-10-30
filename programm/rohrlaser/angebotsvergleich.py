"""Angebotsvergleich: zwei Angebote aus CSV-Dateien oder aus der Angebotsliste Position für Position vergleichen
(Plan „CSV-Angebotsvergleich“, Patrick 30.10.2026, Freigabe „Alle Empfehlungen“ = 1c 2c 3a 4a 5a 6a 7a 8a 9b).

Quellen (1c): unser eigener CSV-Export (Angebotspositionen.csv, auch im ZIP mit Angebotskopf.csv) wird an den festen
Spaltentiteln erkannt und braucht keine Zuordnung; jede andere CSV (Konkurrenz-, Lieferantenangebot, Stückliste)
bekommt eine Spaltenzuordnung, die das Programm aus den Spaltentiteln vorschlägt und die sich je Quelle als Vorlage
speichern lässt. Gelesen wird so robust wie beim Kunden-CSV (Trennzeichen, Kodierung, Titelzeilen, Excel-Schutz).
Nur CSV, keine .xlsx (9b: in Excel „Speichern unter → CSV“). Angebote aus der Liste laufen über dieselben Zeilen wie
der CSV-Export (export.daten), also genau wie die Datei, die das Angebot exportieren würde.

Verglichen werden (2c) Stückpreis, Gesamtpreis und Menge, als Hinweis Werkstoff, Abmessung und Länge, dazu
Bearbeitungszeit, Herstellkosten je Stück und Marge, wo beide Seiten sie haben. Zuordnung der Positionen (3a): gleiche
Artikelnummer, sonst gleiche Bezeichnung mit passender Abmessung und Länge, sonst gleiche Positionsnummer; der Rest
steht als „nur in A“ / „nur in B“ und lässt sich von Hand zuordnen. Unterschiedliche Mengen (4a): verglichen wird der
Stückpreis, der Gesamtpreis von B zusätzlich auf die Mengen von A hochgerechnet. Differenz immer B − A.
Markiert (5a) wird eine Position ab der Schwelle in den Einstellungen (Vorgabe 5 % oder 50 € auf die Position).
Es wird nichts in den Angeboten gespeichert (8a); Ausgabe als PDF und CSV (6a).

Ohne Qt, damit Tests und PDF den Vergleich ohne Fenster rechnen."""
import csv
import io
import re
import zipfile
from pathlib import Path

from . import export
from .kunden_csv import _excel_wert, _text, _trenner

# Felder des Vergleichs: (Schlüssel, Titel, Spaltentitel, an denen die Zuordnung sie erkennt (klein, ohne
# Leerzeichen am Rand), in der Reihenfolge des Vorrangs)
FELDER = (
    ("pos", "Position", ("pos.", "pos", "position", "pos.-nr.", "pos.nr.", "pos-nr", "posnr", "nr.", "nr", "lfd. nr.",
                         "lfd.nr.", "zeile")),
    ("artikel", "Artikelnummer", ("artikelnr.", "artikelnr", "artikel-nr.", "artikelnummer", "art.-nr.", "art.nr.",
                                  "artnr", "art-nr", "artikel", "zeichnungsnummer", "zeichnungsnr.", "zeichnung",
                                  "teilenummer", "teilenr.", "sachnummer", "sachnr.", "materialnummer", "ident")),
    ("bezeichnung", "Bezeichnung", ("artikeltext", "bezeichnung", "benennung", "beschreibung", "kurztext", "text",
                                    "artikelbezeichnung", "positionstext")),
    ("menge", "Menge", ("menge", "anzahl", "stückzahl", "stück", "stk", "stk.", "anz.", "anz", "bestellmenge")),
    ("stueckpreis", "Stückpreis [€]", ("stückpr.", "stückpreis", "einzelpreis", "preis/stk", "preis/stk.",
                                       "preis je stück", "preis pro stück", "e-preis", "ep", "ep [€]",
                                       "einzelpreis [€]", "stückpreis [€]", "preis/st", "preis je stk.")),
    ("preis", "Gesamtpreis [€]", ("gesamtpreis", "gesamt", "gesamtpreis [€]", "gp", "gp [€]", "summe", "betrag",
                                  "positionspreis", "pos.-preis", "gesamt netto", "netto", "wert", "preis")),
    ("werkstoff", "Werkstoff", ("werkstofftyp", "werkstoff", "material", "güte", "werkstoffnummer", "qualität")),
    ("abmessung", "Abmessung", ("abmessung", "profil", "dimension", "querschnitt", "rohr", "maße", "masse")),
    ("laenge", "Länge [mm]", ("l.", "länge", "laenge", "länge [mm]", "länge mm", "zuschnittlänge", "l")),
    ("zeit", "Bearbeitungszeit", ("bearbeitungszeit", "laserzeit", "schneidzeit", "zeit", "fertigungszeit")),
    ("hk", "Herstellkosten je Stück [€]", ("hk()", "hk", "herstellkosten", "hk je stück", "hk/stk")),
    ("marge", "Marge [%]", ("marge netto%", "marge %", "marge", "marge [%]", "gewinn %")),
)
FELD_TITEL = {k: t for k, t, _ in FELDER}
ZAHL_FELDER = ("menge", "stueckpreis", "preis", "laenge", "hk", "marge")
PFLICHT = ("stueckpreis", "preis")            # mindestens eines davon muss zugeordnet sein
EIGEN_MERKMAL = ("Stückpr.", "Liste der Arbeitsgänge", "Artikeltext", "Gesamt HK(€)")
# Spaltenzuordnung des eigenen Exports (export.POSITION_SPALTEN)
EIGEN = dict(pos="Pos.", artikel="ArtikelNr.", bezeichnung="Artikeltext", menge="Menge", stueckpreis="Stückpr.",
             preis="Preis", werkstoff="Werkstofftyp", laenge="L.", zeit="Bearbeitungszeit", hk="HK()",
             marge="Marge Netto%")
VORLAGEN = "vergleich_vorlagen"        # Einstellung (intern): {Name: {spalten: [...], zuordnung: {feld: Spalte}}}
SUMMENZEILE = re.compile(r"^\s*(zwischen)?summe|^\s*gesamt|^\s*netto|^\s*brutto|^\s*mwst|^\s*ust|^\s*übertrag|"
                         r"^\s*rabatt|^\s*fracht|^\s*versand", re.I)
ART = {"artikel": "Artikel-Nr.", "bezeichnung": "Bezeichnung", "pos": "Position", "hand": "von Hand"}


class VergleichFehler(ValueError):
    """Datei lässt sich nicht als Angebot lesen (Text für den Bediener)."""


# ------------------------------------------------------------------ Lesen
def _norm(t):
    return re.sub(r"\s+", " ", str(t or "")).strip().lower()


def _zellen(text):
    """CSV-Text -> Liste von Zeilen (Listen von Texten), leere Zeilen und 'sep=;' weg."""
    nicht_leer = [z for z in text.splitlines() if z.strip()]
    if not nicht_leer:
        raise VergleichFehler("Die Datei ist leer.")
    trenner, sep_zeile = _trenner(nicht_leer)
    out = []
    try:
        for z in csv.reader(io.StringIO(text, newline=""), delimiter=trenner):
            if not any(c.strip() for c in z):
                continue
            if sep_zeile:
                sep_zeile = False
                continue
            out.append([_excel_wert(c).strip() for c in z])
    except csv.Error as e:
        raise VergleichFehler(f"Die Datei ist nicht lesbar ({e}). Bitte in Excel als „CSV UTF-8“ speichern.") from e
    return out


def _ist_zahl(t):
    return bool(re.fullmatch(r"[-+]?[\d.,\s]+\s*(€|eur|%)?", t.strip(), re.I)) and any(c.isdigit() for c in t)


def _kopfzeile(zeilen):
    """Index der Kopfzeile: erste Zeile mit mindestens zwei Feldern, die überwiegend Text (keine Zahlen) sind und
    unter der noch Zeilen folgen (Titelzeilen wie „Angebot 4711“ darüber werden übersprungen)."""
    for i, z in enumerate(zeilen[:15]):
        voll = [c for c in z if c.strip()]
        if len(voll) >= 2 and sum(not _ist_zahl(c) for c in voll) * 2 >= len(voll) and i + 1 < len(zeilen):
            return i
    raise VergleichFehler("Keine Kopfzeile gefunden: die Datei braucht eine Zeile mit Spaltentiteln über den "
                          "Positionen.")


def datei_lesen(pfad=None, roh=None, name=None):
    """CSV oder ZIP (eigener Export) lesen. Ergebnis: Quelle dict(titel, name, spalten, zeilen, eigen, kopf)."""
    name = name or (Path(pfad).name if pfad else "Datei")
    if roh is None:
        try:
            roh = Path(pfad).read_bytes()
        except OSError as e:
            raise VergleichFehler(f"Die Datei lässt sich nicht öffnen:\n{pfad}\n\n{e}") from e
    if roh[:2] == b"PK":
        return _zip_lesen(roh, name)
    if Path(name).suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        raise VergleichFehler("Excel-Dateien bitte in Excel mit „Speichern unter → CSV UTF-8“ als CSV speichern.")
    zeilen = _zellen(_text(roh))
    i = _kopfzeile(zeilen)
    spalten = zeilen[i]
    quelle = dict(name=name, titel=Path(name).stem, spalten=spalten, zeilen=zeilen[i + 1:], kopf={},
                  eigen=all(m in spalten for m in EIGEN_MERKMAL))
    if quelle["eigen"]:
        nr = next((z[spalten.index("Angebot")] for z in quelle["zeilen"]
                   if "Angebot" in spalten and len(z) > spalten.index("Angebot") and z[spalten.index("Angebot")]), "")
        quelle["titel"] = f"Angebot {nr}" if nr else quelle["titel"]
    return quelle


def _zip_lesen(roh, name):
    try:
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            namen = z.namelist()
            pos = next((n for n in namen if n.endswith(export.POSITION_DATEI)), None)
            if pos is None:
                raise VergleichFehler(f"Im ZIP fehlt {export.POSITION_DATEI} (nur der eigene CSV-Export als ZIP).")
            quelle = datei_lesen(roh=z.read(pos), name=name)
            kopf_name = next((n for n in namen if n.endswith(export.KOPF_DATEI)), None)
            if kopf_name:
                k = _zellen(_text(z.read(kopf_name)))
                if len(k) >= 2:
                    quelle["kopf"] = dict(zip(k[0], k[1]))
    except zipfile.BadZipFile as e:
        raise VergleichFehler("Die ZIP-Datei ist beschädigt.") from e
    kunde = quelle["kopf"].get("Kunde:")
    if kunde:
        quelle["titel"] = f"{quelle['titel']} – {kunde}"
    return quelle


def aus_angebot(db, angebot_id):
    """Gespeichertes Angebot als Quelle im Format des eigenen CSV-Exports (wie die Datei, die es exportieren würde).
    Ohne Schnittplan (nicht optimiert) VergleichFehler."""
    from . import preis_simulator, rechnen, teilen
    a = db.angebot(angebot_id)
    if not a:
        raise VergleichFehler("Das Angebot gibt es nicht mehr.")
    nr = a.get("nummer") or ""
    if not a.get("ergebnis"):
        raise VergleichFehler(f"Angebot {nr} ist nicht optimiert: bitte erst öffnen und optimieren.")
    pos = db.positionen(angebot_id)
    if not pos:
        raise VergleichFehler(f"Angebot {nr} hat keine Positionen.")
    k, tab, e = preis_simulator.grundlage(db, a)
    zeilen, summen = rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)
    bearbeiter = a.get("bearbeiter")
    kopfzeile, pos_zeilen = export.daten(
        a, pos, a["ergebnis"], zeilen, summen, k, tab, e, kunde=db.kunde(a.get("kundennr")),
        ersteller=teilen.mitarbeiter(db, bearbeiter).get("name") if bearbeiter else None)
    titel = f"Angebot {nr}" + (f" – {a['kunde']}" if a.get("kunde") else "")
    return dict(name=titel, titel=titel, spalten=list(export.POSITION_SPALTEN), zeilen=pos_zeilen, eigen=True,
                kopf=dict(zip(export.KOPF_SPALTEN, kopfzeile)), angebot_id=angebot_id)


# ------------------------------------------------------------------ Spaltenzuordnung
def vorschlag(spalten):
    """Spaltenzuordnung {feld: Spaltentitel} aus den Spaltentiteln; jede Spalte höchstens einmal."""
    if all(m in spalten for m in EIGEN_MERKMAL):
        return {f: s for f, s in EIGEN.items() if s in spalten}
    frei = {_norm(s): s for s in reversed(spalten) if s.strip()}
    out = {}
    for feld, _, namen in FELDER:
        for n in namen:
            if n in frei:
                out[feld] = frei.pop(n)
                break
    if "stueckpreis" not in out and out.get("preis") and _norm(out["preis"]) != "preis" and "preis" in frei:
        out["stueckpreis"] = frei.pop("preis")          # „Preis“ neben „Gesamt“ ist der Stückpreis
    for feld, _, namen in FELDER:          # zweiter Durchgang: Titel, die mit einem Namen beginnen („Menge Stk“)
        if feld in out:
            continue
        for n in namen:
            treffer = next((s for k, s in frei.items() if len(n) >= 3 and k.startswith(n)), None)
            if treffer:
                out[feld] = treffer
                frei.pop(_norm(treffer))
                break
    return out


def vorlage_finden(vorlagen, spalten):
    """Name der gespeicherten Vorlage mit genau diesen Spaltentiteln, sonst None."""
    sp = [_norm(s) for s in spalten]
    return next((n for n, v in (vorlagen or {}).items() if [_norm(s) for s in v.get("spalten") or ()] == sp), None)


def zuordnung_pruefen(zuordnung):
    """Fehlertext oder None."""
    if not any(zuordnung.get(f) for f in PFLICHT):
        return "Bitte mindestens die Spalte für den Stückpreis oder den Gesamtpreis zuordnen."
    if not any(zuordnung.get(f) for f in ("artikel", "bezeichnung", "pos")):
        return "Bitte Artikelnummer, Bezeichnung oder Position zuordnen, damit sich die Positionen finden lassen."
    return None


# ------------------------------------------------------------------ Werte
def _dezimal_komma(werte):
    """True, wenn in dieser Spalte das Komma die Dezimalstelle trennt (deutsches Excel), False bei Punkt. Eine Spalte
    nur mit Punkt vor genau drei Ziffern (1.500) gilt als Tausendertrennung wie im deutschen Excel."""
    texte = [re.sub(r"[^\d.,\-]", "", w) for w in werte if w]
    if any("," in t for t in texte):
        return True
    return not any(re.search(r"\.(\d{1,2}|\d{4,})$", t) for t in texte)


def zahl(t, komma=True):
    """'1.234,50 €' -> 1234.5 (komma=True) bzw. '1234.50' -> 1234.5 (komma=False); '93.2 %' -> 93.2; leer/Text ->
    None."""
    t = re.sub(r"(€|eur|euro|%|stk\.?|st\.?|mm)", "", str(t or ""), flags=re.I).replace(" ", "").replace(" ", "")
    t = t.replace("'", "")
    if not re.search(r"\d", t):
        return None
    if komma:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def sekunden(t, eigen=False):
    """'HH:MM:SS' / 'MM:SS' -> Sekunden; eine Zahl gilt als Minuten (fremde Dateien)."""
    t = str(t or "").strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", t)
    if m:
        a, b, c = (int(x) if x else None for x in m.groups())
        return a * 3600 + b * 60 + c if c is not None else a * 60 + b
    x = zahl(t, komma=not eigen)
    return None if x is None else x * 60


def _abmessung_eigen(arbeitsgaenge):
    m = re.search(r"(?:Profile|Zukaufteil) \[([^\]]*)\]", arbeitsgaenge or "")
    return m.group(1) if m else ""


def positionen(quelle, zuordnung=None):
    """Positionen der Quelle als Liste von dict(zeile, pos, artikel, bezeichnung, menge, stueckpreis, preis, werkstoff,
    abmessung, laenge, zeit, hk, marge) und Hinweise (übersprungene Zeilen). Stückpreis fehlt -> Preis ÷ Menge,
    Preis fehlt -> Stückpreis × Menge (Menge leer = 1)."""
    eigen = quelle.get("eigen")
    zu = dict(EIGEN) if eigen else dict(zuordnung or vorschlag(quelle["spalten"]))
    spalten = quelle["spalten"]
    idx = {f: spalten.index(s) for f, s in zu.items() if s in spalten}

    def wert(z, f):
        i = idx.get(f)
        return z[i].strip() if i is not None and i < len(z) else ""
    komma = {f: False if eigen else _dezimal_komma([wert(z, f) for z in quelle["zeilen"]]) for f in ZAHL_FELDER}
    out, hinweise = [], []
    for n, z in enumerate(quelle["zeilen"], 1):
        p = dict(zeile=n)
        for f in ("pos", "artikel", "bezeichnung", "werkstoff", "abmessung"):
            p[f] = wert(z, f)
        for f in ZAHL_FELDER:
            p[f] = zahl(wert(z, f), komma[f])
        p["zeit"] = sekunden(wert(z, "zeit"), eigen)
        if eigen:
            p["abmessung"] = _abmessung_eigen(z[spalten.index("Liste der Arbeitsgänge")]
                                              if "Liste der Arbeitsgänge" in spalten else "")
        if p["pos"]:
            x = zahl(p["pos"], komma=False)
            p["pos"] = (str(int(x)) if x is not None and x.is_integer() else p["pos"])
        kennung = p["artikel"] or p["bezeichnung"]
        if p["stueckpreis"] is None and p["preis"] is None:
            if kennung or p["pos"]:
                hinweise.append(f"Zeile {n} ({kennung or 'Pos. ' + p['pos']}): ohne Preis, nicht verglichen")
            continue
        if not kennung and not p["pos"] or SUMMENZEILE.search(kennung or "") and not p["menge"]:
            hinweise.append(f"Zeile {n}: Summenzeile übersprungen")
            continue
        if p["stueckpreis"] is None:
            p["stueckpreis"] = p["preis"] / p["menge"] if p["menge"] else p["preis"]
        if p["preis"] is None:
            p["preis"] = p["stueckpreis"] * (p["menge"] if p["menge"] is not None else 1)
        out.append(p)
    return out, hinweise


# ------------------------------------------------------------------ Zuordnen
def _schluessel(t):
    return re.sub(r"[\s_\-./]+", "", str(t or "")).lower()


def _passt(a, b, toleranz=0.5):
    return a is None or b is None or abs(a - b) <= toleranz


def zuordnen(pa, pb):
    """Paare (i_a, i_b, art) der Positionen: Artikelnummer, dann Bezeichnung + Abmessung + Länge, dann Position."""
    frei_b = set(range(len(pb)))
    paare, frei_a = [], list(range(len(pa)))

    def runde(art, schluessel_a, schluessel_b, extra=lambda a, b: True):
        nonlocal frei_a
        rest = []
        for i in frei_a:
            s = schluessel_a(pa[i])
            j = next((j for j in sorted(frei_b) if s and schluessel_b(pb[j]) == s and extra(pa[i], pb[j])), None)
            if j is None:
                rest.append(i)
            else:
                frei_b.discard(j)
                paare.append((i, j, art))
        frei_a = rest
    runde("artikel", lambda p: _schluessel(p["artikel"]), lambda p: _schluessel(p["artikel"]))
    runde("bezeichnung", lambda p: _norm(p["bezeichnung"]), lambda p: _norm(p["bezeichnung"]),
          lambda a, b: _passt(a["laenge"], b["laenge"]) and (not a["abmessung"] or not b["abmessung"]
                                                             or _schluessel(a["abmessung"]) == _schluessel(b["abmessung"])))
    runde("pos", lambda p: p["pos"], lambda p: p["pos"])
    return sorted(paare)


def von_hand(paare, i_a, i_b):
    """Position i_a von A mit i_b von B zuordnen (bisherige Paare der beiden fallen weg)."""
    return sorted([p for p in paare if p[0] != i_a and p[1] != i_b] + [(i_a, i_b, "hand")])


def trennen(paare, i_a):
    return [p for p in paare if p[0] != i_a]


# ------------------------------------------------------------------ Vergleich
def _diff(a, b):
    return None if a is None or b is None else b - a


def _anteil(a, b):
    return None if a in (None, 0) or b is None else (b - a) / a


def vergleichen(pa, pb, paare, schwelle_anteil=0.05, schwelle_eur=50.0):
    """Zeilen des Vergleichs (in der Reihenfolge von A, Positionen nur in B am Ende) und Summen.
    Zeile: dict(art 'paar'|'nur_a'|'nur_b', a, b (Positionen oder None), zuordnung, menge_a, menge_b, stk_a, stk_b,
    diff_stk, anteil, ges_a, ges_b (B auf die Menge von A), diff_ges, markiert, hinweise [Texte], i_a, i_b)."""
    nach_a = {i: (j, art) for i, j, art in paare}
    in_b = {j for _, j, _ in paare}
    zeilen = []
    for i, a in enumerate(pa):
        if i in nach_a:
            j, art = nach_a[i]
            zeilen.append(_paar(a, pb[j], art, i, j, schwelle_anteil, schwelle_eur))
        else:
            zeilen.append(dict(art="nur_a", a=a, b=None, i_a=i, i_b=None, zuordnung="nur in A", markiert=True,
                               menge_a=a["menge"], stk_a=a["stueckpreis"], ges_a=a["preis"], hinweise=[]))
    for j, b in enumerate(pb):
        if j not in in_b:
            zeilen.append(dict(art="nur_b", a=None, b=b, i_a=None, i_b=j, zuordnung="nur in B", markiert=True,
                               menge_b=b["menge"], stk_b=b["stueckpreis"], ges_b=b["preis"], hinweise=[]))
    return zeilen, summen(zeilen, pa, pb)


def _paar(a, b, art, i, j, schwelle_anteil, schwelle_eur):
    menge = a["menge"] if a["menge"] is not None else b["menge"]
    ges_b = b["stueckpreis"] * menge if menge is not None else b["preis"]
    z = dict(art="paar", a=a, b=b, i_a=i, i_b=j, zuordnung=ART[art], menge_a=a["menge"], menge_b=b["menge"],
             stk_a=a["stueckpreis"], stk_b=b["stueckpreis"], diff_stk=_diff(a["stueckpreis"], b["stueckpreis"]),
             anteil=_anteil(a["stueckpreis"], b["stueckpreis"]), ges_a=a["preis"], ges_b=ges_b,
             diff_ges=_diff(a["preis"], ges_b), hinweise=[])
    h = z["hinweise"]
    if a["menge"] is not None and b["menge"] is not None and abs(a["menge"] - b["menge"]) > 1e-9:
        h.append(f"Menge A {_t(a['menge'])} / B {_t(b['menge'])}")
    for f, titel in (("werkstoff", "Werkstoff"), ("abmessung", "Abmessung")):
        if a[f] and b[f] and _schluessel(a[f]) != _schluessel(b[f]):
            h.append(f"{titel} A {a[f]} / B {b[f]}")
    if not _passt(a["laenge"], b["laenge"]):
        h.append(f"Länge A {_t(a['laenge'])} / B {_t(b['laenge'])} mm")
    for f, titel, form in (("zeit", "Zeit", _zeit_t), ("hk", "HK/Stk", lambda x: _t(x, 2) + " €"),
                           ("marge", "Marge", lambda x: _t(x, 1) + " %")):
        z[f + "_a"], z[f + "_b"] = a[f], b[f]
        if a[f] is not None and b[f] is not None and abs(a[f] - b[f]) > 1e-6:
            h.append(f"{titel} A {form(a[f])} / B {form(b[f])}")
    z["markiert"] = bool(
        schwelle_anteil and z["anteil"] is not None and abs(z["anteil"]) >= schwelle_anteil - 1e-12
        or schwelle_eur and z["diff_ges"] is not None and abs(z["diff_ges"]) >= schwelle_eur - 1e-9)
    return z


def summen(zeilen, pa, pb):
    paar = [z for z in zeilen if z["art"] == "paar"]
    s = dict(summe_a=sum(p["preis"] for p in pa), summe_b_datei=sum(p["preis"] for p in pb),
             paar_a=sum(z["ges_a"] or 0 for z in paar), paar_b=sum(z["ges_b"] or 0 for z in paar),
             paare=len(paar), teurer=sum(1 for z in paar if (z["diff_stk"] or 0) > 0.005),
             guenstiger=sum(1 for z in paar if (z["diff_stk"] or 0) < -0.005),
             markiert=sum(1 for z in paar if z["markiert"]),
             nur_a=sum(1 for z in zeilen if z["art"] == "nur_a"), nur_b=sum(1 for z in zeilen if z["art"] == "nur_b"),
             nur_a_eur=sum(z["ges_a"] or 0 for z in zeilen if z["art"] == "nur_a"),
             nur_b_eur=sum(z["ges_b"] or 0 for z in zeilen if z["art"] == "nur_b"))
    s["gleich"] = s["paare"] - s["teurer"] - s["guenstiger"]
    s["diff"] = s["paar_b"] - s["paar_a"]
    s["anteil"] = s["diff"] / s["paar_a"] if s["paar_a"] else None
    s["groesste"] = sorted((z for z in paar if z["diff_ges"]), key=lambda z: -abs(z["diff_ges"]))[:5]
    return s


# ------------------------------------------------------------------ Texte
def _t(x, stellen=None):
    """Zahl deutsch: 1.234,5 (stellen=None: so viele wie nötig, höchstens 3)."""
    if x is None:
        return ""
    if stellen is None:
        t = f"{x:,.3f}".rstrip("0").rstrip(".")
    else:
        t = f"{x:,.{stellen}f}"
    return t.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def euro(x, vorzeichen=False):
    return "" if x is None else ("+" if vorzeichen and x > 0.004 else "") + _t(x, 2)


def prozent(x, vorzeichen=True):
    return "" if x is None else ("+" if vorzeichen and x > 0.00049 else "") + _t(x * 100, 1) + " %"


def _zeit_t(s):
    s = int(round(s or 0))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def bezeichnung(z):
    p = z["a"] or z["b"]
    return p["artikel"] or p["bezeichnung"] or (f"Pos. {p['pos']}" if p["pos"] else f"Zeile {p['zeile']}")


def kennung(z):
    """Artikelnummer und Bezeichnung (wenn verschieden) für Liste und PDF."""
    p = z["a"] or z["b"]
    teile = [t for t in (p["artikel"], p["bezeichnung"]) if t]
    return " – ".join(dict.fromkeys(teile)) or bezeichnung(z)


CSV_SPALTEN = ("Pos. A", "Pos. B", "Artikel", "Bezeichnung", "Zuordnung", "Menge A", "Menge B", "Stückpreis A",
               "Stückpreis B", "Differenz Stück [€]", "Differenz [%]", "Gesamt A [€]", "Gesamt B auf Menge A [€]",
               "Differenz Gesamt [€]", "markiert", "Hinweise")


def csv_text(zeilen, s, titel_a, titel_b):
    """Vergleich als CSV für Excel (Semikolon, UTF-8 mit BOM, Zahlen mit Komma), Summen am Ende."""
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(["Angebotsvergleich", f"A = {titel_a}", f"B = {titel_b}", "Differenz = B − A"])
    w.writerow(CSV_SPALTEN)
    for z in zeilen:
        a, b = z["a"] or {}, z["b"] or {}
        w.writerow([a.get("pos", ""), b.get("pos", ""), (a or b).get("artikel", ""), (a or b).get("bezeichnung", ""),
                    z["zuordnung"], _t(z.get("menge_a")), _t(z.get("menge_b")), euro(z.get("stk_a")),
                    euro(z.get("stk_b")), euro(z.get("diff_stk")), prozent(z.get("anteil")), euro(z.get("ges_a")),
                    euro(z.get("ges_b")), euro(z.get("diff_ges")), "ja" if z["markiert"] else "",
                    "; ".join(z["hinweise"])])
    w.writerow([])
    w.writerow(["Summe zugeordnete Positionen", "", "", "", f"{s['paare']} Positionen", "", "", "", "", "",
                prozent(s["anteil"]), euro(s["paar_a"]), euro(s["paar_b"]), euro(s["diff"])])
    w.writerow(["Summe A laut Datei", euro(s["summe_a"])])
    w.writerow(["Summe B laut Datei", euro(s["summe_b_datei"])])
    return "﻿" + puffer.getvalue()


def ergebnis_text(s, titel_a="A", titel_b="B"):
    """Ein Satz für Fenster und PDF."""
    if not s["paare"]:
        return "Keine Positionen zugeordnet."
    richtung = "teurer" if s["diff"] > 0.004 else "günstiger" if s["diff"] < -0.004 else "gleich teuer"
    anteil = prozent(abs(s["anteil"]), False) if s["anteil"] is not None else "–"
    t = (f"{titel_b} ist auf die zugeordneten Positionen {euro(abs(s['diff']))} € ({anteil}) "
         f"{richtung} als {titel_a}" if richtung != "gleich teuer" else f"{titel_b} und {titel_a} sind gleich teuer")
    return t + (f" ({s['teurer']} Positionen teurer, {s['guenstiger']} günstiger, {s['gleich']} gleich).")
