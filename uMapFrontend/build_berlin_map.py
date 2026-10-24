"""Complete the Berlin uMap backup with the current remote GeoJSON layers."""

import copy
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BACKUP = HERE / "umap_backup_tempo-30-potenziale-berlin.umap"
OUTPUT = HERE / "tempo-30-potenziale-berlin.umap"
REMOTE_BASE = "https://tempo-30.adfc-berlin.de/uMap"
FACILITY_POPUP = "{popup_content}"

FACILITY_CAVEAT = (
    " Nach der VwV-StVO setzt dies einen direkten Straßenzugang oder starken Ziel- und "
    "Quellverkehr im Nahbereich voraus; die Anordnung ist auf den unmittelbaren Bereich "
    "und insgesamt höchstens 300 m zu begrenzen."
)

INDICATOR_DESCRIPTIONS = {
    "Spielplätze": (
        "Spielplätze gelten seit der StVO-Novelle als neu aufgenommene privilegierte Orte "
        "zum besonderen Schutz von Kindern. Gemäß § 45 Abs. 9 Satz 4 Nr. 6 StVO kann "
        "im unmittelbaren Bereich erleichtert Tempo 30 angeordnet werden, ohne dass eine "
        "qualifizierte Gefahrenlage nachgewiesen werden muss."
        + FACILITY_CAVEAT
    ),
    "Zebrastreifen": (
        "Im unmittelbaren Bereich von Fußgängerüberwegen kann gemäß § 45 Abs. 9 Satz 4 "
        "Nr. 6 StVO erleichtert eine streckenbezogene Beschränkung auf Tempo 30 "
        "angeordnet werden, ohne dass eine qualifizierte Gefahrenlage nachgewiesen werden "
        "muss. Nach der VwV-StVO ist die Anordnung auf insgesamt höchstens 300 m zu begrenzen; "
        "die konkrete Situation ist zu prüfen."
    ),
    "Einrichtungen für Menschen mit Behinderung": (
        "Einrichtungen für Menschen mit Behinderung, etwa Wohnheime, Tagesstätten oder "
        "Werkstätten, sind seit der Reform ausdrücklich als sensible Orte benannt. Gemäß "
        "§ 45 Abs. 9 Satz 4 Nr. 6 StVO kann im unmittelbaren Bereich erleichtert Tempo 30 "
        "angeordnet werden, ohne dass eine qualifizierte Gefahrenlage nachgewiesen werden muss."
        + FACILITY_CAVEAT
    ),
    "Krankenhäuser": (
        "Krankenhäuser sind als sensible Gesundheitseinrichtungen im Ausnahmenkatalog "
        "genannt. Gemäß § 45 Abs. 9 Satz 4 Nr. 6 StVO kann im unmittelbaren Bereich "
        "erleichtert Tempo 30 angeordnet werden, ohne dass eine qualifizierte Gefahrenlage "
        "nachgewiesen werden muss."
        + FACILITY_CAVEAT
    ),
}


def fields(*items):
    return [{"key": key, "type": kind} for key, kind in items]


def remote_layer(filename, name, *, color, on_load=False, extra=None, rank=0):
    properties = {
        "name": name,
        "type": "Default",
        "color": color,
        "browsable": True,
        "inCaption": True,
        "displayOnLoad": on_load,
        "remoteData": {
            "ttl": "300",
            "url": f"{REMOTE_BASE}/{filename}.geojson",
            "proxy": True,
            "format": "geojson",
            "dynamic": False,
        },
        "popupContentTemplate": "{description}",
    }
    properties.update(extra or {})
    return {"type": "FeatureCollection", "features": [], "properties": properties, "rank": rank}


def group(name, layers, rank):
    for index, layer in enumerate(layers):
        layer["rank"] = index
    return {
        "type": "FeatureCollection",
        "features": [],
        "layers": layers,
        "properties": {
            "name": name,
            "group": True,
            "browsable": True,
            "inCaption": True,
            "displayOnLoad": True,
        },
        "rank": rank,
    }


def complete_indicators(indicators):
    layers = indicators["layers"]
    current_fields = {
        "Spielplätze": fields(("osm_id", "Number"), ("name", "String"),
                              ("facility_type", "String"), ("potential_candidate", "Boolean"),
                              ("matched_street_count", "Number"), ("covered_street_count", "Number"),
                              ("description", "Text"), ("popup_content", "Text")),
        "Zebrastreifen": fields(("display_role", "String"), ("potential_candidate", "Boolean"),
                               ("potential_reason", "String"), ("description", "Text")),
        "Einrichtungen für Menschen mit Behinderung": fields(
            ("osm_id", "Number"), ("name", "String"), ("facility_type", "String"),
            ("facility_status", "String"), ("potential_candidate", "Boolean"),
            ("matched_street_count", "Number"), ("covered_street_count", "Number"),
            ("description", "Text"), ("popup_content", "Text")),
        "Krankenhäuser": fields(("osm_id", "Number"), ("name", "String"),
                               ("facility_type", "String"), ("potential_candidate", "Boolean"),
                               ("matched_street_count", "Number"), ("covered_street_count", "Number"),
                               ("description", "Text"), ("popup_content", "Text")),
    }

    # Preserve the backup's zebra stripe marker while keeping crossing
    # segments visible and matching field types to the GeoJSON booleans.
    for layer in layers:
        props = layer["properties"]
        props["fields"] = current_fields[props["name"]]
        props["description"] = INDICATOR_DESCRIPTIONS[props["name"]]
        if props["name"] != "Zebrastreifen":
            props["popupContentTemplate"] = FACILITY_POPUP
        else:
            props["popupContentTemplate"] = "{description}"
            props.update({"stroke": True, "weight": 4})

    education = remote_layer(
        "educational_buildings", "Schulen und Kitas", color="#3b82f6", on_load=True,
        extra={
            "fill": True, "stroke": False, "fillOpacity": 0.16,
            "iconClass": "Circle", "circles": {"radius": {"min": 8}},
            "rules": [{"name": "Bildungseinrichtung mit Potenzial", "condition": "potential_candidate=true",
                       "properties": {"color": "#d7191c", "fillOpacity": 0.7}}],
            "fields": fields(("name", "String"), ("facility_type", "String"),
                             ("potential_candidate", "Boolean"), ("matched_street_count", "Number"),
                             ("covered_street_count", "Number"), ("description", "Text"),
                             ("popup_content", "Text")),
            "popupContentTemplate": FACILITY_POPUP,
            "description": (
                "Bildungseinrichtungen umfassen hier OSM-Schulen und Kitas. Gemäß § 45 Abs. 9 "
                "Satz 4 Nr. 6 StVO kann im unmittelbaren Bereich allgemeinbildender Schulen, "
                "Förderschulen und Kindertagesstätten erleichtert Tempo 30 angeordnet werden, "
                "ohne dass eine qualifizierte Gefahrenlage nachgewiesen werden muss."
                + FACILITY_CAVEAT
                + " Hochfrequentierte Schulwege sind ebenfalls gesetzlich genannt, werden "
                  "aber in diesem Einrichtungs-Layer nicht erfasst."
            ),
        },
    )
    elderly = remote_layer(
        "elderly_homes", "Senioren- und Pflegeeinrichtungen", color="#7c6bb0", on_load=True,
        extra={
            "fill": True, "stroke": False, "fillOpacity": 0.16,
            "iconClass": "Circle", "circles": {"radius": {"min": 8}},
            "rules": [{"name": "Senioreneinrichtung mit Potenzial", "condition": "potential_candidate=true",
                       "properties": {"color": "#d7191c", "fillOpacity": 0.7}}],
            "fields": fields(("name", "String"), ("facility_type", "String"),
                             ("potential_candidate", "Boolean"), ("matched_street_count", "Number"),
                             ("covered_street_count", "Number"), ("description", "Text"),
                             ("popup_content", "Text")),
            "popupContentTemplate": FACILITY_POPUP,
            "description": (
                "Alten- und Pflegeheime zählen als sensible soziale Einrichtungen zum Schutz "
                "vulnerabler und mobilitätseingeschränkter Menschen. Gemäß § 45 Abs. 9 Satz 4 "
                "Nr. 6 StVO in Verbindung mit der VwV-StVO ist im unmittelbaren Bereich in der "
                "Regel Tempo 30 vorgesehen, ohne Nachweis einer qualifizierten Gefahrenlage."
                + FACILITY_CAVEAT
                + " Die OSM-Kennzeichnung einer einzelnen Einrichtung ist vor Ort zu prüfen."
            ),
        },
    )
    layers.extend([education, elderly])
    for index, layer in enumerate(layers):
        layer["rank"] = index
    indicators["properties"]["description"] = "Sensible Einrichtungen und Zebrastreifen mit Tempo-30-Prüfhinweisen."


def street_layers():
    potential = remote_layer(
        "potential_streets", "Straßenabschnitte mit Tempo-30-Potenzial", color="#d7191c", on_load=True,
        extra={
            "weight": 5, "opacity": 0.85,
            "rules": [{"name": "Bedingter Lückenschluss", "condition": "is_conditional_gap=true",
                       "properties": {"color": "#8e44ad", "dashArray": "6,6"}}],
            "fields": fields(("osm_id", "Number"), ("name", "String"),
                             ("maxspeed_class", "String"), ("feature_type", "String"),
                             ("is_conditional_gap", "Boolean"),
                             ("logical_segment_length_m", "Number"),
                             ("logical_segment_way_count", "Number"),
                             ("gap_length_current_m", "Number"),
                             ("gap_length_after_m", "Number"),
                             ("gap_required_potential_types", "String"), ("description", "Text")),
            "description": "Straßenabschnitte mit offenem Tempo-30-Potenzial; violett gestrichelt markiert bedingte Lückenschlüsse. Benachbarte Abschnitte mit denselben Voraussetzungen sind zusammengefasst; isolierte kurze Abschnitte werden ausgeblendet.",
        },
    )
    proposed = remote_layer(
        "facility_street_segments", "Prüfabschnitte an Einrichtungen", color="#e6550d",
        extra={
            "weight": 6, "opacity": 0.9,
            "fields": fields(("facility_name", "String"), ("street_name", "String"),
                             ("current_speed_kmh", "Number"), ("distance_m", "Number"),
                             ("facility_osm_url", "String"), ("street_osm_url", "String"),
                             ("description", "Text")),
            "description": "Konkrete Teile der Tempo-50/60-Ways innerhalb von 20 m einer Einrichtung; keine festgelegten Anordnungsgrenzen.",
        },
    )
    covered = remote_layer(
        "facility_covered_street_segments", "Bereits abgedeckte Anschlussabschnitte", color="#1a9850",
        extra={
            "weight": 5, "opacity": 0.8,
            "rules": [{"name": "Bedingtes Tempo 30", "condition": "conditional_speed=30",
                       "properties": {"color": "#4575b4", "dashArray": "5,5"}}],
            "fields": fields(("facility_name", "String"), ("street_name", "String"),
                             ("coverage_status", "String"), ("conditional_detail", "String"),
                             ("distance_start_m", "Number"), ("distance_end_m", "Number"),
                             ("description", "Text")),
            "description": "Bereits langsame Straßenfortsetzungen bis 500 m entlang der Straße; bedingtes Tempo 30 ist blau gestrichelt.",
        },
    )
    return group("Straßenabschnitte", [potential, proposed, covered], rank=1)


def context_layers():
    review = remote_layer(
        "disability_facilities_review", "Behinderteneinrichtungen – ungeklärt", color="#999999",
        extra={
            "fill": True, "stroke": False, "fillOpacity": 0.18,
            "iconClass": "Circle", "circles": {"radius": {"min": 7}},
            "fields": fields(("name", "String"), ("facility_type", "String"),
                             ("facility_status", "String"), ("potential_candidate", "Boolean"),
                             ("description", "Text"), ("popup_content", "Text")),
            "popupContentTemplate": FACILITY_POPUP,
            "description": "Nicht als bestätigtes Behinderten-Potenzial gewertete OSM-Einrichtungen; Typ und Zielgruppe prüfen.",
        },
    )
    speeds = remote_layer(
        "streets_and_limit", "OSM-Geschwindigkeiten (großer Layer)", color="#999999",
        extra={
            "weight": 2, "opacity": 0.5,
            "rules": [
                {"name": "Tempo 50/60", "condition": "maxspeed_class=T50+",
                 "properties": {"color": "#e34a33", "weight": 3}},
                {"name": "Tempo 30 oder langsamer", "condition": "maxspeed_class=T30-",
                 "properties": {"color": "#31a354"}},
                {"name": "Bedingtes Tempo 30", "condition": "maxspeed_class=Conditional-T30",
                 "properties": {"color": "#3182bd", "dashArray": "5,5"}},
            ],
            "fields": fields(("osm_id", "Number"), ("name", "String"),
                             ("maxspeed_class", "String")),
            "popupContentTemplate": "# {name}\nOSM-Geschwindigkeitsklasse: {maxspeed_class}\n[[https://www.openstreetmap.org/way/{osm_id}|OSM-Straßenabschnitt prüfen]]",
            "description": "OSM-Grundklassen aller Straßenabschnitte. Rund 55 MB; deshalb standardmäßig ausgeschaltet.",
        },
    )
    return group("OSM-Kontext und Prüffälle", [review, speeds], rank=3)


def complete_districts(layer):
    props = layer["properties"]
    keys = [field["key"] for field in props["fields"] if field["key"] != "analysis_scope"]
    keys.extend(["gap_direct_potential", "gap_conditional_potential"])
    props["fields"] = fields(*(
        (key, "String" if key in {"district_id", "district_name"} else "Number") for key in keys
    ))
    props.pop("categorized", None)
    props["choropleth"] = {
        "mode": "kmeans", "brewer": "RdYlGn", "classes": 5,
        "property": "realized_potential_pct_total",
    }
    props["color"] = "#666666"
    props["weight"] = 1
    props["fillOpacity"] = 0.5
    props["description"] = "Anteil geprüfter Objekte ohne offenes Potenzial. Dies ist kein Nachweis einer umgesetzten Tempo-30-Maßnahme."
    props["popupContentTemplate"] += "\nDirekte Lückenschlüsse: {gap_direct_potential}\nBedingte Lückenschlüsse: {gap_conditional_potential}"
    layer["rank"] = 2


def build():
    with BACKUP.open(encoding="utf-8") as source:
        result = copy.deepcopy(json.load(source))

    indicators, districts = result["layers"]
    complete_indicators(indicators)
    complete_districts(districts)
    result["layers"] = [indicators, street_layers(), districts, context_layers()]
    result["properties"]["longCredit"] = (
        "Daten: [[https://www.openstreetmap.org/copyright|OpenStreetMap-Mitwirkende]] (ODbL). "
        "Analyse und Methodik: [[https://github.com/MunichWays/tempo-30-potenzialanalyse|Tempo-30-Potenzialanalyse]]."
    )

    with OUTPUT.open("w", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write("\n")
    return result


if __name__ == "__main__":
    build()
    print(f"Written {OUTPUT}")
