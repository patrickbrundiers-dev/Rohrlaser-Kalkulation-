# Entwickler-Zugang (nur für den Entwickler)

Ein fester Login, mit dem der Entwickler auf **jeder** Installation vollen Zugriff hat – unabhängig von Kundenlizenz,
Hauptadmin oder Lesemodus. Nicht für Kunden; steht bewusst **nicht** in der Bedienungsanleitung.

## Wie es funktioniert
- Das Passwort ist überall gleich, steht aber **nicht im Klartext** im Programm. Hinterlegt ist nur ein öffentlicher
  Prüfwert (`entwickler.VERIFIZIERER`), aus dem Passwort über scrypt mit festem Salz abgeleitet.
- Beim Login leitet das Programm aus dem eingegebenen Passwort denselben Prüfwert ab und vergleicht. Aus dem Prüfwert
  lässt sich das Passwort nicht zurückrechnen; ein auseinandergenommenes Programm enthält kein Geheimnis.
- Erkannt wird das Passwort in der Schlossleiste der Einstellungen („Als Admin freischalten“) und bei der
  Hauptadmin-Anmeldung beim Start. Danach: voller Admin-Zugriff, Lesemodus aufgehoben, Eintrag im Protokoll.

## Einrichten (einmal)
1. Im Lizenz-Werkzeug:
   ```
   python werkzeuge/lizenz_werkzeug.py entwickler-schluessel
   ```
   Passwort zweimal eingeben (mindestens 12 Zeichen). Es gibt die Zeile `VERIFIZIERER = "..."` aus.
2. Diese Zeile in `programm/rohrlaser/entwickler.py` eintragen (nur der öffentliche Prüfwert).
3. Einmal bauen. Ab dann gilt der Login auf jeder neuen Installation.

Das Passwort selbst **nie** in Chat, Repo oder eine Datei schreiben. Solange `VERIFIZIERER` leer ist, ist der
Entwickler-Zugang aus.

## Passwort wechseln
Neuen Prüfwert wie oben erzeugen, `VERIFIZIERER` ersetzen, neu bauen und ausrollen. Alte Installationen nehmen das
neue Passwort erst nach dem Update an.
