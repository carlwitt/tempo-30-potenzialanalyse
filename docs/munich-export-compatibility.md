# Münchner GeoJSON-Kompatibilität (25.10.2026)

Die [bestehende Münchner uMap](https://umap.openstreetmap.de/de/map/tempo-30-potentialkarte-munchen_127687) lädt acht Remote-Feature-Layer von `https://www.munichways.de/App/tempo30_geojson/latest/`. Am 25.10.2026 wurden die acht dort tatsächlich referenzierten Dateien heruntergeladen und mit einem frischen Lauf von `python main.py` für München verglichen. Die Downloads liegen lokal unter `reference-potentials/munich-remote-2026-10-25/` (laut `.gitignore` nicht im PR); [der eingecheckte Vertrag](../DataOutput/munich_remote_contract.json) enthält URLs, SHA-256-Prüfsummen und das beobachtete Schema.

| Bisheriger Remote-Layer | Live-Features | Neuer Export |
| --- | ---: | ---: |
| `disability_facilities.geojson` | 6 | 12 |
| `educational_buildings.geojson` | 491 | 1.491 |
| `elderly_homes.geojson` | 35 | 53 |
| `hospitals.geojson` | 16 | 44 |
| `playgrounds.geojson` | 6.396 | 1.981 |
| `potential_streets.geojson` | 734 | 610 |
| `streets_and_limit.geojson` | 61.140 | 61.167 |
| `zebra.geojson` | 1.045 | 636 |

Der [Prüfschritt](../DataOutput/verify_munich_export.py) läuft im Münchner Wochenworkflow **vor dem Upload**. Alle acht Dateien bestehen die Prüfung: Sie sind GeoJSON-FeatureCollections mit denselben Dateinamen; alle bisherigen Feldnamen kommen weiterhin vor; bisher durchgängig vorhandene Felder fehlen bei keinem Feature; ihre Werttypen bleiben erhalten. Die Geometrietypen entsprechen dem jeweils veröffentlichten Layer, und `feature_type` sowie die `maxspeed_class`-Legendenwerte bleiben im bisherigen Wertebereich. Neue Felder und neue Dateien sind zugelassen. Die Geschwindigkeitsübersicht enthält wieder den breiten OSM-Straßenkontext; nur öffentlich befahrbare Straßen gehen in die Potenzialrechnung ein. Der alte `potential_streets.geojson`-Layer enthält weiterhin auch bedingte Lücken. Die neue Berliner Ansicht `potential_streets_map.geojson` trennt diese aus und ergänzt Anschluss-Kontext. Vollständige Einrichtungs-Layer und kompakte `*_map.geojson`-Ansichten werden separat exportiert.

**Die Feature-Menge ist nicht identisch und nicht rein additiv.** Von 734 live veröffentlichten Potenzial-OSM-IDs enthält der neue Export 357; 377 bisherige IDs fehlen und 252 kommen hinzu. Im Geschwindigkeits-Layer sind dagegen 61.136 von 61.140 bisherigen OSM-IDs weiterhin vorhanden. Die genauen ID-Differenzen stehen lokal in `reference-potentials/munich-remote-2026-10-25/osm_id_comparison.json`. Auch die Spielplatz- und Überwegzahlen ändern sich stark. Das ist ein inhaltlicher Unterschied zwischen dem veröffentlichten Stand und der aktuellen Berechnung, kein Schemaproblem; OSM-Abfragezeitpunkt und Prüfregeln sind verschieden. Der Vertrag schützt ausdrücklich die Datenstruktur der bestehenden Konsumenten, nicht unveränderte Potenzialergebnisse. Wer auch eine unveränderte Feature-Menge voraussetzt, muss diese Änderungen vor dem PR gesondert fachlich bewerten.

Lokale Reproduktion: `python main.py` (mit vorhandenem Overpass-Cache), danach `python DataOutput/verify_munich_export.py`. Ein neuer Download der Remote-Dateien kann andere Inhalte liefern; die SHA-256-Werte im Vertrag bezeichnen genau den hier verglichenen Stand.
