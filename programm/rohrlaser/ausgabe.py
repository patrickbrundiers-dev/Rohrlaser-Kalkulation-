"""Inhalte der Ausgaben: Angebot, Werkstattpapier (Schnittpläne), Kalkulation.

Die Funktionen liefern nur Daten (Zeilen und Summen); pdf.py setzt sie als PDF.
"""
import datetime
import re
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

from . import abruf, fracht_angebot, normprofile, rechnen, stangen_abwicklung, virtuell, zukauf
from .angebot import aktiv as position_aktiv, bedingungen_text, ist_baugruppe, ist_zukaufteil, lieferzeit_text
from .stammdaten import GESCHABT, ROHR_FORMEN

ABLAGE = "Angebote"     # Ordner neben dem Programm, wenn kein Ablageordner eingestellt ist


# ------------------------------------------------------------------ Hilfen
def kaufm_runden(x, stellen=2):
    """Kaufmännisch runden (halbe Einheit von null weg)."""
    if x is None:
        return None
    q = Decimal(1).scaleb(-stellen)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def preiseinheit(preis, ab):
    """Preiseinheit eines Stückpreises (Plan „Kalkulation und Berechnung verbessern“ B3, Patrick 29.10.2026): 100
    unter 'ab' €, 1000 unter einem Zehntel davon, sonst 1 (ab leer oder 0 = immer 1). Auf den Cent gerundete
    Kleinteilpreise verlieren sonst viel (0,034 € → 0,03 € = 12 % weniger)."""
    if not isinstance(ab, (int, float)) or isinstance(ab, bool) or ab <= 0 or preis is None or preis <= 0:
        return 1
    return 1000 if preis < ab / 10 else 100 if preis < ab else 1


def aufrunden(x, stellen=2):
    """Auf die Stelle aufrunden (Cent), Gleitkommareste unter 1e-6 zählen nicht: 66,666… -> 66,67; 66,67000000001 -> 66,67.
    Für Preise, die einen Mindestpreis erreichen müssen."""
    if x is None:
        return None
    q = Decimal(1).scaleb(-stellen)
    return float(Decimal(repr(float(x))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).quantize(q, rounding=ROUND_CEILING))


def euro_text(x):
    """Betrag deutsch mit zwei Stellen, z. B. 1.234,50"""
    return f"{kaufm_runden(x, 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def zahl_kurz(x, dezimal=","):
    """Format '0.##': höchstens 2 Nachkommastellen, ohne Nullen am Ende (42,4 / 2 / 2,6)."""
    if x is None or x == "":
        return ""
    s = f"{kaufm_runden(x, 2):.2f}".rstrip("0").rstrip(".")
    return s.replace(".", dezimal)


def _wert(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _satz(v):
    return "" if v is None else str(v).strip()


def dateiname(kopf, zusatz="", mit_kunde=False):
    """'<Angebotsnummer> [<Kunde>] <Zusatz>' ohne in Dateinamen verbotene Zeichen."""
    s = str(kopf.get("nummer") or "").strip() or "Angebot"
    if mit_kunde and str(kopf.get("kunde") or "").strip():
        s += " " + str(kopf["kunde"]).strip()
    if zusatz:
        s += " " + zusatz
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s).strip()


def ablageordner(einstellung, vorgabe):
    """Ablage: eingestellter Ordner, sonst die Vorgabe (portabel 'Angebote' neben dem Programm, installiert
    Dokumente\\Rohrlaser Angebote). Wird angelegt."""
    ordner = Path(einstellung) if einstellung else Path(vorgabe)
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def nummern_text(nummern):
    """Stangennummern kompakt: [1, 2, 3, 7] -> '1–3, 7'."""
    teile, i = [], 0
    while i < len(nummern):
        j = i
        while j + 1 < len(nummern) and nummern[j + 1] == nummern[j] + 1:
            j += 1
        teile.append(f"{nummern[i]}–{nummern[j]}" if j > i else str(nummern[i]))
        i = j + 1
    return ", ".join(teile)


def datum_text(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return str(iso)


# ------------------------------------------------------------------ Angebot
def profiltext(pid, k, dezimal=","):
    """'Rundrohr Ø 42,4 x 2', 'Quadratrohr 40 x 40 x 3', 'Rechteckrohr 60 x 40 x 3'; Träger, T- und U-Profile mit
    Normbezeichnung ('IPE 200', 'HEB 160', 'UPN 100'), wenn Profil-ID oder Maße zu einem Normprofil passen; sonst die
    Profil-ID."""
    z = k.profile.get(pid)
    if not z:
        return str(pid or "")
    form = z.get("form")
    if form in ("I-/H-Träger", "T-Profil", "U-Profil"):      # Walzprofile mit Normbezeichnung (IPE, HEB, UPN, T …)
        norm = pid if normprofile.daten(pid) else normprofile.name_aus_massen(form, z.get("a"), z.get("b"), z.get("wand"))
        if norm:
            return str(norm)
    a, b, wand = (zahl_kurz(z.get(n), dezimal) for n in ("a", "b", "wand"))
    return {"Rundrohr": f"Rundrohr Ø {a} x {wand}", "Quadratrohr": f"Quadratrohr {a} x {a} x {wand}",
            "Rechteckrohr": f"Rechteckrohr {a} x {b} x {wand}", "U-Profil": f"U-Profil {a} x {b} x {wand}",
            "C-Profil": f"C-Profil {a} x {b} x {wand}", "L-Profil": f"L-Profil {a} x {b} x {wand}",
            "Flachstahl": f"Flachstahl {a} x {wand}",
            "I-/H-Träger": f"I-Träger {a} x {b} x {wand}", "T-Profil": f"T-Profil {a} x {b} x {wand}"}.get(
        form, str(pid))


def rohrart_text(p, k, kopf=None):
    """Rohrart für Angebot und Werkstattpapier (Patrick 31.10.2026, Plan 7a): die im Angebot gewählte Rohrart des
    Hohlprofils bzw. „Naht innen geschabt“ aus dem Werkstoff; '' = nichts zu nennen."""
    if (k.profile.get(p.get("profil_id")) or {}).get("form") not in ROHR_FORMEN:
        return ""
    ra = rechnen.rohrart_angebot(kopf, p.get("profil_id"), p.get("werkstoff_id"))
    if ra:
        return ra
    return GESCHABT if rechnen.rohrart(p.get("werkstoff_id"), k) == GESCHABT else ""


def angebotstext(p, k, dezimal=",", zusatz=(), kopf=None):
    """Bezeichnung einer Position im Angebot, jede Angabe in einer eigenen Zeile, z. B.
    'Rechteckrohr 80 x 40 x 5\nL = 1500 mm\ninkl. Material S235 EN10219\nfeuerverzinkt\ninkl. Gewinde 4xM6\n
    inkl. Gravur'. zusatz: Zusatzarbeiten der Position aus der Kalkulation (Text im Angebot aus den Stammdaten, dazu
    der Text der Position, z. B. RAL 7016). Zukaufteile mit 'Im Angebotstext nennen' je Zeile mit Menge je Teil."""
    if ist_zukaufteil(p):
        return zukaufteil_text(p)
    if ist_baugruppe(p):
        from . import baugruppe
        return baugruppe.text_angebot(p)
    laenge = p.get("laenge")
    zeilen = [profiltext(p.get("profil_id"), k, dezimal),
              f"L = {kaufm_runden(laenge, 0):.0f} mm" if isinstance(laenge, (int, float)) else "L =  mm"]
    w = k.werkstoffe.get(p.get("werkstoff_id"))
    material = (w or {}).get("angebotstext") or str(p.get("werkstoff_id") or "")
    zeilen.append(f"Material {material} vom Kunden beigestellt" if rechnen.beigestellt(p) else "inkl. Material " + material)
    ra = rohrart_text(p, k, kopf)
    if ra:
        zeilen.append(ra if ra == GESCHABT else f"Rohr {ra}")
    ob = rechnen.oberflaeche_von(p)
    if ob:
        zeilen.append((k.oberflaechen.get(ob) or {}).get("angebotstext") or ob)
    zus = []
    if p.get("gewinde"):
        zus.append(f"Gewinde {p['gewinde']}")
    if _wert(p.get("gravur")) > 0 or rechnen.gravur_artikel(p) > 0:
        zus.append("Gravur")
    for e in zusatz or ():
        t_e = e["angebotstext"] + (f" {e['text']}" if e.get("text") else "")
        if t_e not in zus:
            zus.append(t_e)
    zeilen += ["inkl. " + z for z in zus]
    for e in zukauf.eintraege(p):        # Zukaufteile mit 'Im Angebotstext nennen': Menge je Teil und Bezeichnung
        st = e.get("stand") or {}
        name = st.get("bezeichnung") or st.get("artikelnr")
        if name and st.get("angebotstext") == "ja":
            m = _wert(e.get("menge"))
            menge = f"{kaufm_runden(m, 3):g}".replace(".", dezimal)
            zeilen.append("inkl. " + (f"{menge} {zukauf.EINHEIT_KURZ.get(st.get('einheit'), 'St')} {name}" if m else name))
    return "\n".join(zeilen)


def zukaufteil_text(p):
    """Text einer Zukaufteil-Position im Angebot: Bezeichnung der Zukaufartikel (bei mehreren mit Menge je Teil),
    sonst die Bezeichnung der Position, z. B. 'Blech S235 500 × 300 × 5 mm'."""
    namen = []
    eintraege = zukauf.eintraege(p)
    for e in eintraege:
        st = e.get("stand") or {}
        name = st.get("bezeichnung") or st.get("artikelnr") or ""
        m = _wert(e.get("menge"))
        if len(eintraege) > 1 or m != 1:
            name = f"{kaufm_runden(m, 3):g}".replace(".", ",") + f" {zukauf.EINHEIT_KURZ.get(st.get('einheit'), 'St')} {name}"
        namen.append(name)
    return ", ".join(n for n in namen if n) or str(p.get("bezeichnung") or p.get("artikel") or "Zukaufteil")


def _einruecken(vorsatz, text):
    """Satzteil im Angebot: '   2 x ' vor der ersten Zeile, Folgezeilen eingerückt unter die Bezeichnung
    (geschützte Leerzeichen, damit der PDF-Absatz sie nicht entfernt)."""
    erste, *rest = text.split("\n")
    return "\n".join(["   " + vorsatz + erste] + ["\u00a0" * round(1.5 * len(vorsatz)) + z for z in rest])


def beistellung_text(positionen, ergebnis, k, einst, dezimal=","):
    """Hinweis im Angebot, wenn der Kunde Material beistellt, mit dem Stangenbedarf aus der Optimierung, z. B.
    'Material wird vom Kunden beigestellt: 3 Stangen Quadratrohr 40 x 40 x 3, S235 EN10219, à 6.000 mm.'
    Leer ohne Kundenmaterial oder wenn die Einstellung 'beistellung_hinweis' nein ist."""
    pos = [p for p in positionen if rechnen.beigestellt(p) and position_aktiv(p) and not ist_zukaufteil(p)]
    if not pos or (einst or {}).get("beistellung_hinweis") == "nein":
        return ""
    bedarf = {}
    for s in (ergebnis or {}).get("stangen") or ():
        if s.get("beistellung"):
            schl = (s["profil"], s["werkstoff"], s.get("oberflaeche") or "", s["stange"])
            bedarf[schl] = bedarf.get(schl, 0) + 1
    if not bedarf:
        nr = ", ".join(str(p.get("pos") or p.get("artikel") or "") for p in pos)
        return f"Das Material der Pos. {nr} wird vom Kunden beigestellt."
    teile = []
    for (profil, werkstoff, ob, stange), n in bedarf.items():
        w = (k.werkstoffe.get(werkstoff) or {}).get("angebotstext") or werkstoff
        laenge = f"{kaufm_runden(stange, 0):,.0f}".replace(",", ".")
        teile.append(f"{n} {'Stange' if n == 1 else 'Stangen'} {profiltext(profil, k, dezimal)}, {w}"
                     + (f", {ob}" if ob else "") + f", à {laenge} mm")
    return "Material wird vom Kunden beigestellt: " + "; ".join(teile) + "."


def angebot(kopf, positionen, kalk_zeilen, k, einst, staffelpreise=(), dezimal=",", ergebnis=None):
    """Inhalt des Angebots (AngebotFuellen). Ergebnis: dict mit
    zeilen [{art: teil|satz|satzteil, pos, artikel, text, menge, preis, gesamt, staffeln}], netto, mwst, brutto,
    mwst_satz, staffeln [{art, pos, satz, text, menge, bereich ('ab 10'), preis, gesamt}] (Stufen mit FEHLER fehlen;
    jede Stufe steht auch unter 'staffeln' ihrer Teil- bzw. Satzzeile, Stufen ohne passende Zeile nur hier),
    hinweise (Positionen mit Hinweis)."""
    def preis(i, pe=1):
        z = kalk_zeilen[i]
        if z and _wert(z.get("mindestpreis_teil")) > 0:      # auf Mindestpreis angehoben: aufrunden, damit die
            return aufrunden(_wert(z["preis_teil"]) * pe)      # Summe den Mindestpreis nicht unterschreitet
        return kaufm_runden(_wert(z["preis_teil"]) * pe if z else 0, 2)

    pe_ab = einst.get("preiseinheit_ab")

    def _zus(i):
        return (kalk_zeilen[i] or {}).get("zusatzarbeiten") or ()

    def je(p):
        n = _wert(p.get("je_satz"))
        return n if n >= 1 else 1

    zeilen, erledigt = [], set()
    muster_ein = sum(_wert((z or {}).get("muster_einmal_position")) for z in kalk_zeilen)
    muster_zeile = muster_ein > 0
    muster_pos = [p.get("pos") for i, p in enumerate(positionen) if (kalk_zeilen[i] or {}).get("muster") == "ja"]
    for i, p in enumerate(positionen):
        if not position_aktiv(p):
            continue
        satz = _satz(p.get("satz"))
        if not satz:
            # Kleinteile: Preis je 100 bzw. 1000 Stück (Plan B3); Musterteile (Preis 0) je Stück
            pe = preiseinheit(_wert((kalk_zeilen[i] or {}).get("preis_teil")), pe_ab)
            pr, menge = preis(i, pe), _wert(p.get("stueck"))
            text = angebotstext(p, k, dezimal, _zus(i), kopf)
            if (kalk_zeilen[i] or {}).get("muster") == "ja":        # Musterteil: Preis 0 mit Vermerk
                text += "\n" + (MUSTER_VERMERK_ZEILE if muster_zeile else MUSTER_VERMERK)
            zeilen.append(dict(art="teil", pos=p.get("pos"), artikel=p.get("artikel"), text=text,
                               menge=p.get("stueck"), preis=pr, gesamt=kaufm_runden(pr * menge / pe, 2),
                               muster=(kalk_zeilen[i] or {}).get("muster") == "ja", preiseinheit=pe))
        elif satz not in erledigt:
            erledigt.add(satz)
            teile = [(j, q) for j, q in enumerate(positionen) if _satz(q.get("satz")) == satz]
            n = max((_wert(q.get("stueck")) / je(q) for _, q in teile), default=0)
            saetze = max(1, int(n + 0.5))
            bg = next(((j, q) for j, q in teile if ist_baugruppe(q)), None)
            einmal = 0.0        # Einmalkosten der Baugruppe als eigene Zeile: nicht im Preis je Baugruppe
            if bg is not None and (kalk_zeilen[bg[0]] or {}).get("bg_einmal_preis_teil"):
                einmal = kaufm_runden(kalk_zeilen[bg[0]]["bg_einmal_preis_teil"] * _wert(bg[1].get("stueck")), 2)
            if rechnen.neue_preisregeln(einst):    # aus ungerundeten Stückpreisen wie die Staffel (Patrick 26.10.2026)
                roh = sum(_wert((kalk_zeilen[j] or {}).get("preis_teil")) * je(q) for j, q in teile) - einmal / saetze
                mindest_satz = any(_wert((kalk_zeilen[j] or {}).get("mindestpreis_teil")) > 0 for j, _ in teile)
                satzpreis = aufrunden(roh) if mindest_satz else kaufm_runden(roh, 2)
            else:
                satzpreis = kaufm_runden(sum(preis(j) * je(q) for j, q in teile) - (einmal / saetze), 2)
            satz_muster = any((kalk_zeilen[j] or {}).get("muster") == "ja" for j, _ in teile)
            vermerk = ("\n" + (MUSTER_VERMERK_ZEILE if muster_zeile else MUSTER_VERMERK)) if satz_muster else ""
            if bg is None:
                zeilen.append(dict(art="satz", pos=None, artikel=None, satz=satz, text=f"Satz {satz}" + vermerk,
                                   menge=saetze, preis=satzpreis, gesamt=kaufm_runden(satzpreis * saetze, 2),
                                   muster=satz_muster))
            else:               # Schweißbaugruppe: eine Zeile, Einzelteile nur mit Häkchen 'Stückliste'
                from . import baugruppe
                zeilen.append(dict(art="satz", pos=bg[1].get("pos"), artikel=bg[1].get("artikel"), satz=satz,
                                   text=baugruppe.zeile_angebot(bg[1]) + vermerk, menge=saetze, einheit="Stk.",
                                   baugruppe=True, preis=satzpreis, gesamt=kaufm_runden(satzpreis * saetze, 2),
                                   muster=satz_muster))
                if einmal:
                    zeilen.append(dict(art="einmal", pos=None, artikel=None, satz=satz, einheit="pausch.",
                                       text=f"Einmalkosten Schweißbaugruppe {satz} (Rüsten, Vorrichtungen), "
                                            "einmalig je Auftrag",
                                       menge=1, preis=einmal, gesamt=einmal))
                if not baugruppe.stamm_wahl(bg[1], "stueckliste"):
                    continue
                teile = [(j, q) for j, q in teile if j != bg[0]]
            for j, q in teile:
                zeilen.append(dict(art="satzteil", pos=q.get("pos"), artikel=q.get("artikel"),
                                   text=_einruecken(f"{kaufm_runden(je(q), 0):.0f} x ",
                                                   angebotstext(q, k, dezimal, _zus(j), kopf)),
                                   menge=None, preis=None, gesamt=None))
    if muster_zeile:        # Musterkosten als eigene Zeile (Patrick 28.10.2026, F1)
        betrag = kaufm_runden(muster_ein, 2)
        zeilen.append(dict(art="einmal", pos=None, artikel=None, einheit="pausch.", menge=1, preis=betrag,
                           gesamt=betrag, text=f"Musterkosten einmalig (Pos. {_pos_text(muster_pos)}): Material, "
                                               "Programmierung und Rüsten der Muster"))
    hinweise = sum(1 for i, p in enumerate(positionen)
                   if position_aktiv(p) and kalk_zeilen[i] and kalk_zeilen[i]["hinweis"])
    netto = kaufm_runden(sum(z["gesamt"] for z in zeilen if z["gesamt"] is not None), 2)    # Summe ohne Gleitkommareste
    satz_mwst = _wert(einst.get("mwst"))
    mwst = kaufm_runden(netto * satz_mwst, 2)
    staffeln = []
    for z in staffelpreise or ():
        if z.get("preis_einheit") is None:      # Stufe mit FEHLER (z. B. Materialpreis fehlt): nicht ins Angebot
            continue
        # Rüstkosten 'separat' stehen nicht extra im Angebot: der Stufenpreis enthält sie (aufgerundet, damit
        # Menge x Preis den Stufenpreis nicht unterschreitet)
        einmalig, menge = ((z.get("preis") or {}).get("einmalig")) or 0, _wert(z["menge"]) or 1
        bg_einmal = _wert((z.get("preis") or {}).get("bg_einmalig"))   # Baugruppe: Einmalkosten als eigene Zeile
        bg_einmal += _wert((z.get("preis") or {}).get("muster_einmalig"))   # Musterkosten als eigene Zeile
        einmalig -= bg_einmal
        pe = _wert((z.get("preis") or {}).get("preiseinheit")) or 1      # Kleinteile: je 100 bzw. 1000 Stück
        if einmalig:
            pr = aufrunden((_wert(z["preis_gesamt"]) - bg_einmal) / menge * pe)
        else:
            pr = (z.get("preis") or {}).get("preis_pe") if pe > 1 else z["preis_einheit"]
        eintrag = dict(menge=z["menge"], bereich=f"ab {z['menge']:.0f}", preis=pr,
                       gesamt=kaufm_runden(pr * menge / pe + bg_einmal, 2) if einmalig else z["preis_gesamt"],
                       stufe=z.get("stufe_nr"), gemeinsam=bool(z.get("gemeinsam")), einmal=bg_einmal, preiseinheit=pe)
        if z.get("einheit") == "Satz":
            bez = z.get("bezeichnung") or ""
            staffeln.append(dict(art="satz", pos=None, satz=str(z["schluessel"]),
                                 text=f"Satz {z['schluessel']}" + (f" ({bez})" if bez else ""), **eintrag))
        else:
            staffeln.append(dict(art="teil", pos=z["schluessel"], text=z.get("bezeichnung") or "", **eintrag))
    _staffeln_zuordnen(zeilen, staffeln)
    mindest = _wert(einst.get("mindestpreis"))
    gilt = any(z and _wert(z.get("mindestpreis_teil")) > 0 for z in kalk_zeilen) or any(
        _wert((z.get("preis") or {}).get("mindest_anhebung")) > 0 for z in staffelpreise or ())
    return dict(zeilen=zeilen, netto=netto, mwst=mwst, brutto=kaufm_runden(netto + mwst, 2), mwst_satz=satz_mwst, staffeln=staffeln,
                hinweise=hinweise, zahlung=zahlungstext(kopf), fracht=fracht_angebot.angebotstext(kopf), anschrift=[],
                lieferzeit=lieferzeit_text(kopf), bedingungen=bedingungen_text(kopf, einst.get("bedingungen")),
                mindestpreis=(f"Mindestauftragswert {euro_text(mindest)} € netto"
                              + (" (Warenwert ohne Fracht)." if rechnen.neue_preisregeln(einst) else ".")
                              if gilt and mindest > 0 else ""),
                kundenreferenz=kopf.get("kundenreferenz") or "",
                muster="" if muster_zeile else muster_hinweis(kopf, einst, muster_pos,
                                                              sum(_wert((z or {}).get("muster_preis_position"))
                                                                  for z in kalk_zeilen)),
                beistellung=beistellung_text(positionen, ergebnis, k, einst, dezimal),
                rahmen=abruf.rahmentext(kopf, einst, muster=bool(muster_pos), datum=datum_text(kopf.get("datum"))))


MUSTER_VERMERK = "Muster – im Serienpreis enthalten"
MUSTER_VERMERK_ZEILE = "Muster – siehe Musterkosten einmalig"


def _pos_text(nummern):
    return ", ".join(str(int(n)) if isinstance(n, float) and n.is_integer() else str(n) for n in nummern if n not in (None, ""))


def muster_hinweis(kopf, einst, nummern, betrag):
    """Hinweis im Angebots-PDF zu Musterteilen, deren Kosten auf die Serie umgelegt sind (Patrick 28.10.2026, F6 a):
    Text der Einstellung 'muster_hinweis' mit {pos}, {betrag} (Verkaufswert der Muster netto) und {datum}
    (Angebotsdatum + 'muster_frist' Tage). Leer ohne Muster oder ohne Text."""
    vorlage = str((einst or {}).get("muster_hinweis") or "").strip()
    if not nummern or not vorlage or betrag <= 0:
        return ""
    try:
        d = datetime.date.fromisoformat(kopf.get("datum") or "")
    except ValueError:
        d = datetime.date.today()
    d += datetime.timedelta(days=int(_wert(einst.get("muster_frist"))))
    werte = dict(pos=_pos_text(nummern), betrag=euro_text(kaufm_runden(betrag, 2)), datum=d.strftime("%d.%m.%Y"))
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):      # Platzhalter falsch geschrieben: Text wie eingegeben
        return vorlage


def _staffeln_zuordnen(zeilen, staffeln):
    """Staffelstufen unter ihre Angebotszeile hängen (Teil über die Pos., Satz über den Namen), aufsteigend nach
    Menge; eine Stufe mit Menge und Preis der Zeile selbst wäre doppelt und entfällt dort."""
    def schl(v):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else _satz(v)

    for z in zeilen:
        z["staffeln"] = []
    teil = {schl(z["pos"]): z for z in zeilen if z["art"] == "teil" and z.get("pos") not in (None, "")}
    satz = {schl(z["satz"]): z for z in zeilen if z["art"] == "satz"}
    for st in staffeln:
        z = satz.get(schl(st["satz"])) if st["art"] == "satz" else teil.get(schl(st["pos"]))
        st["zugeordnet"] = z is not None
        if z is None or (_wert(st["menge"]) == _wert(z["menge"]) and st["preis"] == z["preis"]):
            continue
        st["baugruppe"] = bool(z.get("baugruppe"))
        z["staffeln"].append(st)
    for z in zeilen:
        z["staffeln"].sort(key=lambda st: _wert(st["menge"]))


def staffel_widersprueche(ang, toleranz=0.005):
    """Staffelpreise, die im Angebots-PDF dem Preis der Zeile widersprechen (Design-Prüfung D4): eine Stufe mit genau
    der angebotenen Menge nennt einen anderen Preis je Einheit, oder eine größere Menge kostet je Einheit mehr als die
    angebotene (kleinere Mengen dürfen teurer sein). Das passiert, wenn Stufen eigene Werte haben (z. B.
    Materialzuschlag). ang = angebot(...). Ergebnis: [Text] je betroffener Zeile."""
    out = []
    for z in ang.get("zeilen") or ():
        menge, preis, st = _wert(z.get("menge")), z.get("preis"), z.get("staffeln") or []
        if not st or not menge or not isinstance(preis, (int, float)):
            continue
        # Preiseinheit (je 100 bzw. 1000 Stück, Plan B3): auf die Preiseinheit der Zeile umrechnen
        pe = z.get("preiseinheit") or 1
        st = [dict(s, preis=s["preis"] / (s.get("preiseinheit") or 1) * pe) for s in st]
        tol = max(0.01, toleranz * preis)
        name = z.get("text") if z.get("art") == "satz" else f"Pos. {z.get('pos')}"
        einheit = "Satz" if z.get("art") == "satz" else "Stk"
        gleich = [s for s in st if abs(_wert(s["menge"]) - menge) < 1e-9]
        if gleich and abs(gleich[0]["preis"] - preis) > tol:
            s = gleich[0]
            out.append(f"{name}: {zahl_kurz(menge)} {einheit} je {euro_text(preis)} €, die Staffel „{s['bereich']}“ nennt "
                       f"{euro_text(s['preis'])} €")
            continue
        teurer = [s for s in st if _wert(s["menge"]) > menge and s["preis"] > preis + tol]
        if teurer:
            s = teurer[0]
            out.append(f"{name}: {zahl_kurz(menge)} {einheit} je {euro_text(preis)} €, die größere Menge „{s['bereich']}“ "
                       f"kostet je Einheit mehr ({euro_text(s['preis'])} €)")
    return out


def _prozent(w):
    return f"{w:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def zahlungstext(kopf):
    """Zahlungsbedingung aus dem Angebotskopf, z. B. 'Zahlung innerhalb 10 Tagen mit 2 % Skonto oder innerhalb
    30 Tagen netto.' Leer, wenn nichts eingetragen ist."""
    skonto, tage, ziel = _wert(kopf.get("skonto")), int(_wert(kopf.get("skonto_tage"))), int(_wert(kopf.get("zahlungsziel")))
    netto = f"innerhalb {ziel} Tagen netto" if ziel else "sofort netto"
    if skonto > 0 and tage:
        return f"Zahlung innerhalb {tage} Tagen mit {_prozent(skonto)} % Skonto oder {netto}."
    return f"Zahlung {netto}." if ziel else ""


def anschrift(kunde):
    """Anschriftzeilen eines Kunden aus dem Kundenstamm (ohne Name)."""
    if not kunde:
        return []
    zeilen = [kunde.get("strasse"), kunde.get("plz_ort")]
    if kunde.get("ansprechpartner"):
        zeilen.append(f"z. Hd. {kunde['ansprechpartner']}")
    return [z for z in zeilen if z]


def gueltig_bis(kopf, einst):
    try:
        d = datetime.date.fromisoformat(kopf.get("datum") or "")
    except ValueError:
        return None
    return d + datetime.timedelta(days=int(_wert(einst.get("gueltigkeit"))))


# ------------------------------------------------------------------ Werkstattpapier
def werkstatt(kopf, positionen, ergebnis, k, tabellen):
    """Materialliste und je Stangenmuster ein Block (WerkstattpapierFuellen).
    Ergebnis: dict(material=[{profil, werkstoff, stange, stangen, gewicht}],
                   muster=[{nummern, anzahl, stange (Schnittplanzeile), rest, ausnutzung, teile=[…]}],
                   zukaufteile=[{pos, artikel, bezeichnung, stueck, text}] (Zukaufteil-Positionen, nicht gelasert),
                   schweissplan, hinweise=rechnen.laser_hinweise)."""
    zk = [dict(pos=p.get("pos"), artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"), stueck=p.get("stueck"),
               text=zukaufteil_text(p)) for p in positionen if ist_zukaufteil(p) and _wert(p.get("stueck")) > 0]
    plan = schweissplan(positionen, tabellen, k)
    hinweise = rechnen.laser_hinweise(positionen, k)      # Laser-Hinweise der Werkstoffe (24.10.2026)
    stege = stege_hinweise(positionen)
    if not ergebnis or not ergebnis.get("stangen"):
        return dict(material=[], muster=[], zukaufteile=zk, schweissplan=plan, hinweise=hinweise, stege=stege)
    # so, wie die Maschine lädt: zugeschnittene Lieferstangen als ihre Werkstücke (rechnen.anzeige_stangen)
    paare = rechnen.anzeige_stangen(ergebnis, rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen))
    werte = {s["nr"]: w for s, w in paare}
    material = {}
    for s, w in paare:
        m = material.setdefault((rechnen.gruppe_der_stange(s), s["stange"]),
                                dict(profil=s["profil"], werkstoff=rechnen.material_text(s["werkstoff"], s.get("oberflaeche"))
                                     + (f" – {ra}" if (ra := rohrart_text(dict(profil_id=s["profil"],
                                                                                werkstoff_id=s["werkstoff"]), k, kopf))
                                        else "")
                                     + (" – Kundenmaterial" if s.get("beistellung") else "")
                                     + (" – MUSTER (eigener Lauf)" if s.get("muster") else ""),
                                     stange=s["stange"], stangen=0, gewicht=0.0))
        m["stangen"] += 1
        m["gewicht"] += _wert(w["gewicht"])
    muster = []
    profil_von = stangen_abwicklung.profil_funktion(kopf, k)
    merker = {}                 # Grundform je Position und Länge einmal für alle Stangen (Performance-Plan P7)
    for s, nummern in rechnen.stangenmuster(dict(stangen=[s for s, _ in paare])):
        w = werte[s["nr"]]
        teile = []
        for platz, t in enumerate(s["teile"], start=1):
            p = positionen[t["index"]] if 0 <= t["index"] < len(positionen) else {}
            teile.append(dict(platz=platz, pos=t["pos"], artikel=t["artikel"], bezeichnung=p.get("bezeichnung"),
                              laenge=t["laenge"], von=t["von"], bis=t["bis"], lage=t["lage"],
                              naht_text=t.get("naht_text") or "", trennung=t["trennung"],
                              kante_a=t.get("kante_a"), kante_b=t.get("kante_b"), ansicht=t.get("ansicht"),
                              drehung=t.get("drehung") or 0, drehfreigabe=t.get("drehfreigabe"), naht=t.get("naht"),
                              querschnitt=t.get("querschnitt"), material_gespart=t.get("material_gespart") or 0))
        muster.append(dict(nummern=nummern, nummern_text=nummern_text(nummern), anzahl=len(nummern), stange=s,
                           rest=w["rest"], ausnutzung=w["ausnutzung"], teile=teile,
                           gespart=rechnen.gehrung_gespart(s), abwicklung=_abwicklung(s, positionen, profil_von, merker)))
    return dict(material=list(material.values()), muster=muster, zukaufteile=zk, schweissplan=plan, hinweise=hinweise,
                stege=stege)


def stege_hinweise(positionen):
    """Positionen mit virtuellem Bauteil (Stege bzw. Ringe 2 mm an den Enden): [{pos, artikel, stueck, abtrennen,
    text}] für die Werkstattpapiere."""
    out = []
    for p in positionen:
        e = virtuell.technik_lesen(p)
        if e and _wert(p.get("stueck")) > 0:
            out.append(dict(pos=p.get("pos"), artikel=p.get("artikel"), stueck=p.get("stueck"),
                            abtrennen=bool(e.get("stege_abtrennen")), text=virtuell.hinweis(e, p.get("profil_id"))))
    return out


def _abwicklung(s, positionen, profil_von, merker=None):
    """Abwicklung der Stange für die Werkstattpapiere (Lantek-Idee L4, F4a) oder None, wenn sie nicht geht."""
    try:
        return stangen_abwicklung.stange(s, positionen, profil_von, merker)
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def schweissplan(positionen, tabellen, k=None):
    """Schweißplan je Schweißbaugruppe für die Werkstattpapiere (Verbesserung P2), ohne Preise: Struktur mit Mengen,
    Einzelteile mit Pos., Nahtgruppen, Arbeitsgänge in Reihenfolge, Vorrichtungen und Vorgabezeit je Baugruppe.
    Mit k: Mengen mit Bezug aus den aktuellen Einzelteilen (bg_mengen), wie im Preis."""
    from . import baugruppe, bg_mengen
    out = []
    for p in positionen:
        bg = baugruppe.lesen(p.get("baugruppe")) if ist_baugruppe(p) else None
        if not bg:
            continue
        km = baugruppe.knoten_map(bg)
        kname = (lambda kid: (km.get(kid) or {}).get("name") or "Unterbaugruppe" if kid else "Baugruppe")
        mengen = None
        if k is not None:                                 # Menge aus den Einzelteilen: aktueller Stand der Teile
            bg_mengen.anwenden(bg, positionen, k)
            mengen = bg_mengen.je_knoten(bg, positionen, k)
        r = baugruppe.rechnen(dict(p, baugruppe=baugruppe.speichern(bg)), tabellen, {},  # nur Zeiten
                              mengen=mengen)
        zeiten = {(x["art"], x["id"]): x for x in r["zeilen"]}
        struktur = [dict(name=k.get("name") or "Unterbaugruppe", menge=k.get("menge"),
                         unter=kname(k.get("parent") or ""), je_bg=baugruppe.faktor(bg, k["id"])) for k in bg["knoten"]]
        teile = [dict(pos=q.get("pos"), artikel=q.get("artikel"), bezeichnung=q.get("bezeichnung"),
                      knoten=kname(baugruppe.zuordnung(q)[1] or ""), je_knoten=q.get("je_knoten") or 1,
                      je_bg=q.get("je_satz"), stueck=q.get("stueck"))
                 for q in (positionen[j] for j in baugruppe.teile(positionen, bg["id"]))]
        naehte = [dict(nr=n.get("nr"), knoten=kname(n.get("knoten") or ""), verfahren=n.get("verfahren"),
                       nahtart=n.get("nahtart"), mass=n.get("mass"), laenge=n.get("laenge"), anzahl=n.get("anzahl"),
                       beidseitig=bool(n.get("beidseitig")), heftpunkte=n.get("heftpunkte"), lage=n.get("lage"),
                       zeit_min=(zeiten.get(("Naht", n.get("id"))) or {}).get("zeit_min"))
                  for n in bg["naehte"]]
        ags = [dict(name=a.get("name") or "Arbeitsgang", knoten=kname(a.get("knoten") or ""), menge=a.get("menge"),
                    zeit_min=(zeiten.get(("Arbeitsgang", a.get("id"))) or {}).get("zeit_min"),
                    ruest_min=a.get("ruest_min"), fremd=bool(a.get("fremd")),
                    vorrichtung=bool(a.get("einmal_eur")), umlage=a.get("umlage"))
               for a in bg["arbeitsgaenge"]]
        out.append(dict(pos=p.get("pos"), name=baugruppe.name(p, bg), anzahl=p.get("stueck"), stamm=bg["stamm"],
                        struktur=struktur, teile=teile, naehte=naehte, arbeitsgaenge=ags,
                        vorgabe_min=r["zeit_min"], schweiss_min=r["schweiss_min"],
                        naht_m=sum(r["naht_m"].values())))
    return out


def muster_titel(m):
    """Titel eines Stangenmusters; Stangen mit Musterteilen (eigener Lauf) sind als MUSTERTEILE gekennzeichnet."""
    return (f"Stange {m['nummern_text']}" if m["anzahl"] == 1
            else f"Stangen {m['nummern_text']}  ({m['anzahl']} Stück gleich)") + \
        ("  – MUSTERTEILE (eigener Lauf)" if (m.get("stange") or {}).get("muster") else "")
