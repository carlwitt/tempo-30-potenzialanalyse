"""Keep a city's candidates and map geometry inside its administrative border.

Problem: Berlin's Overpass bounding box also contains Brandenburg Kitas,
schools and roads; an external road can become a gap anchor that the map clips.
Goal: Candidates, visible connections and district totals cover the same city.
Action: Assign sources to one area, trace gaps on complete in-area roads, and
clip exported geometry to the border.
Impact: Neighboring sources and invisible external anchors cannot create
Berlin map results.
"""

import geopandas as gpd
import pandas as pd


class AreaScope:
    @staticmethod
    def filter_sources(features: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Assign a Kita, school or crossing to Berlin by its representative point.

        A polygon straddling the border is counted once, as in district stats.
        """
        if features.empty:
            return features.copy()
        area = districts.to_crs(features.crs).geometry.union_all()
        inside = features.geometry.representative_point().map(area.covers)
        return features.loc[inside].copy()

    @staticmethod
    def filter_complete_network(streets: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Exclude boundary-crossing roads before tracing gap connections.

        Otherwise a Berlin gap can end at a Brandenburg Tempo-30 road that
        disappears when the exported map is clipped to Berlin.
        """
        if streets.empty:
            return streets.copy()
        area = districts.to_crs(streets.crs).geometry.union_all()
        return streets.loc[streets.geometry.covered_by(area)].copy()

    @staticmethod
    def clip_geometries(features: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Trim exported lines and polygons to the city border.

        For example, a road or playground crossing Berlin's edge remains
        visible only on its Berlin side, without changing source assignment.
        """
        if features.empty:
            return features.copy()
        area = districts.to_crs(features.crs).geometry.union_all()
        indexed = features.reset_index(drop=True)
        kinds = indexed.geometry.geom_type
        # GeoPandas ignores keep_geom_type on a mixed geometry layer.
        clipped = [
            gpd.clip(indexed.loc[kinds == kind], area, keep_geom_type=True)
            for kind in kinds.unique()
        ]
        return gpd.GeoDataFrame(
            pd.concat(clipped).sort_index(kind="stable"), geometry=features.geometry.name, crs=features.crs,
        )
