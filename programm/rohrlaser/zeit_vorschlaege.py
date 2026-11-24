"""Zeitvorschläge für alle Arbeitsgänge (Plan Angebotskalkulation 16.11.2026, Paket K2, F3a). Ohne Qt.

Quelle „arbeitsgang“ für die Kennwerte aus der Nachkalkulation (kennwerte.py, Fenster Kennwerte): je Arbeitsgang
der Arbeitsvorbereitung (Entgraten, Bohren, Montage, Verpackung, eigene Schritte) ist jedes nachkalkulierte Angebot
mit Rückmeldungen ein Fall Soll/Ist je Teil (nachkalk_rueckmeldung, ist['arbeitsgaenge']). Vorschlag ab
MINDESTENS Fällen, Median ohne Ausreißer; geändert wird nur nach Freigabe mit Begründung, mit Historie und
Zurücknehmen.

Was eine Freigabe ändert (Faktor Ist ÷ Soll):
- Zusatzarbeiten, deren Name oder Kategorie zum Arbeitsgang passt (STICHWORTE): Zeitaufwand je Einheit × Faktor;
  ohne Zeitaufwand bei s/Stück die Zeit je Stück, bei €/Stück der Festpreis × Faktor (eigene Arbeit, die Kalkulation
  setzt sie als Betrag ÷ Stundensatz an). Fremdleistungen und Gewinde/Senken/Flowdrill/Bohren nicht.
- Verpackung: zusätzlich Bündeln/Umreifen je Stück × Faktor.
- Nur Vorschlag: Rohrlaser (Schneiddaten kalibrieren, Laserzeit-Bausteine), Schweißen (Kennwerte Schweißen aus den
  Baugruppen), Bohren und Gewinde (nur € je Stück, Grundregel), Material und Qualität.
"""
from . import kennwerte

QUELLE = "arbeitsgang"
MINDESTENS = 3
STICHWORTE = {
    "entgraten": ("entgrat",),
    "montage": ("montage", "montier"),
    "verpack": ("verpack",),
    "richten": ("richt",),
    "biegen": ("bieg",),
    "strahlen": ("strahl",),
}
NUR_VORSCHLAG = {"laser": "über Schneiddaten kalibrieren", "schweiß": "über die Kennwerte Schweißen",
                 "bohren": "Bohren und Gewinde rechnen nur € je Stück", "material": "keine Zeit in der Kalkulation",
                 "qualität": "Prüfkosten aus den Qualitätsstufen"}
NAMEN = {"entgraten": "Entgraten", "montage": "Montage", "verpack": "Verpackung", "laser": "Rohrlaser",
         "schweiß": "Schweißen", "bohren": "Bohren/Gewinde", "material": "Materialbereitstellung",
         "qualität": "Qualitätsprüfung"}
GESPERRT = ("gewinde", "senk", "flowdrill", "bohr")      # nur € je Stück (Grundregel)


def name(art):
    return NAMEN.get(art) or str(art).capitalize()


def faelle(db):
    """[Fall] je Angebot und Arbeitsgang: schluessel=(Arbeitsgang,), soll/ist [s je Teil]."""
    from . import nachkalkulation as nk
    out = []
    for f in nk.faelle(db)[0]:
        for art, g in (f["ist"].get("arbeitsgaenge") or {}).items():
            teile = g.get("teile") or 0
            if teile > 0 and (g.get("soll_s") or 0) > 0 and (g.get("ist_s") or 0) > 0:
                out.append(dict(schluessel=(name(art),), soll=g["soll_s"] / teile, ist=g["ist_s"] / teile,
                                angebot=f["nummer"], datum=f["datum"], art=art))
    return out


def _art_aus_name(text):
    for k, v in NAMEN.items():
        if v == text:
            return k
    return str(text).lower()


def betroffen(db, art):
    """[(Tabelle, Zeile, Feld)] der Werte, die eine Freigabe für diesen Arbeitsgang ändert."""
    if art in NUR_VORSCHLAG:
        return []
    worte = STICHWORTE.get(art, (art,))
    out = []
    for z in db.zeilen("zusatzarbeiten"):
        text = f"{z.get('name') or ''} {z.get('kategorie') or ''}".lower()
        if not any(w in text for w in worte) or any(w in str(z.get("name") or "").lower() for w in GESPERRT):
            continue
        if z.get("fremd") == "ja" or z.get("aktiv") == "nein":
            continue
        if isinstance(z.get("zeit"), (int, float)) and z["zeit"] > 0:
            out.append(("zusatzarbeiten", z, "zeit"))
        elif z.get("art") in ("s/Stück", "€/Stück") and isinstance(z.get("preis"), (int, float)) and z["preis"] > 0:
            out.append(("zusatzarbeiten", z, "preis"))     # Zeit je Stück bzw. Festpreis eigener Arbeit
    if art == "verpack":
        out += [("verpackung", z, "zeit_bund") for z in db.zeilen("verpackung")
                if isinstance(z.get("zeit_bund"), (int, float)) and z["zeit_bund"] > 0]
    return out


def betroffen_text(db, art):
    if art in NUR_VORSCHLAG:
        return f"nur Vorschlag ({NUR_VORSCHLAG[art]})"
    b = betroffen(db, art)
    if not b:
        return "keine passende eigene Zusatzarbeit"
    was = {"zeit_bund": "Bündeln je Stück", "zeit": "Zeitaufwand", "preis": "Preis bzw. Zeit je Stück"}
    return ", ".join(f"{z.get('name')} ({was[f]})" for _, z, f in b)


def anwenden(db, schluessel, faktor):
    art = _art_aus_name(schluessel[0])
    if art in NUR_VORSCHLAG:
        raise ValueError(f"{schluessel[0]}: nur Vorschlag ({NUR_VORSCHLAG[art]}).")
    b = betroffen(db, art)
    if not b:
        raise ValueError(f"{schluessel[0]}: keine eigene Zusatzarbeit, die dazu passt.")
    aend = []
    for tabelle, z, feld in b:
        neu = round(z[feld] * faktor, 2)
        db.aendern(tabelle, z["id"], feld, neu)
        aend.append([tabelle, z["id"], feld, z[feld], neu])
    return aend


kennwerte.register_quelle(QUELLE, "Zeit je Arbeitsgang (Rückmeldungen der Aufträge)", faelle, anwenden)
kennwerte.MINDEST_JE_QUELLE[QUELLE] = MINDESTENS
