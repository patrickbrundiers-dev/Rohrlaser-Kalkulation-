"""Staffelpreise: jede Mengenstufe als eigenes Angebot neu rechnen.

Eine Stufe hat einen Schlüssel (Satzbezeichnung aus der Spalte 'Satz' oder eine Positionsnummer) und
eine Menge (Anzahl Sätze bzw. Stück). Im Rechenlauf sind nur die Positionen dieser Stufe besetzt:
bei einem Satz Menge × 'Stück je Satz', bei einer Position die Menge selbst. Alle anderen Stückzahlen
sind leer. So fallen Rüsten, Stangenwechsel und Verschnitt je Stufe neu an, ebenso Programmierkosten, Rüstzeit und Pauschale
je Abmessung, Angebotsaufschlag und Fracht (jede Stufe ist ein eigenes Angebot).
"""
import hashlib
import json

from . import rechnen
from .stammdaten import kontext_aus

SPALTEN = ("schluessel", "bezeichnung", "einheit", "menge", "teile", "stangen", "material", "laser", "ruesten",
           "herstell", "herstell_einheit", "preis_einheit", "preis_gesamt", "hinweis")
MAX_STUFEN = 200


def txt(v):
    """Schlüssel immer als Text vergleichen; ganze Zahlen ohne Nachkommastellen (Txt in Staffel.bas)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) else repr(float(v))
    return str(v).strip()


def _zahl(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def je_satz(p):
    n = _zahl(p.get("je_satz"))
    return n if n >= 1 else 1


def pruefen(stufe, positionen):
    """Prüfspalte der Staffeln."""
    schl = txt(stufe.get("schluessel"))
    if not schl:
        return ""
    if _zahl(stufe.get("menge")) < 1:
        return "FEHLER: Menge fehlt"
    n = sum(1 for p in positionen if txt(p.get("satz")) == schl)
    if n:
        return f"Satz mit {n} Positionen"
    if any(txt(p.get("pos")) == schl for p in positionen):
        return "Position"
    return "FEHLER: Satz/Pos. nicht im Angebot"


def auswahl(positionen):
    """Was sich als Stufe wählen lässt: jeder Satz und jede Position ohne Satz (mit Profil).
    Ergebnis: [(Schlüssel, Anzeigetext, aktuelle Menge in Sätzen bzw. Stück oder None)]."""
    saetze, einzeln = {}, []
    for p in positionen:
        if p.get("profil_id") in (None, ""):
            continue
        s = txt(p.get("satz"))
        if s:
            saetze.setdefault(s, []).append(p)
        elif txt(p.get("pos")):
            menge = int(_zahl(p.get("stueck"))) if _zahl(p.get("stueck")) >= 1 else None
            text = f"Pos. {txt(p.get('pos'))}" + "".join(f" – {p[n]}" for n in ("artikel", "bezeichnung") if p.get(n))
            einzeln.append((txt(p.get("pos")), text, menge))
    out = []
    for s, ps in saetze.items():
        mengen = {int(_zahl(p.get("stueck")) // je_satz(p)) for p in ps if _zahl(p.get("stueck")) >= 1}
        menge = mengen.pop() if len(mengen) == 1 else None
        pos = ", ".join(txt(p.get("pos")) for p in ps)
        out.append((s, f"Satz {s} ({len(ps)} Pos.: {pos})", menge or None))
    return out + einzeln


def gueltige(stufen):
    """Stufen, die gerechnet werden: Schlüssel gefüllt und Menge ≥ 1 (höchstens MAX_STUFEN)."""
    return [s for s in stufen if txt(s.get("schluessel")) and _zahl(s.get("menge")) >= 1][:MAX_STUFEN]


def szenario(schl, menge, positionen):
    """Stückzahlen eines Rechenlaufs. Ergebnis: (ist_satz, {Index: Stückzahl}, Bezeichnung)."""
    ist_satz = any(txt(p.get("satz")) == schl for p in positionen) and bool(schl)
    mengen, bez = {}, ""
    for i, p in enumerate(positionen):
        if p.get("profil_id") in (None, ""):
            continue
        if (txt(p.get("satz")) == schl) if ist_satz else (txt(p.get("pos")) == schl):
            mengen[i] = menge * (je_satz(p) if ist_satz else 1)
            if len(bez) < 60:
                if ist_satz:
                    bez += (", " if bez else "Pos. ") + txt(p.get("pos"))
                else:
                    bez = txt(p.get("bezeichnung"))
    return ist_satz, mengen, bez


def rechnen_alle(kopf, positionen, stufen, k, tabellen, einst, fortschritt=None):
    """Alle gültigen Stufen rechnen. Ergebnis: Liste von dicts mit den Spalten aus SPALTEN.
    fortschritt(i, n) wird vor jeder Stufe aufgerufen und kann mit False abbrechen."""
    stufen = gueltige(stufen)
    zeilen = []
    for n, st in enumerate(stufen):
        if fortschritt and fortschritt(n, len(stufen)) is False:
            break
        zeilen.append(stufe_rechnen(kopf, positionen, txt(st["schluessel"]), st["menge"], k, tabellen, einst))
    return zeilen


def stufe_rechnen(kopf, positionen, schl, menge, k, tabellen, einst):
    ist_satz, mengen, bez = szenario(schl, menge, positionen)
    z = dict.fromkeys(SPALTEN)
    z.update(schluessel=schl, einheit="Satz" if ist_satz else "Stück", menge=menge)
    if not mengen:
        z.update(bezeichnung="", hinweis="FEHLER: Satz/Pos. nicht im Angebot")
        return z
    z["bezeichnung"] = bez
    lauf = [dict(p, stueck=mengen.get(i)) for i, p in enumerate(positionen)]
    erg = rechnen.optimieren(kopf, lauf, k)
    if erg["neue_profile"]:      # Profil aus dem Namen gilt für diesen Lauf als angelegt
        k = kontext_aus({"profile": list(k.profile.values()) + erg["neue_profile"],
                         "werkstoffe": list(k.werkstoffe.values()), "maschinen": list(k.maschinen.values()),
                         "oberflaechen": list(k.oberflaechen.values())}, k.profilformen, k.kategorien)
    kz, summen = rechnen.kalkulation(kopf, lauf, erg, k, tabellen, einst)
    z.update(teile=summen["teile"], stangen=summen["stangen"], material=summen["material"], laser=summen["laser"],
             ruesten=summen["ruesten"], herstell=summen["herstell"])
    z["herstell_einheit"] = summen["herstell"] / menge
    z["preis_einheit"] = round(summen["verkauf"] / menge, 2)
    z["preis_gesamt"] = round(z["preis_einheit"] * menge, 2)
    hinweise = offen = 0
    for i in mengen:
        if kz[i] is None:
            continue
        if kz[i]["hinweis"]:
            hinweise += 1
        offen += _zahl(kz[i]["nicht_eingeplant"])
    text = f"WARNUNG: {offen:.0f} Teile nicht eingeplant" if offen > 0 else ""
    if hinweise:
        text += ("; " if text else "") + f"{hinweise} Hinweis(e) in der Kalkulation"
    z["hinweis"] = text or None
    return z


def kennung(kopf, positionen, stufen, k, tabellen, einst):
    """Prüfsumme über alle Eingaben der Staffelrechnung; weicht sie ab, sind die Staffelpreise veraltet."""
    felder = ("maschine", "stange", "fracht", "skonto")
    daten = [{f: kopf.get(f) for f in felder},
             [{a: b for a, b in p.items() if a not in ("id", "angebot_id", "nr", "zeile")} for p in positionen],
             [(txt(s.get("schluessel")), s.get("menge")) for s in gueltige(stufen)],
             [k.profile, k.werkstoffe, k.maschinen, k.oberflaechen], tabellen,
             {n: einst.get(n) for n in ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung", "gewinn",
                                         "ruesten_abmessung",
                                         "pauschale_abmessung", "programmierung_teil", "angebotsaufschlag")}]
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()
