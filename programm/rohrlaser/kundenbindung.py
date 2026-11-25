"""Kundenbindung Anfrage -> Angebot -> Auftrag (Patrick 25.11.2026, Master-Auftrag Outlook-Import).

Der Kunde einer Anfrage – automatisch eindeutig erkannt oder von Hand gewählt – gilt für alle Schritte: Prüfdialog,
Positionen, Angebot, Mail-Antworten bis zum Auftrag. Er steht zentral in der Anfrage-Akte (anfragen_akten.Akte.kunde);
die von Hand gewählte Zuordnung geht immer vor. Automatisch geändert wird nie etwas: weicht die Mail oder das Formular
ab, gibt es nur einen Hinweis. Ein Kundenwechsel hält Anfrage und Angebote gleich, aber nur nach Rückfrage:

- offene Angebote der Anfrage folgen, wenn der Benutzer es bestätigt (Haken im Fenster, Vorgabe an),
- beauftragte Angebote (Vorgang „Beauftragt“ bzw. mit Auftragsnummer) folgen nie von allein; nur mit eigenem Haken,
- ein Kundenwechsel im Angebot bzw. im Prüfdialog wird in die Anfrage zurückgeschrieben (Verlauf: „im Angebot gewählt“).

Ohne Qt: die Fenster stehen in anfragen_seite bzw. angebot_fenster."""

BEAUFTRAGT = "Beauftragt"


def gebunden(akte):
    """Ist der Kunde der Akte bindend? Ja, sobald er bestätigt, von Hand gewählt oder beim Eingang eindeutig erkannt ist
    (dann steht er in akte.kunde) – auch „ohne Kunde“ (bestätigt) ist bindend."""
    if akte is None:
        return False
    return bool(akte.stand.get("kunde_bestaetigt") or akte.kunde)


def quelle(akte):
    """Woher der Kunde der Akte kommt: 'von Hand', 'bestätigt', 'automatisch', '' (kein Kunde)."""
    if akte is None:
        return ""
    s = akte.stand
    if s.get("kunde") is not None and s.get("kunde_bestaetigt"):
        letzte = next((e for e in reversed(akte.verlauf) if e.get("aktion") == "zuordnung"
                       and e.get("feld") in ("kunde", "bestaetigt", "ohne_kunde")), None)
        return "bestätigt" if letzte and letzte.get("feld") == "bestaetigt" else "von Hand"
    return "automatisch" if akte.kunde else ""


def angebote(db, akte):
    """Angebote der Akte: [dict(id, nummer, kundennr, kunde, vorgang, auftragsnr, beauftragt)] (Nummern aus dem Verlauf
    „Angebot verknüpft“; jedes Verknüpfen schreibt die Nummer dorthin)."""
    nummern = [n for n in (akte.stand.get("angebote") or []) if n]
    if not nummern:
        return []
    marken = ",".join("?" * len(nummern))
    return [_zeile(z) for z in db.con.execute(f"SELECT id, nummer, kundennr, kunde, vorgang, auftragsnr FROM angebote "
                                              f"WHERE nummer IN ({marken}) ORDER BY id", tuple(nummern)).fetchall()]


def _zeile(z):
    vorgang = str(z[4] or "")
    return dict(id=z[0], nummer=str(z[1] or ""), kundennr=str(z[2] or ""), kunde=str(z[3] or ""), vorgang=vorgang,
                auftragsnr=str(z[5] or ""), beauftragt=vorgang == BEAUFTRAGT or bool(z[5]))


def wechsel(db, akte, neu):
    """Was ein Kundenwechsel der Akte auf neu (Kundennummer, '' = ohne Kunde) berührt: dict(offen [Angebote mit anderem
    Kunden, nicht beauftragt], beauftragt [mit anderem Kunden, beauftragt], gleich [schon beim neuen Kunden])."""
    neu = str(neu or "")
    out = dict(offen=[], beauftragt=[], gleich=[])
    for a in angebote(db, akte):
        if a["kundennr"] == neu:
            out["gleich"].append(a)
        else:
            out["beauftragt" if a["beauftragt"] else "offen"].append(a)
    return out


def wechsel_text(w, neu_text):
    """Rückfragetext zum Kundenwechsel (leer, wenn kein Angebot betroffen ist)."""
    zeilen = []
    if w["offen"]:
        zeilen.append("Offene Angebote dieser Anfrage mit anderem Kunden: "
                      + ", ".join(f"{a['nummer']} ({a['kundennr'] or 'ohne Kunde'})" for a in w["offen"]))
    if w["beauftragt"]:
        zeilen.append("Beauftragt (Auftrag) – bleiben beim bisherigen Kunden, umstellen nur mit eigenem Haken: "
                      + ", ".join(f"{a['nummer']} ({a['kundennr'] or 'ohne Kunde'}"
                                  + (f", Auftrag {a['auftragsnr']}" if a["auftragsnr"] else "") + ")"
                                  for a in w["beauftragt"]))
    if zeilen:
        zeilen.insert(0, f"Neuer Kunde der Anfrage: {neu_text}.")
    return "\n".join(zeilen)


def angebote_umstellen(db, liste, kundennr):
    """Angebote (aus wechsel) auf den Kunden umstellen (Name, Zahlungsbedingungen, Ansprechpartner wie im Angebot
    beim Kundenwechsel). Ergebnis: umgestellte Nummern."""
    out = []
    for a in liste or ():
        db.kunde_uebernehmen(a["id"], str(kundennr or "") or None)
        out.append(a["nummer"])
    return out


def akte_folgen(db, angebot_id, kundennr, name="", grund="im Angebot gewählt"):
    """Kundenwechsel im Angebot (bzw. im Prüfdialog) in die verknüpften Anfragen zurückschreiben, damit Anfrage und
    Angebot denselben Kunden haben. Nur Akten mit anderem Kunden; Ergebnis: Nummern der geänderten Akten."""
    from . import anfragen_akten as ak
    if not ak.aktiv(db) or getattr(db, "nur_lesen", False):
        return []
    nummern = ak.akten_zum_angebot(db, angebot_id)
    if not nummern:
        return []
    abl = ak.ablage(db)
    out = []
    for nr in nummern:
        try:
            akte = abl.lesen(nr)
            if akte is None or akte.geloescht or str(akte.kunde or "") == str(kundennr or ""):
                continue
            if kundennr:
                abl.zuordnung_aendern(akte, "kunde", str(kundennr), name, grund=grund)
            else:
                abl.zuordnung_aendern(akte, "ohne_kunde", grund=grund)
            out.append(nr)
        except (OSError, ak.AblageFehler):
            continue
    return out
