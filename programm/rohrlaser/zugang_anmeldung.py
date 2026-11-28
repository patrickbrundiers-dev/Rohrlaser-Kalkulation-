"""Zugangssystem Paket C: Anmeldung eines laufenden Programms (ohne Qt; das Fenster ist zugang_fenster.py).

Eine Anmeldung je Programm. Sie verbindet die Prüfstelle (zugang_pruefstelle) mit dieser Datenbank (zugang_daten):

- Pflicht (E5a): sobald es ein aktives Konto mit Passwort oder PIN gibt, meldet sich bei jedem Start jemand an.
  Kein automatisches Anmelden; gemerkt wird je Arbeitsplatz nur das Kürzel des letzten Benutzers (Einstellung
  LETZTER in der eigenen Datendatei, nicht im Abgleich), nie ein Passwort.
- Benutzer: Passwort oder Werkstatt-PIN, danach Einmalcode, wenn das Konto ihn verlangt (E3a). Fehlversuche je Kürzel
  in zg_konto_stand (zugang_daten.Sperre, übersteht Neustart).
- Entwickler (E1a/E2a): Ausweis vom USB-Stick (Besitz) oder die an dieser Installation hinterlegte Kopie (dann der
  Einmalcode, wenn bei der Hinterlegung eingerichtet). Kein eingebautes Passwort; geprüft wird mit dem öffentlichen
  Lizenzschlüssel, der Sperrliste und dem Datum der Lizenzstelle.
- Sperre nach Inaktivität (E4a): ablauf_pruefen() sperrt; entsperren() nur mit dem Geheimnis desselben Benutzers.
- Übergang bis Paket D: Die bisherigen Rechteprüfungen (rollen.stufe, admin_schutz.ist_admin) lesen das angemeldete
  Kürzel aus rollen.SITZUNG; die Anmeldung setzt es. Der Entwickler wird zusätzlich als Hauptadmin freigeschaltet
  (ohne Signaturschlüssel: Admin-Vorgaben signieren kann er so nicht).
"""
import time
from pathlib import Path

from . import protokoll as _protokoll
from . import zugang_authentifizierung as auth
from . import zugang_ausweis as aw
from . import zugang_daten as D
from . import zugang_protokoll as P
from . import zugang_pruefstelle as PS

LETZTER = "zg_letzter_benutzer"
ENTWICKLER_SPERRE = "entwickler_anmeldung.json"
ORDNER_PROTOKOLL = "Sicherheit"


class Anmeldung:
    def __init__(self, db, lizenz_stelle=None, ordner=None, uhr=time.time, stick_wurzeln=None):
        self.db = db
        self.lizenz = lizenz_stelle
        self.uhr = uhr
        self.stick_wurzeln = stick_wurzeln           # Tests: Ordner statt echter Wechseldatenträger
        basis = Path(ordner) if ordner else (Path(db.pfad).parent if getattr(db, "pfad", None) else None)
        self.ordner = basis
        self.ps = D.pruefstelle(db, basis / ORDNER_PROTOKOLL if basis else None)
        self.ausweis_quelle = None                   # Pfad/daten des zuletzt benutzten Ausweises
        self._daten = None                           # Ausweis der Entwickler-Sitzung (für entsperren)

    # -------------------------------------------------------------- Auswahl
    def konten(self):
        return D.konten(self.db)

    def pflicht(self):
        """E5a: Anmelden muss man, sobald ein aktives Konto ein Passwort oder eine PIN hat."""
        return any(k["status"] == "aktiv" and (k["hash"] or k["pin"]) for k in self.konten().values())

    def auswahl(self):
        """[(Kürzel, Anzeige)] der aktiven Konten mit Passwort oder PIN, nach Name."""
        ks = [k for k in self.konten().values() if k["status"] == "aktiv" and (k["hash"] or k["pin"])]
        return [(k["kuerzel"], f"{k['name']} ({k['kuerzel']})")
                for k in sorted(ks, key=lambda k: (k["name"] or k["kuerzel"]).lower())]

    def letzter(self):
        k = self.db.einstellung(LETZTER) if self.db is not None else None
        return str(k or "")

    def _letzter_setzen(self, kuerzel):
        if getattr(self.db, "nur_lesen", ""):
            return
        try:
            self.db.einstellung_setzen(LETZTER, str(kuerzel))
        except Exception as e:      # noqa: BLE001 – Merken ist Komfort
            _protokoll.warnung(f"Anmeldung: letzter Benutzer nicht gemerkt ({e})")

    # -------------------------------------------------------------- Benutzer
    def anmelden(self, kuerzel, geheim, totp_code=None):
        """Mit Kürzel und Passwort oder PIN (und Einmalcode) anmelden. Ergebnis: zugang_pruefstelle.Ergebnis."""
        from .teilen import kuerzel_sauber
        k = kuerzel_sauber(kuerzel)
        konto = self.konten().get(k)
        feld = "hash"
        if konto and konto["pin"] and not auth.pruefen(geheim, konto["hash"]) and auth.pruefen(geheim, konto["pin"]):
            konto, feld = dict(konto, hash=konto["pin"]), "pin"
        e = self.ps.benutzer_anmelden(konto if konto else dict(kuerzel=k), geheim, totp_code,
                                      sperre=D.Sperre(self.db, k, self.uhr), jetzt=self.uhr())
        if not konto and not e.ok:
            return e
        if e.ok:
            D.anmeldung_merken(self.db, k, self.ps.arbeitsplatz, e.totp_schritt)
            self._letzter_setzen(k)
            if e.neuer_hash and self._konten_schreibbar():
                D.konto_speichern(self.db, k, **({"hash_": e.neuer_hash} if feld == "hash" else {}))
                if feld == "pin":
                    self._pin_umstellen(k, e.neuer_hash)
            self._alt_setzen(k)
            PS.AKTUELL = self.ps
        return e

    def _konten_schreibbar(self):
        """Hash-Umstellung nur, wo die Konten hier gepflegt werden (ohne Admin-Schutz); sonst überschreibt die
        signierte Vorgabe sie ohnehin, und die Umstellung macht der Admin beim nächsten Speichern."""
        from . import admin_schutz
        return not getattr(self.db, "nur_lesen", "") and not admin_schutz.aktiv(self.db)

    def _pin_umstellen(self, kuerzel, neu):
        from . import rollen as R
        liste = R.benutzer(self.db)
        if kuerzel in liste:
            liste[kuerzel]["pin"] = neu
            self.db.einstellung_setzen(D.BENUTZER, liste)

    # -------------------------------------------------------------- Entwickler
    def ausweis_finden(self):
        """(daten, von_stick, totp_geheimnis, Pfad/Text) des Ausweises: zuerst USB-Stick, sonst hier hinterlegt;
        (None, False, '', Grund) ohne Ausweis."""
        p = aw.auf_stick_suchen(self.stick_wurzeln)
        if p is not None:
            try:
                return aw.lesen(p), True, "", str(p)
            except (OSError, ValueError, aw.L.LizenzFehler) as e:
                return None, False, "", f"Ausweis auf dem Stick nicht lesbar: {e}"
        if self.lizenz is not None:
            h = aw.hinterlegt(self.lizenz.ordner)
            if h and h.get("installation") == self.ps.installation:
                return h["ausweis"], False, h.get("totp") or "", "an dieser Installation hinterlegt"
        return None, False, "", ("Kein Entwickler-Ausweis gefunden. Bitte den USB-Stick mit der Datei "
                                 f"{aw.DATEI} einstecken.")

    def _entwickler_sperre(self):
        from . import hauptadmin as H
        orte = [H.zweiter_ort().with_name(ENTWICKLER_SPERRE)]
        if self.lizenz is not None:
            orte.insert(0, Path(self.lizenz.ordner) / ENTWICKLER_SPERRE)
        return H.Sperre(orte, uhr=self.uhr)

    def entwickler_anmelden(self, passwort, totp_code=None, heute=None):
        daten, von_stick, totp, wo = self.ausweis_finden()
        if daten is None:
            return PS.Ergebnis(False, wo)
        gesperrt, schluessel, spaetestes = self._lizenzdaten()
        sperre = self._entwickler_sperre()
        st_key = "entwickler_totp"
        e = self.ps.entwickler_anmelden(daten, passwort, von_stick, totp_code, totp,
                                        int(self.db.einstellung(st_key) or -1) if self.db is not None else -1,
                                        sperre=sperre, gesperrt=gesperrt, schluessel=schluessel, heute=heute,
                                        spaetestes=spaetestes, jetzt=self.uhr())
        if e.ok:
            self.ausweis_quelle, self._daten = wo, daten
            if e.totp_schritt is not None and e.totp_schritt >= 0 and not getattr(self.db, "nur_lesen", ""):
                self.db.einstellung_setzen(st_key, int(e.totp_schritt))
            self._alt_setzen("", entwickler=True)
            PS.AKTUELL = self.ps
        return e

    def _lizenzdaten(self):
        from . import lizenz as L
        if self.lizenz is None:
            return (), None, None
        sperr = L.sperrliste_pruefen(Path(self.lizenz.ordner) / L.SPERRLISTE, self.lizenz.schluessel) or {}
        return tuple(sperr.get("gesperrt") or ()), self.lizenz.schluessel, self.lizenz._spaetestes()

    def ausweis_hinterlegen(self, totp_geheimnis=""):
        """Nur in einer Entwickler-Sitzung vom Stick: Ausweis an dieser Installation hinterlegen (E2a)."""
        s = self.ps.sitzung
        if not (s and s.entwickler and s.aktiv) or self._daten is None or self.lizenz is None:
            return "Hinterlegen geht nur nach Anmeldung mit dem Ausweis vom USB-Stick."
        if "hinterlegt" in str(self.ausweis_quelle):
            return "Der Ausweis ist hier schon hinterlegt."
        aw.hinterlegen(self.lizenz.ordner, self._daten, self.ps.installation, totp_geheimnis,
                       schluessel=self.lizenz.schluessel)
        self.ps.protokoll.schreiben(P.KONFIGURATION_GEAENDERT, "ENTWICKLER", "Ausweis hinterlegt",
                                    einmalcode=bool(totp_geheimnis))
        return ""

    # -------------------------------------------------------------- Übergang zu den bisherigen Prüfungen
    def _alt_setzen(self, kuerzel, entwickler=False, abmelden=False):
        from . import admin_schutz, rollen
        if rollen.SITZUNG is not None:
            rollen.SITZUNG.kuerzel = kuerzel
        if admin_schutz.SITZUNG is not None:
            if entwickler:
                admin_schutz.SITZUNG.freischalten(admin_schutz.HAUPTADMIN)
            elif abmelden and admin_schutz.SITZUNG.freigeschaltet:
                admin_schutz.SITZUNG.sperren()       # Abmelden/Wechsel: Admin-Freischaltung des Vorgängers endet
        if abmelden and self.lizenz is not None:
            self.lizenz.hauptadmin_ok = self.lizenz.admin_ok = False
            self.lizenz.hauptadmin_seed = None

    # -------------------------------------------------------------- Sitzung
    @property
    def sitzung(self):
        return self.ps.sitzung

    def angemeldet(self):
        s = self.ps.sitzung
        return bool(s and not s.beendet)

    def eingabe(self):
        self.ps.sitzungen.eingabe()

    def ablauf_pruefen(self):
        return self.ps.ablauf_pruefen()

    def sperren(self):
        if self.ps.sitzungen.sperren():
            s = self.ps.sitzung
            self.ps.protokoll.schreiben(P.SITZUNG_ABGELAUFEN, s.kuerzel, "von Hand gesperrt")
            return True
        return False

    def gesperrt(self):
        s = self.ps.sitzung
        return bool(s and s.gesperrt and not s.beendet)

    def entsperren(self, geheim, totp_code=None):
        """Gesperrte Sitzung mit dem Geheimnis desselben Benutzers wieder freigeben. Ergebnis: Fehlertext oder ''."""
        s = self.ps.sitzung
        if not s or s.beendet:
            return "Nicht angemeldet."
        if s.entwickler:
            sperre = self._entwickler_sperre()
            w = sperre.wartezeit()
            if w:
                return f"Zu viele Fehlversuche. Bitte {auth.warte_text(w)} warten."
            ok = self._daten is not None and aw.tresor_oeffnen(self._daten, geheim) is not None
        else:
            sperre = D.Sperre(self.db, s.kuerzel, self.uhr)
            w = sperre.wartezeit()
            if w:
                return f"Zu viele Fehlversuche. Bitte {auth.warte_text(w)} warten."
            konto = self.konten().get(s.kuerzel) or {}
            ok = konto.get("status") == "aktiv" and any(
                konto.get(f) and auth.pruefen(geheim, konto[f]) for f in ("hash", "pin"))
            if ok and konto.get("totp"):
                if not totp_code:
                    return "Bitte den Einmalcode aus der Authenticator-App eingeben."
                schritt = auth.totp_pruefen(konto["totp"], totp_code, self.uhr(), int(konto.get("totp_zuletzt", -1)))
                ok = schritt is not None
                if ok:
                    D.anmeldung_merken(self.db, s.kuerzel, self.ps.arbeitsplatz, schritt)
        if not ok:
            sperre.fehlschlag()
            self.ps.protokoll.schreiben(P.ANMELDUNG_FEHLER, s.kuerzel, ergebnis="entsperren")
            return PS.FALSCH
        sperre.erfolg()
        self.ps.sitzungen.entsperren()
        self.ps.protokoll.schreiben(P.ANMELDUNG_OK, s.kuerzel, "entsperrt")
        return ""

    def abmelden(self, wechsel=False):
        s = self.ps.abmelden(wechsel)
        self._daten = None
        self._alt_setzen("", abmelden=True)
        return s

    def text(self):
        """Statuszeile: wer ist angemeldet."""
        s = self.ps.sitzung
        if not s or s.beendet:
            return "Nicht angemeldet"
        from . import zugang_berechtigung as B
        rolle = ", ".join(B.ROLLE_TITEL.get(r, r) for r in s.rollen) or "ohne Rolle"
        return f"{s.name} ({rolle})" + (" – gesperrt" if s.gesperrt else "")
