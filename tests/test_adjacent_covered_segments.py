import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

from DataOutput.AdjacentCoveredSegments import AdjacentCoveredSegments
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


class AdjacentCoveredSegmentsTests(unittest.TestCase):
    @staticmethod
    def _facility(x=90):
        return gpd.GeoDataFrame(
            {"osm_id": [1], "name": ["Kita"],
             "osm_url": ["https://www.openstreetmap.org/node/1"],
             "description": ["Kindertagesstätte"]},
            geometry=[Point(x, 5)], crs="EPSG:25832",
        )

    @staticmethod
    def _streets(records):
        return gpd.GeoDataFrame(
            {
                "osm_id": [road[0] for road in records],
                "name": [road[1] for road in records],
                "maxspeed_class": [road[2] for road in records],
                "conditional_speed": [road[3] for road in records],
            },
            geometry=[LineString(road[4]) for road in records], crs="EPSG:25832",
        )

    @staticmethod
    def _results():
        return {"educational_buildings": PotentialCalculationResult([10], [1], [(1, 10)])}

    def test_traces_connected_t30_and_conditional_t30_with_500m_network_limit(self):
        streets = self._streets([
            (10, "Hauptstraße", "50", None, [(0, 0), (100, 0)]),
            (20, "Hauptstraße", "30", None, [(100, 0), (200, 0)]),
            (30, "Hauptstraße", "50", "30", [(200, 0), (800, 0)]),
            (40, "Hauptstraße", "30", None, [(-100, 0), (0, 0)]),
            (50, "Parallele Straße", "30", None, [(90, 10), (300, 10)]),
        ])
        streets["cond_speed_days"] = [None, None, "Mo-Fr", None, None]
        facilities = {"educational_buildings": self._facility()}

        result = AdjacentCoveredSegments.create(streets, facilities, self._results())
        rows = result.set_index("street_osm_id")

        self.assertEqual(set(rows.index), {20, 30, 40})
        self.assertAlmostEqual(rows.loc[20, "distance_start_m"], 10)
        self.assertAlmostEqual(rows.loc[30, "distance_start_m"], 110)
        self.assertAlmostEqual(rows.loc[30, "geometry"].length, 390)
        self.assertAlmostEqual(rows.loc[40, "distance_start_m"], 90)
        self.assertAlmostEqual(rows.loc[40, "geometry"].length, 100)
        self.assertEqual(rows.loc[30, "coverage_status"], "Bedingtes Tempo 30")
        self.assertIn("Mo-Fr", rows.loc[30, "description"])
        self.assertIn("500.0 m", rows.loc[30, "description"])

        popup = AdjacentCoveredSegments.annotate_facilities(
            facilities["educational_buildings"], result, "educational_buildings"
        )
        source_popup = AdjacentCoveredSegments.annotate_potential_streets(
            streets.loc[streets.osm_id == 10].assign(description="Potenzial"), result
        )
        self.assertEqual(popup.covered_street_count.tolist(), [3])
        self.assertIn("Bedingtes Tempo 30", popup.description.iloc[0])
        self.assertIn("Mo-Fr", popup.description.iloc[0])
        self.assertIn("Angrenzend bereits abgedeckt", source_popup.description.iloc[0])

    def test_does_not_turn_into_t30_side_street_when_main_road_continues_at_t50(self):
        streets = self._streets([
            (10, "Hauptstraße", "50", None, [(0, 0), (100, 0)]),
            (20, "Hauptstraße", "50", None, [(100, 0), (200, 0)]),
            (30, "Seitenstraße", "30", None, [(100, 0), (100, 200)]),
        ])

        result = AdjacentCoveredSegments.create(
            streets, {"educational_buildings": self._facility()}, self._results()
        )

        self.assertTrue(result.empty)
        self.assertEqual(result.crs, streets.crs)

    def test_omits_covered_road_beyond_500m_of_source_anchor(self):
        streets = self._streets([
            (10, "Lange Straße", "50", None, [(0, 0), (1000, 0)]),
            (20, "Lange Straße", "30_Zone", None, [(1000, 0), (1100, 0)]),
        ])

        result = AdjacentCoveredSegments.create(
            streets, {"educational_buildings": self._facility(100)}, self._results()
        )

        self.assertTrue(result.empty)

    def test_uses_nearest_logical_continuation_across_renamed_road(self):
        streets = self._streets([
            (10, "Alte Straße", "50", None, [(0, 0), (100, 0)]),
            (20, "Neue Straße", "30_Zone", None, [(100, 0), (200, 0)]),
        ])

        result = AdjacentCoveredSegments.create(
            streets, {"educational_buildings": self._facility()}, self._results()
        )

        self.assertEqual(result.street_osm_id.tolist(), [20])
        self.assertEqual(result.coverage_status.tolist(), ["Tempo-30-Zone"])

    def test_covered_context_uses_only_visible_facility_source_pairs(self):
        streets = self._streets([
            (10, "Hauptstraße", "50", None, [(0, 0), (100, 0)]),
            (11, "Hauptstraße", "50", None, [(100, 0), (200, 0)]),
            (20, "Hauptstraße", "30", None, [(200, 0), (300, 0)]),
        ])
        potentials = {"educational_buildings": PotentialCalculationResult(
            [10, 11], [1], [(1, 10), (1, 11)]
        )}

        result = AdjacentCoveredSegments.create(
            streets, {"educational_buildings": self._facility(150)}, potentials,
            visible_proposal_pairs={("educational_buildings", 1, 11)},
        )

        self.assertEqual(result.street_osm_id.tolist(), [20])
        self.assertEqual(result.source_street_osm_id.tolist(), [11])


if __name__ == "__main__":
    unittest.main()
