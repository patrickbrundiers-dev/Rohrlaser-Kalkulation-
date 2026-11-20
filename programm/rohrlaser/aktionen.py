"""Aktionsbibliothek (Großes Design- und Layout-Update, Patrick 19.11.2026, Punkt 3): alle wichtigen Funktionen des
Programms als auswählbare Aktionen für „Meine Werkzeugleiste“, die Schnellzugriffe der Startseite und eigene
Tastenkürzel.

Jede Aktion ruft eine Funktion auf, die es im Programm schon gibt (Angebotsseite, Hauptfenster, Menü); hier steht keine
eigene Geschäftslogik. Eine Aktion, die gerade nicht passt (z. B. „Optimieren“ ohne geöffnetes Angebot), ist
ausgegraut und nennt im Tooltip den Grund (grund). Aktionen, die nur im 3D-Editor gelten, stehen dort im Menüband
(menueband.py); die Bibliothek führt sie mit dem Hinweis „im Menüband des 3D-Editors“, man kann sie nicht in die
Hauptleiste legen (NUR_EDITOR).

Kontexte (kontext): start, angebotsliste, angebot, anfragen, auftraege, produktion, pflege, einstellungen. Die
kontextabhängigen Knöpfe der Leiste wählt werkzeugleiste.KONTEXT_VORGABE je Kontext (vom Benutzer änderbar).

Ohne Qt-Fenster testbar: AKTIONEN, AKTION, GRUPPEN, kontext(f), grund(f, a), ausfuehren(f, a) brauchen nur ein
Objekt mit den Attributen des Hauptfensters.
"""
from dataclasses import dataclass, field
from typing import Callable

GRUPPEN = ("Angebote", "Kalkulation", "Bauteile", "3D-Editor", "Material", "Dokumente", "Produktion", "Navigation",
           "Allgemein")

KONTEXTE = (("start", "Startseite"), ("angebotsliste", "Angebotsliste"), ("angebot", "Geöffnetes Angebot"),
            ("anfragen", "Anfragen"), ("auftraege", "Aufträge und Versand"), ("produktion", "Produktion und Fertigung"),
            ("pflege", "Kunden, Lager, Zukauf, Fracht"), ("einstellungen", "Einstellungen"))
KONTEXT_TITEL = dict(KONTEXTE)

# Bedingungen (bedingung): angebot = ein Angebot ist geöffnet und zu sehen, position = dazu eine Position gewählt,
# auswahl = in der Angebotsliste ist ein Angebot gewählt oder ein Angebot ist geöffnet
OHNE_ANGEBOT = "Nur mit geöffnetem Angebot (Angebot in der Angebotsliste doppelklicken)"
OHNE_POSITION = "Bitte im geöffneten Angebot zuerst eine Position wählen"
OHNE_AUSWAHL = "Bitte ein Angebot öffnen oder in der Angebotsliste wählen"


@dataclass
class Aktion:
    id: str
    titel: str
    gruppe: str
    symbol: str = ""                        # Name aus symbole.PFADE oder menueband.EDITOR_PFADE
    tipp: str = ""
    ausfuehren: Callable = None             # ausfuehren(f) -> beliebig; None = nur im 3D-Editor (NUR_EDITOR)
    bedingung: str = ""                     # "", angebot, position, auswahl
    funktion: str = ""                      # Name in funktionen.FUNKTIONEN: ausgeschaltet = ausgeblendet
    menue: Callable = None                  # menue(f) -> [(Titel, Aufruf)]: Knopf mit Auswahlliste (z. B. letzte Angebote)
    stichworte: tuple = field(default_factory=tuple)    # weitere Suchwörter im Konfigurator


# ------------------------------------------------------------------ Hilfen
def angebot(f):
    """Geöffnetes und gerade sichtbares Angebot (AngebotSeite) oder None."""
    seite = f.reiter.currentWidget() if getattr(f, "reiter", None) is not None else None
    return seite if seite is not None and seite in getattr(f, "offen", {}).values() else None


def _zeile(seite):
    """Gewählte Positionszeile des Angebots oder None."""
    try:
        i = seite.pos_ansicht.currentIndex()
    except AttributeError:
        return None
    return i.row() if i.isValid() and i.row() < len(seite.positionen) else None


def _in_liste(f):
    return getattr(f, "reiter", None) is not None and f.reiter.currentWidget() is getattr(f, "angebote", None)


def _liste_gewaehlt(f):
    try:
        return _in_liste(f) and f.angebote.ansicht.currentIndex().isValid()
    except AttributeError:
        return False


def _seite_zeigen(f, name):
    seite = getattr(f, name, None)
    if seite is None:
        return None
    f.reiter.setCurrentWidget(seite)
    return seite


def _stammdaten(f, tabelle, suche=False):
    seite = next((s for s in getattr(f, "seiten", ()) if s.t.name == tabelle), None)
    if seite is None:
        return None
    f.zeigen(seite)
    if suche and hasattr(seite, "suche"):
        seite.suche.setFocus()
        seite.suche.selectAll()
    return seite


def _mit_angebot(methode, *args, zeile=False):
    """Aufruf einer Methode der geöffneten Angebotsseite (bei zeile=True mit der gewählten Positionszeile)."""
    def aufruf(f):
        seite = angebot(f)
        if seite is None:
            return None
        if zeile:
            return getattr(seite, methode)(_zeile(seite))
        return getattr(seite, methode)(*args)
    return aufruf


def _kuerzel(name):
    return lambda f: f.kuerzel(name)


def _angebot_kopieren(f):
    """Angebot kopieren: in der Liste das gewählte, im geöffneten Angebot dieses (vorher in der Liste wählen)."""
    seite = angebot(f)
    if seite is not None:
        if not _in_liste_waehlen(f, seite.id):
            return None
    return f.angebote.kopieren()


def _in_liste_waehlen(f, angebot_id):
    """Angebot in der Angebotsliste markieren (für Aktionen, die mit der Liste arbeiten). True = gefunden."""
    liste = f.angebote
    m = liste.ansicht.model()
    for r in range(m.rowCount()):
        i = m.index(r, 0)
        try:
            if liste._id(i) == angebot_id:
                liste.ansicht.setCurrentIndex(i)
                return True
        except (AttributeError, IndexError, KeyError):
            break
    f.meldung("Das Angebot steht gerade nicht in der Angebotsliste (Filter oder Zeitraum).", fehler=True)
    return False


def _auftrag_uebergeben(f):
    seite = angebot(f)
    if seite is not None:
        return f.in_auftrag_uebernehmen([seite.id])
    return f.angebote.in_auftrag()


def _ordner(f):
    seite = angebot(f)
    if seite is not None:
        return f.angebot_ordner_oeffnen(seite.kopf)
    if _in_liste(f):
        return f.angebote.ordner_oeffnen()
    return f.ablage_oeffnen()


def letztes_pdf(f):
    """Neueste PDF-Datei im Ordner des geöffneten Angebots (Pfad) oder None."""
    seite = angebot(f)
    if seite is None:
        return None
    try:
        ordner = f.angebot_ordner(seite.kopf)
        dateien = [p for p in ordner.rglob("*.pdf") if p.is_file()]
    except OSError:
        return None
    return max(dateien, key=lambda p: p.stat().st_mtime) if dateien else None


def _pdf_oeffnen(f):
    pfad = letztes_pdf(f)
    if pfad is None:
        f.meldung("Im Ordner dieses Angebots liegt noch kein PDF. „Angebot (PDF)“ erstellt eins.", fehler=True)
        return None
    f.datei_oeffnen(pfad)
    return pfad


def _speichern(f):
    """Strg+S: offene Eingabe in einer Tabelle abschließen und speichern. Jede Änderung speichert das Programm sofort
    (kein eigener Speichern-Schritt nötig); mit gemeinsamem Ordner gehen die Änderungen gleich zu den Kollegen."""
    f.kuerzel("speichern")
    from . import teilen
    if teilen.aktiv(f.db) and angebot(f) is not None:
        return f.abgleichen()
    f.meldung("Gespeichert. Jede Änderung wird sofort gespeichert.")
    return True


def _fertigmeldung(f):
    seite = getattr(f, "produktion", None)
    if seite is None:
        return None
    if f.reiter.currentWidget() is not seite or seite.zeile() is None:
        f.reiter.setCurrentWidget(seite)
        f.meldung("Bitte in der Produktion den Arbeitsgang wählen und dann „Fertigmeldung“.", fehler=True)
        return None
    from . import auftrag_produktion as pr
    return seite.mit_menge(pr.ABGESCHLOSSEN)


def _produktionsstatus(f):
    seite = angebot(f)
    if getattr(f, "auftraege_an", lambda: False)():
        return _seite_zeigen(f, "produktion")
    if seite is not None:
        return f.fertigung_zeigen(seite.id)
    return _seite_zeigen(f, "fertigung")


def _thema_wechseln(f):
    """Hell ↔ Dunkel (gemerkt an diesem Arbeitsplatz wie unter Einstellungen → Ansicht)."""
    from . import stil
    neu = "Hell" if stil.thema() != "Hell" else "Dunkel"
    f.db.einstellung_setzen("ansicht_thema", neu)
    f.ansicht_anwenden()
    return neu


def _letzte_angebote(f, anzahl=12):
    try:
        zeilen = sorted(f.db.angebote(), key=lambda z: str(z.get("geaendert") or ""), reverse=True)[:anzahl]
    except Exception:           # noqa: BLE001 – Liste ist Zusatz
        return []
    return [(" · ".join(str(x) for x in (z.get("nummer"), z.get("kunde")) if x) or f"Angebot {z['id']}",
             lambda aid=z["id"]: f.angebot_oeffnen(aid)) for z in zeilen]


def _zuletzt_benutzt(f):
    from . import werkzeugleiste
    aus = []
    for aid in werkzeugleiste.zuletzt(f.db):
        a = AKTION.get(aid)
        if a is not None and a.ausfuehren is not None and a.menue is None:
            aus.append((a.titel, lambda a=a: ausfuehren(f, a)))
    return aus


def _favoriten(f):
    """Schnellzugriffe der Startseite als Auswahlliste (dieselbe Auswahl wie die Karte „Schnellzugriffe“)."""
    from . import werkzeugleiste
    aus = []
    for aid in werkzeugleiste.schnellzugriffe(f.db):
        a = AKTION.get(aid)
        if a is not None and a.ausfuehren is not None and a.menue is None:
            aus.append((a.titel, lambda a=a: ausfuehren(f, a)))
    return aus


def _offen(f):
    return None


# ------------------------------------------------------------------ Bibliothek
_A = Aktion
AKTIONEN = (
    # Angebote
    _A("angebot_neu", "Neues Angebot", "Angebote", "neu", "Leeres Angebot anlegen und öffnen",
       lambda f: f.angebote.neu()),
    _A("angebot_neu_step", "Neues Angebot aus STEP …", "Angebote", "step", "STEP-Dateien wählen, Angebot anlegen",
       lambda f: f.angebote.neu_aus_step(), stichworte=("import",)),
    _A("angebot_oeffnen", "Angebot öffnen …", "Angebote", "oeffnen",
       "In der Angebotsliste: das gewählte Angebot öffnen; sonst Angebot suchen (Strg+K)",
       lambda f: f.angebote.oeffnen_gewaehlt() if _liste_gewaehlt(f) else f.befehlspalette()),
    _A("angebote_letzte", "Letzte Angebote", "Angebote", "liste", "Zuletzt geänderte Angebote zum Öffnen",
       _offen, menue=_letzte_angebote),
    _A("angebot_kopieren", "Angebot kopieren …", "Angebote", "kopieren",
       "Gewähltes bzw. geöffnetes Angebot kopieren (anderer Kunde wählbar)", _angebot_kopieren, "auswahl"),
    _A("angebot_speichern", "Speichern", "Angebote", "sichern",
       "Offene Eingabe abschließen und speichern (Strg+S); mit gemeinsamem Ordner gleich abgleichen", _speichern),
    _A("angebot_fassung", "Neue Fassung", "Angebote", "kopieren", "Neue Fassung des geöffneten Angebots anlegen",
       lambda f: f.neue_fassung(), "angebot"),
    _A("angebot_archivieren", "Angebote archivieren …", "Angebote", "ordner",
       "Alte Angebote ins Archiv verschieben (Datei → Alte Angebote archivieren)", lambda f: f.archivieren()),
    _A("angebot_exportieren", "Angebot exportieren (CSV) …", "Angebote", "ausgaben",
       "Angebotskopf und Positionen als CSV-Dateien", _mit_angebot("csv_export"), "angebot", stichworte=("export",)),
    _A("angebote_vergleichen", "Angebotsvergleich …", "Angebote", "liste", "Zwei Angebote gegenüberstellen",
       lambda f: f.angebote_vergleichen()),
    _A("angebot_mail", "Angebot per E-Mail …", "Angebote", "mail", "Angebot als PDF per E-Mail schicken",
       _mit_angebot("angebot_mail"), "angebot", "funktion_angebot_mail"),
    _A("angebot_fertigstellen", "Fertigstellen …", "Angebote", "pdf", "PDF, E-Mail und Vorgang „Verschickt“ in einem Schritt",
       _mit_angebot("fertigstellen"), "angebot"),
    _A("angebot_schliessen", "Angebot schließen", "Angebote", "", "Geöffnetes Angebot schließen (Strg+W)",
       _kuerzel("schliessen"), "angebot"),
    # Kalkulation
    _A("kalk_neu", "Neue Kalkulation (Schnellpreis) …", "Kalkulation", "neu",
       "Schnelle Preisauskunft ohne Angebot: Profil, Länge, Stück (Strg+Alt+P)", lambda f: f.schnellpreis()),
    _A("kalk_starten", "Kalkulation starten (Optimieren)", "Kalkulation", "optimieren",
       "Stangen optimieren und alle Preise rechnen (F9)", _mit_angebot("optimieren"), "angebot"),
    _A("kalk_aktualisieren", "Kalkulation aktualisieren", "Kalkulation", "abgleich", "Seite neu laden und rechnen (F5)",
       _kuerzel("aktualisieren")),
    _A("kalk_pruefen", "Kalkulation prüfen (Angebots-Check) …", "Kalkulation", "auswahl",
       "Alle offenen Punkte vor dem Angebots-PDF", _mit_angebot("check_zeigen"), "angebot", stichworte=("prüfen",)),
    _A("kalk_problem", "Nächster offener Punkt", "Kalkulation", "suche", "Zur nächsten Position mit Hinweis springen (F7)",
       _mit_angebot("naechstes_problem"), "angebot"),
    _A("kalk_material", "Material und Materialkosten …", "Kalkulation", "material",
       "Materialeinsatz und Kosten je Abmessung; Werkstoff, Lieferlänge, Meterpreis ändern",
       _mit_angebot("material_einstellen"), "angebot", stichworte=("materialkosten", "auswählen")),
    _A("kalk_maschinen", "Maschinenzeiten und -vergleich …", "Kalkulation", "auswertung",
       "Laserzeiten und Preise je Maschine vergleichen", _mit_angebot("maschinen_vergleichen"), "angebot"),
    _A("kalk_staffeln", "Staffelpreise rechnen", "Kalkulation", "staffel", "Preise aller Staffeln rechnen (F8)",
       _kuerzel("staffeln"), "angebot"),
    _A("kalk_zusatz", "Zusatzarbeiten …", "Kalkulation", "zusatz", "Gewinde, Senken, Biegen … für die markierten Teile",
       _mit_angebot("zusatzarbeiten"), "angebot"),
    _A("kalk_gesamt", "Gesamtkalkulation (PDF)", "Kalkulation", "pdf", "Interne Kalkulation als PDF (Strg+Umschalt+K)",
       _mit_angebot("kalkulation_pdf"), "angebot"),
    _A("pdf_angebot", "Angebot (PDF) erstellen", "Kalkulation", "pdf", "Angebots-PDF für den Kunden (Strg+P)",
       _mit_angebot("angebot_pdf"), "angebot", stichworte=("pdf erstellen", "dokumente")),
    # Bauteile
    _A("teil_importieren", "Bauteile importieren (STEP, DXF) …", "Bauteile", "step",
       "STEP- oder DXF-Dateien ins geöffnete Angebot holen (Strg+I)", _mit_angebot("dateien_waehlen"), "angebot",
       stichworte=("step öffnen",)),
    _A("teil_neu", "Bauteil hinzufügen", "Bauteile", "neu", "Neue Position (Rohr, Blech, Zukauf, Baugruppe)",
       _mit_angebot("position_neu"), "angebot", stichworte=("position",)),
    _A("teil_bearbeiten", "Bauteil bearbeiten (Editor) …", "Bauteile", "kontur",
       "Editor der gewählten Position öffnen (Rohr: Schneidweg-Rechner/3D-Editor, Blech, Baugruppe)",
       _mit_angebot("editor_oeffnen", zeile=True), "position"),
    _A("teil_kopieren", "Bauteil kopieren", "Bauteile", "kopieren", "Markierte Positionen duplizieren (Strg+Umschalt+D)",
       _mit_angebot("position_duplizieren"), "position"),
    _A("teil_loeschen", "Bauteil löschen …", "Bauteile", "loeschen", "Markierte Positionen löschen (mit Rückfrage)",
       _mit_angebot("positionen_loeschen"), "position"),
    _A("teil_bibliothek", "Bauteilbibliothek …", "Bauteile", "liste", "Position aus einer gespeicherten Vorlage",
       _mit_angebot("position_aus_vorlage"), "angebot"),
    _A("teil_vorlage", "Als Vorlage speichern …", "Bauteile", "sichern", "Gewählte Position in die Bauteilbibliothek",
       _mit_angebot("als_vorlage_speichern", zeile=True), "position"),
    _A("step_oeffnen", "STEP-Datei öffnen …", "Bauteile", "step",
       "Im Angebot: STEP importieren; sonst neues Angebot aus STEP",
       lambda f: f.kuerzel("importieren") if angebot(f) is not None else f.angebote.neu_aus_step()),
    _A("teil_geometrie", "Geometrie prüfen (STEP-Merkmale) …", "Bauteile", "auswahl",
       "STEP-Merkmale der markierten Positionen prüfen", _mit_angebot("step_merkmale_pruefen"), "position",
       stichworte=("3d",)),
    # 3D-Editor
    _A("d3_editor", "3D-Editor öffnen", "3D-Editor", "ansicht3d", "Editor der gewählten Position öffnen",
       _mit_angebot("editor_oeffnen", zeile=True), "position"),
    _A("d3_ansicht", "STEP-Viewer (3D-Ansicht) …", "3D-Editor", "ansicht3d",
       "Alle Teile des Angebots in 3D, die gewählte zuerst", _mit_angebot("ansicht_3d"), "angebot"),
    # Material
    _A("mat_suchen", "Material suchen", "Material", "suche", "Profile in den Stammdaten suchen",
       lambda f: _stammdaten(f, "profile", suche=True)),
    _A("mat_verwaltung", "Materialverwaltung", "Material", "material", "Profile (Abmessungen) und Werkstoffe pflegen",
       lambda f: _stammdaten(f, "profile")),
    _A("mat_werkstoffe", "Werkstoffe", "Material", "material", "Werkstoffe und Preise pflegen",
       lambda f: _stammdaten(f, "werkstoffe")),
    _A("mat_preise", "Materialpreise aktualisieren …", "Material", "abgleich", "Online-Preise der Lieferanten holen",
       lambda f: f.onlinepreise()),
    _A("mat_liste", "Materialliste / Materialanfrage …", "Material", "mail",
       "Materialbedarf des Angebots als Anfrage an die Lieferanten", _mit_angebot("material_anfragen"), "angebot",
       "funktion_materialanfrage"),
    _A("mat_lager", "Lager", "Material", "lager", "Materialbestand und Reststücke", lambda f: _seite_zeigen(f, "lager")),
    _A("mat_zukauf", "Zukaufteile …", "Material", "zukauf", "Zukaufteile des Angebots bearbeiten",
       _mit_angebot("zukaufteile"), "angebot", "funktion_zukauf"),
    # Dokumente
    _A("dok_pdf_oeffnen", "Letztes PDF öffnen", "Dokumente", "pdf", "Neuestes PDF im Ordner des Angebots öffnen",
       _pdf_oeffnen, "angebot"),
    _A("dok_zeichnung", "Zeichnung / Abwicklung (PDF) …", "Dokumente", "pdf",
       "Abwicklung der gewählten Rohrposition 1:1 mit Passmarken", _mit_angebot("abwicklung_drucken", zeile=True),
       "position", stichworte=("zeichnung exportieren",)),
    _A("dok_werkstatt", "Werkstattpapiere mit Schnittplan (PDF)", "Dokumente", "ausgaben",
       "Schnittschema, Stangenbelegung und Arbeitsgänge für die Werkstatt (Strg+Umschalt+P)",
       _mit_angebot("werkstatt_pdf"), "angebot", stichworte=("schnittschema", "produktionsunterlagen")),
    _A("dok_akte", "Angebotsdokument erstellen …", "Dokumente", "pdf", "Angebotsakte: Kunde und intern",
       _mit_angebot("angebotsdokument"), "angebot"),
    _A("dok_ablage", "Dokumentenablage öffnen …", "Dokumente", "ordner", "Dokumentenablage / PPEASE-Verknüpfung",
       lambda f: f.ppease_ablage(angebot(f).kopf if angebot(f) is not None else None)),
    _A("dok_ordner", "Angebotsordner öffnen", "Dokumente", "ordner",
       "Ordner des Angebots (in der Liste: des gewählten, sonst die Ablage)", _ordner),
    # Produktion
    _A("prod_uebergeben", "Auftrag übergeben …", "Produktion", "auftraege", "Angebot in einen Auftrag übernehmen",
       _auftrag_uebergeben, "auswahl"),
    _A("prod_status", "Produktionsstatus", "Produktion", "produktion",
       "Arbeitsgänge in der Werkstatt bzw. Fertigungsstatus des Angebots", _produktionsstatus),
    _A("prod_stueckliste", "Stückliste (CSV) …", "Produktion", "liste", "Stückliste je Satz/Baugruppe",
       _mit_angebot("csv_stueckliste"), "angebot"),
    _A("prod_fertigmeldung", "Fertigmeldung …", "Produktion", "produktion",
       "Gewählten Arbeitsgang in der Produktion abschließen", _fertigmeldung),
    _A("prod_etiketten", "Etiketten mit QR-Code (PDF) …", "Produktion", "pdf", "Teile-Etiketten drucken",
       _mit_angebot("etiketten_pdf"), "angebot", "funktion_etiketten"),
    _A("prod_pruefplan", "Prüfplan / Messprotokoll (PDF) …", "Produktion", "pdf", "Prüfplan des Angebots",
       _mit_angebot("pruefplan_pdf"), "angebot"),
    # Navigation
    _A("nav_start", "Dashboard (Start)", "Navigation", "start", "Startseite", lambda f: _seite_zeigen(f, "start")),
    _A("nav_angebote", "Angebotsliste", "Navigation", "angebote", "Alle Angebote",
       lambda f: _seite_zeigen(f, "angebote")),
    _A("nav_anfragen", "Anfragen", "Navigation", "mail", "Kundenanfragen", lambda f: _seite_zeigen(f, "anfragen_seite")),
    _A("nav_kunden", "Kunden", "Navigation", "kunden", "Kundenstamm", lambda f: _seite_zeigen(f, "kunden")),
    _A("nav_auftraege", "Aufträge", "Navigation", "auftraege", "Auftragsverwaltung",
       lambda f: _seite_zeigen(f, "auftraege")),
    _A("nav_produktion", "Produktion", "Navigation", "produktion", "Arbeitsgänge in der Werkstatt",
       lambda f: _seite_zeigen(f, "produktion")),
    _A("nav_auswertung", "Auswertungen", "Navigation", "auswertung", "Aufträge auswerten",
       lambda f: _seite_zeigen(f, "auswertung")),
    _A("nav_zukauf", "Zukaufartikel", "Navigation", "zukauf", "Zukaufartikel, Kategorien, Lieferanten",
       lambda f: _seite_zeigen(f, "zukauf")),
    _A("nav_einstellungen", "Einstellungen", "Navigation", "einstellungen", "Einstellungen öffnen",
       lambda f: _seite_zeigen(f, "bereich")),
    # Allgemein
    _A("suchen", "Suchen und ausführen …", "Allgemein", "suche", "Angebote, Kunden, Befehle suchen (Strg+K)",
       lambda f: f.befehlspalette()),
    _A("rueckgaengig", "Rückgängig", "Allgemein", "rueckgaengig", "Letzte Änderung im Angebot zurücknehmen (Strg+Z)",
       _kuerzel("rueckgaengig"), "angebot"),
    _A("wiederholen", "Wiederholen", "Allgemein", "wiederholen", "Zurückgenommene Änderung wiederholen (Strg+Y)",
       _kuerzel("wiederholen"), "angebot"),
    _A("abgleichen", "Mit den Kollegen abgleichen", "Allgemein", "abgleich", "Gemeinsamen Ordner abgleichen",
       lambda f: f.abgleichen()),
    _A("favoriten", "Favoriten", "Allgemein", "start", "Meine Schnellzugriffe (Auswahl wie auf der Startseite)",
       _offen, menue=_favoriten),
    _A("zuletzt", "Zuletzt verwendet", "Allgemein", "vorher", "Zuletzt über die Leiste ausgeführte Funktionen",
       _offen, menue=_zuletzt_benutzt),
    _A("sicherung", "Datensicherung erstellen", "Allgemein", "sichern", "Sicherung der Datendatei jetzt",
       lambda f: f.sicherung_erstellen()),
    _A("thema", "Hell / Dunkel umschalten", "Allgemein", "blick", "Farbschema wechseln (gemerkt an diesem Platz)",
       _thema_wechseln, stichworte=("dark mode", "light mode")),
    _A("info_panel", "Info-Panel rechts", "Allgemein", "liste", "Aktuelles Angebot, Status, Hinweise rechts ein-/ausblenden",
       lambda f: f.info_panel_umschalten()),
    _A("leiste_konfigurieren", "Meine Werkzeugleiste konfigurieren …", "Allgemein", "einstellungen",
       "Knöpfe hinzufügen, sortieren, gruppieren, umbenennen", lambda f: f.werkzeugleiste_konfigurieren()),
    _A("startseite_anpassen", "Dashboard anpassen …", "Allgemein", "start", "Karten der Startseite wählen und anordnen",
       lambda f: f.startseite_anpassen()),
    _A("anleitung", "Bedienungsanleitung", "Allgemein", "pdf", "Bedienungsanleitung (F1)", lambda f: f.anleitung_oeffnen()),
)

# Werkzeuge, die nur im 3D-Editor gelten: dort im Menüband (menueband.py, Thread 3D-Editor). Für die Übersicht im
# Konfigurator, nicht für die Hauptleiste.
NUR_EDITOR = (("Ansicht drehen", "Maus (rechte Taste) oder Ansichtswürfel"), ("Ansicht zurücksetzen", "Taste Pos1"),
              ("Zoom auf Bauteil", "Einpassen"), ("Kontur erstellen", "Reiter Konstruktion"),
              ("Kontur bearbeiten", "Reiter Konstruktion"), ("Messen", "Reiter Messen"),
              ("Ausschnitt erstellen", "Reiter Konstruktion"), ("Gehrung bearbeiten", "Reiter Enden"))

AKTION = {a.id: a for a in AKTIONEN}
# Aktionen, die eine Seite des Hauptfensters zeigen: aus, wenn die Seite ausgeblendet ist (Funktion aus, ohne Recht)
SEITE = {"nav_start": "start", "nav_angebote": "angebote", "nav_anfragen": "anfragen_seite", "nav_kunden": "kunden",
         "nav_auftraege": "auftraege", "nav_produktion": "produktion", "nav_auswertung": "auswertung",
         "nav_zukauf": "zukauf", "nav_einstellungen": "bereich", "mat_lager": "lager",
         "prod_fertigmeldung": "produktion"}


def kontext(f):
    """Arbeitsbereich, in dem das Hauptfenster gerade steht (siehe KONTEXTE)."""
    r = getattr(f, "reiter", None)
    w = r.currentWidget() if r is not None else None
    if w is None:
        return "start"
    if w in getattr(f, "offen", {}).values():
        return "angebot"
    for name, k in (("start", "start"), ("angebote", "angebotsliste"), ("anfragen_seite", "anfragen"),
                    ("materialanfragen", "anfragen"), ("auftraege", "auftraege"), ("versand", "auftraege"),
                    ("auswertung", "auftraege"), ("produktion", "produktion"), ("fertigung", "produktion"),
                    ("bereich", "einstellungen")):
        if w is getattr(f, name, None):
            return k
    return "pflege"


def sichtbar(a):
    """Aktion zeigen? Ausgeschaltete Funktionen (funktionen.py) blenden ihre Knöpfe aus."""
    if not a.funktion:
        return True
    from . import funktionen
    try:
        return funktionen.an(a.funktion)
    except Exception:       # noqa: BLE001 – ohne Datenbank (Tests ohne Fenster): sichtbar
        return True


def grund(f, a):
    """Warum die Aktion gerade nicht geht ('' = geht)."""
    if a.ausfuehren is None:
        return "Steht im Menüband des 3D-Editors"
    if a.bedingung in ("angebot", "position") and angebot(f) is None:
        return OHNE_ANGEBOT
    if a.bedingung == "position" and _zeile(angebot(f)) is None:
        return OHNE_POSITION
    if a.bedingung == "auswahl" and angebot(f) is None and not _liste_gewaehlt(f):
        return OHNE_AUSWAHL
    seite = SEITE.get(a.id)
    if seite is not None:
        w = getattr(f, seite, None)
        r = getattr(f, "reiter", None)
        if w is None or (r is not None and r.indexOf(w) >= 0 and not r.isTabVisible(r.indexOf(w))):
            return "Diese Seite ist ausgeschaltet oder für diesen Benutzer nicht freigegeben"
    return ""


def ausfuehren(f, a):
    """Aktion ausführen (nur wenn sie gerade geht; sonst Hinweis). Merkt sie unter „Zuletzt verwendet“."""
    warum = grund(f, a)
    if warum:
        f.meldung(f"{a.titel}: {warum}.", fehler=True)
        return None
    from . import werkzeugleiste
    werkzeugleiste.benutzt(f.db, a.id)
    return a.ausfuehren(f)
