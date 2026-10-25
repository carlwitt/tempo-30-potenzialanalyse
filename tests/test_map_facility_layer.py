"""A fully exported school need not appear as a map point when it has no
proposal. Check compact map selection while excluding unconfirmed disability
facilities from the optional layer.
"""

import unittest

import geopandas as gpd
from shapely.geometry import Point

from DataOutput.MapFacilityLayer import MapFacilityLayer


class MapFacilityLayerTests(unittest.TestCase):
    def test_covered_facilities_are_hidden_without_changing_full_layer(self):
        features = gpd.GeoDataFrame(
            {"osm_id": [1, 2], "potential_candidate": [False, True]},
            geometry=[Point(0, 0), Point(1, 0)], crs="EPSG:25832",
        )

        visible = MapFacilityLayer.select(features, "educational_buildings")

        self.assertEqual(visible.osm_id.tolist(), [2])
        self.assertEqual(features.osm_id.tolist(), [1, 2])

    def test_disability_review_cases_are_hidden(self):
        features = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3, 4], "potential_candidate": [False, False, False, True],
             "facility_status": ["confirmed_disabled", "target_group_unknown",
                                 "different_target_group", "confirmed_disabled"]},
            geometry=[Point(index, 0) for index in range(4)], crs="EPSG:25832",
        )

        visible = MapFacilityLayer.select(features, "disability_facilities")

        self.assertEqual(visible.osm_id.tolist(), [4])
        self.assertEqual(features.osm_id.tolist(), [1, 2, 3, 4])

    def test_unconfirmed_disability_facilities_are_hidden_even_if_marked_as_candidates(self):
        features = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3], "potential_candidate": [True, True, True],
             "facility_status": ["target_group_unknown", "different_target_group",
                                 "confirmed_disabled"]},
            geometry=[Point(index, 0) for index in range(3)], crs="EPSG:25832",
        )

        visible = MapFacilityLayer.select(features, "disability_facilities")

        self.assertEqual(visible.osm_id.tolist(), [3])


if __name__ == "__main__":
    unittest.main()
