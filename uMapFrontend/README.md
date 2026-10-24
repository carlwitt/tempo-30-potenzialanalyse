# Berlin-uMap-Konfiguration

`umap_backup_tempo-30-potenziale-berlin.umap` ist der unveränderte Ausgangspunkt. Mit

```sh
python uMapFrontend/build_berlin_map.py
```

wird `tempo-30-potenziale-berlin.umap` reproduzierbar erzeugt. Die Datei enthält 12 Remote-Layer, aber keine eingebetteten GeoJSON-Features. Sie kann zunächst als **neue** Karte in uMap importiert und dort geprüft werden; eine bestehende Karte wird durch das Erzeugen dieser Datei nicht verändert. Die Sicherung enthält keine lokalen Feature-Kommentare.

Alle Layer erwarten die jeweiligen Dateien unter `https://tempo-30.adfc-berlin.de/uMap/`. Die lokalen Gegenstücke liegen in `GEOJSON_EXPORT/Berlin/` und müssen separat auf dem Server veröffentlicht werden. Die Erreichbarkeit des Hosts wurde bei der Erstellung nicht bestätigt. Die große OSM-Geschwindigkeitsübersicht ist nicht mehr in der Karte; `disability_facilities_review.geojson` liegt bei den sensiblen Einrichtungen. Die Unfall-Heatmap ist wegen ihrer Datenmenge beim Laden ausgeschaltet und kann bei Bedarf aktiviert werden.

`accidents.geojson` wird für Berlin aus den offiziellen Unfallatlas-CSV-Jahresarchiven 2022–2025 erzeugt. `ULAND=11` begrenzt die Auswahl auf Berlin; `heat_weight` berechnet sich aus `2**(6-UKATEGORIE)` (32/16/8). Die ZIP-Dateien werden unter `overpass_cache/unfallatlas/` zwischengespeichert. Neue verfügbare Jahre müssen in `AccidentAtlasExport.YEARS` ergänzt werden. Die Heatmap-Normierung erfolgt durch uMap je Zoomstufe relativ zur dortigen Maximaldichte, nicht auf eine feste absolute Skala. Unfallatlas: [OpenGeodata NRW](https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/), Lizenz [DL-DE/BY-2.0](https://www.govdata.de/dl-de/by-2-0).

Die Bezirks-Choroplethenkarte verwendet `realized_potential_pct_total` als numerisches Feld. „Realisiert“ bedeutet hier nur „kein offenes Potenzial nach den Berechnungsregeln“; es bestätigt keine tatsächlich angeordnete Tempo-30-Maßnahme. Zur Berechnung und ihren Grenzen siehe [Methodik](../docs/methodik.md).

Einrichtungs-Layer verwenden `popup_content`: ein verlinkter OSM-Name, nur vorhandene Angaben wie Betreiber und eine gemeinsame Zeile für Street View und Mapillary. Bei offenen Potenzialen kommen Anlass und verknüpfte Prüfabschnitte hinzu. `description` behält die ausführlicheren OSM-Prüfangaben; die separaten Bild-URLs werden aus dem nächstgelegenen Tempo-50/60-Way erzeugt. Nach Änderungen am Export müssen die Remote-GeoJSON-Dateien erneut veröffentlicht werden, damit die neue Popup-Vorlage sichtbar wird.
