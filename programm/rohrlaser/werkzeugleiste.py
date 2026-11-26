"""Meine Werkzeugleiste, Schnellzugriffe, Dashboard-Layout und Arbeitsbereiche (Großes Design- und Layout-Update,
Patrick 19.11.2026, Punkte 3, 4, 8 und 9). Nur Daten, ohne Qt: die Oberfläche steht in werkzeugleiste_qt.py und
werkzeugleiste_dialog.py, die Aktionen in aktionen.py.

Gemerkt wird je Benutzer (Kürzel des angemeldeten Benutzers, sonst des Arbeitsplatzes) in der eigenen Datendatei
dieses Platzes. Die Namen beginnen mit „leiste_“ und stehen nicht in stammdaten.EINSTELLUNGEN: sie gehen nie über
den gemeinsamen Ordner, das persönliche Profil (einstellungen_extras.PROFIL_VORSILBEN) nimmt sie mit.

Aufbau der Werkzeugleiste (leiste(db)):
    {"knoepfe": [{"id": "angebot_neu", "text": "", "symbol": "", "farbe": ""}, {"gruppe": "Kalkulation"}, …],
     "kontext": {"angebot": ["kalk_starten", …], …},   # fehlender Kontext = KONTEXT_VORGABE
     "kontext_an": True, "groesse": "mittel", "beschriftung": "neben", "tasten": {"angebot_neu": "Ctrl+Alt+N"},
     "sichtbar": True}
Ein Eintrag mit "gruppe" ist ein Trenner mit Gruppentitel ("" = nur Trennstrich).

Standardlayouts je Benutzergruppe (Punkt 8): Der Admin legt sie fest (Rolle → Leiste, Startseite, Schnellzugriffe).
Sie stehen in der Datei Admin/oberflaeche_vorgaben.json im gemeinsamen Ordner und zusätzlich hier (VORGABEN), damit
sie auch ohne Ordner gelten. Ein Benutzer ohne eigene Leiste bekommt die Vorgabe seiner ersten Rolle, sonst die
eingebaute (ROLLEN_VORGABE, LEISTE_VORGABE).
"""
import copy
import datetime
import json

LEISTE = "leiste_werkzeugleiste"        # {Kürzel: Aufbau}
ZULETZT = "leiste_zuletzt"              # {Kürzel: [Aktions-ID]} neueste zuerst
SCHNELL = "leiste_schnellzugriffe"      # {Kürzel: [Aktions-ID]}
START = "leiste_startseite"             # {Kürzel: {"oben": [...], "links": [...], "rechts": [...]}}
PROFILE = "leiste_profile"              # {Kürzel: {Name: Schnappschuss}}
INFO = "leiste_info_panel"              # {Kürzel: True/False}
VORGABEN = "leiste_vorgaben"            # {Rolle: {"leiste": …, "startseite": …, "schnell": …}} (Kopie der Datei)
DATEI = ("Admin", "oberflaeche_vorgaben.json")
ZULETZT_MAX = 10

GROESSEN = (("klein", "Klein (16 px)", 16), ("mittel", "Mittel (22 px)", 22), ("gross", "Groß / Tablet (32 px)", 32))
GROESSE_PX = {n: px for n, _, px in GROESSEN}
BESCHRIFTUNGEN = (("neben", "Text neben dem Symbol"), ("unter", "Text unter dem Symbol"), ("aus", "Nur Symbol"))
# Knopffarben aus dem Designsystem (design.py): neutral, Akzent und die Statusfarben
FARBEN = (("", "Neutral"), ("akzent", "Akzent (Dunkelblau)"), ("gruen", "Grün"), ("orange", "Orange"), ("rot", "Rot"))

LEISTE_VORGABE = {
    "knoepfe": [{"id": "angebot_neu", "farbe": "akzent"}, {"id": "angebot_neu_step"}, {"id": "angebote_letzte"},
                {"gruppe": ""}, {"id": "suchen"}, {"id": "favoriten"}],
    "kontext": {}, "kontext_an": True, "groesse": "mittel", "beschriftung": "neben", "tasten": {}, "sichtbar": False}
# Vorgabe aus seit UI Next Level (Patrick 26.11.2026, F3): wer die Leiste angepasst hat, behält seine (sichtbar=True);
# einschalten unter Ansicht → Meine Werkzeugleiste
# Kontextabhängige Knöpfe (Punkt 3.3): erscheinen rechts neben den eigenen, je nach Arbeitsbereich
KONTEXT_VORGABE = {
    "start": ["kalk_neu", "mat_suchen", "startseite_anpassen"],
    "angebotsliste": ["angebot_oeffnen", "angebot_kopieren", "angebote_vergleichen", "prod_uebergeben", "dok_ordner"],
    "angebot": ["angebot_speichern", "kalk_starten", "teil_neu", "teil_importieren", "d3_ansicht", "kalk_pruefen",
                "dok_ordner", "pdf_angebot"],
    "anfragen": ["angebot_neu_step", "abgleichen"],
    "auftraege": ["prod_status", "nav_produktion", "nav_auswertung"],
    "produktion": ["prod_fertigmeldung", "nav_auftraege", "kalk_aktualisieren"],
    "pflege": ["mat_suchen", "mat_preise", "kalk_aktualisieren"],
    "einstellungen": ["leiste_konfigurieren", "startseite_anpassen", "thema"],
}
# eingebaute Vorgaben je Rolle (rollen.ROLLEN); der Admin kann sie überschreiben (VORGABEN)
ROLLEN_VORGABE = {
    "werkstatt": {"knoepfe": [{"id": "nav_produktion", "farbe": "akzent"}, {"id": "prod_fertigmeldung", "farbe": "gruen"},
                              {"id": "prod_status"}, {"gruppe": ""}, {"id": "suchen"}],
                  "groesse": "gross", "beschriftung": "unter"},
    "versand": {"knoepfe": [{"id": "nav_auftraege", "farbe": "akzent"}, {"id": "prod_status"}, {"gruppe": ""},
                            {"id": "suchen"}]},
    "qs": {"knoepfe": [{"id": "nav_auftraege", "farbe": "akzent"}, {"id": "prod_pruefplan"}, {"gruppe": ""},
                       {"id": "suchen"}]},
}
SCHNELL_VORGABE = ["angebot_neu", "angebot_neu_step", "kalk_neu", "mat_suchen", "mat_preise", "dok_ablage",
                   "nav_anfragen", "leiste_konfigurieren"]
# Karten der Startseite (Punkt 4); Titel für den Dialog „Dashboard anpassen“
KARTEN = (("kacheln", "Kennzahlen Angebote (Entwürfe, offen, Aufträge, Trefferquote)"),
          ("auftrag_kacheln", "Kennzahlen Aufträge"), ("anfragen_kacheln", "Kennzahlen Anfragen"),
          ("anfragen", "Neue Anfragen"), ("angebote", "Angebote und zuletzt bearbeitet"),
          ("heute", "Heute: Pipeline, Wiedervorlage, Notizen, Automatik"),
          ("schnellzugriffe", "Schnellzugriffe und zuletzt verwendet"), ("stammdaten", "Stammdaten"),
          ("sicherung", "Systemstatus: Daten und Sicherung"))
KARTE_TITEL = dict(KARTEN)
OBEN_KARTEN = ("kacheln", "auftrag_kacheln", "anfragen_kacheln")      # Kachelzeilen: nur oben
START_VORGABE = {"oben": ["kacheln", "auftrag_kacheln", "anfragen_kacheln"], "links": ["anfragen", "angebote"],
                 "rechts": ["heute", "schnellzugriffe", "stammdaten", "sicherung"]}

# Arbeitsbereiche (Punkt 9): eingebaute Layoutprofile; eigene speichert der Benutzer unter einem Namen
EINGEBAUT = {
    "Standard": {"leiste": LEISTE_VORGABE, "startseite": START_VORGABE, "info": False, "dichte": "normal"},
    "Kalkulation": {"leiste": dict(LEISTE_VORGABE, knoepfe=[
        {"id": "angebot_neu", "farbe": "akzent"}, {"id": "angebote_letzte"}, {"gruppe": "Kalkulation"},
        {"id": "kalk_material"}, {"id": "kalk_maschinen"}, {"id": "kalk_staffeln"}, {"id": "kalk_gesamt"},
        {"gruppe": ""}, {"id": "suchen"}]), "info": True, "dichte": "normal"},
    "Angebot": {"leiste": dict(LEISTE_VORGABE, knoepfe=[
        {"id": "angebot_neu", "farbe": "akzent"}, {"id": "angebote_letzte"}, {"gruppe": "Angebot"},
        {"id": "angebot_mail"}, {"id": "dok_akte"}, {"id": "angebot_fertigstellen", "farbe": "gruen"},
        {"gruppe": ""}, {"id": "suchen"}]), "info": True, "dichte": "normal"},
    "Tablet": {"leiste": dict(LEISTE_VORGABE, groesse="gross", beschriftung="unter"), "info": False,
               "dichte": "komfortabel", "navigation": "breit"},
}


# ------------------------------------------------------------------ Benutzer
def benutzer(db):
    """Kürzel, für das die Oberfläche gemerkt wird: angemeldeter Benutzer, sonst dieser Arbeitsplatz ('' = keins)."""
    try:
        from . import rollen
        return rollen.angemeldet(db) or ""
    except Exception:           # noqa: BLE001 – ohne Benutzerverwaltung
        return ""


def rollen_von(db, k=None):
    try:
        from . import rollen
        if not rollen.aktiv(db):
            return []
        return list((rollen.benutzer(db).get(k if k is not None else benutzer(db)) or {}).get("rollen") or [])
    except Exception:           # noqa: BLE001
        return []


def _alle(db, name):
    v = db.einstellung(name)
    return dict(v) if isinstance(v, dict) else {}


def _je_benutzer(db, name, k=None):
    return _alle(db, name).get(benutzer(db) if k is None else k)


def _setzen(db, name, wert, k=None):
    if getattr(db, "nur_lesen", False):
        return False
    alle = _alle(db, name)
    k = benutzer(db) if k is None else k
    if wert is None:
        alle.pop(k, None)
    else:
        alle[k] = wert
    db.einstellung_setzen(name, alle)
    return True


# ------------------------------------------------------------------ Werkzeugleiste
def sauber(leiste):
    """Aufbau prüfen und ergänzen: unbekannte Aktionen fallen weg, fehlende Werte aus LEISTE_VORGABE."""
    from .aktionen import AKTION, KONTEXT_TITEL
    roh = leiste if isinstance(leiste, dict) else {}
    aus = copy.deepcopy(LEISTE_VORGABE)
    for k in ("kontext_an", "sichtbar"):
        if isinstance(roh.get(k), bool):
            aus[k] = roh[k]
    if roh.get("groesse") in GROESSE_PX:
        aus["groesse"] = roh["groesse"]
    if roh.get("beschriftung") in dict(BESCHRIFTUNGEN):
        aus["beschriftung"] = roh["beschriftung"]
    if isinstance(roh.get("knoepfe"), list):
        knoepfe = []
        for e in roh["knoepfe"]:
            if isinstance(e, str):
                e = {"id": e}
            if not isinstance(e, dict):
                continue
            if "gruppe" in e:
                knoepfe.append({"gruppe": str(e.get("gruppe") or "")[:40]})
            elif e.get("id") in AKTION:
                knoepfe.append({"id": e["id"], **{n: str(e[n])[:60] for n in ("text", "symbol", "farbe") if e.get(n)}})
        aus["knoepfe"] = knoepfe
    if isinstance(roh.get("kontext"), dict):
        aus["kontext"] = {k: [a for a in v if a in AKTION] for k, v in roh["kontext"].items()
                          if k in KONTEXT_TITEL and isinstance(v, list)}
    if isinstance(roh.get("tasten"), dict):
        aus["tasten"] = {a: str(t) for a, t in roh["tasten"].items() if a in AKTION and t}
    return aus


def vorgabe(db, k=None):
    """Leiste für einen Benutzer ohne eigene: Admin-Vorgabe seiner Rolle, eingebaute Rollenvorgabe, sonst Standard."""
    vorgaben = _alle(db, VORGABEN)
    for r in rollen_von(db, k):
        if isinstance((vorgaben.get(r) or {}).get("leiste"), dict):
            return sauber(vorgaben[r]["leiste"])
    for r in rollen_von(db, k):
        if r in ROLLEN_VORGABE:
            return sauber(dict(LEISTE_VORGABE, **ROLLEN_VORGABE[r]))
    return sauber(LEISTE_VORGABE)


def leiste(db, k=None):
    eigene = _je_benutzer(db, LEISTE, k)
    return sauber(eigene) if isinstance(eigene, dict) else vorgabe(db, k)


def leiste_setzen(db, wert, k=None):
    return _setzen(db, LEISTE, sauber(wert) if wert is not None else None, k)


def kontext_knoepfe(lst, kontext):
    """Aktions-IDs der kontextabhängigen Knöpfe (ohne die, die schon fest in der Leiste stehen)."""
    if not lst.get("kontext_an", True):
        return []
    ids = lst.get("kontext", {}).get(kontext)
    if ids is None:
        ids = KONTEXT_VORGABE.get(kontext, [])
    fest = {e.get("id") for e in lst.get("knoepfe", ())}
    return [a for a in ids if a not in fest]


def tasten(db, k=None):
    return dict(leiste(db, k).get("tasten") or {})


def tasten_konflikte(eigene, vorhandene):
    """Eigene Tastenkürzel, die schon ein Menüpunkt hat: [(Aktion, Taste, Menüpunkt)]. vorhandene = {Taste: Text}."""
    norm = {str(t).replace(" ", "").lower(): text for t, text in vorhandene.items() if t}
    aus = []
    gesehen = {}
    for a, t in eigene.items():
        n = str(t).replace(" ", "").lower()
        if n in norm:
            aus.append((a, t, norm[n]))
        elif n in gesehen:
            aus.append((a, t, gesehen[n]))
        gesehen[n] = a
    return aus


# ------------------------------------------------------------------ Zuletzt verwendet, Schnellzugriffe
def benutzt(db, aid):
    """Aktion als zuletzt verwendet merken (höchstens ZULETZT_MAX, neueste zuerst)."""
    try:
        liste = [a for a in (_je_benutzer(db, ZULETZT) or []) if a != aid]
        _setzen(db, ZULETZT, [aid] + liste[:ZULETZT_MAX - 1])
    except Exception:           # noqa: BLE001 – Merken ist Zusatz, die Aktion geht vor
        from . import protokoll
        protokoll.warnung("Zuletzt verwendete Funktion nicht gemerkt")


def zuletzt(db, k=None):
    from .aktionen import AKTION
    return [a for a in (_je_benutzer(db, ZULETZT, k) or []) if a in AKTION]


def schnellzugriffe(db, k=None):
    from .aktionen import AKTION
    eigene = _je_benutzer(db, SCHNELL, k)
    if not isinstance(eigene, list):
        for r in rollen_von(db, k):
            v = (_alle(db, VORGABEN).get(r) or {}).get("schnell")
            if isinstance(v, list):
                eigene = v
                break
    if not isinstance(eigene, list):
        eigene = SCHNELL_VORGABE
    return [a for a in eigene if a in AKTION]


def schnellzugriffe_setzen(db, ids, k=None):
    return _setzen(db, SCHNELL, list(ids) if ids is not None else None, k)


# ------------------------------------------------------------------ Startseite (Dashboard)
def start_sauber(wert):
    """Anordnung der Startseite prüfen: jede Karte höchstens einmal, Kachelzeilen nur oben, Rest ausgeblendet."""
    roh = wert if isinstance(wert, dict) else START_VORGABE
    gesehen, aus = set(), {"oben": [], "links": [], "rechts": []}
    for bereich in ("oben", "links", "rechts"):
        for karte in roh.get(bereich) or ():
            if karte in KARTE_TITEL and karte not in gesehen and ((bereich == "oben") == (karte in OBEN_KARTEN)):
                aus[bereich].append(karte)
                gesehen.add(karte)
    return aus


def startseite(db, k=None):
    eigene = _je_benutzer(db, START, k)
    if not isinstance(eigene, dict):
        for r in rollen_von(db, k):
            v = (_alle(db, VORGABEN).get(r) or {}).get("startseite")
            if isinstance(v, dict):
                eigene = v
                break
    return start_sauber(eigene)


def startseite_setzen(db, wert, k=None):
    return _setzen(db, START, start_sauber(wert) if wert is not None else None, k)


def ausgeblendet(anordnung):
    sichtbar = {c for v in anordnung.values() for c in v}
    return [c for c, _ in KARTEN if c not in sichtbar]


# ------------------------------------------------------------------ Info-Panel
def info_an(db, k=None):
    return _je_benutzer(db, INFO, k) is True


def info_setzen(db, an, k=None):
    return _setzen(db, INFO, bool(an), k)


# ------------------------------------------------------------------ Arbeitsbereiche (Layoutprofile)
def profile(db, k=None):
    """Eigene Arbeitsbereiche {Name: Schnappschuss} des Benutzers."""
    v = _je_benutzer(db, PROFILE, k)
    return dict(v) if isinstance(v, dict) else {}


def schnappschuss(db, fenster_zustand="", navigation=None, k=None):
    """Aktuelle Oberfläche als Arbeitsbereich: Leiste, Startseite, Schnellzugriffe, Info-Panel, Dichte, Navigation
    und die Lage von Leiste und Panel im Fenster (QMainWindow.saveState als Base64)."""
    return {"leiste": leiste(db, k), "startseite": startseite(db, k), "schnell": schnellzugriffe(db, k),
            "info": info_an(db, k), "dichte": db.einstellung("ansicht_dichte") or "normal",
            "navigation": navigation or db.einstellung("navigation_breite") or "automatisch",
            "fenster": fenster_zustand or "", "stand": datetime.datetime.now().isoformat(timespec="seconds")}


def profil_speichern(db, name, daten, k=None):
    name = " ".join(str(name or "").split())[:40]
    if not name:
        return "Bitte einen Namen angeben."
    if name in EINGEBAUT:
        return f"„{name}“ ist ein eingebauter Arbeitsbereich. Bitte einen anderen Namen wählen."
    alle = profile(db, k)
    alle[name] = daten
    _setzen(db, PROFILE, alle, k)
    return ""


def profil_loeschen(db, name, k=None):
    alle = profile(db, k)
    if alle.pop(name, None) is None:
        return False
    _setzen(db, PROFILE, alle, k)
    return True


def profil_daten(db, name, k=None):
    """Schnappschuss eines Arbeitsbereichs (eigener oder eingebauter) oder None."""
    eigene = profile(db, k)
    if name in eigene:
        return eigene[name]
    return copy.deepcopy(EINGEBAUT.get(name)) if name in EINGEBAUT else None


def profil_anwenden(db, daten, k=None):
    """Leiste, Startseite, Schnellzugriffe, Info-Panel und Dichte aus einem Arbeitsbereich übernehmen (das Fenster
    übernimmt danach Navigation und Fensterlage selbst). Ergebnis: die übernommenen Teile."""
    teile = []
    if isinstance(daten.get("leiste"), dict):
        leiste_setzen(db, daten["leiste"], k)
        teile.append("leiste")
    if isinstance(daten.get("startseite"), dict):
        startseite_setzen(db, daten["startseite"], k)
        teile.append("startseite")
    if isinstance(daten.get("schnell"), list):
        schnellzugriffe_setzen(db, daten["schnell"], k)
        teile.append("schnell")
    if isinstance(daten.get("info"), bool):
        info_setzen(db, daten["info"], k)
        teile.append("info")
    if daten.get("dichte") in ("kompakt", "normal", "komfortabel") and not getattr(db, "nur_lesen", False):
        db.einstellung_setzen("ansicht_dichte", daten["dichte"])
        teile.append("dichte")
    return teile


def zuruecksetzen(db, k=None):
    """Eigene Leiste, Startseite und Schnellzugriffe löschen: es gilt wieder die Vorgabe (Rolle oder Standard)."""
    for name in (LEISTE, START, SCHNELL, INFO):
        _setzen(db, name, None, k)


# ------------------------------------------------------------------ Vorgaben je Benutzergruppe (Admin)
def vorgaben(db):
    return _alle(db, VORGABEN)


def vorgabe_setzen(db, rolle, daten):
    """Admin: Standardlayout einer Rolle festlegen (None = löschen) und in den gemeinsamen Ordner schreiben."""
    alle = vorgaben(db)
    if daten is None:
        alle.pop(rolle, None)
    else:
        alle[rolle] = {"leiste": sauber(daten.get("leiste")), "startseite": start_sauber(daten.get("startseite")),
                       "schnell": [a for a in daten.get("schnell") or SCHNELL_VORGABE]}
    db.einstellung_setzen(VORGABEN, alle)
    return vorgaben_schreiben(db)


def vorgaben_schreiben(db):
    """Vorgaben in Admin/oberflaeche_vorgaben.json im gemeinsamen Ordner ablegen. Ergebnis: True, wenn geschrieben."""
    from . import teilen
    w = teilen.dateiweg(db)
    if w is None:
        return False
    try:
        w.datei_schreiben(json.dumps({"art": "oberflaeche_vorgaben", "vorgaben": vorgaben(db)}, ensure_ascii=False,
                                     indent=1).encode("utf-8"), *DATEI)
    except OSError:
        return False
    return True


def vorgaben_lesen(db):
    """Vorgaben aus dem gemeinsamen Ordner übernehmen (beim Start und nach dem Abgleich). Ergebnis: True = neu."""
    from . import teilen
    w = teilen.dateiweg(db)
    if w is None:
        return False
    try:
        roh = w.datei_lesen(*DATEI)
        daten = json.loads(roh.decode("utf-8")) if roh else None
    except (OSError, ValueError):
        return False
    if not isinstance(daten, dict) or daten.get("art") != "oberflaeche_vorgaben":
        return False
    neu = {r: v for r, v in (daten.get("vorgaben") or {}).items() if isinstance(v, dict)}
    if neu == vorgaben(db) or getattr(db, "nur_lesen", False):
        return False
    db.einstellung_setzen(VORGABEN, neu)
    return True
