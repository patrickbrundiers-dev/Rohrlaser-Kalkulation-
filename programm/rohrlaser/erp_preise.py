"""Materialpreise aus einer Einkaufs-CSV des ERP (Plan „Materialpreise aus ERP-CSV“, Patrick 30.10.2026, Freigabe
„Alle Empfehlungen“ = 1a 2a 3a 4a 5a 6a 7a 8a 9b 10a 11a).

Die CSV enthält je Kauf Kaufdatum, Menge [m], Meterpreis [€/m], Artikelnummer und die EK-Bezeichnung („Rohr
40x40x3 S235JRH feuerverzinkt“). Ablauf:
1. lesen() + spalten_vorschlag(): Spalten am Kopf erkennen, sonst Zuordnung von Hand (gespeichert als Vorlage je
   Spaltenkopf, Einstellung erp_vorlagen); kaeufe() prüft Datum und Zahlen je Zeile.
2. zerlegen(): Profil, Werkstoff und Oberfläche aus der Bezeichnung; Ampel grün (eindeutig), gelb (Werkstoff
   mehrdeutig/fehlt, Oberfläche unbekannt), rot (Profil fehlt oder nicht erkannt). Bestätigte Zuordnungen stehen je
   ERP-Artikel in erp_zuordnung (7a), auch „überspringen“.
3. auswerten(): je Profil + Werkstoff + Oberfläche gewichteter Durchschnitt nach Menge über die letzten
   erp_monate Monate (1a, 2a), Ausreißer über ±erp_ausreisser vom Median zählen nicht (3a, je Kauf änderbar), dazu
   letzter Preis, Min/Max und der heutige Preis aus den Stammdaten.
4. uebernehmen(): Preis-Zeile mit Basis €/m (4a) nach Sicherung; nur Rohware (5a), Käufe mit Oberfläche ergeben
   einen Aufpreis-Vorschlag €/kg (aufpreise, nur Anzeige).

Die Käufe stehen nur in der eigenen Datendatei (erp_kaeufe) und werden nicht mit den Kollegen abgeglichen (6a);
übernommene Preise sind normale Stammdaten und gehen wie jede Preisänderung an alle Plätze. Ohne Qt."""
import csv
import datetime
import io
import re
from statistics import median

from . import kunden_csv

FELDER = (("datum", "Kaufdatum"), ("menge", "Menge [m]"), ("preis", "Meterpreis [€/m]"),
          ("artikelnr", "Artikelnummer"), ("bezeichnung", "EK-Artikel (Bezeichnung)"))
FELD_TITEL = dict(FELDER)
PFLICHT = ("datum", "menge", "preis", "bezeichnung")      # Artikelnummer darf fehlen (dann zählt die Bezeichnung)
VORLAGEN = "erp_vorlagen"       # Einstellung (intern): {Spaltenkopf mit | getrennt: {Feld: Spaltennummer}}
LIEFERANT = "ERP"
GRUEN, GELB, ROT = "grün", "gelb", "rot"

# Spaltenköpfe je Feld, normalisiert (klein, nur Buchstaben/Ziffern): erst gleich, dann enthalten
_KOPF = {"datum": ("kaufdatum", "datum", "belegdatum", "bestelldatum", "lieferdatum", "eingangsdatum",
                   "rechnungsdatum", "wareneingang", "buchungsdatum"),
         "preis": ("meterpreis", "preisjem", "preism", "eurom", "ekpreis", "einkaufspreis", "einzelpreis", "preis"),
         "artikelnr": ("artikelnummer", "artikelnr", "artnr", "materialnummer", "materialnr", "matnr", "nummer"),
         "menge": ("mengeinmeter", "mengem", "menge", "meter", "laenge", "länge"),
         "bezeichnung": ("ekartikel", "artikelbezeichnung", "bezeichnung", "artikeltext", "beschreibung", "text",
                         "artikel", "material")}
_REIHE = ("preis", "artikelnr", "datum", "menge", "bezeichnung")    # „Meterpreis“ enthält „meter“: Preis zuerst


class ErpFehler(ValueError):
    """Datei nicht lesbar (Text für den Benutzer)."""


def _norm(t):
    return re.sub(r"[^0-9a-zäöüß]+", "", str(t or "").lower())


# ------------------------------------------------------------------ 1. Datei lesen
def lesen(roh):
    """CSV (Bytes oder Text) -> dict(kopf, zeilen [Zellen], erste = Dateizeile der ersten Datenzeile).
    Kodierung und Trennzeichen wie beim Kunden-Import; die Kopfzeile ist die erste Zeile mit mindestens drei
    Textzellen (eine Titelzeile davor wird übersprungen)."""
    text = kunden_csv._text(roh)
    zeilen = text.splitlines()
    if not any(z.strip() for z in zeilen):
        raise ErpFehler("Die Datei ist leer.")
    trenner, sep_zeile = kunden_csv._trenner(zeilen)
    if sep_zeile:
        zeilen = zeilen[1:]
    alle = [[kunden_csv._excel_wert(c).strip() for c in z] for z in csv.reader(io.StringIO("\n".join(zeilen)),
                                                                               delimiter=trenner)]
    for i, z in enumerate(alle[:15]):
        texte = [c for c in z if c and zahl(c) is None and datum(c) is None]
        if len(texte) >= 3:
            daten = [r for r in alle[i + 1:] if any(c for c in r)]
            return dict(kopf=z, zeilen=daten, erste=i + 2 + (1 if sep_zeile else 0))
    raise ErpFehler("Keine Kopfzeile gefunden: die Datei braucht eine Zeile mit den Spaltennamen (z. B. Kaufdatum; "
                    "Menge; Meterpreis; Artikelnummer; EK-Artikel).")


def spalten_vorschlag(kopf):
    """{Feld: Spaltennummer} aus den Spaltenköpfen; nicht erkannte Felder fehlen."""
    namen = [_norm(k) for k in kopf]
    frei, out = set(range(len(kopf))), {}
    for gleich in (True, False):
        for feld in _REIHE:
            if feld in out:
                continue
            for wort in _KOPF[feld]:
                treffer = [i for i in sorted(frei) if (namen[i] == wort if gleich else wort in namen[i])]
                if treffer:
                    out[feld] = treffer[0]
                    frei.discard(treffer[0])
                    break
    return out


def vorlage_schluessel(kopf):
    return "|".join(_norm(k) for k in kopf)


def zuordnung_fuer(kopf, vorlagen):
    """Gespeicherte Zuordnung für genau diesen Spaltenkopf, sonst der Vorschlag. Ergebnis (zuordnung, gespeichert)."""
    v = (vorlagen or {}).get(vorlage_schluessel(kopf))
    if v and all(isinstance(i, int) and 0 <= i < len(kopf) for i in v.values()):
        return dict(v), True
    return spalten_vorschlag(kopf), False


def fehlende(zuordnung):
    return [f for f in PFLICHT if f not in zuordnung]


def zahl(t):
    """Zahl aus Text: 1.234,56 / 1,234.56 / 12,5 / 12.5 / „3,45 €“ / „120 m“; None, wenn keine Zahl."""
    s = str(t or "").replace(" ", " ").strip()
    s = re.sub(r"(?i)\s*(€|eur|euro|€/m|m|lfm|lfdm)\.?$", "", s).replace("€", "").replace(" ", "")
    if not re.fullmatch(r"[-+]?[\d.,]*\d[\d.,]*", s or "x"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1 or re.fullmatch(r"[-+]?\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")              # 1.250 = 1250 (deutsche Tausenderpunkte)
    try:
        return float(s)
    except ValueError:
        return None


def datum(t):
    """Datum aus TT.MM.JJJJ, TT.MM.JJ, JJJJ-MM-TT, TT/MM/JJJJ (auch mit Uhrzeit) oder Excel-Tageszahl; sonst None."""
    s = str(t or "").strip().split(" ")[0].split("T")[0]
    for f in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y.%m.%d", "%Y%m%d"):
        try:
            d = datetime.datetime.strptime(s, f).date()
            if 1990 <= d.year <= 2100:
                return d
        except ValueError:
            pass
    if re.fullmatch(r"\d{5}", s) and 30000 <= int(s) <= 60000:          # Excel: Tage seit 30.12.1899
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(s))
    return None


def schluessel(artikelnr, bezeichnung):
    """Kennung eines ERP-Artikels: Artikelnummer, ohne sie die Bezeichnung."""
    a = str(artikelnr or "").strip()
    return a if a else "#" + " ".join(str(bezeichnung or "").split()).lower()


def kaeufe(daten, zuordnung):
    """Käufe aus lesen() mit der Spaltenzuordnung: (Liste dict(zeile, datum, menge, preis, artikelnr, bezeichnung,
    schluessel), Meldungen). Zeilen mit Fehler (Datum, Menge, Preis nicht lesbar, Menge/Preis ≤ 0, z. B. Gutschrift)
    werden übersprungen und gemeldet; leere Zeilen und Summenzeilen ohne Datum still."""
    out, meldungen = [], []
    for n, z in enumerate(daten["zeilen"], daten.get("erste", 2)):
        def zelle(feld):
            i = zuordnung.get(feld)
            return z[i].strip() if i is not None and i < len(z) else ""
        bez, d_text = zelle("bezeichnung"), zelle("datum")
        if not bez and not d_text:
            continue
        if not d_text and re.match(r"(?i)\s*(summe|gesamt|total)", " ".join(z)):
            continue
        d, m, p = datum(d_text), zahl(zelle("menge")), zahl(zelle("preis"))
        fehler = [f"{FELD_TITEL[f]} „{t}“ nicht lesbar" for f, w, t in
                  (("datum", d, d_text), ("menge", m, zelle("menge")), ("preis", p, zelle("preis"))) if w is None]
        if not bez:
            fehler.append("EK-Artikel leer")
        if not fehler and (m <= 0 or p <= 0):
            fehler.append("Menge oder Preis nicht größer 0 (Gutschrift/Storno?)")
        if fehler:
            meldungen.append(f"Zeile {n}: " + ", ".join(fehler) + " – übersprungen")
            continue
        art = zelle("artikelnr")
        out.append(dict(zeile=n, datum=d, menge=m, preis=p, artikelnr=art, bezeichnung=" ".join(bez.split()),
                        schluessel=schluessel(art, bez)))
    return out, meldungen


# ------------------------------------------------------------------ 2. Bezeichnung zerlegen
_Z = r"\d+(?:[.,]\d+)?"
_MASSE = re.compile(rf"(?<![\d.,])({_Z})\s*(?:mm)?\s*[x×*X]\s*({_Z})(?:\s*(?:mm)?\s*[x×*X]\s*({_Z}))?(?![\d])")
_FORM = (("Rundrohr", r"rund|ø|⌀|\brr\b|\bro\b|siederohr|präzisionsrohr|praezisionsrohr|gewinderohr|\bd\s*=?\s*\d"),
         ("Quadratrohr", r"quadrat|vierkantrohr|vierkant-rohr|\bqr\b|\bvk\b|\bqhp\b|\bmshq\b"),
         ("Rechteckrohr", r"rechteck|\bre\b|\brk\b|\brhp\b|\bmshr\b"),
         ("Flachstahl", r"flach|\bfl\b"),
         ("L-Profil", r"winkel|l-profil|\bl\s*\d"),
         ("U-Profil", r"u-profil|\bu\s*\d"))
_OBER_WORT = re.compile(r"(?i)(?<![\w])(feuerverzinkt|sendzimirverzinkt|galvanisch verzinkt|verzinkt|fvz|gebeizt|"
                        r"geschliffen|gestrahlt|kugelgestrahlt|lackiert|pulverbeschichtet|grundiert|eloxiert|"
                        r"E6/EV1|K\d{3}|geölt|poliert)(?![\w])")
_NORM = re.compile(r"(?<!\d)(102\d\d|103\d\d|10305|10296|10217)(?!\d)")       # EN 10219, 10210, 10305 …


def _f(x):
    return float(str(x).replace(",", "."))


def masse(text):
    """Profilform und Maße aus der Bezeichnung: dict(form, a, b, wand) oder None."""
    t = str(text or "")
    m = _MASSE.search(t)
    if not m:
        return None
    z = [_f(x) for x in m.groups() if x]
    klein = t.lower()
    form = next((f for f, muster in _FORM if re.search(muster, klein)), None)
    if form is None:
        form = "Rundrohr" if len(z) == 2 else ("Quadratrohr" if z[0] == z[1] else "Rechteckrohr")
    if form in ("Rundrohr", "Flachstahl"):
        a, b, wand = z[0], None, z[1]
    elif form == "Quadratrohr":
        if len(z) == 3 and z[0] != z[1]:
            form, a, b, wand = "Rechteckrohr", z[0], z[1], z[2]
        else:
            a, b, wand = z[0], None, z[-1]
    elif form == "L-Profil":
        a, b, wand = (z[0], z[0], z[1]) if len(z) == 2 else (z[0], z[1], z[2])
    elif len(z) == 3:
        a, b, wand = z
    else:
        return None
    if a <= 0 or wand <= 0:
        return None
    return dict(form=form, a=a, b=b, wand=wand)


def _gleich(x, y, tol=0.051):
    return x is not None and y is not None and abs(float(x) - float(y)) <= tol


def profil_finden(text, profile):
    """Profil-ID aus den Stammdaten: zuerst eine Profil-ID, die wörtlich in der Bezeichnung steht (IPE 200, RP
    0106-35, QR 40x40x3), sonst gleiche Form und Maße (±0,05 mm, Rechteckrohr auch gedreht). Ergebnis (Profil-ID
    oder None, erkannte Maße oder None)."""
    flach = re.sub(r"\s+", "", str(text or "")).lower().replace(",", ".")
    beste = None
    for pid in profile:
        p = re.sub(r"\s+", "", str(pid)).lower().replace(",", ".")
        if len(p) < 3:
            continue
        for m in re.finditer(re.escape(p), flach):
            if not re.match(r"[\d.]", flach[m.end():m.end() + 1]) and (m.start() == 0 or not flach[m.start() - 1].isdigit()):
                if beste is None or len(p) > len(re.sub(r"\s+", "", beste)):
                    beste = pid
    mas = masse(text)
    if beste is not None:
        return beste, mas
    if mas is None:
        return None, None
    for pid, p in profile.items():
        if p.get("form") != mas["form"] or not _gleich(p.get("wand"), mas["wand"]):
            continue
        if mas["form"] in ("Rundrohr", "Flachstahl", "Quadratrohr"):
            if _gleich(p.get("a"), mas["a"]):
                return pid, mas
        elif (_gleich(p.get("a"), mas["a"]) and _gleich(p.get("b"), mas["b"])) or \
                (mas["form"] == "Rechteckrohr" and _gleich(p.get("a"), mas["b"]) and _gleich(p.get("b"), mas["a"])):
            return pid, mas
    return None, mas


def werkstoff_finden(text, werkstoffe):
    """(Werkstoff-ID oder None, Wort, Kandidaten): Erkennung wie beim Outlook-Import (mail.werkstoff); passen mehrere,
    entscheidet eine Norm-Nummer in der Bezeichnung (EN 10219 / 10210), sonst bleibt es offen."""
    from .mail import werkstoff
    zeilen = [dict(z, werkstoff_id=wid) for wid, z in werkstoffe.items()]
    wid, wort, kand = werkstoff(text, zeilen)
    if wid is None and len(kand) > 1:
        normen = set(_NORM.findall(str(text or "")))
        if normen:
            passt = [w for w in kand if any(n in " ".join(str(werkstoffe.get(w, {}).get(f) or "") for f in
                                                          ("norm", "angebotstext", "werkstoff_id")) for n in normen)]
            if len(passt) == 1:
                return passt[0], wort, kand
    return wid, wort, kand


def oberflaeche_finden(text, oberflaechen, werkstoff=None):
    """(Oberfläche, unbekannt): Name aus den Stammdaten (längster, der in der Bezeichnung steht), roh/blank/schwarz
    = '' (roh); ein Oberflächenwort ohne Stammdatenzeile (z. B. verzinkt) kommt mit unbekannt=True zurück. Steht das
    Wort im Werkstoff selbst (DX51D+Z275 sendzimirverzinkt), ist es keine Oberfläche."""
    klein = str(text or "").lower()
    namen = sorted((n for n in oberflaechen if n and n.lower() != "roh"), key=len, reverse=True)
    for n in namen:
        if re.search(r"(?<![a-z0-9])" + re.escape(n.lower()) + r"(?![a-z0-9])", klein) or \
                (len(n) >= 6 and n.lower() in klein):
            return n, False
    m = _OBER_WORT.search(text or "")
    if m:
        w = (werkstoff or {})
        im_werkstoff = " ".join(str(w.get(f) or "") for f in ("werkstoff", "norm", "angebotstext")).lower()
        if m.group(1).lower() not in im_werkstoff:
            return m.group(1), True
    return "", False


def zerlegen(text, k):
    """Bezeichnung -> dict(profil_id, vorschlag (neues Profil: form, a, b, wand, profil_id), werkstoff_id,
    kandidaten, werkstoff_wort, oberflaeche, ober_unbekannt, ampel, hinweis)."""
    pid, mas = profil_finden(text, k.profile)
    wid, wort, kand = werkstoff_finden(text, k.werkstoffe)
    ober, unbekannt = oberflaeche_finden(text, k.oberflaechen, k.werkstoffe.get(wid))
    vorschlag = None
    if pid is None and mas is not None:
        from .profil_neu import profil_id
        vorschlag = dict(mas, profil_id=profil_id(mas["form"], mas["a"], mas["b"], mas["wand"]))
    hinweis = []
    if pid is None:
        hinweis.append(f"Profil {vorschlag['profil_id']} fehlt in den Stammdaten" if vorschlag else
                       "Abmessung nicht erkannt")
    if wid is None:
        hinweis.append(f"Werkstoff „{wort}“ mehrdeutig: {', '.join(kand)}" if len(kand) > 1 else
                       "Werkstoff nicht erkannt")
    if unbekannt:
        hinweis.append(f"Oberfläche „{ober}“ fehlt in den Stammdaten")
    ampel = ROT if pid is None else (GELB if wid is None or unbekannt else GRUEN)
    return dict(profil_id=pid, vorschlag=vorschlag, werkstoff_id=wid, kandidaten=kand, werkstoff_wort=wort,
                oberflaeche=ober, ober_unbekannt=unbekannt, ampel=ampel, hinweis="; ".join(hinweis))


# ------------------------------------------------------------------ Speicher (nur diese Datendatei, 6a)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS erp_kaeufe (id INTEGER PRIMARY KEY, datum TEXT, schluessel TEXT, artikelnr TEXT, "
    "bezeichnung TEXT, menge REAL, preis REAL, datei TEXT, importiert TEXT, rechnen INTEGER, "
    "UNIQUE (datum, schluessel, menge, preis))",
    "CREATE TABLE IF NOT EXISTS erp_zuordnung (schluessel TEXT PRIMARY KEY, artikelnr TEXT, bezeichnung TEXT, "
    "profil_id TEXT, werkstoff_id TEXT, oberflaeche TEXT, ignorieren INTEGER, geaendert TEXT)",
)


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def speichern(db, liste, datei=""):
    """Käufe in erp_kaeufe; gleiche Käufe (Datum, Artikel, Menge, Preis) nur einmal. Ergebnis: Anzahl neu."""
    zaehlen = "SELECT COUNT(*) FROM erp_kaeufe"
    vorher = db.con.execute(zaehlen).fetchone()[0]
    with db.con:
        db.con.executemany(
            "INSERT OR IGNORE INTO erp_kaeufe (datum, schluessel, artikelnr, bezeichnung, menge, preis, datei, "
            "importiert) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(k["datum"].isoformat(), k["schluessel"], k["artikelnr"], k["bezeichnung"], k["menge"], k["preis"],
              datei, _jetzt()) for k in liste])
    return db.con.execute(zaehlen).fetchone()[0] - vorher


def gespeicherte(db):
    """Alle gespeicherten Käufe (dict mit datum als date), älteste zuerst."""
    out = []
    for r in db.con.execute("SELECT * FROM erp_kaeufe ORDER BY datum, id"):
        z = dict(r)
        z["datum"] = datetime.date.fromisoformat(z["datum"])
        out.append(z)
    return out


def kauf_rechnen(db, kauf_id, rechnen):
    """Ausreißer von Hand: rechnen True = immer mitrechnen, False = nie, None = automatisch (3a)."""
    with db.con:
        db.con.execute("UPDATE erp_kaeufe SET rechnen=? WHERE id=?",
                       (None if rechnen is None else int(bool(rechnen)), kauf_id))


def zuordnungen(db):
    return {r["schluessel"]: dict(r) for r in db.con.execute("SELECT * FROM erp_zuordnung")}


def zuordnung_merken(db, schl, artikelnr, bezeichnung, profil_id=None, werkstoff_id=None, oberflaeche="",
                     ignorieren=False):
    with db.con:
        db.con.execute("INSERT OR REPLACE INTO erp_zuordnung (schluessel, artikelnr, bezeichnung, profil_id, "
                       "werkstoff_id, oberflaeche, ignorieren, geaendert) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (schl, artikelnr, bezeichnung, profil_id, werkstoff_id, oberflaeche or "", int(ignorieren),
                        _jetzt()))


def zuordnung_vergessen(db, schluessel_liste):
    with db.con:
        db.con.executemany("DELETE FROM erp_zuordnung WHERE schluessel=?", [(s,) for s in schluessel_liste])


def artikel(kauf_liste, gemerkt, k):
    """Je ERP-Artikel (Schlüssel) eine Zeile der Prüfliste: dict(schluessel, artikelnr, bezeichnung, kaeufe, meter,
    profil_id, werkstoff_id, oberflaeche, ampel, hinweis, gemerkt, ignorieren, vorschlag, kandidaten). Gemerkte
    Zuordnungen gelten vor der Erkennung, solange Profil und Werkstoff noch in den Stammdaten stehen."""
    je = {}
    for kauf in kauf_liste:
        a = je.setdefault(kauf["schluessel"], dict(schluessel=kauf["schluessel"], artikelnr=kauf["artikelnr"],
                                                   bezeichnung=kauf["bezeichnung"], kaeufe=0, meter=0.0))
        a["kaeufe"] += 1
        a["meter"] += kauf["menge"]
        a["bezeichnung"] = kauf["bezeichnung"]          # neueste Schreibweise
    for a in je.values():
        z = gemerkt.get(a["schluessel"])
        if z and z.get("ignorieren"):
            a.update(profil_id=None, werkstoff_id=None, oberflaeche="", ampel=GRUEN, hinweis="übersprungen (gemerkt)",
                     gemerkt=True, ignorieren=True, vorschlag=None, kandidaten=[])
        elif z and z.get("profil_id") in k.profile and z.get("werkstoff_id") in k.werkstoffe:
            a.update(profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"], oberflaeche=z.get("oberflaeche") or "",
                     ampel=GRUEN, hinweis="gemerkt", gemerkt=True, ignorieren=False, vorschlag=None, kandidaten=[])
        else:
            e = zerlegen(a["bezeichnung"], k)
            a.update(profil_id=e["profil_id"], werkstoff_id=e["werkstoff_id"], oberflaeche=e["oberflaeche"],
                     ampel=e["ampel"], hinweis=e["hinweis"], gemerkt=False, ignorieren=False,
                     vorschlag=e["vorschlag"], kandidaten=e["kandidaten"])
    return sorted(je.values(), key=lambda a: ({ROT: 0, GELB: 1, GRUEN: 2}[a["ampel"]], a["bezeichnung"].lower()))


# ------------------------------------------------------------------ 3. Preis ermitteln
def heute_preis_m(profil_id, werkstoff_id, k, tabellen):
    """Heutiger Materialpreis €/m aus den Stammdaten (Preise, sonst Tonnenpreis) ohne Oberfläche und Teuerung:
    (Preis oder None, Herkunft-Text)."""
    from .rechnen import kg_je_m, preis_zeile
    kgm = kg_je_m(profil_id, werkstoff_id, k)
    z = preis_zeile(profil_id, werkstoff_id, k, tabellen)
    if z is not None and z.get("preis"):
        b, p = z.get("basis"), z["preis"]
        wert = p if b == "€/m" else (p * kgm if b == "€/kg" and kgm else
                                     (p * 1000 / z["lieferlaenge"] if b == "€/Stange" and z.get("lieferlaenge")
                                      else None))
        return wert, f"Preise {_t(p)} {b}" + (f", {z['lieferant']}" if z.get("lieferant") else "") + \
            (f", ab {_datum_text(z.get('gueltig_ab'))}" if z.get("gueltig_ab") else "")
    t = (k.werkstoffe.get(werkstoff_id) or {}).get("tonnenpreis")
    if t and kgm:
        return t / 1000 * kgm, f"Tonnenpreis {_t(t, 0)} €/t"
    return None, "kein Preis"


def _datum_text(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def _t(x, stellen=2):
    return f"{x:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def auswerten(kauf_liste, artikel_liste, k, tabellen, heute=None, monate=12, grenze=0.25, schwelle=0.02):
    """Je Profil + Werkstoff + Oberfläche eine Gruppe aus den Käufen der zugeordneten Artikel (grün, nicht
    übersprungen): dict(profil_id, werkstoff_id, oberflaeche, kaeufe [Kauf + ausreisser, im_zeitraum, gerechnet],
    anzahl, meter, durchschnitt (gewichtet, = Vorschlag), letzter, letzter_datum, min, max, von, bis, heute,
    herkunft, abweichung, kg_m, haken). Zeitraum = die letzten monate Monate vor heute; Ausreißer = mehr als grenze
    vom Median des Zeitraums (mit rechnen 1/0 je Kauf von Hand übersteuert); haken (10a) = Rohware mit Vorschlag und
    Abweichung über schwelle zum heutigen Preis."""
    from .rechnen import kg_je_m
    heute = heute or datetime.date.today()
    ab = _monate_zurueck(heute, monate)
    zu = {a["schluessel"]: a for a in artikel_liste if a["ampel"] == GRUEN and not a.get("ignorieren")
          and a.get("profil_id") and a.get("werkstoff_id")}
    gruppen = {}
    for kauf in kauf_liste:
        a = zu.get(kauf["schluessel"])
        if a is None:
            continue
        g = gruppen.setdefault((a["profil_id"], a["werkstoff_id"], a["oberflaeche"] or ""), [])
        g.append(kauf)
    out = []
    for (pid, wid, ober), liste in gruppen.items():
        liste = sorted(liste, key=lambda x: x["datum"])
        im = [x for x in liste if x["datum"] >= ab]
        med = median([x["preis"] for x in im]) if im else None
        kaeufe_g = []
        for x in liste:
            drin = x["datum"] >= ab
            ausreisser = bool(drin and med and abs(x["preis"] / med - 1) > grenze)
            hand = x.get("rechnen")
            gerechnet = drin and (bool(hand) if hand is not None else not ausreisser)
            kaeufe_g.append(dict(x, im_zeitraum=drin, ausreisser=ausreisser, gerechnet=gerechnet))
        rech = [x for x in kaeufe_g if x["gerechnet"]]
        meter = sum(x["menge"] for x in rech)
        schnitt = round(sum(x["menge"] * x["preis"] for x in rech) / meter, 2) if meter else None   # wie gespeichert
        hp, herkunft = heute_preis_m(pid, wid, k, tabellen)
        roh = not ober
        abw = schnitt / hp - 1 if schnitt and hp and roh else None      # mit Oberfläche: kein Vergleich mit Rohpreis
        out.append(dict(profil_id=pid, werkstoff_id=wid, oberflaeche=ober, kaeufe=kaeufe_g, anzahl=len(rech),
                        meter=meter, durchschnitt=schnitt,
                        letzter=liste[-1]["preis"], letzter_datum=liste[-1]["datum"],
                        min=min((x["preis"] for x in im), default=None), max=max((x["preis"] for x in im), default=None),
                        von=rech[0]["datum"] if rech else None, bis=rech[-1]["datum"] if rech else None,
                        ausreisser=sum(1 for x in kaeufe_g if x["ausreisser"]), heute=hp, herkunft=herkunft,
                        abweichung=abw, kg_m=kg_je_m(pid, wid, k),
                        haken=bool(roh and schnitt and (abw is None or abs(abw) > schwelle))))
    return sorted(out, key=lambda g: (g["oberflaeche"] != "", g["profil_id"].lower(), g["werkstoff_id"].lower(),
                                      g["oberflaeche"].lower()))


def _monate_zurueck(d, monate):
    j, m = divmod(d.year * 12 + d.month - 1 - int(monate), 12)
    tag = min(d.day, 28)
    return datetime.date(j, m + 1, tag)


def aufpreise(gruppen, k):
    """Aufpreis-Vorschlag je Oberfläche in €/kg (5a, nur Anzeige): je Profil + Werkstoff (Durchschnitt mit Oberfläche
    − Rohpreis) ÷ kg/m, gewichtet nach Metern. Rohpreis = Durchschnitt der Rohware aus der Datei, sonst der heutige
    Preis. Ergebnis [dict(oberflaeche, aufpreis_kg, profile, meter, heute (Text aus den Stammdaten oder ''))]."""
    roh = {(g["profil_id"], g["werkstoff_id"]): g for g in gruppen if not g["oberflaeche"]}
    je = {}
    for g in gruppen:
        if not g["oberflaeche"] or not g["durchschnitt"] or not g["kg_m"]:
            continue
        r = roh.get((g["profil_id"], g["werkstoff_id"]))
        basis = r["durchschnitt"] if r and r["durchschnitt"] else g["heute"]
        if not basis:
            continue
        e = je.setdefault(g["oberflaeche"], dict(summe=0.0, meter=0.0, profile=0))
        e["summe"] += (g["durchschnitt"] - basis) / g["kg_m"] * g["meter"]
        e["meter"] += g["meter"]
        e["profile"] += 1
    out = []
    for ober, e in sorted(je.items()):
        z = k.oberflaechen.get(ober) or {}
        heute = f"{_t(z['aufpreis_m'])} {z.get('aufpreis_basis') or '€/m'}" if z.get("aufpreis_m") is not None else ""
        out.append(dict(oberflaeche=ober, aufpreis_kg=e["summe"] / e["meter"] if e["meter"] else None,
                        profile=e["profile"], meter=e["meter"], heute=heute))
    return out


# ------------------------------------------------------------------ 4. Übernehmen
def bemerkung(g):
    zeit = f"{g['von'].strftime('%m/%Y')}–{g['bis'].strftime('%m/%Y')}" if g.get("von") else ""
    return f"ERP: Ø {g['anzahl']} Käufe, {_t(g['meter'], 0)} m, {zeit}".strip(", ")


def uebernehmen(db, gruppen, heute=None):
    """Durchschnitt der angehakten Gruppen (nur Rohware) als Preis-Zeile €/m (4a) schreiben, vorher geschützte
    Sicherung '_vor_ERP_Preisimport'. Vorhandene Zeile Profil + Werkstoff: Basis, Preis, Gültig ab, Lieferant und
    Bemerkung werden ersetzt (Liefer-Stangenlänge bleibt). Ergebnis (neu, geändert, Pfad der Sicherung)."""
    wahl = [g for g in gruppen if g.get("haken") and not g["oberflaeche"] and g.get("durchschnitt")]
    if not wahl:
        return 0, 0, None
    pfad = db.sicherung(zusatz="vor_ERP_Preisimport")
    ab = (heute or datetime.date.today()).isoformat()
    vorhanden = {(z.get("profil_id"), z.get("werkstoff_id")): z for z in db.zeilen("preise")}
    neu = geaendert = 0
    for g in wahl:
        werte = dict(basis="€/m", preis=g["durchschnitt"], gueltig_ab=ab, lieferant=LIEFERANT, bemerkung=bemerkung(g))
        z = vorhanden.get((g["profil_id"], g["werkstoff_id"]))
        if z is None:
            db.neu("preise", dict(werte, profil_id=g["profil_id"], werkstoff_id=g["werkstoff_id"]))
            neu += 1
        else:
            for feld, wert in werte.items():
                if z.get(feld) != wert:
                    db.aendern("preise", z["id"], feld, wert)
            geaendert += 1
    return neu, geaendert, pfad


# ------------------------------------------------------------------ Hinweis im Material-Fenster (9b)
def hinweise(db, k, tabellen, heute=None):
    """{(Profil, Werkstoff, Oberfläche): Gruppe aus auswerten()} aus den gespeicherten Käufen und Zuordnungen, für den
    Hinweis „ERP Ø …“ im Material-Fenster; leer ohne Käufe."""
    liste = gespeicherte(db)
    if not liste:
        return {}
    e = db.einstellungen()
    gruppen = auswerten(liste, artikel(liste, zuordnungen(db), k), k, tabellen, heute,
                        monate=e.get("erp_monate") or 12, grenze=e.get("erp_ausreisser") or 0.25,
                        schwelle=e.get("erp_schwelle") or 0.02)
    return {(g["profil_id"], g["werkstoff_id"], g["oberflaeche"]): g for g in gruppen if g["durchschnitt"]}


def hinweis_text(g):
    return (f"ERP Ø {_t(g['durchschnitt'])} €/m aus {g['anzahl']} Käufen ({_t(g['meter'], 0)} m, bis "
            f"{g['bis'].strftime('%d.%m.%Y')})" if g and g.get("durchschnitt") else "")
