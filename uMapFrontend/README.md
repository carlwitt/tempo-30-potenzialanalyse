# uMap-Konfiguration

`umap_backup_tempo-30-potenziale-berlin.umap` ist der unveränderte Ausgangspunkt. Mit

```sh
sh uMapFrontend/build_berlin_map.sh
```

wird `tempo-30-potenziale-berlin.umap` reproduzierbar erzeugt. Die Datei enthält 11 Remote-Layer, aber keine eingebetteten GeoJSON-Features. Beim Laden sind nur die allgemeinen Straßen-Potenziale sichtbar; bedingte Lückenschlüsse, Einrichtungs-, Zebrastreifen-, Statistik- und Unfall-Layer können bei Bedarf eingeschaltet werden. Sie kann zunächst als **neue** Karte in uMap importiert und dort geprüft werden; eine bestehende Karte wird durch das Erzeugen dieser Datei nicht verändert. Die Sicherung enthält keine lokalen Feature-Kommentare.

`build_umap_configuration.py` erspart bei einem neuen Gebiet die manuelle Anlage der Remote-GeoJSON-Layer samt Stilen, Popup-Feldern und Beschreibungen. Es übernimmt die Kartenvorlage und verweist die Layer auf die Exporte des gewählten Gebiets. Der Shell-Wrapper `build_berlin_map.sh` übergibt die Berliner Pfade, Daten-URL, Gebiets- und Kartennamen sowie Unfalljahre. Er funktioniert unabhängig vom Arbeitsverzeichnis; mit `PYTHON=.venv/bin/python sh uMapFrontend/build_berlin_map.sh` lässt sich der Python-Interpreter wählen (bei relativem Interpreterpfad vom Repository-Verzeichnis aus). Zusätzliche Argumente überschreiben die Wrapper-Werte, beispielsweise `sh uMapFrontend/build_berlin_map.sh --output /tmp/berlin.umap`.

Die Layer- und Indikatorgruppenbeschreibungen werden aus [layer_descriptions.yaml](layer_descriptions.yaml) neben dem Python-Skript geladen, unabhängig vom Arbeitsverzeichnis. Texte können dort ohne Python-Änderungen gepflegt werden; `>-` verbindet die Textzeilen mit Leerzeichen ohne abschließenden Zeilenumbruch. Der Eintrag `accidents` verwendet die Platzhalter `{area_name}` und `{accident_start_year}`, die der Builder aus den Kommandozeilenoptionen einsetzt. Zum Laden wird PyYAML aus den Projektabhängigkeiten benötigt (`python3 -m pip install -r requirements.txt`).

Für andere Gebiete kann der Python-Builder direkt aufgerufen werden:

```sh
python3 uMapFrontend/build_umap_configuration.py \
  --backup /path/to/template.umap \
  --output /path/to/potsdam.umap \
  --remote-base https://example.org/potsdam/uMap \
  --area-name Potsdam \
  --map-name "Tempo 30 Potenziale Potsdam" \
  --accident-start-year 2022 \
  --accident-end-year 2025
```

Die Vorlage muss dieselbe Struktur wie die Sicherung haben: eine Indikatorgruppe mit Spielplätzen, Zebrastreifen, Behinderteneinrichtungen und Krankenhäusern sowie einen Bezirksstatistik-Layer. Kartenposition, URI, Grundkarte und Marker-Stile werden aus dieser Vorlage übernommen; für ein anderes Gebiet muss sie entsprechend vorbereitet werden. Alle Remote-GeoJSON-URLs werden auf die angegebene Basis umgestellt. Die Optionen konfigurieren nur die Karte, nicht die Datenberechnung: insbesondere müssen Bezirks- und Unfalldaten für das gewählte Gebiet separat bereitgestellt werden.

Alle Layer erwarten die jeweiligen Dateien unter `https://tempo-30.adfc-berlin.de/uMap/`. Die lokalen Gegenstücke liegen in `GEOJSON_EXPORT/berlin/` und müssen separat auf dem Server veröffentlicht werden. Die Erreichbarkeit des Hosts wurde bei der Erstellung nicht bestätigt. Die große OSM-Geschwindigkeitsübersicht ist nicht mehr in der Karte. Einrichtungs-Layer verwenden `*_map.geojson` mit offenen Kandidaten statt der vollständigen Quelldateien; bereits abgedeckte Einrichtungen erscheinen dadurch auch nach Einschalten dieser Layer nicht als blaue Punkte. Behinderteneinrichtungen mit fehlender oder anderer OSM-Zielgruppe werden vorerst nicht in der Karte dargestellt und gehen nicht in die Potenzialstatistik ein. Im vollständigen Export bleibt ihr `facility_status` für eine spätere Prüfung erhalten. Die Unfall-Heatmap bleibt als zuschaltbarer Layer erhalten; ihre GeoJSON-Datei ist groß und kann deshalb etwas Ladezeit benötigen.

Der Karten-Builder lädt keine GeoJSON-Dateien hoch. Zeigt eine neu importierte `.umap`-Datei nur rote Straßen, ist zuerst die Serverdatei `potential_streets.geojson` zu prüfen: Ein älterer Export enthält das Farbfeld `map_potential_type` noch nicht. Die Konfiguration unterstützt für solche Exporte zusätzlich `feature_type` und `gap_role`; für die korrekte Farbe bei mehreren Potenzialgründen muss der aktuelle GeoJSON-Export veröffentlicht werden.

Die Straßengruppe trennt „Straßenabschnitte mit Tempo-30-Potenzial“ (`potential_streets.geojson`, einschließlich direkter Lückenschlüsse) und „Bedingte Lückenschlüsse“ (`conditional_gap_streets.geojson`). Nur der allgemeine Potenzial-Layer ist beim Laden sichtbar. Dort sind Einrichtungs- und Spielplatzpotenziale rot, Zebrastreifenpotenziale orange, direkte Lückenschlüsse samt durchlaufenen Abschnitten violett und bestehende Tempo-30-Anschlüsse grün. Bei mehreren Gründen bestimmt Lückenschluss vor Zebrastreifen vor Einrichtung die Farbe; die Gründe bleiben im Popup erhalten. Das Feld `map_potential_type` steuert nur diese Darstellung und ändert weder Berechnung noch Statistik. Bereits als Potenzial dargestellte Zwischenabschnitte werden nicht doppelt gezeichnet. Bedingte Lückenschlüsse erscheinen nach dem Einschalten violett gestrichelt; ein bestehender, dauerhaft geltender Tempo-30-Anschluss ist grün. Der noch offene Anschluss und sein auslösender Ort stehen mit OSM-Links im Lücken-Popup, ohne zusätzliche Linie über den ganzen Anschlussweg. Zeitabhängiges Tempo 30 zählt nicht als bestehender Anschluss. Die vollständige OSM-Geometrie dient als Kontext, nicht als festgelegte Anordnungsgrenze. Der Layer „Prüfabschnitte an Einrichtungen“ ist aus der Karte entfernt; seine Daten können für Einrichtungs-Popups weiterhin exportiert werden. Bei der Umstellung müssen die neuen Exporte veröffentlicht und die aktualisierte uMap-Konfiguration importiert werden.

`target_speed_kmh=30` kennzeichnet den Zielzustand der eigentlichen Lücke. Die noch nicht umgesetzte Maßnahme am anderen Ende bleibt als Voraussetzung in `gap_required_potentials` erhalten; sie wird nicht als zusätzlicher Straßenabschnitt gezeichnet.

Ein bedingter Lückenschluss setzt auf der Gegenseite bereits bestehendes Tempo 30 voraus. **Nur ein Anschluss darf noch nicht umgesetzt sein**; zwei offene Anschluss-Potenziale werden nicht als bedingte Lücke berechnet. Mehrere Maßnahmen am selben offenen Anschluss sind Alternativen, nicht zusätzliche offene Enden.

`accidents.geojson` wird für Berlin aus den offiziellen Unfallatlas-CSV-Jahresarchiven 2022–2025 erzeugt. `ULAND=11` begrenzt die Auswahl auf Berlin; `heat_weight` berechnet sich aus `2**(6-UKATEGORIE)` (32/16/8). Die ZIP-Dateien werden unter `overpass_cache/unfallatlas/` zwischengespeichert. Neue verfügbare Jahre müssen in `AccidentAtlasExport.YEARS` ergänzt werden. Die Heatmap-Normierung erfolgt durch uMap je Zoomstufe relativ zur dortigen Maximaldichte, nicht auf eine feste absolute Skala. Unfallatlas: [OpenGeodata NRW](https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/), Lizenz [DL-DE/BY-2.0](https://www.govdata.de/dl-de/by-2-0).

Die Bezirks-Choroplethenkarte ist beim Laden ausgeblendet und kann bei Bedarf eingeschaltet werden. Sie verwendet `realized_potential_pct_total` als numerisches Feld. „Realisiert“ bedeutet hier nur „kein offenes Potenzial nach den Berechnungsregeln“; es bestätigt keine tatsächlich angeordnete Tempo-30-Maßnahme. Zur Berechnung und ihren Grenzen siehe [Methodik](../docs/methodik.md).

Einrichtungs-Layer verwenden `popup_content`: ein verlinkter OSM-Name, nur vorhandene Angaben wie Betreiber und eine gemeinsame Zeile für Street View und Mapillary. Bei offenen Potenzialen kommen Anlass und verknüpfte Prüfabschnitte hinzu. `description` behält die ausführlicheren OSM-Prüfangaben; die separaten Bild-URLs werden aus dem nächstgelegenen Tempo-50/60-Straßenabschnitt erzeugt. Nach Änderungen am Export müssen die Remote-GeoJSON-Dateien erneut veröffentlicht werden, damit die neue Popup-Vorlage sichtbar wird.
