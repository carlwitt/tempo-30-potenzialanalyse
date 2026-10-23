import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

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

if __name__ == "__main__":
    unittest.main()
