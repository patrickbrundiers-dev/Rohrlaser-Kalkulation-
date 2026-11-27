"""Prüfstelle: die einzige Stelle, die Zugriffe entscheidet (Paket A; angeschlossen an Oberfläche und Kern ab C/D).

darf(recht) ist nur wahr, wenn alle drei Ebenen zustimmen:
1. Sitzung: angemeldet, nicht abgemeldet, nicht wegen Inaktivität gesperrt.
2. Benutzer: das Einzelrecht über eine Rolle oder einzeln gegeben (berechtigung.wirksame_rechte).
3. Lizenz: das Modul des Rechts ist lizenziert (module.lizenziert) und die Lizenz ist nicht im Lesemodus (dann
   gelten nur Rechte, die nichts schreiben).
Der Entwickler (gültiger Ausweis) überspringt nur Ebene 2 und 3 – nie Ebene 1: auch er braucht eine gültige Sitzung.

verlangen(recht) ist die Prüfung für die Fachlogik: Sie wirft ZugangVerweigert (mit verständlichem Grund) und
schreibt den Versuch ins Sicherheitsprotokoll. Die Oberfläche blendet zusätzlich aus, ist aber nicht der Schutz.

Anmelden: benutzer_anmelden() für Konten (Datensatz aus der Benutzerverwaltung, ab Paket B Tabelle zg_benutzer) und
entwickler_anmelden() für den Entwickler-Ausweis. Beide zählen Fehlversuche (authentifizierung.Sperre), melden nie,
ob es am Benutzernamen oder am Passwort lag, und protokollieren jeden Versuch ohne das Eingegebene.

AKTUELL ist die Prüfstelle des laufenden Programms. Solange keine gesetzt ist (alte Startwege vor Paket C, Tests
ohne Anmeldung), erlauben darf()/verlangen() alles wie bisher – so bleibt jede Version für sich lauffähig.
"""
import datetime
from dataclasses import dataclass

from .. import module as _module
from . import authentifizierung as auth
from . import ausweis as aw
from . import berechtigung as B
from . import protokoll as P
from .sitzungen import SitzungFehler, Sitzungen

AKTUELL = None
FALSCH = "Benutzername oder Passwort falsch."
STATUS_AKTIV, STATUS_GESPERRT, STATUS_DEAKTIVIERT = "aktiv", "gesperrt", "deaktiviert"


class ZugangVerweigert(PermissionError):
    def __init__(self, recht, grund):
        super().__init__(grund)
        self.recht = recht
        self.grund = grund


@dataclass
class Ergebnis:
    ok: bool
    text: str = ""
    warten: int = 0
    sitzung: object = None
    neuer_hash: str = ""            # Passwort auf scrypt umstellen: diesen Hash im Konto speichern
    passwort_aendern: bool = False  # Konto verlangt ein neues Passwort, bevor gearbeitet wird
    totp_schritt: int = -1          # benutzter Einmalcode-Schritt (im Konto merken, gegen Wiederverwendung)
    zweiter_faktor_fehlt: bool = False


class Pruefstelle:
    def __init__(self, protokoll=None, sitzungen=None, installation="", umgebung="produktiv", arbeitsplatz="",
                 modul_erlaubt=None, nur_lesen=None, eigene_rollen=None):
        self.sitzungen = sitzungen or Sitzungen()
        self.protokoll = protokoll or P.Protokoll(None, installation, arbeitsplatz)
        self.installation = str(installation)
        self.umgebung = umgebung
        self.arbeitsplatz = arbeitsplatz
        self.modul_erlaubt = modul_erlaubt or _module.lizenziert
        self.nur_lesen = nur_lesen or (lambda: False)
        self.eigene_rollen = eigene_rollen
        self.gesehen = set()            # benutzte Nonces der Entwickler-Anmeldung

    # -------------------------------------------------------------- Entscheidung
    def grund(self, recht):
        """'' wenn erlaubt, sonst der Grund für den Benutzer."""
        try:
            s = self.sitzungen.pruefen()
        except SitzungFehler as e:
            return str(e)
        if s.entwickler:
            return ""
        if recht in B.NUR_ENTWICKLER:
            return "Nur für den Entwickler."
        r = B.RECHT.get(recht)
        if r is None:
            return f"Unbekanntes Recht „{recht}“."
        if recht not in s.rechte:
            return f"Keine Berechtigung: {r.titel}."
        if r.modul and not self.modul_erlaubt(r.modul):
            titel = _module.MODUL[r.modul].titel if r.modul in _module.MODUL else r.modul
            return f"Das Modul {titel} ist in dieser Lizenz nicht enthalten."
        if r.schreibt and self.nur_lesen():
            return "Die Lizenz ist im Lesemodus: Ansehen geht, Ändern nicht."
        return ""

    def darf(self, recht):
        return self.grund(recht) == ""

    def verlangen(self, recht, objekt=""):
        g = self.grund(recht)
        if g:
            s = self.sitzungen.aktuell
            self.protokoll.schreiben(P.ZUGRIFF_VERWEIGERT, s.kuerzel if s else "", objekt or recht, "abgelehnt",
                                     recht=recht, grund=g)
            raise ZugangVerweigert(recht, g)
        return True

    # -------------------------------------------------------------- Benutzer
    def benutzer_anmelden(self, konto, geheim, totp_code=None, sperre=None, jetzt=None):
        """konto: dict(id, kuerzel, name, hash, status, rollen, plus, minus, totp, totp_zuletzt, passwort_aendern,
        minuten) oder None (unbekannt). sperre: authentifizierung.Sperre dieses Kontos."""
        kuerzel = (konto or {}).get("kuerzel", "")
        if sperre is not None:
            w = sperre.wartezeit()
            if w:
                return Ergebnis(False, f"Zu viele Fehlversuche. Bitte {auth.warte_text(w)} warten.", warten=w)
        if not konto or not auth.pruefen(geheim, konto.get("hash")):
            warten = sperre.fehlschlag() if sperre is not None else 0
            self.protokoll.schreiben(P.ANMELDUNG_FEHLER, kuerzel, ergebnis="falsch")
            text = FALSCH + (f" Nächster Versuch in {auth.warte_text(warten)}." if warten else "")
            return Ergebnis(False, text, warten=warten)
        status = konto.get("status") or STATUS_AKTIV
        if status != STATUS_AKTIV:
            self.protokoll.schreiben(P.ANMELDUNG_FEHLER, kuerzel, ergebnis=status)
            return Ergebnis(False, "Dieses Benutzerkonto ist gesperrt. Bitte an den Administrator wenden."
                            if status == STATUS_GESPERRT else "Dieses Benutzerkonto ist deaktiviert.")
        schritt = -1
        if konto.get("totp"):
            if not totp_code:
                return Ergebnis(False, "Bitte den Einmalcode aus der Authenticator-App eingeben.",
                                zweiter_faktor_fehlt=True)
            schritt = auth.totp_pruefen(konto["totp"], totp_code, jetzt, int(konto.get("totp_zuletzt", -1)))
            if schritt is None:
                warten = sperre.fehlschlag() if sperre is not None else 0
                self.protokoll.schreiben(P.ANMELDUNG_FEHLER, kuerzel, ergebnis="einmalcode")
                return Ergebnis(False, "Der Einmalcode stimmt nicht oder wurde schon benutzt.", warten=warten,
                                zweiter_faktor_fehlt=True)
        if sperre is not None:
            sperre.erfolg()
        rechte = B.wirksame_rechte(konto.get("rollen"), konto.get("plus"), konto.get("minus"), self.eigene_rollen)
        s = self.sitzungen.anlegen(konto.get("id") or kuerzel, kuerzel, konto.get("name", ""),
                                   konto.get("rollen") or (), rechte, False, self.installation, self.arbeitsplatz,
                                   konto.get("minuten"))
        neu = auth.hash_bilden(geheim) if auth.braucht_umstellung(konto.get("hash")) else ""
        self.protokoll.schreiben(P.ANMELDUNG_OK, kuerzel, rollen=list(konto.get("rollen") or ()))
        return Ergebnis(True, sitzung=s, neuer_hash=neu, passwort_aendern=bool(konto.get("passwort_aendern")),
                        totp_schritt=schritt)

    # -------------------------------------------------------------- Entwickler
    def entwickler_anmelden(self, daten, passwort, von_stick, totp_code=None, totp_geheimnis="", totp_zuletzt=-1,
                            sperre=None, gesperrt=(), schluessel=None, heute=None, spaetestes=None, jetzt=None):
        """Anmeldung mit Entwickler-Ausweis. von_stick: Ausweis kommt vom Wechseldatenträger (Besitz); sonst ist es
        die hier hinterlegte Kopie (dann gilt ihr Einmalcode, wenn eingerichtet). sperre.stand() schützt vor alten
        Kopien mit altem Passwort."""
        if sperre is not None:
            w = sperre.wartezeit()
            if w:
                return Ergebnis(False, f"Zu viele Fehlversuche. Bitte {auth.warte_text(w)} warten.", warten=w)
        try:
            daten, inhalt = aw.pruefen(daten, schluessel, heute, gesperrt, self.umgebung, self.installation,
                                       spaetestes)
        except aw.AusweisFehler as e:
            self.protokoll.schreiben(P.ANMELDUNG_FEHLER, "Entwickler", ergebnis="ausweis", grund=str(e))
            return Ergebnis(False, str(e))
        aid = inhalt["ausweis_id"]
        if sperre is not None and aw.stand(daten) < sperre.stand(aid):
            self.protokoll.schreiben(P.ANMELDUNG_FEHLER, "Entwickler", aid, "alter_stand")
            return Ergebnis(False, "Diese Kopie des Ausweises hat ein altes Passwort. Bitte den aktuellen Ausweis "
                                   "verwenden.")
        seed = aw.tresor_oeffnen(daten, passwort)
        if seed is None:
            warten = sperre.fehlschlag() if sperre is not None else 0
            self.protokoll.schreiben(P.ANMELDUNG_FEHLER, "Entwickler", aid, "falsch")
            return Ergebnis(False, FALSCH + (f" Nächster Versuch in {auth.warte_text(warten)}." if warten else ""),
                            warten=warten)
        schritt = -1
        if not von_stick:
            if not totp_geheimnis:
                pass        # hinterlegt ohne Einmalcode (E2a: Einmalcode optional)
            elif not totp_code:
                return Ergebnis(False, "Bitte den Einmalcode aus der Authenticator-App eingeben.",
                                zweiter_faktor_fehlt=True)
            else:
                schritt = auth.totp_pruefen(totp_geheimnis, totp_code, jetzt, totp_zuletzt)
                if schritt is None:
                    warten = sperre.fehlschlag() if sperre is not None else 0
                    self.protokoll.schreiben(P.ANMELDUNG_FEHLER, "Entwickler", aid, "einmalcode")
                    return Ergebnis(False, "Der Einmalcode stimmt nicht oder wurde schon benutzt.", warten=warten,
                                    zweiter_faktor_fehlt=True)
        # Besitz des Anmeldeschlüssels nachweisen wie gegenüber einem Server (gleicher Weg, eine Logik)
        z = datetime.datetime.now(datetime.timezone.utc) if jetzt is None else \
            datetime.datetime.fromtimestamp(jetzt, datetime.timezone.utc)
        anfrage = aw.anfrage_signieren(seed, inhalt, self.installation, z)
        try:
            aw.anfrage_pruefen(anfrage, inhalt, self.installation, z, self.gesehen)
        except aw.AusweisFehler as e:
            return Ergebnis(False, str(e))
        if sperre is not None:
            sperre.erfolg()
            sperre.stand_merken(aid, aw.stand(daten))
        s = self.sitzungen.anlegen(aid, "ENTWICKLER", inhalt.get("name") or "Entwickler", (B.ENTWICKLER,),
                                   frozenset(B.NAMEN) | frozenset(B.NUR_ENTWICKLER), True, self.installation,
                                   self.arbeitsplatz, ausweis=aid, anfrage=anfrage)
        self.protokoll.schreiben(P.ENTWICKLER_ZUGRIFF, "ENTWICKLER", aid, "ok",
                                 weg="stick" if von_stick else "hinterlegt", umgebung=self.umgebung)
        return Ergebnis(True, sitzung=s, totp_schritt=schritt)

    # -------------------------------------------------------------- Abmelden, wechseln, entsperren
    def abmelden(self, wechsel=False):
        s = self.sitzungen.beenden()
        if s:
            self.protokoll.schreiben(P.BENUTZERWECHSEL if wechsel else P.ABMELDUNG, s.kuerzel)
        return s

    def ablauf_pruefen(self):
        if self.sitzungen.ablauf_pruefen():
            s = self.sitzungen.aktuell
            self.protokoll.schreiben(P.SITZUNG_ABGELAUFEN, s.kuerzel if s else "")
            return True
        return False

    @property
    def sitzung(self):
        return self.sitzungen.aktuell


def darf(recht):
    return True if AKTUELL is None else AKTUELL.darf(recht)


def verlangen(recht, objekt=""):
    return True if AKTUELL is None else AKTUELL.verlangen(recht, objekt)
