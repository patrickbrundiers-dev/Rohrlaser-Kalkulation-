# Rohrlaser-Maschinenplanung (T03, T11, LT7)

Belegungsplanung und Auslastung der drei Rohrlaser im Browser. Ein kleiner Planungsserver läuft auf **einem**
Rechner, alle anderen öffnen die Planung im Browser. Gespeichert wird zentral in einer SQLite-Datei auf dem
Server-Rechner. Mehrere Personen können gleichzeitig planen: Änderungen erscheinen bei allen sofort. Wer auf einem
veralteten Stand speichert, wird abgewiesen und sieht, wer zuletzt geändert hat.

## Starten

* **Portabel (Windows):** ZIP `Rohrlaser-Maschinenplanung.zip` entpacken, z. B. nach `D:\Maschinenplanung`.
  `Rohrlaser-Maschinenplanung.exe` starten. Keine Installation, keine Admin-Rechte.
  Das ZIP baut GitHub unter *Actions > Planung > Run workflow*.
* **Entwicklung:** `python -m planung` (nur Python-Standardbibliothek).
* Optionen: `--port 8765`, `--host 127.0.0.1` (nur dieser Rechner), `--daten ORDNER`, `--selbsttest`.

Im Browser `http://RECHNERNAME:8765/` öffnen. Beim ersten Aufruf wird der erste Benutzer (Rolle *verwalten*) angelegt.

**Automatisch mit Windows starten:** `Autostart-einrichten.cmd` ausführen. Das legt eine Verknüpfung im
Autostart-Ordner des angemeldeten Benutzers an (ohne Admin-Rechte). Der Server läuft dann, solange dieser Benutzer
angemeldet ist.

## Daten und Sicherung

* Daten: Ordner `Planungsdaten` neben der .exe (`planung.db`).
* Sicherung: beim Start und danach täglich in `Planungsdaten/Sicherung`. Die letzten 30 werden behalten.
  Zusätzlich gibt es den Knopf *Sicherung jetzt* unter *Maschinen & Kalender*.
* Zurückspielen: Server beenden, die gewünschte Sicherung als `planung.db` kopieren, Server starten.
* Die Rohrlaser-Kalkulation und ihre Datenbank werden nicht verändert.

## Erreichbarkeit von anderen PCs (Firewall)

Ohne Admin-Rechte kann keine Firewall-Regel angelegt werden. Ob andere PCs den Server erreichen, hängt von der
Firewall-Einstellung des Server-Rechners ab:

1. Server auf dem Server-Rechner starten. Eine Windows-Firewall-Abfrage lässt sich ohne Admin-Rechte nur
   abbrechen; das ist in Ordnung, der Server läuft trotzdem.
2. Auf einem **anderen** PC `Erreichbarkeit-pruefen.cmd` ausführen und den Rechnernamen eingeben.
3. `TcpTestSucceeded : True` = erreichbar. Sonst muss die IT den TCP-Port 8765 eingehend für dieses Programm
   freigeben (einmalig).

## Rollen

| Rolle | darf |
|---|---|
| lesen | Dashboard, Plantafel, Aufträge und Kalender ansehen |
| planen | zusätzlich Aufträge anlegen und ändern, einplanen, verschieben, fixieren, Stillstände eintragen |
| verwalten | zusätzlich Schichtmodelle, Ausnahmen, Feiertage, Einstellungen, Benutzer, Sicherung |

## Rechenregeln (dokumentiert)

* **Dauer einer Belegung:** manuell eingetragene Dauer, sonst Maschinenzeit + Rüstzeit des Auftrags, sonst *offen*.
* **Ende:** wird aus Beginn, Dauer und den verfügbaren Schichtfenstern der Maschine berechnet (Pausen, Feiertage,
  Ausnahmen und Stillstände werden übersprungen) und auf die volle Minute aufgerundet. Ändert sich der Kalender,
  verschiebt sich das Ende automatisch.
* **Schichtmodell:** je Maschine und Wochentag beliebig viele Fenster mit *gültig ab/bis*. Ende ≤ Beginn = über
  Mitternacht. Ausnahmen: *frei* (Fenster entfällt) oder *Zusatzschicht*.
* **Auslastung** = geplante Minuten in den verfügbaren Fenstern / verfügbare Minuten, je Tag, Woche oder Monat.
* **Terminrisiko:** Puffer = Arbeitstage zwischen geplantem Ende und Liefertermin. Ende nach Liefertermin =
  *überschritten*, Puffer unter der Schwelle (Einstellung, Vorgabe 2 Arbeitstage) = *kritisch*.
* **Verschieben:** zuerst Vorschau, dann Speichern. *Nachrücken* schiebt nachfolgende Belegungen derselben Maschine
  auf; fixierte Belegungen werden nie verschoben (dann Fehlermeldung).
* **Feiertage:** Knopf übernimmt die 9 bundesweiten Feiertage. Landesfeiertage bitte als Ausnahme eintragen.

## Offene Punkte und Grenzen

* Welche Maschine welche Aufträge kann, ist noch nicht hinterlegt. Je Auftrag können erlaubte Maschinen eingetragen
  werden; ohne Eintrag gelten alle drei.
* Schwelle für *kritisch* (2 Arbeitstage) ist eine Annahme und unter *Maschinen & Kalender* einstellbar.
* Übernahme aus der Kalkulation (Knopf *An Planung übergeben*) und Import der alten Excel folgen.
* Nachtschichten in der Nacht der Zeitumstellung werden mit der Uhrzeit gerechnet (eine Stunde mehr bzw. weniger
  wird nicht berücksichtigt).
* Anmeldung mit eigenen Benutzern; Windows-Anmeldung (Domäne) ist nicht angebunden.
