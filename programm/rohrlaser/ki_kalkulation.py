"""KI 2 (Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“): Kalkulation erklären und auswerten.

Alle Zahlen kommen aus der Rechnung des Programms; ein lokales Sprachmodell formuliert höchstens um (Faktencheck in
ki_orchestrator). Nichts ändert einen Preis.

preis_erklaeren(ctx, fuer_kunde)    Punkt 7: Zusammensetzung des Preises intern bzw. als Satz für den Kunden
vergleich_frueher(ctx)              Punkt 8: Wiederholteile, Unterschied zum Preis von damals in Ursachen zerlegt
nachkalk_muster(db)                 Punkt 9: wo Ist und Soll in den nachkalkulierten Aufträgen auseinanderliegen
vergessene_positionen(ctx)          Punkt 6: was frühere Angebote desselben Kunden fast immer hatten, hier aber fehlt
rueckfrage_entwurf(ctx)             Punkt 10: Rückfrage-Mail mit den offenen Punkten (wie Ausgaben → Rückfrage)
suche(db, frage)                    Punkt 12: Angebote nach Werkstoff, Profilform, Maß, Länge, Kunde, Zeitraum
Ohne Qt."""
import datetime
import re

from .stammdaten import zahl_als_text
from . import protokoll

MUSTER_MIN_N = 3
MUSTER_MIN_PROZENT = 10.0


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _z(v, stellen=2):
    return zahl_als_text(round(_n(v), stellen)) if stellen else zahl_als_text(round(_n(v)))


# ------------------------------------------------------------------ Punkt 6: vergessene Positionen
VERGESSEN_MIN_N = 3
VERGESSEN_ANTEIL = 0.6


def _merkmale(db, kopf, positionen):
    from . import rechnen
    from .angebot import ist_zukaufteil
    out = set()
    for p in positionen or ():
        try:
            out |= {e["name"] for e in rechnen.zusatz_liste(p) if e.get("name")}
        except Exception:       # noqa: BLE001
            protokoll.warnung("ki_kalkulation: abgefangen")
        if ist_zukaufteil(p):
            out.add("Zukaufteile")
    if str((kopf or {}).get("zeugnis_31") or "").lower() in ("ja", "1", "true"):
        out.add("Werkszeugnis 3.1")
    return out


def vergessene_positionen(ctx, n_frueher=10, min_n=VERGESSEN_MIN_N, anteil=VERGESSEN_ANTEIL):
    """[dict(name, anteil, n, text)]: Zusatzarbeiten/Zeugnis/Zukauf, die mindestens anteil der letzten n_frueher
    Angebote desselben Kunden hatten (mindestens min_n Angebote), dieses Angebot aber nicht. Nur Hinweis."""
    kopf = ctx.kopf or {}
    kunde = kopf.get("kunde")
    if not kunde:
        return []
    frueher = [a for a in ctx.db.angebote() if a.get("kunde") == kunde and a.get("id") != ctx.angebot_id]
    frueher.sort(key=lambda a: str(a.get("datum") or ""), reverse=True)
    frueher = frueher[:n_frueher]
    if len(frueher) < min_n:
        return []
    jetzt = _merkmale(ctx.db, kopf, ctx.positionen)
    zaehler = {}
    for a in frueher:
        try:
            m = _merkmale(ctx.db, ctx.db.angebot(a["id"]) or a, ctx.db.positionen(a["id"]))
        except Exception:       # noqa: BLE001
            protokoll.warnung("ki_kalkulation: abgefangen")
            continue
        for x in m:
            zaehler[x] = zaehler.get(x, 0) + 1
    out = []
    for name, k in sorted(zaehler.items(), key=lambda x: -x[1]):
        if name not in jetzt and k / len(frueher) >= anteil:
            out.append(dict(name=name, anteil=round(k / len(frueher), 2), n=len(frueher),
                            text=f"{name}: in {k} von {len(frueher)} früheren Angeboten für {kunde}, hier nicht "
                                 "– vergessen?"))
    return out


# ------------------------------------------------------------------ Punkt 7: Preis erklären
def preis_erklaeren(ctx, fuer_kunde=False):
    """dict(text, positionen [dict(pos, preis_stk, menge, material_pct, laser_pct, ruesten_pct)]) oder None."""
    from . import rechnen
    s, zeilen, pos = ctx.summen, ctx.zeilen, ctx.positionen
    if not s or not zeilen:
        return None
    selbst, verkauf = _n(s.get("selbst")), _n(s.get("verkauf"))
    if selbst <= 0 or verkauf <= 0:
        return None
    gruppen = {"Material": ("material", "schrott", "zuschlag_material", "lagerzins"),
               "Laserbearbeitung": ("laser_schneiden", "schneidgas", "stangenwechsel_kosten"),
               "Rüsten und Programmierung": ("ruesten_maschine", "ruesten_abmessungen", "programmierung", "pauschalen"),
               "Zusatzarbeiten und Gewinde": ("zusatz", "gewinde", "arbeitsschritte"),
               "Schweißbaugruppen": ("baugruppe_eigen", "baugruppe_fremd"),
               "Zukaufteile": ("zukauf_einstand", "zukauf_aufschlag")}
    anteile = sorted(((g, sum(_n(s.get(k)) for k in ks)) for g, ks in gruppen.items()), key=lambda x: -x[1])
    anteile = [(g, w) for g, w in anteile if w > 0.005 * selbst]
    ruesten = sum(_n(s.get(k)) for k in gruppen["Rüsten und Programmierung"])
    stueck = sum(_n(p.get("stueck")) for p in pos if p.get("muster") != "ja")
    pos_out = []
    for i, (p, z) in enumerate(zip(pos, zeilen)):
        if not z or _n(p.get("stueck")) <= 0:
            continue
        pos_out.append(dict(pos=p.get("pos") or i + 1, artikel=p.get("artikel") or "", preis_stk=_n(z.get("preis_teil")),
                            menge=_n(p.get("stueck"))))
    if fuer_kunde:
        haupt = [g for g, _ in anteile[:2]]
        satz = (f"Der Preis ergibt sich vor allem aus {' und '.join(haupt)}" if haupt else "Der Preis ergibt sich aus "
                "Material und Bearbeitung")
        satz += f" bei insgesamt {_z(stueck, 0)} Teilen."
        if ruesten > 0.1 * selbst:
            satz += (" Ein spürbarer Teil sind einmalige Kosten für Rüsten und Programmierung; bei größeren Mengen "
                     "verteilen sie sich auf mehr Teile und der Stückpreis sinkt.")
        if any(p.get("zukauf") for p in pos):
            satz += " Zukaufteile sind zum Einstandspreis mit Aufschlag enthalten."
        return dict(text=satz, positionen=pos_out, anteile=anteile)
    zeilen_t = [f"Verkaufspreis {_z(verkauf)} € bei Selbstkosten {_z(selbst)} €, Gewinn {_z(_n(s.get('gewinn')))} €."]
    zeilen_t += [f"• {g}: {_z(w)} € ({_z(100 * w / selbst, 0)} % der Selbstkosten)" for g, w in anteile]
    if stueck:
        zeilen_t.append(f"Rüsten und Programmierung je Teil: {_z(ruesten / stueck)} € bei {_z(stueck, 0)} Teilen.")
    teuer = sorted(pos_out, key=lambda x: -x["preis_stk"] * x["menge"])[:3]
    if teuer:
        zeilen_t.append("Größte Positionen: " + "; ".join(f"Pos. {x['pos']} {_z(x['preis_stk'])} €/Stk. × "
                                                          f"{_z(x['menge'], 0)}" for x in teuer))
    try:
        from . import plausibel
        h, ertrag = plausibel.ertrag_laser(zeilen, s)
        if h > 0:
            zeilen_t.append(f"Ertrag je Laserstunde {_z(ertrag / h)} € ({_z(h, 2)} h).")
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_kalkulation: abgefangen")
    try:        # Produktionsdaten-Intelligenz: worauf die Zeit beruht (nie höher als belegt)
        from . import produktion_genauigkeit as pg
        bw = pg.angebot(ctx.db, pos)
        if bw:
            zeilen_t.append("Datenbasis Bearbeitungszeit: " + "; ".join(f"Pos. {p.get('pos') or '?'} {pg.kurz(b)}"
                                                                       for p, b in bw[:4]) + (" …" if len(bw) > 4 else ""))
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_kalkulation: Datenbasis abgefangen")
    _ = rechnen
    return dict(text="\n".join(zeilen_t), positionen=pos_out, anteile=anteile)


# ------------------------------------------------------------------ Punkt 8: Vergleich mit früheren Aufträgen
def vergleich_frueher(ctx, max_pos=6):
    """[dict(pos, nummer, damals, heute, text, satz)] für Positionen mit Wiederholteil (gleiche Artikelnummer).
    Braucht das offene Angebot (seite); sonst die ähnlichen Angebote aus der Suche."""
    seite = ctx.seite
    out = []
    if seite is None or not hasattr(seite, "wiederholpreis_erklaeren"):
        return out
    try:
        treffer = seite.wiederholteile_suchen() or {}
    except Exception:           # noqa: BLE001
        return out
    from .wiederholteile import AEHNLICH
    for i, p in enumerate(seite.positionen):
        if len(out) >= max_pos:
            break
        t = [x for x in treffer.get(p.get("id")) or () if x.art != AEHNLICH]
        if not t:
            continue
        meldung = getattr(seite.f, "meldung", None)
        try:
            seite.f.meldung = lambda *a, **k: None      # keine Einblendung aus dem Assistenten heraus
            r = seite.wiederholpreis_erklaeren(i, zeigen=False)
        except Exception:       # noqa: BLE001
            r = None
        finally:
            if meldung is not None:
                seite.f.meldung = meldung
        if not r:
            continue
        schritte = "; ".join(f"{'+' if s_['eur'] >= 0 else '−'}{_z(abs(s_['eur']))} € {s_['name']}"
                             for s_ in r["schritte"] if abs(s_["eur"]) >= 0.005)
        out.append(dict(pos=p.get("pos"), nummer=r.get("nummer") or t[0].angebot.get("nummer"), damals=r["damals"],
                        heute=r["heute"], satz=r.get("satz") or "",
                        text=f"Pos. {p.get('pos')}: damals {_z(r['damals'])} €/Stk. ({r.get('nummer') or ''}), heute "
                             f"{_z(r['heute'])} €/Stk." + (f" – {schritte}" if schritte else "")))
    return out


# ------------------------------------------------------------------ Punkt 9: Nachkalkulation in Worten
def nachkalk_muster(db, min_n=MUSTER_MIN_N, min_prozent=MUSTER_MIN_PROZENT):
    """[dict(merkmal, gruppe, kostenart, n, prozent, text)] – Gruppen mit genug Aufträgen und deutlicher Abweichung
    Ist gegen Soll, größte zuerst."""
    from . import nachkalkulation as nk
    out = []
    for merkmal, titel in nk.MERKMALE.items():
        try:
            a = nk.auswertung(db, merkmal)
        except Exception:       # noqa: BLE001
            protokoll.warnung("ki_kalkulation: abgefangen")
            continue
        for z in a.get("zeilen") or ():
            if (z.get("n") or 0) < min_n or z.get("prozent") is None or abs(z["prozent"]) < min_prozent:
                continue
            richtung = "über" if z["prozent"] > 0 else "unter"
            gruppe = z.get("gruppe")
            wo = f"{titel} {gruppe}" if merkmal != "kostenart" else "alle Aufträge"
            out.append(dict(merkmal=titel, gruppe=gruppe, kostenart=z.get("kostenart"), n=z["n"],
                            prozent=round(z["prozent"], 1),
                            text=f"{wo}, {z.get('kostenart')}: Ist im Mittel {_z(abs(z['prozent']), 0)} % {richtung} "
                                 f"Soll ({z['n']} Aufträge)."))
    seen, eindeutig = set(), []
    for x in sorted(out, key=lambda x: -abs(x["prozent"])):
        k = (x["merkmal"], x["gruppe"], x["kostenart"])
        if k not in seen:
            seen.add(k)
            eindeutig.append(x)
    return eindeutig


# ------------------------------------------------------------------ Punkt 10: Rückfrage-Mail
def rueckfrage_entwurf(ctx):
    """dict(betreff, text, punkte) mit den offenen Punkten des Angebots (wie Ausgaben → Rückfrage an Kunden …)
    oder None, wenn nichts offen ist."""
    from . import rueckfrage
    seite, db = ctx.seite, ctx.db
    kopf = ctx.kopf or {}
    try:
        check = ctx.check or []
    except Exception:           # noqa: BLE001
        check = []
    punkte = rueckfrage.punkte(check, ctx.positionen or [], ctx.zeilen or [])
    if not punkte:
        return None
    kunde = db.kunde(kopf.get("kundennr")) if kopf.get("kundennr") and hasattr(db, "kunde") else None
    text = rueckfrage.text(kopf, kunde, punkte, db.einstellung("benutzer_name") or "")
    _ = seite
    return dict(betreff=rueckfrage.betreff(kopf), text=text, punkte=punkte)


# ------------------------------------------------------------------ Punkt 12: Suche in normaler Sprache
KATEGORIEN = {"edelstahl": "Edelstahl", "nirosta": "Edelstahl", "v2a": "Edelstahl", "v4a": "Edelstahl",
              "alu": "Aluminium", "aluminium": "Aluminium", "stahl": "Stahl", "baustahl": "Stahl"}
FORMEN = {"rundrohr": "Rundrohr", "rundrohre": "Rundrohr", "quadratrohr": "Quadratrohr", "quadratrohre": "Quadratrohr",
          "rechteckrohr": "Rechteckrohr", "rechteckrohre": "Rechteckrohr", "flachstahl": "Flachstahl",
          "winkel": "Winkel", "u-profil": "U-Profil", "ovalrohr": "Ovalrohr"}


def filter_aus_text(frage, kunden=()):
    """dict(kategorie, form, laenge_min, laenge_max, mass, kunde, seit) aus einer Frage in normaler Sprache."""
    t = str(frage or "").lower()
    f = {}
    for w, k in KATEGORIEN.items():
        if re.search(rf"\b{re.escape(w)}\w*", t):
            f["kategorie"] = k
            if k != "Stahl":
                break
    for w, k in FORMEN.items():
        if re.search(rf"\b{re.escape(w)}\b", t):
            f["form"] = k
            break
    m = re.search(r"(über|ueber|mehr als|größer als|groesser als|ab|>)\s*(\d+(?:[.,]\d+)?)\s*(m|mm)\b", t)
    if m:
        f["laenge_min"] = float(m.group(2).replace(",", ".")) * (1000 if m.group(3) == "m" else 1)
    m = re.search(r"(unter|weniger als|kleiner als|bis|<)\s*(\d+(?:[.,]\d+)?)\s*(m|mm)\b", t)
    if m:
        f["laenge_max"] = float(m.group(2).replace(",", ".")) * (1000 if m.group(3) == "m" else 1)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?:\s*[x×]\s*(\d+(?:[.,]\d+)?))?", t)
    if m:
        f["mass"] = [float(g.replace(",", ".")) for g in m.groups() if g]
    for k in kunden:
        name = str(k or "").strip()
        if len(name) >= 3 and name.lower().split()[0] in t:
            f["kunde"] = name
            break
    m = re.search(r"\bseit\s+(\d{4})\b", t)
    if m:
        f["seit"] = f"{m.group(1)}-01-01"
    m = re.search(r"\bletzten?\s+(\d{1,2})\s+monat", t)
    if m:
        f["seit"] = (datetime.date.today() - datetime.timedelta(days=30 * int(m.group(1)))).isoformat()
    if re.search(r"\b(?:dieses|diesem)\s+jahr", t):
        f["seit"] = f"{datetime.date.today().year}-01-01"
    return f


def suche(db, frage, n=30):
    """(filter, [dict(angebot_id, nummer, kunde, datum, positionen [Text])]) – Angebote, deren Positionen allen
    erkannten Bedingungen genügen; leer, wenn die Frage keine Bedingung enthält."""
    angebote = db.angebote()
    f = filter_aus_text(frage, sorted({a.get("kunde") for a in angebote if a.get("kunde")}, key=lambda x: -len(x)))
    if not any(k in f for k in ("kategorie", "form", "laenge_min", "laenge_max", "mass")) and "kunde" not in f:
        return f, []
    profile = {p["profil_id"]: p for p in db.zeilen("profile")}
    werkstoffe = {w["werkstoff_id"]: w for w in db.zeilen("werkstoffe")}
    out = []
    for a in angebote:
        if f.get("kunde") and f["kunde"] != a.get("kunde"):
            continue
        if f.get("seit") and str(a.get("datum") or "") < f["seit"]:
            continue
        treffer = []
        try:
            positionen = db.positionen(a["id"])
        except Exception:       # noqa: BLE001
            protokoll.warnung("ki_kalkulation: abgefangen")
            continue
        for p in positionen:
            pr, ws = profile.get(p.get("profil_id")) or {}, werkstoffe.get(p.get("werkstoff_id")) or {}
            if f.get("kategorie") and f["kategorie"].lower() not in str(ws.get("kategorie") or "").lower():
                continue
            if f.get("form") and pr.get("form") != f["form"]:
                continue
            la = _n(p.get("laenge"))
            if f.get("laenge_min") and la <= f["laenge_min"]:
                continue
            if f.get("laenge_max") and (not la or la >= f["laenge_max"]):
                continue
            if f.get("mass"):
                werte = [x for x in (pr.get("a"), pr.get("b"), pr.get("wand")) if x is not None]
                if not all(any(abs(m - w) <= 0.15 for w in werte) for m in f["mass"]):
                    continue
            treffer.append(f"Pos. {p.get('pos')} {p.get('profil_id') or ''} {_z(la, 0)} mm {p.get('werkstoff_id') or ''}"
                           f" × {_z(_n(p.get('stueck')), 0)}")
        if treffer or (not any(k in f for k in ("kategorie", "form", "laenge_min", "laenge_max", "mass"))
                       and f.get("kunde")):
            out.append(dict(angebot_id=a["id"], nummer=a.get("nummer"), kunde=a.get("kunde") or "",
                            datum=a.get("datum") or "", positionen=treffer))
    out.sort(key=lambda x: str(x["datum"]), reverse=True)
    return f, out[:n]


def filter_text(f):
    teile = []
    if f.get("kategorie"):
        teile.append(f["kategorie"])
    if f.get("form"):
        teile.append(f["form"])
    if f.get("mass"):
        teile.append("×".join(_z(x, 1) for x in f["mass"]))
    if f.get("laenge_min"):
        teile.append(f"Länge über {_z(f['laenge_min'], 0)} mm")
    if f.get("laenge_max"):
        teile.append(f"Länge unter {_z(f['laenge_max'], 0)} mm")
    if f.get("kunde"):
        teile.append(f"Kunde {f['kunde']}")
    if f.get("seit"):
        teile.append(f"seit {f['seit']}")
    return ", ".join(teile)


# ------------------------------------------------------------------ KI 3 (Paket B-Rest): Preisrisiko
RISIKO_MARGE = 0.08         # unter dieser Marge (oder der Mindestmarge der Einstellungen) zählt die Marge als knapp
RISIKO_STUFEN = ((5, "hoch"), (3, "mittel"), (0, "niedrig"))


def preisrisiko(ctx):
    """dict(stufe, punkte, gruende [dict(text, punkte, quelle)], text) oder None (nicht optimiert): wie sicher der
    Preis ist – alte Materialpreise, unsichere Erkennung, knappe Marge, ungewohntes Teil, Zukauf ohne Preis. Nur
    Hinweis; der Preis bleibt die Rechnung des Programms."""
    from . import ki_agenten as ag
    s = ctx.summen
    if not s:
        return None
    gruende = []
    r = ag.pruefen(ctx.db, ctx.angebot_id, ctx.seite, ["material", "qualitaet", "einkauf", "rohrlaser"], ctx.heute,
                   protokoll=False)
    for b in r["befunde"]:
        q = b.get("quelle") or ""
        if q == "Preisalter" and b["art"] in (ag.WARNUNG, ag.HINWEIS):
            gruende.append(dict(text=b["text"], punkte=2, quelle=q))
        elif q == "STEP-Prüfstatus":
            gruende.append(dict(text=b["text"], punkte=2 if b["art"] == ag.WARNUNG else 1, quelle=q))
        elif q == "Schneiddaten" and b["art"] in (ag.WARNUNG, ag.HINWEIS):
            gruende.append(dict(text=b["text"], punkte=1, quelle=q))
        elif b.get("agent") == "Einkaufs-KI" and b["art"] in (ag.WARNUNG, ag.FEHLER):
            gruende.append(dict(text=b["text"], punkte=2, quelle=q or "Einkauf"))
    verkauf = _n(s.get("verkauf"))
    if verkauf > 0:
        from . import marge as mg
        marge = mg.marge(s) or 0.0
        try:
            mind = float(ctx.db.einstellung("mindestmarge") or 0)
        except (TypeError, ValueError):
            mind = 0.0
        grenze = max(mind, RISIKO_MARGE)
        if marge < grenze:
            gruende.append(dict(text=f"Marge {_z(100 * marge, 1)} % liegt unter {_z(100 * grenze, 1)} %.",
                                punkte=2 if marge < grenze / 2 else 1, quelle="Kalkulation"))
    if ctx.seite is not None and hasattr(ctx.seite, "wiederholteile_suchen"):
        try:
            if not vergleich_frueher(ctx):
                gruende.append(dict(text="Keine Wiederholteile: für diese Teile gibt es keinen früheren Preis.",
                                    punkte=1, quelle="Wiederholteile"))
        except Exception:       # noqa: BLE001
            protokoll.warnung("ki_kalkulation: Wiederholteile nicht prüfbar")
    punkte = sum(g["punkte"] for g in gruende)
    stufe = next(t for ab, t in RISIKO_STUFEN if punkte >= ab)
    text = f"Preisrisiko {stufe} ({punkte} Punkte)" + (":\n" + "\n".join(f"• {g['text']} ({g['quelle']})"
                                                         for g in gruende) if gruende else
                                                         ": keine Auffälligkeiten.")
    return dict(stufe=stufe, punkte=punkte, gruende=gruende, text=text)


# ------------------------------------------------------------------ KI 3: Texte auf Englisch (nur Entwurf)
SYSTEM_EN = ("You translate German business texts of a tube laser cutting company into clear, polite English. "
             "Keep every number, unit, article number and name exactly as given. Do not add facts. Output only "
             "the translated text.")


def _de_zahlen(en):
    """Englisch geschriebene Zahlen (1,224.11 / 12.5) deutsch schreiben (1.224,11 / 12,5) für den Faktencheck."""
    def um(m):
        t = m.group(0)
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", t):
            t = t.replace(",", "")
        elif "," in t:
            return t
        ganz, _, rest = t.partition(".")
        if ganz.isdigit() and int(ganz) >= 1000 and (rest or m.group(0) != t):     # mit Tausender/Dezimalteil
            ganz = f"{int(ganz):,}".replace(",", ".")
        return ganz + ("," + rest if rest else "")
    return re.sub(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?(?![\d])", um, str(en))


def uebersetzen(db, text, senden=None):
    """dict(text, ok, modell, fremde_zahlen): englischer Entwurf des Textes mit dem lokalen Sprachmodell. ok=False,
    wenn kein Modell aktiv ist oder die Übersetzung eine Zahl enthält, die im Original nicht steht (dann bleibt der
    deutsche Text)."""
    from . import ki_modelle, ki_orchestrator, ki_protokoll
    if not str(text or "").strip():
        return dict(text="", ok=False, modell="", fremde_zahlen=[])
    if not ki_modelle.aktiv(db):
        return dict(text=text, ok=False, modell="", fremde_zahlen=[],
                    hinweis="Englisch braucht ein lokales Sprachmodell (KI-Zentrale → Modelle).")
    try:
        a = ki_modelle.erzeugen(db, ki_modelle.ERKLAEREN, text, system=SYSTEM_EN, senden=senden)
    except ki_modelle.KiFehler as e:
        return dict(text=text, ok=False, modell="", fremde_zahlen=[], hinweis=f"Sprachmodell: {e}")
    en = str(a.get("text") or "").strip()
    ok, fremd = ki_orchestrator.faktencheck(_de_zahlen(en), text)
    try:
        ki_protokoll.schreiben(db, "KI-Übersetzung", "englisch", ergebnis="ok" if ok else f"verworfen {fremd}",
                               modell=a.get("modell", ""), status="ok" if ok else "fehler")
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_kalkulation: Protokoll Übersetzung")
    if not ok or not en:
        return dict(text=text, ok=False, modell=a.get("modell", ""), fremde_zahlen=fremd,
                    hinweis="Die Übersetzung enthielt Zahlen, die im Original nicht stehen – verworfen.")
    return dict(text=en, ok=True, modell=a.get("modell", ""), fremde_zahlen=[])
