"""Prepare potential streets for readable map display.

One OSM way can stretch well beyond a Kita or crossing. For long nongap
ways, show only the pieces near matched source objects while retaining the
original way ID. When several sources support one segment, choose a single
map color by gap, crossing, then facility priority while retaining every
reason in the feature's data and popup.
"""

from collections import defaultdict

import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import unary_union


class PotentialStreetDisplay:
    MAX_UNCLIPPED_WAY_M = 500
    EVIDENCE_RADIUS_M = 150

    @staticmethod
    def categorize(streets, potential_results):
        """Color a gap over a crossing and a crossing over a facility.

        For example, a way beside a school and a zebra crossing is orange;
        a way that also closes a gap is purple. Existing slow anchors stay
        green. The source reasons remain available in the exported popup.
        """
        gap_result = potential_results.get("gap")
        gap_ids = set(gap_result.street_ids) if gap_result else set()
        if gap_result:
            direct_gap_ids = set(gap_result.direct_gap_lengths_m or {})
            for gap_id, corridor in (gap_result.gap_corridor_ways or {}).items():
                if gap_id in direct_gap_ids:
                    gap_ids.update(corridor)
        crossing_ids = set(potential_results.get("zebra").street_ids) if potential_results.get("zebra") else set()

        def category(street):
            role = street.get("gap_role")
            if role == "existing_connection":
                return "existing_connection"
            if role == "corridor_connection":
                return "gap"
            source_ids = set(street["source_osm_ids"])
            if source_ids & gap_ids or street.get("feature_type") == "Potenzial durch Lückenschluss":
                return "gap"
            if source_ids & crossing_ids or street.get("feature_type") == "Potenzial durch Zebrastreifen":
                return "crossing"
            return "facility"

        result = streets.copy()
        if result.empty:
            result["map_potential_type"] = []
            return result
        result["map_potential_type"] = result.apply(category, axis=1)
        return result

    @staticmethod
    def _line_parts(geometry):
        if isinstance(geometry, LineString):
            return [geometry] if geometry.length > 0 else []
        return [part for item in getattr(geometry, "geoms", ())
                for part in PotentialStreetDisplay._line_parts(item)]

    @staticmethod
    def clip_long_ways(streets, source_layers, potential_results):
        """Show long non-gap ways only within 150 m of their source objects."""
        if streets.empty:
            return streets.copy()

        metric = streets.to_crs("EPSG:25832")
        evidence = defaultdict(list)
        for kind, result in potential_results.items():
            if kind == "gap" or kind not in source_layers:
                continue
            features = source_layers[kind]
            if features.empty:
                continue
            by_id = features.to_crs(metric.crs).set_index("osm_id").geometry
            for source_id, street_id in result.source_street_pairs or []:
                if source_id in by_id.index:
                    geometry = by_id.loc[source_id]
                    if isinstance(geometry, gpd.GeoSeries):
                        evidence[street_id].extend(geometry.tolist())
                    else:
                        evidence[street_id].append(geometry)

        gap_ids = set(potential_results.get("gap").street_ids) if potential_results.get("gap") else set()
        records = []
        for _, street in metric.iterrows():
            street_id = street["osm_id"]
            if (street_id in gap_ids or street.geometry.length <= PotentialStreetDisplay.MAX_UNCLIPPED_WAY_M
                    or street_id not in evidence):
                records.append(street)
                continue
            area = unary_union([geometry.buffer(PotentialStreetDisplay.EVIDENCE_RADIUS_M)
                                for geometry in evidence[street_id]])
            parts = PotentialStreetDisplay._line_parts(street.geometry.intersection(area))
            if not parts:
                raise ValueError(f"Potential street {street_id} has no geometry near its sources")
            for part in parts:
                clipped = street.copy()
                clipped["geometry"] = part
                records.append(clipped)

        return gpd.GeoDataFrame(records, geometry="geometry", crs=metric.crs).to_crs(streets.crs)
