# Tempo-30-Potenzialanalyse

Dieses Projekt wertet OpenStreetMap-Daten (OSM) aus und exportiert GeoJSON-Layer für die Prüfung möglicher Tempo-30-Abschnitte. Ein Treffer ist ein **Prüfhinweis**, keine Aussage über die rechtliche Zulässigkeit oder eine bereits umgesetzte Maßnahme. Die Daten werden von uMap als entfernte Layer geladen; die Berechnung und die Exporte liegen in diesem Repository, nicht in uMap.

## Lokal ausführen

Benötigt wird Python 3.11 oder neuer. Vom Repository-Verzeichnis aus:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
MPLBACKEND=Agg .venv/bin/python main.py Berlin \
  --public-road-candidates --validate-osm-sources --broaden-facilities \
  --near-road-facilities --confirmed-disability-only --strict-gap-evidence \
  --clip-long-potentials --filter-short-potentials \
  --simplify-crossings --compact-playgrounds \
  --additional-features --prefer-main-entrances
.venv/bin/python -m unittest discover -s tests
```

Ohne Argument wird München berechnet. Die GeoJSON-Dateien landen in `GEOJSON_EXPORT/<Gebiet>/`. `overpass_cache/` und `GEOJSON_EXPORT/` bleiben lokal und werden nicht eingecheckt. Beim ersten Lauf werden OSM-Daten über Overpass abgerufen; spätere Läufe verwenden den lokalen Cache. Eine Neuberechnung mit aktuellen OSM-Daten erfordert, die betreffenden Cache-Dateien gezielt zu entfernen.

**Neue Prüfregeln sind Opt-in, nicht vom Gebietsnamen abhängig.** Ohne Flags bleibt die Berechnung beim Regelstand von `main`; additive Prüffelder und zusätzliche Kartenansichten bleiben verfügbar. Die drei [Weekly-Workflows](.github/workflows/) wählen die Regeln ausdrücklich in ihrem `Run main.py`-Schritt: München ohne neue Regeln, Berlin und Potsdam mit allen Regeln. `--additional-features` lädt die zum Gebiet passenden Quellen und Grenzfilter aus [additional_features.json](additional_features.json); der Python-Einstieg enthält dafür keine ortsspezifische Fallunterscheidung. OSM-Haupteingänge werden für Prüfbilder immer geladen; `--prefer-main-entrances` nutzt sie zusätzlich vor der Gebäudegeometrie bei der Straßenwahl. Eine Regel wird durch Hinzufügen bzw. Entfernen ihres CLI-Flags aktiviert bzw. deaktiviert. Die vollständige [Flag-Tabelle und der reproduzierbare München-Abgleich](docs/munich-export-compatibility.md) erklären die Unterschiede. `python main.py --help` zeigt alle Optionen.

Die wichtigsten Berlin-Layer sind `potential_streets_map.geojson` (Straßenabschnitte mit Potenzial einschließlich direkter Lückenschlüsse und Anschluss-Kontext, ohne bedingte Lückenschlüsse), `conditional_gap_streets.geojson` (bedingte Lückenschlüsse mit `is_conditional_gap=true` und benötigten Vormaßnahmen), `facility_covered_street_segments.geojson` (angrenzende bereits abgedeckte Abschnitte, bis 500 m entlang der Straße), `zebra.geojson` (Überwege als Segment und Marker), die Einrichtungs-Layer sowie `district_stats.geojson`. Die bisherige Datei `potential_streets.geojson` enthält weiterhin alle Potenzialstraßen einschließlich bedingter Lückenschlüsse, damit die bestehende Münchner uMap unverändert geladen werden kann. Die vollständigen Einrichtungsdateien bleiben zur Prüfung erhalten; uMap lädt deren `*_map.geojson`-Ansichten mit farbigen aktiven und grauen inaktiven Indikatoren. Unbestätigte bzw. anders zugeordnete soziale Einrichtungen bleiben nur im vollständigen Export mit `facility_status` erhalten; sie erscheinen nicht in der Karte und zählen weder als Behinderten-Potenzial noch in die Bezirksquote. `accidents.geojson` enthält die Berliner Unfallatlas-Unfälle mit Personenschaden seit 2022 als gewichtete Heatmap; siehe [uMap-Konfiguration](uMapFrontend/README.md). Die OSM-Geschwindigkeitsübersicht und `facility_street_segments.geojson` werden intern weiter für Berechnung und Popups benötigt, aber nicht als uMap-Layer angezeigt.

Mit `--filter-short-potentials` entfallen in den drei Straßen-Potenzial-Dateien einzelne OSM-Teilstücke bis einschließlich 20 m und logische Abschnitte bis einschließlich 50 m. Kurze Teilstücke bleiben erhalten, wenn sie einen längeren bedingten Lückenschluss verbinden; dessen zusammenhängende Teilstücke mit gleichen Voraussetzungen werden zu einem Kartenobjekt vereinigt. Das betrifft nur diese Exporte, nicht die Quellberechnung oder Bezirksstatistik.

Methodik, Felddefinitionen und Grenzen stehen in [docs/methodik.md](docs/methodik.md). Der [Vergleich mit den veröffentlichten Münchner Remote-Layern](docs/munich-export-compatibility.md) dokumentiert das bestehende GeoJSON-Schema und die Inhaltsunterschiede. Die Unit-Tests arbeiten mit kleinen OSM-/Geometrie-Fixtures und benötigen keinen Overpass-Zugriff.

## Weitere Datenquellen über WFS

[additional_features.json](additional_features.json) konfiguriert zusätzliche Einrichtungen ohne quellenspezifisches Python-Skript. Der Berlin-Eintrag lädt das amtliche Kita-Verzeichnis über WFS 2.0/GeoJSON und ordnet ihm `amenity=kindergarten` zu. `fields` bildet interne Feldnamen auf Attribute des Dienstes ab; `areas` begrenzt die Quelle auf die genannten Berechnungsgebiete und `layer` bestimmt die Einrichtungsebene.

Der optionale Abschnitt `filters` deklariert räumliche Grenzen ebenfalls über `areas`. Ein `osm_boundary`-Eintrag enthält die Overpass-Abfrage `query`, den OSM-Schlüssel `id_tag` für die Bezirkskennung sowie einen versionierten `cache_datatype`. `AdditionalFeatures` lädt die Grenze und filtert Quellobjekte und das vollständige Lückennetz; der Export nutzt dieselbe Grenze für Zuschnitt und Bezirksstatistik. Für Gebiete ohne passenden Filter bleibt das Verhalten unverändert. Aktuell ist dieser Filter nur für Berlin konfiguriert; weitere Gebiete benötigen keine neue CLI-Option.

Der WFS-Endpunkt dient nur dem Datenabruf. Einrichtungs-Popups verlinken die [öffentliche Berliner Datensatzseite](https://daten.berlin.de/datensaetze/kindertagesstatten-wfs-d03b94d2); ein nicht zugeordnetes amtliches Objekt erhält keinen erfundenen OSM-Link.

```bash
# --additional-features lädt und merged die konfigurierten Quellen.
# Anschließend entstehen GeoJSON-Dateien und additional_features_statistics.json.
MPLBACKEND=Agg .venv/bin/python main.py Berlin --additional-features
```

Die Kita Papagei, Treskowallee 124, ist dort unter `e_nr=11171690` vorhanden. Eindeutige Treffer ergänzen vorhandene OSM-Einrichtungen, weitere Einrichtungen fließen mit externer Identität in Berechnung und Popups ein. Mehrdeutige Zuordnungen werden mit Warnung zurückgestellt, nicht geraten. Der Statistikexport dokumentiert den Merge und Kita-Zahlen vor/nach Straßenfilter und Potenzialprüfung. Externe Features erhalten keine erfundenen OSM-IDs oder OSM-Links. Details, Match-Kriterien und Grenzen: [WFS-Schnittstelle](docs/methodik.md#wfs-schnittstelle-für-externe-quellen).
