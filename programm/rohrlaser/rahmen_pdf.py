"""Dokumente zum Rahmenauftrag (Patrick 20.11.2026, Master-Auftrag Punkt 11) im Stil der Angebotsakte (akte_pdf:
Schrift, Farben, Tabellen; Petrol = an den Kunden, Bernstein = intern). Rechnet nichts, setzt nur die Sicht
(rahmenauftrag.sicht/kennzahlen) und das Ergebnis von rahmen_kalk.berechnen.

Dokumente (ARTEN): kunde (Kundenangebot Rahmenauftrag, ohne Kosten, Gewinn, Marge), abrufe (Abruf- und
Lieferübersicht, an den Kunden möglich), intern (Interne Rahmenkalkulation), material (Materialbedarfsplanung),
produktion (Produktionsplanung), vergleich (Wirtschaftlichkeitsvergleich der Produktionsvarianten), abschluss
(Abschlussübersicht zum Vertragsende).

kunde_pruefen(pfad) sucht interne Begriffe im fertigen Kunden-PDF (Schutztest wie bei der Angebotsakte)."""
import datetime

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer

from . import akte_pdf as ap
from . import rahmen_kalk as rk
from . import rahmenauftrag as ra

KUNDE, INTERN = "kunde", "intern"
ARTEN = {"kunde": ("Kundenangebot Rahmenauftrag", KUNDE), "abrufe": ("Abruf- und Lieferübersicht", KUNDE),
         "intern": ("Interne Rahmenauftragskalkulation", INTERN), "material": ("Materialbedarfsplanung", INTERN),
         "produktion": ("Produktionsplanung", INTERN),
         "vergleich": ("Wirtschaftlichkeitsvergleich der Produktionsvarianten", INTERN),
         "abschluss": ("Abschlussübersicht Rahmenauftrag", INTERN)}
INTERNE_BEGRIFFE = ("Selbstkosten", "Marge", "Gewinn", "Deckungsbeitrag", "Herstellkosten", "Rüstkosten",
                    "Kapitalbindung", "Mindestmarge", "INTERN")

g, pz, mg, dt = ap.geld, ap.prozent, ap.menge, ap.datum


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


class _Blatt(rl_canvas.Canvas):
    """Kopf, Fuß, Randleiste (wie die Akte), Titel „Rahmenauftrag <Nummer>“, Seite x von y."""
    titel, art, nummer, firma, st, stand = "", KUNDE, "", "", None, ""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._blaetter = []

    def showPage(self):
        self._blaetter.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._blaetter)
        for i, z in enumerate(self._blaetter, start=1):
            self.__dict__.update(z)
            self._rahmen(i, n)
            super().showPage()
        super().save()

    def _rahmen(self, i, n):
        st, intern = self.st, self.art == INTERN
        h, b = ap.BLATT_H, ap.BLATT_B
        self.saveState()
        self.setFillColor(ap.INTERN if intern else ap.KUNDE)
        self.rect(0, 0, 9 * mm if intern else 3.2 * mm, h, stroke=0, fill=1)
        if intern:
            self.setFillColor(ap.WEISS)
            self.setFont(st["semi"], 7.5)
            self.translate(5.9 * mm, h / 2)
            self.rotate(90)
            self.drawCentredString(0, 0, "INTERN  ·  NICHT AN KUNDEN WEITERGEBEN  ·  INTERN")
        self.restoreState()
        oben = h - 13 * mm
        self.setFillColor(ap.INTERN if intern else ap.KUNDE)
        self.setFont(st["medium"], 7.2)
        self.drawString(ap.RAND_L, oben + 3.6 * mm, "INTERNE KALKULATION" if intern else self.firma)
        self.setFillColor(ap.TINTE)
        self.setFont(st["semi"], 9)
        self.drawString(ap.RAND_L, oben - 0.6 * mm, self.titel)
        self.drawRightString(b - ap.RAND_R, oben - 0.6 * mm, f"Rahmenauftrag {self.nummer}")
        self.setFont(st["sans"], 7.2)
        self.setFillColor(ap.STAHL)
        self.drawRightString(b - ap.RAND_R, oben + 3.6 * mm, f"Seite {i} von {n}")
        self.setStrokeColor(ap.TINTE)
        self.setLineWidth(0.8)
        self.line(ap.RAND_L, oben - 3.2 * mm, b - ap.RAND_R, oben - 3.2 * mm)
        self.setStrokeColor(ap.LINIE)
        self.setLineWidth(0.5)
        self.line(ap.RAND_L, 17.5 * mm, b - ap.RAND_R, 17.5 * mm)
        self.setFont(st["sans"], 6.8)
        self.setFillColor(ap.STAHL)
        self.drawString(ap.RAND_L, 13.2 * mm, self.stand)
        if intern:
            self.setFillColor(ap.INTERN)
            self.setFont(st["semi"], 6.8)
            self.drawRightString(b - ap.RAND_R, 13.2 * mm, "INTERN")


_ST = {}


def _t(daten, breiten, rechts=(), summen=()):
    if not _ST:
        _ST.update(ap._stile())
    return ap._tabelle(daten, [w * mm if w else None for w in breiten], rechts=rechts, summen=summen, stil=_ST)


def _kopfdaten(r, st):
    paare = [("Kunde", f"{r.get('kunde') or ''}" + (f" (Nr. {r['kundennr']})" if r.get("kundennr") else "")),
             ("Rahmenauftrag", r.get("nummer") or ""), ("Projekt", r.get("projekt") or ""),
             ("Laufzeit", f"{dt(r.get('start'))} bis {dt(r.get('ende'))}")]
    if r.get("kunden_nr"):
        paare.append(("Ihre Rahmennummer", r["kunden_nr"]))
    return [ap._kv(paare, st), Spacer(1, 4 * mm)]


def _positionen_kunde(r, st):
    k = ra.kennzahlen(r)
    zeilen = [["Pos.", "Artikel", "Bezeichnung", "Rahmenmenge", "Stückpreis €", "Gesamt €"]]
    for p in k["positionen"]:
        zeilen.append([p["pos"], p.get("artikel") or "", p.get("bezeichnung") or "", mg(p["menge"]),
                       g(p.get("preis"), 2), g(p["wert"])])
    zeilen.append(["", "", "Summe", mg(k["menge"]), "", g(k["wert"])])
    return ap._ueberschrift("Positionen und Rahmenmengen", st) + [
        _t(zeilen, (12, 28, None, 24, 24, 26), rechts=(3, 4, 5), summen=(len(zeilen) - 1,))]


def _bindung_text(r):
    b = r.get("preisbindung") or {}
    m = b.get("modell") or rk.FEST_LAUFZEIT
    if m == rk.FEST_LAUFZEIT:
        return "Die Stückpreise gelten fest über die gesamte Vertragslaufzeit."
    if m == rk.FEST_BIS:
        return f"Die Stückpreise gelten fest bis {dt(b.get('bis'))}; danach nach Vereinbarung."
    if m == rk.MATERIAL_BIS:
        return f"Der Materialpreis ist gebunden bis {dt(b.get('bis'))}."
    if m == rk.GLEITKLAUSEL:
        return ("Materialpreisgleitklausel: Der Stückpreis ändert sich im Verhältnis des Materialanteils "
                f"({_n(b.get('anteil')):g} %) zur Änderung des vereinbarten Materialpreises bzw. -index"
                + (f" (Basis {b['basis']})" if b.get("basis") else "")
                + f", erst ab einer Änderung von {_n(b.get('schwelle') or rk.VORGABEN['gleit_schwelle']):g} %. "
                "Anpassungen werden vorab schriftlich mitgeteilt.")
    if m == rk.PRUEFTERMINE:
        return "Die Preise werden zu folgenden Terminen überprüft: " + ", ".join(dt(t) for t in b.get("pruef_termine") or ())
    return "Preisanpassungen nach individueller Vereinbarung."


def _seite_kunde(r, erg, st, einst):
    out = ap._seiten_titel(1, "Angebot Rahmenauftrag", ap.akte_.KUNDE, st,
                           " · ".join(x for x in (r.get("projekt"), dt(datetime.date.today().isoformat())) if x))
    out += _kopfdaten(r, st)
    out += _positionen_kunde(r, st)
    # Staffelpreise (nur Preise, keine Kosten): Szenario der festgeschriebenen Fertigungsweise
    staffel = (erg or {}).get("preisstaffel") or []
    if staffel:
        name = {rk.A: "je Abruf gefertigt", rk.B: "Gesamtfertigung", rk.C: "gebündelt (optimiert)"}.get(
            (erg or {}).get("empfehlung"), "gebündelt (optimiert)")
        zeilen = [["Rahmenmenge [Stk.]", "Stückpreis € bei eigener Materialbeschaffung", "bei Materialbeistellung"]]
        for z in staffel:
            s = {x["name"]: x for x in z["szenarien"]}
            zeilen.append([mg(z["menge"]), g(s.get(name, {}).get("preis_stueck"), 2),
                           g(s.get("Materialbeistellung Kunde", {}).get("preis_stueck"), 2)])
        out += ap._ueberschrift("Staffelpreise nach Rahmenmenge", st, "bei gleichem Abrufrhythmus") + [
            _t(zeilen, (40, None, 50), rechts=(1, 2))]
    bed = [("Abrufmenge", f"mindestens {mg(r.get('min_abruf'))} Stück" + (
        f", höchstens {mg(r.get('max_abruf'))} Stück" if _n(r.get("max_abruf")) else "") if _n(r.get("min_abruf"))
        else (f"höchstens {mg(r.get('max_abruf'))} Stück" if _n(r.get("max_abruf")) else "nach Bedarf")),
        ("Geplante Abrufe", f"{mg(r.get('abrufe_geplant'))}" + (f", alle {mg(r.get('intervall'))} Monate"
                                                               if _n(r.get("intervall")) else "")
         if _n(r.get("abrufe_geplant")) else "nach Abruf"),
        ("Abrufbedingungen", r.get("abrufbedingungen") or "Abruf schriftlich mit Liefertermin"),
        ("Lieferbedingungen", r.get("lieferbedingungen") or ""), ("Lieferorte", r.get("lieferorte") or ""),
        ("Preisgültigkeit", dt(r.get("preis_gueltig")) if r.get("preis_gueltig") else f"bis {dt(r.get('ende'))}"),
        ("Preisbindung", _bindung_text(r)), ("Zahlungsbedingungen", r.get("zahlung") or "")]
    if r.get("bedingungen"):
        bed.append(("Vereinbarungen", r["bedingungen"]))
    out += ap._ueberschrift("Vertragsbedingungen", st) + [ap._kv([x for x in bed if x[1]], st, (38 * mm, None))]
    return out


class _Balken(ap.Flowable):
    """Abrufe als Balken je Termin: geplant (hell) und geliefert (Petrol)."""

    def __init__(self, abrufe, breite=ap.BREITE, hoehe=48 * mm):
        super().__init__()
        self.a, self.b, self.h = abrufe, breite, hoehe

    def wrap(self, *a):
        return self.b, self.h

    def draw(self):
        a = [x for x in self.a if x.get("status") != ra.STORNIERT]
        if not a:
            return
        d = Drawing(self.b, self.h)
        top = max(max(x["menge"] for x in a), 1)
        unten, links, h = 10 * mm, 8 * mm, self.h - 16 * mm
        w = (self.b - links) / len(a)
        d.add(Line(links, unten, self.b, unten, strokeColor=ap.TINTE, strokeWidth=0.6))
        for i, x in enumerate(a):
            x0 = links + i * w + w * 0.15
            bw = w * 0.7
            d.add(Rect(x0, unten, bw, h * x["menge"] / top, fillColor=ap.KUNDE_FL, strokeColor=ap.KUNDE,
                       strokeWidth=0.4))
            if x["geliefert_menge"]:
                d.add(Rect(x0, unten, bw, h * x["geliefert_menge"] / top, fillColor=ap.KUNDE, strokeWidth=0))
            d.add(String(x0 + bw / 2, unten + h * x["menge"] / top + 1.5 * mm, mg(x["menge"]), fontSize=6.5,
                         textAnchor="middle", fillColor=ap.TINTE))
            d.add(String(x0 + bw / 2, unten - 4 * mm, dt(x.get("datum"))[:5] + dt(x.get("datum"))[8:],
                         fontSize=6, textAnchor="middle", fillColor=ap.STAHL))
        d.drawOn(self.canv, 0, 0)


def _seite_abrufe(r, erg, st, einst):
    k = ra.kennzahlen(r)
    out = ap._seiten_titel(1, "Abruf- und Lieferübersicht", ap.akte_.KUNDE, st, f"Stand {dt(datetime.date.today().isoformat())}")
    out += _kopfdaten(r, st)
    out += [ap._kacheln([("Rahmenmenge", mg(k["menge"])), ("Abgerufen", mg(k["abgerufen"])),
                         ("Geliefert", mg(k["geliefert"])), ("Offen", mg(k["offen"])),
                         ("Noch abrufbar", mg(max(k["verfuegbar"], 0))), ("Restwert €", g(k["restwert"]))], st),
            Spacer(1, 4 * mm), _Balken(k["abrufe"]), Spacer(1, 2 * mm),
            ap._p("Balken hell = Abrufmenge, dunkel = geliefert.", st["klein"])]
    zeilen = [["Nr.", "Termin geplant", "Geliefert am", "Status", "Menge", "Geliefert", "Wert €", "Lieferort"]]
    for a in k["abrufe"]:
        zeilen.append([str(a["nr"]), dt(a.get("datum")), dt(a.get("ist_datum")), a.get("status") or "", mg(a["menge"]),
                       mg(a["geliefert_menge"]), g(a["wert"]), a.get("lieferort") or ""])
    out += ap._ueberschrift("Abrufe", st) + [_t(zeilen, (10, 22, 22, 22, 16, 18, 22, None), rechts=(4, 5, 6))]
    zeilen = [["Pos.", "Bezeichnung", "Rahmenmenge", "Abgerufen", "Geliefert", "Offen", "Restwert €"]]
    for p in k["positionen"]:
        zeilen.append([p["pos"], p.get("bezeichnung") or "", mg(p["menge"]), mg(p["abgerufen"]), mg(p["geliefert"]),
                       mg(p["offen"]), g(p["restwert"])])
    out += ap._ueberschrift("Je Position", st) + [_t(zeilen, (12, None, 22, 20, 20, 18, 24), rechts=(2, 3, 4, 5, 6))]
    return out


def _kosten_zeilen(e):
    return [("Programmierung (einmalig + Wiederholung)", e["programmierung"]),
            ("Einmalig: Vorrichtung, Verwaltung", e["einmalig"]), ("Rüsten je Los", e["ruesten"]),
            ("Fertigung je Stück (Schneiden, Schweißen, Nacharbeit, Zukauf)", e["fertigung"]),
            ("Material", e["material"]), ("Kapitalbindung Material", e["material_kapital"]),
            ("Lager (Platz, Einlagern)", e["lager"]), ("Kapitalbindung Fertigteile", e["kapital"]),
            ("Lieferabwicklung, Kommissionierung, Verpackung", e["lieferung"])]


def _seite_intern(r, erg, st, einst):
    out = ap._seiten_titel(1, "Interne Rahmenauftragskalkulation", ap.akte_.INTERN, st,
                           f"Version {(r.get('version') or {}).get('nr') or '–'} · Variante {erg['empfehlung']} "
                           f"{rk.VARIANTE_TEXT[erg['empfehlung']]} · Material {erg['material_art']}")
    out += _kopfdaten(r, st)
    e = erg["ergebnis"]
    out += [ap._kacheln([("Selbstkosten €", g(e["selbst"])), ("Gewinn €", g(e["gewinn"] + e["anhebung"])),
                         ("Marge", pz(e["marge"])), ("Netto €", g(e["netto"])), ("Preis je Stück €", g(e["preis_stueck"], 3)),
                         ("Lose", str(e["lose"]))], st), Spacer(1, 4 * mm)]
    zeilen = [["Kostenklasse / Posten", "Betrag €", "je Stück €"]]
    for t, w in _kosten_zeilen(e):
        zeilen.append([t, g(w), g(w / e["menge"], 3) if e["menge"] else ""])
    zeilen.append(["Selbstkosten", g(e["selbst"]), g(e["selbst_stueck"], 3)])
    zeilen.append(["Gewinn (ohne Zukauf und Fracht)", g(e["gewinn"]), g(e["gewinn"] / e["menge"], 3)])
    if e["anhebung"]:
        zeilen.append(["Anhebung auf Mindestmarge", g(e["anhebung"]), g(e["anhebung"] / e["menge"], 3)])
    zeilen.append(["Fracht (ohne Gewinn)", g(e["fracht"]), g(e["fracht"] / e["menge"], 3)])
    zeilen.append(["Nettopreis (nach Skonto)", g(e["netto"]), g(e["preis_stueck"], 3)])
    out += ap._ueberschrift("Kosten des Rahmens", st, "Kosten je Los aus der zentralen Angebotsrechnung; jede "
                            "Kostenklasse genau einmal") + [
        _t(zeilen, (None, 30, 26), rechts=(1, 2), summen=(10,))]
    zeilen = [["Pos.", "Losfix F €", "Fertigung €/Stk.", "Material €/Stk.", "Zukauf €/Stk.", "Programm. €", "kg/Stk.",
               "Selbstk. €/Stk.", "Vertragspreis €"]]
    jp = erg.get("je_position") or {}
    for p in r.get("positionen") or ():
        x = erg["modell"]["pos"].get(str(p.get("pos")))
        if not x:
            continue
        zeilen.append([str(p.get("pos")), g(x["F"]), g(x["vf"], 3), g(x["m"], 3), g(x["z"], 3), g(x["P"]), g(x["kg"], 3),
                       g((jp.get(str(p.get("pos"))) or {}).get("selbst_stueck"), 3), g(p.get("preis"), 2)])
    out += ap._ueberschrift("Kostenmodell je Position", st) + [
        _t(zeilen, (12, 18, 20, 20, 18, 18, 14, 20, None), rechts=tuple(range(1, 9)))]
    par = erg["parameter"]
    out += ap._ueberschrift("Parameter", st) + [ap._kv([
        ("Zins", f"{par['zins']:g} % p. a."), ("Lagerplatz", f"{g(par['lagerplatz'])} € je Palette und Monat, "
                                                             f"{par['teile_palette']:g} Teile je Palette"),
        ("Programmierung je weiterem Los", f"{par['prog_wiederholung']:g} %"),
        ("Je Abruf", f"{par['kommission_min']:g} min × {g(par['kommission_satz'])} €/h + {g(par['abwicklung'])} € "
                     f"Abwicklung + {g(par['verpackung'])} € Verpackung"),
        ("Material", f"Bestellkosten {g(par['bestellkosten'])} €, Mindestmenge {par['moq_kg']:g} kg"),
        ("Mindestmarge", pz(erg["marge_min"]))], st, (50 * mm, None))]
    return out


def _seite_material(r, erg, st, einst):
    out = ap._seiten_titel(1, "Materialbedarfsplanung", ap.akte_.INTERN, st, f"Material {erg['material_art']}")
    k = ra.kennzahlen(r)
    m = k["material"]
    out += [ap._kacheln([("Gekauft kg", g(m["gekauft_kg"], 1)), ("Gekauft €", g(m["gekauft_eur"])),
                         ("Verbraucht kg", g(m["verbraucht_kg"], 1)), ("Bestand kg", g(m["bestand_kg"], 1)),
                         ("Bedarf offen kg", g(m["bedarf_offen_kg"], 1)), ("Noch kaufen kg", g(m["noch_kaufen_kg"], 1))],
                        st), Spacer(1, 3 * mm),
            ap._p("Nur das für diesen Rahmenauftrag gekaufte Material (kein allgemeines Restelager). Bereits gekauftes "
                  "Material wird bei späteren Abrufen nicht noch einmal beschafft.", st["klein"])]
    mv = erg.get("materialvergleich") or {}
    zeilen = [["Materialart", "Variante", "Material €", "Kapitalbindung €", "Selbstkosten €", "Käufe"]]
    for art, v in (mv.get("je") or {}).items():
        x = v[v["empfehlung"]]
        zeilen.append([art, v["empfehlung"], g(x["material"]), g(x["material_kapital"]), g(x["selbst"]),
                       str(len(x["material_kaeufe"]))])
    out += ap._ueberschrift("Einkauf gesamt oder je Los?", st,
                            f"Empfehlung: {mv.get('empfehlung')} (Unterschied {g(mv.get('ersparnis'))} €)") + [
        _t(zeilen, (36, 16, 26, 28, 28, None), rechts=(2, 3, 4, 5))]
    e = erg["ergebnis"]
    zeilen = [["Bestelltermin", "kg", "€", "Rabatt"]]
    for x in e["material_kaeufe"]:
        zeilen.append([dt(x["datum"]), g(x["kg"], 1), g(x["eur"]), f"{x['rabatt']:g} %"])
    out += ap._ueberschrift("Geplante Bestellungen", st, e.get("material_hinweis") or "") + [
        _t(zeilen, (40, 30, 30, None), rechts=(1, 2, 3))]
    zeilen = [["Datum", "kg", "€", "Lieferant / Los"]]
    for x in (r.get("material") or {}).get("kaeufe") or ():
        zeilen.append([dt(x.get("datum")), g(x.get("kg"), 1), g(x.get("eur")), x.get("lieferant") or ""])
    for x in (r.get("material") or {}).get("verbrauch") or ():
        zeilen.append([dt(x.get("datum")), g(-_n(x.get("kg")), 1), "", f"Verbrauch {x.get('los') or ''}"])
    out += ap._ueberschrift("Materialkonto", st) + [_t(zeilen, (30, 30, 30, None), rechts=(1, 2))]
    return out


def _seite_produktion(r, erg, st, einst):
    e = erg["ergebnis"]
    out = ap._seiten_titel(1, "Produktionsplanung", ap.akte_.INTERN, st,
                           f"Variante {erg['empfehlung']} {rk.VARIANTE_TEXT[erg['empfehlung']]}: {e['lose']} Lose")
    pos = sorted({p for los in e["je_los"] for p in los["mengen"]})
    zeilen = [["Los", "Fertigung am", "für Abrufe"] + [f"Pos. {p}" for p in pos] + ["Rüsten €", "Lager €"]]
    for los in e["je_los"]:
        zeilen.append([str(los["nr"]), dt(los["datum"]), ", ".join(map(str, los["abrufe"]))]
                      + [mg(los["mengen"].get(p)) for p in pos] + [g(los["ruesten"]), g(los["lager"] + los["kapital"])])
    out += [_t(zeilen, [10, 22, 26] + [None] * len(pos) + [20, 20], rechts=tuple(range(3, 5 + len(pos))))]
    gp = erg.get("gegenpruefung")
    if isinstance(gp, list) and gp:
        zeilen = [["Los", "Stück", "Modell €", "Zentrale Rechnung €", "Abweichung"]]
        for x in gp:
            zeilen.append([str(x["los"]), mg(x["stueck"]), g(x["modell"]), g(x["exakt"]), f"{x['abweichung']:.1f} %"])
        out += ap._ueberschrift("Gegenprüfung mit der zentralen Rechnung", st) + [
            _t(zeilen, (14, 20, 30, 36, None), rechts=(1, 2, 3, 4))]
    rest = erg.get("restplan")
    if rest:
        x = rest[rest["empfehlung"]]
        out += ap._ueberschrift("Restplan (offene Abrufe)", st,
                                f"Variante {rest['empfehlung']}: {x['lose']} Lose, Selbstkosten {g(x['selbst'])} €")
    return out


def _seite_vergleich(r, erg, st, einst):
    v = erg["varianten"]
    out = ap._seiten_titel(1, "Wirtschaftlichkeitsvergleich", ap.akte_.INTERN, st,
                           f"Empfehlung: Variante {v['empfehlung']} {rk.VARIANTE_TEXT[v['empfehlung']]}")
    kopf = ["Posten", "A je Abruf", "B gesamt", "C optimiert"]
    zeilen = [kopf, ["Lose"] + [str(v[x]["lose"]) for x in (rk.A, rk.B, rk.C)]]
    for t, n in (("Rüsten", "ruesten"), ("Fertigung", "fertigung"), ("Programmierung", "programmierung"),
                 ("Material", "material"), ("Kapital Material", "material_kapital"), ("Lager", "lager"),
                 ("Kapital Fertigteile", "kapital"), ("Lieferung", "lieferung"), ("Selbstkosten", "selbst"),
                 ("Gewinn + Anhebung", None), ("Fracht", "fracht"), ("Netto", "netto")):
        zeilen.append([t] + [g(v[x][n]) if n else g(v[x]["gewinn"] + v[x]["anhebung"]) for x in (rk.A, rk.B, rk.C)])
    zeilen.append(["Preis je Stück"] + [g(v[x]["preis_stueck"], 3) for x in (rk.A, rk.B, rk.C)])
    zeilen.append(["Marge"] + [pz(v[x]["marge"]) for x in (rk.A, rk.B, rk.C)])
    out += [_t(zeilen, (None, 34, 34, 34), rechts=(1, 2, 3), summen=(10,))]
    zeilen = [["Feste Losgröße", "Lose", "Selbstkosten €", "Preis je Stück €"]]
    for gr, x in v["feste"]:
        zeilen.append([mg(gr), str(x["lose"]), g(x["selbst"]), g(x["preis_stueck"], 3)])
    out += ap._ueberschrift("Feste Losgrößen (auf ganze Abrufe gerundet)", st,
                            f"Andler-Richtwert: {mg(v['andler'])} Stück" if v.get("andler") else "") + [
        _t(zeilen, (36, 20, 36, None), rechts=(1, 2, 3))]
    zeilen = [["Rahmenmenge", "Szenario", "Selbstk. €/Stk.", "Gewinn €/Stk.", "Marge", "Preis €/Stk.", ""]]
    for z in erg.get("preisstaffel") or ():
        for i, s in enumerate(z["szenarien"]):
            zeilen.append([mg(z["menge"]) if i == 0 else "", s["name"], g(s["selbst_stueck"], 3),
                           g(s["gewinn_stueck"], 3), pz(s["marge"]), g(s["preis_stueck"], 3),
                           "unter Mindestmarge" if s["unter_mindestmarge"] else ""])
    out += ap._ueberschrift("Preisstaffel und Szenarien", st) + [
        _t(zeilen, (22, 44, 22, 22, 16, 22, None), rechts=(2, 3, 4, 5))]
    return out


def _seite_abschluss(r, erg, st, einst):
    a = rk.abschluss(r)
    out = ap._seiten_titel(1, "Abschlussübersicht", ap.akte_.INTERN, st, f"Stichtag {dt(a['stichtag'])}")
    out += _kopfdaten(r, st)
    out += [ap._kacheln([("Umsatz geliefert €", g(a["umsatz"])), ("Restwert €", g(a["restwert"])),
                         ("Abrufe geliefert", f"{a['abrufe_ist']} von {a['abrufe_plan']}"),
                         ("Storniert", str(a["storniert"]))], st), Spacer(1, 3 * mm)]
    zeilen = [["Pos.", "Menge", "Abgerufen", "Geliefert", "Nicht abgerufen", "Gefertigt", "Auf Lager", "Verpflichtung"]]
    for z in a["zeilen"]:
        zeilen.append([z["pos"], mg(z["menge"]), mg(z["abgerufen"]), mg(z["geliefert"]), mg(z["nicht_abgerufen"]),
                       mg(z["gefertigt"]), mg(z["bestand"]), mg(z["verpflichtung"])])
    out += [_t(zeilen, (12, 20, 20, 20, 26, 20, 20, None), rechts=tuple(range(1, 8)))]
    if a["hinweise"]:
        out += ap._ueberschrift("Offene Punkte", st) + [ap._p("• " + h, st["text"]) for h in a["hinweise"]]
    return out


BAUER = dict(kunde=_seite_kunde, abrufe=_seite_abrufe, intern=_seite_intern, material=_seite_material,
             produktion=_seite_produktion, vergleich=_seite_vergleich, abschluss=_seite_abschluss)
BRAUCHT_RECHNUNG = ("intern", "material", "produktion", "vergleich")


def schreiben(pfad, art, r, erg=None, einst=None):
    """Dokument art (ARTEN) für die Sicht r schreiben; erg = rahmen_kalk.berechnen (für intern, material,
    produktion, vergleich Pflicht; im Kundenangebot nur für die Staffelpreise)."""
    if art not in ARTEN:
        raise ValueError(f"Unbekanntes Dokument {art}")
    if art in BRAUCHT_RECHNUNG and (not erg or erg.get("fehler")):
        raise ValueError((erg or {}).get("fehler") or "Bitte zuerst die Wirtschaftlichkeit berechnen.")
    st = ap._stile()
    titel, farbe = ARTEN[art]
    doc = BaseDocTemplate(str(pfad), pagesize=A4, leftMargin=ap.RAND_L, rightMargin=ap.RAND_R, topMargin=ap.RAND_O,
                          bottomMargin=ap.RAND_U, title=f"{titel} {r.get('nummer') or ''}",
                          author=ap.firmenname(einst) or "Rohrlaser-Kalkulation", creator="Rohrlaser-Kalkulation")
    doc.addPageTemplates([PageTemplate("blatt", [Frame(ap.RAND_L, ap.RAND_U, ap.BREITE,
                                                       ap.BLATT_H - ap.RAND_O - ap.RAND_U, leftPadding=0,
                                                       rightPadding=0, topPadding=0, bottomPadding=0)])])
    v = r.get("version") or {}
    stand = f"Stand {dt(datetime.date.today().isoformat())}" + (f"  ·  Kalkulation Version {v['nr']} vom "
                                                                f"{dt(v.get('am'))}" if v and farbe == INTERN else "")
    blatt = type("Blatt", (_Blatt,), dict(titel=titel, art=farbe, nummer=r.get("nummer") or "",
                                          firma=ap.firmenname(einst) or "", st=st, stand=stand))
    doc.build(BAUER[art](r, erg, st, einst or {}), canvasmaker=blatt)
    return pfad


def kunde_pruefen(pfad):
    """Interne Begriffe im Kunden-PDF: Liste der gefundenen Begriffe (leer = sauber)."""
    from pypdf import PdfReader
    text = " ".join(s.extract_text() or "" for s in PdfReader(str(pfad)).pages)
    return [b for b in INTERNE_BEGRIFFE if b.lower() in text.lower()]
