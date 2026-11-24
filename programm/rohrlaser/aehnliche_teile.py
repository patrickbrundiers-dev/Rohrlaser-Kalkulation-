"""Ähnliche Teile über einen Geometrie-Fingerabdruck (GEO-014) und Revisionsvergleich mit Preiswirkung (GEO-019),
Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“.

Fingerabdruck einer Rohrposition: Profilform und Außenmaße mit Wand, Werkstoff, Länge, Schneidweg je Meter und
Konturen klein/mittel/groß. Die Ähnlichkeit (0 … 1) gewichtet Profil 30 %, Länge 25 %, Konturen 25 % und Schneidweg
je Meter 20 %; ein anderer Werkstoff zählt × 0,8. Gleiche Profilform ist Pflicht. Gesucht wird in allen anderen
Angeboten (auch denen der Kollegen); der Wiederholteil-Abgleich (wiederholteile.py, gleiche Artikelnummer oder exakt
gleiche Geometrie) bleibt davon unberührt.

Preiswirkung einer Revision: Das Teil wird allein gerechnet, heute und je geänderter Eigenschaft mit dem alten Wert
(Profil, Werkstoff, Länge, Konturen mit Schneidweg und Einstichen). Die Differenz je Eigenschaft sagt, was die Änderung
am Preis je Stück ausmacht; „gesamt“ rechnet alle alten Werte zusammen. Der alte Angebotspreis wird nie übernommen,
er steht nur zum Vergleich daneben. Ohne Qt."""
import json
import math

from . import rechnen, wiederholteile as wt

GRENZE = 0.75               # ab dieser Ähnlichkeit wird ein Teil gezeigt
GEWICHT = dict(profil=0.30, laenge=0.25, konturen=0.25, schneidweg=0.20)
WERKSTOFF_FAKTOR = 0.8
MASS_TOL = 0.25             # Außenmaß bis 25 % anders: Profil-Anteil fällt linear auf 0
FELDER = ("id", "angebot_id", "pos", "art", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge", "stueck",
          "schneidweg", "einstiche", "klein_n", "mittel_n", "gross_n")
# Gruppen für die Preiswirkung: (Text, Felder, die zusammen auf den alten Wert gehen)
GRUPPEN = (("Profil", ("profil_id",)), ("Werkstoff", ("werkstoff_id",)), ("Länge", ("laenge",)),
           ("Konturen und Schneidweg", ("schneidweg", "einstiche", "klein_n", "mittel_n", "gross_n")))


def _z(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) else None


def fingerabdruck(p, profil):
    """dict(form, a, b, wand, werkstoff, laenge, sw_m, konturen (klein, mittel, groß)) oder None (kein Profil oder
    keine Länge)."""
    if not profil or not profil.get("form") or not _z(p.get("laenge")):
        return None
    laenge = float(p["laenge"])
    sw = _z(p.get("schneidweg"))
    return dict(form=profil["form"], a=_z(profil.get("a")) or 0.0, b=_z(profil.get("b")) or _z(profil.get("a")) or 0.0,
                wand=_z(profil.get("wand")) or 0.0, werkstoff=str(p.get("werkstoff_id") or "").strip(),
                laenge=laenge, sw_m=(sw / laenge * 1000) if sw else None,
                konturen=tuple(int(_z(p.get(n)) or 0) for n in ("klein_n", "mittel_n", "gross_n")))


def _nah(x, y, tol):
    """1 bei gleich, linear fallend auf 0 bei relativer Abweichung tol."""
    m = max(abs(x), abs(y))
    return 1.0 if m == 0 else max(0.0, 1 - abs(x - y) / m / tol)


def aehnlichkeit(f1, f2):
    """Ähnlichkeit 0 … 1 zweier Fingerabdrücke; 0 bei anderer Profilform."""
    if not f1 or not f2 or f1["form"] != f2["form"]:
        return 0.0
    prof = min(_nah(f1["a"], f2["a"], MASS_TOL), _nah(f1["b"], f2["b"], MASS_TOL))
    prof *= 1.0 if abs(f1["wand"] - f2["wand"]) < 1e-6 else 0.8
    laenge = _nah(f1["laenge"], f2["laenge"], 0.5)
    k1, k2 = f1["konturen"], f2["konturen"]
    n = max(sum(k1), sum(k2))
    kont = 1.0 if n == 0 else max(0.0, 1 - sum(abs(x - y) for x, y in zip(k1, k2)) / n)
    if f1["sw_m"] and f2["sw_m"]:
        sw = _nah(f1["sw_m"], f2["sw_m"], 0.5)
    else:
        sw = 1.0 if not f1["sw_m"] and not f2["sw_m"] else 0.5
    g = GEWICHT
    wert = g["profil"] * prof + g["laenge"] * laenge + g["konturen"] * kont + g["schneidweg"] * sw
    return wert * (1.0 if f1["werkstoff"] == f2["werkstoff"] else WERKSTOFF_FAKTOR)


def _kandidaten_profile(profil, k):
    """Profil-IDs gleicher Form mit Außenmaß innerhalb MASS_TOL (Vorfilter der Datenbank)."""
    a = _z(profil.get("a")) or 0.0
    out = []
    for pid, pr in (k.profile or {}).items():
        if pr.get("form") == profil.get("form") and _nah(a, _z(pr.get("a")) or 0.0, MASS_TOL) > 0:
            out.append(pid)
    return out


def suchen(db, angebot_id, p, k, grenze=GRENZE, n=30):
    """Ähnliche Teile zur Position p in anderen Angeboten: [dict(aehnlichkeit, position, angebot, preis
    (Menge, € je Stück) oder None, unterschiede [Texte])], ähnlichste zuerst, höchstens n."""
    profil = (k.profile or {}).get(p.get("profil_id"))
    fp = fingerabdruck(p, profil)
    if fp is None:
        return []
    pids = _kandidaten_profile(profil, k)
    if not pids:
        return []
    spalten = ", ".join(f'p."{f}"' for f in FELDER)
    sql = (f"SELECT {spalten}, a.nummer AS _nummer, a.kunde AS _kunde, a.kundennr AS _kundennr, a.datum AS _datum, "
           "a.vorgang AS _vorgang, a.fremd AS _fremd, a.staffelpreise AS _sp FROM positionen p "
           "JOIN angebote a ON a.id = p.angebot_id WHERE p.angebot_id != ? AND p.laenge BETWEEN ? AND ? "
           f"AND p.profil_id IN ({', '.join('?' * len(pids))})")
    zeilen = db.con.execute(sql, [angebot_id, fp["laenge"] * 0.5, fp["laenge"] * 1.5] + pids)
    out, staffeln = [], {}
    for z in (dict(r) for r in zeilen):
        alt = {f: z[f] for f in FELDER}
        w = aehnlichkeit(fp, fingerabdruck(alt, (k.profile or {}).get(alt.get("profil_id"))))
        if w < grenze:
            continue
        if z["angebot_id"] not in staffeln:
            try:
                staffeln[z["angebot_id"]] = json.loads(z["_sp"]) if z["_sp"] else None
            except ValueError:
                staffeln[z["angebot_id"]] = None
        out.append(dict(aehnlichkeit=w, position=alt,
                        angebot=dict(id=z["angebot_id"], nummer=z["_nummer"], kunde=z["_kunde"],
                                     kundennr=z["_kundennr"], datum=z["_datum"], vorgang=z["_vorgang"] or "Entwurf",
                                     fremd=bool(z["_fremd"])),
                        preis=wt.preis_aus_staffeln(staffeln[z["angebot_id"]], z["pos"], z["stueck"]),
                        unterschiede=wt.aenderungen(p, alt)))
    out.sort(key=lambda x: (-x["aehnlichkeit"], x["angebot"]["vorgang"] != "Beauftragt",
                            str(x["angebot"]["datum"] or "")))
    return out[:n]


def _preis(kopf, p, k, tabellen, einst_db):
    """Preis je Stück der Position allein gerechnet (eigene Optimierung) oder None."""
    q = dict(p, id=p.get("id") or -1)
    try:
        erg = rechnen.optimieren(kopf, [q], k, tabellen, einst_db)
        zeilen, _ = rechnen.kalkulation(kopf, [q], erg, k, tabellen, rechnen.einstellungen_angebot(kopf, einst_db))
    except Exception:           # noqa: BLE001 – unvollständige Daten: ohne Preiswirkung
        return None
    z = zeilen[0] if zeilen else None
    return _z((z or {}).get("preis_teil"))


def preiswirkung(kopf, p, alt, k, tabellen, einst_db):
    """GEO-019: dict(heute, alt_gerechnet, gesamt, teile [(Text, € je Stück)]) – heute = Preis je Stück der Position
    allein, alt_gerechnet = mit allen alten Werten (heute gerechnet), teile = Wirkung je geänderter Eigenschaft
    (heute − mit diesem alten Wert). None, wenn sich nichts rechnen lässt."""
    heute = _preis(kopf, p, k, tabellen, einst_db)
    if heute is None:
        return None
    teile, alle = [], dict(p)
    for text, felder in GRUPPEN:
        if all(alt.get(f) in (None, "") or alt.get(f) == p.get(f) for f in felder):
            continue
        q = dict(p, **{f: alt.get(f) for f in felder if alt.get(f) not in (None, "")})
        alle.update({f: alt.get(f) for f in felder if alt.get(f) not in (None, "")})
        w = _preis(kopf, q, k, tabellen, einst_db)
        if w is not None and abs(heute - w) >= 0.005:
            teile.append((text, heute - w))
    damals = _preis(kopf, alle, k, tabellen, einst_db) if teile else heute
    return dict(heute=heute, alt_gerechnet=damals, gesamt=heute - damals if damals is not None else None, teile=teile)


def preiswirkung_text(w):
    """„Länge +1,20 €, Konturen und Schneidweg +0,35 € je Stück (zusammen +1,55 €)“ oder ''."""
    if not w or not w["teile"]:
        return ""
    e = (lambda x: ("+" if x > 0 else "−") + f"{abs(x):.2f}".replace(".", ",") + " €")
    s = ", ".join(f"{t} {e(d)}" for t, d in w["teile"]) + " je Stück"
    if w["gesamt"] is not None and len(w["teile"]) > 1:
        s += f" (zusammen {e(w['gesamt'])})"
    return s
