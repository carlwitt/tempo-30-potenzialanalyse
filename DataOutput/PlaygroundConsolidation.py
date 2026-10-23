"""Select playground features relevant to the map export."""

import geopandas as gpd


class PlaygroundConsolidation:
    @staticmethod
    def summarize_playground_features(playgroundGDF: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Keep potential features and all playground polygons."""
        is_potential = playgroundGDF["potential_candidate"].eq(True).fillna(False)
        is_polygon = playgroundGDF.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        return playgroundGDF.loc[is_potential | is_polygon].copy()
