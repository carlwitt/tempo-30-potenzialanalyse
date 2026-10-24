"""Keep facilities with a direct relationship to a traffic street."""

import geopandas as gpd


class FacilityStreetRelevance:
    MAX_DISTANCE_M = 20
    TRAFFIC_HIGHWAYS = frozenset({
        "primary", "primary_link", "secondary", "secondary_link",
        "tertiary", "tertiary_link", "unclassified", "residential",
        "living_street", "road",
    })

    @staticmethod
    def traffic_streets(streets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Exclude paths, platforms, service roads and trunk roads."""
        return streets.loc[streets["highway"].isin(FacilityStreetRelevance.TRAFFIC_HIGHWAYS)].copy()

    @staticmethod
    def filter_near_streets(
        facilities: gpd.GeoDataFrame, streets: gpd.GeoDataFrame,
        max_distance_m: float = MAX_DISTANCE_M,
    ) -> gpd.GeoDataFrame:
        """Measure from the whole facility geometry, including polygon edges."""
        if facilities.empty or streets.empty:
            return facilities.iloc[0:0].copy()

        roads = FacilityStreetRelevance.traffic_streets(streets)
        if roads.empty:
            return facilities.iloc[0:0].copy()

        nearby = facilities.to_crs("EPSG:25832")[["geometry"]].reset_index(drop=True)
        nearby["geometry"] = nearby.geometry.buffer(max_distance_m)
        roads = roads.to_crs("EPSG:25832")[["geometry"]]
        matches = gpd.sjoin(nearby, roads, predicate="intersects").index.unique()
        return facilities.iloc[matches].copy()
