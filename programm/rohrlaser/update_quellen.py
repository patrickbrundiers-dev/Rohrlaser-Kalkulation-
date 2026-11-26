"""Woher das Update kommt (Auftrag Patrick 19.11.2026): Internet, Update-Ordner (Netzwerkordner, USB-Stick) oder
eine Update-Datei. Keine Abhängigkeit von einem einzigen Kanal, aber auch keine zweite Update-Logik: jede Quelle
liefert nur die Adresse einer Dateiliste, alles Weitere (Signatur, Prüfsummen, Laden, Austauschen, Zurückstellen)
macht update.py wie beim Online-Update.

Einstellungen (nur dieser Arbeitsplatz, Update-Center → Einstellungen):
- update_quelle: „automatisch“ (Vorgabe: Update-Ordner, wenn erreichbar, sonst Internet; bei gleichem Stand der
  Ordner), „ordner“ (nur der Update-Ordner, nie Internet) oder „internet“ (nur Internet, wie bis 0.9.40x).
  Legt der Admin im Update-Ordner „nur aus dem Ordner“ fest (Freigabe.json), fragt kein Platz das Internet.
- update_ordner: Update-Ordner; leer = Unterordner „Updates“ im gemeinsamen Ordner (falls eingerichtet).
- update_proxy: „system“ (Windows-Einstellung), „aus“ oder „Rechner:Port“; update_zertifikat: Datei mit dem
  Stammzertifikat der Firma (PEM), zusätzlich zum Windows-Zertifikatsspeicher (update_netz.py).
- update_beim_start: „ja“ (Vorgabe) sucht beim Start still nach einer neuen Version.

Verlauf: jede Suche mit Ergebnis, jedes Laden und jedes Einspielen steht in Daten/Protokoll/update_verlauf.json
(höchstens VERLAUF_MAX Einträge) und – wenn ein Update-Ordner da ist – als Rückmeldung dieses Platzes dort.

Ohne Qt.
"""
import datetime
import json
import os
import shutil
from pathlib import Path

from . import update, update_netz, update_verteilen

AUTOMATISCH, ORDNER, INTERNET = "automatisch", "ordner", "internet"
MODI = ((AUTOMATISCH, "Automatisch: Update-Ordner, sonst Internet"), (ORDNER, "Nur Update-Ordner (kein Internet)"),
        (INTERNET, "Nur Internet"))
UPDATES = "Updates"                 # Unterordner im gemeinsamen Ordner (Vorgabe für den Update-Ordner)
VERLAUF = "update_verlauf.json"
VERLAUF_MAX = 200


class Quelle:
    """Eine Quelle: art (internet, ordner, datei), name für die Anzeige, ort (Adresse bzw. Pfad)."""
    art = "internet"

    def __init__(self, ort, name=None):
        self.ort = str(ort)
        self.name = name or self.ort

    def adresse(self):
        """Adresse bzw. Pfad der Dateiliste (für update.online_liste und update.laden)."""
        return self.ort

    def liste(self):
        """Dateiliste laden und prüfen (Signatur, Aufbau) – update.online_liste."""
        return update.online_liste(self.adresse())

    def vorbereiten(self, online, plan):
        """Vor update.laden: was die Quelle braucht, damit die Pakete unter adresse() liegen (Update-Datei)."""

    def paket_holen(self, online, paket, ziel, weiter=None, melden=None):
        """Ein Paket nach ziel (für update_verteilen.bereitstellen)."""
        info = (online.get("pakete") or {}).get(paket) or {}
        url = update._ist_url(self.adresse())
        update.holen(update.paket_adresse(self.adresse(), online, paket), ziel, weiter,
                     timeout=update.DOWNLOAD_TIMEOUT_S, grenze=info.get("groesse", update.PAKET_GROESSE_MAX),
                     warten=update.WIEDERHOLEN_S if url else (), melden=melden)

    def sperrliste(self):
        try:
            return update.holen(update.daneben(self.adresse(), update.SPERRLISTE), timeout=15, grenze=1 << 20)
        except update.UpdateFehler:
            return None

    def text(self):
        return {"internet": "Internet", "ordner": "Update-Ordner", "datei": "Update-Datei"}[self.art] + f": {self.name}"

    def __repr__(self):
        return f"<Quelle {self.art} {self.ort}>"


class InternetQuelle(Quelle):
    art = "internet"

    def __init__(self, ort=update.ADRESSE):
        super().__init__(ort, "GitHub (Rohrlaser-Updates)" if ort == update.ADRESSE else ort)


class OrdnerQuelle(Quelle):
    art = "ordner"

    def adresse(self):
        p = update_verteilen.liste_im_ordner(self.ort)
        if p is None:
            raise update.UpdateFehler(f"Im Update-Ordner {self.ort} liegt kein Update (Datei {update.DATEILISTE} "
                                      "fehlt oder der Ordner ist nicht erreichbar).")
        return str(p)

    def freigabe(self):
        """Vorgaben des Admins in diesem Ordner (update_verteilen.freigabe_lesen)."""
        return update_verteilen.freigabe_lesen(self.ort)


class DateiQuelle(Quelle):
    """Update-Datei (.rlupdate): Dateiliste und Signatur werden nach arbeit ausgepackt, die gebrauchten Pakete
    erst vor dem Laden (vorbereiten)."""
    art = "datei"

    def __init__(self, ort, arbeit):
        super().__init__(ort, Path(ort).name)
        self.arbeit = Path(arbeit)
        self._liste = None

    def adresse(self):
        if self._liste is None:
            shutil.rmtree(self.arbeit, ignore_errors=True)
            self._liste = str(update_verteilen.datei_auspacken(self.ort, self.arbeit, namen=()))
        return self._liste

    def vorbereiten(self, online, plan):
        update_verteilen.datei_auspacken(self.ort, self.arbeit, namen=plan["pakete"])

    def paket_holen(self, online, paket, ziel, weiter=None, melden=None):
        update_verteilen.datei_auspacken(self.ort, self.arbeit, namen=[paket])
        os.replace(self.arbeit / paket, ziel)
        if weiter:
            weiter(((online.get("pakete") or {}).get(paket) or {}).get("groesse", 0))


# ------------------------------------------------------------------ Einstellungen
def einstellungen(db):
    """Update-Einstellungen dieses Arbeitsplatzes (mit Vorgaben)."""
    def e(name, vorgabe=""):
        try:
            w = db.einstellung(name) if db is not None else None
        except Exception:       # noqa: BLE001 – Datenbank nicht offen
            w = None
        return vorgabe if w in (None, "") else w
    modus = e("update_quelle", AUTOMATISCH)
    return dict(quelle=modus if modus in dict(MODI) else AUTOMATISCH, ordner=str(e("update_ordner")).strip(),
                proxy=str(e("update_proxy", update_netz.SYSTEM)), zertifikat=str(e("update_zertifikat")).strip(),
                beim_start=e("update_beim_start", "ja") != "nein")


def speichern(db, quelle=None, ordner=None, proxy=None, zertifikat=None, beim_start=None):
    """Einstellungen prüfen und speichern; Proxy/Zertifikat gelten sofort (update_netz). Fehler -> ValueError."""
    if proxy is not None or zertifikat is not None:
        jetzt = einstellungen(db)
        update_netz.setzen(jetzt["proxy"] if proxy is None else proxy,
                           jetzt["zertifikat"] if zertifikat is None else zertifikat)
    if quelle is not None:
        if quelle not in dict(MODI):
            raise ValueError(f"Unbekannte Update-Quelle {quelle}")
        db.einstellung_setzen("update_quelle", quelle)
    if ordner is not None:
        db.einstellung_setzen("update_ordner", str(ordner).strip())
    if proxy is not None:
        db.einstellung_setzen("update_proxy", update_netz.proxy_pruefen(proxy))
    if zertifikat is not None:
        db.einstellung_setzen("update_zertifikat", str(zertifikat).strip())
    if beim_start is not None:
        db.einstellung_setzen("update_beim_start", "ja" if beim_start else "nein")


def netz_anwenden(db):
    """Proxy und Zertifikat aus den Einstellungen setzen (beim Start). Ungültige Werte: Windows-Vorgabe, Hinweis."""
    e = einstellungen(db)
    try:
        update_netz.setzen(e["proxy"], e["zertifikat"])
        return None
    except update_netz.NetzFehler as fehler:
        update_netz.setzen()
        return str(fehler)


def update_ordner(db):
    """Eingestellter Update-Ordner oder Vorgabe <gemeinsamer Ordner>\\Updates (Serverbetrieb: <Ablage am
    Server>\\Updates); None ohne beides."""
    e = einstellungen(db)
    if e["ordner"]:
        return Path(e["ordner"])
    try:
        from . import teilen
        o = teilen.dateiordner(db)
    except Exception:       # noqa: BLE001
        o = None
    return Path(o) / UPDATES if o else None


def quellen(db, internet=update.ADRESSE):
    """Quellen in der Reihenfolge der Suche (Einstellung update_quelle, Vorgabe des Admins nur_ordner)."""
    e = einstellungen(db)
    o = update_ordner(db)
    ordner = OrdnerQuelle(o) if o else None
    nur_ordner = e["quelle"] == ORDNER or bool(ordner and ordner.freigabe().get("nur_ordner"))
    erg = []
    if ordner is not None and e["quelle"] != INTERNET:
        erg.append(ordner)
    if not nur_ordner:
        erg.append(InternetQuelle(internet))
    return erg


# ------------------------------------------------------------------ Suche über alle Quellen
def suchen(quellen_liste):
    """Jede Quelle fragen. Ergebnis: dict(beste=(Quelle, Dateiliste) oder None, ergebnisse=[(Quelle, Liste, Fehler)]).
    Beste = höchster Stand mit gültiger Signatur; bei gleichem Stand die erste Quelle (der Ordner vor dem
    Internet)."""
    ergebnisse, beste = [], None
    for q in quellen_liste:
        try:
            liste = q.liste()
            ergebnisse.append((q, liste, None))
            if beste is None or int(liste.get("stand") or 0) > int(beste[1].get("stand") or 0):
                beste = (q, liste)
        except update.UpdateFehler as e:
            ergebnisse.append((q, None, str(e)))
    return dict(beste=beste, ergebnisse=ergebnisse)


# ------------------------------------------------------------------ Verlauf
def verlauf_pfad(db):
    try:
        return Path(db.pfad).parent / "Protokoll" / VERLAUF
    except (AttributeError, TypeError):
        return None


def verlauf_lesen(pfad):
    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8")) if pfad else []
    except (OSError, ValueError):
        return []
    return [e for e in d if isinstance(e, dict)] if isinstance(d, list) else []


def verlauf_schreiben(pfad, **eintrag):
    """Eintrag vorn anfügen (zeit, art, von, nach, quelle, ergebnis, fehler …). Fehler zählen nicht."""
    if not pfad:
        return None
    e = dict(zeit=datetime.datetime.now().isoformat(timespec="seconds"), **eintrag)
    if e.get("fehler"):
        e["fehler"] = update_netz.ohne_zugang(str(e["fehler"]))[:1000]
    try:
        alt = verlauf_lesen(pfad)
        Path(pfad).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(pfad).with_name(Path(pfad).name + ".neu")
        tmp.write_text(json.dumps([e] + alt[:VERLAUF_MAX - 1], ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, pfad)
    except OSError:
        return None
    return e


def letzte_erfolgreiche(pfad):
    """Letzter Eintrag mit ergebnis „ok“ (eingespielt) oder None."""
    return next((e for e in verlauf_lesen(pfad) if e.get("art") == "eingespielt" and e.get("ergebnis") == "ok"), None)
