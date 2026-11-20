"""Angebotsakte: Datenmodell des neuen Angebots- und Kalkulationsdokuments (Patrick 18.11.2026, Entwicklungsauftrag
„Neues PDF-Angebots- und Kalkulationssystem“, Konzept https://claude.ai/artifact/4kHKywv5QaUcHUvVujTNUq).

Die Akte sammelt fertige Werte, sie rechnet keine Preise und Zeiten nach (eine zentrale Datenquelle):
- Preise, Kosten, Zeiten: die Kalkulation des Angebots (rechnen.kalkulation, im Fenster _rechnung), dieselbe Kopie
  für alle Seiten,
- Positionen, Staffeln, Konditionen: ausgabe.angebot (wie das Angebots-PDF),
- Schnittschema: der gespeicherte Schnittplan (rechnen.anzeige_stangen mit stangen_werte),
- Material je Abmessung: rechnen.material_abmessungen, Preisquelle aus den Stammdaten Preise/Lieferlängen,
- Arbeitsschritte: summen['zeiten'], Zusatzarbeiten der Kalkulationszeilen, Schweißbaugruppen (bg_zeilen),
- 3D-Bilder: PNG aus dem Zeichner des 3D-Viewers (ansicht3d.vorschaubild), vom Fenster übergeben.
Hier wird nur zusammengestellt, gruppiert und summiert, was die Kalkulation geliefert hat (Summen von Teilbeträgen,
Anteile in %). Ohne Qt; akte_pdf.py setzt das PDF.

Seiten: 1 Kundenangebot, 2 Technische Bauteilübersicht (Kunde), 3 Schnittschema, 4 Material, 5 Fertigung,
6 Zukauf (entfällt ohne Zukauf und Fremdleistung), 7 Gesamtkalkulation (intern)."""
import datetime
import hashlib
import json
import re

from . import ausgabe, rechnen
from .angebot import kein_laserteil

KUNDE, INTERN = "kunde", "intern"
SEITEN = ((1, "kunde", "Kundenangebot", KUNDE), (2, "technik", "Technische Bauteilübersicht", KUNDE),
          (3, "schnitt", "Schnittschema und Materialausnutzung", INTERN), (4, "material", "Materialkalkulation", INTERN),
          (5, "fertigung", "Fertigungskalkulation", INTERN), (6, "zukauf", "Zukauf- und Normteile", INTERN),
          (7, "gesamt", "Gesamtkalkulation", INTERN), (8, "kalkblatt", "Technisches Kalkulationsblatt", INTERN))
# Drei Dokumente aus derselben Kalkulation (Angebotswesen P2, 20.11.2026): Kundenangebot, interne Kalkulation und
# technisches Kalkulationsblatt (je Position Zeiten, Schneidwege, Vorschübe und die Kosten je Teil bis zum Preis)
ARTEN = {"kunde": ("Kundenangebot", (1, 2)), "intern": ("Interne Kalkulation", (3, 4, 5, 6, 7)),
         "technik": ("Technisches Kalkulationsblatt", (8,)),
         "gesamt": ("Angebots- und Kalkulationsdokument", (1, 2, 3, 4, 5, 6, 7, 8))}
DATEI_ZUSATZ = {"kunde": "Kunde", "intern": "Intern", "technik": "Technik", "gesamt": "Gesamt"}
OK, HINWEIS, WARNUNG, FEHLER = "OK", "HINWEIS", "WARNUNG", "FEHLER"

# Gesamtkalkulation (Seite 7): jede Kostenart der Kalkulation (rechnen.KOSTENARTEN, ohne die Zwischensummen) genau
# einmal in einer Gruppe; die Gruppen ergeben zusammen den Verkaufspreis. Stufe: 1 = Selbstkosten, 2 = danach.
GESAMT_GRUPPEN = (
    ("Materialkosten", ("material", "lagerzins"), 1),
    ("Schrotterlös Verschnitt", ("schrott",), 1),
    ("Maschinenkosten (Laser, Schneidgas)", ("laser_schneiden", "schneidgas"), 1),
    ("Rüstkosten (Maschine, Abmessungen, Stangenwechsel)", ("ruesten_maschine", "ruesten_abmessungen",
                                                           "stangenwechsel_kosten"), 1),
    ("Programmierkosten", ("programmierung",), 1),
    ("Arbeitskosten (Gewinde, Arbeitsschritte, Zusatzarbeiten, Schweißen)",
     ("gewinde", "arbeitsschritte", "zusatz", "handling_beistellung", "qualitaet", "baugruppe_eigen"), 1),
    ("Fremdleistungen (Schweißbaugruppen)", ("baugruppe_fremd",), 1),
    ("Zukaufteile (Einstand)", ("zukauf_einstand",), 1),
    ("Aufschlag Zukaufteile (statt Gewinn)", ("zukauf_aufschlag",), 1),
    ("Gemeinkosten (Zuschläge Material, Fertigung, Fremdleistung)",
     ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"), 1),
    ("Risikozuschlag (Ausschuss)", ("ausschuss",), 1),
    ("Sonstige Kosten (Pauschalen, Angebotsaufschlag)", ("pauschalen", "angebotsaufschlag"), 1),
    ("Weitere Zuschläge (Laufzeit, Neuteil, Verpackung, Finanzierung)",
     ("mannlos", "neuteil", "verpackung", "finanzierung"), 2),
    ("Gewinnaufschlag", ("gewinn",), 2),
    ("Angebotsregeln", ("regel",), 2),
    ("Fracht", ("fracht", "frachtfrei"), 2),
    ("Kundenkonditionen (Rabatt, Rundung, Skonto)", ("rabatt", "rundung", "skonto"), 2),
    ("Anhebung auf Mindestpreis", ("mindestpreis_anhebung",), 2),
    ("Muster: Anteil weiterer Abrufe", ("muster_spaeter",), 2))
_ZWISCHEN = ("herstell", "selbst", "verkauf")
assert sorted(n for _, ns, _ in GESAMT_GRUPPEN for n in ns) == sorted(
    n for _, n, _ in rechnen.KOSTENARTEN if n not in _ZWISCHEN)

# Variable Kosten für den Deckungsbeitrag: alles, was je Auftrag zugekauft oder verbraucht wird
VARIABEL = ("material", "lagerzins", "schrott", "schneidgas", "zukauf_einstand", "baugruppe_fremd", "fracht",
            "frachtfrei", "skonto")

# Art eines Arbeitsschritts für Seite 5 (Patricks Liste), nach Wörtern im Namen
SCHRITT_ARTEN = (("Entgraten", ("entgrat", "nachbearb", "gleitschl")), ("Sägen", ("säge", "saege")),
                 ("Gewinde", ("gewinde",)), ("Senken", ("senk",)), ("Flowdrill", ("flowdrill", "fließ")),
                 ("Bohren", ("bohr",)), ("Fräsen", ("fräs", "fraes")), ("Schweißen", ("schweiß", "schweiss", "naht",
                                                                                   "heft")),
                 ("Montage", ("montage", "montier", "einpress", "einniet", "zusammenbau")),
                 ("Oberfläche", ("verzink", "pulver", "lackier", "beschicht", "strahl", "eloxal")),
                 ("Prüfen", ("prüf", "pruef", "qualität", "messen", "kontrolle")),
                 ("Verpacken", ("verpack",)))
# nur €/Stück, keine Zeit (Projektregel): diese Arten zeigen die Zeit nie
NUR_STUECKPREIS = ("Gewinde", "Senken", "Flowdrill", "Bohren")

ZUKAUF_ARTEN = (("Schrauben", ("schraube", "din 912", "din 933", "iso 4762", "iso 4017", "bolzen")),
                ("Muttern", ("mutter", "din 934", "iso 4032")), ("Scheiben", ("scheibe", "din 125", "iso 7089")),
                ("Gewindeeinsätze", ("einnietmutter", "gewindeeinsatz", "helicoil", "einpressmutter", "rivkle")),
                ("Normteile", ("din ", "iso ", "norm")))


def _n(v):
    return rechnen._n(v)


def _f(v):
    """Zahl aus Zahl oder Text der Zukaufrechnung ('1.6'), sonst 0."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def geld(x):
    """Betrag wie im Dokument: 1.650,20 €."""
    t = f"{_n(x):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{t} €"


def schritt_art(name):
    t = str(name or "").lower()
    for art, woerter in SCHRITT_ARTEN:
        if any(w in t for w in woerter):
            return art
    return "Weitere"


def zukauf_art(text):
    t = f" {str(text or '').lower()} "
    for art, woerter in ZUKAUF_ARTEN:
        if any(w in t for w in woerter):
            return art
    return "Kaufteile"


def pos_text(pos):
    if isinstance(pos, float) and pos.is_integer():
        pos = int(pos)
    return "" if pos in (None, "") else str(pos)


def fingerabdruck(zeilen, summen, ang, ergebnis=None):
    """Kurzer Fingerabdruck der Kalkulation (10 Zeichen): ändert sich, sobald sich ein Preis, eine Stückzahl, der
    Verkaufspreis oder der Schnittplan ändert. Gleiche Kalkulation = gleicher Abdruck (Akte „aktuell“)."""
    teile = [round(_n(summen.get("verkauf")), 4), round(_n((ang or {}).get("netto")), 2)]
    for z in zeilen or ():
        teile.append(None if not z else (pos_text(z.get("pos")), z.get("stueck"), round(_n(z.get("preis_teil")), 4)))
    teile.append((ergebnis or {}).get("kennung") if isinstance((ergebnis or {}).get("kennung"), (str, int)) else
                 len((ergebnis or {}).get("stangen") or ()))
    return hashlib.sha256(json.dumps(teile, default=str).encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ Seite 1: Kundenangebot
def _kunde(kopf, ang, einst, positionen, k):
    bis = ausgabe.gueltig_bis(kopf, einst, positionen, k)
    ap = (ang or {}).get("ansprechpartner") or {}
    texte = [t for t in ((ang or {}).get(n) for n in ("rahmen", "beistellung", "muster", "mindestpreis", "fracht"))
             if t]
    return dict(nummer=kopf.get("nummer") or "", datum=kopf.get("datum"), gueltig_bis=bis.isoformat() if bis else None,
                gueltig_tage=(ang or {}).get("gueltig_tage"), kundennr=kopf.get("kundennr") or "",
                kunde=kopf.get("kunde") or "", anschrift=list((ang or {}).get("anschrift") or ()),
                ansprechpartner=dict(name=ap.get("name") or "", telefon=ap.get("telefon") or "",
                                     email=ap.get("email") or ""),
                kundenreferenz=(ang or {}).get("kundenreferenz") or kopf.get("kundenreferenz") or "",
                zeilen=[dict(art=z.get("art"), pos=pos_text(z.get("pos")), artikel=z.get("artikel") or "",
                             text=z.get("text") or "", menge=z.get("menge"), einheit=z.get("einheit") or "Stk.",
                             preis=z.get("preis"), gesamt=z.get("gesamt"), muster=bool(z.get("muster")),
                             staffeln=[dict(bereich=s.get("bereich"), menge=s.get("menge"), preis=s.get("preis"),
                                            gesamt=s.get("gesamt")) for s in z.get("staffeln") or ()])
                        for z in (ang or {}).get("zeilen") or ()],
                netto=_n((ang or {}).get("netto")), mwst=_n((ang or {}).get("mwst")),
                brutto=_n((ang or {}).get("brutto")), mwst_satz=_n((ang or {}).get("mwst_satz")),
                lieferzeit=re.sub(r"^Lieferzeit:\s*", "", (ang or {}).get("lieferzeit") or "").rstrip(".") or "",
                zahlung=(ang or {}).get("zahlung") or "", bedingungen=(ang or {}).get("bedingungen") or "",
                texte=texte)


# ------------------------------------------------------------------ Seite 2: Technik
def _technik(positionen, zeilen, k, bilder):
    out = []
    for i, p in enumerate(positionen):
        if not p:
            continue
        art = p.get("art") or "Rohrteil"
        pid, wid = p.get("profil_id"), p.get("werkstoff_id")
        w = (k.werkstoffe.get(wid) or {}) if k and wid else {}
        pr = (k.profile.get(pid) or {}) if k and pid else {}
        laser = not kein_laserteil(p)
        bearb = ausgabe.bearbeitung_text(p) if laser else ""
        bearb = bearb[len("Bearbeitung: "):] if bearb.startswith("Bearbeitung: ") else bearb
        extra = []
        if laser and str(p.get("gewinde") or "").strip():
            extra.append(f"Gewinde {p['gewinde']}")
        if laser and p.get("gravur") in ("ja", True, 1):
            extra.append("Gravur")
        if laser and str(p.get("zusatz") or "").strip():
            extra.append(str(rechnen.zusatz_text(p) or "").strip())
        if kein_laserteil(p) and art == "Zukaufteil":
            bearb = ausgabe.zukaufteil_text(p)
        hinweise = []
        if p.get("muster") == "ja":
            hinweise.append("Musterteil")
        if (zeilen[i] or {}).get("kundenmaterial") if i < len(zeilen) else False:
            hinweise.append("Material vom Kunden beigestellt")
        if str(p.get("satz") or "").strip():
            hinweise.append(f"Teil von Satz {p['satz']}")
        out.append(dict(index=i, id=p.get("id"), pos=pos_text(p.get("pos")), artikel=p.get("artikel") or "",
                        bezeichnung=p.get("bezeichnung") or "", art=art, laser=laser, profil=pid or "",
                        form=pr.get("form") or "", wand=pr.get("wand"),
                        material=w.get("kategorie") or "", guete=wid or "", werkstoff=w.get("werkstoff") or "",
                        norm=w.get("norm") or "", oberflaeche=p.get("oberflaeche") or "",
                        laenge=p.get("laenge") if laser else None, stueck=p.get("stueck"),
                        bearbeitung=", ".join(x for x in [bearb] + extra if x), hinweise=hinweise,
                        bild=(bilder or {}).get(p.get("id"))))
    return out


# ------------------------------------------------------------------ Seite 3: Schnittschema
def _muster_schluessel(s):
    return (s.get("profil"), s.get("werkstoff"), s.get("oberflaeche") or "", round(_n(s.get("stange")), 1),
            round(_n(s.get("end")), 1), round(_n(s.get("greif")), 1),
            tuple((pos_text(t.get("pos")), round(_n(t.get("von")), 1), round(_n(t.get("bis")), 1), t.get("lage"),
                   round(_n(t.get("eingespart_mm")), 1)) for t in s.get("teile") or ()))


def _schnitt(ergebnis, kopf, positionen, k, tabellen, aktuell, zeilen):
    stangen = (ergebnis or {}).get("stangen") or []
    if not stangen:
        return dict(vorhanden=False, aktuell=aktuell, gruppen=[], summe={}, nicht_eingeplant=_nicht_eingeplant(zeilen,
                                                                                                             ergebnis))
    sw = rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)
    anzeige = rechnen.anzeige_stangen(ergebnis, sw)
    gruppen, muster = {}, {}
    zaehler = {}                         # Pos -> laufende Teilnummer im ganzen Angebot
    for s, w in anzeige:
        w = w or {}
        gk = (s.get("profil"), s.get("werkstoff"), s.get("oberflaeche") or "", s.get("stange"))
        g = gruppen.setdefault(gk, dict(profil=s.get("profil"), werkstoff=s.get("werkstoff"),
                                        oberflaeche=s.get("oberflaeche") or "", stange=s.get("stange"), muster=[],
                                        stangen=0, meter=0.0, nutz=0.0, kg=0.0, kosten=0.0, rest=0.0))
        mk = _muster_schluessel(s)
        m = muster.get((gk, mk))
        if m is None:
            teile = []
            for t in s.get("teile") or ():
                teile.append(dict(pos=pos_text(t.get("pos")), artikel=t.get("artikel") or "", laenge=_n(t.get("laenge")),
                                  von=_n(t.get("von")), bis=_n(t.get("bis")), lage=t.get("lage"),
                                  gemeinsam=_n(t.get("eingespart_mm")) > 0, naht=t.get("naht_text") or ""))
            m = muster[(gk, mk)] = dict(stange=_n(s.get("stange")), end=_n(s.get("end")), greif=_n(s.get("greif")),
                                        verlust=_n(s.get("verlust")), teile=teile, nummern=[], anzahl=0,
                                        summe=_n(w.get("summe")), rest=_n(w.get("rest")),
                                        ausnutzung=w.get("ausnutzung"), zugeschnitten=bool(s.get("zugeschnitten")),
                                        teilnummern={}, rest_frei=max(0.0, _n(s.get("stange")) - _n(s.get("greif"))
                                                                       - max([_n(s.get("end"))] + [
                                                                           _n(t.get("bis")) for t in s.get("teile") or ()])))
            g["muster"].append(m)
        m["anzahl"] += 1
        m["nummern"].append(s.get("nr"))
        for t in m["teile"]:
            zaehler[t["pos"]] = zaehler.get(t["pos"], 0) + 1
            m["teilnummern"].setdefault(t["pos"], []).append(zaehler[t["pos"]])
        g["stangen"] += 1
        g["meter"] += _n(s.get("stange")) / 1000
        g["nutz"] += _n(w.get("summe")) / 1000
        g["kg"] += _n(w.get("gewicht"))
        g["kosten"] += _n(w.get("kosten"))
        g["rest"] += m["rest_frei"] / 1000
    liste = list(gruppen.values())
    for g in liste:
        g["ausnutzung"] = g["nutz"] / g["meter"] if g["meter"] else None
        g["verschnitt"] = g["meter"] - g["nutz"]
        for m in g["muster"]:
            m["schnitte"] = len(m["teile"])
    meter = sum(g["meter"] for g in liste)
    nutz = sum(g["nutz"] for g in liste)
    summe = dict(stangen=sum(g["stangen"] for g in liste), lieferstangen=len(stangen), meter=meter, nutz=nutz,
                 verschnitt=meter - nutz, rest=sum(g["rest"] for g in liste), kg=sum(g["kg"] for g in liste),
                 kosten=sum(g["kosten"] for g in liste), ausnutzung=nutz / meter if meter else None)
    return dict(vorhanden=True, aktuell=aktuell, gruppen=liste, summe=summe,
                nicht_eingeplant=_nicht_eingeplant(zeilen, ergebnis))


def _nicht_eingeplant(zeilen, ergebnis):
    out = []
    for z in zeilen or ():
        if z and _n(z.get("nicht_eingeplant")) > 0:
            out.append(dict(pos=pos_text(z.get("pos")), artikel=z.get("artikel") or "",
                            anzahl=int(_n(z.get("nicht_eingeplant")))))
    for f in (ergebnis or {}).get("fehler") or ():
        out.append(dict(pos="", artikel="", anzahl=0, text=str(f)))
    return out


# ------------------------------------------------------------------ Seite 4: Material
def preis_quelle(pid, wid, laenge, k, tabellen):
    """Preiszeile aus den Stammdaten (Lieferlänge, sonst Preise) wie rechnen.preis_herkunft: dict(preis, basis,
    lieferant, gueltig_ab, quelle) oder Tonnenpreis des Werkstoffs; nur gelesen."""
    try:
        z = next((r for r in rechnen.lieferlaengen(pid, wid, k, tabellen, auto=False)
                  if _n(r.get("laenge")) == _n(laenge)), None)
        quelle = "Lieferlängen"
        if z is None:
            z, quelle = rechnen.preis_zeile(pid, wid, k, tabellen), "Preise"
    except Exception:       # noqa: BLE001 – Angabe fehlt dann
        z, quelle = None, ""
    if z is None or rechnen._leer(z.get("basis")):
        t = (k.werkstoffe.get(wid) or {}).get("tonnenpreis") if k else None
        return dict(preis=_n(t) if t else None, basis="€/t" if t else "", lieferant="", gueltig_ab=None,
                    quelle="Tonnenpreis Werkstoff" if t else "kein Preis hinterlegt")
    return dict(preis=_n(z.get("preis")), basis=z.get("basis") or "", lieferant=z.get("lieferant") or "",
                gueltig_ab=z.get("gueltig_ab"), quelle=quelle)


def _material(kopf, positionen, ergebnis, k, tabellen, zeilen, summen, einst, schnitt):
    abm = rechnen.material_abmessungen(kopf, positionen, ergebnis, k, tabellen)
    rest_min = _n(einst.get("rest_min_laenge"))
    reste = {}
    for g in schnitt.get("gruppen") or ():
        for m in g["muster"]:
            if rest_min > 0 and m["rest_frei"] >= rest_min:
                reste[(g["profil"], g["werkstoff"], g["oberflaeche"], g["stange"])] = reste.get(
                    (g["profil"], g["werkstoff"], g["oberflaeche"], g["stange"]), 0.0) + m["rest_frei"] / 1000 * m["anzahl"]
    gruppen = []
    for a in abm:
        pr = (k.profile.get(a["profil"]) or {}) if k else {}
        w = (k.werkstoffe.get(a["werkstoff"]) or {}) if k else {}
        q = preis_quelle(a["profil"], a["werkstoff"], a["stange"], k, tabellen)
        eur_m = a["manuell"] if a.get("manuell") else a.get("wirksam")
        kg_m = _n(a.get("kg_m"))
        verschnitt = max(0.0, _n(a["meter"]) - _n(a["nutz_m"]))
        ausn = a.get("ausnutzung")
        rest_m = reste.get((a["profil"], a["werkstoff"], a["oberflaeche"] or "", a["stange"]), 0.0)
        gruppen.append(dict(profil=a["profil"], form=pr.get("form") or "", wand=pr.get("wand"),
                            werkstoff=a["werkstoff"], material=w.get("kategorie") or "",
                            werkstoff_name=w.get("werkstoff") or "", oberflaeche=a.get("oberflaeche") or "",
                            lieferant=q["lieferant"], preis=q["preis"], basis=q["basis"], gueltig_ab=q["gueltig_ab"],
                            quelle=q["quelle"], eur_m=_n(eur_m) if eur_m is not None else None,
                            eur_kg=(_n(eur_m) / kg_m) if eur_m and kg_m else None, kg_m=kg_m, hand=bool(a.get("manuell")),
                            kunde=bool(a.get("kunde")), stange=a["stange"], laengen=dict(a.get("laengen") or {}),
                            positionen=[pos_text(x) for x in a["positionen"]], teile_m=_n(a["teile_m"]),
                            stangen=a["stangen"], meter=_n(a["meter"]), kg=_n(a["kg"]), kosten=_n(a["kosten"]),
                            nutz_m=_n(a["nutz_m"]), ausnutzung=ausn, verschnitt_m=verschnitt,
                            verschnitt_eur=_n(a["kosten"]) * (1 - ausn) if ausn is not None else 0.0,
                            rest_m=rest_m, restwert=rest_m * _n(eur_m) if eur_m else 0.0, fehlt=a.get("fehlt")))
    teile = []
    for p, z in zip(positionen, zeilen):
        if not z or not p or kein_laserteil(p):
            continue
        teile.append(dict(pos=pos_text(p.get("pos")), artikel=p.get("artikel") or "", profil=p.get("profil_id") or "",
                          werkstoff=p.get("werkstoff_id") or "", laenge=_n(p.get("laenge")), stueck=_n(z.get("stueck")),
                          teil=_n(z.get("material_teil")), gesamt=_n(z.get("material_position")),
                          kunde=bool(z.get("kundenmaterial"))))
    return dict(gruppen=gruppen, teile=teile, material=_n(summen.get("material")), schrott=_n(summen.get("schrott")),
                lagerzins=_n(summen.get("lagerzins")), rest_min=rest_min,
                ausschuss_material=_n(summen.get("ausschuss_material")),
                schnitt_kosten=sum(g["kosten"] for g in gruppen))


# ------------------------------------------------------------------ Seite 5: Fertigung
def _fertigung(kopf, positionen, zeilen, summen, k, bearbeitungen):
    zeiten = {z.get("schritt"): z for z in summen.get("zeiten") or ()}

    def zeit(name):
        return _n((zeiten.get(name) or {}).get("gesamt_min"))

    def kosten(name):
        return _n((zeiten.get(name) or {}).get("kosten"))
    m = (k.maschinen.get(kopf.get("maschine")) or {}) if k else {}
    laser = dict(maschine=kopf.get("maschine") or "", maschine_name=m.get("name") or m.get("bezeichnung") or "",
                 satz=_n(summen.get("satz_maschine")), satz_laser=_n(summen.get("satz_laser")),
                 schneid_min=zeit("Laser schneiden"), schneid_eur=kosten("Laser schneiden"),
                 gas_eur=kosten("Schneidgas"), gas_m3=_n(summen.get("gas_m3")),
                 ruest_min=zeit("Rüsten Maschine") + zeit("Rüsten je Abmessung"),
                 ruest_eur=_n(summen.get("ruesten_maschine")) + _n(summen.get("ruesten_abmessungen")),
                 wechsel=int(_n(summen.get("stangenwechsel"))), wechsel_min=zeit("Stangenwechsel"),
                 wechsel_eur=_n(summen.get("stangenwechsel_kosten")),
                 bereit_min=zeit("Materialbereitstellung"), bereit_eur=kosten("Materialbereitstellung"),
                 prog_min=zeit("Programmierung"), prog_eur=_n(summen.get("programmierung")),
                 laeufe=int(_n(summen.get("laeufe"))), teile=int(_n(summen.get("teile"))))
    laser["lauf_min"] = laser["schneid_min"] + laser["ruest_min"] + laser["wechsel_min"]
    laser["handling_min"] = laser["wechsel_min"] + laser["bereit_min"]
    laser["handling_eur"] = laser["wechsel_eur"] + laser["bereit_eur"]
    # Arbeitsschritte des Angebots (Vorgabe Arbeitsschritte, Personal), ohne die oben einzeln gezeigten
    oben = {"Laser schneiden", "Schneidgas", "Rüsten Maschine", "Rüsten je Abmessung", "Stangenwechsel",
            "Materialbereitstellung", "Programmierung", "Gewinde", "Gewinde Festpreis", "Zusatzarbeiten mit Zeit",
            "Zusatzarbeiten (€)", "Schweißbaugruppen", "Schweißbaugruppen Fremdleistung (€)", "Ausschuss"}
    angebot_schritte = [dict(name=z.get("schritt"), art=schritt_art(z.get("schritt")), menge=z.get("menge"),
                             einheit=z.get("einheit") or "", min=_n(z.get("gesamt_min")), satz=_n(z.get("satz")),
                             eur=_n(z.get("kosten")), quelle=z.get("quelle") or "")
                        for z in summen.get("zeiten") or () if z.get("schritt") not in oben
                        and (_n(z.get("kosten")) or _n(z.get("gesamt_min")))]
    schritte = []                       # je Position: jeder Arbeitsschritt einzeln
    for i, (p, z) in enumerate(zip(positionen, zeilen)):
        if not p or not z:
            continue
        stk = _n(z.get("stueck"))
        pos = pos_text(p.get("pos"))
        if _n(z.get("gewinde_teil")) or _n(z.get("gewinde_preis")):
            je = _n(z.get("gewinde_teil")) or _n(z.get("gewinde_preis"))
            schritte.append(dict(pos=pos, name=f"Gewinde {p.get('gewinde') or ''}".strip(), art="Gewinde",
                                 menge=stk, einheit="Stk.", je=je, eur=je * stk, min=None, fremd=False))
        for e in z.get("zusatzarbeiten") or ():
            je = _n(e.get("teil"))
            art = schritt_art(e.get("name"))
            schritte.append(dict(pos=pos, name=e.get("name") or "", art=art, menge=stk, einheit="Stk.", je=je,
                                 eur=je * stk, fremd=bool(e.get("fremd")), basis=f"{rechnen.zahl(_n(e.get('menge')), 2)} "
                                 f"{e.get('einheit') or ''}".strip() if e.get("menge") not in (None, "") else "",
                                 min=None if art in NUR_STUECKPREIS else (_n(e.get("arbeit_s")) * stk / 60 or None)))
        for b in z.get("bg_zeilen") or ():
            fak = _n(b.get("faktor")) or 1.0
            eur_teil = _n(b.get("kosten")) * fak
            schritte.append(dict(pos=pos, name=b.get("name") or b.get("art") or "", art=schritt_art(
                f"{b.get('art')} {b.get('name')}") if b.get("art") != "Naht" else "Schweißen", menge=stk,
                einheit="Stk.", je=eur_teil, eur=eur_teil * stk + _n(b.get("einmal")),
                min=_n(b.get("zeit_min")) * fak * stk or None, fremd=bool(b.get("fremd")),
                basis=(b.get("werte") or {}).get("rechenweg") or ""))
    laser_teile = []
    for pos, liste in bearbeitungen or ():
        if liste:
            laser_teile.append(dict(pos=pos_text(pos), s=sum(_n(x.get("s")) for x in liste),
                                    eur=sum(_n(x.get("eur")) for x in liste), n=len(liste)))
    je_pos = []
    for p, z in zip(positionen, zeilen):
        if not p or not z or kein_laserteil(p):
            continue
        je_pos.append(dict(pos=pos_text(p.get("pos")), artikel=p.get("artikel") or "", stueck=_n(z.get("stueck")),
                           laser_s=_n(z.get("laser_netto")), laser_teil=_n(z.get("laser_teil")),
                           ruesten_teil=_n(z.get("ruesten_teil")), prog_teil=_n(z.get("programmierung_anteil")),
                           einstiche=_n(z.get("einstiche_teil")), schneidweg=sum(_n(z.get(n)) for n in (
                               "mm_gross", "mm_mittel", "mm_klein", "mm_gravur"))))
    return dict(laser=laser, angebot_schritte=angebot_schritte, schritte=schritte, je_pos=je_pos,
                laser_teile=laser_teile, zuschlag_fertigung=_n(summen.get("zuschlag_fertigung")),
                ausschuss_fertigung=_n(summen.get("ausschuss_fertigung")), baugruppe_eigen=_n(summen.get(
                    "baugruppe_eigen")), baugruppe_fremd=_n(summen.get("baugruppe_fremd")))


# ------------------------------------------------------------------ Seite 6: Zukauf
def _zukauf(positionen, summen, fertigung):
    artikel = []
    for g in summen.get("zukauf") or ():
        if not g:
            continue
        st, b = g.get("stand") or {}, g.get("bestellung") or {}
        nummern = []
        for schl in g.get("schluessel") or ():
            i = schl[0] if isinstance(schl, (list, tuple)) and schl else None
            if isinstance(i, int) and i < len(positionen):
                t = pos_text(positionen[i].get("pos"))
                if t and t not in nummern:
                    nummern.append(t)
        menge = _f(b.get("bestellt") or b.get("verbrauch"))
        einstand, aufschlag = _f(g.get("einstand")), _f(g.get("aufschlag"))
        artikel.append(dict(art=zukauf_art(f"{st.get('bezeichnung') or ''} {st.get('kategorie') or ''} "
                                           f"{st.get('artikelnr') or ''}"),
                            artikelnr=st.get("artikelnr") or "", lieferant=b.get("lieferant") or "",
                            bezeichnung=st.get("bezeichnung") or "", einheit=st.get("einheit") or "",
                            menge=menge, ek=_f(b.get("ek")), einstand=einstand, aufschlag=aufschlag,
                            regel=g.get("regel") or "", gesamt=einstand + aufschlag,
                            einzel=(einstand + aufschlag) / menge if menge else 0.0, positionen=nummern,
                            satz=(aufschlag / einstand) if einstand else None,
                            hinweis="; ".join(x for x in (g.get("fehler"), g.get("warnung")) if x)))
    fremd = [dict(s) for s in fertigung.get("schritte") or () if s.get("fremd")]
    return dict(artikel=artikel, fremd=fremd, einstand=_n(summen.get("zukauf_einstand")),
                aufschlag=_n(summen.get("zukauf_aufschlag")), fehlt=int(_n(summen.get("zukauf_fehlt"))),
                zuschlag_fremd=_n(summen.get("zuschlag_fremdleistung")))


# ------------------------------------------------------------------ Seite 7: Gesamt
def _gesamt(summen, zeilen, positionen, ang, einst):
    gruppen = []
    for titel, namen, stufe in GESAMT_GRUPPEN:
        betrag = sum(_n(summen.get(n)) for n in namen)
        gruppen.append(dict(titel=titel, betrag=betrag, stufe=stufe, namen=namen))
    verkauf = _n(summen.get("verkauf"))
    selbst = _n(summen.get("selbst"))
    gewinn = _n(summen.get("gewinn"))
    variabel = sum(_n(summen.get(n)) for n in VARIABEL)
    zukauf = _n(summen.get("zukauf_einstand")) + _n(summen.get("zukauf_aufschlag"))
    basis = summen.get("gewinn_stufen_basis")
    basis = _n(basis) if basis is not None else max(0.0, selbst - zukauf)
    teile = int(_n(summen.get("teile")))
    je_pos = []
    for p, z in zip(positionen, zeilen):
        if not p or not z:
            continue
        preis, stk = _n(z.get("preis_teil")), _n(z.get("stueck"))
        teil_von = ""
        if p.get("art") != "Schweißbaugruppe" and not rechnen._leer(p.get("baugruppe")):
            teil_von = "Teil der Schweißbaugruppe (Preis im Satz)"
        elif not rechnen._leer(p.get("satz")):
            teil_von = f"Teil von Satz {p.get('satz')}"
        je_pos.append(dict(pos=pos_text(p.get("pos")), artikel=p.get("artikel") or "", stueck=stk, teil_von=teil_von,
                           selbst=_n(z.get("selbst_teil")), gewinn=_n(z.get("gewinn_teil")), preis=preis,
                           gesamt=_n(z.get("preis_position")), marge=_n(z.get("gewinn_teil")) / preis if preis else None))
    netto = _n((ang or {}).get("netto"))
    return dict(gruppen=gruppen, herstell=_n(summen.get("herstell")), selbst=selbst, verkauf=verkauf,
                verkauf_kalkuliert=_n(summen.get("verkauf_kalkuliert")) or verkauf, angebot_netto=netto,
                rundung_stueck=netto - verkauf, gewinn=gewinn, gewinn_satz=summen.get("gewinn_satz"),
                gewinn_gestaffelt=bool(summen.get("gewinn_gestaffelt")), gewinn_basis=basis,
                variabel=variabel, deckungsbeitrag=verkauf - variabel,
                marge=gewinn / verkauf if verkauf else None, db_satz=(verkauf - variabel) / verkauf if verkauf else None,
                teile=teile, je_teil=verkauf / teile if teile else None, je_pos=je_pos,
                verschnitt_eur=None, untergrenze_kurz=_n(summen.get("untergrenze_kurz")),
                untergrenze_lang=_n(summen.get("untergrenze_lang")), skonto_satz=_n(summen.get("skonto_satz")),
                mwst_satz=_n((ang or {}).get("mwst_satz")) or _n(einst.get("mwst")))


# ------------------------------------------------------------------ Seite 8: Technisches Kalkulationsblatt
# Schneidwege je Teil: (Text, Weg, Vorschub, Zeit) als Schlüssel der Kalkulationszeile
KB_WEGE = (("Kontur groß und Trennschnitt", "mm_gross", "vorschub_gross", "zeit_gross"),
           ("Kontur mittel", "mm_mittel", "vorschub_mittel", "zeit_mittel"),
           ("Kontur klein", "mm_klein", "vorschub_klein", "zeit_klein"),
           ("Gravur", "mm_gravur", "vorschub_gravur", "zeit_gravur"))
# weitere Zeitanteile je Teil (rechnen.ZEITANTEILE ohne die Schneidwege)
KB_ZEITEN = (("Anfahren und Drehen", "zeit_anfahren"), ("Mehrzeit 3D", "zeit_d3"), ("Ecken und Radien", "zeit_ecken"),
             ("Anschlag doppelt", "zeit_doppel"), ("Nebenzeit je Teil", "zeit_neben"),
             ("Drehen je Seitenwechsel", "zeit_drehen"), ("Messzyklen", "zeit_messen"),
             ("Anfahrweg je Innenkontur", "zeit_anfahrweg"), ("Abfall zerteilen", "zeit_abfall"),
             ("Entnahme von Hand", "zeit_entnahme"), ("Zusatzzeit", "zeit_extra"),
             ("Prüfzeit Anbauteile", "zeit_pruefung"))
# Kosten je Teil bis zu den Herstellkosten; die Summe ist genau herstell_teil der Kalkulation (rechnen.kalkulation)
KB_HERSTELL = (("Material", "material_teil"), ("Schrotterlös Verschnitt", "schrott_teil"),
               ("Lagerzins", "lagerzins_teil"), ("Ausschuss Material", "ausschuss_mat_teil"),
               ("Zuschlag Material", "zuschlag_material_teil"), ("Laser schneiden", "laser_schneiden_teil"),
               ("Schneidgas", "schneidgas_teil"), ("Gewinde (€/Stück)", "gewinde_teil"),
               ("Ausschuss Fertigung", "ausschuss_fert_teil"), ("Rüsten Maschine", "ruesten_maschine_teil"),
               ("Stangenwechsel", "stangenwechsel_teil"), ("Rüsten je Abmessung", None),
               ("Weitere Arbeitsschritte", "arbeit_teil"), ("Zusatzarbeiten", "zusatz_eigen_teil"),
               ("Handling Kundenmaterial", "handling_teil"), ("Qualität (Prüfplan)", "qualitaet_teil"),
               ("Zuschlag Fertigung", "zuschlag_fertigung_teil"), ("Fremdleistungen", "zusatz_fremd_teil"),
               ("Zuschlag Fremdleistung", "zuschlag_fremdleistung_teil"),
               ("Schweißen und Arbeitsgänge (Baugruppe)", "bg_eigen_teil"),
               ("Fremdleistungen (Baugruppe)", "bg_fremd_teil"))
KB_SELBST = (("Programmierung", "programmierung_anteil"), ("Pauschale je Abmessung", "pauschale_abm_teil"),
             ("Angebotsaufschlag", "angebotsaufschlag_teil"), ("Zukaufteile (Einstand)", "zukauf_einstand_teil"),
             ("Aufschlag Zukaufteile", "zukauf_aufschlag_teil"))


def _kalkblatt(kopf, positionen, zeilen, k, ang):
    """Je Position die technischen Grundlagen und die Kosten je Teil. Alle Werte sind die der Kalkulation; die
    Kostenzeilen ergeben je Stufe genau Herstellkosten, Selbstkosten und Preis je Teil."""
    vk = {}
    for z in (ang or {}).get("zeilen") or ():
        if z.get("pos") not in (None, "") and z.get("preis") is not None:
            vk.setdefault(pos_text(z.get("pos")), _n(z.get("preis")))
    out = []
    for p, z in zip(positionen, zeilen):
        if not p or not z:
            continue
        stk = _n(z.get("stueck"))
        pid, wid = p.get("profil_id"), p.get("werkstoff_id")
        w = (k.werkstoffe.get(wid) or {}) if k and wid else {}
        laser = not kein_laserteil(p)
        wege = []
        if laser:
            for text, mm_, v, t in KB_WEGE:
                if _n(z.get(mm_)) or _n(z.get(t)):
                    wege.append(dict(text=text, mm=_n(z.get(mm_)), vorschub=z.get(v), s=_n(z.get(t))))
            if _n(z.get("einstiche_teil")) or _n(z.get("zeit_einstiche")):
                wege.append(dict(text="Einstiche", anzahl=_n(z.get("einstiche_teil")), einstechzeit=z.get(
                    "einstechzeit"), s=_n(z.get("zeit_einstiche"))))
        zeiten = [dict(text=t, s=_n(z.get(n))) for t, n in KB_ZEITEN if laser and _n(z.get(n))]
        kosten, summe = [], 0.0
        bg = bool(z.get("baugruppe"))
        for text, n in KB_HERSTELL:
            if bg and n == "material_teil":
                continue        # Schnellkalkulation der Baugruppe: Material pauschal in den Selbstkosten
            if n is None:       # Rüsten je Abmessung: Rest des Rüstens je Teil, damit die Summe stimmt
                eur = _n(z.get("ruesten_teil")) - _n(z.get("ruesten_maschine_teil")) - _n(z.get("stangenwechsel_teil"))
            else:
                eur = _n(z.get(n))
            summe += eur
            if abs(eur) > 5e-7:
                kosten.append(dict(text=text, teil=eur, position=eur * stk, stufe=0))
        herstell = _n(z.get("herstell_teil"))
        if abs(summe - herstell) > 1e-6:
            kosten.append(dict(text="Abgleich (Rundung, ältere Rechnung)", teil=herstell - summe,
                               position=(herstell - summe) * stk, stufe=0))
        kosten.append(dict(text="Herstellkosten", teil=herstell, position=herstell * stk, stufe=1))
        summe = herstell
        for text, n in ((("Material pauschal (Baugruppe)", "material_teil"),) if bg else ()) + KB_SELBST:
            eur = _n(z.get(n))
            summe += eur
            if abs(eur) > 5e-7:
                kosten.append(dict(text=text, teil=eur, position=eur * stk, stufe=0))
        selbst = _n(z.get("selbst_teil"))
        if abs(summe - selbst) > 1e-6:
            kosten.append(dict(text="Abgleich (Rundung, ältere Rechnung)", teil=selbst - summe,
                               position=(selbst - summe) * stk, stufe=0))
        kosten.append(dict(text="Selbstkosten", teil=selbst, position=selbst * stk, stufe=1))
        preis = _n(z.get("preis_teil"))
        rest = preis - selbst
        for text, n in (("Gewinn", "gewinn_teil"), ("Fracht", "fracht_teil"), ("Skonto", "skonto_teil")):
            eur = _n(z.get(n))
            rest -= eur
            if abs(eur) > 5e-7:
                kosten.append(dict(text=text, teil=eur, position=eur * stk, stufe=0))
        if abs(rest) > 5e-5:
            kosten.append(dict(text="Mindestpreis, Muster und Übriges", teil=rest, position=rest * stk, stufe=0))
        kosten.append(dict(text="Preis je Teil laut Kalkulation", teil=preis, position=_n(z.get("preis_position"))
                           or preis * stk, stufe=1))
        out.append(dict(pos=pos_text(p.get("pos")), artikel=p.get("artikel") or "", bezeichnung=p.get(
            "bezeichnung") or "", art=p.get("art") or "Rohrteil", laser=laser, profil=pid or "",
            werkstoff=" ".join(x for x in (wid or "", f"({w.get('kategorie')})" if w.get("kategorie") else "") if x),
            laenge=p.get("laenge") if laser else None, stueck=stk,
            maschine=p.get("maschine") or kopf.get("maschine") or "", gas=z.get("gas") or "",
            wand_stufe=z.get("wand_stufe"), sd_herkunft=z.get("sd_herkunft") or "",
            zeit_manuell=bool(z.get("zeit_manuell")), wege=wege, zeiten=zeiten,
            laser_brutto=_n(z.get("laser_brutto")), laser_netto=_n(z.get("laser_netto")),
            einsparung=_n(z.get("einsparung")), faktor=_n(z.get("faktor_laserzeit")) or 1.0,
            kosten=kosten, herstell=herstell, selbst=selbst, preis=preis, vk_angebot=vk.get(pos_text(p.get("pos"))),
            marge=_n(z.get("gewinn_teil")) / preis if preis else None, hinweis=z.get("hinweis") or ""))
    return out


# ------------------------------------------------------------------ Zusammenstellen und prüfen
def sammeln(kopf, positionen, ergebnis, k, tabellen, einst, zeilen, summen, ang, bilder=None, bearbeitungen=None,
            aktuell=True, bearbeiter="", jetzt=None):
    """Akte aus den fertigen Werten des Angebots. zeilen/summen = eine Kalkulation (rechnen.kalkulation), ang =
    ausgabe.angebot mit denselben Zeilen, bilder = {Positions-ID: PNG-Bytes}, bearbeitungen = [(Pos., Liste)]
    (bearbeitung.fuer_position), aktuell = Schnittplan passt zum Angebot. Ergebnis: dict je Seite plus kopf,
    fingerabdruck, pruefung."""
    zeilen = list(zeilen or ())
    positionen = list(positionen or ())
    jetzt = jetzt or datetime.datetime.now()
    akte = dict(erstellt=jetzt.isoformat(timespec="minutes"), bearbeiter=bearbeiter or "",
                nummer=kopf.get("nummer") or "", kunde_name=kopf.get("kunde") or "",
                fingerabdruck=fingerabdruck(zeilen, summen, ang, ergebnis), fehler_seiten={})
    teile = (("kunde", lambda: _kunde(kopf, ang, einst, positionen, k)),
             ("technik", lambda: _technik(positionen, zeilen, k, bilder)),
             ("schnitt", lambda: _schnitt(ergebnis, kopf, positionen, k, tabellen, aktuell, zeilen)))
    for name, f in teile:
        akte[name] = _sicher(akte, name, f)
    akte["material"] = _sicher(akte, "material", lambda: _material(kopf, positionen, ergebnis, k, tabellen, zeilen,
                                                                   summen, einst, akte.get("schnitt") or {}))
    akte["fertigung"] = _sicher(akte, "fertigung", lambda: _fertigung(kopf, positionen, zeilen, summen, k,
                                                                      bearbeitungen))
    akte["zukauf"] = _sicher(akte, "zukauf", lambda: _zukauf(positionen, summen, akte.get("fertigung") or {}))
    akte["gesamt"] = _sicher(akte, "gesamt", lambda: _gesamt(summen, zeilen, positionen, ang, einst))
    akte["kalkblatt"] = _sicher(akte, "kalkblatt", lambda: _kalkblatt(kopf, positionen, zeilen, k, ang))
    if akte.get("gesamt") and akte.get("material"):
        akte["gesamt"]["verschnitt_eur"] = sum(g["verschnitt_eur"] for g in akte["material"]["gruppen"])
    akte["pruefung"] = pruefen(akte, summen)
    return akte


def _sicher(akte, name, f):
    """Eine Seite nie am Ganzen scheitern lassen: Fehler merken (Prüfliste), Seite bleibt leer."""
    from . import protokoll
    try:
        return f()
    except Exception as e:      # noqa: BLE001
        protokoll.warnung(f"Angebotsakte: Seite {name} übersprungen ({type(e).__name__}: {e})")
        akte["fehler_seiten"][name] = f"{type(e).__name__}: {e}"
        return [] if name in ("technik", "kalkblatt") else {}


def zukauf_vorhanden(akte):
    z = akte.get("zukauf") or {}
    return bool(z.get("artikel") or z.get("fremd"))


def seiten_fuer(art, akte=None, auswahl=None):
    """Seitennummern eines Dokuments (art kunde/intern/gesamt), nur die gewählten; Seite 6 nur mit Zukauf."""
    nummern = [n for n in ARTEN[art][1] if auswahl is None or n in auswahl]
    if akte is not None and not zukauf_vorhanden(akte):
        nummern = [n for n in nummern if n != 6]
    return nummern


def pruefen(akte, summen=None):
    """Prüfliste vor der Freigabe (Auftrag Abschnitt 8): [(Stufe, Text)], Stufe OK/HINWEIS/WARNUNG/FEHLER."""
    out = []
    k = akte.get("kunde") or {}
    g = akte.get("gesamt") or {}
    s = akte.get("schnitt") or {}
    m = akte.get("material") or {}
    for name, fehler in (akte.get("fehler_seiten") or {}).items():
        out.append((FEHLER, f"Seite „{name}“ konnte nicht zusammengestellt werden: {fehler}"))
    zeilen = k.get("zeilen") or []
    summe_pos = round(sum(_n(z.get("gesamt")) for z in zeilen), 2)
    if zeilen and abs(summe_pos - round(_n(k.get("netto")), 2)) > 0.011:
        out.append((FEHLER, f"Summe der Positionen {geld(summe_pos)} ≠ Netto {geld(k.get('netto'))}"))
    elif zeilen:
        out.append((OK, f"Summe der Positionen = Netto ({geld(summe_pos)})"))
    if k and abs(round(_n(k.get("netto")) + _n(k.get("mwst")), 2) - round(_n(k.get("brutto")), 2)) > 0.011:
        out.append((FEHLER, "Netto + MwSt. ergibt nicht den Bruttobetrag"))
    if g:
        teil = sum(x["betrag"] for x in g.get("gruppen") or ())
        if abs(teil - _n(g.get("verkauf"))) > 0.005:
            out.append((FEHLER, f"Kostenpositionen {geld(teil)} ergeben nicht den Verkaufspreis "
                                f"{geld(g.get('verkauf'))}"))
        else:
            out.append((OK, "Alle Kostenpositionen ergeben den Verkaufspreis der Kalkulation"))
        diff = _n(g.get("angebot_netto")) - _n(g.get("verkauf"))
        grenze = sum(0.005 * max(1.0, _n(z.get("menge"))) for z in zeilen) + 0.01
        if abs(diff) > grenze:
            out.append((WARNUNG, f"Angebot netto weicht um {geld(diff)} von der Kalkulation ab "
                                 f"(mehr als die Rundung der Stückpreise, höchstens {geld(grenze)})"))
        elif abs(diff) >= 0.005:
            out.append((HINWEIS, f"Angebot netto {geld(diff)} gegenüber der Kalkulation durch die Rundung "
                                 "der Stückpreise auf 2 Stellen"))
    if s.get("vorhanden"):
        if not s.get("aktuell"):
            out.append((WARNUNG, "Schnittplan passt nicht zum Angebot – vor dem Erstellen neu optimieren"))
        else:
            out.append((OK, f"Schnittplan aktuell ({s['summe'].get('lieferstangen', 0)} Stangen)"))
        soll = (summen or {}).get("stangen")
        if soll is not None and int(_n(soll)) != int(s["summe"].get("lieferstangen") or 0):
            out.append((WARNUNG, f"Stangen laut Kalkulation {int(_n(soll))}, im Schnittplan "
                                 f"{s['summe'].get('lieferstangen')}"))
    elif any(t.get("laser") for t in akte.get("technik") or ()):
        out.append((WARNUNG, "Kein Schnittplan vorhanden – Schnittschema bleibt leer"))
    for x in s.get("nicht_eingeplant") or ():
        out.append((FEHLER, x.get("text") or f"Pos. {x['pos']}: {x['anzahl']} Teil(e) nicht eingeplant"))
    for gr in m.get("gruppen") or ():
        if not gr.get("kunde") and not gr.get("eur_m"):
            out.append((WARNUNG, f"Kein Materialpreis für {gr['profil']} {gr['werkstoff']}"))
        elif not gr.get("kunde") and not gr.get("lieferant") and not gr.get("hand"):
            out.append((HINWEIS, f"Kein Lieferant hinterlegt für {gr['profil']} {gr['werkstoff']} ({gr['quelle']})"))
    z = akte.get("zukauf") or {}
    if z.get("fehlt"):
        out.append((WARNUNG, f"{z['fehlt']} Zukaufteil(e) ohne Preis"))
    ohne = [t["pos"] or t["artikel"] for t in akte.get("technik") or () if not t.get("bild")]
    if ohne:
        out.append((HINWEIS, "Ohne 3D-Bild (keine 3D-Daten): Pos. " + ", ".join(ohne[:12]) + (" …" if len(ohne) > 12
                                                                                               else "")))
    return out


def schlimmste(pruefung):
    for stufe in (FEHLER, WARNUNG, HINWEIS):
        if any(s == stufe for s, _ in pruefung or ()):
            return stufe
    return OK


def als_json(akte):
    """Akte als JSON-Text für Kalkulationsdaten/ (ohne Bilder)."""
    def ohne_bilder(x):
        if isinstance(x, dict):
            return {k: ohne_bilder(v) for k, v in x.items() if k != "bild"}
        if isinstance(x, (list, tuple)):
            return [ohne_bilder(v) for v in x]
        return x
    return json.dumps(ohne_bilder(akte), ensure_ascii=False, indent=1, default=str)
