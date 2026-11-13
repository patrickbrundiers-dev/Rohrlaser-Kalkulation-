"""Kurze Hilfe im Programm (Reiter Hilfe, P8). Ein Text, damit das Programm ohne die Anleitung der Kalkulation
auskommt."""
from . import NAME, VERSION, laufzeit
from . import daten as D

ABSCHNITTE = (
    ("Wofür ist das Programm?",
     "Es zeigt, wie voll die Maschinen sind und ob die Aufträge ihren Liefertermin halten. Je Auftrag führt es "
     "Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche "
     "Laufzeit. Es läuft für sich allein, ohne die Kalkulation."),
    ("Auftrag anlegen",
     "Reiter <b>Aufträge</b>, <b>Neuer Auftrag …</b>. Auftragsnummer, Maschine und kalkulierte Laufzeit sind "
     "Pflicht. Ohne Liefertermin wird der Auftrag hinter allen anderen eingeplant. Doppelklick auf eine Zeile "
     "öffnet den Auftrag zum Ändern."),
    ("Laufzeit eingeben",
     "Jede Schreibweise geht: <b>1 Stunde 30 Minuten</b>, 1 Std 30 Min, 1 h 30 min, 1h30, <b>1:30</b>, "
     "<b>90 Minuten</b>, 90 min, 1,5 h. Unter dem Feld steht sofort, wie die Eingabe verstanden wurde. Eine ganze "
     "Zahl ohne Einheit gilt als Minuten, eine Kommazahl als Stunden. Beides und die Anzeige (1 h 30 min, 1:30 h, "
     "1,50 h, 90 min) lassen sich in den Einstellungen umstellen."),
    ("Start, Stopp und fertig melden",
     "<b>Start</b> lässt für den gewählten Auftrag die Uhr laufen, derselbe Knopf heißt dann <b>Stopp</b>. Die "
     "gestoppte Zeit steht in der Spalte Status. <b>Fertig melden …</b> (Taste F8) fragt die tatsächliche Laufzeit "
     "ab und schlägt die gestoppte Zeit vor. Ein fertiger Auftrag belegt die Maschine nicht mehr; <b>Wieder "
     "öffnen</b> nimmt die Fertigmeldung zurück."),
    ("Fertig melden mit Suche und Uhrzeit",
     "<b>Fertig melden …</b> geht auch, ohne den Auftrag erst in der Liste zu suchen: Im Feld oben die "
     "Auftragsnummer oder den Kunden tippen, ein Teil genügt. Darunter stehen die offenen Aufträge, die passen; die "
     "Pfeiltasten wählen, die <b>Eingabetaste</b> übernimmt den Treffer. Dann die tatsächliche Laufzeit prüfen und "
     "mit der Eingabetaste fertig melden. <b>Fertig melden und nächster</b> lässt das Fenster offen und springt "
     "zurück in die Suche. Ist in der Liste schon ein offener Auftrag gewählt, ist er eingetragen. Läuft die Uhr "
     "noch, hält die Fertigmeldung sie an. Neben <b>Fertig am</b> steht die <b>Uhrzeit</b>, vorbelegt mit jetzt; "
     "sie steht danach in der Spalte Fertig am und in der Tagesansicht unter Heute tatsächlich."),
    ("Reihenfolge",
     "Normal laufen die Aufträge einer Maschine nach Liefertermin. Über <b>Reihenfolge</b> lässt sich der gewählte "
     "Auftrag <b>vorziehen</b> (läuft als Nächstes) oder <b>zurückstellen</b> (läuft zuletzt). <b>Wieder nach "
     "Liefertermin</b> hebt das auf. Ein Auftrag, dessen Uhr läuft, steht immer vorn."),
    ("Löschen und Papierkorb",
     f"<b>Löschen</b> legt den Auftrag ohne Rückfrage in den Papierkorb. Unter <b>Mehr → Papierkorb …</b> lässt er "
     f"sich {D.PAPIERKORB_TAGE} Tage lang zurückholen, danach wird er endgültig entfernt."),
    ("Auslastung lesen",
     "Je Maschine eine Zeile mit Wochenbalken: Der Rahmen ist die Kapazität der Woche, die Füllung sind die "
     "eingeplanten Aufträge (grün, ab 80 % gelb, über 100 % rot). Grau links stehen die tatsächlichen Stunden der "
     "letzten vier Wochen aus den Fertigmeldungen. Die Aufträge laufen ab heute nacheinander durch die freien "
     "Stunden; was nicht in eine Woche passt, rutscht in die nächste. Die Plantafel darunter zeigt jeden Auftrag "
     "als Block, das Dreieck ist sein Liefertermin. Roter Rahmen: Termin nicht zu halten. Oranger Rahmen: knapp. "
     "Ein Klick auf einen Wochenbalken zeigt rechts die Aufträge dieser Woche. Oben rechts blenden die Knöpfe "
     "<b>Wochenbalken</b> und <b>Liste rechts</b> diese Teile aus, dann hat die Plantafel mehr Platz; der Platz "
     "merkt sich die Wahl. Wie gerechnet wird, steht im Tooltip der roten Terminrisiko-Zeile, die Zeichen der "
     "Plantafel im Tooltip von „Plantafel ⓘ“."),
    ("Terminauskunft",
     "<b>Terminauskunft …</b> im Reiter Auslastung: Laufzeit eingeben, das Programm nennt je Maschine, wann ein "
     "neuer Auftrag fertig wäre, wenn er hinter allen offenen Aufträgen läuft. Gespeichert wird dabei nichts."),
    ("Arbeitsliste für die Werkstatt",
     "<b>Arbeitsliste PDF …</b> schreibt je Maschine eine Seite mit den Aufträgen in der geplanten Reihenfolge, "
     "mit Laufzeit, Start, Fertig-Datum, Liefertermin und einem Feld zum Abhaken. <b>PDF …</b> daneben druckt "
     "Wochenbalken, Plantafel und die Aufträge mit Terminrisiko."),
    ("Soll und Ist",
     "Vergleicht die kalkulierte mit der tatsächlichen Laufzeit, je Maschine und je Auftrag, mit Abweichung in "
     "Zeit und Prozent. Abweichungen ab 10 % sind farbig. Die Liste gibt es als CSV und PDF."),
    ("Maschinen, Arbeitszeit, Sperrtage",
     "Reiter <b>Einstellungen</b>; jede Änderung gilt sofort. Je Maschine: Stunden je Tag (Montag bis Freitag), "
     "aktiv oder nicht und <b>Sperrtage</b> für Wartung oder Ausfall (z. B. 24.11.2026-25.11.2026; 02.12.2026). "
     "Für alle Maschinen: Stunden am Samstag, Nutzungsgrad, Feiertage des Bundeslands, Betriebsruhe und der "
     "Vorlauf zwischen „Laser fertig“ und Liefertermin."),
    ("Benutzer und Rechte",
     "Reiter <b>Einstellungen</b>, Gruppe <b>Benutzer und Rechte</b>. Solange dort niemand eingetragen ist, darf "
     "jeder Platz alles. Mit dem ersten Benutzer gelten die Rechte für alle Plätze: Das Programm erkennt den "
     "Benutzer am Windows-Anmeldenamen, eine eigene Anmeldung gibt es nicht. <b>Verwaltung</b> darf alles, "
     "<b>Planung</b> legt Aufträge an, ändert und löscht sie, <b>Werkstatt</b> startet, stoppt und meldet fertig, "
     "<b>Nur lesen</b> sieht an und druckt. Wer nicht eingetragen ist, bekommt die Rolle aus <i>Alle anderen</i>. "
     "Name und Rolle stehen unten rechts im Fenster. Die Rechte schützen vor Versehen, nicht vor Absicht: Wer die "
     "Datenbankdatei mit einem anderen Werkzeug öffnet, umgeht sie."),
    ("Änderungsverlauf",
     "<b>Mehr → Änderungsverlauf …</b> zeigt für den gewählten Auftrag, wer wann was angelegt, geändert, "
     "gestartet, gestoppt oder fertig gemeldet hat."),
    ("Auftrag auf mehreren Maschinen",
     "Läuft ein Auftrag nicht auf einer Maschine allein, zum Beispiel eine Abmessung nur auf der T11 und der Rest "
     "auf der LT7, setzt du im Auftrag das Häkchen <b>Auftrag auf mehrere Maschinen aufteilen</b>. Statt Maschine "
     "und Laufzeit erscheint eine Tabelle: je Zeile eine Maschine mit ihrer Laufzeit. Die Teile laufen "
     "gleichzeitig und werden einzeln gestartet und fertig gemeldet; bei mehreren offenen Teilen fragt der Knopf, "
     "welches gemeint ist. Fertig ist der Auftrag, wenn das letzte Teil fertig ist. In der Liste steht er als eine "
     "Zeile, bei Maschine zum Beispiel <i>T11 + LT7</i>."),
    ("Arbeitsgänge",
     "<b>Einstellungen → Arbeitsgänge → Mehrere Arbeitsgänge je Auftrag verwenden</b> schaltet sie ein (Vorgabe: "
     "aus). Dann lässt sich ein Auftrag in Arbeitsgänge teilen, die nacheinander laufen, zum Beispiel Laser, "
     "Entgraten, Verzinken. Jeder Arbeitsgang hat seinen Arbeitsplatz und seine Laufzeit. Weitere Arbeitsplätze "
     "legst du bei den Maschinen an, mit Stunden je Tag wie eine Maschine. <b>Fremdarbeit</b> belegt keinen "
     "Arbeitsplatz: Du gibst nur die Dauer in Arbeitstagen an. Für wiederkehrende Abläufe gibt es <b>Vorlagen</b>; "
     "im Auftrag übernimmst du eine Vorlage und änderst sie nach Bedarf. Ein Häkchen bei <i>gleichzeitig mit Zeile "
     "davor</i> lässt zwei Zeilen nebeneinander laufen.<br><br>"
     "<b>So rechnet das Programm:</b> Ein Arbeitsgang beginnt erst, wenn der davor fertig ist. Mit Übergangszeit 0 "
     "kann er am selben Tag weitergehen, sonst nach so vielen Arbeitstagen, wie beim Arbeitsplatz als "
     "<i>Übergangszeit davor</i> steht (Transport, Abkühlen, Liegezeit). Fremdarbeit zählt ab dem Ende des "
     "Arbeitsgangs davor; ist sie mit Start als weggegeben gemeldet, ab diesem Tag. Die <b>Durchlaufzeit</b> sind "
     "die Arbeitstage vom Start des ersten bis zum Ende des letzten Arbeitsgangs. Das <b>Terminrisiko</b> rechnet "
     "mit dem Ende des letzten Arbeitsgangs plus Vorlauf.<br><br>"
     "<b>Melden:</b> Start, Stopp und Fertig melden gelten immer für den Arbeitsgang, der an der Reihe ist. Die "
     "Spalte Status zeigt, wie viele fertig sind und welcher jetzt läuft. <i>Soll und Ist</i> zählt je Maschine "
     "jeden Arbeitsgang an seinem Arbeitsplatz. Die Arbeitsliste hat für jeden Arbeitsplatz eine Seite. Aufträge "
     "ohne Arbeitsgänge bleiben, wie sie sind."),
    ("Werkstatt-Ansicht",
     "Für das Tablet oder den Rechner in der Halle: Der Knopf <b>Werkstatt-Ansicht</b> rechts oben neben den Reitern "
     "zeigt eine große Ansicht. Oben wählst du die Maschine, darunter stehen ihre Aufträge in der geplanten "
     "Reihenfolge; was gerade läuft, steht ganz oben. Die großen Knöpfe <b>Start</b>, <b>Stopp</b> und "
     "<b>Fertig</b> gelten für den gewählten Auftrag. Ein Gerät genügt für alle Maschinen. Mit <i>An diesem Platz "
     "immer so starten</i> öffnet das Programm an diesem Rechner gleich in der Werkstatt-Ansicht und merkt sich die "
     "Maschine; <i>Vollbild</i> blendet alles andere aus, <i>Zur Planung</i> führt zurück. Melden darf, wer die "
     "Rolle Werkstatt, Planung oder Verwaltung hat."),
    ("Grund bei Stopp",
     "Beim Knopf <b>Stopp</b> fragt das Programm mit einem Klick nach dem Grund: Störung, Material fehlt, Rüsten, "
     "Pause oder anderer Auftrag. Der Grund steht danach beim Auftrag und im Änderungsverlauf. Im Reiter <b>Soll und "
     "Ist</b> zeigt die Tabelle <i>Unterbrechungen nach Grund</i>, wie oft und wie lange aus welchem Grund "
     "gestanden wurde. Als Stillstand zählt die Zeit bis zum Weiterlaufen am selben Tag. Die Liste der Gründe und "
     "die Frage selbst stellst du unter <b>Einstellungen → Grund bei Stopp</b> ein."),
    ("Kennzahlen",
     "Der Reiter <b>Kennzahlen</b> zeigt auf einen Blick: <b>Termintreue</b> (Anteil der Aufträge, die am "
     "Liefertermin oder früher fertig gemeldet wurden), <b>verspätete Aufträge</b> (offen und Liefertermin vorbei, "
     "oder laut Plan zu spät), die Abweichung der <b>Kalkulation</b> und die <b>Auslastung</b> der nächsten vier "
     "Wochen. Die Balken zeigen die Termintreue je Monat, darunter steht, wie weit die Kalkulation in dem Monat "
     "danebenlag. Ein Doppelklick auf einen verspäteten Auftrag zeigt ihn im Reiter Aufträge."),
    ("Material da ab",
     "Ist das Material für einen Auftrag noch nicht da, setzt du im Auftrag das Häkchen <b>Material da ab</b> und "
     "wählst den Tag. Vor diesem Tag plant das Programm den Auftrag nicht ein, andere Aufträge nutzen die Zeit "
     "davor. In der Liste steht <i>wartet auf Material</i>. Sobald der Auftrag gestartet wird oder der Tag "
     "erreicht ist, gilt das Material als da. In einer CSV-Datei heißt die Spalte <i>Material da ab</i>."),
    ("Übergabe automatisch erkennen",
     "Unter <b>Einstellungen → Übergabe aus der Kalkulation</b> wählst du einen Ordner. Speichert die Kalkulation "
     "dort eine Übergabedatei, erscheint nach etwa einer Minute über der Auftragsliste eine Zeile mit <b>Einlesen "
     "…</b>. Das Programm zeigt, wie viele Aufträge neu oder geändert sind, und übernimmt erst nach deiner "
     "Bestätigung. <i>Nicht einlesen</i> lässt die Datei liegen, bis die Kalkulation sie neu schreibt. Die Zeile "
     "sieht, wer Aufträge anlegen darf (Planung, Verwaltung)."),
    ("Wartung und Bediener",
     "Unter <b>Einstellungen → Wartung und Bediener</b> trägst du Wartungen je Maschine ein: einmalig an einem Tag, "
     "alle X Wochen oder alle X Laufstunden (gezählt aus den Fertigmeldungen und der geplanten Arbeitszeit), jeweils "
     "mit Dauer. An dem Tag hat die Maschine entsprechend weniger Stunden, die Plantafel zeigt den Tag grau "
     "schraffiert mit <i>Wartung</i>, überfällige rot. Mit <b>Erledigt</b> zählt eine wiederkehrende Wartung ab "
     "diesem Tag neu.<br><br>Darunter stehen die <b>Bediener</b>: welche Maschinen jemand bedienen darf, ob er "
     "Einrichter ist und wann er fehlt (Urlaub, krank, z. B. 24.11.2026-28.11.2026). Je Tag bekommt jede Schicht "
     "einer Maschine einen anwesenden Bediener. Fehlt er, läuft die Maschine an dem Tag entsprechend weniger, die "
     "Plantafel zeigt den Tag orange mit <i>Bediener</i>, und die Glocke warnt 5 Arbeitstage vorher (auch, wenn "
     "kein Einrichter da ist). Maschinen, bei denen niemand eingetragen ist, rechnen wie bisher. Beides lässt sich "
     "unter Funktionen ausschalten."),
    ("Schnittstelle zur Kalkulation",
     "Ab Version 2.8 schickt die Kalkulation je beauftragtem Angebot eine Auftragsdatei in den Übergabe-Ordner, "
     "mit allen Positionen, Zusatzarbeiten (Gewinde, Schweißen, Verzinken …) und deren Zeiten, Material und "
     "<i>Material da ab</i>. Die Zeit für den Laser ist Laserzeit plus Rüsten, jede Zusatzarbeit wird ein eigener "
     "Arbeitsgang mit der Zeit aus der Kalkulation; nur wo keine Zeit kommt, rechnet das Programm mit seinen "
     "Richtzeiten. Ändert sich das Angebot, kommt eine neue Freigabe: Zeiten, Material und Termin werden "
     "übernommen, aber was die Werkstatt schon getan hat, bleibt (Maschine nach Umplanen, gelaufene Zeit, fertig "
     "gemeldete Arbeitsgänge, fester Platz, Reihenfolge). Eine ältere Freigabe wird übergangen. Wird der Auftrag "
     "in der Kalkulation storniert, kommt er in den Papierkorb; ist er schon gelaufen, bleibt er und du bekommst "
     "einen Hinweis.<br><br>In die andere Richtung schreibt das Programm einmal am Tag und nach jeder "
     "Fertigmeldung <i>Rueckmeldung.csv</i> in denselben Ordner: Ist-Zeiten je Auftrag und Arbeitsgang, freie "
     "Stunden je Maschine für 8 Wochen und den frühesten Fertig-Tag für einen neuen Auftrag mit 1, 4, 8 oder 16 "
     "Stunden. Ausschalten unter Einstellungen → Ansicht und Felder → Funktionen → <i>Rückmeldung an die "
     "Kalkulation</i>."),
    ("Plantafel lesen",
     "Die Plantafel im Reiter <b>Auslastung</b> zeigt je Maschine eine Zeile und jeden Auftrag als Balken mit "
     "Auftragsnummer, Kunde und Restlaufzeit. Mit <b>1 Woche, 2 Wochen, 4 Wochen, Alles</b> wählst du, wie viele "
     "Tage zu sehen sind; den Rest erreichst du mit dem Rollbalken, die Maschinen bleiben links stehen. <b>Farbe "
     "nach</b> färbt die Balken nach Terminrisiko (grün im Termin, orange knapp, rot zu spät), nach Kunde oder nach "
     "Status; die Legende steht daneben. Im Balken: ▶ läuft, ❚❚ gestoppt mit Grund, schraffiert = wartet auf "
     "Material, weißer Punkt = fester Platz, helle Leiste unten = schon erledigter Anteil. Das Dreieck am "
     "Zeilenfuß ist der Liefertermin, eine gestrichelte Linie zeigt die Verspätung. Der Streifen über jeder Zeile "
     "zeigt, wie voll der Tag ist. Die Maus über einem Balken zeigt alle Angaben; ein Klick hebt alle Teile dieses "
     "Auftrags hervor, Arbeitsgänge sind mit einer gepunkteten Linie verbunden. Ansicht und Farbe merkt sich der "
     "Platz."),
    ("Plantafel: mit der Maus verschieben",
     "Im Reiter <b>Auslastung</b> ziehst du einen Auftrag in der Plantafel mit der Maus auf einen anderen Tag oder "
     "in die Zeile einer anderen Maschine. Er liegt dann <b>fest</b>: Er beginnt nicht vor diesem Tag und wird vor "
     "allen anderen eingeplant. Die anderen Aufträge ordnen sich davor und dahinter weiter nach Liefertermin. Ein "
     "weißer Punkt im Balken zeigt den festen Platz, in der Liste steht <i>fest ab …</i>. Über der Tafel steht "
     "danach, ob dadurch ein anderer Termin kippt. <b>Verschieben rückgängig</b> nimmt den letzten Zug zurück, "
     "<b>Reihenfolge → Festen Platz lösen</b> im Reiter Aufträge ordnet einen Auftrag wieder nach Liefertermin "
     "ein."),
    ("Was wäre, wenn …",
     "<b>Auslastung → Was wäre, wenn …</b> rechnet auf Probe: Samstagsarbeit, Zusatzstunden für eine Maschine in "
     "einer Woche oder ein Auftrag auf einer anderen Maschine. Die Tabelle zeigt, welche Aufträge dadurch früher "
     "oder später fertig werden und wie sich das Terminrisiko ändert. Gespeichert wird nichts, bis du "
     "<b>Übernehmen</b> drückst. Zusatzstunden gelten für die gewählte Woche und verteilen sich auf ihre "
     "Arbeitstage."),
    ("Ausweichmaschine",
     "Bei einem Auftrag mit Terminrisiko prüft das Programm, ob er auf einer anderen Maschine früher fertig wäre, "
     "ohne dass ein anderer Auftrag dadurch schlechter dasteht. Der Vorschlag steht im Reiter Auslastung rechts in "
     "der Spalte <b>Vorschlag</b>; <b>Vorschlag übernehmen</b> legt den Auftrag um. Das Programm rechnet mit "
     "derselben Laufzeit und verschiebt nichts von selbst. Welche Maschinen als Ausweichmaschine gelten, stellst "
     "du in den Einstellungen bei der Maschine ein; für Arbeitsplätze wie Entgraten nimmst du das Häkchen heraus."),
    ("Zusatzfelder",
     "Eigene Angaben je Auftrag, zum Beispiel Material, Stückzahl oder Bearbeiter, legst du in den Einstellungen "
     "an. Sie erscheinen in der Liste, im Auftrag und in der CSV-Datei."),
    ("Aus Excel oder CSV einlesen",
     "<b>Mehr → Aus Excel oder CSV einlesen …</b> übernimmt Aufträge aus einer Excel-Datei (.xlsx, erstes Blatt) "
     "oder CSV-Datei. Schneller geht es mit <b>Strg+V</b>: in Excel die Zeilen samt Überschriftenzeile markieren, "
     "Strg+C, im Programm Strg+V. Die erste Zeile nennt die Spalten: "
     "Auftragsnummer, Maschine und Kalkulierte Laufzeit sind Pflicht, dazu nach Wunsch Liefertermin, Kunde, "
     "Bemerkung und Zusatzfelder. Bekannte Auftragsnummern werden aktualisiert, fertig gemeldete bleiben "
     "unverändert. Vor dem Übernehmen zeigt das Programm, was neu und was geändert ist. Die Datei aus "
     "<i>Übergabe …</i> der Kalkulation lässt sich genauso einlesen."),
    ("Lizenz",
     "Die Auslastung braucht wie die Kalkulation eine Lizenz je Rechner. Die Lizenz der Kalkulation gilt mit: Ist "
     "die Kalkulation auf diesem Rechner installiert und freigeschaltet, ist nichts zu tun. Sonst im Reiter "
     "<b>Hilfe</b> auf <b>Lizenz …</b>: die Rechner-ID kopieren und an Patrick senden, dann die erhaltene "
     "Lizenzdatei laden (dieselbe Datei wie für die Kalkulation, oder für Plätze ohne Kalkulation eine Lizenz "
     "„nur Auslastung“). Ohne gültige Lizenz bleibt alles lesbar, aber nichts änderbar (wie die Rolle „Nur lesen“); "
     "unten rechts steht dann der Grund. Vor Ablauf erscheint dort rechtzeitig ein Hinweis. Die "
     "<b>Hauptadmin-Lizenz</b> (ohne Rechner-ID) gilt auch hier: Liegt sie auf dem Rechner, fragt die Auslastung beim "
     "Start nach dem Hauptadmin-Passwort; ohne Passwort startet sie nicht. Werkstatt-Rechner merken davon nichts."),
    ("Warnungen, Puffer und Kundenpriorität",
     "<b>Warnungen:</b> Die Glocke oben rechts zeigt, wie viele Warnungen es gibt (rot = dringend). Klick öffnet die "
     "Liste, ein Klick auf eine Zeile zeigt den Auftrag. Gewarnt wird, wenn der Liefertermin überschritten ist oder "
     "laut Plan nicht zu halten, wenn das Material noch nicht da ist und der Auftrag bald starten soll, wenn eine "
     "Maschine nach einem Stopp mit Grund länger steht und wenn Fremdarbeit schon zurück sein müsste. Im Reiter "
     "<b>Aufträge</b> steht dieselbe Meldung als rote Zeile über der Liste. Die Grenzen stehen unter "
     "<b>Einstellungen → Termine und Abläufe → Warnungen und Kundenpriorität</b>. In der Liste der Glocke lässt sich "
     "für diesen Platz ein <i>Windows-Hinweis bei neuer Warnung</i> einschalten. Keine Mail, keine Cloud. "
     "Ausschalten: Funktionen → Warnungen.<br><b>Puffer und spätester Start:</b> In der Auftragsliste zeigt "
     "<i>Puffer [AT]</i>, wie viele Arbeitstage zwischen lieferbar und Liefertermin liegen. <i>Spätester Start</i> = "
     "geplanter Start plus Puffer: So spät kann der Auftrag noch anfangen und hält den Termin, wenn alles andere "
     "bleibt (gelb = heute, rot = schon vorbei). Beide Spalten lassen sich sortieren.<br><b>Kundenpriorität:</b> "
     "In derselben Einstellung je Kunde A (wichtig), B (normal) oder C (kann warten). A-Kunden werden so "
     "eingeplant, als läge ihr Liefertermin 3 Tage früher, C-Kunden 3 Tage später (Zahl änderbar); der "
     "Liefertermin selbst und das Terminrisiko bleiben. Von Hand vorgezogene Aufträge und feste Plätze gehen weiter "
     "vor. Die Spalte <i>Priorität</i> erscheint, sobald ein Kunde A oder C ist.<br><b>Länger als kalkuliert:</b> "
     "Ist die kalkulierte Zeit eines laufenden Auftrags verbraucht, plant das Programm bis zur Fertigmeldung noch "
     "eine Restzeit ein (15 % der Kalkulation, mindestens 30 Minuten), damit die Maschine nicht als frei gilt; die "
     "Glocke meldet „läuft länger als kalkuliert“.<br><b>Nicht umplanen:</b> Optimieren und Ausweichmaschine ändern "
     "nichts an Aufträgen, die in den nächsten 2 Arbeitstagen beginnen (0 = aus). Von Hand verschieben geht "
     "weiter. Beide Werte stehen in derselben Einstellung."),
    ("Zusatzschritte: Gewinde, Nieten, Schweißen, Verzinken",
     "Einschalten unter <b>Einstellungen → Ansicht und Felder → Funktionen → Zusatzschritte</b> (schaltet die "
     "Arbeitsgänge mit ein und legt die Arbeitsplätze <i>Bearbeitung</i> und <i>Schweißen</i> an). Im Auftrag dann "
     "<b>Stückzahl</b> eintragen und <b>+ Zusatzschritt …</b> klicken: Schritt wählen (Gewinde schneiden, Senken, "
     "Bohren, Nieten, Schweißen, Verzinken, Pulverbeschichten) und die Anzahl je Teil eingeben, z. B. 4 × M8 oder "
     "3 Heftpunkte und 2 Nähte bis 20 cm. Das Programm rechnet <i>Rüsten + Stückzahl × (Handling + Anzahl × Zeit "
     "je Stück)</i> und zeigt den Rechenweg; ändert sich die Stückzahl, rechnet es neu. Verzinken und "
     "Pulverbeschichten sind Fremdarbeit mit 5 Arbeitstagen; abgeholt und angeliefert wird nur montags und "
     "mittwochs (änderbar). Die Zeiten je Stück stehen unter <b>Einstellungen → Termine und Abläufe → "
     "Zusatzschritte</b>; die Startwerte sind Schätzwerte. Aus den Fertigmeldungen schlägt das Programm bessere "
     "Werte vor, übernommen wird erst mit <b>✓ Übernehmen</b>. Schnell anlegen und Excel verstehen z. B. "
     "<i>50 Stk 4xM8 2xNiete verzinken</i> (Excel: Spalten <i>Stückzahl</i> und <i>Zusatzschritte</i>)."),
    ("Monatsplan wie in Excel",
     "Im Reiter <b>Auslastung</b> über der Plantafel auf <b>Monat</b> klicken. Jede Zeile ist ein Tag, jede Spalte "
     "eine Maschine. In der Zelle stehen die Aufträge, die an diesem Tag auf der Maschine laufen, mit ihrer Zeit an "
     "diesem Tag (ein langer Auftrag steht an mehreren Tagen); der Punkt davor zeigt das Terminrisiko. Unten in "
     "der Zelle die Tagesauslastung: grün, gelb ab 80 %, rot wenn der Tag voll ist; „frei“ = ohne Schicht. "
     "◀ und ▶ blättern einen Monat, <b>Heute</b> springt zum heutigen Tag. Vergangene Tage zeigen grau, was "
     "tatsächlich lief. Ganz unten die Summe des Monats je Maschine (geplant von verfügbar). Klick wählt einen "
     "Auftrag, Doppelklick öffnet ihn. Zum Aushängen: <b>PDF … → Monatsplan A3 quer</b>, der ganze Monat auf "
     "einer Seite. Gerechnet wird wie in der Plantafel, der Monatsplan ist nur eine andere Ansicht."),
    ("Schnell anlegen",
     "Im Reiter <b>Aufträge</b> oben rechts: eine Zeile wie <i>A-2701 LT7 3:30 25.11. Schulz</i> tippen und Enter "
     "drücken. Das Programm erkennt die Maschine am Namen, die Laufzeit am Doppelpunkt oder an der Einheit "
     "(3:30, 3 h 30 min, 90 min, 1,5 h) und den Liefertermin am Datum (TT.MM. oder TT.MM.JJJJ); das erste übrige "
     "Wort ist die Auftragsnummer, der Rest der Kunde. Die Reihenfolge ist egal. Fehlt etwas, steht unten, was."),
    ("Funktionen ein- und ausschalten",
     "Unter <b>Einstellungen → Ansicht und Felder → Funktionen</b> stehen die Zusatzfunktionen mit Häkchen: "
     "<i>Material und Rüsten</i> (Material, Rüstzeit und Rohrmaße, Ziel „Wenig Rüsten“), <i>Material da ab</i>, "
     "<i>Teillieferungen</i>, <i>Mehrere Arbeitsgänge</i> und <i>Werkstatt-Ansicht</i>. Ausgeschaltet verschwinden "
     "Felder und Knöpfe, und geplant wird ohne sie (z. B. ohne Rüstzeit). Schon eingetragene Werte bleiben "
     "gespeichert und sind beim Einschalten wieder da. Material und Rüsten sowie Material da ab sind in einer "
     "neuen Datenbank aus; wer schon Werte eingetragen hat, behält sie an. Gilt für alle Plätze."),
    ("Excel-Liste automatisch abgleichen",
     "Unter <b>Einstellungen → Termine und Abläufe → Abgleich mit eurer Excel-Liste</b> wählst du eure "
     "Auftragsliste (z. B. im gemeinsamen Ordner). Das Programm liest sie beim Start und jede Minute, wenn sie "
     "neu gespeichert wurde, und übernimmt neue und geänderte Aufträge ohne Rückfrage; vorher sichert es die "
     "Datenbank. Aufträge, die in der Datei fehlen, bleiben im Programm. Unten rechts steht der letzte Abgleich "
     "mit Uhrzeit; ist die Datei gerade offen oder nicht lesbar, versucht es das Programm beim nächsten Mal."),
    ("Frühester Liefertermin",
     "Beim <b>neuen Auftrag</b> zeigt die Zeile <i>Frühestens fertig</i>, wann der Auftrag mit der eingetragenen "
     "Laufzeit auf der gewählten Maschine (und den anderen geeigneten) fertig wäre. <i>Als Liefertermin</i> setzt "
     "diesen Tag als Liefertermin."),
    ("Erfahrungswert je Maschine",
     "Läuft eine Maschine regelmäßig länger oder kürzer als kalkuliert, hakst du bei der Maschine "
     "<b>Mit Erfahrungswert planen</b> an. Das Programm nimmt dann das Verhältnis Ist zu Soll der fertig "
     "gemeldeten Aufträge der letzten 365 Tage (ab 5 Aufträgen, zwischen 0,5 und 2) und plant die offenen "
     "Aufträge dieser Maschine damit. Die eingetragene Laufzeit bleibt unverändert. Vorgabe: aus."),
    ("Mehrere Plätze und Sicherung",
     "Die Datenbank ist eine Datei. Liegt sie in einem gemeinsamen Ordner (<b>Einstellungen → Datenbank an anderem "
     "Ort …</b>, an jedem Platz denselben Ort wählen), arbeiten alle Plätze mit denselben Aufträgen; Änderungen "
     "erscheinen bei den anderen nach wenigen Sekunden. Beim Start legt das Programm einmal am Tag eine Kopie in "
     "den Ordner <i>Sicherung</i> neben der Datenbank, die letzten zehn bleiben."),
    ("Schichten",
     "Unter <b>Einstellungen → Schichten</b> stehen die Schichten mit Beginn, Ende und Pause (Vorgabe Früh, Spät, "
     "Nacht). Bei der Maschine (<b>Maschine ändern …</b>) wird angehakt, welche Schichten sie von Montag bis "
     "Freitag fährt. Ihre Stunden je Tag ergeben sich dann aus den Schichten ohne Pause, und die Einlastung rechnet "
     "damit. Eine Maschine ohne Schicht behält ihre Stunden je Tag von Hand. Die Pfeile ▲ ▼ sortieren die Liste."),
    ("Schichten: Samstag und Ausnahmen",
     "Bei <b>Maschine ändern …</b> lassen sich unter <b>Schichten am Samstag</b> eigene Schichten für den Samstag "
     "anhaken; ohne Haken gelten die Samstagsstunden für alle Maschinen. Unter <b>Einstellungen → Schichten → "
     "Ausnahmen</b> stehen abweichende Tage: Sonderschicht, Kurzarbeit, Brückentag. Eine Ausnahme gilt für eine "
     "Maschine oder für alle, für einen Tag oder einen Zeitraum, mit den angehakten Schichten; ohne Haken wird "
     "an diesen Tagen nicht gearbeitet. Ein einzelner Tag gilt auch am Samstag und am Feiertag, ein Zeitraum für "
     "Montag bis Freitag ohne Feiertage; am Sonntag wird nie eingelastet. Gibt es mehrere Ausnahmen für einen Tag, "
     "geht die für die Maschine vor der für alle und der einzelne Tag vor dem Zeitraum. Sperrtage und Betriebsruhe "
     "gehen immer vor. Die Tagesansicht nennt den Grund der Ausnahme neben der Uhrzeit."),
    ("Schichten: Wochenwechsel",
     "Wechseln die Schichten einer Maschine von Woche zu Woche, stellt man bei <b>Maschine ändern …</b> unter "
     "<b>Wochenwechsel über</b> zwei bis vier Wochen ein und hakt für jede Woche ihre Schichten an, z. B. Woche 1 "
     "Früh, Woche 2 Spät, oder Woche 1 Früh und Spät, Woche 2 nur Früh. Das Datum darunter legt fest, in welcher "
     "Woche Woche 1 gilt (es zählt der Montag dieser Woche); danach wiederholt sich die Folge von selbst. "
     "Einlastung, Auslastung und Tagesansicht rechnen jede Woche mit ihren Schichten. Im Feld Stunden je Tag steht "
     "die kleinste Woche; der Dialog zeigt, welche Woche gerade gilt."),
    ("Optimieren",
     "<b>Optimieren …</b> auf der Seite Auslastung sucht eine Reihenfolge und Maschinenverteilung, bei der möglichst "
     "kein Auftrag zu spät fertig wird. Das Programm probiert Schritt für Schritt: einen gefährdeten Auftrag auf "
     "eine Ausweichmaschine legen, ihn vorziehen, oder eine Reihenfolge von Hand wieder nach Liefertermin ordnen. "
     "Ziel sind möglichst wenige verspätete Aufträge; dafür kann ein Auftrag, der ohnehin nicht zu halten ist, "
     "weiter nach hinten rücken. Es zeigt die Änderungen und ihre Wirkung je Auftrag als Vorschlag. Erst <b>Übernehmen</b> speichert, "
     "<b>Optimierung rückgängig</b> stellt den Stand davor wieder her. Laufende Aufträge, Aufträge mit festem "
     "Platz, mit mehreren Arbeitsgängen oder mit Teillieferungen bleiben unberührt."),
    ("Optimieren: Ziel wählen",
     "Der Knopf <b>Optimieren …</b> fragt nach dem Ziel. <b>Wenige Verspätungen</b> ist die Optimierung auf "
     "Termine. <b>Wenig Rüsten</b> stellt Aufträge mit gleichem Material auf ihrer Maschine direkt hintereinander, "
     "solange dadurch kein Termin mehr reißt oder knapp wird; die Aufträge bis dorthin bekommen eine feste "
     "Reihenfolge, neue Aufträge stehen dahinter (Reihenfolge → wieder nach Liefertermin hebt das auf). "
     "<b>Gleichmäßige Auslastung</b> verteilt Aufträge so auf die Ausweichmaschinen, dass ihr Arbeitsvorrat in "
     "Arbeitstagen möglichst gleich ist, ebenfalls ohne dass ein Termin schlechter wird. Der Vorschlag zeigt oben "
     "die Rüstzeit oder den Unterschied vorher und nachher."),
    ("Rüstzeit und Material",
     "Unter <b>Einstellungen → Maschinen</b> hat jede Maschine eine <b>Rüstzeit je Auftrag</b> in Minuten. Das "
     "Programm rechnet sie zu jedem Auftrag dazu, der noch nicht läuft. Im Auftrag lässt sich die Rüstzeit einzeln "
     "ändern (leer = wie die Maschine, 0 = ohne). Steht im Auftrag ein <b>Material</b> und läuft auf der Maschine "
     "direkt davor das gleiche Material, entfällt das Rüsten; gleich heißt gleich geschrieben, Groß und Klein sind "
     "egal. In der Plantafel ist das Rüsten der dunkle Anfang des Balkens, die Infokarte nennt die Zeit oder "
     "„Rüsten gespart“. Die Restlaufzeit in Plantafel und Listen enthält die Rüstzeit. Bei Aufträgen mit mehreren "
     "Arbeitsgängen gilt je Zeile die Rüstzeit ihres Arbeitsplatzes."),
    ("Maschineneignung: größtes Rohr",
     "Je Maschine lassen sich der <b>größte Durchmesser</b> und die <b>größte Rohrlänge</b> eintragen (0 = keine "
     "Grenze), im Auftrag der Durchmesser oder das größte Außenmaß und die Länge des Rohrs (leer = unbekannt). "
     "Passt das Rohr nicht, lehnt das Programm die Maschine ab: beim Speichern, beim Ziehen in der Plantafel und "
     "in Was wäre, wenn. Ausweichmaschine und Optimieren schlagen eine unpassende Maschine nie vor."),
    ("Teillieferungen",
     "Für Abrufaufträge im Auftrag <b>Teillieferungen</b> anhaken und je Lieferung Termin und Menge eintragen. Die "
     "kalkulierte Laufzeit teilt sich nach den Mengen; jede Lieferung wird mit ihrem eigenen Termin eingelastet "
     "und steht als eigener Balken in der Plantafel (Lieferung 1/3). Der Liefertermin des Auftrags ist der letzte. "
     "Was schon gelaufen ist, zählt für die früheste Lieferung. Das Terminrisiko des Auftrags ist das der "
     "schlechtesten Lieferung; der Hinweis auf dem Liefertermin in der Auftragsliste zeigt alle. Teillieferungen "
     "gibt es nur bei Aufträgen ohne Arbeitsgänge."),
    ("Plantafel: Suchen, Vollbild, Drucken",
     "Ein Klick auf einen <b>Wochenbalken</b> oben zeigt rechts die Aufträge dieser Woche und rollt die Plantafel "
     "zu dieser Woche. Das Feld <b>Suchen</b> über der Plantafel findet einen Auftrag nach Auftragsnummer oder Kunde, hebt ihn hervor "
     "und rollt zu seinem Beginn; die Eingabetaste springt zum nächsten Treffer. <b>Vollbild</b> zeigt die "
     "Plantafel allein über den ganzen Bildschirm, zum Beispiel in der Halle; sie folgt jeder Änderung, Esc "
     "schließt. Dort lässt sich die <b>Schrift</b> auf groß oder sehr groß stellen (die ganze Tafel wird größer), "
     "oben steht die <b>Uhr</b>, und <b>Blättern</b> schaltet automatisch weiter: in der Tagesansicht durch die "
     "nächsten fünf Arbeitstage, in der Wochenansicht durch die nächsten Wochen, dann von vorn; passen nicht alle "
     "Maschinen auf den Bildschirm, kommen erst die unteren. Der Platz merkt sich beides. Unter <b>PDF …</b> gibt es die Auslastung in A4 und in A3 zum Aushängen und die Tagesansicht des "
     "gezeigten Tages mit der Liste der Aufträge und ihren Uhrzeiten."),
    ("Tagesansicht: tatsächliche Zeiten",
     "In der Tagesansicht steht beim laufenden Auftrag, seit wann er läuft und wie viel der kalkulierten Zeit "
     "verbraucht ist. Unter der Tafel steht <b>Heute tatsächlich</b>: je Maschine, was läuft und was heute fertig "
     "gemeldet wurde, mit Uhrzeit, tatsächlicher gegen kalkulierter Laufzeit und der Abweichung. Überzieht ein "
     "laufender Auftrag seine kalkulierte Zeit, steht er dort in Rot mit den Minuten."),
    ("Mausrad",
     "Das Mausrad ändert nie einen Wert: Über Zahlenfeldern, Datumsfeldern und Auswahllisten rollt es die Seite."),
    ("Plantafel: Tagesansicht",
     "Die Ansicht <b>Tag</b> zeigt einen Tag über die ganze Breite, mit Stundenraster und den Schichten der "
     "Maschine. Im Balken stehen Auftragsnummer und Kunde, von wann bis wann der Auftrag an diesem Tag läuft, die "
     "Restlaufzeit, wann er fertig wird und der Liefertermin. <b>◀</b> und <b>▶</b> blättern einen Tag weiter, "
     "<b>Heute</b> springt zurück. Die Uhrzeiten sind gerechnet: Die Aufträge laufen nacheinander ab Schichtbeginn, "
     "Pausen und der Nutzungsgrad sind gleichmäßig verteilt."),
    ("Online-Update",
     "Ab Version 1.7 sieht das Programm kurz nach dem Start online nach, ob es eine neuere Version gibt, und meldet "
     "sich nur dann. <b>Jetzt aktualisieren</b> lädt nur die geänderten Dateien, sichert die Datenbank, schließt "
     "das Programm, tauscht die Dateien aus und startet neu. <b>Später</b> lässt alles, wie es ist. Von Hand: "
     "<b>Nach Updates suchen</b> oben in diesem Reiter. Aufträge, Einstellungen und die Datei Auslastung.ini "
     "bleiben unberührt. Geht etwas schief (keine Verbindung, eine Datei ist noch geöffnet), bleibt die bisherige "
     "Version und startet wieder. Arbeiten mehrere Plätze mit derselben Datenbank, bitte alle Plätze "
     "aktualisieren: Eine ältere Version öffnet eine Datenbank nicht mehr, die eine neuere schon umgestellt hat. "
     "Das Programm braucht dafür Zugriff auf github.com und Schreibrecht im eigenen Ordner."),
)


def html():
    teile = [f"<h2>{NAME} {VERSION}</h2>"]
    for titel, text in ABSCHNITTE:
        teile.append(f"<h3>{titel}</h3><p>{text}</p>")
    teile.append(f"<p><i>Beispiele für die Laufzeit: {laufzeit.BEISPIELE.replace('z. B. ', '')}.</i></p>")
    return "\n".join(teile)
