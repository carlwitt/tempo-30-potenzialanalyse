"""Associate mapped main entrances with their facility before street checks.

An OSM school polygon can touch a fast road along a wall while its direct
access faces another street. Prefer entrance nodes belonging to its outline;
an entrance inside the polygon is weaker, but still more local evidence than
the whole building edge. The same association guides imagery and candidates.
"""

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


class EntranceEvidence:
    @staticmethod
    def points_for_feature(feature, entrances, by_id, use_area=True):
        if entrances is None or entrances.empty:
            return [], None, []
        node_ids = feature.get("osm_node_ids", [])
        if not isinstance(node_ids, (list, tuple, set)):
            node_ids = []
        node_ids = list(dict.fromkeys([*node_ids, feature.get("osm_id")]))
        matched_ids = [node_id for node_id in node_ids if node_id in by_id]
        points = [by_id[node_id] for node_id in matched_ids]
        if points:
            return points, "OSM-Haupteingang auf Objektgrenze", matched_ids
        if use_area and isinstance(feature.geometry, (Polygon, MultiPolygon)):
            matches = entrances.sindex.query(feature.geometry, predicate="intersects")
            points = entrances.geometry.iloc[matches].tolist()
            if points:
                return (
                    points, "OSM-Haupteingang im Areal; Zuordnung angenähert",
                    entrances["osm_id"].iloc[matches].tolist(),
                )
        return [], None, []

    @staticmethod
    def preferred_geometry(features, entrances, metric_crs="EPSG:25832", use_area=True):
        """Replace a facility's search geometry only when an entrance matches."""
        result = features.to_crs(metric_crs).copy()
        matched = set()
        result["main_entrance_osm_ids"] = [[] for _ in range(len(result))]
        if entrances is None or entrances.empty or result.empty:
            return result, matched
        metric_entrances = entrances.to_crs(metric_crs)
        by_id = dict(zip(metric_entrances["osm_id"], metric_entrances.geometry))
        for index, feature in result.iterrows():
            points, _, ids = EntranceEvidence.points_for_feature(
                feature, metric_entrances, by_id, use_area=use_area,
            )
            if points:
                result.at[index, "geometry"] = unary_union(points)
                result.at[index, "main_entrance_osm_ids"] = ids
                matched.add(index)
        return result, matched
