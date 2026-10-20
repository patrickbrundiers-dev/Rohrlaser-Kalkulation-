"""Inhalte der Ausgaben: Angebot, Werkstattpapier (Schnittpläne), Kalkulation.

Die Funktionen liefern nur Daten (Zeilen und Summen); pdf.py setzt sie als PDF.
"""
import datetime
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from . import fracht_angebot, rechnen, zukauf

ABLAGE = "Angebote"     # Ordner neben dem Programm, wenn kein Ablageordner eingestellt ist


# ------------------------------------------------------------------ Hilfen
def kaufm_runden(x, stellen=2):
    """Kaufmännisch runden (halbe Einheit von null weg)."""
    if x is None:
        return None
    q = Decimal(1).scaleb(-stellen)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


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


def ablageordner(einstellung, programmordner):
    """Ablage: eingestellter Ordner, sonst 'Angebote' neben dem Programm. Wird angelegt."""
    ordner = Path(einstellung) if einstellung else Path(programmordner) / ABLAGE
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
    """'Rundrohr Ø 42,4 x 2', 'Quadratrohr 40 x 40 x 3', 'Rechteckrohr 60 x 40 x 3', sonst die Profil-ID."""
    z = k.profile.get(pid)
    if not z:
        return str(pid or "")
    a, b, wand = (zahl_kurz(z.get(n), dezimal) for n in ("a", "b", "wand"))
    return {"Rundrohr": f"Rundrohr Ø {a} x {wand}", "Quadratrohr": f"Quadratrohr {a} x {a} x {wand}",
            "Rechteckrohr": f"Rechteckrohr {a} x {b} x {wand}", "U-Profil": f"U-Profil {a} x {b} x {wand}",
            "C-Profil": f"C-Profil {a} x {b} x {wand}", "L-Profil": f"L-Profil {a} x {b} x {wand}",
            "Flachstahl": f"Flachstahl {a} x {wand}"}.get(z.get("form"), str(pid))


def angebotstext(p, k, dezimal=",", zusatz=()):
    """Bezeichnung einer Position im Angebot, z. B. 'Rechteckrohr 80 x 40 x 5, L = 1500 mm, inkl. Material
    S235 EN10219, Zusatzarbeiten: Gewinde 4xM6, Gravur, feuerverzinkt'. zusatz: Zusatzarbeiten der Position
    aus der Kalkulation (Text im Angebot aus den Stammdaten, dazu der Text der Position, z. B. RAL 7016)."""
    laenge = p.get("laenge")
    t = profiltext(p.get("profil_id"), k, dezimal)
    t += f", L = {kaufm_runden(laenge, 0):.0f} mm" if isinstance(laenge, (int, float)) else ", L =  mm"
    w = k.werkstoffe.get(p.get("werkstoff_id"))
    t += ", inkl. Material " + ((w or {}).get("angebotstext") or str(p.get("werkstoff_id") or ""))
    ob = rechnen.oberflaeche_von(p)
    if ob:
        t += ", " + ((k.oberflaechen.get(ob) or {}).get("angebotstext") or ob)
    zus = []
    if p.get("gewinde"):
        zus.append(f"Gewinde {p['gewinde']}")
    if _wert(p.get("gravur")) > 0:
        zus.append("Gravur")
    for e in zusatz or ():
        t_e = e["angebotstext"] + (f" {e['text']}" if e.get("text") else "")
        if t_e not in zus:
            zus.append(t_e)
    if zus:
        t += ", Zusatzarbeiten: " + ", ".join(zus)
    zk = []                 # Zukaufteile mit 'Im Angebotstext nennen': Menge je Teil und Bezeichnung
    for e in zukauf.eintraege(p):
        st = e.get("stand") or {}
        name = st.get("bezeichnung") or st.get("artikelnr")
        if name and st.get("angebotstext") == "ja":
            m = _wert(e.get("menge"))
            menge = f"{kaufm_runden(m, 3):g}".replace(".", dezimal)
            zk.append(f"{menge} {zukauf.EINHEIT_KURZ.get(st.get('einheit'), 'St')} {name}" if m else name)
    if zk:
        t += ", inkl. Zukaufteile: " + ", ".join(zk)
    return t


def angebot(kopf, positionen, kalk_zeilen, k, einst, staffelpreise=(), dezimal=","):
    """Inhalt des Angebots (AngebotFuellen). Ergebnis: dict mit
    zeilen [{art: teil|satz|satzteil, pos, artikel, text, menge, preis, gesamt}], netto, mwst, brutto,
    mwst_satz, staffeln [{art, pos, text, menge, bereich ('ab 10' bzw. '10–49'), preis, gesamt}] (Stufen mit FEHLER
    fehlen), hinweise (Positionen mit Hinweis)."""
    def preis(i):
        z = kalk_zeilen[i]
        return round(_wert(z["preis_teil"]) if z else 0, 2)

    def _zus(i):
        return (kalk_zeilen[i] or {}).get("zusatzarbeiten") or ()

    def je(p):
        n = _wert(p.get("je_satz"))
        return n if n >= 1 else 1

    zeilen, erledigt = [], set()
    for i, p in enumerate(positionen):
        if p.get("profil_id") in (None, ""):
            continue
        satz = _satz(p.get("satz"))
        if not satz:
            pr, menge = preis(i), _wert(p.get("stueck"))
            zeilen.append(dict(art="teil", pos=p.get("pos"), artikel=p.get("artikel"), text=angebotstext(p, k, dezimal, _zus(i)),
                               menge=p.get("stueck"), preis=pr, gesamt=round(pr * menge, 2)))
        elif satz not in erledigt:
            erledigt.add(satz)
            teile = [(j, q) for j, q in enumerate(positionen) if _satz(q.get("satz")) == satz]
            n = max((_wert(q.get("stueck")) / je(q) for _, q in teile), default=0)
            saetze = max(1, int(n + 0.5))
            satzpreis = round(sum(preis(j) * je(q) for j, q in teile), 2)
            zeilen.append(dict(art="satz", pos=None, artikel=None, text=f"Satz {satz}", menge=saetze,
                               preis=satzpreis, gesamt=round(satzpreis * saetze, 2)))
            for j, q in teile:
                zeilen.append(dict(art="satzteil", pos=q.get("pos"), artikel=q.get("artikel"),
                                   text=f"   {kaufm_runden(je(q), 0):.0f} x {angebotstext(q, k, dezimal, _zus(j))}",
                                   menge=None, preis=None, gesamt=None))
    hinweise = sum(1 for i, p in enumerate(positionen)
                   if p.get("profil_id") not in (None, "") and kalk_zeilen[i] and kalk_zeilen[i]["hinweis"])
    netto = sum(z["gesamt"] for z in zeilen if z["gesamt"] is not None)
    satz_mwst = _wert(einst.get("mwst"))
    mwst = kaufm_runden(netto * satz_mwst, 2)
    staffeln = []
    for z in staffelpreise or ():
        if z.get("preis_einheit") is None:      # Stufe mit FEHLER (z. B. Materialpreis fehlt): nicht ins Angebot
            continue
        bis = z.get("bis")
        if not isinstance(bis, (int, float)):
            bereich = f"ab {z['menge']:.0f}"
        else:
            bereich = f"{z['menge']:.0f}–{bis:.0f}" if bis > z["menge"] else f"{z['menge']:.0f}"
        einmalig = ((z.get("preis") or {}).get("einmalig")) or 0
        zus = f", zzgl. einmalige Rüstkosten {f'{einmalig:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')} €" \
            if einmalig else ""
        if z.get("einheit") == "Satz":
            bez = z.get("bezeichnung") or ""
            staffeln.append(dict(art="satz", pos=None, text=f"Satz {z['schluessel']}" + (f" ({bez})" if bez else "") + zus,
                                 menge=z["menge"], bereich=bereich, preis=z["preis_einheit"], gesamt=z["preis_gesamt"]))
        else:
            staffeln.append(dict(art="teil", pos=z["schluessel"], text=(z.get("bezeichnung") or "") + zus,
                                 menge=z["menge"], bereich=bereich, preis=z["preis_einheit"],
                                 gesamt=z["preis_gesamt"]))
    return dict(zeilen=zeilen, netto=netto, mwst=mwst, brutto=netto + mwst, mwst_satz=satz_mwst, staffeln=staffeln,
                hinweise=hinweise, zahlung=zahlungstext(kopf), fracht=fracht_angebot.angebotstext(kopf), anschrift=[])


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
                   muster=[{nummern, anzahl, stange (Schnittplanzeile), rest, ausnutzung, teile=[…]}])."""
    if not ergebnis or not ergebnis.get("stangen"):
        return dict(material=[], muster=[])
    sw = rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)
    werte = {s["nr"]: w for s, w in zip(ergebnis["stangen"], sw)}
    material = {}
    for s in ergebnis["stangen"]:
        m = material.setdefault(rechnen.gruppe_der_stange(s),
                                dict(profil=s["profil"], werkstoff=rechnen.material_text(s["werkstoff"], s.get("oberflaeche")),
                                     stange=s["stange"], stangen=0, gewicht=0.0))
        m["stangen"] += 1
        m["gewicht"] += _wert(werte[s["nr"]]["gewicht"])
    muster = []
    for s, nummern in rechnen.stangenmuster(ergebnis):
        w = werte[s["nr"]]
        teile = []
        for platz, t in enumerate(s["teile"], start=1):
            p = positionen[t["index"]] if 0 <= t["index"] < len(positionen) else {}
            teile.append(dict(platz=platz, pos=t["pos"], artikel=t["artikel"], bezeichnung=p.get("bezeichnung"),
                              laenge=t["laenge"], von=t["von"], bis=t["bis"], lage=t["lage"], trennung=t["trennung"]))
        muster.append(dict(nummern=nummern, nummern_text=nummern_text(nummern), anzahl=len(nummern), stange=s,
                           rest=w["rest"], ausnutzung=w["ausnutzung"], teile=teile))
    return dict(material=list(material.values()), muster=muster)


def muster_titel(m):
    return (f"Stange {m['nummern_text']}" if m["anzahl"] == 1
            else f"Stangen {m['nummern_text']}  ({m['anzahl']} Stück gleich)")
