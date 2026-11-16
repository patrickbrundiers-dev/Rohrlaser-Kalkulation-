"""Fragen zum Rechenweg regelbasiert beantworten (KI-002 Weg A, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale: kein Sprachmodell).

„Warum ist Position 3 teurer als Position 2?“: beide Preise je Teil werden in dieselben Bausteine geteilt
(herkunft.bausteine: Material, Laser, Rüsten, Zusatzarbeiten, Zukauf, Schweißen, Übriges, Zuschläge und Gewinn im
Verhältnis); die Antwort nennt die Unterschiede je Baustein, größter zuerst, mit den Zahlen, die dahinter stehen
(Länge, Profil, Laserzeit, Stückzahl …). Die Unterschiede ergeben zusammen genau den Preisunterschied. Es werden nur
Zahlen der Kalkulation genannt, keine geschätzten. Ohne Qt, ohne Netz."""
from . import herkunft, rechnen

GRENZE = 0.005          # € je Teil: kleinere Unterschiede nennt die Antwort nicht einzeln (stehen unter „Rest“)


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _je_baustein(z, p, kopf, k, tabellen):
    out = {}
    for b in herkunft.bausteine(z, p, kopf, k, tabellen):
        name = b["baustein"].split(":")[0]
        out[name] = out.get(name, 0.0) + b["eur"]
    return out


def _grund(name, za, pa, zb, pb):
    """Zahlen hinter einem Baustein (nur vorhandene Werte)."""
    z = rechnen.zahl
    if name == "Material":
        teile = []
        if pa.get("profil_id") != pb.get("profil_id"):
            teile.append(f"Profil {pa.get('profil_id')} statt {pb.get('profil_id')}")
        if pa.get("werkstoff_id") != pb.get("werkstoff_id"):
            teile.append(f"Werkstoff {pa.get('werkstoff_id')} statt {pb.get('werkstoff_id')}")
        if _n(pa.get("laenge")) != _n(pb.get("laenge")):
            teile.append(f"Länge {z(_n(pa.get('laenge')), 0)} statt {z(_n(pb.get('laenge')), 0)} mm")
        return ", ".join(teile)
    if name == "Laser":
        return (f"Laserzeit {z(_n(za.get('laser_netto')), 1)} statt {z(_n(zb.get('laser_netto')), 1)} s je Teil"
                + (f", Schneidweg {z(_n(pa.get('schneidweg')), 0)} statt {z(_n(pb.get('schneidweg')), 0)} mm"
                   if _n(pa.get("schneidweg")) != _n(pb.get("schneidweg")) else "")
                + (f", Einstiche {z(_n(pa.get('einstiche')), 0)} statt {z(_n(pb.get('einstiche')), 0)}"
                   if _n(pa.get("einstiche")) != _n(pb.get("einstiche")) else ""))
    if name == "Rüsten":
        return (f"Rüsten auf {z(_n(za.get('stueck')), 0)} statt {z(_n(zb.get('stueck')), 0)} Teile umgelegt"
                if _n(za.get("stueck")) != _n(zb.get("stueck")) else "")
    if name == "Zusatzarbeiten":
        return f"{z(_n(za.get('zusatz_teil')))} statt {z(_n(zb.get('zusatz_teil')))} € je Teil vor Zuschlägen"
    if name == "Zukauf":
        return f"Zukaufteile {z(_n(za.get('zukauf_teil')))} statt {z(_n(zb.get('zukauf_teil')))} € je Teil"
    if name == "Qualität":
        return f"Qualitätsstufe {pa.get('qualitaet') or 'keine'} statt {pb.get('qualitaet') or 'keine'}"
    return ""


def warum(i, j, kopf, positionen, zeilen, k, tabellen):
    """Unterschied Position i gegen Position j (Indizes): dict(frage, antwort, preis_a, preis_b, unterschied,
    gruende=[dict(baustein, eur, text)], rest). Summe der gruende + rest = unterschied (je Teil)."""
    pa, pb = positionen[i], positionen[j]
    za, zb = zeilen[i], zeilen[j]
    frage = f"Warum kostet Pos. {pa.get('pos')} je Teil mehr oder weniger als Pos. {pb.get('pos')}?"
    if za is None or zb is None:
        return dict(frage=frage, antwort="Eine der Positionen ist nicht gerechnet.", gruende=[], unterschied=None,
                    preis_a=None, preis_b=None, rest=0.0)
    a, b = _je_baustein(za, pa, kopf, k, tabellen), _je_baustein(zb, pb, kopf, k, tabellen)
    preis_a, preis_b = _n(za.get("preis_teil")), _n(zb.get("preis_teil"))
    diff = preis_a - preis_b
    gruende = []
    for name in sorted(set(a) | set(b), key=lambda n: -abs(a.get(n, 0.0) - b.get(n, 0.0))):
        d = a.get(name, 0.0) - b.get(name, 0.0)
        if abs(d) >= GRENZE:
            gruende.append(dict(baustein=name, eur=d, text=_grund(name, za, pa, zb, pb)))
    rest = diff - sum(g["eur"] for g in gruende)        # kleine Bausteine: Summe der Gründe + Rest = Unterschied
    z = rechnen.zahl
    if abs(diff) < GRENZE:
        kopfsatz = f"Pos. {pa.get('pos')} und Pos. {pb.get('pos')} kosten je Teil gleich viel ({z(preis_a)} €)."
    else:
        kopfsatz = (f"Pos. {pa.get('pos')} kostet je Teil {z(abs(diff))} € {'mehr' if diff > 0 else 'weniger'} als "
                    f"Pos. {pb.get('pos')} ({z(preis_a)} gegen {z(preis_b)} €).")
    zeilen_t = [f"{g['baustein']}: {'+' if g['eur'] >= 0 else '−'}{z(abs(g['eur']))} €"
                + (f" ({g['text']})" if g["text"] else "") for g in gruende]
    if abs(rest) >= GRENZE:
        zeilen_t.append(f"Rest: {'+' if rest >= 0 else '−'}{z(abs(rest))} €")
    antwort = kopfsatz + (" Unterschiede je Teil, Zuschläge und Gewinn anteilig: " + "; ".join(zeilen_t) + "."
                          if zeilen_t else "")
    return dict(frage=frage, antwort=antwort, preis_a=preis_a, preis_b=preis_b, unterschied=diff, gruende=gruende,
                rest=rest)
