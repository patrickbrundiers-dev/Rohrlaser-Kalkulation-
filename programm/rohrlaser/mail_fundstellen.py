"""Anfrage-Mail auslesen mit Fundstelle und Sicherheit (KI-001, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale; Regel „KI darf keine technischen Tatsachen erfinden. Alle automatisch ermittelten Werte
müssen mit ihrer Herkunft und Sicherheit gekennzeichnet werden“).

Nutzt die vorhandenen Leser (mail.termin, mail.werkstoff, mail.staffel_mengen, mail.zusatz_erwaehnt,
formular.anfragenummer, formular.kunde) und ergänzt je Wert die Fundstelle (die zitierte Zeile des Texts) und die
Sicherheit:
  sicher    eindeutig gelesen (Anfrage-Nr. mit Beschriftung, Datum/Kalenderwoche, genau ein Werkstoff mit Namen)
  prüfen    gelesen, aber auslegbar (Dauer in Wochen/Tagen, Kunde über den Namen im Text, Staffel, Zusatzarbeit,
            Werkstoff über Kurzname wie V2A)
  unsicher  mehrere Möglichkeiten (Werkstoff mehrdeutig: das Programm entscheidet nicht)
Ein Wert ohne Fundstelle erscheint nie. Übernommen wird wie bisher nur über den Prüfdialog. Ohne Qt, ohne Netz, ohne
Sprachmodell: alles bleibt auf dem Rechner."""
import re

SICHER, PRUEFEN, UNSICHER = "sicher", "prüfen", "unsicher"
FELDER = ("anfrage_nr", "kunde", "termin", "werkstoff", "staffel", "zusatz")
TITEL = {"anfrage_nr": "Anfrage-Nr.", "kunde": "Kunde", "termin": "Wunschtermin", "werkstoff": "Werkstoff",
         "staffel": "Staffelmengen", "zusatz": "Zusatzarbeit"}
ZITAT_MAX = 120


def zeile_mit(text, wort):
    """Die erste Zeile des Texts, die das Wort enthält (ohne Groß/klein), gekürzt auf ZITAT_MAX; sonst ''."""
    if not wort:
        return ""
    w = str(wort).lower()
    for z in (text or "").splitlines():
        if w in z.lower():
            z = " ".join(z.split())
            if len(z) > ZITAT_MAX:
                i = max(0, z.lower().find(w) - 40)
                z = ("…" if i else "") + z[i:i + ZITAT_MAX] + "…"
            return z
    return ""


def _w(feld, wert, fundstelle, sicherheit, quelle=""):
    return dict(feld=feld, titel=TITEL[feld], wert=wert, fundstelle=fundstelle, sicherheit=sicherheit, quelle=quelle)


def auslesen(text, werkstoffe=(), katalog=(), kunden=(), eigene=(), quelle="", heute=None):
    """Werte eines Texts mit Fundstelle und Sicherheit: [dict(feld, titel, wert, fundstelle, sicherheit, quelle)]."""
    from . import formular, mail
    out = []
    nr = formular.anfragenummer(text)
    if nr:
        out.append(_w("anfrage_nr", nr, zeile_mit(text, nr), SICHER, quelle))
    kd = formular.kunde(text, kunden, eigene) if kunden else None
    if kd:
        name = next((k.get("name") for k in kunden if str(k.get("kundennr")) == str(kd)), "")
        out.append(_w("kunde", kd, zeile_mit(text, name), PRUEFEN, quelle))
    art, wert, satz = mail.termin(text, heute)
    if art:
        out.append(_w("termin", f"{art} {wert}", " ".join(satz.split())[:ZITAT_MAX],
                      SICHER if art in ("Lieferdatum", "Kalenderwoche") else PRUEFEN, quelle))
    if werkstoffe:
        wid, wort, kand = mail.werkstoff(text, werkstoffe)
        if wid:
            zeile = next((z for z in werkstoffe if z.get("werkstoff_id") == wid), {})
            genau = mail._norm(wort) in {mail._norm(zeile.get(n)) for n in ("werkstoff_id", "werkstoff",
                                                                             "werkstoff_nr")} - {""}
            out.append(_w("werkstoff", wid, zeile_mit(text, wort), SICHER if genau else PRUEFEN, quelle))
        elif wort:
            out.append(_w("werkstoff", f"{wort} (mehrdeutig: {', '.join(kand or ()) or 'kein Werkstoff'})",
                          zeile_mit(text, wort.split(",")[0].strip()), UNSICHER, quelle))
    staffel = mail.staffel_mengen(text)
    if staffel:
        zitat = next((z for z in (text or "").splitlines()
                      if all(re.search(rf"\b{n}\b", z) for n in staffel[:2])), "")
        out.append(_w("staffel", " / ".join(map(str, staffel)), " ".join(zitat.split())[:ZITAT_MAX], PRUEFEN, quelle))
    for name, wort in mail.zusatz_erwaehnt(text, katalog):
        out.append(_w("zusatz", name, zeile_mit(text, wort), PRUEFEN, quelle))
    return [x for x in out if x["fundstelle"]]          # nie ein Wert ohne Fundstelle


def zusammen(quellen, **kw):
    """Je Feld der erste Wert (Quellen in Reihenfolge, neueste zuerst; Zusatzarbeiten je Name einmal)."""
    out, gesehen = [], set()
    for name, text in quellen:
        for x in auslesen(text, quelle=name, **kw):
            schl = (x["feld"], x["wert"]) if x["feld"] == "zusatz" else x["feld"]
            if schl not in gesehen:
                gesehen.add(schl)
                out.append(x)
    return out


def hinweis_text(werte):
    """Eine Zeile für den Prüfdialog."""
    if not werte:
        return ""
    return "Gelesen mit Fundstelle: " + "; ".join(
        f"{x['titel']} {x['wert']} („{x['fundstelle']}“, {x['sicherheit']})" for x in werte)


def _passt(feld, gelesen, erwartet):
    if feld == "werkstoff" and erwartet == "mehrdeutig":
        return "mehrdeutig" in str(gelesen)
    return str(gelesen) == str(erwartet)


def vergleich(werte, erwartet):
    """Trefferquote einer Mail: dict(erwartet, richtig, falsch, fehlt, zu_viel). erwartet = {Feld: Wert} bzw.
    zusatz = [Namen]; ein gelesener Wert, der nicht erwartet war, zählt als zu_viel."""
    richtig = falsch = fehlt = zu_viel = 0
    n = 0
    for feld in FELDER:
        soll = erwartet.get(feld)
        ist = [x["wert"] for x in werte if x["feld"] == feld]
        if feld == "zusatz":
            soll = set(soll or ())
            n += len(soll)
            richtig += len(soll & set(ist))
            fehlt += len(soll - set(ist))
            zu_viel += len(set(ist) - soll)
            continue
        if soll is None:
            zu_viel += bool(ist)
            continue
        n += 1
        if not ist:
            fehlt += 1
        elif _passt(feld, ist[0], soll):
            richtig += 1
        else:
            falsch += 1
    return dict(erwartet=n, richtig=richtig, falsch=falsch, fehlt=fehlt, zu_viel=zu_viel)
