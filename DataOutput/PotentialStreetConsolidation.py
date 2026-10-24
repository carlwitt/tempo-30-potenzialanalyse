"""Turn connected potential ways into readable street sections for export."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString, Point
from shapely.ops import linemerge, unary_union


class PotentialStreetConsolidation:
    MAX_SOURCE_LENGTH_M = 20
    MAX_ISOLATED_LENGTH_M = 50
    ENDPOINT_TOLERANCE_M = 0.5

    @staticmethod
    def _dependency_key(groups):
        return tuple(sorted(
            tuple(sorted((option["potential_type"], int(option["anchor_street_osm_id"]))
                         for option in group))
            for group in (groups or [])
        ))

    @staticmethod
    def connected_members(metric, keys):
        parent = list(range(len(metric)))
        tolerance = PotentialStreetConsolidation.ENDPOINT_TOLERANCE_M
        spatial_index = metric.sindex
        endpoints = [
            (Point(line.coords[0]), Point(line.coords[-1])) if line.geom_type == "LineString" else ()
            for line in metric.geometry
        ]

        def root(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for index, ends in enumerate(endpoints):
            if keys[index] is None:
                continue
            for endpoint in ends:
                for other in spatial_index.query(endpoint.buffer(tolerance)):
                    if other <= index or keys[other] != keys[index]:
                        continue
                    if any(endpoint.distance(candidate) <= tolerance for candidate in endpoints[other]):
                        parent[root(other)] = root(index)

        members = {}
        for index in range(len(metric)):
            members.setdefault(root(index), []).append(index)
        return list(members.values())

    @staticmethod
    def filter_short_isolated(streets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Remove source ways up to 20 m, then logical sections up to 50 m.

        Connectivity uses only the remaining potential ways with the same
        street name. Unnamed ways cannot be safely associated with one another.
        """
        if streets.empty:
            result = streets.copy()
            result["logical_segment_length_m"] = pd.Series(dtype=float)
            result["logical_segment_way_count"] = pd.Series(dtype=int)
            return result

        metric = streets.to_crs("EPSG:25832")
        lengths = metric.geometry.length
        names = [str(name).strip() if pd.notna(name) and str(name).strip() else None
                 for name in metric["name"]]

        # A short way inside a longer conditional gap is a connector, not an
        # isolated map fragment. It must survive until the section is merged.
        protected = set()
        if "is_conditional_gap" in streets:
            keys = [
                (names[index], PotentialStreetConsolidation._dependency_key(groups))
                if names[index] and conditional else None
                for index, (conditional, groups) in enumerate(zip(
                    streets["is_conditional_gap"], streets["gap_required_potentials"]
                ))
            ]
            for members in PotentialStreetConsolidation.connected_members(metric, keys):
                if len(members) > 1 and sum(lengths.iloc[index] for index in members) > 50:
                    protected.update(index for index in members if keys[index] is not None)

        source_positions = [
            index for index, length in enumerate(lengths)
            if length > PotentialStreetConsolidation.MAX_SOURCE_LENGTH_M or index in protected
        ]
        source = streets.iloc[source_positions]
        metric = metric.iloc[source_positions].reset_index(drop=True)
        if metric.empty:
            result = source.copy()
            result["logical_segment_length_m"] = pd.Series(dtype=float)
            result["logical_segment_way_count"] = pd.Series(dtype=int)
            return result

        names = [str(name).strip() if pd.notna(name) and str(name).strip() else None
                 for name in metric["name"]]
        components = PotentialStreetConsolidation.connected_members(metric, names)
        length_by_index = {}
        count_by_index = {}
        for members in components:
            length = sum(metric.geometry.length.iloc[index] for index in members)
            for index in members:
                length_by_index[index] = length
                count_by_index[index] = len(members)

        retained = [index for index in range(len(metric))
                    if length_by_index[index] > PotentialStreetConsolidation.MAX_ISOLATED_LENGTH_M]
        result = source.iloc[retained].copy()
        result["logical_segment_length_m"] = [round(length_by_index[index], 1) for index in retained]
        result["logical_segment_way_count"] = [count_by_index[index] for index in retained]
        return result

    @staticmethod
    def consolidate_conditional_gaps(streets: gpd.GeoDataFrame, reference_streets) -> gpd.GeoDataFrame:
        """Merge touching gap ways with the same name, speed and prerequisites."""
        if streets.empty:
            return streets.copy()

        metric = streets.to_crs("EPSG:25832").reset_index(drop=True)
        reference = reference_streets.to_crs("EPSG:25832").drop_duplicates("osm_id").set_index("osm_id")
        keys = []
        for _, street in metric.iterrows():
            name = street["name"]
            keys.append((str(name).strip(), street["maxspeed_class"],
                         PotentialStreetConsolidation._dependency_key(street["gap_required_potentials"]))
                        if street["is_conditional_gap"] and pd.notna(name) and str(name).strip()
                        else None)

        records = []
        for members in PotentialStreetConsolidation.connected_members(metric, keys):
            row = metric.iloc[members[0]].copy()
            source_ids = [int(metric.iloc[index]["osm_id"]) for index in members]
            row["source_osm_ids"] = source_ids
            row["gap_length_after_m"] = None
            row["gap_length_with_prerequisites_m"] = None
            if keys[members[0]] is not None:
                row["gap_length_current_m"] = None
                geometry = unary_union(metric.geometry.iloc[members].tolist())
                row["geometry"] = linemerge(geometry) if isinstance(geometry, MultiLineString) else geometry
                length = sum(metric.geometry.iloc[index].length for index in members)
                row["logical_segment_length_m"] = round(length, 1)
                row["logical_segment_way_count"] = len(members)
                row["gap_length_after_m"] = round(length, 1)

                # Only a unique anchor per required end gives one defensible
                # current length; other alternatives are left unquantified.
                groups = row["gap_required_potentials"]
                anchor_ids = set()
                for group in groups:
                    ids = {int(option["anchor_street_osm_id"]) for option in group}
                    if len(ids) == 1:
                        anchor_ids.update(ids)
                    else:
                        anchor_ids = set()
                        break
                if anchor_ids and anchor_ids.issubset(reference.index):
                    row["gap_length_with_prerequisites_m"] = round(
                        length + sum(reference.loc[anchor_id].geometry.length for anchor_id in anchor_ids), 1
                    )
            records.append(row)

        result = gpd.GeoDataFrame(records, geometry="geometry", crs=metric.crs)
        return result.to_crs(streets.crs)
