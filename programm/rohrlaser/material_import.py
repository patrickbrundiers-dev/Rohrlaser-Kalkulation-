"""ERP-Stammdaten-Import für den Materialstamm (Master-Auftrag Materialdatenbank, Patrick 23.11.2026). Ohne Qt.

Neben dem Import der Einkäufe (erp_preise: Kaufdatum, Menge, Meterpreis) liest dieser Import eine Artikel- bzw.
Preisliste aus dem ERP: je Zeile ein Material mit Materialnummer, Bezeichnung, Werkstoff, Abmessung oder Maßen,
EK-Preis mit Einheit, Lieferant, Gewicht, Gültig ab. Ablauf:

1. lesen(): Kodierung (UTF-8, ANSI/cp1252, UTF-16), Trennzeichen (; , Tab |) und Kopfzeile wie der Kunden-Import,
   Dezimalkomma oder -punkt je Zelle (erp_preise.zahl). Excel (.xlsx) über materialplattform.xlsx_als_csv.
2. spalten_vorschlag(): Spalten nach Namen (auch abweichende Schreibweisen); Importprofile merken die Zuordnung je
   Spaltenkopf (Einstellung material_importprofile, nur dieser PC).
3. analysieren(): Vorschau ohne Änderung, jede Zeile in genau einer Gruppe: neu, aktualisiert, Preisänderung,
   unverändert, doppelt, fehlerhaft, nicht zuordenbar. Ein Werkstoff wird nie geraten (mehrdeutig = nicht
   zuordenbar); gemerkte EK-Zuordnungen je Artikelnummer gelten zuerst.
4. ausfuehren(): nur die bestätigten Gruppen, vorher Sicherung; jede Änderung wird mit altem Wert in
   material_import_posten festgehalten. Bricht etwas ab, wird alles Geänderte zurückgenommen.
5. rueckgaengig(): einen Importlauf vollständig zurücknehmen (neu angelegte Zeilen weg, alte Werte zurück).

Preise: €/m, €/kg, €/Stange (= €/Stück) bleiben, €/t wird €/kg (÷ 1.000), €/100 m wird €/m (÷ 100). Der Preis geht
in 'Preise' (aktiver Preis, Gültig ab, Lieferant) und mit Lieferant zusätzlich in 'Material-Lieferanten'. Bestehende
Angebote ändern sich nie: festgeschriebene behalten ihren Preisstand, offene meldet der Preiswächter.
"""
import csv
import datetime
import io
import json
import re

from . import erp_preise
from . import materialplattform as mp

FELDER = (("materialnr", "Materialnummer / Artikelnr."), ("bezeichnung", "Bezeichnung"), ("werkstoff", "Werkstoff"),
          ("abmessung", "Abmessung"), ("form", "Profilart"), ("a", "Außen-Ø / Breite [mm]"), ("b", "Höhe [mm]"),
          ("wand", "Wandstärke [mm]"), ("laenge", "Länge [mm]"), ("preis", "EK-Preis"), ("einheit", "Preiseinheit"),
          ("lieferant", "Lieferant"), ("gewicht", "Gewicht [kg/m]"), ("gueltig_ab", "Gültig ab"),
          ("oberflaeche", "Oberfläche"), ("handelsname", "Handelsbezeichnung"),
          ("bestellnr", "Bestellnummer (Lieferant)"))
FELD_TITEL = dict(FELDER)
PFLICHT = ("preis",)                 # dazu Bezeichnung oder Abmessung/Maße (prüft analysieren)
PROFILE = "material_importprofile"   # Einstellung (intern, nur dieser PC): {Name: dict(kopf, spalten, einheit, lieferant)}

_KOPF = {"materialnr": ("artikelnummer", "artikelnr", "artnr", "materialnummer", "materialnr", "matnr", "artikel",
                        "itemno", "nummer", "sachnummer", "teilenummer"),
         "bezeichnung": ("bezeichnung", "artikelbezeichnung", "materialbezeichnung", "materialname", "ekartikel",
                         "beschreibung", "text", "kurztext", "name", "description"),
         "werkstoff": ("werkstoff", "guete", "güte", "material", "stahlsorte", "qualitaet", "qualität", "grade",
                       "werkstoffnummer"),
         "abmessung": ("abmessung", "dimension", "masse", "maße", "groesse", "größe", "profilabmessung", "size"),
         "form": ("profilart", "profiltyp", "profil", "form", "artikelgruppe", "warengruppe"),
         "a": ("aussendurchmesser", "außendurchmesser", "durchmesser", "breite", "da", "aussenmass", "außenmaß"),
         "b": ("hoehe", "höhe", "breite2"),
         "wand": ("wandstaerke", "wandstärke", "wand", "wanddicke", "dicke", "staerke", "stärke", "s"),
         "laenge": ("laenge", "länge", "stangenlaenge", "stangenlänge", "lieferlaenge", "lieferlänge", "fixlaenge"),
         "preis": ("ekpreis", "einkaufspreis", "ek", "preis", "nettopreis", "listenpreis", "price", "vkpreis"),
         "einheit": ("preiseinheit", "einheit", "me", "mengeneinheit", "pe", "unit", "basis"),
         "lieferant": ("lieferant", "hauptlieferant", "kreditor", "supplier", "hersteller"),
         "gewicht": ("gewicht", "gewichtjem", "kgm", "kgjem", "metergewicht", "weight"),
         "gueltig_ab": ("gueltigab", "gültigab", "gueltig", "gültig", "datum", "preisdatum", "stand"),
         "oberflaeche": ("oberflaeche", "oberfläche", "ausfuehrung", "ausführung", "finish"),
         "handelsname": ("handelsbezeichnung", "handelsname", "markenname"),
         "bestellnr": ("bestellnummer", "bestellnr", "lieferantenartikelnummer", "lieferantenartnr",
                       "lieferantenartikelnr", "herstellerartikelnummer", "herstellernummer", "supplierpartno",
                       "orderno", "bestellcode")}
_REIHE = ("bestellnr", "materialnr", "bezeichnung", "werkstoff", "abmessung", "wand", "preis", "einheit", "lieferant", "gewicht",
          "gueltig_ab", "laenge", "oberflaeche", "handelsname", "form", "a", "b")

NEU, AKTUALISIERT, PREIS, GLEICH, DOPPELT, FEHLER, OFFEN = (
    "neu", "aktualisiert", "Preisänderung", "unverändert", "doppelt", "fehlerhaft", "nicht zuordenbar")
GRUPPEN = (NEU, PREIS, AKTUALISIERT, GLEICH, DOPPELT, FEHLER, OFFEN)
AUSFUEHRBAR = (NEU, PREIS, AKTUALISIERT)
SPRUNG_PCT = 15.0           # Preiswarnung in der Vorschau ab ±15 % zum bisherigen Preis
GEWICHT_TOL = 0.05          # Gewicht aus dem ERP weicht mehr als 5 % vom berechneten kg/m ab: Hinweis

TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS material_importe (id INTEGER PRIMARY KEY, zeit TEXT, datei TEXT, importprofil TEXT, "
    "benutzer TEXT, zeilen INTEGER, neu INTEGER, aktualisiert INTEGER, preise INTEGER, unveraendert INTEGER, "
    "doppelt INTEGER, fehler INTEGER, offen INTEGER, status TEXT, protokoll TEXT)",
    "CREATE TABLE IF NOT EXISTS material_import_posten (id INTEGER PRIMARY KEY, import_id INTEGER, tabelle TEXT, "
    "zeilen_id INTEGER, aktion TEXT, alt TEXT, neu TEXT)",
)


class ImportFehler(Exception):
    pass


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _norm(t):
    return re.sub(r"[^a-z0-9äöüß]", "", str(t or "").lower())


# ------------------------------------------------------------------ 1. Lesen
def lesen(roh, dateiname=""):
    """Datei (Bytes) -> dict(kopf, zeilen, erste). .xlsx wird vorher als CSV gelesen."""
    if str(dateiname).lower().endswith(".xlsx") or roh[:2] == b"PK":
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "datei.xlsx"
            p.write_bytes(roh)
            text = mp.xlsx_als_csv(p)
        if text is None:
            raise ImportFehler("Die Excel-Datei ist nicht lesbar.")
        roh = text
    try:
        return erp_preise.lesen(roh)
    except erp_preise.ErpFehler as e:
        raise ImportFehler(str(e)) from None


# ------------------------------------------------------------------ 2. Spalten und Importprofile
def spalten_vorschlag(kopf):
    """{Feld: Spaltennummer} aus den Spaltenköpfen: erst gleicher Name, dann Name enthalten."""
    namen = [_norm(k) for k in kopf]
    frei, out = set(range(len(kopf))), {}
    for gleich in (True, False):
        for feld in _REIHE:
            if feld in out:
                continue
            for wort in _KOPF[feld]:
                w = _norm(wort)
                treffer = [i for i in sorted(frei) if (namen[i] == w if gleich else (len(w) > 2 and w in namen[i]))]
                if treffer:
                    out[feld] = treffer[0]
                    frei.discard(treffer[0])
                    break
    return out


def profile(db):
    return dict(db.einstellung(PROFILE) or {})


def profil_speichern(db, name, kopf, spalten, einheit=None, lieferant=None):
    alle = profile(db)
    alle[name] = dict(kopf="|".join(_norm(k) for k in kopf), spalten={f: int(i) for f, i in spalten.items()},
                      einheit=einheit or "", lieferant=lieferant or "")
    db.einstellung_setzen(PROFILE, alle)


def profil_loeschen(db, name):
    alle = profile(db)
    alle.pop(name, None)
    db.einstellung_setzen(PROFILE, alle)


def profil_fuer(db, kopf):
    """(Name, Profil) des gespeicherten Importprofils mit genau diesen Spaltenköpfen oder (None, None)."""
    sig = "|".join(_norm(k) for k in kopf)
    return next(((n, p) for n, p in profile(db).items() if p.get("kopf") == sig), (None, None))


def fehlende(spalten):
    """Was der Zuordnung noch fehlt (Texte) – leer = vollständig."""
    out = [FELD_TITEL[f] for f in PFLICHT if f not in spalten]
    if not any(f in spalten for f in ("bezeichnung", "abmessung", "a")):
        out.append("Bezeichnung oder Abmessung")
    return out


# ------------------------------------------------------------------ 3. Analyse / Vorschau
EINHEITEN = {"€/m": ("€/m", 1.0), "eur/m": ("€/m", 1.0), "m": ("€/m", 1.0), "lfm": ("€/m", 1.0), "€/lfm": ("€/m", 1.0),
             "€/100m": ("€/m", 0.01), "100m": ("€/m", 0.01), "€/kg": ("€/kg", 1.0), "kg": ("€/kg", 1.0),
             "€/t": ("€/kg", 0.001), "t": ("€/kg", 0.001), "to": ("€/kg", 0.001), "€/to": ("€/kg", 0.001),
             "€/100kg": ("€/kg", 0.01), "100kg": ("€/kg", 0.01), "€/stange": ("€/Stange", 1.0),
             "stange": ("€/Stange", 1.0), "€/stück": ("€/Stange", 1.0), "€/stk": ("€/Stange", 1.0),
             "stück": ("€/Stange", 1.0), "stk": ("€/Stange", 1.0), "st": ("€/Stange", 1.0)}


def einheit_lesen(t, vorgabe="€/m"):
    """('€/m'|'€/kg'|'€/Stange', Faktor) aus der Preiseinheit; leer = vorgabe. None = unbekannt."""
    s = re.sub(r"\s+", "", str(t or "").lower()).replace("eur", "€").replace("je", "/").replace("pro", "/")
    if not s:
        return EINHEITEN.get(re.sub(r"\s+", "", str(vorgabe).lower()), ("€/m", 1.0))
    if s in EINHEITEN:
        return EINHEITEN[s]
    s2 = s.lstrip("€/")
    return EINHEITEN.get(s2) or EINHEITEN.get("€/" + s2)


def _zelle(z, spalten, feld):
    i = spalten.get(feld)
    return z[i].strip() if i is not None and i < len(z) else ""


def _profil(text, form, a, b, wand, k):
    """(Profil-ID vorhanden oder None, Vorschlag für neues Profil oder None)."""
    from .profil_neu import profil_id
    if form and a and wand:
        f = next((x for x in ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachoval", "Elliptisch", "Flachstahl")
                  if _norm(x)[:5] in _norm(form)), None) or \
            {"vierkantrohr": "Quadratrohr", "rr": "Rundrohr", "qr": "Quadratrohr", "re": "Rechteckrohr",
             "ovalrohr": "Flachoval"}.get(_norm(form))
        if f:
            mas = dict(form=f, a=a, b=b if f in ("Rechteckrohr", "Flachoval", "Elliptisch", "Flachstahl") else None,
                       wand=wand)
            if f == "Rechteckrohr" and not b:
                mas = None
            if mas:
                pid = profil_id(mas["form"], mas["a"], mas["b"], mas["wand"])
                return (pid, None) if pid in k.profile else (None, dict(mas, profil_id=pid))
    pid, mas = erp_preise.profil_finden(text, k.profile)
    if pid:
        return pid, None
    if mas:
        return None, dict(mas, profil_id=profil_id(mas["form"], mas["a"], mas["b"], mas["wand"]))
    return None, None


def analysieren(db, daten, spalten, einheit_vorgabe="€/m", lieferant_vorgabe=None, heute=None):
    """Vorschau: [dict(zeile, gruppe, materialnr, bezeichnung, profil_id, profil_neu, werkstoff_id, werkstoff_neu,
    oberflaeche, basis, preis, preis_m, alt_m, pct, laenge, lieferant, gueltig_ab, hinweis, roh)]. Ändert nichts."""
    from . import erp_anlegen
    heute = heute or datetime.date.today()
    k = db.kontext()
    tabellen = db.tabellen()
    preise = {mp.schluessel(z): z for z in tabellen.get("preise") or ()}
    stamm = {(z.get("profil_id"), z.get("werkstoff_id"), z.get("oberflaeche") or ""): z
             for z in db.zeilen("materialstamm")}
    gemerkt = {}
    try:
        for z in erp_preise.zuordnungen(db).values():
            if z.get("artikelnr") and not z.get("ignorieren"):
                gemerkt[z["artikelnr"]] = z
    except Exception:           # noqa: BLE001  (Datei ohne ERP-Tabellen)
        from . import protokoll
        protokoll.warnung("Materialimport: ERP-Zuordnungen nicht lesbar")
    from . import material_stamm
    nummern = material_stamm.nummern(db)    # vorhandene Werte über Artikel- und Bestellnummer erkennen (23.11.2026)
    neue_ws = {}
    gesehen, out = {}, []
    for n, z in enumerate(daten["zeilen"], daten.get("erste", 2)):
        roh = list(z)
        def zelle(f):
            return _zelle(z, spalten, f)
        e = dict(zeile=n, materialnr=zelle("materialnr"), bezeichnung=zelle("bezeichnung"), roh=roh, hinweis=[],
                 profil_id=None, profil_neu=None, werkstoff_id=None, werkstoff_neu=None, oberflaeche="", basis=None,
                 preis=None, preis_m=None, alt_m=None, pct=None, laenge=None, lieferant=None, gueltig_ab=None,
                 handelsname=zelle("handelsname"), bestellnr=zelle("bestellnr"))
        out.append(e)
        if not any(c.strip() for c in z):
            e.update(gruppe=FEHLER, hinweis=["leere Zeile"])
            continue
        p_text = zelle("preis")
        p = erp_preise.zahl(p_text)
        ein = einheit_lesen(zelle("einheit"), einheit_vorgabe)
        if p is None or p <= 0:
            e.update(gruppe=FEHLER, hinweis=[f"EK-Preis „{p_text}“ nicht lesbar oder ≤ 0"])
            continue
        if ein is None:
            e.update(gruppe=FEHLER, hinweis=[f"Preiseinheit „{zelle('einheit')}“ unbekannt (€/m, €/kg, €/t, "
                                             "€/100 m, €/Stange, €/Stück)"])
            continue
        e["basis"], e["preis"] = ein[0], round(p * ein[1], 6)
        lg = erp_preise.zahl(zelle("laenge"))
        e["laenge"] = lg if lg and 500 <= lg <= 30000 else (lg * 1000 if lg and 0.5 <= lg <= 30 else None)
        if e["basis"] == "€/Stange" and not e["laenge"]:
            e["laenge"] = 6000.0
            e["hinweis"].append("Preis je Stange/Stück ohne Länge: 6.000 mm angenommen")
        d_text = zelle("gueltig_ab")
        d = erp_preise.datum(d_text) if d_text else None
        if d_text and d is None:
            e["hinweis"].append(f"Gültig ab „{d_text}“ nicht lesbar: heute")
        e["gueltig_ab"] = (d or heute).isoformat()
        lief = zelle("lieferant") or lieferant_vorgabe or ""
        e["lieferant"] = lief if lief in k.zukauf_lieferanten else None
        if lief and e["lieferant"] is None:
            e["hinweis"].append(f"Lieferant „{lief}“ nicht im Lieferantenstamm: Preis ohne Lieferant")
        text = " ".join(x for x in (e["bezeichnung"], zelle("abmessung"), zelle("werkstoff"), zelle("oberflaeche"))
                        if x) + erp_preise.artikelnr_hinweis(e["materialnr"])
        a, b, w = (erp_preise.zahl(zelle(f)) for f in ("a", "b", "wand"))
        if not w and zelle("abmessung") and a is None:
            w = None
        merk = gemerkt.get(e["materialnr"]) if e["materialnr"] else None
        quelle = "Zuordnung der Artikelnummer gemerkt"
        if not (merk and merk.get("profil_id") in k.profile and merk.get("werkstoff_id") in k.werkstoffe):
            merk = None
            for nr in (e["materialnr"], e["bestellnr"]):
                if nr and nummern.get(str(nr).strip()):
                    merk = nummern[str(nr).strip()]
                    quelle = f"vorhanden, erkannt über {merk['quelle']} {nr}"
                    break
        if merk:
            pid, vorschlag = merk["profil_id"], None
            wid, wneu = merk["werkstoff_id"], None
            e["oberflaeche"] = merk.get("oberflaeche") or ""
            e["hinweis"].append(quelle)
        else:
            pid, vorschlag = _profil(text, zelle("form"), a, b, w, k)
            form = (k.profile.get(pid) or {}).get("form") if pid else (vorschlag or {}).get("form")
            wtext = zelle("werkstoff") or text
            if form in erp_anlegen.HOHLPROFILE:
                wid, wneu, _grund = erp_anlegen.werkstoff_fuer(wtext + " " + text, k)
                if wid is None and wneu is None:
                    wid = erp_preise.werkstoff_finden(wtext, k.werkstoffe)[0]
            else:
                wid, wneu = erp_preise.werkstoff_finden(wtext, k.werkstoffe)[0], None
            if wneu is not None:
                wneu = neue_ws.setdefault(wneu["werkstoff_id"], wneu)
                wid = wneu["werkstoff_id"]
            elif wid is None:
                kand = erp_preise.werkstoff_finden(wtext, k.werkstoffe)[2]
                e["hinweis"].append(f"Werkstoff mehrdeutig ({', '.join(kand[:4])}), bitte im ERP-Text eindeutig "
                                    "oder Zuordnung merken" if len(kand) > 1 else
                                    f"Werkstoff „{zelle('werkstoff') or '?'}“ nicht erkannt")
            ober, unbekannt = erp_preise.oberflaeche_finden(text, k.oberflaechen, k.werkstoffe.get(wid))
            if unbekannt:
                e["hinweis"].append(f"Oberfläche „{ober}“ fehlt in den Stammdaten")
                wid = None
            e["oberflaeche"] = ober or ""
            e["werkstoff_neu"] = wneu
        if pid is None and vorschlag is None:
            e["hinweis"].append("Abmessung nicht erkannt")
        e.update(profil_id=pid or (vorschlag or {}).get("profil_id"), profil_neu=vorschlag, werkstoff_id=wid)
        if e["profil_id"] is None or wid is None:
            e["gruppe"] = OFFEN
            continue
        schl = (e["profil_id"], wid, e["oberflaeche"], e["lieferant"] or "", e["laenge"] or 0)
        if schl in gesehen:
            e["gruppe"] = DOPPELT
            e["hinweis"].append(f"gleiches Material wie Zeile {gesehen[schl]} (die letzte Zeile zählt nicht)")
            continue
        gesehen[schl] = n
        pr = k.profile.get(e["profil_id"]) or vorschlag or {}
        ws = k.werkstoffe.get(wid) or wneu or {}
        kgm = mp.kg_je_m(pr, ws) if pr.get("profil_id") in k.profile or vorschlag else None
        if vorschlag and kgm is None:
            from .stammdaten import flaeche_berechnet
            fl = flaeche_berechnet(vorschlag)
            kgm = fl * float(ws.get("dichte") or 7.85) / 1000 if fl else None
        gew = erp_preise.zahl(zelle("gewicht"))
        if gew and kgm and abs(gew / kgm - 1) > GEWICHT_TOL:
            e["hinweis"].append(f"Gewicht laut ERP {gew:.3f} kg/m, berechnet {kgm:.3f} kg/m (Abmessung prüfen)")
        e["preis_m"] = mp.je_meter(e["basis"], e["preis"], kgm, e["laenge"] or 6000)
        alt = preise.get((e["profil_id"], wid))
        if alt is not None:
            e["alt_m"] = mp.je_meter(alt.get("basis"), alt.get("preis"), kgm, alt.get("lieferlaenge") or 6000)
        if e["alt_m"] and e["preis_m"]:
            e["pct"] = (e["preis_m"] / e["alt_m"] - 1) * 100
            if abs(e["pct"]) >= SPRUNG_PCT:
                e["hinweis"].append(f"Preissprung {'+' if e['pct'] >= 0 else '−'}{abs(e['pct']):.1f} % – bitte prüfen"
                                   .replace(".", ","))
        sz = stamm.get((e["profil_id"], wid, e["oberflaeche"] or ""))
        if sz and e["materialnr"] and sz.get("materialnr") and str(sz["materialnr"]) != str(e["materialnr"]):
            e["hinweis"].append(f"Materialnummer {sz['materialnr']} → {e['materialnr']}")
        if vorschlag or wneu or sz is None:
            e["gruppe"] = NEU
            if vorschlag:
                e["hinweis"].append(f"Profil {vorschlag['profil_id']} wird angelegt")
            if wneu:
                e["hinweis"].append(f"Werkstoff {wid} wird angelegt ({wneu.get('norm')})")
        elif alt is None or e["alt_m"] is None or abs((e["preis_m"] or 0) - e["alt_m"]) >= 0.005:
            e["gruppe"] = PREIS
        elif any((e[f] or "") != (sz.get(f2) or "") for f, f2 in (("materialnr", "materialnr"),
                                                                    ("bezeichnung", "bezeichnung"),
                                                                    ("handelsname", "handelsname")) if e[f]):
            e["gruppe"] = AKTUALISIERT
        else:
            e["gruppe"] = GLEICH
    return out


def zaehlen(posten):
    out = {g: 0 for g in GRUPPEN}
    for e in posten:
        out[e["gruppe"]] += 1
    return out


def fehler_csv(posten):
    """Fehlerhafte, doppelte und nicht zuordenbare Zeilen als CSV (Semikolon, mit Grund) zum Nachbessern im ERP."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Zeile", "Gruppe", "Grund", "Inhalt der Zeile …"])
    for e in posten:
        if e["gruppe"] in (FEHLER, OFFEN, DOPPELT):
            w.writerow([e["zeile"], e["gruppe"], "; ".join(e["hinweis"])] + list(e["roh"]))
    return buf.getvalue()


# ------------------------------------------------------------------ 4. Ausführen mit Protokoll / 5. Rückgängig
class _Lauf:
    def __init__(self, db, import_id):
        self.db, self.id = db, import_id

    def merken(self, tabelle, zeilen_id, aktion, alt=None, neu=None):
        with self.db.con:
            self.db.con.execute("INSERT INTO material_import_posten (import_id, tabelle, zeilen_id, aktion, alt, neu) "
                                "VALUES (?, ?, ?, ?, ?, ?)", (self.id, tabelle, zeilen_id, aktion,
                                                              json.dumps(alt, default=str) if alt else None,
                                                              json.dumps(neu, default=str) if neu else None))

    def neu(self, tabelle, werte):
        i = self.db.neu(tabelle, werte)
        self.merken(tabelle, i, "neu", neu=werte)
        return i

    def aendern(self, tabelle, zeile, werte):
        alt = {f: zeile.get(f) for f in werte if zeile.get(f) != werte[f]}
        if not alt:
            return False
        for f in alt:
            self.db.aendern(tabelle, zeile["id"], f, werte[f])
        kontext = {f: zeile.get(f) for f in ("profil_id", "werkstoff_id", "lieferant", "basis") if zeile.get(f)}
        self.merken(tabelle, zeile["id"], "geaendert", alt=alt, neu=dict({f: werte[f] for f in alt},
                                                                          _kontext=kontext))
        return True


def ausfuehren(db, posten, gruppen=AUSFUEHRBAR, datei="", importprofil="", sichern=True):
    """Bestätigte Gruppen übernehmen. Ergebnis dict(import_id, neu, aktualisiert, preise, profile, werkstoffe,
    sicherung). Jeder Fehler nimmt den ganzen Lauf zurück (ImportFehler)."""
    from . import erp_anlegen  # noqa: F401  (Werkstoff-Vorlagen)
    sich = None
    if sichern:
        try:
            sich = db.sicherung(zusatz="vor_Materialimport")
        except Exception:       # noqa: BLE001  (ohne Sicherungsordner, z. B. Tests: Rückgängig bleibt möglich)
            from . import protokoll
            protokoll.warnung("Materialimport: Sicherung nicht möglich")
    z = zaehlen(posten)
    benutzer = db.einstellung("benutzer_name") or ""
    with db.con:
        cur = db.con.execute(
            "INSERT INTO material_importe (zeit, datei, importprofil, benutzer, zeilen, neu, aktualisiert, preise, "
            "unveraendert, doppelt, fehler, offen, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_jetzt(), str(datei), importprofil or "", benutzer, len(posten), 0, 0, 0, z[GLEICH], z[DOPPELT],
             z[FEHLER], z[OFFEN], "läuft"))
    import_id = cur.lastrowid if cur.lastrowid else db.con.execute("SELECT MAX(id) FROM material_importe").fetchone()[0]
    lauf = _Lauf(db, import_id)
    erg = dict(import_id=import_id, neu=0, aktualisiert=0, preise=0, profile=0, werkstoffe=0, sicherung=sich)
    heute = datetime.date.today().isoformat()
    try:
        for e in posten:
            if e["gruppe"] not in gruppen:
                continue
            wneu = e.get("werkstoff_neu")
            if wneu and wneu["werkstoff_id"] not in db.kontext().werkstoffe:
                lauf.neu("werkstoffe", {kk: v for kk, v in wneu.items() if v is not None})
                erg["werkstoffe"] += 1
            pv = e.get("profil_neu")
            if pv and pv["profil_id"] not in db.kontext().profile:
                lauf.neu("profile", {kk: v for kk, v in dict(profil_id=pv["profil_id"], form=pv["form"], a=pv["a"],
                                                             b=pv.get("b"), wand=pv["wand"],
                                                             bemerkung="aus ERP-Materialimport").items()
                                     if v is not None})
                erg["profile"] += 1
            pid, wid, ober = e["profil_id"], e["werkstoff_id"], e["oberflaeche"] or ""
            # Materialstamm
            sz = next((s for s in db.zeilen("materialstamm") if (s.get("profil_id"), s.get("werkstoff_id"),
                                                                  s.get("oberflaeche") or "") == (pid, wid, ober)), None)
            werte = {f: e[f] for f in ("materialnr", "bezeichnung", "handelsname") if e.get(f)}
            if e.get("lieferant"):
                werte["lieferant"] = e["lieferant"]
            if sz is None:
                lauf.neu("materialstamm", dict(werte, profil_id=pid, werkstoff_id=wid, oberflaeche=ober or None,
                                               aktiv="ja", angelegt=heute, geaendert=heute,
                                               quelle=f"ERP-Import {heute}"))
                erg["neu"] += 1
            elif lauf.aendern("materialstamm", sz, dict(werte, geaendert=heute)):
                erg["aktualisiert"] += 1 if e["gruppe"] == AKTUALISIERT else 0
            if ober:            # Preise gelten für Rohware; Oberfläche ist ein Aufpreis
                continue
            # aktiver Preis
            alt = next((p for p in db.zeilen("preise") if (p.get("profil_id"), p.get("werkstoff_id")) == (pid, wid)),
                       None)
            pw = dict(basis=e["basis"], preis=e["preis"], gueltig_ab=e["gueltig_ab"])
            if e.get("lieferant"):
                pw["lieferant"] = e["lieferant"]
            if e["basis"] == "€/Stange" or (e.get("laenge") and alt is None):
                pw["lieferlaenge"] = e["laenge"]
            if alt is None:
                lauf.neu("preise", dict(pw, profil_id=pid, werkstoff_id=wid))
                erg["preise"] += 1
            elif lauf.aendern("preise", alt, pw):
                erg["preise"] += 1
            # Lieferantenpreis
            if e.get("lieferant"):
                lg = e.get("laenge")
                lz = next((x for x in db.zeilen(mp.LIEFERANTEN_TABELLE) if (x.get("profil_id"), x.get("werkstoff_id"),
                           x.get("lieferant")) == (pid, wid, e["lieferant"]) and (x.get("laenge") or None) == lg
                           and not x.get("ab_menge")), None)
                lw = dict(basis=e["basis"], preis=e["preis"], gueltig_ab=e["gueltig_ab"])
                if e.get("bestellnr") or e.get("materialnr"):
                    lw["artikelnr"] = e.get("bestellnr") or e["materialnr"]
                if lz is None:
                    lauf.neu(mp.LIEFERANTEN_TABELLE, dict(lw, profil_id=pid, werkstoff_id=wid,
                                                          lieferant=e["lieferant"], laenge=lg))
                else:
                    lauf.aendern(mp.LIEFERANTEN_TABELLE, lz, lw)
            if e.get("materialnr"):     # Einkäufe (erp_preise) mit derselben Artikelnummer zählen für dieses Material
                try:
                    erp_preise.zuordnung_merken(db, erp_preise.schluessel(e["materialnr"], e["bezeichnung"]),
                                                e["materialnr"], e["bezeichnung"], pid, wid, ober)
                except Exception:       # noqa: BLE001
                    from . import protokoll
                    protokoll.warnung("Materialimport: EK-Zuordnung nicht gemerkt")
    except Exception as ex:     # noqa: BLE001  (alles zurücknehmen, dann melden)
        rueckgaengig(db, import_id, status="abgebrochen, zurückgenommen")
        raise ImportFehler(f"Import abgebrochen und vollständig zurückgenommen: {ex}") from ex
    with db.con:
        db.con.execute("UPDATE material_importe SET neu=?, aktualisiert=?, preise=?, status=?, protokoll=? WHERE id=?",
                       (erg["neu"], erg["aktualisiert"], erg["preise"], "übernommen",
                        json.dumps(dict(profile=erg["profile"], werkstoffe=erg["werkstoffe"],
                                        sicherung=str(sich or ""))), import_id))
    from . import ki_protokoll
    ki_protokoll.schreiben(db, "Materialprüfung", "ERP-Materialimport",
                           ergebnis=f"{erg['neu']} neu, {erg['preise']} Preise, {erg['profile']} Profile, "
                                    f"{erg['werkstoffe']} Werkstoffe", quellen=[str(datei)])
    return erg


def laeufe(db):
    """Importhistorie, neueste zuerst: [dict(id, zeit, datei, importprofil, benutzer, zeilen, neu, aktualisiert,
    preise, unveraendert, doppelt, fehler, offen, status)]."""
    return [dict(r) for r in db.con.execute("SELECT * FROM material_importe ORDER BY id DESC")]


def letzter_lauf(db):
    try:
        r = db.con.execute("SELECT * FROM material_importe WHERE status='übernommen' ORDER BY id DESC "
                           "LIMIT 1").fetchone()
    except Exception:           # noqa: BLE001  (Datei ohne Importtabellen)
        return None
    return dict(r) if r else None


def posten_des_laufs(db, import_id):
    return [dict(r, alt=json.loads(r["alt"]) if r["alt"] else None, neu=json.loads(r["neu"]) if r["neu"] else None)
            for r in db.con.execute("SELECT * FROM material_import_posten WHERE import_id=? ORDER BY id",
                                    (import_id,))]


def rueckgaengig(db, import_id, status="rückgängig gemacht"):
    """Einen Importlauf zurücknehmen: in umgekehrter Reihenfolge neue Zeilen löschen und geänderte Felder auf den
    alten Wert setzen. Später von Hand geänderte Felder werden nicht überschrieben (Meldung). Ergebnis: (Anzahl
    zurückgenommen, [Meldungen])."""
    n, meldungen = 0, []
    for p in reversed(posten_des_laufs(db, import_id)):
        zeile = next((z for z in db.zeilen(p["tabelle"]) if z.get("id") == p["zeilen_id"]), None)
        if zeile is None:
            continue
        if p["aktion"] == "neu":
            db.loeschen(p["tabelle"], [p["zeilen_id"]])
            n += 1
        else:
            for f, v in (p["alt"] or {}).items():
                if zeile.get(f) != (p["neu"] or {}).get(f):
                    meldungen.append(f"{p['tabelle']} Zeile {p['zeilen_id']}: {f} inzwischen von Hand geändert, "
                                     "bleibt")
                    continue
                db.aendern(p["tabelle"], p["zeilen_id"], f, v)
            n += 1
    with db.con:
        db.con.execute("UPDATE material_importe SET status=? WHERE id=?", (status, import_id))
    return n, meldungen


def preis_aenderungen(db, import_id=None):
    """Preisänderungen aus der Importhistorie (für Preisverlauf mit Herkunft): [dict(zeit, datei, tabelle, profil_id,
    werkstoff_id, lieferant, alt, neu, pct, quelle)]; import_id = nur dieser Lauf."""
    sql = ("SELECT p.*, i.zeit AS zeit, i.datei AS datei, i.status AS status FROM material_import_posten p "
           "JOIN material_importe i ON i.id = p.import_id WHERE p.tabelle IN ('preise', 'material_lieferanten')")
    arg = ()
    if import_id is not None:
        sql += " AND p.import_id=?"
        arg = (import_id,)
    out, k = [], None
    for r in db.con.execute(sql + " ORDER BY p.id DESC", arg):
        alt, neu = json.loads(r["alt"]) if r["alt"] else {}, json.loads(r["neu"]) if r["neu"] else {}
        if "preis" not in neu:
            continue
        a, b = mp._n(alt.get("preis")), mp._n(neu.get("preis"))
        ktx = dict(neu.get("_kontext") or {}, **{f: neu[f] for f in ("profil_id", "werkstoff_id", "lieferant", "basis")
                                                 if neu.get(f)})
        ba, bn = alt.get("basis") or ktx.get("basis"), ktx.get("basis")
        if a and b and ba != bn:        # andere Preisbasis (z. B. €/kg → €/m): in €/m vergleichen
            if k is None:
                k = db.kontext()
            kgm = mp.kg_je_m(k.profile.get(ktx.get("profil_id")) or {}, k.werkstoffe.get(ktx.get("werkstoff_id")) or {})
            a, b = mp.je_meter(ba, a, kgm, 6000), mp.je_meter(bn, b, kgm, 6000)
            ktx["basis"] = "€/m (umgerechnet)"
        out.append(dict(zeit=r["zeit"], datei=r["datei"], tabelle=r["tabelle"], profil_id=ktx.get("profil_id"),
                        werkstoff_id=ktx.get("werkstoff_id"), lieferant=ktx.get("lieferant"), zeilen_id=r["zeilen_id"],
                        alt=a, neu=b, basis=ktx.get("basis"),
                        pct=(b / a - 1) * 100 if a and b else None, status=r["status"],
                        quelle=f"ERP-Import {str(r['zeit'])[:10]}"))
    return out
