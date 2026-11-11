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
     "gestoppte Zeit steht in der Spalte Status. <b>Fertig melden …</b> fragt die tatsächliche Laufzeit ab und "
     "schlägt die gestoppte Zeit vor. Ein fertiger Auftrag belegt die Maschine nicht mehr; <b>Wieder öffnen</b> "
     "nimmt die Fertigmeldung zurück."),
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
     "Ein Klick auf einen Wochenbalken zeigt rechts die Aufträge dieser Woche."),
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
    ("CSV einlesen und speichern",
     "<b>Mehr → CSV einlesen …</b> übernimmt Aufträge aus einer Datei. Die erste Zeile nennt die Spalten: "
     "Auftragsnummer, Maschine und Kalkulierte Laufzeit sind Pflicht, dazu nach Wunsch Liefertermin, Kunde, "
     "Bemerkung und Zusatzfelder. Bekannte Auftragsnummern werden aktualisiert, fertig gemeldete bleiben "
     "unverändert. Vor dem Übernehmen zeigt das Programm, was neu und was geändert ist. Die Datei aus "
     "<i>Übergabe …</i> der Kalkulation lässt sich genauso einlesen."),
    ("Mehrere Plätze und Sicherung",
     "Die Datenbank ist eine Datei. Liegt sie in einem gemeinsamen Ordner (<b>Einstellungen → Datenbank an anderem "
     "Ort …</b>, an jedem Platz denselben Ort wählen), arbeiten alle Plätze mit denselben Aufträgen; Änderungen "
     "erscheinen bei den anderen nach wenigen Sekunden. Beim Start legt das Programm einmal am Tag eine Kopie in "
     "den Ordner <i>Sicherung</i> neben der Datenbank, die letzten zehn bleiben."),
)


def html():
    teile = [f"<h2>{NAME} {VERSION}</h2>"]
    for titel, text in ABSCHNITTE:
        teile.append(f"<h3>{titel}</h3><p>{text}</p>")
    teile.append(f"<p><i>Beispiele für die Laufzeit: {laufzeit.BEISPIELE.replace('z. B. ', '')}.</i></p>")
    return "\n".join(teile)
