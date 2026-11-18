"""Adapter je Abrufweg für die Online-Preise (Entwicklungsauftrag Patrick 18.11.2026). Ohne Qt.

Jeder Adapter liefert Preisstände als dicts im Format von onlinepreise.PREISE (lieferant, artikelnr, bezeichnung,
werkstoff, form/a/b/wand, laenge, basis, preis, preisart, brutto, staffel, mindestmenge, mengeneinheit, ve,
verfuegbarkeit, lieferzeit, gueltig_bis …) und speichert nichts selbst; gespeichert wird über onlinepreise.eintragen.

- PreislistenAdapter: CSV oder Excel (.xlsx) aus dem Preislisten-Ordner des Lieferanten oder einer gewählten Datei.
  Spalten erkennt das Programm am Kopf (Artikel, Bezeichnung, Güte, Länge, Preis, Einheit …); eine abweichende
  Zuordnung je Lieferant steht in online_lieferanten.spalten (JSON {Feld: Spaltenkopf}). Jede Datei wird nur einmal
  gelesen (Prüfsumme, auch über alle Plätze).
- OciAdapter: OCI-Punchout (SAP Open Catalog Interface 4.0). Interaktiv öffnet der Browser über eine kleine lokale
  Seite (nur 127.0.0.1) den Shop mit dem OCI-Zugang; „Warenkorb übertragen“ schickt die Artikel per Formular an
  die lokale HOOK_URL zurück. Mit Hintergrundsuche (FUNCTION=BACKGROUND_SEARCH, nur wenn der Lieferant sie
  freigeschaltet hat) kommt das Ergebnis ohne Bedienung als OCI-Formular in der Antwort.
- Shop-Suche: öffnet die Suche im Browser (Suchadresse mit {suche}, sonst die Startseite; Suchtext in der
  Zwischenablage); den Preis trägt der Anwender mit Quelle „Shop (von Hand)“ ein.

Keine Anmeldung mit dem normalen Shop-Login und kein Auslesen von Shopseiten (Nutzungsbedingungen)."""
import html
import http.server
import re
import secrets
import socketserver
import threading
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from . import onlinepreise as op

ZEITLIMIT = 20          # s je Netzanfrage
DATEIEN = ("*.csv", "*.CSV", "*.xlsx", "*.XLSX", "*.txt", "*.TXT")

# --------------------------------------------------------------------------------------------- Preislisten
# Feld -> Spaltenköpfe (Vergleich ohne Groß-/Kleinschreibung und Sonderzeichen; erster Treffer gilt)
KOEPFE = {
    "artikelnr": ("artikelnummer", "artikelnr", "artnr", "artikel", "materialnummer", "materialnr", "sachnummer",
                  "itemno", "itemnumber", "articleno", "productid", "sku"),
    "bezeichnung": ("bezeichnung", "artikelbezeichnung", "beschreibung", "kurztext", "produkt", "produktbezeichnung",
                    "description", "text", "materialkurztext"),
    "werkstoff": ("werkstoff", "guete", "güte", "stahlguete", "stahlgüte", "qualitaet", "qualität", "materialqualitaet",
                  "materialqualität", "stahlsorte", "sorte", "grade"),
    "form": ("profilart", "profil", "form", "produktgruppe", "warengruppe"),
    "abmessung": ("abmessung", "abmessungen", "dimension", "masse", "maße", "groesse", "größe", "size"),
    "a": ("aussendurchmesser", "außendurchmesser", "durchmesser", "breite", "hoehea", "a", "d", "od"),
    "b": ("hoehe", "höhe", "b", "h"),
    "wand": ("wandstaerke", "wandstärke", "wand", "s", "t", "dicke", "staerke", "stärke"),
    "laenge": ("laenge", "länge", "lagerlaenge", "lagerlänge", "stangenlaenge", "stangenlänge", "length", "lg"),
    "preis": ("preis", "nettopreis", "kundenpreis", "listenpreis", "ekpreis", "ek", "einkaufspreis", "price",
              "preisnetto", "preiseur", "netto"),
    "einheit": ("einheit", "preiseinheit", "pe", "me", "mengeneinheit", "basis", "preisbasis", "unit", "per", "je"),
    "waehrung": ("waehrung", "währung", "currency", "wkz"),
    "staffel": ("staffel", "staffelpreise", "mengenstaffel"),
    "mindestmenge": ("mindestmenge", "mindestabnahme", "moq", "minmenge"),
    "ve": ("ve", "verpackungseinheit", "bund", "bundmenge", "packeinheit"),
    "verfuegbarkeit": ("verfuegbarkeit", "verfügbarkeit", "bestand", "lager", "verfuegbar", "verfügbar", "stock"),
    "lieferzeit": ("lieferzeit", "lieferzeittage", "leadtime", "lz"),
    "gueltig_bis": ("gueltigbis", "gültigbis", "gueltigkeit", "gültigkeit", "validto", "preisgueltigbis"),
    "oberflaeche": ("oberflaeche", "oberfläche", "ausfuehrung", "ausführung", "finish"),
    "hersteller": ("hersteller", "werk", "manufacturer", "marke"),
}
PFLICHT = ("preis",)


def _kopf(t):
    return re.sub(r"[^0-9a-zäöüß]+", "", str(t or "").lower())


def zellen(roh, name):
    """Zellen einer Preisliste [[str]] aus Bytes (CSV/TXT oder XLSX)."""
    from . import stueckliste
    if str(name).lower().endswith(".xlsx"):
        return stueckliste.xlsx_zeilen(roh)
    return stueckliste.csv_zeilen(roh)


def kopfzeile(zeilen_):
    """Index der Kopfzeile: die erste der ersten 15 Zeilen mit einer Preis-Spalte und mindestens 2 bekannten Köpfen."""
    bekannt = {k for v in KOEPFE.values() for k in v}
    for i, z in enumerate(zeilen_[:15]):
        koepfe = [_kopf(c) for c in z]
        if sum(1 for c in koepfe if c in bekannt) >= 2 and any(c in KOEPFE["preis"] or c.startswith("preis")
                                                                  for c in koepfe):
            return i
    return None


def spalten_vorschlag(kopf, eigene=None):
    """{Feld: Spaltenindex} aus der Kopfzeile; eigene {Feld: Spaltenkopf} geht vor."""
    k = [_kopf(c) for c in kopf]
    out = {}
    for feld, titel in (eigene or {}).items():
        if _kopf(titel) in k:
            out[feld] = k.index(_kopf(titel))
    for feld, namen in KOEPFE.items():
        if feld in out:
            continue
        for n in namen:
            if n in k and k.index(n) not in out.values():
                out[feld] = k.index(n)
                break
    if "preis" not in out:              # „Preis € / m“, „Preis je 100 kg“ …
        for i, c in enumerate(k):
            if c.startswith("preis") and i not in out.values():
                out["preis"] = i
                break
    return out


def _einheit_aus_kopf(titel):
    """'Preis €/m', 'Preis je 100 kg', 'EUR/t' -> Einheit-Text oder None."""
    m = re.search(r"(?:€|eur)\s*/\s*(\d*\s*[a-zäöü]+)|je\s+(\d*\s*[a-zäöü]+)|pro\s+(\d*\s*[a-zäöü]+)",
                  str(titel or "").lower())
    if not m:
        return None
    return next(g for g in m.groups() if g)


def preisliste_lesen(roh, name, lief=None):
    """Preisstände aus einer Preisliste: (eintraege, meldungen). Zeilen ohne lesbaren Preis oder ohne erkennbare
    Preisbasis werden nicht übernommen, sondern gemeldet (nie geraten)."""
    lief = lief or {}
    meldungen = []
    zeilen_ = zellen(roh, name)
    if not zeilen_:
        return [], [f"{name}: nicht lesbar oder leer"]
    i = kopfzeile(zeilen_)
    if i is None:
        return [], [f"{name}: keine Kopfzeile mit Preis-Spalte gefunden"]
    kopf = zeilen_[i]
    sp = spalten_vorschlag(kopf, op.spalten_laden(lief))
    if "preis" not in sp:
        return [], [f"{name}: keine Preis-Spalte"]
    einheit_kopf = _einheit_aus_kopf(kopf[sp["preis"]])
    brutto_kopf = "brutto" in str(kopf[sp["preis"]]).lower()
    out = []
    for nr, z in enumerate(zeilen_[i + 1:], i + 2):
        if not any(str(c).strip() for c in z):
            continue

        def wert(feld):
            j = sp.get(feld)
            return str(z[j]).strip() if j is not None and j < len(z) else ""
        preis = op.zahl(wert("preis"))
        if preis is None or preis <= 0:
            meldungen.append(f"Zeile {nr}: kein Preis")
            continue
        einheit = wert("einheit") or einheit_kopf
        b = op.basis_aus_einheit(einheit) if einheit else None
        if b is None:
            meldungen.append(f"Zeile {nr}: Preiseinheit „{einheit or 'leer'}“ unbekannt")
            continue
        basis, faktor = b
        bezeichnung = wert("bezeichnung") or wert("abmessung")
        e = dict(artikelnr=wert("artikelnr"), bezeichnung=" ".join(x for x in (bezeichnung, wert("abmessung")
                                                                               if wert("bezeichnung") else "") if x),
                 werkstoff=wert("werkstoff"), basis=basis, preis=round(preis * faktor, 6),
                 preisart=lief.get("preisart") or "Kundenpreis",
                 brutto="ja" if brutto_kopf or op.ja(lief.get("brutto")) else "nein",
                 waehrung=wert("waehrung") or "EUR", staffel=wert("staffel"), ve=wert("ve"),
                 verfuegbarkeit=wert("verfuegbarkeit"), lieferzeit=op.zahl(wert("lieferzeit")),
                 gueltig_bis=_iso(wert("gueltig_bis")), oberflaeche=wert("oberflaeche"), hersteller=wert("hersteller"))
        if e["waehrung"].upper() not in ("EUR", "€", "EURO"):
            meldungen.append(f"Zeile {nr}: Währung {e['waehrung']} (nur EUR wird verglichen)")
            continue
        for feld in ("a", "b", "wand", "laenge"):
            w = op.zahl(wert(feld))
            if w:
                e[feld] = w * 1000 if feld == "laenge" and w < 30 else w     # 6 (m) -> 6000 mm
        if wert("form"):
            f = op.zerlegen(wert("form"))["form"]
            if f:
                e["form"] = f
        if wert("mindestmenge"):
            e["mindestmenge"] = op.zahl(wert("mindestmenge"))
            e["mengeneinheit"] = {"€/m": "m", "€/kg": "kg"}.get(basis, "Stange")
        if not e["artikelnr"] and not e["bezeichnung"]:
            meldungen.append(f"Zeile {nr}: weder Artikelnummer noch Bezeichnung")
            continue
        if e.get("laenge") is None:
            lg = op.zerlegen(e["bezeichnung"])["laenge"]
            if lg:
                e["laenge"] = lg
        out.append({k: v for k, v in e.items() if v not in (None, "")})
    return out, meldungen


def _iso(t):
    d = op._datum(t)
    return d.isoformat() if d else (t or None)


def preislisten_im_ordner(ordner):
    """Preislisten-Dateien im Ordner (neueste zuletzt)."""
    p = Path(ordner or "")
    if not str(ordner or "").strip() or not p.is_dir():
        return []
    dateien = {f for muster in DATEIEN for f in p.glob(muster) if f.is_file()}
    return sorted(dateien, key=lambda f: f.stat().st_mtime)


# --------------------------------------------------------------------------------------------- OCI
OCI_EINHEIT = {"MTR": "m", "M": "m", "KGM": "kg", "KG": "kg", "TNE": "t", "T": "t", "PCE": "St", "ST": "St",
               "STK": "St", "C62": "St", "EA": "St", "PC": "St"}


class _Formular(HTMLParser):
    """Sammelt <input name=… value=…> (OCI-Rückgabe als HTML-Formular) und das Ziel des Formulars."""

    def __init__(self):
        super().__init__()
        self.felder, self.ziel = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and self.ziel is None:
            self.ziel = a.get("action")
        if tag == "input" and a.get("name"):
            self.felder.append((a["name"], a.get("value") or ""))


def oci_felder_aus_html(text):
    p = _Formular()
    p.feed(str(text or ""))
    return p.felder


def oci_artikel(felder):
    """OCI-Felder [(Name, Wert)] -> Preisstände. NEW_ITEM-PRICE gilt je NEW_ITEM-PRICEUNIT Einheiten NEW_ITEM-UNIT;
    Langtext NEW_ITEM-LONGTEXT_n:132[] wird angehängt. Positionen ohne Preis oder mit unbekannter Einheit fallen weg
    (Meldung)."""
    je = {}
    for name, wert in felder:
        m = re.fullmatch(r"NEW_ITEM-([A-Z_0-9]+)\[(\d+)\]", name, re.I)
        if m:
            je.setdefault(int(m.group(2)), {})[m.group(1).upper()] = html.unescape(wert)
            continue
        m = re.fullmatch(r"NEW_ITEM-LONGTEXT_(\d+):132\[\]", name, re.I)
        if m:
            d = je.setdefault(int(m.group(1)), {})
            d["LONGTEXT"] = (d.get("LONGTEXT", "") + " " + html.unescape(wert)).strip()
    out, meldungen = [], []
    for n in sorted(je):
        d = je[n]
        preis = op.zahl(d.get("PRICE"))
        einheit = OCI_EINHEIT.get(str(d.get("UNIT") or "").upper(), d.get("UNIT"))
        b = op.basis_aus_einheit(einheit)
        if preis is None or preis <= 0 or b is None:
            meldungen.append(f"Position {n}: {d.get('DESCRIPTION') or '?'} ohne Preis oder mit Einheit "
                             f"„{d.get('UNIT') or 'leer'}“")
            continue
        je_einheit = op.zahl(d.get("PRICEUNIT")) or 1
        basis, faktor = b
        if str(d.get("CURRENCY") or "EUR").upper() != "EUR":
            meldungen.append(f"Position {n}: Währung {d.get('CURRENCY')}")
            continue
        text = " ".join(x for x in (d.get("DESCRIPTION"), d.get("LONGTEXT")) if x)
        e = dict(artikelnr=d.get("VENDORMAT") or d.get("EXT_PRODUCT_ID") or "", bezeichnung=text,
                 werkstoff=text, basis=basis, preis=round(preis * faktor / je_einheit, 6), preisart="Kundenpreis",
                 brutto="nein", waehrung="EUR", hersteller=d.get("MANUFACTCODE") or "",
                 lieferzeit=op.zahl(d.get("LEADTIME")))
        lg = op.zerlegen(text)["laenge"]
        if lg:
            e["laenge"] = lg
        out.append({k: v for k, v in e.items() if v not in (None, "")})
    return out, meldungen


def oci_parameter(benutzer, passwort, hook, suche=None, hintergrund=False):
    p = {"USERNAME": benutzer or "", "PASSWORD": passwort or "", "HOOK_URL": hook, "~OkCode": "ADDI",
         "~TARGET": "_top", "~CALLER": "CTLG", "returntarget": "_top"}
    if hintergrund:
        p.update(FUNCTION="BACKGROUND_SEARCH", SEARCHSTRING=suche or "")
    elif suche:
        p.update(FUNCTION="DETAIL", SEARCHSTRING=suche)
    return p


def oci_hintergrund(adresse, benutzer, passwort, suche, oeffnen=None):
    """OCI-Hintergrundsuche: POST an die Einstiegsadresse, Antwort = OCI-Formular. Ergebnis (eintraege, meldungen).
    oeffnen: Ersatz für urllib.request.urlopen (Tests)."""
    if not str(adresse or "").lower().startswith("https://"):
        raise ValueError("OCI-Einstiegsadresse muss mit https:// beginnen")
    daten = urllib.parse.urlencode(oci_parameter(benutzer, passwort, "http://127.0.0.1/", suche, True)).encode()
    req = urllib.request.Request(adresse, data=daten, headers={"User-Agent": "Rohrlaser-Kalkulation OCI"})
    with (oeffnen or urllib.request.urlopen)(req, timeout=ZEITLIMIT) as r:
        text = r.read(5_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    return oci_artikel(oci_felder_aus_html(text))


class OciEmpfang:
    """Kleiner HTTP-Empfänger nur auf 127.0.0.1 für eine OCI-Sitzung. /start?t=… liefert eine Seite, die den Shop
    per POST mit dem OCI-Zugang öffnet (das Passwort steht nie in einer Adresse); /hook?t=… nimmt den Warenkorb an.
    fertig (threading.Event) ist gesetzt, sobald der Warenkorb da ist; ergebnis = (eintraege, meldungen)."""

    def __init__(self, adresse, benutzer, passwort, suche=None):
        self.token = secrets.token_urlsafe(16)
        self.adresse, self.benutzer, self.passwort, self.suche = adresse, benutzer, passwort, suche
        self.fertig, self.ergebnis, self._start_benutzt = threading.Event(), ([], []), False
        empfang = self

        class Hand(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _antwort(self, text, code=200):
                roh = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if u.path == "/start" and q.get("t") == [empfang.token] and not empfang._start_benutzt:
                    empfang._start_benutzt = True           # nur einmal: danach kein Passwort mehr abrufbar
                    self._antwort(empfang.startseite())
                else:
                    self._antwort("<p>Nicht gefunden.</p>", 404)

            def do_POST(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                n = int(self.headers.get("Content-Length") or 0)
                roh = self.rfile.read(min(n, 5_000_000)).decode("utf-8", errors="replace")
                if u.path != "/hook" or q.get("t") != [empfang.token]:
                    self._antwort("<p>Nicht gefunden.</p>", 404)
                    return
                felder = urllib.parse.parse_qsl(roh, keep_blank_values=True)
                empfang.ergebnis = oci_artikel(felder)
                empfang.fertig.set()
                self._antwort("<html><body style='font-family:sans-serif'><h3>Übertragen</h3><p>Die Artikel sind in "
                              "der Rohrlaser-Kalkulation angekommen. Dieses Fenster kann geschlossen werden.</p>"
                              "</body></html>")

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
        self.server = Server(("127.0.0.1", 0), Hand)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def hook(self):
        return f"http://127.0.0.1:{self.port}/hook?t={self.token}"

    @property
    def start_adresse(self):
        return f"http://127.0.0.1:{self.port}/start?t={self.token}"

    def startseite(self):
        p = oci_parameter(self.benutzer, self.passwort, self.hook, self.suche)
        felder = "".join(f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">' for k, v in p.items())
        return (f"<html><body onload='document.forms[0].submit()' style='font-family:sans-serif'>"
                f"<form method='post' action='{html.escape(self.adresse)}'>{felder}"
                f"<p>Shop wird geöffnet …</p><noscript><button>Shop öffnen</button></noscript></form></body></html>")

    def stoppen(self):
        self.server.shutdown()
        self.server.server_close()


# --------------------------------------------------------------------------------------------- Shop-Suche
def suchtext(form=None, a=None, b=None, wand=None, werkstoff=None, profil_id=None):
    """Suchtext für Shop und OCI: 'Rechteckrohr 80x40x3 S235JRH'."""
    from .stammdaten import zahl_als_text as z

    def m(x):
        return z(x, 2).rstrip("0").rstrip(",") if x is not None else ""
    if form and a and wand:
        if form == "Rundrohr":
            dims = f"{m(a)}x{m(wand)}"
        elif form == "Quadratrohr":
            dims = f"{m(a)}x{m(a)}x{m(wand)}"
        else:
            dims = f"{m(a)}x{m(b or a)}x{m(wand)}"
        return " ".join(x for x in (form, dims, werkstoff or "") if x)
    return " ".join(x for x in (profil_id or "", werkstoff or "") if x)


def shop_adresse(lief, text):
    """Adresse der Shop-Suche: Suchadresse mit {suche} (URL-kodiert), sonst die Startseite (Suchtext dann über die
    Zwischenablage)."""
    vorlage = str(lief.get("such_adresse") or "").strip()
    if vorlage and "{suche}" in vorlage:
        return vorlage.replace("{suche}", urllib.parse.quote_plus(text or ""))
    return str(lief.get("shop_adresse") or "").strip() or None


# --------------------------------------------------------------------------------------------- Verbindung testen
def testen(lief, zugang=None, oeffnen=None):
    """(ok, Text) für „Verbindung testen“. Preisliste: Ordner da und Dateien darin; Shop: Startseite erreichbar;
    OCI: Zugang hinterlegt und Einstiegsadresse antwortet (mit Hintergrundsuche: Testsuche)."""
    weg = lief.get("weg")
    if weg == "Preisliste":
        ordner = lief.get("preisliste_ordner")
        if not ordner:
            return False, "Kein Preislisten-Ordner eingetragen."
        if not Path(ordner).is_dir():
            return False, f"Ordner {ordner} nicht erreichbar."
        n = len(preislisten_im_ordner(ordner))
        return True, f"Ordner erreichbar, {n} Preisliste(n) darin."
    if weg == "OCI-Punchout":
        if not lief.get("oci_adresse"):
            return False, "Keine OCI-Einstiegsadresse (kommt vom Lieferanten mit der Freischaltung)."
        if not zugang:
            return False, "Kein OCI-Zugang hinterlegt (Zugangsdaten …)."
        if op.ja(lief.get("oci_hintergrund")):
            try:
                eintraege, _ = oci_hintergrund(lief["oci_adresse"], zugang[0], zugang[1], "Rohr", oeffnen)
            except (OSError, ValueError, urllib.error.URLError) as f:
                return False, f"OCI-Hintergrundsuche fehlgeschlagen: {f}"
            return True, f"OCI-Hintergrundsuche antwortet ({len(eintraege)} Artikel für „Rohr“)."
        return _erreichbar(lief["oci_adresse"], oeffnen)
    adr = lief.get("shop_adresse")
    if not adr:
        return False, "Keine Shop-Adresse eingetragen."
    return _erreichbar(adr, oeffnen)


def _erreichbar(adresse, oeffnen=None):
    try:
        req = urllib.request.Request(adresse, method="GET", headers={"User-Agent": "Rohrlaser-Kalkulation"})
        with (oeffnen or urllib.request.urlopen)(req, timeout=ZEITLIMIT) as r:
            return True, f"Erreichbar (HTTP {getattr(r, 'status', 200)})."
    except urllib.error.HTTPError as f:
        return f.code < 500, f"Antwort HTTP {f.code}."
    except (OSError, ValueError) as f:
        return False, f"Nicht erreichbar: {f}"
