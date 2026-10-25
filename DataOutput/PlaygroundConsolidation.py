"""Select playground features relevant to the map export."""

import geopandas as gpd


class PlaygroundConsolidation:
    @staticmethod
    def summarize_playground_features(
        playgroundGDF: gpd.GeoDataFrame, compact: bool = True,
    ) -> gpd.GeoDataFrame:
        """Use compact map sources only when the region enables that rule."""
        if not compact:
            return PlaygroundConsolidation._legacy_point_clusters(playgroundGDF)
        is_potential = playgroundGDF["potential_candidate"].eq(True).fillna(False)
        is_polygon = playgroundGDF.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        return playgroundGDF.loc[is_potential | is_polygon].copy()

    @staticmethod
    def _legacy_point_clusters(playgrounds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Preserve main's non-candidate playground markers and 15 m clusters."""
        from sklearn.cluster import DBSCAN
        import pandas as pd
        from shapely.geometry import mapping

        metric = playgrounds.to_crs("EPSG:32632")
        mask = metric["potential_candidate"].eq(False) & metric.geometry.geom_type.eq("Point")
        points = metric.loc[mask].copy()
        if points.empty:
            return playgrounds.copy()
        coordinates = pd.DataFrame({"x": points.geometry.x, "y": points.geometry.y})
        points["cluster_id"] = DBSCAN(eps=15, min_samples=1).fit(coordinates).labels_
        features = []
        for _, cluster in points.groupby("cluster_id", sort=False):
            geometry = cluster.geometry.iloc[0] if len(cluster) == 1 else cluster.geometry.union_all().centroid
            features.append({
                "type": "Feature", "properties": {"potential_candidate": False},
                "geometry": mapping(geometry),
            })
        for _, row in metric.loc[~mask].iterrows():
            features.append({
                "type": "Feature", "properties": {"potential_candidate": row.potential_candidate},
                "geometry": mapping(row.geometry),
            })
        return gpd.GeoDataFrame.from_features(features, crs="EPSG:32632").to_crs(playgrounds.crs)
