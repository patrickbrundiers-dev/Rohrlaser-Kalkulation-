"""Rollen und Einzelrechte (Paket A: Katalog und Regeln; Paket D: Prüfung an allen Kernfunktionen).

Ein Einzelrecht ist ein fester Name (z. B. 'angebot.freigeben'). Eine Rolle ist ein Bündel von Einzelrechten. Je
Benutzer gilt: Rechte aller seiner Rollen, plus einzeln gegebene, minus einzeln entzogene. Rollen und Bündel kann der
Administrator später erweitern (eigene Rollen); der Katalog der Einzelrechte wächst mit dem Programm.

Die Rolle ENTWICKLER steht in keiner Tabelle: Sie entsteht nur durch einen gültigen Entwickler-Ausweis (ausweis.py)
und darf alles, auch Rechte, die es heute noch nicht gibt. vergabe_fehler() verhindert, dass jemand Rechte vergibt,
die er selbst nicht hat, oder die Rolle Entwickler zuweist.

Jedes Einzelrecht kann zu einem Lizenz-Modul gehören (module.py); dann gilt es nur, wenn die Lizenz das Modul
freischaltet (pruefstelle). Ohne Qt.
"""
from collections import namedtuple

Recht = namedtuple("Recht", "name titel gruppe modul schreibt")

ENTWICKLER, SYSTEMADMIN, ADMIN, KALK_PRO, KALK_STANDARD, MITARBEITER, NUR_LESEN = (
    "entwickler", "systemadmin", "admin", "kalkulator_pro", "kalkulator_standard", "mitarbeiter", "nur_lesen")

RECHTE = (
    Recht("angebot.sehen", "Angebote ansehen", "Angebote", None, False),
    Recht("angebot.erstellen", "Angebote erstellen", "Angebote", None, True),
    Recht("angebot.bearbeiten", "Angebote bearbeiten", "Angebote", None, True),
    Recht("angebot.freigeben", "Angebote freigeben", "Angebote", None, True),
    Recht("angebot.loeschen", "Angebote löschen", "Angebote", None, True),
    Recht("preise.ek_sehen", "Einkaufspreise anzeigen", "Preise", None, False),
    Recht("preise.vk_bearbeiten", "Verkaufspreise bearbeiten", "Preise", None, True),
    Recht("stamm.material", "Materialstammdaten ändern", "Stammdaten", None, True),
    Recht("stamm.lieferanten", "Lieferanten bearbeiten", "Stammdaten", "einkauf", True),
    Recht("stamm.maschinen", "Maschinenparameter ändern", "Stammdaten", None, True),
    Recht("stamm.faktoren", "Kalkulationsfaktoren ändern", "Stammdaten", None, True),
    Recht("import.step", "STEP-Dateien importieren", "Technik", None, True),
    Recht("cad.bearbeiten", "CAD-Daten bearbeiten", "Technik", None, True),
    Recht("editor.3d", "3D-Editor verwenden", "Technik", None, True),
    Recht("nesting.verwenden", "Verschachtelung und Optimierung", "Technik", None, True),
    Recht("fracht.verwenden", "Verpackungs- und Frachtberechnung", "Technik", None, True),
    Recht("baugruppen.verwenden", "Schweißbaugruppen und Baugruppen", "Technik", "baugruppen", True),
    Recht("blech.verwenden", "Bleche und Kantteile", "Technik", "blech", True),
    Recht("zukauf.verwenden", "Zukaufteile und Materialanfrage", "Einkauf", "einkauf", True),
    Recht("auftrag.sehen", "Aufträge ansehen", "Auftrag", "auftrag", False),
    Recht("auftrag.bearbeiten", "Aufträge bearbeiten", "Auftrag", "auftrag", True),
    Recht("av.bearbeiten", "Arbeitsvorbereitung", "Auftrag", "auftrag", True),
    Recht("produktion.bearbeiten", "Produktion und Rückmeldung", "Auftrag", "auftrag", True),
    Recht("qs.bearbeiten", "Qualitätskontrolle", "Auftrag", "auftrag", True),
    Recht("versand.bearbeiten", "Auslieferung und Versand", "Auftrag", "auftrag", True),
    Recht("auswertung.sehen", "Auswertungen", "Auswertung", None, False),
    Recht("daten.import", "Daten importieren", "Daten", None, True),
    Recht("daten.export", "Daten exportieren", "Daten", None, False),
    Recht("benutzer.verwalten", "Benutzer verwalten", "Verwaltung", None, True),
    Recht("rollen.verwalten", "Rollen und Rechte verwalten", "Verwaltung", None, True),
    Recht("arbeitsplaetze.verwalten", "Arbeitsplätze verwalten", "Verwaltung", None, True),
    Recht("lizenz.verwalten", "Lizenzverwaltung öffnen", "Verwaltung", None, True),
    Recht("system.einstellungen", "Systemeinstellungen bearbeiten", "Verwaltung", None, True),
    Recht("datenbank.verwalten", "Datenbankverwaltung", "Verwaltung", None, True),
    Recht("protokoll.sehen", "Protokolle und Diagnose ansehen", "Verwaltung", None, False),
)
RECHT = {r.name: r for r in RECHTE}
NAMEN = tuple(r.name for r in RECHTE)
NUR_ENTWICKLER = ("entwickler.dashboard",)       # nie über Rollen vergebbar

_TECHNIK = ("import.step", "cad.bearbeiten", "editor.3d", "nesting.verwenden", "fracht.verwenden",
            "baugruppen.verwenden", "blech.verwenden", "zukauf.verwenden")
_ANGEBOT = ("angebot.sehen", "angebot.erstellen", "angebot.bearbeiten")
_AUFTRAG = ("auftrag.sehen", "auftrag.bearbeiten", "av.bearbeiten", "produktion.bearbeiten", "qs.bearbeiten",
            "versand.bearbeiten")
_VERWALTUNG_SYS = ("benutzer.verwalten", "rollen.verwalten", "arbeitsplaetze.verwalten", "lizenz.verwalten",
                   "system.einstellungen", "datenbank.verwalten", "protokoll.sehen")
_SEHEN = tuple(r.name for r in RECHTE if not r.schreibt and r.name != "preise.ek_sehen")

ROLLEN = {
    SYSTEMADMIN: ("Systemadministrator", NAMEN),
    ADMIN: ("Administrator", tuple(n for n in NAMEN if n not in ("lizenz.verwalten", "datenbank.verwalten",
                                                                  "arbeitsplaetze.verwalten"))),
    KALK_PRO: ("Kalkulator Pro", _ANGEBOT + ("angebot.freigeben", "angebot.loeschen", "preise.ek_sehen",
                                             "preise.vk_bearbeiten", "auswertung.sehen", "daten.import",
                                             "daten.export") + _TECHNIK + ("auftrag.sehen",)),
    KALK_STANDARD: ("Kalkulator Standard", _ANGEBOT + _TECHNIK + ("auftrag.sehen", "daten.export")),
    MITARBEITER: ("Mitarbeiter", ()),
    NUR_LESEN: ("Nur Lesen", _SEHEN),
}
ROLLE_TITEL = {ENTWICKLER: "Entwickler", **{k: v[0] for k, v in ROLLEN.items()}}


def rollen_rechte(rolle, eigene=None):
    """Einzelrechte einer Rolle (eigene: vom Administrator angepasste Rollen {name: [rechte]})."""
    if eigene and rolle in eigene:
        return frozenset(r for r in eigene[rolle] if r in RECHT)
    return frozenset(ROLLEN.get(rolle, ("", ()))[1])


def wirksame_rechte(rollen=(), plus=(), minus=(), eigene=None):
    """Menge der Einzelrechte eines Benutzers. Unbekannte Namen und die Rolle Entwickler zählen nicht."""
    r = set()
    for ro in rollen or ():
        if ro != ENTWICKLER:
            r |= rollen_rechte(ro, eigene)
    r |= {x for x in plus or () if x in RECHT}
    r -= set(minus or ())
    return frozenset(r)


def vergabe_fehler(eigene_rechte, ist_entwickler, rollen=(), plus=(), eigene=None):
    """Fehlertext, wenn jemand mit eigene_rechte diese Rollen bzw. Einzelrechte nicht vergeben darf, sonst ''."""
    if ENTWICKLER in (rollen or ()):
        return "Die Rolle Entwickler kann niemand zuweisen; sie gilt nur mit einem Entwickler-Ausweis."
    if any(x in NUR_ENTWICKLER for x in plus or ()):
        return "Dieses Recht gehört nur dem Entwickler."
    unbekannt = [ro for ro in rollen or () if ro not in ROLLEN and not (eigene and ro in eigene)]
    if unbekannt:
        return f"Unbekannte Rolle: {', '.join(unbekannt)}"
    if ist_entwickler:
        return ""
    if "benutzer.verwalten" not in eigene_rechte:
        return "Benutzer verwalten ist nicht freigegeben."
    soll = wirksame_rechte(rollen, plus, (), eigene)
    fehlt = sorted(soll - set(eigene_rechte))
    if fehlt:
        return ("Rechte, die man selbst nicht hat, kann man nicht vergeben: "
                + ", ".join(RECHT[x].titel for x in fehlt))
    return ""
