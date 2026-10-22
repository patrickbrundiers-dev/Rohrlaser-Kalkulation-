"""Materialanfrage per E-Mail: Stangenbedarf aus der Optimierung (nur Eigenmaterial) je Profil + Werkstoff +
Oberfläche + Lieferlänge, Lieferant aus 'Lieferlängen' bzw. 'Preise', E-Mail-Adresse aus den Lieferanten.

Versand: Das Programm sendet nie selbst. 'In Outlook öffnen' legt über PowerShell (COM, klassisches Outlook) eine
E-Mail mit Empfänger, Betreff und Text an und zeigt sie an; gesendet wird nur mit dem Klick in Outlook.
Ohne klassisches Outlook (z. B. neues Outlook, keine COM-Schnittstelle) entsteht eine E-Mail-Datei (.eml, als
Entwurf markiert) in der Ablage, die das Standard-Mailprogramm öffnet.

Betreff und Text kommen aus Vorlagen in den Einstellungen (Platzhalter {angebot}, {kunde}, {positionen}, {datum},
{absender}). Je Zeile optional der Zuschnitt beim Lieferanten (12-m-Stange geschnitten auf die Stangenlängen der
Planung) und die Anforderungen des Werkstoffs (Prüfbescheinigung, Herkunft EU, Maßtoleranzen nach Norm). Die
Signatur setzt Outlook selbst (Standardsignatur für neue E-Mails); die E-Mail-Datei bekommt die eigene Signatur aus
den Einstellungen.
"""
import html
import re
import json
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from email.utils import formatdate
from datetime import date
from pathlib import Path
import mimetypes

from . import rechnen
from .stammdaten import EINSTELLUNG
from .ausgabe import kaufm_runden, profiltext
from .angebot import ist_zukaufteil

OHNE_LIEFERANT = "(ohne Lieferant)"


def _lieferant(profil, werkstoff, laenge, tabellen):
    for z in tabellen.get("lieferlaengen") or ():
        if z.get("profil_id") == profil and z.get("werkstoff_id") == werkstoff and z.get("laenge") == laenge \
                and z.get("lieferant"):
            return z["lieferant"]
    for z in tabellen.get("preise") or ():
        if z.get("profil_id") == profil and z.get("werkstoff_id") == werkstoff and z.get("lieferant"):
            return z["lieferant"]
    return None


def bedarf(positionen, ergebnis, k, tabellen, werte=None):
    """Zeilen der Anfrage aus der Optimierung: [{profil, werkstoff, oberflaeche, laenge, stangen, gewicht, lieferant,
    pos (Positionsnummern), text, zuschnitte (je zugeschnittener Stange die Stangenlängen), anforderungen (Text)}]. Kundenmaterial fehlt (der Kunde liefert
    es). werte = stangen_werte (Gewicht je Stange), sonst ohne Gewicht."""
    zeilen = {}
    gewichte = {s["nr"]: w.get("gewicht") for s, w in zip((ergebnis or {}).get("stangen") or (), werte or ())}
    for s in (ergebnis or {}).get("stangen") or ():
        if s.get("beistellung"):
            continue
        schl = (s["profil"], s["werkstoff"], s.get("oberflaeche") or "", s["stange"])
        z = zeilen.setdefault(schl, dict(profil=s["profil"], werkstoff=s["werkstoff"], oberflaeche=s.get("oberflaeche")
                                         or "", laenge=s["stange"], stangen=0, gewicht=0.0, pos=[],
                                         lieferant=_lieferant(s["profil"], s["werkstoff"], s["stange"], tabellen)))
        z["stangen"] += 1
        if s.get("werkstuecke"):        # vom Lieferanten zugeschnitten (z. B. 12 m in Stangen bis zur Beladelänge)
            z.setdefault("zuschnitte", []).append(tuple(w["laenge"] for w in s["werkstuecke"]))
        g = gewichte.get(s["nr"])
        z["gewicht"] = z["gewicht"] + g if isinstance(g, (int, float)) and z["gewicht"] is not None else None
        for t in s.get("teile") or ():
            i = t.get("index", -1)
            if 0 <= i < len(positionen) and not ist_zukaufteil(positionen[i]):
                p = positionen[i]
                nr = str(p.get("pos") or p.get("artikel") or i + 1)
                if nr not in z["pos"]:
                    z["pos"].append(nr)
    out = list(zeilen.values())
    for z in out:
        z.setdefault("zuschnitte", [])
        z["anforderungen"] = anforderungen(z["werkstoff"], k)
        z["text"] = zeile_text(z, k)
    return out


def zeile_text(z, k, stangen=None):
    """'3 Stangen Quadratrohr 40 x 40 x 3, S235 EN10219, à 6.000 mm (ca. 63 kg)'."""
    n = z["stangen"] if stangen is None else stangen
    w = (k.werkstoffe.get(z["werkstoff"]) or {}).get("angebotstext") or z["werkstoff"]
    laenge = f"{kaufm_runden(z['laenge'], 0):,.0f}".replace(",", ".")
    g = z.get("gewicht")
    gew = f" (ca. {rechnen.zahl(g * n / z['stangen'], 0)} kg)" if g and z["stangen"] else ""
    return (f"{n} {'Stange' if n == 1 else 'Stangen'} {profiltext(z['profil'], k)}, {w}"
            + (f", {z['oberflaeche']}" if z["oberflaeche"] else "") + f", à {laenge} mm{gew}")


ZEUGNISSE = {"2.2": "Werkszeugnis 2.2 nach EN 10204", "3.1": "Abnahmeprüfzeugnis 3.1 nach EN 10204",
             "3.2": "Abnahmeprüfzeugnis 3.2 nach EN 10204"}


def anforderungen(werkstoff, k):
    """Anforderungen des Werkstoffs für die Anfrage (Stammdaten Werkstoffe, Spalten 'Anfrage: …'), '' = keine."""
    w = k.werkstoffe.get(werkstoff) or {}
    teile = [ZEUGNISSE[w["anfrage_zeugnis"]]] if w.get("anfrage_zeugnis") in ZEUGNISSE else []
    if (w.get("anfrage_herkunft_eu") or "").strip().lower() == "ja":
        teile.append("Herkunft EU")
    if (w.get("anfrage_toleranz") or "").strip().lower() == "ja":
        teile.append("Maßtoleranzen nach Norm")
    return ", ".join(teile)


def _mm(w):
    return f"{kaufm_runden(w, 0):,.0f}".replace(",", ".")


def zuschnitt_text(z):
    """'je Stange geschnitten auf 5.950 + 5.950 mm' bzw. bei verschiedenen Zuschnitten 'davon 2 Stangen geschnitten
    auf …, 1 Stange geschnitten auf …'; '' ohne Zuschnitt."""
    muster = {}
    for m in z.get("zuschnitte") or ():
        muster[m] = muster.get(m, 0) + 1
    if not muster:
        return ""

    def laengen(m):
        gleich = {}
        for l in m:
            gleich[l] = gleich.get(l, 0) + 1
        return " + ".join(f"{n} x {_mm(l)}" if n > 1 else _mm(l) for l, n in gleich.items()) + " mm"
    if len(muster) == 1:
        return f"je Stange geschnitten auf {laengen(next(iter(muster)))}"
    return "davon " + ", ".join(f"{n} {'Stange' if n == 1 else 'Stangen'} geschnitten auf {laengen(m)}"
                                for m, n in sorted(muster.items(), key=lambda x: -x[1]))


def zeile_block(z, k, stangen=None, zuschnitt=True):
    """Zeile der Liste in der E-Mail: Materialzeile, darunter eingerückt Zuschnitt und Anforderungen."""
    zeilen = [f"- {zeile_text(z, k, stangen)}"]
    if zuschnitt and zuschnitt_text(z):
        zeilen.append(f"  {zuschnitt_text(z)}")
    if z.get("anforderungen"):
        zeilen.append(f"  {z['anforderungen']}")
    return "\n".join(zeilen)


def lieferanten(db_zeilen):
    """{Name: E-Mail} aus den Lieferanten (Zukaufartikel)."""
    return {z["name"]: (z.get("email") or "").strip() for z in db_zeilen if z.get("name")}


def _einst(einst, name):
    """Text einer Einstellung, leer = Vorgabe."""
    w = (einst or {}).get(name)
    return w if isinstance(w, str) and w.strip() else EINSTELLUNG[name].vorgabe


def absender(einst):
    """Briefkopf-Zeilen ohne die unveränderten Vorgaben."""
    return "\n".join(t for t in ((einst or {}).get(f"briefkopf_{i}") for i in (1, 2, 3, 4))
                     if t and t not in ("Firmenname", "Straße Nr.", "PLZ Ort", "Telefon / E-Mail"))


def signatur(einst):
    """Eigene Signatur (Einstellung, leer = Briefkopf) für die E-Mail-Datei und Outlook ohne Outlook-Signatur."""
    return ((einst or {}).get("anfrage_signatur") or "").strip() or absender(einst)


def outlook_signatur(einst):
    """True: Outlook setzt seine Standardsignatur, das Programm hängt keine eigene an."""
    return ((einst or {}).get("anfrage_outlook_signatur") or "ja").strip().lower() != "nein"


def _vorlage(text, werte):
    """Platzhalter {name} ersetzen; unbekannte bleiben stehen."""
    return re.sub(r"\{(\w+)\}", lambda m: str(werte[m.group(1)]) if m.group(1) in werte else m.group(0), text)


def _werte(kopf, einst, positionen=""):
    return dict(angebot=kopf.get("nummer") or "", kunde=kopf.get("kunde") or "", positionen=positionen,
                datum=date.today().strftime("%d.%m.%Y"), absender=absender(einst))


def betreff(kopf, einst=None):
    return _vorlage(_einst(einst, "anfrage_betreff"), _werte(kopf, einst)).strip()


def anschreiben(kopf, zeilen, einst, k, mengen=None, zuschnitt=None):
    """Text der E-Mail aus der Vorlage (Einstellung anfrage_text), ohne Signatur. mengen = {Zeilenindex: Stangen}
    überschreibt die Anzahl, zuschnitt = Zeilenindizes mit Zuschnitt (None = alle, die einen haben)."""
    mengen = mengen or {}
    liste_ = "\n".join(zeile_block(z, k, mengen.get(i), zuschnitt is None or i in zuschnitt)
                       for i, z in enumerate(zeilen))
    return _vorlage(_einst(einst, "anfrage_text"), _werte(kopf, einst, liste_))


def mit_signatur(text_, sig):
    return text_.rstrip() + (f"\n{sig}" if sig else "")


def text_html(text_):
    """Text als HTML (für das Einfügen vor die Outlook-Signatur)."""
    zeilen = "<br>\n".join(html.escape(z).replace("  ", "&nbsp;&nbsp;") for z in text_.split("\n"))
    return f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">{zeilen}<br><br></div>'


def eml(pfad, an, betreff_, text_, anhaenge=()):
    """E-Mail-Entwurf als .eml (X-Unsent: 1, öffnet in Outlook als neue E-Mail) mit Anhängen schreiben."""
    m = EmailMessage()
    m["To"] = an or ""
    m["Subject"] = betreff_
    m["Date"] = formatdate(localtime=True)
    m["X-Unsent"] = "1"
    m.set_content(text_)
    for a in anhaenge:
        a = Path(a)
        art = (mimetypes.guess_type(a.name)[0] or "application/octet-stream").split("/")
        m.add_attachment(a.read_bytes(), maintype=art[0], subtype=art[1], filename=a.name)
    Path(pfad).write_bytes(bytes(m))
    return Path(pfad)


# PowerShell: klassisches Outlook per COM, E-Mail nur anzeigen (Display), nie senden
OUTLOOK_PS = r"""
$ErrorActionPreference = 'Stop'
$d = Get-Content -Raw -Encoding UTF8 -LiteralPath $args[0] | ConvertFrom-Json
$o = New-Object -ComObject Outlook.Application
$m = $o.CreateItem(0)
$m.To = $d.an
$m.Subject = $d.betreff
foreach ($a in $d.anhaenge) { [void]$m.Attachments.Add($a) }
if ($d.signatur) {
    # Erst anzeigen: dabei setzt Outlook die Standardsignatur ein; der Text kommt davor
    $m.Display($false)
    $h = $m.HTMLBody
    $b = [regex]::Match($h, '(?is)<body[^>]*>')
    if ($b.Success) { $m.HTMLBody = $h.Insert($b.Index + $b.Length, $d.html) } else { $m.HTMLBody = $d.html + $h }
} else {
    $m.Body = $d.text
    $m.Display($false)
}
"""


def outlook_daten(an, betreff_, text_, anhaenge=(), signatur_=False):
    return dict(an=an or "", betreff=betreff_, text=text_, html=text_html(text_), signatur=bool(signatur_),
                anhaenge=[str(Path(a)) for a in anhaenge])


def outlook_oeffnen(an, betreff_, text_, anhaenge=(), ausfuehren=None, signatur_=False):
    """E-Mail im klassischen Outlook anzeigen (nicht senden). signatur_ = True: Text vor die Standardsignatur von
    Outlook setzen. ausfuehren(befehl) ersetzt subprocess.run (Tests). Ergebnis: (True, '') oder (False, Fehlertext)."""
    if ausfuehren is None and sys.platform != "win32":
        return False, "Outlook gibt es nur unter Windows."
    with tempfile.TemporaryDirectory() as tmp:
        skript, daten = Path(tmp) / "outlook.ps1", Path(tmp) / "mail.json"
        skript.write_text(OUTLOOK_PS, encoding="utf-8-sig")
        daten.write_text(json.dumps(outlook_daten(an, betreff_, text_, anhaenge, signatur_), ensure_ascii=False), encoding="utf-8")
        befehl = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(skript), str(daten)]
        try:
            if ausfuehren:
                r = ausfuehren(befehl)
            else:
                r = subprocess.run(befehl, capture_output=True, text=True, timeout=60,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "").strip()[:400] or f"Rückgabewert {r.returncode}"
    return True, ""
