"""Neuerungen je Programmversion, neueste zuerst.

Jede neue Programmversion (__init__.VERSION) bekommt oben einen Eintrag [Version, ausführlich, kurz];
tests/test_anleitung.py prüft das. Die Kurzfassung (eine Zeile) steht in der Bedienungsanleitung, die nur die
letzten Versionen zeigt (Kapitel „Was ist neu“); die vollständige Liste zeigt das Programm unter
Hilfe → Was ist neu … Text mit <b>/<i>; [[marke]] verweist auf ein Kapitel der Bedienungsanleitung.
"""
import re

IN_ANLEITUNG = 5          # so viele Versionen zeigt die Bedienungsanleitung


def als_html(neuerungen=None):
    """Vollständige Liste für das Fenster Hilfe → Was ist neu … ([[marke]] wird zu „(siehe Anleitung)“)."""
    zeilen = []
    for eintrag in neuerungen or NEUERUNGEN:
        text = re.sub(r"\s*\(?(\[\[[a-z0-9_]+\]\]|Kapitel \d+(\.\d+)*)\)?", "", eintrag[1]).replace(" ,", ",")
        zeilen.append(f'<tr><td style="padding:4px 12px 4px 0; white-space:nowrap"><b>{eintrag[0]}</b></td>'
                      f'<td style="padding:4px 0">{text}</td></tr>')
    return "<table>" + "".join(zeilen) + "</table>"


NEUERUNGEN = [
    ["0.9.321", "<b>Schweißbaugruppe Teil 2</b>: Rechts im Fenster stehen Preis, Zeit, <b>Sicherheit</b> (± %), "
     "<i>Preis je BG von Hand</i> und der Kostenbalken jetzt fest oben; <i>Kalkulation: Zeit</i>, <i>Kosten</i> und "
     "<i>Einzelwerte</i> sind zuklappbar (wird gemerkt), die Tabellen brauchen keinen waagerechten Rollbalken mehr. "
     "Neue Regeln der Vorkalkulation: <b>Vorwärmen</b> dicker Stahlnähte, <b>Prüfumfang</b> nach Qualität (als "
     "Zeit oder Fremdleistung) und der Vergleich, ab welcher Stückzahl sich eine <b>Vorrichtung</b> rechnet. Fehlen "
     "neue Regeln in den Stammdaten, meldet die Startseite <i>Neue Schweiß-Richtwerte verfügbar</i> (Doppelklick "
     "lädt sie, vorhandene Werte bleiben). Schweißbaugruppen mit offenen Vorschlägen stehen im Angebots-Check; der "
     "Rechtsklick <b>Alle Schweißbaugruppen nachrechnen</b> aktualisiert alle auf einmal ([[schweissbaugruppe]]).",
     "Schweißbaugruppe: Ergebnis übersichtlicher, Sicherheit des Preises, Vorwärmen, Prüfumfang, neue Richtwerte melden"],
    ["0.9.320", "<b>Oberfläche nachgebessert</b> (Prüfrundgang): Auf großen Bildschirmen steht die linke Spalte "
     "(Angebotskopf, Kalkulation, Fracht) nur beim Reiter Positionen voll; bei Kalkulation, Schnittplan, Staffeln, "
     "Nachkalkulation und STEP-Protokoll bleibt ein schmaler Streifen, ein Klick klappt sie auf, die Tabellen haben "
     "so die ganze Breite. Die Kurzfassung von Kalkulation und Fracht steht dort unter dem Titel statt abgeschnitten "
     "daneben. Der Detailbereich zeigt nach dem Öffnen die erste Position (auf hohen Bildschirmen, [[angebot]]). Im Schnittplan ist die "
     "3D-Vorschau ohne gewählte Position nur eine Kopfzeile, auf der Startseite bekommt die Kundenspalte die Breite, "
     "in Fertigung und Lager kleben die Spaltenköpfe leerer Tabellen nicht mehr zusammen. Rechnung und Daten "
     "bleiben unverändert.",
     "Linke Spalte bei breiten Reitern schmal, Kurztexte unter dem Titel, erste Position im Detailbereich."],
    ["0.9.319", "<b>Roadmap Phase 2, Paket 2b Material</b>: <b>Preisverlauf …</b> zeigt jeden Stand der "
     "Materialpreise mit Datum, Kurve und Durchschnitt über 3/6/12 Monate; neue Tabelle <b>Materialindex</b> "
     "(Legierungszuschlag je Monat auf den Tonnenpreis) ([[lieferlaengen]]). <b>EK-Verlauf …</b> unter "
     "Preisänderungen, Hinweis bei EK-Preissprung ([[zukauf_preise]]). <b>Mindestabnahme</b> des Lieferanten in "
     "Preise und Lieferlängen: Hinweis im Angebots-Check, wahlweise in den Preis. Oberflächen mit <b>Vormaterial "
     "schon veredelt</b>: Vergleich gegen Veredeln nach dem Laser ([[werkstoffe]]). Maschinen: Mehrzeit für "
     "<b>schwere Stangen</b>. Angebots-Check: Gewicht aus STEP-Volumen gegen Profil × Länge ([[angebots_check]]). "
     "Neue Einstellungen stehen auf aus, leere Felder ändern nichts.",
     "Preisverlauf, Materialindex, EK-Verlauf, Mindestabnahme, Vormaterial verzinkt, schwere Stangen, STEP-Gewicht."],
    ["0.9.318", "<b>Anfrage-Mail: Übernahme nur mit Häkchen</b>: Im Prüfdialog hat jeder aus der Mail vorbelegte Wert "
     "(Anfrage-Nr., Wunschtermin, Werkstoff) ein Häkchen mit der Fundstelle im Tooltip. <i>sicher</i> ist angehakt, "
     "<i>prüfen</i> nicht; ohne Häkchen gilt der Wert ohne Mail ([[anfrage_mail]]).",
     "Anfrage-Mail: Werte nur mit Häkchen übernehmen"],
    ["0.9.317", "<b>Materialanfragen über Outlook</b>: Die Materialanfrage nimmt jetzt auch Blech-, Zukauf- und "
     "Dreh-/Frästeile mit Artikelnummer und Zeichnung auf und nennt unter jeder Rohrzeile die Artikelnummern. "
     "Mehrere Lieferanten lassen sich auf einmal anfragen (je Lieferant eine eigene E-Mail); passende stehen oben "
     "(Lieferant des Materials, dann nach <b>Materialgruppe</b>). Neu sind Liefertermin, Angebotsgültigkeit, "
     "zusätzliche Informationen und eine interne Bemerkung, die Materialliste als PDF und Zeichnungen aus dem Ordner "
     "des Angebots als Anhang. Eigene <b>E-Mail-Vorlagen</b> mit Anrede, Text, Gruß und Signatur stehen unter "
     "Einstellungen → E-Mail-Vorlagen; Lieferanten bekommen Materialgruppen, Anrede und Standardvorlage. Der neue Reiter "
     "<b>Materialanfragen</b> zeigt alle Anfragen mit Kennung, Status (Entwurf, Versendet, Angebot erhalten, "
     "Abgeschlossen), Datum, Uhrzeit und wer; „Gesendete in Outlook prüfen“ erkennt versendete Anfragen, eine "
     "eingelesene Antwort setzt „Angebot erhalten“, die Bestellung schließt ab. Erinnerung mit einem Klick, Rückfrage vor "
     "doppeltem Versand. Der <b>interne Einkauf</b> (Einstellungen → Materialanfrage) steht als Empfänger zur Wahl und "
     "verteilt die Anfragen weiter (Rohr und Blech auf Wunsch an zwei Adressen). <b>Blechteile</b> bekommen Zeichnung, Abwicklung (DXF) und STEP als Anhang "
     "(vorhandene Dateien des Kunden oder vom Programm erzeugt). Gesendet wird weiter nur in Outlook "
     "([[materialanfrage]]).",
     "Materialanfragen: Blech/Zukauf, mehrere Lieferanten, Vorlagen, PDF, Zeichnungen, Verlauf mit Status."],
    ["0.9.316", "<b>Anfragen sicherer und vollständiger</b> ([[anfragen_seite]]): Jeder neue Anhang wird im "
                "Hintergrund mit dem Windows-Virenschutz geprüft; ein Fund wird gesperrt (nichts gelöscht), rot "
                "markiert und gemeldet, Kalkulieren ist dann gesperrt. <b>Antworten des Kunden</b> (AW:/RE: mit "
                "gleichem Betreff von derselben Firma oder dieselbe Outlook-Unterhaltung) kommen in die vorhandene "
                "Anfrage statt als neue, mit Meldung an alle. Anfragen, die länger als 24 Stunden neu sind, stehen "
                "rot in der Liste und auf der Startseite; einmal am Tag ab 7 Uhr kommt eine Erinnerung.",
     "Anfragen: Virenprüfung der Anhänge, Kundenantworten zur Anfrage, Erinnerung nach 24 Stunden"],
    ["0.9.315", "<b>Datenbank über die neue Zugriffsschicht</b>: alle Lese- und Schreibzugriffe des Programms laufen jetzt "
     "über die gemeinsame Schicht für SQLite und PostgreSQL (Plan Datenbank-Modernisierung, Schritt 3a). Für Sie "
     "ändert sich nichts: gleiche Datendatei, gleiche Bedienung, gleiche Geschwindigkeit "
     "([[mehrere_arbeitsplaetze]]).",
     "Datenbank über die neue Zugriffsschicht (ohne sichtbare Änderung)"],
    ["0.9.314", "<b>Roadmap Phase 2, Paket 2a</b>: Haken <b>Vorbehalt bei Teilbestellung</b> im Angebotskopf; mit "
     "<i>Teilbestell-Risiko im Angebots-Check ab [%]</i> rechnet der Check jede Position allein und nennt, was allein "
     "bestellt teurer wäre ([[angebotskopf]]). Haken <b>Preis lose Einzelteile nennen</b>: bei Schweißbaugruppen "
     "steht im Angebot zusätzlich der Preis ungeschweißt. Knopf <b>Sinnvolle Stufen …</b> im Reiter Staffeln "
     "schlägt Mengen vor, an denen der Preis spürbar sinkt oder die Stangen voll werden; angelegt wird nur, was "
     "angehakt ist ([[staffeln]]). Bei Wiederholteilen zerlegt <b>Preis erklären …</b> den Unterschied zu damals in "
     "Ursachen, mit Satz für den Kunden ([[wiederholteile]]). Arbeitsgang-Regeln mit <b>Bohrung Ø von/bis</b> und "
     "<b>Wand von/bis</b>, dazu die Übersicht <b>Alle Merkmal-Regeln …</b> ([[abrechnungsregeln]]). Neue "
     "Einstellungen stehen auf aus.",
     "Teilbestell-Risiko, Preis lose Einzelteile, Sinnvolle Stufen, Preis erklären, Merkmal-Regeln mit Bohrungs-Ø."],
    ["0.9.313", "<b>Anfragen direkt aus Outlook</b> ([[anfragen_outlook]]): <b>Outlook …</b> auf der Seite Anfragen "
                "holt die Mails aus dem Outlook-Ordner <i>Anfragen</i> des klassischen Outlook an diesem Rechner, "
                "jede Minute im Hintergrund, ohne Azure und ohne Admin. Jede Mail wird mit allen Anhängen eine "
                "Anfrage und wandert nach <i>Anfragen\\Neu</i>; Übernehmen, Erledigen und Zurückgeben verschieben "
                "die Mail nach <i>In Bearbeitung</i>, <i>Erledigt</i> bzw. <i>Neu</i>, Verschieben in Outlook ändert "
                "die Anfrage. Nur ein Rechner ruft ab, dieselbe Mail ergibt nie zwei Anfragen, neue Anfragen melden "
                "sich unten rechts in Windows. Gesendet oder gelöscht wird nichts.",
     "Anfragen direkt aus dem klassischen Outlook, Ordner in beide Richtungen"],
    ["0.9.312", "<b>Neue Oberfläche, Teil 3</b>: In der Positionsliste zeigt die neue Spalte <b>Arbeitsgänge</b> "
     "Kürzel wie P (Programmierung), L (Laser), G (Gewinde), E (Entgraten); grau sind Vorschläge, orange Punkte zum "
     "Prüfen, Doppelklick öffnet die Zusatzarbeiten. Darunter steht für die gewählte Position ein <b>Detailbereich</b> "
     "mit Arbeitsgängen, Material und Preis je Teil (<i>Ansicht → Detailbereich unter den Positionen</i> blendet ihn "
     "aus). Die Übersicht hat Kacheln für <b>Laserzeit</b>, <b>Arbeitszeit</b> und <b>Deckungsbeitrag</b> "
     "([[angebot]]). Rechnung und Daten bleiben unverändert.",
     "Spalte Arbeitsgänge, Detailbereich je Position, Kacheln Laserzeit/Arbeitszeit/Deckungsbeitrag."],
    ["0.9.311", "<b>Anfragen verwalten</b> ([[anfragen_seite]]): neue Seite <b>Anfragen</b> mit den Ordnern Neu, In "
                "Bearbeitung, Erledigt und Meine, Zählerleiste, Suche und Filter. Jede Anfrage aus dem "
                "Anfrage-Ordner bekommt eine Akte (A-2026-00042) mit Kopie von Mail und Anhängen und einem "
                "vollständigen Verlauf. <b>Übernehmen</b> mit einem Klick (bei zwei gleichzeitig gewinnt genau "
                "einer), <b>Zuweisen</b>, Bearbeiter ändern, Priorität, interne Notizen, Bearbeitungsstand, "
                "<b>Kalkulieren</b> direkt aus der Anfrage (Angebot und Anfrage verknüpft), <b>Als erledigt "
                "markieren</b>, Wieder öffnen; erledigte Anfragen bleiben, Löschen gibt es nicht. Übersicht je "
                "Mitarbeiter mit Bearbeitungsdauer. Vorbereitung für die Outlook-Anbindung.",
     "Seite Anfragen: Neu, In Bearbeitung, Erledigt mit Verlauf, Übernehmen und Kalkulieren"],
    ["0.9.310", "Intern: Die Hauptadmin-Anmeldung zieht im Programm Rohrlaser Auslastung keine Teile der "
                "Kalkulation mehr mit (Auslastung 2.9.2 lässt sich wieder bauen). Bedienung unverändert.",
     "Intern: Rohrlaser Auslastung 2.9.2 mit Hauptadmin-Anmeldung wieder baubar."],
    ["0.9.309", "<b>Neue Oberfläche, Teil 2</b>: Auf großen Bildschirmen (ab Full HD) ist die Angebotsseite "
     "<b>dreispaltig</b>: links Angebotskopf, Kalkulation und Fracht untereinander, in der Mitte die Positionen über "
     "die ganze Höhe, rechts die Übersicht. <i>Ansicht → Angebotsseite</i> stellt automatisch, drei oder zwei "
     "Spalten ein ([[fenster]]). Über der Positionsliste steht die Zahl der <b>offenen Punkte</b>; <b>F7</b> "
     "springt zur nächsten Position mit FEHLER, WARNUNG oder HINWEIS, Umschalt+F7 zur vorherigen "
     "([[rueckgaengig]]). Die <b>Startseite</b> zeigt oben Kennzahl-Kacheln für alle: Entwürfe, verschickte "
     "Angebote, Aufträge und Trefferquote der letzten 90 Tage, fällige Wiedervorlagen ([[start]]). Lange Karten der "
     "<b>Einstellungen</b> (z. B. Funktionen) stehen auf breiten Seiten in zwei Spalten, die Seite rollt weniger "
     "([[einstellungen]]). Rechnung und Daten "
     "bleiben unverändert.",
     "Angebotsseite dreispaltig auf großen Bildschirmen; F7 springt zum nächsten offenen Punkt; Kennzahl-Kacheln auf der Startseite."],
    ["0.9.308", "<b>Roadmap Phase 1 fertig</b>: <b>Gewinn auf Material</b> je Kunde (Kundenvorgaben) und je Angebot "
                "(„wie Gewinn“ oder eigener Satz, [[angebotskopf]]). <b>Werkszeugnis 3.1 verlangt</b> als Haken im "
                "Angebotskopf und als Kundenvorgabe, mit Kosten je Abmessung aus den Einstellungen. <b>Rüsten und "
                "Programmierung als eigene Zeile</b> „einmalig je Auftrag“ statt in den Stückpreisen. "
                "<b>Artikelnummer gravieren</b> als Kundenvorgabe: nach dem STEP-Import automatisch, übrige Teile "
                "meldet der Angebots-Check mit Erledigen ([[positionsgravur]]). <b>Hauptbauteil</b> der "
                "Schweißbaugruppe: steht in Stückliste und Angebot zuerst.",
     "Gewinn auf Material je Kunde, Werkszeugnis 3.1 mit Kosten, Rüsten/Programmierung als eigene Zeile, Gravur als "
     "Kundenvorgabe, Hauptbauteil"],
    ["0.9.307", "<b>Knickrahmen nach ArTube</b>: Schließung am Scheitel <i>abgeschrägt</i> (Grat), <i>Radius "
     "symmetrisch</i> und <i>asymmetrisch</i> (Außenradius, Korrektur) und <b>Verankerung</b> mit Nase und "
     "Aussparung, im Knickrahmen-Fenster, beim Erstellen aus der STEP und je V-Ausschnitt ([[knickrahmen]]). "
     "<b>Lochfeld</b> als <b>Lochkreis</b> oder als <b>Spirale</b> um ein Rundrohr. <b>Maßbezug und Genauigkeit</b> "
     "je Kontur stehen im Prüfplan und in Massbezuege.csv des CAM-Pakets ([[pruefplan]], [[cam_paket]]).",
     "Knickrahmen: Schließungen und Verankerung; Lochkreis und Spirale; Maßbezug und Genauigkeit je Kontur"],
    ["0.9.306", "<b>Palettenschein für den Kunden</b> ([[palettenschein]]): im Fenster Palettenbegleitschein und im "
     "Reiter Versand der Knopf <i>Für den Kunden</i>. Je Palette ein Blatt mit Absender, Empfänger, Ihrer Bestellung, "
     "unserem Auftrag, Lieferdatum, Palette x / n, Inhalt (Pos., Artikelnummer, Bezeichnung, Stück), Stück und "
     "Bruttogewicht; ohne Arbeitsschritte, Auftragsstatus, Hinweis und Bearbeiter. Der Schein für die Halle bleibt "
     "unverändert.",
     "Palettenschein für den Kunden (ohne interne Felder)"],
    ["0.9.305", "<b>Grundlage für die neue Datenbank</b>: eine zentrale Zugriffsschicht, die SQLite und PostgreSQL "
     "gleich bedient, und ein eingebetteter Datenbankserver für den Einzelplatz (Plan Datenbank-Modernisierung, "
     "Schritt 3a). Noch ohne sichtbare Änderung: das Programm arbeitet weiter mit der eigenen Datendatei "
     "([[mehrere_arbeitsplaetze]]).",
     "Grundlage neue Datenbank (noch ohne sichtbare Änderung)"],
    ["0.9.304", "<b>Zukaufartikel direkt in der Position</b>: im Fenster Zukaufteile Bezeichnung, Menge und EK "
     "eintippen, ohne den Artikel vorher im Artikelstamm anzulegen; der Artikel gehört zur Position und wird mit dem "
     "Angebot gespeichert. Jede Zeile ist direkt änderbar (Bezeichnung, Menge, Artikelnr., EK, Aufschlag %, VK je "
     "Einheit rechnet den Aufschlag zurück), Details mit Hersteller, Lieferant, Bezugskosten, Beschreibung und "
     "Bemerkung, Duplizieren, Entfernen und optional <i>Im Artikelstamm merken</i>. Änderungen an Stammartikeln in "
     "der Position gelten nur dort. Ab zwei Zukaufartikeln zeigt die Positionsliste eine aufklappbare Summenzeile, "
     "das Kalkulations-PDF Positionen, Hersteller und <i>ohne Stamm</i>. Die Schnellanlage <i>Neuer "
     "Zukaufartikel …</i> speichert nur noch mit Häkchen im Artikelstamm. Gespeicherte Angebote rechnen unverändert "
     "([[zukauf_angebot]]).",
     "Zukaufartikel direkt in der Position erfassen, ohne Artikelstamm."],
    ["0.9.303", "<b>Hauptadmin-Lizenz ohne Rechner-ID</b> ([[hauptadmin]]): eigene Lizenzart für Patrick, gilt auf "
                "beliebig vielen eigenen Rechnern, unbefristet bis zum Sperren. Beim Start erscheint dann ein "
                "<b>Anmeldefenster</b>; ohne Passwort (oder Notfallcode) öffnet das Programm nicht. Nach 5 "
                "Fehlversuchen Wartezeit (1 Minute, verdoppelt bis 60 Minuten). Passwort ändern im neuen Menü "
                "<b>Hauptadmin</b>, dort auch Datei für weitere Rechner, Rechte, Funktionen, Einstellungen sichern/"
                "wiederherstellen/zurücksetzen und Diagnose. Das Passwort steht nirgends, auch nicht als Hash "
                "(verschlüsselter Admin-Schlüssel, scrypt + AES-GCM, signiert). Kundenlizenzen und Werkstatt-Rechner "
                "unverändert, ohne Anmeldung. Gilt auch in der Rohrlaser Auslastung.",
     "Hauptadmin-Lizenz ohne Rechner-ID mit Anmeldung beim Start, Menü Hauptadmin"],
    ["0.9.302", "<b>Schweißbaugruppe flexibel kalkulieren</b> ([[bg_kalkulation]]): <b>Stückzeit</b> und <b>Rüstzeit</b> "
     "getrennt, beide von Hand übersteuerbar (auch je Bereich Vorbereitung, Heften, Schweißen, Nachbearbeitung, "
     "Weitere), daneben immer automatisch und Abweichung, ↺ zurück; <b>Komplexitätsfaktor</b> mit Gründen; "
     "<b>Schnellkalkulation</b> mit Material und Zukauf pauschal; aufklappbare <b>Kosten je Baugruppe</b> mit "
     "Material, Teilen, Zukauf, Bereichen, Zuschlägen, Verkaufspreis, Deckungsbeitrag und Marge; <b>Preis je BG von "
     "Hand</b> mit Warnung unter Selbstkosten; Gewinn und Zuschlag Fremdleistung im Fenster; <b>Ablauf einsetzen</b> "
     "aus Vorlagen; letzte <b>Ist-Zeit</b> aus der Nachkalkulation im Fenster; Lernvorschlag Schweißbaugruppe gesamt "
     "(nur Vorschlag); Kosten je Satz im Fenster Satz in 3D. Ohne Eingabe rechnet alles wie bisher.",
     "Schweißbaugruppe: Zeit von Hand, Rüst-/Stückzeit, Kostenübersicht mit Marge, Preis von Hand, Ablauf-Vorlagen"],
    ["0.9.301", "<b>Neue Oberfläche, Teil 1</b> (UI-Modernisierung): Die Hauptreiter sind einer <b>Seitenleiste "
     "links</b> gewichen, mit Symbolen und nach Arbeitsbereichen gegliedert (Arbeiten, Auftrag, Pflege, "
     "Einstellungen unten). Ab 1600 Pixel Fensterbreite mit Text, sonst nur Symbole; <i>Ansicht → Seitenleiste</i> "
     "legt die Breite fest. Geöffnete Angebote und die Suche stehen jetzt in der <b>Menüzeile</b>, so beginnt die "
     "Arbeitsfläche zwei Zeilen höher. Reiter im ganzen Programm flacher mit Unterstrich. Knopf und Reiter "
     "<b>Zukaufteile</b> im Angebot erscheinen nur noch, wenn das Angebot Zukaufteile enthält ([[fenster]]).",
     "Seitenleiste links statt Hauptreiter, offene Angebote in der Menüzeile, Zukaufteile nur bei Bedarf."],
    ["0.9.300", "<b>Kalkulation nachvollziehbar</b>: Je Position eine <b>Bearbeitungsliste</b> mit Zeit und Kosten je Bearbeitung, das <b>Zeitbild</b> in 7 Zeitarten, ein <b>Schachtelvergleich</b> in einer Tabelle, <b>Qualitätskosten aus dem Prüfplan</b> und bei Zusatzarbeiten <b>Rüstzeit je Los</b> sowie Personal/Maschine. Neuer Unterreiter <b>Kalkulation → Optimierung</b> (Variante gegen Original, Übernehmen nur als neue Fassung) mit <b>Empfindlichkeit ±10 %</b> für Vorschub, Materialpreis, Stundensatz, Rüstzeit und Zusatzarbeiten. "
     "<b>Herkunft und Sicherheit</b> je Preisbaustein (STEP, Stammdaten, Richtwert, gelernt, Hand, geschätzt) mit Kennzahl „Unsicher“ und Hinweis im Angebots-Check ab 5 % ([[herkunft_sicherheit]]); Schneiddaten mit <b>Quelle und Stand</b>. <b>Stammdaten prüfen</b> über Zeilen hinweg ([[stammdaten_pruefen]]), <b>Regelkatalog</b> der Prüfregeln mit einstellbarer Stufe ([[regelkatalog]]). "
     "<b>Rückfragen nur mit Preiswirkung</b> (Feld „Offene Frage“), Wettbewerbsvergleich als <b>Median</b>, <b>Kostentreiber</b> über alle Aufträge ([[kostentreiber]]), Anfrage-Mail mit <b>Fundstelle und Sicherheit</b> je gelesenem Wert und <b>Warum teurer?</b> für zwei Positionen ([[warum_teurer]]). Es wird nichts geschätzt, was nicht gekennzeichnet ist.",
     "Bearbeitungsliste, Zeitbild, Optimierung, Empfindlichkeit, Herkunft/Sicherheit, Stammdaten prüfen, Regelkatalog, Rückfragen mit Preiswirkung, Kostentreiber, Mail-Fundstellen, Warum teurer"],
    ["0.9.299", "<b>PDF-Ausgaben neu gestaltet</b> ([[pdf_design]]): ein Designsystem mit den Farben des Programms "
     "für alle Dokumente. Angebot, Auftragsbestätigung und <b>Lieferschein</b> sind Geschäftsbriefe (Anschrift im "
     "Fensterbereich, Firmenangaben einmal im Fuß); im Angebot steht die <b>Bezeichnung</b> der Position fett über "
     "Profil und Länge, die Staffelpreise in einer Zeile, die Summe mit Linien. <b>Vorschau</b> vor dem Speichern "
     "von Angebot und AB (abschaltbar). Prüfplan fortlaufend statt einer Seite je Teil, Nachkalkulation ohne "
     "leere Kostenarten, Werkstattpapiere „gem. Schnitt“ ohne Umbruch, kurze Tabellen und Summenzeilen werden "
     "nicht mehr getrennt. Lieferschein: <i>Ihre Bestellung</i> zeigt jetzt die Bestellnummer, <i>Ihre Anfrage</i> "
     "die Anfrage. Alle Beträge unverändert.",
     "PDF-Ausgaben neu gestaltet: Geschäftsbrief, Bezeichnung im Angebot, Vorschau, kompakter Prüfplan."],
    ["0.9.298", "<b>Übersicht vor dem Messen</b>: bei größeren STEP-Importen zeigt ein Fenster vorher Baugruppen, "
     "Bauteile, gleiche Teile, vermutete Zukaufteile, Einheit und die geschätzte Messzeit ([[step]]). "
     "<b>Gewindeeinsätze</b> (Nietmutter, Einpressmutter, Helicoil) sind eine eigene Zukauf-Kategorie. <b>An "
     "Außenwänden trennen</b>: im 3D die Außenwände eines Rohrs anklicken, ein angeschweißtes Rohr oder eine Lasche "
     "wird ein eigenes Teil. <b>Kontur aus Kanten</b>: im Rohr- und Blech-Editor gewählte Kanten werden zu einer "
     "Sonderkontur bzw. einem Polygon genau an ihrer Stelle, geprüft auf geschlossen und ohne Selbstüberschneidung; "
     "<b>Skalieren</b> streckt eine Kontur um ihre Mitte ([[kanten_kontur]]). Im 3D wählt ein <b>erneuter Klick</b> "
     "an derselben Stelle das verdeckte Element dahinter, die Tafel zeigt die Größe einer Fläche bzw. den Ø einer "
     "Zylinderfläche und passende Knöpfe ([[ansicht_3d_bedienung]]). <b>DXF-Import</b>: Bohrungen auf einem "
     "Layer GEWINDE, SENKUNG, AUFBOHREN … oder in einer eingestellten Farbe bekommen gleich die Ausführung Gewinde, "
     "Senkung bzw. Bohren ([[dxf_import]]). <b>DXF speichern</b> schreibt Kurven und dichte Punktfolgen als "
     "echte Bögen, auf 0,01 mm genau ([[blech_dxf]]). <b>STL speichern</b> im Rohr- und Blech-Editor, in der "
     "Schweißbaugruppe und im Satz in 3D schreibt das 3D-Modell als STL ([[stl_export]]). <b>Aus Scan/Bild</b> "
     "im Rohr- und Blech-Editor zeichnet Umriss und Löcher aus einem Scan, Foto oder Raster-PDF nach, mit echten "
     "Bögen und erkannten Bohrungen; Maßstab über die Breite des Teils ([[nachzeichnen]]). <b>Gegenrohr</b> mit "
     "Schweißspalt und Kontakt innen oder außen; <b>Werkzeug aus Körper</b>: ein anderes Teil derselben STEP "
     "schneidet das Rohr, die Kontur entsteht genau an der Stelle ([[werkzeug_koerper]]). <b>Rohrzug aus "
     "Punkten</b>: Neue Position aus den XYZ-Punkten der Mittellinie, gerade Rohre mit Gehrungen an den Knicken "
     "werden eine Schweißbaugruppe mit 3D ([[rohrzug]]).",
     "STEP-Import: Übersicht vor dem Messen, Gewindeeinsätze, Rohr an Außenwänden trennen; Kontur aus Kanten, "
     "Kontur skalieren, verdeckte Elemente wählen, Flächendaten; DXF: Gewinde/Senkung/Bohren aus Layer oder Farbe, "
     "Bögen statt Kurven; STL speichern; Kontur aus Scan/Bild; Gegenrohr mit Spalt und Kontakt, Werkzeug aus Körper; Rohrzug aus Punkten"],
    ["0.9.297", "<b>Roadmap Phase 1</b> (alle neuen Schalter Vorgabe aus): Angebots-Check warnt bei <b>altem Materialpreis</b> (30 Tage, Sprung zur Materialanfrage) und nennt <b>„x Stück mehr passen ohne weitere Stange“</b> mit Stückpreis; <b>Live-Stückpreis</b> im Rohr-Editor. "
     "Im Angebot wahlweise <b>Mindermengenzuschlag als eigene Zeile</b>, <b>Preisaufteilung</b> Material/Bearbeitung, <b>Gültigkeit je Werkstoff-Kategorie</b>, <b>Bearbeitung aus den Merkmalen</b> im Text und <b>Vorbehalt</b> bei ungeprüften STEP-Teilen; offene STEP-Merkmale als Fragen in der Rückfrage-Mail. "
     "<b>Kunden-Stückliste</b> als CSV/Excel einlesen, <b>Kundenpreisliste</b> und <b>Stückliste je Satz/Baugruppe</b> als CSV, <b>Maschine samt Schneiddaten als Datei</b> (Stammdaten → Maschinen → Datei). "
     "Zusatzarbeiten je m <b>Schnittlänge</b> bzw. <b>Kantenlänge außen</b> (Entgraten), neue Zusatzarbeit <b>Reiben</b>, <b>Werkstoff-Gleichnamen</b> (AISI 304 = 1.4301 = X5CrNi18-10) für Mail, Formular und STEP. "
     "STEP-Import: Muttern mit umgedrehten Flächen sind Normteile, eine Lasche an einer Mutter fällt nicht mehr als Anbauteil weg.",
     "Roadmap Phase 1: Preisalter, Mehrmenge, Live-Preis, Mindermenge/Preisaufteilung, Stücklisten, Maschinendatei, Entgraten je m, Reiben, Werkstoff-Gleichnamen"],
    ["0.9.296", "<b>Dynamik-Richtwerte</b> für T03, T11 und LT7 (Eilgang, Beschleunigung, Drehzahl) beim Update in leere Felder eingetragen: Drehen, Leerwege und Ecken rechnen damit aus der Dynamik ([[dynamik]]). "
     "<b>Ovale Profile</b> Flachoval, Halbflachoval und Elliptisch mit Gewicht, Trennschnitt und Umriss ([[ovalprofile]]). "
     "<b>Teil wenden</b>: gewendetes Duplikat einer Position, die Stückzahl wird so aufgeteilt, dass die wenigsten Stangen nötig sind; Prüfregel „Teil löst sich nicht“ ([[teil_wenden]]). "
     "<b>Gravurtext mit Platzhaltern</b> ({Angebot}, {Artikel}, {Nr} 23/1000, {Datum}, {KW} …) mit Grenzen und Gravurtexte.csv im CAM-Paket ([[gravurtext]]); <b>Schrift ausschneiden</b> als Schablonenschrift mit Stegen ([[schrift_ausschneiden]]). "
     "<b>Druckluft</b> als drittes Schneidgas (Einstellung <i>Schneiden mit Druckluft</i>, Vorgabe aus): Schneiddaten mit Druckluft gehen dann vor N₂, mit eigenen Gaskosten ([[kalkulation_genauer]]). "
     "<b>Ist-Zeiten aus CSV</b> in der Nachkalkulation: Laufzeiten der Maschine einlesen, Spalten zuordnen, Teile über Position oder Programmname finden ([[nachkalkulation]]). "
     "<b>Hinweis für den Bediener</b> je Position in Werkstattpapieren, Etikett und CAM-Paket; die CAM-Stückliste zeigt Messungen, Schnittqualität, Kante oxidfrei, Mikrostege und Teil am Stangenende ([[bediener]]). "
     "<b>Teil am Stangenende</b> (aus den Adige-Unterlagen, „Abfallvorstellung“): Kann die Maschine den "
     "Abfall vor dem letzten Teil abtrennen (neues Maschinenfeld <i>Teil am Stangenende</i>), nutzt das letzte Teil "
     "den Greiferrest bis auf den Mindestabfall, wenn sein Ende B gerade ist und im Spannbereich keine Kontur liegt. "
     "Das spart Stangen, und lange Teile bis fast zur ganzen Stangenlänge werden möglich ([[optimieren]]). "
     "<b>Fertigungslos</b>: Im Reiter Fertigung lassen sich mehrere beauftragte Aufträge gemeinsam schneiden; die "
     "Werkstattpapiere zeigen Stangen im Los gegen einzeln, die Preise bleiben ([[fertigungslos]]). Neue "
     "<b>Prüfregeln</b>: großer Ausschnitt, Rundloch im Rundrohr, Kontur auf dem Kantenradius, stark geschwächtes "
     "Teil, Kontur im Spannbereich; neue Maschinengrenzen kleinstes spannbares Profil und Stangengewicht des "
     "Laders ([[pruefregeln]]). <b>Laserzeit genauer</b> (Maschinenfelder, leer = aus): Drehzeit je Seitenwechsel, "
     "Messzyklen, Anfahrweg je Innenkontur, Abfall zerteilen, Active Tilt, langsamer auf dicker Wand mit N₂, "
     "Ausrichten asymmetrischer Profile, Laden von Hand unter dem Lademinimum, Entnahme über der Entladegrenze; "
     "neue Schnittqualität je Position (Standard, Qualität, Schnell, Kleines Rohr) ([[laserzeit_genauer]]). "
     "<b>Ganze Stange ohne Trennschnitt</b>: Teile in Lieferlänge gehen ohne Anschnitt und Trennschnitt "
     "(Maschinenfeld, [[optimieren]]). <b>Kante oxidfrei (N₂)</b> je Position, Hinweis bei O₂-Schnitt vor "
     "Pulver, Lack oder Verzinken ([[oxidfrei]]). 2D/3D-Schnitt: 3D-Parameter je Geometrie nach dem größten "
     "Winkel, Ansatz mit Beschleunigungsgrenze ab 3 mm, Eckzeit für Innenkonturen über die Kante, Hinweis bei "
     "3D-Faktor über 1. <b>Dynamik statt fester Zeiten</b>: Leerwege, Drehen und Ecken aus Eilgang, Drehzahl und "
     "Beschleunigungen der Maschine ([[dynamik]]). Neue Prüfregeln „Naht nicht suchbar“ und „Strahl trifft "
     "Gegenflansch“; 3D-Winkel über dem Schwenkwinkel wahlweise als FEHLER.",
     "Teil am Stangenende (weniger Stangen) und Fertigungslos (Aufträge gemeinsam schneiden)"],
    ["0.9.295", "<b>Ideen aus PROfirst und LogiTRACE</b>: Positionen aus PDF-Zeichnung oder Schnellpreis sind "
     "<b>nur kalkuliert</b> und gehen ohne STEP nicht ins CAM ([[nur_kalkuliert]]); <b>Wenden sperren</b> für "
     "Sichtseiten ([[wenden_sperren]]); die Optimierung nimmt auf Wunsch <b>weniger verschiedene Belegungen</b> "
     "bis z. B. 2 % Mehrverschnitt (Einstellung, Vorgabe aus) ([[belegungen]]). <b>Kundenhinweis</b> groß im Angebotskopf ([[kundenhinweis]]), <b>Ertrag nach "
     "Einkauf und nach Herstellkosten</b> ([[ertrag_einkauf]]), Zusatzarbeiten mit <b>Formel und Wertetabelle</b> "
     "([[zusatz_formel]]). Lager mit <b>Meldebestand</b> ([[meldebestand]]), <b>Stangen melden</b> mit offener Menge "
     "und Restplan ([[stangen_melden]]), <b>Teil in früheren Stangenplänen finden</b> ([[stangenplan_suche]]). "
     "Kantteile gegen <b>Gesenke und Presse</b> prüfen, K-Faktor nach Formel ([[kantbarkeit_presse]]). Dazu "
     "Teilebilder beim Auftrag ([[teilebilder]]), Schnittstelle beim Beauftragen ([[auftrag_skript]]), Füllteile als "
     "Vorschlag ([[fuellteile]]) und Abwicklung 1:1 drucken ([[abwicklung_1zu1]]). Selbst angelegte Teile haben "
     "jetzt auch ein <b>3D-Bild und die 3D-Ansicht</b>, gerechnet aus den Eingaben ([[step_3d_ansicht]]).",
     "3D auch ohne STEP, Nur kalkuliert, Wenden sperren, weniger Belegungen, Kundenhinweis, Ertrag, Formel-Zusatzarbeit, Meldebestand, "
     "Stangen melden, Gesenke, Abwicklung 1:1"],
    ["0.9.294", "<b>STEP-Import schneller und genauer</b>: Die 3D-Gegenprobe gegen die STEP läuft schon vor dem "
     "Prüfdialog. Rohre und Kantteile, die im Editor wie in der STEP liegen, sind nicht mehr gelb; Abweichungen "
     "stehen mit Millimeter-Angabe gleich im Prüfdialog. Mehrachsig gekantete Teile werden im Blech-Editor und beim "
     "STEP-Speichern richtig gefaltet. Baugruppen mit vielen angeschweißten Teilen sind etwa doppelt so schnell "
     "gemessen, das Übernehmen großer Baugruppen bleibt nicht mehr stehen ([[step]]). "
     "<b>Zukaufteile</b> (Schrauben, Muttern, Scheiben, Niete, Stifte …) bekommen Kategorie, Norm und Größe; der "
     "Knopf <b>Zukaufteile …</b> im Prüfdialog listet sie mit 3D-Ansicht, ein Klick übernimmt sie als Position "
     "([[importprofile]]). <b>Rohrimport abgesichert</b>: Abweichungen nennen die Ursache, eine Fase am Rohrende "
     "zählt nicht mehr als Abweichung, Rechtsklick <b>Wie in der STEP übernehmen</b> nimmt ein Teil ohne "
     "Editor-Modell, der Werkstoff aus der STEP wird vorgeschlagen, und der Bericht beginnt mit einem "
     "<b>Importbericht je Datei</b>. Wannen mit Ecklaschen falten richtig. <b>Auswahl im 3D</b>, in allen "
     "3D-Fenstern gleich: Körper, Fläche, Kante oder Punkt wählen (die Art steht im Bild), Strg+Klick, "
     "Fensterauswahl, Filter, Ausblenden, Isolieren und Eigenschaften ([[ansicht_3d_bedienung]]). "
     "<b>Ausschnitt mit Tiefe</b>: eine Ausklinkung, bei der die Tiefe eingestellt wird, im Rohr-Editor auf der "
     "gewählten Fläche (Rechteck, rund, Langloch, Polygon; Richtung umkehrbar; Vorschau im 3D) und im Blech-Editor "
     "an einer Kante. 5 mm Tiefe werden nie von selbst zum Durchbruch; was der Laser nicht schneiden kann, wird "
     "mit Grund abgelehnt ([[ausschnitt_tiefe]]).",
     "STEP-Import: 3D-Gegenprobe vor dem Prüfdialog, weniger gelbe Teile, Kantteile richtig gefaltet, schneller; "
     "Zukaufteile mit Kategorie, Norm und Größe als Liste, per Klick ins Angebot; Abweichung mit Ursache, "
     "Wie in der STEP übernehmen, Werkstoff aus der STEP, Importbericht je Datei; Auswahl im 3D (Körper, Fläche, "
     "Kante, Punkt) mit Ausblenden und Isolieren"],
    ["0.9.293", "<b>Schnittstelle zur Rohrlaser Auslastung</b>: Beauftragte Aufträge gehen mit Positionen, Laser- und "
     "Rüstzeit, Zusatzarbeiten und Stangenbedarf von selbst in den gemeinsamen Ordner, Änderungen und Storno auch. "
     "Die Rückmeldung der Auslastung liefert den frühesten Fertig-Tag für <b>Termin prüfen …</b> und die Ist-Laserzeit "
     "für die Nachkalkulation ([[schnittstelle_auslastung]]).",
     "Schnittstelle zur Rohrlaser Auslastung: Aufträge automatisch übergeben, Liefertermin aus dem echten Plan"],
    ["0.9.292", "<b>Was andere Anbieter haben</b>: Eigene <b>Angebotsregeln</b> (Wenn-Dann) im Angebots-Check, z. B. "
     "Edelstahl ab 4 mm Wand mit Gehrung → Zuschlag 8 %, dazu Hinweis, Warnung, Rückfrage an den Kunden oder „Nicht "
     "anbieten“ ([[angebotsregeln]]). Die <b>Reaktionszeit</b> von der Anfrage bis zum Angebot steht in den "
     "Kennzahlen der Startseite und in der Angebots-Auswertung ([[reaktionszeit]]). Die Auswertung zeigt die "
     "Trefferquote jetzt auch je Profilform, Wand, Länge, Komplexität und Stückzahl ([[absage]]). Offene Anfragen "
     "lassen sich nach „Wichtigste zuerst“ sortieren, und die Startseite meldet Stammkunden, die viel länger als "
     "sonst nicht bestellt haben, mit Nachfass-Mail ([[automatik_einstellungen]]).",
     "Angebotsregeln, Reaktionszeit, Trefferquote nach Teilemerkmalen, wichtigste Anfragen zuerst, stille "
     "Stammkunden"],
    ["0.9.291", "<b>Umwegfaktor gemessen</b>: Die Entfernung nach PLZ rechnet jetzt mit Luftlinie × 1,25 statt 1,35. "
     "Gemessen mit den Straßen-km eines Routenplaners ab Delbrück zu 11 Orten in ganz Deutschland (Lippstadt bis "
     "Freiburg und Malchow): 1,25 liegt im Mittel 5,5 % neben der Straße, 1,35 lag 7,5 % zu weit. Ab Delbrück "
     "z. B. Herford wieder 65 €, Dortmund 80 € statt 100 € ([[fracht_entfernung]]). Wer den Faktor in den "
     "Einstellungen selbst geändert hat, behält seinen Wert.",
     "Umwegfaktor der Entfernung nach PLZ gemessen: 1,25 statt 1,35"],
    ["0.9.290", "<b>Kalkulation genauer</b>: Hat ein Profil keinen eigenen Preis und rechnet deshalb mit einem "
     "Tonnenpreis deutlich unter ähnlichen Profilpreisen, warnt der Angebots-Check (vorher zeigte die Position „OK“: "
     "ein S355-Rohr war 32 € billiger als dasselbe in S235). <b>Erledigen</b> legt den ähnlichen Preis als Profilpreis "
     "an ([[angebots_check]]). Dasselbe Teil in mehreren Positionen wird nur einmal programmiert "
     "([[kalkulationsbasis]]). Abrechnungsregeln haben einen eigenen <b>Mindestbetrag je Angebot</b> "
     "([[abrechnungsregeln]]). Das Kalkulations-PDF zeigt das <b>Schnittschema je Mengenstufe</b> "
     "([[staffeln]]). Ältere festgeschriebene Angebote rechnen wie verschickt.",
     "Kalkulation genauer: Preislücke beim Tonnenpreis, Programmierung einmal, Mindestbetrag je Regel, "
     "Schnittschema je Stufe im PDF"],
    ["0.9.289", "<b>Fracht genauer: Entfernung nach PLZ</b>: Das Programm kennt jetzt den Mittelpunkt aller rund "
     "8.300 deutschen Postleitzahlen (ohne Internet) und rechnet die Entfernung vom Versandort zur vollen Ziel-PLZ "
     "(Luftlinie × Umwegfaktor 1,35, einstellbar unter Einstellungen › Frachtkosten). Die Richtwert-Zone richtet sich "
     "nach diesen km statt nach der zweistelligen PLZ-Region (ab Delbrück z. B. Lippstadt 80 € → 65 €, Warburg "
     "100 € → 80 €), die eigene Anlieferung rechnet mit den echten km (Lippstadt 170 € → 60 €). Im Angebot steht "
     "neben Ziel-PLZ und Land das Feld <b>km</b>: grau der gerechnete Wert, eine eingetragene Zahl gilt statt dessen. "
     "Eigene Zonen und Kunden-Zuordnungen bleiben nach PLZ ([[fracht_entfernung]]).",
     "Fracht genauer: Entfernung aus der vollen PLZ, Zone nach km, Feld km im Angebot"],
    ["0.9.288", "<b>Alles sichtbar auf dem Laptop</b> (Layout-Prüfung): Auf schmalen Bildschirmen (1280 und 1366 px) "
     "passen die Reiter des Angebots jetzt immer ohne Blätterpfeile – die Schrittanzeige rechts daneben kürzt sich "
     "dafür (erledigte Schritte nur ✓, ganz schmal nur die Zeichen und „Weiter ▸“; der volle Text steht im Tooltip). "
     "In der Übersicht trennt der Zeilenumbruch keinen Betrag mehr von „€“. Die Einstellungen nutzen einspaltig die "
     "ganze Breite (Ordnerfelder zeigen den ganzen Pfad). Die Nachkalkulation hält die Eingabespalte breit genug; "
     "auf 0 gerundete Abweichungen stehen als „0,00“ statt „-0,00“. In der 3D-Ansicht liegt die Legende auf einem "
     "hellen Feld, lange Hinweise unter dem 3D-Bild lassen sich rollen statt abgeschnitten zu werden, und lange "
     "Teilenamen im Baugruppen-Editor enden mit „…“ (ganzer Name im Tooltip). Kürzere Platzhalter in Suche und "
     "Fertigung, Auswahlfelder im STEP-Dialog mit vollem Text im Tooltip. Ein neuer automatischer Rundgang prüft "
     "alle Seiten, Einstellungen und Menüfenster bei 1280, 1366 und 1920 px auf abgeschnittene und überlappende "
     "Elemente.",
     "Laptop-Layout: alle Angebotsreiter sichtbar, nichts abgeschnitten, 3D-Legende lesbar"],
    ["0.9.287", "<b>Neue Revision eines Artikels erkennen, Auftragschance als Ampel</b> ([[wiederholteile]]): Kommt "
     "ein Artikel mit gleicher Artikelnummer, aber anderer Geometrie wieder (z. B. aus einer neuen STEP), zeigt die "
     "Übersicht <i>Wiederholteile</i> in Orange, was sich geändert hat: <i>geändert gegenüber 2026-00142: 40 mm "
     "länger, 2 Konturen mehr, Schneidweg +20 %</i>. Der Angebots-Check nennt dazu den Staffelpreis von damals und "
     "bei gleicher Menge den von heute mit Abweichung in %. Die Angebotsliste hat die neue Spalte <i>Chance [%]</i> "
     "für verschickte Angebote: grün ab 50 %, gelb ab 25 %, darunter rot; der Mauszeiger nennt die Begründung "
     "(Kunde, Preisklasse, Alter). Die Spalte bleibt weg, solange es zu wenige entschiedene Angebote gibt oder die "
     "Funktion <i>Auftragschance</i> aus ist. Preise ändern sich dadurch nicht. <b>STEP neu einlesen</b> im "
     "Rohr-Editor ([[schneidweg_rechner]]) nimmt die gemerkte Datei der Position (oder eine neuere Revision im selben "
     "Ordner) und zeigt vor dem Überschreiben eine Vorschau: Konturen unverändert, neu, entfallen, geänderte Enden, "
     "Länge und Profil. Von Hand gesetzte Gewinde, Senkungen, Flowdrill und Gravuren bleiben erhalten. Eine "
     "STEP-Datei lässt sich ins Editor-Fenster ziehen. Blech-, Dreh-/Frästeil-, Baugruppen- und Satz-Editor haben "
     "den Knopf <i>STEP neu einlesen …</i> jetzt auch (Prüfdialog, Position wird ersetzt, Rückgängig möglich). "
     "Bei mehreren Teilen in der Datei zeigt die Teilwahl jedes Teil als 3D-Bild; misst die Datei ein anderes "
     "Profil, stellt <i>Profil aus Datei übernehmen</i> die Position darauf um.",
     "Neue Revision eines Artikels wird erkannt; Auftragschance als Ampel; STEP neu einlesen mit Vorschau"],
    ["0.9.286", "<b>Lieferdatum ab Werk und frei Haus</b> ([[lieferdatum_frei_haus]]): Die Frachtlaufzeit wird "
     "eingerechnet. Ab Werk = versandbereit (so wird geplant), frei Haus = beim Kunden. Laufzeit am Frachttarif "
     "(neues Feld <i>Laufzeit [Arbeitstage]</i>), sonst Vorgabe Inland 1 / Ausland 3 Arbeitstage; 0 bei ab Werk, "
     "Abholung, frei Frachtführer und Eigener Anlieferung. Lieferzeit und Wunschtermin meinen bei frei Haus die "
     "Ankunft: <i>Termin prüfen …</i> rechnet ab Werk rückwärts und nennt das Datum frei Haus. Das Fenster "
     "<i>Beauftragt</i> hat beide Daten gekoppelt, Angebotsliste und Fertigung zeigen <i>ab Werk</i> und "
     "<i>frei Haus</i>, Angebot und Auftragsbestätigung nennen das Datum passend zur Lieferbedingung.",
     "Lieferdatum ab Werk und frei Haus: Frachtlaufzeit je Tarif (sonst 1/3 Arbeitstage) wird eingerechnet."],
    ["0.9.285", "<b>Maschinenauslastung als Grafik</b> ([[auslastung]]). Neue Unterseite <i>Auslastung</i> im Reiter "
     "Fertigung (auch <i>Datei → Maschinenauslastung …</i>): <b>Wochenbalken</b> je Maschine (Rahmen = Kapazität, "
     "gefüllt = Aufträge, ab 80 % gelb, über 100 % rot, schraffiert = verschickte Angebote) und eine <b>Plantafel</b> "
     "mit den Aufträgen auf der Zeitachse; Doppelklick öffnet das Angebot. Neue Sicht <b>eingelastet</b>: Die "
     "Aufträge laufen ab heute nach Liefertermin durch die freien Stunden, Überlast rutscht in die Folgewoche; "
     "daraus kommen <i>Laser fertig</i>, Puffer und das <b>Terminrisiko</b> (knapp, überschritten) je Auftrag. Die "
     "bisherige Rechnung bleibt als Sicht <i>Terminwoche</i>. Dazu die <b>gemessene</b> Auslastung der letzten "
     "vier Wochen aus den Scans <i>Laser Start/Ende</i>, <b>Was wäre, wenn …</b> (Auftrag testweise auf andere "
     "Maschine, Zusatzstunden, Samstag; nichts wird gespeichert), <b>PDF</b> für die Werkstattbesprechung, eine "
     "Kachel <i>Auslastung</i> auf der Startseite und die freie Laserzeit bis zum Termin in <i>Termin prüfen …</i>. "
     "Dazu gibt es die Auslastung als <b>eigenes Programm Rohrlaser Auslastung</b>, das ohne die Kalkulation läuft "
     "(Auftragsnummer, kalkulierte Laufzeit, Liefertermin, tatsächliche Laufzeit nach der Fertigmeldung, "
     "Zusatzfelder; Laufzeit in jeder Schreibweise wie <i>1 Stunde 30 Minuten</i>, <i>90 Minuten</i> oder "
     "<i>1:30</i>; Papierkorb, Reihenfolge von Hand, Sperrtage je Maschine, Terminauskunft, Arbeitsliste als PDF und "
     "Hilfe im Programm); <b>Übergabe …</b> auf der Seite Auslastung schreibt die Aufträge als Datei dafür.",
     "Maschinenauslastung als Grafik: Wochenbalken, Plantafel, Terminrisiko je Auftrag, gemessene Auslastung und "
     "Was-wäre-wenn; dazu als eigenes Programm Rohrlaser Auslastung ([[auslastung]])."],
    ["0.9.284", "<b>Schneller starten und STEP-Import schneller</b>: Die STEP-Messung schneidet bei der Profilsuche "
     "jede Lage nur noch einmal (vorher bis zu siebenmal) und baut für die Prüfung der Nahtzugänglichkeit die "
     "Hilfsdaten je Körper einmal auf statt je Messpunkt. Für Nähte und Anbauteile wird der Abstand zweier Teile nur "
     "noch zwischen nahe liegenden Flächen gemessen, auf allen Kernen (Fahrgestell: 400 s auf unter 50 s) – große "
     "Baugruppen laufen damit nicht mehr ins Zeitlimit und bekommen ihre Nähte. Die Messwerte bleiben genau gleich. "
     "Die Startseite füllt "
     "sich erst, wenn sie gezeigt wird, so öffnet das Programm schneller. Neu im Tempo-Protokoll: Dauer des "
     "Programmstarts und jeder STEP-Messung (Lesen, Auswertung der Baugruppe, langsamste Körper), zusammengefasst "
     "im Support-Paket ([[zeitwaechter]]). Behoben: bei zwei gleich langen Berührungen zweier Teile (z. B. beide "
     "Seiten eines Blechs) lag der Nahtverlauf je nach Programmlauf mal auf der einen, mal auf der anderen Seite; "
     "jetzt immer gleich.",
     "Schneller starten, STEP-Messung schneller bei gleichen Werten, Start- und STEP-Zeiten im Tempo-Protokoll"],
    ["0.9.283", "<b>STEP-Import in den Editor an echten Baugruppen nachgeschärft</b> ([[step]]): 18 Baugruppen mit "
     "2.748 Körpern wurden gemessen, übernommen und im Editor gegen die STEP gelegt. Rohre, die nur ein unsicher "
     "erkanntes Blech oder einen Bolzen berühren, werden jetzt ohne Anhaken übernommen (Ampel gelb, die Anbauteile "
     "stehen wie bisher unter <i>Anbauteile prüfen</i>). Winkel mit Ausklinkung am Ende zeigten bei gespiegelten "
     "Teilen eine Zacke am Schenkelende; die Gegenprobe meldete Winkel mit Gehrung fälschlich als „3 mm neben der "
     "STEP“. Rohre mit sehr dicker Wand (ab einem Viertel des Außenmaßes, z. B. 80 × 80 × 25 oder Ø30 × 10) stehen "
     "auf Gelb mit dem Hinweis <i>Dreh- oder Frästeil?</i>. Flachstahl mit Längsfasen, der in den Stammdaten steht, "
     "braucht kein Anhaken mehr. Eine Meldung des STEP-Lesers zur Datei allein setzt gültige Körper nicht mehr auf "
     "<i>prüfen</i>.",
     "STEP-Import: sichere Rohre mit Anbauteil ohne Anhaken, Winkel-Enden richtig, dickwandige Teile auf Gelb."],
    ["0.9.282", "<b>Schweißbaugruppe: genauer, automatisch, übersichtlicher</b> ([[schweissbaugruppe]]). "
     "<b>Genauer</b> (mit den Regeln aus <i>Richtwerte laden</i>): Ansatzzeit je Naht und Seite (10 s), damit viele "
     "kurze Nähte nicht so billig sind wie eine lange; Schweißlage PA/PB/PF/PE als Vorschlag aus dem Nahtverlauf im "
     "STEP (Rundnaht bis 20 kg wird gedreht); Nahtvorbereitung (Fase) für Stumpf- und Ecknähte ab 4 mm; "
     "Richtwert-Kennwerte mit Abschmelzleistung nach Nahtgröße (<i>Richtwerte laden</i> bietet an, alte Richtwerte "
     "zu staffeln). <b>Automatisch</b>: Mit <i>Vorkalkulation automatisch</i> rechnet die Baugruppe ihre Vorschläge "
     "auch bei geschlossenem Editor neu, wenn sich ein Einzelteil ändert (nur im eigenen Entwurf, mit Meldung und "
     "Preisunterschied; Werte von Hand und bestätigte bleiben); leere Schweiß-Stammdaten laden die Richtwerte "
     "selbst; ungeprüfte Nahtgruppen übernehmen geänderte Kennwerte sofort, geprüfte zeigen <i>in den Stammdaten "
     "geändert</i>. <b>Übersichtlicher</b>: Nahtgruppen in einer Grundansicht ohne Querscrollen (Schalter <i>Alle "
     "Spalten</i>, Feld zur markierten Nahtgruppe mit Rechenweg), ohne STEP klappt die leere 3D-Fläche zu, das "
     "Ergebnis steht rechts als Zeilen mit Kostenbalken, Kachel <i>Vorschläge offen</i>.",
     "Schweißbaugruppe rechnet genauer (Ansatzzeit, Schweißlage aus STEP, Fase, Abschmelzleistung nach Nahtgröße), "
     "hält sich bei Änderungen der Teile selbst aktuell und zeigt die Nahtgruppen ohne Querscrollen."],
    ["0.9.281", "<b>Feinschliff aus der Design-Prüfung</b>: In der Bedienungsanleitung stehen Zeichen wie ▾, ▸, │ oder "
     "N₂ jetzt richtig statt als schwarzes Kästchen. Der Knopf <b>Vorgang</b> zeigt nur noch einen Pfeil. Die offenen "
     "Schritte über dem Angebot sind besser lesbar. Der Hinweis „(n abweichend von den Einstellungen)“ steht vorn in "
     "der Kurzfassung der Kalkulation und wird nicht mehr abgeschnitten. Hilfetexte zeigen ein gezeichnetes i-Symbol "
     "vor <b>mehr</b> und <b>Hilfe</b>. Scheitert das automatische Optimieren, stehen wieder die vorläufigen Preise "
     "da statt „wird berechnet …“.",
     "Anleitung ohne Kästchen, Knopf Vorgang mit einem Pfeil, Schritte lesbarer, Abweichungs-Hinweis vorn."],
    ["0.9.280", "<b>Schneller und zuverlässiger</b> (Performance-Update): Jede Änderung im Angebot rechnet Positionswerte, "
     "Schneiddaten, Stangenpreise und Stangenwerte nur noch einmal (vorher für Positionstabelle und Kalkulation "
     "doppelt, mit gestaffeltem Gewinn dreifach); der Angebots-Check nach der Eingabepause rechnet keine zweite "
     "Kalkulation mehr für die Auslastung. Großes Angebot (500 Positionen, gestaffelter Gewinn): Änderung 0,88 → "
     "0,60 s, Check 0,69 → 0,29 s; alle Preise und Werte bleiben auf den Cent gleich. Das Tempo-Protokoll nennt jetzt "
     "auch im Angebot und im Fenster Schweißbaugruppe, welcher Schritt bremst, und ein <b>Hänger-Schutz</b> schreibt "
     "nach 10 s ohne Reaktion sofort eine Zeile ([[zeitwaechter]]). Beim Start wird die Datendatei kurz geprüft "
     "([[datensicherung]]). <b>Angebots-PDF</b> (großes Angebot mit veraltetem Plan) 12,6 → 5,6 s: die Kalkulation "
     "läuft je Klick höchstens dreimal statt 16-mal. <b>Optimieren</b> rechnet nur geänderte Profilgruppen neu "
     "(großes Angebot nach einer Änderung 6,6 → 1-2 s, [[veraltet]]). <b>Werkstattpapiere</b> 4,5 → 3,3 s. Der "
     "Angebots-Check und das Fenster Schweißbaugruppe rechnen weniger doppelt. Schnittpläne und PDFs bleiben gleich.",
     "Änderungen, Angebots-PDF, Optimieren und Werkstattpapiere schneller (gleiche Ergebnisse), Hänger-Schutz, Datenprüfung beim Start."],
    ["0.9.279", "<b>Mehr Intelligenz</b> ([[lernen]]): Der Angebots-Check vergleicht den Preis je kg jedes Teils mit "
     "früheren Teilen derselben Abmessung und ähnlicher Länge und meldet schon 1,5-fache Abweichungen mit Prozent. "
     "Die Wiedervorlage auf der Startseite zeigt je Angebot die geschätzte Auftragschance und steht nach Chance × "
     "Wert. Aus Zusatzarbeiten, die Sie immer wieder von Hand eintragen, schlägt die Lernzentrale ein Erkennungswort "
     "oder eine Arbeitsgang-Regel vor (<b>Übernehmen</b>, mit Rückgängig). Unter dem Verkaufspreis steht, um wie viel "
     "Sie bei Absagen mit Wettbewerbspreis teurer waren, und der Angebots-Check warnt, wenn die zugesagte Lieferzeit "
     "kürzer ist als Ihre echte Durchlaufzeit aus dem Fertigungsstatus. Alles lässt sich unter Einstellungen → "
     "Funktionen → <b>Intelligenz</b> in vier Schaltern einzeln ausschalten; Gelerntes bleibt dabei gespeichert. "
     "Dazu: Die Lernzentrale schlägt <b>Kundenvorgaben</b> vor, wenn die letzten drei Angebote eines Kunden dieselbe "
     "Maschine, Lieferzeit oder Materialvorgabe haben, und eine neue <b>Programmierzeit-Vorgabe</b>, wenn Sie sie "
     "regelmäßig überschreiben. Der Angebots-Check nennt <b>Reklamationen</b> zu Wiederholteilen und meldet, wenn "
     "nachkalkulierte Aufträge des Kunden am Laser deutlich länger brauchten. Nehmen Sie selbst Angewendetes zweimal "
     "zurück, <b>verlernt</b> das Programm es. Startseite und Monatsbericht zeigen, wo Sie auffällig oft verlieren.",
     "Preis-Plausibilität nach Länge, Auftragschance, Regel-Vorschläge, Wettbewerbsabstand, Lieferzeit aus Ist."],
    ["0.9.278", "<b>Angebots-Check: Erledigen</b> ([[angebots_check]]): Punkte, die das Programm selbst lösen kann "
     "(Schnittplan optimieren, Staffelpreise rechnen, aktuelle Preise übernehmen), haben den Knopf <b>Erledigen</b>, "
     "mehrere <b>Alles Automatische erledigen</b>. Ungeprüfte STEP-Teile lassen sich der Reihe nach bestätigen "
     "(<b>Passt, nächstes</b>).",
     "Angebots-Check: Erledigen; ungeprüfte STEP-Teile der Reihe nach bestätigen."],
    ["0.9.278", "<b>Rechtsklick im Prüfdialog</b> ([[erkennung_ampel]]): Passt, Nur dieses Teil aufteilen und Art "
     "direkt am Teil. <b>Preisliste</b> ([[normteile_ohne_preis]]): Lieferant wählbar, abweichende vorhandene Preise "
     "alt → neu zum Prüfen.",
     "Prüfdialog-Rechtsklick mit Passt/Aufteilen/Art; Preisliste mit Lieferant und Preisaktualisierung."],
    ["0.9.278", "<b>Rohr mit angeschweißtem Blech</b> ([[drehfraesteile]]): Kopfplatte oder Lasche mit dem Rohr zu "
     "einem Körper verschmolzen: das Teil ist ein Rohr mit Anbauteil (ein Rundrohr mit Kopfplatte war vorher ein "
     "Drehteil), steht gelb und <b>Aufteilen</b> trennt es in Rohr und Blech als eigene Positionen.",
     "Rohr mit Kopfplatte/Lasche: Rohr statt Drehteil, Aufteilen trennt Rohr und Blech."],
    ["0.9.278", "<b>Passt für gleiche Teile</b> ([[erkennung_ampel]]): <b>Passt (N gleiche)</b> bestätigt dasselbe gelbe "
     "Teil in allen Zeilen und Dateien auf einmal. Unter <i>Werte setzen</i> lassen sich auch <b>Art</b> und "
     "<b>Profil</b> für markierte bzw. alle Zeilen setzen.",
     "Passt (N gleiche); Art und Profil für markierte Zeilen setzen."],
    ["0.9.278", "<b>Gemerkte Art mit Datum</b> ([[step]]): kommt ein Teil wieder, dessen Art von Hand geändert wurde, "
     "steht es grün mit <i>Art wie am TT.MM.JJJJ von Hand gewählt</i>.",
     "Von Hand gewählte Art beim nächsten Import grün mit Datum."],
    ["0.9.278", "<b>Angebots-Check: ungeprüfte STEP-Teile</b> ([[angebots_check]]): Hinweis <i>N Teile aus dem "
     "STEP-Import ungeprüft (gelb)</i> und <i>vereinfacht gemessen</i> mit Sprung zur Position.",
     "Angebots-Check nennt ungeprüfte gelbe und vereinfacht gemessene Teile."],
    ["0.9.278", "<b>Normteil-Preise aus CSV</b> ([[normteile_ohne_preis]]): <b>Preise aus CSV …</b> liest die "
     "Preisliste des Lieferanten, ordnet sie den Normteilen ohne Preis zu (Artikelnummer, Norm + Gewinde + Länge, "
     "Bezeichnung) und trägt die Preise zum Prüfen ein; gespeichert wird mit <b>Preise speichern</b>.",
     "Normteil-Preise aus der Lieferanten-CSV übernehmen."],
    ["0.9.277", "<b>Stangenoptimierung direkt in der Staffel</b> ([[staffeln]]): Im Reiter Staffeln hat das Ergebnis die "
     "Unterreiter <b>Kosten</b> und <b>Stangen</b>; Stangen zeigt die Stangenoptimierung der markierten Stufe "
     "(je Abmessung Stangen, Verschnitt, Ausnutzung, €/m, Materialkosten und das Stangenbild), grau daneben "
     "dieselbe Abmessung im Angebot. Das Fenster der Stufe hat dafür den Reiter <b>Stangen</b>.",
     "Stangenoptimierung je Stufe direkt im Reiter Staffeln und im Fenster der Stufe, mit Vergleich zum Angebot."],
    ["0.9.276", "<b>Kalkulation und Zeiten in der Staffel</b> ([[staffel_kalkulation]]): Ein Doppelklick auf eine Stufe "
     "zeigt neben den Einstellungen die Reiter <b>Kalkulation</b> (Summenzeile, Preis der Stufe je Satz bzw. Position "
     "mit dem Grund jeder Abweichung, Tabelle je Bauteil kompakt oder mit allen Spalten), <b>Zeiten</b> (alle "
     "Arbeitsschritte, Maschinen-, Personal- und Durchlaufzeit, Laserzeit je Satz bzw. Position) und <b>Wirksame "
     "Werte</b> (Wert und Quelle Stufe/Angebot, €/m, Lieferlänge, Stundensätze). Im Reiter Staffeln zeigt die Gruppe "
     "<b>Zeiten</b> die Laser- und Arbeitszeit je Stufe. Vorhandene Staffeln werden dafür einmal neu gerechnet.",
     "Stufe öffnen zeigt Kalkulation, Zeiten und wirksame Werte wie im Angebot."],
    ["0.9.275", "<b>Das Programm lernt</b> ([[lernen]]): Lehnen Sie einen Zusatzarbeit-Vorschlag beim selben Kunden in drei "
     "Angeboten hintereinander ab (✗) bzw. übernehmen ihn (✓), lehnt der nächste STEP-Import ihn gleich ab bzw. "
     "übernimmt ihn, mit Einblendung und Rückgängig im Automatik-Protokoll. Bei Wiederholteilen übernimmt der Import "
     "die Werte, die im früheren Angebot von Hand eingetragen waren (Schneidzeit, Programmierzeit, Einstiche, Gewinde, "
     "Naht), nie den Preis. Neben dem Verkaufspreis steht die Trefferquote des Kunden als Hinweis. Alles Gelernte "
     "zeigt <b>Datei → Lernzentrale …</b>; dort lässt es sich einzeln vergessen. Gelerntes geht über den gemeinsamen "
     "Ordner an die Kollegen; reife Kennwert-Vorschläge aus der Nachkalkulation meldet die Startseite.",
     "Das Programm lernt aus ✓/✗ bei Zusatzarbeiten und Werten von Hand; Lernzentrale, Trefferquote."],
    ["0.9.274", "<b>Prüfdialog ohne Querscrollen</b> ([[erkennung_ampel]]): die Spalte Hinweis zeigt nur ein "
     "Stichwort, der ganze Text steht im Infofeld unter der 3D-Ansicht; Länge, Schneidweg und Konturen stehen dort "
     "und sind als Spalten ausgeblendet (Rechtsklick auf die Kopfzeile blendet sie ein), die übrigen Spalten passen "
     "sich der Fensterbreite an.",
     "Prüfdialog passt ohne Querscrollen ins Fenster, Hinweis als Stichwort."],
    ["0.9.274", "<b>Profil im Prüfdialog anlegen</b> ([[erkennung_ampel]]): fehlt ein gemessenes Profil in den "
     "Stammdaten, legt der Knopf <b>Profil anlegen</b> über der Liste es gleich an (Form und Maße aus der Messung); "
     "die Teile sind danach nicht mehr gelb.",
     "Fehlendes Profil direkt im Prüfdialog anlegen."],
    ["0.9.274", "<b>Gelbe Teile der Reihe nach prüfen</b> ([[erkennung_ampel]]): <b>Nächstes prüfen</b> (F8) springt "
     "zum nächsten gelben Teil, <b>Passt</b> (Leertaste) hakt es an, macht es grün und geht weiter.",
     "Nächstes prüfen (F8) und Passt (Leertaste) im Prüfdialog."],
    ["0.9.274", "<b>Zeitlimit 600 s, sonst vereinfacht</b> ([[step]]): die Vorgabe für das Zeitlimit je Körper ist "
     "600 s (alte Vorgabe 120 s wird einmalig angehoben, eigene Werte bleiben). Braucht ein Körper trotzdem länger, "
     "wird er vereinfacht gemessen (Hüllmaß, Volumen, als Frästeil/Zukauf, gelb) statt gar nicht.",
     "Zeitlimit 600 s; zu langsame Körper vereinfacht statt gar nicht gemessen."],
    ["0.9.274", "<b>Aufteilen auch für Bolzen</b> ([[drehfraesteile]]): angeschweißte Bolzen, Stehbolzen und "
     "Gewindestangen machen einen Körper gelb <i>mehrere Teile</i> und lassen sich mit <b>Aufteilen</b> abtrennen "
     "(glatt Rundstahl/Drehteil, mit Gewinde Normteil); Sechskant mit Schaft bleibt eine Schraube.",
     "Aufteilen trennt auch Bolzen, Gewindestangen und Schrauben ab."],
    ["0.9.274", "<b>Normteile ohne Preis</b> ([[normteile_ohne_preis]]): neuer Unterreiter der Zukaufartikel mit "
     "allen Normteilen ohne EK; Preise in der Zeile eintragen und auf einmal speichern. Der Angebots-Check nennt "
     "Normteile ohne Preis und springt dorthin.",
     "Normteile ohne Preis gesammelt nachtragen (Zukaufartikel)."],
    ["0.9.273", "<b>Angebotsliste mit Anfrage-Nr. und Gewinn</b> ([[angebote]]): neue Spalten <b>Anfrage-Nr.</b> "
     "(Anfrage des Kunden aus dem Angebotskopf, auch über die Suche) und <b>Gewinn [%]</b> (fester Gewinn des Angebots "
     "bzw. der wirksame gestaffelte Satz). <b>Gestaffelter Gewinn im Angebot</b> ([[gewinn_gestaffelt]]): das Feld "
     "<i>Gewinn [%]</i> zeigt jetzt „gestaffelt · 30,0 %“ statt des festen Gewinns der Einstellungen, mit den Stufen "
     "im Tooltip; Knopf <b>Gestaffelt</b> nimmt einen festen Gewinn wieder weg. Bugfix: die Kurzzeile der Kalkulation "
     "zeigt keine leeren Felder mehr (z. B. „Rabatt  %“).",
     "Angebotsliste mit Anfrage-Nr. und Gewinn; gestaffelter Gewinn im Angebot richtig angezeigt."],
    ["0.9.272", "<b>Alle Editoren gleich aufgebaut</b> ([[teile_editor]]): die <b>Schweißbaugruppe</b> und <i>Satz "
     "in 3D</i> haben jetzt denselben Rahmen wie Rohr- und Blech-Editor: oben das Menüband (Konstruktion, Ansicht, "
     "Ausgabe), links Strukturbaum bzw. Teile, in der Mitte die 3D-Ansicht mit den Reitern darunter, rechts das "
     "Ergebnis, unten Kacheln und Prüfmeldungen (Klick springt zur Zeile). Der Strukturbaum und das 3D sind immer "
     "sichtbar, kein eigener Reiter mehr; alle Editoren öffnen maximiert.",
     "Schweißbaugruppe und Satz in 3D aufgebaut wie Rohr- und Blech-Editor."],
    ["0.9.272", "<b>Normteile mit Preis</b> ([[importprofile]]): erkannte Kugeln, Schrauben und Muttern in einer "
     "Schweißbaugruppe oder einem Satz kommen angehakt als <b>Zukaufteil</b> hinein. Der Preis kommt aus den "
     "Zukaufartikeln der Kategorie <b>Normteile</b> (gleiche Bezeichnung); fehlt der Artikel, wird er ohne EK "
     "angelegt und die Position steht gelb <i>EK fehlt</i>, bis der Preis eingetragen ist.",
     "Normteile in Baugruppen und Sätzen als Zukauf mit Preis aus der Normteil-Liste."],
    ["0.9.272", "<b>Aufteilen</b> ([[drehfraesteile]]): ein Körper aus mehreren verschmolzenen Teilen (gelb, z. B. "
     "Platte mit angeschweißter Mutter) lässt sich im Prüfdialog mit dem Knopf <b>Aufteilen</b> über der Liste an "
     "Sechskant bzw. Kugel trennen. Beide Teile werden einzeln gemessen, Lage wie in der STEP; die Mutter wird "
     "Normteil.",
     "Verschmolzene Mutter/Kugel im Prüfdialog abtrennen (Aufteilen)."],
    ["0.9.272", "<b>Langsame Teile im Hintergrund</b> ([[step]]): messen nur noch einzelne Körper, die schon länger "
     "als 20 s laufen, öffnet der Prüfdialog gleich mit allen übrigen Teilen. Die langsamen stehen als <i>Messung "
     "läuft noch</i> da und rücken von selbst nach; OK wartet nötigenfalls auf sie.",
     "Prüfdialog wartet nicht mehr auf einzelne langsame Teile."],
    ["0.9.272", "<b>Prüfsammlung wächst von selbst</b> ([[support_paket]]): eine im STEP-Prüfdialog von Hand geänderte "
     "Art merkt sich das Programm (Kennwerte der Messung und Vorschaubild, keine STEP-Datei und keine Namen); das "
     "Support-Paket nimmt sie mit, daraus werden neue Erkennungsregeln.",
     "Von Hand geänderte Arten kommen ins Support-Paket (ohne STEP-Dateien)."],
    ["0.9.272", "<b>Weniger Rückfragen</b> ([[meldungen]]): Stammdaten-Zeilen löschen, Richtwerte "
     "Schweißen und Fracht laden, Vorlagen (Baugruppe, Kontur, Schneidweg) überschreiben oder löschen und den "
     "Preisstand eines Zukaufartikels im Angebot aktualisieren geschehen sofort, die Einblendung bietet "
     "<b>Rückgängig</b>. Große STEP-Dateien werden ohne Frage gemessen (Größe und Dauer in der Fortschrittsanzeige), "
     "nach einem Abbruch kommen die gemessenen Dateien gleich in den Prüfdialog, die Erstmusterprüfung bietet die "
     "Meldung nach dem Prüfplan mit <i>Übernehmen</i> an.",
     "11 Rückfragen durch Rückgängig bzw. Übernehmen ersetzt."],
    ["0.9.271", "<b>STEP-Erkennung nach der Prüfsammlung</b> ([[drehfraesteile]]): 53 typische Teile aus Baggerschaufel, "
     "Dach und Anlage wurden bestätigt, die 21 erkannten Fehler sind behoben. Kugeln und Schrauben/Gewindestangen mit "
     "Sechskant sind <b>Normteile</b> (erst nach Anhaken übernommen), Ringe mit Kalotten und Hülsen mit Boden sind "
     "Drehteile. Winkel ohne Normmaß oder mit Biegeradius und abwickelbare Sonderprofile sind Kantteile; die gespiegelte "
     "Kopie eines Kantteils wird jetzt auch als Kantteil erkannt. Flachstahl mit Ausschnitten oder kürzer als 3 × Breite, "
     "Brennteile mit Schweißfasen und Platten mit Einpressmuttern sind Bleche, ein kurzer Klotz mit Bohrung ist ein "
     "Frästeil. Ein Körper aus <b>mehreren verschmolzenen Teilen</b> steht gelb und wird nicht übernommen. "
     "Modellierte Gewinde misst der Import vorab als Drehteil statt minutenlang ein Profil zu suchen (0003-400-001: "
     "22 statt 58 Minuten), die Länge von Drehteilen mit gegenläufigen Zylinderachsen stimmt wieder (Rolle 10 mm kam "
     "als 2534 mm), und der Zeitwächter nennt beim Übernehmen aus dem STEP die langsamen Abschnitte "
     "([[zeitwaechter]]).",
     "STEP: Normteile, Ringe, Kantteile, Bleche und verschmolzene Teile richtig; Gewinde schnell; Drehteil-Länge."],
    ["0.9.270", "<b>Blech-EK je Satz und je Schweißbaugruppe</b> ([[satz_bearbeiten]]): den kompletten Einkaufspreis "
     "der Bleche (ebenso Vollmaterial, Dreh-/Frästeile) gibt es jetzt in allen Editoren: im Fenster <i>Satz "
     "bearbeiten</i>, in <i>Satz in 3D</i> und im Editor der <b>Schweißbaugruppe</b> als <b>Einkauf je Baugruppe</b>. "
     "Der Betrag wird nach Gewicht auf die Teile umgelegt (× Anzahl Sätze bzw. Baugruppen). Neu im Rechtsklick: "
     "<i>Blech-EK je Satz/Baugruppe …</i>. Gibt es keine passenden Zukaufteile, sagt die Zeile, warum kein Feld da ist.",
     "Blech-EK komplett je Satz und je Schweißbaugruppe, in allen Editoren und per Rechtsklick."],
    ["0.9.269", "<b>Einfacher bedienen</b>: oben rechts steht das Feld <b>Suchen … (Strg+K)</b>; es findet jetzt auch "
     "die Knöpfe der offenen Seite ([[befehlspalette]]). Die Schrittanzeige im Angebot ist anklickbar, der Knopf "
     "<b>Weiter: …</b> führt den nächsten Schritt aus. Die <b>Lieferzeit</b> steht in einem Feld: einfach "
     "„3 Wochen“, „10 AT“, „KW 48“ oder „15.11.“ schreiben ([[lieferzeit]]). Sechs Rückfragen sind weg (Schneidweg "
     "ersetzt die STEP-Werte, Zielpreis, Zukauf-Preisstand, Änderungsverlauf, Ursprung zurücksetzen): es passiert "
     "sofort, die Einblendung bietet <b>Rückgängig</b> ([[rueckgaengig]]). Fehlermeldungen sagen in Klartext, was "
     "los ist und was zu tun ist (z. B. Datei in einem anderen Programm geöffnet). Neue Arbeitsplätze bekommen einmal "
     "die Liste <b>Erste Schritte</b> (Hilfe → Erste Schritte …, [[erste_schritte]]). Keine abgeschnittenen Texte mehr "
     "bei 1366 × 768; die 3D-Leiste bricht um, das Prüfmeldungsfeld im Editor ist ohne Meldung nur eine Zeile hoch.",
     "Suchfeld, Weiter-Knopf, Lieferzeit in einem Feld, Rückgängig statt Rückfrage, Fehler in Klartext, Erste Schritte."],
    ["0.9.268", "<b>STEP genauer</b> ([[step]]): Flachstahl mit Längsfasen an den Kanten (z. B. die Schneidkante einer "
     "Baggerschaufel) galt bisher als glattes Rechteck, die Fasen fielen weg. Jetzt meldet der Import „Querschnitt mit "
     "Längsfasen“ mit den Maßen, das Teil steht gelb, und Skizze und 3D zeigen den Querschnitt wie in der STEP. "
     "Zuschnitte von Blechen und Kantteilen mit kleinen gerundeten Ecken galten als Rechteck, der Schneidweg im "
     "Blech-Editor lag bis 1 % zu hoch. Jetzt gilt ein Zuschnitt nur noch als Rechteck, wenn auch der Umfang passt; "
     "sonst rechnet der Editor mit der Kontur aus der STEP.",
     "STEP: Flachstahl mit Längsfasen und Zuschnitte mit runden Ecken wie in der STEP."],
    ["0.9.267", "<b>Einzelteile, Satz und Schweißbaugruppe umwandeln</b> ([[umwandeln]]): per Rechtsklick werden markierte "
     "Einzelteile ein Satz (Name und Anzahl Sätze im Fenster, Vorschlag = größter gemeinsamer Teiler der Stückzahlen), "
     "ein Satz eine Schweißbaugruppe (Editor mit allen Teilen, Anzahl Baugruppen = Anzahl Sätze) und beides wieder "
     "zurück. Aus einer Baugruppe wird ein Satz mit denselben Teilen und Stückzahlen; Nähte, Arbeitsgänge und "
     "Vorrichtungen merkt sich das Programm und setzt sie beim Zurückwandeln wieder ein. Dieselben Knöpfe stehen in "
     "Satz in 3D, Satz bearbeiten und im Editor der Schweißbaugruppe. Preise, Zusatzarbeiten, Konturen und Lage der "
     "Teile bleiben gleich.",
     "Einzelteile ↔ Satz ↔ Schweißbaugruppe per Rechtsklick umwandeln."],
    ["0.9.266", "<b>Fehler behoben, gemeinsamer Ordner</b> ([[mehrere_arbeitsplaetze]]): sobald ein gemeinsamer Ordner eingetragen war, kam "
     "alle 15 Sekunden „Unerwarteter Fehler: 'dict' object is not callable“; Lebenszeichen und Sofort-Schreiben "
     "liefen dann nicht mehr. Der Takt läuft jetzt wieder fehlerfrei.",
     "Gemeinsamer Ordner: Fehler alle 15 Sekunden behoben."],
    ["0.9.265", "<b>STEP-Import schneller</b> ([[step]]): als Satz oder Schweißbaugruppe prüft das Programm bei gleichen "
     "Teilen, wie jede Kopie eingebaut ist (gedreht, gewendet). Bei vielen gleichen Kleinteilen (z. B. 173 Schrauben im "
     "Pizzaofen) dauerte das über eine halbe Stunde. Jetzt wird jede Kopie nur einmal gesucht und aussichtslose Drehungen "
     "werden früh verworfen: 5-mal so schnell, die Lage ist dieselbe. Gedreht eingebaute Kopien gleicher Bleche, Kantteile, "
     "Dreh- und Frästeile werden nicht mehr einzeln gemessen, sie übernehmen die Messung des ersten Teils (Pizzaofen: "
     "Messung 4 statt 9 Minuten); Rohre und Profile werden weiter einzeln gemessen. Behoben: große Baugruppen mit "
     "Kantteilen (z. B. 0003-400-001) blieben beim Import hängen, wenn ein Kantteil eine Auswahl mit weiterer Auswahl "
     "hatte; ein solches Teil kommt jetzt mit, notfalls mit Fehlermeldung statt endlosem Warten. Das Zeitlimit je Körper "
     "gilt beim Abschluss großer Baugruppen je Schritt, der Abschluss begann sonst immer wieder von vorn.",
     "STEP-Import großer Baugruppen mit vielen gleichen Teilen deutlich schneller."],
    ["0.9.264", "<b>STEP-Import stabiler</b>: ein Rohr mit Anbauteil längs, dessen Innenkontur in der STEP als Ellipse mit "
     "gleichen Radien gespeichert ist, brachte die Messung zum Absturz (Anhänger-Dach). Jetzt wird es normal gemessen. "
     "<b>Flachstahl mit runden oder abgerundeten Enden</b> (z. B. Lasche mit Radius, Ecken R10): das Ende stand im "
     "Schneidweg-Rechner gerade und dafür zwei falsche Sonderkonturen quer über dem Teil. Jetzt ist es ein komplexes "
     "Ende mit dem Umriss wie in der STEP.",
     "STEP-Import stabiler (Anhänger-Dach), Flachstahl mit runden Enden wie in der STEP."],
    ["0.9.263", "<b>Kantteile aus der STEP</b> ([[bleche]]): die Biegezone wird echt abgerollt. Ein Fenster oder "
     "Ausschnitt quer über einer Kante, ein Freischnitt oder eine Bohrung in der Biegung steht jetzt mit ihrem "
     "Umriss im Zuschnitt (vorher ein Schlitz bis zum Rand, ohne Schenkel im Blech-Editor) und ist als <i>über "
     "Biegung</i> gekennzeichnet. <b>Ellipsen</b> in Blechen heißen Ellipse mit Achsen statt Polygon. Ein gekantetes C mit flachen Schenkel-Enden "
     "vorne und hinten ist ein Kantteil (vorher U-Profil); leicht angekantete Bleche (2°–30°) haben die richtige "
     "Kantrichtung (vorher teils Z statt Wanne, 2°/5° Flachstahl), seitliche Stecknasen sind in der Außenkontur. Dicke Platten mit Senkungen sind Bleche (vorher Frästeil), ein C-Halter mit eingerollten Enden ist ein Kantteil "
     "(vorher Sonderprofil), ein warmgewalzter Winkel mit ganz gerundeten Schenkelenden ist ein L-Profil (vorher offenes "
     "Sonderprofil, nicht kalkuliert). "
     "Kantteile mit <b>eingeprägten Taschen</b> sind Kantteile (vorher kein Zuschnitt), die Prägung ist im Zuschnitt "
     "geschlossen. <b>IGES-Import</b> ([[step]]): .igs/.iges gehen überall wie STEP, Flächen werden genäht, "
     "Biegungen und Bohrungen echt erkannt. <b>Fehler behoben</b>: große Baugruppen (z. B. Palettenwagen, "
     "Formenregal) brachen beim Import ab.",
     "IGES-Import; Kantteile: Ausschnitt über der Biegung richtig abgewickelt, Ellipsen, Prägungen"],
    ["0.9.262", "<b>Fehler behoben</b> im Fenster STEP-Import prüfen: Eine <b>Regel des Kunden</b> ([[profil_regeln]]) "
     "mit anderer Profilform (z. B. Quadrat- statt Rechteckrohr) ließ beim Zurückstellen auf das gemessene Profil die "
     "Form der Regel stehen; die Position bekam dann den Hinweis <i>Profil fehlt in Stammdaten</i> und neu gerechnete "
     "Enden mit kürzerem Schneidweg als in der STEP. Jetzt gilt wieder die gemessene Form, das Teil wird genau wie ohne "
     "Regel übernommen. Der Haken <b>Nur zu prüfende</b> ([[erkennung_ampel]]) geht von selbst aus, wenn nichts mehr "
     "zu prüfen ist (vorher blieb die Liste leer).",
     "Fehler behoben: Regel des Kunden zurückstellen, Haken Nur zu prüfende"],
    ["0.9.261", "<b>Regeln des Kunden</b> ([[profil_regeln]]): wählt man im STEP-Import für ein Teil ein anderes Profil "
     "als das gemessene, gilt das beim nächsten Import desselben Kunden automatisch für alle Teile mit diesem "
     "gemessenen Profil (gelb mit Hinweis <i>Regel des Kunden</i>; das gemessene Profil wählen stellt zurück und "
     "löscht die Regel). Der <b>Zeitwächter</b> ([[zeitwaechter]]) schreibt jetzt auch den Arbeitsspeicher mit, das "
     "Support-Paket nennt den höchsten Stand. Intern: Prüfsammlung für echte STEP-Dateien und gleich lange Testteile.",
     "Regeln des Kunden aus Profil-Korrekturen, Arbeitsspeicher im Zeitwächter"],
    ["0.9.260", "<b>Ampel nach dem STEP-Import</b> ([[erkennung_ampel]]): im Fenster STEP-Import prüfen zeigt ein "
     "Farbpunkt je Teil, wie sicher Art, Profil und Konturen erkannt sind (grün sicher, gelb prüfen, rot nicht "
     "übernehmbar), mit Grund im Tooltip, Zusammenfassung unter der Liste und Haken <i>Nur zu prüfende</i>. "
     "<b>Startseite</b>: <i>N Fehler seit gestern</i> mit Knopf <i>Support-Paket …</i> und, sobald genug "
     "Nachkalkulationen da sind, <i>Laserzeit Ist gegen Soll</i> je Maschine. <b>Referenzangebote</b> "
     "([[referenzangebote]]): bis zu fünf Angebote festhalten (<i>Ausgaben</i>) und nach einem Update unter "
     "<i>Hilfe → Referenzangebote prüfen …</i> nachrechnen. Die automatischen Tests laufen in drei Teilen "
     "gleichzeitig (schneller zum Update).",
     "Ampel nach dem STEP-Import, Fehler und Laserzeit auf der Startseite, Referenzangebote"],
    ["0.9.259", "<b>Mehr Platz für die Positionsliste</b> ([[mehr_platz]]): auf einem Laptop (1366 × 768) "
     "13 statt 9 sichtbare Zeilen. Angebotskopf, Kalkulation und Fracht stehen zugeklappt in einer Zeile, die "
     "Knopfleiste passt in eine Zeile (Ablagefeld <i>STEP / DXF</i>). <b>»</b> im Titel klappt die Übersicht ein; "
     "rechts bleibt ein schmaler Streifen mit Farbpunkt und Verkaufspreis, <b>«</b> oder ein Klick holt sie zurück "
     "(gemerkt). <b>Spalten-Ansichten</b> ([[spalten_ansichten]]): über der Liste <i>Alle · Erfassen · Prüfen · "
     "Preis</i> zeigen nur die Spalten für den Arbeitsschritt; <i>STEP-Werte</i> und <i>Berechnete Werte</i> stehen "
     "jetzt im Menü <i>Weitere Spalten</i>. <b>Nichts doppelt</b>: Meldungen nur in der Einblendung, der grüne Kasten <i>Optimierung "
     "abgeschlossen</i> entfällt (Schrittanzeige), <i>▸ Alle zuklappen</i> kürzer, <i>Angebots-Check …</i> im Menü "
     "Ausgaben nur bei eingeklappter Übersicht, <i>Arbeitsgänge vorschlagen …</i> nicht mehr im Rechtsklick.",
     "Mehr Platz: Kopf und Knopfleiste je eine Zeile, Übersicht einklappbar, Spalten-Ansichten, nichts doppelt"],
    ["0.9.258", "<b>Zeitwächter</b> ([[zeitwaechter]]): jede Stelle, an der das Programm länger als 0,5 s nicht "
     "reagiert, steht mit Dauer, Ort und der Bedienung davor in <i>Daten/Protokoll/tempo.log</i>. Das "
     "<b>Support-Paket</b> enthält die Datei und eine Zusammenfassung der häufigsten langsamen Stellen. Die "
     "automatische Prüfung achtet jetzt darauf, dass eine Eingabe im Angebot nie neu optimiert und die Kalkulation "
     "nur einmal rechnet. Dazu <b>schneller</b>: die Anzeige nach jeder Änderung spart die Schnittplan-Auswertung je "
     "Gruppe, die Prüfung gleicher Spalten und bei Angeboten ohne Fracht die Positionswerte (500 Positionen: Zelle "
     "ändern 0,83 → 0,73 s), der Reiter Nachkalkulation rechnet die Kalkulation einmal statt dreimal.",
     "Zeitwächter: langsame Schritte im Protokoll und im Support-Paket; Anzeige nach Änderungen schneller"],
    ["0.9.257", "<b>Wieder schneller</b> ([[tempo_0411]]): Seit 0.9.235 rechnete jede Änderung im Angebot deutlich mehr "
     "als nötig. Die Suche nach Wiederholteilen lief nach jeder Änderung neu, sogar bei einer Stückzahl, und doppelt; "
     "jetzt nur noch, wenn sich andere Angebote oder Artikelnummer, Profil, Werkstoff, Länge oder Konturen ändern, "
     "und sie vergleicht nur Teile mit passender Länge. Der Angebots-Check in der Übersicht rechnet Maschinenvergleich "
     "und Kalkulationsbasis erst nach etwa 1 s Ruhe (der Check vor dem PDF immer sofort). Der Grundwerte-Check nutzt "
     "die schon gerechnete Kalkulation, "
     "der Vorgang wird ohne das ganze Angebot gelesen. Im gemeinsamen Ordner verglich die Suche nach Konfliktkopien "
     "jede Datei mit jeder (bei 1.000 Nummern-Dateien rund 7 s, zweimal bei jedem Schreiben nach einer Änderung); "
     "jetzt Bruchteile einer Sekunde. Gemessen: Stückzahl ändern bei 200 Angeboten 0,5 s statt 2,0 s, Angebot öffnen "
     "0,9 s statt 1,4 s. Alle Ergebnisse bleiben gleich.",
     "Wieder schneller: Ändern im Angebot, Öffnen, Schreiben in den gemeinsamen Ordner"],
    ["0.9.256", "<b>Einzelteile aufgeräumt</b> ([[saetze_abheben]]): Einzelteile stehen unter einem grauen Band "
     "<i>Einzelteile</i> mit Positionen, Stück, Gewicht, Preis und offenen Vorschlägen; zugeklappte Sätze, Baugruppen "
     "und Einzelteile sind nur noch das Band, der Status zeigt nur sein Symbol, der Zeilenkopf keine zweite Nummer. "
     "<b>Vorschläge für alle Teile</b> ([[zusatz_erkennen]]): der gelbe Knopf übernimmt oder lehnt jede "
     "Zusatzarbeit für alle Teile auf einmal ab, ✓/✗ direkt in der Zelle, <i>Einzeln prüfen</i> zeigt nur offene Punkte. "
     "<b>✓/✗ für jede Zusatzarbeit</b> ([[zusatz_unterzeilen]]): in den Zeilen unter der Position bestätigen oder "
     "entfernen, auch Gewinde; offene Gewinde, Senkungen und Flowdrill aus der STEP bestätigen oder ablehnen, einzeln "
     "oder für alle Teile.",
     "Einzelteile mit Band; Zusatzarbeiten, Gewinde und Bohrungen für alle Teile bestätigen oder ablehnen"],
    ["0.9.255", "<b>Schweißbaugruppen</b> ([[vorkalkulation_baugruppe]]): Außennähte (Stumpf- und Ecknaht) bekommen "
     "in der Vorkalkulation immer mindestens <i>Naht verschleifen</i>, Kehlnähte in der Innenecke nicht. Scheitert "
     "die STEP-Messung an einem Teilepaar, bleiben die übrigen Nahtkandidaten erhalten (vorher gingen alle verloren, "
     "auch bei Unterbaugruppen), mit Hinweis <i>Nahtkandidaten unvollständig</i>. Gleiche Teile in mehreren "
     "Unterbaugruppen bekommen beim STEP-Import je Unterbaugruppe eine eigene Position, statt alle direkt an der "
     "Baugruppe zu hängen.",
     "Außennähte immer verschleifen; gleiche Teile je Unterbaugruppe eine Position; Nahtkandidaten robuster"],
    ["0.9.254", "<b>Art immer wählbar: Blech, Rohr/Profil oder Dreh-/Frästeil</b> ([[art_auswahl]]): kurze dicke "
     "Kantteile (z. B. Winkel 40 × 40 × 8 mit Biegeradius) wurden als Frästeil erkannt, die Biegeradien zählten sogar "
     "als Bohrungen. Jetzt entscheidet eine zentrale Regelliste die Art und nennt den Grund in der Hinweisspalte; ein "
     "Kantteil mit Biegeradien wird nie Frästeil. Jedes Teil wird in allen drei Arten gemessen, die Spalte Art im "
     "Prüfdialog bietet immer alle drei an (nicht messbare ausgegraut mit Grund), Preis und 3D rechnen sofort neu "
     "(Dreh-/Frästeile goldgelb). Die Wahl merkt sich das Programm für das gleiche Teil. Nach dem Übernehmen: "
     "Rechtsklick bzw. Knopf in den Editoren <i>Art ändern …</i>. Dazu: <b>Richtpreis Dreh-/Frästeil "
     "überschreiben</b> wie beim Blech ([[drehfraes_richtpreis]]) mit eigenen Werten je Teil, und der Editor zeigt "
     "das Teil <b>in 3D wie in der STEP</b> (echte Form und Lage, goldgelb).",
     "Art Blech / Rohr / Dreh-Frästeil immer wählbar, Kantteile nie Frästeil, Richtpreis Dreh-/Frästeil überschreibbar, Dreh-/Frästeil-Editor mit 3D wie STEP"],
    ["0.9.253", "<b>Sätze übersichtlicher</b> ([[saetze_abheben]]): jeder Satz und jede Schweißbaugruppe hat ein "
     "<b>Kopfband</b> mit Anzahl, Teilen, Fläche, Gewicht und Preis je Satz. Klick aufs Band markiert den ganzen Satz, "
     "Doppelklick öffnet <i>Satz bearbeiten</i>. Jeder Satz hat eine eigene, kräftigere Farbe (sechs Farben reihum statt "
     "zwei blasser). Die Spalte Satz ist ausgeblendet (über Weitere Spalten), Status <i>OK</i> nur als Häkchen, "
     "Positionsart nur bei Bedarf, und der Knopf <b>Übersicht</b> blendet die rechte Spalte aus.",
     "Sätze mit Kopfband, Summen und eigener Farbe; Übersicht ausblendbar"],
    ["0.9.252", "<b>Zusatzarbeit für ganzen Satz repariert</b> ([[zusatz_satz]]): Rechtsklick auf eine "
     "Schweißbaugruppe oder eines ihrer Einzelteile brachte bisher die Meldung „Bitte eine Position markieren, die in "
     "einem Satz steht“. Jetzt öffnet sich das Fenster für alle Einzelteile der Baugruppe (Stück je Baugruppe, Fläche "
     "und Gewicht je Baugruppe). Die Kopfzeile eines zugeklappten Satzes steht bei <i>Zusatzarbeiten …</i> für den "
     "ganzen Satz, und im Reiter <i>Kalkulation</i> gibt es jetzt ein Rechtsklick-Menü.",
     "Zusatzarbeit für ganzen Satz auch bei Schweißbaugruppen, zugeklappten Sätzen und in der Kalkulation"],
    ["0.9.251", "<b>Gewinde aus dem Blech-Editor</b> ([[blech_richtwerte]]): Bohrungen, die im Blech-Editor die "
     "Ausführung <i>Gewinde schneiden</i> haben, kommen beim Übernehmen bestätigt ins Bohrbild der Position und kosten "
     "€ je Stück aus Einstellungen › Gewinde zusätzlich zum Blech-EK (nicht im Richtpreis). Vorher wurden sie nur "
     "gezählt und nicht berechnet.",
     "Bleche: im Editor gewählte Gewinde werden berechnet"],
    ["0.9.250", "<b>Richtpreis für Dreh- und Frästeile</b>: neue Dreh-/Frästeile aus dem STEP-Import bekommen einen "
     "geschätzten EK aus Rohling (Lagermaß, €/kg), <b>Arbeitsgängen</b> mit Zeiten aus Schnittwerten (Schruppen, "
     "Schlichten, Bohren, Einstechen, Planfräsen, Taschen …), Rüsten und Programmieren auf die Stückzahl verteilt, "
     "Zusätzen €/Stück und Aufschlag des Lieferanten, mit Hinweis <i>Fremdangebot einholen</i>. "
     "<b>Machbarkeitsprüfung</b> als Ampel (tiefe Bohrung, schlankes Teil, dünne Wand, kleiner Innenradius, tiefe "
     "Tasche, Maschinengröße) und <b>Skizze</b> Rohling/Fertigteil im Dialog <i>Richtpreis Dreh-/Frästeil …</i>; "
     "Zeiten von Hand änderbar, Staffeln rechnen je Stufe neu; Werte unter Einstellungen → Dreh- und Frästeile "
     "([[drehfraes_richtpreis]]). Neu <b>Fräsen nach Bearbeitung …</b> (Rechtsklick): Teil oder Schweißbaugruppe "
     "danach planfräsen, bohren, Gewinde, reiben, Taschen; Preis je Stück als Zusatzarbeit, eigene Maschine oder "
     "Lohnfertiger ([[fraesen_nach]]). STEP-Import erkennt jetzt auch <b>Flansche mit Lochkreis</b>, <b>Ringe mit "
     "Lasche</b> und <b>gebohrte Verteilerblöcke</b> als Dreh-/Frästeil; Messing CW…; Rohling bei Alu/Messing als "
     "Rund-/Flachmaterial. Eigene Tabelle <b>Dreh-/Fräs-Werkstoffe</b> (Gruppe, Dichte, Stangenpreis €/kg, "
     "Zerspanbarkeit %) wie bei den Blechen ([[drehfraes_werkstoffe]]).",
     "Richtpreis für Dreh-/Frästeile mit Arbeitsgängen, Machbarkeit und Skizze; Fräsen nach Bearbeitung"],
    ["0.9.249", "STEP-Import: <b>Dreh- und Frästeile</b> (Welle mit Absätzen, Bolzen mit Einstich oder Fase, Buchse, "
     "Block mit Tasche, ausgefräster Winkel) werden erkannt und <b>Zukaufteile</b> ohne EK statt gelaserter Rohre "
     "oder Profile, mit Kategorie Drehteile bzw. Frästeile; gleiche Teile aus früheren Anfragen nehmen den vorhandenen "
     "Artikel ([[drehfraesteile]]). <b>Bleche</b>: dicke schmale flache Teile sind jetzt auch Bleche, Flachstahl steht "
     "nur noch zur Wahl, wenn die Größe passt; der <b>Werkstoff</b> der Bleche passt sich den Rohren der Datei an, "
     "sonst S235 ([[bleche]]). <b>Kantteile mit Biegeradien</b> sind Blech gekantet, außer ihre Maße sind ein "
     "<b>Standard-Kantprofil</b>: U-Stahl (rund-/scharfkantig nach unserer Liste), Kant-C und Kant-L stehen jetzt in "
     "den Stammdaten ([[profile]]). Ein offen gezeichnetes Rohr gilt nur mit ganzen Außenmaßen als Rohr, "
     "wenn das Rohr genau so groß ist wie das Teil, ein C mit Lippen nur bis 20 mm Schlitz; sonst Kantteil, das Rohr in "
     "der Spalte Art wählbar ([[offene_rohre]]). <b>Kantteile</b>: Hut, Z, Dachwinkel, Sicke, Saum und mehrachsige "
     "Halter sicher Blech gekantet, Grund in der Hinweisspalte, Abwicklung schräg im Raum richtig. <b>Winkel</b>: "
     "mit Biegeradius (außen = innen + Dicke) immer Kantteil, scharfkantig oder nur innen Radius immer L-Profil; "
     "die 3D-Ansicht zeigt die gewählte Art (Kantteil blau, Profil mit Anfangs-/Endschnitt). <b>Zukaufteile</b> im Import nur bei Schweißbaugruppe angehakt, sonst von Hand; "
     "im Fenster Satz bearbeiten <b>Einkauf je Satz</b> für Bleche, Vollmaterial und Dreh-/Frästeile, nach Gewicht "
     "umgelegt ([[satz_bearbeiten]]). Sicherere Erkennung: Rolle mit Radius, Flansch mit Absatz, Teile schräg im Raum, "
     "gleichschenkliger Kant-Winkel; eine Testreihe mit über 50 gebauten Teilen prüft das.",
     "Dreh- und Frästeile als Zukauf, Kantprofile Standard, Zukauf-Haken, Einkauf je Satz"],
    ["0.9.248", "<b>Automationen</b> ([[automatik]]): Neue Anfragen werden im Hintergrund <b>vorgemessen</b> (Teile, "
     "Profile, Richtpreis) und stehen nach einer <b>Ampel</b> für die Antwortfrist sortiert. <b>Nachträge</b> legt das "
     "Programm selbst in den Angebotsordner (gelbe Leiste <i>Übernehmen</i> im Angebot), <b>Bestellungen</b> erkennt es "
     "und gleicht sie mit dem Angebot ab (<i>Bestellung prüfen …</i>), <b>Wiederholanfragen</b> ohne STEP werden aus "
     "dem Teilekatalog ein neues Angebot, fehlende Kundendaten kommen aus der Signatur. <b>Auftrag starten</b>: "
     "Häkchen im Fenster Beauftragt für AB, Materialbestellung, Werkstattpapiere, CAM und Etiketten. "
     "<b>Lieferantenantwort einlesen</b> (Mail/PDF), <b>Material bestellen</b> beim gewählten Lieferanten mit "
     "Wareneingang auf der Startseite, <b>Preiswächter</b> für offene Angebote, <b>Nachkalkulation vorbelegt</b> beim "
     "Versand. Beim Angebot: <b>Übernehmen und fertigstellen</b> (PDF, Outlook-Antwort, Verschickt, Wiedervorlage, "
     "nächste Anfrage), günstigste Maschine, Lieferzeit nach Auslastung, Beistellung und Oberfläche aus der Mail, "
     "Rückfrage vorbereitet, Lernen aus Nacharbeit, Anfragen automatisch zuweisen. Alles steht unter <i>Datei → "
     "Automatik-Protokoll …</i> und lässt sich zurücknehmen.",
     "Automationen: Anfragen vormessen und Ampel, Nachtrag/Bestellung zuordnen, Auftrag starten, Angebot fertigstellen"],
    ["0.9.247", "<b>Weitere Zusatzarbeiten rund um den Rohrlaser</b> ([[zusatz_rohrlaser]]) fest in der Auswahl, mit "
     "Beispielpreis und Erkennungswörtern: Innengrat entfernen, Schweißfase anfasen, Schlacke/Spritzer innen "
     "entfernen, <b>Trennmittel innen</b> gegen Spritzer, Richten, <b>Drehen/Fräsen</b>, <b>Brünieren</b>, "
     "Ölen/Konservieren, Grundieren, Endkappen/Stopfen einsetzen, Einpressmuttern setzen, Etikettieren/Beschriften, "
     "Erstmusterprüfbericht und Prüfbericht 3.1. Bestehende Dateien bekommen sie einmalig dazu.",
     "14 weitere Zusatzarbeiten (u. a. Brünieren, Trennmittel innen, Drehen/Fräsen)"],
    ["0.9.246", "Sätze und Schweißbaugruppen übersichtlicher: Schweißbaugruppen sind <b>grün</b> hinterlegt (⚙ Name · "
     "Anzahl in der Spalte Satz), die <b>Kalkulation</b> steht in der Reihenfolge der Positionsliste mit Baugruppe "
     "und Einzelteilen darunter und lässt sich am Zeilenkopf zuklappen, <b>Alle Gruppen zuklappen</b> klappt alle "
     "Sätze und Baugruppen auf eine Zeile (je Angebot gemerkt) ([[saetze_abheben]]). Der Status steht in einer Zeile, "
     "die Unterzeile <i>Programmieren</i> nur noch mit echten Arbeitsschritten. Die Übersicht rechts schneidet "
     "Beträge bei schmalem Fenster nicht mehr ab, die Balken <i>Kosten je Baugruppe</i> überlappen nicht mehr. Im "
     "Editor der Schweißbaugruppe zeigt die Teileliste nur die Teile der Baugruppe (<b>Alle Positionen zeigen</b>, "
     "Suche), die Nahtgruppen haben eine Spalte <b>Rechenweg</b>, und die <b>Vorkalkulation automatisch</b> "
     "(Heftpunkte, Positionieren, Wenden) ist jetzt Vorgabe ([[schweissbaugruppe]]). Nahtlänge genauer: aus STEP "
     "zählen zwei parallele Rohre nur die Längsnähte, ein Rohr, das über ein schmaleres Rohr übersteht, nur die "
     "aufliegenden Wände, eine Lasche ohne Stirnseiten (Spalte <i>Aufteilung der Länge</i>); ohne STEP rechnet "
     "<b>Länge aus</b> die Länge aus einem Teil (rundum, Längsnaht, 2 Seiten); neue Spalte <b>geschweißt %</b> für "
     "Stichnähte. <b>Positionieren</b> nach Stückgewicht (Basisteil = schwerstes Teil, Faktor bis 1, 5, 20 kg, "
     "darüber Kran; Richtwerte laden) ([[naht_laenge]]).",
     "Sätze/Baugruppen grün und zuklappbar, Kalkulation gruppiert, Rechenweg Naht, Nahtlänge genauer, Stichnaht, "
     "Positionieren nach Gewicht"],
    ["0.9.245", "<b>Bleche mit Richtwerten, die man ändern kann</b> ([[blech_richtwerte]]): Der Blech-Editor zeigt "
     "Gewicht, Material, €/kg, Schneidweg, Einstiche, Laserzeit, Stundensatz, Kantungen, Rüsten und Aufschlag als "
     "Tabelle; ein <i>eigener Wert</i> gilt nur für dieses Teil (↺ zurück), der Richtpreis wird immer daraus "
     "berechnet. Bleche aus der STEP rechnen mit Gewicht aus dem Volumen und dem gemessenen Schneidweg. Neue Spalte "
     "<b>EK Blech</b> im Angebot: Angebotspreis des Lieferanten per Klick eintragen, er gilt statt des Richtpreises "
     "(leer = Richtpreis). <b>Tafelbelegung</b> als Bild im Editor und gemeinsam je Werkstoff/Dicke in der neuen "
     "Übersicht <i>Bleche</i> (nur Ansicht). Prüfdialog zeigt Gewicht und Richtpreis je Blech. Innenkonturen rot auf der Tafelbelegung. <b>Gewinde in "
     "Blechen</b>: Kernlöcher aus der STEP werden Gewinde-Vorschläge (Bohrungen prüfen); bestätigt kosten sie € je "
     "Stück aus Einstellungen › Gewinde zusätzlich zum Blech-EK.",
     "Bleche: Richtwerte änderbar, Angebotspreis per Klick, Tafelbelegung als Bild, Gewinde erkannt"],
    ["0.9.244", "<b>Bohrungsart nachträglich ändern</b>: In <i>Bohrungen prüfen</i> hat jede Bohrung die Spalte "
     "<b>Ausführung</b> (Gewinde schneiden, Flowdrill + Gewinde formen, Einnietmutter, Senkung, Bohren, nur lasern) "
     "mit ★-Vorschlag nach Gewindegröße, Wandstärke und Werkstoff und dem Grund (z. B. „Wand 2 mm = 1,6 Gänge M8 – "
     "zu wenig“). Laser-Ø, Schneidweg, Einstiche, Gewinde und Zusatzarbeiten (€/Stück) folgen der Ausführung; die "
     "STEP-Kontur bleibt (Hinweis „weicht von STEP ab“). <b>Alle M8 → …</b> und <b>★ Vorschläge übernehmen</b>, auch "
     "für das ganze Angebot; in allen Editoren als Eigenschaft <i>Ausführung</i>, beim Blech die Arbeit im "
     "Richtpreis ([[bohrung_ausfuehrung]]).",
     "Bohrungsart ändern (Gewinde ↔ Flowdrill ↔ Einnietmutter …) mit ★-Vorschlägen"],
    ["0.9.243", "<b>Auf Ursprung zurücksetzen</b> in allen Editoren: Rohr- und Blech-Editor haben im Menüband neben "
     "Rückgängig den Knopf <b>Zurücksetzen</b> mit <i>Alles wie beim Öffnen</i> und <i>Alles wie aus STEP/DXF "
     "importiert</i> (auch gelöschte Konturen kommen zurück); dasselbe im Editor der Schweißbaugruppe und im Fenster "
     "Satz in 3D. Mit Rückfrage, Strg+Z holt den Stand davor. Den Importstand merkt sich die Position ab jetzt beim "
     "Einlesen ([[teile_editor]], [[baugruppe_ursprung]]).",
     "Zurücksetzen auf Ursprung (wie beim Öffnen / wie aus STEP) in allen Editoren"],
    ["0.9.242", "<b>Zusatzarbeit für ganzen Satz</b> ([[zusatz_satz]]): Rechtsklick auf eine Position eines Satzes → "
     "<i>Zusatzarbeit für ganzen Satz …</i> belegt alle Positionen des Satzes auf einmal, z. B. mit Pulverbeschichten "
     "oder Verzinken. Das Fenster und der Tooltip der Spalte Satz zeigen <b>Fläche (m²) und Gewicht (kg) je Satz</b> "
     "und für alle Sätze, die Tabelle € je Satz. Gerechnet wird weiter je Teil (Summe gleich). <b>Bleche</b> haben "
     "beim Pulverbeschichten jetzt ihre Fläche (beide Seiten ohne Löcher) statt 0 m².",
     "Zusatzarbeit für ganzen Satz mit Fläche und Gewicht je Satz; Bleche mit Fläche beim Pulvern"],
    ["0.9.241", "<b>Angebote vergleichen</b> ([[angebotsvergleich]]): unter <i>Datei → Angebote vergleichen …</i> oder "
                "mit zwei markierten Angeboten in der Angebotsliste (rechte Maustaste → <i>Vergleichen …</i>) zwei "
                "Angebote Position für Position gegenüberstellen. Quellen: Angebote aus der Liste, der eigene "
                "CSV-Export (auch als ZIP) oder eine fremde CSV, z. B. ein Konkurrenz- oder Lieferantenangebot, mit "
                "Spaltenzuordnung, die sich je Quelle als Vorlage speichern lässt. Zuordnung der Positionen über "
                "Artikelnummer, Bezeichnung mit Abmessung und Länge oder Position, der Rest von Hand. Differenz B − A "
                "je Stück, in % und auf die Mengen von A, Hinweise zu Menge, Werkstoff, Länge, Zeit, Herstellkosten "
                "und Marge; markiert ab 5 % oder 50 € (Einstellungen → Automatik und Prüfung). Ausgabe als PDF und "
                "CSV; in den Angeboten wird nichts gespeichert. Abschaltbar unter Einstellungen → Funktionen.",
     "Angebote vergleichen: zwei Angebote aus Liste oder CSV Position für Position, mit PDF und CSV"],
    ["0.9.240", "<b>STEP-Import: Enden mit Hinterschnitt</b> ([[schneidweg_rechner]]): T-Schlitz, Schlüsselloch-Schlitz, "
     "Schwalbenschwanz, Haken und Bohrungen halb über das Ende stehen jetzt genau wie in der STEP im Editor (vorher "
     "0,4 bis 3 mm daneben). Eine Bohrung bis an die Rundung oder in einer dichten Lochreihe (Steg 0,5 mm) wurde als "
     "Fließloch mit Schnittlänge 0 erkannt – jetzt gelaserte Bohrung bzw. Sonderkontur.",
     "STEP: Enden mit Hinterschnitt wie STEP, Bohrung an der Rundung kein Fließloch mehr"],
    ["0.9.239", "STEP-Import aus einer E-Mail mit <b>vielen Teilen</b>: Die PDFs der Anfrage stehen im Prüfdialog ab vier "
     "Dateien in <b>einer Zeile</b> (<i>26 PDF-Dateien: 1 mit Formular, 25 Zeichnungen</i>), <b>Einzeln anzeigen</b> "
     "klappt sie mit Bildlauf auf. Die Teileliste mit ihren Auswahlfeldern bleibt immer mindestens acht Zeilen hoch, "
     "das Fenster passt auf 1366×768 ([[anfragen]]). Steht <i>Satz</i> bzw. <i>geschweißt</i>/<i>SBG</i> im "
     "Datei- oder Baugruppennamen der STEP, sind <b>Als Satz</b> bzw. <b>als Schweißbaugruppe</b> schon gewählt "
     "(abwählbar, [[step_satz]]). <b>Zeichnungen</b>: Gewinde (<i>4x M8</i>), Flowdrill, Einnietmuttern, Senkungen "
     "und Blindniete werden mit Anzahl aus dem Zeichnungstext gelesen; Gewinde/Flowdrill hängen sich gelb an die "
     "passende Bohrung (Bohrungen prüfen), Einnietmuttern und Zusatzarbeiten-Wörter werden Vorschläge, Abweichungen "
     "zum STEP ein Hinweis ([[anfragen]]).",
     "Prüfdialog bei vielen Teilen/PDFs übersichtlich; Satz/Schweißbaugruppe am Namen vorgewählt; Gewinde, "
     "Flowdrill, Nieten aus der Zeichnung"],
    ["0.9.238", "<b>STEP-Import: jede Kontur wie in der STEP</b> ([[schneidweg_rechner]]): Jede Bohrung, jedes "
     "Langloch und Rechteck wird gegen den gemessenen Umriss geprüft und sonst eine Sonderkontur mit dem Umriss der "
     "STEP. Zwei überlappende Bohrungen gleichen Ø (lagen als eine Bohrung bis 3 mm daneben), Bohrungen auf der "
     "Rundung von Quadrat-/Rechteckrohren (0,9 mm) und Sechskante in Flachstahl/Winkel (wurden Langloch) stimmen "
     "jetzt. <b>Bleche</b>: Rechteck mit Eckradius bekommt den Radius, Rechteck mit Fasen wird Polygon, Polygone "
     "auf 0,02 mm, Lage auf 0,01 mm, keine Kontur geht verloren, neue <i>Blech-Gegenprobe</i> mit Hinweis.",
     "STEP: jede Kontur gegen den Umriss geprüft (Doppelbohrung, Bohrung auf Rundung, Bleche mit Radius/Fasen)"],
    ["0.9.237", "<b>Zusatzarbeiten erkennen und wählen</b>: Jede Zusatzarbeit hat Erkennungswörter (z. B. „verzinkt; "
     "fvz; tZn“). Stehen sie in Bezeichnung, Artikelnummer, STEP-Name, Anfrage-Mail oder Zeichnung, erscheint "
     "gelb „＋ Feuerverzinken ?“ in der Positionsliste; der gelbe Knopf übernimmt alle oder einzeln, RAL-Farbe als Text "
     "([[zusatz_erkennen]]). Neues <b>Auswahlfenster</b> mit Suche, Häkchen, Gruppen (häufig, beim Kunden, Kategorie), "
     "€ je Teil und ohne Doppel; <b>Rechtsklick → Zusatzarbeit hinzufügen</b> mit den häufigsten. <b>＋ Neue "
     "Zusatzarbeit …</b> als Kurzformular mit Vorlagen (Eloxieren, Richten, Prüfbericht 3.1 …): Admin legt sie in den "
     "Einstellungen an, sonst gilt sie nur in diesem Angebot und der Admin übernimmt sie später ([[zusatz_neu]]). "
     "<b>Einnietmuttern</b>: Sechskantlöcher und Senkungen im Teil schlagen <i>Einnietmuttern setzen</i> mit der "
     "Anzahl je Teil vor.",
     "Zusatzarbeiten erkennen (gelbe Vorschläge, Einnietmuttern aus Sechskantlöchern/Senkungen), neues "
     "Auswahlfenster, Schnellmenü, Kurzformular mit Vorlagen"],
    ["0.9.236", "Prüfung der Kalkulationsbasis: <b>Grundwerte prüfen …</b> unter Stammdaten → Maschinen und im "
     "Angebots-Check zeigt leere Nebenzeiten, Beispiel-Stundensätze und doppelt gezählte Zuschläge mit der Wirkung in € "
     "([[kalkulationsbasis]]). <b>Schneiddaten</b> zwischen zwei Wandstufen werden interpoliert (2,6 mm nicht mehr mit "
     "den 3-mm-Werten). <b>Wiederholteile</b> mit Programm rechnen nur 1 min Programmierung. Neu einstellbar: weniger "
     "Rüstzeit, wenn sich nur die Wand ändert, <b>Gewinn auf Material</b> getrennt, mittlere Last für den Strom im "
     "ermittelten Stundensatz. Ausschuss rechnet im Hundert. Festgeschriebene Angebote bleiben unverändert.",
     "Grundwerte prüfen, Schneiddaten interpoliert, Wiederholteile, Gewinn auf Material"],
    ["0.9.235", "Weitere Vorschläge für Kalkulation und Ablauf: <b>Maschinen vergleichen</b> im Kopf "
     "([[maschinen_vergleich]]), <b>Sperrtage je Maschine</b> ([[sperrtage]]), <b>Fassungsvergleich</b> "
     "([[fassung_vergleich]]), <b>Teilekatalog je Kunde</b> ([[teilekatalog]]). <b>Preisregeln</b> (alle aus, bis man "
     "sie einschaltet): Runden von Stück- oder Gesamtpreis, Kundenkonditionen Rabatt, frachtfrei ab Warenwert und "
     "Mindestauftragswert, Verpackung aus den Stammdaten, Finanzierung über das Zahlungsziel ([[preisregeln]]), "
     "Neuteil-Zuschlag und mannlose Laufzeit je Maschine ([[neuteil_mannlos]]). <b>Preisuntergrenze und Zielpreis "
     "rückwärts</b> ([[zielpreis]]), Hinweise zu Auslastung und Marktpreis aus Absagen ([[kalk_hinweise]]), "
     "<b>Vier-Augen-Freigabe</b> ([[freigabe]]), <b>Rückfrage an Kunden</b> ([[rueckfrage]]), <b>Positionsvorlagen</b> "
     "([[positionsvorlagen]]), <b>Offene Angebote prüfen</b> und <b>Monatsbericht</b> ([[offene_pruefen]]), "
     "<b>Lieferantenangebote</b> mit Bewertung ([[lieferantenangebote]]), <b>Lieferschein</b> mit Teillieferung und "
     "Werkszeugnissen ([[lieferschein]]), <b>Laserzeit per Scan</b> für die Nachkalkulation ([[laserzeit_scan]]).",
     "Maschinenvergleich, Preisregeln, Zielpreis, Freigabe, Rückfrage, Vorlagen, Lieferschein, Lieferantenangebote, "
     "Scan-Zeit"],
    ["0.9.234", "Neun Verbesserungen für Kalkulation und System: <b>Gleitklausel Material</b> bei Abruf-Angeboten "
     "([[gleitklausel]]): festgeschriebene gegen aktuelle Materialpreise, ab ±5 % fällig, nur Material gleitet, "
     "Übernehmen mit Vermerk im Versandverlauf. <b>Eilzuschlag</b> ([[eilzuschlag]]): Feld im Kopf und Vorschlag aus "
     "<i>Termin prüfen …</i> nach Arbeitstagen zu früh (15 %/30 %). <b>CO₂-Bilanz</b> intern im Preisaufbau und "
     "Kalkulations-PDF ([[co2_bilanz]], Funktion, Vorgabe aus). <b>Wiederholteile</b> zeigen, wie der letzte "
     "Auftrag lief, der Angebots-Check weist auf große Abweichungen hin ([[wiederholteil_nachkalk]]). "
     "<b>Ertrag je Laserstunde je Kunde</b> in der Angebots-Auswertung ([[ertrag_laserstunde]]). <b>Prüfplan / "
     "Messprotokoll</b> als PDF mit ISO 2768 und Zusatzarbeit Erstmusterprüfung ([[pruefplan]]). <b>Support-Paket</b> "
     "als ZIP ([[support_paket]]). <b>Datenschutz</b>: Datenauskunft als PDF, Kunden anonymisieren (nur Admin), "
     "Frist für abgelehnte Angebote (Vorgabe aus) ([[datenschutz]]). <b>Übergabe an CAM</b>: Ordner mit STEP je "
     "Teil, Stückliste und Schnittplan ([[cam_paket]]).",
     "Gleitklausel, Eilzuschlag, CO₂, Wiederholteil-Rückblick, Ertrag/Laserstunde, Prüfplan, Support-Paket, "
     "Datenschutz, CAM-Ordner"],
    ["0.9.233", "<b>STEP-Import: Rechteck mit Eckradius bleibt Rechteck</b> ([[schneidweg_rechner]]): Ein "
                "Rechteckausschnitt mit gerundeten Ecken (z. B. R3) kam bisher als <i>Sonderkontur</i> und war im "
                "Editor nicht mit Maßen änderbar. Jetzt wird er eine Zeile <i>Rechteck</i> mit dem Eckradius aus der "
                "gemessenen Schnittlänge, wenn der Umriss damit auf 0,05 mm wie in der STEP liegt; über eine Rohrecke "
                "bleibt er Sonderkontur. Dritte Probe mit 18 weiteren Teilen (Sechskant-, Schlüssel- und Kreuzloch, "
                "Lochkranz, Langloch über Ecke und nah am Ende, gedrehte und Freiform-STEP): alle wie in der STEP.",
     "STEP: Rechteck mit Eckradius wird Rechteck-Zeile mit Radius statt Sonderkontur"],
    ["0.9.232", "Zwei Fehler im Windows-Programm 0.9.231 behoben: <b>Etiketten mit QR-Code</b> ([[etiketten]]) brachen "
     "mit „No module named reportlab.graphics.barcode.code128“ ab, weil ein Teil der Barcode-Bausteine im "
     "Programmpaket fehlte. Der <b>STEP-Import</b> ([[step]]) brach bei Rohren mit großem rundem Loch (Durchbruch für "
     "einen Stutzen) mit „No module named numpy“ ab; die Prüfung des Durchbruchs gegen die STEP rechnet jetzt ohne "
     "numpy, genauso genau. Der Selbsttest jedes Windows-Pakets erzeugt nun ein Etiketten-PDF und importiert ein "
     "Rohr mit Stutzen-Durchbruch, ein Test prüft, dass jedes benutzte Modul im Paket ist.",
     "Etiketten mit QR-Code und STEP-Import mit Stutzen-Durchbruch: Abbrüche im Windows-Programm behoben."],
    ["0.9.231", "<b>Fehler-Durchgang</b>: Die <b>Optimierung</b> überspringt volle Stangen und schon geprüfte gleiche "
     "Teile ([[optimieren]]); der Schnittplan bleibt Stange für Stange gleich, aber große Stückzahlen gehen viel "
     "schneller (20.000 gleiche Teile vorher über 10 Minuten, jetzt unter 1 Sekunde; 6.000 gemischte Teile mit "
     "Gehrungen vorher rund 80 s, jetzt etwa 7 s). Rechtsklick unter den Positionen ohne Markierung und dann "
     "<i>Baugruppe bearbeiten …</i> zeigt einen Hinweis statt einer Fehlermeldung. <i>inf</i>, <i>nan</i> oder "
     "<i>1e999</i> in Zahlen- und Rechenfeldern werden abgelehnt ([[eingaben]]), statt einen Preis „nan“ zu "
     "ergeben.",
     "Fehler-Durchgang: Optimierung großer Stückzahlen viel schneller, zwei Abstürze behoben"],
    ["0.9.230", "<b>Gemeinsamer Ordner</b> ([[ordner_einrichten]]): rote Leiste oben, solange der Ordner nicht "
                "erreichbar ist (seit wann, Änderungen bleiben hier); ist er wieder da, gleicht das Programm gleich ab "
                "und meldet die endgültigen Nummern. <b>Datei → Arbeitsplatz einrichten (Assistent) …</b>: Ordner, "
                "Kürzel, erster Abgleich in drei Schritten. <b>Datei → Gemeinsamen Ordner umziehen …</b> (Admin): "
                "alles kopieren und prüfen, die Kollegen stellen mit einem Klick um. Schneller schreiben: unveränderte "
                "Daten bleiben liegen, nur geänderte Stammdaten-Zeilen werden neu geschrieben.",
     "Leiste bei Ordner-Ausfall; Assistent für neue Arbeitsplätze; Ordner umziehen (Admin); schneller schreiben"],
    ["0.9.229", "<b>Gleichzeitig ändern</b> ([[zeile_sperre]]): Ändert ein Kollege gerade dieselbe Stammdaten-Zeile "
                "(Kunde, Material, Preis …), fragt das Programm „Trotzdem ändern?“ (weiche Sperre, 2 Minuten nach "
                "seiner Änderung). <b>Windows-Meldung</b> unten rechts bei Übergaben, Anfragen, Notizen und fälligen "
                "Wiedervorlagen, wenn das Programm nicht vorn ist; Klick öffnet das Angebot. Abschaltbar unter "
                "Einstellungen → Mein Arbeitsplatz → Gemeinsamer Ordner.",
     "Weiche Sperre für gleichzeitig geänderte Stammdaten-Zeilen; Windows-Meldung bei Nachrichten der Kollegen"],
    ["0.9.228", "<b>Verlauf: wer hat was geändert</b> ([[aenderungsverlauf]]): <i>Vorgang → Verlauf …</i> in der "
                "Angebotsliste zeigt je Angebot, wer wann welches Feld von welchem auf welchen Wert geändert hat (Kopf, "
                "Positionen, Staffeln), über alle Arbeitsplätze im gemeinsamen Ordner; <i>Kollegen im gemeinsamen "
                "Ordner → Verlauf Stammdaten …</i> dasselbe für Kunden, Material, Preise und gemeinsame "
                "Einstellungen. <b>Alten Wert zurückholen</b> für eigene Angebote und eigene Änderungen, der Admin "
                "auch für die Stammdaten der Kollegen. Der Verlauf reicht 12 Monate zurück.",
     "Verlauf je Angebot und für Stammdaten (wer, wann, vorher, nachher); alten Wert zurückholen"],
    ["0.9.227", "<b>Angebot per E-Mail</b> ([[angebot_mail]]): <i>Ausgaben → Angebot per E-Mail …</i> erstellt das PDF "
                "und öffnet in Outlook die E-Mail an den Kunden mit Anhang, als Antwort auf die Anfrage-Mail, wenn sie "
                "im Angebotsordner liegt; Vorlagen unter Einstellungen → Angebot per E-Mail, Vermerk im Versandverlauf. "
                "<b>Termin prüfen …</b> im Angebotskopf ([[termin_auslastung]]): frühester Liefertermin nach freier "
                "Maschinenkapazität und Material-Lieferzeit, auch beim Beauftragen. <b>Schnellpreis</b> "
                "([[schnellpreis]]): Datei → Schnellpreis … (Strg+Alt+P) gibt einen Richtpreis mit kleiner Staffel "
                "für Telefonanfragen, „Als Angebot übernehmen“. <b>Laufzeit je Teil</b> in der Nachkalkulation "
                "([[laufzeit_teil]]): ergibt die Ist-Laserzeit und schlägt Vorschübe je Schneiddaten-Zeile "
                "(Werkstoff, Wandstärke) vor.",
     "Angebot per E-Mail (Outlook, Antwort auf die Anfrage); Termin nach Auslastung; Schnellpreis; Laufzeit je Teil"],
    ["0.9.226", "<b>PDF-Anfrageformular besser ausgewertet</b> ([[anfragen]]): Positionstabellen liest das Programm "
                "über die Lage der Wörter (PDF mit Text und Scan) – Menge aus der Mengenspalte, Zellen über zwei "
                "Zeilen, <i>1.000 Stk</i> = 1000, Positionsnummern und Längen nie als Menge; nennt das Formular nur "
                "<i>MG-01</i>, passt die Menge zur STEP <i>MG-01 Stiel</i> (gelb). Die <b>Anfrage-Nr.</b> steht auch "
                "in Kopftabellen oder heißt <i>Beleg-Nr.</i>, <i>Vorgang</i>, <i>Unser Zeichen</i>; ein Datum zählt "
                "nie. Neu: <b>Werkstoff je Position</b> aus dem Formular (nur eindeutig, gelb mit Quelle).",
     "PDF-Formular: Tabellen über die Lage, Anfrage-Nr. aus Kopftabellen, Werkstoff je Position"],
    ["0.9.225", "<b>U-Profile als Standard</b> ([[profile]]): Die U-Profile nach DIN 1026-1 von UPN 30x15 bis UPN 200 "
                "stehen in den Stammdaten Profile (Steg, Flansch, Normfläche und Gewicht je Meter, ohne Preis); "
                "<i>UNP 100</i> oder <i>U 100</i> beim Tippen findet UPN 100, auch in der Schnellzeile. "
                "<b>Wandstärke ändern …</b> ([[wand_aendern]]): Rechtsklick auf Positionen oder im Fenster Material "
                "…, andere Wandstärke bei gleichem Außenmaß, fehlendes Profil wird angelegt. <b>Rohrart je "
                "Abmessung</b> ([[rohrart_angebot]]): im Fenster Material … geschweißt, nahtlos, stranggepresst oder "
                "neu <i>Naht innen geschabt</i>, steht in Materialanfrage, Angebot und Werkstattpapieren.",
     "U-Profile UPN 30x15 bis 200 als Standard, Wandstärke ändern, Rohrart je Abmessung (auch Naht innen geschabt)"],
    ["0.9.224", "<b>Outlook-Import: intern weitergeleitete Mails</b> ([[anfrage_mail]]): Leitet ein Kollege eine "
                "Kundenanfrage weiter (WG:/FW:, im Text, als .msg/.eml-Anhang oder mehrfach), kommen Kunde, "
                "Ansprechpartner, Signatur (neuer Kunde mit Adresse), Anfragedatum, Staffelmengen, Zusatzarbeiten, "
                "Termin und Bemerkung aus der Mail des Kunden statt vom Kollegen; ein späterer Nachtrag direkt vom "
                "Kunden kommt dazu. Der Prüfdialog zeigt <i>Intern weitergeleitet von …</i> und die Notiz des "
                "Kollegen; ein Termin oder Werkstoff in der Notiz gilt (Hinweis auf den Kundenwert). Neu unter "
                "Einstellungen → Firma: <i>Weitere eigene E-Mail-Domains</i>; die Adressen der Arbeitsplätze im "
                "gemeinsamen Ordner zählen automatisch als intern, die eigene Firma wird nie als Kunde angelegt.",
     "Outlook-Import: intern weitergeleitete Mails erkannt, Kunde und Anfragetext vom ursprünglichen Absender"],
    ["0.9.223", "<b>STEP-Import: weitere kritische Konturen wie in der STEP</b> ([[schneidweg_rechner]]): Ein Langloch "
                "quer um ein Rundrohr stand als Rechteck im Editor (1,9 mm daneben), eine außermittige Bohrung im "
                "Rundrohr und eine Schrägbohrung in einer ebenen Wand als Kreis statt Ellipse (0,6–0,9 mm). Weicht der "
                "gemessene Umriss mehr als 0,05 mm vom Langloch, Rechteck oder Kreis ab, kommt die Zeile jetzt als "
                "<i>Sonderkontur</i> mit dem Umriss der STEP; mit 3D-Schnittbearbeitung bleibt die schräge Bohrung "
                "eine geneigte Bohrung. Ein scharfkantiges U, das so in den Stammdaten steht, bleibt auch mit "
                "Ausklinkung am Flanschende U-Profil statt Kantteil. Die <i>Gegenprobe beim Übernehmen</i> prüft "
                "jetzt auch offene Profile (L, U, C, Flachstahl). Ältere Importe: STEP neu einlesen.",
     "STEP-Import: Langloch quer im Rundrohr, außermittige und schräge Bohrungen wie STEP; Gegenprobe auch für L/U/C"],
    ["0.9.222", "<b>Mitarbeiter ausgeschieden</b> ([[mitarbeiter_ausgeschieden]]): In <i>Datei → Kollegen im "
                "gemeinsamen Ordner …</i> trägt der Admin einen Kollegen mit <b>Ausgeschieden …</b> aus: seine Angebote "
                "übernimmt der Admin oder ein Kollege (für alle oder je Angebot), sein Ordner kommt ins Archiv des "
                "gemeinsamen Ordners und wird nicht mehr gelesen; die Nummern bleiben. <b>Lizenzen der Plätze</b>: "
                "<i>Gemeinsamen Ordner prüfen</i> meldet aktive Plätze ohne gültige Lizenz und dieselbe Lizenz an "
                "mehreren Kürzeln; der Admin sieht das in der Statusleiste.",
     "Ausgeschiedene Mitarbeiter austragen (Angebote verteilen, Ordner ins Archiv); Lizenzhinweise der Plätze"],
    ["0.9.221", "<b>Kollegen im gemeinsamen Ordner</b> ([[kollegen_uebersicht]]): <i>Datei → Kollegen im gemeinsamen "
                "Ordner …</i> zeigt je Mitarbeiter, ob er gerade da ist, Rechner, Version, letzten Abgleich, Zahl der "
                "Angebote, gerade geöffnete Angebote, offene Übergaben/Notizen an ihn und seine PC-Uhr; "
                "<b>Notiz an …</b> direkt aus der Liste. <b>Schneller abgleichen</b> ([[mehrere_arbeitsplaetze]]): "
                "Ein Lebenszeichen alle 30 Sekunden zeigt den Kollegen fast sofort, wer woran arbeitet; Änderungen "
                "gehen gleich nach der Eingabe in den Ordner, der automatische Abgleich läuft jede Minute "
                "(vorher alle 2 Minuten).",
     "Übersicht der Kollegen; Lebenszeichen alle 30 s; Änderungen gleich in den Ordner; Abgleich jede Minute"],
    ["0.9.220", "<b>Gemeinsamen Ordner prüfen</b> ([[ordner_pruefen]]): <i>Datei → Gemeinsamen Ordner prüfen …</i> "
                "zeigt, ob der gemeinsame Ordner richtig arbeitet: erreichbar, Geschwindigkeit, Uhr, eigenes Kürzel, "
                "Programmversion und letzter Abgleich der Kollegen, Konfliktkopien von OneDrive/SharePoint, doppelt "
                "reservierte Nummern, abgebrochene Schreibvorgänge und vorläufige Nummern, jeweils mit <i>Was tun</i>. "
                "Eine falsch gehende PC-Uhr wird bei jedem Abgleich gegen die Uhr des Ordners gemessen und "
                "herausgerechnet, damit sie keinen Konflikt mehr falsch entscheidet. Eigene Konfliktkopien räumt der "
                "Abgleich in den lokalen Ordner Konfliktkopien. Die Statusleiste warnt bei falscher Uhr und doppelten "
                "Nummern.",
     "Gemeinsamen Ordner prüfen; falsche PC-Uhr wird herausgerechnet; Konfliktkopien aufgeräumt"],
    ["0.9.219", "<b>Anzahl Sätze und Stück je Satz ändern</b> ([[satz_bearbeiten]]): Doppelklick auf die Spalte Satz "
                "oder <i>Rechtsklick → Satz bearbeiten (Anzahl Sätze) …</i> öffnet ein Fenster mit der Anzahl Sätze "
                "(− / +) und Stück je Satz je Position; die Stückzahlen rechnen sich live mit, OK ist ein Schritt für "
                "Rückgängig. In der Liste ziehen die Spalten mit: Stück je Satz geändert → Stückzahl folgt, Stückzahl "
                "einer Satzposition geändert → Stück je Satz folgt (geht es nicht ganz auf, bleibt alles wie getippt "
                "mit Hinweis). Dasselbe Feld <i>Anzahl Sätze</i> im Fenster Satz in 3D; der Blech-Editor folgt der "
                "gleichen Regel.",
     "Anzahl Sätze mit − / + ändern, Stück je Satz und Stückzahl ziehen mit"],
    ["0.9.218", "<b>Durchbruch für einen Stutzen aus der STEP</b> ([[schneidweg_rechner]]): Ein rundes Loch in der "
                "Rohrwand für ein abgehendes Rohr (rechtwinklig, schräg, mit Versatz, in beliebiger Lage am Umfang) "
                "kommt jetzt als <i>Durchbruch</i> mit Gegenrohr Ø, Winkel, Versatz, Seite und Lage in den Editor "
                "statt als Bohrung – genau wie in der STEP (vorher im Rundrohr bis 5 mm daneben). Im 3D-Editor "
                "lassen sich Ø, Winkel und Versatz direkt rechts ändern. Kleine Löcher bleiben Bohrungen.",
     "Stutzen-Loch aus der STEP als Durchbruch, genau wie in der STEP und im 3D-Editor änderbar"],
    ["0.9.217", "<b>Rohranschluss aus der STEP erkennen und im 3D bearbeiten</b> ([[schneidweg_rechner]]): Ein Ende, "
                "das mit Sattel- bzw. Fischmaulschnitt auf einem runden Gegenrohr sitzt (rechtwinklig, schräg, mit "
                "Versatz, in beliebiger Lage am Umfang), kommt jetzt als <i>Gegenrohr</i> mit Ø, Winkel, Versatz und "
                "Drehung in den Editor statt als nicht änderbares komplexes Ende – Rund-, Quadrat- und Rechteckrohr, "
                "Ende A und B, genau wie in der STEP. Im 3D-Editor stehen beim gewählten Ende die Felder Ø, Winkel, "
                "Versatz und Drehung direkt rechts; die Schnittkurve wird sofort neu gerechnet. Der Gegenrohr-Dialog "
                "hat beim Rundrohr das neue Feld <i>Drehung um die Rohrachse</i>.",
     "Rohranschluss (Sattel/Fischmaul) aus der STEP als Gegenrohr, im 3D-Editor änderbar"],
    ["0.9.216", "<b>Lizenzpflicht ab 20.11.2026</b> ([[lesemodus]]): Bis zum 19.11. zeigt das Programm ohne gültige "
                "Lizenz nur den Hinweis mit dem Termin, ab dem 20.11.2026 schaltet es in den Lesemodus (ansehen, "
                "exportieren, sichern und Updates gehen weiter, Daten bleiben erhalten). <b>Schutz der "
                "Programmdateien</b>: Beim Start prüft das Programm seine eigenen Dateien gegen die signierte "
                "Dateiliste des Updates; sind sie verändert, gilt dasselbe wie ohne Lizenz. Bricht die Lizenzprüfung "
                "unerwartet ab, startet das Programm ab dem 20.11. im Lesemodus statt ohne Prüfung. Das "
                "Lizenz-Werkzeug liegt nicht mehr im öffentlichen Download.",
     "Lizenzpflicht ab 20.11.2026; Programm prüft beim Start seine eigenen Dateien"],
    ["0.9.215", "<b>Position als neue Position kopieren</b> ([[position_kopieren]]): <i>Rechtsklick → Position "
                "duplizieren</i> (Strg+Umschalt+D) legt eine Kopie mit allen Eingaben, Technik, Zusatzarbeiten, "
                "Gravur, Zukauf, 3D und Staffeln an, mit eindeutiger Artikelnummer direkt hinter dem Original; "
                "Schweißbaugruppe mit allen Teilen, erste Satzzeile mit dem ganzen Satz. <i>Positionen aus anderem "
                "Angebot übernehmen …</i> (auch unter Neue Position) holt Positionen aus jedem Angebot, auch von "
                "Kollegen oder festgeschrieben, ans Ende; das andere Angebot bleibt unverändert.",
     "Position duplizieren (Strg+Umschalt+D) und Positionen aus anderem Angebot übernehmen"],
    ["0.9.214", "<b>Kalkulations-PDF überarbeitet</b> ([[ausgabe]]): Seite 1 bleibt nicht mehr leer, Kostenarten und "
                "neue <b>Kennzahlen</b> (Stundensatz von Hand/ermittelt, Zeitbasis, Gewinn, Preis je kg, Ertrag je "
                "Maschinenstunde, Fracht, Abruf) stehen nebeneinander; der doppelte Kasten „Rüsten und Mengen“ ist "
                "weg. Neu: Datum, Kunden-Nr. und Stundensatz im Kopf, Kachel Selbstkosten, Gewinn in %, greifende "
                "Gewinnstufe, Schneidgas in m³, Fracht mit Art und Umlage, Warnungen der Preis-Gegenprobe, Rechenweg "
                "des ermittelten Stundensatzes, Abschnitte Abruf-/Rahmenangebot, Zukaufteile und Staffelpreise, "
                "Schneiddaten je Teil. Die Positionstabelle steht in zwei Teilen (Kosten je Teil, Preisaufbau) mit "
                "Bezeichnung und den fehlenden Spalten (Schweißen, Fremdleistung, Gas, Ausschuss, Schrott, Lagerzins), "
                "Zahlen brechen nicht mehr um. Die Rechnung selbst ist unverändert.",
     "Kalkulations-PDF: Kennzahlen, Stundensatz, Gewinnstufe, Fracht, Abruf, Staffeln, Zukaufteile; Seite 1 nicht mehr leer"],
    ["0.9.213", "<b>Vorbereitet für die Server-Synchronisation</b> ([[server_vorbereitung]]): Angebote und Positionen "
                "haben eine feste Kennung (bleibt bei der endgültigen Nummer und beim Kollegen gleich), ein "
                "Änderungsprotokoll merkt sich jede Änderung an Stammdaten, gemeinsamen Einstellungen und Angeboten, "
                "und Ordner, Nummern und gemeinsame Dateien laufen über eine gemeinsame Schnittstelle. Für die Arbeit "
                "ändert sich nichts: gemeinsamer Ordner, Dateien und Abgleich bleiben gleich.",
     "Vorbereitung Server-Synchronisation: feste Kennungen, Änderungsprotokoll, eine Stelle für den Austausch"],
    ["0.9.212", "<b>Hauptadmin und weitere Admins</b> ([[admin_rechte]]): Neue Seite <i>Allgemein → Arbeitsplätze und "
                "Rechte</i> mit allen Arbeitsplätzen (Name und Kürzel vom ersten Start, Rechner, Lizenz mit Ampel, "
                "Version, zuletzt da). Der Hauptadmin (Passwort der Admin-Lizenz) gibt dort Mitarbeitern das Recht "
                "<b>Admin</b> mit Startpasswort, sperrt Admins oder vergibt ein neues Startpasswort. Ein Admin schaltet "
                "sich mit seinem eigenen Passwort frei, an jedem Arbeitsplatz mit gültiger Lizenz, und ändert alle "
                "Seiten mit 🔒, aber nicht Admin-Schutz und Rechte. Der Verlauf zeigt, welcher Admin was geändert hat.",
     "Hauptadmin und weitere Admins mit eigenem Passwort, Seite Arbeitsplätze und Rechte"],
    ["0.9.211", "<b>Admin-Schutz für Einstellungen</b> ([[passwort]]): Der Reiter Einstellungen öffnet für alle; "
                "Seiten mit 🔒 (Vorschlag: Preise, Gewinn, Kosten, Maschinen, Schneiddaten, Firma, Funktionen, "
                "Frachtkosten …) ändert nur der Admin, andere sehen die Werte grau. <b>Als Admin freischalten …</b> "
                "mit dem Admin-Passwort geht an jedem Arbeitsplatz und gilt bis <b>Admin sperren</b>, Programmende "
                "oder 15 Minuten ohne Eingabe. Welche Seiten geschützt sind, legt der Admin unter Allgemein → "
                "Admin-Schutz mit Häkchen fest. Was der Admin dort einstellt, gilt als Admin-Vorgaben an jedem "
                "Arbeitsplatz (gemeinsamer Ordner, für einen späteren Server vorbereitet); ein Nicht-Admin kann es "
                "nicht überschreiben. Das bisherige Passwort für den ganzen Reiter entfällt. <b>Frachtdaten</b> "
                "(Zonen, Tarife, Paletten, Zuschläge, Dienstleister, Historie) stehen jetzt unter Einstellungen → "
                "Fracht ([[frachtkosten]]); im Reiter Frachtkosten bleibt der Rechner mit <b>Frachtdaten pflegen "
                "…</b>. Bitte alle Arbeitsplätze gleichzeitig updaten.",
     "Admin-Schutz für Einstellungen (gilt an allen Arbeitsplätzen); Frachtdaten unter Einstellungen → Fracht"],
    ["0.9.210", "<b>Aufgeschnittene Rohre aus der STEP</b> ([[offene_rohre]]): Rechteckrohr mit großem Ausschnitt über "
                "Oberseite und Seitenwände (Trapez), der die Seitenwände nur teilweise wegnimmt, galt als V-Ausschnitt "
                "eines Knickrahmens und stand im Editor bis 16 mm neben der STEP – jetzt Sonderkontur genau wie "
                "gezeichnet; ein V ist es nur noch, wenn die Seitenwände bis an die Stegwand durchgeschnitten sind "
                "([[knickrahmen]]). Quadrat-/Rechteckrohr, oben zwischen den Enden offen und mit Fenster in einer "
                "Seitenwand: die Rohrachse lag im Schwerpunkt des offenen Stücks (13 mm daneben), jetzt aus den "
                "geschlossenen Querschnitten. Ebenso behoben: Quadratrohr mit Gehrung an beiden Enden und Fenster "
                "(3 mm daneben), Schlitz über den Eckradius ins Ende (0,5 mm), Winkel/U mit Ausklinkung am Ende (freies "
                "Schenkelende schräg). Teile-Editor: ein komplexes Ende aus der STEP heißt nicht mehr „gerade“. "
                "<b>Gegenprobe beim Übernehmen</b> ([[schneidweg_rechner]]): das 3D-Modell des Editors wird mit den "
                "Linien der STEP verglichen, ab 0,1 mm Abweichung bekommt die Position einen Hinweis.",
     "Aufgeschnittene Rohre im Editor genau wie in der STEP, Gegenprobe Editor gegen STEP beim Übernehmen"],
    ["0.9.209", "<b>STEP-Export gegen die Mutter-STEP geprüft</b> ([[step_mutter]]): Nach jedem STEP speichern "
                "(Rohr-Editor, Blech-Editor, Schweißbaugruppe, Satz in 3D) vergleicht das Programm jeden Körper mit "
                "dem Körper der eingelesenen Kundendatei – genau gleich, örtlich geändert (Schlitze/Nasen der "
                "Steckverbindung, 2D-Gehrung, im Editor geändert) oder <b>ACHTUNG: liegt nicht dort</b> (Warnung). "
                "Behoben: gleiche Rohre, die gedreht oder gewendet eingebaut sind (gegenüberliegende Seiten eines "
                "Rahmens mit Gehrungen), lagen in 3D und im STEP-Export gespiegelt; ältere Angebote: STEP neu einlesen.",
     "STEP-Export wird mit der Mutter-STEP verglichen (Warnung bei falscher Lage); gespiegelte Gehrungsrahmen behoben"],
    ["0.9.208", "<b>Abruf-/Rahmenangebot</b> ([[abruf_angebot]]): Haken im Angebotskopf mit Jahresmenge und "
                "Abrufmenge von–bis, Laufzeit und Material. Die Stückzahlen sind der kleinste Abruf; Programmierung "
                "und Musterteile werden auf die kleinste Jahresmenge verteilt, Rüsten und Fracht zählen je Abruf. "
                "Material wahlweise je Abruf mit Materialklausel oder für die Jahresmenge bevorratet mit Lagerzins. "
                "Knopf „Abrufstufen anlegen“ im Reiter Staffeln (Mitte und größter Abruf), im Angebots-PDF ein Block "
                "„Rahmenbedingungen“ aus Textbausteinen der Einstellungen. Schema 70.",
     "Abruf-/Rahmenangebot: Jahresmenge in Abrufen, Einmalkosten auf die Jahresmenge, Rahmenbedingungen im PDF"],
    ["0.9.207", "<b>Bedienungsanleitung, Kurzanleitung und Präsentation auf dem Stand 0.9.206</b>: neue "
                "Bildschirmfotos für Preis-Simulator ([[preis_simulator]]), Maschinenauslastung je Woche "
                "([[auslastung]]), Reklamationen ([[reklamation]]), Stundensatz ermitteln ([[stundensatz_ermitteln]]) "
                "und Etiketten mit QR-Code ([[etiketten]]); der Preis-Simulator steht jetzt bei „Angebote verwalten“ "
                "neben der Angebots-Auswertung. Am Programm ändert sich nichts.",
     "Anleitung und Kurzanleitung mit neuen Bildern, Preis-Simulator bei „Angebote verwalten“"],
    ["0.9.206", "<b>Gewinn gestaffelt nach Auftragswert</b> ([[gewinn_gestaffelt]]): in den Einstellungen "
                "(Seite <i>Gewinn gestaffelt</i>) bis zu 4 Grenzen und 5 Sätze, z. B. 30 % bis 500 €, 20 % bis 2.000 €, 12 % bis "
                "10.000 €, darüber 8 %. Auftragswert = Selbstkosten des Angebots ohne Zukaufteile und Fracht; ein "
                "Satz für alle Positionen; an den Grenzen kein Preissprung nach unten. Ab Werk aus; ein eigener "
                "Gewinn im Angebot oder in der Staffel-Stufe gilt statt der Stufen, festgeschriebene Angebote bleiben "
                "gleich.",
     "Gewinn gestaffelt nach Auftragswert (bis 5 Stufen, Vorgabe aus)"],
    ["0.9.205", "<b>Paket und lange Teile auf der Europalette</b>: Der Packvorschlag im Frachtrechner rechnet jetzt "
                "auch <b>Paketversand</b> mit drei Kartons (S 400 × 300 × 200 mm bis 10 kg 10,49 €, M 600 × 400 × "
                "400 mm bis 20 kg 18,99 €, L 1.200 × 200 × 200 mm bis 31,5 kg 23,99 €, Richtwert DHL) und nimmt das "
                "Paket, wenn es günstiger als jede Palette ist; die Packliste zeigt jeden Karton mit Draufsicht und "
                "Seitenansicht. Kartons und Preise sind unter <i>Paletten und Ladehilfsmittel</i> bzw. Tarif "
                "RW-PAKET änderbar. Europalette und Einwegpalette nehmen Teile bis 3.000 mm, Überstand nur längs "
                "über die 1.200er Seite, quer nie ([[pack_rechner]]).",
     "Frachtrechner: Paketversand mit Kartons S/M/L, Europalette bis 3.000 mm mit Überstand längs."],
    ["0.9.204", "<b>Pack-Logik im Frachtrechner</b>: Der Knopf <i>Aus Angebot laden …</i> (Frachtkosten › Fracht "
                "kalkulieren) übernimmt die Ware eines Angebots und packt sie nach Maßen und Stückzahl wie der "
                "Palettenschein, statt nur Gewicht ÷ 800 kg. Der Packvorschlag probiert jetzt alle Ladungsträger "
                "(Europalette, Gitterbox, Industrie-, Sonderpalette …, lange Teile auf Langgut) und nimmt den "
                "günstigsten Frachtpreis, z. B. eine Sonderpalette 2,40 m statt Europalette + Langgut. Die neue "
                "<b>Packliste</b> zeigt den Vergleich und je Palette Draufsicht, Seitenansicht mit Höhe und den "
                "Aufbau; auch im Fenster <i>Fracht berechnen …</i> eines Angebots ([[pack_rechner]]).",
     "Frachtrechner: Ware aus Angebot laden, günstigste Ladungsträger, Packliste mit Skizze."],
    ["0.9.203", "<b>Fracht im Nahbereich günstiger</b>: Die Richtwerte für den Palettenversand haben zwei neue Ringe, "
                "<i>bis 50 km</i> (1 Palette 65 €) und <i>50–100 km</i> (80 €); bisher kostete alles bis 200 km "
                "100 €. Ab Delbrück z. B. Paderborn, Bielefeld und Herford 65 €, Münster und Osnabrück 80 €. Neu ist "
                "die Versandart <b>Eigene Anlieferung</b> (eigener Lkw, bis 200 km): 20 € je Sendung plus 1,00 € je "
                "gefahrenem km, die Entfernung im Frachtrechner eintragen (20 km = 60 €). Beim ersten Start werden "
                "geladene Richtwerte einmalig neu geladen (vorher Datensicherung <i>vor_Fracht_Nahbereich</i>), "
                "eigene Tarife und Einträge bleiben. Angebote mit gespeicherter Frachtberechnung behalten ihre "
                "Tarifkopie, bis die Ziel-PLZ neu eingegeben wird; festgeschriebene Angebote bleiben unverändert "
                "([[fracht_richtwerte]]).",
     "Fracht: Nahbereich bis 50 km 65 €, bis 100 km 80 €; Versandart Eigene Anlieferung (€/km)."],
    ["0.9.202", "<b>Einstellungen aufgeräumt</b>: Statt einer langen Seite <i>Vorgaben</i> mit allen Einstellungen "
                "hat jedes Thema eine eigene Seite neben den passenden Stammdaten, z. B. <i>Zuschläge und Preise</i>, "
                "<i>Neue Angebote</i>, <i>Blech-Richtpreis</i>, <i>STEP-Import</i>, <i>Versand und Paletten</i>. "
                "Alles, was nur für diesen Arbeitsplatz gilt (Name, Farbschema, Ordner, Signatur), steht auf <i>Mein "
                "Arbeitsplatz</i>. Titel ohne doppelte Vorsilbe (voller Titel im Tooltip), selten geänderte Toleranzen "
                "und Faktoren eingeklappt; die Suche findet weiter alles und öffnet die richtige Seite "
                "([[vorgaben]]). <b>Funktionen ein- und ausschalten</b>: Auf der neuen Seite <i>Funktionen</i> lassen "
                "sich 15 Bereiche abschalten, z. B. Bleche, Zukaufteile, Frachtkosten, Schweißbaugruppen, "
                "Nachkalkulation, Reklamationen oder Musterteile. Ausschalten blendet nur aus, Daten und Rechnung "
                "bleiben; nach dem Update ist alles eingeschaltet ([[funktionen]]). Werte mit „0 = aus“ wie Nachfassen, "
                "automatisch optimieren, Mindestmarge oder Standard-Staffeln haben einen Schalter davor, der den "
                "letzten Wert behält.",
     "Einstellungen nach Themen auf eigenen Seiten; Funktionen ein- und ausschalten."],
    ["0.9.201", "<b>Schneiddaten mit Schneidtabellen abgeglichen</b>: Die Richtwerte für T11 und LT7 sind mit "
                "veröffentlichten Schneidtabellen verglichen; die Bemerkung jeder Zeile nennt jetzt die Herkunft "
                "(Herstellerwert oder Schätzung). Stahl mit N₂ 3–4 mm langsamer (LT7 3.500 / 2.500, T11 4.000 / 3.000 "
                "mm/min), Edelstahl LT7 3 mm 5.000 und 4 mm 4.500, T11 6 mm 2.200 mm/min, Einstechzeiten Edelstahl "
                "nach Herstellertabelle (0,2 bis 2,0 s). T11 endet an der Grenze der TruLaser Tube 5000 fiber 4 kW "
                "(Stahl 10, Edelstahl und Alu 6 mm); dickere Wände zeigen eine Warnung statt einer Zeit "
                "([[maschinen_schneiddaten]]). Unveränderte Standardzeilen werden beim ersten Start angepasst "
                "(mit Sicherung), eigene Werte bleiben; festgeschriebene Angebote rechnen unverändert.",
     "Schneiddaten mit Schneidtabellen abgeglichen, Herkunft je Zeile, Warnung über der Maschinengrenze."],
    ["0.9.200", "<b>Kalkulation genauer</b> ([[kalkulation_genauer]]): neue Maschinenfelder <i>Nebenzeit je Teil</i> "
                "(Ausschieben/Entnehmen), <i>Schneidgas N₂/O₂ [€/h]</i> (Gaskosten je Laserstunde nach dem Gas der "
                "Schneiddaten; genauer über <i>Düse Ø</i> und <i>Gasdruck</i> in den Schneiddaten und <i>Gaspreis "
                "€/m³</i> in den Einstellungen: das Programm rechnet den Gasverbrauch in m³ je Teil) und <i>Rüstzuschlag je weiterer Profilform</i>; in den Einstellungen <i>Ausschuss</i> "
                "(auf Material und Laserzeit) und <i>Schrotterlös Verschnitt</i> (Gutschrift). Alles leer = Preise wie "
                "bisher. <b>Preiseinheit für Kleinteile</b> (optional, ab Werk aus; Einstellung <i>Preis je 100 Stück "
                "unter</i>, z. B. 0,10 €): darunter steht der Preis je 100 Stück im "
                "Angebot und in den Staffeln, ohne Rundungsverlust. <b>Preis-Plausibilität</b> im Angebots-Check: "
                "Preis unter Material, Preis je kg gegen früher verschickte Angebote derselben Abmessung, Ertrag je "
                "Laserstunde. <b>Stundensatz ermitteln</b> je Maschine ([[stundensatz_ermitteln]]): aus Anschaffung, "
                "Nutzungsdauer, Raum, Instandhaltung, Wartung, Strom, Verschleiß und Bediener; ein Satz von Hand "
                "enthält Gas und Strom (Gas nur mit <i>Gas zusätzlich zum Stundensatz</i>); <i>Schneidgas rechnen</i> = nein "
                "schaltet das Gas für alle Maschinen aus. Angebot und Staffel "
                "rechnen Gewinn und Fracht jetzt an einer gemeinsamen Stelle; ein "
                "Test prüft bei jedem Update, dass eine Stufe mit den Mengen des Angebots dessen Preis ergibt.",
     "Kalkulation genauer: Nebenzeit, Schneidgas aus Düse und Druck, Ausschuss, Schrotterlös, Profilwechsel; Preis je 100 Stück; "
     "Preis-Plausibilität; Stundensatz ermitteln"],
    ["0.9.199", "<b>Optimieren mit fester Schweißnaht an mehreren Positionen</b>: Hatten mehrere Positionen einer "
                "Abmessung eine feste Naht (oder Gehrungen), konnte die Optimierung ein Teil doppelt und ein anderes "
                "gar nicht einplanen; die Kontrolle meldete dann „Teile fehlen oder doppelt“. Ursache war ein "
                "Zwischenspeicher, der Teile nach der Reihenfolge der Schnittmuster vertauschte – behoben, die "
                "Kontrolle bleibt. <b>Schweißnaht …</b> für mehrere Positionen: verschiedene Nahtwinkel bleiben je "
                "Position, solange der Winkel nicht geändert wird; die Querschnittslage gilt nur für Rechteckrohre, "
                "bei Quadrat- und Rechteckrohr liegt die Naht immer auf einer Seitenmitte, und die Optimierung "
                "rechnet mit derselben Seite wie Spalte und Prüfung ([[schweissnaht]]).",
     "Optimieren mit fester Naht an mehreren Positionen: kein Teil mehr doppelt/fehlend; Nahtwinkel je Position."],
    ["0.9.198", "<b>STEP-Import mit größeren Gravuren schneller und richtig</b>: Schrift oder Markierungen, die im "
                "CAD als <b>eigene dünne Körper</b> (bis 0,5 mm, oft je Zeichen ein Körper) oder als lose Flächen auf "
                "dem Rohr liegen, werden jetzt Gravur des Rohrs – mit allen Konturen (auch innen in „O“, „A“, „B“), "
                "genau wie in der STEP, wie eingeprägte Schrift. Früher wurde jedes Zeichen als Blech vermessen "
                "(24 Zeichen mehrere Minuten, jetzt wenige Sekunden), als Anbauteil ohne Innenkonturen gezählt oder bei Flächen "
                "gar nicht als Gravur erkannt. Erhabene Schrift bis 0,5 mm gilt nicht mehr als Anbauteil-Verdacht "
                "(rund dreimal schneller), und bei sehr viel eingeprägter Schrift sind die Querschnitte schneller. "
                "Behoben: <b>lange Gravur mit Stecknasen vorne und hinten</b> – im Editor war das halbe Teil "
                "weggeschnitten (der Querschnitt durch die Schrift galt als Profil, die Wand wurde Teil der Enden, "
                "Messung mehrere Minuten). Jetzt Enden, Wand und Schneidweg wie ohne Gravur, wenige Sekunden "
                "([[step_messung]]).",
     "STEP: Schrift als eigener Körper oder Fläche wird Gravur des Rohrs (statt Minuten nur Sekunden)."],
    ["0.9.197", "<b>Reihenfolge der Positionen ändern</b>: markierte Positionen mit <b>Alt+↑ / Alt+↓</b>, "
                "Rechtsklick (Nach oben, Nach unten, An den Anfang, Ans Ende) oder durch Ziehen am Zeilenkopf "
                "verschieben; Schweißbaugruppen wandern mit ihren Teilen, Sätze ganz. Kalkulation, Angebots-PDF und "
                "Werkstattpapiere folgen, aufsteigende Positionsnummern bleiben aufsteigend, Staffeln je Position und "
                "ein aktueller Schnittplan ziehen mit; <i>Positionsnummern neu vergeben</i> zählt 10, 20, 30 … "
                "([[reihenfolge]]). <b>Artikelnummer im STEP-Import ändern</b>: Spalte <i>Artikelnummer ✎</i> mit "
                "Doppelklick, F2 oder Rechtsklick; gleiche Nummer an zwei Teilen rot mit Hinweis, schon im Angebot "
                "gelb, leeres Feld = wieder die Nummer aus der STEP ([[importprofile]]).",
     "Reihenfolge der Positionen verschieben (Alt+↑/↓, Ziehen); Artikelnummer im STEP-Import ändern."],
    ["0.9.196", "<b>Schneiddaten auf Standard zurücksetzen mit Vorschau</b>: Der Knopf <i>Auf Standard zurücksetzen "
                "…</i> öffnet einen Dialog: alle Maschinen, eine Maschine oder nur die markierten Zeilen, wahlweise "
                "eigene Zeilen (z. B. je Werkstoff) behalten. Die Vorschau zeigt jeden Wert jetzt → Standard, welche "
                "eigenen Zeilen entfallen und welche Standardzeilen fehlen; vorher legt das Programm eine "
                "Datensicherung an, die letzte Rückfrage steht auf Nein. Werte, die vom Standard abweichen, sind in "
                "der Tabelle orange, der Tooltip nennt den Standard ([[schneiddaten_standard]]). "
                "<b>Schneidzeit genauer</b>: Anfangs- und Endschnitt aus dem Schneidweg-Rechner und aus "
                "<i>Bohrungen prüfen</i> zählen wie beim STEP-Import nach ihrem Hüllmaß (bisher immer Vorschub groß, "
                "die Einsparung gemeinsamer Schnitte zog aber mit der Klasse des Endes ab); Innenkonturen für "
                "Programmierzeit und Regeln ohne die Enden. Standard <i>Zeit je Ecke</i> nach Wandstärke, 0,2 s + 0,05 s je mm (leere Richtwertzeilen "
                "werden einmalig gefüllt). Neues Maschinenfeld <i>Zeit je Kontur (Anfahren/Drehen)</i>, leer = 0 "
                "([[schneidzeit_genauer]]). Festgeschriebene Angebote rechnen unverändert.",
     "Schneiddaten zurücksetzen mit Vorschau und Sicherung; Schneidzeit: Enden, Ecken, Anfahren genauer."],
    ["0.9.195", "<b>Zeitraum in der Angebotsliste</b>: Neben dem Vorgang wählt man, welche Angebote die Liste zeigt "
                "– mit Datum oder Änderung in den letzten 30, 60, 100, 150 oder 365 Tagen oder alle (Vorgabe 150 Tage, "
                "Einstellungen → Angebot, nur dieser Arbeitsplatz). Fällige Wiedervorlagen, beauftragte und noch nicht "
                "versendete Aufträge und geöffnete Angebote bleiben immer sichtbar, die Suche findet alle. Unter der "
                "Liste steht, wie viele ältere ausgeblendet sind, mit „Alle zeigen“ ([[angebote]]).",
     "Angebotsliste: Zeitraum 30/60/100/150/365 Tage oder alle, Suche findet weiter alle."],
    ["0.9.194", "<b>Teuerungszuschlag je Werkstoff</b>: Bei den Werkstoffen gibt es neu die Spalten "
                "<i>Teuerungszuschlag je</i> (% oder €/kg), <i>Teuerungszuschlag</i> und <i>Teuerung Stand</i>. "
                "Der Zuschlag kommt auf den Materialpreis aus Lieferlängen, Preisen oder Tonnenpreis, nicht auf "
                "Oberflächen-Aufpreise und Preise von Hand. Der Tooltip des Materialpreises nennt ihn, der "
                "Angebots-Check meldet einen Zuschlag ohne Stand oder älter als 3 Monate, festgeschriebene Angebote "
                "behalten ihren Zuschlag ([[teuerungszuschlag]]). Neu ist auch der <b>Preis-Simulator</b> "
                "(Datei → Preis-Simulator …): Was wäre, wenn Material einer Kategorie oder Stundensätze teurer "
                "werden? Er zeigt für alle offenen Angebote den Verkaufspreis vorher/nachher, mit Admin-Rechten "
                "auch die Marge bei gleichem Preis, ohne etwas zu speichern ([[preis_simulator]]). Beim Vorgang "
                "<b>Abgelehnt</b> fragt das Programm nach dem <b>Absagegrund</b> (optional Preis des Wettbewerbs); "
                "<i>Datei → Angebots-Auswertung …</i> zeigt die Trefferquote je Kunde, Werkstoff-Kategorie, "
                "Preisklasse und Absagegrund ([[absage]]). Für beauftragte Angebote gibt es die "
                "<b>Auftragsbestätigung (PDF)</b> im Menü <i>Ausgaben</i>: Layout und Preise des Angebots, "
                "Bestellnummer des Kunden, Liefertermin mit KW, Nummer wie das Angebot oder eigener Nummernkreis "
                "AB-2026-00001 ([[auftragsbestaetigung]]). <b>Etiketten mit QR-Code</b> je Position "
                "(Ausgaben bzw. Reiter Fertigung, A4-Bogen oder Etikettendrucker) und <b>Rückmeldung per Scan</b>: "
                "Reiter Fertigung → Scannen …, Arbeitsschritt wählen, scannen; der Unterreiter Rückmeldungen zeigt "
                "je Position, was geschnitten, entgratet und verpackt ist ([[etiketten]]). "
                "<b>Maschinenauslastung je Woche</b> (Datei bzw. Reiter Fertigung): Laserstunden der Aufträge gegen "
                "den Schichtkalender (Stunden je Tag und Maschine, Samstag, Feiertage, Betriebsruhe), auf Wunsch mit "
                "verschickten Angeboten nach Trefferquote ([[auslastung]]). <b>Reklamationen</b> je Auftrag und "
                "Position (Ausgaben → Reklamation erfassen …) mit Fehlerart, Ursache, Maßnahme und Kosten; die Kosten "
                "stehen als eigene Kostenart in der Nachkalkulation, Datei → Reklamationen … zeigt offene und die "
                "Quote je Fehlerart, Kunde und Werkstoff ([[reklamation]]).",
     "Teuerungszuschlag je Werkstoff; Preis-Simulator; Absagegrund mit Trefferquote; Auftragsbestätigung als PDF; "
     "QR-Etiketten mit Rückmeldung per Scan; Maschinenauslastung je Woche; Reklamationen."],
    ["0.9.193", "<b>Prüfung Performance, System, Daten, Optik</b> (Berechnung und Import unverändert): Am "
                "<b>Laptop</b> (Angebotsseite niedriger als 760 Punkte) sind die Karten oben flacher, Kalkulation und "
                "Fracht stehen zugeklappt nebeneinander, so sind mehr Positionen sichtbar ([[angebot]]). "
                "Zugeklappte Zeilen enden mit „…“ statt abgeschnitten, der Tooltip zeigt alles. Einblendungen stehen "
                "links neben der Übersicht und verdecken keine Preise ([[meldungen]]). In den Zeiten der Übersicht "
                "stehen Zeit und Betrag mit Abstand. Leere Listen in Fertigung, Versand und Lager zeigen einen "
                "Hinweis ([[fertigung]]). Eine seltene Fehlermeldung beim Schließen eines Angebots ist behoben.",
     "Laptop: mehr Positionen sichtbar, „…“ statt abgeschnitten, Einblendung neben der Übersicht, Hinweis in leeren Listen."],
    ["0.9.192", "<b>Enter schließt kein Fenster mehr</b>: In allen Dialogen übernimmt Enter nur die Eingabe im "
                "Feld (Text, Zahl, Rechnung, Datum, Auswahl), in Tabellen geht es eine Zeile weiter. Übernehmen "
                "und schließen nur mit dem Knopf oder gezielt mit <b>Strg+Enter</b>. Ausnahmen: reine Ja/Nein-"
                "Fragen, Dateiauswahl und Suchen und ausführen ([[eingaben]]).",
     "Enter schließt in keinem Dialog das Fenster; Strg+Enter übernimmt."],
    ["0.9.191", "<b>PDF-Dokumente ohne Überlappungen</b>: Alle Ausgaben (Angebot, Werkstattpapiere, Kalkulation, "
                "Nachkalkulation, Palettenschein, Verladeliste) mit langen Texten geprüft und korrigiert – langer "
                "Briefkopf in der Fußzeile bis zu drei Zeilen statt über die Seitenzahl, Stundensatz in der "
                "Kalkulation nicht mehr über der Gesamtzeit, Artikeltext im Palettenschein mit „…“ statt über der "
                "Stückzahl, Einheit „pausch.“ ohne Umbruch, Kopfangaben oben bündig und langer Kundenname breiter, "
                "zu lange Tabellenwerte umbrochen. Dazu: Stangenbild mit drei Stangen je Seite (Werkstattpapiere rund "
                "20 % kürzer), Summe und Konditionen im Angebot zusammen, lange Artikelnummern kleiner und lesbarer "
                "([[ausgabe]]).",
     "PDFs: keine Überlappungen bei langen Texten, Stangenbild kompakter, Summe und Konditionen zusammen."],
    ["0.9.190", "<b>Staffeln rechnen sich nach Änderungen selbst neu</b>: Sind im Angebot Stufen angelegt, rechnet "
                "das Programm sie nach jeder Änderung am Angebot (Positionen, Stückzahl, Material, Zusatzarbeiten, "
                "Editoren, Rückgängig, Stammdaten, Einstellungen) 1,5 s nach der letzten Eingabe im Hintergrund neu, "
                "vor dem Angebots-PDF sofort. Stufen legt es weiterhin nie selbst an; Mengen und Werte der Stufen "
                "bleiben unverändert ([[staffeln_automatisch]]).",
     "Angelegte Staffeln werden nach Änderungen am Angebot automatisch neu gerechnet."],
    ["0.9.189", "<b>Gehrung auf 2D umstellen</b>: Wird im Editor das Häkchen <i>3D-Schnittbearbeitung</i> "
                "abgewählt, gilt jede Gehrung sofort als 2D, auch wenn am Ende noch <i>Gehrung in 3D</i> stand: "
                "3D-Ansicht, Skizze, Zeichnung/PDF und STEP-Export zeigen die lange Seite um Wand · tan(Winkel) "
                "kürzer, die Innenkante bleibt maßhaltig, die Schnittlänge gleich. Eine in 3D übernommene ebene "
                "STEP-Gehrung wird beim Umstellen auf 2D ebenso kürzer. Neu auch für offene Profile und Flachstahl: "
                "der Schenkel, der zur langen Seite zeigt, wird um seine Dicke · tan(Winkel) kürzer "
                "([[schneidweg_rechner]]).",
     "Gehrung auf 2D umstellen: lange Seite überall um Wand · tan(Winkel) kürzer, auch offene Profile."],
    ["0.9.188", "<b>DXF-Import robuster</b> für Bleche und Rohre: Papierbereich (Layout), Schriftfelder mit Attributen, "
                "Mehrfach-Blöcke, Linientyp „VonLayer“, Sonderzeichen und Splines aus Stützpunkten werden gelesen. "
                "Kleine Lücken (bis 0,5 mm) werden geschlossen, doppelte Linien und Bohrungen zählen einmal, Teile mit "
                "gemeinsamer Kante werden beide erkannt. Gleiche Bleche werden ein Teil mit Stückzahl. Kreise auf der "
                "Außenkante, sich schneidende Konturen und Zoll ohne Einheit meldet das Prüffenster "
                "([[dxf_import]]). Im Rohr-Schriftfeld wird auch „Werkstoff: S235JR“ gelesen. <b>Rohr oder Blech</b> wird "
                "sicherer erkannt: mehr Profiltexte (SHS, RHS, CHS, Profilrohr, QR40x40x3, mit Norm), eine "
                "Rohrzeichnung braucht einen Beleg (Bemaßung, verdeckte Kanten, Schraffur, Profiltext), sonst fragt "
                "das Zuordnungsfenster und bietet „Als Blech importieren“.",
     "DXF-Import robuster: Layout, Attribute, Lücken, doppelte Linien, gleiche Teile, Rohr oder Blech sicherer."],
    ["0.9.187", "<b>STEP-Import für typische Laserteile robuster</b> (Testreihe nach Beispielbildern: Profile mit "
                "Lochbildern auf mehreren Seiten, Kerben, Ausklinkungen, C-Profile, Kantteile): <b>offene Profile</b> "
                "(U, C, L, Kantprofil) zeigen Ausklinkungen am Ende (auch T-förmig), Kerben im Schenkel und "
                "V-Ausschnitte mit dem echten Umriss wie in der STEP statt als Kreis; eine breite Kerbe über drei "
                "Wände eines Rechteckrohrs lag im Editor auf der falschen Seite; schräg liegende Langlöcher und "
                "Rechtecke werden Sonderkontur mit Umriss. <b>Senkungen</b> auch, wenn der Kegel durch die ganze Wand "
                "geht, und Zylindersenkungen – geschnitten wird nur der Bohrungs-Ø (auch bei Blechen). <b>Gewinde</b>: "
                "Vorschlag auch nach dem Kern-Ø nach ISO (M8 = 6,647) und für ausmodellierte Gewinde "
                "([[bohrungen_pruefen]]).",
     "STEP: offene Profile mit echtem Umriss, Senkung durch die Wand, Gewinde nach ISO-Kern-Ø und ausmodelliert."],
    ["0.9.186", "<b>Fehlende Abmessung gleich anlegen</b>: Steht eine getippte Abmessung (z. B. RE 70x30x3) nicht in "
                "den Stammdaten, bietet ein Menü unter dem Feld <i>Abmessung … neu anlegen …</i> an – in der "
                "Schnellzeile, in der Profilspalte und in der Kopfzeile des Rohr-Editors (Neue Position). Das Fenster "
                "ist aus der Eingabe vorbelegt (Form, Maße, Profil-ID, kg/m), fragt bei C-Profil und Trägern ohne "
                "Normtabelle die Fläche ab, und die Position wird danach mit der neuen Abmessung angelegt. Kein "
                "Materialpreis wird geraten ([[abmessung_neu]]).",
     "Unbekannte Abmessung in Schnellzeile, Profilspalte oder Rohr-Editor: Menü „neu anlegen …“, vorbelegt."],
    ["0.9.185", "<b>Viele Angebote, Teil 2</b>: <b>Wiederholteile</b> sucht über einen Index nur passende Positionen "
                "und stuft im Hintergrund ein, das Angebot bleibt auch bei Tausenden Angeboten flüssig "
                "([[wiederholteile]]). Der Reiter <b>Versand</b> rechnet erst, wenn er gezeigt wird; Aufträge ohne "
                "Palettenschein, deren Liefertermin über 90 Tage zurückliegt, stehen automatisch unter Archiviert "
                "([[versand]]). <b>Sicherungen gestaffelt</b>: 7 Tage, 4 Wochen, 12 Monate, vor Updates nur die letzten 3; "
                "die tägliche Sicherung läuft im Hintergrund, der Schnittplan wird gepackt gespeichert (Datendatei etwa "
                "40 % kleiner, [[datensicherung]]). Neu: <b>Datei → Alte Angebote archivieren …</b> und <b>Archiv "
                "durchsuchen …</b>, eine Archivdatei je Jahr, Angebote lassen sich jederzeit zurückholen ([[archiv]]). <b>"
                "Abgleich mit den Kollegen bei vielen Angeboten schnell</b>: Das Programm packt nur noch Angebote "
                "neu, die seit dem letzten Abgleich geändert wurden, und legt im gemeinsamen Ordner je Mitarbeiter einen "
                "Ordner mit einer Datei je Monat an; über das Netz geht nur der geänderte Monat (bei 1.000 Angeboten "
                "0,1 statt 6,6 Sekunden). Alte Einzeldateien werden weiter gelesen. Bitte alle Arbeitsplätze "
                "aktualisieren, ältere Programme sehen die neuen Ordner nicht ([[gemeinsamer_ordner]]).",
     "Viele Angebote: Wiederholteile schneller, Versand-Reiter, gestaffelte Sicherungen, Archiv alter Angebote, Abgleich nur geänderte Angebote je Monat."],
    ["0.9.184", "<b>Musterteile</b>: Positionen lassen sich als <b>Muster</b> markieren (Spalte <i>Muster</i>, "
                "Rechtsklick „Muster an/aus“, Häkchen in Rohr-, Blech-, Baugruppen-Editor und Satz in 3D). Muster "
                "stehen im Angebot mit 0,00 € und dem Vermerk „Muster – im Serienpreis enthalten“; ihre Kosten "
                "(Selbstkosten mit normalem Gewinn, Zukauf nur mit Aufschlag) werden nach Wert auf die "
                "Serienpositionen umgelegt, so entsteht nie eine Minusmarge. Muster laufen als eigener Lauf mit "
                "eigenem Rüsten, Material nach belegter Länge. Je Angebot umschaltbar auf eine eigene Zeile "
                "„Musterkosten einmalig“ (ohne Serienposition automatisch). Staffelpreise legen die Muster je "
                "Stufe einmal um; das Angebots-PDF nennt, dass die Muster berechnet werden, wenn keine Serie "
                "folgt ([[musterteile]]).",
                "Musterteile: 0 € im Angebot, Kosten auf die Serie umgelegt, keine Minusmarge"],
    ["0.9.183", "<b>Viele Angebote</b>: Staffeln, Mengenstufen und STEP-Protokoll eines Angebots findet die Datendatei "
                "jetzt über einen Index. Öffnen, Rückgängig, Löschen und der Abgleich mit den Kollegen bleiben auch bei "
                "Tausenden Angeboten gleich schnell; die Indizes entstehen beim ersten Start von selbst ([[datensicherung]]).",
     "Datendatei: schneller bei vielen Angeboten (Indizes)."],
    ["0.9.182", "<b>Eigene Abrechnungsregeln für Zusatzarbeiten</b>: Die Arbeitsgang-Regeln setzen jetzt auch, "
                "<i>wie</i> abgerechnet wird und <i>wann</i> eine Zusatzarbeit automatisch gilt. Je Regel Zuordnung "
                "(Vorschlag, automatisch, nur Preis), Abrechnung, Preis je Einheit, Menge (z. B. Innen- + "
                "Außenfläche), Faktor und Mindestbetrag je Teil, neue Bedingungen Abmessung von/bis und Teileart "
                "Rohr/Profil bzw. Blech; die genaueste Regel gewinnt. Automatische Zusatzarbeiten werden gerechnet, "
                "stehen gelb mit „(automatisch)“ in Positionsliste und Unterzeilen und lassen sich unter "
                "„Arbeitsgänge vorschlagen …“ abwählen. Neu vorbelegt: <b>Strahlen</b> nach kg Fertigteil mit drei "
                "Beispielregeln (aus). Zusatzarbeiten haben neu Menge aus, Faktor und Mindestbetrag je Teil; der "
                "Aufpreis einer Oberfläche geht auch je kg oder je m². Gewinde, Senken, Flowdrill und Bohren "
                "bleiben € je Stück; alte und festgeschriebene Angebote rechnen unverändert ([[abrechnungsregeln]]).",
     "Eigene Abrechnungsregeln: Preis je Werkstoff/Profil, automatisch zuordnen, Strahlen €/kg, Aufpreis je kg."],
    ["0.9.181", "<b>Mehr im gemeinsamen Ordner</b> ([[gemeinsamer_ordner_mehr]]): <b>Anfragen</b> liegen im Unterordner "
                "<i>Anfragen</i> (wenn kein eigener Anfrage-Ordner eingetragen ist) und lassen sich mit <i>Zuweisen …</i> "
                "einem Kollegen geben; alle sehen <i>für MK</i>, beim Kollegen steht sie fett ([[anfragen]]). Neue "
                "<b>Angebotsordner</b> (PDF, CSV, STEP) entstehen im Unterordner <i>Angebote</i>, so öffnet jeder "
                "denselben Ordner; ältere bleiben in der eigenen Ablage. <b>Notizen an Kollegen</b> (Vorgang ▾ → "
                "<i>Notiz an Kollegen …</i>, wahlweise mit Wiedervorlage) stehen auf seiner Startseite unter "
                "<i>Heute</i> mit <i>Erledigt</i> und <i>Antworten …</i>. Die <b>Sicherung beim Beenden</b> kommt "
                "zusätzlich nach <i>Sicherungen/Kürzel</i>. Alles einzeln abschaltbar (Einstellungen → Benutzer).",
     "Anfragen zuweisen, Angebotsordner, Notizen und Sicherung im gemeinsamen Ordner"],
    ["0.9.180", "<b>Löschschutz für optimierte Angebote</b>: Neue Einstellung <i>Angebot → Löschschutz: optimierte "
                "Angebote nicht löschbar</i> (Vorgabe aus). <i>immer</i> schützt jedes Angebot, das "
                "einmal optimiert wurde, <i>nur von Hand</i> nur die von Hand optimierten. "
                "Geschützte Angebote lassen sich in der Angebotsliste nicht löschen; der Hinweis nennt den Ausweg "
                "(Vorgang <i>Abgelehnt</i> oder <i>Kopieren</i>). Positionen bleiben löschbar, mit Admin-Rechten "
                "fragt das Programm nach und löscht trotzdem. Ältere Angebote mit <i>Optimiert am</i> gelten als "
                "optimiert ([[angebote]]).",
     "Löschschutz: einmal optimierte Angebote nicht mehr löschbar (Einstellung, Vorgabe aus; Admin darf)."],
    ["0.9.179", "<b>Mehrere Mails zur selben Anfrage</b>: Mails vom selben Kunden mit derselben Anfrage-Nr. oder "
                "demselben Betreff (ohne AW:/WG:) innerhalb von 3 Tagen sind eine Anfrage, auch ein Nachtrag ohne "
                "STEP. Bei verschiedenen Angaben gilt die neueste Mail, die ältere steht als Hinweis im Prüfdialog "
                "(Stückzahl gelb mit Tooltip). Kommt eine STEP-Datei neu, gilt die neueste Version; die alte bleibt "
                "als <i>Name (alt)</i> liegen und wird nicht importiert. Ein Nachtrag zu einem schon übernommenen "
                "Angebot wird auf der Startseite genannt ([[anfrage_mail]]).",
     "Mehrere Mails je Anfrage: zusammengefasst, neueste gilt, alte STEP als „(alt)“."],
    ["0.9.178", "<b>Zusammenarbeit über den gemeinsamen Ordner</b>: Das Programm gleicht jetzt <b>alle 2 Minuten "
                "von selbst</b> ab (nur wenn sich etwas geändert hat; Einstellung <i>Automatischer Abgleich alle [min]</i>), "
                "rechts in der Statusleiste steht <i>⇄ abgeglichen 14:32</i>. <b>Wer arbeitet woran</b>: hat ein "
                "Kollege sein Angebot offen, steht <i>● geöffnet</i> hinter seinem Kürzel ([[wer_arbeitet_woran]]). "
                "Angebote lassen sich <b>an einen Kollegen übergeben</b> (Vorgang ▾, mit Notiz, zurücknehmbar) und "
                "beim Bearbeiter die <b>Übernahme anfragen</b>; er wird gefragt und kann übergeben oder ablehnen "
                "([[angebot_uebergeben]]). <b>Konflikte</b> (dieselben Stammdaten bei zwei Kollegen verschieden "
                "geändert) zeigt <i>Datei → Abgleich-Konflikte …</i>; die verlorene Fassung lässt sich "
                "wiederherstellen ([[abgleich_konflikte]]).",
     "Gemeinsamer Ordner: Abgleich alle 2 Minuten, sehen wer woran arbeitet, Angebote übergeben/anfragen, Konflikte"],
    ["0.9.177", "<b>Schweißbaugruppe: a-Maß, Heftpunkte und Schweißzeit genauer</b>: Die a-Maß-Regel schlägt mindestens "
                "3 mm und mindestens √(dickere Wand) − 0,5 vor (EN 1993-1-8), nie mehr als die dünnere Wand. Liegt "
                "ein a-Maß zwischen zwei Kennwertzeilen, rechnet die Schweißzeit den Wert dazwischen (nach a²); dicke "
                "Nähte werden mehrlagig mit Zeit je Zusatzlage. Heftpunkte zählen beide Enden mit, rundum nach dem "
                "Umfang, Edelstahl und Aluminium enger; die Heftzeit wächst mit der Wanddicke. Neue Regeln unter "
                "Einstellungen → Schweiß-Vorkalkulation (Richtwerte laden ergänzt sie) ([[vorkalkulation_baugruppe]]).",
     "Schweißbaugruppe: a-Maß mit Mindestmaß, Kennwerte dazwischen, mehrlagig, Heftpunkte genauer."],
    ["0.9.176", "<b>Schweißbaugruppe: Erreichbarkeit der Nähte aus STEP</b>: Die STEP-Messung prüft je Naht, ob der "
                "Brenner hinkommt (andere Teile im Weg, enge Ecken). Die Vorkalkulation schlägt daraus die "
                "<b>Zugänglichkeit</b> je Nahtgruppe und die <b>Wendevorgänge</b> vor (gelb, mit Begründung). Nähte, "
                "die gar nicht erreichbar sind, zeigt das 3D orange, der Status warnt "
                "([[baugruppe_erreichbar]]).",
     "Schweißbaugruppe: Zugänglichkeit und Wenden aus der Erreichbarkeit im STEP."],
    ["0.9.175", "<b>Schweißbaugruppe: Serieneffekt, Rüsten je Los, Lernen der Vorkalkulation</b>: In den Stammdaten der "
                "Baugruppe senkt ein <b>Serieneffekt</b> (% je Verdopplung, mit Untergrenze) die Zeit für Schweißen "
                "und eigene Arbeitsgänge je Staffelstufe; die <b>Losgröße</b> lässt Rüstzeiten je Los anfallen "
                "([[baugruppe_serie]]). Die Nachkalkulation nimmt freiwillig <i>davon Rüsten / Positionieren / "
                "Verputzen</i> auf, daraus schlägt das Programm Faktoren für die Regeln der Vorkalkulation vor. Die "
                "Zeiten zeigen Schweißen und Arbeitsgänge getrennt.",
     "Schweißbaugruppe: Serieneffekt, Rüsten je Los, Vorkalkulation lernt aus der Nachkalkulation."],
    ["0.9.174", "<b>Schweißbaugruppe: Werkstoff und Nachbehandlung</b>: Nahtgruppen haben die Spalte <b>Werkstoff</b> "
                "(Faktor auf die Lichtbogenzeit, Richtwert Edelstahl 1,3); die Vorkalkulation schlägt ihn aus den "
                "Teilen vor. Neu vorgeschlagen werden <i>Beizen / Passivieren</i> bei Edelstahl, <i>Richten</i> bei "
                "viel Naht je kg und dünner Wand und eine <i>Sichtprüfung</i> – mit Regeln unter Einstellungen → "
                "Schweiß-Vorkalkulation (Richtwerte laden ergänzt sie) ([[vorkalkulation_baugruppe]]).",
     "Schweißbaugruppe: Faktor Werkstoff, Vorschläge Beizen, Richten, Sichtprüfung."],
    ["0.9.173", "<b>Schweißbaugruppe: Mengen aus den Einzelteilen</b>: Arbeitsgänge nach Gewicht, Fläche oder Länge "
                "(Verzinken €/kg, Pulvern €/m², Prüfen je Teil) rechnen ihre Menge selbst – neue Spalte <b>Menge "
                "aus</b> mit Gewicht, Oberfläche, Länge, Naht oder Teile; ändert sich ein Teil, ändert sich der Preis "
                "mit. Über der Tabelle stehen Gewicht, Außenfläche, Nahtlänge und Anzahl Teile je Baugruppe. Das "
                "Gewicht für das Wenden kommt ohne Eintrag in den Stammdaten aus der Summe der Teile "
                "([[baugruppe_mengen]]).",
     "Schweißbaugruppe: Menge aus Gewicht, Oberfläche, Länge, Naht oder Teile automatisch."],
    ["0.9.172", "<b>E-Mail und Anfrageformular schlauer</b>: Ist der Absender unbekannt, legt das Programm den "
                "Kunden mit Adresse, Ansprechpartner und Telefon aus Signatur bzw. Formular an – mit der Bemerkung "
                "<i>Kunde prüfen</i> (bei Abbruch wieder entfernt). Das Anfrageformular wird wie die Mail ausgewertet "
                "(Lieferzeit, Werkstoff). Robuster: ältere Outlook-Mails nur mit RTF-Text, <i>winmail.dat</i>, "
                "beschädigte Anhänge. Intelligenter: bei Antworten zählt die neueste Nachricht, Lieferzeit auch als "
                "Dauer (<i>in 3 Wochen</i>), Kunde über den Firmennamen in der Domain; Hinweise zu Mengenstaffel, "
                "Zusatzarbeiten und doppelter Anfrage-Nr. ([[anfrage_mail]]). <b>PDF: Zeichnung oder Formular</b>: "
                "Jede Seite eines PDFs (auch Scans) wird eingeordnet; Zeichnungen liefern nur ihr Schriftfeld "
                "(Stückzahl, Werkstoff für das passende STEP-Teil, gelb), nie Positionen; die Einordnung lässt sich "
                "im Prüfdialog umschalten ([[anfragen]]). <b>ZIP-Dateien</b> im Anfrage-Ordner oder aufs "
                "Programm gezogen werden ausgepackt. Texterkennung bei mehreren Scans deutlich schneller.",
     "Mail/Formular: neue Kunden („Kunde prüfen“), RTF/winmail.dat; PDF Zeichnung/Formular je Seite; ZIP auspacken."],
    ["0.9.171", "<b>Artikelnummer aus der STEP-Datei besser</b>: Schreibt das CAD-System eine eigene "
                "<b>Teilenummer</b> in die STEP-Datei, wird sie die Artikelnummer und die Benennung die Bezeichnung. "
                "Namen werden bereinigt: CAD-Zusätze (<i>Rohr:1</i>, <i>Teil1&lt;1&gt;</i>), Dateiendungen "
                "(<i>.SLDPRT</i>), Kopie-Zusätze (<i>Kopie von</i>, <i> - Kopie</i>, <i> (1)</i>) und die "
                "<b>Revision</b> (<i>_Rev B</i>, <i>_v2</i>, <i>Index C</i>, steht dann in der Bezeichnung) fallen "
                "weg. CAD-Standardnamen wie <i>Teil1</i>, <i>Part1</i>, <i>Body1</i> gelten wie kein Name (dann der "
                "Dateiname). Steht eine Nummer im Namen (<i>Strebe links 4711-020</i>), wird sie erkannt. Im "
                "<b>Prüfdialog</b> zeigt der Tooltip auf dem Teil die Herkunft der Nummer, unsichere Nummern sind "
                "gelb, und ein Doppelklick ändert die Artikelnummer ([[importprofile]]).",
     "Artikelnummer aus STEP: Teilenummer, Bereinigung, Revision, Nummer im Namen, im Prüfdialog änderbar"],
    ["0.9.170", "<b>12-m-Zuschnitt genauer</b>: Für die Werkstücke aus einer 12-m-Stange probiert die Optimierung "
                "neben Beladelänge und 12 m ÷ 2 … 6 jetzt alle 250 mm ab der nötigen Länge als Obergrenze aus (bis "
                "300 Teile je Abmessung). Bei gemischten Teilelängen spart das Lieferstangen, z. B. 3 statt 4 "
                "12-m-Stangen ([[lieferlaengen]]).",
     "12-m-Zuschnitt: feineres Raster der Werkstücklängen, spart bei gemischten Teilen Stangen."],
    ["0.9.169", "<b>Teil länger als die Stange</b>: Passt ein Teil nicht auf die 6-m-Stange des Angebots, wohl aber "
                "auf eine längere Lieferlänge (z. B. 12 m, beim Lieferanten auf Beladelänge zugeschnitten) oder auf "
                "eine von Hand vorgegebene Stange, zeigt die Position keinen FEHLER mehr. Die Optimierung plant die "
                "Gruppe dann automatisch mit der günstigsten passenden Lieferlänge, auch bei ausgeschaltetem "
                "Längenvergleich ([[lieferlaengen]]). Neu im Fenster 12-m-Lösung ansehen: <b>Vorschlag Mischen</b>, "
                "z. B. 10 × 12 m + 1 × 6 m statt 11 × 12 m, wenn das günstiger ist (nur zum Ansehen, der Schnittplan "
                "bleibt, nur bei eingeschaltetem Längenvergleich) mit Link <i>Stangenbelegung ansehen …</i>. "
                "Stangenbild-Übersicht: das Detail-Fenster wechselt mit der Maus auf die nächste Stange und schließt "
                "von selbst, wenn die Maus die Stangen verlässt ([[stangenbild]]).",
     "Zu langes Teil ohne FEHLER bei 12 m; Vorschlag 12 m + 6 m; Stangen-Popup folgt der Maus."],
    ["0.9.168", "<b>CSV-Dateien robuster</b>: Der <b>Kunden-Import</b> liest jetzt auch Dateien aus Excel für Mac, "
                "Unicode-Text (UTF-16), Komma- und Tab-Dateien, <i>sep=;</i> und Titelzeilen, stürzt bei kaputten "
                "Dateien nicht mehr ab und nennt bei jedem Fehler Zeile und Spalte (Buchstabe und Titel); Export → "
                "Import zeigt nie Fehler für unveränderte Kunden. Der <b>Kunden-Export</b> schützt führende Nullen, "
                "+49-Telefonnummern und Ähnliches vor Excel und schreibt unter Windows keine doppelten Zeilenenden "
                "mehr (auch Zukauf-, PLZ- und Fertigungs-CSV) ([[kunden_csv]]). Im <b>Angebots-CSV</b> stehen in "
                "Zahlenspalten nur noch Zahlen: Lieferzeit in Wochen (2 statt „ca. 2 Wochen“), Marge Netto% und "
                "Verschnitt ohne %-Zeichen, Schneidgas N2/O2 ([[csv_export]]).",
     "CSV robuster: Kunden-Import mit Zeile/Spalte, Excel-Schutz; Angebots-CSV Lieferzeit als Zahl."],
    ["0.9.165", "<b>E-Mail aus Outlook auslesen</b>: Eine ganze Mail (*.msg aus Outlook oder *.eml) im "
                "Anfrage-Ordner oder auf die Startseite gezogen reicht – das Programm packt STEP-Dateien, Formulare, "
                "ZIP-Archive und weitergeleitete Mails aus und belegt vor: Kunde über die Absenderadresse bzw. "
                "Domain, Anfrage-Nr. aus Betreff und Text, Wunschtermin als Lieferzeit (KW oder Datum), interne "
                "Bemerkung mit Absender und Betreff, Werkstoff (nur eindeutig) und Stückzahlen je Artikel. Der "
                "Prüfdialog zeigt oben, was aus der Mail kommt ([[anfrage_mail]]).",
     "Outlook-Mail (.msg/.eml) auslesen: Anhänge, Kunde, Anfrage-Nr., Lieferzeit, Werkstoff, Stückzahlen."],
    ["0.9.164", "<b>Sätze heben sich ab</b>: In der Positionsliste stehen die Positionen eines Satzes zusammen und "
                "sind je Satz farbig hinterlegt (abwechselnd blau und violett, auch im Dunkelmodus). Die Spalten "
                "Satz und Stück je Satz stehen gleich hinter Pos.; die erste Position zeigt fett Name und Anzahl "
                "Sätze. Eine Klammer am Zeilenkopf (▾ │ └) zeigt, was zusammengehört; Klick auf ▾ klappt den Satz "
                "zu. Im Reiter Kalkulation (kompakt und alle Spalten) gibt es die Spalte Satz mit derselben Farbe "
                "([[saetze_abheben]]).",
     "Sätze farbig und zusammen in Positionsliste und Kalkulation, Klammer am Zeilenkopf, zuklappbar."],
    ["0.9.163", "<b>STEP-Import und Editor robuster</b> (Testreihe über alle Testteile und die bisherigen STEP-Dateien): "
                "<b>Flowdrill</b> (Fließlochbohrung) fehlte im Editor, steht jetzt mit Kernloch Ø an der gemessenen "
                "Stelle; <b>Senkung</b> zeigt im 3D den Senkrand wie die STEP. <b>Offene Profile</b>: Gehrungen an U-, "
                "L- und Flachprofilen lagen teils auf der falschen Seite (bis 50 mm), Rechteck-Ausschnitte und "
                "Langlöcher waren nur ein Kreis; beides jetzt wie in der STEP. <b>C-Profil</b> mit der gemessenen "
                "Abkantung ([[schneidweg_rechner]]).",
     "STEP-Import robuster: Flowdrill im Editor, Gehrungen und Ausschnitte an offenen Profilen, C-Profil mit Lippe."],
    ["0.9.162", "<b>Kleine Löcher trotzdem schneiden</b>: Für Bohrungen kleiner als 0,7 × Wandstärke gibt es neben "
                "<i>Gravur Ø0,5</i> und <i>Loch Ø0,5</i> (markieren und aufbohren) die dritte Wahl <i>Ø schneiden "
                "(ohne Bohren)</i>: der Laser schneidet den vollen Lochdurchmesser, Zeit und Preis kommen aus dem "
                "Schneidweg, es gibt keine Zusatzarbeit Bohren und keine Warnung. Je Bohrung im Fenster Bohrungen "
                "prüfen wählbar, Vorgabe für STEP-Import und alle Editoren in der Einstellung <i>Bohrung kleiner "
                "als 0,7 × Wandstärke am Laser</i> ([[bohrungen_pruefen]]).",
     "Bohrung < 0,7 × Wand: 3. Option „Ø schneiden (ohne Bohren)“."],
    ["0.9.161", "<b>Wettbewerbsvergleich umgesetzt</b>: <b>Lager</b> (Einstellung, Vorgabe aus) mit Bestand, "
                "Zugang, Korrektur, Journal und – nur wenn eingeschaltet – <b>Reststücken</b>; im beauftragten Angebot "
                "<i>Material aus Lager …</i> plant, reserviert ohne Doppelbelegung und bucht den Verbrauch "
                "([[lager]]). <b>Nachkalkulation</b> mit Fracht und Ausschuss, gespeichertem Soll-Stand und "
                "<i>Auswertung aller Aufträge …</i>; Kennwert-Vorschläge für die Laserzeit nur nach Freigabe "
                "([[nachkalk_auswertung]]). <b>STEP-Merkmale prüfen …</b>: Status je Merkmal (sicher / prüfen / "
                "nicht erkannt), Rohdaten und Korrekturen ([[step_merkmale]]). <b>Arbeitsgänge vorschlagen …</b> "
                "nach eigenen Regeln, gerechnet erst nach Annehmen ([[arbeitsgaenge]]). <b>Varianten vergleichen …</b> "
                "mit Zielgröße ([[varianten]]). Reiter <b>Fertigung</b>: Freigabe mit festgehaltenem Stand, Status je "
                "Auftrag, Durchlaufzeiten, Export, Materialverbrauch je Charge ([[fertigung]]).",
     "Lager mit optionalen Reststücken, Nachkalkulation-Auswertung, STEP-Merkmale, Arbeitsgänge, Varianten, Fertigung."],
    ["0.9.160", "<b>Gehrung in 2D: lange Seite kürzer</b>: Bei einer Gehrung, die in 2D (90° zur Oberfläche) "
                "geschnitten wird, ist jetzt die Innenkante maßhaltig; die Spitze wird um Wand · tan(Winkel) kürzer "
                "(3 mm bei Wand 3 und 45°), damit innen nichts über die Gehrung ragt. <b>STEP</b>: Gehrungen, die in "
                "der Datei schon 2D geschnitten sind, werden als Gehrung erkannt (nicht mehr komplexes Ende). "
                "Größere Ausschnitte: ein langes Fenster im Rohr lag im Editor bis 6 mm daneben, eine Stufe am "
                "Rundrohr-Ende 1,3 mm; beides liegt jetzt genau wie in der STEP ([[schneidweg_rechner]]).",
     "Gehrung 2D mit maßhaltiger Innenkante, 2D-Gehrungen aus der STEP erkannt, große Ausschnitte genau."],
    ["0.9.159", "<b>Rüsten als Betrag in €</b> (je Angebot bzw. je Abmessung): Aus dem Betrag wird jetzt auch die "
                "<b>Rüstzeit</b> gerechnet, Betrag ÷ Stundensatz (z. B. 30 € bei 90 €/h = 20 min). Sie steht im Reiter "
                "<i>Zeiten & Arbeitskosten</i>, in den Werkstattpapieren und in der Nachkalkulation; der Preis bleibt "
                "genau der eingegebene Betrag ([[angebotskopf]]).",
     "Rüsten in €: Rüstzeit = Betrag ÷ Stundensatz."],
    ["0.9.158", "<b>STEP-Import in den Editor genau wie die STEP</b>: Gehrungen mit einem Schlitz an der Spitze, "
                "Ausklinkungen und andere komplexe Enden lagen im Rohr-Editor als gerades Ende (bis 80 mm daneben), "
                "der Schlitz fehlte. Jetzt stehen alle Enden in Editor, Skizze und 3D wie in der STEP; ein Schlitz, "
                "der ins Ende läuft, ist eine eigene Zeile „Teil von Ende B“ (offen zum Ende, kein eigener Einstich, "
                "Schneidweg unverändert). Schrägschnitt zweiachsig: gemessene Richtung bleibt im Editor, Spitze auf "
                "der gerundeten Ecke ([[schneidweg_rechner]]). Ältere Importe: STEP neu einlesen.",
     "STEP-Import: Gehrungen, Ausklinkungen und Schlitze im Editor genau wie in der STEP."],
    ["0.9.157", "<b>Rohr mit großem Ausschnitt</b>: Ein Rund-, Quadrat- oder Rechteckrohr, das an beiden Enden als "
                "Ring gezeichnet ist und dazwischen fast über die ganze Länge offen (Längsausschnitt, Sattel mit "
                "Schlitz, Kerben am Rand), wird wieder als Rohr erkannt (war <i>offenes Sonderprofil</i>). Der "
                "Ausschnitt ist Innenkontur genau wie in der STEP, die Ringe der Zeichnung bleiben unverändert. Ein "
                "Ausschnitt, der an einen Sattel anschließt, gilt nicht mehr als Fließloch ([[offene_rohre]]).",
     "Rohr mit großem Ausschnitt und geschlossenen Enden wird als Rohr erkannt."],
    ["0.9.156", "<b>Zusatzarbeiten unter der Position</b>: Mit dem Häkchen <b>Zusatzarbeiten unter Position</b> "
                "(Vorgabe an) steht unter jeder Position je Arbeitsschritt eine eingerückte Zeile mit Menge, Preis je "
                "Einheit, Zeit, € je Teil, € der Position und eigen/Fremdleistung, in der Reihenfolge der Werkstatt: "
                "Programmieren, Gewinde, Nachbearbeitung, Montage mit Zukaufteilen, Oberfläche, Prüfung, Verpackung. "
                "Gravur extra und andere Laserzeit-Arbeiten stecken im Laserschneiden und erscheinen nicht. Auch in "
                "der kompakten Kalkulation; Doppelklick öffnet die Zusatzarbeiten ([[zusatz_unterzeilen]]).",
     "Häkchen „Zusatzarbeiten unter Position“: je Arbeitsschritt eine Zeile unter der Position."],
    ["0.9.155", "<b>Schweißnaht und Gravur auch bei Spalt</b>: Liegt zwischen Blech und Rohr (oder zwei anderen Teilen "
                "einer Baugruppe) ein Spalt bis 3 mm (Einstellung), erkennt der STEP-Import die Naht und graviert den "
                "Umriss genau unter das Blech; Vorschläge und Anbauteile tragen das Spaltmaß und sind zum Prüfen "
                "markiert, die Teile werden nie verschoben. Neu: WARNUNG bei Spalt über 2 mm (Einstellung) und für "
                "Teile ohne Naht zu einem anderen Teil. Der Spalt kostet mehr Schweißgut: Nahtgruppen rechnen mit a + Spalt "
                "(gelb bis „a-Maß und Spalt bestätigen“), auch eine im 3D gezeichnete Naht findet das Teil auf der "
                "anderen Seite des Spalts. Rohr durch ein Blech gesteckt: Naht rundum, beidseitig ([[naht_spalt]]). Neu im Reiter Nahtgruppen: "
                "<b>Aus Zeichnung …</b> liest a-Maße (DIN EN ISO 2553) und Stückliste aus PDF, DXF oder Scan "
                "([[zeichnung_baugruppe]]).",
     "Schweißnaht und Gravur auch bei Spalt zwischen Blech und Rohr."],
    ["0.9.154", "<b>Hell- und Dunkelmodus optisch verbessert</b>: Im Dunkelmodus sind Rahmen von Eingabefeldern, "
                "Auswahllisten und Häkchenkästchen wieder sichtbar, Hauptknöpfe kräftig blau mit gut lesbarer weißer "
                "Schrift, die Herkunft der Merkmale im Teile-Editor und die Legende der Kostenbalken nicht mehr dunkel "
                "auf dunkel. Im Stangenbild steht die Positionsnummer auf hellen Teilfarben in dunkler Schrift. Der "
                "Hellmodus hat eine ruhige, einheitlich kühlgraue Fensterfläche ([[einstellungen]]).",
     "Dunkelmodus: sichtbare Rahmen und Häkchen, lesbare Hauptknöpfe; Hellmodus einheitlich kühlgrau; Stangenbild "
     "lesbare Positionsnummern."],
    ["0.9.153", "<b>Angebot aus STEP schneller</b>: Der Prüfdialog zeigt alle Dateien in einer Liste (Pfeile "
                "springen zur Datei), den Hinweis gleich hinter dem Teil und passt auf 1366 px. Oben stehen Kunde und "
                "<b>Anfrage-Nr.</b> (Vorschlag aus dem Ordnernamen). Unter <i>Werte setzen</i> gibt es eine "
                "<b>Zusatzarbeit für alle</b> (z. B. Feuerverzinken), auch fürs Importprofil des Kunden "
                "([[importprofile]]). <b>Bohrungen prüfen</b> öffnet für alle Positionen ein Fenster "
                "([[bohrungen_pruefen]]). <b>Fehler behoben</b>: Zusatzarbeiten für mehrere markierte Positionen "
                "überschrieben Gewinde, Senken und Flowdrill der anderen; jetzt ändert sich nur das Gemeinsame "
                "([[zusatzarbeiten_angebot]]). Die Spalte <b>Gewinde · Zusatzarbeiten</b> steht hinter der "
                "Artikelnummer; bis zum automatischen Optimieren steht „wird berechnet …“ statt eines Preises ohne "
                "Material. <b>Rüsten</b> wahlweise als fester Betrag in € je Angebot bzw. je Abmessung statt Minuten "
                "([[angebotskopf]]).",
     "STEP-Prüfdialog mit allen Dateien, Anfrage-Nr. und Zusatzarbeit für alle; Bohrungen aller Positionen in einem "
     "Fenster; Fehler Zusatzarbeiten bei Mehrfachauswahl behoben; Rüsten wahlweise in €."],
    ["0.9.152", "<b>Preisregeln nach der Prüfung der Preisberechnung</b> (26.10.2026): Zukaufteile und Bleche "
                "bekommen <b>keinen Gewinn</b> mehr, nur ihren Aufschlag; der Gewinn rechnet auf die Selbstkosten "
                "ohne Zukaufteile. Der <b>Mindestpreis</b> gilt für die Ware ohne Fracht nach Abzug des Skontos "
                "([[mindestpreis]]). Der <b>Satzpreis</b> wird aus den ungerundeten Stückpreisen gebildet und ist "
                "damit gleich dem Staffelpreis derselben Menge. Die <b>Mindestmarge</b> misst den Gewinn am "
                "Warenwert. <b>Pauschale je Abmessung</b>: Vorgabe 0 € (Rüsten je Abmessung deckt sie). Rüsten "
                "Maschine wird nach Maschinenzeit, der Stangenwechsel nach Stangenanteil verteilt (Summen gleich). "
                "<b>Zuschnittkosten</b> beim Lieferanten gehen in die Stangenkosten ein. Die <b>Fracht</b> einer "
                "Schweißbaugruppe trägt die Baugruppe als ein Packstück (keine Meldung „Gewicht fehlt“ mehr). "
                "Festgeschriebene Angebote rechnen wie verschickt.",
     "Preisregeln: Zukauf ohne Gewinn, Mindestpreis für die Ware, Satzpreis wie Staffel, Fracht bei Baugruppen."],
    ["0.9.151", "<b>Aufschlag Bleche</b> und <b>Aufschlag Zukaufteile</b> je Angebot (Karte Kalkulation, unter "
                "Zuschlag Fremdleistung): Vorgabe je 10 % aus den Einstellungen, % auf den Einstand aller Bleche bzw. "
                "aller übrigen Zukaufteile des Angebots; ersetzt dort Artikel-, Kategorie- und Standardaufschlag, ein "
                "Positionsaufschlag geht vor. Die Zeilen stehen nur da, wenn das Angebot Bleche bzw. Zukaufteile hat; "
                "ältere Angebote rechnen wie bisher ([[angebotskopf]]).",
     "Aufschlag Bleche und Zukaufteile je Angebot (Vorgabe 10 %)."],
    ["0.9.150", "<b>Stangen von Hand vorgeben</b>: Im Fenster <i>Material …</i> hat jede Abmessung die Spalte "
                "<b>Stangen vorgegeben</b>. Dort lassen sich mehrere Stangenlängen mit Stückzahl eintragen (z. B. "
                "3 × 6.000 + 2 × 4.500 mm). Die Optimierung plant dann nur mit genau diesen Stangen, mit möglichst "
                "wenig Stangenlänge; Teile, die nicht mehr passen, stehen unter <i>nicht eingeplant</i>. Staffelpreise "
                "rechnen ohne Vorgabe ([[stangen_vorgabe]]). Außerdem meldet ein von Hand eingetragener Meterpreis "
                "nichts mehr im Status: der berechnete Preis ist nur Vorgabe ([[meterpreis]]). Das <b>Stangenbild</b> "
                "öffnet jetzt in der <i>Übersicht</i>; bleibt die Maus 1 Sekunde auf einer Stange, zeigt ein kleines "
                "Fenster ihre Detail-Ansicht (Kennzahlen, Teile, Abwicklung), Esc schließt es; die Wartezeit ist unter "
                "Einstellungen › Ansicht einstellbar ([[stangenbild]]).",
     "Stangen von Hand vorgeben; Meterpreis von Hand ohne Meldung; Stangenbild: Übersicht als Standard, Details per "
     "Maus"],
    ["0.9.149", "<b>Konturen: bei 90° zur Oberfläche gilt die Innenkante</b>: Wird eine Kontur senkrecht zur Oberfläche "
                "geschnitten (2D), hat sie innen genau die Maße der Zeichnung bzw. der STEP; der Strahl steht an jedem "
                "Punkt 90° zur Oberfläche, außen ist die Kontur auf dem Rundrohr und in der Rundung der Ecke "
                "(Quadrat-/Rechteckrohr, Kontur nah am Rand) deshalb breiter. 3D-Ansicht, Schnittkörper, Abwicklung, "
                "STEP-Export und Schnittlänge rechnen so. Mit <b>Schnittrichtung parallel (3D)</b> wird daraus die "
                "ebene Bearbeitung: ebene Schnittfläche, außen wie gezeichnet, Ansicht und Schnittlänge stellen sich "
                "beim Umschalten sofort um. Die Schnittrichtung gibt es jetzt auch beim Quadrat- und Rechteckrohr "
                "([[teile_editor]]).",
     "Konturen bei 90° zur Oberfläche: Innenkante maßhaltig, außen breiter; parallel (3D) = ebene Bearbeitung, auch "
     "am Eckradius."],
    ["0.9.148", "<b>Virtuelles Bauteil weiter genutzt</b>: Winkel/U aus größerem Profil und offen gezeichnete Rohre "
                "lassen sich als <b>STEP mit Stegen bzw. Ringen</b> speichern (Rechtsklick oder STEP speichern im "
                "Schneidweg-Rechner, Lage wie die Kundendatei). Je Position wählbar, ob die Stege <b>bleiben</b> "
                "(Vorgabe) oder <b>abgetrennt</b> werden (Zusatzarbeit „Stege abtrennen“ €/Stück). Zeichnung und "
                "Werkstattpapiere zeigen die Stege rot mit Hinweis; das <b>Gewicht</b> je Teil kommt aus dem "
                "gemessenen Volumen statt aus dem Metergewicht des größeren Profils ([[offene_rohre]]). Behoben: ein "
                "virtueller Winkel/U lag in Satz und Baugruppe um einige Millimeter verschoben, jetzt exakt wie in "
                "der STEP. "
                "Auch STEP speichern im Fenster <b>Satz in 3D</b> und im Editor der "
                "Schweißbaugruppe schreibt Winkel/U aus größerem Profil und offen gezeichnete Rohre als exakten "
                "Körper mit Stegen bzw. Ringen 2 mm (abgetrennt: wie gezeichnet) ([[step_baugruppe]]). Neue Prüfregel "
                "<b>Virtuelles Bauteil prüfen</b> warnt, wenn das gemessene Mehrvolumen der Stege nicht zum Profil "
                "passt ([[pruefregeln]]). Zusatzarbeiten in €/kg rechnen mit dem Gewicht aus dem Volumen, in €/m² "
                "mit der anteiligen Fläche. Die Stecknasen sind gegen das 3D-Modell nachgemessen: der Schneidweg "
                "stimmt auf 0,1 mm.",
     "Virtuelles Bauteil: STEP-Export (auch im Satz), Stege bleiben/abtrennen, Zeichnung, Gewicht, Prüfregel"],
    ["0.9.147", "<b>Online-Update im Firmennetz robuster</b>: Bricht der Download ab (Firewall, Proxy, "
                "Virenscanner), versucht das Programm es selbst bis zu sechsmal und macht an der Abbruchstelle "
                "weiter; ein späterer Versuch setzt das schon Geladene fort. Die Meldung nennt die wahrscheinliche "
                "Ursache (Sperrseite eines Proxys, HTTP 403, fremdes Zertifikat, fehlende Schreibrechte der portablen "
                "Version), jeder Versuch steht mit Proxy-Angabe im Protokoll ([[updates]]). <b>Neue Kopie findet die "
                "alten Daten</b>: Startet eine neu entpackte oder neu installierte Version ohne Daten, zeigt sie die "
                "zuletzt benutzten Daten (frühere portable Kopie oder installierte Version) an und übernimmt sie mit "
                "einem Klick samt Lizenz und Angebots-Ablage ([[datensicherung]]).",
     "Update: Download setzt nach Abbruch fort; neue Kopie übernimmt die alten Daten per Klick"],
    ["0.9.146", "<b>Teile im 3D anklicken</b>: Im Fenster Satz in 3D und im Editor der Schweißbaugruppe (Reiter "
                "Strukturbaum und 3D) wählt ein Klick auf ein Teil es aus, auch nahe an einer Kante; Strg+Klick nimmt "
                "weitere dazu oder weg. Liste und Baum gehen mit. Im Editor der Schweißbaugruppe stehen unter dem 3D "
                "<b>Knickrahmen erstellen …</b> und <b>Steckverbindung hinzufügen</b> für die gewählten Rohre "
                "([[baugruppe_baum]]). Beim Stecksystem zeigt eine Zeile im Reiter Steckverbindungen Aufnahme und "
                "Stecker blau im 3D, ein Klick auf ein Rohr markiert seine Verbindungen ([[satz_3d]]). "
                "<b>Doppelklick</b> wählt die ganze Gehrungskette, <b>Rechtsklick</b> öffnet ein Menü (Knickrahmen "
                "erstellen/lösen, Steckverbindung hinzufügen/tauschen/entfernen, Nur Gewähltes). Der "
                "<b>Rahmen-Assistent</b> zeigt den Rahmen im 3D und hat die Ecke <i>Knickrahmen</i>: der Rahmen wird "
                "gleich ein geknicktes Rohr ([[rahmen_assistent]]). Ein Klick in ein Feld einer Tabelle markiert "
                "jetzt auch die Zeile.",
     "Knickrahmen und Stecksystem: Teile im 3D per Klick, Doppelklick und Rechtsklick wählen; Rahmen-Assistent mit 3D"],
    ["0.9.145", "<b>STEP mit mehreren Teilen nicht mehr automatisch als Satz</b>: Im Dialog STEP-Import prüfen wird "
                "eine Baugruppe jetzt als Einzelpositionen übernommen. Das Feld <i>Anzahl</i> oben erhöht nur die "
                "Stückzahl aller Teile der Datei. Ein Satz entsteht nur mit dem Knopf <b>Als Satz</b>; dann zählt "
                "<i>Anzahl</i> als Anzahl Sätze und die Spalte zeigt Stück je Satz ([[step]]).",
     "STEP mit mehreren Teilen: Einzelpositionen, Anzahl erhöht Stückzahl, Satz nur mit Knopf „Als Satz“"],
    ["0.9.144", "<b>Winkel aus größerem Profil als virtuelles Bauteil</b>: Wird für einen Winkel oder ein U ein "
                "größeres Profil gleicher Form gewählt (z. B. L 33×30×6 aus L 60×40×6), misst das Programm jetzt das "
                "Teil plus je einen Steg 2 mm des größeren Profils an den Enden wie ein echtes Bauteil. Enden, "
                "Längsschnitte und Querschnitte stimmen damit genau, auch bei Gehrungen und Ausklinkungen am "
                "gekürzten Schenkel; im 3D sind die Stege rot. Gilt im Prüfdialog und beim Profilwechsel in der "
                "Positionstabelle ([[offene_rohre]]). Außerdem wartet das automatische Optimieren, solange Sie eine Zelle "
                "bearbeiten, damit die Eingabe nicht unterbrochen wird.",
     "Winkel/U aus größerem Profil: Teil mit Stegen 2 mm als virtuelles Bauteil gemessen"],
    ["0.9.143", "<b>Staffeln nie automatisch rechnen</b>: Staffelpreise werden nur noch mit dem Knopf "
                "<b>Staffelpreise rechnen</b> (Reiter Staffeln) gerechnet, nicht mehr im Hintergrund nach Änderungen "
                "und nicht vor dem Angebots-PDF. Veraltete Stufen haben keinen Preis und fehlen im Angebot; der "
                "Angebots-Check warnt davor. Das Angebots-PDF legt auch keine Standard-Staffeln mehr an, das macht "
                "nur der Knopf <b>Standard-Staffeln</b> ([[staffeln]]).",
     "Staffeln: nur noch auf Knopfdruck rechnen, nie automatisch"],
    ["0.9.142", "<b>STEP-Import: vier Fehler behoben</b>: Ein geschlossenes Rohr mit vielen Langlöchern (z. B. QR "
                "40x40x2) wurde als Kantteil erkannt; jetzt ist ein geschlossenes Rohr immer ein Rohr, alle Schnitte "
                "werden übernommen ([[bleche]]). Im Rohr-Editor fehlte der Umriss komplexer Enden (Ausklinkung wurde "
                "gerade gezeigt) und der Eckradius aus der STEP (Konturen lagen bei anderem Radius bis über 1 mm "
                "daneben); beides bleibt jetzt erhalten. Haben verschiedene Teile denselben Bauteilnamen, wurde beim "
                "Übernehmen nur eines übernommen; jetzt bekommt jedes weitere Teil die Nummer mit -2, -3 … "
                "([[importprofile]]).",
     "STEP-Import: Rohr nie Kantteil, Ausklinkung und Radius im Editor wie STEP, alle Positionen übernommen."],
    ["0.9.141", "<b>Schnittschema je Staffel</b>: Im Reiter <i>Staffeln</i> zeigt das Ergebnis je Stufe und "
                "Abmessung die Stangen (Anzahl × Lieferlänge, Ausnutzung) und ihre Kosten inkl. Verschnitt. Der neue "
                "Knopf <b>Schnittschema …</b> (oder Doppelklick) öffnet den Schnittplan der Stufe mit Stangen, Meter, "
                "Verschnitt, €/m und Materialkosten je Abmessung und dem Stangenbild. So ist der Materialpreis jeder "
                "Staffel nachvollziehbar. Gespeicherte Staffelpreise werden dafür einmal neu gerechnet ([[staffeln]]).",
     "Staffeln: Schnittschema je Stufe mit Stangen, Verschnitt und Materialkosten"],
    ["0.9.140", "<b>Rohrteil aus einer PDF-Zeichnung (Test)</b>: Mit der Einstellung <i>Testfunktion "
                "PDF-Zeichnungen</i> bietet <i>Neue Position</i> den Typ <i>Aus PDF-Zeichnung (Test)</i>. Profil, Länge, "
                "Werkstoff, Benennung, Artikel und Stückzahl kommen aus dem Text der Zeichnung (auch Scan oder Foto), "
                "der Rohr-Editor öffnet damit. Ist das PDF direkt aus dem CAD gespeichert, liest das Programm auch die "
                "Linien wie bei einer DXF: Enden, Bohrungen und Ausschnitte kommen mit. Englische Schriftfelder werden "
                "gelesen; fehlt das Profil im Text, kommt es aus den Maßen am Querschnitt und die Wandstärke wird aus "
                "den passenden Profilen gewählt ([[pdf_zeichnung]]).",
     "Testfunktion: Rohrteil aus einer PDF-Zeichnung, auch mit Enden und Konturen aus den Linien."],
    ["0.9.139", "<b>Blech-Editor: Konturen im 3D aus dem Material geschnitten</b>: Bohrungen, Senkungen, "
                "Langlöcher, Rechtecke und Polygone sind in der 3D-Ansicht echte Löcher mit Lochwand durch die "
                "Blechdicke, auch im gekanteten Teil und in der Biegung; bisher waren sie nur rote Linien auf der "
                "geschlossenen Fläche. Gravuren und Konturen, die über den Rand reichen oder sich überschneiden, "
                "bleiben Linien ([[blech_editor]]).",
     "Blech-Editor: Konturen im 3D als echte Löcher"],
    ["0.9.138", "<b>Schweißbaugruppen-Editor schneller</b>: Der Reiter <i>Strukturbaum und 3D</i> rechnete die "
                "Schweißnaht-Raupen bei jedem Klick im Baum neu und beim Öffnen doppelt; das Programm stand dabei je "
                "Klick mehrere Sekunden. Jetzt werden die Raupen einmal gerechnet und gemerkt, auch für das nächste "
                "Öffnen derselben Baugruppe, und die Suche der Flächen an der Naht prüft nur noch Dreiecke in der Nähe. "
                "Bei einem Satz mit 15 Teilen dauern sechs Klicks im Baum 5 s statt 33 s, der 3D-Reiter öffnet beim "
                "zweiten Mal in 2 s statt 9 s. Das Bild bleibt genau gleich ([[baugruppe_baum]]).",
     "Schweißbaugruppen-Editor: 3D und Klicks im Strukturbaum viel schneller"],
    ["0.9.137", "<b>Winkel aus größerem Profil: Stege 2 mm jetzt auch beim Profilwechsel</b>: Wird ein Winkel, U oder C "
                "auf ein größeres Profil gleicher Form gestellt (z. B. L 33×30×6 → L 60×40×6), rechnet das Programm die "
                "Längsschnitte zwischen den Stegen 2 mm an den Enden jetzt auch, wenn das Profil erst nach dem "
                "Übernehmen in der Positionstabelle oder im Rohr-Editor geändert wird. Fehlt das größere Profil in den "
                "Stammdaten, wird es mit den Maßen aus dem Namen angelegt statt mit den gemessenen "
                "([[offene_rohre]]).",
     "Winkel/U/C auf größeres Profil gestellt: Stege 2 mm auch nach dem Übernehmen, Profil mit Maßen aus dem Namen"],
    ["0.9.136", "<b>Scans und Fotos als Anfrageformular</b>: Gescannte PDFs, Faxe und Handyfotos (JPG, PNG, TIFF) "
                "liest die mitgelieferte Texterkennung Tesseract (Deutsch/Englisch) schon im Hintergrund, die Liste "
                "zeigt <i>liest Formular …</i>. Anfragenummer, Kunde und Stückzahlen wie beim PDF mit Text; leicht "
                "verwechselbare Zeichen (0/O, 4/A …) gleichen sich aus, unsichere Mengen sind gelb ([[anfragen]]).",
     "Scans, Faxe und Fotos als Anfrageformular (Texterkennung Tesseract)."],
    ["0.9.135", "<b>Große STEP-Dateien viel schneller eingelesen</b>: Ab 20 MB lässt der STEP-Import beim Einlesen zwei "
                "Prüfungen auf sich kreuzende Kanten weg, die mit der Zahl der Bohrungen quadratisch wachsen. Ein Rundrohr "
                "mit 7.000 Bohrungen wird so in etwa 13 min statt über 80 min eingelesen; "
                "Volumen und Messwerte bleiben gleich (geprüft mit 1.000 und 3.000 Bohrungen). Kleinere Dateien werden "
                "unverändert eingelesen ([[step]]).",
     "Große STEP-Dateien (ab 20 MB) viel schneller eingelesen, gleiche Messwerte"],
    ["0.9.134", "<b>Anfrageformular lesen</b>: Liegt bei einer neuen Anfrage ein PDF mit Text, liest das Programm "
                "die <b>Anfragenummer</b> (kommt in <i>Ihre Anfrage / Zeichen</i>, Unterordner heißt "
                "<i>Kunde – Anfragenummer</i>), den <b>Kunden</b> aus der Kundenliste und die <b>Stückzahlen</b> je "
                "Artikelnummer bzw. STEP-Dateiname. Unsicher erkannte Mengen sind im Prüfdialog gelb ([[anfragen]]).",
     "Anfrageformular (PDF mit Text): Anfragenummer, Kunde und Stückzahlen werden übernommen."],
    ["0.9.133", "<b>Neue Anfragen aus dem Anfrage-Ordner</b>: STEP-Dateien und Anfrageformulare in einen Ordner "
                "legen (Einstellungen → Ablage → <i>Anfrage-Ordner</i>); die Startseite zeigt sie unter <b>Neue "
                "Anfragen</b>. Ein Unterordner ist eine Anfrage, lose Dateien mit weniger als 10 Minuten Abstand "
                "auch. Öffnen macht daraus ein Angebot aus STEP und verschiebt die Dateien danach in den "
                "Angebotsordner; mehrere Anfragen eines Kunden lassen sich zusammen öffnen, Kollegen sehen <i>in "
                "Bearbeitung</i> ([[anfragen]]).",
     "Neue Anfragen aus dem Anfrage-Ordner auf der Startseite, Öffnen als Angebot, Dateien in den Angebotsordner"],
    ["0.9.132", "<b>Design-Prüfung</b>: Die Fußzeile der PDFs wird bei langen Firmendaten kleiner bzw. zweizeilig und "
                "läuft nicht mehr in „Seite x von y“. In den Werkstattpapieren steht die Spalte <i>Lage</i> mittig "
                "und breiter. Die <b>Übersicht</b> rechts wird so breit wie ihr Inhalt und schneidet keine Beträge "
                "mehr ab; die <b>Staffelkurve</b> zeigt die Preise auf hellem Grund neben der Linie und den größten "
                "Preis an der Achse. Der <b>Angebots-Check</b> warnt, wenn ein Staffelpreis dem Angebotspreis "
                "widerspricht ([[angebots_check]]).",
     "Design-Prüfung: PDF-Fußzeile, Spalte Lage, Übersicht nicht abgeschnitten, Staffelkurve, Check Staffel gegen Angebotspreis"],
    ["0.9.131", "<b>Angebotskopf und Kalkulation kompakter</b>: Bearbeiter neben der Bemerkung, der Satz „Im Angebot: "
                "Lieferzeit …“ nur noch ohne Lieferzeit (sonst als Tooltip); die Fracht steht auf breiten Bildschirmen "
                "rechts neben der Kalkulation, der Haken Mindestauftragswert unter Verkauf und Gewinn. <i>Rüstzeit je "
                "Maschine</i> fällt bei 0 min weg, <b>Stangenwechsel je Stange</b> ist je Angebot änderbar (gelb bei "
                "Abweichung, Stangenwechsel SN bleibt) ([[angebotskopf]]). Das Ablagefeld neben <i>Neue "
                "Position</i> nimmt <b>STEP und DXF</b> per Ziehen oder Klick an, auch gemischt; <i>STEP importieren "
                "…</i> steht nur noch im Menü (Strg+I) ([[step]]).",
     "Kopf und Kalkulation kompakter, Stangenwechsel je Angebot, Ablagefeld für STEP und DXF."],
    ["0.9.130", "<b>Fehlersuche</b>: Die <b>Schnellzeile</b> liest Profilmaße mit Leerzeichen (<i>RR 42,4 x 2</i>, "
                "<i>QR 40 x 40 x 3</i>) und <i>1250 x 20</i> als Länge × Stück; ein mehrdeutiger Werkstoff (<i>S235</i>) "
                "nimmt den der letzten Position, die Vorgabe bzw. den zuletzt benutzten, sonst Hinweis "
                "<i>mehrdeutig</i> ([[schnellzeile]]). Halbschalen (Teile je Rohrumfang): Meterpreise und Fenster "
                "Abmessung zählen die Teilemeter nach Rohrstücken. Der <b>Notfallcode</b> gilt nach dem spätesten "
                "gesehenen Datum, eine zurückgestellte Uhr macht einen alten Code nicht wieder gültig "
                "([[lizenz_laden]]). Vollmaterial aus STEP: Hinweis <i>Bohrungen/Gewinde nicht ausgewertet, bitte "
                "prüfen</i> ([[vollmaterial]]).",
     "Fehlersuche: Schnellzeile (Leerzeichen, Länge × Stück, S235), Halbschalen-Meter, Notfallcode, Vollmaterial-Hinweis"],
    ["0.9.129", "<b>Schnittkörper im 3D</b>: Jede Kontur ist zusätzlich ein halb durchsichtiger Körper, so tief wie "
                "sie schneidet – eine Wand, beide Wände (durchgehend bis unter die Gegenwand), je Kopie bei allen "
                "Seiten, eine schräge Bohrung entlang ihrer Neigung, eine Gravur so tief wie angegeben, beim Blech "
                "durch die Dicke. Farbe je Konturart, die Maus darüber zeigt Kontur und Tiefe, die gewählte Kontur ist "
                "kräftiger, ein Klick ins Loch wählt sie. Vorgabe an, abschaltbar mit <b>Schnittkörper</b> (Leiste "
                "unter dem 3D, Blick-Menü, Rechtsklick → Darstellung); gilt für Rohr- und Blech-Editor, "
                "Schweißbaugruppe und Satz in 3D ([[ansicht_3d_bedienung]]). Unbekannte Konturen (Sonderkontur) "
                "sind pink und haben die Form aus der importierten STEP-Datei, V-Ausschnitte der Knickrahmen braun; "
                "die Körper stehen außen und innen je 2 mm über. <b>Konturen genau wie die STEP</b>: Konturen über "
                "gerundete Ecken und Bohrungen auf den Seiten vorne/unten/hinten lagen bis zu einigen mm neben der "
                "STEP, jetzt auf Hundertstel genau; der Eckradius kommt aus der STEP-Datei, komplexe Enden haben im 3D "
                "ihren gemessenen Verlauf, Rundrohre stehen im 3D wie die STEP. Schon importierte Teile mit <b>STEP "
                "neu einlesen …</b> korrigieren.",
     "Schnittkörper im 3D; Konturen und Enden aus der STEP auf Hundertstel genau"],
    ["0.9.128", "<b>Eingaben intuitiver</b>: Ja/Nein-Einstellungen sind Schalter, Ja/Nein-Spalten der Tabellen "
                "Häkchen in der Zelle (ein Klick, Leertaste, J/N). Wenige Möglichkeiten (Thema, Dichte, "
                "Eingaberichtung …) stehen als Knopfreihe da; feste Auswahllisten der Einstellungen nehmen keine "
                "Tippfehler mehr an. In allen Zahlenfeldern und Zahlenspalten darf man rechnen (<i>6000/4</i>), der "
                "alte Wert ist beim Hineinklicken markiert, eine unfertige Rechnung rot umrandet ([[eingaben]]). "
                "Fenster passen auf den Bildschirm (auch gemerkte Größen am Laptop), das offene Fenster bleibt vor dem "
                "Hauptfenster ([[fenster_merken]]).",
     "Schalter, Knopfreihen, Rechnen im Feld, Fenster passen und bleiben vorne"],
    ["0.9.127", "<b>Abwicklung als Fenster</b>: Rohr- und Blech-Editor haben oben rechts im Menüband den Knopf "
                "<b>Abwicklung</b>; er zeigt die Abwicklung groß in einem eigenen Fenster, das jeder Eingabe folgt. "
                "<b>Esc</b> schließt nur dieses Fenster, der Editor bleibt offen ([[teile_editor]]). Fehler behoben: "
                "<b>Enter</b> nach einer Eingabe schloss den Editor (auch Baugruppe und Satz in 3D); jetzt bestätigt "
                "Enter nur die Eingabe.",
     "Abwicklung im eigenen Fenster (Esc schließt nur das Fenster); Enter schließt den Editor nicht mehr"],
    ["0.9.126", "<b>3D drehen um den Mauszeiger</b>: In allen 3D-Ansichten (Teile-Editor Rohr und Blech, "
                "Schweißbaugruppe, Satz in 3D, STEP-Prüfdialog, 3D-Ansicht der Positionen) dreht die linke Maustaste "
                "jetzt um den Punkt des Modells unter dem Mauszeiger; ein kleiner Kreis zeigt ihn beim Drehen. Neben "
                "dem Modell gedrückt, dreht die Ansicht wie bisher um die Modellmitte. Das Mausrad zoomt zur "
                "Mausposition ([[step_3d_ansicht]]).",
     "3D: Drehpunkt unter dem Mauszeiger, Zoom zur Mausposition"],
    ["0.9.125", "<b>STEP-Baugruppe: Teile genau an ihrer Stelle</b>: Beim STEP speichern einer Baugruppe oder eines "
                "Satzes lagen quadratische Bleche verdreht und versetzt, Flachstahl als Blech teils 40 mm daneben. Das "
                "Ausrichten am 3D-Netz der STEP-Messung prüft jetzt die Achsen der Einbaulage, der Datei und der Kanten, "
                "rechnet mit dem genauen Flächenschwerpunkt und führt nach; Umlaute in den Teilenamen stimmen "
                "([[step_baugruppe]]). <b>Nasen nie in die Außenwand</b>: <i>Alle Stöße stecken</i> prüft jede Nase "
                "auf der Wand der Aufnahme; passt sie nicht, werden die Nasen um 90° gedreht oder es bleibt eine Nase, "
                "an Ecken je Träger eine Nase, um 90° versetzt; Lage x = Mitte des Steckers. Gleiche Teile, die andere "
                "Nasen oder Schlitze brauchen, werden in eigene Positionen geteilt; nur gedreht eingebaute gleiche "
                "Rohre bleiben eine Position ([[steckverbindung]]).",
     "STEP-Baugruppe: Bleche genau an ihrer Stelle; Stecknasen nie in die Außenwand, Ecken je Träger eine Nase."],
    ["0.9.124", "<b>DXF-Import Rohr mit Patricks Bauteil 1 verbessert</b>: Die Striche des Schnittverlaufs (A–A) "
                "machten die Draufsicht zu lang; deshalb wurde die Vorderansicht verworfen und die Gehrung als "
                "Ausklinkung gelesen, Bohrungen lagen 12 mm daneben. Jetzt: Gehrung 30° richtig, Fenster mit Eckradius, "
                "Ø 50 durch beide Wände an der richtigen Stelle, schräge Bohrung als Bohrung mit Neigung "
                "([[dxf_rohr]]).",
     "DXF-Import Rohr: Schnittverlauf, Gehrung, schräge Bohrung"],
    ["0.9.123", "<b>Performance-Update</b> (Belastungstest Rundrohr 84 × 2 mit 200, 1.000 und 7.000 Bohrungen): Das "
                "3D-Modell aus den Eingaben rechnet bei vielen Bohrungen ein Mehrfaches schneller und wird gemerkt "
                "(1.000 Bohrungen: 24 s → 5 s); der Rohr-Editor öffnet dreimal so schnell, eine Änderung braucht keine "
                "18 s mehr für die Ergebnistabelle. Satz in 3D und Baugruppe: ein Klick rechnet die Teile nicht neu. "
                "<b>STEP speichern</b> zieht nicht überlappende Bohrungen in einem Durchgang ab (1.000 Bohrungen: über "
                "5 min → 20 s), zeigt bei langen Exporten Dauer und Abbrechen, das Zeitlimit wächst mit den Bohrungen "
                "([[step_export]]). Positionsliste, Vorschaubilder, Werkstattpapiere und Stangenbild schneller; "
                "Staffeln und Nachkalkulation füllen sich erst beim Öffnen des Reiters. Behoben: Angebots-PDF mit "
                "einem Satz, der nicht auf eine Seite passt (Fehler beim Erzeugen); der Satz bricht jetzt um, die "
                "Spaltenköpfe stehen auf jeder Seite. Neu: <b>Systemvoraussetzungen</b> in der Anleitung und "
                "<b>Hilfe → Systemprüfung …</b>, einmal nach Installation bzw. Update mit Hinweis, wenn der Rechner "
                "unter dem Minimum liegt ([[systemvoraussetzungen]]). Alle Preise, Zeiten und Messwerte bleiben gleich.",
     "Performance-Update: 3D, Rohr-Editor, STEP speichern viel schneller; Systemvoraussetzungen und Systemprüfung"],
    ["0.9.122", "<b>Abwicklung mit ausgeschnittenen Konturen</b>: In der Abwicklung der Skizze (Schneidweg-Rechner, "
                "Teile-Editor, Zeichnung) sind Bohrungen, Rechtecke, Langlöcher und andere Konturen jetzt als Loch im "
                "Material zu sehen; das Material ist etwas kräftiger hinterlegt, Gravuren bleiben Linien. Eine "
                "Text-Gravur steht in Skizze und Abwicklung als echte Schrift statt als Rechteck. Im Blech-Editor sind "
                "die Konturen ebenso ausgeschnitten "
                "([[schneidweg_rechner]]).",
     "Abwicklung: Konturen als ausgeschnitten dargestellt"],
    ["0.9.121", "<b>Vollmaterial als Zukaufartikel</b>: neue Artikeltypen <b>Rundstahl</b> und <b>Vierkantstahl</b> "
                "(Ø bzw. Kante, Länge, Werkstoff); Gewicht aus der Dichte, EK je Stück = Gewicht × Preis je kg "
                "(Vorgabe Tonnenpreis des Werkstoffs), Kategorie <i>Vollmaterial</i> ([[vollmaterial]]). Der "
                "STEP-Import übernimmt Rund- und Vierkantstahl als Zukaufteil-Positionen (Gruppe <i>Vollmaterial</i> im "
                "Prüfdialog, [[bleche]]), von Hand über <b>Neue Position → Zukaufteil</b> mit Art Rundstahl bzw. "
                "Vierkantstahl. Gesägt wird über die neue Zusatzarbeit <b>Sägen</b> (€ je Schnitt); Zusatzarbeiten an "
                "Zukaufteil-Positionen werden jetzt mitgerechnet ([[zukauf_positionen]]).",
     "Rund- und Vierkantstahl als Zukaufartikel (EK aus €/kg, STEP-Import, Zusatzarbeit Sägen)."],
    ["0.9.120", "<b>Admin-Passwort in der Admin-Lizenz</b>: Das Lizenz-Werkzeug fragt beim Ausstellen einer Admin-Lizenz "
                "das Admin-Passwort ab (mindestens 10 Zeichen) und legt es verschlüsselt in die signierte Lizenz; nur "
                "dieses gilt dann beim Start. Ändern = Admin-Lizenz neu ausstellen (Verlängern …); nach dem Laden nimmt der "
                "Rechner die alte Admin-Lizenz nicht mehr an. Ältere Admin-Lizenzen "
                "ohne Passwort nutzen weiter das Passwort der Einstellungen. Das Passwort der Einstellungen lässt sich "
                "nur noch mit Admin-Rechten setzen, ändern oder entfernen. Passwort vergessen: Notfallcode aus dem "
                "Lizenz-Werkzeug für die Rechner-ID, gilt heute und morgen ([[lizenz_laden]]).",
     "Admin-Passwort in der Admin-Lizenz, Einstellungs-Passwort nur mit Admin-Rechten, Notfallcode"],
    ["0.9.119", "<b>Größte Nasenbreite der Steckverbindung</b>: Die Nase bleibt auf der geraden Wandfläche des "
                "Steckers (Wandbreite − 2 × Eckradius) mit einem Rand je Seite (neue Einstellung, Vorgabe 2 mm); ein "
                "breiterer Wert wird automatisch gekürzt und im Text der Verbindung genannt ([[steckverbindung]]).",
     "Steckverbindung: Nase höchstens gerade Wandfläche − 2 × Rand"],
    ["0.9.118", "<b>Gravur der Anbauteile im 3D und im STEP</b>: Das 3D aus den Eingaben (Rohr-Editor, 3D der "
                "Position) zeigt die Gravur aufgeschweißter Bolzen, Laschen und Bleche an ihrer Stelle, wie sie unter "
                "Anbauteile prüfen gewählt ist. STEP speichern schneidet sie als Rille 0,1 mm ins Rohr. Gilt für Teile, "
                "die ab dieser Version eingelesen werden ([[anbauteile]]).",
     "Gravur der Anbauteile im 3D aus den Eingaben und als Rille im STEP"],
    ["0.9.117", "<b>Offen gezeichnete Rohre aus dem Rohr</b>: Ein Quadrat- oder Rechteckrohr, das der Kunde als "
                "gekantetes Blech mit einer offenen Seite gezeichnet hat (U offen, C mit Schlitz, U mit Lasche), und "
                "Halbschalen eines Rundrohrs erkennt der STEP-Import und rechnet sie aus dem geschlossenen Rohr: an "
                "Ende A und B bleibt je ein Ring 2 mm des ganzen Rohrs stehen (Radius aus der STEP, an allen Ecken "
                "gleich), dazwischen wird die offene Seite als Fenster ausgeschnitten. Rohrgröße = nächstgrößeres "
                "Normrohr, die Datei bleibt unverändert. Nichts fällt weg: ragen scharfe Schenkelenden über die "
                "Rohrecken, wird das nächstgrößere Rohr genommen, bei dem der Radius erst danach beginnt. Halbschalen: "
                "passen mehrere in einen Umfang (5 mm Luft), werden sie einzeln freigeschnitten, Rohrstücke = Stück ÷ "
                "je Umfang (neues Feld Teile je Rohrumfang). Ein anderes Rohr in der Profil-ID rechnet Enden und "
                "Fenster um; ein Winkel, U oder C aus einem größeren Profil gleicher Form (z. B. L 33×30×6 aus L "
                "60×40×6) bekommt gekürzte Schenkel mit Stegen 2 mm an den Enden, aus einem Rohr Ringe und Fenster. Immer Rohr; ohne Normmaß oder über der Maschinengrenze automatisch Kantteil, Kantteil und "
                "U/C immer zur Auswahl. Die Ringe sind im 3D rot und laufen wie die Nachbarwände (auch Gehrungen). Ein "
                "Spalt bis 2 mm wird ganz geschlossen ([[offene_rohre]]).",
     "Offen gezeichnete Rohre und Halbschalen im STEP: aus dem Rohr mit Ringen 2 mm an den Enden"],
    ["0.9.116", "<b>Bedienung schneller</b>: Neues Angebot aus STEP in einem Fenster: Kunde oben im Prüfdialog, "
                "fehlende Profile und doppelte Artikel als Häkchen statt Rückfragen, Knopf <b>Übernehmen und Angebot "
                "(PDF)</b> ([[angebot_aus_step]]). Hinweise als Einblendung ohne OK-Klick, Löschen im Angebot ohne "
                "Rückfrage mit <b>Rückgängig</b> in der Einblendung, Bericht im Meldungsverlauf ([[meldungen]]). "
                "Rechtsklick zeigt nur die passenden Einträge, <b>Für markierte setzen …</b> ändert Werkstoff und "
                "Oberfläche mehrerer Positionen ([[rechtsklick]]). <b>◀ Vorige / Nächste ▶</b> in Schneidweg-Rechner, "
                "Blech-Editor und Baugruppe ([[blaettern]]). Fenstergröße und Teiler gemerkt, offene Angebote nach "
                "dem Neustart wieder offen, zuletzt benutzte Profile und Werkstoffe oben in den Listen "
                "([[fenster_merken]]). <b>Schnellzeile</b> über der Positionsliste: „QR 40x3 S235 1250 20“ + Eingabe "
                "legt die Position an, auch mehrere Zeilen aus E-Mail oder Excel ([[schnellzeile]]). Der "
                "Prüfdialog <b>lernt</b>: Korrekturen per Häkchen ins Importprofil des Kunden ([[importprofile]]).",
     "STEP-Anfrage in einem Fenster, Rückgängig statt Rückfragen, Blättern, Schnellzeile, Prüfdialog lernt"],
    ["0.9.115", "<b>Rahmen-Assistent</b>: Neue Position → Rahmen-Assistent legt einen Rechteckrahmen oder Quader aus "
                "Quadrat-, Rechteck- oder Rundrohr ohne STEP-Datei an. Aus Außenmaß, Profil und Ecken (Gehrung, stumpf, "
                "stumpf mit Steckverbindungen) entstehen die Rohre als Positionen eines Satzes mit Einbaulage und Stößen, "
                "so dass Satz in 3D, Vorschläge, Steckverbindungen und Montagefolge wie bei einer STEP-Datei arbeiten "
                "([[rahmen_assistent]]).",
     "Rahmen-Assistent: Rechteckrahmen und Quader aus Rohr ohne STEP"],
    ["0.9.114", "<b>Montagefolge und Montageblatt</b>: Knopf Montage über dem 3D (Schweißbaugruppe, Satz in 3D) baut "
                "die gesteckten Teile Schritt für Schritt auf, mit Text je Schritt (Teil, Marke, Steckrichtung), und "
                "zieht sie als Explosionsansicht auseinander. Die Werkstattpapiere haben je Baugruppe bzw. Satz mit "
                "Steckverbindungen ein Montageblatt mit Skizze und Schritten zum Abhaken ([[montagefolge]]).",
     "Montagefolge im 3D mit Explosion, Montageblatt in den Werkstattpapieren"],
    ["0.9.113", "<b>Montagemarken und Steckbarkeit</b>: Steckverbindungen bekommen auf Wunsch eine Zahl, die neben "
                "die Schlitze der Aufnahme und auf das Ende des Steckers graviert wird (Knopf Marken nummerieren, "
                "Einstellung für neue Verbindungen, Vorgabe aus). Steckbarkeit prüfen sucht eine Reihenfolge, in der "
                "sich alle Teile stecken lassen, und meldet Schlitze über Konturen und feste Längsnähte auf Schlitzen "
                "oder Nasen ([[montagemarken]]).",
     "Montagemarken an Schlitz und Nase, Steckbarkeit prüfen"],
    ["0.9.112", "<b>DXF-Import für verschiedene Zeichnungen</b>: Rohrzeichnungen nach USA (Drittwinkel), senkrecht "
                "gezeichnete Rohre, Blattrahmen, mehrere Teile auf einem Blatt und Profiltexte wie Ø42,4x2 werden "
                "erkannt. Ist das Programm unsicher, zeigt ein Zuordnungsfenster die Ansichten zum Zuordnen; die "
                "Projektion merkt es sich je Zeichnungsstil ([[dxf_rohr]]). Außerdem bleibt eine Gravur über einer Biegung "
                "im STEP des Kantteils erhalten.",
     "DXF-Import robust: USA-Projektion, gedreht, mehrere Teile, Zuordnungsfenster"],
    ["0.9.111", "<b>Vorschläge mit Ersparnis</b>: Im Fenster Satz in 3D und im Editor der Schweißbaugruppe findet "
                "das Programm Knickrahmen, Steckverbindungen aus den Stößen der STEP-Datei und eine günstige Lage der "
                "Längsnaht (frei von Konturen, Schlitzen und Nasen, bevorzugt innen) selbst. Je Vorschlag steht, was "
                "er spart oder kostet (Ecknähte, Positionieren, Knicken, Laserzeit), nur aus vorhandenen Werten; "
                "anhaken und übernehmen ([[vorschlaege]]). Nahtgruppen aus den STEP-Vorschlägen verlieren die Ecken "
                "eines neuen Knickrahmens.",
     "Vorschläge Knickrahmen, Steckverbindung, Längsnaht mit Ersparnis"],
    ["0.9.110", "<b>Baugruppe und Satz als STEP</b>: STEP speichern im Editor der Schweißbaugruppe und im Fenster "
                "Satz in 3D schreibt alle Teile als STEP-Baugruppe mit echten Volumenkörpern in der Einbaulage, "
                "gleiche Teile einmal definiert, Unterbaugruppen wie im Strukturbaum. Rohre mit Schlitzen und Nasen, "
                "Bleche eben oder gekantet ([[step_baugruppe]]).",
     "Baugruppe und Satz als STEP-Baugruppe speichern"],
    ["0.9.109", "<b>Gekantete Bleche als STEP</b>: STEP speichern im Blech-Editor schreibt jetzt auch Kantteile und "
                "mehrachsig gekantete Bleche aus dem STEP-Import (Schale, Kasten) als echten Volumenkörper. "
                "Innenradius wie eingegeben, Außenmaße wie die Schenkel; Bohrungen und Konturen werden mitgebogen, "
                "auch in der Biegezone ([[step_export]]).",
     "STEP speichern auch für gekantete Bleche"],
    ["0.9.108", "<b>Rohrteil aus einer DXF-Zeichnung</b>: Zeichnungen mit Vorderansicht, Draufsicht und Schnitt werden "
                "ein Rohrteil im Rohr-Editor (<i>Neue Position → Aus DXF</i>, DXF aufs Angebot ziehen oder im "
                "Rohr-Editor <i>DXF importieren</i>). Maßstab je Ansicht aus der Bemaßung, Profil aus dem Schnitt, "
                "Länge, Gehrungen, Bohrungen, Langlöcher, Rechtecke und Ausklinkungen auf der richtigen Wand; "
                "Bezeichnung, Artikel und Werkstoff aus dem Schriftfeld. Mit STEP speichern wird daraus eine "
                "maßhaltige STEP-Datei ([[dxf_rohr]]).",
     "Rohrteil aus DXF-Zeichnung (Ansichten) in den Rohr-Editor"],
    ["0.9.107", "<b>STEP speichern</b> im Rohr- und Blech-Editor (Menüband <i>Ausgabe</i>): das Teil als STEP-Datei "
                "mit echtem Volumenkörper, wie im 3D-Modell. Rohr mit echtem Außenradius, Gehrung, 3D-Schnitt, "
                "Sattel, Bohrungen als Zylinder, Langlöcher und Rechtecke mit echten Bögen, Ausklinkungen, Nasen der "
                "Steckverbindung und Gravuren als Rille 0,1 mm tief mit 0,5 mm Abstand; ebene Bleche (auch aus dem "
                "DXF-Import) mit echten Bögen ([[step_export]]).",
     "STEP speichern: Rohr und ebenes Blech als Volumenkörper"],
    ["0.9.106", "<b>DXF-Import erkennt Ansichten</b>: Zeichnungen mit mehreren Ansichten ergeben keine Scheinteile "
               "mehr. Bemaßung auf Layer MASSE, verdeckte Kanten und Schraffur fallen weg (weitere Layer in der "
               "Einstellung). Die Isometrie ist nicht angehakt, die Seitenansicht eines Blechs liefert die Dicke, "
               "Teile unter 5 mm (Maßpfeile) und Konturen mit offenen Linien sind nicht angehakt, mit Grund. Eine "
               "<b>Rohrzeichnung</b> (Schnitt mit Wand und Ansicht) wird erkannt und mit Profil und Länge gemeldet, "
               "statt sie in Bleche zu zerlegen; der Rohr-Import folgt ([[dxf_import]]).",
     "DXF-Import: Ansichten, Isometrie, Maßpfeile und Rohrzeichnungen erkannt"],
    ["0.9.105", "<b>Nasen der Steckverbindung in der Abwicklung</b>: In der Abwicklung der Stange (Stangen-Detail und "
                "Werkstattpapiere) und in der Abwicklung des Rohr-Editors stehen die Nasen jetzt als Laschen über "
                "den Schnitt hinaus; vorher war das Ende gerade gezeichnet (Stangenbild).",
     "Nasen der Steckverbindung in der Abwicklung der Stange sichtbar."],
    ["0.9.104", "<b>Reiter Versand abschaltbar</b>: Einstellungen › Versand › <i>Reiter Versand und "
                "Palettenbegleitschein verwenden</i> = nein blendet den Reiter Versand und alle Wege dorthin aus "
                "(Menüeinträge <i>Palettenbegleitschein …</i>, Hinweis bei Beauftragt, Palettenscheine in den "
                "Werkstattpapieren, Suche Strg+K); wieder auf ja ist alles zurück, die Daten bleiben ([[versand]]).",
     "Reiter Versand per Einstellung ein- und ausschaltbar"],
    ["0.9.103", "<b>3D-Ansichten: Blick, Perspektive, Darstellung, exaktes Messen</b> – in allen 3D-Fenstern gleich "
               "(Teile-Editor, Positionen, STEP-Prüfdialog, Teilebaum, Schweißbaugruppe, Satz in 3D) mit Leiste und "
               "Ansichtswürfel. <i>Blick</i>: Isometrie, Vorn, Hinten, Oben, Unten, Ende A, Ende B, Auf Auswahl, um "
               "90° drehen (Strg + Pfeiltasten). <i>Perspektivisch</i> umschaltbar (Vorgabe orthogonal, je Benutzer "
               "gemerkt). Neue Darstellungen <i>Drahtgitter</i> und <i>Verdeckt gestrichelt</i>, Tangentenkanten an "
               "Rundungen. <b>Messen mit exakten Kernwerten</b>: fängt Kreismitte, Kantenmitte, Ecke und Fläche aus "
               "der echten Geometrie (Bohrung Ø 8 = 8,000), Abstand mit Δ längs/quer/hoch, Fläche–Fläche, "
               "Kante–Kante, Punkt–Fläche und Winkel in der kopierbaren Mess-Tafel. [[ansicht_3d_bedienung]]",
     "3D-Ansichten: sechs Seiten, Perspektive, Drahtgitter, verdeckte Kanten, Messen mit exakten Kernwerten."],
    ["0.9.102", "<b>Nasen der Steckverbindung im Rohr-Editor</b>: Die Schnittebene an einem Ende mit Nasen stand "
                "an der Spitze der Nasen und verdeckte sie, als wären sie abgeschnitten. Sie steht jetzt am Schnitt, "
                "die Nasen ragen sichtbar darüber hinaus. [[editor_griffe]]",
     "Nasen der Steckverbindung nicht mehr von der Schnittebene verdeckt."],
    ["0.9.101", "<b>Knickrahmen mit gerundeter Ecke</b>: Ist die Außenkante am Knick gerundet (Knick mit Radius statt "
               "scharfer Kante), hielt der STEP-Import die Gehrungen der Schenkel für eine Fase, und der Knickrahmen "
               "war „nicht verbindbar“. Die Eckenden kommen jetzt aus der Eckgeometrie ([[knickrahmen_koerper]]).",
     "Knickrahmen aus einem Körper auch mit gerundeter Außenkante am Knick verbindbar."],
    ["0.9.100", "<b>Knickrahmen im Editor der Schweißbaugruppe</b>: wie im Fenster Satz in 3D Rohre mit Gehrung "
                "markieren und <i>Knickrahmen erstellen …</i>. Die Nahtvorschläge an den Ecken fallen weg, der Stoß "
                "bleibt; mit OK wird der Rahmen eine Position der Baugruppe. [[knickverbindung]]",
     "Knickrahmen auch im Editor der Schweißbaugruppe erstellen."],
    ["0.9.99", "<b>Knickrahmen im Fenster Satz in 3D</b>: Rohre mit Gehrung markieren und <i>Knickrahmen erstellen "
               "…</i> – wie im STEP-Prüfdialog, auch wenn der Satz schon im Angebot steht. Mit OK wird der Rahmen "
               "eine Position (gestreckt, V-Ausschnitte, Zusatzarbeit Knicken, gefaltet im 3D); die Rohre fallen weg "
               "bzw. zählen je Satz weniger, gleiche Rahmen werden eine Position. [[satz_3d]]",
     "Knickrahmen auch im Fenster Satz in 3D erstellen."],
    ["0.9.98", "<b>Knickrahmen aus einem Körper sicherer erkannt</b>: Hatte ein Rahmen Bohrungen oder Ausschnitte nur "
               "in einer Wand (z. B. eine Lochreihe oben an einem Schenkel), lag die berechnete Rahmenebene minimal "
               "schief und der STEP-Import erkannte den Knickrahmen nicht. Die Ebene kommt jetzt genau von der "
               "Rahmenwand ([[knickrahmen_koerper]]).",
     "Knickrahmen aus einem Körper auch mit einseitigen Bohrungen erkannt."],
    ["0.9.97", "<b>Programmcode geschützt</b>: Der eigene Programmcode wird jetzt zu Maschinencode übersetzt "
               "ausgeliefert, in Programm und Online-Updates steckt kein lesbarer Quelltext mehr ([[updates]]). Neu "
               "sind die <b>Lizenzbedingungen</b>: Das Setup zeigt sie vor dem Installieren, im Programm stehen sie "
               "unter <i>Hilfe → Lizenzbedingungen …</i> ([[lizenz]]). Setup und ZIP gibt es zusätzlich im "
               "<b>Download-Bereich</b> des Update-Repositorys ([[start]]). Das erste Update danach ist größer, weil "
               "alle Programmdateien neu sind.",
     "Programmcode übersetzt, Lizenzbedingungen, Download-Bereich ([[updates]], [[lizenz]])."],
    ["0.9.96", "<b>Dunkelmodus verbessert</b>: Eingabezellen sind im Dunkelmodus blaugrau statt olivbraun, berechnete "
               "Zellen etwas dunkler, sodass beides gut zu unterscheiden ist. Das Feld „STEP-Dateien hierher ziehen“, "
               "die Skizzen und Zeichnungen in Rohr-, Blech-, Naht- und Profil-Editor und die 3D-Ansicht sind jetzt "
               "auch dunkel; Zeichnungen im PDF bleiben weiß. <b>Wie Windows</b> erkennt den Windows-Dunkelmodus "
               "zuverlässig über die Windows-Einstellung, und Hell bleibt hell, auch wenn Windows dunkel ist (vorher "
               "mischten sich weiße Karten mit dunklen Fenstern). Farbschema, Schriftgröße und Dichte wirken sofort, "
               "ohne Neustart. Spaltenköpfe lassen Platz für den Sortierpfeil und werden nicht mehr abgeschnitten "
               "(z. B. „Programmierzei…“) ([[einstellungen]]).",
     "Dunkelmodus: blaugraue Eingabezellen, dunkle Skizzen und 3D, Wie Windows zuverlässig, Wechsel sofort"],
    ["0.9.95", "<b>Satz in 3D</b>: Ein Satz aus Rohrlaserteilen, der keine Schweißbaugruppe ist (z. B. ein Rahmen "
               "als Stecksystem), steht im neuen Fenster <i>Satz in 3D …</i> (Rechtsklick auf eine Position) in der "
               "Einbaulage der STEP-Datei. Dort "
               "legen Sie Steckverbindungen an wie in der Schweißbaugruppe: zwei Rohre markieren (auch per Klick im "
               "3D) oder <i>Alle Stöße stecken</i>; Schlitze und Nasen stehen sofort im Modell. <b>Längsnaht per "
               "Klick</b>: <i>Längsnaht wählen</i> und die Fläche eines Rohrs anklicken – auch im 3D der "
               "Schweißbaugruppe. [[satz_3d]]",
     "Satz in 3D: Steckverbindungen für Sätze ohne Schweißbaugruppe, Längsnaht per Klick auf die Fläche."],
    ["0.9.94", "<b>3D der Schweißbaugruppe wie im Rohr-Editor</b>: Leiste mit Blick, Ansichtswürfel, Darstellung "
               "(auch Durchsichtig), <i>Nur Gewähltes</i>, <i>Nähte</i> ein/aus, Messen und Winkel. Die Rohre stehen "
               "so im 3D, wie sie gerechnet werden: aus den Eingaben, mit den Schlitzen und Nasen der "
               "Steckverbindungen. Schweißnähte als Raupe (Kehlnaht als Dreieck mit dem a-Maß, Stumpfnaht flach); "
               "fehlt der Nahtverlauf, kommt er aus dem Stoß der Rohre. Auch im Teile-Editor sind die Nasen jetzt "
               "modelliert. [[baugruppe_baum]]",
     "3D der Schweißbaugruppe wie im Rohr-Editor: Nasen und Schlitze im Modell, Nähte als Raupe."],
    ["0.9.93", "<b>3D-Editor: Gegenrohr, Lochfeld, Fase, Schrift</b>: Ein Rohrende lässt sich auf ein "
               "<b>Gegenrohr</b> setzen – rund oder rechteckig, schräg, mit Versatz, auf Rund-, Quadrat- und "
               "Rechteckrohr; das Programm rechnet die echte Schnittkurve, im 3D steht das Gegenrohr pink. Neu als "
               "Konturen: <b>Durchbruch</b> (Loch für ein Rohr, das durch die Wand geht, auch schräg und beidseitig) und "
               "<b>Lochfeld</b> (Raster aus Bohrungen oder Langlöchern in einer Zeile, Reihen quer, versetzt). Rechteck "
               "und Ausklinkung bekommen gefaste Ecken (Rechtsklick → Ecken). Text-Gravuren erscheinen im 3D als echte "
               "Schrift. Die Ausklinkung auf Rundrohr ist jetzt richtig herum gezeichnet "
               "([[schneidweg_rechner]], [[teile_editor]]).",
     "3D-Editor: Gegenrohr (schräg, Versatz, eckig), Durchbruch, Lochfeld, Fase, Schrift im 3D."],
    ["0.9.92", "<b>Lizenz-Werkzeug des Herstellers</b>: zeigt je Lizenz den Status (läuft ab, abgelaufen, gesperrt), "
               "erinnert 30 Tage vor Ablauf, verlängert eine Lizenz mit einem Klick, hat eine Kundenübersicht und lädt "
               "die Sperrliste direkt zum Update-Server hoch. Am Programm selbst ändert sich nichts.",
     "Lizenz-Werkzeug: Erinnerung, Verlängern, Kundenübersicht, Sperrliste hochladen."],
    ["0.9.91", "<b>Sicherer Release-Ablauf</b>: Vor jeder Veröffentlichung prüft der Build, dass im Paket nur "
               "Programmdateien liegen (keine Daten, Angebote, Lizenzen, Schlüssel, Tests oder Quelltext) und "
               "schreibt eine Release-Zusammenfassung mit allen Prüfsummen. Neu ist ein <b>Vorabkanal</b> für "
               "Test-PCs ([[updates]]).",
     "Release-Prüfung und Vorabkanal für Test-PCs ([[updates]])."],
    ["0.9.90", "<b>DXF-Import für Bleche</b>: im Blech-Editor <i>DXF importieren</i>, im Angebot <i>Neue Position → "
               "Bleche aus DXF</i> oder DXF-Dateien aufs Angebot ziehen. Die Kontur kommt genau wie gezeichnet "
               "(Bögen bleiben Bögen), Bohrung/Langloch/Rechteck nur bei exakter Form. Rahmen und Schriftfeld fallen "
               "weg, mehrere Bleche einer Zeichnung werden einzelne Positionen, Maßstab aus Bemaßung oder Schriftfeld. "
               "Werkstoff und Dicke werden aus Dateiname und Texten vorgeschlagen; Biegelinien machen ein Kantteil "
               "([[dxf_import]]). <b>STEP-Import</b>: ein Rechteckrohr mit Gehrungen an beiden Enden wurde manchmal als "
               "gekantetes Blech erkannt (und die anstoßenden Rohre bekamen es als Anbauteil); geschlossene Rohre "
               "bleiben jetzt Rohr. <b>3D</b>: Kann die Maschine des Angebots 3D, ist die 3D-Schnittbearbeitung bei Teilen "
               "mit Gehrung oder schräger Bohrung von selbst an (im Rohr-Editor und im STEP-Prüfdialog, je Teil "
               "abwählbar); senkrechte Schnitte bleiben 2D. Fehler „NoneType … __round__“ beim Knickrahmen mit "
               "schräger Innenwand in 3D behoben. <b>Schweißnaht im 3D</b>: eine feste Nahtlage zeigt der Rohr-Editor "
               "(und die 3D-Ansicht der Position) als rote Linie über die ganze Länge. <b>Schnittflächen 2D/3D</b>: in 2D "
               "steht der Strahl überall senkrecht zum Mantel (Innenkante unter der Außenkante, so auch im 3D "
               "gezeichnet); in 3D schwenkt der Kopf je Stelle nur so weit wie nötig, über 45° (Grenze der Maschine) "
               "steht er auf 45° – diese Stücke sind gelb, die Position bekommt eine WARNUNG mit Ende und Länge, die "
               "Schneidzeit rechnet je Stück mit seinem Winkel.",
     "DXF-Import: genaue Kontur, Rahmen weg, mehrere Bleche, Werkstoff/Dicke vorgeschlagen ([[dxf_import]])."],
    ["0.9.89", "<b>Palettenbegleitschein und Versand im Programm</b> (ersetzt das Palettenschein-Tool): neuer Reiter "
               "<b>Versand</b> mit allen beauftragten Aufträgen, Filtern (überfällig, heute, diese Woche, "
               "verladebereit, versendet, archiviert), Sammeldruck, Verladeliste und Status. Je Auftrag rechnet das "
               "Programm die <b>Anzahl der Paletten</b> lagenweise aus Teilmaßen, Höhe (1,2 m) und Gewicht (1,5 t): "
               "jede Position zuerst einzeln, angefangene Paletten zusammen, wenn Platz ist; die Packliste zeigt den "
               "Aufbau je Palette. Je Palette ein Schein A4 quer mit <i>Inhalt dieser Palette</i>, Arbeitsschritte "
               "aus dem Angebot vorgeschlagen, PDF im Angebotsordner und hinten an den Werkstattpapieren. Der "
               "Packvorschlag der Fracht rechnet genauso. Arbeitstage und Liefertermin-Vorschlag ohne Feiertage des "
               "Bundeslands ([[versand]], [[paletten_rechnung]]).",
     "Reiter Versand mit Palettenbegleitschein und genauer Palettenanzahl"],
    ["0.9.88", "Fehler behoben: Die Werkstatt-PDF mit Stangenbild brach bei der Strichpunkt-Linie ab.",
     "Werkstatt-PDF mit Stangenbild wieder fehlerfrei."],
    ["0.9.87", "<b>Updates nur noch signiert</b>: Das Programm spielt nur noch Updates ein, deren Dateiliste mit dem "
               "Schlüssel des Herstellers digital signiert ist. Eine veränderte oder fremde Dateiliste lehnt es ab "
               "und bleibt auf der bisherigen Version ([[updates]]).",
     "Updates nur noch mit gültiger Signatur ([[updates]])."],
    ["0.9.86", "<b>Kontur-Vorlagen im Teile-Editor</b>: markierte Konturen (z. B. ein Bohrbild mit seinen Abständen) "
               "unter einem Namen speichern, wahlweise nur für den Kunden, und in andere Rohre oder Bleche einsetzen; "
               "das Menü zeigt jede Vorlage mit Bild. <i>Aus Position</i> zeigt je Position ein Vorschaubild. In der "
               "<b>3D-Ansicht der Positionen</b> öffnet ein Doppelklick auf das Teil (oder <i>Im Editor öffnen</i>) "
               "die Position im Editor. <b>Fix</b>: In der Darstellung <i>Mit Kanten</i> liefen bei Rohren mit Ausschnitt "
               "(z. B. Knickrahmen) viele Längslinien über das ganze Rohr; die Wand hat jetzt keine offenen Stöße mehr "
               "([[teile_editor]], [[step_3d_ansicht]]).",
     "Kontur-Vorlagen mit Bild, je Kunde; 3D-Ansicht der Positionen öffnet den Editor ([[teile_editor]])."],
    ["0.9.85", "<b>Blech zeichnen im Teile-Editor</b>: Außenkontur mit Klicks in der Abwicklung zeichnen, Eckpunkte am "
               "Griff ziehen, Rechtsklick rundet oder fast eine Ecke; Innenkonturen, Biegelinien und Außenkanten mit "
               "der Maus ziehen (Biegelinie ändert die Schenkel). Langloch, Rechteck und Polygon haben einen "
               "<i>Drehwinkel</i> ([[blech_editor]]).",
     "Blech: Außenkontur zeichnen, Ecken runden/fasen, Konturen und Biegelinien ziehen, Drehwinkel ([[blech_editor]])."],
    ["0.9.84", "<b>Messen und Querschnitt im Teile-Editor</b>: Messen fängt auch Konturmitten, <i>Winkel</i> misst "
               "aus drei Punkten, fertige Maße bleiben im 3D stehen bis <i>Maße löschen</i>. <i>Querschnitt</i> "
               "zeigt das Rohr an einer Stelle x quer geschnitten mit allen Konturen, die dort durch die Wand gehen; "
               "die Stelle ist im 3D markiert. <b>Knickrahmen</b>: der Freistich an der Spitze des V-Ausschnitts "
               "nimmt jetzt im 3D Material weg (vorher blieb der Teil des Kreises innerhalb des V stehen) "
               "([[teile_editor]], [[knickrahmen]]).",
     "Messen: Konturmitten, Winkel, Maße bleiben; Querschnitt an Stelle x ([[teile_editor]])."],
    ["0.9.83", "<b>Stangenbild wie in Lantek</b>: Umschalter <i>Stangenmuster</i> / <i>Übersicht</i> / <i>Detail</i> im "
               "Reiter Stangenbild und im Abmessungs-Fenster. Die Übersicht zeigt jede Stange als dünne Zeile, nach "
               "Abmessung gruppiert; ein Klick öffnet das Detail mit Kennzahlen, den Teilen als Kacheln und der "
               "<b>Abwicklung der ganzen Stange</b> (alle Konturen an ihrem Platz, Naht SN). Die Abwicklung steht "
               "auch in den Werkstattpapieren unter jedem Stangenmuster. Im Reiter Schnittplan links ein "
               "<b>Teilebaum</b> mit Benötigt/Eingeplant/Offen, Status-Punkt und 3D-Vorschau ([[optimieren]]).",
     "Stangen-Übersicht, Stangen-Detail mit Abwicklung, Teilebaum mit 3D im Schnittplan ([[optimieren]])."],
    ["0.9.82", "<b>Schneller bei großen Angeboten</b>: <b>Optimieren</b> rechnet ab etwa 1.500 Teilen die "
     "Profilgruppen auf mehreren Prozessorkernen gleichzeitig (500 Positionen: 10 s statt 28 s, mit Vergleich der "
     "Lieferlängen 17 s statt 45 s), der Schnittplan ist derselbe. Die <b>Suche in der Angebotsliste</b> filtert, "
     "sobald man kurz mit dem Tippen aufhört, statt bei jeder Taste (1.000 Angebote: 0,3 s statt 4,6 s). Tabellen "
     "messen die Spaltenbreite an den sichtbaren und höchstens 100 Zeilen; ein sehr langer Eintrag weiter unten "
     "kann gekürzt sein und steht ganz im Tooltip ([[optimieren]]).",
     "Optimieren großer Angebote auf mehreren Kernen, schnellere Suche in der Angebotsliste ([[optimieren]])."],
    ["0.9.81", "<b>Eigenschaften je Kontur wie in AlmaCAM</b> (Teile-Editor, Rohr): Bezug der Lage (Mitte oder "
               "Kante, ab Ende A oder B; ab B bleibt der Abstand bei neuer Teilelänge), Drehwinkel der Kontur, Wände "
               "(beide durchgehend, alle vier Seiten, am Umfang verteilt – jede Kopie zählt im Schneidweg und ist in "
               "Skizze und 3D zu sehen) und beim Rundrohr die Schnittrichtung parallel zur Konturachse (3D) "
               "([[teile_editor]]).",
     "Kontur: Bezug der Lage, Drehwinkel, beide Wände/am Umfang, Schnitt parallel ([[teile_editor]])."],
    ["0.9.80", "<b>Update abgesichert</b>: Das Programm prüft die Dateiliste eines Updates, bevor es sie benutzt "
               "(nur https von der offiziellen Adresse, keine Pfade außerhalb des Programmordners, Prüfsummen, "
               "Größengrenzen, freier Speicherplatz) und schützt vor manipulierten Paketen. Bricht ein Update hart "
               "ab, stellt der nächste Start die bisherige Version wieder her. Die Dateiliste wird digital "
               "signiert; die Pflicht zur Signatur folgt mit dem nächsten Update ([[updates]]).",
     "Update geprüft und signiert, Wiederherstellung nach abgebrochenem Update ([[updates]])."],
    ["0.9.79", "<b>Kalkulation je Teil einzeln</b>: Reiter Kalkulation und Kalkulations-PDF zeigen je Teil jede "
               "Kostenart in einer eigenen Spalte statt zusammengefasst (Laser schneiden und Gewinde, Rüsten "
               "Maschine, Rüsten je Abmessung und Stangenwechsel, die drei Zuschläge, Programmierung, Pauschale je "
               "Abmessung, Angebotsaufschlag, Zukaufteile, Gewinn und Fracht); die Spalten einer Zeile ergeben den "
               "Preis je Teil.",
     "Kalkulation je Teil: jede Kostenart in eigener Spalte."],
    ["0.9.78", "<b>3D-Ansicht schöner</b>: Licht wie auf blankem Metall mit Glanzlicht und Fülllicht, "
               "Hintergrund mit Verlauf; Rundungen bleiben glatt, Kanten scharf. Ohne Grafikkarte (Software, "
               "Remote-Desktop) gilt dasselbe Licht ([[step_3d_ansicht]]).",
     "3D-Ansicht im Metall-Look mit Glanz- und Fülllicht ([[step_3d_ansicht]])."],
    ["0.9.77", "<b>Zeichnung des Blechteils als PDF</b>: Im Blech-Editor (unten und im Menüband unter <i>Ausgabe</i>) "
               "schreibt <i>Zeichnung als PDF …</i> eine maßstäbliche Zeichnung: Abwicklung bzw. Zuschnitt mit "
               "Außenmaßen und Biegelinien, beim Kantteil die Seitenansicht, dazu die Biegungen (Lage, Winkel, "
               "Richtung, Radius, Ausgleich) und die Innenkonturen mit Lage ([[blech_zeichnung]]).",
     "Zeichnung des Blechteils als PDF ([[blech_zeichnung]])"],
    ["0.9.76", "<b>Vorkalkulation automatisch</b> je Schweißbaugruppe: Häkchen im Editor, vorbelegt aus der "
               "Einstellung. Bei ja übernimmt die Baugruppe alle Nahtvorschläge aus dem STEP (a-Maß nach Regel) und "
               "schlägt Schweißen, Heften, Verputzen, Rüsten, Positionieren und Wenden bei jeder Änderung neu vor; "
               "Werte von Hand und bestätigte bleiben ([[vorkalkulation_baugruppe]]).",
     "Vorkalkulation automatisch je Schweißbaugruppe, Vorgabe aus der Einstellung ([[vorkalkulation_baugruppe]])."],
    ["0.9.75", "<b>CSV-Export als einzelne Dateien</b>: <i>Ausgaben → CSV-Export</i> fragt nach dem Ordner (Start: "
               "zuletzt gewählter Ordner) und speichert <i>&lt;Nr&gt; Angebotskopf.csv</i> und <i>&lt;Nr&gt; "
               "Angebotspositionen.csv</i> einzeln statt als ZIP. In der Schrittanzeige wird <b>④ Verschickt</b> "
               "erst grün, wenn auch der CSV-Export gemacht ist ([[csv_export]]).",
     "CSV-Export einzeln in wählbaren Ordner; „Verschickt“ erst nach CSV-Export grün."],
    ["0.9.74", "<b>Steckverbindung anlegen</b>: Im Editor der Schweißbaugruppe gibt es den Reiter "
               "<i>Steckverbindungen</i>. <b>Steckverbindung hinzufügen</b> verbindet die zwei markierten Rohre "
               "(Aufnahme und Stecker), mit Lage x, Seite, Nasen, Nasenbreite, Spiel, Überstand, Wänden und Winkel; die "
               "Spalte <i>Schlitz und Nasen</i> zeigt das Ergebnis oder was fehlt. Beim Speichern bekommt die Aufnahme "
               "die Schlitze, der Stecker die Nasen; Schneidweg, Einstiche und Länge werden neu gerechnet. Entfernen "
               "nimmt beides wieder heraus. Im Teile-Editor bleiben Schlitze und Nasen beim Übernehmen erhalten. <b>Alle Stöße "
               "stecken</b> legt bei Baugruppen aus dem STEP-Import alle Verbindungen auf einmal an: Der Import merkt "
               "sich jedes Rohrende auf einem anderen Rohr mit Lage, Seite und Winkel (STEP-JSON 1.18); bei gleichen "
               "Teilen kommen Schlitze und Nasen nur einmal ([[steckverbindung_anlegen]]).",
     "Steckverbindungen im Editor der Schweißbaugruppe anlegen, „Alle Stöße stecken“ aus STEP "
     "([[steckverbindung_anlegen]])"],
    ["0.9.73", "<b>Beauftragt mit Auftragsnummer und Liefertermin</b>: <i>Vorgang ▾ → Beauftragt</i> fragt die "
               "Auftragsnummer des Kunden und den Liefertermin ab (Vorschlag aus der Lieferzeit); beides steht in "
               "der Angebotsliste und lässt sich suchen. <b>Eingabe wie in Excel</b> in der Positionsliste: "
               "Eingabe springt weiter (nach unten oder rechts, Einstellung), ↓ in der letzten Zeile legt eine "
               "Position an, <b>Strg+D</b> übernimmt den Wert von oben, im Profil-Feld findet „40x3“ das Profil "
               "„QR 40x40x3“ ([[excel_eingabe]]).",
     "Beauftragt mit Auftragsnummer und Termin; Positionsliste: Eingabe, ↓, Strg+D wie in Excel."],
    ["0.9.72", "<b>Knickrahmen: Knick verschieben</b> im Teile-Editor (Pfeile ziehen) oder in der Tabelle gab den "
               "FEHLER „V-Ausschnitte wurden von Hand geändert“. Jetzt folgen die Schenkel dem Knick, die gestreckte "
               "Länge bleibt ([[knickrahmen]]).",
     "Knickrahmen: Knick verschieben führt die Schenkel mit ([[knickrahmen]])."],
    ["0.9.71", "<b>Steckverbindung (Rechenkern)</b>: Zwei Rohre einer Schweißbaugruppe können mit Nasen und Schlitzen "
               "ineinanderstecken. Die Aufnahme bekommt je Nase einen Schlitz (Rechteck, Spiel je Seite), das Ende des "
               "Steckers die Nasen (je Nase zwei Flanken, Teil um die Nasenlänge länger). Auch Rundrohr (Bogen-Nase, "
               "Sattel) und schräge Stöße ab 30°. Neue Einstellungen unter Steckverbindung, Prüfregel <i>Nase zu "
               "schmal</i> und FEHLER <i>Steckverbindung ohne Gegenstück</i> in der Baugruppe "
               "([[steckverbindung]]). Anlegen im Dialog folgt im nächsten Schritt.",
     "Steckverbindung: Schlitze und Nasen rechnen ([[steckverbindung]])."],
    ["0.9.70", "<b>Teile-Editor: echte Ausschnitte im 3D</b>: Bei Rund-, Quadrat- und Rechteckrohr sind Bohrungen, "
               "Langlöcher, Rechtecke, Ausklinkungen, Schlitze, Polygone, V-Ausschnitte und Sonderkonturen ausgeschnitten, "
               "mit roter Lochwand durch die Wandstärke; Ausschnitte am Ende fehlen auch in der Stirnfläche. Gravur und "
               "Flowdrill bleiben Linien. <b>Klick auf eine Fläche</b> im 3D wählt: Lochwand = Kontur, Stirnfläche = "
               "Ende, Rohrwand = <b>Profil und Teil</b> mit Profil, Abmessung, Wandstärke, Werkstoff und Teilelänge "
               "([[teile_editor]]). <b>Rundungen glatt</b>: Rundrohr, Eckradien und Lochwände sehen in der 3D-Ansicht "
               "(OpenGL) rund aus statt gestreift; Kanten bleiben scharf.",
     "Teile-Editor: Konturen im 3D echt ausgeschnitten, Flächen anklickbar, Profil-Einstellungen, glatte Rundungen ([[teile_editor]])."],
    ["0.9.69", "<b>Artikelnummer gravieren</b> als Hilfe beim Schweißen: im Editor der Schweißbaugruppe Haken "
               "<i>Artikelnr. gravieren</i> und Schrifthöhe je Teil, <i>Alle gravieren</i>; Einstellung ja/nein "
               "gibt den Haken vor (auch beim STEP-Import), Schrifthöhe 10 mm. Rohre: die Gravur zählt in die "
               "Laserzeit. Bleche: Zeile <i>Text-Gravur</i> im Blech-Editor, Lage automatisch in der größten freien "
               "Fläche (mindestens 0,5 mm Abstand), verschiebbar, mit Feld <i>Vorschub Gravur</i> in den "
               "Blechlaser-Richtwerten ([[positionsgravur]]).",
     "Artikelnummer auf Rohre und Bleche der Schweißbaugruppe gravieren ([[positionsgravur]])."],
    ["0.9.68", "<b>3D der Baugruppe</b>: Steckt ein Teil öfter in der Baugruppe, als die STEP-Datei Körper dafür hat "
               "(Menge von Hand erhöht oder Unterbaugruppe aus eigener Datei), nennt die Zeile unter der Ansicht "
               "jetzt die Teile mit „1 von 4 Stück“ ([[baugruppe_baum]]).",
     "3D der Baugruppe: Hinweis, wenn nicht alle Stück eines Teils im 3D stehen ([[baugruppe_baum]])."],
    ["0.9.67", "<b>Neue Fassung offline</b>: Fassungen eines Angebots mit vorläufiger Nummer (V-PB-1-2) bekommen "
     "beim Abgleich bzw. vor dem Angebots-PDF dieselbe endgültige Nummer wie das erste Angebot, mit ihrem Zusatz "
     "(2026-00042-2); <i>Ersetzt durch …</i> und die Grundnummer werden mitgeändert ([[mehrere_arbeitsplaetze]]).",
     "Fassungen vorläufiger Nummern bekommen die endgültige Nummer mit Zusatz ([[mehrere_arbeitsplaetze]])."],
    ["0.9.66", "<b>Teile-Editor: am 3D-Modell bearbeiten</b> wie im CAM-Programm. Die gewählte Kontur hat Pfeile "
               "zum Ziehen (längs und quer um den Umfang, auch auf die Nachbarfläche), das Maß steht dabei am "
               "Mauszeiger; <b>Fangen</b> auf Raster (5 mm, Rundrohr 15°), Teilmitte und Flächenmitte, Alt = frei. "
               "<b>Maße am Modell</b> (ab A, bis B, zur Nachbarkontur) mit Doppelklick ändern, Rechnungen wie L/2 gehen. "
               "<b>Schnittebenen</b> an den Enden mit Griff für den Gehrungswinkel. <b>Pfeiltasten</b> verschieben um "
               "den Rasterschritt (Umschalt ×10). <b>Rechtsklick</b>: Duplizieren, Spiegeln, Gegenseite, Auf "
               "STEP-Wert, Entfernen, Messen von hier. <b>Darstellung</b> Schattiert, Mit Kanten, Durchsichtig und "
               "<i>nur Gewähltes</i>; Gewähltes ist grün. Der Editor öffnet immer maximiert ([[editor_griffe]]).",
     "Teile-Editor: Konturen und Gehrung direkt am 3D-Modell ziehen, Maße am Modell, Rechtsklick-Menü, "
     "Darstellungsarten ([[editor_griffe]])."],
    ["0.9.64", "<b>Werkstoffliste für den Rohrlaser</b>: 17 neue Werkstoffe (u. a. EN 10210 warmgefertigt, "
               "DX51D+Z275 sendzimirverzinkt, P235TR1, P235GH nahtlos, S420MH/S460MH, S355J2WH wetterfest, 1.4541, "
               "1.4016, 1.4003, 1.4462 Duplex, EN AW-6061/6005A) und die Kategorie <b>Buntmetall</b> (CuZn37, "
               "Cu-DHP) mit Faser-Richtwerten. Neue Felder je Werkstoff: <b>Rohrart</b> (nahtlos/stranggepresst = "
               "keine Nahtvorgabe, kein Stangenwechsel SN), <b>Schneidgas</b> (nur N₂/nur O₂), <b>Vorschub-Faktor</b> "
               "auf die Schneiddaten der Kategorie, <b>Laser</b> (nur Faser warnt auf T03) und <b>Laser-Hinweis</b> "
               "(Tooltip, Angebots-Check, Kalkulation, Werkstattpapiere). Bestehende Dateien bekommen die neuen "
               "Werkstoffe einmalig dazu, eigene bleiben unverändert ([[werkstoffe]]).",
     "Werkstoffliste für den Rohrlaser: 17 neue Werkstoffe, Buntmetall, Schneidgas, Vorschub-Faktor, Rohrart "
     "([[werkstoffe]])."],
    ["0.9.63", "<b>Teile-Editor: Gruppe Knicke</b>: Bei einem Knickrahmen zeigt der Merkmalsbaum des Schneidweg-Rechners "
               "die Knicke (Knickwinkel, Lage, Stegwand) und den Rahmen mit seiner Herkunft (STEP oder manuell). Ein "
               "Klick zeigt den V-Ausschnitt in Tabelle, Skizze und 3D ([[knickrahmen]]).",
     "Teile-Editor: Gruppe Knicke für Knickrahmen ([[knickrahmen]])."],
    ["0.9.62", "<b>Außenradius bei Quadrat- und Rechteckrohr</b>: neues Feld in den Profilen (leer = Vorgabe nach "
               "EN 10219: 2 × Wand bis 6 mm, 2,5 × bis 10 mm, darüber 3 ×; 0 = scharfkantig). Er kürzt die "
               "Schnittlänge der Enden (QR 40 × 40 × 3 gerade 149,7 statt 160 mm, schräg mit elliptischen Ecken) und "
               "die Außenfläche; Skizze und 3D-Modell zeigen runde Ecken. Im Schneidweg-Rechner (Eigenschaften des "
               "Teils) lässt er sich für das Angebot ändern; er gilt dann für alle Positionen mit gleichem Profil und "
               "Werkstoff ([[profile]], [[teile_editor]]). Bei Werkstoff <b>Aluminium</b> ist die Vorgabe 0 "
               "(scharfkantig), solange Stammdaten oder Angebot nichts anderes festlegen.",
     "Außenradius für Quadrat- und Rechteckrohr, im Angebot je Profil und Werkstoff ([[profile]])."],
    ["0.9.61", "<b>Eigener Ordner je Angebot</b>: Alles, was das Programm zu einem Angebot speichert (Angebot, "
               "Kalkulation, Werkstattpapiere, Nachkalkulation, Zeichnungen, CSV-Export, Materialanfrage, STEP-Messung), "
               "kommt in den Ordner <i>Nummer Kunde</i> in der Ablage; Fassungen als Unterordner <i>Fassung 2</i>. Neuer "
               "Knopf <b>Ordner öffnen</b> in der Übersicht und im Menü Ausgaben. Auf Wunsch kopiert der STEP-Import die "
               "STEP-Dateien in den Unterordner <i>STEP</i> (Haken im Prüfdialog, Vorgabe in den Einstellungen). Lose "
               "Dateien in der Ablage werden einmalig in den Ordner ihres Angebots verschoben ([[angebotsordner]]).",
     "Eigener Ordner je Angebot, Knopf Ordner öffnen, STEP-Dateien optional mitkopieren ([[angebotsordner]])."],
    ["0.9.60", "<b>Knickrahmen aus einem Körper</b>: Ist ein geknickter Rahmen aus Quadrat- oder Rechteckrohr in "
               "der STEP-Datei ein einziger Körper, erkennt ihn der Import (auch gestreckt gezeichnet mit "
               "V-Ausschnitten). Er teilt ihn an den Ecken, misst jeden Schenkel und zeigt eine Zeile <i>Knickrahmen (n Knicke) aus einem Körper</i>. Übernommen wird sie wie "
               "eine Knickverbindung: gestrecktes Rohr, V-Ausschnitte, Bohrungen an ihrer Stelle, Zusatzarbeit Knicken. "
               "Rechtsklick → <i>Knickrahmen bearbeiten …</i> ([[knickrahmen_koerper]]).",
     "Knickrahmen aus einem STEP-Körper wird erkannt ([[knickrahmen_koerper]])."],
    ["0.9.58", "<b>Teile-Editor neu aufgebaut</b> (Schneidweg-Rechner und Blech-Editor) wie ein CAM-Programm: "
     "oben ein <b>Menüband</b> (Konstruktion, Ansicht, Ausgabe), in der Mitte das <b>3D-Modell</b> mit "
     "Ansichtswürfel und die Skizze, rechts die <b>Eigenschaften</b> des gewählten Merkmals mit Maßbild, unten "
     "Kennzahlen und der Zähler der Prüfmeldungen. Das Rohr hat jetzt auch ohne STEP-Datei ein 3D-Modell, das jede "
     "Eingabe sofort zeigt. Maßfelder rechnen (z. B. 1200/2+15, 3x25, L-40); Duplizieren mit Strg+D, Entfernen mit "
     "Entf. Die Tabelle bleibt über Ansicht → Tabelle erreichbar ([[teile_editor]]).",
     "Teile-Editor mit Menüband, 3D-Modell, Eigenschaften und Rechenfeldern ([[teile_editor]])."],
    ["0.9.57", "<b>Naht im 3D zeichnen</b>: Im Baugruppen-Editor (Reiter <i>Strukturbaum und 3D</i>) lässt sich eine "
               "Schweißnaht direkt am Modell zeichnen: <i>Naht zeichnen</i>, Punkte entlang der Naht anklicken, "
               "<i>Als Nahtgruppe übernehmen</i>. Länge, beteiligte Teile, Unterbaugruppe und Wanddicke ermittelt das "
               "Programm ([[baugruppe_baum]]).",
     "Schweißnaht im 3D der Baugruppe von Hand zeichnen ([[baugruppe_baum]])."],
    ["0.9.56", "<b>Schweißnähte in 3D</b>: Im Baugruppen-Editor zeigt der Reiter <i>Strukturbaum und 3D</i> die "
               "Schweißnähte als Linien am Modell: Nahtgruppen schwarz, offene Nahtvorschläge magenta, die gewählte "
               "Nahtgruppe rot. Den Nahtverlauf liefert der STEP-Import ab dieser Version; ältere Importe neu "
               "einlesen ([[baugruppe_baum]]).",
     "Schweißnähte in der 3D-Ansicht der Baugruppe ([[baugruppe_baum]])."],
    ["0.9.55", "<b>Knickverbindung aus Einzelrohren</b>: Ist ein Rahmen in der STEP-Datei aus einzelnen Rohren mit "
               "Gehrung gezeichnet, schlägt der Prüfdialog einen Knickrahmen vor (auch: Rohre markieren, Rechtsklick). "
               "Daraus wird eine Position mit gestrecktem Rohr, V-Ausschnitten, den Bohrungen aller Rohre an ihrer "
               "Stelle und der Zusatzarbeit Knicken; die Nahtkandidaten an den Knicken fallen weg. Neu im Fenster "
               "Knickrahmen: <b>Innenwand schräg (3D)</b>, Vorgabe aus ([[knickverbindung]], [[knickrahmen]]).",
     "Knickverbindung aus STEP-Einzelrohren, Innenwand schräg (3D) wählbar ([[knickverbindung]])."],
    ["0.9.53", "<b>Online-Update zuverlässiger</b>: Nach <i>Jetzt aktualisieren</i> lädt das Programm die neuen "
               "Dateien, schließt dann alles (Fenster, STEP-Messung, Abgleich, Sicherung, Datendatei) und tauscht "
               "erst danach aus. Ist eine Datei noch geöffnet, wartet es bis zu 30 s und nennt dann Datei und Grund "
               "mit <i>Wiederholen</i> oder <i>Abbrechen</i>; bei Abbruch oder Fehler bleibt die alte Version. Ist nur die "
               "Anleitung gesperrt, wird sie beim nächsten Start getauscht. Die "
               "Bedienungsanleitung öffnet sich aus einer Kopie im Datenordner und blockiert das Update nicht mehr "
               "([[updates]]).",
     "Update: erst alles schließen, dann austauschen; gesperrte Dateien abwarten, Wiederholen/Abbrechen "
     "([[updates]])."],
    ["0.9.52", "<b>Strukturbaum und 3D</b> im Editor der Schweißbaugruppe: Baum aus Baugruppe, Unterbaugruppen, "
     "Einzelteilen und Nahtgruppen, rechts die ganze Baugruppe in 3D in Einbaulage. Klick auf eine Unterbaugruppe, "
     "ein Teil oder eine Nahtgruppe hebt die Teile hervor; ein Teil auf eine Unterbaugruppe ziehen ordnet es neu zu. "
     "Der STEP-Import merkt sich dafür die Lage aller gleichen Körper ([[baugruppe_baum]]).",
     "Strukturbaum mit 3D im Baugruppen-Editor, Teile per Ziehen zuordnen ([[baugruppe_baum]])."],
    ["0.9.51", "<b>STEP per Drag &amp; Drop</b>: Der Windows-Explorer bleibt beim Ziehen von STEP-Dateien ins "
               "Programm nicht mehr hängen, bis die Positionen im Angebot stehen; er ist gleich nach dem Loslassen "
               "wieder frei. Das Programm kommt nach vorne und zeigt die Messung sofort. Ein weiterer Drop während "
               "eines laufenden Imports wird mit Hinweis abgelehnt. Große Ordner stocken beim Darüberziehen nicht "
               "mehr ([[step]]).",
     "STEP per Drag & Drop: Explorer bleibt frei, Programm kommt nach vorne ([[step]])."],
    ["0.9.50", "<b>Vorkalkulation der Schweißbaugruppe</b>: <b>Vorkalkulation rechnen</b> im Baugruppen-Editor "
     "schlägt Heftpunkte und Nacharbeit je Nahtgruppe, die Positionierhilfe je Einzelteil (Steckverbindung, "
     "Vorrichtung, Gravur, frei) und die Arbeitsgänge Rüsten Schweißplatz, Teile positionieren, Wenden / Umspannen "
     "und Verputzen vor. Gelb = Vorschlag mit Rechnung im Tooltip, <b>Vorschläge bestätigen</b> übernimmt sie, Werte "
     "von Hand bleiben. Die Regeln stehen unter Einstellungen → Schweiß-Vorkalkulation (neu leer, Richtwerte per "
     "Knopf); wahlweise rechnet das Programm die Vorschläge gleich beim STEP-Import "
     "([[vorkalkulation_baugruppe]]).",
     "Vorkalkulation der Schweißbaugruppe: Rüsten, Positionieren, Heften, Verputzen als Vorschläge "
     "([[vorkalkulation_baugruppe]])."],
    ["0.9.49", "<b>Knickrahmen</b> im Schneidweg-Rechner: Rahmen aus einem Quadrat- oder Rechteckrohr, an jeder Ecke "
               "ein V-Ausschnitt, nur die Stegwand bleibt stehen. <b>Knickrahmen …</b> nimmt die Schenkel (z. B. "
               "500; 300; 500; 300), Knickwinkel und Stegwand und setzt die V-Ausschnitte, die Gehrung am Stoß und die "
               "<b>gestreckte Länge</b> (Außenmaße − Ausgleich nach DIN 6935 je Knick + Knickzugabe). Neue Konturart "
               "<i>V-Ausschnitt</i>, neue Zusatzarbeit <i>Knicken</i> (€ je Knick), neue Prüfregeln <i>Schenkel zu "
               "kurz</i>, <i>Kontur im Knickbereich</i>, <i>Wand zu dick zum Knicken</i> ([[knickrahmen]]).",
     "Knickrahmen: V-Ausschnitte, gestreckte Länge, Zusatzarbeit Knicken, Prüfregeln ([[knickrahmen]])."],
    ["0.9.48", "<b>Nachfassen und Wiedervorlage</b>: Verschickte Angebote ohne Antwort stehen nach 10 Tagen "
               "(Einstellung) auf der Startseite unter Wiedervorlage und im neuen Filter <i>Wiedervorlage fällig</i>, "
               "mit Grund. <b>Nachfassen vermerken …</b> trägt Anruf oder E-Mail in den Versandverlauf ein, die Tage "
               "zählen dann neu. <b>Wiedervorlage …</b> setzt ein eigenes Datum, auch für Entwürfe ([[nachfassen]]).",
     "Nachfassen: automatische Wiedervorlage, Nachfassen vermerken, eigenes Wiedervorlage-Datum ([[nachfassen]])."],
    ["0.9.47", "<b>Gemeinsamer Nummernkreis</b>: Angebotsnummern ohne Kürzel, <b>2026-00001</b>, 2026-00002 … für "
     "alle Mitarbeiter gemeinsam; der Zähler läuft über den Jahreswechsel weiter. Jede Nummer wird im gemeinsamen "
     "Ordner reserviert, so kommt keine doppelt vor, auch wenn zwei gleichzeitig ein Angebot anlegen. Ist der Ordner "
     "nicht erreichbar, gibt es eine vorläufige Nummer (V-PB-1), die endgültige kommt beim nächsten Abgleich; "
     "Angebots-PDF und Materialanfrage erst mit endgültiger Nummer. Das Kürzel bleibt als Bearbeiter, ältere "
     "Nummern bleiben ([[mehrere_arbeitsplaetze]]).",
     "Gemeinsamer Nummernkreis 2026-00001 ohne Kürzel, keine Nummer doppelt ([[mehrere_arbeitsplaetze]])."],
    ["0.9.46", "<b>Neue Fassung</b>: <i>Datei → Neue Fassung des Angebots</i> oder der Haken im Dialog Kopieren legt "
               "das Angebot mit gleicher Nummer und Zusatz -2, -3 … an: gleicher Kunde, heutiges Datum, aktuelle "
               "Preise, Positionen und Staffeln. Die alte Fassung steht auf <b>Ersetzt durch …</b> und zählt in "
               "keinem Vorgang mehr; Filter <i>Ersetzt (alte Fassungen)</i> ([[neue_fassung]]).",
     "Neue Fassung -2, -3 statt Kopie; alte Fassung „Ersetzt“."],
    ["0.9.45", "<b>Neues Angebot aus STEP</b>: STEP-Dateien oder einen Ordner auf die Angebotsliste oder die "
               "Startseite ziehen oder <i>Datei → Neues Angebot aus STEP …</i>: Das Programm schlägt den Kunden aus dem Ordnernamen vor "
               "(sonst den Kunden des letzten Angebots mit Importprofil), legt das Angebot mit den Kundenvorgaben an "
               "und startet gleich den STEP-Import ([[angebot_aus_step]]).",
     "Neues Angebot direkt aus STEP-Dateien oder Ordner, Kunde aus dem Ordnernamen."],
    ["0.9.44", "<b>Angebots-Check</b> vor dem Versand: Die Übersicht zeigt laufend alle offenen Punkte mit "
               "<b>Hinspringen</b> (Positionen mit FEHLER oder WARNUNG, Kunde, Fracht, Zukauf ohne Einkaufspreis, "
               "Hinweise der Kalkulation, Mindestmarge, Mindestauftragswert, Stammdaten geändert, Kunde ohne E-Mail, "
               "Lieferzeit, Kundenreferenz). Vor dem Angebots-PDF und vor <i>Verschickt</i> kommt höchstens "
               "<b>eine</b> Rückfrage; ein veralteter Schnittplan wird ohne Rückfrage neu optimiert. FEHLER lassen "
               "sich nur mit Begründung übergehen, sie steht im Versandverlauf. Neue Einstellung <i>Mindestmarge</i> "
               "([[angebots_check]]).",
     "Angebots-Check: eine Rückfrage vor dem PDF, Hinspringen, FEHLER nur mit Begründung ([[angebots_check]])."],
    ["0.9.43", "<b>Kundenvorgaben</b>: Einstellungen → Kundenvorgaben hält je Kunde Maschine, Stangenlänge, Gewinn, "
               "Lieferzeit, Material neuer Positionen und eigene Standard-Staffeln (0 = keine). Ein neues Angebot "
               "für den Kunden und das Wählen des Kunden im Angebot übernehmen sie; von Hand geänderte Kopfwerte "
               "bleiben, die Statuszeile nennt, was übernommen wurde ([[kundenvorgaben]]).",
     "Kundenvorgaben je Kunde: Maschine, Gewinn, Lieferzeit, Material, Staffeln."],
    ["0.9.42", "<b>Schneller nach jeder Änderung</b>: Die Stammdaten werden nur neu gelesen, wenn sie sich geändert "
               "haben (auch Abgleich mit Kollegen, Wiederherstellen, andere Programme), und der Optimierungsstand wird "
               "je Anzeige nur einmal geprüft. Ein Angebot zeigt Änderungen dadurch rund ein Drittel schneller an "
               "([[optimieren]]).",
     "Schneller nach jeder Änderung: Stammdaten zwischengespeichert ([[optimieren]])."],
    ["0.9.41", "<b>Automatisch optimieren</b>: Entwürfe bis 100 Positionen (und unter 500 Teilen) optimieren sich etwa "
               "0,8 Sekunden nach jeder Änderung selbst, F9 ist meist nicht mehr nötig. Einstellung <i>Automatisch "
               "optimieren: Entwürfe bis Positionen (0 = aus)</i>; verschickte Angebote, fremde Angebote und der "
               "Lesemodus bleiben unverändert, ein Fehler steht nur in der Statuszeile ([[optimieren]]).",
     "Entwürfe bis 100 Positionen optimieren sich nach jeder Änderung selbst."],
    ["0.9.40", "<b>Wiederholteile erkennen</b>: Wurde ein Teil schon angeboten (auch von Kollegen), zeigt die Übersicht "
               "im Angebot wie oft, zuletzt wann und wo, den damaligen Stückpreis aus den Staffelpreisen und ob es "
               "beauftragt war; Treffer über gleiche Artikelnummer (sicher beim selben Kunden) oder gleiche Geometrie. "
               "<b>Werte übernehmen …</b> holt Schneidzeit von Hand, Programmierzeit, Zusatzarbeiten, Gewinde und Naht "
               "einzeln wählbar; der Preis wird nie übernommen ([[wiederholteile]]).",
     "Wiederholteile mit altem Preis und Werte übernehmen ([[wiederholteile]])."],
    ["0.9.39", "<b>Biegerohre</b> im STEP-Import: gebogene Rundrohre (Geraden und Bögen) werden erkannt. Das "
     "Programm rechnet die gestreckte Länge (Geraden + Faktor neutrale Faser × Bögen, Einstellung unter STEP-Import, "
     "Vorgabe 1,0) und setzt die Bohrungen an die richtige Stelle am geraden Rohr. Die Biegedaten (LRA und XYZ) "
     "stehen im Teile-Editor, die Skizze zeigt die Biegezonen. Neue Prüfregeln <i>Kontur in der Biegezone</i> und "
     "<i>Gerade zwischen Biegungen zu kurz</i>, neue Zusatzarbeit <i>Biegen</i> (€ je Biegung, Menge aus dem Import). "
     "Prüfstatus immer prüfen ([[biegerohre]]).",
     "Biegerohre: gestreckte Länge, Konturen am geraden Rohr, Biegedaten, Biegezonen, Zusatzarbeit Biegen "
     "([[biegerohre]])."],
    ["0.9.38", "<b>Spaltenbreiten bleiben</b>: Von Hand gezogene Spalten behalten ihre Breite auch nach einem Neustart "
               "(je Tabelle, nur an diesem Arbeitsplatz); Rechtsklick auf den Spaltenkopf → <b>Spaltenbreiten "
               "zurücksetzen</b> passt wieder alles an. Die Hauptknöpfe (Neue Position, STEP importieren, Optimieren, "
               "Angebot (PDF) …) und die Startseite tragen schlichte <b>Symbole</b> vor dem Text ([[positionen]]).",
     "Gezogene Spaltenbreiten bleiben über den Neustart; Symbole an den Hauptknöpfen."],
    ["0.9.37", "<b>Material … mit Zusatzfenstern</b>: Doppelklick auf <b>Stangen</b> öffnet die Abmessung in einem "
               "eigenen Fenster mit Stangenbild, Schnittmustern, Meter- und Gewichtsbilanz und der Liste aller Teile "
               "(Länge, Stück, Enden, Naht, eingeplant, auf Stangen, Material und Verkaufspreis je Teil). Doppelklick "
               "auf Material € oder €/m zeigt den Preis-Aufbau mit Herkunft des Meterpreises, auf den Querschnitt die "
               "Profil-Info mit passenden Maschinen. Rechtsklick: 12-m-Lösung, Materialanfrage und Schnittplan nur "
               "für diese Abmessung, Positionen markieren ([[abmessung_fenster]]).",
     "Material …: Doppelklick öffnet Abmessung, Preis-Aufbau und Profil-Info ([[abmessung_fenster]])."],
    ["0.9.36", "<b>Suchen und ausführen</b>: <b>Strg+K</b> (Menü Ansicht) findet von überall Angebote, Kunden, "
               "Profile, Werkstoffe, Einstellungen und Menübefehle; Enter öffnet oder führt aus ([[befehlspalette]]). "
               "<b>Startseite mit Karte Heute</b>: eigene Angebote je Vorgang mit Summe (Klick zeigt die "
               "Angebotsliste mit diesem Filter), <b>Wiedervorlage</b> verschickter Angebote, deren Gültigkeit bald "
               "endet, und mit Admin-Lizenz die Kennzahlen der letzten 90 Tage mit Trefferquote ([[start]]). Im "
               "Angebot zeigt der <b>Kostenwasserfall</b> unter dem Preisaufbau, welcher Posten den Preis treibt; im "
               "Reiter Staffeln zeigt die <b>Staffelkurve</b> den Preis je Einheit über die Mengen ([[staffeln]]).",
     "Strg+K sucht und führt aus; Startseite mit Wiedervorlage und Pipeline; Kostenwasserfall und Staffelkurve."],
    ["0.9.35", "<b>Mehrere STEP-Dateien als eine Schweißbaugruppe</b>: Im Prüfdialog des STEP-Imports lässt sich eine "
     "Datei mit <i>in Baugruppe „…“</i> als Unterbaugruppe in die Schweißbaugruppe einer anderen Datei einhängen; "
     "<i>Sätze</i> gilt dann als Stück je übergeordneter Baugruppe ([[step]], [[schweissbaugruppe]]). Im Angebot "
     "eines Kollegen öffnet der Baugruppen-Editor nur zum Ansehen.",
     "STEP-Import: mehrere Dateien als eine Schweißbaugruppe ([[step]])."],
    ["0.9.34", "<b>Gewinn auf alle Kosten</b>: Der Gewinn rechnet jetzt auf die <b>Selbstkosten</b> = Herstellkosten + "
               "Programmierung + Pauschale je Abmessung + Angebotsaufschlag + Zukaufteile, nicht mehr nur auf die "
               "Herstellkosten. Die Fracht kommt ohne Gewinn danach, das Skonto wie bisher zuletzt auf den Preis mit "
               "Gewinn. Preisaufbau, Kalkulation-PDF und Staffelpreise zeigen die neue Zeile <i>Selbstkosten</i> und "
               "„Gewinn (… % auf Selbstkosten …)“. Mit gleichem Gewinn-% steigen die Preise (Prüfangebote +1,6 bis "
               "+8 %). Verschickte, festgeschriebene Angebote rechnen weiter wie bisher, bis <b>Aktuelle Preise "
               "übernehmen …</b> ([[gewinn_basis]]). <b>Zeiten aufgeschlüsselt</b>: In der Übersicht klappen "
               "Maschine und Personal per ▸ ihre Arbeitsschritte mit Zeit und Kosten auf; Schweißbaugruppen und "
               "Schweißen als Zusatzarbeit zählen jetzt als Personalzeit, die Rüstzeit steht als „davon Rüsten“, "
               "dazu Arbeitszeit gesamt, Durchlaufzeit und Ø je Teil ([[zeiten]]).",
     "Gewinn auf die Selbstkosten (alle Kosten außer Fracht), Skonto danach; Zeiten nach Maschine und Personal "
     "aufgeschlüsselt ([[gewinn_basis]], [[zeiten]])."],
    ["0.9.33", "<b>Schweißbaugruppen lernen aus der Nachkalkulation</b>: Unter Einstellungen → Schweiß-Kennwerte "
     "schlägt <i>Kennwerte aus Nachkalkulation …</i> je Verfahren und Nahtart einen Faktor Ist ÷ Soll vor (Median, "
     "Ausreißer ausgeschlossen); geändert wird erst nach Freigabe mit Begründung, jede Freigabe lässt sich "
     "zurücknehmen. Dazu wahlweise Schweißzusatz und Schutzgas je Verfahren, ein a-Maß-Vorschlag nach Regel "
     "(0,7 × Wanddicke, zu bestätigen) für Kehlnähte aus STEP, farbige Abweichungen in der Nachkalkulation "
     "mit Verlauf je Vorlage und eine gruppierte Positionsliste (Einzelteile unter ihrer Baugruppe, zuklappbar) "
     "([[schweiss_stammdaten]], [[schweissbaugruppe]]).",
     "Kennwerte aus der Nachkalkulation, Schweißzusatz/Gas, a-Maß nach Regel ([[schweiss_stammdaten]])."],
    ["0.9.32", "<b>Dunkel, Hoher Kontrast, Schriftgröße</b>: Unter Vorgaben, Gruppe Ansicht, lassen sich Farbschema "
               "(Hell, Dunkel, Hoher Kontrast, Wie Windows), Schriftgröße (90 bis 150 %) und Dichte (kompakt, normal, "
               "komfortabel) wählen; gilt ab dem nächsten Start, nur an diesem Arbeitsplatz. Kurze Hinweise erscheinen "
               "jetzt unten rechts und verschwinden von selbst, <b>Meldungen (N)</b> in der Statusleiste zeigt die "
               "letzten noch einmal ([[einstellungen]], [[fragen]]). <b>Aufgeräumte Bedienung</b>: Im Angebot eine "
               "Knopfleiste in drei Gruppen; rechts nur <b>Angebot (PDF)</b>, alle weiteren Ausgaben (Werkstattpapiere, "
               "Kalkulation, Materialanfrage, CSV-Export, Ablage) im Menü <b>Ausgaben</b>; Positionen löschen über "
               "Rechtsklick oder Entf. Über den Reitern zeigt eine Schrittanzeige ① erfasst → ② optimiert → ③ geprüft → "
               "④ verschickt. Geöffnete Angebote stehen in einer eigenen Reiterzeile unter <b>Angebote</b>. Die Einstellungen haben links eine Navigation nach Themen mit <b>Suchfeld</b>; in den "
               "Vorgaben steht die Einheit im Feld (z. B. „15,00 min“) und „0 = aus“ als Text im Feld ([[ausgabe]]).",
     "Farbschema Dunkel/Hoher Kontrast, Schriftgröße; Knopfleiste mit Menü Ausgaben, Schrittanzeige, "
     "Einstellungen mit Navigation und Suche ([[einstellungen]])."],
    ["0.9.31", "<b>Schneller durch den Ablauf</b>: <b>Standard-Staffeln</b> (Vorgabe Menge × 1, × 2, × 5, in den "
               "Einstellungen änderbar) legt ein Knopf im Reiter Staffeln an, und das erste Angebots-PDF ohne Stufe "
               "macht es selbst ([[staffeln]]). <b>Stückzahl ändern …</b> setzt die Stückzahl markierter oder aller "
               "Positionen × Faktor oder auf einen Wert ([[rueckgaengig]]). In der Nachkalkulation übernimmt "
               "<b>Rest wie geplant</b> alle leeren Ist-Werte aus dem Soll, die Angebotsliste filtert "
               "<i>Nachkalkulation offen</i> ([[nachkalkulation]]). Neue Tastenkürzel: F8 Staffelpreise, "
               "Strg+Umschalt+P Werkstattpapiere, Strg+Umschalt+K Kalkulation, Strg+Umschalt+M Materialanfrage, "
               "Strg+Umschalt+S Stückzahl ändern.",
     "Standard-Staffeln, Stückzahl ändern, Nachkalkulation „Rest wie geplant“ und neue Tastenkürzel."],
    ["0.9.30", "<b>Schweißplan und Baugruppen in Kalkulation und CSV</b>: Die Werkstattpapiere haben je "
     "Schweißbaugruppe eine Seite Schweißplan (Struktur, Einzelteile, Nahtgruppen, Arbeitsgänge und Vorrichtungen "
     "zum Abhaken, Vorgabezeit, ohne Preise); die Kalkulation-PDF zeigt je Baugruppe Nahtgruppen und Arbeitsgänge "
     "mit Zeit, Kosten und Herkunft; der CSV-Export (ZIP) enthält Schweissbaugruppen.csv ([[schweissbaugruppe]]).",
     "Schweißplan in den Werkstattpapieren, Baugruppen in Kalkulation-PDF und CSV ([[schweissbaugruppe]])."],
    ["0.9.29", "<b>Übersichtlicher</b>: Der Angebotskopf braucht 5 statt 8 Zeilen, die Positionsliste wird höher. "
               "Der Status hat ein Symbol (Haken, i, Dreieck, Kreuz), Eingabefelder sind nur noch hell gelb, der "
               "Verkaufspreis steht groß in der Übersicht. Die Staffel-Tabelle schneidet keine Texte mehr ab. Leere "
               "Spalten Bearbeiter und Nachkalkuliert blendet die Angebotsliste aus; die Startseite zeigt die "
               "Stammdaten-Tabellen nur aufgeklappt. Lange Hinweise in Dialogen zeigen den ersten Satz, der Rest "
               "steht hinter <b>ⓘ mehr</b> ([[angebot]]).",
     "Angebot kompakter, Status mit Symbol, Verkaufspreis groß ([[angebot]])."],
    ["0.9.28", "<b>Baugruppen-Vorlagen</b>: Im Editor einer Schweißbaugruppe lassen sich Struktur, Nahtgruppen und "
     "Arbeitsgänge als Vorlage speichern und in neue Baugruppen einsetzen (Kennwerte aus den aktuellen Stammdaten). "
     "Neu im Rechtsklick-Menü: <b>Baugruppe in anderes Angebot kopieren …</b> mit allen Einzelteilen "
     "([[schweissbaugruppe]]).",
     "Baugruppen-Vorlagen und Baugruppe in anderes Angebot kopieren ([[schweissbaugruppe]])."],
    ["0.9.27", "<b>Teile-Editor</b>: Schneidweg-Rechner und Blech-Editor haben einen gemeinsamen Rahmen. Links "
     "stehen die Merkmale des Teils (Enden, Innenkonturen, Biegungen, Schweißnaht, Gravur) mit ihrer Herkunft STEP, "
     "manuell oder Vorgabe; geänderte STEP-Werte lassen sich auf die Messung zurücksetzen. Unten stehen die "
     "Prüfmeldungen, ein Klick zeigt die Stelle in Tabelle, Skizze und 3D-Ansicht. Dazu Rückgängig/Wiederholen "
     "(Strg+Z/Strg+Y), Messen Punkt–Punkt in der 3D-Ansicht und beim Rohr ein Reiter 3D mit dem Netz aus dem "
     "STEP-Import; ein Klick auf eine Kontur in 3D wählt ihre Zeile ([[teile_editor]]).",
     "Teile-Editor: Merkmale mit Herkunft, Prüfmeldungen mit Klick, Rückgängig, Messen in 3D ([[teile_editor]])."],
    ["0.9.26", "<b>Bedienungsanleitung Teil C bildlastig</b>: Einstellungen, Mehrere Arbeitsplätze, Stammdaten, "
     "Zukaufartikel, Frachtkosten sowie Updates und Datensicherung zeigen wie Teil A und B zuerst das Bild mit einem "
     "kurzen Satz oder Schritten; die Einzelheiten stehen im Kasten <i>Genauer</i>. Die Stammdaten haben eigene "
     "Abschnitte je Tabelle (Kunden, Profile, Werkstoffe und Oberflächen, Preise und Lieferlängen, Maschinen und "
     "Schneiddaten). Die Kurzanleitung enthält jetzt auch Teil C ([[stammdaten]]).",
     "Anleitung Teil C mit Bildern und Kästen „Genauer“, Kurzanleitung mit Teil C ([[stammdaten]])."],
    ["0.9.20", "<b>Passwort verschlüsselt</b>: Das Passwort der Einstellungen (zugleich Admin-Passwort beim Start) steht "
               "nicht mehr lesbar in der Datendatei, sondern nur als Prüfwert. Das bisherige Passwort gilt weiter. Das "
               "Feld unter Vorgaben, Gruppe Zugang, bleibt deshalb leer; neues Passwort eintippen ändert es, "
               "<b>Entfernen</b> schaltet es ab ([[passwort]]). Dazu laufen die Programmtests jetzt gemeinsam und "
               "schneller.",
     "Passwort der Einstellungen verschlüsselt gespeichert ([[passwort]])."],
    ["0.9.19", "<b>Schweißbaugruppen schneller und übersichtlicher</b>: Der Status großer Angebote mit Baugruppen "
     "rechnet die Sollwerte nur noch einmal je Stand (500 Teile rund fünfmal schneller); Nahtgruppen ohne Kennwert "
     "oder a-Maß sind im Editor gelb markiert, Richtwerte als Etikett; der Doppelklick auf den Status springt zur "
     "betroffenen Zeile; beschädigte Baugruppendaten nennen Ort und Grund; neuer <b>Kostenbalken</b> je Baugruppe in "
     "der Übersicht und im Editor ([[schweissbaugruppe]]).",
     "Baugruppen: schnellerer Status, gelbe Nahtgruppen, Sprung zur Zeile, Kostenbalken ([[schweissbaugruppe]])."],
    ["0.9.18", "<b>Fertigungsprüfung</b>: Rohr-, Profil- und Blechteile werden auf zu kleine Bohrungen, zu schmale "
     "Stege, Konturen zu nah am Ende bzw. an der Blechkante, Gravuren über eine Kante, zu kurze Teile und die "
     "Kantbarkeit geprüft. Der Befund steht mit der Lage am Teil im Status, im Schneidweg-Rechner und im "
     "Blech-Editor. Jede Regel ist im Unterreiter Prüfregeln (Fertigung) abschaltbar, mit Grenzwert und Stufe; neu "
     "bei den Maschinen: Kürzestes Teil ([[pruefregeln]]).",
     "Fertigungsprüfung mit Regeltabelle ([[pruefregeln]])."],
    ["0.9.17", "<b>Tafelausnutzung</b>: Das Material eines Blechteils kommt aus dem Tafelbedarf der Stückzahl "
     "(Hüllrechtecke mit Steg auf den Tafelformaten, die letzte Tafel nur mit der belegten Fläche) statt aus einem "
     "festen Verschnitt; größere Lose und Staffelpreise werden dadurch günstiger. Tafelformate, Randabstand und Steg "
     "stehen in den Einstellungen ([[blech_tafel]]).",
     "Blech-Material aus dem Tafelbedarf je Stückzahl ([[blech_tafel]])."],
    ["0.9.16", "<b>Kantbarkeit prüfen</b>: Der Blech-Editor weist bei Kantteilen auf zu kurze Schenkel (nach "
               "V-Öffnung), zu kleine Innenradien, Bohrungen zu nah an der Biegelinie und fehlende Freischnitte an "
               "Biegeecken hin; die Regeln stehen unter Einstellungen ([[blech_kantbarkeit]]).",
     "Blech-Editor: Hinweise zur Kantbarkeit ([[blech_kantbarkeit]])."],
    ["0.9.15", "<b>Admin-Passwort beim Start</b>: Mit Admin-Lizenz fragt das Programm beim Start das Admin-Passwort "
               "ab (= Passwort der Einstellungen). Nach Abbrechen oder dreimal falsch startet es ohne Admin-Rechte wie "
               "mit einer Benutzerlizenz; <i>Hilfe → Lizenz …</i>, <b>Admin freischalten …</b> holt sie nach. "
               "Benutzerlizenzen gelten jetzt in der Regel 3 statt 6 Monate ([[lizenz]]).",
     "Admin-Lizenz: Passwort beim Start; Benutzerlizenzen 3 Monate ([[lizenz]])."],
    ["0.9.14", "<b>K-Faktor-Tabelle</b>: Der Blech-Editor nimmt den K-Faktor jeder Biegung aus der neuen Tabelle "
               "<i>K-Faktoren (Abwicklung)</i> nach Kategorie, Blechdicke und Innenradius ÷ Dicke (Beispielwerte nach "
               "DIN 6935; Innenradius = Dicke wie bisher 0,33). Der Editor zeigt die genutzten K-Faktoren "
               "([[blech_stammdaten]]).",
     "Blech-Editor: K-Faktor je Biegung aus der K-Faktor-Tabelle ([[blech_stammdaten]])."],
    ["0.9.13", "<b>DXF der Abwicklung</b>: Der Blech-Editor speichert den Zuschnitt mit <b>DXF speichern …</b> als "
               "DXF-Datei (R12) mit Layern für Außenkontur, Innenkonturen, Biegelinien nach oben und unten, Gravur "
               "und Beschriftung; Rundungen als echte Bögen. Layernamen unter Einstellungen ([[blech_dxf]]).",
     "Blech-Editor: Abwicklung als DXF mit Layern ([[blech_dxf]])."],
    ["0.9.12", "<b>3D-Ansicht mit Grafikkarte</b>: Die 3D-Ansicht zeichnet jetzt mit OpenGL, wenn der Rechner das kann. "
               "Auch große Baugruppen bleiben beim Drehen fein und flüssig. Über Remote-Desktop und wenn OpenGL nicht "
               "klappt, zeichnet sie wie bisher. Einstellbar unter Vorgaben, Ansicht ([[step_3d_ansicht]]).",
     "3D-Ansicht mit Grafikkarte (OpenGL), Rückfall wie bisher ([[step_3d_ansicht]])."],
    ["0.9.11", "<b>Schweißbaugruppen: Nachkalkulation und Nahtkandidaten</b>: Der Reiter Nachkalkulation zeigt je "
                "Baugruppe Soll und Ist für Schweißen und Arbeitsgänge [h], Material/Einmalbeträge und "
                "Fremdleistungen [€], Abweichungsgrund und die Schweißzeit je Meter Naht ([[nachkalkulation]]). "
                "Aus STEP erkannte Nahtkandidaten stehen im Editor als Vorschläge und werden erst mit <i>Markierte "
                "übernehmen</i> Nahtgruppen ([[schweissbaugruppe]]).",
     "Schweißbaugruppen: Nachkalkulation je Baugruppe, Nahtkandidaten aus STEP als Vorschläge."],
    ["0.9.10", "<b>STEP-Import schneller</b>: Gleiche Teile einer Baugruppe (im CAD nur verschoben, z. B. acht gleiche "
              "Stützen) werden nur einmal gemessen, und eine große Datei wird auf mehrere Messprozesse verteilt. Eine "
              "Baugruppe mit 200 Körpern braucht statt 85 s etwa 30 s, mit 3 Prozessen etwa 15 s; die Messwerte "
              "bleiben gleich. Die 3D-Ansicht großer Baugruppen bleibt beim Drehen flüssig ([[step]]).",
     "STEP-Import schneller: gleiche Teile einmal messen, große Dateien verteilt, 3D flüssiger ([[step]])."],
    ["0.9.9", "<b>Schweißbaugruppe aus STEP</b>: Im Prüfdialog des STEP-Imports legt das Häkchen <i>als "
               "Schweißbaugruppe</i> (neben <i>Sätze</i>) den Satz als Schweißbaugruppe an: Unterbaugruppen mit Menge "
               "aus der STEP-Struktur, Teile zugeordnet; Nahtgruppen und Arbeitsgänge im Editor ergänzen ([[step]]).",
     "STEP-Import: Satz wahlweise als Schweißbaugruppe mit Unterbaugruppen aus der Datei."],
    ["0.9.8", "<b>STEP: Nahtkandidaten</b>: Bei Baugruppen erkennt die Messung, welche Teile sich berühren, und "
              "schlägt je Stelle eine Schweißnaht vor (Länge, Kehl-, Stumpf- oder Ecknaht, Wanddicke). Die "
              "Vorschläge stehen im Messergebnis mit Status <i>prüfen</i> und sind die Grundlage für die "
              "Schweißbaugruppen ([[step]]).",
     "STEP: Nahtkandidaten bei Baugruppen ([[step]])."],
    ["0.9.7", "<b>Kompakte Übersicht in der Kalkulation</b>: Der Reiter Kalkulation zeigt je Bauteil auf einen Blick "
               "Profil, Stückzahl, Länge, Material, Oberfläche, Laserzeit berechnet und genutzt (je Teil, dazu je "
               "Position in Minuten) und den Verkaufspreis je Teil und Position; Doppelklick springt zur Position. "
               "Häkchen <i>Kompakt</i> aus zeigt wie bisher alle Spalten ([[kalkulation]]).",
     "Kalkulation kompakt: Profil, Stück, Länge, Material, Oberfläche, Laserzeit berechnet/genutzt, VK je Bauteil "
     "([[kalkulation]])."],
    ["0.9.6", "<b>Schweißbaugruppen im Angebot</b>: eine Zeile je Baugruppe mit Zeichnung, Werkstoff und "
               "Oberfläche; Einzelteile nur mit dem Häkchen <i>Stückliste im Angebot zeigen</i>. Einmalkosten "
               "(Rüsten, Vorrichtungen) zählen in den Staffeln wie Rüsten; mit dem Häkchen <i>Einmalkosten als eigene "
               "Zeile im Angebot</i> stehen sie als eigene Zeile und in den Staffeln als <i>zzgl. einmalig</i> "
               "([[schweissbaugruppe]]).",
     "Schweißbaugruppe als eine Angebotszeile, Stückliste und Einmalkosten wahlweise getrennt."],
    ["0.9.5", "<b>STEP: Bauteilnamen, Normteile, Importprofile</b>: Die Messung liest die Baugruppenstruktur und "
              "die Bauteilnamen aus der STEP-Datei. Der Bauteilname wird die Artikelnummer (Einstellung "
              "<i>Artikelnummer aus</i>; ohne Namen wie bisher der Dateiname). Normteile wie Schrauben, Muttern und "
              "Scheiben sind im Prüfdialog abgewählt. Neuer Unterreiter <i>Importprofile (STEP)</i>: je Kunde "
              "Benennung, Muster für die Artikelnummer, eigene Normteil-Begriffe, Werkstoff und Vorgaben. Die "
              "Struktur (Unterbaugruppen mit Menge) steht im Messergebnis für die Schweißbaugruppen "
              "([[importprofile]]).",
     "STEP: Artikel aus Bauteilnamen, Normteile abgewählt, Importprofile je Kunde ([[importprofile]])."],
    ["0.9.4", "<b>Lizenzen ladbar</b>: Das Programm kennt jetzt Patricks Schlüssel, Lizenzdateien lassen sich unter "
              "<i>Hilfe → Lizenz …</i> laden. <b>E-Mail an Patrick …</b> geht direkt an patrick.brundiers@gmail.com. "
              "Weiterhin keine Sperre ohne Lizenz ([[lizenz]]).",
     "Lizenzdateien lassen sich laden, E-Mail mit Rechner-ID an Patrick ([[lizenz]])."],
    ["0.9.3", "<b>CSV-Export neu</b>: Knopf <b>CSV-Export</b> rechts bei der Ausgabe mit <i>Kopf + Positionen "
               "(ZIP)</i>, <i>Nur Angebotskopf</i> und <i>Nur Angebotspositionen</i>. Angebotskopf.csv (26 Spalten, "
               "eine Zeile) und Angebotspositionen.csv (40 Spalten, eine Zeile je Position) im vorgegebenen Format: "
               "Semikolon, UTF-8 mit BOM, CRLF, Dezimalpunkt (79.98), Zeiten HH:MM:SS; ZIP heißt Angebot_&lt;Nr&gt;.zip "
               "([[csv_export]]). Der bisherige CSV-Export der Kalkulation entfällt; alle Werte stehen weiter im "
               "Kalkulations-PDF.",
     "CSV-Export Angebotskopf.csv + Angebotspositionen.csv (einzeln oder als ZIP) im festen Spaltenformat"],
    ["0.9.2", "<b>Schweißbaugruppen</b>: neue Positionsart <i>Schweißbaugruppe</i>. <i>Neue Position → "
               "Schweißbaugruppe</i> öffnet den Editor mit Struktur und Teilen (Unterbaugruppen mit Menge, markierte "
               "Positionen vorgewählt), Nahtgruppen, Arbeitsgängen und Vorrichtungen (Einmalkosten je Auftrag, "
               "anteilig oder wiederverwendbar), Stammdaten und Übersicht; gerechnet wird bei jeder Eingabe. Die "
               "Einzelteile bleiben normale Positionen, die Baugruppe rechnet nur ihre eigenen Leistungen dazu; Satz "
               "und Stückzahlen der Teile folgen der Baugruppe. <b>Aus Zusatzarbeiten …</b> übernimmt eine "
               "Zusatzarbeit als Arbeitsgang ([[schweissbaugruppe]]). Neue Unterreiter Schweißverfahren, "
               "Schweiß-Kennwerte und Schweiß-Faktoren; <b>Richtwerte laden</b> trägt fehlende Zeilen ein, eigene "
               "bleiben ([[schweiss_stammdaten]]). Angebote ohne Baugruppe rechnen genau wie bisher.",
     "Schweißbaugruppen: Editor, Nahtgruppen, Arbeitsgänge, Richtwerte laden ([[schweissbaugruppe]])."],
    ["0.9.1", "<b>STEP-Import robuster</b>: Die Messung zeigt Datei, Körper und Restzeit. Ein Körper, der länger als "
              "das Zeitlimit braucht (Vorgabe 120 s) oder abstürzt, wird ausgelassen und als <i>nicht gemessen</i> "
              "gemeldet, der Rest der Datei wird gemessen. Schon gemessene Dateien kommen sofort aus dem "
              "<i>Zwischenspeicher</i>. Nach <b>Abbrechen</b> lassen sich die fertigen Dateien übernehmen. Neue Karte "
              "<i>STEP-Import</i> in den Einstellungen mit Prozessen, Zeitlimit, Zwischenspeicher und Toleranzen "
              "([[einstellungen]]).",
     "STEP-Import: Zeitlimit je Körper, Zwischenspeicher, Teilergebnis bei Abbruch ([[einstellungen]])."],
    ["0.9.0", "<b>Lizenz</b>: neuer Menüpunkt <i>Hilfe → Lizenz …</i> mit Zustand, <b>Rechner-ID</b> (Kopieren, "
              "fertige E-Mail an Patrick) und <b>Lizenzdatei laden …</b> (auch per Drag & Drop). Eine Lizenz gilt "
              "offline für einen Rechner, Benutzerlizenzen meist 6 Monate; vor Ablauf erscheint ein Hinweis unten "
              "rechts. Ohne gültige Lizenz gilt später der <i>Lesemodus</i>: alles ansehen, exportieren und sichern, "
              "aber nichts ändern; Daten gehen nie verloren. <b>Noch keine Sperre</b>: Diese Version zeigt ohne Lizenz "
              "nur einen Hinweis. Bitte die Rechner-ID an Patrick senden ([[lizenz]]).",
     "Lizenz: <i>Hilfe → Lizenz …</i> mit Rechner-ID und Lizenzdatei laden, vorerst nur Hinweis ([[lizenz]])."],
    ["0.8.40", "<b>Profil geändert: Schneidwege gehen mit</b>: Wählt man für ein STEP-Teil ein anderes Profil (im "
               "Prüfdialog oder später im Angebot), rechnen Bohrungen, Langlöcher und Rechtecke mit ihren Maßen neu, "
               "Sonderkonturen und Gravuren werden auf den neuen Querschnitt übertragen; der Bericht nennt "
               "<i>Schneidweg alt → neu</i>. Nicht umrechenbare Zeilen bleiben gemessen und sind gelb. Von Hand "
               "nachgetragene Teile behalten die gemessenen Konturen ([[step]]).",
     "Profilwechsel: Konturen und Schneidweg für das neue Profil umgerechnet ([[step]])."],
    ["0.8.39", "<b>Rohr-Editor: Sonderkontur und Gravur</b>: Konturen über mehrere Wände und freie Formen aus dem "
               "STEP-Import stehen als <i>Sonderkontur</i> mit ihrem echten Umriss in Skizze und Abwicklung, auch über "
               "die Ecke. Prägungen sind <i>Gravur</i>-Zeilen mit Lage und Tiefe, grün gezeichnet und nicht im "
               "Schneidweg. Komplexe Enden zeigen in der Abwicklung ihren gemessenen Verlauf ([[schneidweg_rechner]]).",
     "Rohr-Editor: Sonderkontur mit echtem Umriss, Gravur grün ([[schneidweg_rechner]])."],
    ["0.8.38", "<b>Blech-Editor mit 3D-Ansicht</b>: Unter der Skizze steht das gekantete Teil dreidimensional "
               "(drehen, zoomen), mit Konturen und Biegelinien. Mehrachsig gekantete Teile aus dem STEP-Import "
               "(Schale, Kasten) kommen als Zuschnitt mit Außenkontur und Kantungen, scharfkantige L-/U-Teile ohne "
               "passendes Profil in den Stammdaten als Kantteil ([[blech_editor]]).",
     "Blech-Editor: 3D-Ansicht, mehrachsig gekantete Teile mit Abwicklung ([[blech_editor]])."],
    ["0.8.37", "<b>STEP-Import erkennt mehr</b>: Gekantete Bleche werden abgewickelt, auch scharfkantige und "
               "mehrachsige (Schale, Kasten): Zuschnitt, Schenkel, Biegelinien, Innenkonturen und Schneidweg kommen "
               "aus der Abwicklung ([[bleche]]). Konturen über mehrere Wände und freie Formen heißen "
               "<i>Sonderkontur</i> und haben ihren echten Umriss; Vertiefungen bis 0,5 mm sind <i>Gravur</i> statt "
               "Sackbohrung ([[step_messung]]). Gekreuzte Rohre werden nicht mehr als Verbundkern gemessen.",
     "STEP-Import: Kantteile abgewickelt, Sonderkontur mit Umriss, Gravur nach Tiefe ([[step_messung]])."],
    ["0.8.36", "<b>Schweißen als Zusatzarbeit</b>: neue Abrechnung €/h; je Position die Schweißzeit in Sekunden je "
               "Teil eintragen, gerechnet wird Sekunden ÷ 3600 × Stundensatz <i>Schweißen</i> (75 €/h, unter "
               "Stundensätze änderbar), z. B. 48 s = 1,00 € je Teil. Ohne Sekunden warnt der Status "
               "([[zusatzarbeiten_angebot]]). <b>Mindestauftragswert je Angebot ausschaltbar</b>: Häkchen "
               "<i>Mindestauftragswert anwenden</i> in der Karte Kalkulation dieses Angebots, Vorgabe an; der Betrag "
               "bleibt in den Einstellungen ([[mindestpreis]]).",
     "Schweißen nach Zeit (Sekunden je Teil × 75 €/h) und Mindestauftragswert je Angebot abschaltbar "
     "([[zusatzarbeiten_angebot]], [[mindestpreis]])."],
    ["0.8.35", "<b>Bohrungen im Rundrohr</b>: Beim 2D-Schnitt zeigt der Strahl zur Rohrmitte, das Loch ist außen "
               "breiter als in der Konstruktion. Schneidweg-Rechner und STEP-Import rechnen jetzt diese Kontur auf "
               "der Außenhaut (z. B. Ø 10 in 40 × 2: 33,4 statt 31,4 mm), auch für Senkungen. Schräge Bohrungen in "
               "3D bleiben unverändert ([[schneidweg_rechner]]).",
     "Bohrungen im Rundrohr: Schneidweg mit dem breiteren Außenumfang beim 2D-Schnitt ([[schneidweg_rechner]])."],
    ["0.8.34", "<b>Bedienungsanleitung bildlastiger</b>: Teil A und B zeigen zuerst Bilder mit roten Nummern und "
               "Bildfolgen Schritt 1, 2, 3, darunter ein bis zwei Sätze; Einzelheiten stehen kleiner unter "
               "<i>Genauer</i>. Neu die <b>Kurzanleitung</b> (nur Bilder von Teil A und B, <i>Hilfe → Kurzanleitung "
               "(PDF)</i>). „Was ist neu“ zeigt in der Anleitung nur noch die letzten Versionen, alle stehen unter "
               "<i>Hilfe → Was ist neu …</i>.",
     "Anleitung mit mehr Bildern und Kästen „Genauer“, neue Kurzanleitung (<i>Hilfe → Kurzanleitung (PDF)</i>), "
     "alle Neuerungen unter <i>Hilfe → Was ist neu …</i> ([[neu]])."],
    ["0.8.33", "<b>3D nur, wenn die Schnittfläche nicht senkrecht zur Rohroberfläche steht</b>: der STEP-Import misst "
               "je Ende und Kontur den Winkel zwischen Schnittfläche und Oberfläche. Gehrungen, die überall senkrecht "
               "zur Wand stehen (wie ein 2D-Laser schneidet), bleiben auch mit 3D-Häkchen 2D; schräge Langlöcher und "
               "Ausschnitte bekommen „3D prüfen“. Texte im Rohr-Editor und Prüfdialog klargestellt.",
     "3D-Schnitt nur, wenn die Schnittfläche nicht senkrecht zur Rohroberfläche steht; senkrechte Gehrungen "
     "bleiben 2D."],
    ["0.8.32", "<b>Schneidweg-Rechner</b>: neue Konturart <i>Flowdrill</i> (Kernloch-Ø, nur markiert) und Spalte "
               "<i>Gewinde</i> je Bohrung (automatisch, kein Gewinde oder Auswahl). Von Hand eingegebene Gewinde, "
               "Senkungen, Flowdrill und Bohren kommen sofort bestätigt mit Preis je Stück in die Position, so "
               "einfach wie beim STEP-Import ([[schneidweg_rechner]]).",
     "Schneidweg-Rechner: Flowdrill und Gewinde je Bohrung; von Hand Eingegebenes kommt gleich bestätigt in die "
     "Position ([[schneidweg_rechner]])."],
    ["0.8.31", "<b>Mehrere Arbeitsplätze</b>: Name und Kürzel je Benutzer, das Kürzel steht vorn in der "
               "Angebotsnummer (PB-2026-0001); Bearbeiter im Angebotskopf und als Ansprechpartner im Angebots-PDF. "
               "Über einen <b>gemeinsamen Ordner</b> sieht jeder die Angebote der Kollegen (nur ansehen, als Kopie "
               "übernehmen) und alle teilen die Stammdaten; Abgleich beim Start, beim Beenden und mit dem Knopf "
               "<i>Abgleichen</i> ([[mehrere_arbeitsplaetze]]).",
     "Mehrere Arbeitsplätze: Kürzel in der Angebotsnummer, Angebote und Stammdaten über einen gemeinsamen Ordner teilen ([[mehrere_arbeitsplaetze]])."],
    ["0.8.30", "<b>RP-Profile kalkuliert</b>: Schnitt durch den Anschlag mit den Schneiddaten der doppelten Wand, "
               "neue Spalte <i>Zeit je Ecke</i> in den Schneiddaten (RP nach Kontur, Quadrat-/Rechteckrohr 4 Ecken), "
               "Maschinenfelder <i>RP-/Sonderprofile spannbar</i>, <i>Rüstzuschlag Sonderprofil</i> und "
               "<i>Mindestabstand Düse</i> mit Warnungen ([[rp_profile]]). <b>STEP-Import</b>: anderes Profil gewählt "
               "→ WARNUNG mit STEP- und Profilwerten, Anfangs- und Endschnitt werden für das gewählte Profil neu "
               "gerechnet. <b>Schneidweg-Rechner</b>: Schrägschnitt zweiachsig (über Höhe und Breite) und 3D-Enden "
               "aus dem STEP-Import (mehrere Ebenen, Ausklinkung) ([[schneidweg_rechner]]).",
     "RP-Profile werden kalkuliert ([[rp_profile]]); Profilwechsel im STEP-Import; Schneidweg-Rechner mit Schrägschnitt über zwei Achsen ([[schneidweg_rechner]])."],
    ["0.8.29", "<b>Schneller</b>, ohne Änderung an Bedienung und Ergebnissen: große Angebote öffnen und rechnen "
               "deutlich schneller (Angebots-PDF mit Staffeln bei 200 Positionen 5 s statt 22 s, Optimieren 3 s statt "
               "8 s), der Programmstart ist kürzer und die STEP-Messung großer Baugruppen etwa 12 % schneller. Preise, "
               "Zeiten und Messwerte bleiben gleich.",
     "Große Angebote, Programmstart und STEP-Messung deutlich schneller; Bedienung und Ergebnisse unverändert."],
    ["0.8.28", "Anbauteile im Angebot: Spalte <b>Anbauteile</b> der Positionen mit Doppelklick auf <i>Anbauteile "
              "prüfen</i>, Status und Freigabe-Hinweis, Gravur Anbauteile getrennt ausgewiesen (Kalkulation, "
              "Preisaufbau, PDF, Schneidweg-Rechner), Einstellung <i>Prüfzeit je Teil mit unsicher erkannten "
              "Anbauteilen</i>. Im STEP-Prüfdialog die Option <b>Anbauteile nicht ins Angebot übernehmen</b> "
              "(Vorgabe an): angeschweißte eigene Körper einer Baugruppe werden keine eigenen Positionen "
              "([[anbauteile]]).",
     "Anbauteile (Kopfplatten, Muttern …) aus dem STEP-Import getrennt im Angebot ([[anbauteile]])."],
    ["0.8.27", "<b>Fasen im STEP-Import</b>: Fasen an den Rohrenden werden erkannt und nicht gelasert; Hinweis im "
               "Bericht, Länge und Schneidweg an der längsten Stelle (gerader Schnitt). Bisher zählte eine Fase als "
               "Innenkontur und das Ende als „nicht erkannt“.",
     "Fasen an Rohrenden: Hinweis im STEP-Import, gerechnet wird mit der längsten Länge."],
    ["0.8.26", "Gewinde, Senken, Flowdrill und Bohren rechnen nur noch mit einem <b>Preis je Stück</b>, ohne "
               "Zeiten. Die Preise kommen aus den Einstellungen und lassen sich je Position im Fenster Bohrungen "
               "prüfen ändern (Spalten Gewinde [€/Stk] und Arbeit [€/Stk]); Senken, Flowdrill und Bohren sind "
               "jetzt Festpreise (0,40 / 0,60 / 0,40 €), Gewinde ohne Preis bekommen einmalig Zeit × Stundensatz "
               "als Preis ([[bohrungen_pruefen]])."],
    ["0.8.25", "<b>Fenster Material …</b> im Angebot: je Abmessung Querschnitt, Materialeinsatz (Stangen, Meter, kg, €) "
               "und Meterpreis, Werkstoff, Lieferlänge, Oberfläche und Eigen-/Kundenmaterial zum Ändern ([[material_fenster]]). "
               "<b>Kalkulation-PDF</b> übersichtlicher: Anteil der Kostenarten, Materialeinsatz je Abmessung, Spalten "
               "ohne Wert ausgeblendet, Stangenbild am Ende. Handling Kundenmaterial in €/m statt €/kg. "
               "Träger, T- und U-Profile im Angebotstext mit Normbezeichnung (IPE, HEA, HEB, UPN …)."],
    ["0.8.24", "STEP-Import erkennt <b>RP-Profile</b> per Fingerabdruck (Bibliothek und selbst geladene), schneidet "
               "die Doppellage des Anschlags nur einmal, misst <b>Mehrkammerprofile</b> und meldet "
               "<b>Verbundprofile</b> mit Kern ([[step_messung]]). Die Skizze im Schneidweg-Rechner zeigt die "
               "RP-Kontur."],
    ["0.8.23", "Konturen aus der STEP-Datei sitzen an der richtigen Stelle: Bleche bringen jede Innenkontur mit "
               "Lage (x/y im Zuschnitt), Art und Maßen in den Blech-Editor, eine freie Außenkontur als Polygon "
               "([[blech_editor]]). U-, C-, L-, T-Profile, Träger und Flachstahl: jede Kontur auf ihrer Fläche (Steg, "
               "Flansch, Schenkel) mit Versatz quer statt alle auf der ersten Fläche. Quadrat- und Rechteckrohre mit Eckradius: Versatz quer jetzt genau, vorher bis zu "
               "einigen mm daneben; ältere Teile mit <i>STEP neu einlesen …</i> korrigieren ([[schneidweg_rechner]])."],
    ["0.8.22", "Programmierung als Zeit statt fester 8,50 € je Position: <b>5 min je Position + 0,5 min je "
               "Innenkontur</b> × Stundensatz <i>Programmierung</i>, je Position in der Spalte <i>Programmierzeit "
               "[min]</i> änderbar, sichtbar in Zeiten &amp; Arbeitskosten, in den Staffel-Stufen und im "
               "Kalkulation-PDF. Alle Angebote rechnen neu, nur bereits verschickte behalten ihren Betrag "
               "([[stundensaetze]])."],
    ["0.8.21", "<b>Naht der Lieferstange im Angebot</b> statt in den Stammdaten: je Profil und Werkstoff im Fenster "
               "Schweißnaht oder in der Materialanfrage, Vorgabe aus den Teilen, kein Hinweis mehr ohne Eintrag "
               "([[schweissnaht]]); die Materialanfrage nennt die Seite („Schweißnaht auf der Breitseite“) und hat "
               "einen eigenen, immer sichtbaren Knopf <b>Materialanfrage (E-Mail)</b> ([[materialanfrage]])."],
    ["0.8.20", "<b>RP-Profile</b> (Rohre mit Anschlag aus doppeltem Blech): neue Profilform <i>RP-Profil</i>, die "
               "Bibliothek RP-ROHRE ist mitgeliefert, eigene MegaCAD-Makros lassen sich laden, Querschnitt, Gewicht "
               "und Schnittlänge kommen aus der Kontur ([[rp_profile]])."],
    ["0.8.19", "<b>STEP-Import mit 3D</b>: Häkchen <i>3D-Schnittbearbeitung aktivieren</i> im Prüfdialog; "
               "Gehrungen und schräge Bohrungen (mit gemessener Neigung längs/quer) werden in 3D übernommen, ohne "
               "Häkchen erscheint bei schrägen Bohrungen „3D prüfen“."],
    ["0.8.18", "<b>Rohr-Editor mit 3D</b>: Häkchen <i>3D-Schnittbearbeitung aktivieren</i>, je Ende <i>Gehrung in "
               "3D</i>, je Bohrung <i>3D</i> mit Neigung längs und quer (Schnellauswahl ±45°/±30°/0°). Schräge "
               "Bohrungen als Ellipse in Rechnung und Skizze, Winkel über der Maschinengrenze werden begrenzt und "
               "gemeldet."],
    ["0.8.17", "<b>3D-Greifmaß</b> in der Optimierung: hat das letzte Teil einer Stange eine 3D-Bearbeitung am Ende, "
               "bleibt dahinter das Greifmaß der Maschine frei (statt des Greiferrests, wenn größer, nie zusätzlich); "
               "ein Teil ohne 3D kommt nach Möglichkeit ans Ende. Stangenbild und Werkstattpapiere zeigen es mit "
               "<i>3D</i>, ein Teil, das mit dem Greifmaß nicht auf die Stange passt, bekommt einen FEHLER."],
    ["0.8.16", "Grundlage für die <b>3D-Schnittbearbeitung</b> mit geschwenktem Laserkopf: neue Maschinenwerte "
               "<i>3D: Bearbeitung verfügbar</i> (Vorgabe nein), Schwenkwinkel min./max. (±45°), Greifmaß (300 mm), "
               "Zusatzzeit und Faktor. Gehrungen in 3D und schräge Bohrungen rechnen mit den Schneiddaten der "
               "wirksamen Dicke Wand ÷ cos(Winkel); die Kalkulation zeigt die <i>Mehrzeit 3D</i> getrennt. Winkel "
               "über der Grenze werden begrenzt (WARNUNG), 3D auf einer Maschine ohne 3D ist ein FEHLER. Die Eingabe "
               "im Schneidweg-Rechner und das Greifmaß in der Optimierung folgen."],
    ["0.8.15", "Rohr / Profil als neue Position: Profilform vorwählen (die Liste zeigt dann nur Profile dieser Form), "
               "fehlendes Profil direkt mit <b>Neu …</b> anlegen (Form und Maße, Profil-ID, Querschnitt und Gewicht "
               "automatisch) ([[neue_position]]). Schneidweg-Rechner: die längste Seite einer Gehrung steht auf "
               "<b>automatisch</b> und wird aus <i>gekippt über</i> angenommen; die Skizze zeigt sie, die Optimierung "
               "dreht das Teil passend ([[schneidweg_rechner]])."],
    ["0.8.14", "STEP-Import: Rohre mit gegenüberliegenden Langlöchern (z. B. RE 40x30x3) werden wieder gemessen statt "
     "<i>nicht übernehmbar</i>. Nicht übernehmbare Teile zeigt die 3D-Baugruppe <b>magenta</b>, die Zeile nennt Grund "
     "und Hüllmaß, Anklicken hebt das Teil hervor; mit <b>Von Hand nachtragen</b> (Profilform, Profil-ID) wird es "
     "doch übernommen. Die Spalte Art ist bei jeder Zeile wählbar ([[step]]). Ebene flache Teile kommen als <b>Blech</b>, "
     "Flachstahl ist in der Spalte Art wählbar (Einstellung <i>ebene flache Teile vorgeben als</i>); Bleche mit "
     "Senkungen werden erkannt ([[bleche]])."],
    ["0.8.13", "Optimieren mit Gehrungen ineinander und großen Gruppen deutlich schneller (Beispiel 830 Teile mit "
              "Gehrungen: wenige Sekunden statt mehrerer Minuten), gleiche Ergebnisse. Vergleich mit 12 m nur noch, wenn "
              "in den Einstellungen eingeschaltet (Vorgabe aus, [[lieferlaengen]]). Gehrungen ohne angegebene "
              "Richtung werden bei frei drehbaren Teilen trotzdem ineinandergelegt, der Schneidweg-Rechner weist "
              "darauf hin ([[schneidweg_rechner]])."],
    ["0.8.12", "Bohrungen prüfen schlägt wie die Gewinde jetzt auch die Arbeitsschritte vor: <b>Senken</b> für "
               "Senkungen, <b>Flowdrill</b> für Fließlochbohrungen und <b>Bohren</b> für Bohrungen kleiner als 0,7 × "
               "Wandstärke (Laser markiert nur, danach aufbohren). Nach dem Bestätigen stehen sie mit der Anzahl je "
               "Teil als Zusatzarbeit in der Position; die drei Zusatzarbeiten werden einmalig in den Stammdaten "
               "angelegt. Gilt für STEP-Import und Schneidweg-Rechner ([[bohrungen_pruefen]])."],
    ["0.8.11", "STEP-Import: Einstellung <b>STEP-Import: Standardordner</b> (dort startet der Dateidialog, sonst im "
               "zuletzt benutzten Ordner) und gut sichtbares <b>Ablagefeld</b> für Drag &amp; Drop neben "
               "<i>STEP importieren …</i>, im leeren Angebot groß statt der Positionsliste ([[step]])."],
    ["0.8.10", "Zwei Stangenwechselzeiten je Maschine: <b>Stangenwechsel</b> (Vorgabe 24 s) und <b>Stangenwechsel "
              "SN</b> (29 s) für Stangen, auf denen ein Teil eine feste Schweißnaht-Lage hat ([[schweissnaht]])."],
    ["0.8.9", "Selbst angelegte Positionen bekommen ein <b>Vorschaubild</b> vor der Artikelnummer: Rohr/Profil als "
              "Draufsicht mit Gehrungen und Innenkonturen, Blech-/Kantteil als Zuschnitt. Ändert sich das Teil (oder "
              "die STEP-Datei), wird das Bild neu gezeichnet; Doppelklick aufs Bild öffnet den Schneidweg-Rechner "
              "bzw. den Blech-Editor ([[schneidweg_rechner]], [[blech_editor]]). STEP-Import: Bleche wählen "
              "Blech-Werkstoffe statt Rohr-Werkstoffen, neue Blechartikel bekommen den Blech-Richtpreis als EK, und "
              "Doppelklick aufs Bild eines Blechs öffnet den Blech-Editor statt der 3D-Ansicht "
              "([[blechartikel]])."],
    ["0.8.8", "STEP-Import: Spalte <b>Anbauteile</b> im Prüfdialog, Fenster <b>Anbauteile prüfen</b> (Art, "
              "Bearbeitung, Gravur, Bestätigen/Ausschließen, Messung ohne Trennung) und 3D-Vorschau Original/"
              "Rohrgeometrie/Gravurkonturen ([[anbauteile]])."],
    ["0.8.7", "STEP-Import trennt <b>Anbauteile</b> (aufgeschweißte Bolzen, Laschen, Bleche, Muttern, Kopfplatten) "
              "vom Rohr: Profil, Länge und Schneidweg nur vom Rohr, Anbauteile mit Lage und Gravur (Bolzen Kreuz, "
              "sonst Umriss), unsichere Fälle zum Prüfen ([[anbauteile]])."],
    ["0.8.6", "Schneidweg-Rechner und Blech-Editor neu aufgeteilt: Die Konturtabellen haben Platz für mehrere Zeilen "
              "ohne Rollen, Skizze und Ergebnis stehen nebeneinander (Rohr) bzw. rechts (Blech), die Fenster öffnen "
              "bildschirmgroß ([[schneidweg_rechner]], [[blech_editor]])."],
    ["0.8.5", "Staffeln: Im Fenster der Stufe Sätze und Positionen per Häkchen wählen (neue Stufe: alle angehakt). "
              "Blechteile aus dem Blech-Editor je Stufe mit dem EK aus dem Einkauf ab Stückzahl, sonst mit dem "
              "Richtpreis für die Stückzahl der Stufe neu gerechnet ([[staffeln]])."],
    ["0.8.4", "Mausrad ändert keine Werte mehr: Über Zahlen- und Datumsfeldern, Auswahllisten und Schiebereglern "
              "rollt das Rad immer die Seite oder Tabelle, auch in Dialogen und Tabellenzellen ([[mausrad]])."],
    ["0.8.3", "Stangenbild und Werkstattpapiere: Schweißnaht als roter Strich auf jedem Teil, dazu je Stange "
              "Querschnitt mit rotem Punkt und Anzahl gedrehter Teile; Gehrungen ineinander mit grünen Schnittkanten, "
              "gespartes Material einmal je Stange (in Rest und Ausnutzung enthalten); Tooltip je Teil "
              "([[optimieren]])."],
    ["0.8.2", "<b>Neue Position</b> fragt zuerst den Typ: Rohr / Profil öffnet den Schneidweg-Rechner mit Kopfzeile "
              "(Artikel, Profil, Werkstoff, Länge, Stückzahl), Blech / Kantteil den neuen <b>Blech-Editor</b> mit "
              "Abwicklung und Richtpreis als EK ([[blech_editor]]; eigene Blech-Werkstoffe und Blechlaser-Richtwerte "
              "unter Einstellungen, getrennt vom Rohrlaser), Zukaufteil die Schnellanlage, Leere Zeile wie bisher "
              "([[neue_position]])."],
    ["0.8.1", "Schneidweg-Rechner: Werte aus dem STEP-Import auch bei älteren Positionen (Enden, Bohrungen, Konturen, "
              "Gravur), <b>STEP neu einlesen …</b>, Schweißnaht wählbar, Rechteck-/Quadratrohr bei Naht und Seite nur "
              "0°/90°/180°/270°, beschriftete Enden und Maße je Konturart, Maße und Naht in der Skizze, "
              "<b>Zeichnung als PDF …</b>; Doppelklick auf das kleine STEP-Bild öffnet den Rechner "
              "([[schneidweg_rechner]])."],
    ["0.8.0", "Staffelpreise in Stufen: jede Stufe ist ein eigener Auftrag mit Mengen für einen oder mehrere Sätze "
              "und Positionen, gemeinsam optimiert und kalkuliert; gleiche Mengen wie im Angebot ergeben dessen "
              "Preise. Fenster je Stufe mit den Einstellungen des Angebots, Materialpreis €/m je Abmessung und "
              "Mengen ([[staffeln]]); alte Staffeln werden der Größe nach auf Stufen verteilt (Schema 36). "
              "Angebot mit sieben statt zehn Reitern: Zeiten & Arbeitskosten liegt unter Kalkulation, Stangenbild und "
              "Auswertung unter Schnittplan ([[optimieren]]); Übersicht zeigt den Preisaufbau Schritt für Schritt bis "
              "zum Verkaufspreis, Gruppen per Klick aufklappbar; Status, Optimierung und Kalkulation prüfen Positionen "
              "mit einer gemeinsamen Prüffunktion (ungültige Stückzahl mit Nachkommastellen jetzt FEHLER im Status)."],
    ["0.7.0", "Verbesserungen aus dem Prüfbericht: Warnungen bei Satz mit ungleicher Anzahl Sätze, nicht erkannten "
              "Gewinden und negativen Werten; Hinweis zu Staffelpreisen im Angebots-PDF (Kasten); Angebots-PDF schreibt "
              "alle Preisgrundlagen fest und zeigt Abweichungen vom verschickten Stand ([[preise_festschreiben]]); "
              "„Prüfen vor Freigabe“ in der Übersicht; Status gleich nach der Positionsnummer; Kalkulationswerte zu "
              "Beginn zugeklappt; Vorgang (Entwurf, Verschickt, Beauftragt, Abgelehnt), Gültig bis und Filter in der "
              "Angebotsliste ([[angebote]]); Optimierung großer Angebote im Hintergrund mit Abbruch und etwa dreimal "
              "schneller; Herkunft des Materialpreises im Tooltip ([[meterpreis]]); Gewinde aus der Liste im Dialog "
              "Zusatzarbeiten; Fehlerprotokoll Daten/Protokoll/fehler.log. Android-App und Handy-Export entfernt."],
    ["0.6.38", "Datei → Stammdaten fürs Handy exportieren …: Stammdaten und Einstellungen als Datei für die "
               "Android-App (Testversion), dort nur zum Ansehen und für den Stangenrechner ([[datensicherung]])."],
    ["0.6.37", "Mehr Doppelklick: Status führt zur Lösung (Dialog oder Zelle zum Eintragen), Schneidweg/Einstiche/"
               "STEP-Werte öffnen den Schneidweg-Rechner, Artikel mit 3D die 3D-Ansicht, Schnittplan, Stangenbild und "
               "STEP-Protokoll springen zur Position, Kunde im Angebotskopf öffnet den Kunden, Kundenliste zeigt die "
               "Angebote des Kunden ([[doppelklick]])."],
    ["0.6.36", "STEP-Import erkennt Senkungen und Flowdrill (Fließlochbohrungen). Gewinde, Senkungen und Flowdrill "
               "werden per Doppelklick auf die Position im Fenster Bohrungen prüfen bestätigt oder abgelehnt; Senk-Ø "
               "auf Wunsch als Gravur, Flowdrill als Gravur oder Loch Ø0,5 ([[bohrungen_pruefen]])."],
    ["0.6.35", "Materialanfrage: Zuschnitt der 12-m-Stange je Zeile („geschnitten auf …“, abwählbar), Anforderungen "
               "je Werkstoff zum Ankreuzen (Prüfbescheinigung, Herkunft EU, Maßtoleranzen), Betreff und Text als "
               "Vorlage in den Einstellungen, Signatur aus Outlook bzw. eigene Signatur ([[materialanfrage]])."],
    ["0.6.34", "Frachtkosten, Zukauf und Dialoge mit kurzen Hilfetexten (ⓘ mehr, wie [[stammdaten]]); Zukauf-Formular "
               "mit Abschnitten zum Auf- und Zuklappen ([[zukauf]])."],
    ["0.6.33", "Einstellungen übersichtlicher: Hilfetexte kurz mit ⓘ mehr oder nur als Tooltip (Einstellung), "
               "Prüfung OK grau statt grün, Filter „Nur Fehler und Warnungen“ ([[stammdaten]]); Vorgaben als "
               "Karten, bei breitem Fenster zweispaltig ([[vorgaben]])."],
    ["0.6.32", "Startseite als Übersicht (Neues Angebot, zuletzt bearbeitete Angebote, Stammdaten, Sicherung); "
               "Angebotsliste mit farbigem Status und Verkaufspreis ([[angebote]])."],
    ["0.6.31", "Angebot übersichtlicher: Übersicht rechts über die ganze Höhe, Angebotskopf und Fracht klappen auf "
               "eine Zeile zu ([[angebot]]); Kalkulation ohne leere Spalten mit 2 Nachkommastellen "
               "([[kalkulation]]), Schnittplan zeigt Gleiches einmal und gleich die erste Stange, Auswertung "
               "„Alle Teile eingeplant“."],
    ["0.6.30", "Einheitliches Aussehen wie die PDFs (dunkelblaue Akzente, Reiter, Tabellenköpfe mit Linie, "
               "Zebra-Zeilen); Angebot passt auf 1366-px-Bildschirme ([[ausgabe]]); Spaltenköpfe nicht mehr "
               "abgeschnitten, Staffel-Kostentabelle mit lesbarem Zeilenabstand, Nachkalkulation zeigt alle "
               "Stangengruppen."],
    ["0.6.29", "Schneidweg-Rechner: <b>maßstäbliche Skizze</b> mit Draufsicht, Seitenansicht, Ansicht von A und "
               "<b>Abwicklung</b> für alle Profilformen, Bemaßung, Zoom; Konturen anklicken (Zeile wird markiert) "
               "und mit der Maus verschieben. Neu je Kontur: Seite bzw. Winkel, Versatz quer und Abstand für Muster; "
               "neue Konturarten Senkung und Ausklinkung am Ende; Vorlagen speichern und laden, Konturen aus einer "
               "anderen Position kopieren. Der STEP-Import legt die gemessenen Konturen im Rechner ab: sie erscheinen "
               "in Tabelle und Skizze und lassen sich bearbeiten ([[schneidweg_rechner]])."],
    ["0.6.28", "Zeichnungen je Position wieder entfernt (Spalte, Ziehen von Dateien auf eine Position, automatisches "
               "Anhängen der STEP-Datei). Bereits in den Ordner des Angebots kopierte Zeichnungen löscht das Programm "
               "beim ersten Start einmalig; andere Dateien im Ordner bleiben. Die "
               "Materialanfrage per Outlook bleibt, ohne Zeichnungsanhang ([[materialanfrage]])."],
    ["0.6.27", "Reiter Kunden: <b>CSV exportieren</b> und <b>CSV importieren …</b> mit Vorschau, Prüfung, Wahl "
               "„nur neue anlegen“ und Datensicherung vorher ([[kunden_csv]])."],
    ["0.6.26", "STEP-Import von Baugruppen: im Prüfdialog steht eine Datei mit mehreren Teilen als Baugruppe, die "
               "3D-Ansicht zeigt sie zusammengebaut (Lage aus der STEP, gleiche Teile gleiche Farbe), und sie wird "
               "standardmäßig ein Satz (Sätze = 1) ([[step]])."],
    ["0.6.25", "Frachtzonen: <b>Auf Standard zurücksetzen …</b> stellt die Standardzonen und PLZ-Zuordnungen der "
               "Richtwerte wieder her, mit Rückfrage und Datensicherung vorher ([[fracht_zonen_standard]])."],
    ["0.6.24", "Schnittplan, Stangenbild und Werkstattpapiere zeigen Drehung, Schweißnaht und ineinanderliegende "
               "Gehrungen (schräge Kanten), die Auswertung den Vergleich ohne Drehen ([[optimieren]])."],
    ["0.6.23", "Optimierung legt Gehrungen ineinander: Teile werden um die eigene Achse gedreht, nie gewendet; feste "
               "oder unbekannte Schweißnaht sperrt die Drehung ([[optimieren]], [[schweissnaht]])."],
    ["0.6.22", "Gehrungen mit Richtung: der STEP-Import misst, an welcher Seite ein schräges Ende am längsten ist "
               "([[step_messung]]), im Schneidweg-Rechner wird sie gewählt ([[schneidweg_rechner]]). Grundlage für "
               "das Ineinanderlegen von Gehrungen in der Optimierung."],
    ["0.6.21", "Schweißnaht je Position: Vorgabe (keine, feste Position, unbekannt), Winkel am Querschnitt (Blick von "
               "Ende A, 0° oben, 90° rechts), Querschnittslage bei Rechteckrohr, Breit- oder Schmalseite; Profil mit "
               "<i>Naht der Lieferstange</i> und Prüfung im Status ([[schweissnaht]])."],
    ["0.6.20", "Bedienungsanleitung neu gegliedert: Teil A Erste Schritte mit neuem Schnellstart in 10 Schritten "
               "([[schnellstart]]), Teil B Ein Angebot rechnen (jetzt bis zur Nachkalkulation), Teil C Einrichten und "
               "pflegen, Anhang; jedes Kapitel beginnt mit dem Kasten <i>Wofür / Wo im Programm</i>. Aussehen wie das "
               "Angebots-PDF (dunkelblau, ohne Gitterlinien). Ergänzt: Spalten der Zukauf-CSV ([[zukauf_csv]])."],
    ["0.6.19", "Schneiddaten: neue Rohr-Richtwerte für die Faserlaser (dünne Wände höchstens 8.000 mm/min, Stahl mit "
               "N₂ bis 4 mm, T11 erst ab 3 mm schneller als LT7); unveränderte Richtwert-Zeilen älterer Dateien "
               "werden einmalig angepasst ([[stammdaten]]). Konturklassen zählen zusätzlich nach Hüllmaß ÷ "
               "Wandstärke (klein bis 3 ×, mittel bis 8 × Wand, je Maschine änderbar), die strengere Klasse gilt; "
               "Kontur kleiner als 0,7 × Wand gibt eine Warnung (ggf. nur gravieren und aufbohren) ([[konturklassen]])."],
    ["0.6.18", "Schneiddaten: Schaltfläche <i>Auf Standard zurücksetzen …</i> stellt für eine Maschine oder alle "
              "(T03, T11, LT7) nach Sicherheitsabfrage die mitgelieferten Richtwerte wieder her "
              "([[schneiddaten_standard]])."],
    ["0.6.17", "Werkstattpapiere, Kalkulation und Nachkalkulation im Design des Angebots ([[ausgabe]]): Firmenname, "
              "kleines Logo, Listen ohne Gitter. Werkstattpapiere mit Kästchen zum Abhaken und fetter Kopfzeile je "
              "Stangenmuster; Kalkulation mit Kennzahlen oben und ohne Kostenarten mit 0,00 €; Nachkalkulation mit "
              "Kennzahlen und farbigen Abweichungen (rot = teurer, grün = günstiger)."],
    ["0.6.16", "Angebots-PDF moderner: ohne Gitterlinien, Briefkopf mit Firmenlogo (neue Einstellung <i>Firmenlogo</i>), "
              "Anschrift links und Angebotsdaten rechts, Summenblock mit Gesamtbetrag, Konditionen zeilenweise. "
              "Staffelpreise stehen jetzt in ihrer Position („Ab 50 Stk. je“) statt als eigene Tabelle; einmalige "
              "Rüstkosten sind im Stufenpreis enthalten ([[ausgabe]], [[staffeln]])."],
    ["0.6.15", "Lieferlängen: Die Restlänge einer zugeschnittenen 12-m-Stange kommt an die letzte Stange (bis zur "
              "Beladelänge), das spart einen Sägeschnitt; sonst ist sie Abfall. Der Vergleich öffnet sich groß über den "
              "Knopf <i>12-m-Lösung ansehen …</i> im Reiter Auswertung, den es nur bei einer sinnvollen Lösung gibt. "
              "Händler-Mehrlänge im Materialpreis (Einstellungen, Vorgabe +50 mm je Stange bis 6,5 m, +100 mm "
              "darüber), nicht in der Längenplanung. Neue Einstellung <i>Puffer je "
              "zugeschnittener Stange</i> (Vorgabe 50 mm): Zuschnitte nicht mehr auf den Millimeter genau. Material "
              "zählt weiter die ganzen Lieferstangen, nach Länge auf alle Teile verteilt ([[lieferlaengen]])."],
    ["0.6.14", "Spaltenbreite und Zeilenhöhe automatisch in allen Tabellen: Spalten passend zum Inhalt (Höchstbreite), "
              "lange Texte umgebrochen bis drei Zeilen, kurze Zeilen bleiben einzeilig; von Hand gezogene Spalten "
              "bleiben ([[angebot]])."],
    ["0.6.13", "Maschinen: neues Feld <i>Min. Stangenlänge Zuschnitt</i> (Vorgabe 2.500 mm, auch für vorhandene "
              "Maschinen). Beim Zuschnitt einer 12-m-Stange wird keine Stange kürzer, damit die automatische "
              "Stangenladung sie nimmt; eine kürzere wird verlängert, der Mehrbedarf ist Verschnitt ([[lieferlaengen]])."],
    ["0.6.12", "Windows-Tastenkürzel: Strg+Z/Strg+Y (Rückgängig/Wiederholen im Angebot, bis 100 Schritte), "
              "Strg+C/V/X für Zellen und Blöcke aus Excel, Entf löscht mit Rückfrage, Strg+N, Strg+F, Strg+S, Strg+P, "
              "Strg+I, F5, F9, Strg+W, Strg+Tab, Strg+Bild↓/↑; neue Menüs Bearbeiten und Ansicht, "
              "<i>Hilfe → Tastenkürzel …</i> ([[rueckgaengig]], [[tastenkuerzel]])."],
    ["0.6.11", "Lieferlängen: Schnittplan, Stangenbild und Werkstattpapiere zeigen zugeschnittene 12-m-Stangen als "
              "ihre Stücke (eigene Stangen mit Endbeschnitt und Greiferrest), ohne den Zuschnitt; gerechnet wird weiter "
              "mit den 12-m-Stangen ([[lieferlaengen]])."],
    ["0.6.10", "Zeichnungen je Position (seit 0.6.28 wieder entfernt) und <b>Material per Outlook anfragen</b>: Stangenbedarf aus der "
              "Optimierung, Lieferant und E-Mail-Adresse, gesendet wird nur in Outlook ([[materialanfrage]])."],
    ["0.6.9", "Frachtkosten: <b>Richtwerte laden</b> für den Palettenversand (Marktpreise 10/2026 + 10 % Puffer, "
              "Maut und Diesel enthalten, Zonen nach Entfernung vom Versandort, schwere Paletten, Langgut, Inseln; "
              "[[fracht_richtwerte]]). Automatische Fracht übernimmt die volle PLZ des Kunden."],
    ["0.6.8", "Online-Update: erscheint zwischen Suche und Update eine noch neuere Version, nimmt das Programm diese "
              "statt mit <i>HTTP Error 404</i> abzubrechen; die Pakete des vorigen Stands bleiben länger liegen "
              "([[updates]])."],
    ["0.6.7", "Übersicht im Angebot ohne die Kennzahlen Gesamtlänge und Stangen, weil diese Summen über "
              "verschiedene Abmessungen nicht aussagekräftig sind. Stangen je Abmessung zeigt das Stangenbild."],
    ["0.6.6", "Schneidweg-Rechner ausgebaut: Gehrung bei allen Profilen über Höhe oder Breite, Ausklinkung "
              "(Sattelschnitt) auf ein Rundrohr, Polygon aus Koordinaten, Skizze mit Lage der Konturen, "
              "Gewinde-Vorschlag aus den Bohrungen ([[schneidweg_rechner]])."],
    ["0.6.5", "Mindestpreis: gilt immer aus den Einstellungen für alle Angebote, auch ältere (dort stand bisher 0 €), "
              "und wird bei jeder Änderung geprüft; im Angebot nicht mehr änderbar ([[mindestpreis]]). Zuschlag "
              "Material und Zuschlag Fertigung ebenso nur noch in den Einstellungen, dort einmalig auf 0 % gesetzt."],
    ["0.6.4", "Vorschub Gravur der Richtwerte auf 3.000 mm/min gesenkt (bisher Faser 15.000, CO₂ 10.000); ältere "
              "Datendateien werden einmalig angepasst, von Hand geänderte Werte bleiben ([[stammdaten]])."],
    ["0.6.3", "Schneidweg-Rechner für Teile ohne STEP-Datei: Gehrungen, Bohrungen, Langlöcher, Rechtecke, Schlitze "
              "und sonstige Konturen eingeben, Schneidweg, Einstiche, Konturklassen und Schneidzeit sofort sehen und "
              "in die Position übernehmen (Rechtsklick auf die Position, [[schneidweg_rechner]])."],
    ["0.6.2", "Kundenmaterial: Spalte <i>Material</i> je Position (Eigenmaterial / Kunde beigestellt), Vorgabe im "
              "Angebotskopf, eigene Stangengruppe ohne Materialkosten, optional Handling je kg, Hinweis mit "
              "Stangenbedarf im Angebot ([[kundenmaterial]])."],
    ["0.6.1", "Angebot: Kalkulationswerte, die von den Einstellungen abweichen, sind gelb markiert und aufgelistet "
              "(auch Stundensätze), Preisänderung nach jeder Änderung in der Statuszeile, <i>Vorgaben aus "
              "Einstellungen</i> nennt jede Änderung ([[angebot]])."],
    ["0.6.0", "Angebot: eigene <b>Lieferzeit</b> je Angebot (Arbeitstage, Wochen, KW, Datum oder Text, [[lieferzeit]]), "
              "<b>Ihre Anfrage / Zeichen</b> im Kopf und im PDF, <b>Mindestpreis</b> 200 € netto: Stückpreise "
              "werden anteilig angehoben, Hinweis „Mindestauftragswert“ ([[mindestpreis]])."],
    ["0.5.17", "Angebot: Der Angebotstext jeder Position steht zeilenweise (Profil, Länge, Material, Oberfläche, je "
               "Zusatzarbeit und Zukaufteil eine Zeile <i>inkl. …</i>) statt hintereinander ([[ausgabe]])."],
    ["0.5.16", "Programm und Setup sind mit dem eigenen Zertifikat <i>Patrick Brundiers</i> signiert; neue Datei "
               "<i>Windows-Vertrauen-einrichten.cmd</i> (ohne Adminrechte) gibt Setup/ZIP frei und trägt das Zertifikat "
               "ein, Anleitung zu „Zulassen“ vor dem Entpacken ([[windows_warnungen]], [[windows_vertrauen]])."],
    ["0.5.15", "Angebot: Spalte <i>Materialpreis [€/m]</i> zeigt den berechneten Meterpreis grau und lässt ihn wie die "
               "Schneidzeit günstiger oder teurer überschreiben ([[meterpreis]])."],
    ["0.5.14", "Lieferlängen: 6-m- gegen 12-m-Stangen vergleichen, 12 m nur als vom Lieferanten geschnittene "
               "Werkstücke bis zur Beladelänge, Übernahme per Klick, Staffeln wählen selbst ([[lieferlaengen]])."],
    ["0.5.13", "Maschinen T03 (Trumpf, CO₂ 3,2 kW), T11 (Trumpf, Faser 4 kW) und LT7 (Adige, Faser 3 kW) statt RL-1/RL-2, "
               "neue Schneiddaten-Richtwerte je Laser, Prüfspalte warnt bei unplausiblen Vorschüben; beim Umbenennen "
               "einer Maschine ziehen Angebote und Standard-Maschine mit ([[stammdaten]])."],
    ["0.5.12", "Schneidzeit mit der größten Wandstärke (neues Feld <i>Wandstärke max.</i> bei den Profilen, "
               "Normprofile mit der Flanschdicke) und mehrere Einstiche je Anfangs-/Endschnitt: I-/H-Träger und "
               "U-Profil 4, T-Profil 2 ([[optimieren]])."],
    ["0.5.11", "Einkaufspreis fehlender Zukaufteile direkt im Angebot eintragen (<i>Zukaufteile … → EK eintragen …</i>), "
               "gespeichert ab der Stückzahl der Position ([[zukauf_positionen]])."],
    ["0.5.10", "Automatische Fracht rechnet nach jeder Änderung am Angebot sofort neu und schreibt den Betrag ins "
               "Feld Frachtkosten ([[fracht_angebot]])."],
    ["0.5.9", "STEP-Import: bei Grenzfällen ist die Art im Prüfdialog wählbar (Flachstahl oder Blech, Profil oder "
              "Kantteil) ([[step]])."],
    ["0.5.8", "Fracht automatisch berechnen mit Ziel-PLZ und Land, zweistellige Postleitzahlen in den Frachtzonen "
              "([[fracht]]). STEP-Import: Standard-Werkstoff für Rohre und Profile, Stückzahl 1 bei Einzelteilen."],
    ["0.5.7", "Konturklassen: Konturliste je Position, Neu-Einteilung, Enden nach Hüllmaß ([[konturklassen]])."],
    ["0.5.6", "Konturklassen: Zeitanteile je Klasse, Warnung bei widersprüchlichen Konturwerten."],
    ["0.5.4 – 0.5.5", "Bleche aus dem STEP-Import werden eigene Zukaufteil-Positionen ([[zukauf_positionen]])."],
    ["0.5.3", "Online-Update ohne Anmeldung aus einem öffentlichen Update-Verzeichnis ([[updates]]); Blechartikel "
              "mit Maßen, Werkstoff und fehlendem Einkaufspreis ([[blechartikel]])."],
    ["0.5.2", "STEP-Import erkennt I-/H-Träger und T-Profile."],
    ["0.5.1", "STEP-Import erkennt Bleche und grenzt sie vom Flachstahl ab ([[bleche]])."],
    ["0.5.0", "Preise je Angebot festschreiben ([[preise_festschreiben]]), Schnittmuster-Optimierung, "
              "kaufmännische Rundung im Angebot."],
]
