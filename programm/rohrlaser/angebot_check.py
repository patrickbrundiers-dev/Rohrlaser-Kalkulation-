"""Angebots-Check vor dem Versand (Plan „Intelligenteres Programm“ A2, mit W7 aus „Arbeitsabläufe“): alle offenen
Punkte eines Angebots in einer Liste, laufend in der Übersicht und als eine Sammelrückfrage vor dem Angebots-PDF und
vor dem Vorgang „Verschickt“.

Ein Punkt ist ein Paar (Art, Text) wie bisher in rechnen.freigabe_punkte, dazu ziel (wohin „Hinspringen“ führt) und
details (z. B. betroffene Positionen). Arten: FEHLER blockiert (übergehen nur mit Begründung), WARNUNG fragt einmal,
HINWEIS informiert nur.

Ziele: pos:<Zeile>, kopf:<Feld>, kunde, fracht, optimieren, staffeln, preise, kalkulation.
"""
import datetime

FEHLER, WARNUNG, HINWEIS = "FEHLER", "WARNUNG", "HINWEIS"
ARTEN = (FEHLER, WARNUNG, HINWEIS)
POSITIONEN_ZEIGEN = 6           # so viele Positionsnummern nennt ein Punkt, danach „…“


class Punkt(tuple):
    """(Art, Text) mit ziel und details; vergleicht und entpackt wie das Paar."""

    def __new__(cls, art, text, ziel=None, details=""):
        p = super().__new__(cls, (art, text))
        p.ziel, p.details = ziel, details
        return p

    @property
    def art(self):
        return self[0]

    @property
    def text(self):
        return self[1]


def _leer(v):
    return v is None or v == ""


def _zahl(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def _pos_liste(zeilen, positionen):
    """'Pos. 10, 20, 30 …' der Zeilen."""
    nr = [str(positionen[z].get("pos") or z + 1) for z in zeilen]
    return "Pos. " + ", ".join(nr[:POSITIONEN_ZEIGEN]) + (" …" if len(nr) > POSITIONEN_ZEIGEN else "")


def _n_pos(n):
    return f"{n} Position{'en' if n > 1 else ''}"


def punkte(kopf, positionen, status, stand, summen, staffeln_veraltet=0, gueltig_bis=None, heute=None, *,
           kalk_zeilen=None, kunde=None, preis_abweichung=(), mindestmarge=0, admin=False, laser_hinweise=(),
           staffel_widersprueche=()):
    """Alle Punkte [Punkt], FEHLER zuerst. status = Status je Position, stand = Stand der Optimierung, summen =
    rechnen.kalkulation(...)[1], kalk_zeilen = deren Zeilen (Hinweise, Zukauf ohne EK je Position), kunde = Zeile des
    Kunden (None = nicht prüfen), preis_abweichung = rechnen.preisbasis_abweichung, mindestmarge = Anteil (0 = aus),
    admin = Marge mit Zahlen nennen (sonst ohne), laser_hinweise = rechnen.laser_hinweise (Werkstoff-Hinweise für den
    Rohrlaser, Patrick 24.10.2026 „5b“), staffel_widersprueche = ausgabe.staffel_widersprueche (Staffelpreise, die im
    Angebots-PDF dem Preis der Zeile widersprechen)."""
    from .angebot import aktiv as position_aktiv
    from .rechnen import anbau_offen, bohrbild_offen, verschickt_abweichung
    from .stammdaten import zahl_als_text as zahl
    from . import fracht_angebot
    out = []
    aktiv = [i for i, p in enumerate(positionen) if position_aktiv(p)]
    st = {i: str(status[i] if i < len(status) else "") for i in aktiv}
    if not aktiv:
        out.append(Punkt(FEHLER, "keine Positionen"))
    if _leer(kopf.get("kunde")):
        out.append(Punkt(WARNUNG, "kein Kunde eingetragen", "kopf:kunde"))
    if stand != "aktuell":
        out.append(Punkt(WARNUNG, "Schnittplan nicht aktuell: wird vor dem Angebot neu optimiert", "optimieren"))
    for art in (FEHLER, WARNUNG):
        z = [i for i in aktiv if st[i].startswith(art)]
        if z:
            out.append(Punkt(art, f"{_n_pos(len(z))} mit {art} (siehe Meldungen)", f"pos:{z[0]}",
                             _pos_liste(z, positionen)))
    for pruefen, text in ((bohrbild_offen, "Bohrungen/Gewinde-Vorschlag ungeprüft"), (anbau_offen, "Anbauteile ungeprüft")):
        z = [i for i in aktiv if pruefen(positionen[i])]
        if z:
            out.append(Punkt(WARNUNG, f"{_n_pos(len(z))}: {text}", f"pos:{z[0]}", _pos_liste(z, positionen)))
    if kalk_zeilen is not None and stand == "aktuell":     # vorher meldet jede Position „kein Schnittplan“
        z = [i for i in aktiv if i < len(kalk_zeilen) and kalk_zeilen[i] and kalk_zeilen[i].get("hinweis")
             and not st[i].startswith((FEHLER, WARNUNG))]
        if z:
            out.append(Punkt(WARNUNG, f"{_n_pos(len(z))} mit Hinweis in der Kalkulation, z. B. "
                             f"„{kalk_zeilen[z[0]]['hinweis']}“", f"pos:{z[0]}", _pos_liste(z, positionen)))
    if kalk_zeilen is not None:
        z = [i for i in aktiv if i < len(kalk_zeilen) and kalk_zeilen[i] and kalk_zeilen[i].get("zukauf_fehlt")]
        if z:
            out.append(Punkt(WARNUNG, f"{_n_pos(len(z))}: Zukaufteil ohne Einkaufspreis", f"pos:{z[0]}",
                             _pos_liste(z, positionen)))
    if summen.get("fracht_fehler"):
        out.append(Punkt(WARNUNG, f"Fracht: {summen['fracht_fehler']}", "fracht",
                         "Das Angebot enthält dann keine Fracht." if fracht_angebot.auto(kopf) else ""))
    verkauf, gewinn = _zahl(summen.get("verkauf")), _zahl(summen.get("gewinn"))
    if mindestmarge and verkauf and gewinn is not None and gewinn / verkauf < mindestmarge - 1e-9:
        text = (f"Marge {zahl(100 * gewinn / verkauf, 1)} % unter der Mindestmarge {zahl(100 * mindestmarge, 1)} %"
                if admin else "Marge unter der Mindestmarge (Einstellungen)")
        out.append(Punkt(WARNUNG, text, "kalkulation"))
    if staffel_widersprueche:
        n = len(staffel_widersprueche)
        out.append(Punkt(WARNUNG, f"Staffelpreis widerspricht dem Angebotspreis ({n} Zeile{'n' if n > 1 else ''}): "
                         f"{staffel_widersprueche[0]}", "staffeln",
                         "Die Stufen rechnen mit eigenen Werten (z. B. Materialzuschlag). Der Kunde sieht beide Preise "
                         "untereinander; Stufe oder Angebotswerte angleichen. " + "; ".join(staffel_widersprueche[1:3])))
    if staffeln_veraltet:
        out.append(Punkt(HINWEIS, f"{staffeln_veraltet} Staffelstufe(n) veraltet (werden vor dem PDF neu gerechnet)",
                         "staffeln"))
    for h in laser_hinweise or ():
        z = [i for i in h["zeilen"] if i in st]
        if z:
            out.append(Punkt(HINWEIS, f"Werkstoff {h['werkstoff']}: {h['text']}", f"pos:{z[0]}",
                             _pos_liste(z, positionen)))
    if summen.get("mindestpreis_gilt"):
        out.append(Punkt(HINWEIS, f"Mindestauftragswert greift: Preis wurde auf {zahl(summen.get('verkauf'), 2)} € "
                         f"angehoben (+{zahl(summen.get('mindestpreis_anhebung') or 0, 2)} €)",
                         "kopf:mindestpreis_anwenden"))
    if preis_abweichung:
        n = len(preis_abweichung)
        out.append(Punkt(HINWEIS, f"Stammdaten seit dem Festschreiben geändert ({n} Wert{'e' if n > 1 else ''}): "
                         "„Aktuelle Preise übernehmen …“ rechnet mit den neuen", "preise",
                         "; ".join(preis_abweichung[:3]) + (" …" if n > 3 else "")))
    v = verschickt_abweichung(kopf.get("preisbasis"), summen.get("verkauf"))
    if v:
        out.append(Punkt(HINWEIS, v, "kalkulation"))
    if kunde is not None and not _leer(kopf.get("kunde")) and _leer((kunde or {}).get("email")):
        out.append(Punkt(HINWEIS, "Kunde ohne E-Mail-Adresse", "kunde"))
    if _leer(kopf.get("lieferzeit_art")) and _leer(kopf.get("lieferzeit_zusatz")):
        out.append(Punkt(HINWEIS, "Lieferzeit leer (es gilt der Text der Bedingungen)", "kopf:lieferzeit"))
    if _leer(kopf.get("kundenreferenz")):
        out.append(Punkt(HINWEIS, "Kundenreferenz (Anfrage des Kunden) leer", "kopf:kundenreferenz"))
    if gueltig_bis and kopf.get("vorgang") == "Verschickt" and gueltig_bis < (heute or datetime.date.today()):
        out.append(Punkt(HINWEIS, f"Gültigkeit abgelaufen ({gueltig_bis.strftime('%d.%m.%Y')})"))
    return sorted(out, key=lambda p: ARTEN.index(p.art))


def offen(liste):
    """Punkte, die vor dem Versand eine Rückfrage auslösen (FEHLER, WARNUNG)."""
    return [p for p in liste if p.art != HINWEIS]


def blockiert(liste):
    return any(p.art == FEHLER for p in liste)


def versand_eintrag(liste, begruendung):
    """Was im Versandverlauf steht, wenn der Check übergangen wurde: {punkte, begruendung} oder None."""
    o = offen(liste)
    if not o:
        return None
    return dict(punkte=[f"{p.art}: {p.text}" for p in o], begruendung=(begruendung or "").strip() or None)
