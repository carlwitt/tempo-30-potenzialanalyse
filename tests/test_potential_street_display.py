"""A long OSM way may have two distant crossing sources. Check that only local
supported sections appear, while a gap keeps its full connection.
"""

import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

from DataOutput.PotentialStreetDisplay import PotentialStreetDisplay
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


class PotentialStreetDisplayTests(unittest.TestCase):
    def test_distant_crossings_create_separate_local_sections_on_long_way(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [42], "name": ["Teststraße"]},
            geometry=[LineString([(x0, y), (x0 + 1000, y)])], crs="EPSG:25832",
        )
        crossings = gpd.GeoDataFrame(
            {"osm_id": [1, 2]},
            geometry=[Point(x0 + 100, y), Point(x0 + 800, y)], crs=streets.crs,
        )
        potential = {"zebra": PotentialCalculationResult([42], [1, 2], [(1, 42), (2, 42)])}

        result = PotentialStreetDisplay.clip_long_ways(streets, {"zebra": crossings}, potential)

        self.assertEqual(result.osm_id.tolist(), [42, 42])
        self.assertEqual([round(length) for length in result.geometry.length], [250, 300])
        self.assertEqual(round(result.geometry.iloc[0].bounds[2] - x0), 250)

    def test_gap_way_keeps_full_corridor(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [42]}, geometry=[LineString([(x0, y), (x0 + 1000, y)])],
            crs="EPSG:25832",
        )
        crossings = gpd.GeoDataFrame(
            {"osm_id": [1]}, geometry=[Point(x0 + 100, y)], crs=streets.crs,
        )
        potential = {
            "zebra": PotentialCalculationResult([42], [1], [(1, 42)]),
            "gap": PotentialCalculationResult([42]),
        }

        result = PotentialStreetDisplay.clip_long_ways(streets, {"zebra": crossings}, potential)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.geometry.iloc[0].length, 1000)

    def test_map_colors_prioritize_gap_then_crossing_then_facility(self):
        streets = gpd.GeoDataFrame(
            {
                "source_osm_ids": [[1], [2], [3], [4], [5], [6], [7]],
                "feature_type": [
                    "Potenzial durch Bildungseinrichtung",
                    "Potenzial durch Zebrastreifen",
                    "Potenzial durch mehrere Faktoren",
                    "Potenzial durch mehrere Faktoren",
                    None, None, "Potenzial durch mehrere Faktoren",
                ],
                "gap_role": ["potential"] * 4 + ["corridor_connection", "existing_connection", "potential"],
            },
            geometry=[Point(i, 0) for i in range(7)], crs="EPSG:25832",
        )
        potentials = {
            "educational_buildings": PotentialCalculationResult([1, 3, 4, 7]),
            "zebra": PotentialCalculationResult([2, 3, 4, 7]),
            "gap": PotentialCalculationResult(
                [4], direct_gap_lengths_m={4: 100}, gap_corridor_ways={4: [7]},
            ),
        }

        result = PotentialStreetDisplay.categorize(streets, potentials)

        self.assertEqual(result.map_potential_type.tolist(), [
            "facility", "crossing", "crossing", "gap", "gap", "existing_connection", "gap",
        ])
