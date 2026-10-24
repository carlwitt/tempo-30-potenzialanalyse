"""Expose the exact OSM street ways matched to facility potential candidates."""

from collections import defaultdict

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString


class FacilityStreetSegments:
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
                street_url = f"https://www.openstreetmap.org/way/{street_id}"
                nearby = street.geometry.intersection(facility.geometry.buffer(20))
                parts = list(nearby.geoms) if isinstance(nearby, MultiLineString) else [nearby]
                for part in parts:
                    if not isinstance(part, LineString) or part.is_empty or part.length == 0:
                        continue
                    records.append({
                        "facility_layer": layer,
                        "facility_id": facility_id,
                        "facility_name": facility_name,
                        "facility_osm_url": facility["osm_url"],
                        "street_osm_id": street_id,
                        "street_name": name,
                        "current_speed_kmh": int(speed),
                        "distance_m": distance,
                        "street_osm_url": street_url,
                        "description": (
                            f"Tempo-30-Prüfabschnitt (innerhalb 20 m der Einrichtung)\n"
                            f"Straße: {name}\nAktuell laut OSM: {speed} km/h\n"
                            f"Anlass: {facility_name}\nAbstand zur Einrichtung: {distance:.1f} m\n"
                            f"[[{street_url}|Vollständigen OSM-Abschnitt prüfen]]\n"
                            f"[[{facility['osm_url']}|Einrichtung prüfen]]"
                        ),
                        "geometry": part,
                    })

        columns = [
            "facility_layer", "facility_id", "facility_name", "facility_osm_url",
            "street_osm_id", "street_name", "current_speed_kmh", "distance_m",
            "street_osm_url", "description", "geometry",
        ]
        result = gpd.GeoDataFrame(records, columns=columns, geometry="geometry", crs="EPSG:25832")
        return result.to_crs(streets.crs)

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
        for _, segment in segments.iterrows():
            facilities = matched[segment["street_osm_id"]]
            if not any(
                facility["facility_layer"] == segment["facility_layer"]
                and facility["facility_id"] == segment["facility_id"]
                for facility in facilities
            ):
                facilities.append(segment)

        descriptions = []
        for _, street in result.iterrows():
            name = street["name"] if pd.notna(street["name"]) else "Straße ohne OSM-Namen"
            street_url = f"https://www.openstreetmap.org/way/{street['osm_id']}"
            lines = [f"Straße: [[{street_url}|{name}]]",
                     f"Höchstgeschwindigkeit: {street['maxspeed_class']} km/h"]
            source_ids = street.get("source_osm_ids") or [street["osm_id"]]
            facilities = list({(facility["facility_layer"], facility["facility_id"]): facility
                               for source_id in source_ids
                               for facility in matched.get(source_id, [])}.values())
            if facilities:
                lines.append("Nahe Einrichtungen:")
                for facility in facilities:
                    lines.append(
                        f"[[{facility['facility_osm_url']}|{facility['facility_name']}]] "
                        f"({facility['distance_m']:.1f} m)"
                    )
            descriptions.append("\n\n".join(lines))
        result["description"] = descriptions
        return result
