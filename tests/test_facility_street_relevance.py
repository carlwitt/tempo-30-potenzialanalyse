import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance


class FacilityStreetRelevanceTests(unittest.TestCase):
    def test_all_facility_geometries_need_a_traffic_street_within_20_metres(self):
        streets = gpd.GeoDataFrame(
            {"highway": ["residential", "service", "platform"]},
            geometry=[
                LineString([(0, -20), (0, 100)]),
                LineString([(100, -20), (100, 100)]),
                LineString([(200, -20), (200, 100)]),
            ], crs="EPSG:25832",
        )
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3, 4, 5]},
            geometry=[
                Point(19, 0), Point(21, 0), box(18, 30, 50, 60),
                Point(100, 0), Point(200, 0),
            ], crs="EPSG:25832",
        )

        result = FacilityStreetRelevance.filter_near_streets(facilities, streets)

        self.assertEqual(result.osm_id.tolist(), [1, 3])
        self.assertEqual(len(facilities), 5)

    def test_empty_roads_keep_an_empty_layer_with_its_columns(self):
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1]}, geometry=[Point(0, 0)], crs="EPSG:25832",
        )
        roads = gpd.GeoDataFrame(
            {"highway": ["service"]},
            geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:25832",
        )

        result = FacilityStreetRelevance.filter_near_streets(facilities, roads)

        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), facilities.columns.tolist())


if __name__ == "__main__":
    unittest.main()
