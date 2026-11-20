"""Rahmenauftrags- und Abrufkalkulation (Patrick 20.11.2026, Master-Auftrag „Intelligente Rahmenauftrags- und
Abrufkalkulation“, Konzept-Doc „Konzept Rahmenaufträge und Abrufkalkulation“). Ohne Qt.

Grundsatz: Die Kosten eines Fertigungsloses kommen NUR aus der zentralen Rechnung (staffeln.stufe_lauf +
stufe_bepreisen mit ausgeschaltetem Abruf-Haken, siehe kostenmodell_aus_angebot). Dieses Modul rechnet nur, was
darüber liegt: Zeitpunkte, Lager, Kapitalbindung, Materialeinkauf, Lieferungen, Losbildung und den Preis des
Rahmens. So gibt es keine zweite Teilekalkulation und keine doppelt gezählten Kosten.

Kostenmodell je Position p (aus zwei Läufen der zentralen Rechnung, kleiner Abruf q1 und Rahmenmenge q2):
  Fertigung je Los = F_p + vf_p · q   (F = Rüsten, Stangenwechsel, Pauschalen je Los …; vf = Fertigung + Zukauf)
  Material je Stück m_p, Zukauf je Stück z_p (Teil von vf, ohne Gewinn), Programmierung P_p (einmalig),
  Fracht je Lieferung fr0_p + fr1_p · q.
Kostenklassen, jede genau einmal:
  einmalig    Programmierung (je weiteres Los + Wiederholanteil), Vorrichtung/Muster (Parameter einmalig_eur)
  je Los      F_p (nur Positionen mit Menge im Los)
  je Stück    vf_p, m_p
  je Abruf    Fracht, Verpackung, Kommissionierung, Lieferabwicklung
  je Rahmen   Lagerplatz, Kapitalbindung (Fertigteile und vorgekauftes Material), Verwaltung
Gewinn G = Gewinnsatz × (Selbstkosten − Zukauf); kein Gewinn auf Zukauf und Fracht (wie die zentrale Rechnung).
Mindestmarge über staffeln.marge_anhebung (Paket P1 Angebotswesen), solange es die noch nicht gibt, die gleiche
Formel hier (mindestmarge_anheben).

Varianten: A = ein Los je Abruf, B = ein Los zu Beginn, C = optimale Lose (Wagner-Whitin, exakt über alle
Gruppierungen aufeinanderfolgender Abrufe); dazu feste Losgrößen (100 / 250 / 500 / 1.000, auf ganze Abrufe
gerundet) und die Andler-Losgröße als Richtwert. Material getrennt: je Los, gesamt zu Beginn oder beigestellt,
mit Preisstaffel nach kg, Mindestbestellmenge und Bestellkosten; was über den Bedarf gekauft wird, bleibt auf dem
Materialkonto des Rahmens und mindert den nächsten Einkauf (kein allgemeines Restelager).
"""
import calendar
import datetime
import math

MONAT_TAGE = 30.4375

# Material
JE_LOS, GESAMT, BEISTELLUNG = "je Los", "gesamt zu Beginn", "Beistellung Kunde"
MATERIAL_ARTEN = (JE_LOS, GESAMT, BEISTELLUNG)

# Varianten
A, B, C = "A", "B", "C"
VARIANTE_TEXT = {A: "Fertigung je Abruf", B: "Gesamtmenge auf einmal", C: "Optimierte Losgrößen"}
FESTE_LOSE = (100, 250, 500, 1000)
STAFFEL_MENGEN = (100, 250, 500, 1000, 2500, 5000)

# Vorgaben (Einstellungen rahmen_*, alle änderbar; 0 = aus)
VORGABEN = dict(
    zins=6.0,                   # Kapitalzins % p. a. (Fertigteile und vorgekauftes Material)
    lagerplatz=15.0,            # € je Palettenplatz und Monat
    teile_palette=200.0,        # Teile je Palette (für Lagerplatz)
    einlagern=10.0,             # € je Los, das (teilweise) eingelagert wird
    prog_wiederholung=10.0,     # % der Programmierung je weiterem Los (Programm laden, prüfen)
    kommission_min=10.0,        # Minuten Kommissionieren/Verpacken je Abruf
    kommission_satz=45.0,       # €/h Versand
    verpackung=0.0,             # € je Abruf (Packmittel, falls nicht in der Fracht)
    abwicklung=15.0,            # € je Abruf (Lieferschein, Avis, Disposition)
    verwaltung=0.0,             # € je Rahmen (Vertrag, Pflege)
    einmalig=0.0,               # € einmalig (Vorrichtung, Werkzeug) je Rahmen
    bestellkosten=25.0,         # € je Materialbestellung
    moq_kg=0.0,                 # Mindestbestellmenge Material [kg]
    max_lagerdauer=0.0,         # höchstens so viele Monate auf Lager (0 = ohne Grenze)
    gleit_schwelle=2.0,         # % Bagatellgrenze der Gleitklausel
)


def _n(x):
    if isinstance(x, bool):
        return 0.0
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def parameter(einst=None, rahmen_par=None):
    """Wirksame Parameter: Rahmen vor Einstellungen (rahmen_<name>) vor Vorgabe."""
    e, r = einst or {}, rahmen_par or {}
    out = {}
    for n, v in VORGABEN.items():
        w = r.get(n)
        if w is None or w == "":
            w = e.get(f"rahmen_{n}")
        out[n] = _n(w) if w is not None and w != "" else v
    out["staffel"] = sorted(((_n(a), _n(b)) for a, b in (r.get("material_staffel") or ())), key=lambda t: t[0])
    return out


def datum(t):
    if isinstance(t, datetime.date):
        return t
    try:
        return datetime.date.fromisoformat(str(t)[:10])
    except (TypeError, ValueError):
        return None


def monate(a, b):
    """Monate von a bis b (Kalendertage ÷ 30,4375), nie negativ."""
    da, db_ = datum(a), datum(b)
    if not da or not db_:
        return 0.0
    return max(0.0, (db_ - da).days / MONAT_TAGE)


# ------------------------------------------------------------------ Kostenmodell
def modell_zeile(F=0.0, vf=0.0, m=0.0, z=0.0, P=0.0, fr0=0.0, fr1=0.0, kg=0.0):
    return dict(F=F, vf=vf, m=m, z=z, P=P, fr0=fr0, fr1=fr1, kg=kg)


def _gerade(q1, w1, q2, w2):
    """(Achsenabschnitt, Steigung) durch zwei Punkte; bei gleicher Menge alles als Steigung."""
    if q2 > q1 > 0:
        s = (w2 - w1) / (q2 - q1)
        return w1 - s * q1, s
    return 0.0, (w2 / q2 if q2 else 0.0)


def modell_aus_laeufen(lauf1, lauf2, q1, q2, kg=None):
    """Kostenmodell aus zwei Preisläufen der zentralen Rechnung je Position: lauf = {pos: preise-dict} (Felder
    selbst, programmierung, m_gesamt, zukauf_einstand, zukauf_aufschlag, fracht, gewinn, gewinn_basis), q = {pos:
    Menge}. Ergebnis dict(pos={pos: modell_zeile}, gewinn=Satz, skonto=Anteil)."""
    pos, g_sum, gb_sum, sk = {}, 0.0, 0.0, 0.0
    for p, b in lauf2.items():
        a = lauf1.get(p) or b
        qa, qb = _n(q1.get(p)), _n(q2.get(p))
        fert = lambda x: _n(x.get("selbst")) - _n(x.get("programmierung")) - _n(x.get("m_gesamt"))   # noqa: E731
        F, vf = _gerade(qa, fert(a), qb, fert(b))
        fr0, fr1 = _gerade(qa, _n(a.get("fracht")), qb, _n(b.get("fracht")))
        z = (_n(b.get("zukauf_einstand")) + _n(b.get("zukauf_aufschlag"))) / qb if qb else 0.0
        pos[p] = modell_zeile(F=max(F, 0.0), vf=vf if F >= 0 else fert(b) / qb if qb else 0.0,
                              m=_n(b.get("m_gesamt")) / qb if qb else 0.0, z=z, P=_n(b.get("programmierung")),
                              fr0=max(fr0, 0.0), fr1=fr1 if fr0 >= 0 else (_n(b.get("fracht")) / qb if qb else 0.0),
                              kg=_n((kg or {}).get(p)))
        g_sum += _n(b.get("gewinn"))
        gb_sum += _n(b.get("gewinn_basis"))
        sk = _n(b.get("skonto_anteil")) or sk
    return dict(pos=pos, gewinn=g_sum / gb_sum if gb_sum > 0 else 0.0, skonto=sk)


def preislauf(kopf, positionen, mengen, k, tabellen, einst):
    """EIN Lauf der zentralen Rechnung für ein Los: mengen = {pos: Stück}, alle zusammen optimiert und kalkuliert
    (Rüsten der Maschine einmal je Los), Abruf-Haken aus. Ergebnis {pos: preise-dict} oder Fehlertext (str)."""
    from . import rechnen, staffeln
    kp = dict(kopf, abruf=None)
    mz = [dict(schluessel=str(p), menge=int(q)) for p, q in mengen.items() if _n(q) > 0]
    if not mz:
        return {}
    e = rechnen.einstellungen_angebot(kp, einst) if "gewinn" not in einst else einst
    lz = staffeln.stufe_lauf(kp, positionen, {}, mz, k, tabellen, e)
    bep = staffeln.stufe_bepreisen(lz, {}, mz, staffeln.stufe_einst(kp, {}, e))
    out = {}
    for x, z in zip(bep, mz):
        pr = x.get("preis")
        if not pr or pr.get("fehler"):
            return (pr or {}).get("fehler") or x.get("hinweis") or f"Pos. {z['schluessel']}: keine Kalkulation"
        out[z["schluessel"]] = dict(pr, kg_brutto=0.0)
    # gekauftes Materialgewicht (Stangen mit Verschnitt) je Position: kg der Abmessung nach Teilelänge × Menge
    sch = next((x.get("schnittschema") for x in lz if x.get("schnittschema")), None)
    laenge = {str(p.get("pos")): _n(p.get("laenge")) for p in positionen}
    for g in (sch or {}).get("abmessungen") or ():
        if g.get("kunde"):
            continue
        teile = [str(p) for p in g.get("positionen") or () if str(p) in out]
        anteil = {p: laenge.get(p, 0.0) * _n(mengen.get(p)) for p in teile}
        summe = sum(anteil.values())
        for p in teile:
            if summe:
                out[p]["kg_brutto"] += _n(g.get("kg")) * anteil[p] / summe
    return out


def kostenmodell_aus_angebot(kopf, positionen, rahmen_pos, abrufe, k, tabellen, einst):
    """Kostenmodell aus dem Angebot (zentrale Rechnung): q1 = kleinster Abruf je Position, q2 = Rahmenmenge.
    rahmen_pos = [dict(pos, menge, kg_teil)]. Ergebnis (modell, laeufe) oder (None, Fehlertext)."""
    q2 = {str(p["pos"]): int(_n(p.get("menge"))) for p in rahmen_pos if _n(p.get("menge")) > 0}
    q1 = {}
    for p in q2:
        mengen = [_n((a.get("mengen") or {}).get(p)) for a in abrufe if _n((a.get("mengen") or {}).get(p)) > 0]
        q1[p] = int(min(mengen)) if mengen else q2[p]
    l2 = preislauf(kopf, positionen, q2, k, tabellen, einst)
    if isinstance(l2, str):
        return None, l2
    l1 = l2 if q1 == q2 else preislauf(kopf, positionen, q1, k, tabellen, einst)
    if isinstance(l1, str):
        return None, l1
    # kg je Teil: von Hand am Rahmen, sonst gekauftes Gewicht (mit Verschnitt) aus dem Lauf der Rahmenmenge
    kg = {str(p["pos"]): _n(p.get("kg_teil")) or (_n(l2.get(str(p["pos"]), {}).get("kg_brutto")) / q2[str(p["pos"])]
                                                  if q2.get(str(p["pos"])) else 0.0) for p in rahmen_pos}
    return modell_aus_laeufen(l1, l2, q1, q2, kg), dict(q1=q1, q2=q2, laeufe=(l1, l2))


# ------------------------------------------------------------------ Mindestmarge (zentral: staffeln, Paket P1)
def mindestmarge_anheben(gewinn, anhebung, selbst, m):
    """Anhebung auf die Ware, damit die Marge (G + Anhebung) ÷ (S + G + Anhebung) mindestens m ist:
    max(0, m·S/(1−m) − G − bisherige Anhebung). Nutzt staffeln.marge_anhebung, sobald es die gibt."""
    from . import staffeln
    f = getattr(staffeln, "marge_anhebung", None)
    if f is not None:
        return f(gewinn, anhebung, selbst, m)
    if not m or m <= 0 or m >= 1:
        return 0.0
    return max(0.0, m * selbst / (1 - m) - gewinn - anhebung)


def mindestmarge_satz(einst):
    from . import staffeln
    f = getattr(staffeln, "mindestmarge", None)
    if f is not None:
        return _n(f(einst or {}))
    return _n((einst or {}).get("mindestmarge"))


# ------------------------------------------------------------------ Bewertung eines Losplans
def _summe(abrufe, idx, p):
    return sum(_n((abrufe[i].get("mengen") or {}).get(p)) for i in idx)


def _material_preis(kg_menge, eur, staffel):
    """Material-€ nach der Preisstaffel (Rabatt % ab kg, höchste erreichte Stufe)."""
    rabatt = 0.0
    for ab, r in staffel:
        if kg_menge >= ab:
            rabatt = r
    return eur * (1 - rabatt / 100), rabatt


def bewerten(lose, abrufe, modell, par, material=JE_LOS, start=None, marge_min=0.0):
    """Kosten eines Losplans. lose = [[Index der Abrufe], …] (je Los aufeinanderfolgende Abrufe; das Los wird zum
    Termin seines ersten Abrufs gefertigt), abrufe = [dict(datum, mengen={pos: Stück})] nach Datum. Ergebnis dict
    mit allen Posten, je_los, material_kaeufe, selbst, gewinn, anhebung, fracht, preis_stueck, marge."""
    pos = modell["pos"]
    t0 = datum(start) or (datum(abrufe[0]["datum"]) if abrufe else None)
    zins = par["zins"] / 100
    fert = ruest = prog = lager = kapital = handling = 0.0
    je_los = []
    for n, idx in enumerate(lose):
        t = abrufe[idx[0]]["datum"]
        q = {p: _summe(abrufe, idx, p) for p in pos}
        f_los = sum(pos[p]["F"] for p in pos if q[p] > 0)
        v_los = sum(pos[p]["vf"] * q[p] for p in pos)
        lg = kz = 0.0
        for i in idx[1:]:
            mon = monate(t, abrufe[i]["datum"])
            for p in pos:
                qi = _n((abrufe[i].get("mengen") or {}).get(p))
                if qi <= 0:
                    continue
                wert = pos[p]["vf"] + pos[p]["m"]          # Herstellwert je Teil (ohne Losfixkosten)
                kz += qi * wert * zins / 12 * mon
                lg += qi / max(par["teile_palette"], 1) * par["lagerplatz"] * mon
        eingelagert = len(idx) > 1
        ruest += f_los
        fert += v_los
        lager += lg + (par["einlagern"] if eingelagert else 0.0)
        handling += par["einlagern"] if eingelagert else 0.0
        kapital += kz
        je_los.append(dict(nr=n + 1, datum=t, abrufe=[i + 1 for i in idx], mengen=q, stueck=sum(q.values()),
                           ruesten=f_los, fertigung=v_los, lager=lg, kapital=kz))
    P = sum(pos[p]["P"] for p in pos)
    prog = P + max(len(lose) - 1, 0) * P * par["prog_wiederholung"] / 100
    # Lieferungen: je Abruf gleich, egal wie gefertigt wird
    fracht = liefer = 0.0
    for a in abrufe:
        q = a.get("mengen") or {}
        fracht += sum(pos[p]["fr0"] + pos[p]["fr1"] * _n(q.get(p)) for p in pos if _n(q.get(p)) > 0)
        liefer += par["kommission_min"] / 60 * par["kommission_satz"] + par["verpackung"] + par["abwicklung"]
    mat = material_rechnen(lose, abrufe, modell, par, material, t0, _n(par.get("bestand_kg")),
                           _n(par.get("bestand_eur")))
    zukauf = sum(pos[p]["z"] * _summe(abrufe, range(len(abrufe)), p) for p in pos)
    einmalig = par["einmalig"] + par["verwaltung"]
    selbst = ruest + fert + prog + lager + kapital + liefer + mat["kosten"] + mat["kapital"] + einmalig
    gewinn = modell["gewinn"] * max(selbst - zukauf, 0.0)
    anhebung = mindestmarge_anheben(gewinn, 0.0, selbst, marge_min) if marge_min else 0.0
    menge = sum(_n(v) for a in abrufe for v in (a.get("mengen") or {}).values())
    sk = modell.get("skonto") or 0.0
    netto = (selbst + gewinn + anhebung + fracht) / (1 - sk) if sk < 1 else 0.0
    marge = (gewinn + anhebung) / (selbst + gewinn + anhebung) if selbst + gewinn + anhebung else None
    marge_ohne = gewinn / (selbst + gewinn) if selbst + gewinn else None
    return dict(lose=len(lose), je_los=je_los, ruesten=ruest, fertigung=fert, programmierung=prog, lager=lager,
                kapital=kapital, lieferung=liefer, fracht=fracht, material=mat["kosten"],
                material_kapital=mat["kapital"], material_kaeufe=mat["kaeufe"], material_rest=mat["rest"],
                material_hinweis=mat["hinweis"], zukauf=zukauf, einmalig=einmalig, selbst=selbst, gewinn=gewinn,
                anhebung=anhebung, netto=netto, menge=menge, preis_stueck=netto / menge if menge else 0.0,
                selbst_stueck=selbst / menge if menge else 0.0, marge=marge, marge_ohne=marge_ohne,
                unter_mindestmarge=bool(marge_min and marge_ohne is not None and marge_ohne < marge_min - 1e-9),
                material_art=material, handling=handling)


def material_rechnen(lose, abrufe, modell, par, material, t0, bestand_kg=0.0, bestand_eur=0.0):
    """Materialeinkauf getrennt von der Fertigung. JE_LOS: zu jedem Los Bedarf − Konto (mindestens die
    Mindestbestellmenge), Überschuss bleibt auf dem Materialkonto des Rahmens; GESAMT: alles zum ersten Los;
    BEISTELLUNG: kein Material. Kapitalbindung für Material, das vor seinem Los gekauft wurde.
    bestand = schon gekauftes Material des Rahmens (wird nie nochmal gekauft)."""
    pos = modell["pos"]
    zins = par["zins"] / 100
    bedarf = []                                     # je Los (kg, € zum Grundpreis)
    for idx in lose:
        kg = eur = 0.0
        for p in pos:
            q = _summe(abrufe, idx, p)
            kg += q * pos[p]["kg"]
            eur += q * pos[p]["m"]
        bedarf.append((abrufe[idx[0]]["datum"], kg, eur))
    if material == BEISTELLUNG or not bedarf:
        return dict(kosten=0.0, kapital=0.0, kaeufe=[], rest=dict(kg=0.0, eur=0.0), hinweis="")
    mit_kg = all(pos[p]["kg"] > 0 for p in pos)
    hinweis = "" if mit_kg else "Gewicht je Teil fehlt: Preisstaffel und Mindestbestellmenge nicht angewendet"
    eur_je_kg = sum(b[2] for b in bedarf) / sum(b[1] for b in bedarf) if mit_kg and sum(b[1] for b in bedarf) else 0
    konto_kg, konto_eur = bestand_kg, bestand_eur
    kaeufe, kosten, kapital = [], 0.0, 0.0
    if material == GESAMT:
        kg = sum(b[1] for b in bedarf)
        eur = sum(b[2] for b in bedarf)
        kg_neu = max(kg - konto_kg, 0.0) if mit_kg else 0.0
        eur_neu = max(eur - konto_eur, 0.0) if not mit_kg else kg_neu * eur_je_kg
        if mit_kg and par["moq_kg"] > kg_neu > 0:
            kg_neu, eur_neu = par["moq_kg"], par["moq_kg"] * eur_je_kg
        if eur_neu > 0:
            preis, rabatt = _material_preis(kg_neu, eur_neu, par["staffel"] if mit_kg else ())
            kaeufe.append(dict(datum=bedarf[0][0], kg=kg_neu, eur=preis, rabatt=rabatt))
            kosten = preis + par["bestellkosten"]
            faktor = preis / eur_neu
            for t, _kg, e in bedarf[1:]:            # Material späterer Lose liegt seit dem Kauf
                kapital += e * faktor * zins / 12 * monate(bedarf[0][0], t)
        rest_kg = konto_kg + kg_neu - kg if mit_kg else 0.0
        rest_eur = rest_kg * eur_je_kg if mit_kg else max(konto_eur + eur_neu - eur, 0.0)
        return dict(kosten=kosten, kapital=kapital, kaeufe=kaeufe, rest=dict(kg=max(rest_kg, 0), eur=max(rest_eur, 0)),
                    hinweis=hinweis)
    kauf_t = None
    for t, kg, eur in bedarf:
        if mit_kg:
            nimm = min(konto_kg, kg)
            # Überschuss eines früheren Kaufs lag seit damals auf dem Konto
            if nimm > 0 and kauf_t:
                kapital += nimm * eur_je_kg * zins / 12 * monate(kauf_t, t)
            konto_kg -= nimm
            kg_neu = kg - nimm
            if kg_neu > 1e-9 and par["moq_kg"] > kg_neu:
                kauf = par["moq_kg"]
            else:
                kauf = kg_neu
            if kauf > 1e-9:
                preis, rabatt = _material_preis(kauf, kauf * eur_je_kg, par["staffel"])
                kaeufe.append(dict(datum=t, kg=kauf, eur=preis, rabatt=rabatt))
                kosten += preis + par["bestellkosten"]
                konto_kg += kauf - kg_neu
                kauf_t = t
        else:
            nimm = min(konto_eur, eur)
            konto_eur -= nimm
            if eur - nimm > 1e-9:
                kaeufe.append(dict(datum=t, kg=0.0, eur=eur - nimm, rabatt=0.0))
                kosten += eur - nimm + par["bestellkosten"]
    return dict(kosten=kosten, kapital=kapital, kaeufe=kaeufe,
                rest=dict(kg=konto_kg if mit_kg else 0.0, eur=konto_kg * eur_je_kg if mit_kg else konto_eur),
                hinweis=hinweis)


# ------------------------------------------------------------------ Varianten
def abrufe_ordnen(abrufe):
    """Abrufe für die Planung: ohne Stornierte, mit Menge, nach Datum (gleicher Tag = ein Abruf)."""
    from . import rahmenauftrag as ra
    tage = {}
    for a in abrufe:
        if a.get("status") == ra.STORNIERT:
            continue
        mengen = {str(p): _n(q) for p, q in (a.get("mengen") or {}).items() if _n(q) > 0}
        d = datum(a.get("datum") or a.get("plan_datum"))
        if not mengen or not d:
            continue
        z = tage.setdefault(d.isoformat(), dict(datum=d.isoformat(), mengen={}, nr=[]))
        for p, q in mengen.items():
            z["mengen"][p] = z["mengen"].get(p, 0.0) + q
        z["nr"].append(a.get("nr"))
    return [tage[t] for t in sorted(tage)]


def _losplan_kosten(i, j, abrufe, modell, par, material, t0):
    """Kosten eines Loses über die Abrufe i..j (für die Losoptimierung, ohne Lieferkosten, die überall gleich
    sind). Bei GESAMT gehen die Materialkosten in die Bewertung, hier nur ihre Kapitalbindung."""
    idx = list(range(i, j + 1))
    if par["max_lagerdauer"] and monate(abrufe[i]["datum"], abrufe[j]["datum"]) > par["max_lagerdauer"] + 1e-9:
        return math.inf
    r = bewerten([idx], abrufe, modell, dict(par, prog_wiederholung=0.0, einmalig=0.0, verwaltung=0.0,
                                             kommission_min=0.0, verpackung=0.0, abwicklung=0.0),
                 material=JE_LOS if material == JE_LOS else BEISTELLUNG, start=t0)
    k = r["ruesten"] + r["fertigung"] + r["lager"] + r["kapital"] + r["material"] + r["material_kapital"]
    if material == GESAMT:
        eur = sum(modell["pos"][p]["m"] * _summe(abrufe, idx, p) for p in modell["pos"])
        k += eur * par["zins"] / 100 / 12 * monate(t0, abrufe[i]["datum"])
    P = sum(modell["pos"][p]["P"] for p in modell["pos"])
    return k + P * par["prog_wiederholung"] / 100        # jedes Los; das erste wird unten wieder abgezogen


def optimal(abrufe, modell, par, material=JE_LOS, t0=None):
    """Wagner-Whitin: kostengünstigste Aufteilung der Abrufe in Lose aufeinanderfolgender Abrufe (exakt)."""
    n = len(abrufe)
    if not n:
        return []
    t0 = t0 or abrufe[0]["datum"]
    best = [0.0] + [math.inf] * n
    von = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(1, j + 1):
            c = best[i - 1] + _losplan_kosten(i - 1, j - 1, abrufe, modell, par, material, t0)
            if c < best[j] - 1e-9:
                best[j], von[j] = c, i
    lose, j = [], n
    while j > 0:
        i = von[j]
        lose.append(list(range(i - 1, j)))
        j = i - 1
    return lose[::-1]


def vollsuche(abrufe, modell, par, material=JE_LOS, start=None):
    """Alle 2^(n−1) Aufteilungen (nur für die Gegenprüfung kleiner Fälle). Ergebnis (bestes Ergebnis, Lose)."""
    n = len(abrufe)
    best = None
    for maske in range(2 ** max(n - 1, 0)):
        lose, akt = [], [0]
        for i in range(1, n):
            if maske >> (i - 1) & 1:
                lose.append(akt)
                akt = [i]
            else:
                akt.append(i)
        lose.append(akt)
        if par["max_lagerdauer"] and any(monate(abrufe[x[0]]["datum"], abrufe[x[-1]]["datum"]) >
                                         par["max_lagerdauer"] + 1e-9 for x in lose):
            continue
        r = bewerten(lose, abrufe, modell, par, material, start)
        if best is None or r["selbst"] < best[0]["selbst"] - 1e-9:
            best = (r, lose)
    return best


def feste_lose(abrufe, groesse):
    """Feste Losgröße auf ganze Abrufe gerundet: ein Los nimmt so viele aufeinanderfolgende Abrufe, bis es
    mindestens die Losgröße hat (der Rest am Ende ist kleiner)."""
    lose, akt, summe = [], [], 0.0
    for i, a in enumerate(abrufe):
        akt.append(i)
        summe += sum(_n(v) for v in (a.get("mengen") or {}).values())
        if summe >= groesse - 1e-9:
            lose.append(akt)
            akt, summe = [], 0.0
    if akt:
        lose.append(akt)
    return lose


def andler(abrufe, modell, par):
    """Andler-Losgröße (Richtwert, gleichmäßiger Bedarf): √(2 · F · D ÷ h); D = Stück je Jahr, F = Losfixkosten,
    h = (Herstellwert × Zins + Lagerplatz × 12 ÷ Teile je Palette) je Stück und Jahr."""
    if not abrufe:
        return None
    menge = sum(_n(v) for a in abrufe for v in (a.get("mengen") or {}).values())
    mon = monate(abrufe[0]["datum"], abrufe[-1]["datum"]) or 12.0
    d = menge / mon * 12 if len(abrufe) > 1 else menge
    pos = modell["pos"]
    gesamt = sum(_summe(abrufe, range(len(abrufe)), p) for p in pos) or 1.0
    wert = sum((pos[p]["vf"] + pos[p]["m"]) * _summe(abrufe, range(len(abrufe)), p) for p in pos) / gesamt
    F = sum(pos[p]["F"] for p in pos) + sum(pos[p]["P"] for p in pos) * par["prog_wiederholung"] / 100
    h = wert * par["zins"] / 100 + par["lagerplatz"] * 12 / max(par["teile_palette"], 1)
    return int(round(math.sqrt(2 * F * d / h))) if h > 0 and F > 0 else None


def varianten(abrufe_roh, modell, par, material=JE_LOS, start=None, marge_min=0.0, feste=FESTE_LOSE):
    """Wirtschaftlichkeitsvergleich: A, B, C (+ feste Losgrößen, Andler) für eine Materialart. Ergebnis dict(A, B,
    C, feste=[(Größe, Ergebnis)], andler, empfehlung, abrufe)."""
    abr = abrufe_ordnen(abrufe_roh) if abrufe_roh and "status" in abrufe_roh[0] else list(abrufe_roh)
    if not abr:
        return None
    n = len(abr)
    t0 = start or abr[0]["datum"]
    lose = {A: [[i] for i in range(n)], B: [list(range(n))], C: optimal(abr, modell, par, material, t0)}
    out = {}
    for v, l_ in lose.items():
        r = bewerten(l_, abr, modell, par, material, t0, marge_min)
        r["plan"] = l_
        if par["max_lagerdauer"] and any(monate(abr[x[0]]["datum"], abr[x[-1]]["datum"]) >
                                         par["max_lagerdauer"] + 1e-9 for x in l_):
            r["gesperrt"] = f"länger als {par['max_lagerdauer']:g} Monate auf Lager"
        out[v] = r
    out["feste"] = []
    for g in feste:
        lf = feste_lose(abr, g)
        r = bewerten(lf, abr, modell, par, material, t0, marge_min)
        r["plan"] = lf
        out["feste"].append((g, r))
    out["andler"] = andler(abr, modell, par)
    frei = [v for v in (A, B, C) if not out[v].get("gesperrt")]
    out["empfehlung"] = min(frei, key=lambda v: (out[v]["selbst"], "CAB".index(v))) if frei else A
    out["abrufe"] = abr
    out["material_art"] = material
    return out


def materialvergleich(abrufe_roh, modell, par, start=None, marge_min=0.0, beistellung=False):
    """Material je Los gegen Material gesamt (und Beistellung): je Materialart die beste Variante.
    Ergebnis dict(je={Materialart: varianten}, empfehlung=Materialart, ersparnis=€)."""
    arten = [JE_LOS, GESAMT] + ([BEISTELLUNG] if beistellung else [])
    je = {m: varianten(abrufe_roh, modell, par, m, start, marge_min) for m in arten}
    if not je[JE_LOS]:
        return None
    best = lambda m: je[m][je[m]["empfehlung"]]["selbst"]       # noqa: E731
    vergleich = [JE_LOS, GESAMT]
    emp = min(vergleich, key=best)
    return dict(je=je, empfehlung=emp, ersparnis=abs(best(JE_LOS) - best(GESAMT)))


# ------------------------------------------------------------------ Preisstaffel nach Rahmenmenge
def skalieren(abrufe, menge):
    """Abrufplan auf eine andere Rahmenmenge: gleiche Termine, Mengen anteilig, ganze Stück, Summe je Position
    exakt (größter Rest zuerst)."""
    abr = [dict(a, mengen=dict(a.get("mengen") or {})) for a in abrufe]
    for p in {p for a in abrufe for p in (a.get("mengen") or {})}:
        alt = sum(_n((a.get("mengen") or {}).get(p)) for a in abrufe)
        if alt <= 0:
            continue
        ziel = round(menge * alt / sum(_n(v) for a in abrufe for v in (a.get("mengen") or {}).values()))
        roh = [_n((a.get("mengen") or {}).get(p)) * ziel / alt for a in abrufe]
        ganz = [math.floor(x) for x in roh]
        rest = int(ziel - sum(ganz))
        for i in sorted(range(len(roh)), key=lambda i: roh[i] - ganz[i], reverse=True)[:rest]:
            ganz[i] += 1
        for a, g in zip(abr, ganz):
            a["mengen"][p] = g
    return [a for a in abr if any(_n(v) > 0 for v in a["mengen"].values())]


SZENARIEN = (("je Abruf gefertigt", A, JE_LOS), ("Gesamtfertigung", B, GESAMT), ("gebündelt (optimiert)", C, JE_LOS),
             ("Materialbevorratung", C, GESAMT), ("Materialbeistellung Kunde", C, BEISTELLUNG))


def preisstaffel(abrufe_roh, modell, par, mengen=STAFFEL_MENGEN, start=None, marge_min=0.0):
    """Stückpreise für verschiedene Rahmenmengen und Szenarien (A je Abruf, B gesamt, C gebündelt, C mit
    Bevorratung, C beigestellt). Ergebnis [dict(menge, szenarien=[dict(name, variante, material, selbst_stueck,
    gewinn_stueck, marge, preis_stueck, unter_mindestmarge, lose)])]."""
    abr = abrufe_ordnen(abrufe_roh) if abrufe_roh and "status" in abrufe_roh[0] else list(abrufe_roh)
    out = []
    for q in mengen:
        s = skalieren(abr, q)
        if not s:
            continue
        zeile = dict(menge=q, szenarien=[])
        cache = {}
        for name, v, mat in SZENARIEN:
            if mat not in cache:
                cache[mat] = varianten(s, modell, par, mat, start, marge_min, feste=())
            r = cache[mat][v]
            zeile["szenarien"].append(dict(name=name, variante=v, material=mat, selbst_stueck=r["selbst_stueck"],
                                           gewinn_stueck=(r["gewinn"] + r["anhebung"]) / r["menge"],
                                           marge=r["marge"], marge_ohne=r["marge_ohne"],
                                           preis_stueck=r["preis_stueck"], anhebung=r["anhebung"],
                                           unter_mindestmarge=r["unter_mindestmarge"], lose=r["lose"]))
        out.append(zeile)
    return out


# ------------------------------------------------------------------ Selbstkosten je Position (für Preisbindung)
def je_position(ergebnis, modell, abrufe):
    """Selbstkosten des Rahmens auf die Positionen verteilt (nach eigenem Anteil: Stückkosten × Menge + Losfixkosten
    × Lose + Programmierung). Ergebnis {pos: dict(menge, selbst_stueck, material_stueck)}."""
    pos = modell["pos"]
    w, q = {}, {}
    for p in pos:
        q[p] = _summe(abrufe, range(len(abrufe)), p)
        w[p] = (pos[p]["vf"] + pos[p]["m"]) * q[p] + pos[p]["F"] * ergebnis["lose"] + pos[p]["P"]
    gesamt = sum(w.values()) or 1.0
    faktor = ergebnis["netto"] / ergebnis["selbst"] if ergebnis["selbst"] else 0.0
    out = {}
    for p in pos:
        s = ergebnis["selbst"] * w[p] / gesamt / q[p] if q[p] else 0.0
        # Stückpreis-Vorschlag: gleiches Verhältnis Preis ÷ Selbstkosten wie der ganze Rahmen
        out[p] = dict(menge=q[p], selbst_stueck=s, material_stueck=pos[p]["m"], preis_stueck=round(s * faktor, 2))
    return out


# ------------------------------------------------------------------ Preisbindung und Materialpreisänderung
FEST_LAUFZEIT, FEST_BIS, MATERIAL_BIS, GLEITKLAUSEL, INDIVIDUELL, PRUEFTERMINE = (
    "Festpreis über die Laufzeit", "Festpreis bis Datum", "Materialpreisbindung bis Datum", "Materialpreisgleitklausel",
    "Individuelle Preisanpassung", "Preisüberprüfung zu Terminen")
PREISMODELLE = (FEST_LAUFZEIT, FEST_BIS, MATERIAL_BIS, GLEITKLAUSEL, INDIVIDUELL, PRUEFTERMINE)


def gebunden(bindung, heute=None):
    """(gebunden?, Text): Ist der Vertragspreis heute fest? Gleitklausel/Individuell/Prüftermine: nicht fest."""
    b = bindung or {}
    heute = datum(heute) or datetime.date.today()
    m = b.get("modell") or FEST_LAUFZEIT
    if m == FEST_LAUFZEIT:
        return True, "Festpreis über die ganze Laufzeit"
    if m in (FEST_BIS, MATERIAL_BIS):
        bis = datum(b.get("bis"))
        if bis and heute <= bis:
            return True, f"{m} {bis.strftime('%d.%m.%Y')}"
        return False, f"{m} abgelaufen" if bis else f"{m}: Datum fehlt"
    return False, m


def auswirkung(positionen_rahmen, je_pos, faktor, bindung=None, skonto=0.0, heute=None, schwelle=None):
    """Auswirkung einer Materialpreisänderung (faktor = neuer ÷ alter Materialpreis, z. B. 2,90 ÷ 2,50) auf die
    offene Restmenge. positionen_rahmen = [dict(pos, preis, offen)], je_pos = je_position(...).
    Ergebnis dict(zeilen=[…], material_alt, material_neu, differenz, selbst_alt, selbst_neu, gewinn_alt,
    gewinn_neu, marge_alt, marge_neu, erloes, gebunden, text, faellig, vorschlag={pos: neuer Preis})."""
    b = bindung or {}
    fest, text = gebunden(b, heute)
    schwelle = _n(schwelle if schwelle is not None else b.get("schwelle", VORGABEN["gleit_schwelle"])) / 100
    zeilen, s = [], dict(material_alt=0.0, material_neu=0.0, selbst_alt=0.0, erloes=0.0)
    vorschlag = {}
    for p in positionen_rahmen:
        k = str(p["pos"])
        offen, preis = _n(p.get("offen")), _n(p.get("preis"))
        x = je_pos.get(k) or {}
        m_alt = _n(x.get("material_stueck")) * offen
        m_neu = m_alt * faktor
        selbst = _n(x.get("selbst_stueck")) * offen
        erloes = preis * (1 - skonto) * offen
        anteil = _n(b.get("anteil")) / 100 if _n(b.get("anteil")) else (
            _n(x.get("material_stueck")) / (preis * (1 - skonto)) if preis else 0.0)
        p1 = preis * (1 + anteil * (faktor - 1))
        vorschlag[k] = round(p1, 2)
        zeilen.append(dict(pos=k, offen=offen, preis=preis, material_alt=m_alt, material_neu=m_neu,
                           differenz=m_neu - m_alt, selbst_alt=selbst, selbst_neu=selbst + m_neu - m_alt,
                           gewinn_alt=erloes - selbst, gewinn_neu=erloes - selbst - (m_neu - m_alt),
                           anteil=anteil, preis_neu=round(p1, 2)))
        s["material_alt"] += m_alt
        s["material_neu"] += m_neu
        s["selbst_alt"] += selbst
        s["erloes"] += erloes
    s["differenz"] = s["material_neu"] - s["material_alt"]
    s["selbst_neu"] = s["selbst_alt"] + s["differenz"]
    s["gewinn_alt"] = s["erloes"] - s["selbst_alt"]
    s["gewinn_neu"] = s["erloes"] - s["selbst_neu"]
    s["marge_alt"] = s["gewinn_alt"] / s["erloes"] if s["erloes"] else None
    s["marge_neu"] = s["gewinn_neu"] / s["erloes"] if s["erloes"] else None
    preis_aenderung = (sum(z["preis_neu"] * z["offen"] for z in zeilen) / sum(z["preis"] * z["offen"] for z in zeilen)
                       - 1) if any(z["preis"] * z["offen"] for z in zeilen) else 0.0
    gleit = (b.get("modell") or FEST_LAUFZEIT) in (GLEITKLAUSEL, INDIVIDUELL, PRUEFTERMINE) or not fest
    s.update(zeilen=zeilen, gebunden=fest, text=text, faktor=faktor, preis_aenderung=preis_aenderung,
             faellig=bool(gleit and abs(preis_aenderung) >= schwelle - 1e-12 and abs(faktor - 1) > 1e-12),
             vorschlag=vorschlag, schwelle=schwelle)
    return s


# ------------------------------------------------------------------ Warnungen, Ampel, Abschluss
GRUEN, GELB, ROT = "grün", "gelb", "rot"
_STUFE = {GRUEN: 0, GELB: 1, ROT: 2}


def warnungen(r, heute=None, marge_min=0.0, einst=None):
    """Warnungen eines Rahmenauftrags (Sicht aus rahmenauftrag.sicht): [(Ampel, Text)]."""
    from . import rahmenauftrag as ra
    heute = datum(heute) or datetime.date.today()
    k = ra.kennzahlen(r, heute.isoformat())
    out = []
    if r.get("status") not in (ra.AKTIV, ra.ANGEBOTEN, ra.ENTWURF):
        return out
    ende, start = datum(r.get("ende")), datum(r.get("start"))
    if ende and k["offen"] > 0:
        tage = (ende - heute).days
        if tage < 0:
            out.append((ROT, f"Vertrag seit {-tage} Tagen abgelaufen, {k['offen']:g} Stück offen"))
        elif tage <= 30:
            out.append((ROT, f"Vertrag endet in {tage} Tagen, {k['offen']:g} Stück offen"))
        elif tage <= 90:
            out.append((GELB, f"Vertrag endet in {tage} Tagen"))
    for a in k["ueberfaellig"]:
        tage = (heute - datum(a["datum"])).days
        out.append((ROT if tage > 14 else GELB, f"Abruf {a['nr']} seit {tage} Tagen überfällig"))
    if start and ende and ende > start and r.get("status") == ra.AKTIV and k["menge"] > 0:
        anteil = (heute - start).days / (ende - start).days
        if 0.25 < anteil <= 1 and k["abgerufen"] < 0.7 * anteil * k["menge"]:
            out.append((GELB, f"Abrufe unter Plan: {k['abgerufen']:g} von erwartet {anteil * k['menge']:.0f} Stück"))
    if k["ueber"]:
        out.append((ROT, f"Rahmenmenge überschritten: {', '.join(k['ueber'])}"))
    mn, mx = _n(r.get("min_abruf")), _n(r.get("max_abruf"))
    for a in k["abrufe"]:
        q = a["menge"]
        if a.get("status") != ra.STORNIERT and q and ((mn and q < mn) or (mx and q > mx)):
            out.append((GELB, f"Abruf {a['nr']}: {q:g} Stück außerhalb {mn:g}–{mx:g}"))
    mat = k["material"]
    naechster = next((a for a in k["abrufe"] if a.get("status") in (ra.GEPLANT, ra.ABGERUFEN)
                      and datum(a["datum"]) and datum(a["datum"]) >= heute - datetime.timedelta(days=60)), None)
    if mat["gekauft_kg"] > 0 and naechster and mat["bestand_kg"] < naechster.get("kg", 0) - 1e-9:
        tage = (datum(naechster["datum"]) - heute).days
        if tage <= 14:
            out.append((ROT if tage <= 7 else GELB,
                        f"Material reicht nicht für Abruf {naechster['nr']} ({mat['bestand_kg']:.0f} von "
                        f"{naechster['kg']:.0f} kg)"))
    vm = vertragsmarge(r)
    if marge_min and vm is not None and vm < marge_min - 1e-9:
        out.append((ROT, f"Marge zu Vertragspreisen {100 * vm:.1f} % unter Mindestmarge {100 * marge_min:.1f} %"))
    rest_unw = r.get("rest_unwirtschaftlich") or (r.get("version") or {}).get("rest_unwirtschaftlich")
    if rest_unw:
        out.append((GELB, rest_unw))
    for t in (r.get("preisbindung") or {}).get("pruef_termine") or ():
        d = datum(t)
        if d and heute <= d <= heute + datetime.timedelta(days=14):
            out.append((GELB, f"Preisüberprüfung am {d.strftime('%d.%m.%Y')}"))
    if r.get("vorschlaege_offen"):
        out.append((GELB, "Preisänderung wartet auf Freigabe"))
    if r.get("konflikte"):
        out.append((GELB, f"{len(r['konflikte'])} gleichzeitige Änderung(en) an mehreren Plätzen, bitte prüfen"))
    return out


def vertragsmarge(r):
    """Marge zu den vereinbarten Stückpreisen mit den Selbstkosten der festgeschriebenen Version (ohne Fracht und
    Skonto): (Erlös − Selbstkosten) ÷ Erlös; None ohne Version oder ohne Preise."""
    v = r.get("version") or {}
    jp, erg = v.get("je_position") or {}, v.get("ergebnis") or {}
    if not jp or not erg:
        return None
    sk = _n((v.get("modell") or {}).get("skonto"))
    erloes = selbst = 0.0
    for p in r.get("positionen") or ():
        x = jp.get(str(p.get("pos")))
        if not x or not _n(p.get("preis")):
            return None
        erloes += _n(p["preis"]) * (1 - sk) * x["menge"]
        selbst += x["selbst_stueck"] * x["menge"]
    erloes -= _n(erg.get("fracht"))
    return (erloes - selbst) / erloes if erloes > 0 else None


def ampel(warn):
    return max((w[0] for w in warn), key=lambda a: _STUFE[a], default=GRUEN)


def restmenge_unwirtschaftlich(r, modell, par):
    """Text, wenn die offene Restmenge in einem eigenen Los teurer würde als der Vertragspreis; sonst ''."""
    from . import rahmenauftrag as ra
    if not modell:
        return ""
    k = ra.kennzahlen(r)
    sk = modell.get("skonto") or 0.0
    teuer = []
    for p in k["positionen"]:
        rest = p["offen"] - p["bestand"]
        x = modell["pos"].get(str(p["pos"]))
        if rest <= 0 or not x or not _n(p.get("preis")):
            continue
        kosten = (x["F"] + x["P"] * par["prog_wiederholung"] / 100) / rest + x["vf"] + x["m"]
        if kosten > _n(p["preis"]) * (1 - sk):
            teuer.append(f"Pos. {p['pos']}: Rest {rest:g} Stk. kostet {kosten:.2f} €/Stk. > Preis {_n(p['preis']):.2f} €")
    return ("Restmenge unwirtschaftlich: " + "; ".join(teuer)) if teuer else ""


def abschluss(r, heute=None):
    """Abschlussübersicht zum Vertragsende: je Position Menge, abgerufen, geliefert, nicht abgerufen, gefertigt,
    Fertigteilbestand, offene Lieferverpflichtung, Umsatz, Restwert; dazu Material und Abrufe Plan/Ist."""
    from . import rahmenauftrag as ra
    heute = datum(heute) or datetime.date.today()
    k = ra.kennzahlen(r, heute.isoformat())
    zeilen = [dict(pos=p["pos"], bezeichnung=p.get("bezeichnung") or "", menge=p["menge"], abgerufen=p["abgerufen"],
                   geliefert=p["geliefert"], nicht_abgerufen=max(p["menge"] - p["abgerufen"], 0.0),
                   gefertigt=p["gefertigt"], bestand=p["bestand"],
                   verpflichtung=max(p["abgerufen"] - p["geliefert"], 0.0),
                   umsatz=p["geliefert"] * _n(p.get("preis")), restwert=p["offen"] * _n(p.get("preis")))
              for p in k["positionen"]]
    hinweise = []
    for z in zeilen:
        if z["verpflichtung"] > 0:
            hinweise.append(f"Pos. {z['pos']}: {z['verpflichtung']:g} Stück abgerufen, aber nicht geliefert")
        if z["bestand"] > 0:
            hinweise.append(f"Pos. {z['pos']}: {z['bestand']:g} Stück gefertigt auf Lager (mit Kunde klären: Abnahme "
                            "oder Berechnung)")
        if z["nicht_abgerufen"] > 0:
            hinweise.append(f"Pos. {z['pos']}: {z['nicht_abgerufen']:g} Stück nicht abgerufen")
    if k["material"]["bestand_kg"] > 0 or k["material"]["bestand_eur"] > 0:
        hinweise.append(f"Material des Rahmens übrig: {k['material']['bestand_kg']:.1f} kg "
                        f"({k['material']['bestand_eur']:.2f} €), nur melden (kein Restelager)")
    return dict(nummer=r.get("nummer"), kunde=r.get("kunde"), stichtag=heute.isoformat(), zeilen=zeilen,
                material=k["material"], abrufe_plan=k["abrufe_plan"], abrufe_ist=k["abrufe_ist"],
                storniert=k["storniert"], umsatz=sum(z["umsatz"] for z in zeilen),
                restwert=sum(z["restwert"] for z in zeilen), hinweise=hinweise)


# ------------------------------------------------------------------ Gegenprüfung und Gesamtrechnung
def gegenpruefung(kopf, positionen, ergebnis, k, tabellen, einst, modell):
    """Jedes Los des Ergebnisses einmal exakt mit der zentralen Rechnung (seine echten Mengen, eigener Schnittplan)
    gegen das lineare Modell: [dict(los, stueck, modell, exakt, abweichung %)]; Fehlertext (str) bei Fehler."""
    out = []
    for los in ergebnis["je_los"]:
        mengen = {p: q for p, q in los["mengen"].items() if q > 0}
        lauf = preislauf(kopf, positionen, mengen, k, tabellen, einst)
        if isinstance(lauf, str):
            return lauf
        exakt = sum(_n(x.get("selbst")) - _n(x.get("programmierung")) - _n(x.get("m_gesamt")) for x in lauf.values())
        mod = los["ruesten"] + los["fertigung"]
        mat_ex = sum(_n(x.get("m_gesamt")) for x in lauf.values())
        mat_mod = sum(modell["pos"][p]["m"] * q for p, q in mengen.items() if p in modell["pos"])
        out.append(dict(los=los["nr"], stueck=los["stueck"], modell=mod, exakt=exakt,
                        abweichung=100 * (mod - exakt) / exakt if exakt else 0.0, material_modell=mat_mod,
                        material_exakt=mat_ex,
                        material_abweichung=100 * (mat_mod - mat_ex) / mat_ex if mat_ex else 0.0))
    return out


def berechnen(r, modell, einst=None, heute=None, mengen=STAFFEL_MENGEN):
    """Gesamtrechnung eines Rahmens (Sicht r) mit einem Kostenmodell: Varianten A/B/C für die gewählte Materialart,
    Materialvergleich, Preisstaffel, Selbstkosten je Position und Restplan (offene Abrufe, schon Gefertigtes und
    gekauftes Material abgezogen). Ergebnis dict (JSON-fähig, für die festgeschriebene Version)."""
    from . import rahmenauftrag as ra
    par = parameter(einst, r.get("parameter"))
    marge_min = mindestmarge_satz(einst)
    art = (r.get("parameter") or {}).get("material") or JE_LOS
    abr = abrufe_ordnen(r.get("abrufe") or ())
    if not abr:
        return dict(fehler="Keine Abrufe mit Menge und Datum: bitte zuerst den Abrufplan anlegen.")
    start = r.get("start") or abr[0]["datum"]
    v = varianten(abr, modell, par, art, start, marge_min)
    mv = materialvergleich(abr, modell, par, start, marge_min, beistellung=True)
    beste = v[v["empfehlung"]]
    k = ra.kennzahlen(r)
    rest_abr = abrufe_ordnen(ra.offene_abrufe_fuer_plan(r))
    rest = None
    if rest_abr and (k["geliefert"] or k["gefertigt"] or k["material"]["gekauft_kg"]):
        par_r = dict(par, bestand_kg=k["material"]["bestand_kg"], bestand_eur=k["material"]["bestand_eur"],
                     einmalig=0.0, verwaltung=0.0)
        mod_r = dict(modell, pos={p: dict(x, P=0.0) for p, x in modell["pos"].items()}) if k["gefertigt"] else modell
        rest = varianten(rest_abr, mod_r, par_r, art, heute or datetime.date.today().isoformat(), marge_min)
    return dict(parameter=par, marge_min=marge_min, material_art=art, varianten=v, materialvergleich=mv,
                preisstaffel=preisstaffel(abr, modell, par, mengen, start, marge_min), empfehlung=v["empfehlung"],
                ergebnis=beste, je_position=je_position(beste, modell, abr), restplan=rest, modell=modell,
                rest_unwirtschaftlich=restmenge_unwirtschaftlich(r, modell, par))


# ------------------------------------------------------------------ Abruf-Angebot im Angebotsfenster (20.11.2026)
def abrufplan_aus_angebot(kopf, positionen, start=None):
    """Abrufplan eines Abruf-/Rahmenangebots (abruf.py) für die Rahmenrechnung: Abrufe = kleinste Jahresmenge ÷
    kleinster Abruf (aufgerundet), gleichmäßig über die Laufzeit; je Abruf die Stückzahl jeder Position (Stückzahl
    im Angebot = kleinster Abruf, wie im Abruf-Angebot). Ergebnis (abrufe, rahmen_pos, daten) oder (None, None,
    Fehlertext)."""
    from . import abruf
    ab = abruf.daten(kopf)
    if not ab:
        return None, None, "Jahresmenge und Abrufmenge fehlen."
    pos = [p for p in positionen or () if p.get("muster") != "ja" and p.get("pos") is not None
           and _n(p.get("stueck")) > 0]
    if not pos:
        return None, None, "Keine Position mit Stückzahl."
    n = max(int(math.ceil(ab["jahr_von"] / ab["von"] - 1e-9)), 1)
    t0 = datum(start) or datetime.date.today()
    schritt = ab["laufzeit"] / n

    def termin(i):                  # ganze Monate auf den Kalendertag, sonst Tage (30,4375 je Monat)
        if abs(schritt - round(schritt)) < 1e-9:
            m = t0.month - 1 + int(round(i * schritt))
            j, m = t0.year + m // 12, m % 12 + 1
            return datetime.date(j, m, min(t0.day, calendar.monthrange(j, m)[1]))
        return t0 + datetime.timedelta(days=round(i * schritt * 30.4375))
    abr = [dict(nr=i + 1, datum=termin(i).isoformat(),
                mengen={str(p["pos"]): _n(p["stueck"]) for p in pos}) for i in range(n)]
    rahmen_pos = [dict(pos=str(p["pos"]), menge=_n(p["stueck"]) * n) for p in pos]
    return abr, rahmen_pos, ab


def angebot_auswertung(kopf, positionen, k, tabellen, einst, start=None):
    """Wirtschaftlichkeit eines Abruf-Angebots mit derselben Rechnung wie der Rahmenauftrag: Varianten A/B/C
    (Lager, Kapital, Kommissionierung), Materialvergleich, Preisstaffel für die kleinste und größte Jahresmenge,
    empfohlene Losgröße. Ändert am Angebot nichts. Ergebnis dict oder dict(fehler=Text)."""
    abr, rpos, ab = abrufplan_aus_angebot(kopf, positionen, start)
    if abr is None:
        return dict(fehler=ab)
    modell, info = kostenmodell_aus_angebot(kopf, positionen, rpos, abr, k, tabellen, einst)
    if modell is None:
        return dict(fehler=info)
    par = parameter(einst)
    if ab["bevorraten"] and ab["zins"] > 0:
        par["zins"] = 100 * ab["zins"]
    marge_min = mindestmarge_satz(einst)
    art = GESAMT if ab["bevorraten"] else JE_LOS
    t0 = abr[0]["datum"]
    v = varianten(abr, modell, par, art, t0, marge_min)
    mv = materialvergleich(abr, modell, par, t0, marge_min)
    je_abruf = sum(_n(x) for x in abr[0]["mengen"].values())
    mengen = sorted({int(round(je_abruf * max(ab["jahr_von"] / ab["von"], 1))),
                     int(round(je_abruf * max(ab["jahr_bis"] / ab["von"], 1)))})
    beste = v[v["empfehlung"]]
    return dict(abrufe=len(abr), je_abruf=je_abruf, material_art=art, varianten=v, materialvergleich=mv,
                preisstaffel=preisstaffel(abr, modell, par, mengen, t0, marge_min), empfehlung=v["empfehlung"],
                ergebnis=beste, losgroesse=beste["menge"] / max(beste["lose"], 1), marge_min=marge_min,
                je_position=je_position(beste, modell, abr))


def _de(x, nk=2):
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def angebot_text(a):
    """Kurztext der Auswertung für Fenster und Meldungen."""
    if not a or a.get("fehler"):
        return (a or {}).get("fehler") or ""
    v, e = a["varianten"], a["empfehlung"]
    b = v[e]
    t = (f"{a['abrufe']} Abrufe à {_de(a['je_abruf'], 0)} Stk. Empfehlung: Variante {e} – {VARIANTE_TEXT[e]}, "
         f"{b['lose']} Los(e) zu ca. {_de(a['losgroesse'], 0)} Stk., Preis {_de(b['preis_stueck'], 3)} €/Stk.")
    ein = v[A]["selbst"] - b["selbst"]
    if ein > 0.005:
        t += f" Gegenüber Fertigung je Abruf {_de(ein)} € günstiger."
    mv = a.get("materialvergleich")
    if mv:
        t += f" Material: {mv['empfehlung']} ist {_de(mv['ersparnis'])} € günstiger."
    return t
