"""Zentrale 3D-Einstellungen (3D-Visualisierungsupdate V7, Patrick 19.11.2026): Profile, Export/Import, Selbsttest.

Ein Profil ist ein Satz der 3D-Einstellungen dieses Arbeitsplatzes (Aussehen: visualisierung.NAMEN, Navigation:
navigation3d.NAMEN). Feste Profile kommen mit dem Programm; eigene Profile speichert jeder Arbeitsplatz für sich (Name
EIGENE, nicht in stammdaten.EINSTELLUNGEN, daher nie abgeglichen). Export/Import als JSON-Datei, damit ein Kollege dieselbe
Ansicht übernehmen kann. Der Selbsttest zeichnet ein Prüfrohr in allen Darstellungen und Materialien (nur Anzeige,
ändert nichts) und meldet, was nicht stimmt.

Ohne Qt bis auf selbsttest() (lädt Qt erst dort)."""
import json
import time

from . import navigation3d, visualisierung

NAMEN = tuple(visualisierung.NAMEN) + tuple(navigation3d.NAMEN)
VORGABEN = {**visualisierung.VORGABEN, **navigation3d.VORGABEN}
EIGENE = "ansicht3d_eigene_profile"        # JSON {Name: {Einstellung: Wert}} – nur dieser Arbeitsplatz
DATEI_ART = "rohrlaser-3d-einstellungen"
DATEI_VERSION = 1
STANDARD = "Standard (Vorgaben)"
GRENZE_MS = 3000          # Selbsttest: ein Prüfbild (420 × 260, Software-Weg) darf so lange dauern, auch auf vollem PC
inv, sw, creo = list(navigation3d.MAUSBELEGUNGEN)[1:4]
# Feste Profile: nur die genannten Werte ändern sich, alles andere bleibt
PROFILE = {
    STANDARD: dict(VORGABEN),
    "Präsentation (Kunde)": {"ansicht3d_material": "Edelstahl", "ansicht3d_licht": "Studio",
                             "ansicht3d_hintergrund": "Studio (Blaugrau)", "ansicht3d_schatten": "ja"},
    "Werkstatt (kräftig)": {"ansicht3d_material": "Rohstahl", "ansicht3d_licht": "Werkstatt",
                            "ansicht3d_hintergrund": "Hellgrau", "ansicht3d_schatten": "ja"},
    "Technisch (wie Zeichnung)": {"ansicht3d_material": "Matt", "ansicht3d_licht": "Technisch (flach)",
                                  "ansicht3d_hintergrund": "Weiß", "ansicht3d_schatten": "nein",
                                  "ansicht3d_kantenfarbe": "Schwarz", "ansicht3d_verdeckt": "ja"},
    "Schwacher PC (schnell)": {"ansicht3d_material": "Matt", "ansicht3d_licht": "Technisch (flach)",
                               "ansicht3d_hintergrund": "Hellgrau", "ansicht3d_schatten": "nein",
                               "nav_traegheit": "nein", "ansicht3d_verdeckt": "nein"},
    "Wie Inventor": {"nav_maus": inv},
    "Wie SolidWorks": {"nav_maus": sw},
    "Wie Creo": {"nav_maus": creo},
}


class ProfilFehler(ValueError):
    pass


def werte(db):
    """Aktuelle 3D-Einstellungen dieses Arbeitsplatzes {Name: Wert}."""
    out = dict(VORGABEN)
    for n in NAMEN:
        try:
            v = db.einstellung(n) if db is not None else None
        except Exception:       # noqa: BLE001 – Lesemodus: Vorgabe
            v = None
        if v not in (None, ""):
            out[n] = v
    return out


def pruefen(roh):
    """Nur bekannte Namen mit gültigen Werten (Auswahlen aus den Listen, Zahlen im Bereich). Ergebnis: (gültig, [Text
    je verworfenem Wert])."""
    gut, weg = {}, []
    auswahl = {"ansicht3d_material": visualisierung.MATERIALIEN, "ansicht3d_licht": visualisierung.LICHTPROFILE,
               "ansicht3d_hintergrund": visualisierung.HINTERGRUENDE, "nav_maus": navigation3d.MAUSBELEGUNGEN,
               "ansicht3d_kantenfarbe": visualisierung.KANTENFARBEN,
               "ansicht3d_kantenstaerke": visualisierung.KANTENSTAERKEN}
    zahlen = {"nav_dreh_tempo": (0.1, 5.0), "nav_zoom_tempo": (0.1, 5.0), "nav_schiebe_tempo": (0.1, 5.0),
              "nav_nachlauf": (0.5, 0.97), **visualisierung.KANTEN_ZAHLEN}
    for n, v in (roh or {}).items():
        if n not in VORGABEN:
            weg.append(f"{n}: unbekannt")
            continue
        if n in auswahl and v not in auswahl[n]:
            weg.append(f"{n}: „{v}“ gibt es nicht")
            continue
        if n in zahlen:
            try:
                v = float(v)
            except (TypeError, ValueError):
                weg.append(f"{n}: keine Zahl")
                continue
            lo, hi = zahlen[n]
            if not lo <= v <= hi:
                weg.append(f"{n}: {v} außerhalb {lo} … {hi}")
                continue
        if VORGABEN[n] in ("ja", "nein") and v not in ("ja", "nein"):
            weg.append(f"{n}: nur ja/nein")
            continue
        gut[n] = v
    return gut, weg


def anwenden(db, neu):
    """Werte übernehmen (nur gültige), speichern und sofort in allen 3D-Ansichten zeigen. Ergebnis: geänderte Namen."""
    gut, _ = pruefen(neu)
    alt = werte(db)
    geaendert = [n for n, v in gut.items() if alt.get(n) != v]
    for n in geaendert:
        db.einstellung_setzen(n, gut[n])
    aussehen = {n: gut[n] for n in visualisierung.NAMEN if n in gut}
    if aussehen:
        try:
            from . import ansicht3d
            ansicht3d.aussehen_setzen({**visualisierung.aktuell(), **aussehen})
        except Exception:       # noqa: BLE001 – ohne Qt (Tests): nur das Modul setzen
            visualisierung.setzen({**visualisierung.aktuell(), **aussehen})
    return geaendert


def eigene(db):
    """Eigene Profile dieses Arbeitsplatzes {Name: Werte}."""
    try:
        roh = db.einstellung(EIGENE)
        d = json.loads(roh) if isinstance(roh, str) else (roh or {})
        return {str(k): v for k, v in d.items() if isinstance(v, dict)}
    except Exception:       # noqa: BLE001 – kaputter Eintrag: keine eigenen Profile
        return {}


def alle(db):
    """Feste und eigene Profile (eigene überschreiben nie feste Namen)."""
    out = dict(PROFILE)
    for k, v in eigene(db).items():
        if k not in PROFILE:
            out[k] = v
    return out


def speichern(db, name):
    """Aktuelle Werte als eigenes Profil name speichern (feste Namen sind geschützt)."""
    name = (name or "").strip()
    if not name or name in PROFILE:
        raise ProfilFehler("Bitte einen eigenen Namen wählen (die festen Profile lassen sich nicht überschreiben).")
    d = eigene(db)
    d[name] = werte(db)
    db.einstellung_setzen(EIGENE, json.dumps(d, ensure_ascii=False))
    return name


def loeschen(db, name):
    d = eigene(db)
    if d.pop(name, None) is None:
        return False
    db.einstellung_setzen(EIGENE, json.dumps(d, ensure_ascii=False))
    return True


def exportieren(db, pfad):
    """3D-Einstellungen und eigene Profile als JSON-Datei. Ergebnis: Anzahl Werte."""
    w = werte(db)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(dict(art=DATEI_ART, version=DATEI_VERSION, werte=w, profile=eigene(db)), f, ensure_ascii=False,
                  indent=2)
    return len(w)


def importieren(db, pfad):
    """JSON-Datei übernehmen: Werte (geprüft) und eigene Profile dazu. Ergebnis: (geänderte Namen, verworfen)."""
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ProfilFehler(f"Datei nicht lesbar: {e}") from e
    if not isinstance(d, dict) or d.get("art") != DATEI_ART:
        raise ProfilFehler("Das ist keine Datei mit 3D-Einstellungen dieses Programms.")
    _, weg = pruefen(d.get("werte"))
    geaendert = anwenden(db, d.get("werte") or {})
    profile = {k: v for k, v in (d.get("profile") or {}).items() if isinstance(v, dict) and k not in PROFILE}
    if profile:
        e = eigene(db)
        e.update({k: pruefen(v)[0] for k, v in profile.items()})
        db.einstellung_setzen(EIGENE, json.dumps(e, ensure_ascii=False))
    return geaendert, weg


def selbsttest(breite=420, hoehe=260):
    """Qualitätsprüfung der 3D-Anzeige auf diesem PC: Prüfrohr in allen Darstellungen, Materialien, Lichtprofilen,
    mit Schnitt und Explosion zeichnen (Software-Weg; nur Anzeige). Ergebnis: [(Prüfung, ok, Text)]."""
    import copy

    from . import ansicht3d, rohr3d, schneidweg as sw
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    qr = dict(form="Quadratrohr", a=40, b=40, wand=3)
    kont = [dict(art=sw.BOHRUNG, anzahl=1, d=12, x=120)]
    netz = rohr3d.netz(sw.v_ergaenzen(dict(a={}, b={}, laenge=400, konturen=kont), qr), qr, 400)
    vorher = copy.deepcopy(netz)
    ergebnis = []
    weg, grund = ansicht3d.renderer_waehlen()          # was die echten Ansichten nutzen
    alt_renderer = ansicht3d._renderer
    ansicht3d.renderer_setzen("Software")              # Prüfbild immer im Software-Weg (lesbar, gleiche Formeln)
    a = ansicht3d.Ansicht3D()
    a.resize(breite, hoehe)
    ansicht3d.renderer_setzen(alt_renderer)
    alt_aussehen = visualisierung.aktuell()

    def bild(name):
        a._bild = None
        t0 = time.perf_counter()
        img = a.grab().toImage()
        ms = (time.perf_counter() - t0) * 1000
        farben = {img.pixel(x, y) for x in range(0, img.width(), 23) for y in range(0, img.height(), 17)}
        return len(farben) > 6, ms, name
    try:
        a.setzen(netz, "Prüfrohr")
        if app is not None:
            app.processEvents()
        for dar in ansicht3d.DARSTELLUNGEN:
            a.darstellung_setzen(dar)
            gut, ms, _ = bild(dar)
            ergebnis.append((f"Darstellung „{dar}“", gut and ms < GRENZE_MS, f"{ms:.0f} ms"))
        a.darstellung_setzen(ansicht3d.MIT_KANTEN)
        for mat in visualisierung.MATERIALIEN:
            visualisierung.setzen({**alt_aussehen, "ansicht3d_material": mat})
            gut, ms, _ = bild(mat)
            ergebnis.append((f"Material „{mat}“", gut, f"{ms:.0f} ms"))
        for li in visualisierung.LICHTPROFILE:
            visualisierung.setzen({**alt_aussehen, "ansicht3d_licht": li})
            gut, ms, _ = bild(li)
            ergebnis.append((f"Licht „{li}“", gut, f"{ms:.0f} ms"))
        visualisierung.setzen(alt_aussehen)
        a.schnittebenen_setzen([dict(achse="Z", anteil=0.5)])
        w = a.wand_schnitt
        ergebnis.append(("Schnitt quer: Wandstärke 3 mm erkannt", bool(w) and abs(w[0] - 3.0) < 0.1,
                         f"{w[0]:.2f} mm" if w else "keine"))
        a.schnittebenen_setzen([])
        ergebnis.append(("Anzeige ändert das Netz nicht", netz == vorher, "unverändert" if netz == vorher else
                         "GEÄNDERT"))
        ergebnis.append(("Zeichenweg der 3D-Ansichten", True, f"{weg} ({grund})" if weg == "OpenGL" else
                         f"Software ({grund}) – zeichnet gleich, nur langsamer"))
    except Exception as e:      # noqa: BLE001 – der Test meldet, er stürzt nie ab
        ergebnis.append(("Selbsttest", False, f"{type(e).__name__}: {e}"))
    finally:
        visualisierung.setzen(alt_aussehen)
        a.deleteLater()
    return ergebnis
