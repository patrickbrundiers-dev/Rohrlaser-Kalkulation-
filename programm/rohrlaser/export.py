"""CSV-Export eines Angebots im Format von Patrick (23.10.2026): Angebotskopf.csv (eine Zeile je Angebot) und
Angebotspositionen.csv (eine Zeile je Position), einzeln oder zusammen als ZIP.

Format: Semikolon, UTF-8 mit BOM, Zeilenende CRLF, Dezimalpunkt ohne Tausendertrennzeichen (wie die Beispieldatei, Patrick 23.10.2026), Beträge mit 2 Stellen,
Zeiten HH:MM:SS, Datum TT.MM.JJJJ. Texte mit Semikolon, Anführungszeichen oder Zeilenumbruch stehen in
Anführungszeichen (innere Anführungszeichen verdoppelt). Werte, die es im Programm nicht gibt, bleiben leer.
Der Export liest nur: alle Werte kommen aus der Kalkulation des Angebots (rechnen.kalkulation), nichts wird
gespeichert. Die Zuordnung je Spalte steht in den Funktionen kopf_zeile und positions_zeilen.
"""
import csv
import datetime
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path

from . import fracht_angebot, rechnen
from .angebot import ist_zukaufteil, lieferzeit_text
from .ausgabe import angebot as angebot_inhalt, angebotstext, aufrunden, kaufm_runden, profiltext
from .optimierung import umfang
from .stammdaten import zahl_als_text

# Spalten in der vorgegebenen Reihenfolge (nicht umbenennen: das Zielprogramm liest die Titel)
KOPF_SPALTEN = (
    "Erstellungsdatum", "Datum Kunde:", "Kunden Nr.", "Kunde:", "Nachname", "Versandzone:", "Kundenanfrage:",
    "Kommentar", "Versandkosten", "Feste Versandkosten", "Versand inkl.", "Lieferzeit", "%Kunde Mat", "%Kunde Arb.",
    "%Fremdarb.", "Bearbeitungszeit", "Gesamtzeit", "Restblech min.€", "Preis", "Kundenkurzbez.", "Position",
    "Anrede", "%Aufschlag", "Rabatt(Euros)", "Aufrunden", "Angebot erstellt von")
POSITION_SPALTEN = (
    "Angebot", "Art", "ArtikelNr.", "Pos.", "Pos.Nr.", "Bestellt", "Anzahl Tafeln", "Format", "Arb.",
    "Anz. Baugruppe", "Menge", "Stückpr.", "Preis", "Preis geändert", "Werkstoff", "Werkstofftyp", "Dicke", "Fläche",
    "Gew.", "Umfang", "Maschine", "Schneiden", "Date", "L.", "B.", "Artikeltext", "Bearbeitungszeit", "Gesamtzeit",
    "zum Schneiden", "Gesamt HK(€)", "Marge Netto%", "Kommentar", "Preis/Kg", "Einsatzgewicht", "HK()",
    "Marge Netto()", "Gesamt Einkauf()", "Gesamt Einkauf(Kg)", "Verschnitt", "Liste der Arbeitsgänge")
assert len(KOPF_SPALTEN) == 26 and len(POSITION_SPALTEN) == 40
KOPF_DATEI, POSITION_DATEI = "Angebotskopf.csv", "Angebotspositionen.csv"
# Schweißbaugruppen (Verbesserung P3): eigene Datei im ZIP, nur wenn das Angebot Baugruppen hat; Kopf- und
# Positionsdatei bleiben unverändert (festes Format)
BAUGRUPPE_DATEI = "Schweissbaugruppen.csv"
BAUGRUPPE_SPALTEN = ("Pos", "Artikel", "Bezeichnung", "Anzahl", "Schweisszeit_min_je_BG", "Nahtlaenge_m_je_BG",
                     "Zeit_min_je_BG", "Fertigung_EUR_je_BG", "Fremdleistung_EUR_je_BG", "Einmalkosten_EUR_je_BG",
                     "Herstellkosten_EUR_je_BG", "Preis_EUR_je_BG", "Nahtgruppen", "Arbeitsgaenge", "Richtwerte")
TRENNER = ";"
DEZIMAL = "."             # Dezimaltrennzeichen der Zahlen


# ------------------------------------------------------------------ Formate
def _zahl(w):
    if isinstance(w, bool) or w is None:
        return None
    if isinstance(w, (int, float)):
        return float(w)
    try:            # als Text gespeicherte Zahl ('12,5' oder '12.5')
        return float(str(w).strip().replace(",", "."))
    except ValueError:
        return None


def zahl(w, stellen=None):
    """Zahl mit DEZIMAL, ohne Tausendertrennzeichen; stellen=None: so viele Stellen wie nötig (2958, 1.5)."""
    x = _zahl(w)
    if x is None:
        return ""
    if stellen is None:
        x = kaufm_runden(x, 6)
        t = zahl_als_text(int(x) if x.is_integer() else x, None, tausender=False)
    else:
        t = zahl_als_text(kaufm_runden(x, stellen), stellen, tausender=False)
    return t.replace(",", DEZIMAL)


def geld(w):
    return zahl(w, 2)


def zeit(sekunden):
    """'HH:MM:SS' (Stunden auch über 24), auf ganze Sekunden gerundet; leer ohne gültige Zeit."""
    x = _zahl(sekunden)
    if x is None or x < 0 or x != x:
        return ""
    s = int(kaufm_runden(x, 0))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def datum(w):
    """ISO-Datum oder Zeitstempel -> 'TT.MM.JJJJ'; leer, wenn es kein Datum ist."""
    try:
        return datetime.date.fromisoformat(str(w or "")[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def _text(w):
    return "" if w is None else str(w).strip()


def _einzeilig(w):
    """Mehrzeiligen Text (Angebotstext) mit ', ' in eine Zeile bringen."""
    return ", ".join(t.strip() for t in _text(w).splitlines() if t.strip())


# ------------------------------------------------------------------ Inhalt
def _werte(z, n):
    return _zahl((z or {}).get(n)) or 0.0


def _gesamtzeit_s(p, z, summen, teile_abm, profil):
    """Zeit einer Position [s]: Laserzeit × Menge + Anteil Rüsten Maschine und Stangenwechsel (nach Teilen des
    Angebots) + Rüsten je Abmessung (nach Teilen der Abmessung) + Programmierzeit der Position."""
    c = _werte(z, "stueck")
    if not c:
        return 0.0
    t = _werte(z, "laser_netto") * c
    teile = _zahl(summen.get("teile")) or 0
    if teile:
        t += (_werte(summen, "ruestzeit") * 60 + _werte(summen, "stangenwechsel_s")) * c / teile
    n_abm = teile_abm.get(p.get("profil_id")) or 0
    if n_abm:
        abm = _werte(summen, "ruestzeit_abmessung")
        if (profil or {}).get("form") in rechnen.SONDERFORMEN:
            abm += _werte(summen, "ruestzeit_sonder")
        t += abm * 60 * c / n_abm
    t += _werte(z, "prog_min") * 60
    return t


def _stueckpreis(z):
    """Stückpreis wie im Angebots-PDF (ausgabe.angebot): kaufmännisch gerundet, beim Mindestpreis aufgerundet."""
    if _werte(z, "mindestpreis_teil") > 0:
        return aufrunden(_werte(z, "preis_teil"))
    return kaufm_runden(_werte(z, "preis_teil"), 2)


def _arbeitsgaenge(p, z, k):
    """'Profile [Rechteckrohr 120x60x3], Gewinde [4xM6], Zusatzarbeit [Entgraten 1 Stück]': je Arbeitsgang
    'Art [Angabe]', durch ', ' getrennt."""
    if ist_zukaufteil(p):
        out = [f"Zukaufteil [{_einzeilig(p.get('bezeichnung') or p.get('artikel'))}]"]
    else:
        out = [f"Profile [{profiltext(p.get('profil_id'), k).replace(' x ', 'x')}]"]
        ob = rechnen.oberflaeche_von(p)
        if ob:
            out.append(f"Oberfläche [{ob}]")
        if _text(p.get("gewinde")):
            out.append(f"Gewinde [{_einzeilig(p['gewinde']).replace(', ', '; ')}]")
        if (_zahl(p.get("gravur")) or 0) > 0:
            out.append("Gravur")
    for e in (z or {}).get("zusatzarbeiten") or ():
        out.append(f"Zusatzarbeit [{e['name']} {zahl(e.get('menge'))} {e.get('einheit') or ''}]".replace(" ]", "]"))
    return ", ".join(out)


def kopf_zeile(kopf, kalk_zeilen, summen, einst, positionen, k, kunde=None, ersteller=None, pos_zeilen=None):
    """Werte des Angebotskopfs (dict Spalte -> Text). kunde: Kundendatensatz, ersteller: Name des Bearbeiters,
    pos_zeilen: positions_zeilen (Bearbeitungszeit und Gesamtzeit = Summe der Positionen)."""
    kunde = kunde or {}
    netto = angebot_inhalt(kopf, positionen, kalk_zeilen, k, einst)["netto"]
    fd = fracht_angebot.daten(kopf) or {}
    m = fracht_angebot.modus(kopf)
    lz = lieferzeit_kurz(kopf)
    pz = pos_zeilen or []
    bearb = sum(x["_bearbeitung_s"] for x in pz if x["_bearbeitung_s"] is not None)
    gesamt = sum(x["_gesamt_s"] for x in pz)
    return {
        "Erstellungsdatum": datum(kopf.get("angelegt")),
        "Datum Kunde:": datum(kopf.get("datum")),
        "Kunden Nr.": _text(kopf.get("kundennr")),
        "Kunde:": _text(kopf.get("kunde")) or _text(kunde.get("name")),
        "Nachname": _text(kunde.get("ansprechpartner")),
        "Versandzone:": _text(fd.get("zone")) or _text(kunde.get("lieferbedingung")),
        "Kundenanfrage:": _text(kopf.get("kundenreferenz")),
        "Kommentar": _text(kopf.get("bemerkung")),
        "Versandkosten": geld(summen.get("fracht")),
        "Feste Versandkosten": "True" if m == fracht_angebot.MANUELL and _werte(summen, "fracht") > 0 else "False",
        "Versand inkl.": "True" if m == fracht_angebot.ENTHALTEN else "False",
        "Lieferzeit": lz,
        "%Kunde Mat": zahl(100 * _werte(einst, "zuschlag_material")),
        "%Kunde Arb.": zahl(100 * _werte(einst, "zuschlag_fertigung")),
        "%Fremdarb.": zahl(100 * _werte(einst, "zuschlag_fremdleistung")),
        "Bearbeitungszeit": zeit(bearb) if pz else "",
        "Gesamtzeit": zeit(gesamt) if pz else "",
        # Mindestauftragswert (Einstellungen; 0, wenn er im Angebot ausgeschaltet ist)
        "Restblech min.€": geld(einst.get("mindestpreis")) if _werte(einst, "mindestpreis") > 0 else "",
        "Preis": geld(netto),
        "Kundenkurzbez.": "",
        "Position": "",
        "Anrede": "",
        "%Aufschlag": zahl(100 * _werte(einst, "gewinn")),
        "Rabatt(Euros)": "",
        "Aufrunden": "+" + zahl(0.01, 2),        # Preise werden kaufmännisch auf 1 Cent gerundet
        "Angebot erstellt von": _text(ersteller) or _text(kopf.get("bearbeiter")),
    }


def lieferzeit_kurz(kopf):
    """Lieferzeit kurz, z. B. 'ca. 2 Wochen nach Auftragseingang' (ohne 'Lieferzeit:' und Schlusspunkt)."""
    t = lieferzeit_text(kopf)
    return re.sub(r"^Lieferzeit:\s*", "", t).rstrip(".")


def positions_zeilen(kopf, positionen, ergebnis, kalk_zeilen, summen, k, tabellen):
    """Werte je Position (Liste von dict Spalte -> Text, dazu _bearbeitung_s und _gesamt_s für den Kopf), in der
    Reihenfolge der Positionen. Positionen ohne Kalkulation (ohne Profil) fehlen."""
    nummer = _text(kopf.get("nummer"))
    # Stangengewicht je Stangengruppe (für Einsatzgewicht und Verschnitt)
    gruppen_kg = {}
    if ergebnis and ergebnis.get("stangen"):
        for s, x in zip(ergebnis["stangen"], rechnen.stangen_werte(ergebnis, kopf, positionen, k, tabellen)):
            if x.get("gewicht") is not None:
                g = rechnen.gruppe_der_stange(s)
                gruppen_kg[g] = gruppen_kg.get(g, 0.0) + x["gewicht"]
    teile_abm = {}
    for p, z in zip(positionen, kalk_zeilen):
        if z and not ist_zukaufteil(p):
            teile_abm[p.get("profil_id")] = teile_abm.get(p.get("profil_id"), 0) + _werte(z, "stueck")
    datum_angebot = datum(kopf.get("datum"))
    out = []
    for p, z in zip(positionen, kalk_zeilen):
        if not z:
            continue
        zk = ist_zukaufteil(p)
        pr = None if zk else k.profile.get(p.get("profil_id"))
        w = rechnen.position_werte(p, kopf, k, tabellen)
        c = _werte(z, "stueck")
        stueckpr = _stueckpreis(z)
        preis = kaufm_runden(stueckpr * c, 2)
        hk_teil, hk = _werte(z, "herstell_teil"), _werte(z, "herstell_position")
        einkauf = _werte(z, "material_position") + _werte(z, "zukauf_einstand_teil") * c
        kg_teil = w.get("gewicht")
        einsatz = None
        if not zk and c:
            g = gruppen_kg.get(rechnen.gruppe_von(p, kopf))
            if g is not None:
                einsatz = g * _werte(z, "anteil") / c
        einsatz_ges = einsatz * c if einsatz is not None else None
        verschnitt = (f"{zahl(100 * (einsatz - kg_teil) / einsatz, 0)}%"
                      if einsatz and kg_teil is not None else "")
        flaeche = None          # Mantelfläche außen [m²] = Umfang des Querschnitts × Teilelänge
        if pr and _zahl(p.get("laenge")):
            u = umfang(pr.get("form"), _zahl(pr.get("a")) or 0, _zahl(pr.get("b")), _zahl(pr.get("wand")),
                       _zahl(pr.get("flaeche")), p.get("profil_id"), _zahl(pr.get("r_aussen")))
            flaeche = u / 1000 * _zahl(p["laenge"]) / 1000 if u else None
        werkstoff = k.werkstoffe.get(p.get("werkstoff_id")) or {}
        bearb = None if zk else _zahl(z.get("laser_netto"))
        gesamt_s = 0.0 if zk else _gesamtzeit_s(p, z, summen, teile_abm, pr)
        hand = not zk and (_text(p.get("zeit_manuell")) != "" or (_zahl(p.get("preis_m")) or 0) > 0)
        je = _zahl(p.get("je_satz"))
        zeile = {
            "Angebot": nummer,
            "Art": str(len(out) + 1),
            "ArtikelNr.": _text(p.get("artikel")),
            "Pos.": zahl(p.get("pos")),
            "Pos.Nr.": "",
            "Bestellt": "0",
            "Anzahl Tafeln": "",
            "Format": "" if zk else zahl(w.get("stange")),
            "Arb.": "",
            "Anz. Baugruppe": zahl(je) if _text(p.get("satz")) and je else "1",
            "Menge": zahl(c),
            "Stückpr.": geld(stueckpr),
            "Preis": geld(preis),
            "Preis geändert": "1" if hand else "0",
            "Werkstoff": "" if zk else _text(werkstoff.get("kategorie")),
            "Werkstofftyp": "" if zk else (_text(werkstoff.get("angebotstext")) or _text(p.get("werkstoff_id"))),
            "Dicke": "" if zk or not pr else zahl(pr.get("wand")),
            "Fläche": zahl(flaeche, 3),
            "Gew.": zahl(kg_teil, 3),
            "Umfang": "" if zk else zahl(p.get("schneidweg"), 0),
            "Maschine": "" if zk else _text(kopf.get("maschine")),
            "Schneiden": "" if zk else _text(z.get("gas")),
            "Date": datum_angebot,
            "L.": "" if zk else zahl(p.get("laenge")),
            "B.": "",
            "Artikeltext": _einzeilig(angebotstext(p, k, ",", z.get("zusatzarbeiten") or ())),
            "Bearbeitungszeit": zeit(bearb),
            "Gesamtzeit": "" if zk else zeit(gesamt_s),
            "zum Schneiden": "0",
            "Gesamt HK(€)": geld(hk),
            "Marge Netto%": f"{zahl(100 * (preis - hk) / hk, 1)} %" if hk > 0 else "",
            "Kommentar": _text(z.get("hinweis")),
            "Preis/Kg": geld(einkauf / einsatz_ges) if einsatz_ges and _werte(z, "material_position") > 0 else "",
            "Einsatzgewicht": zahl(einsatz, 3),
            "HK()": geld(hk_teil),
            "Marge Netto()": geld(preis - hk),
            "Gesamt Einkauf()": geld(einkauf),
            "Gesamt Einkauf(Kg)": zahl(einsatz_ges, 2),
            "Verschnitt": verschnitt,
            "Liste der Arbeitsgänge": _arbeitsgaenge(p, z, k),
            "_bearbeitung_s": bearb,
            "_gesamt_s": gesamt_s,
        }
        out.append(zeile)
    return out


def daten(kopf, positionen, ergebnis, kalk_zeilen, summen, k, tabellen, einst, kunde=None, ersteller=None):
    """(Kopfzeile, Positionszeilen) als Listen von Texten in der Spaltenreihenfolge."""
    pz = positions_zeilen(kopf, positionen, ergebnis, kalk_zeilen, summen, k, tabellen)
    kz = kopf_zeile(kopf, kalk_zeilen, summen, einst, positionen, k, kunde, ersteller, pz)
    return [kz[s] for s in KOPF_SPALTEN], [[z[s] for s in POSITION_SPALTEN] for z in pz]


def baugruppen_zeilen(positionen, kalk_zeilen):
    """Eine Zeile je Schweißbaugruppe (Texte in BAUGRUPPE_SPALTEN): Zeiten, Nahtlänge und Kosten je Baugruppe aus der
    Kalkulation. Leer ohne Baugruppe."""
    out = []
    for p, z in zip(positionen, kalk_zeilen):
        if not z or not z.get("baugruppe"):
            continue
        bz = z.get("bg_zeilen") or ()
        out.append([zahl(p.get("pos"), 0), _text(p.get("artikel")), _einzeilig(p.get("bezeichnung")),
                    zahl(p.get("stueck"), 0), zahl(z.get("bg_schweiss_min"), 2),
                    zahl(sum((z.get("bg_naht_m") or {}).values()), 3), zahl(z.get("bg_zeit_min"), 2),
                    geld(z.get("bg_eigen_teil")), geld(z.get("bg_fremd_teil")), geld(z.get("bg_einmal_teil")),
                    geld(z.get("herstell_teil")), geld(z.get("preis_teil")),
                    str(sum(1 for x in bz if x["art"] == "Naht")), str(sum(1 for x in bz if x["art"] != "Naht")),
                    "ja" if any((x.get("werte") or {}).get("richtwert") for x in bz) else "nein"])
    return out


# ------------------------------------------------------------------ Dateien
def csv_bytes(spalten, zeilen):
    """CSV als Bytes: UTF-8 mit BOM, Semikolon, CRLF, Anführungszeichen nur wo nötig."""
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, delimiter=TRENNER, quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(spalten)
    for z in zeilen:
        if len(z) != len(spalten):
            raise ValueError(f"Zeile mit {len(z)} statt {len(spalten)} Spalten")
        w.writerow(z)
    return puffer.getvalue().encode("utf-8-sig")


def _sicher_schreiben(pfad, inhalt):
    """Erst in eine Hilfsdatei daneben, dann ersetzen: ein Fehler lässt keine halbe Datei zurück."""
    pfad = Path(pfad)
    fd, tmp = tempfile.mkstemp(prefix=".export_", dir=str(pfad.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def kopf_csv(pfad, kopfzeile):
    _sicher_schreiben(pfad, csv_bytes(KOPF_SPALTEN, [kopfzeile]))


def positionen_csv(pfad, pos_zeilen):
    _sicher_schreiben(pfad, csv_bytes(POSITION_SPALTEN, pos_zeilen))


def zip_schreiben(pfad, kopfzeile, pos_zeilen, bg_zeilen=None):
    """ZIP mit Angebotskopf.csv und Angebotspositionen.csv, mit Baugruppen dazu Schweissbaugruppen.csv."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(KOPF_DATEI, csv_bytes(KOPF_SPALTEN, [kopfzeile]))
        z.writestr(POSITION_DATEI, csv_bytes(POSITION_SPALTEN, pos_zeilen))
        if bg_zeilen:
            z.writestr(BAUGRUPPE_DATEI, csv_bytes(BAUGRUPPE_SPALTEN, bg_zeilen))
    _sicher_schreiben(pfad, puffer.getvalue())


def zip_name(kopf):
    """'Angebot_2613000461.zip' (unzulässige Zeichen der Nummer als _)."""
    nr = re.sub(r'[\\/:*?"<>|\x00-\x1f\s]', "_", _text(kopf.get("nummer"))) or "ohne_Nummer"
    return f"Angebot_{nr}.zip"
