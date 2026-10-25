"""Find eligible faster roads close to a facility's actual geometry.

A school can border a 50 km/h street even when its center is distant.
Measure in a metric CRS and retain the source-to-road pair, so the
proposal and its popup identify the school that supports each segment.
"""

import geopandas as gpd

from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


class ProximityPotential:
    @staticmethod
    def find_tempo50_segments_near_features(
        streets_gdf: gpd.GeoDataFrame,
        features_gdf: gpd.GeoDataFrame,
        search_distance_m: float = 15.0,
        metric_crs: str = "EPSG:25832",
    ) -> PotentialCalculationResult:
        """
        Finds OSM IDs of tempo-50/60 street segments that are within
        search_distance_m of given spatial features (schools, hospitals, etc.)
        """

        if streets_gdf is None or streets_gdf.empty:
            return PotentialCalculationResult([], [])

        if features_gdf is None or features_gdf.empty:
            return PotentialCalculationResult([], [])

        tempo50_or_60 = FacilityStreetRelevance.potential_streets(streets_gdf)

        if tempo50_or_60.empty:
            return PotentialCalculationResult([], [])

        # -----------------------------
        # CRS handling
        # -----------------------------
        if tempo50_or_60.crs != metric_crs:
            tempo50_or_60 = tempo50_or_60.to_crs(metric_crs)

        features = features_gdf.copy()
        if features.crs != metric_crs:
            features = features.to_crs(metric_crs)

        # -----------------------------
        # Buffer features
        # -----------------------------
        features_buffered = features.copy()
        features_buffered["geometry"] = features.geometry.buffer(max(
            search_distance_m, FacilityStreetRelevance.ADDRESSED_EXTERNAL_POINT_DISTANCE_M,
        ))

        features_buffered = features_buffered[["osm_id", "geometry"]].rename(
            columns={"osm_id": "feature_id"}
        )

        # -----------------------------
        # Spatial Join
        # -----------------------------
        joined = gpd.sjoin(
            tempo50_or_60,
            features_buffered,
            how="inner",
            predicate="intersects"
        )

        joined = joined.loc[[
            street.geometry.distance(features.geometry.loc[feature_index])
            <= FacilityStreetRelevance.search_distance(
                features.loc[feature_index], street, search_distance_m,
            )
            for _, street in joined.iterrows()
            for feature_index in [street["index_right"]]
        ]]

        # -----------------------------
        # Result
        # -----------------------------
        street_ids = joined["osm_id"].drop_duplicates().tolist()
        feature_ids = joined["feature_id"].drop_duplicates().tolist()
        source_street_pairs = list(
            joined[["feature_id", "osm_id"]].drop_duplicates().itertuples(index=False, name=None)
        )

        return PotentialCalculationResult(
            street_ids=street_ids,
            opt_source_ids=feature_ids,
            source_street_pairs=source_street_pairs,
        )
