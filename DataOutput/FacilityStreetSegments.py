"""Map the street pieces supported by each facility candidate.

A long OSM way can pass a Kita but extend far beyond it. Clip each matched
50/60 km/h way to the facility's search area and retain its OSM identity.
This shows the relevant part of the proposal and lets reviewers inspect
the source way without mistaking its full length for potential.
"""

from collections import defaultdict

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString

from DataOutput.PotentialStreetConsolidation import PotentialStreetConsolidation
from DataOutput.SpeedLimitDescription import SpeedLimitDescription
from DataRetrieval.AdditionalFeatures import facility_url
from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance


class FacilityStreetSegments:
    MIN_ISOLATED_CLIP_M = 10.0

    @staticmethod
    def create(streets, facilities, potential_results):
        pairs_by_layer = {
            layer: result.source_street_pairs or []
            for layer, result in potential_results.items() if layer in facilities
        }
        street_ids = {street_id for pairs in pairs_by_layer.values() for _, street_id in pairs}
        metric_streets = streets.loc[streets["osm_id"].isin(street_ids)].to_crs("EPSG:25832")
        street_by_id = metric_streets.drop_duplicates("osm_id").set_index("osm_id")
        records = []

        for layer, pairs in pairs_by_layer.items():
            metric_facilities = facilities[layer].to_crs("EPSG:25832")
            facility_by_id = metric_facilities.drop_duplicates("osm_id").set_index("osm_id")
            for facility_id, street_id in pairs:
                if facility_id not in facility_by_id.index or street_id not in street_by_id.index:
                    continue
                facility = facility_by_id.loc[facility_id]
                street = street_by_id.loc[street_id]
                name = street["name"] if pd.notna(street["name"]) else "Straße ohne OSM-Namen"
                facility_name = facility["name"] if pd.notna(facility["name"]) else "Einrichtung ohne OSM-Namen"
                speed = street["maxspeed_class"]
                distance = round(facility.geometry.distance(street.geometry), 1)
                entrance_reference = facility.get("street_reference") == "OSM-Haupteingang"
                street_url = f"https://www.openstreetmap.org/way/{street_id}"
                search_distance = FacilityStreetRelevance.search_distance(facility, street, 20)
                nearby = street.geometry.intersection(facility.geometry.buffer(search_distance))
                parts = list(nearby.geoms) if isinstance(nearby, MultiLineString) else [nearby]
                for part in parts:
                    if not isinstance(part, LineString) or part.is_empty or part.length == 0:
                        continue
                    records.append({
                        "facility_layer": layer,
                        "facility_id": facility_id,
                        "facility_name": facility_name,
                        "facility_osm_url": facility_url(facility),
                        "street_osm_id": street_id,
                        "street_name": name,
                        "current_speed_kmh": int(speed),
                        "distance_m": distance,
                        "distance_reference": "OSM-Haupteingang" if entrance_reference else None,
                        "main_entrance_osm_ids": facility.get("main_entrance_osm_ids", []),
                        "street_osm_url": street_url,
                        "description": (
                            f"Tempo-30-Prüfabschnitt (innerhalb {search_distance:g} m der Einrichtung)\n"
                            f"Straße: {name}\nAktuell laut OSM: {speed} km/h\n"
                            f"Anlass: {facility_name}\n"
                            f"Abstand {'zum OSM-Haupteingang' if entrance_reference else 'zur Einrichtung'}: "
                            f"{distance:.1f} m\n"
                            f"[[{street_url}|Vollständigen OSM-Abschnitt prüfen]]\n"
                            f"[[{facility_url(facility)}|Einrichtung prüfen]]"
                        ),
                        "geometry": part,
                    })

        columns = [
            "facility_layer", "facility_id", "facility_name", "facility_osm_url",
            "street_osm_id", "street_name", "current_speed_kmh", "distance_m",
            "distance_reference", "main_entrance_osm_ids", "street_osm_url", "description", "geometry",
        ]
        result = gpd.GeoDataFrame(records, columns=columns, geometry="geometry", crs="EPSG:25832")
        return result.to_crs(streets.crs)

    @staticmethod
    def filter_short_isolated(segments, retained_street_ids):
        """Hide tiny facility clips unless they join a useful nearby section."""
        # Keep the facility overlay aligned with the consolidated potential streets.
        visible = segments.loc[segments["street_osm_id"].isin(retained_street_ids)].copy()
        if visible.empty:
            return visible

        metric = visible.to_crs("EPSG:25832").reset_index(drop=True)
        keys = []
        for _, segment in metric.iterrows():
            name = segment["street_name"]
            street_key = name if name != "Straße ohne OSM-Namen" else segment["street_osm_id"]
            keys.append((segment["facility_layer"], segment["facility_id"], street_key))

        retained = []
        # Measure connected clips together so a short connector is not lost.
        for members in PotentialStreetConsolidation.connected_members(metric, keys):
            if metric.geometry.iloc[members].length.sum() > FacilityStreetSegments.MIN_ISOLATED_CLIP_M:
                retained.extend(members)
        return visible.iloc[sorted(retained)].copy()

    @staticmethod
    def annotate_facilities(features, segments, layer):
        result = features.copy()
        matched = defaultdict(list)
        for _, segment in segments.loc[segments["facility_layer"] == layer].iterrows():
            roads = matched[segment["facility_id"]]
            if not any(road["street_osm_id"] == segment["street_osm_id"] for road in roads):
                roads.append(segment)

        descriptions = []
        for _, feature in result.iterrows():
            lines = [feature["description"]]
            roads = matched.get(feature["osm_id"], [])
            if roads:
                lines.append("Tempo-30-Prüfabschnitte:")
                for road in roads:
                    lines.append(
                        f"[[{road['street_osm_url']}|{road['street_name']}]] — "
                        f"aktuell {road['current_speed_kmh']} km/h; Abstand {road['distance_m']:.1f} m"
                    )
            descriptions.append("\n".join(line for line in lines if isinstance(line, str)))
        result["description"] = descriptions
        result["matched_street_count"] = [len(matched.get(feature["osm_id"], [])) for _, feature in result.iterrows()]
        return result

    @staticmethod
    def annotate_potential_streets(streets, segments):
        result = streets.copy()
        matched = defaultdict(list)
        metric_streets = result.to_crs("EPSG:25832")
        metric_segments = segments.to_crs("EPSG:25832")
        for _, segment in metric_segments.iterrows():
            facilities = matched[segment["street_osm_id"]]
            if not any(
                facility["facility_layer"] == segment["facility_layer"]
                and facility["facility_id"] == segment["facility_id"]
                for facility in facilities
            ):
                facilities.append(segment)

        descriptions = []
        for position, (_, street) in enumerate(result.iterrows()):
            name = street["name"] if pd.notna(street["name"]) else "Straße ohne OSM-Namen"
            street_url = f"https://www.openstreetmap.org/way/{street['osm_id']}"
            lines = [f"Straße: [[{street_url}|{name}]]",
                     SpeedLimitDescription.describe(street)]
            source_ids = street.get("source_osm_ids") or [street["osm_id"]]
            visible_geometry = metric_streets.geometry.iloc[position]
            local_facilities = {}
            for source_id in source_ids:
                for facility in matched.get(source_id, []):
                    # A long OSM way may have several separate visible clips.
                    if visible_geometry.distance(facility.geometry) <= 1:
                        key = (facility["facility_layer"], facility["facility_id"])
                        local_facilities[key] = facility
            facilities = local_facilities.values()
            if facilities:
                lines.append("Nahe Einrichtungen:")
                for facility in facilities:
                    facility_label = (
                        f"{facility['facility_name']} ([[{facility['facility_osm_url']}|amtliche Quelle]])"
                        if isinstance(facility["facility_id"], str)
                        else f"[[{facility['facility_osm_url']}|{facility['facility_name']}]]"
                    )
                    lines.append(
                        f"{facility_label} "
                        f"({facility['distance_m']:.1f} m"
                        + (" zum OSM-Haupteingang" if facility.get("distance_reference") == "OSM-Haupteingang" else "")
                        + ")"
                    )
                    for node_id in facility.get("main_entrance_osm_ids") or []:
                        lines.append(
                            f"Zugang prüfen: [[https://www.openstreetmap.org/node/{node_id}|"
                            f"OSM-Haupteingang {node_id}]]"
                        )
            descriptions.append("\n\n".join(lines))
        result["description"] = descriptions
        return result
