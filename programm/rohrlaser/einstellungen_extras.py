"""Einstellungsverwaltung (Großes UI- und Funktionsupdate, Patrick 19.11.2026, Punkt 3): Favoriten, Standardwerte,
Zurücksetzen je Wert und je Seite, Änderungsverlauf, Plausibilitätsprüfung, Export/Import und das persönliche Profil.
Ohne Qt; die Oberfläche steht in fenster.EinstellungenSeite und einstellungen_extras_dialog.py.

Gemerkt wird je Arbeitsplatz in der eigenen Datendatei (Namen außerhalb von stammdaten.EINSTELLUNGEN gehen nie über
den gemeinsamen Ordner): Favoriten und Verlauf sind persönlich, so wie Fensterlagen und 3D-Darstellung.

Schutz wichtiger Werte: Zurücksetzen und Import lassen Passwort, Nummernkreise, Kürzel und Ordner aus
(einstellungen_sicherung.NIE_GRUPPEN/NIE_NAMEN), überspringen vom Admin gesperrte Einstellungen und legen vorher eine
geschützte Datensicherung an (vor_einstellungen)."""
import datetime
import json
from pathlib import Path

FAVORITEN = "einstellungen_favoriten"       # [Name] in Klickfolge
VERLAUF = "einstellungen_verlauf"           # [dict(zeit, wer, name, titel, alt, neu)], neueste zuletzt
VERLAUF_MAX = 500
PROFIL_ART = "rohrlaser-profil"
# persönliche Werte (Profil): Darstellung, Fenster, Editor-Layout, Favoriten – nie Ordner, Kürzel oder Nummern
PROFIL_NAMEN = ("ansicht_thema", "ansicht_schrift", "ansicht_dichte", "ansicht_3d", "ansicht_hilfe", "eingabe_richtung",
                "stangenbild_popup", "angebote_zeitraum", FAVORITEN)
PROFIL_VORSILBEN = ("ansicht_", "editor_", "fenster_", "menueband", "leiste_", "navigation", "nav_")


# ------------------------------------------------------------------ Standardwerte
def einstellung(name):
    from .stammdaten import EINSTELLUNG
    return EINSTELLUNG.get(name)


def wert_text(e, wert):
    """Wert einer Einstellung lesbar (für Standard, Verlauf und Tooltip)."""
    from .stammdaten import zahl_als_text
    if e is not None and e.art == "passwort":
        return "(gesetzt)" if wert else "(leer)"
    if e is not None and e.art == "bild":
        return "(Bild)" if wert else "(kein Bild)"
    if wert is None or wert == "":
        return "leer"
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if e is not None and e.art == "anteil" and isinstance(wert, (int, float)):
        return f"{zahl_als_text(wert * 100, None, tausender=False)} %"
    if isinstance(wert, (int, float)):
        return zahl_als_text(wert, None, tausender=False)
    text = str(wert) if not isinstance(wert, (list, dict)) else json.dumps(wert, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + " …"


def gleich(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return (a in (None, "") and b in (None, "")) or a == b


def ist_standard(db, name):
    e = einstellung(name)
    return e is None or gleich(db.einstellung(name), e.vorgabe)


def beschreibung(e):
    """Tooltip einer Einstellung: voller Titel, Standardwert, erlaubter Bereich."""
    teile = [e.titel, f"Standard: {wert_text(e, e.vorgabe)}"]
    if e.art in ("zahl", "ganz", "anteil", "zahl_leer") and e.von is not None and e.bis is not None:
        f = 100 if e.art == "anteil" else 1
        einheit = " %" if e.art == "anteil" else ""
        teile.append(f"Erlaubt: {wert_text(None, e.von * f)} bis {wert_text(None, e.bis * f)}{einheit}")
    return "\n".join(teile)


# ------------------------------------------------------------------ Favoriten
def favoriten(db):
    from .stammdaten import EINSTELLUNG
    v = db.einstellung(FAVORITEN)
    return [n for n in v if n in EINSTELLUNG] if isinstance(v, list) else []


def favorit(db, name):
    return name in favoriten(db)


def favorit_setzen(db, name, an=None):
    """Favorit an/aus (an=None: umschalten). Ergebnis: ist jetzt Favorit."""
    liste = favoriten(db)
    an = name not in liste if an is None else bool(an)
    if an and name not in liste:
        liste.append(name)
    elif not an and name in liste:
        liste.remove(name)
    db.einstellung_setzen(FAVORITEN, liste)
    return an


# ------------------------------------------------------------------ Änderungsverlauf
def _wer(db):
    try:
        return db.einstellung("benutzer_kuerzel") or ""
    except Exception:           # Lesemodus u. ä.: Verlauf ohne Kürzel
        return ""


def verlauf_eintragen(db, name, alt, neu, zeit=None):
    """Eine Änderung merken (je Arbeitsplatz, die letzten VERLAUF_MAX)."""
    e = einstellung(name)
    if e is None or name in (FAVORITEN, VERLAUF) or gleich(alt, neu):
        return
    liste = verlauf(db)
    liste.append(dict(zeit=zeit or datetime.datetime.now().isoformat(timespec="seconds"), wer=_wer(db), name=name,
                      titel=e.titel, alt=wert_text(e, alt), neu=wert_text(e, neu)))
    db.einstellung_setzen(VERLAUF, liste[-VERLAUF_MAX:])


def verlauf(db, name=None):
    v = db.einstellung(VERLAUF)
    liste = [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    return [x for x in liste if name is None or x.get("name") == name]


# ------------------------------------------------------------------ Zurücksetzen
def erlaubte(namen=None, gesperrt=()):
    """Namen, die Zurücksetzen/Import ändern dürfen: ohne Passwort, Nummern, Kürzel, Ordner und Gesperrtes."""
    from .einstellungen_sicherung import einstellungen_namen
    frei = [n for n in einstellungen_namen() if n not in set(gesperrt)]
    return frei if namen is None else [n for n in frei if n in set(namen)]


def zuruecksetzen(db, namen, gesperrt=(), sichern=True):
    """Einstellungen namen auf ihren Standard (nur erlaubte). Ergebnis: (geänderte Namen, Pfad der Sicherung)."""
    ziel = [n for n in erlaubte(namen, gesperrt) if not ist_standard(db, n)]
    if not ziel:
        return [], None
    pfad = db.sicherung(zusatz="vor_einstellungen") if sichern else None
    for n in ziel:
        alt = db.einstellung(n)
        db.einstellung_setzen(n, einstellung(n).vorgabe)
        verlauf_eintragen(db, n, alt, einstellung(n).vorgabe)
    return ziel, pfad


# ------------------------------------------------------------------ Plausibilität
HINWEIS, WARNUNG, FEHLER = "HINWEIS", "WARNUNG", "FEHLER"


def _z(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def pruefen(werte):
    """Plausibilitätsprüfung der Einstellungen. werte = {Name: Wert} (z. B. db.einstellungen()). Ergebnis:
    [(Stufe, Text, [Namen])]. Bereichsgrenzen (von/bis) sind FEHLER, auffällige Kombinationen WARNUNG/HINWEIS."""
    from .stammdaten import EINSTELLUNGEN
    out = []
    for e in EINSTELLUNGEN:
        w = _z(werte.get(e.name))
        if w is None or e.art not in ("zahl", "ganz", "anteil", "zahl_leer"):
            continue
        if (e.von is not None and w < e.von - 1e-9) or (e.bis is not None and w > e.bis + 1e-9):
            out.append((FEHLER, f"{e.titel}: {wert_text(e, w)} liegt außerhalb von {wert_text(e, e.von)} bis "
                                f"{wert_text(e, e.bis)}", [e.name]))
    g = _z(werte.get("gewinn"))
    if g is not None and g > 1:
        out.append((WARNUNG, f"Gewinn {wert_text(einstellung('gewinn'), g)} – über 100 %, bitte prüfen", ["gewinn"]))
    if g is not None and g == 0:
        out.append((HINWEIS, "Gewinn 0 %: neue Angebote rechnen ohne Gewinn", ["gewinn"]))
    for n in ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"):
        z = _z(werte.get(n))
        if z is not None and z > 0.5:
            out.append((WARNUNG, f"{einstellung(n).titel} {wert_text(einstellung(n), z)} – ungewöhnlich hoch", [n]))
    for n in ("aufschlag_blech", "aufschlag_zukauf"):
        z = _z(werte.get(n))
        if z is not None and z > 1:
            out.append((WARNUNG, f"{einstellung(n).titel} {wert_text(einstellung(n), z)} – über 100 %", [n]))
    # gestaffelter Gewinn: Grenzen müssen steigen
    grenzen = [(i, _z(werte.get(f"gewinn_bis_{i}"))) for i in range(1, 5)]
    belegt = [(i, b) for i, b in grenzen if b]
    for (i, a), (j, b) in zip(belegt, belegt[1:]):
        if b <= a:
            out.append((FEHLER, f"Gewinn gestaffelt: Grenze {j} ({wert_text(None, b)} €) nicht über Grenze {i} "
                                f"({wert_text(None, a)} €)", [f"gewinn_bis_{i}", f"gewinn_bis_{j}"]))
    r = _z(werte.get("ruesten_abmessung"))
    if r is not None and r > 240:
        out.append((WARNUNG, f"Rüstzeit je Abmessung {wert_text(None, r)} min – über 4 Stunden", ["ruesten_abmessung"]))
    return out


def pruefen_fuer(werte, namen):
    """Nur die Befunde, die eine der Einstellungen namen betreffen (Banner einer Seite)."""
    namen = set(namen)
    return [b for b in pruefen(werte) if namen & set(b[2])]


# ------------------------------------------------------------------ Export und Import
def exportieren(db, ziel, namen=None):
    """Einstellungen (ohne Passwort, Nummern, Kürzel, Ordner) als JSON-Datei; namen = nur diese. Ergebnis: Anzahl."""
    from . import lizenz as L
    werte = {n: db.einstellung(n) for n in erlaubte(namen)}
    L._schreiben(ziel, json.dumps(dict(art="rohrlaser-einstellungen", format=1,
                                       zeit=datetime.datetime.now().isoformat(timespec="seconds"), werte=werte),
                                  indent=1, ensure_ascii=False))
    return len(werte)


class ImportFehler(ValueError):
    pass


def _lesen(quelle, art):
    try:
        d = json.loads(Path(quelle).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ImportFehler(f"Die Datei lässt sich nicht lesen: {e}") from None
    if not isinstance(d, dict) or d.get("art") != art or not isinstance(d.get("werte"), dict):
        raise ImportFehler("Das ist keine Datei mit Einstellungen dieses Programms." if art != PROFIL_ART
                           else "Das ist keine Profil-Datei dieses Programms.")
    return d["werte"]


def import_vorschau(db, quelle, gesperrt=()):
    """Was ein Import ändern würde: dict(aendern=[(Name, alt, neu)], gesperrt=[Name], unbekannt=[Name],
    befunde=Plausibilität danach)."""
    werte = _lesen(quelle, "rohrlaser-einstellungen")
    frei = set(erlaubte(None, gesperrt))
    alle = set(erlaubte(None))
    aendern = [(n, db.einstellung(n), v) for n, v in werte.items() if n in frei and not gleich(db.einstellung(n), v)]
    nachher = dict(db.einstellungen(), **{n: v for n, _, v in aendern})
    return dict(aendern=aendern, gesperrt=sorted(n for n in werte if n in alle and n not in frei),
                unbekannt=sorted(n for n in werte if n not in alle), befunde=pruefen(nachher))


def importieren(db, quelle, gesperrt=(), sichern=True):
    """Einstellungen aus einer Datei von exportieren (bzw. Hauptadmin → Einstellungen sichern) übernehmen: nur
    erlaubte und nicht gesperrte Namen, Bereichsfehler werden übersprungen. Vorher eine geschützte Sicherung.
    Ergebnis: dict(geaendert=[Namen], uebersprungen=[Namen], sicherung=Pfad)."""
    v = import_vorschau(db, quelle, gesperrt)
    falsch = {n for stufe, _, namen in pruefen({n: w for n, _, w in v["aendern"]}) if stufe == FEHLER
              for n in namen if any(n == x for x, _, _ in v["aendern"])}
    ziel = [(n, a, w) for n, a, w in v["aendern"] if n not in falsch]
    pfad = db.sicherung(zusatz="vor_einstellungen") if sichern and ziel else None
    for n, alt, w in ziel:
        db.einstellung_setzen(n, w)
        verlauf_eintragen(db, n, alt, w)
    return dict(geaendert=[n for n, _, _ in ziel], uebersprungen=sorted(falsch) + v["gesperrt"], sicherung=pfad)


# ------------------------------------------------------------------ persönliches Profil
def profil_namen(db):
    """Persönliche Werte dieses Arbeitsplatzes: PROFIL_NAMEN und gespeicherte Werte mit PROFIL_VORSILBEN."""
    try:
        gespeichert = [r[0] for r in db.con.execute("SELECT name FROM einstellungen").fetchall()]
    except Exception:
        gespeichert = []
    namen = list(PROFIL_NAMEN)
    namen += sorted(n for n in gespeichert if n.startswith(PROFIL_VORSILBEN) and n not in namen
                    and "ordner" not in n)
    return namen


def profil_exportieren(db, ziel):
    """Persönliches Profil (Darstellung, Editor-Layout, Fenster, Favoriten) als Datei, z. B. für einen anderen
    Rechner. Ergebnis: Anzahl Werte."""
    from . import lizenz as L
    werte = {n: db.einstellung(n) for n in profil_namen(db)}
    werte = {n: v for n, v in werte.items() if v is not None}
    L._schreiben(ziel, json.dumps(dict(art=PROFIL_ART, format=1, wer=_wer(db),
                                       zeit=datetime.datetime.now().isoformat(timespec="seconds"), werte=werte),
                                  indent=1, ensure_ascii=False))
    return len(werte)


def profil_importieren(db, quelle):
    """Persönliches Profil übernehmen: nur persönliche Werte (Vorsilben/PROFIL_NAMEN), nie Ordner, Kürzel,
    Nummern oder gemeinsame Einstellungen. Ergebnis: Anzahl übernommen."""
    werte = _lesen(quelle, PROFIL_ART)
    n = 0
    for name, v in werte.items():
        if (name in PROFIL_NAMEN or name.startswith(PROFIL_VORSILBEN)) and "ordner" not in name:
            if not gleich(db.einstellung(name), v):
                db.einstellung_setzen(name, v)
                n += 1
    return n
