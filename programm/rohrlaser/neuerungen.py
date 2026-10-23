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
