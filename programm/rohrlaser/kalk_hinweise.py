"""Rechenhilfen und Hinweise der Kalkulation (Vorschläge vom 02.11.2026):
- G1 Zielpreis rückwärts: nötiger Gewinn für einen Zielpreis (gesamt) bzw. Menge, ab der ein Stück-Zielpreis mit dem
  normalen Gewinn erreicht wird; „Auf Zielpreis setzen“ stellt den Gewinn des Angebots um.
- G4 Gewinn nach Auslastung: nur Hinweis im Angebots-Check (Lieferwoche voll bzw. viel frei).
- G5 Marktpreis aus Absagen: mittlerer Abstand zum Wettbewerb bei ähnlichen Angeboten (Werkstoff-Kategorie und
  Preisklasse), erst ab MARKT_AB Absagen mit Preis.
- J1 Preisuntergrenze: Warnung, wenn Preis oder Zielpreis darunter liegt.
- J5 Losgröße (Andler) für Abruf-Angebote.
Ohne Qt."""
import math

from . import absage
from .stammdaten import zahl_als_text as zahl

MARKT_AB = 3


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ G1 Zielpreis
def gewinn_fuer_ziel(verkauf_bei, ziel, von=-0.5, bis=5.0, schritte=60):
    """Gewinn (Anteil), mit dem verkauf_bei(gewinn) den Zielpreis trifft (Bisektion; der Preis steigt mit dem Gewinn).
    None, wenn der Zielpreis auch mit Gewinn 'von' nicht erreichbar ist."""
    if ziel <= 0:
        return None
    if verkauf_bei(von) > ziel + 0.005:
        return None
    if verkauf_bei(bis) < ziel:
        return bis
    for _ in range(schritte):
        mitte = (von + bis) / 2
        if verkauf_bei(mitte) < ziel:
            von = mitte
        else:
            bis = mitte
    return (von + bis) / 2


def menge_fuer_ziel(stueckpreis_bei, stueck, ziel, faktoren=(1, 1.5, 2, 3, 4, 5, 7.5, 10, 15, 20)):
    """Kleinste Stückzahl (Vielfaches der angefragten), bei der stueckpreis_bei(menge) ≤ Ziel € je Stück; None, wenn
    auch das 20-fache nicht reicht."""
    for f in faktoren:
        menge = max(1, int(math.ceil(stueck * f)))
        if stueckpreis_bei(menge) <= ziel + 1e-9:
            return menge
    return None


def ziel_text(ziel, gewinn_alt, gewinn_neu, mindestmarge=None, marge_neu=None):
    if gewinn_neu is None:
        return f"Zielpreis {zahl(ziel, 2)} € ist auch ohne Gewinn nicht zu erreichen."
    t = (f"Für den Zielpreis {zahl(ziel, 2)} € netto braucht das Angebot {zahl(100 * gewinn_neu, 1)} % Gewinn "
         f"(jetzt {zahl(100 * gewinn_alt, 1)} %).")
    if mindestmarge and marge_neu is not None and marge_neu < mindestmarge:
        t += f" Die Marge läge dann mit {zahl(100 * marge_neu, 1)} % unter der Mindestmarge ({zahl(100 * mindestmarge, 0)} %)."
    return t


# ------------------------------------------------------------------ J1 Preisuntergrenze
def untergrenze_punkte(summen, ziel=None):
    """Angebots-Check: WARNUNG, wenn der Preis (nach Skonto) bzw. der Zielpreis unter der langfristigen Untergrenze
    liegt; unter der kurzfristigen deckt er nicht einmal die variablen Kosten."""
    out = []
    lang, kurz = _n(summen.get("untergrenze_lang")), _n(summen.get("untergrenze_kurz"))
    if lang <= 0:
        return out
    preis = _n(summen.get("verkauf")) - _n(summen.get("skonto"))
    for was, wert in (("Der Preis", preis), ("Der Zielpreis", _n(ziel))):
        if wert <= 0:
            continue
        if wert < kurz - 0.005:
            out.append(("WARNUNG", f"{was} {zahl(wert, 2)} € liegt unter der kurzfristigen Preisuntergrenze "
                                   f"{zahl(kurz, 2)} € (variable Kosten) – jedes Stück kostet Geld.", None))
        elif wert < lang - 0.005:
            out.append(("WARNUNG", f"{was} {zahl(wert, 2)} € liegt unter der langfristigen Preisuntergrenze "
                                   f"{zahl(lang, 2)} € (Selbstkosten) – nur als Lückenfüller sinnvoll.", None))
    return out


# ------------------------------------------------------------------ G4 Gewinn nach Auslastung
def auslastung_punkt(quote, woche, hoch=0.90, niedrig=0.50):
    """Hinweis zur Belegung der Lieferwoche (quote = Bedarf ÷ Kapazität der Maschine) oder None. Nie automatisch."""
    if quote is None:
        return None
    if hoch and quote >= hoch:
        return ("HINWEIS", f"Die Maschine ist in {woche} zu {zahl(100 * quote, 0)} % belegt: kein Preisnachlass "
                           "nötig, eher mehr Gewinn.", None)
    if niedrig and quote < niedrig:
        return ("HINWEIS", f"Die Maschine ist in {woche} erst zu {zahl(100 * quote, 0)} % belegt: Spielraum beim "
                           "Gewinn bis zur Mindestmarge.", None)
    return None


# ------------------------------------------------------------------ G5 Marktpreis aus Absagen
def marktpreis(zeilen, werkstoffe_je_angebot, kategorien, kategorie, netto, heute=None, ohne_id=None):
    """Absagen mit Wettbewerbspreis der letzten 365 Tage mit gleicher Werkstoff-Kategorie und Preisklasse:
    dict(n, abstand=mittlerer Abstand unser/Wettbewerb − 1, kategorie, klasse) oder None (unter MARKT_AB)."""
    klasse = absage.preisklasse(netto)
    werte = []
    for z in absage.auswahl(zeilen, heute, 365):
        if z.get("id") == ohne_id or absage._vorgang(z) != "Abgelehnt":
            continue
        if absage.kategorie_des_angebots(werkstoffe_je_angebot.get(z["id"]), kategorien) != kategorie:
            continue
        if absage.preisklasse(z.get("vk_netto")) != klasse:
            continue
        a = absage.letzte(z)
        n = z.get("vk_netto")
        if a and a.get("preis") and isinstance(n, (int, float)) and n > 0:
            werte.append(n / a["preis"] - 1)
    if len(werte) < MARKT_AB:
        return None
    return dict(n=len(werte), abstand=sum(werte) / len(werte), kategorie=kategorie, klasse=klasse)


def markt_text(m):
    if not m:
        return ""
    richtung = "unter" if m["abstand"] > 0 else "über"
    return (f"Bei ähnlichen Angeboten ({m['kategorie']}, {m['klasse']}) lag der Wettbewerb im Mittel "
            f"{zahl(abs(100 * m['abstand']), 0)} % {richtung} uns ({m['n']} Absagen mit Preis).")


# ------------------------------------------------------------------ J5 Losgröße
def losgroesse(jahresmenge, ruest_je_los, stueckkosten, zins):
    """Wirtschaftliche Losgröße nach Andler: √(2 × Jahresmenge × Rüstkosten je Los ÷ (Stückkosten × Lagerzins)).
    None ohne Werte."""
    j, r, s, z = _n(jahresmenge), _n(ruest_je_los), _n(stueckkosten), _n(zins)
    if j <= 0 or r <= 0 or s <= 0 or z <= 0:
        return None
    return max(1, int(round(math.sqrt(2 * j * r / (s * z)))))
