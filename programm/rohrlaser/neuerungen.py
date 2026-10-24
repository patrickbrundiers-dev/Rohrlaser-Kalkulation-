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
    ["0.9.65", "<b>Teile-Editor: am 3D-Modell bearbeiten</b> wie im CAM-Programm. Die gewählte Kontur hat Pfeile "
               "zum Ziehen (längs und quer um den Umfang, auch auf die Nachbarfläche), das Maß steht dabei am "
               "Mauszeiger; <b>Fangen</b> auf Raster (5 mm, Rundrohr 15°), Teilmitte und Flächenmitte, Alt = frei. "
               "<b>Maße am Modell</b> (ab A, bis B, zur Nachbarkontur) mit Doppelklick ändern, Rechnungen wie L/2 gehen. "
               "<b>Schnittebenen</b> an den Enden mit Griff für den Gehrungswinkel. <b>Pfeiltasten</b> verschieben um "
               "den Rasterschritt (Umschalt ×10). <b>Rechtsklick</b>: Duplizieren, Spiegeln, Gegenseite, Auf "
               "STEP-Wert, Entfernen, Messen von hier. <b>Darstellung</b> Schattiert, Mit Kanten, Durchsichtig und "
               "<i>nur Gewähltes</i>; Gewähltes ist grün. Der Editor öffnet immer maximiert ([[editor_griffe]]).",
     "Teile-Editor: Konturen und Gehrung direkt am 3D-Modell ziehen, Maße am Modell, Rechtsklick-Menü, "
     "Darstellungsarten ([[editor_griffe]])."],
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
