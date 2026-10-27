"""Prüfstatus je STEP-Merkmal (Wettbewerbsvergleich P0-3): erkannte und nicht eindeutig erkannte Geometrie sichtbar
trennen, Rohdaten und Annahmen der Messung festhalten, manuelle Korrekturen protokollieren.

Je Teil eine Liste Merkmale: Profilform, Querschnitt, Wandstärke, Länge, Ende A, Ende B, Innenkonturen,
Gewinde-Vorschlag, Anbauteile und Hinweise der Messung, je mit Status
  sicher        – die Messung meldet das Merkmal als sicher erkannt
  prüfen        – wahrscheinlich bzw. unsicher erkannt, Annahme (z. B. Gewinde aus dem Kernloch) oder Hinweis
  nicht erkannt – fehlt oder ist kein Standardprofil (Sonderprofil wird nie still als Standardprofil gerechnet)
Grundlage ist die Erkennungssicherheit, die STEP-Import.exe je Merkmal schreibt (Spalte 'sicherheit':
sicher / wahrscheinlich / unsicher / nicht ausgewertet); 'wahrscheinlich' gilt hier als 'prüfen'.

Gespeichert je Position als JSON (positionen.step_merkmale): {merkmale, roh (Messwerte), datei, am, korrekturen
[{am, feld, alt, neu}], geprueft (am, wer)}. Ändert jemand nach dem Import ein gemessenes Feld der Position, hängt
die Datenbank (position_aendern) eine Korrektur an; die Korrekturen bleiben mit der Position gespeichert.
"""
import datetime
import json

SICHER, PRUEFEN, NICHT = "sicher", "prüfen", "nicht erkannt"
RANG = {SICHER: 0, PRUEFEN: 1, NICHT: 2}
# Felder der Position, die aus der Messung kommen (Änderung von Hand = Korrektur)
GEMESSEN = ("profil_id", "laenge", "schneidweg", "einstiche", "a_gerade", "a_schnitt", "b_gerade", "b_schnitt",
            "innen", "gravur", "bohrungen", "gewinde", "a_ende", "b_ende")
ROH = ("profilform", "abm_a", "abm_b", "wandstaerke", "flaeche", "laenge", "schneidweg", "ende_a", "ende_b",
       "ende_a_gerade", "ende_b_gerade", "innen", "innen_konturen", "gravur", "bohrungen", "sicherheit",
       "pruefstatus", "profil_id_vorschlag", "hinweise", "huelle")


def _sicherheit(m):
    out = {}
    for teil in (m.get("sicherheit") or "").split(";"):
        k, _, v = teil.partition("=")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def _z(m, name):
    try:
        return float(m.get(name) or 0)
    except (TypeError, ValueError):
        return 0.0


def _status(wert):
    return {"sicher": SICHER, "wahrscheinlich": PRUEFEN, "unsicher": PRUEFEN}.get(wert, PRUEFEN)


def _ende(m, seite):
    """(Wert, Status, Grund) eines Endes aus der Konturliste der Messung."""
    gerade = m.get(f"ende_{seite.lower()}_gerade") == "1"
    if gerade:
        return "gerade", SICHER, ""
    try:
        liste = json.loads(m.get("konturen_liste") or "[]")
    except (TypeError, ValueError):
        liste = []
    d = next((x for x in liste if isinstance(x, dict) and x.get("art") == f"Ende {seite}"), None) if isinstance(
        liste, list) else None
    form = (d or {}).get("form") or ""
    if form in ("Gehrung", "Schrägschnitt zweiachsig") and (d or {}).get("gehrung"):
        return f"{form} {float(d['gehrung']):g}°", SICHER if d.get("richtung") is not None else PRUEFEN, \
            "" if d.get("richtung") is not None else "Richtung der Gehrung nicht gemessen"
    if form:
        return form, PRUEFEN, "nicht gerades Ende mit Ausklinkung oder Kontur: im Schneidweg-Rechner prüfen"
    return "nicht gerade", PRUEFEN, "Form des Endes nicht erkannt"


def merkmale(m, gewinde_vorschlag=None):
    """Merkmale eines gemessenen Teils (Messwerte von STEP-Import.exe): [dict(merkmal, wert, status, grund)]."""
    if m.get("fehler"):
        return [dict(merkmal="Datei", wert="", status=NICHT, grund=str(m["fehler"]))]
    si = _sicherheit(m)
    form = m.get("profilform") or ""
    out = []

    def neu(merkmal, wert, status, grund=""):
        out.append(dict(merkmal=merkmal, wert=wert, status=status, grund=grund))
    if not form:
        neu("Profilform", "", NICHT, "kein Profilquerschnitt gefunden")
    elif "Sonderprofil" in form:
        neu("Profilform", form, NICHT, "kein Standardprofil: Profil von Hand wählen oder anlegen")
    else:
        neu("Profilform", form, _status(si.get("profil")),
            "" if si.get("profil") == "sicher" else f"Erkennung {si.get('profil') or 'ohne Angabe'}")
    a, b = _z(m, "abm_a"), _z(m, "abm_b")
    if a <= 0:
        neu("Querschnitt", "", NICHT, "Abmessung fehlt")
    else:
        neu("Querschnitt", f"{a:g} × {b:g} mm" if b else f"{a:g} mm", _status(si.get("profil")),
            "" if si.get("profil") == "sicher" else "Abmessung aus unsicherer Profilerkennung")
    w = _z(m, "wandstaerke")
    if w <= 0 and form not in ("Flachstahl",):
        neu("Wandstärke", "", NICHT, "Wandstärke nicht gemessen")
    else:
        neu("Wandstärke", f"{w:g} mm", _status(si.get("wandstaerke")),
            "" if si.get("wandstaerke") == "sicher" else f"Erkennung {si.get('wandstaerke') or 'ohne Angabe'}")
    lg = _z(m, "laenge")
    if lg <= 0:
        neu("Länge", "", NICHT, "Länge nicht gemessen")
    else:
        s_l = si.get("laenge") or si.get("achse")
        neu("Länge", f"{lg:g} mm", _status(s_l), "" if s_l == "sicher" else f"Achse/Länge {s_l or 'ohne Angabe'}")
    for seite in ("A", "B"):
        wert, status, grund = _ende(m, seite)
        neu(f"Ende {seite}", wert, status, grund)
    n_innen = int(_z(m, "innen_konturen"))
    s_k = si.get("konturen")
    if s_k == "nicht ausgewertet":
        neu("Innenkonturen", "", PRUEFEN, "Konturen nicht ausgewertet: im Schneidweg-Rechner ergänzen")
    else:
        neu("Innenkonturen", f"{n_innen} Stück, {_z(m, 'innen'):g} mm", _status(s_k) if n_innen else SICHER,
            "" if not n_innen or s_k == "sicher" else "Ausschnitt oder komplexe Kontur: Form prüfen")
    if gewinde_vorschlag:
        neu("Gewinde-Vorschlag", gewinde_vorschlag, PRUEFEN,
            "Annahme aus dem Kernloch-Durchmesser; gerechnet wird erst nach Eintrag in „Gewinde geprüft“")
    if "anbauteile" in si:
        neu("Anbauteile", m.get("anbauteile") and "vorhanden" or "", _status(si["anbauteile"]),
            "" if si["anbauteile"] == "sicher" else "Anbauteile im Angebot bestätigen")
    if m.get("hinweise"):
        neu("Hinweise der Messung", str(m["hinweise"])[:200], PRUEFEN, "Hinweis der Messung lesen")
    return out


def gesamt(liste):
    """Schlechtester Status der Liste (sicher, wenn leer)."""
    return max((x["status"] for x in liste or ()), key=RANG.get, default=SICHER)


def zaehlen(liste):
    out = {SICHER: 0, PRUEFEN: 0, NICHT: 0}
    for x in liste or ():
        out[x["status"]] += 1
    return out


def kurztext(liste):
    """'3 prüfen, 1 nicht erkannt' bzw. 'alle sicher'."""
    n = zaehlen(liste)
    teile = [f"{n[s]} {s}" for s in (NICHT, PRUEFEN) if n[s]]
    return ", ".join(teile) if teile else "alle sicher"


def html(liste):
    """Zeile für den Prüfdialog: offene Merkmale farbig."""
    farbe = {PRUEFEN: "#7A5A00", NICHT: "#B42318"}
    offen = [x for x in liste if x["status"] != SICHER]
    if not offen:
        return "<span style='color:#1E6B34'>Merkmale: alle sicher erkannt</span>"
    return "Merkmale: " + "; ".join(f"<b style='color:{farbe[x['status']]}'>{x['merkmal']} {x['status']}</b>"
                                    + (f" ({x['grund']})" if x["grund"] else "") for x in offen)


def speicherwert(m, gewinde_vorschlag=None, jetzt=None):
    """JSON für positionen.step_merkmale."""
    jetzt = jetzt or datetime.datetime.now().replace(microsecond=0)
    return json.dumps(dict(merkmale=merkmale(m, gewinde_vorschlag), datei=m.get("datei") or "",
                           koerper=m.get("koerper") or "", am=str(jetzt),
                           roh={k: m.get(k) for k in ROH if m.get(k) not in (None, "")}, korrekturen=[]),
                      ensure_ascii=False)


def lesen(text):
    if not text:
        return None
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def korrektur(text, feld, alt, neu, jetzt=None):
    """Korrektur an den gespeicherten Wert anhängen; Ergebnis: neuer Text (unverändert ohne Merkmale)."""
    d = lesen(text)
    if d is None or feld not in GEMESSEN or alt == neu:
        return text
    d.setdefault("korrekturen", []).append(dict(am=str(jetzt or datetime.datetime.now().replace(microsecond=0)),
                                                feld=feld, alt=alt, neu=neu))
    return json.dumps(d, ensure_ascii=False)


def bestaetigen(text, wer="", jetzt=None):
    """Alle Merkmale von Hand geprüft (Angebots-Check zählt sie dann nicht mehr als offen)."""
    d = lesen(text)
    if d is None:
        return text
    d["geprueft"] = dict(am=str(jetzt or datetime.datetime.now().replace(microsecond=0)), wer=wer)
    return json.dumps(d, ensure_ascii=False)


def offen(p):
    """Offene Merkmale einer Position (nicht bestätigt, Status prüfen oder nicht erkannt)."""
    d = lesen(p.get("step_merkmale"))
    if not d or d.get("geprueft"):
        return []
    return [x for x in d.get("merkmale") or () if x.get("status") != SICHER]
