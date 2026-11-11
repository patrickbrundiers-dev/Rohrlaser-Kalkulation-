"""Rohrlaser Auslastung: eigenes Programm zur Maschinenauslastung, läuft ohne die Kalkulation (Patrick 11.11.2026).

Je Auftrag: Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche
Laufzeit; dazu frei anlegbare Zusatzfelder. Eigene Datenbankdatei (daten.py), Rechnung über rohrlaser.einlastung
(rechnung.py), Grafik über rohrlaser.auslastung_grafik (fenster.py). Aus dem Paket rohrlaser werden nur einlastung,
wochen, feiertage, stil, auslastung_grafik und mausrad gebraucht, für das Online-Update (aktualisierung.py)
zusätzlich update und update_schluessel."""
VERSION = "2.3.0"
NAME = "Rohrlaser Auslastung"
# Kurztext „Neu darin“ für den Hinweis des Online-Updates (steht in der Dateiliste Update.json)
NEU = ("Schnelleingabe: „A-2701 LT7 3:30 25.11. Kunde“ tippen, Enter, Auftrag ist angelegt. Neue Seite Funktionen in den Einstellungen: Material und Rüsten, Material da ab, Teillieferungen, Arbeitsgänge "
       "und Werkstatt-Ansicht lassen sich ausschalten; eingetragene Werte bleiben. Aus 2.2: mehr Platz für die "
       "Plantafel, Excel einlesen und automatisch abgleichen, frühester Liefertermin, Erfahrungswert je Maschine.")
