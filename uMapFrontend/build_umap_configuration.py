"""Create a uMap configuration for a new analysis area from a template.

Configuring remote GeoJSON layers, styles, popup fields and descriptions by
hand for each area is repetitive. Given a prepared uMap template and the
area's export URL, build an importable map whose layers reference those
exports. For example, a Potsdam map can reuse the street and facility
styling while pointing to Potsdam's GeoJSON files.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import yaml


with Path(__file__).with_name("layer_descriptions.yaml").open(encoding="utf-8") as source:
    LAYER_DESCRIPTIONS = yaml.safe_load(source)


FACILITY_POPUP = "{popup_content}"
FACILITY_STREET_COLOR = "#d7191c"
CROSSING_STREET_COLOR = "#f28e2b"
GAP_STREET_COLOR = "#8e44ad"
EXISTING_CONNECTION_COLOR = "#1a9850"
# Four categories from Tableau 10; gray is reserved for inactive indicators.
# https://d3js.org/d3-scale-chromatic/categorical#schemeTableau10
INDICATOR_COLORS = {
    "children": "#76b7b2", "education": "#4e79a7",
    "care": "#af7aa1", "crossing": "#f28e2c",
}
INACTIVE_COLOR = "#9e9e9e"


def fields(*items):
    return [{"key": key, "type": kind} for key, kind in items]


def remote_layer(filename, name, *, color, on_load=False, extra=None, rank=0):
    """Define a styled layer that loads GeoJSON from a URL at map runtime."""
    properties = {
        "name": name,
        "type": "Default",
        "color": color,
        "browsable": True,
        "inCaption": True,
        "displayOnLoad": on_load,
        "remoteData": {
            "ttl": "300",
            "url": f"{filename}.geojson",
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
    """Show each indicator's category in color and its inactive state in gray.

    Rebuild the six layers together so template colors and obsolete review
    rules cannot override the legend. Only the zebra pictogram is inherited.
    The optional layers include both states; streets remain the initial view.
    """
    zebra = next(layer["properties"] for layer in indicators["layers"]
                 if layer["properties"]["name"] == "Zebrastreifen")
    common_fields = fields(
        ("osm_id", "Number"), ("name", "String"), ("facility_type", "String"),
        ("potential_candidate", "Boolean"), ("matched_street_count", "Number"),
        ("covered_street_count", "Number"), ("description", "Text"), ("popup_content", "Text"),
    )
    layers = []
    for name, filename, category in (
        ("Spielplätze", "playgrounds_map", "children"),
        ("Zebrastreifen", "zebra", "crossing"),
        ("Einrichtungen für Menschen mit Behinderung", "disability_facilities_map", "care"),
        ("Krankenhäuser", "hospitals_map", "care"),
        ("Schulen und Kitas", "educational_buildings_map", "education"),
        ("Senioren- und Pflegeeinrichtungen", "elderly_homes_map", "care"),
    ):
        rules = [
            {"name": f"{name} ohne Auswirkungen auf die aktuelle Geschwindigkeitsbeschränkung",
             "condition": "potential_candidate=false",
             "properties": {"color": INACTIVE_COLOR, "opacity": 0.45,
                            "fillOpacity": 0.15, "iconOpacity": 0.5}},
            {"name": f"{name} mit möglichem Einfluss auf eine Tempo-30-Anordnung",
             "condition": "potential_candidate=true",
             "properties": {"color": INDICATOR_COLORS[category], "opacity": 0.85,
                            "fillOpacity": 0.35, "iconOpacity": 0.9}},
        ]
        if category == "education":
            # uMap uses the first matching rule per property: inactive Kitas
            # stay gray; active Kitas share the playground color.
            rules.insert(1, {"name": "Kitas", "condition": "facility_type=Kindergarten",
                             "properties": {"color": INDICATOR_COLORS["children"]}})
        style = {
            "fill": True, "stroke": False, "fillOpacity": 0.15, "iconOpacity": 0.5,
            "iconClass": "Circle", "circles": {"radius": {"min": 8}},
            "rules": rules, "fields": common_fields,
            "popupContentTemplate": FACILITY_POPUP,
            "description": LAYER_DESCRIPTIONS[name],
        }
        if category == "crossing":
            style.update({"fill": False, "stroke": True, "weight": 4,
                          "popupContentTemplate": "{description}",
                          "fields": fields(("display_role", "String"), ("potential_candidate", "Boolean"),
                                           ("potential_reason", "String"), ("description", "Text"))})
            style.pop("iconClass")
            style.update({key: zebra[key] for key in ("iconUrl", "iconClass") if key in zebra})
        elif filename == "disability_facilities_map":
            style["fields"] = [*common_fields, *fields(("facility_status", "String"))]
        layers.append(remote_layer(filename, name, color=INACTIVE_COLOR, extra=style, rank=len(layers)))
    indicators["layers"] = layers
    indicators["properties"]["displayOnLoad"] = False
    indicators["properties"]["description"] = LAYER_DESCRIPTIONS["Tempo 30 Indikatoren"]


def street_layers():
    potential = remote_layer(
        "potential_streets_map", "Straßenabschnitte mit Tempo-30-Potenzial",
        color=FACILITY_STREET_COLOR, on_load=True,
        extra={
            "weight": 5, "opacity": 0.85, "popupShape": "Large",
            # The map and GeoJSON are published separately. Older remote exports
            # lack map_potential_type, so retain rules for their existing fields.
            # The precise category rules come last for current multifactor ways.
            "rules": [
                {"name": "Zebrastreifen-Potenzial (älterer Export)",
                 "condition": "feature_type=Potenzial durch Zebrastreifen",
                 "properties": {"color": CROSSING_STREET_COLOR}},
                {"name": "Lückenschluss-Potenzial (älterer Export)",
                 "condition": "feature_type=Potenzial durch Lückenschluss",
                 "properties": {"color": GAP_STREET_COLOR}},
                {"name": "Bedingter Lückenschluss (älterer Export)",
                 "condition": "is_conditional_gap=true",
                 "properties": {"color": GAP_STREET_COLOR}},
                {"name": "Durchlaufener Lückenschlussabschnitt (älterer Export)",
                 "condition": "gap_role=corridor_connection",
                 "properties": {"color": GAP_STREET_COLOR}},
                {"name": "Bestehender Tempo-30-Anschluss (älterer Export)",
                 "condition": "gap_role=existing_connection",
                 "properties": {"color": EXISTING_CONNECTION_COLOR, "dashArray": "", "weight": 6}},
                {"name": "Zebrastreifen-Potenzial", "condition": "map_potential_type=crossing",
                 "properties": {"color": CROSSING_STREET_COLOR}},
                {"name": "Lückenschluss-Potenzial", "condition": "map_potential_type=gap",
                 "properties": {"color": GAP_STREET_COLOR}},
                {"name": "Bestehender Tempo-30-Anschluss", "condition": "map_potential_type=existing_connection",
                 "properties": {"color": EXISTING_CONNECTION_COLOR, "dashArray": "", "weight": 6}},
            ],
            "fields": fields(("osm_id", "Number"), ("name", "String"),
                             ("maxspeed_class", "String"), ("feature_type", "String"),
                             ("map_potential_type", "String"),
                             ("is_conditional_gap", "Boolean"),
                             ("logical_segment_length_m", "Number"),
                             ("logical_segment_way_count", "Number"),
                             ("gap_length_current_m", "Number"),
                             ("gap_length_with_prerequisites_m", "Number"),
                             ("gap_length_after_m", "Number"),
                             ("gap_required_potential_types", "String"),
                             ("gap_existing_street_osm_ids", "String"),
                             ("gap_role", "String"), ("description", "Text")),
            "description": LAYER_DESCRIPTIONS["Straßenabschnitte mit Tempo-30-Potenzial"],
        },
    )
    conditional = remote_layer(
        "conditional_gap_streets", "Bedingte Lückenschlüsse", color=GAP_STREET_COLOR,
        extra={
            "weight": 5, "opacity": 0.85, "dashArray": "6,6", "popupShape": "Large",
            "fields": potential["properties"]["fields"] + fields(
                ("target_speed_kmh", "Number"),
                ("existing_speed_conditional", "Boolean"),
                ("gap_corridor_street_osm_ids", "String")),
            "labelKey": "name",
            "rules": [{"name": "Bestehender Tempo-30-Anschluss",
                       "condition": "gap_role=existing_connection",
                       "properties": {"color": EXISTING_CONNECTION_COLOR, "dashArray": "", "weight": 6}},
                      {"name": "Lückenschlusspotenzial",
                       "condition": "gap_role=corridor_connection",
                       "properties": {"color": GAP_STREET_COLOR, "dashArray": "5,5", "weight": 4}}],
            "description": LAYER_DESCRIPTIONS["Bedingte Lückenschlüsse"],
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
            "description": LAYER_DESCRIPTIONS["Bereits abgedeckte Anschlussabschnitte"],
        },
    )
    return group("Straßenabschnitte", [potential, conditional, covered], rank=1)


def accident_layer(area_name, accident_start_year, accident_end_year):
    layer = remote_layer(
        "accidents", f"Unfälle mit Personenschaden {accident_start_year}–{accident_end_year}", color="#d7301f",
        extra={
            "type": "Heat", "browsable": False,
            "heat": {"radius": 20, "intensityProperty": "heat_weight"},
            "fields": fields(("accident_id", "String"), ("UJAHR", "Number"),
                             ("UMONAT", "Number"), ("UKATEGORIE", "Number"),
                             ("heat_weight", "Number"), ("description", "Text")),
            "description": LAYER_DESCRIPTIONS["Unfälle mit Personenschaden"].format(
                area_name=area_name, accident_start_year=accident_start_year,
            ),
        },
        rank=3,
    )
    return layer


def complete_districts(layer):
    props = layer["properties"]
    props["displayOnLoad"] = False
    keys = [field["key"] for field in props["fields"] if field["key"] != "analysis_scope"]
    for key in ("gap_direct_potential", "gap_conditional_potential"):
        if key not in keys:
            keys.append(key)
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
    props["description"] = LAYER_DESCRIPTIONS["Bezirksstatistiken"]
    for line in ("Direkte Lückenschlüsse: {gap_direct_potential}",
                 "Bedingte Lückenschlüsse: {gap_conditional_potential}"):
        if line not in props["popupContentTemplate"]:
            props["popupContentTemplate"] += "\n" + line
    layer["rank"] = 2


def build(*, backup: Path, output: Path, remote_base: str, area_name: str,
          map_name: str, accident_start_year: int, accident_end_year: int):
    """Fill the template's layer structure and remote URLs for one area.

    The template supplies the map view and base settings; exported GeoJSON
    must already be available under ``remote_base``. This writes only the
    uMap configuration, not the source data.
    """
    if accident_start_year > accident_end_year:
        raise ValueError("Accident start year must not exceed end year")
    if urlsplit(remote_base).scheme not in {"http", "https"} or not urlsplit(remote_base).netloc:
        raise ValueError("Remote base must be an absolute HTTP(S) URL")
    if backup.resolve() == output.resolve():
        raise ValueError("Output must not overwrite the backup")
    with backup.open(encoding="utf-8") as source:
        result = json.load(source)

    by_name = {layer["properties"]["name"]: layer for layer in result["layers"]}
    indicators = by_name["Tempo 30 Indikatoren"]
    districts = by_name["Bezirksstatistiken"]
    complete_indicators(indicators)
    complete_districts(districts)
    result["layers"] = [
        indicators, street_layers(), districts,
        accident_layer(area_name, accident_start_year, accident_end_year),
    ]
    for group_layer in result["layers"]:
        for layer in group_layer.get("layers", [group_layer]):
            remote = layer["properties"].get("remoteData")
            if remote and remote.get("url"):
                filename = Path(urlsplit(remote["url"]).path).name
                remote["url"] = f"{remote_base.rstrip('/')}/{filename}"
    result["properties"]["name"] = map_name
    result["properties"]["longCredit"] = (
        "Daten: [[https://www.openstreetmap.org/copyright|OpenStreetMap-Mitwirkende]] (ODbL). "
        "Unfälle: [[https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/|Unfallatlas]] "
        "([[https://www.govdata.de/dl-de/by-2-0|DL-DE/BY-2.0]]). "
        "Analyse und Methodik: [[https://github.com/MunichWays/tempo-30-potenzialanalyse|Tempo-30-Potenzialanalyse]]."
    )

    with output.open("w", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-base", required=True)
    parser.add_argument("--area-name", required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--accident-start-year", type=int, required=True)
    parser.add_argument("--accident-end-year", type=int, required=True)
    args = parser.parse_args()
    try:
        build(**vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(f"Written {args.output}")


if __name__ == "__main__":
    main()
