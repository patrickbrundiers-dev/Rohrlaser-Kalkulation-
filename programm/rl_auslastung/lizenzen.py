"""Lizenz der Rohrlaser Auslastung (Plan 2.4, Patrick 11.11.2026: „Kalkulations-Lizenz gilt mit“).

Gültig ist
- eine Lizenz der Kalkulation (Admin, Benutzer, Test) für diesen Rechner – dieselbe Datei für beide Programme, oder
- eine eigene Lizenz der Art „auslastung“ (Lizenz-Werkzeug, Art „Nur Auslastung“) für Plätze ohne Kalkulation. Die
  Kalkulation nimmt sie nicht an (unbekannte Lizenzart), damit schaltet sie dort nichts frei.

Signatur, Rechner-ID, Sperrliste, Uhr-Prüfung und Einführung in zwei Stufen kommen aus rohrlaser.lizenz; am Code der
Kalkulation ändert sich nichts. Ohne gültige Lizenz arbeitet der Platz mit der Rolle „nur ansehen“: Aufträge,
Plantafel und Auswertungen bleiben lesbar, geändert wird nichts. Eine Admin-Lizenz gilt hier wie eine Benutzerlizenz
(die Auslastung hat kein Admin-Passwort, Rechte regelt die Benutzerverwaltung).

Lizenzordner: Ordner „Lizenz“ neben der Auslastung.ini dieses Platzes (ort.basis()), nicht im gemeinsamen
Datenordner – eine Lizenz gilt je Rechner. Ist dort keine Lizenz, wird die aktive Lizenz einer installierten
Kalkulation auf demselben Rechner mitbenutzt (LOCALAPPDATA\\Rohrlaser Angebotskalkulation\\Daten\\Lizenz).
Ohne Qt.
"""
import datetime
import json
import os
from pathlib import Path

from rohrlaser import lizenz as L

ART = "auslastung"
ORDNER = "Lizenz"
KALKULATION = Path("Rohrlaser Angebotskalkulation") / "Daten" / L.ORDNER


def ordner(basis):
    return Path(basis) / ORDNER


def kalkulation_ordner():
    """Lizenzordner einer installierten Kalkulation auf diesem Rechner oder None."""
    lokal = os.environ.get("LOCALAPPDATA")
    if not lokal:
        return None
    o = Path(lokal) / KALKULATION
    return o if (o / L.AKTIV).is_file() else None


def pruefen(quelle, schluessel=None):
    """Aufbau und Signatur wie rohrlaser.lizenz.pruefen, zusätzlich die Art „auslastung“ (Ablaufdatum Pflicht, kein
    Admin-Passwort). Ergebnis: Inhalt; L.LizenzFehler, wenn ungültig."""
    daten = L.lesen(quelle)
    inhalt = daten.get("inhalt") if isinstance(daten.get("inhalt"), dict) else None
    if inhalt is None or inhalt.get("art") != ART:
        return L.pruefen(daten, schluessel)
    if daten.get("format") != L.FORMAT:
        raise L.LizenzFehler("Lizenz für eine neuere Programmversion – bitte das Programm aktualisieren.")
    schluessel = L.standard_schluessel() if schluessel is None else schluessel
    sid = inhalt.get("schluessel_id")
    if sid not in schluessel:
        raise L.LizenzFehler(f"Lizenz mit unbekanntem Schlüssel {sid!r} – bitte das Programm aktualisieren.")
    if not L.signatur_gueltig(inhalt, daten.get("signatur"), sid, schluessel):
        raise L.LizenzFehler("Signatur ungültig: Die Lizenzdatei wurde verändert oder stammt nicht von Patrick.")
    if not inhalt.get("lizenz_id"):
        raise L.LizenzFehler("Lizenz-ID fehlt.")
    if not isinstance(inhalt.get("rechner"), list):
        raise L.LizenzFehler("Feld rechner muss eine Liste sein.")
    if inhalt.get("admin_passwort"):
        raise L.LizenzFehler("Nur eine Admin-Lizenz darf ein Admin-Passwort enthalten.")
    if not inhalt.get("gueltig_bis"):
        raise L.LizenzFehler("Eine Lizenz für die Auslastung braucht ein Ablaufdatum.")
    for feld in ("gueltig_ab", "gueltig_bis"):
        if inhalt.get(feld):
            try:
                datetime.date.fromisoformat(inhalt[feld])
            except (TypeError, ValueError):
                raise L.LizenzFehler(f"Feld {feld} ist kein Datum.") from None
    return inhalt


def ermitteln(quelle, heute=None, rechner=None, schluessel=None, sperrliste=None, spaetestes=None,
              durchsetzung=None):
    """Zustand wie rohrlaser.lizenz.ermitteln; eine Lizenz der Art „auslastung“ gilt wie eine Benutzerlizenz."""
    if quelle is not None:
        try:
            daten = L.lesen(quelle)
            inhalt = daten.get("inhalt") if isinstance(daten.get("inhalt"), dict) else {}
            if inhalt.get("art") == ART:
                pruefen(daten, schluessel)
                # geprüft: ab hier dieselben Regeln wie für eine Benutzerlizenz (Rechner, Sperrliste, Uhr, Ablauf)
                return _wie_benutzer(inhalt, heute, rechner, sperrliste, spaetestes, durchsetzung)
        except L.LizenzFehler as e:
            return _lesemodus(str(e).rstrip("."), heute, rechner, spaetestes, durchsetzung)
    return L.ermitteln(quelle, heute, rechner, schluessel, sperrliste, spaetestes, durchsetzung)


def _lesemodus(grund, heute, rechner, spaetestes, durchsetzung, inhalt=None):
    rechner = L.rechner_id() if rechner is None else rechner
    durch = L.durchsetzung_aktiv(heute or datetime.date.today(), spaetestes) if durchsetzung is None else durchsetzung
    if durch:
        hinweis = f"Nur ansehen: {grund}"
    else:
        hinweis = (f"Ab {L.STICHTAG} braucht das Programm eine Lizenz ({grund}). Bitte die Rechner-ID "
                   f"{rechner or '?'} an Patrick senden (Hilfe → Lizenz …).")
    return L.Zustand("lesemodus", rechner, inhalt or {}, grund, hinweis, "rot" if durch else "gelb",
                     start_hinweis=durch, durchsetzung=durch)


def _wie_benutzer(inhalt, heute, rechner, sperrliste, spaetestes, durchsetzung):
    """Die Regeln von rohrlaser.lizenz.ermitteln nach der Prüfung, für eine geprüfte Auslastungs-Lizenz."""
    heute = heute or datetime.date.today()
    rechner = L.rechner_id() if rechner is None else rechner
    durch = L.durchsetzung_aktiv(heute, spaetestes) if durchsetzung is None else durchsetzung
    lid = inhalt["lizenz_id"]
    if sperrliste and lid in (sperrliste.get("gesperrt") or []):
        return _lesemodus(f"Lizenz {lid} ist gesperrt", heute, rechner, spaetestes, durch, inhalt)
    ids = [L.id_normal(r) for r in inhalt["rechner"]]
    if ids and L.id_normal(rechner) not in ids:
        return _lesemodus(f"Lizenz gilt für eine andere Rechner-ID (dieser Rechner: {rechner or 'unbekannt'})",
                          heute, rechner, spaetestes, durch, inhalt)
    if L.uhr_zurueck(heute, spaetestes):
        return _lesemodus(f"Systemzeit prüfen – das Datum {_text(heute)} liegt vor dem zuletzt gesehenen "
                          f"{_text(spaetestes)}", heute, rechner, spaetestes, durch, inhalt)
    ab = inhalt.get("gueltig_ab")
    if ab and heute < datetime.date.fromisoformat(ab):
        return _lesemodus(f"Lizenz gilt erst ab {_text(datetime.date.fromisoformat(ab))}", heute, rechner,
                          spaetestes, durch, inhalt)
    bis = datetime.date.fromisoformat(inhalt["gueltig_bis"])
    rest = (bis - heute).days
    if rest > L.WARNUNG_TAGE:
        return L.Zustand("gueltig", rechner, inhalt, tage_rest=rest, durchsetzung=durch)
    if rest >= 0:
        return L.Zustand("bald", rechner, inhalt, hinweis=f"Lizenz läuft am {_text(bis)} ab (noch {rest} "
                                                          f"Tag{'' if rest == 1 else 'e'}) – bitte verlängern.",
                         farbe="gelb", tage_rest=rest, start_hinweis=rest <= L.WARNUNG_START_TAGE, durchsetzung=durch)
    if -rest <= L.KULANZ_TAGE:
        lese_ab = bis + datetime.timedelta(days=L.KULANZ_TAGE + 1)
        return L.Zustand("kulanz", rechner, inhalt, hinweis=f"Lizenz abgelaufen am {_text(bis)}, nur ansehen ab "
                                                            f"{_text(lese_ab)} – bitte verlängern.",
                         farbe="rot", tage_rest=rest, start_hinweis=True, durchsetzung=durch)
    z = _lesemodus(f"Lizenz abgelaufen am {_text(bis)}", heute, rechner, spaetestes, durch, inhalt)
    z.tage_rest = rest
    return z


def _text(d):
    return d.strftime("%d.%m.%Y")


class Stelle(L.LizenzStelle):
    """Lizenz des laufenden Programms für den Lizenzdialog der Kalkulation (gleiche Schnittstelle: zustand,
    rechner, pruefen, laden, text). Ohne Datendatei, ohne Admin-Passwort."""

    def __init__(self, basis, schluessel=None, rechner=None, durchsetzung=None, kalkulation=True):
        super().__init__(ordner(basis), None, schluessel, rechner, durchsetzung)
        self.kalkulation = kalkulation_ordner() if kalkulation is True else kalkulation
        self.quelle = ""                # "", "eigene" oder "kalkulation"

    def pruefen(self, heute=None):
        heute = heute or datetime.date.today()
        o = self.ordner
        if not (o / L.AKTIV).is_file() and self.kalkulation and (Path(self.kalkulation) / L.AKTIV).is_file():
            o, self.quelle = Path(self.kalkulation), "kalkulation"
        else:
            self.quelle = "eigene" if (o / L.AKTIV).is_file() else ""
        spaet = L.spaetestes_datum(self.ordner)
        sperr = L.sperrliste_pruefen(self.ordner / L.SPERRLISTE, self.schluessel)
        aktiv = L.aktive_lizenz(o)
        z = ermitteln(aktiv, heute, self.rechner, self.schluessel, sperr, spaet, self.durchsetzung)
        if z.stufe == "admin":                       # hier ohne Admin-Passwort: wie eine Benutzerlizenz, unbefristet
            z.admin_aus = False
        if z.hinweis.startswith("Lesemodus: "):        # hier heißt es „nur ansehen“ (Rolle Nur lesen)
            z.hinweis = "Nur ansehen: " + z.hinweis[len("Lesemodus: "):]
        if not L.uhr_zurueck(heute, spaet) and self.ordner.parent.is_dir():
            L.zeit_merken(self.ordner, heute, spaet)
        self.zustand = z
        return z

    def admin_passwort(self, z=None):
        return ""

    def laden(self, quelle, heute=None):
        """Lizenzdatei übernehmen (L.LizenzFehler, wenn ungültig; dann bleibt alles, wie es war) und neu prüfen.
        Lizenzen der Kalkulation wie dort (rohrlaser.lizenz.lizenz_laden), eigene Auslastungs-Lizenzen ebenso."""
        if isinstance(quelle, str) and not quelle.lstrip().startswith("{"):
            quelle = Path(quelle)
        daten = L.lesen(quelle)
        inhalt = daten.get("inhalt") if isinstance(daten.get("inhalt"), dict) else {}
        if inhalt.get("art") != ART:
            L.lizenz_laden(self.ordner, daten, heute, self.rechner, self.schluessel)
            return self.pruefen(heute)
        pruefen(daten, self.schluessel)
        ids = [L.id_normal(r) for r in inhalt["rechner"]]
        if ids and L.id_normal(self.rechner) not in ids:
            raise L.LizenzFehler(f"Diese Lizenz gilt für eine andere Rechner-ID (dieser Rechner: "
                                 f"{self.rechner or 'unbekannt'}).")
        bis = datetime.date.fromisoformat(inhalt["gueltig_bis"])
        if (heute or datetime.date.today()) > bis + datetime.timedelta(days=L.KULANZ_TAGE):
            raise L.LizenzFehler(f"Diese Lizenz ist schon am {_text(bis)} abgelaufen.")
        self.ordner.mkdir(parents=True, exist_ok=True)
        vorher = L.aktive_lizenz(self.ordner)
        if vorher:
            (self.ordner / L.ALT).mkdir(parents=True, exist_ok=True)
            vorher.replace(self.ordner / L.ALT / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}.lizenz")
        (self.ordner / L.AKTIV).write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
        return self.pruefen(heute)

    def text(self):
        z = self.zustand or self.pruefen()
        i = z.inhalt
        von = " (Lizenz der Kalkulation)" if self.quelle == "kalkulation" else ""
        if i and z.stufe != "lesemodus":
            if z.stufe == "admin":
                return f"Admin-Lizenz {i.get('lizenz_id')} ({i.get('inhaber')}), unbefristet{von}"
            art = "Testlizenz" if z.test else "Lizenz nur Auslastung" if i.get("art") == ART else "Lizenz"
            wer = ", ".join(x for x in (i.get("inhaber"), i.get("firma")) if x)
            return f"{art} {i.get('lizenz_id')} ({wer}), gültig bis {_text(datetime.date.fromisoformat(i['gueltig_bis']))}{von}"
        return ("Nur ansehen: " if z.nur_lesen else "Keine gültige Lizenz: ") + z.grund
