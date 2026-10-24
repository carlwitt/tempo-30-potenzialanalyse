import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from DataOutput.DistrictStatsCreator import DistrictStatsCreator


class DistrictStatsCreatorTests(unittest.TestCase):
    def test_counts_crossings_and_facilities_over_full_districts(self):
        districts = gpd.GeoDataFrame(
            {"district_id": ["01", "02", "03"], "district_name": ["A", "B", "C"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)],
            crs="EPSG:4326",
        )
        crossings = gpd.GeoDataFrame(
            {
                "display_role": ["marker", "segment", "marker", "marker"],
                "potential_candidate": [True, True, False, True],
            },
            geometry=[
                Point(0.75, 0.5),
                LineString([(0.7, 0.5), (0.8, 0.5)]),
                Point(1.5, 0.5),
                Point(1, 0.5),
            ],
            crs="EPSG:4326",
        )
        playgrounds = gpd.GeoDataFrame(
            {"potential_candidate": [False, True, None]},
            geometry=[Point(0.5, 0.5), box(1.2, 0.2, 1.8, 0.8), Point(1.7, 0.5)],
            crs="EPSG:4326",
        )
        gap_streets = gpd.GeoDataFrame(
            {"osm_id": [100, 101, 102], "feature_type": [
                "Potenzial durch Lückenschluss",
                "Potenzial durch mehrere Faktoren",
                "Potenzial durch Lückenschluss",
            ]},
            geometry=[
                LineString([(0.2, 0.5), (0.8, 0.5)]),
                LineString([(1.2, 0.5), (1.8, 0.5)]),
                LineString([(1, 0.2), (1, 0.8)]),
            ],
            crs="EPSG:4326",
        )
        streets = gpd.GeoDataFrame(
            geometry=[LineString([(0.5, 0.4), (0.5, 0.6)]), LineString([(1.3, 0.2), (1.3, 0.8)])],
            crs="EPSG:4326",
        )

        result = DistrictStatsCreator.create(
            districts, crossings, streets, {"playgrounds": playgrounds}, gap_streets,
            conditional_gap_street_ids={101},
        )

        self.assertEqual(result.crossing_total.tolist(), [2, 1, 0])
        self.assertEqual(result.crossing_potential.tolist(), [2, 0, 0])
        self.assertEqual(result.crossing_potential_pct.iloc[:2].tolist(), [100.0, 0.0])
        self.assertTrue(result.crossing_potential_pct.isna().iloc[2])
        self.assertEqual(result.playgrounds_total.tolist(), [1, 1, 0])
        self.assertEqual(result.playgrounds_potential.tolist(), [0, 1, 0])
        self.assertEqual(result.playgrounds_potential_pct.iloc[:2].tolist(), [0.0, 100.0])
        self.assertTrue(result.playgrounds_potential_pct.isna().iloc[2])
        self.assertEqual(result.playgrounds.tolist(), [1, 1, 0])
        self.assertEqual(result.playground_potential.tolist(), [0, 1, 0])
        self.assertEqual(result.playground_potential_pct.iloc[:2].tolist(), [0.0, 100.0])
        self.assertEqual(result.gap_potential.tolist(), [2, 1, 0])
        self.assertEqual(result.gap_conditional_potential.tolist(), [0, 1, 0])
        self.assertEqual(result.gap_direct_potential.tolist(), [2, 0, 0])
        self.assertEqual(result.all_types_total.tolist(), [3, 2, 0])
        self.assertEqual(result.all_types_potential.tolist(), [2, 1, 0])
        self.assertEqual(result.all_types_realized.tolist(), [1, 1, 0])
        self.assertEqual(result.realized_potential_pct_total.iloc[:2].tolist(), [33.3, 50.0])
        self.assertTrue(result.realized_potential_pct_total.isna().iloc[2])
        self.assertEqual(result.hospitals_total.tolist(), [0, 0, 0])
        for layer in ("crossing", *DistrictStatsCreator.FACILITY_LAYERS):
            for metric in ("total", "potential", "potential_pct"):
                self.assertIn(f"{layer}_{metric}", result.columns)
        self.assertEqual(result.geometry.iloc[0].bounds, (0, 0, 1, 1))
        self.assertNotIn("analysis_scope", result.columns)

    def test_playground_distance_uses_polygon_boundary_and_20_meter_cutoff(self):
        districts = gpd.GeoDataFrame(
            {"district_id": ["01"], "district_name": ["A"]},
            geometry=[box(-100, -100, 100, 100)], crs="EPSG:25832",
        )
        crossings = gpd.GeoDataFrame(
            {"display_role": [], "potential_candidate": []}, geometry=[], crs="EPSG:25832",
        )
        playgrounds = gpd.GeoDataFrame(
            {"potential_candidate": [True, False, False]},
            geometry=[Point(19, 0), Point(21, 0), box(15, 30, 55, 60)],
            crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            geometry=[LineString([(0, -10), (0, 70)])], crs="EPSG:25832",
        )

        result = DistrictStatsCreator.create(districts, crossings, streets, {"playgrounds": playgrounds})

        self.assertEqual(result.playgrounds_total.iloc[0], 2)
        self.assertEqual(result.playgrounds_potential.iloc[0], 1)
        self.assertEqual(result.playground_potential_pct.iloc[0], 50.0)

    def test_unverified_disability_facilities_are_not_counted_as_covered(self):
        districts = gpd.GeoDataFrame(
            {"district_id": ["01"], "district_name": ["A"]},
            geometry=[box(0, 0, 1, 1)], crs="EPSG:4326",
        )
        crossings = gpd.GeoDataFrame(
            {"display_role": [], "potential_candidate": []}, geometry=[], crs="EPSG:4326",
        )
        disability = gpd.GeoDataFrame(
            {"facility_status": ["confirmed_disabled", "target_group_unknown"],
             "potential_candidate": [True, False]},
            geometry=[Point(0.2, 0.2), Point(0.4, 0.4)], crs="EPSG:4326",
        )
        streets = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

        result = DistrictStatsCreator.create(
            districts, crossings, streets, {"disability_facilities": disability}
        )

        self.assertEqual(result.disability_facilities_total.iloc[0], 1)
        self.assertEqual(result.disability_facilities_potential.iloc[0], 1)


if __name__ == "__main__":
    unittest.main()
