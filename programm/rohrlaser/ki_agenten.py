"""KI-Plattform Phase 2 und 4: zehn Fach-Agenten über den vorhandenen Prüfungen und Lernsystemen (Master-Prompt
Patrick 20.11.2026, Punkte 3 und 7).

Ein Agent rechnet nichts Kaufmännisches neu und erfindet keine Zahl: er ruft die deterministischen Module des Programms
auf (Kalkulation, Angebots-Check, Plausibilität, Material-, STEP- und Preisprüfungen, Kennwerte, Kalibrierung,
BG-Zeiten, Nachkalkulation, Anfragen) und gibt ihre Ergebnisse als einheitliche Befunde zurück. Jeder Befund nennt
seine Quelle und den Datenstand. Nichts wird geändert (ki_qualitaet prüft das mit einem Fingerabdruck der Tabellen).

Befund = dict(agent, art, text, begruendung, ziel, quelle, stand, zahlen, aktion, schluessel)
  art     FEHLER (blockiert bzw. sicher falsch), WARNUNG, HINWEIS, INFO (Kennzahl), VORSCHLAG (mit Knopf im Programm)
  ziel    wie angebot_check: pos:<Zeile>, kopf:<Feld>, optimieren, staffeln, preise, kalkulation, … (Hinspringen)
  zahlen  {Name: Wert} – die Zahlen im Text, für den Faktencheck der Modellantwort
  aktion  vorhandene Aktion des Angebots-Checks (optimieren, staffeln_rechnen, preise …), nur per Klick

Kontext: ein Angebot aus der Datenbank (rechnet es wie preis_simulator/pruefangebote mit festgeschriebener Basis) oder
das geöffnete Angebotsfenster (nimmt dessen Kalkulation und Angebots-Check, rechnet nichts doppelt). Ohne Angebot
beantworten die Agenten Fragen über alle Daten (uebersicht). Ohne Qt."""
import datetime
import statistics
from . import protokoll

FEHLER, WARNUNG, HINWEIS, INFO, VORSCHLAG = "FEHLER", "WARNUNG", "HINWEIS", "INFO", "VORSCHLAG"
ARTEN = (FEHLER, WARNUNG, VORSCHLAG, HINWEIS, INFO)
RANG = {a: i for i, a in enumerate(ARTEN)}
AUSNUTZUNG_MIN = 0.75       # Stangengruppe darunter: Hinweis auf Verschnitt
GEWINN_MIN = 0.05           # Gewinn unter 5 % des Verkaufspreises: Warnung
KONTUR_JE_M = 40            # mehr Einstiche je Meter Teil: ungewöhnliche Geometrie
PREISSPRUNG_PCT = 10        # Materialpreis in 3 Monaten mehr als ±10 %


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _z(v, stellen=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(v, stellen)


def befund(agent, art, text, ziel=None, quelle="", begruendung="", zahlen=None, aktion=None, schluessel=None,
           stand=""):
    return dict(agent=agent, art=art, text=text, ziel=ziel, quelle=quelle, begruendung=begruendung,
                zahlen=dict(zahlen or {}), aktion=aktion, schluessel=schluessel, stand=stand)


# ------------------------------------------------------------------ Kontext
class Kontext:
    """Daten eines Angebots für alle Agenten, jeweils nur einmal geholt bzw. gerechnet."""

    def __init__(self, db, angebot_id=None, seite=None, heute=None):
        self.db, self.seite, self.heute = db, seite, heute or datetime.date.today()
        self.angebot_id = angebot_id if angebot_id is not None else getattr(seite, "id", None)
        self._m = {}
        self.fehler = []            # (Quelle, Text) nicht verfügbarer Prüfungen

    def _merk(self, name, fn):
        if name not in self._m:
            try:
                self._m[name] = fn()
            except Exception as e:      # noqa: BLE001 – eine Quelle fehlt: die anderen laufen weiter
                self.fehler.append((name, f"{type(e).__name__}: {e}"[:200]))
                self._m[name] = None
        return self._m[name]

    @property
    def kopf(self):
        if self.seite is not None and getattr(self.seite, "kopf", None):
            return self.seite.kopf
        return self._merk("kopf", lambda: self.db.angebot(self.angebot_id) if self.angebot_id else None)

    @property
    def positionen(self):
        if self.seite is not None and getattr(self.seite, "positionen", None) is not None:
            return list(self.seite.positionen)
        return self._merk("positionen", lambda: self.db.positionen(self.angebot_id) if self.angebot_id else []) or []

    @property
    def ergebnis(self):
        if self.seite is not None and getattr(self.seite, "ergebnis", None) is not None:
            return self.seite.ergebnis
        return (self.kopf or {}).get("ergebnis")

    def _grundlage(self):
        if self.seite is not None and getattr(self.seite, "k", None) is not None:
            return self.seite.k, self.seite.tabellen if hasattr(self.seite, "tabellen") else self.db.tabellen(), \
                getattr(self.seite, "einst", None) or self.db.einstellungen()
        from . import preis_simulator
        return preis_simulator.grundlage(self.db, self.kopf)

    @property
    def grundlage(self):
        return self._merk("grundlage", self._grundlage)

    def _rechnen(self):
        if not self.kopf or not self.ergebnis or not self.positionen:
            return None
        from . import dauermerker, rechnen
        k, tab, e = self.grundlage
        with dauermerker.ohne():
            r = rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, k, tab, e)
        return r[0], r[1]

    @property
    def kalkulation(self):
        """(zeilen, summen) oder None (nicht optimiert)."""
        return self._merk("kalkulation", self._rechnen)

    @property
    def zeilen(self):
        return (self.kalkulation or ([], {}))[0]

    @property
    def summen(self):
        return (self.kalkulation or ([], {}))[1]

    @property
    def check(self):
        """Punkte des Angebots-Checks aus dem geöffneten Fenster (dort laufend gerechnet), sonst leer."""
        return list(getattr(self.seite, "_punkte", None) or ()) if self.seite is not None else []

    @property
    def stand(self):
        return str((self.kopf or {}).get("geaendert") or (self.kopf or {}).get("datum") or "")

    def merk(self, name, fn):
        return self._merk(name, fn)


# ------------------------------------------------------------------ Agenten
class Agent:
    name = ""
    titel = ""
    aufgabe = ""
    woerter = ()            # Stichwörter für den Orchestrator (klein, ohne Umlaute-Sonderfälle)
    quellen = ()            # genutzte Programm-Module (Anzeige im Dashboard)

    def pruefen(self, ctx):
        """Befunde zu einem Angebot."""
        return []

    def uebersicht(self, db, heute=None):
        """Befunde über alle Daten (ohne Angebot)."""
        return []

    def b(self, art, text, **w):
        return befund(self.titel, art, text, **w)


def _pos_nr(p, i):
    return str(p.get("pos") or i + 1)


class KalkulationsKI(Agent):
    name, titel = "kalkulation", "Kalkulations-KI"
    aufgabe = "Kostenstruktur, fehlende Positionen, unplausible Preise, Gewinn und Ertrag je Laserstunde"
    woerter = ("kalkulation", "teuer", "kosten", "preis", "gewinn", "marge", "deckungsbeitrag", "zuschlag",
               "gemeinkosten", "verkaufspreis", "fehlt", "fehlen", "position", "billig", "günstig", "guenstig")
    quellen = ("rechnen.kalkulation", "plausibel", "angebot_check")

    def pruefen(self, ctx):
        from . import plausibel, rechnen
        out = []
        if not ctx.kopf:
            return out
        if not ctx.ergebnis:
            out.append(self.b(WARNUNG, "Das Angebot ist noch nicht optimiert: ohne Schnittplan gibt es keine Kalkulation.",
                              ziel="optimieren", aktion="optimieren", quelle="Schnittplan"))
            return out
        s, zeilen, pos = ctx.summen, ctx.zeilen, ctx.positionen
        if not s:
            return out
        q = "Kalkulation (rechnen.kalkulation)"
        selbst, verkauf, gewinn = _n(s.get("selbst")), _n(s.get("verkauf")), _n(s.get("gewinn"))
        if selbst > 0:
            teile = sorted(((t, _n(s.get(schl))) for t, schl, fett in rechnen.KOSTENARTEN if not fett
                            and _n(s.get(schl)) > 0), key=lambda x: -x[1])[:3]
            if teile:
                txt = ", ".join(f"{t} {_z(w)} € ({_z(100 * w / selbst, 0)} %)" for t, w in teile)
                out.append(self.b(INFO, f"Größte Kostenarten: {txt} von {_z(selbst)} € Selbstkosten.", quelle=q,
                                  ziel="kalkulation", zahlen={t: round(w, 2) for t, w in teile} | {"selbst": round(selbst, 2)}))
        if verkauf > 0:
            anteil = gewinn / verkauf
            out.append(self.b(INFO, f"Verkaufspreis {_z(verkauf)} €, Gewinn {_z(gewinn)} € ({_z(100 * anteil, 1)} %).",
                              quelle=q, zahlen=dict(verkauf=round(verkauf, 2), gewinn=round(gewinn, 2))))
            if anteil < GEWINN_MIN:
                out.append(self.b(WARNUNG, f"Gewinn nur {_z(100 * anteil, 1)} % des Verkaufspreises.", ziel="kopf:gewinn",
                                  quelle=q, begruendung=f"Grenze {_z(100 * GEWINN_MIN, 0)} %",
                                  zahlen=dict(gewinn_pct=round(100 * anteil, 1))))
        h, ertrag = plausibel.ertrag_laser(zeilen, s)
        if h > 0:
            out.append(self.b(INFO, f"Ertrag je Laserstunde {_z(ertrag / h)} € ({_z(h, 2)} h Laserzeit).",
                              quelle="plausibel.ertrag_laser", zahlen=dict(ertrag_h=round(ertrag / h, 2),
                                                                         laser_h=round(h, 2))))
        try:
            vergleich = plausibel.vergleich_aus(ctx.db.versand_verlaeufe(ctx.angebot_id))
        except Exception:       # noqa: BLE001
            vergleich = {}
        k = ctx.grundlage[0]
        for art, text, zeile in plausibel.punkte(pos, zeilen, s, k, vergleich):
            out.append(self.b(art, text, ziel=f"pos:{zeile}" if zeile is not None else "kalkulation",
                              quelle="Preis-Plausibilität (plausibel)"))
        for i, (p, z) in enumerate(zip(pos, zeilen)):
            if not z or p.get("muster") == "ja":
                continue
            if _n(p.get("stueck")) > 0 and _n(z.get("preis_teil")) <= 0 and p.get("profil_id"):
                out.append(self.b(FEHLER, f"Pos. {_pos_nr(p, i)} hat keinen Preis.", ziel=f"pos:{i}", quelle=q))
            if p.get("profil_id") and _n(p.get("laenge")) > 0 and not _n(p.get("schneidweg")) and \
                    not _n(z.get("laser_netto")):
                out.append(self.b(WARNUNG, f"Pos. {_pos_nr(p, i)}: kein Schneidweg und keine Laserzeit – fehlt die "
                                  "Bearbeitung?", ziel=f"pos:{i}", quelle=q))
            if _n(p.get("gewinde")) > 0 and _n(z.get("gewinde_teil")) <= 0:
                out.append(self.b(WARNUNG, f"Pos. {_pos_nr(p, i)}: {int(_n(p.get('gewinde')))} Gewinde ohne Preis.",
                                  ziel=f"pos:{i}", quelle=q))
        return out

    def uebersicht(self, db, heute=None):
        from . import kostentreiber
        a = kostentreiber.auswertung(db, heute)
        out = []
        for z in (a.get("arten") or [])[:5]:
            out.append(self.b(INFO, f"Kostentreiber {z['name']}: {_z(z['eur'])} € in {z['auftraege']} Aufträgen.",
                              quelle="Kostentreiber (kostentreiber)", zahlen=dict(eur=round(z["eur"], 2))))
        return out


class RohrlaserKI(Agent):
    name, titel = "rohrlaser", "Rohrlaser-KI"
    aufgabe = "Laserzeit, Schneidwege, Konturen, ungewöhnliche Geometrien, Schneiddaten-Sicherheit, Zeitprognose"
    woerter = ("schneid", "laser", "zeit", "kontur", "geometrie", "step", "dxf", "lst", "einstich", "machbar",
               "fertigbar", "risiko", "schneidzeit", "laserzeit", "prognose")
    quellen = ("rechnen (Laserzeit)", "kalibrierung.laserzeit_band", "Schneiddaten")

    def pruefen(self, ctx):
        from . import kalibrierung
        out, pos, zeilen = [], ctx.positionen, ctx.zeilen
        if not zeilen:
            return out
        laser = [(i, p, z, _n(z.get("laser_netto")) * _n(p.get("stueck"))) for i, (p, z) in enumerate(zip(pos, zeilen))
                 if z]
        gesamt = sum(x[3] for x in laser)
        if gesamt > 0:
            i, p, z, s = max(laser, key=lambda x: x[3])
            out.append(self.b(INFO, f"Laserzeit gesamt {_z(gesamt / 60, 1)} min; Pos. {_pos_nr(p, i)} braucht "
                              f"{_z(100 * s / gesamt, 0)} % davon.", ziel=f"pos:{i}", quelle="Laserzeit (rechnen)",
                              zahlen=dict(laser_min=round(gesamt / 60, 1), anteil_pct=round(100 * s / gesamt))))
        for i, p, z, _ in laser:
            m = _n(p.get("laenge")) / 1000
            e = _n(z.get("einstiche_teil") or p.get("einstiche"))
            if m > 0 and e / m > KONTUR_JE_M:
                out.append(self.b(HINWEIS, f"Pos. {_pos_nr(p, i)}: {int(e)} Einstiche auf {_z(m, 2)} m – ungewöhnlich "
                                  "viele Konturen, Bearbeitung und Wärmeverzug prüfen.", ziel=f"pos:{i}",
                                  quelle="Geometrie der Position", zahlen=dict(einstiche=int(e))))
            if str(z.get("sd_sicherheit") or "") == "niedrig":
                out.append(self.b(HINWEIS, f"Pos. {_pos_nr(p, i)}: Schneiddaten nur {z.get('sd_herkunft') or 'geschätzt'}"
                                  " – Laserzeit unsicher.", ziel=f"pos:{i}", quelle="Schneiddaten"))
        masch = (ctx.kopf or {}).get("maschine")
        band = ctx.merk("band", lambda: kalibrierung.laserzeit_band(ctx.db, masch)) if masch else None
        if band and gesamt > 0:
            unten, oben = gesamt * band["unten"] / 3600, gesamt * band["oben"] / 3600
            out.append(self.b(INFO, f"Prognose aus {band['n']} nachkalkulierten Aufträgen auf {masch}: Laserzeit "
                              f"voraussichtlich {_z(unten, 2)}–{_z(oben, 2)} h (geplant {_z(gesamt / 3600, 2)} h).",
                              quelle="Kalibrierung D2 (Nachkalkulation)",
                              zahlen=dict(unten_h=round(unten, 2), oben_h=round(oben, 2))))
        return out


class MaterialKI(Agent):
    name, titel = "material", "Material-KI"
    aufgabe = "Schnittplan, Ausnutzung, Verschnitt, Materialbedarf, STEP-Gewicht, alte Materialpreise"
    woerter = ("material", "verschnitt", "stange", "ausnutzung", "bestell", "bedarf", "rest", "gewicht",
               "materialverbrauch", "reduzieren", "schnittplan")
    quellen = ("Schnittplan", "material_pruefung", "preisalter")

    def pruefen(self, ctx):
        from . import material_pruefung, preisalter
        out = []
        erg = ctx.ergebnis
        if not erg:
            return out
        gruppen = {}
        for st in erg.get("stangen") or ():
            g = gruppen.setdefault((st.get("profil"), st.get("werkstoff"), st.get("stange")), [0, 0.0])
            g[0] += 1
            g[1] += sum(_n(t.get("laenge")) for t in st.get("teile") or ())
        bedarf = []
        for (profil, werkstoff, laenge), (n, teile_mm) in gruppen.items():
            if not laenge or not n:
                continue
            aus = teile_mm / (n * laenge)
            bedarf.append(f"{n} × {profil} {werkstoff} {int(laenge)} mm")
            if aus < AUSNUTZUNG_MIN:
                out.append(self.b(HINWEIS, f"{profil} {werkstoff}: Ausnutzung nur {_z(100 * aus, 0)} % auf {n} Stangen "
                                  f"({_z((n * laenge - teile_mm) / 1000, 2)} m Rest/Verschnitt). Andere Stangenlänge oder "
                                  "Mengen prüfen.", ziel="optimieren", quelle="Schnittplan",
                                  zahlen=dict(ausnutzung_pct=round(100 * aus), stangen=n)))
        if bedarf:
            out.append(self.b(INFO, "Materialbedarf: " + "; ".join(bedarf) + ".", quelle="Schnittplan",
                              ziel="materialanfrage"))
        k, tab, e = ctx.grundlage
        for art, text, *rest in material_pruefung.gewicht_punkte(ctx.positionen, k, e):
            z = rest[0] if rest else None
            out.append(self.b(art, text, ziel=f"pos:{z}" if isinstance(z, int) else None, quelle="STEP-Gewicht (MAT-019)"))
        for p in preisalter.punkte(ctx.positionen, k, tab, e, ctx.heute):
            out.append(self.b(p[0], p[1], ziel=getattr(p, "ziel", None) or "materialanfrage",
                              quelle="Preisalter", aktion=getattr(p, "aktion", None)))
        return out


class SchweissKI(Agent):
    name, titel = "schweissen", "Schweiß-KI"
    aufgabe = "Schweißbaugruppen: Zeiten von Hand gegen gelernte Vergleichswerte, Nachkalkulation"
    woerter = ("schweiß", "schweiss", "naht", "baugruppe", "bg", "nahtlänge", "schweißzeit")
    quellen = ("bg_zeitlernen", "kennwerte (Quelle schweissen)")

    def pruefen(self, ctx):
        from . import bg_zeitlernen
        out = []
        s = ctx.summen
        if _n(s.get("baugruppe_eigen")) <= 0:
            return out
        out.append(self.b(INFO, f"Schweißbaugruppen: {_z(_n(s.get('baugruppe_schweiss_min')), 0)} min Schweißen, "
                          f"{_z(_n(s.get('baugruppe_eigen')))} € eigene Fertigung.", quelle="Kalkulation",
                          zahlen=dict(schweiss_min=round(_n(s.get('baugruppe_schweiss_min'))))))
        nummer = (ctx.kopf or {}).get("nummer")
        zeilen = [z for z in bg_zeitlernen.faelle(ctx.db) if str(z.get("angebot")) == str(nummer)]
        alle = [z for z in bg_zeitlernen.faelle(ctx.db) if str(z.get("angebot")) != str(nummer)]
        faktoren = [_n(z.get("hand_min")) / _n(z.get("auto_min")) for z in alle if _n(z.get("auto_min")) > 0
                    and _n(z.get("hand_min")) > 0]
        if len(faktoren) >= 5:
            med = statistics.median(faktoren)
            mad = statistics.median(abs(f - med) for f in faktoren) or 0.05
            for z in zeilen:
                if _n(z.get("auto_min")) > 0 and _n(z.get("hand_min")) > 0:
                    f = _n(z["hand_min"]) / _n(z["auto_min"])
                    if abs(f - med) > 3 * mad:
                        out.append(self.b(HINWEIS, f"{z.get('titel') or 'Baugruppe'}: Zeit von Hand "
                                          f"{_z(_n(z['hand_min']), 0)} min ist {_z(f, 2)}-mal die automatische; sonst "
                                          f"im Mittel {_z(med, 2)}-mal ({len(faktoren)} Entscheidungen).",
                                          quelle="BG-Zeiten (bg_zeitlernen)", zahlen=dict(faktor=round(f, 2))))
        return out

    def uebersicht(self, db, heute=None):
        from . import bg_zeitlernen
        n = len(bg_zeitlernen.faelle(db))
        return [self.b(INFO, f"{n} Schweißzeit-Entscheidungen gespeichert (Lernvorschläge ab "
                       f"{bg_zeitlernen.VORSCHLAG_AB} vergleichbaren).", quelle="bg_zeiten", zahlen=dict(n=n))]


class EinkaufsKI(Agent):
    name, titel = "einkauf", "Einkaufs-KI"
    aufgabe = "Preisentwicklung der Materialien, Zukaufteile ohne Preis, Lieferanten"
    woerter = ("einkauf", "lieferant", "preisentwicklung", "preissteigerung", "zukauf", "schraube", "mutter",
               "normteil", "bestellen", "bestellt", "einkaufspreis", "ek")
    quellen = ("preisverlauf", "Zukaufteile")

    def pruefen(self, ctx):
        from . import preisverlauf
        out = []
        if _n(ctx.summen.get("zukauf_fehlt")) > 0:
            out.append(self.b(WARNUNG, f"{int(_n(ctx.summen['zukauf_fehlt']))} Zukaufteil(e) ohne Einkaufspreis.",
                              ziel="normteile", quelle="Zukaufteile"))
        gesehen = set()
        for p in ctx.positionen:
            schl = (p.get("profil_id"), p.get("werkstoff_id"))
            if not all(schl) or schl in gesehen:
                continue
            gesehen.add(schl)
            try:
                punkte = preisverlauf.reihe(preisverlauf.eintraege(ctx.db.con, *schl))
            except Exception:   # noqa: BLE001
                protokoll.warnung("ki_agenten: abgefangen")
                continue
            for kz in preisverlauf.kennzahlen(punkte, ctx.heute):
                if kz["monate"] == 3 and kz["aenderung_pct"] is not None and abs(kz["aenderung_pct"]) >= PREISSPRUNG_PCT:
                    out.append(self.b(HINWEIS, f"{schl[0]} {schl[1]}: Materialpreis in 3 Monaten "
                                      f"{'+' if kz['aenderung_pct'] > 0 else ''}{_z(kz['aenderung_pct'], 1)} %.",
                                      quelle="Preisverlauf", ziel="preise",
                                      zahlen=dict(aenderung_pct=round(kz["aenderung_pct"], 1))))
        return out


class AngebotsKI(Agent):
    name, titel = "angebot", "Angebots-KI"
    aufgabe = "Angebots-Check, Wiederholteile, ähnliche frühere Angebote, Auftragschance, Staffeln"
    woerter = ("angebot", "vergleich", "ähnlich", "aehnlich", "früher", "frueher", "chance", "staffel", "menge",
               "wiederhol", "prüfung", "pruefung", "versand", "kunde")
    quellen = ("angebot_check", "wiederholteile", "lernen.chancen", "Staffeln")

    def pruefen(self, ctx):
        from . import lernen, wiederholteile
        out = []
        for p in ctx.check:
            art, text = p[0], p[1]
            out.append(self.b(art if art in ARTEN else HINWEIS, text, ziel=getattr(p, "ziel", None),
                              aktion=getattr(p, "aktion", None), quelle="Angebots-Check"))
        kopf = ctx.kopf or {}
        try:
            treffer = ctx.merk("treffer", lambda: wiederholteile.suchen(ctx.db, ctx.angebot_id, kopf.get("kundennr"),
                                                                        ctx.positionen))
        except Exception:       # noqa: BLE001
            treffer = None
        if treffer:
            n = len(treffer)
            out.append(self.b(INFO, f"{n} Position{'en' if n != 1 else ''} gab es schon in früheren Angeboten "
                              "(Wiederholteile).", quelle="Wiederholteile", zahlen=dict(n=n)))
            if not ctx.check:
                for art, text, zeile in wiederholteile.check_punkte(treffer, ctx.positionen):
                    out.append(self.b(art, text, ziel=f"pos:{zeile}" if zeile is not None else None,
                                      quelle="Wiederholteile (Nachkalkulation)"))
        q = (lernen.chancen_db(ctx.db, ctx.heute) or {}).get(ctx.angebot_id)
        if q:
            wert = q[0] if isinstance(q, (tuple, list)) else q
            if isinstance(wert, (int, float)):
                out.append(self.b(INFO, f"Geschätzte Auftragschance {_z(100 * wert, 0)} %.", quelle="Auftragschance",
                                  zahlen=dict(chance_pct=round(100 * wert))))
        return out


class QualitaetsKI(Agent):
    name, titel = "qualitaet", "Qualitäts-KI"
    aufgabe = "Ungeprüfte STEP-Merkmale, Plausibilität der STEP-Messung, unsichere Bauteilart, Sonderprofile, "\
              "Reklamationen bei Wiederholteilen"
    woerter = ("qualität", "qualitaet", "fehler", "unstimmig", "prüfen", "pruefen", "reklamation", "konstruktion",
               "3d", "editor", "erkannt", "plausib", "wandstärke", "wandstaerke", "import", "rohr erkannt")
    quellen = ("step_pruefung", "step_plausibel", "bauteil_analyse", "einsichten.reklamation_punkte")

    def _import(self, ctx):
        """STEP-Import (Auftrag 21.11.2026): Plausibilität der Messwerte und unsicher erkannte Bauteilarten aus dem beim
        Übernehmen gespeicherten Stand (positionen.step_merkmale) – nichts wird neu gemessen oder geschätzt, jede Zahl
        im Text steht in zahlen (Faktencheck). Bestätigte Positionen („Passt“) zählen nicht."""
        from . import step_pruefung
        out = []
        for i, p in enumerate(ctx.positionen):
            d = step_pruefung.lesen(p.get("step_merkmale"))
            if not d or d.get("geprueft"):
                continue
            for b in (d.get("plausibel") or ())[:4]:
                zahlen = {}
                for k, v in (b.get("basis") or {}).items():     # Listen (Innen-/Sollmaß, Normwände) einzeln
                    for j, x in enumerate(v if isinstance(v, (list, tuple)) else [v]):
                        if isinstance(x, (int, float)) and not isinstance(x, bool):
                            zahlen[k if not isinstance(v, (list, tuple)) else f"{k}_{j + 1}"] = x
                out.append(self.b(HINWEIS, f"Pos. {_pos_nr(p, i)}: {b.get('titel')}: {b.get('text')}", ziel=f"pos:{i}",
                                  quelle="STEP-Plausibilität (Messwerte)", zahlen=zahlen,
                                  begruendung="aus den Messwerten der STEP und den Stammdaten; die Messung gilt"))
            a = d.get("analyse") or {}
            if a and a.get("stufe") not in (None, "sicher"):
                uns = "; ".join(str(x) for x in (a.get("unsicherheiten") or ())[:2])
                out.append(self.b(HINWEIS, f"Pos. {_pos_nr(p, i)}: Bauteilart „{a.get('kategorie')}“ nur "
                                  f"{a.get('konfidenz', 0)} % sicher" + (f" ({uns})" if uns else "") + " – im Prüfdialog "
                                  "bestätigen oder ändern.", ziel=f"pos:{i}", quelle="Importanalyse (Konfidenz)",
                                  zahlen=dict(konfidenz=a.get("konfidenz", 0))))
        return out

    def pruefen(self, ctx):
        from . import einsichten, step_pruefung
        out = self._import(ctx)
        offen = [(i, p, step_pruefung.offen(p)) for i, p in enumerate(ctx.positionen)]
        offen = [x for x in offen if x[2]]
        nicht = [(i, p) for i, p, m in offen if any(x.get("status") == step_pruefung.NICHT for x in m)]
        for i, p in nicht:
            namen = ", ".join(x.get("titel") or x.get("name") or "" for x in step_pruefung.offen(p)
                              if x.get("status") == step_pruefung.NICHT)
            out.append(self.b(WARNUNG, f"Pos. {_pos_nr(p, i)}: aus der STEP nicht erkannt: {namen or 'Merkmale'}.",
                              ziel=f"pos:{i}", quelle="STEP-Prüfstatus"))
        rest = [x for x in offen if (x[0], x[1]) not in nicht]
        if rest:
            out.append(self.b(HINWEIS, f"{len(rest)} Position(en) mit STEP-Merkmalen „prüfen“ (unsicher erkannt).",
                              ziel="stepgelb:" + ",".join(str(i) for i, _, _ in rest), quelle="STEP-Prüfstatus",
                              zahlen=dict(n=len(rest))))
        treffer = ctx.merk("treffer", lambda: None)
        for art, text, *z in einsichten.reklamation_punkte(ctx.db, treffer, ctx.positionen):
            out.append(self.b(art, text, ziel=f"pos:{z[0]}" if z and z[0] is not None else None,
                              quelle="Reklamationen"))
        return out


class ProduktionsKI(Agent):
    name, titel = "produktion", "Produktions-KI"
    aufgabe = "Nachkalkulation ähnlicher Aufträge, Abweichungen Soll/Ist, Zeitverluste"
    woerter = ("produktion", "auslastung", "abweichung", "nachkalkulation", "ist", "verlieren", "verlust",
               "zeitverlust", "auftrag", "aufträge", "auftraege", "termin", "durchlauf")
    quellen = ("nachkalkulation", "einsichten.nachkalk_hinweis", "kostentreiber")

    def pruefen(self, ctx):
        from . import einsichten
        out = []
        t = einsichten.nachkalk_hinweis(ctx.db, ctx.kopf, ctx.positionen, ohne_id=ctx.angebot_id)
        if t:
            out.append(self.b(HINWEIS, t, quelle="Nachkalkulation ähnlicher Aufträge", ziel="kalkulation"))
        out += self._datenbasis(ctx)
        return out

    def _datenbasis(self, ctx):
        """Genauigkeitsbewertung je Laserposition aus den Maschinendaten (Produktionsdaten-Intelligenz 24.11.2026):
        wie viele vergleichbare LST/BPF-Teile es gibt und wie genau die Zeit bei ihnen war; nie höher als belegt."""
        from . import produktion_genauigkeit as pg
        try:
            bw = pg.angebot(ctx.db, ctx.positionen)
        except Exception:       # noqa: BLE001 – ohne Produktionsdaten-Tabellen (alter Stand) kein Befund
            protokoll.warnung("ki_agenten: Datenbasis Produktionsdaten nicht lesbar")
            return []
        if not bw:
            return []
        n_gem = sum(b["gemessen"] for _, b in bw)
        ohne = [str(p.get("pos") or "?") for p, b in bw if not b["vergleichbar"]]
        teile = [f"Pos. {p.get('pos') or '?'}: {pg.kurz(b)}" for p, b in bw[:6]]
        out = [self.b(INFO, "Datenbasis der Bearbeitungszeit (Maschinendaten): " + "; ".join(teile)
                      + (" …" if len(bw) > 6 else ""), quelle="Produktionsdaten-Intelligenz", ziel="lernsystem",
                      zahlen=dict(gemessen=n_gem, positionen=len(bw)))]
        if ohne and len(ohne) == len(bw):
            out.append(self.b(HINWEIS, "Für keine Position gibt es vergleichbare Maschinendaten: die Zeiten sind "
                              "reine Rechnung. Gelaufene LST-Dateien einlesen verbessert die Datenbasis.",
                              quelle="Produktionsdaten-Intelligenz", ziel="lernsystem"))
        return out

    def _maschinendaten(self, db):
        return _maschinendaten_befunde(self, db)

    def uebersicht(self, db, heute=None):
        from . import ki_lernhistorie
        out = []
        for a in ki_lernhistorie.abweichungen(db)[:5]:
            out.append(self.b(HINWEIS if abs(a["prozent"]) >= 20 else INFO,
                              f"Angebot {a['nummer']} ({a['kunde']}): Einzelkosten Ist {_z(a['ist'])} € gegen Soll "
                              f"{_z(a['soll'])} € ({'+' if a['prozent'] > 0 else ''}{_z(a['prozent'], 1)} %), "
                              f"größte Abweichung: {a['groesste']}.", quelle="Nachkalkulation",
                              zahlen=dict(prozent=round(a["prozent"], 1))))
        out += self._maschinendaten(db)
        from . import kostentreiber
        k = kostentreiber.auswertung(db, heute)
        for z in [z for z in k.get("abmessungen") or () if z.get("abweichung") is not None][:3]:
            out.append(self.b(HINWEIS, f"{z['name']}: Laufzeit Ist {_z(100 * z['abweichung'], 0)} % gegen Soll "
                              f"({z['n_ist']} Aufträge mit Ist-Zeit).", quelle="Kostentreiber"))
        return out


def _maschinendaten_befunde(agent, db):
    """Ursachen der Zeitabweichung über alle zugeordneten Maschinendaten und Zeitmodelle je Konturklasse."""
    from . import lst_vergleich, produktion_abgleich, produktion_lst, produktion_zeitmodell
    out = []
    try:
        teile = produktion_lst.teile(db)
        if not teile:
            return []
        zeilen = lst_vergleich.vergleich(db, teile)
        erg = produktion_abgleich.auswerten(db, zeilen)
    except Exception:       # noqa: BLE001
        protokoll.warnung("ki_agenten: Maschinendaten nicht auswertbar")
        return []
    _, urs = produktion_abgleich.zusammenfassung(erg)
    for u, d in sorted(urs.items(), key=lambda x: -abs(x[1]["median_s"]))[:3]:
        if d["n"] >= 3:
            out.append(agent.b(HINWEIS, f"Maschinendaten: häufigste Ursache der Zeitabweichung „{u}“, im Mittel "
                               f"{_z(d['median_s'], 1)} s je Teil ({d['n']} Teile).", quelle="Produktionsdaten-Abgleich",
                               ziel="lernsystem", zahlen=dict(median_s=d["median_s"], n=d["n"])))
    for m in produktion_zeitmodell.modelle(teile, [e["zeile"] for e in erg]):
        if m["status"] == "ok":
            out.append(agent.b(INFO, "Zeitmodell je Konturklasse: " + produktion_zeitmodell.text(m),
                               quelle="Produktionsdaten-Zeitmodell", ziel="lernsystem",
                               zahlen=dict(n=m["n"], programme=m["programme"])))
    return out


class LernKI(Agent):
    name, titel = "lernen", "Lern-KI"
    aufgabe = "Reife Lernvorschläge aus Nachkalkulation, Kalibrierung, Handeinträgen, BG-Zeiten, LST"
    woerter = ("lernen", "gelernt", "erfahrung", "kennwert", "kalibrier", "verbessern", "lernvorschlag",
               "trainings", "lerndaten")
    quellen = ("kennwerte", "kalibrierung", "lernen", "muster", "bg_zeitlernen")

    def uebersicht(self, db, heute=None):
        from . import ki_lernhistorie
        out = []
        for v in ki_lernhistorie.offene_vorschlaege(db):
            out.append(self.b(VORSCHLAG, f"{v['titel']}: {v['text']}", quelle=v["quelle"], ziel="lernzentrale",
                              zahlen=dict(faktor=v.get("faktor") or 0, n=v.get("n") or 0)))
        for f in ki_lernhistorie.fehlerhafte_daten(db)[:10]:
            out.append(self.b(WARNUNG, f"Lerndaten prüfen: {f['text']}", quelle=f["quelle"], ziel="lernzentrale"))
        return out


class VerwaltungsKI(Agent):
    name, titel = "verwaltung", "Verwaltungs-KI"
    aufgabe = "Offene Kundenanfragen, Fristen, Prioritäten, fehlende Angaben, Rückfragen"
    woerter = ("anfrage", "anfragen", "outlook", "mail", "e-mail", "kunde", "frist", "priorität", "prioritaet",
               "rückfrage", "rueckfrage", "dokument", "zeichnung")
    quellen = ("anfragen_akten", "anfrage_art")

    def uebersicht(self, db, heute=None):
        from . import ki_prognose
        out = []
        for a in ki_prognose.anfragen_prioritaet(db, heute)[:8]:
            out.append(self.b(HINWEIS if a["punkte"] >= 50 else INFO,
                              f"Anfrage {a['nr']} {a['kunde'] or a['absender']}: {a['betreff']} – {a['grund']}",
                              quelle="Anfragen (Outlook)", ziel=f"anfrage:{a['nr']}",
                              zahlen=dict(punkte=a["punkte"])))
        return out


AGENTEN = (KalkulationsKI(), RohrlaserKI(), MaterialKI(), SchweissKI(), EinkaufsKI(), AngebotsKI(), QualitaetsKI(),
           ProduktionsKI(), LernKI(), VerwaltungsKI())
AGENT = {a.name: a for a in AGENTEN}


def sortiert(befunde):
    return sorted(befunde, key=lambda b: (RANG.get(b["art"], 9)))


def pruefen(db, angebot_id=None, seite=None, agenten=None, heute=None, protokoll=True):
    """Alle (oder die genannten) Agenten auf ein Angebot: dict(befunde, fehler, kontext). Protokolliert die Prüfung
    und merkt Fehler/Warnungen/Vorschläge als offene Empfehlungen."""
    import time
    from . import ki_protokoll
    t0 = time.perf_counter()
    ctx = Kontext(db, angebot_id, seite, heute)
    out = []
    for a in (AGENT[n] for n in agenten) if agenten else AGENTEN:
        try:
            for b in a.pruefen(ctx) or ():
                b["stand"] = b.get("stand") or ctx.stand
                out.append(b)
        except Exception as e:  # noqa: BLE001 – ein Agent fällt aus: die anderen laufen weiter
            ctx.fehler.append((a.titel, f"{type(e).__name__}: {e}"[:200]))
    out = sortiert(out)
    if protokoll and ctx.angebot_id is not None:
        nummer = (ctx.kopf or {}).get("nummer") or ctx.angebot_id
        ki_protokoll.schreiben(db, "Orchestrator", "pruefung", frage=f"Angebot {nummer}",
                               ergebnis=f"{len(out)} Befunde, davon "
                               f"{sum(1 for b in out if b['art'] in (FEHLER, WARNUNG))} Fehler/Warnungen",
                               quellen=sorted({b['quelle'] for b in out if b.get('quelle')}),
                               dauer=time.perf_counter() - t0, angebot_id=ctx.angebot_id)
        schl = set()
        for b in out:
            b["schluessel"] = b.get("schluessel") or f"{b['agent']}|{ctx.angebot_id}|{b['text']}"[:500]
            if ki_protokoll.empfehlung_merken(db, b, ctx.angebot_id):
                schl.add(b["schluessel"])
        ki_protokoll.angebot_schliessen(db, ctx.angebot_id, {b["schluessel"] for b in out})
    return dict(befunde=out, fehler=list(ctx.fehler), kontext=ctx)


def uebersicht(db, agenten=None, heute=None):
    """Befunde über alle Daten (ohne Angebot)."""
    out, fehler = [], []
    for a in (AGENT[n] for n in agenten) if agenten else AGENTEN:
        try:
            out += a.uebersicht(db, heute) or []
        except Exception as e:  # noqa: BLE001
            fehler.append((a.titel, f"{type(e).__name__}: {e}"[:200]))
    return dict(befunde=sortiert(out), fehler=fehler)
