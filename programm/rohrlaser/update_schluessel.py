"""Öffentliche Schlüssel für die Prüfung der Dateiliste Update.json (update.py, Datei Update.json.sig), je
Schlüssel-ID. Getrennt von den Lizenz-Schlüsseln (lizenz_schluessel.py).

Nur öffentliche Schlüssel, nie private. Den Eintrag U1 gibt das Lizenz-Werkzeug aus („Update-Schlüssel erzeugen …“);
der private Schlüssel liegt passwortgeschützt im Lizenzordner und als Secret UPDATE_SIGNATUR in GitHub.
Sobald hier ein Schlüssel steht, nimmt das Programm nur noch gültig signierte Dateilisten an (update.online_liste).
Wechsel: U2 dazunehmen und U1 stehen lassen, ein Release mit beiden ausliefern, erst danach mit U2 signieren.
"""
SCHLUESSEL = {
}
