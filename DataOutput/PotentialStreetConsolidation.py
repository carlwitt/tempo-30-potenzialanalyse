"""Group connected, equally named potential ways for export filtering."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


class PotentialStreetConsolidation:
    MAX_ISOLATED_LENGTH_M = 50
    ENDPOINT_TOLERANCE_M = 0.5

    @staticmethod
    def filter_short_isolated(streets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Keep source ways, but remove logical sections no longer than 50 m.

        Connectivity is limited to potential ways with the same street name.
        Unnamed ways cannot be safely associated with one another.
        """
        if streets.empty:
            result = streets.copy()
            result["logical_segment_length_m"] = pd.Series(dtype=float)
            result["logical_segment_way_count"] = pd.Series(dtype=int)
            return result

        metric = streets.to_crs("EPSG:25832").reset_index(drop=True)
        parent = list(range(len(metric)))
        tolerance = PotentialStreetConsolidation.ENDPOINT_TOLERANCE_M
        spatial_index = metric.sindex
        names = [str(name).strip() if pd.notna(name) else "" for name in metric["name"]]
        endpoints = [
            (Point(line.coords[0]), Point(line.coords[-1])) if line.geom_type == "LineString" else ()
            for line in metric.geometry
        ]

        def root(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        # A shared name alone is insufficient: only touching way endpoints
        # form one logical section. Spatial-index queries keep this local.
        for index, ends in enumerate(endpoints):
            if not names[index]:
                continue
            for endpoint in ends:
                for other in spatial_index.query(endpoint.buffer(tolerance)):
                    if other <= index or names[other] != names[index]:
                        continue
                    if any(endpoint.distance(candidate) <= tolerance for candidate in endpoints[other]):
                        parent[root(other)] = root(index)

        members = {}
        for index in range(len(metric)):
            members.setdefault(root(index), []).append(index)

        lengths = metric.geometry.length
        component_lengths = {
            component: sum(lengths.iloc[index] for index in indices)
            for component, indices in members.items()
        }
        keep = [
            component_lengths[root(index)] > PotentialStreetConsolidation.MAX_ISOLATED_LENGTH_M
            for index in range(len(metric))
        ]

        result = streets.iloc[[index for index, retained in enumerate(keep) if retained]].copy()
        result["logical_segment_length_m"] = [
            round(component_lengths[root(index)], 1) for index, retained in enumerate(keep) if retained
        ]
        result["logical_segment_way_count"] = [
            len(members[root(index)]) for index, retained in enumerate(keep) if retained
        ]
        return result
