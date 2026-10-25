# Münchner GeoJSON-Kompatibilität (25.10.2026)

## Maßgebliche Referenz: aktueller main

Ein alter Live-Export ist **keine** Referenz für unveränderte Prüfregeln: Er vermischt Regeländerungen und den OSM-Abfragezeitpunkt. Maßgeblich ist deshalb ein neuer München-Lauf des unveränderten Remote-`main`, aktuell Commit `9198b1b1d61879a51f5c26a1cb7b2d1b82c15909`. Der Lauf erfolgt in einem eigenen Git-Worktree mit zunächst leerem Cache. Anschließend verwendet der Feature-Branch **denselben Rohdaten-Cache**, ohne neue Regeln zu aktivieren. Damit werden tatsächlich die Algorithmen verglichen, nicht alte und neue OSM-Snapshots.

[compare_munich_baseline.py](../DataOutput/compare_munich_baseline.py) vergleicht alle acht vom aktuellen `main` erzeugten Layer, ihre Feature-Anzahlen einschließlich Duplikaten, bisherigen Eigenschaften, Potenzialentscheidungen und Geometrien. Neue Dateien und additive Eigenschaften werden zugelassen; GeoJSON-Feature-IDs und die Reihenfolge sind unerheblich. Koordinaten werden auf acht Nachkommastellen gerundet (etwa ein Millimeter), um reine Projektions-Rundungsfehler auszublenden. Ein Unterschied führt zu Exit-Code 1. Der bisherige [Schema-Vertrag](../DataOutput/verify_munich_export.py) bleibt eine zusätzliche Strukturprüfung, ersetzt diesen Ergebnisvergleich aber nicht.

Reproduktion aus dem Repository-Verzeichnis (die beiden Zielverzeichnisse dürfen noch nicht existieren):

```sh
ROOT=$(pwd)
git fetch origin main
git worktree add --detach reference-potentials/munich-main-current origin/main
(
  cd reference-potentials/munich-main-current
  MPLBACKEND=Agg "$ROOT/.venv/bin/python" main.py
)
mkdir -p reference-potentials/munich-candidate-current/overpass_cache
cp -p reference-potentials/munich-main-current/overpass_cache/*.json \
  reference-potentials/munich-candidate-current/overpass_cache/
(
  cd reference-potentials/munich-candidate-current
  MPLBACKEND=Agg "$ROOT/.venv/bin/python" "$ROOT/main.py"
)
.venv/bin/python DataOutput/compare_munich_baseline.py \
  --baseline reference-potentials/munich-main-current/GEOJSON_EXPORT/München \
  --candidate reference-potentials/munich-candidate-current/GEOJSON_EXPORT/München \
  --report reference-potentials/munich-current-comparison.json
```

Der Referenz-Worktree bleibt unverändert. Die kopierten Rohdaten sind pro Abfrage identisch; zwischen den verschiedenen Overpass-Abfragen vergehen weiterhin einige Minuten. Die Prüfung ist ein Vergleich des konkret dokumentierten Snapshots, kein Beweis für beliebige zukünftige OSM-Daten.

### Verifiziertes Ergebnis

Beide vollständigen Läufe sind erfolgreich. Der Ergebnisvergleich meldet in **allen acht bisherigen Layern null entfernte, hinzugefügte oder geänderte Features** (zusätzliche Felder und Dateien ausgenommen):

| Layer | Frischer main | Branch ohne Flags |
| --- | ---: | ---: |
| `potential_streets.geojson` | 734 | 734 |
| `streets_and_limit.geojson` | 61.167 | 61.167 |
| `zebra.geojson` | 1.045 | 1.045 |
| `educational_buildings.geojson` | 491 | 491 |
| `hospitals.geojson` | 16 | 16 |
| `elderly_homes.geojson` | 35 | 35 |
| `playgrounds.geojson` | 6.403 | 6.403 |
| `disability_facilities.geojson` | 6 | 6 |

Die Dateien und Vergleichsdaten bleiben lokal unter `reference-potentials/`: [Ergebnisbericht](../reference-potentials/munich-current-comparison.json) und [SHA-256-Manifest der sieben identischen OSM-Rohdaten-Dateien](../reference-potentials/munich-current-source-manifest.json). Sie werden nicht eingecheckt. Der `main`-Worktree wurde nicht verändert; bestehende Exporte im Arbeitsverzeichnis und der Server wurden nicht überschrieben.

Bei der Verifikation wurden folgende Probleme gefunden und behoben:

- Ohne Kurzabschnittsfilter fehlten Export-Metadaten; die vermeintliche Kompatibilitätsvariante brach nach der Berechnung ab. Metadaten entstehen jetzt unabhängig vom Filter, auch bei leeren Potenzial-Layern.
- Externe Zusatzquellen und der Berlin-Grenzfilter waren nicht ausdrücklich steuerbar.
- Quellen-Validierung aktivierte zugleich eine zusätzliche Behinderten-Namensausnahme; Relationen und Namensausnahme hängen jetzt ausschließlich am Broadening-Flag.
- Die neue Geschwindigkeitsdarstellung veränderte ohne Opt-in die bisherige Zonen-Kategorie; im Legacy-Profil bleibt sie unverändert.
- Der größere Puffer mit nachfolgender Distanzprüfung wich auch ohne externe Quellen vom ursprünglichen Pufferverfahren ab; ohne Opt-in wird wieder der unveränderte Suchpuffer genutzt.
- Die Priorität `website` vor `contact:website` änderte 215 bisherige Einrichtungs-Eigenschaften, obwohl die Potenzialentscheidungen bereits identisch waren. Auch diese Erweiterung erfolgt jetzt nur mit `--broaden-facilities`.

**181 Unit-/Regressionstests bestanden**, einschließlich der echten ungefilterten/leeren Exporte, beider Lückenprofile, unabhängiger Flags, der tatsächlichen Weekly-Kommandos und der farbigen/grauen Indikatoransichten. Der zusätzliche historische GeoJSON-Schema-Vertrag besteht für alle acht neu gerechneten Layer. Ein unabhängiger LLM-Code-Review der Regelprofile meldete keine signifikanten verbleibenden Probleme. Dieser Review ergänzt die gemessene Ergebnisgleichheit; er ersetzt weder fachliche Vor-Ort-Prüfung noch Tests mit weiteren zukünftigen OSM-Daten.

## Steuerbare Prüfregeln

Alle zwölf Flags sind standardmäßig aus. Die [Münchner Wochenberechnung](../.github/workflows/weekly_run.yml) verwendet keine; [Berlin](../.github/workflows/weekly_run_berlin.yml) und [Potsdam](../.github/workflows/weekly_run_potsdam.yml) alle. Änderungen werden ausdrücklich im jeweiligen `Run main.py`-Schritt freigegeben. Gebietsspezifische Quellen und Grenzfilter stehen deklarativ in [additional_features.json](../additional_features.json) und werden von `AdditionalFeatures` geladen. Die getesteten Workflow-Kommandos müssen mit den erwarteten Profilen übereinstimmen.

| Flag | Aktivierte Änderung gegenüber main |
| --- | --- |
| `--public-road-candidates` | Öffentliche Auto-Zugänglichkeit, Ausschluss von Autobahnen bei Einrichtungen/Überwegen, erweiterte niedrige Geschwindigkeits-/Zonentags und Erkennung komplexer bedingter Tempo-30-Regeln; auch bedingtes Tempo 30 schließt Überweg-Potenzial aus. |
| `--validate-osm-sources` | Nur selbst passend getaggte Einrichtungen/Überwege statt Geometrie-Stützknoten; widersprüchliche Überweg-Tags ausschließen. |
| `--broaden-facilities` | Schulen/Kitas und Krankenhäuser ohne alte Namensfilter, zusätzliche Krankenhaus-Tags, Einrichtungen aus Multipolygon-Relationen, explizit behinderte Zielgruppe auch ohne Namenshinweis; betreutes Wohnen nur mit Senioren-Zielgruppe. `website` vor `contact:website` nutzen; ohne Flag bleibt das bisherige Website-Feld unverändert. Unabhängig von der Stützknoten-Validierung. |
| `--near-road-facilities` | Nur Einrichtungen im Umfeld öffentlicher Auto-Straßen für die Potenzialberechnung verwenden; vollständige Quell-Exporte erhalten. |
| `--confirmed-disability-only` | Nur `social_facility:for=disabled` erzeugt Behinderten-Potenzial. |
| `--strict-gap-evidence` | Neue direkte/bedingte Lückenschlussregeln mit dauerhaft langsamen Anschlüssen und nachprüfbaren Voraussetzungen statt bisheriger Kettensuche, die auch bedingte Tempo-30-Anschlüsse akzeptiert. |
| `--clip-long-potentials` | Lange Nicht-Lücken-OSM-Wege auf das Umfeld ihrer Quellen zuschneiden. |
| `--filter-short-potentials` | Kurze isolierte Kartenabschnitte ausblenden und bedingte Lückenschlüsse zusammenführen. |
| `--simplify-crossings` | Zusammengehörige Überweg-Geometrien und Marker konsolidieren. |
| `--compact-playgrounds` | Nicht potenzielle Spielplatzpunkte in `playgrounds.geojson` ausblenden statt bisheriger 15-m-Cluster; die Indikatoransicht `playgrounds_map.geojson` behält beide Zustände. |
| `--additional-features` | Konfigurierte externe Quellen einmischen und passende deklarative Grenzfilter laden (Quellzuordnung, vollständiges Lückennetz, Exportzuschnitt und Bezirksstatistik); für adressierte amtliche Punkte den passenden Straßenabstand bis 30 m zulassen. Ohne passenden Grenzfilter bleibt das Netz ungefiltert. |
| `--prefer-main-entrances` | Zugeordnete OSM-Haupteingänge vor der Gebäudegeometrie für Einrichtungspotenziale nutzen; ohne Eingang bleibt die bisherige Geometrie maßgeblich. Der Eingangsdatenabruf und die Bildlinks erfolgen unabhängig vom Flag. |

Additive Prüffelder, Popups und zusätzliche `*_map.geojson`-Ansichten bleiben erhalten. Die vollständigen bisher genutzten Layer bleiben davon getrennt. Der Ausschluss unbestätigter Behinderteneinrichtungen aus der Indikatoransicht ist keine Änderung des alten vollständigen Quellen-Layers. Fehlerhafte/unvollständige Overpass-Antworten werden unabhängig von den Flags abgewiesen; Datenfehler sind kein freischaltbarer Fachregelmodus.

## Historischer Live-Schema-Abgleich

Der folgende frühere Abgleich dokumentiert nur die damalige Live-Schnittstelle und die **erweiterte** Berechnung, nicht die Ergebnisgleichheit mit aktuellem `main`:

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

Der [Prüfschritt](../DataOutput/verify_munich_export.py) läuft im Münchner Wochenworkflow **vor dem Upload**. Alle acht Dateien bestehen die Prüfung: Sie sind GeoJSON-FeatureCollections mit denselben Dateinamen; alle bisherigen Feldnamen kommen weiterhin vor; bisher durchgängig vorhandene Felder fehlen bei keinem Feature; ihre Werttypen bleiben erhalten. Die Geometrietypen entsprechen dem jeweils veröffentlichten Layer, und `feature_type` sowie die `maxspeed_class`-Legendenwerte bleiben im bisherigen Wertebereich. Neue Felder und neue Dateien sind zugelassen. Die Geschwindigkeitsübersicht enthält wieder den breiten OSM-Straßenkontext; nur öffentlich befahrbare Straßen gehen in die Potenzialrechnung ein. Der alte `potential_streets.geojson`-Layer enthält weiterhin auch bedingte Lücken. Die neue Berliner Ansicht `potential_streets_map.geojson` trennt diese aus und ergänzt Anschluss-Kontext. Vollständige Einrichtungs-Layer und `*_map.geojson`-Indikatoransichten werden separat exportiert.

**Die Feature-Menge dieses historischen Vergleichs ist nicht identisch und nicht rein additiv.** Von 734 live veröffentlichten Potenzial-OSM-IDs enthält der erweiterte Export 357; 377 bisherige IDs fehlen und 252 kommen hinzu. Im Geschwindigkeits-Layer sind dagegen 61.136 von 61.140 bisherigen OSM-IDs weiterhin vorhanden. Die genauen ID-Differenzen stehen lokal in `reference-potentials/munich-remote-2026-10-25/osm_id_comparison.json`. Auch die Spielplatz- und Überwegzahlen ändern sich stark. Dieser Vergleich konnte Abfragezeitpunkt und Regeln nicht trennen; dafür ist der oben beschriebene frische `main`-Vergleich erforderlich.

Die SHA-256-Werte im historischen Vertrag bezeichnen genau die damals heruntergeladenen Remote-Dateien, nicht den neuen `main`-Referenzlauf.
