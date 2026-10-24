"""Find covered street continuations next to facility potential roads."""

import math
from collections import defaultdict

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, substring


class AdjacentCoveredSegments:
    MAX_DISTANCE_M = 500
    ENDPOINT_TOLERANCE_M = 0.5
    COVERED_CLASSES = {"10", "20", "30", "30_Zone"}

    @staticmethod
    def _covered(road) -> bool:
        return road.get("conditional_speed") == "30" or road["maxspeed_class"] in AdjacentCoveredSegments.COVERED_CLASSES

    @staticmethod
    def _status(road) -> str:
        if road.get("conditional_speed") == "30":
            return "Bedingtes Tempo 30"
        if road["maxspeed_class"] == "30_Zone":
            return "Tempo-30-Zone"
        return f"Tempo {road['maxspeed_class']}"

    @staticmethod
    def _condition_detail(road) -> str | None:
        if road.get("conditional_speed") != "30":
            return None
        days = road.get("cond_speed_days")
        start = road.get("cond_speed_starttime")
        end = road.get("cond_speed_endtime")
        special = road.get("cond_speed_special")
        times = f"{start}–{end}" if pd.notna(start) and pd.notna(end) else None
        available = [str(part) for part in (days, times, special) if pd.notna(part) and str(part).strip()]
        return ", ".join(available) if available else None

    @staticmethod
    def _other_end(line: LineString, joint: Point) -> Point | None:
        start, end = Point(line.coords[0]), Point(line.coords[-1])
        if start.distance(joint) <= AdjacentCoveredSegments.ENDPOINT_TOLERANCE_M:
            return end
        if end.distance(joint) <= AdjacentCoveredSegments.ENDPOINT_TOLERANCE_M:
            return start
        return None

    @staticmethod
    def _outward_vector(line: LineString, joint: Point) -> tuple[float, float]:
        coords = list(line.coords)
        if Point(coords[0]).distance(joint) <= AdjacentCoveredSegments.ENDPOINT_TOLERANCE_M:
            a, b = coords[0], coords[1]
        else:
            a, b = coords[-1], coords[-2]
        return b[0] - a[0], b[1] - a[1]

    @staticmethod
    def _deflection(first: LineString, second: LineString, joint: Point) -> float:
        ax, ay = AdjacentCoveredSegments._outward_vector(first, joint)
        bx, by = AdjacentCoveredSegments._outward_vector(second, joint)
        lengths = math.hypot(ax, ay) * math.hypot(bx, by)
        if not lengths:
            return 180.0
        # Opposite outward vectors mean a straight continuation through the joint.
        cosine = max(-1.0, min(1.0, -(ax * bx + ay * by) / lengths))
        return math.degrees(math.acos(cosine))

    @staticmethod
    def _next_road(roads: gpd.GeoDataFrame, current, joint: Point, visited: set[int]):
        candidates = []
        matches = roads.sindex.query(joint.buffer(AdjacentCoveredSegments.ENDPOINT_TOLERANCE_M))
        for index in matches:
            road = roads.iloc[index]
            if road["osm_id"] in visited:
                continue
            other_end = AdjacentCoveredSegments._other_end(road.geometry, joint)
            if other_end is None:
                continue
            angle = AdjacentCoveredSegments._deflection(current.geometry, road.geometry, joint)
            same_name = pd.notna(current["name"]) and pd.notna(road["name"]) \
                and current["name"] == road["name"]
            if angle > (60 if same_name else 25):
                continue
            candidates.append((not same_name, angle, road["osm_id"], road, other_end))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[:3])[3:]

    @staticmethod
    def _slice_from_joint(line: LineString, joint: Point, length: float) -> LineString:
        if Point(line.coords[0]).distance(joint) <= AdjacentCoveredSegments.ENDPOINT_TOLERANCE_M:
            return substring(line, 0, length)
        return substring(line, line.length - length, line.length)

    @staticmethod
    def _trace(roads, source, facility, layer, joint, used, max_distance_m):
        visited = {source["osm_id"]}
        current = source
        while used < max_distance_m:
            continuation = AdjacentCoveredSegments._next_road(roads, current, joint, visited)
            if continuation is None:
                break
            road, other_end = continuation
            visited.add(road["osm_id"])
            if not AdjacentCoveredSegments._covered(road):
                break

            length = min(road.geometry.length, max_distance_m - used)
            if length <= 0:
                break
            section = AdjacentCoveredSegments._slice_from_joint(road.geometry, joint, length)
            yield {
                "facility_layer": layer,
                "facility_id": facility["osm_id"],
                "facility_name": facility["name"] if pd.notna(facility["name"]) else "Einrichtung ohne OSM-Namen",
                "facility_osm_url": facility["osm_url"],
                "source_street_osm_id": source["osm_id"],
                "street_osm_id": road["osm_id"],
                "street_name": road["name"] if pd.notna(road["name"]) else "Straße ohne OSM-Namen",
                "maxspeed_class": road["maxspeed_class"],
                "conditional_speed": road.get("conditional_speed"),
                "conditional_detail": AdjacentCoveredSegments._condition_detail(road),
                "coverage_status": AdjacentCoveredSegments._status(road),
                "distance_start_m": round(used, 1),
                "distance_end_m": round(used + length, 1),
                "street_osm_url": f"https://www.openstreetmap.org/way/{road['osm_id']}",
                "geometry": section,
            }
            if length < road.geometry.length:
                break
            used += length
            current, joint = road, other_end

    @staticmethod
    def create(streets, facilities, potential_results, max_distance_m=MAX_DISTANCE_M):
        """Follow each matched road from its facility-nearest point, up to 500 m."""
        columns = [
            "facility_layer", "facility_id", "facility_name", "facility_osm_url",
            "source_street_osm_id", "street_osm_id", "street_name", "maxspeed_class",
            "conditional_speed", "conditional_detail", "coverage_status",
            "distance_start_m", "distance_end_m",
            "street_osm_url", "description", "geometry",
        ]
        pairs = [
            (layer, facility_id, road_id)
            for layer, result in potential_results.items() if layer in facilities
            for facility_id, road_id in (result.source_street_pairs or [])
        ]
        if not pairs:
            return gpd.GeoDataFrame(columns=columns, geometry="geometry", crs=streets.crs)

        roads = streets.loc[streets.geometry.geom_type == "LineString"].to_crs("EPSG:25832")
        roads = roads.drop_duplicates("osm_id").reset_index(drop=True)
        roads_by_id = roads.set_index("osm_id", drop=False)
        facilities_by_layer = {
            layer: features.to_crs("EPSG:25832").drop_duplicates("osm_id").set_index("osm_id", drop=False)
            for layer, features in facilities.items()
        }
        records = {}
        for layer, facility_id, source_id in pairs:
            if source_id not in roads_by_id.index or facility_id not in facilities_by_layer[layer].index:
                continue
            source = roads_by_id.loc[source_id]
            facility = facilities_by_layer[layer].loc[facility_id]
            anchor = nearest_points(facility.geometry, source.geometry)[1]
            position = source.geometry.project(anchor)
            ends = (
                (Point(source.geometry.coords[0]), position),
                (Point(source.geometry.coords[-1]), source.geometry.length - position),
            )
            for joint, distance in ends:
                for record in AdjacentCoveredSegments._trace(
                    roads, source, facility, layer, joint, distance, max_distance_m
                ):
                    key = layer, facility_id, record["street_osm_id"]
                    previous = records.get(key)
                    if previous is None or record["distance_start_m"] < previous["distance_start_m"]:
                        records[key] = record

        for record in records.values():
            condition = record["conditional_detail"]
            condition_line = f"Bedingung laut OSM: {condition}\n" if condition else ""
            record["description"] = (
                f"Bereits abgedeckter Anschlussabschnitt: {record['street_name']}\n"
                f"OSM-Grundklasse: {record['maxspeed_class']}; {record['coverage_status']}\n"
                f"{condition_line}"
                f"Entfernung entlang der Straße vom Einrichtungsbezugspunkt: "
                f"{record['distance_start_m']:.1f}–{record['distance_end_m']:.1f} m\n"
                f"[[{record['street_osm_url']}|OSM-Straßenway prüfen]]\n"
                f"[[{record['facility_osm_url']}|Einrichtung prüfen]]"
            )
        result = gpd.GeoDataFrame(records.values(), columns=columns, geometry="geometry", crs="EPSG:25832")
        return result.to_crs(streets.crs)

    @staticmethod
    def annotate_facilities(features, segments, layer):
        result = features.copy()
        matched = defaultdict(list)
        for _, segment in segments.loc[segments["facility_layer"] == layer].iterrows():
            matched[segment["facility_id"]].append(segment)
        descriptions = []
        for _, feature in result.iterrows():
            lines = [feature["description"]]
            roads = sorted(matched[feature["osm_id"]], key=lambda road: road["distance_start_m"])
            if roads:
                lines.append("Angrenzend bereits abgedeckt (bis 500 m entlang der Straße):")
                for road in roads:
                    condition = f" ({road['conditional_detail']})" if road["conditional_detail"] else ""
                    lines.append(
                        f"[[{road['street_osm_url']}|{road['street_name']}]] — "
                        f"{road['coverage_status']}{condition}; ab {road['distance_start_m']:.1f} m"
                    )
            descriptions.append("\n".join(line for line in lines if isinstance(line, str)))
        result["description"] = descriptions
        result["covered_street_count"] = [len(matched[feature["osm_id"]]) for _, feature in result.iterrows()]
        return result

    @staticmethod
    def annotate_potential_streets(streets, segments):
        result = streets.copy()
        matched = defaultdict(dict)
        for _, segment in segments.iterrows():
            matched[segment["source_street_osm_id"]][segment["street_osm_id"]] = segment
        descriptions = []
        for _, street in result.iterrows():
            lines = [street["description"]]
            roads = matched[street["osm_id"]].values()
            if roads:
                lines.append("Angrenzend bereits abgedeckt:")
                for road in roads:
                    condition = f" ({road['conditional_detail']})" if road["conditional_detail"] else ""
                    lines.append(
                        f"[[{road['street_osm_url']}|{road['street_name']}]] — "
                        f"{road['coverage_status']}{condition}"
                    )
            descriptions.append("\n".join(line for line in lines if isinstance(line, str)))
        result["description"] = descriptions
        return result
