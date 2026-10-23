"""Combine OSM zebra crossing fragments for map display."""

from itertools import combinations

import geopandas as gpd
from shapely.geometry import LineString, Point


class ZebraCrossingSimplifier:
    @staticmethod
    def _continuation(first: LineString, second: LineString, max_gap_m: float) -> bool:
        """Check whether two short ways continue across the same crossing."""
        a0, a1 = Point(first.coords[0]), Point(first.coords[-1])
        b0, b1 = Point(second.coords[0]), Point(second.coords[-1])
        endpoint_pairs = [(a, b) for a in (a0, a1) for b in (b0, b1)]
        a, b = min(endpoint_pairs, key=lambda pair: pair[0].distance(pair[1]))
        if a.distance(b) > max_gap_m:
            return False

        ax, ay = a1.x - a0.x, a1.y - a0.y
        bx, by = b1.x - b0.x, b1.y - b0.y
        a_length = (ax * ax + ay * ay) ** 0.5
        b_length = (bx * bx + by * by) ** 0.5
        if not a_length or not b_length:
            return False

        # Allow about 32° of bend and 4 m sideways offset, regardless of way direction.
        parallel = abs(ax * bx + ay * by) / (a_length * b_length) >= 0.85
        sideways = abs(ax * (b.y - a.y) - ay * (b.x - a.x)) / a_length
        return parallel and sideways <= 4.0

    @staticmethod
    def simplify(
        zebras: gpd.GeoDataFrame, max_gap_m: float = 20.0
    ) -> gpd.GeoDataFrame:
        """Merge crossing ways; keep one marker for each crossing mapped only as a point."""
        if zebras.empty:
            result = zebras.copy()
            result["display_role"] = []
            return result

        # The gap and offset limits are metres, so project WGS84 input first.
        metric_crs = zebras.crs if zebras.crs.is_projected else zebras.estimate_utm_crs()
        metric = zebras.to_crs(metric_crs).reset_index(drop=True)
        line_indices = metric.index[metric.geometry.geom_type == "LineString"].tolist()
        point_indices = metric.index[metric.geometry.geom_type == "Point"].tolist()

        # Union aligned way fragments into one crossing group.
        parents = {index: index for index in line_indices}

        def root(index):
            while parents[index] != index:
                index = parents[index]
            return index

        for first, second in combinations(line_indices, 2):
            if ZebraCrossingSimplifier._continuation(
                metric.geometry[first], metric.geometry[second], max_gap_m
            ):
                parents[root(second)] = root(first)

        groups = {}
        for index in line_indices:
            groups.setdefault(root(index), []).append(index)

        # Nodes within 3 m of a way share its marker; others stay point-only crossings.
        attached_points = {key: [] for key in groups}
        standalone_points = []
        for index in point_indices:
            point = metric.geometry[index]
            nearest = min(
                line_indices, key=lambda line: point.distance(metric.geometry[line]), default=None
            )
            if nearest is not None and point.distance(metric.geometry[nearest]) <= 3.0:
                attached_points[root(nearest)].append(index)
            else:
                standalone_points.append(index)

        features = []
        for group, members in groups.items():
            if len(members) == 1:
                segment = metric.geometry[members[0]]
            else:
                # Bridge the carriageway gap between the two outermost endpoints.
                endpoints = [
                    Point(coords)
                    for index in members
                    for coords in (metric.geometry[index].coords[0], metric.geometry[index].coords[-1])
                ]
                start, end = max(
                    combinations(endpoints, 2), key=lambda pair: pair[0].distance(pair[1])
                )
                segment = LineString([start, end])

            # A group is a potential if any of its ways or attached nodes is one.
            properties = metric.iloc[members[0]].to_dict()
            properties["potential_candidate"] = bool(
                metric.loc[members + attached_points[group], "potential_candidate"].fillna(False).any()
            )
            features.append({**properties, "geometry": segment, "display_role": "segment"})
            features.append({
                **properties,
                "geometry": segment.interpolate(0.5, normalized=True),
                "display_role": "marker",
            })

        for index in standalone_points:
            features.append({**metric.iloc[index].to_dict(), "display_role": "marker"})

        return gpd.GeoDataFrame(features, geometry="geometry", crs=metric.crs).to_crs(zebras.crs)
