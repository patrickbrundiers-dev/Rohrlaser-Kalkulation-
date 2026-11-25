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

from . import csv_import, erp_preise
from . import materialplattform as mp

FELDER = (("materialnr", "Materialnummer / Artikelnr."), ("bezeichnung", "Bezeichnung"), ("werkstoff", "Werkstoff"),
          ("abmessung", "Abmessung"), ("form", "Profilart"), ("a", "Außen-Ø / Breite [mm]"), ("b", "Höhe [mm]"),
          ("wand", "Wandstärke [mm]"), ("laenge", "Länge [mm]"), ("preis", "EK-Preis"), ("einheit", "Preiseinheit"),
          ("lieferant", "Lieferant"), ("gewicht", "Gewicht [kg/m]"), ("gueltig_ab", "Gültig ab"),
          ("oberflaeche", "Oberfläche"), ("handelsname", "Handelsbezeichnung"),
          ("bestellnr", "Bestellnummer (Lieferant)"), ("gueltig_bis", "Gültig bis"), ("waehrung", "Währung"))
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
         "gueltig_ab": ("gueltigab", "gültigab", "gueltigvon", "gültigvon", "gueltig", "gültig", "datum", "preisdatum",
                        "stand", "validfrom"),
         "gueltig_bis": ("gueltigbis", "gültigbis", "ablaufdatum", "validuntil", "validto"),
         "waehrung": ("waehrung", "währung", "whrg", "currency"),
         "oberflaeche": ("oberflaeche", "oberfläche", "ausfuehrung", "ausführung", "finish"),
         "handelsname": ("handelsbezeichnung", "handelsname", "markenname"),
         "bestellnr": ("bestellnummer", "bestellnr", "lieferantenartikelnummer", "lieferantenartnr",
                       "lieferantenartikelnr", "herstellerartikelnummer", "herstellernummer", "supplierpartno",
                       "orderno", "bestellcode")}
_REIHE = ("bestellnr", "materialnr", "bezeichnung", "werkstoff", "abmessung", "wand", "preis", "einheit", "lieferant", "gewicht",
          "gueltig_bis", "gueltig_ab", "laenge", "oberflaeche", "handelsname", "form", "a", "b", "waehrung")

NEU, AKTUALISIERT, PREIS, GLEICH, DOPPELT, FEHLER, OFFEN = (
    "neu", "aktualisiert", "Preisänderung", "unverändert", "doppelt", "fehlerhaft", "nicht zuordenbar")
GRUPPEN = (NEU, PREIS, AKTUALISIERT, GLEICH, DOPPELT, FEHLER, OFFEN)
AUSFUEHRBAR = (NEU, PREIS, AKTUALISIERT)
SPRUNG_PCT = 15.0           # Preiswarnung ab ±15 %, nur falls die Einstellung ek_preis_markierung (Vorgabe 10 %) fehlt
GEWICHT_TOL = 0.05          # Gewicht aus dem ERP weicht mehr als 5 % vom berechneten kg/m ab: Hinweis

TABELLEN_SQL = csv_import.TABELLEN_SQL      # Importläufe und Posten: gemeinsame Importbasis (Spalte art)


class ImportFehler(Exception):
    pass


def einrichten(con):
    csv_import.einrichten(con)


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
        return csv_import.datei_lesen(roh, bekannte=[w for ws in _KOPF.values() for w in ws])
    except csv_import.ImportFehler as e:
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
    csv_import.profil_speichern(db, PROFILE, name, kopf, spalten, einheit=einheit or "", lieferant=lieferant or "")


def profil_loeschen(db, name):
    csv_import.profil_loeschen(db, PROFILE, name)


def profil_fuer(db, kopf, lieferant=None):
    """(Name, Profil) des gespeicherten Importprofils für diese Spaltenköpfe oder (None, None): genau gleicher Kopf,
    sonst ein Profil, dessen Spalten (über den Namen) alle vorkommen – dann mit den Spaltennummern dieser Datei."""
    n, p, sp = csv_import.profil_passend(profile(db), kopf, lieferant)
    return (n, dict(p, spalten=sp)) if n else (None, None)


def spalten_erkennen(daten):
    """{Feld: dict(spalte, sicherheit, grund)}: Spaltennamen wie spalten_vorschlag, Gegenprobe am Inhalt."""
    out = {}
    inhalt = {"preis": lambda a: a["zahl"], "gueltig_ab": lambda a: a["datum"], "gueltig_bis": lambda a: a["datum"],
              "gewicht": lambda a: a["zahl"], "wand": lambda a: a["zahl"], "laenge": lambda a: a["zahl"]}
    for f, i in spalten_vorschlag(daten["kopf"]).items():
        s_, grund = csv_import.SICHER, f"Spaltenname „{daten['kopf'][i]}“"
        werte = csv_import.spalten_werte(daten, i)
        if f in inhalt and any(c.strip() for c in werte) and inhalt[f](csv_import.inhalt_art(werte)) < 0.5:
            s_, grund = csv_import.VORSCHLAG, grund + ", aber der Inhalt passt nicht dazu – bitte prüfen"
        out[f] = dict(spalte=i, sicherheit=s_, grund=grund)
    if not daten.get("mit_kopf", True):
        return csv_import.spalten_erkennen(daten, {f: () for f in _KOPF}, reihe=("bezeichnung", "preis",
                                                                                  "materialnr"),
                                           inhalt=dict(inhalt, bezeichnung=erp_preise._inhalt_bezeichnung,
                                                       materialnr=erp_preise._inhalt_artikelnr))
    return out


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


def analysieren(db, daten, spalten, einheit_vorgabe="€/m", lieferant_vorgabe=None, heute=None, hand=None,
                ersetzen=(), fortschritt=None):
    """Vorschau: [dict(zeile, gruppe, materialnr, bezeichnung, profil_id, profil_neu, werkstoff_id, werkstoff_neu,
    oberflaeche, basis, preis, preis_m, alt_m, pct, laenge, lieferant, gueltig_ab, hinweis, roh)]. Ändert nichts.
    hand = {Dateizeile: dict(profil_id, werkstoff_id, oberflaeche)}: in der Vorschau von Hand zugeordnete Zeilen
    (Ausbau 1.3); sie gehen vor jeder Erkennung und tragen hand=True. Gehört der aktive Preis einem anderen
    Lieferanten oder ist er neuer, bleibt er (lieferant_konflikt, Hinweis); Dateizeilen in ersetzen dürfen ihn
    ersetzen (von Hand bestätigt)."""
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
    sprung = db.einstellung(erp_preise.PREIS_MARKE)
    sprung = SPRUNG_PCT if sprung in (None, "") else float(sprung)
    dez = daten.get("dezimal")
    for n, z in enumerate(daten["zeilen"], daten.get("erste", 2)):
        if fortschritt and n % 500 == 0:
            fortschritt(n, len(daten["zeilen"]))
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
        p = erp_preise.zahl(p_text, dez)
        ein = einheit_lesen(zelle("einheit"), einheit_vorgabe)
        if p is None or p <= 0:
            e.update(gruppe=FEHLER, hinweis=[f"EK-Preis „{p_text}“ nicht lesbar oder ≤ 0"])
            continue
        if ein is None:
            e.update(gruppe=FEHLER, hinweis=[f"Preiseinheit „{zelle('einheit')}“ unbekannt (€/m, €/kg, €/t, "
                                             "€/100 m, €/Stange, €/Stück)"])
            continue
        w_text = zelle("waehrung")
        if w_text and w_text.lower().strip(". ") not in ("eur", "euro", "€"):
            e.update(gruppe=FEHLER, hinweis=[f"Währung {w_text}: nur Euro wird übernommen"])
            continue
        bis_text = zelle("gueltig_bis")
        bis = erp_preise.datum(bis_text) if bis_text else None
        if bis is not None and bis < heute:
            e.update(gruppe=FEHLER, hinweis=[f"Preis abgelaufen (gültig bis {bis.strftime('%d.%m.%Y')})"])
            continue
        e["gueltig_bis"] = bis.isoformat() if bis else None
        e["basis"], e["preis"] = ein[0], round(p * ein[1], 6)
        lg = erp_preise.zahl(zelle("laenge"), dez)
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
        a, b, w = (erp_preise.zahl(zelle(f), dez) for f in ("a", "b", "wand"))
        if not w and zelle("abmessung") and a is None:
            w = None
        merk = gemerkt.get(e["materialnr"]) if e["materialnr"] else None
        quelle = "Zuordnung der Artikelnummer gemerkt"
        von_hand = (hand or {}).get(n)
        if von_hand and von_hand.get("profil_id") in k.profile and von_hand.get("werkstoff_id") in k.werkstoffe:
            merk, quelle = von_hand, "in der Vorschau von Hand zugeordnet"
            e["hand"] = True
        elif not (merk and merk.get("profil_id") in k.profile and merk.get("werkstoff_id") in k.werkstoffe):
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
        gew = erp_preise.zahl(zelle("gewicht"), dez)
        if gew and kgm and abs(gew / kgm - 1) > GEWICHT_TOL:
            e["hinweis"].append(f"Gewicht laut ERP {gew:.3f} kg/m, berechnet {kgm:.3f} kg/m (Abmessung prüfen)")
        e["preis_m"] = mp.je_meter(e["basis"], e["preis"], kgm, e["laenge"] or 6000)
        alt = preise.get((e["profil_id"], wid))
        if alt is not None:
            e["alt_m"] = mp.je_meter(alt.get("basis"), alt.get("preis"), kgm, alt.get("lieferlaenge") or 6000)
        if e["alt_m"] and e["preis_m"]:
            e["pct"] = (e["preis_m"] / e["alt_m"] - 1) * 100
            if abs(e["pct"]) >= sprung:
                e["hinweis"].append(f"Preissprung {'+' if e['pct'] >= 0 else '−'}{abs(e['pct']):.1f} % – bitte prüfen"
                                   .replace(".", ","))
                e["markiert"] = True
        # Master-Auftrag 25.11.2026: ein neuer Lieferantenpreis ersetzt nie unbemerkt den aktiven Preis eines anderen
        # Lieferanten, und ein älterer Preis nie einen neueren
        if alt is not None and not e["oberflaeche"] and n not in ersetzen:
            a_lief = (alt.get("lieferant") or "").strip()
            if a_lief and e["lieferant"] and a_lief != e["lieferant"]:
                e["lieferant_konflikt"] = True
                e["hinweis"].append(f"aktiver Preis ist von {a_lief}: bleibt; der Preis von {e['lieferant']} wird als "
                                    "Lieferantenpreis gespeichert (aktiven Preis ersetzen nur von Hand)")
            elif alt.get("gueltig_ab") and str(alt["gueltig_ab"]) > e["gueltig_ab"]:
                e["lieferant_konflikt"] = True
                e["hinweis"].append(f"älter als der aktive Preis (gültig ab {alt['gueltig_ab']}): aktiver Preis bleibt")
        sz = stamm.get((e["profil_id"], wid, e["oberflaeche"] or ""))
        if sz and e["materialnr"] and sz.get("materialnr") and str(sz["materialnr"]) != str(e["materialnr"]):
            e["hinweis"].append(f"Materialnummer {sz['materialnr']} → {e['materialnr']}")
        if vorschlag or wneu or sz is None:
            e["gruppe"] = NEU
            if vorschlag:
                e["hinweis"].append(f"Profil {vorschlag['profil_id']} wird angelegt")
            if wneu:
                e["hinweis"].append(f"Werkstoff {wid} wird angelegt ({wneu.get('norm')})")
        elif (alt is None or e["alt_m"] is None or abs((e["preis_m"] or 0) - e["alt_m"]) >= 0.005) and \
                not (e.get("lieferant_konflikt") and not e["lieferant"]):
            e["gruppe"] = PREIS
        elif any((e[f] or "") != (sz.get(f2) or "") for f, f2 in (("materialnr", "materialnr"),
                                                                    ("bezeichnung", "bezeichnung"),
                                                                    ("handelsname", "handelsname")) if e[f]):
            e["gruppe"] = AKTUALISIERT
        else:
            e["gruppe"] = GLEICH
    return out


def hand_merken(db, posten, gruppen=None):
    """Von Hand zugeordnete Zeilen mit Artikelnummer als ERP-Zuordnung merken (erp_zuordnung): der nächste Import
    und der EK-Import erkennen den Artikel dann von selbst. gruppen: nur Zeilen dieser Gruppen (None = alle).
    Ergebnis: Anzahl gemerkter Artikel."""
    n = 0
    for e in posten:
        if not e.get("hand") or not e.get("materialnr") or (gruppen is not None and e["gruppe"] not in gruppen):
            continue
        erp_preise.zuordnung_merken(db, erp_preise.schluessel(e["materialnr"], e["bezeichnung"]), e["materialnr"],
                                    e["bezeichnung"], e["profil_id"], e["werkstoff_id"], e.get("oberflaeche") or "")
        n += 1
    return n


def auswirkung(db, posten, gruppen=AUSFUEHRBAR):
    """Auswirkung des Imports auf offene Angebote (Ausbau 2.5): Angebote ohne festgeschriebene Preise, die ein
    Material mit geändertem Preis verwenden und keinen eigenen Meterpreis an der Position haben; sie rechnen nach
    der Übernahme mit dem neuen Preis. Festgeschriebene Angebote ändern sich nie. Ergebnis: [dict(angebot_id,
    nummer, kunde, positionen, materialien [(Profil, Werkstoff, alt €/m, neu €/m, %)])], nach Nummer. Ändert nichts."""
    neu = {}
    for e in posten:
        if e["gruppe"] in gruppen and e.get("alt_m") and e.get("preis_m") and abs(e["preis_m"] - e["alt_m"]) >= 0.005:
            neu[(e["profil_id"], e["werkstoff_id"])] = (e["alt_m"], e["preis_m"], e.get("pct"))
    if not neu:
        return []
    out = {}
    try:
        zeilen = db.con.execute(
            "SELECT a.id, a.nummer, a.kunde, p.profil_id, p.werkstoff_id, COUNT(*) FROM positionen p "
            "JOIN angebote a ON a.id = p.angebot_id WHERE a.preisbasis IS NULL AND p.profil_id IS NOT NULL "
            "AND p.werkstoff_id IS NOT NULL AND p.preis_m IS NULL "
            "GROUP BY a.id, a.nummer, a.kunde, p.profil_id, p.werkstoff_id").fetchall()
    except Exception:           # noqa: BLE001  (nur Anzeige: nie die Vorschau verhindern)
        from . import protokoll
        protokoll.warnung("Materialimport: Auswirkung auf offene Angebote nicht lesbar")
        return []
    for aid, nummer, kunde, pid, wid, anzahl in zeilen:
        if (pid, wid) not in neu:
            continue
        z = out.setdefault(aid, dict(angebot_id=aid, nummer=nummer or "", kunde=kunde or "", positionen=0,
                                     materialien=[]))
        z["positionen"] += int(anzahl or 0)
        z["materialien"].append((pid, wid) + neu[(pid, wid)])
    return sorted(out.values(), key=lambda z: str(z["nummer"]))


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
_Lauf = csv_import.Lauf         # gemeinsame Importbasis (Posten gesammelt, ein Schreibvorgang)


def _aelter(neu, alt):
    """True, wenn das Gültig-ab neu vor alt liegt (beide als Datum/Text lesbar)."""
    try:
        a, b = str(neu or "")[:10], str(alt or "")[:10]
        return bool(a and b and a < b)
    except Exception:           # noqa: BLE001
        return False


def ausfuehren(db, posten, gruppen=AUSFUEHRBAR, datei="", importprofil="", sichern=True, fortschritt=None,
               aktiv_ersetzen=()):
    """Bestätigte Gruppen übernehmen. Ergebnis dict(import_id, neu, aktualisiert, preise, profile, werkstoffe,
    sicherung). Jeder Fehler nimmt den ganzen Lauf zurück (ImportFehler). Materialstamm, Preise und
    Lieferantenpreise werden einmal gelesen (nicht je Zeile). Den aktiven Preis eines anderen Lieferanten ersetzt
    eine Zeile nur, wenn ihre Dateizeile in aktiv_ersetzen steht (sonst nur Lieferantenpreis)."""
    from . import erp_anlegen  # noqa: F401  (Werkstoff-Vorlagen)
    sich = None
    if sichern:
        try:
            sich = db.sicherung(zusatz="vor_Materialimport")
        except Exception:       # noqa: BLE001  (ohne Sicherungsordner, z. B. Tests: Rückgängig bleibt möglich)
            from . import protokoll
            protokoll.warnung("Materialimport: Sicherung nicht möglich")
    z = zaehlen(posten)
    lieferanten = sorted({e["lieferant"] for e in posten if e.get("lieferant") and e["gruppe"] in gruppen})
    lauf = csv_import.lauf_beginnen(db, csv_import.ART_MATERIAL, datei, importprofil, len(posten),
                                    ", ".join(lieferanten)[:200],
                                    dict(unveraendert=z[GLEICH], doppelt=z[DOPPELT], fehler=z[FEHLER],
                                         offen=z[OFFEN]))
    import_id = lauf.id
    erg = dict(import_id=import_id, neu=0, aktualisiert=0, preise=0, profile=0, werkstoffe=0, sicherung=sich)
    heute = datetime.date.today().isoformat()
    k = db.kontext()
    werkstoffe, profile_ = set(k.werkstoffe), set(k.profile)
    stamm = {(s.get("profil_id"), s.get("werkstoff_id"), s.get("oberflaeche") or ""): s
             for s in db.zeilen("materialstamm")}
    preise = {}
    for p_ in db.zeilen("preise"):
        preise.setdefault((p_.get("profil_id"), p_.get("werkstoff_id")), p_)
    lief = {}
    for x in db.zeilen(mp.LIEFERANTEN_TABELLE):
        if not x.get("ab_menge"):
            lief.setdefault((x.get("profil_id"), x.get("werkstoff_id"), x.get("lieferant"), x.get("laenge") or None), x)
    zu = [e for e in posten if e["gruppe"] in gruppen]
    try:
        for i, e in enumerate(zu):
            if fortschritt and i % 200 == 0:
                fortschritt(i, len(zu))
            wneu = e.get("werkstoff_neu")
            if wneu and wneu["werkstoff_id"] not in werkstoffe:
                lauf.neu("werkstoffe", {kk: v for kk, v in wneu.items() if v is not None})
                werkstoffe.add(wneu["werkstoff_id"])
                erg["werkstoffe"] += 1
            pv = e.get("profil_neu")
            if pv and pv["profil_id"] not in profile_:
                lauf.neu("profile", {kk: v for kk, v in dict(profil_id=pv["profil_id"], form=pv["form"], a=pv["a"],
                                                             b=pv.get("b"), wand=pv["wand"],
                                                             bemerkung="aus ERP-Materialimport").items()
                                     if v is not None})
                profile_.add(pv["profil_id"])
                erg["profile"] += 1
            pid, wid, ober = e["profil_id"], e["werkstoff_id"], e["oberflaeche"] or ""
            # Materialstamm
            sz = stamm.get((pid, wid, ober))
            werte = {f: e[f] for f in ("materialnr", "bezeichnung", "handelsname") if e.get(f)}
            if e.get("lieferant"):
                werte["lieferant"] = e["lieferant"]
            if sz is None:
                w = dict(werte, profil_id=pid, werkstoff_id=wid, oberflaeche=ober or None, aktiv="ja", angelegt=heute,
                         geaendert=heute, quelle=f"ERP-Import {heute}")
                stamm[(pid, wid, ober)] = dict(w, id=lauf.neu("materialstamm", w))
                erg["neu"] += 1
            elif lauf.aendern("materialstamm", sz, dict(werte, geaendert=heute)):
                erg["aktualisiert"] += 1 if e["gruppe"] == AKTUALISIERT else 0
            if ober:            # Preise gelten für Rohware; Oberfläche ist ein Aufpreis
                continue
            # aktiver Preis (nie unbemerkt den Preis eines anderen Lieferanten oder einen neueren ersetzen)
            alt = preise.get((pid, wid))
            pw = dict(basis=e["basis"], preis=e["preis"], gueltig_ab=e["gueltig_ab"])
            if e.get("lieferant"):
                pw["lieferant"] = e["lieferant"]
            if e["basis"] == "€/Stange" or (e.get("laenge") and alt is None):
                pw["lieferlaenge"] = e["laenge"]
            if alt is None:
                w = dict(pw, profil_id=pid, werkstoff_id=wid)
                preise[(pid, wid)] = dict(w, id=lauf.neu("preise", w))
                erg["preise"] += 1
            elif e.get("lieferant_konflikt") and e["zeile"] not in aktiv_ersetzen:
                pass
            elif lauf.aendern("preise", alt, pw):
                erg["preise"] += 1
            # Lieferantenpreis
            if e.get("lieferant"):
                lg = e.get("laenge")
                lz = lief.get((pid, wid, e["lieferant"], lg or None))
                lw = dict(basis=e["basis"], preis=e["preis"], gueltig_ab=e["gueltig_ab"])
                if e.get("gueltig_bis"):
                    lw["gueltig_bis"] = e["gueltig_bis"]
                if e.get("bestellnr") or e.get("materialnr"):
                    lw["artikelnr"] = e.get("bestellnr") or e["materialnr"]
                if lz is not None and _aelter(e.get("gueltig_ab"), lz.get("gueltig_ab")):
                    pass        # älteres Angebot dieses Lieferanten: das neuere bleibt (kein veralteter Preis)
                elif lz is None:
                    w = dict(lw, profil_id=pid, werkstoff_id=wid, lieferant=e["lieferant"], laenge=lg)
                    lief[(pid, wid, e["lieferant"], lg or None)] = dict(w, id=lauf.neu(mp.LIEFERANTEN_TABELLE, w))
                    if e.get("lieferant_konflikt"):
                        erg["preise"] += 1
                elif lauf.aendern(mp.LIEFERANTEN_TABELLE, lz, lw) and e.get("lieferant_konflikt"):
                    erg["preise"] += 1
            if e.get("materialnr"):     # Einkäufe (erp_preise) mit derselben Artikelnummer zählen für dieses Material
                try:
                    erp_preise.zuordnung_merken(db, erp_preise.schluessel(e["materialnr"], e["bezeichnung"]),
                                                e["materialnr"], e["bezeichnung"], pid, wid, ober)
                except Exception:       # noqa: BLE001
                    from . import protokoll
                    protokoll.warnung("Materialimport: EK-Zuordnung nicht gemerkt")
        lauf.flush()
    except Exception as ex:     # noqa: BLE001  (alles zurücknehmen, dann melden)
        lauf.flush()
        rueckgaengig(db, import_id, status="abgebrochen, zurückgenommen")
        raise ImportFehler(f"Import abgebrochen und vollständig zurückgenommen: {ex}") from ex
    csv_import.lauf_abschliessen(db, lauf, erg["neu"], erg["aktualisiert"], erg["preise"],
                                 protokoll=dict(profile=erg["profile"], werkstoffe=erg["werkstoffe"],
                                                sicherung=str(sich or "")))
    from . import ki_protokoll
    ki_protokoll.schreiben(db, "Materialprüfung", "ERP-Materialimport",
                           ergebnis=f"{erg['neu']} neu, {erg['preise']} Preise, {erg['profile']} Profile, "
                                    f"{erg['werkstoffe']} Werkstoffe", quellen=[str(datei)])
    return erg


def laeufe(db):
    """Importhistorie (alle Importarten), neueste zuerst: [dict(id, zeit, datei, importprofil, benutzer, zeilen, neu,
    aktualisiert, preise, unveraendert, doppelt, fehler, offen, status, art, lieferant)]."""
    return csv_import.laeufe(db)


def letzter_lauf(db):
    try:
        r = db.con.execute("SELECT * FROM material_importe WHERE status='übernommen' ORDER BY id DESC "
                           "LIMIT 1").fetchone()
    except Exception:           # noqa: BLE001  (Datei ohne Importtabellen)
        return None
    return dict(r) if r else None


posten_des_laufs = csv_import.posten_des_laufs


def rueckgaengig(db, import_id, status="rückgängig gemacht"):
    """Einen Importlauf zurücknehmen (jede Importart: EK-Einkäufe und Kunden mit ihren eigenen Posten). Ergebnis:
    (Anzahl zurückgenommen, [Meldungen])."""
    r = db.con.execute("SELECT art FROM material_importe WHERE id=?", (import_id,)).fetchone()
    art = (r[0] if r else None) or csv_import.ART_MATERIAL
    if art == csv_import.ART_EK:
        return erp_preise.rueckgaengig(db, import_id, status)
    if art == csv_import.ART_KUNDEN:
        from . import kunden_csv
        return kunden_csv.rueckgaengig(db, import_id, status)
    return csv_import.rueckgaengig(db, import_id, status)


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
