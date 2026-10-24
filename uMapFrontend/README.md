# Berlin-uMap-Konfiguration

`umap_backup_tempo-30-potenziale-berlin.umap` ist der unveränderte Ausgangspunkt. Mit

```sh
python uMapFrontend/build_berlin_map.py
```

wird `tempo-30-potenziale-berlin.umap` reproduzierbar erzeugt. Die Datei enthält 12 Remote-Layer, aber keine eingebetteten GeoJSON-Features. Sie kann zunächst als **neue** Karte in uMap importiert und dort geprüft werden; eine bestehende Karte wird durch das Erzeugen dieser Datei nicht verändert. Die Sicherung enthält keine lokalen Feature-Kommentare.

Alle Layer erwarten die jeweiligen Dateien unter `https://tempo-30.adfc-berlin.de/uMap/`. Die lokalen Gegenstücke liegen in `GEOJSON_EXPORT/Berlin/` und müssen separat auf dem Server veröffentlicht werden. Die Erreichbarkeit des Hosts wurde bei der Erstellung nicht bestätigt. `streets_and_limit.geojson` ist wegen seiner Größe standardmäßig ausgeschaltet.

Die Bezirks-Choroplethenkarte verwendet `realized_potential_pct_total` als numerisches Feld. „Realisiert“ bedeutet hier nur „kein offenes Potenzial nach den Berechnungsregeln“; es bestätigt keine tatsächlich angeordnete Tempo-30-Maßnahme. Zur Berechnung und ihren Grenzen siehe [Methodik](../docs/methodik.md).

Einrichtungs-Layer verwenden `popup_content`: ein verlinkter OSM-Name, nur vorhandene Angaben wie Betreiber und eine gemeinsame Zeile für Street View und Mapillary. Bei offenen Potenzialen kommen Anlass und verknüpfte Prüfabschnitte hinzu. `description` behält die ausführlicheren OSM-Prüfangaben; die separaten Bild-URLs werden aus dem nächstgelegenen Tempo-50/60-Way erzeugt. Nach Änderungen am Export müssen die Remote-GeoJSON-Dateien erneut veröffentlicht werden, damit die neue Popup-Vorlage sichtbar wird.
