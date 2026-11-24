"""Richtwerte der Maschinen aktualisieren (Patrick 16.11.2026 „Alle Werte zur Berechnung mit recherchierten Werten
füllen, … Option zum Updaten der Einstellungen einbauen“).

Die mitgelieferten Richtwerte (stammdaten.*_RICHTWERTE) kommen beim Update einmal in leere Felder. Ändern sich die
Richtwerte später (neue Recherche, neue Programmversion), zeigt „Richtwerte aktualisieren …“ einen Vergleich je
Maschine und Feld: aktueller Wert, neuer Richtwert und Art des aktuellen Werts. Vorgeschlagen (angehakt) werden nur
Werte, die der Nutzer nicht selbst geändert hat: leere Felder und Werte, die das Programm selbst eingetragen hat
(Merker ``richtwerte_eingetragen`` je Maschine und Feld) bzw. frühere Richtwerte. Eigene Werte bleiben, solange man
sie nicht selbst anhakt.
"""
from . import stammdaten as sd

MERKER = "richtwerte_eingetragen"       # Einstellung {maschinen_id: {feld: wert}}: vom Programm eingetragene Werte

LEER, ALT, EIGEN, FEST = "leer", "Richtwert alt", "eigener Wert", "fester Wert gilt"

# frühere Richtwerte, die als „nicht selbst geändert“ gelten: {feld: {maschinen_id: (Werte, …)}}
FRUEHER = {"beschl_dreh": {m: (w,) for m, w in sd.ALTE_DREHBESCHL.items()}}


def gruppen():
    """[(Gruppenname, Felder, Richtwerte je Maschine)] aller mitgelieferten Richtwerte."""
    return [("Dynamik", sd.DYNAMIK_FELDER, sd.DYNAMIK_RICHTWERTE),
            ("Einstechen", sd.EINSTICH_FELDER, sd.EINSTICH_RICHTWERTE),
            ("Zeiten", sd.ZEITEN_FELDER, sd.ZEITEN_RICHTWERTE),
            ("Kopfweg und Vorschub", sd.KOPFWEG_FELDER, sd.KOPFWEG_RICHTWERTE),
            ("Werkstoff", sd.WERKSTOFF_FELDER, sd.WERKSTOFF_RICHTWERTE),
            ("Grenzen und Zuschläge", sd.WEITERE_FELDER, sd.WEITERE_RICHTWERTE)]


def richtwerte(maschinen_id):
    """{feld: (Richtwert, Gruppe)} für die Maschine (nur T03, T11, LT7)."""
    out = {}
    for name, felder, werte in gruppen():
        for feld, w in zip(felder, werte.get(maschinen_id) or ()):
            out[feld] = (w, name)
    return out


def _gleich(a, b):
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) < 1e-9
    return a == b


def _leer(w):
    return w in (None, "")


def _fest_gesetzt(z, feld):
    """Feld mit Bedingung (stammdaten.ZEITEN_NUR_WENN), dessen fester Wert selbst gesetzt ist: dann gilt der feste
    Wert, der Richtwert würde nicht rechnen."""
    bed = sd.ZEITEN_NUR_WENN.get(feld)
    if not bed:
        return False
    w = z.get(bed[0])
    return not (_leer(w) if bed[1] is None else (_leer(w) or _gleich(w, bed[1])))


def vergleich(maschinen, eingetragen=None):
    """Vergleich je Maschine und Feld, wo der aktuelle Wert vom Richtwert abweicht: [dict(id, maschinen_id, feld,
    titel, gruppe, aktuell, richtwert, art, vorschlag, quelle)]; vorschlag = True für leere und vom Programm
    eingetragene bzw. frühere Richtwerte (nicht selbst geändert)."""
    eingetragen = eingetragen or {}
    out = []
    for z in maschinen:
        mid = z.get("maschinen_id")
        mein = eingetragen.get(mid) or {}
        for feld, (rw, gruppe) in richtwerte(mid).items():
            if feld not in _namen():
                continue
            akt = z.get(feld)
            if _gleich(akt, rw):
                continue
            if _leer(akt):
                art = FEST if _fest_gesetzt(z, feld) else LEER
            elif feld in mein and _gleich(akt, mein[feld]) or any(_gleich(akt, w) for w in
                                                                    (FRUEHER.get(feld) or {}).get(mid, ())):
                art = ALT
            else:
                art = EIGEN
            out.append(dict(id=z.get("id"), maschinen_id=mid, feld=feld, titel=sd.MASCHINEN.feld(feld).titel,
                            gruppe=gruppe, aktuell=akt, richtwert=rw, art=art, vorschlag=art in (LEER, ALT),
                            quelle=sd.RICHTWERT_QUELLE.get(feld, "Schätzung")))
    return out


def _namen():
    return {f.name for f in sd.MASCHINEN.felder}


def anzahl_vorschlaege(maschinen, eingetragen=None):
    return sum(1 for v in vergleich(maschinen, eingetragen) if v["vorschlag"])


def merken(eingetragen, maschinen_id, feld, wert):
    """eingetragen (dict) um einen vom Programm eingetragenen Wert ergänzen; Ergebnis dasselbe dict."""
    eingetragen.setdefault(maschinen_id, {})[feld] = wert
    return eingetragen


def uebernehmen(db, zeilen):
    """Ausgewählte Vergleichszeilen (vergleich) in die Maschinen schreiben und als vom Programm eingetragen merken;
    Ergebnis Anzahl geänderter Werte."""
    eingetragen = db.einstellung(MERKER) or {}
    n = 0
    for v in zeilen:
        db.aendern("maschinen", v["id"], v["feld"], v["richtwert"])
        merken(eingetragen, v["maschinen_id"], v["feld"], v["richtwert"])
        n += 1
    if n:
        db.einstellung_setzen(MERKER, eingetragen)
    return n


def text(w):
    if _leer(w):
        return "leer"
    if isinstance(w, float) and w.is_integer():
        w = int(w)
    return str(w).replace(".", ",") if isinstance(w, (int, float)) else str(w)
