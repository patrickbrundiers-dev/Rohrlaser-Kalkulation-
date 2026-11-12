"""Kostenübersicht einer Schweißbaugruppe (Konzept „Schweißbaugruppen-Kalkulation flexibel“ 12.11.2026, Paket 2):
was eine Baugruppe samt Einzelteilen kostet und wie sich ihr Preis zusammensetzt, je Baugruppe.

Keine neue Rechnung: alles kommt aus der Angebotskalkulation (rechnen.kalkulation) und aus baugruppe.rechnen. Die
Einzelteile zählen mit ihrem Anteil je Baugruppe (Stückzahl der Position ÷ Anzahl Baugruppen).

  Material            material_teil der Einzelteile
  Zukaufteile         zukauf_teil der Einzelteile und der Baugruppe (Normteile, Schrauben …)
  Fertigung Teile     Selbstkosten der Einzelteile − Material − Zukauf − Zuschläge (Laser, Gewinde, Rüsten,
                      Zusatzarbeiten, Arbeitsschritte, Programmierung …)
  Bereiche            eigene Leistungen der Baugruppe nach Bereich (Vorbereitung, Schweißen inkl. Heften,
                      Nachbearbeitung, Weitere), ohne Schweißdraht und Gas
  Schweißzusatz/Gas   Verbrauch der Nahtgruppen
  Einmalkosten        umgelegte Rüst- und Einmalkosten der Baugruppe
  Fremdleistungen     Arbeitsgänge mit Fremd (laufend)
  = Kosten vor Zuschlägen; + Zuschläge (Material, Fertigung, Fremdleistung) = Selbstkosten
  + Gewinn + Fracht + Skonto (+ Mindestpreis/Muster) = Verkaufspreis
  Deckungsbeitrag = Verkaufspreis − Material − Zukauf − Fremdleistungen − Schweißzusatz/Gas
  Marge = Gewinn ÷ Verkaufspreis
Die Summen sind so gebaut, dass jeder Euro genau einmal zählt: Summe aller Posten + Zuschläge + Gewinn + Fracht +
Skonto + Rest = Summe der Verkaufspreise je Baugruppe (Test).
"""
from . import baugruppe, bg_vorgabe

ZUSCHLAEGE = ("zuschlag_material_teil", "zuschlag_fertigung_teil", "zuschlag_fremdleistung_teil")


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _je_bg(q, n_bg):
    return _n(q.get("stueck")) / n_bg if n_bg else 0.0


def uebersicht(positionen, kalk_zeilen, bg_index, r=None):
    """Übersicht der Baugruppe positionen[bg_index] (kalk_zeilen parallel zu positionen; ohne Kalkulation None):
    dict(posten [dict(titel, eur, kinder [(Text, €, Erklärung)], art)], zuschlaege, gewinn, fracht, skonto, rest,
    selbst, verkauf, verkauf_auftrag, db, marge, n, maschine_min, arbeit_min, mit_teilen). r = baugruppe.rechnen
    der Baugruppe (sonst aus der Kalkulationszeile)."""
    p = positionen[bg_index]
    bg = baugruppe.lesen(p.get("baugruppe")) or baugruppe.leer()
    n_bg = _n(p.get("stueck")) or 0
    zb = (kalk_zeilen[bg_index] if kalk_zeilen else None) or {}
    if r is None:
        r = dict(zeilen=zb.get("bg_zeilen") or [], eigen=_n(zb.get("bg_eigen_teil")), fremd=_n(zb.get("bg_fremd_teil")),
                 einmal=_n(zb.get("bg_einmal_teil")), einmal_fremd=0.0, verbrauch=0.0, zeiten=zb.get("bg_zeiten"))
    mit_teilen = bool(kalk_zeilen)
    material = zukauf = fertigung = zuschlaege = gewinn = fracht = skonto = rest = maschine_s = 0.0
    k_mat, k_zk, k_fert = [], [], []
    if mit_teilen:
        for j in baugruppe.teile(positionen, bg["id"]):
            q, z = positionen[j], kalk_zeilen[j] or {}
            je = _je_bg(q, n_bg)
            if not je:
                continue
            name = f"Pos. {q.get('pos') or j + 1} {q.get('artikel') or q.get('bezeichnung') or ''}".strip()
            m, zk = _n(z.get("material_teil")) * je, _n(z.get("zukauf_teil")) * je
            zs = sum(_n(z.get(f)) for f in ZUSCHLAEGE) * je
            sk = _n(z.get("selbst_teil")) * je
            f_ = sk - m - zk - zs
            material += m
            zukauf += zk
            fertigung += f_
            zuschlaege += zs
            g, fr, s = _n(z.get("gewinn_teil")) * je, _n(z.get("fracht_teil")) * je, _n(z.get("skonto_teil")) * je
            gewinn, fracht, skonto = gewinn + g, fracht + fr, skonto + s
            rest += _n(z.get("preis_teil")) * je - sk - g - fr - s
            maschine_s += _n(z.get("laser_netto")) * je
            stk = f"{je:g} Stk. je BG".replace(".", ",")
            if m:
                k_mat.append((name, m, stk))
            if zk:
                k_zk.append((name, zk, stk))
            if abs(f_) > 1e-9:
                k_fert.append((name, f_, stk + (f", Laser {_n(z.get('laser_netto')) * je / 60:.1f} min".replace(".", ",")
                                                if z.get("laser_netto") else "")))
        bz = _n(zb.get("zukauf_teil"))
        if bz:
            zukauf += bz
            k_zk.append(("an der Baugruppe", bz, "Zukaufteile der Baugruppen-Position"))
    # eigene Leistungen der Baugruppe nach Bereich
    ber = {b: [0.0, []] for b in bg_vorgabe.BEREICHE}
    fremd_k = []
    for x in r["zeilen"]:
        w = x.get("werte") or {}
        if x.get("fremd"):
            if x["kosten"]:
                fremd_k.append((x["name"], x["kosten"], x.get("knoten") or ""))
            continue
        b = bg_vorgabe.SCHWEISSEN if x["art"] == "Naht" else (x.get("bereich") or bg_vorgabe.WEITERE)
        if b == bg_vorgabe.HEFTEN:
            b = bg_vorgabe.SCHWEISSEN
        eur = x["kosten"] - (_n(w.get("material")) * _n(x.get("faktor") or 1) if x["art"] == "Naht" else 0.0)
        if abs(eur) < 1e-9 and not x["zeit_min"]:
            continue            # nur Einmalbetrag (z. B. Vorrichtung): steht unter Einmalkosten
        text = w.get("rechenweg") or ""
        if x.get("auto") and abs(x["auto"]["zeit_min"] - x["zeit_min"]) > 1e-9:
            text = (text + " · " if text else "") + (f"Zeit von Hand/Komplexität: {bg_vorgabe.zeit_text(x['zeit_min'])} "
                                                     f"statt {bg_vorgabe.zeit_text(x['auto']['zeit_min'])}")
        elif x["zeit_min"]:
            text = (text + " · " if text else "") + bg_vorgabe.zeit_text(x["zeit_min"]) + " je BG"
        ber[b][0] += eur
        ber[b][1].append((x["name"], eur, text))
    verbrauch = _n(r.get("verbrauch"))
    einmal = _n(r.get("einmal"))
    fremd = _n(r.get("fremd")) - _n(r.get("einmal_fremd"))
    # Kosten der Baugruppen-Zeile, die r nicht kennt (aus der Kalkulation ohne r): Rest bis zu eigen + fremd
    posten = []
    if mit_teilen:
        posten += [dict(titel="Material", eur=material, kinder=k_mat, art="material"),
                   dict(titel="Fertigung Einzelteile", eur=fertigung, kinder=k_fert, art="fertigung")]
    posten.append(dict(titel="Zukaufteile", eur=zukauf, kinder=k_zk, art="zukauf"))
    for b in bg_vorgabe.BEREICHE:
        if b == bg_vorgabe.HEFTEN:
            continue
        eur, kinder = ber[b]
        if kinder or eur:
            posten.append(dict(titel=b if b != bg_vorgabe.SCHWEISSEN else "Schweißen (inkl. Heften)", eur=eur,
                               kinder=kinder, art="bereich"))
    if verbrauch:
        posten.append(dict(titel="Schweißzusatz und Gas", eur=verbrauch, kinder=[], art="verbrauch"))
    if einmal:
        n_txt = f"{n_bg:g}".replace(".", ",")
        posten.append(dict(titel="Einmalkosten (umgelegt)", eur=einmal, art="einmal",
                           kinder=[(x["name"], x["einmal"] / n_bg if n_bg else 0.0, f"{x['einmal']:.2f} € je Auftrag ÷ "
                                    f"{n_txt} Stk.".replace(".", ",", 1)) for x in r["zeilen"] if x["einmal"]]))
    if fremd or fremd_k:
        posten.append(dict(titel="Fremdleistungen", eur=fremd, kinder=fremd_k, art="fremd"))
    posten = [x for x in posten if x["eur"] or x["kinder"]]
    kosten = sum(x["eur"] for x in posten)
    if zb:
        zuschlaege += _n(zb.get("zuschlag_fertigung_teil")) + _n(zb.get("zuschlag_fremdleistung_teil"))
        gewinn += _n(zb.get("gewinn_teil"))
        fracht += _n(zb.get("fracht_teil"))
        skonto += _n(zb.get("skonto_teil"))
        rest += _n(zb.get("preis_teil")) - _n(zb.get("selbst_teil")) - _n(zb.get("gewinn_teil")) \
            - _n(zb.get("fracht_teil")) - _n(zb.get("skonto_teil"))
    selbst = kosten + zuschlaege
    verkauf = selbst + gewinn + fracht + skonto + rest if zb else None
    variabel = material + zukauf + fremd + verbrauch
    zt = r.get("zeiten") or {}
    return dict(posten=posten, kosten=kosten, zuschlaege=zuschlaege, selbst=selbst, gewinn=gewinn, fracht=fracht,
                skonto=skonto, rest=rest, verkauf=verkauf, n=n_bg,
                verkauf_auftrag=verkauf * n_bg if verkauf is not None else None,
                db=verkauf - variabel if verkauf is not None else None,
                marge=gewinn / verkauf * 100 if verkauf else None, maschine_min=maschine_s / 60,
                arbeit_min=(zt.get("stueck_min") or 0.0) + ((zt.get("ruest_min") or 0.0) / n_bg if n_bg else 0.0),
                mit_teilen=mit_teilen)
