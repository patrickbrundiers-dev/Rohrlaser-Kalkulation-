"""Rohrlaser Auslastung: eigenes Programm zur Maschinenauslastung, läuft ohne die Kalkulation (Patrick 11.11.2026).

Je Auftrag: Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche
Laufzeit; dazu frei anlegbare Zusatzfelder. Eigene Datenbankdatei (daten.py), Rechnung über rohrlaser.einlastung
(rechnung.py), Grafik über rohrlaser.auslastung_grafik (fenster.py). Aus dem Paket rohrlaser werden nur einlastung,
wochen, feiertage, stil (mit design), auslastung_grafik und mausrad gebraucht, für das Online-Update (aktualisierung.py)
zusätzlich update und update_schluessel."""
VERSION = "2.9.1"
NAME = "Rohrlaser Auslastung"
# Kurztext „Neu darin“ für den Hinweis des Online-Updates (steht in der Dateiliste Update.json)
NEU = ("Wartung im Kalender (einmalig, alle X Wochen oder alle X Laufstunden) und Bediener mit Urlaub und "
       "Krankheit: Einstellungen → Wartung und Bediener. Die Plantafel zeigt Wartung grau und fehlende Bediener "
       "orange, die Glocke warnt vorher. "
       "Schnittstelle zur Kalkulation: Aufträge kommen mit Positionen, Zusatzarbeiten, Zeiten und Material "
       "aus der Kalkulation; Storno nimmt sie heraus, gelaufene Zeiten und Umplanungen der Werkstatt bleiben. Die "
       "Auslastung meldet Ist-Zeiten, freie Stunden je Woche und den frühesten Fertig-Tag zurück. "
       "Warnungen: Glocke oben rechts mit Liste (Termin in Gefahr, Material fehlt, Maschine steht, "
       "Fremdarbeit nicht zurück). Spalten Puffer und Spätester Start in der Auftragsliste. Kundenpriorität "
       "A/B/C (Einstellungen → Termine und Abläufe). Läuft ein Auftrag länger als kalkuliert, bleibt eine "
       "Restzeit im Plan. Optimieren lässt die nächsten 2 Arbeitstage unverändert. "
       "Zusatzschritte: Gewinde, Senken, Bohren, Nieten, Schweißen mit Zeit aus der Anzahl je Teil, Verzinken und "
       "Pulvern 5 Arbeitstage, Abholung montags und mittwochs (Funktionen → Zusatzschritte). "
       "Monatsplan wie in Excel: Auslastung → Monat (Tage × Maschinen, Aufträge mit Zeit, Tagesauslastung, "
       "PDF A3 zum Aushängen). Lizenz: Die Lizenz der Kalkulation gilt mit (Hilfe → Lizenz …). Schnelleingabe: "
       "„A-2701 LT7 3:30 25.11. Kunde“ tippen, Enter. Neue Seite Funktionen: Material und Rüsten, Material da ab, "
       "Teillieferungen, Arbeitsgänge und Werkstatt-Ansicht lassen sich ausschalten; eingetragene Werte bleiben.")
