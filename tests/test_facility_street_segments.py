import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult
from PotentialCalculation.ProximityPotential import ProximityPotential


class FacilityStreetSegmentsTests(unittest.TestCase):
    def test_proximity_keeps_facility_street_pairs_and_excludes_conditional_t30(self):
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1, 2]}, geometry=[Point(10, 5), Point(40, 5)], crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20, 30], "maxspeed_class": ["50", "60", "50"],
             "conditional_speed": [None, None, "30"]},
            geometry=[LineString([(0, 0), (20, 0)]),
                      LineString([(30, 0), (50, 0)]),
                      LineString([(0, 4), (20, 4)])],
            crs="EPSG:25832",
        )

        result = ProximityPotential.find_tempo50_segments_near_features(
            streets, facilities, search_distance_m=10, metric_crs="EPSG:25832"
        )

        self.assertEqual(set(result.source_street_pairs), {(1, 10), (2, 20)})

    def test_creates_lines_and_annotates_both_popups(self):
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1], "name": ["Werkstatt"],
             "osm_url": ["https://www.openstreetmap.org/node/1"],
             "description": ["Einrichtungstyp laut OSM: Soziale Werkstatt"]},
            geometry=[Point(10, 5)], crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            {"osm_id": [10], "name": ["Teststraße"], "maxspeed_class": ["50"]},
            geometry=[LineString([(0, 0), (20, 0)])], crs="EPSG:25832",
        )
        potentials = {"disability_facilities": PotentialCalculationResult(
            [10], [1], [(1, 10)]
        )}

        lines = FacilityStreetSegments.create(
            streets, {"disability_facilities": facilities}, potentials
        )
        popup = FacilityStreetSegments.annotate_facilities(
            facilities, lines, "disability_facilities"
        )
        road_popup = FacilityStreetSegments.annotate_potential_streets(streets, lines)

        self.assertEqual(lines.geometry.geom_type.tolist(), ["LineString"])
        self.assertEqual(lines.current_speed_kmh.tolist(), [50])
        self.assertEqual(lines.distance_m.tolist(), [5.0])
        self.assertIn("Teststraße", popup.description.iloc[0])
        self.assertIn("aktuell 50 km/h", popup.description.iloc[0])
        self.assertEqual(popup.matched_street_count.tolist(), [1])
        self.assertIn("Werkstatt", road_popup.description.iloc[0])

    def test_no_matches_produce_an_empty_line_layer(self):
        streets = gpd.GeoDataFrame(
            {"osm_id": [10], "name": ["Teststraße"], "maxspeed_class": ["50"]},
            geometry=[LineString([(0, 0), (20, 0)])], crs="EPSG:25832",
        )

        lines = FacilityStreetSegments.create(streets, {}, {})

        self.assertTrue(lines.empty)
        self.assertEqual(lines.crs, streets.crs)

    def test_long_osm_way_is_clipped_to_facility_vicinity(self):
        facilities = gpd.GeoDataFrame(
            {"osm_id": [1], "name": ["Kita"],
             "osm_url": ["https://www.openstreetmap.org/node/1"]},
            geometry=[Point(50, 5)], crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            {"osm_id": [10], "name": ["Lange Straße"], "maxspeed_class": ["50"]},
            geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25832",
        )

        lines = FacilityStreetSegments.create(
            streets, {"educational_buildings": facilities},
            {"educational_buildings": PotentialCalculationResult([10], [1], [(1, 10)])},
        )

        self.assertEqual(len(lines), 1)
        self.assertLess(lines.geometry.iloc[0].length, 40)
        self.assertGreater(lines.geometry.iloc[0].length, 38)
        self.assertIn("innerhalb 20 m", lines.description.iloc[0])


if __name__ == "__main__":
    unittest.main()
