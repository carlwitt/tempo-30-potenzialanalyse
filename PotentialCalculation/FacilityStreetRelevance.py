"""Select facilities whose geometry genuinely reaches a public road.

A large school polygon can touch a street even when its centroid is far
away, while a remote institution name does not justify a road proposal.
Measure from the full geometry, require a public car road, and allow a
small addressed-point offset for official records. Only nearby facilities
then create street candidates.
"""

import geopandas as gpd
from shapely.geometry import Point

from DataRetrieval.RoadClassification import RoadClassification


class FacilityStreetRelevance:
    MAX_DISTANCE_M = 20
    ADDRESSED_EXTERNAL_POINT_DISTANCE_M = 30
    MOTORWAYS = frozenset({"motorway", "motorway_link"})

    @staticmethod
    def _street_name(value):
        if not isinstance(value, str):
            return ""
        return (value.casefold().replace("straße", "str").replace("strasse", "str")
                .replace("str.", "str").replace(" ", "").replace("-", ""))

    @staticmethod
    def search_distance(feature, street, default_distance_m: float) -> float:
        """Allow a small centerline offset for an addressed official point."""
        if (feature.get("element_type") == "external"
                and isinstance(feature.geometry, Point)
                and isinstance(feature.get("housenumber"), str)
                and feature.get("housenumber").strip()
                and FacilityStreetRelevance._street_name(feature.get("street"))
                and FacilityStreetRelevance._street_name(feature.get("street"))
                    == FacilityStreetRelevance._street_name(street.get("name"))):
            return max(default_distance_m, FacilityStreetRelevance.ADDRESSED_EXTERNAL_POINT_DISTANCE_M)
        return default_distance_m

    @staticmethod
    def traffic_streets(streets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Use the same car-access decision as street retrieval."""
        if "public_motorcar" in streets:
            return streets.loc[streets["public_motorcar"].eq(True)].copy()
        mask = streets.apply(RoadClassification.allows_public_motorcar, axis=1)
        return streets.loc[mask].copy()

    @staticmethod
    def potential_streets(streets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Select eligible 50/60 km/h roads for crossing and facility candidates."""
        roads = FacilityStreetRelevance.traffic_streets(streets)
        eligible = (
            ~roads["highway"].isin(FacilityStreetRelevance.MOTORWAYS)
            & roads["maxspeed_class"].isin({"50", "60"})
            & roads["conditional_speed"].ne("30")
        )
        return roads.loc[eligible].copy()

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

        metric_facilities = facilities.to_crs("EPSG:25832").reset_index(drop=True)
        metric_roads = roads.to_crs("EPSG:25832").reset_index(drop=True)
        nearby = metric_facilities[["geometry"]].copy()
        nearby["geometry"] = nearby.geometry.buffer(
            max(max_distance_m, FacilityStreetRelevance.ADDRESSED_EXTERNAL_POINT_DISTANCE_M)
        )
        joined = gpd.sjoin(nearby, metric_roads[["geometry"]], predicate="intersects")
        matches = {
            facility_index for facility_index, road_index in
            joined.reset_index()[["index", "index_right"]].itertuples(index=False, name=None)
            if metric_facilities.geometry.iloc[facility_index].distance(
                metric_roads.geometry.iloc[road_index]
            ) <= FacilityStreetRelevance.search_distance(
                metric_facilities.iloc[facility_index], metric_roads.iloc[road_index], max_distance_m,
            )
        }
        return facilities.iloc[sorted(matches)].copy()
