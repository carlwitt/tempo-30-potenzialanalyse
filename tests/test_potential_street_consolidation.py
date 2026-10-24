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

    def test_20_m_way_is_removed_even_when_attached_to_long_section(self):
        streets = self.streets([
            (1, "A", 0, 60, 0), (2, "A", 60, 80, 0),
            (3, "A", 80, 105, 0), (4, "A", 105, 131, 0),
        ])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertEqual(result.osm_id.tolist(), [1, 3, 4])
        self.assertEqual(result.logical_segment_length_m.tolist(), [60.0, 51.0, 51.0])
        self.assertEqual(result.logical_segment_way_count.tolist(), [1, 2, 2])

    def test_removing_short_way_can_leave_section_below_50_m(self):
        streets = self.streets([(1, "A", 0, 20, 0), (2, "A", 20, 55, 0)])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertTrue(result.empty)

    def test_all_source_ways_at_most_20_m_yield_empty_export(self):
        streets = self.streets([(1, "A", 0, 10, 0), (2, "A", 10, 30, 0)])

        result = PotentialStreetConsolidation.filter_short_isolated(streets)

        self.assertTrue(result.empty)
        self.assertEqual(result.crs, streets.crs)
        self.assertIn("logical_segment_way_count", result.columns)

    def test_short_connector_is_merged_into_long_conditional_gap(self):
        streets = self.streets([
            (1, "A", 0, 60, 0), (2, "A", 60, 77, 0),
            (3, "A", 77, 147, 0),
        ])
        option = {"potential_type": "zebra", "anchor_street_osm_id": 4,
                  "source_objects": [{"name": "Zebrastreifen", "osm_url": "https://www.openstreetmap.org/node/5"}]}
        streets["is_conditional_gap"] = True
        streets["gap_required_potentials"] = [[[option]]] * 3
        streets["maxspeed_class"] = "50"
        anchor = self.streets([(4, "A", 147, 187, 0)])

        filtered = PotentialStreetConsolidation.filter_short_isolated(streets)
        result = PotentialStreetConsolidation.consolidate_conditional_gaps(filtered, anchor)

        self.assertEqual(filtered.osm_id.tolist(), [1, 2, 3])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.source_osm_ids.iloc[0], [1, 2, 3])
        self.assertEqual(result.logical_segment_length_m.iloc[0], 147.0)
        self.assertEqual(result.gap_length_after_m.iloc[0], 147.0)
        self.assertEqual(result.gap_length_current_m.iloc[0], 187.0)
        self.assertEqual(round(result.geometry.iloc[0].length, 1), 147.0)

    def test_conditional_sections_with_different_anchors_stay_separate(self):
        streets = self.streets([(1, "A", 0, 60, 0), (2, "A", 60, 120, 0)])
        streets["is_conditional_gap"] = True
        streets["gap_required_potentials"] = [
            [[{"potential_type": "zebra", "anchor_street_osm_id": anchor}]]
            for anchor in (3, 4)
        ]
        streets["maxspeed_class"] = "50"
        anchors = self.streets([(3, "A", -40, 0, 0), (4, "A", 120, 160, 0)])

        filtered = PotentialStreetConsolidation.filter_short_isolated(streets)
        result = PotentialStreetConsolidation.consolidate_conditional_gaps(filtered, anchors)

        self.assertEqual(len(result), 2)
        self.assertEqual(result.source_osm_ids.tolist(), [[1], [2]])

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
