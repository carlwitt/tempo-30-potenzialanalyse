"""A large school polygon can touch a public road away from its center. Check
whole-geometry distance and addressed official points so remote or
traffic-free facilities do not produce proposals.
"""

import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance
from PotentialCalculation.ProximityPotential import ProximityPotential
from DataOutput.FacilityStreetSegments import FacilityStreetSegments


class FacilityStreetRelevanceTests(unittest.TestCase):
    def test_all_facility_geometries_need_a_traffic_street_within_20_metres(self):
        streets = gpd.GeoDataFrame(
            {"highway": ["residential", "service", "platform", "service", "residential", "living_street"],
             "service": [None, "driveway", None, "alley", None, None],
             "access": [None, None, None, "customers", "private", None]},
            geometry=[
                LineString([(0, -20), (0, 100)]),
                LineString([(100, -20), (100, 100)]),
                LineString([(200, -20), (200, 100)]),
                LineString([(300, -20), (300, 100)]),
                LineString([(400, -20), (400, 100)]),
                LineString([(500, -20), (500, 100)]),
            ], crs="EPSG:25832",
        )
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3, 4, 5, 6, 7, 8]},
            geometry=[
                Point(19, 0), Point(21, 0), box(18, 30, 50, 60),
                Point(100, 0), Point(200, 0), Point(300, 0),
                Point(400, 0), Point(500, 0),
            ], crs="EPSG:25832",
        )

        result = FacilityStreetRelevance.filter_near_streets(facilities, streets)

        self.assertEqual(result.osm_id.tolist(), [1, 3, 6, 8])
        self.assertEqual(len(facilities), 8)

    def test_empty_roads_keep_an_empty_layer_with_its_columns(self):
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1]}, geometry=[Point(0, 0)], crs="EPSG:25832",
        )
        roads = gpd.GeoDataFrame(
            {"highway": ["service"], "service": ["driveway"]},
            geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:25832",
        )

        result = FacilityStreetRelevance.filter_near_streets(facilities, roads)

        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), facilities.columns.tolist())

    def test_addressed_official_point_matches_named_road_at_27_metres(self):
        roads = gpd.GeoDataFrame(
            {"osm_id": [151370242], "name": ["Treskowallee"], "highway": ["secondary"],
             "maxspeed_class": ["50"], "conditional_speed": [None]},
            geometry=[LineString([(0, -100), (0, 100)])], crs="EPSG:25832",
        )
        facilities = gpd.GeoDataFrame(
            {"osm_id": ["official:kita:11171580"], "element_type": ["external"],
             "street": ["Treskowallee"], "housenumber": ["22"],
             "name": ["BIP Kreativitätskita Treskow-Höfe"]},
            geometry=[Point(27, 0)], crs="EPSG:25832",
        )
        relevant = FacilityStreetRelevance.filter_near_streets(facilities, roads)
        self.assertEqual(len(relevant), 1)
        potential = ProximityPotential.find_tempo50_segments_near_features(roads, relevant, 20)
        self.assertEqual(potential.source_street_pairs, [("official:kita:11171580", 151370242)])
        segments = FacilityStreetSegments.create(
            roads, {"educational_buildings": relevant}, {"educational_buildings": potential},
        )
        self.assertEqual(len(segments), 1)
        self.assertIn("innerhalb 30 m", segments.description.iloc[0])

        facilities.loc[0, "street"] = "Andere Straße"
        self.assertTrue(FacilityStreetRelevance.filter_near_streets(facilities, roads).empty)
        self.assertEqual(
            ProximityPotential.find_tempo50_segments_near_features(roads, facilities, 20).street_ids,
            [],
        )


if __name__ == "__main__":
    unittest.main()
