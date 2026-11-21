"""KI-Plattform Phase 3: eine Lernhistorie über alle Lernsysteme (Master-Prompt Patrick 20.11.2026, Punkt 4).

Es gibt kein zweites Lernsystem: die Lernwerte bleiben, wo sie heute stehen, mit ihrer Freigabe und ihrem
Rückgängig (keine KI ändert Kalkulationsparameter ungeprüft):
  kennwerte_historie   freigegebene Kennwert-Vorschläge aller registrierten Quellen (Nachkalkulation Rüsten/
                       Laserzeit, Schweißen, Vorkalkulation, Kalibrierung D1/D3/E7, Zeit je Arbeitsgang, LST-Lernsystem
                       sobald es seine Quellen anmeldet) mit Datum, Faktor, Fällen, Streuung, Begründung, Programmversion,
                       alten Werten und Zurücknehmen
  gelernt              Lernzentrale (Zusatzarbeiten je Kunde, gelernte Einstellungen) mit Vergessen/Sperren
  bg_zeiten            Zeiten von Hand an Schweißbaugruppen mit Version und Status
Diese Datei liest sie zusammen (eintraege), prüft die Lerndaten auf Fehler (fehlerhafte_daten), sammelt reife
Vorschläge (offene_vorschlaege), vergleicht vor einer Freigabe alte und neue Rechnung an echten Angeboten (vergleich)
und wertet die Abweichungen der Nachkalkulation je Auftrag aus (abweichungen). Ohne Qt.

Lernmechanismus (Punkt 4, Schritte 1–7): 1. Kalkulation speichern = Soll-Stand der Nachkalkulation; 2. Ist-Daten =
Nachkalkulation, Rückmeldungen, LST; 3. Abweichung = abweichungen(); 4. Ursache = größte Kostenart und Gruppe
(Maschine, Werkstoff, Wand); 5./6. Erfahrungswert = Faktor Ist ÷ Soll (Median ohne Ausreißer, kennwerte.auswerten);
7. Vorschlag mit Vergleich alt/neu, Freigabe mit Begründung, Version, Rückgängig."""
import datetime
import json
from . import protokoll

AUSREISSER_FAKTOR = 10.0        # Ist mehr als 10-mal (oder weniger als ein Zehntel) des Solls: fast sicher ein Tippfehler
VERGLEICH_ANGEBOTE = 10         # so viele Angebote rechnet der Vergleich alt/neu


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _z(v, stellen=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(v, stellen)


# ------------------------------------------------------------------ Lernhistorie
def eintraege(db):
    """Alle Lernwerte mit Stand: [dict(quelle, titel, was, datum, version, status, art, id)] neueste zuerst.
    art: 'kennwert' (zurücknehmbar über kennwerte.zuruecknehmen), 'gelernt' (Lernzentrale), 'bg_zeit'."""
    from . import kennwerte
    out = []
    try:
        for z in kennwerte.historie(db):
            titel = (kennwerte.QUELLEN.get(z.get("quelle")) or (z.get("quelle"),))[0]
            try:
                schl = " / ".join(str(s) for s in json.loads(z.get("schluessel") or "[]"))
            except ValueError:
                schl = str(z.get("schluessel") or "")
            out.append(dict(quelle="Kennwerte", titel=titel, was=f"{schl}: Faktor {_z(z.get('faktor'), 3)} aus "
                            f"{z.get('n') or 0} Fällen – {z.get('begruendung') or ''}", datum=z.get("datum") or "",
                            version=z.get("version") or "", status="zurückgenommen" if z.get("zurueck") else "aktiv",
                            art="kennwert", id=z["id"]))
    except Exception:           # noqa: BLE001 – Tabelle fehlt (alte Datei)
        protokoll.warnung("ki_lernhistorie: abgefangen")
    try:
        from . import lernen
        for e in lernen.uebersicht(db, mit_kennwerten=False):
            out.append(dict(quelle="Lernzentrale", titel=e.get("bereich") or "", was=f"{e.get('kunde') or ''} "
                            f"{e.get('was') or ''}".strip(), datum=e.get("wann") or "", version="",
                            status=e.get("stand") or "", art="gelernt", id=None))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_lernhistorie: abgefangen")
    try:
        from . import bg_zeitlernen
        for r in bg_zeitlernen.faelle(db, alle=True):
            out.append(dict(quelle="BG-Zeiten", titel=r.get("titel") or "Baugruppe",
                            was=f"Angebot {r.get('angebot')}: von Hand {_z(r.get('hand_min'), 0)} min, automatisch "
                            f"{_z(r.get('auto_min'), 0)} min", datum=r.get("geaendert") or "",
                            version=str(r.get("version") or ""), status=r.get("status") or "", art="bg_zeit",
                            id=r.get("id")))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_lernhistorie: abgefangen")
    return sorted(out, key=lambda e: str(e["datum"]), reverse=True)


def zuruecknehmen(db, eintrag):
    """Rückgängig für einen Kennwert der Lernhistorie (die anderen Arten in ihren Fenstern). Ergebnis: Anzahl."""
    from . import kennwerte, ki_protokoll
    if eintrag.get("art") != "kennwert" or eintrag.get("status") != "aktiv":
        return 0
    n = kennwerte.zuruecknehmen(db, eintrag["id"])
    ki_protokoll.schreiben(db, "Lern-KI", "zuruecknehmen", ergebnis=f"{eintrag['titel']}: {n} Werte zurückgesetzt")
    return n


# ------------------------------------------------------------------ fehlerhafte Lerndaten
def fehlerhafte_daten(db, vorschlaege=None):
    """Verdächtige Fälle in den Lerndaten: [dict(text, quelle, angebot, grund)]. Gründe: Ist 0 oder negativ, Ist mehr
    als AUSREISSER_FAKTOR-mal bzw. weniger als ein Zehntel des Solls, derselbe Auftrag doppelt in einer Gruppe,
    Ausreißer der Freigabe-Rechnung (3 × MAD). Solche Fälle zählen in den Vorschlägen schon nicht (Ausreißer) bzw.
    sollten in der Nachkalkulation korrigiert werden."""
    from . import kennwerte
    out = []
    try:
        liste = vorschlaege if vorschlaege is not None else kennwerte.vorschlaege(db, mindest_n=1)
    except Exception:           # noqa: BLE001
        return out
    for v in liste:
        schl = " / ".join(str(s) for s in v.get("schluessel") or ())
        gesehen = {}
        for f in (v.get("faelle") or []) + (v.get("ausreisser") or []):
            soll, ist = _n(f.get("soll")), _n(f.get("ist"))
            nr = f.get("angebot")
            grund = None
            if ist is not None and ist <= 0:
                grund = "Ist-Wert 0"
            elif soll and ist and (ist / soll > AUSREISSER_FAKTOR or ist / soll < 1 / AUSREISSER_FAKTOR):
                grund = f"Ist {_z(ist / soll, 1)}-mal das Soll"
            if grund:
                out.append(dict(text=f"{v.get('titel')} ({schl}), Angebot {nr}: {grund}", quelle="Nachkalkulation",
                                angebot=nr, grund=grund))
            gesehen[nr] = gesehen.get(nr, 0) + 1
        for nr, n in gesehen.items():
            if nr and n > 1 and v.get("quelle") not in ("laserzeit_teil", "laserzeit_bereich", "laserzeit_bausteine"):
                out.append(dict(text=f"{v.get('titel')} ({schl}): Angebot {nr} zählt {n}-mal", quelle="Nachkalkulation",
                                angebot=nr, grund="doppelt"))
        for f in v.get("ausreisser") or ():
            if not any(x["angebot"] == f.get("angebot") and x["grund"] != "doppelt" for x in out):
                out.append(dict(text=f"{v.get('titel')} ({schl}), Angebot {f.get('angebot')}: Ausreißer (zählt nicht)",
                                quelle="Nachkalkulation", angebot=f.get("angebot"), grund="Ausreißer"))
    return out


# ------------------------------------------------------------------ reife Vorschläge
def offene_vorschlaege(db, mindest_n=5):
    """Vorschläge mit genug Daten aus allen Lernquellen: [dict(titel, text, quelle, faktor, n, vorschlag)]."""
    from . import lernen
    out = []
    for v in lernen.kennwerte_reif(db, mindest_n):
        schl = " / ".join(str(s) for s in v.get("schluessel") or ())
        out.append(dict(titel=v.get("titel") or v.get("quelle"), text=f"{schl}: Ist ÷ Soll = {_z(v['faktor'], 3)} aus "
                        f"{v['n']} Fällen (Streuung {_z(v.get('streuung'), 3)})", quelle="Kennwerte",
                        faktor=round(v["faktor"], 3), n=v["n"], vorschlag=v))
    for v in lernen.muster_reif(db):
        out.append(dict(titel="Handeinträge", text=str(v.get("text") or v.get("titel") or v.get("wert") or ""),
                        quelle="Muster", faktor=None, n=v.get("angebote"), vorschlag=v))
    return out


# ------------------------------------------------------------------ Vergleich alt/neu vor der Freigabe
class _Aufzeichnung:
    """Datenbank-Hülle für die anwenden-Funktionen der Kennwert-Quellen: liest wie die Datenbank, schreibt nichts,
    merkt sich die Änderungen (Tabelle, ID, Feld, neu)."""

    def __init__(self, db):
        self._db, self.aenderungen = db, []

    def aendern(self, tabelle, zeilen_id, feld, wert, *a, **k):
        self.aenderungen.append((tabelle, zeilen_id, feld, wert))
        return None

    def neu(self, *a, **k):
        raise RuntimeError("Vergleich: keine neuen Zeilen")

    def __getattr__(self, name):
        return getattr(self._db, name)


def _mit_aenderungen(zeilen, aend, tabelle):
    neu = {}
    for t, zid, feld, wert in aend:
        if t == tabelle:
            neu.setdefault(zid, {})[feld] = wert
    return [dict(z, **neu[z.get("id")]) if z.get("id") in neu else z for z in zeilen]


def grundlage_mit(db, aend):
    """(Kontext, Tabellen) der Stammdaten mit den aufgezeichneten Änderungen (nur Kopien; nichts gespeichert)."""
    from .datenbank import Datenbank
    tab = dict(db.tabellen())
    for t in {a[0] for a in aend}:
        if t in tab:
            tab[t] = _mit_aenderungen(tab[t], aend, t)

    class _Hilfe:
        def __getattr__(self, name):
            return getattr(db, name)

        def zeilen(self, tabelle, mit_uid=False):
            return _mit_aenderungen(db.zeilen(tabelle), aend, tabelle)
    return Datenbank._kontext_bauen(_Hilfe()), tab


def vergleich(db, vorschlag, angebot_ids=None):
    """Alte gegen neue Rechnung für einen Kennwert-Vorschlag, bevor ihn jemand freigibt: dict(aenderungen, angebote
    [dict(nummer, kunde, alt, neu, prozent)], text). Gerechnet werden die Prüfangebote, sonst die letzten
    beauftragten Angebote; festgeschriebene Preis-/Zeitbasis eines Angebots gilt weiter."""
    from . import kennwerte, preis_simulator, pruefangebote, rechnen
    anwenden = (kennwerte.QUELLEN.get(vorschlag.get("quelle")) or (None, None, None))[2]
    if anwenden is None or not vorschlag.get("faktor"):
        return dict(aenderungen=[], angebote=[], text="Dieser Vorschlag ändert keine Stammdaten.")
    auf = _Aufzeichnung(db)
    anwenden(auf, vorschlag["schluessel"], vorschlag["faktor"])
    if not auf.aenderungen:
        return dict(aenderungen=[], angebote=[], text="Keine Stammdaten betroffen.")
    k_neu, tab_neu = grundlage_mit(db, auf.aenderungen)
    k_alt, tab_alt = db.kontext(), db.tabellen()
    if angebot_ids is None:
        angebot_ids = pruefangebote.ids(db) or [a["id"] for a in db.angebote()
                                                if (a.get("vorgang") or "") == "Beauftragt"][:VERGLEICH_ANGEBOTE]
    out = []
    for aid in list(angebot_ids)[:VERGLEICH_ANGEBOTE]:
        a = db.angebot(aid)
        if not a or not a.get("ergebnis"):
            continue
        pos = db.positionen(aid)
        try:
            werte = []
            for akt in ((k_alt, tab_alt), (k_neu, tab_neu)):
                k, tab, e = preis_simulator.grundlage(db, a, akt)
                werte.append(rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)[1]["verkauf"])
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            continue
        alt, neu = werte
        out.append(dict(nummer=a.get("nummer"), kunde=a.get("kunde") or "", alt=round(alt, 2), neu=round(neu, 2),
                        prozent=round(100 * (neu / alt - 1), 2) if alt else None))
    geaendert = [x for x in out if x["alt"] != x["neu"]]
    text = (f"{len(auf.aenderungen)} Stammdaten-Werte würden sich ändern; von {len(out)} gerechneten Angeboten "
            f"ändern sich {len(geaendert)}" + (f", im Mittel {_z(sum(x['prozent'] or 0 for x in geaendert) / len(geaendert), 2)} %"
                                               if geaendert else "") + ".")
    return dict(aenderungen=auf.aenderungen, angebote=out, text=text)


# ------------------------------------------------------------------ Abweichungen Soll/Ist je Auftrag
def abweichungen(db):
    """Nachkalkulierte Aufträge nach größter Abweichung der erfassten Einzelkosten: [dict(nummer, kunde, soll, ist,
    prozent, groesste, datum)]."""
    from . import nachkalkulation
    try:
        fl, _ = nachkalkulation.faelle(db)
    except Exception:           # noqa: BLE001
        return []
    kunden = {a.get("nummer"): a.get("kunde") or "" for a in db.angebote()}
    out = []
    for f in fl:
        zeilen = [z for z in f["soll"].get("zeilen") or () if len(z) >= 8 and z[7]]
        soll = sum(_n(z[5]) or 0 for z in zeilen)
        ist = sum(_n(z[6]) or 0 for z in zeilen)
        if soll <= 0 or not zeilen:
            continue
        g = max(zeilen, key=lambda z: abs((_n(z[6]) or 0) - (_n(z[5]) or 0)))
        d = (_n(g[6]) or 0) - (_n(g[5]) or 0)
        out.append(dict(nummer=f["nummer"], kunde=kunden.get(f["nummer"], ""), soll=round(soll, 2), ist=round(ist, 2),
                        prozent=round(100 * (ist / soll - 1), 1),
                        groesste=f"{g[0]} {'+' if d > 0 else ''}{_z(d)} €", datum=f.get("datum") or ""))
    return sorted(out, key=lambda x: -abs(x["prozent"]))


def lernstand(db):
    """Kennzahlen für das Dashboard: dict(kennwerte_aktiv, kennwerte_zurueck, gelernt, bg_zeiten, nachkalkuliert,
    reif, verdaechtig, letzte, datenqualitaet_pct)."""
    e = eintraege(db)
    try:
        from . import nachkalkulation
        fl, ohne = nachkalkulation.faelle(db)
    except Exception:           # noqa: BLE001
        fl, ohne = [], 0
    try:
        from . import kennwerte
        v = kennwerte.vorschlaege(db, mindest_n=1)
    except Exception:           # noqa: BLE001
        v = []
    fehler = fehlerhafte_daten(db, v)
    faelle = sum(len(x.get("faelle") or ()) + len(x.get("ausreisser") or ()) for x in v)
    return dict(kennwerte_aktiv=sum(1 for x in e if x["art"] == "kennwert" and x["status"] == "aktiv"),
                kennwerte_zurueck=sum(1 for x in e if x["art"] == "kennwert" and x["status"] != "aktiv"),
                gelernt=sum(1 for x in e if x["art"] == "gelernt"),
                bg_zeiten=sum(1 for x in e if x["art"] == "bg_zeit"), nachkalkuliert=len(fl), ohne_soll=ohne,
                reif=sum(1 for x in v if x.get("status") == "ok"), faelle=faelle, verdaechtig=len(fehler),
                datenqualitaet_pct=round(100 * (1 - len(fehler) / faelle)) if faelle else None,
                letzte=e[0]["datum"] if e else "",
                stand=datetime.datetime.now().isoformat(timespec="seconds"))
