"""Rohrlaser Auslastung: eigenes Programm zur Maschinenauslastung, läuft ohne die Kalkulation (Patrick 11.11.2026).

Je Auftrag: Auftragsnummer, Maschine, kalkulierte Laufzeit, Liefertermin und nach der Fertigmeldung die tatsächliche
Laufzeit; dazu frei anlegbare Zusatzfelder. Eigene Datenbankdatei (daten.py), Rechnung über rohrlaser.einlastung
(rechnung.py), Grafik über rohrlaser.auslastung_grafik (fenster.py). Aus dem Paket rohrlaser werden nur einlastung,
wochen, feiertage, stil, auslastung_grafik und mausrad gebraucht, für das Online-Update (aktualisierung.py)
zusätzlich update und update_schluessel."""
VERSION = "2.2.0"
NAME = "Rohrlaser Auslastung"
# Kurztext „Neu darin“ für den Hinweis des Online-Updates (steht in der Dateiliste Update.json)
NEU = ("Mehr Platz für die Plantafel (Wochenbalken flacher und ausblendbar, Liste rechts einklappbar, Einstellungen in "
       "Unterreitern). Aufträge aus Excel einlesen (.xlsx oder Strg+V), eure Excel-Liste automatisch abgleichen, "
       "frühester Liefertermin beim neuen Auftrag, Erfahrungswert je Maschine aus Soll und Ist.")
