import unittest

import geopandas as gpd
from shapely.geometry import LineString

from DataOutput.PotentialStreetConsolidation import PotentialStreetConsolidation


class PotentialStreetConsolidationTests(unittest.TestCase):
    @staticmethod
    def streets(specs):
        """Each spec is (id, name, start x, end x, y), in metres."""
        return gpd.GeoDataFrame(
            {
                "osm_id": [spec[0] for spec in specs],
                "name": [spec[1] for spec in specs],
                "feature_type": ["T30_Potenzial_Schule"] * len(specs),
            },
            geometry=[
                LineString([(390000 + start, 5820000 + y), (390000 + end, 5820000 + y)])
                for _, _, start, end, y in specs
            ],
            crs="EPSG:25832",
        )

    def test_connected_short_ways_are_kept_when_combined_length_exceeds_50(self):
        streets = self.streets([(1, "Schulstraße", 0, 30, 0), (2, "Schulstraße", 30, 55, 0)])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertEqual(result.osm_id.tolist(), [1, 2])
        self.assertEqual(result.logical_segment_length_m.tolist(), [55.0, 55.0])
        self.assertEqual(result.logical_segment_way_count.tolist(), [2, 2])
        self.assertEqual(streets.columns.tolist(), ["osm_id", "name", "feature_type", "geometry"])

    def test_short_logical_section_is_removed_inclusively(self):
        streets = self.streets([
            (1, "A", 0, 20, 0), (2, "A", 20, 50, 0),
            (3, "B", 100, 151, 0),
        ])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertEqual(result.osm_id.tolist(), [3])

    def test_same_name_elsewhere_does_not_rescue_short_way(self):
        streets = self.streets([(1, "A", 0, 30, 0), (2, "A", 100, 130, 0)])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertTrue(result.empty)

    def test_other_names_and_missing_names_do_not_connect(self):
        streets = self.streets([
            (1, "A", 0, 30, 0), (2, "B", 30, 60, 0),
            (3, None, 100, 130, 0), (4, None, 130, 160, 0),
        ])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertTrue(result.empty)

    def test_endpoint_near_miss_connects_but_crossing_at_midpoint_does_not(self):
        streets = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3], "name": ["A"] * 3},
            geometry=[
                LineString([(390000, 5820000), (390030, 5820000)]),
                LineString([(390030.4, 5820000), (390055.4, 5820000)]),
                LineString([(390010, 5819990), (390010, 5820010)]),
            ],
            crs="EPSG:25832",
        )

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertEqual(result.osm_id.tolist(), [1, 2])

    def test_empty_input_preserves_crs_and_schema(self):
        streets = self.streets([])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertTrue(result.empty)
        self.assertEqual(result.crs, streets.crs)
        self.assertIn("logical_segment_length_m", result.columns)


if __name__ == "__main__":
    unittest.main()
