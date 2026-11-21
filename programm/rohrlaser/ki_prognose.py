"""KI-Plattform Phase 5: Prognosen, Mengenstaffel-Vorschlag, Anfragen-Priorität, Prozessverbesserungen (Master-Prompt
Patrick 20.11.2026, Punkte 5 und 9). Alles deterministisch aus vorhandenen Rechenwegen; nichts wird gespeichert.

mengenstaffel(ctx, mengen)        Stückpreise je Position für Mengen wie 10/25/50/100 über staffeln.stufe_rechnen
                                  (jede Menge ein eigener Rechenlauf mit Rüsten, Verschnitt, Mindestpreis); nur
                                  Vorschlag, übernommen wird er im Reiter Staffeln
fertigungszeit(ctx)               Laserzeit geplant und als Bandbreite aus der Nachkalkulation (Kalibrierung D2)
anfragen_prioritaet(db)           offene Kundenanfragen nach Punkten: Angebotsfrist, Alter, Kunde mit Aufträgen,
                                  Anhänge vorhanden
prozessverbesserungen(db)         wiederkehrende Muster: oft von Hand überschriebene Zeiten, häufige Absagegründe,
                                  größte Kostentreiber, Abweichungen der Nachkalkulation
Ohne Qt."""
import datetime
import re
from . import protokoll

MENGEN = (10, 25, 50, 100)
POSITIONEN_MAX = 8


def _z(v, stellen=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(v, stellen)


def mengen_aus_text(text):
    """'Mengenstaffel für 10, 25, 50 und 100 Stück' -> (10, 25, 50, 100); keine Zahlen: MENGEN."""
    werte = []
    for m in re.findall(r"(?<![\d.,])(\d{1,6})(?![\d.,]*\s*(?:mm|%|€|kg|m\b))", str(text or "")):
        w = int(m)
        if 0 < w <= 100000 and w not in werte:
            werte.append(w)
    return tuple(sorted(werte)) or MENGEN


def mengenstaffel(ctx, mengen=MENGEN):
    """[dict(pos, bezeichnung, mengen [dict(menge, preis_einheit, preis_gesamt, stangen)])] je aktiver Position."""
    from . import staffeln
    kopf, pos = ctx.kopf, ctx.positionen
    if not kopf or not pos:
        return []
    k, tab, e = ctx.grundlage
    out = []
    for p in pos:
        if not p.get("pos") or not staffeln.position_aktiv(p) or len(out) >= POSITIONEN_MAX:
            continue
        zeile = dict(pos=str(p.get("pos")), bezeichnung=p.get("bezeichnung") or p.get("artikel") or "", mengen=[])
        for m in mengen:
            try:
                x = staffeln.stufe_rechnen(kopf, pos, str(p.get("pos")), m, k, tab, e)
            except (ValueError, KeyError, TypeError, ZeroDivisionError):
                continue
            zeile["mengen"].append(dict(menge=m, preis_einheit=x.get("preis_einheit"), preis_gesamt=x.get("preis_gesamt"),
                                        stangen=x.get("stangen"), hinweis=x.get("hinweis")))
        if zeile["mengen"]:
            out.append(zeile)
    return out


def mengenstaffel_text(liste):
    zeilen = []
    for z in liste:
        teile = "; ".join(f"{m['menge']} Stk. {_z(m['preis_einheit'])} €/Stk." for m in z["mengen"]
                          if m.get("preis_einheit") is not None)
        zeilen.append(f"Pos. {z['pos']} {z['bezeichnung']}: {teile}")
    return "\n".join(zeilen)


def fertigungszeit(ctx):
    """dict(geplant_h, unten_h, oben_h, n, maschine) oder None."""
    from . import kalibrierung
    zeilen, pos = ctx.zeilen, ctx.positionen
    if not zeilen:
        return None
    s = sum((z.get("laser_netto") or 0) * (p.get("stueck") or 0) for p, z in zip(pos, zeilen) if z) / 3600
    m = (ctx.kopf or {}).get("maschine")
    b = kalibrierung.laserzeit_band(ctx.db, m) if m else None
    return dict(geplant_h=round(s, 2), unten_h=round(s * b["unten"], 2) if b else None,
                oben_h=round(s * b["oben"], 2) if b else None, n=b["n"] if b else 0, maschine=m)


# ------------------------------------------------------------------ Anfragen
def anfragen_prioritaet(db, heute=None, akten=None):
    """Offene Anfragen (Status neu / in Bearbeitung) nach Punkten, höchste zuerst: [dict(nr, kunde, absender,
    betreff, punkte, grund, status)]. Punkte: Frist in ≤ 2 Tagen 50, ≤ 5 Tagen 30; wartet seit > 2 Tagen 20;
    bekannter Kunde mit Aufträgen 15; Anhänge (Zeichnungen/STEP) 10; Priorität „hoch“ von Hand 40."""
    from . import anfrage_art, anfragen_akten as ak
    heute = heute or datetime.date.today()
    if akten is None:
        try:
            akten = ak.ablage(db).alle()
        except Exception:       # noqa: BLE001 – keine Anfragen-Ablage
            return []
    try:
        beauftragt = {str(a.get("kundennr")) for a in db.angebote() if (a.get("vorgang") or "") == "Beauftragt"
                      and a.get("kundennr")}
    except Exception:           # noqa: BLE001
        beauftragt = set()
    out = []
    for a in akten:
        try:
            if a.status not in (ak.NEU, ak.BEARBEITUNG) or a.aussortiert:
                continue
            punkte, gruende = 0, []
            frist = _frist(a, anfrage_art)
            if frist:
                tage = (frist - heute).days
                if tage <= 2:
                    punkte += 50
                    gruende.append(f"Angebotsfrist {frist.strftime('%d.%m.')}")
                elif tage <= 5:
                    punkte += 30
                    gruende.append(f"Frist {frist.strftime('%d.%m.')}")
            e = a.eingang
            if e and (datetime.datetime.now() - e).days > 2 and a.status == ak.NEU:
                punkte += 20
                gruende.append(f"wartet seit {(datetime.datetime.now() - e).days} Tagen")
            nr = str((a.zuordnung or {}).get("kundennr") or "") if isinstance(a.zuordnung, dict) else ""
            if nr and nr in beauftragt:
                punkte += 15
                gruende.append("Kunde mit Aufträgen")
            if a.dateien():
                punkte += 10
                gruende.append("mit Unterlagen")
            if str(a.prioritaet or "").lower() in ("hoch", "eilig", "1"):
                punkte += 40
                gruende.append("Priorität hoch")
            out.append(dict(nr=a.kopf.get("nr") or getattr(a, "nr", ""), kunde=a.kunde or "", absender=a.absender or "",
                            betreff=a.betreff or "", punkte=punkte, grund=", ".join(gruende) or "ohne Besonderheit",
                            status=a.status))
        except Exception:       # noqa: BLE001 – eine kaputte Akte stoppt die Liste nicht
            protokoll.warnung("ki_prognose: abgefangen")
            continue
    return sorted(out, key=lambda x: -x["punkte"])


def _frist(akte, anfrage_art):
    text = " ".join(str(akte.kopf.get(n) or "") for n in ("betreff", "text", "kurztext"))
    try:
        werte = anfrage_art.technische_werte(text) if hasattr(anfrage_art, "technische_werte") else []
    except Exception:           # noqa: BLE001
        werte = []
    for w in werte or ():
        if w.get("feld") == "angebotsfrist":
            d = _datum(w.get("wert"))
            if d:
                return d
    m = re.search(r"(?:angebot|frist|abgabe)[^\d]{0,30}(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", text, re.I)
    if m:
        return _datum(m.group(0)[m.start(1) - m.start(0):])
    return None


def _datum(t):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", str(t or ""))
    if not m:
        return None
    j = int(m.group(3)) if m.group(3) else datetime.date.today().year
    j = j + 2000 if j < 100 else j
    try:
        return datetime.date(j, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


# ------------------------------------------------------------------ Prozessverbesserungen
def prozessverbesserungen(db, heute=None):
    """[dict(text, quelle)] aus den vorhandenen Auswertungen (Einsichten I11/I12, Kostentreiber, Nachkalkulation)."""
    out = []
    try:
        from . import einsichten
        for v in einsichten.zeit_vorschlaege(db) or ():
            out.append(dict(text=str(v.get("text") or v.get("titel") or ""), quelle="Handeinträge (I11)"))
        for v in einsichten.verlustmuster(db, heute) or ():
            out.append(dict(text=str(v.get("text") or v), quelle="Verlustmuster (I12)"))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_prognose: abgefangen")
    try:
        from . import kostentreiber
        k = kostentreiber.auswertung(db, heute)
        if k.get("arten"):
            z = k["arten"][0]
            anteil = z["eur"] / k["summe_eur"] if k.get("summe_eur") else 0
            out.append(dict(text=f"Größter Kostentreiber: {z['name']} mit {_z(z['eur'])} € "
                            f"({_z(100 * anteil, 0)} % der Bearbeitungskosten) in {z['auftraege']} Aufträgen.",
                            quelle="Kostentreiber"))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_prognose: abgefangen")
    try:
        from . import ki_lernhistorie
        ab = ki_lernhistorie.abweichungen(db)
        teurer = [a for a in ab if a["prozent"] > 10]
        if len(teurer) >= 3:
            out.append(dict(text=f"{len(teurer)} von {len(ab)} nachkalkulierten Aufträgen waren mehr als 10 % teurer "
                            "als geplant – Lernvorschläge in der Lernzentrale prüfen.", quelle="Nachkalkulation"))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_prognose: abgefangen")
    return [x for x in out if x["text"]]
