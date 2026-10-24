import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from DataOutput.DistrictStatsCreator import DistrictStatsCreator
from DataOutput.ZebraCrossingSimplifier import ZebraCrossingSimplifier


class ZebraCrossingSimplifierTests(unittest.TestCase):
    def test_split_crossing_and_tagged_point_become_one_segment_and_marker(self):
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [False, True, False], "street": [None] * 3},
            geometry=[
                LineString([(0, 0), (0, 5)]),
                LineString([(0, 8), (0, 13)]),
                Point(0, 4),
            ],
            crs="EPSG:25833",
        )

        result = ZebraCrossingSimplifier.simplify(zebras)

        self.assertEqual(result.display_role.tolist(), ["segment", "marker"])
        self.assertAlmostEqual(result.iloc[0].geometry.length, 13)
        self.assertAlmostEqual(result.iloc[1].geometry.y, 6.5)
        self.assertTrue(result.potential_candidate.all())
        self.assertEqual(len(zebras), 3)

    def test_point_only_crossing_remains_a_marker(self):
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [False], "street": [None]},
            geometry=[Point(10, 10)],
            crs="EPSG:25833",
        )

        result = ZebraCrossingSimplifier.simplify(zebras)

        self.assertEqual(result.display_role.tolist(), ["marker"])
        self.assertTrue(result.geometry.iloc[0].equals(zebras.geometry.iloc[0]))

    def test_nearby_perpendicular_crossings_stay_separate(self):
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [False, False], "street": [None, None]},
            geometry=[
                LineString([(0, 0), (0, 5)]),
                LineString([(3, 0), (8, 0)]),
            ],
            crs="EPSG:25833",
        )

        result = ZebraCrossingSimplifier.simplify(zebras)

        self.assertEqual(result.display_role.tolist().count("segment"), 2)
        self.assertEqual(result.display_role.tolist().count("marker"), 2)

    def test_end_nodes_of_one_crossing_count_once_in_district_stats(self):
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [False, False, True, True], "street": [None] * 4},
            geometry=[
                LineString([(0, 0), (0, 5)]),
                LineString([(0, 5), (0, 10)]),
                Point(0, -4.5),
                Point(0, 14.5),
            ],
            crs="EPSG:25832",
        )
        district = gpd.GeoDataFrame(
            {"district_id": ["01"]},
            geometry=[Polygon([(-100, -100), (100, -100), (100, 100), (-100, 100)])],
            crs=zebras.crs,
        )

        result = ZebraCrossingSimplifier.simplify(zebras)
        markers = result.loc[result.display_role == "marker"]
        counts = DistrictStatsCreator._counts(district, markers)

        self.assertEqual(result.display_role.tolist(), ["segment", "marker"])
        self.assertTrue(markers.potential_candidate.iloc[0])
        self.assertEqual(counts[0], [1, 1])

        covered = zebras.copy()
        covered["potential_candidate"] = False
        covered_markers = ZebraCrossingSimplifier.simplify(covered)
        covered_markers = covered_markers.loc[covered_markers.display_role == "marker"]
        self.assertEqual(DistrictStatsCreator._counts(district, covered_markers)[0], [1, 0])

    def test_nearby_side_node_remains_separate_crossing(self):
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [False, False], "street": [None, None]},
            geometry=[LineString([(0, 0), (0, 10)]), Point(5, 12)],
            crs="EPSG:25832",
        )

        result = ZebraCrossingSimplifier.simplify(zebras)

        self.assertEqual(result.display_role.tolist(), ["segment", "marker", "marker"])

if __name__ == "__main__":
    unittest.main()
