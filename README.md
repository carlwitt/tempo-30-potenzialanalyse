# Tempo-30-Potenzialanalyse

Dieses Projekt wertet OpenStreetMap-Daten (OSM) aus und exportiert GeoJSON-Layer für die Prüfung möglicher Tempo-30-Abschnitte. Ein Treffer ist ein **Prüfhinweis**, keine Aussage über die rechtliche Zulässigkeit oder eine bereits umgesetzte Maßnahme. Die Daten werden von uMap als entfernte Layer geladen; die Berechnung und die Exporte liegen in diesem Repository, nicht in uMap.

## Lokal ausführen

Benötigt wird Python 3.11 oder neuer. Vom Repository-Verzeichnis aus:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
MPLBACKEND=Agg .venv/bin/python main.py Berlin
.venv/bin/python -m unittest discover -s tests
```

Ohne Argument wird München berechnet. Die GeoJSON-Dateien landen in `GEOJSON_EXPORT/<Gebiet>/`. `overpass_cache/` und `GEOJSON_EXPORT/` bleiben lokal und werden nicht eingecheckt. Beim ersten Lauf werden OSM-Daten über Overpass abgerufen; spätere Läufe verwenden den lokalen Cache. Eine Neuberechnung mit aktuellen OSM-Daten erfordert, die betreffenden Cache-Dateien gezielt zu entfernen.

Die wichtigsten Berlin-Layer sind `potential_streets_map.geojson` (Straßenabschnitte mit Potenzial einschließlich direkter Lückenschlüsse und Anschluss-Kontext, ohne bedingte Lückenschlüsse), `conditional_gap_streets.geojson` (bedingte Lückenschlüsse mit `is_conditional_gap=true` und benötigten Vormaßnahmen), `facility_covered_street_segments.geojson` (angrenzende bereits abgedeckte Abschnitte, bis 500 m entlang der Straße), `zebra.geojson` (Überwege als Segment und Marker), die Einrichtungs-Layer sowie `district_stats.geojson`. Die bisherige Datei `potential_streets.geojson` enthält weiterhin alle Potenzialstraßen einschließlich bedingter Lückenschlüsse, damit die bestehende Münchner uMap unverändert geladen werden kann. Die vollständigen Einrichtungsdateien bleiben zur Prüfung erhalten; uMap lädt deren `*_map.geojson`-Ansichten mit offenen Potenzialen. Unbestätigte bzw. anders zugeordnete soziale Einrichtungen bleiben nur im vollständigen Export mit `facility_status` erhalten; sie erscheinen nicht in der Karte und zählen weder als Behinderten-Potenzial noch in die Bezirksquote. `accidents.geojson` enthält die Berliner Unfallatlas-Unfälle mit Personenschaden seit 2022 als gewichtete Heatmap; siehe [uMap-Konfiguration](uMapFrontend/README.md). Die OSM-Geschwindigkeitsübersicht und `facility_street_segments.geojson` werden intern weiter für Berechnung und Popups benötigt, aber nicht als uMap-Layer angezeigt.

In den drei Straßen-Potenzial-Dateien entfallen einzelne OSM-Teilstücke bis einschließlich 20 m und logische Abschnitte bis einschließlich 50 m. Kurze Teilstücke bleiben erhalten, wenn sie einen längeren bedingten Lückenschluss verbinden; dessen zusammenhängende Teilstücke mit gleichen Voraussetzungen werden zu einem Kartenobjekt vereinigt. Das betrifft nur diese Exporte, nicht die Quellberechnung oder Bezirksstatistik.

Methodik, Felddefinitionen und Grenzen stehen in [docs/methodik.md](docs/methodik.md). Der [Vergleich mit den veröffentlichten Münchner Remote-Layern](docs/munich-export-compatibility.md) dokumentiert das bestehende GeoJSON-Schema und die Inhaltsunterschiede. Die Unit-Tests arbeiten mit kleinen OSM-/Geometrie-Fixtures und benötigen keinen Overpass-Zugriff.

## Weitere Datenquellen über WFS

[additional_features.json](additional_features.json) konfiguriert zusätzliche Einrichtungen ohne quellenspezifisches Python-Skript. Der Berlin-Eintrag lädt das amtliche Kita-Verzeichnis über WFS 2.0/GeoJSON und ordnet ihm `amenity=kindergarten` zu. `fields` bildet interne Feldnamen auf Attribute des Dienstes ab; `areas` begrenzt die Quelle auf die genannten Berechnungsgebiete und `layer` bestimmt die Einrichtungsebene.

Der WFS-Endpunkt dient nur dem Datenabruf. Einrichtungs-Popups verlinken die [öffentliche Berliner Datensatzseite](https://daten.berlin.de/datensaetze/kindertagesstatten-wfs-d03b94d2); ein nicht zugeordnetes amtliches Objekt erhält keinen erfundenen OSM-Link.

```bash
# Der normale Berechnungslauf lädt und merged die konfigurierten Quellen.
# Anschließend entstehen GeoJSON-Dateien und additional_features_statistics.json.
MPLBACKEND=Agg .venv/bin/python main.py Berlin
```

Die Kita Papagei, Treskowallee 124, ist dort unter `e_nr=11171690` vorhanden. Eindeutige Treffer ergänzen vorhandene OSM-Einrichtungen, weitere Einrichtungen fließen mit externer Identität in Berechnung und Popups ein. Mehrdeutige Zuordnungen werden mit Warnung zurückgestellt, nicht geraten. Der Statistikexport dokumentiert den Merge und Kita-Zahlen vor/nach Straßenfilter und Potenzialprüfung. Externe Features erhalten keine erfundenen OSM-IDs oder OSM-Links. Details, Match-Kriterien und Grenzen: [WFS-Schnittstelle](docs/methodik.md#wfs-schnittstelle-für-externe-quellen).
