"""A zebra crossing beside a private or already conditional Tempo-30 road is not
an open proposal. Check road eligibility before distance matching.
"""

import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

from PotentialCalculation.ZebraPotential import ZebraPotential


class ZebraPotentialTests(unittest.TestCase):
    def test_conditional_t30_is_already_covered(self):
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20], "highway": ["residential"] * 2,
             "maxspeed_class": ["50"] * 2, "conditional_speed": ["30", None]},
            geometry=[LineString([(0, 0), (10, 0)]),
                      LineString([(100, 0), (110, 0)])], crs="EPSG:25832",
        )
        zebras = gpd.GeoDataFrame(
            {"osm_id": [1, 2]}, geometry=[Point(5, 0), Point(105, 0)], crs="EPSG:25832",
        )

        result = ZebraPotential.find_tempo50_segments_near_zebra(streets, zebras)

        self.assertEqual(result.source_street_pairs, [(2, 20)])

    def test_private_road_does_not_create_zebra_potential(self):
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20], "highway": ["service", "residential"],
             "access": ["private", None], "maxspeed_class": ["50", "50"],
             "conditional_speed": [None, None]},
            geometry=[LineString([(0, 0), (10, 0)]),
                      LineString([(100, 0), (110, 0)])], crs="EPSG:25832",
        )
        zebras = gpd.GeoDataFrame(
            {"osm_id": [1, 2]}, geometry=[Point(5, 0), Point(105, 0)], crs="EPSG:25832",
        )

        result = ZebraPotential.find_tempo50_segments_near_zebra(streets, zebras)

        self.assertEqual(result.source_street_pairs, [(2, 20)])

    def test_motorway_is_not_a_zebra_candidate(self):
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20], "highway": ["motorway", "residential"],
             "maxspeed_class": ["60", "50"], "conditional_speed": [None, None]},
            geometry=[LineString([(0, 0), (10, 0)]),
                      LineString([(100, 0), (110, 0)])], crs="EPSG:25832",
        )
        zebras = gpd.GeoDataFrame(
            {"osm_id": [1, 2]}, geometry=[Point(5, 0), Point(105, 0)], crs="EPSG:25832",
        )

        result = ZebraPotential.find_tempo50_segments_near_zebra(streets, zebras)

        self.assertEqual(result.source_street_pairs, [(2, 20)])


if __name__ == "__main__":
    unittest.main()
