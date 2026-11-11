"""Rohrlaser Auslastung: eigenes Programm zur Maschinenauslastung, läuft ohne die Kalkulation (Patrick 11.11.2026).

Je Auftrag: Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche
Laufzeit; dazu frei anlegbare Zusatzfelder. Eigene Datenbankdatei (daten.py), Rechnung über rohrlaser.einlastung
(rechnung.py), Grafik über rohrlaser.auslastung_grafik (fenster.py). Aus dem Paket rohrlaser werden nur einlastung,
wochen, feiertage, stil, auslastung_grafik und mausrad gebraucht, für das Online-Update (aktualisierung.py)
zusätzlich update und update_schluessel."""
VERSION = "2.0.1"
NAME = "Rohrlaser Auslastung"
# Kurztext „Neu darin“ für den Hinweis des Online-Updates (steht in der Dateiliste Update.json)
NEU = ("Klick auf einen Wochenbalken rollt die Plantafel zu dieser Woche. Aus 2.0: Rüstzeit und Material, Maschineneignung nach Rohrgröße, Teillieferungen, Optimieren mit Ziel, Vollbild für "
       "die Halle mit großer Schrift und Uhr, Fertig melden mit Suche nach Auftragsnummer und Uhrzeit.")
