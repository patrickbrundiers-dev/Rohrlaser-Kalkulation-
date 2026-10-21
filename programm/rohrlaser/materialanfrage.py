"""Materialanfrage per E-Mail: Stangenbedarf aus der Optimierung (nur Eigenmaterial) je Profil + Werkstoff +
Oberfläche + Lieferlänge, Lieferant aus 'Lieferlängen' bzw. 'Preise', E-Mail-Adresse aus den Lieferanten.

Versand: Das Programm sendet nie selbst. 'In Outlook öffnen' legt über PowerShell (COM, klassisches Outlook) eine
E-Mail mit Empfänger, Betreff und Text an und zeigt sie an; gesendet wird nur mit dem Klick in Outlook.
Ohne klassisches Outlook (z. B. neues Outlook, keine COM-Schnittstelle) entsteht eine E-Mail-Datei (.eml, als
Entwurf markiert) in der Ablage, die das Standard-Mailprogramm öffnet.
"""
import json
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
import mimetypes

from . import rechnen
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
    pos (Positionsnummern), text}]. Kundenmaterial fehlt (der Kunde liefert
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


def lieferanten(db_zeilen):
    """{Name: E-Mail} aus den Lieferanten (Zukaufartikel)."""
    return {z["name"]: (z.get("email") or "").strip() for z in db_zeilen if z.get("name")}


def betreff(kopf):
    return f"Materialanfrage zu Angebot {kopf.get('nummer') or ''}".strip()


def anschreiben(kopf, zeilen, einst, k, mengen=None):
    """Text der E-Mail: Anrede, Bedarf als Liste, Bitte um Preis und Liefertermin, Absender aus dem Briefkopf.
    mengen = {Zeilenindex: Stangen} überschreibt die Anzahl."""
    mengen = mengen or {}
    liste_ = "\n".join(f"- {zeile_text(z, k, mengen.get(i))}" for i, z in enumerate(zeilen))
    ref = f" (unser Angebot {kopf['nummer']})" if kopf.get("nummer") else ""
    absender = "\n".join(t for t in ((einst or {}).get(f"briefkopf_{i}") for i in (1, 2, 3, 4))
                         if t and t not in ("Firmenname", "Straße Nr.", "PLZ Ort", "Telefon / E-Mail"))
    return ("Sehr geehrte Damen und Herren,\n\n"
            f"bitte senden Sie uns ein Angebot für folgendes Material{ref}:\n\n{liste_}\n\n"
            "Bitte mit Preis, Lieferzeit und Angabe der Lieferlänge.\n\n"
            "Mit freundlichen Grüßen" + (f"\n{absender}" if absender else ""))


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
$m.Body = $d.text
foreach ($a in $d.anhaenge) { [void]$m.Attachments.Add($a) }
$m.Display($false)
"""


def outlook_daten(an, betreff_, text_, anhaenge=()):
    return dict(an=an or "", betreff=betreff_, text=text_, anhaenge=[str(Path(a)) for a in anhaenge])


def outlook_oeffnen(an, betreff_, text_, anhaenge=(), ausfuehren=None):
    """E-Mail im klassischen Outlook anzeigen (nicht senden). ausfuehren(befehl) ersetzt subprocess.run (Tests).
    Ergebnis: (True, '') oder (False, Fehlertext)."""
    if ausfuehren is None and sys.platform != "win32":
        return False, "Outlook gibt es nur unter Windows."
    with tempfile.TemporaryDirectory() as tmp:
        skript, daten = Path(tmp) / "outlook.ps1", Path(tmp) / "mail.json"
        skript.write_text(OUTLOOK_PS, encoding="utf-8-sig")
        daten.write_text(json.dumps(outlook_daten(an, betreff_, text_, anhaenge), ensure_ascii=False), encoding="utf-8")
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
