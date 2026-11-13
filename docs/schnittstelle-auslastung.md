# Schnittstelle Kalkulation ↔ Rohrlaser Auslastung (Format 2)

Stand 11.11.2026 (nach Gegenlesen der Kalkulation), freigegeben von Patrick („Alle Empfehlungen“, Plan https://claude.ai/artifact/VXiRT4u3tWT9BoABB7M6cp).
Gilt für beide Programme. Beide laufen weiter allein: Ohne Ordner gibt es keinen Austausch und keine Fehlermeldung.

## Grundsätze

- Austausch über Dateien in **einem gemeinsamen Ordner**. Vorgabe ist der Unterordner `Auslastung` neben der Datenbank
  der Kalkulation. In der Auslastung ist es die Einstellung „Übergabe-Ordner“, in der Kalkulation die Einstellung
  „Ordner Auslastung“. Die Auslastung kennt den Ort der Kalkulation nicht; dort wird der Ordner einmal
  unter Einstellungen gewählt.
- CSV, Trennzeichen `;`, Kodierung UTF-8 mit BOM (öffnet direkt in Excel). Erste Zeile = Spaltennamen.
- Jede Zeile hat die Spalte `Format` mit dem Wert `2`. Eine Datei ohne diese Spalte gilt als Format 1, die heutige
  Übergabe mit fünf Spalten, und wird weiter gelesen.
- Zahlen mit Komma (`12,5`), Zeiten in **Minuten**, Datum `TT.MM.JJJJ`, Ja/Nein als `ja` / `nein`.
- Unbekannte Spalten werden übergangen. Beide Seiten können später Spalten ergänzen, ohne dass die andere Seite bricht.
  Fehlt eine Spalte oder ist ein Feld leer, gilt „nicht bekannt“, nicht 0.
- Schreiben immer erst in `<name>.tmp` und dann umbenennen, damit die andere Seite nie eine halbe Datei liest.

## Richtung 1: Kalkulation → Auslastung (Auftragsdatei)

**Auslöser:** automatisch, wenn ein Angebot auf „beauftragt“ gesetzt wird, und wieder bei jeder Änderung danach
(neue Freigabe-Version). Der Knopf „Übergabe …“ schreibt dieselbe Datei für Nachzügler.

**Dateiname:** `Auftrag-<Auftragsnummer>-<JJJJMMTT-HHMMSS>.csv`, je Auftrag eine Datei. Die Auslastung liest jede
neue oder geänderte Datei einmal, innerhalb einer Minute. Den Freigabe-Zähler führt die Kalkulation. Bei mehreren
Dateien zum selben Auftrag gilt die höchste `Freigabe`, bei gleicher Freigabe der neuere Zeitstempel im Dateinamen.
Eine Datei mit kleinerer Freigabe als der schon gelesenen wird übergangen.

**Zeilen:** Die Spalte `Art` sagt, was die Zeile ist. Die Kopffelder stehen in jeder Zeile.

| Art | eine Zeile je | Bedeutung |
|---|---|---|
| `Position` | Position des Angebots | Teil mit Stückzahl, Material und Laserzeit |
| `Zusatzarbeit` | Zusatzarbeit einer Position | Gewinde, Senken, Bohren, Nieten, Schweißen, Verzinken, Pulvern … |
| `Stangen` | Profil + Werkstoff des Schnittplans | Stangenbedarf für den Materialbedarf je Woche |
| `Lieferung` | Teillieferung | Menge und Termin (vorerst schreibt die Kalkulation keine, ihr Fehlen ist kein Fehler) |
| `Storno` | Auftrag (einzige Zeile der Datei) | Auftrag zurückgenommen |

**Spalten** (Pflicht = muss gefüllt sein, sonst wird die Datei mit Meldung abgelehnt):

| Spalte | Art | Pflicht | Inhalt |
|---|---|---|---|
| Format | alle | ja | `2` |
| Art | alle | ja | `Position`, `Zusatzarbeit`, `Stangen`, `Lieferung`, `Storno` |
| Auftragsnummer | alle | ja | Angebots- bzw. Auftragsnummer der Kalkulation, Schlüssel in der Auslastung |
| Freigabe | alle | ja | Freigabe-Version (Zahl, steigt mit jeder Änderung) |
| Kundenauftrag | alle | | Auftragsnr. des Kunden |
| Kunde | alle | | Kundenname |
| Kundennr | alle | | Kundennummer |
| Maschine | alle außer Storno | ja | Rohrlaser, z. B. `LT7`; muss in der Auslastung bekannt sein, sonst wird sie angelegt |
| Liefertermin | alle | | Datum |
| Pos | Position, Zusatzarbeit, Lieferung | ja | Positionsnummer |
| Artikel | Position | | Artikelnummer |
| Bezeichnung | Position | | Text |
| Stückzahl | Position, Lieferung | ja | Stück (Lieferung: Menge dieser Lieferung) |
| Profilform | Position, Stangen | | z. B. `Rundrohr`, `Rechteckrohr` |
| Maß a [mm] | Position, Stangen | | Außenmaß a bzw. Durchmesser |
| Maß b [mm] | Position, Stangen | | Außenmaß b (leer bei Rundrohr) |
| Wand [mm] | Position, Stangen | | Wandstärke |
| Werkstoff | Position, Stangen | | z. B. `S235` |
| Teilelänge [mm] | Position | | |
| Material | Position | | `eigen` oder `Kunde` |
| Laserzeit [min] | Position | ja | Laserzeit der ganzen Position (alle Stück), ohne Rüsten; `0` erlaubt (z. B. Schweißbaugruppe) |
| Rüstzeit [min] | Position | | „Rüsten Maschine“ auf der ersten Position, „Rüsten je Abmessung“ auf der ersten Position jeder Abmessung, sonst `0`. Laserzeit + Rüstzeit aller Positionen = Maschinenzeit der Kalkulation |
| Arbeit | Zusatzarbeit | ja | Name der Zusatzarbeit, wie in der Kalkulation |
| Anzahl je Teil | Zusatzarbeit | | z. B. `4` bei 4 × M8 |
| Zeit [min] | Zusatzarbeit | | Zeit für die ganze Position; leer = Kalkulation hat keine Zeit |
| Fremdleistung | Zusatzarbeit | | `ja` = außer Haus |
| Arbeitstage | Zusatzarbeit | | bei Fremdleistung: Dauer in Arbeitstagen |
| Stangen | Stangen | ja | Anzahl Stangen |
| Stangenlänge [mm] | Stangen | | |
| Nutzlänge [mm] | Stangen | | genutzte Länge über alle Stangen |
| Material da ab | Position, Stangen | | Datum, ab dem das Material dieses Profils erwartet wird (leer = da) |
| Termin | Lieferung | ja | Datum der Teillieferung |

**Was die Auslastung daraus macht:**

- Positionen ohne Laser schreibt die Kalkulation nicht. Eine Schweißbaugruppe kommt als Position mit Laserzeit 0
  und der Zusatzarbeit „Schweißen“.
- Ein Auftrag je Auftragsnummer. Laserzeit = Summe `Laserzeit [min]` aller Positionen, Rüstzeit = Summe
  `Rüstzeit [min]`, Stückzahl = Summe der Positionen, Material = Profil und Werkstoff, wenn alle Positionen gleich sind (sonst leer).
  Die Laufzeit des Lasers in der Auslastung ist Laserzeit + Rüstzeit (die Rüstzeit der Maschine kommt nicht
  noch einmal dazu).
- **Maschine je Position** (MACH-006, ab 0.9.331): Laufen einzelne Positionen eines Auftrags auf einer anderen
  Maschine als der Kopf, schreibt die Kalkulation je Maschine einen eigenen Teilauftrag. Der Teil der Kopf-Maschine
  behält die Auftragsnummer, jeder andere heißt `<Auftragsnummer> @ <Maschine>` (z. B. `2026-0902 @ LT7`) und kommt in
  einer eigenen Datei mit eigener Freigabe. Jede Datei hat weiter genau eine Maschine; das Format bleibt `2`, die
  Auslastung braucht keine Änderung. „Rüsten Maschine“ steht auf der ersten Position jeder Maschine, Positionen,
  Zusatzarbeiten und Stangen-Zeilen im Teilauftrag ihrer Maschine. Kommt die Position auf die Kopf-Maschine zurück,
  folgt für den Teilauftrag ein `Storno`. In der Rückmeldung zählt die Kalkulation die Ist-Laserzeit eines Auftrags
  erst, wenn der Auftrag und alle Teilaufträge `fertig` sind (Summe), und Ist-Stangen aus allen Teilen.
- Zusatzarbeiten werden eigene Arbeitsgänge nach dem Laser, je Arbeit zusammengefasst über alle Positionen. Zeit =
  `Zeit [min]` aus der Kalkulation. Nur wo sie leer ist, rechnet die Auslastung mit ihren Richtzeiten.
  Der Arbeitsplatz kommt aus den Richtzeiten der Auslastung (Stichwort), Fremdleistung wird Fremdarbeit.
- `Stangen`-Zeilen werden gespeichert und erscheinen im Materialbedarf je Woche.
- `Lieferung`-Zeilen werden Teillieferungen.
- „Material da ab“: Die Auslastung nimmt das späteste Datum über alle Positionen und Stangen als Material-Termin
  des Auftrags.
- `Storno`: Die Auslastung nimmt den Auftrag heraus (in den Papierkorb, wiederherstellbar). Ist er schon gelaufen
  oder teilweise fertig, bleibt er stehen und es kommt nur eine Meldung im Hinweis.
- **Bei einer neuen Freigabe** eines schon eingeplanten Auftrags ändert die Auslastung nur Zeiten, Material, Termin
  und Zusatzarbeiten. Was aus der Werkstatt kommt, bleibt: gelaufen, Start/Stopp, fertig gemeldete Arbeitsgänge,
  fester Platz, Reihenfolge. Ein fertig gemeldeter Auftrag wird nicht mehr geändert (Meldung im Hinweis).

## Richtung 2: Auslastung → Kalkulation (Rückmeldung)

**Datei:** `Rueckmeldung.csv` im selben Ordner. Sie wird bei jeder Fertigmeldung und mindestens einmal am Tag ganz
neu geschrieben, immer der vollständige Stand. Die Kalkulation liest sie nur und ändert in der Auslastung nichts.

| Art | eine Zeile je | Spalten |
|---|---|---|
| `Auftrag` | Auftrag und Arbeitsgang | Auftragsnummer, Pos (leer = ganzer Auftrag), Arbeitsgang (leer = Laser), Maschine, Kalkuliert [min], Tatsächlich [min], Fertig am, Bediener, Status (`offen`, `läuft`, `fertig`), Fertig (Plan), Terminrisiko (`ok`, `knapp`, `nicht zu halten`) |
| `Kapazität` | Maschine und Woche (8 Wochen ab heute) | Maschine, Montag, KW, Verfügbar [h], Verplant [h], Frei [h] |
| `Frühester` | Maschine und Größe | Maschine, Stunden (1, 4, 8, 16), Frühester Fertig-Tag (Datum, ab dem ein neuer Auftrag dieser Größe fertig wäre) |
| `Stangen` (optional, ab 13.11.2026) | Auftrag und Abmessung | Auftragsnummer, Profilform, Maß a [mm], Maß b [mm], Wand [mm], Werkstoff, Stangenlänge [mm] (Texte wie in den Stangen-Zeilen von Richtung 1), Stangen = tatsächlich verbrauchte Stangen. Die Kalkulation trägt sie als Ist-Stangen in die Nachkalkulation ein (beim Versand vorbelegt, sonst Knopf „Verbrauchte Stangen übernehmen“). |

Alle Zeilen haben `Format` = `2` und `Stand` (Datum und Uhrzeit des Schreibens, `TT.MM.JJJJ HH:MM`).

Schlüssel ist die Auftragsnummer. Die Auslastung kennt keine Ist-Zeit je Position, nur je Auftrag und
Arbeitsgang, deshalb bleibt `Pos` leer. Zusatzarbeiten erkennt die Kalkulation am Arbeitsgang-Namen (`Arbeit` aus
Richtung 1).

## Wer baut was

| Teil | Programm | Thread |
|---|---|---|
| Auftragsdatei schreiben (beauftragt, neue Freigabe, Knopf Übergabe) | Kalkulation (`programm/rohrlaser`) | Nächste Verbesserungen der Kalkulation |
| Rückmeldung lesen: Ist-Zeiten, Lieferzeit-Vorschlag im Angebot (abschaltbar) | Kalkulation | Nächste Verbesserungen der Kalkulation |
| Format 2 einlesen, Rückmeldung schreiben, Einstellung Ordner | Auslastung (`programm/rl_auslastung`, 2.8) | /Plan |
| Diese Beschreibung, Beispieldateien, Prüfung beider Seiten | beide | /Plan |

Kein gemeinsamer Code: Die Auslastung lädt aus der Kalkulation nur Rechenkern, Feiertage, Design, Grafik und das
Online-Update (Test R6). Die Beispieldateien in `docs/schnittstelle-beispiel/` sind der gemeinsame Prüfstand: Die
Kalkulation prüft, dass ihr Export dieselben Spalten schreibt, die Auslastung prüft, dass sie die Beispiele liest.
