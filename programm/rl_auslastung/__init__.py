"""Rohrlaser Auslastung: eigenes Programm zur Maschinenauslastung, läuft ohne die Kalkulation (Patrick 11.11.2026).

Je Auftrag: Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche
Laufzeit; dazu frei anlegbare Zusatzfelder. Eigene Datenbankdatei (daten.py), Rechnung über rohrlaser.einlastung
(rechnung.py), Grafik über rohrlaser.auslastung_grafik (fenster.py). Aus dem Paket rohrlaser werden nur einlastung,
wochen, feiertage, stil und auslastung_grafik gebraucht, für das Online-Update (aktualisierung.py) zusätzlich update
und update_schluessel."""
VERSION = "1.7.0"
NAME = "Rohrlaser Auslastung"
# Kurztext „Neu darin“ für den Hinweis des Online-Updates (steht in der Dateiliste Update.json)
NEU = ("Online-Update, Schichten mit Uhrzeiten je Maschine und eine Tagesansicht der Plantafel mit Uhrzeiten.")
