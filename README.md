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

Die wichtigsten Berlin-Layer sind `potential_streets.geojson` (Straßenabschnitte mit Potenzial, einschließlich `is_conditional_gap` und benötigter Vormaßnahmen), `facility_street_segments.geojson` (auf 20 m um eine Einrichtung gekürzte Potenzialabschnitte), `facility_covered_street_segments.geojson` (angrenzende bereits abgedeckte Abschnitte, bis 500 m entlang der Straße), `zebra.geojson` (Überwege als Segment und Marker), die Einrichtungs-Layer sowie `district_stats.geojson`. `disability_facilities_review.geojson` enthält unbestätigte bzw. anders zugeordnete soziale Einrichtungen und liegt in der Karte bei den anderen sensiblen Einrichtungen. `accidents.geojson` enthält die Berliner Unfallatlas-Unfälle mit Personenschaden seit 2022 als gewichtete Heatmap; siehe [uMap-Konfiguration](uMapFrontend/README.md). Die OSM-Geschwindigkeitsübersicht wird intern weiter für die Berechnung benötigt, aber nicht mehr als uMap-Layer angezeigt.

Im Straßen-Potenzial-Layer entfallen einzelne OSM-Teilstücke bis einschließlich 20 m und logische Abschnitte bis einschließlich 50 m. Kurze Teilstücke bleiben erhalten, wenn sie einen längeren bedingten Lückenschluss verbinden; dessen zusammenhängende Teilstücke mit gleichen Voraussetzungen werden zu einem Kartenobjekt vereinigt. Das betrifft nur diesen Export, nicht die Quellberechnung oder Bezirksstatistik.

Methodik, Felddefinitionen und Grenzen stehen in [docs/methodik.md](docs/methodik.md). Die Unit-Tests arbeiten mit kleinen OSM-/Geometrie-Fixtures und benötigen keinen Overpass-Zugriff.
