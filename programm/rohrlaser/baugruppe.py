"""Schweißbaugruppen: Struktur, Mengen, Schweißzeiten, Arbeitsgänge und Einmalkosten (Patrick 23.10.2026, Plan
Schweißbaugruppen, Freigabe „Alles a“).

Eine Schweißbaugruppe ist eine Position der Art 'Schweißbaugruppe' (angebot.BAUGRUPPE). Sie trägt in der Spalte
'baugruppe' (JSON) ihre Stammdaten, die Unterbaugruppen (Knoten), Arbeitsgänge und Nahtgruppen; ihre Stückzahl ist
die Anzahl Baugruppen. Die Einzelteile sind gewöhnliche Positionen (Rohrlaserteil, Zukaufteil), die ihr über die
Spalte 'bg_knoten' ('<Baugruppen-ID>' bzw. '<Baugruppen-ID>/<Knoten-ID>') zugeordnet sind, mit 'je_knoten' Stück je
direkt übergeordneter (Unter-)Baugruppe. So rechnen Einzelteile unverändert über Optimierung und
rechnen.kalkulation (keine Doppelrechnung); die Baugruppe rechnet nur ihre eigenen Leistungen dazu. Satz und
'Stück je Satz' der Teile folgen aus der Struktur (abgleich), damit Angebot, Staffeln und PDF die Baugruppe wie
einen Satz behandeln.

Rechenweg je Baugruppe (alle Beträge je Baugruppe, ungerundet):
  Menge eines Knotens  m(k) = Menge des Knotens × Menge seiner übergeordneten Knoten (Baugruppe selbst: 1)
  Nahtgruppe           Naht [m] = Länge je Naht × Anzahl × (2 bei beidseitig) / 1000
                       Lichtbogenzeit = Naht × Kennwert [min/m] × Faktor Schweißlage × Zugänglichkeit × Qualität
                       Schweißzeit = Lichtbogenzeit ÷ Lichtbogenzeitfaktor + Heftpunkte × Anzahl × Zeit je Heftpunkt
                       (oder die Zeit von Hand), × m(k); Kosten = Zeit × Stundensatz des Verfahrens
  Arbeitsgang          laufend = (Zeit je Einheit × Menge / 60 × Stundensatz + Kosten je Einheit × Menge) × m(k)
                       einmalig = Rüstzeit / 60 × Stundensatz + Einmalbetrag (Vorrichtung, Lehre, Programm …),
                       je Umlage: 'je Auftrag' ganz, 'anteilig' × Anteil %, 'wiederverwendbar' gar nicht; einmal je
                       Auftrag bzw. Staffelstufe, geteilt durch die Anzahl Baugruppen
  Fremdleistung        Arbeitsgänge mit fremd = ja zählen als Fremdleistung (Zuschlag Fremdleistung), alles andere als
                       Fertigung (Zuschlag Fertigung); danach Gewinn, Skonto, Mindestpreis wie jede Position
Kennwerte, Faktoren und Lichtbogenzeitfaktor kommen aus dem Stand der Nahtgruppe (beim Erfassen gemerkt), sonst
aus den Stammdaten; Stundensätze aus der Zeitbasis des Angebots. Nichts wird erfunden: fehlt ein Kennwert oder
Stundensatz, gibt es keine Zeit bzw. keine Kosten und eine Warnung.
"""
import json
import math
import uuid

from .angebot import ist_baugruppe

KNOTEN_TRENNER = "/"
UMLAGE_AUFTRAG, UMLAGE_ANTEILIG, UMLAGE_WIEDER = "je Auftrag", "anteilig", "wiederverwendbar"
UMLAGEN = (UMLAGE_AUFTRAG, UMLAGE_ANTEILIG, UMLAGE_WIEDER)
LAGEN = {"PA": "Wannenlage", "PB": "Horizontal (Kehlnaht)", "PC": "Querposition", "PD": "Horizontal-Überkopf",
         "PE": "Überkopf", "PF": "Steigend", "PG": "Fallend"}
STAMM_FELDER = (("kundenartikel", "Kundenartikelnummer"), ("zeichnung", "Zeichnungsnummer"),
                ("revision", "Revisionsstand"), ("beschreibung", "Beschreibung"), ("werkstoff", "Werkstoff"),
                ("oberflaeche", "Oberfläche / Beschichtung"), ("gewicht", "Gewicht [kg]"),
                ("abmessungen", "Abmessungen"), ("verfahren", "Fertigungsverfahren"), ("bemerkung", "Bemerkungen"),
                ("intern", "Interne Kalkulationshinweise"))


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def neue_id():
    """Kurze feste Kennung für Baugruppen, Knoten, Arbeitsgänge und Nähte (bleibt beim Kopieren gleich)."""
    return uuid.uuid4().hex[:10]


# ------------------------------------------------------------------ Lesen und Schreiben
def leer():
    """Neue, leere Baugruppe."""
    return dict(id=neue_id(), stamm={}, knoten=[], arbeitsgaenge=[], naehte=[])


def lesen(text):
    """Baugruppe aus der Spalte 'baugruppe' (JSON) mit allen Listen, sonst None (leer oder beschädigt)."""
    if not text:
        return None
    try:
        d = json.loads(text) if isinstance(text, str) else dict(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("id"):
        return None
    for n in ("knoten", "arbeitsgaenge", "naehte"):
        d[n] = [x for x in d.get(n) or () if isinstance(x, dict)]
    d["stamm"] = d.get("stamm") if isinstance(d.get("stamm"), dict) else {}
    return d


_LISTEN = (("knoten", "Unterbaugruppe", "Unterbaugruppen"), ("arbeitsgaenge", "Arbeitsgang", "Arbeitsgänge"),
           ("naehte", "Nahtgruppe", "Nahtgruppen"))


def daten_fehler(text):
    """Erster Fehler der gespeicherten Baugruppendaten mit Ort (T5), sonst None: lesen() verwirft Beschädigtes still,
    der Status nennt so, was und wo (JSON-Stelle, Liste, Eintrag, doppelte Kennung)."""
    if not text:
        return "Baugruppendaten fehlen"
    try:
        d = json.loads(text) if isinstance(text, str) else dict(text)
    except ValueError as e:
        return f"Baugruppendaten beschädigt (JSON, Zeile {getattr(e, 'lineno', '?')}, Zeichen {getattr(e, 'colno', '?')})"
    except TypeError:
        return "Baugruppendaten beschädigt (kein JSON-Text)"
    if not isinstance(d, dict):
        return "Baugruppendaten beschädigt (kein Datensatz)"
    if not d.get("id") or not isinstance(d["id"], str):
        return "Baugruppendaten: Kennung der Baugruppe fehlt"
    if d.get("stamm") is not None and not isinstance(d["stamm"], dict):
        return "Baugruppendaten: Stammdaten sind kein Datensatz"
    for liste, titel, mehrzahl in _LISTEN:
        x = d.get(liste)
        if x is None:
            continue
        if not isinstance(x, list):
            return f"Baugruppendaten: {mehrzahl} sind keine Liste ('{liste}')"
        ids = set()
        for n, e in enumerate(x, 1):
            if not isinstance(e, dict):
                return f"Baugruppendaten: {titel} Nr. {n} ist kein Datensatz"
            kenn = e.get("id")
            if kenn is not None and not isinstance(kenn, (str, int)):
                return f"Baugruppendaten: {titel} {e.get('nr') or e.get('name') or f'Nr. {n}'} hat eine ungültige Kennung"
            if kenn and kenn in ids:
                ort = e.get("nr") or e.get("name") or f"Nr. {n}"
                return f"Baugruppendaten: {titel} {ort} hat eine doppelte Kennung ({kenn})"
            ids.add(kenn)
    return None


def speichern(bg):
    return json.dumps(bg, ensure_ascii=False, sort_keys=True)


def zuordnung(p):
    """(Baugruppen-ID, Knoten-ID) eines Einzelteils; Knoten '' = direkt in der Baugruppe; (None, None) ohne."""
    t = str((p or {}).get("bg_knoten") or "").strip()
    if not t:
        return None, None
    bg, _, kn = t.partition(KNOTEN_TRENNER)
    return bg, kn


def zuordnung_text(bg_id, knoten_id=""):
    return bg_id + (KNOTEN_TRENNER + knoten_id if knoten_id else "")


def baugruppen(positionen):
    """{Baugruppen-ID: (Index, Baugruppe)} aller Positionen der Art Schweißbaugruppe mit lesbaren Daten."""
    out = {}
    for i, p in enumerate(positionen):
        if ist_baugruppe(p):
            bg = lesen(p.get("baugruppe"))
            if bg and bg["id"] not in out:
                out[bg["id"]] = (i, bg)
    return out


def name(p, bg=None):
    """Satzbezeichnung der Baugruppe: Bezeichnung, sonst Artikelnummer, sonst 'Baugruppe <Pos.>'."""
    for n in ("bezeichnung", "artikel"):
        t = str((p or {}).get(n) or "").strip()
        if t:
            return t
    return f"Baugruppe {(p or {}).get('pos') or ''}".strip()


# ------------------------------------------------------------------ Struktur
def knoten_map(bg):
    return {k["id"]: k for k in bg["knoten"] if k.get("id")}


def struktur_fehler(bg):
    """Erster Fehler der Knotenstruktur als Text (unbekannter übergeordneter Knoten, Zyklus, Menge < 1), sonst None."""
    km = knoten_map(bg)
    if len(km) != len(bg["knoten"]):
        return "Unterbaugruppe ohne oder mit doppelter Kennung"
    for k in bg["knoten"]:
        if not _zahl(k.get("menge")) or k["menge"] < 1:
            return f"Unterbaugruppe '{k.get('name') or k['id']}': Menge fehlt"
        weg, x = set(), k
        while x.get("parent"):
            if x["id"] in weg:
                return f"Unterbaugruppe '{k.get('name') or k['id']}' enthält sich selbst"
            weg.add(x["id"])
            x = km.get(x["parent"])
            if x is None:
                return f"Unterbaugruppe '{k.get('name') or k['id']}': übergeordnete Baugruppe fehlt"
    return None


def faktor(bg, knoten_id):
    """Menge eines Knotens je Baugruppe (Produkt der Mengen bis zur Baugruppe); '' = Baugruppe selbst = 1. None bei
    unbekanntem Knoten oder Fehler in der Struktur."""
    if not knoten_id:
        return 1
    if struktur_fehler(bg):
        return None
    km = knoten_map(bg)
    k, f = km.get(knoten_id), 1
    if k is None:
        return None
    while k is not None:
        f *= k["menge"]
        k = km.get(k.get("parent")) if k.get("parent") else None
    return f


def darf_unter(bg, knoten_id, neuer_parent):
    """True, wenn Knoten knoten_id unter neuer_parent ('' = Baugruppe) hängen darf, ohne dass ein Zyklus entsteht."""
    km = knoten_map(bg)
    x = neuer_parent
    while x:
        if x == knoten_id:
            return False
        x = (km.get(x) or {}).get("parent")
    return True


def teile(positionen, bg_id):
    """Indizes der Einzelteile einer Baugruppe."""
    return [i for i, p in enumerate(positionen) if not ist_baugruppe(p) and zuordnung(p)[0] == bg_id]


def gruppen_reihenfolge(positionen):
    """Anzeige der Positionsliste gruppiert (D3): Reihenfolge der Zeilen (Indizes; Einzelteile direkt unter ihrer
    Baugruppe, sonst wie im Angebot) und {Index: Baugruppen-ID} der Einzelteile. Ohne Baugruppe: unverändert."""
    alle = baugruppen(positionen)
    if not alle:
        return list(range(len(positionen))), {}
    zu = {i: bg_id for bg_id in alle for i in teile(positionen, bg_id)}
    folge = []
    for i, p in enumerate(positionen):
        if i in zu:
            continue
        folge.append(i)
        bg = lesen(p.get("baugruppe")) if ist_baugruppe(p) else None
        if bg and alle.get(bg["id"], (None,))[0] == i:
            folge += [j for j in sorted(zu) if zu[j] == bg["id"]]
    return folge, zu


_FINGER = ("art", "bg_knoten", "je_knoten", "stueck", "bezeichnung", "artikel", "pos", "baugruppe")
_KONTEXT = (None, None)          # (Fingerabdruck, (baugruppen, soll_werte, {id(Position): Index})); als Ganzes ersetzt,
                                 # damit der Hintergrundlauf der Staffeln nie ein halbes Paar liest


def _kontext(positionen):
    """Baugruppen, Sollwerte und Index je Position einmal je Stand der Positionsliste (T1): der Status prüft jede Zeile
    gegen dieselben Sollwerte; ein Fingerabdruck der Felder, die sie bestimmen, erkennt jede Änderung."""
    global _KONTEXT
    finger = (id(positionen), len(positionen),
              tuple((id(p),) + tuple(p.get(n) for n in _FINGER) for p in positionen))
    alt = _KONTEXT
    if alt[0] == finger:
        return alt[1]
    wert = (baugruppen(positionen), _soll_werte(positionen), {id(p): i for i, p in enumerate(positionen)})
    _KONTEXT = (finger, wert)
    return wert


def soll_werte(positionen):
    """Wie _soll_werte, aber je Stand der Positionen nur einmal gerechnet (Kopie, damit Aufrufer ändern dürfen)."""
    return {i: dict(v) for i, v in _kontext(positionen)[1].items()}


def _soll_werte(positionen):
    """{Index: {satz, je_satz, stueck}}: Werte, die Baugruppen-Position und Einzelteile nach der Struktur haben müssen
    (Satz = Name der Baugruppe, Stück je Satz = Stück je Knoten × Menge der Knoten, Stückzahl = Stück je Satz ×
    Anzahl Baugruppen). Teile mit unbekannter Baugruppe oder fehlerhafter Struktur fehlen."""
    out = {}
    for bg_id, (i, bg) in baugruppen(positionen).items():
        p = positionen[i]
        satz = name(p, bg)
        anzahl = p.get("stueck") if _zahl(p.get("stueck")) else None
        out[i] = dict(satz=satz, je_satz=1)
        faktoren = {}           # je Knoten nur einmal (Strukturprüfung inbegriffen)
        for j in teile(positionen, bg_id):
            q = positionen[j]
            kn = zuordnung(q)[1]
            if kn not in faktoren:
                faktoren[kn] = faktor(bg, kn)
            f = faktoren[kn]
            je = q.get("je_knoten") if _zahl(q.get("je_knoten")) and q["je_knoten"] >= 1 else 1
            if f is None:
                continue
            je_satz = int(round(je * f))
            out[j] = dict(satz=satz, je_satz=je_satz, stueck=je_satz * anzahl if anzahl is not None else q.get("stueck"))
    return out


def abgleich(positionen):
    """Änderungen [(Index, Feld, Wert)], damit Satz, Stück je Satz und Stückzahl der Struktur folgen."""
    out = []
    for i, soll in sorted(soll_werte(positionen).items()):
        for feld, wert in soll.items():
            if positionen[i].get(feld) != wert:
                out.append((i, feld, wert))
    return out


def teil_pruefen(p, positionen):
    """Text, wenn ein Einzelteil einer Baugruppe zugeordnet ist, die es nicht gibt oder deren Struktur nicht passt."""
    bg_id, kn = zuordnung(p)
    if bg_id is None or positionen is None:
        return None
    alle, soll_alle, index = _kontext(positionen)
    if bg_id not in alle:
        return "Baugruppe der Zuordnung fehlt"
    bg = alle[bg_id][1]
    if kn and kn not in knoten_map(bg):
        return "Unterbaugruppe der Zuordnung fehlt"
    soll = soll_alle.get(index.get(id(p), -1))
    if soll and (str(p.get("satz") or "").strip() != soll["satz"] or p.get("je_satz") != soll["je_satz"]
                 or p.get("stueck") != soll["stueck"]):
        return "Stückzahl passt nicht zur Baugruppe (neu abgleichen)"
    return None


# ------------------------------------------------------------------ STEP-Import
def aus_step(name_bg, struktur, teile_gruppen, nahtkandidaten=()):
    """Schweißbaugruppe aus einer STEP-Datei (Teil 5): Unterbaugruppen aus der Struktur der Messung (STEP-JSON ab
    1.13: knoten {id, name, eltern, menge}); die eine Wurzel ist die Baugruppe selbst. teile_gruppen = [(Position,
    [Knoten-ID je Körper])]: jede Position kommt in die Unterbaugruppe ihrer Körper mit Stück je Unterbaugruppe =
    Körper ÷ Menge der Unterbaugruppe. Liegen gleiche Körper in mehreren Unterbaugruppen oder geht die Teilung nicht
    auf, hängt die Position direkt an der Baugruppe (Stück je Satz bleibt richtig) und bekommt einen Hinweis.
    Nahtgruppen und Arbeitsgänge legt der Import nie an (nichts erfinden). Ändert die Positionen (bg_knoten,
    je_knoten). Nahtkandidaten der Messung (STEP-JSON 1.14) kommen nur als Vorschläge an die Baugruppe
    (vorschlaege_aus_step), nie als Nahtgruppen. Ergebnis: (Baugruppe, [Hinweis je Position bzw. None])."""
    bg = leer()
    bg["stamm"] = dict(bemerkung=f"aus STEP-Import ({name_bg})")
    st_knoten = [k for k in (struktur or {}).get("knoten") or () if isinstance(k, dict) and k.get("id")]
    wurzeln = [k for k in st_knoten if not k.get("eltern")]
    wurzel = wurzeln[0]["id"] if len(wurzeln) == 1 else None
    ids = {k["id"] for k in st_knoten}
    for k in st_knoten:
        if k["id"] == wurzel:
            continue
        eltern = k.get("eltern") if k.get("eltern") in ids and k.get("eltern") != wurzel else ""
        menge = k.get("menge") if _zahl(k.get("menge")) and k["menge"] >= 1 else 1
        bg["knoten"].append(dict(id=str(k["id"]), name=str(k.get("name") or k["id"]), menge=int(menge),
                                 parent=str(eltern) if eltern else ""))
    if struktur_fehler(bg):
        bg["knoten"] = []
    km = knoten_map(bg)
    hinweise = []
    for p, knoten in teile_gruppen:
        gesamt = p.get("je_satz") if _zahl(p.get("je_satz")) and p["je_satz"] >= 1 else len(knoten) or 1
        orte = {str(k or "") if str(k or "") in km else "" for k in knoten} or {""}
        kn, hinweis = "", None
        if len(orte) == 1 and len(knoten) == gesamt:
            kn = orte.pop()
            f = faktor(bg, kn) or 1
            if gesamt % f:
                kn, hinweis = "", "Stückzahl passt nicht zur Unterbaugruppe: direkt der Baugruppe zugeordnet, prüfen"
        elif len(orte) > 1:
            hinweis = "in mehreren Unterbaugruppen: direkt der Baugruppe zugeordnet, im Editor prüfen"
        elif orte != {""}:
            hinweis = "Stück je Satz von Hand geändert: direkt der Baugruppe zugeordnet, prüfen"
        p["bg_knoten"] = zuordnung_text(bg["id"], kn)
        p["je_knoten"] = int(gesamt // (faktor(bg, kn) or 1))
        hinweise.append(hinweis)
    bg["vorschlaege"] = vorschlaege_aus_step(bg, nahtkandidaten, wurzel)
    return bg, hinweise


def unter_einhaengen(struktur, teile_gruppen, kandidaten, unter):
    """Mehrere STEP-Dateien als eine Baugruppe (P8): jede Datei aus unter = [dict(name, menge, struktur, teile,
    kandidaten)] wird eine Unterbaugruppe (Name der Datei, menge Stück je Baugruppe) mit ihrer eigenen Struktur
    darunter. Kennungen bekommen das Präfix U1_, U2_ …; Körper ohne Unterbaugruppe kommen in die Unterbaugruppe der
    Datei. Stück je Satz der Teile wird mit menge multipliziert (ändert die Positionen). Ergebnis: (struktur,
    teile_gruppen, kandidaten) für aus_step."""
    knoten = [dict(k) for k in (struktur or {}).get("knoten") or () if isinstance(k, dict) and k.get("id")]
    wurzeln = [k["id"] for k in knoten if not k.get("eltern")]
    wurzel = wurzeln[0] if len(wurzeln) == 1 else None
    if wurzel is None:          # ohne eine Wurzel: künstliche, damit die Dateien Unterbaugruppen werden
        wurzel = "W0"
        for k in knoten:
            if not k.get("eltern"):
                k["eltern"] = wurzel
        knoten.append(dict(id=wurzel, name="", menge=1, eltern=None))
    teile_gruppen, kandidaten = list(teile_gruppen), list(kandidaten or ())
    for n, u in enumerate(unter, 1):
        menge = int(u.get("menge")) if _zahl(u.get("menge")) and u["menge"] >= 1 else 1
        kid = f"U{n}"
        knoten.append(dict(id=kid, name=str(u.get("name") or kid), menge=menge, eltern=wurzel))
        uk = [k for k in (u.get("struktur") or {}).get("knoten") or () if isinstance(k, dict) and k.get("id")]
        uw = [k["id"] for k in uk if not k.get("eltern")]
        u_wurzel = uw[0] if len(uw) == 1 else None
        ids = {k["id"] for k in uk}

        def neu(x, ids=ids, u_wurzel=u_wurzel, kid=kid):
            return kid if not x or x == u_wurzel or x not in ids else f"{kid}_{x}"
        for k in uk:
            if k["id"] != u_wurzel:
                knoten.append(dict(k, id=neu(k["id"]), eltern=neu(k.get("eltern"))))
        for p, kn in u.get("teile") or ():
            if _zahl(p.get("je_satz")):
                p["je_satz"] = p["je_satz"] * menge
            teile_gruppen.append((p, [neu(x) for x in kn] * menge))
        kandidaten += [dict(k, knoten=neu(k.get("knoten"))) for k in u.get("kandidaten") or ()
                       if isinstance(k, dict)] * menge
    return dict(knoten=knoten), teile_gruppen, kandidaten


def vorschlaege_aus_step(bg, kandidaten, wurzel=None):
    """Nahtkandidaten der STEP-Messung als Vorschläge für Nahtgruppen: gleiche Stoßart, Länge (auf mm) und Dicke in
    derselben Unterbaugruppe werden ein Vorschlag mit Anzahl je Stück der Unterbaugruppe (Kandidaten ÷ Menge; geht
    das nicht auf, direkt an der Baugruppe). Das Maß (a-Maß bzw. Dicke) bleibt offen: die STEP-Datei kennt kein
    a-Maß; bei Stumpf- und Ecknaht ist die gemessene Dicke das Maß. Erst nach Prüfung im Editor (Übernehmen) werden
    sie Nahtgruppen."""
    km = knoten_map(bg)
    gruppen = {}
    for k in kandidaten or ():
        if not isinstance(k, dict) or not _zahl(k.get("laenge_mm")) or k["laenge_mm"] <= 0:
            continue
        kn = str(k.get("knoten") or "")
        kn = kn if kn in km and kn != wurzel else ""
        schl = (kn, k.get("stossart") or "Kehlnaht", round(k["laenge_mm"]), k.get("dicke_mm"))
        gruppen.setdefault(schl, []).append(k)
    out = []
    for (kn, art, laenge, dicke), liste in gruppen.items():
        f = faktor(bg, kn) or 1
        if len(liste) % f:
            kn, f = "", 1
        out.append(dict(id=neue_id(), knoten=kn, nahtart=art, laenge=laenge, anzahl=len(liste) // f,
                        dicke=dicke, teile=[x.get("teile") for x in liste], quelle="STEP"))
    return out


A_REGEL_VORGABE = 0.7          # a-Maß-Regel (P6): a = Faktor × kleinere Wanddicke, abgerundet auf 0,5 mm


def a_mass_regel(dicke, faktor=A_REGEL_VORGABE):
    """Vorschlag a-Maß [mm] nach der Regel a = Faktor × kleinere Wanddicke, auf 0,5 mm abgerundet; None, wenn keine
    Dicke bekannt ist oder weniger als 0,5 mm herauskommt."""
    if not _zahl(dicke) or not _zahl(faktor) or dicke <= 0 or faktor <= 0:
        return None
    a = math.floor(faktor * dicke * 2 + 1e-9) / 2
    return a if a >= 0.5 else None


def vorschlag_naht(v, regel=None):
    """Werte einer Nahtgruppe aus einem Vorschlag: Stumpf- und Ecknaht mit der gemessenen Dicke als Maß, Kehlnaht
    ohne a-Maß (trägt man im Editor ein; bis dahin rechnet die Zeile keine Zeit und zeigt den Grund). regel = Faktor
    der a-Maß-Regel (P6): Kehlnaht mit a = Faktor × Dicke, gekennzeichnet (mass_regel) bis zur Bestätigung."""
    n = dict(knoten=v.get("knoten") or "", nahtart=v.get("nahtart"), laenge=v.get("laenge"),
             anzahl=v.get("anzahl") or 1, quelle="STEP")
    if v.get("nahtart") != "Kehlnaht" and _zahl(v.get("dicke")):
        n["mass"] = v["dicke"]
    elif v.get("nahtart") == "Kehlnaht" and regel:
        a = a_mass_regel(v.get("dicke"), regel)
        if a:
            n["mass"] = n["mass_regel"] = a
    return n


def regel_offen(n):
    """True, wenn das a-Maß einer Nahtgruppe nach der Regel vorgeschlagen und noch nicht bestätigt ist."""
    return _zahl(n.get("mass_regel")) and n.get("mass") == n["mass_regel"]


# ------------------------------------------------------------------ Schweißkennwerte
def _faktor_zeile(tabellen, art, wert):
    if not wert:
        return None
    return next((z for z in tabellen.get("schweiss_faktoren") or ()
                 if z.get("art") == art and str(z.get("wert") or "").strip() == str(wert).strip()), None)


def kennwert(verfahren, nahtart, mass, tabellen):
    """Kennwertzeile (kleinstes 'bis' ≥ Nahtgröße) für Verfahren und Nahtart, sonst None."""
    if not _zahl(mass):
        return None
    kand = [z for z in tabellen.get("schweiss_kennwerte") or ()
            if z.get("verfahren") == verfahren and z.get("nahtart") == nahtart and _zahl(z.get("mass_bis"))
            and _zahl(z.get("min_m")) and z["mass_bis"] >= mass - 1e-9]
    return min(kand, key=lambda z: z["mass_bis"]) if kand else None


def naht_stand(naht, tabellen, datum=None):
    """Kennwerte einer Nahtgruppe aus den Stammdaten, zum Merken in der Nahtgruppe ('stand'): Lichtbogenzeit je m,
    Faktoren, Lichtbogenzeitfaktor, Zeit je Heftpunkt, Stundensatz-ID und ob ein Wert nur Richtwert ist."""
    import datetime
    v = next((z for z in tabellen.get("schweissverfahren") or () if z.get("verfahren") == naht.get("verfahren")), None)
    kw = kennwert(naht.get("verfahren"), naht.get("nahtart"), naht.get("mass"), tabellen)
    fz = {art: _faktor_zeile(tabellen, art, naht.get(feld))
          for art, feld in (("Schweißlage", "lage"), ("Zugänglichkeit", "zugang"), ("Qualität", "qualitaet"))}
    richt = [z for z in [v, kw, *fz.values()] if z and z.get("status") == "Richtwert"]
    return dict(verfahren=bool(v), min_m=kw["min_m"] if kw else None, mass_bis=kw["mass_bis"] if kw else None,
                lichtbogen=(v or {}).get("lichtbogen"), heft_s=(v or {}).get("heft_s"), satz_id=(v or {}).get("satz_id"),
                f_lage=_n((fz["Schweißlage"] or {}).get("faktor")) or 1.0,
                f_zugang=_n((fz["Zugänglichkeit"] or {}).get("faktor")) or 1.0,
                f_qualitaet=_n((fz["Qualität"] or {}).get("faktor")) or 1.0,
                richtwert=bool(richt), datum=datum or datetime.date.today().isoformat(),
                **{k: (v or {}).get(k) for k in VERBRAUCH if _zahl((v or {}).get(k))})


VERBRAUCH = ("dichte", "draht_eur_kg", "gas_l_min", "gas_eur_l")     # Schweißverfahren (P5), leer = nicht rechnen


def verbrauch(naht, st, naht_m, lichtbogen_min):
    """Schweißzusatz und Schutzgas einer Nahtgruppe (P5): Draht [kg] = Nahtquerschnitt × Naht × Dichte, Gas [l] =
    Lichtbogenzeit × Gasverbrauch; Kosten mit den Preisen des Verfahrens. Fehlt ein Preis oder Wert, zählt der Teil
    0 € und hinweis nennt, was fehlt (nur wenn das Verfahren überhaupt Verbrauchswerte hat).
    Ergebnis: dict(draht_kg, gas_l, material, hinweis)."""
    out = dict(draht_kg=0.0, gas_l=0.0, material=0.0, hinweis=None)
    if not any(_zahl(st.get(k)) for k in VERBRAUCH):
        return out
    fehlt = []
    if _zahl(naht.get("mass")) and _zahl(st.get("dichte")):
        out["draht_kg"] = nahtquerschnitt(naht.get("nahtart"), naht["mass"]) * naht_m * st["dichte"] / 1000
    elif not _zahl(st.get("dichte")):
        fehlt.append("Dichte Zusatz")
    if lichtbogen_min and _zahl(st.get("gas_l_min")):
        out["gas_l"] = lichtbogen_min * st["gas_l_min"]
    elif not _zahl(st.get("gas_l_min")):
        fehlt.append("Gasverbrauch")
    elif _zahl(naht.get("zeit_hand")):     # Zeit von Hand: Lichtbogenzeit unbekannt, Gas nicht schätzen
        fehlt.append("Lichtbogenzeit (Zeit von Hand) für Gas")
    if out["draht_kg"] and not _zahl(st.get("draht_eur_kg")):
        fehlt.append("Preis Draht")
    if out["gas_l"] and not _zahl(st.get("gas_eur_l")):
        fehlt.append("Preis Gas")
    out["material"] = out["draht_kg"] * _n(st.get("draht_eur_kg")) + out["gas_l"] * _n(st.get("gas_eur_l"))
    out["hinweis"] = ("Verbrauch: " + ", ".join(fehlt) + " fehlt (0 €)") if fehlt else None
    return out


def naht_rechnen(naht, tabellen, saetze):
    """Zeit und Kosten einer Nahtgruppe je Stück ihres Knotens: dict(naht_m, lichtbogen_min, heft_min, zeit_min,
    satz, kosten, hand, richtwert, fehlt). Stand der Nahtgruppe, sonst Stammdaten. fehlt = Grund, warum keine Zeit
    berechnet werden kann (dann Zeit 0, außer von Hand)."""
    st = naht.get("stand") if isinstance(naht.get("stand"), dict) else naht_stand(naht, tabellen)
    anzahl = _n(naht.get("anzahl")) if _zahl(naht.get("anzahl")) else 1
    seiten = 2 if naht.get("beidseitig") else 1
    naht_m = _n(naht.get("laenge")) * anzahl * seiten / 1000
    satz_id = st.get("satz_id")
    satz = saetze.get(satz_id) if satz_id else None
    out = dict(naht_m=naht_m, lichtbogen_min=0.0, heft_min=0.0, zeit_min=0.0, satz_id=satz_id, satz=satz, kosten=0.0,
               hand=False, richtwert=bool(st.get("richtwert")), fehlt=None)
    if _zahl(naht.get("zeit_hand")):
        out.update(zeit_min=naht["zeit_hand"], hand=True, richtwert=False)
    else:
        if not st.get("verfahren"):
            out["fehlt"] = f"Verfahren '{naht.get('verfahren') or ''}' unbekannt"
        elif not _zahl(naht.get("mass")):
            out["fehlt"] = "a-Maß fehlt" if naht.get("nahtart") == "Kehlnaht" else "Dicke fehlt"
        elif not _zahl(st.get("min_m")):
            out["fehlt"] = (f"kein Kennwert für {naht.get('verfahren')} {naht.get('nahtart') or ''} "
                            f"{_text(naht.get('mass'))} mm")
        elif not _zahl(st.get("lichtbogen")) or st["lichtbogen"] <= 0:
            out["fehlt"] = f"Lichtbogenzeitfaktor fehlt ({naht.get('verfahren')})"
        else:
            lb = naht_m * st["min_m"] * _n(st.get("f_lage") or 1) * _n(st.get("f_zugang") or 1) \
                * _n(st.get("f_qualitaet") or 1)
            heft = _n(naht.get("heftpunkte")) * anzahl * _n(st.get("heft_s")) / 60
            out.update(lichtbogen_min=lb, heft_min=heft, zeit_min=lb / (st["lichtbogen"] / 100) + heft)
    if out["zeit_min"] and not _zahl(satz):
        out["fehlt"] = out["fehlt"] or f"Stundensatz '{satz_id or ''}' fehlt"
    vb = verbrauch(naht, st, naht_m, out["lichtbogen_min"])
    out.update(draht_kg=vb["draht_kg"], gas_l=vb["gas_l"], material=vb["material"], verbrauch_hinweis=vb["hinweis"])
    out["kosten"] = out["zeit_min"] / 60 * _n(satz) + vb["material"]
    return out


def _text(w):
    if not _zahl(w):
        return ""
    return f"{w:g}".replace(".", ",")


# ------------------------------------------------------------------ Arbeitsgänge
def arbeitsgang_rechnen(ag, saetze):
    """Kosten eines Arbeitsgangs je Stück seines Knotens (laufend) und einmal je Auftrag (vor Umlage):
    dict(satz, laufend_min, laufend, einmal_min, einmal, umlage_faktor, fremd, fehlt)."""
    satz = ag.get("satz") if _zahl(ag.get("satz")) else saetze.get(ag.get("satz_id")) if ag.get("satz_id") else None
    menge = _n(ag.get("menge")) if _zahl(ag.get("menge")) else 1
    laufend_min = _n(ag.get("zeit_min")) * menge
    einmal_min = _n(ag.get("ruest_min"))
    umlage = ag.get("umlage") or UMLAGE_AUFTRAG
    f = {UMLAGE_WIEDER: 0.0, UMLAGE_ANTEILIG: _n(ag.get("anteil")) / 100}.get(umlage, 1.0)
    fehlt = None
    if (laufend_min or einmal_min) and not _zahl(satz):
        fehlt = f"Stundensatz fehlt ({ag.get('name') or 'Arbeitsgang'})"
    return dict(satz=satz, laufend_min=laufend_min,
                laufend=laufend_min / 60 * _n(satz) + _n(ag.get("kosten_einheit")) * menge,
                einmal_min=einmal_min, einmal=einmal_min / 60 * _n(satz) + _n(ag.get("einmal_eur")),
                umlage=umlage, umlage_faktor=f, fremd=bool(ag.get("fremd")), fehlt=fehlt)


# ------------------------------------------------------------------ Baugruppe rechnen
def rechnen(p, tabellen, saetze, anzahl=None):
    """Eigene Leistungen einer Baugruppen-Position je Baugruppe. anzahl = Baugruppen im Auftrag (Stufe), leer = Stückzahl
    der Position. Ergebnis: dict(eigen, fremd, einmal, einmal_fremd (Anteil Fremdleistung), einmal_gesamt, zeit_min, schweiss_min, naht_m {Verfahren: m},
    zeilen [{art, id, name, knoten, faktor, zeit_min, kosten, einmal, fremd, text}], fehler, warnungen, richtwert).
    eigen/fremd enthalten den umgelegten Einmalanteil (einmal)."""
    bg = lesen(p.get("baugruppe"))
    n = anzahl if anzahl is not None else p.get("stueck")
    n = n if _zahl(n) and n > 0 else 0
    out = dict(eigen=0.0, fremd=0.0, einmal=0.0, einmal_fremd=0.0, einmal_gesamt=0.0, zeit_min=0.0, schweiss_min=0.0, naht_m={},
               zeilen=[], fehler=None, warnungen=[], richtwert=False, wiederverwendbar=0, verbrauch=0.0)
    if bg is None:
        out["fehler"] = "Baugruppendaten fehlen"
        return out
    sf = struktur_fehler(bg)
    if sf:
        out["fehler"] = sf
        return out
    km = knoten_map(bg)

    def kname(kid):
        return (km.get(kid) or {}).get("name") or "" if kid else ""

    for nt in bg["naehte"]:
        f = faktor(bg, nt.get("knoten") or "")
        if f is None:
            out["warnungen"].append(f"Nahtgruppe {nt.get('nr') or ''}: Unterbaugruppe fehlt".replace("  ", " "))
            continue
        r = naht_rechnen(nt, tabellen, saetze)
        if r["fehlt"]:
            out["warnungen"].append(f"Nahtgruppe {nt.get('nr') or ''}: {r['fehlt']}".replace("  ", " "))
        out["richtwert"] |= r["richtwert"]
        v = nt.get("verfahren") or "?"
        out["naht_m"][v] = out["naht_m"].get(v, 0.0) + r["naht_m"] * f
        out["zeit_min"] += r["zeit_min"] * f
        out["schweiss_min"] += r["zeit_min"] * f
        out["eigen"] += r["kosten"] * f
        out["verbrauch"] += r["material"] * f
        out["zeilen"].append(dict(art="Naht", id=nt.get("id"), name=f"Nahtgruppe {nt.get('nr') or ''}".strip(),
                                  knoten=kname(nt.get("knoten")), faktor=f, zeit_min=r["zeit_min"] * f,
                                  kosten=r["kosten"] * f, einmal=0.0, fremd=False, werte=r))
    for ag in bg["arbeitsgaenge"]:
        f = faktor(bg, ag.get("knoten") or "")
        if f is None:
            out["warnungen"].append(f"{ag.get('name') or 'Arbeitsgang'}: Unterbaugruppe fehlt")
            continue
        r = arbeitsgang_rechnen(ag, saetze)
        if r["fehlt"]:
            out["warnungen"].append(r["fehlt"])
        if r["umlage"] == UMLAGE_WIEDER and r["einmal"]:
            out["wiederverwendbar"] += 1
        einmal = r["einmal"] * r["umlage_faktor"]
        out["einmal_gesamt"] += einmal
        je = r["laufend"] * f + (einmal / n if n else 0.0)
        out["zeit_min"] += r["laufend_min"] * f + (r["einmal_min"] * r["umlage_faktor"] / n if n else 0.0)
        out["einmal"] += einmal / n if n else 0.0
        if r["fremd"]:
            out["einmal_fremd"] += einmal / n if n else 0.0
        out["fremd" if r["fremd"] else "eigen"] += je
        out["zeilen"].append(dict(art="Arbeitsgang", id=ag.get("id"), name=ag.get("name") or "Arbeitsgang",
                                  knoten=kname(ag.get("knoten")), faktor=f, zeit_min=r["laufend_min"] * f,
                                  kosten=r["laufend"] * f, einmal=einmal, fremd=r["fremd"], werte=r))
    return out


KOSTENTEILE = ("Schweißen", "Arbeitsgänge", "Einmalkosten (umgelegt)", "Fremdleistung", "Schweißzusatz und Gas")


def kostenaufteilung(r):
    """Kosten je Baugruppe aus rechnen() nach KOSTENTEILE (Kostenbalken, D2): [(Bezeichnung, €)]; Summe = eigen + fremd.
    Schweißzusatz und Gas (P5) nur, wenn sie etwas kosten."""
    vb = r.get("verbrauch") or 0.0
    schweissen = sum(z["kosten"] for z in r["zeilen"] if z["art"] == "Naht") - vb
    arbeit = sum(z["kosten"] for z in r["zeilen"] if z["art"] == "Arbeitsgang" and not z["fremd"])
    fremd = r["fremd"] - r["einmal_fremd"]
    teile = list(zip(KOSTENTEILE, (schweissen, arbeit, r["einmal"], fremd, vb)))
    return teile if vb else teile[:4]


def groesste_posten(r, n=3):
    """Die n teuersten Zeilen (Nahtgruppe, Arbeitsgang) je Baugruppe inkl. umgelegter Einmalkosten: [(Name, €)]."""
    anteil = r["einmal"] / r["einmal_gesamt"] if r["einmal_gesamt"] else 0.0
    posten = [(z["name"], z["kosten"] + z["einmal"] * anteil) for z in r["zeilen"]]
    return sorted((x for x in posten if x[1] > 0), key=lambda x: -x[1])[:n]


def status(p, w, positionen=None):
    """Status einer Baugruppen-Position (wie rechnen.status): FEHLER, WARNUNG, HINWEIS oder OK."""
    if not _zahl(p.get("stueck")) or p["stueck"] < 1:
        return "FEHLER: Stückzahl fehlt (Anzahl Baugruppen)"
    df = daten_fehler(p.get("baugruppe"))
    if df:
        return "FEHLER: " + df
    bg = lesen(p.get("baugruppe"))
    sf = struktur_fehler(bg)
    if sf:
        return "FEHLER: " + sf
    for liste, titel in ((bg["naehte"], "Nahtgruppe"), (bg["arbeitsgaenge"], "Arbeitsgang")):
        for x in liste:
            for feld in ("laenge", "anzahl", "mass", "zeit_hand", "heftpunkte", "zeit_min", "ruest_min", "menge",
                         "kosten_einheit", "einmal_eur", "satz", "anteil"):
                if _zahl(x.get(feld)) and x[feld] < 0:
                    return f"FEHLER: {titel} {x.get('nr') or x.get('name') or ''}: negativer Wert".replace("  ", " ")
    r = rechnen(p, (w or {}).get("bg_tabellen") or {}, (w or {}).get("saetze") or {})
    if r["fehler"]:
        return "FEHLER: " + r["fehler"]
    if r["warnungen"]:
        return "WARNUNG: " + r["warnungen"][0]
    if positionen is not None:
        if not teile(positionen, bg["id"]):
            return "WARNUNG: Baugruppe ohne Einzelteile"
        for i, q in enumerate(positionen):
            t = teil_pruefen(q, positionen) if not ist_baugruppe(q) and zuordnung(q)[0] == bg["id"] else None
            if t:
                return f"WARNUNG: Pos. {q.get('pos') or i + 1}: {t}"
        doppelt = doppelt_schweissen(p, positionen)
        if doppelt:
            return "WARNUNG: " + doppelt
    if not bg["naehte"] and not bg["arbeitsgaenge"]:
        return "HINWEIS: keine Nahtgruppen und Arbeitsgänge"
    if r["richtwert"]:
        return "HINWEIS: Schweißzeit aus ungeprüften Richtwerten"
    regel = next((n for n in bg["naehte"] if regel_offen(n)), None)
    if regel:
        return f"HINWEIS: Nahtgruppe {regel.get('nr') or ''}: a-Maß nach Regel, bitte bestätigen".replace("  ", " ")
    if r["wiederverwendbar"]:
        return "HINWEIS: wiederverwendbare Vorrichtung nicht berechnet"
    return "OK"


def doppelt_schweissen(p, positionen):
    """Text, wenn die Baugruppe Nahtgruppen hat und eines ihrer Teile zusätzlich die Zusatzarbeit Schweißen trägt."""
    bg = lesen(p.get("baugruppe"))
    if not bg or not bg["naehte"]:
        return None
    from .stammdaten import ZUSATZ_SCHWEISSEN
    for j in teile(positionen, bg["id"]):
        q = positionen[j]
        try:
            liste = json.loads(q.get("zusatz") or "[]")
        except (TypeError, ValueError):
            continue
        if any(isinstance(e, dict) and e.get("name") == ZUSATZ_SCHWEISSEN for e in liste):
            return f"Pos. {q.get('pos') or j + 1} hat zusätzlich Zusatzarbeit Schweißen (doppelt?)"
    return None


STAMM_WAHL = (("stueckliste", "Stückliste im Angebot zeigen",
               "Unter der Angebotszeile der Baugruppe die Einzelteile auflisten (ohne Preise)"),
              ("einmal_getrennt", "Einmalkosten als eigene Zeile im Angebot",
               "Rüsten und Vorrichtungen der Baugruppe nicht in den Stückpreis umlegen, sondern einmalig ausweisen"))


def zeile_angebot(p):
    """Text der Angebotszeile einer Baugruppe (eine Zeile je Baugruppe, Plan-Freigabe 7a): Name, darunter Zeichnung
    mit Revision, Werkstoff, Oberfläche und Beschreibung aus den Stammdaten der Baugruppe."""
    bg = lesen(p.get("baugruppe")) or {}
    st = bg.get("stamm") or {}
    zeilen = [f"Schweißbaugruppe {name(p, bg)}"]
    if st.get("zeichnung"):
        zeilen.append(f"Zeichnung {st['zeichnung']}" + (f" Rev. {st['revision']}" if st.get("revision") else ""))
    for n in ("werkstoff", "oberflaeche", "beschreibung"):
        if str(st.get(n) or "").strip():
            zeilen.append(str(st[n]).strip())
    return "\n".join(zeilen)


def stamm_wahl(p, n):
    """Häkchen aus den Stammdaten der Baugruppe: 'stueckliste' (Einzelteile im Angebot zeigen), 'einmal_getrennt'
    (Einmalkosten als eigene Zeile)."""
    return bool(((lesen(p.get("baugruppe")) or {}).get("stamm") or {}).get(n))


def text_angebot(p):
    """Zeile der Baugruppen-Position im Angebot (Satzteil): 'Schweißen und Fertigung der Baugruppe'."""
    bg = lesen(p.get("baugruppe")) or {}
    st = bg.get("stamm") or {}
    zeilen = ["Schweißen und Fertigung der Baugruppe"]
    if st.get("zeichnung"):
        zeilen.append(f"Zeichnung {st['zeichnung']}" + (f" Rev. {st['revision']}" if st.get("revision") else ""))
    return "\n".join(zeilen)


# ------------------------------------------------------------------ Richtwerte (Knopf 'Richtwerte laden')
# Herleitung statt Erfahrungszahlen: Lichtbogenzeit = Nahtvolumen × Dichte ÷ Abschmelzleistung. Nahtquerschnitt
# Kehlnaht = a² × 1,1 (Nahtüberhöhung), Stumpf-/Ecknaht (V-Naht 60°, Spalt 1,5 mm, ab 3 mm) = (t² × tan 30° +
# 1,5 × t) × 1,1, bis 3 mm I-Naht = 1,5 × t × 1,1. Abschmelzleistungen sind übliche Handwerte je Verfahren und
# müssen an die eigene Fertigung angepasst werden (Status 'Richtwert').
RICHT_VERFAHREN = (
    # Verfahren, Bezeichnung, Abschmelzleistung kg/h, Dichte kg/dm³, Lichtbogenzeitfaktor %, Heftpunkt s
    ("MAG", "Metall-Aktivgas (Stahl), Hand", 3.5, 7.85, 35, 8),
    ("MIG", "Metall-Inertgas (Aluminium), Hand", 2.0, 2.70, 30, 8),
    ("WIG", "Wolfram-Inertgas, Hand", 0.8, 7.85, 30, 10),
    ("E-Hand", "Lichtbogenhandschweißen mit Stabelektrode", 1.5, 7.85, 25, 12),
    ("Roboter MAG", "Roboterschweißen MAG", 5.0, 7.85, 70, 0),
)
RICHT_MASSE = {"Kehlnaht": (2, 3, 4, 5, 6, 8, 10), "Stumpfnaht": (2, 3, 4, 5, 6, 8, 10, 12, 15, 20),
               "Ecknaht": (2, 3, 4, 5, 6, 8, 10)}
RICHT_FAKTOREN = (("Schweißlage", "PA", 1.0), ("Schweißlage", "PB", 1.0), ("Schweißlage", "PC", 1.2),
                  ("Schweißlage", "PD", 1.4), ("Schweißlage", "PE", 1.6), ("Schweißlage", "PF", 1.3),
                  ("Schweißlage", "PG", 1.1), ("Zugänglichkeit", "gut", 1.0), ("Zugänglichkeit", "eingeschränkt", 1.25),
                  ("Zugänglichkeit", "schlecht", 1.6), ("Qualität", "normal", 1.0), ("Qualität", "erhöht", 1.2),
                  ("Qualität", "Sichtnaht", 1.4))


def nahtquerschnitt(nahtart, mass):
    """Nahtquerschnitt [mm²] für die Richtwerte (siehe oben)."""
    if nahtart == "Kehlnaht":
        return mass * mass * 1.1
    if mass <= 3:
        return 1.5 * mass * 1.1
    return (mass * mass * math.tan(math.radians(30)) + 1.5 * mass) * 1.1


def richtwerte():
    """Zeilen für Schweißverfahren, Schweiß-Kennwerte und Schweiß-Faktoren mit Status 'Richtwert'."""
    verfahren, kennwerte, faktoren = [], [], []
    for v, bez, kg_h, dichte, lb, heft in RICHT_VERFAHREN:
        verfahren.append(dict(verfahren=v, bezeichnung=bez, satz_id="Schweißen", lichtbogen=lb, heft_s=heft or None,
                              aktiv="ja", status="Richtwert",
                              bemerkung=f"Richtwert: Abschmelzleistung {_text(kg_h)} kg/h, Lichtbogenzeit {lb} % "
                                        "der Arbeitszeit, bitte an die eigene Fertigung anpassen"))
        for art, masse in RICHT_MASSE.items():
            for m in masse:
                kg_m = nahtquerschnitt(art, m) * dichte / 1000          # mm² × kg/dm³ / 1000 = kg je m
                kennwerte.append(dict(verfahren=v, nahtart=art, mass_bis=m, min_m=round(kg_m / kg_h * 60, 2),
                                      status="Richtwert",
                                      bemerkung=f"hergeleitet: {_text(round(nahtquerschnitt(art, m), 1))} mm² × "
                                                f"{_text(dichte)} kg/dm³ ÷ {_text(kg_h)} kg/h"))
    for art, wert, f in RICHT_FAKTOREN:
        faktoren.append(dict(art=art, wert=wert, faktor=f, status="Richtwert",
                             bemerkung=(LAGEN.get(wert, "") + ", " if wert in LAGEN else "") + "Richtwert"))
    return dict(schweissverfahren=verfahren, schweiss_kennwerte=kennwerte, schweiss_faktoren=faktoren)


SCHLUESSEL = {"schweissverfahren": ("verfahren",), "schweiss_kennwerte": ("verfahren", "nahtart", "mass_bis"),
              "schweiss_faktoren": ("art", "wert")}


def richtwerte_fehlend(tabellen):
    """Richtwert-Zeilen, die in den Stammdaten noch fehlen (gleicher Schlüssel = vorhanden, wird nie geändert)."""
    out = {}
    for name, zeilen in richtwerte().items():
        da = {tuple(z.get(k) for k in SCHLUESSEL[name]) for z in tabellen.get(name) or ()}
        out[name] = [z for z in zeilen if tuple(z.get(k) for k in SCHLUESSEL[name]) not in da]
    return out


def arbeitsgang_vorlage(z):
    """Arbeitsgang aus einer Zusatzarbeit der Stammdaten (Katalog): Name, Stundensatz-ID oder eigener Satz, Zeit je
    Einheit in min, Kosten je Einheit (Festpreis bei €/Stück, €/kg, €/m², €/m, dazu Material; die Menge in kg, m² bzw.
    m trägt man im Arbeitsgang ein), Einmalbetrag bei €/Angebot, Fremdleistung. Werte, die die Zusatzarbeit nicht hat,
    bleiben leer; s/Stück (Laserzeit) gibt es an der Baugruppe nicht."""
    from .stammdaten import ZEITEINHEITEN
    ag = dict(id=neue_id(), name=z.get("name"), umlage=UMLAGE_AUFTRAG, fremd=z.get("fremd") == "ja" or None,
              vorlage=z.get("name"))
    if z.get("satz_id"):
        ag["satz_id"] = z["satz_id"]
    elif _zahl(z.get("satz")):
        ag["satz"] = z["satz"]
    if _zahl(z.get("zeit")) and z["zeit"] > 0:
        ag["zeit_min"] = round(z["zeit"] * ZEITEINHEITEN.get(z.get("zeit_einheit") or "s", 1) / 60, 4)
    preis = z.get("preis") if _zahl(z.get("preis")) else 0
    kosten = (preis if z.get("art") in ("€/Stück", "€/kg", "€/m²", "€/m") else 0) + _n(z.get("material"))
    if kosten:
        ag["kosten_einheit"] = kosten
    if z.get("art") == "€/Angebot" and preis:
        ag["einmal_eur"] = preis
    return {k: v for k, v in ag.items() if v is not None}


# ------------------------------------------------------------------ Vorlagen (P1) und Kopie in ein anderes Angebot (P7)
def vorlage_aus(bg):
    """Vorlage einer Baugruppe: Stammdaten, Unterbaugruppen, Nahtgruppen und Arbeitsgänge ohne Einzelteile, ohne
    gemerkte Kennwerte (beim Einsetzen gelten die aktuellen Stammdaten) und ohne Nahtkandidaten aus STEP."""
    out = json.loads(speichern(bg))
    out.pop("vorschlaege", None)
    out.pop("id", None)
    out.pop("vorlage", None)
    for n in out["naehte"]:
        n.pop("stand", None)
    return out


def vorlage_inhalt(v):
    """Kurztext einer Vorlage für die Auswahl: Anzahl Unterbaugruppen, Nahtgruppen, Arbeitsgänge."""
    teile = [(len(v.get("knoten") or ()), "Unterbaugruppe", "Unterbaugruppen"),
             (len(v.get("naehte") or ()), "Nahtgruppe", "Nahtgruppen"),
             (len(v.get("arbeitsgaenge") or ()), "Arbeitsgang", "Arbeitsgänge")]
    return ", ".join(f"{n} {e if n == 1 else m}" for n, e, m in teile)


def vorlage_einsetzen(bg, v, name=None):
    """Vorlage v in die Baugruppe bg übernehmen (Kennung von bg bleibt, damit zugeordnete Teile dabei bleiben; Nahtkandidaten
    aus STEP bleiben). Ergebnis: Kennungen der Unterbaugruppen der Vorlage (Teile und Kandidaten in anderen
    Unterbaugruppen kommen an die Baugruppe). name = Name der Vorlage (Verlauf in der Nachkalkulation, D5)."""
    v = json.loads(json.dumps(v))
    if name:
        bg["vorlage"] = name
    bg["stamm"] = v.get("stamm") if isinstance(v.get("stamm"), dict) else {}
    for liste in ("knoten", "arbeitsgaenge", "naehte"):
        bg[liste][:] = [x for x in v.get(liste) or () if isinstance(x, dict)]     # gleiche Liste (Tabellen im Editor)
    for n in bg["naehte"]:
        n.pop("stand", None)
    knoten = {k["id"] for k in bg["knoten"] if k.get("id")}
    for v in bg.get("vorschlaege") or ():           # Nahtkandidaten aus STEP bleiben, ohne alte Unterbaugruppe
        if v.get("knoten") and v["knoten"] not in knoten:
            v["knoten"] = ""
    return knoten


def kopie(positionen, bg_id, pos_start=10, schritt=10):
    """Baugruppe bg_id mit ihren Einzelteilen für ein anderes Angebot (P7): neue Kennung der Baugruppe, Zuordnung der
    Teile umgeschrieben, Pos.-Nummern ab pos_start in der Reihenfolge des Angebots. Ergebnis: [(alte Position,
    neue Werte)] (Baugruppe zuerst) oder [] ohne lesbare Baugruppe."""
    alle = baugruppen(positionen)
    if bg_id not in alle:
        return []
    i, bg = alle[bg_id]
    neu_id = neue_id()
    bg = json.loads(speichern(bg))
    bg["id"] = neu_id
    out = [(positionen[i], dict(positionen[i], baugruppe=speichern(bg)))]
    for j in teile(positionen, bg_id):
        q = positionen[j]
        out.append((q, dict(q, bg_knoten=zuordnung_text(neu_id, zuordnung(q)[1] or ""))))
    for n, (_, w) in enumerate(out):
        w["pos"] = pos_start + n * schritt
        for f in ("id", "angebot_id", "nr"):
            w.pop(f, None)
    return out
