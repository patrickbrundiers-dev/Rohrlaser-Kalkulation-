# Zukaufartikelverwaltung optional (Master-Auftrag 23.11.2026)

## Ergebnis

* Neuer Schalter **Einstellungen → Funktionen → Zentrale Zukaufartikelverwaltung** (`funktion_zukauf_stamm`),
  **Vorgabe aus**, jederzeit umschaltbar. Wirkt nur, wenn „Zukaufteile“ (`funktion_zukauf`) an ist.
* **Aus:** Zukaufartikel gehören nur zum Angebot (`positionen.zukauf`, Liste mit vollständigem Preisstand je
  Eintrag, wie seit #457 für freie Einträge). Die Unterreiter Artikel, Preisänderungen und Normteile sind
  ausgeblendet; Kategorien, Lieferanten und Materialgruppen bleiben (Materialanfrage). STEP-Import, Blech-Editor,
  Schnellanlage, Dreh-/Frästeil-Preis und „EK eintragen“ schreiben nur noch ins Angebot.
* **Ein:** wie bisher (Stamm, Vergleich mit Stammpreisen, „Aus Stammdaten aktualisieren“, Merken in den Stamm).
* **Umschalten ändert nichts** an Angeboten oder am Stamm. Beim Umschalten zeigt das Programm eine reine
  Bestandsprüfung (wie viele Positionen Stammartikel bzw. freie Einträge haben).
* **Keine neue Tabelle, kein Schema-Sprung.**

## Dialog „Zukaufteile …“

Spalten Bezeichnung, Menge, Einheit, Artikelnr., Lieferant, Einzel-EK, **EK gesamt**, Aufschlag, VK, Gesamt,
Herkunft. Neu: ▲▼ Reihenfolge, **Mehrere hinzufügen …** (eine Zeile je Artikel, Tab oder `;` getrennt, direkt aus
Excel einfügbar: Bezeichnung; Menge; EK; Artikelnr.; Lieferant), **Aus anderem Angebot …** (Angebot suchen,
Einträge wählen, unabhängige Kopie mit Vermerk „kopiert aus“), Summenzeile mit EK, VK netto, MwSt. und VK brutto.
Hinzufügen, Bearbeiten, Duplizieren, Löschen, Zuordnung zur Position und allgemeine Zusatzposition wie bisher.

## Kalkulation und PDF

Die Rechnung nutzt weiter nur den Preisstand im Eintrag: Ergebnisse sind mit Schalter aus und ein gleich
(Test `test_zukauf_optional.py`). Regel „kein Gewinn auf Zukauf, nur Aufschlag“ bleibt. EK und Aufschlag stehen nie
im Kunden-PDF (geprüft).

## Messung vorher / nachher

`werkzeuge/zukauf_messung.py`: 3.000 Stammartikel, Angebot mit 40 Positionen (20 mit Zukaufteilen, halb Stamm, halb
frei), Median aus 5 Läufen, Abfragen auf `zukauf_*`-Tabellen je Durchlauf. Prüf-PostgreSQL 16 im Container.

| Vorgang | vorher ms | vorher Abfr. | nachher **aus** ms | Abfr. | nachher ein ms | Abfr. |
|---|---:|---:|---:|---:|---:|---:|
| Angebot öffnen | 929 | 23 | 965 | **3** | 920 | 23 |
| Angebot neu rechnen | 114 | 20 | 81 | **0** | 79 | 20 |
| Angebots-Check | 17,1 | 20 | 11,5 | **0** | 13,5 | 20 |
| Dialog Zukaufteile öffnen | 86 | 5 | **8,4** | **0** | 88 | 5 |
| Rechen-Tabellen neu bauen | 20,9 | 1 | **4,2** | 1 | 2,8 | 1 |
| Reiter Zukaufartikel laden | 1.017 | 13 | **3,2** | **3** | 1.011 | 13 |

Vorher gab es den Schalter nicht (Lauf „aus“ und „ein“ gleich, hier „aus“ gezeigt). Das Öffnen eines Angebots
bleibt bei etwa 0,9 s, weil dort andere Teile (Positionen, Tabellen, Oberfläche) die Zeit brauchen; die
Zukauf-Abfragen fallen aber von 23 auf 3. Der Reiter Zukaufartikel (lädt beim Start und nach jedem Abgleich) geht
von etwa 1 s auf 3 ms. Mit Schalter ein ist alles wie vorher.

## Tests

`tests/test_zukauf_optional.py` (12 Szenarien aus dem Auftrag + Blech-Editor, EK, STEP, Materialanfrage ohne Stamm).
Tests, die den Stamm voraussetzen, schalten ihn am Anfang ein.
