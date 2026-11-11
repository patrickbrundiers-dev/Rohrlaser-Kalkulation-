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
