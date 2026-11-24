"""Erfahrungswerte der Schweißbaugruppe (Konzept „Schweißbaugruppen-Kalkulation flexibel“ 12.11.2026, Paket 4).

- letzte(db, p, bg): letzte Ist-Zeit derselben (gleicher Name) oder einer ähnlichen Baugruppe (gleiche Vorlage) aus
  der Nachkalkulation, für die Anzeige im Fenster Schweißbaugruppe. Ist = Schweißen + Arbeitsgänge der
  Nachkalkulation (h je Auftrag); daneben die automatische Zeit derselben Baugruppe (ohne Vorgabe von Hand).
- Lernvorschlag: zwei Quellen für die bestehende Kennwert-Prüfung (kennwerte.vorschlaege, Einstellungen →
  Kennwerte aus der Nachkalkulation): 'bg_ist' (Ist ÷ automatisch) und 'bg_vorgabe' (Zeit von Hand ÷ automatisch).
  Ab 5 Baugruppen in dieselbe Richtung erscheint ein Faktor. Beide Quellen machen nur Vorschläge: es ändert sich
  nichts automatisch; welche Kennwerte angepasst werden, entscheidet man in den Quellen 'schweissen' und
  'vorkalkulation' (die ändern Kennwerte nach Freigabe).
"""
from . import baugruppe, bg_vorgabe, kennwerte


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _name(p, bg):
    return (p.get("artikel") or p.get("bezeichnung") or (bg.get("stamm") or {}).get("bezeichnung") or "").strip().lower()


def _ist_faelle(db, passt=None):
    """Je nachkalkulierte Baugruppe mit Ist-Stunden: dict(angebot, datum, name, vorlage, anzahl, ist_min, auto_min,
    wirksam_min, bg_id). passt(p, bg) filtert vor dem Rechnen (Tempo im Fenster)."""
    from . import rechnen
    from .angebot import ist_baugruppe
    tab = saetze = None
    out = []
    for a in db.angebote():
        if not a.get("nachkalkuliert"):
            continue
        kopf = db.angebot(a["id"])
        ist = kopf.get("nachkalkulation") or {}
        ist_bg = ist.get("baugruppen") or {}
        if not ist_bg:
            continue
        for p in db.positionen(a["id"]):
            bg = baugruppe.lesen(p.get("baugruppe")) if ist_baugruppe(p) else None
            e = ist_bg.get((bg or {}).get("id")) or {}
            h = [_n(e.get(f)) for f in ("schweiss_h", "arbeit_h")]
            if not bg or all(x is None for x in h) or not _n(p.get("stueck")):
                continue
            if passt is not None and not passt(p, bg):
                continue
            if tab is None:
                tab = db.tabellen()
                saetze = rechnen.stundensaetze(tab)
            auto = baugruppe.rechnen(p, tab, saetze, ohne_hand=True).get("zeiten") or {}
            wirk = baugruppe.rechnen(p, tab, saetze).get("zeiten") or {}
            out.append(dict(angebot=kopf.get("nummer") or a.get("nummer") or "", datum=ist.get("am") or kopf.get("datum")
                            or "", name=_name(p, bg), titel=baugruppe.name(p, bg), vorlage=bg.get("vorlage") or "",
                            anzahl=p["stueck"], ist_min=sum(x or 0.0 for x in h) * 60,
                            auto_min=auto.get("gesamt_min") or 0.0, wirksam_min=wirk.get("gesamt_min") or 0.0,
                            hand=bool(wirk.get("hand")), bg_id=bg.get("id")))
    return out


def letzte(db, p, bg):
    """Letzter Ist-Wert derselben Baugruppe (gleicher Name), sonst einer aus derselben Vorlage:
    dict(art 'dieselbe'|'ähnlich', angebot, datum, titel, anzahl, ist_min, ist_je_bg, auto_min, faktor) oder None."""
    if db is None or not bg:
        return None
    name, vorlage = _name(p, bg), bg.get("vorlage") or ""
    if not name and not vorlage:
        return None
    try:
        faelle = _ist_faelle(db, lambda q, b: (name and _name(q, b) == name) or (vorlage and b.get("vorlage") == vorlage))
    except Exception:       # noqa: BLE001 – Anzeige ist Beiwerk, das Fenster darf daran nicht scheitern
        return None
    faelle = [f for f in faelle if f["ist_min"] > 0]
    if not faelle:
        return None
    gleich = [f for f in faelle if name and f["name"] == name]
    art = "dieselbe" if gleich else "ähnlich"
    f = max(gleich or faelle, key=lambda x: (str(x["datum"]), str(x["angebot"])))
    return dict(f, art=art, ist_je_bg=f["ist_min"] / f["anzahl"],
                faktor=f["ist_min"] / f["auto_min"] if f["auto_min"] else None)


def text(e):
    """Kurztext für das Fenster."""
    if not e:
        return ""
    n = f"{e['anzahl']:g}".replace(".", ",")
    t = (f"Erfahrung ({'dieselbe Baugruppe' if e['art'] == 'dieselbe' else 'ähnlich, Vorlage ' + e['vorlage']}): "
         f"{e['angebot']} {str(e['datum'])[:10]}, {n} Stk., Ist {bg_vorgabe.zeit_text(e['ist_min'])} "
         f"= {bg_vorgabe.zeit_text(e['ist_je_bg'])} je BG")
    if e.get("faktor"):
        p = (e["faktor"] - 1) * 100
        t += f" (automatisch damals {bg_vorgabe.zeit_text(e['auto_min'])}, Ist {'+' if p >= 0 else '−'}{abs(p):.0f} %)"
    return t


# ------------------------------------------------------------------ Lernvorschläge (nur Vorschlag)
def faelle_ist(db):
    return [dict(schluessel=("Ist ÷ automatisch",), soll=f["auto_min"] / 60, ist=f["ist_min"] / 60,
                 angebot=f["angebot"], datum=f["datum"]) for f in _ist_faelle(db) if f["auto_min"] > 0]


def faelle_vorgabe(db):
    """Baugruppen mit Zeit von Hand (alle Angebote): Soll = automatische Gesamtzeit, Ist = Zeit mit Vorgabe."""
    from . import rechnen
    from .angebot import ist_baugruppe
    tab = saetze = None
    out = []
    for a in db.angebote():
        for p in db.positionen(a["id"]):
            bg = baugruppe.lesen(p.get("baugruppe")) if ist_baugruppe(p) else None
            if not bg or not bg_vorgabe.hat_vorgabe(bg) or not _n(p.get("stueck")):
                continue
            if tab is None:
                tab = db.tabellen()
                saetze = rechnen.stundensaetze(tab)
            z = baugruppe.rechnen(p, tab, saetze).get("zeiten") or {}
            if z.get("hand") and z.get("auto_gesamt_min"):
                out.append(dict(schluessel=("Zeit von Hand ÷ automatisch",), soll=z["auto_gesamt_min"] / 60,
                                ist=z["gesamt_min"] / 60, angebot=a.get("nummer") or "", datum=a.get("datum") or ""))
    return out


kennwerte.register_quelle("bg_ist", "Schweißbaugruppe gesamt: Ist ÷ automatisch (nur Vorschlag, Paket 4)", faelle_ist)
kennwerte.register_quelle("bg_vorgabe", "Schweißbaugruppe gesamt: Zeit von Hand ÷ automatisch (nur Vorschlag)",
                          faelle_vorgabe)
