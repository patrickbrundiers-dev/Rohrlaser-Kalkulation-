"""Bestandsprüfung beim Umschalten der zentralen Zukaufartikelverwaltung (Master-Auftrag Patrick 23.11.2026, Punkt 8).

Zukaufartikel gehören schon immer zum Angebot: jede Position speichert in positionen.zukauf je Eintrag den ganzen
Preisstand (Einkauf, Staffeln, Bezugskosten, Aufschlagsregeln, Datum). Rechnung, PDFs, Duplizieren und Kopieren lesen
nur diesen Preisstand, nie den Artikelstamm. Deshalb verschiebt das Umschalten keine Daten: es wird nichts gelöscht,
nichts umgeschrieben und keine Position doppelt angelegt. Diese Prüfung liest nur und meldet, ob jeder Eintrag
seinen Preisstand hat. Einträge ohne Preisstand (gab es nie, Absicherung) rechnen in beiden Fällen nicht und werden
genannt. Ohne Qt."""
from . import zukauf


def pruefen(db):
    """Alle Angebote lesen (nur Positionen mit Zukaufteilen, ohne Artikelstamm): dict(angebote, positionen, eintraege,
    stamm (mit Verweis auf einen Stammartikel), frei, ohne_stand [Angebotsnummer], ek_fehlt)."""
    angebote, positionen, n, stamm, frei, ek_fehlt = set(), 0, 0, 0, 0, 0
    ohne = []
    for _pid, aid, nummer, liste in db.zukauf_positionen():
        eintr = [e for e in liste if e.get("artikel_id") is not None or e.get("stand")]
        if not eintr:
            continue
        angebote.add(aid)
        positionen += 1
        for e in eintr:
            n += 1
            if not e.get("stand"):
                ohne.append(nummer or str(aid))
                continue
            if zukauf.ist_frei(e):
                frei += 1
            else:
                stamm += 1
            if zukauf.ek_einheit(e["stand"]) is None and not e.get("ek_fest"):
                ek_fehlt += 1
    return dict(angebote=len(angebote), positionen=positionen, eintraege=n, stamm=stamm, frei=frei,
                ohne_stand=sorted(set(ohne)), ek_fehlt=ek_fehlt)


def text(b, an):
    """Meldung nach dem Umschalten (an = zentrale Verwaltung jetzt eingeschaltet)."""
    if not b["eintraege"]:
        kern = "Noch keine Angebote mit Zukaufartikeln."
    else:
        kern = (f"Geprüft: {b['eintraege']} Zukaufartikel in {b['positionen']} Positionen von {b['angebote']} "
                f"Angeboten, alle mit eigenem Preisstand im Angebot ({b['stamm']} aus dem Artikelstamm übernommen, "
                f"{b['frei']} nur im Angebot) – nichts geändert, Kalkulation und PDFs bleiben gleich.")
        if b["ohne_stand"]:
            kern += f" Ohne Preisstand (bitte prüfen): Angebot {', '.join(b['ohne_stand'][:10])}."
    if an:
        return ("Zentrale Zukaufartikelverwaltung eingeschaltet: Artikel lassen sich wieder zentral speichern und im "
                "Angebot aus dem Stamm wählen. " + kern)
    return ("Zentrale Zukaufartikelverwaltung ausgeschaltet: neue Zukaufartikel werden nur im Angebot gespeichert, "
            "der Artikelstamm bleibt unverändert erhalten. " + kern)
