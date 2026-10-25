"""A 50 km/h road may already have a conditional Tempo-30 rule. Check parsing
and popup text so conditions survive and unsupported open potential is
excluded.
"""

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from DataOutput.GeoJsonCreator import GeoJsonCreator
from DataOutput.PotentialStreetConsolidation import PotentialStreetConsolidation
from DataOutput.SpeedLimitDescription import SpeedLimitDescription
from DataRetrieval.SegmentRetrieval import create_gdf_entry, has_conditional_tempo_30
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult
from PotentialCalculation.ProximityPotential import ProximityPotential


class SpeedLimitDescriptionTests(unittest.TestCase):
    @staticmethod
    def street(osm_id=1062572008, conditional="30 @ (Mo-Fr 07:00-17:00)"):
        return create_gdf_entry(
            {"id": osm_id}, "tertiary",
            [(13.599, 52.5189), (13.601, 52.5189)],
            {"highway": "tertiary", "name": "Wernerstraße", "maxspeed": "50",
             "maxspeed:conditional": conditional},
        )

    def test_both_reported_osm_ways_show_base_and_conditional_speed_in_popup(self):
        for osm_id in (1062572008, 1432745157):
            with self.subTest(osm_id=osm_id):
                streets = gpd.GeoDataFrame([self.street(osm_id)], crs="EPSG:4326")
                segments = FacilityStreetSegments.create(streets, {}, {})
                result = FacilityStreetSegments.annotate_potential_streets(streets, segments)
                self.assertEqual(result.description.iloc[0], (
                    f"Straße: [[https://www.openstreetmap.org/way/{osm_id}|Wernerstraße]]\n\n"
                    "Höchstgeschwindigkeit: 50 km/h\n\n"
                    "Bedingte Höchstgeschwindigkeit: 30 km/h (Mo-Fr 07:00-17:00)"
                ))
                self.assertEqual(streets.conditional_speed.iloc[0], "30")
                self.assertNotIn("description", streets)

    def test_multiple_rules_survive_when_simple_parser_cannot_parse_them(self):
        raw = "30 @ (Mo-Fr 07:00-17:00); 20 @ (Sa 08:00-12:00)"
        street = self.street(conditional=raw)

        self.assertEqual(street["conditional_speed"], "30")
        self.assertEqual(street["maxspeed_conditional_tag"], raw)
        popup = SpeedLimitDescription.describe(street)
        self.assertIn("30 km/h (Mo-Fr 07:00-17:00); 20 km/h (Sa 08:00-12:00)", popup)

    def test_unparsed_conditional_30_does_not_create_facility_potential(self):
        for raw in (
            "30 @ (Mo-Fr 06:00-09:00,16:00-19:00)",
            "30 @ (Mo - Fr 06:00 - 18:00)",
            "50 @ (Mo-Fr 09:00-17:00); 30 @ (Sa 09:00-17:00)",
        ):
            with self.subTest(raw=raw):
                street = gpd.GeoDataFrame([self.street(conditional=raw)], crs="EPSG:4326")
                feature = gpd.GeoDataFrame(
                    {"osm_id": [1]}, geometry=[Point(13.6, 52.5189)], crs="EPSG:4326",
                )
                self.assertEqual(street.conditional_speed.iloc[0], "30")
                self.assertEqual(
                    ProximityPotential.find_tempo50_segments_near_features(street, feature).street_ids,
                    [],
                )

        self.assertFalse(has_conditional_tempo_30("130 @ (Mo-Fr); 50 @ (30:00-31:00)"))

    def test_special_conditions_are_not_discarded_or_reinterpreted(self):
        for raw in ("40 @ (wet)", "30 @ (Mo-Fr 07:00-17:00; PH off)", "unknown condition"):
            with self.subTest(raw=raw):
                street = self.street(conditional=raw)
                popup = SpeedLimitDescription.describe(street)
                self.assertEqual(street["maxspeed_conditional_tag"], raw)
                self.assertIn(raw.split("@")[-1].strip(), popup)

    def test_legacy_split_fields_are_displayed_without_raw_tag(self):
        street = self.street()
        del street["maxspeed_conditional_tag"]

        self.assertIn(
            "Bedingte Höchstgeschwindigkeit: 30 km/h (Mo-Fr 07:00-17:00)",
            SpeedLimitDescription.describe(street),
        )

    def test_null_conditional_fields_do_not_create_empty_or_nan_lines(self):
        for missing in (None, float("nan"), pd.NA, ""):
            with self.subTest(missing=missing):
                street = {"maxspeed_class": "50", "maxspeed_conditional_tag": missing,
                          "conditional_speed": missing}
                self.assertEqual(SpeedLimitDescription.describe(street), "Höchstgeschwindigkeit: 50 km/h")

    def test_non_numeric_base_limits_are_not_labelled_kmh(self):
        for value, expected in (("walk", "Schrittgeschwindigkeit"), ("30_Zone", "Tempo-30-Zone"),
                                ("Keine Daten", "Keine Daten"), ("20", "20 km/h")):
            with self.subTest(value=value):
                self.assertEqual(
                    SpeedLimitDescription.describe({"maxspeed_class": value}),
                    f"Höchstgeschwindigkeit: {expected}",
                )

    def test_missing_condition_is_explicitly_reported(self):
        self.assertIn(
            "30 km/h (Bedingung nicht erfasst)",
            SpeedLimitDescription.describe({"maxspeed_class": "50", "conditional_speed": "30"}),
        )

    def test_merged_gap_popups_do_not_inherit_another_ways_conditions(self):
        streets = gpd.GeoDataFrame(
            [self.street(1, "40 @ (wet)"), self.street(2, "20 @ (snow)")],
            crs="EPSG:4326",
        )
        streets.loc[1, "geometry"] = LineString([(13.601, 52.5189), (13.603, 52.5189)])
        streets["is_conditional_gap"] = True
        streets["gap_required_potentials"] = [[], []]

        result = PotentialStreetConsolidation.consolidate_conditional_gaps(streets, streets)

        self.assertEqual(result.source_osm_ids.tolist(), [[1], [2]])
        segments = FacilityStreetSegments.create(streets, {}, {})
        popups = FacilityStreetSegments.annotate_potential_streets(result, segments)
        self.assertIn("40 km/h (wet)", popups.description.iloc[0])
        self.assertNotIn("snow", popups.description.iloc[0])
        self.assertIn("20 km/h (snow)", popups.description.iloc[1])

    def test_geojson_exports_preserve_conditions_and_render_street_popups(self):
        streets = gpd.GeoDataFrame(
            [self.street(osm_id) for osm_id in (1062572008, 1432745157)], crs="EPSG:4326",
        )
        streets.loc[1, "geometry"] = LineString([(13.601, 52.5189), (13.603, 52.5189)])
        potentials = streets.assign(feature_type="T30_Potenzial_Zebrastreifen")
        plain = self.street(42, conditional=None)
        plain["geometry"] = LineString([(13.61, 52.5189), (13.612, 52.5189)])
        streets = gpd.GeoDataFrame([*streets.to_dict("records"), plain], crs=streets.crs)
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [True], "street": ["Wernerstraße"]},
            geometry=[Point(13.5999, 52.5189)], crs=streets.crs,
        )
        playgrounds = gpd.GeoDataFrame(
            columns=[
                "osm_id", "element_type", "osm_node_ids", "osm_url", "name",
                "official_name", "alt_name", "short_name", "amenity", "healthcare",
                "social_facility", "social_facility_for", "potential_candidate", "street",
                "housenumber", "website", "operator", "geometry",
            ], geometry="geometry", crs=streets.crs,
        )

        all_ids = {1062572008, 1432745157}
        with tempfile.TemporaryDirectory() as directory:
            for conditional_ids in (set(), {1062572008}, all_ids):
                with self.subTest(conditional_ids=conditional_ids):
                    gap = PotentialCalculationResult(
                        street_ids=list(all_ids),
                        conditional_gap_dependencies={
                            osm_id: [[("playgrounds", 42)]] for osm_id in conditional_ids
                        },
                        direct_gap_lengths_m={osm_id: 100.0 for osm_id in all_ids - conditional_ids},
                    )
                    GeoJsonCreator.create_geojson_layer_files(
                        directory, potentials, streets, zebras, {"playgrounds": playgrounds},
                        potential_results={"gap": gap},
                    )
                    layer_ids = {
                        "potential_streets": all_ids - conditional_ids,
                        "conditional_gap_streets": conditional_ids,
                        "streets_and_limit": all_ids | {42},
                    }
                    for layer, expected_ids in layer_ids.items():
                        data = json.loads((Path(directory) / f"{layer}.geojson").read_text())
                        self.assertEqual(data["type"], "FeatureCollection")
                        exported_ids = {
                            osm_id for feature in data["features"]
                            for osm_id in feature["properties"].get(
                                "source_osm_ids", [feature["properties"]["osm_id"]]
                            )
                        }
                        self.assertEqual(exported_ids, expected_ids)
                        for feature in data["features"]:
                            props = feature["properties"]
                            self.assertIn("Höchstgeschwindigkeit: 50 km/h", props["description"])
                            if props["osm_id"] == 42:
                                self.assertNotIn("Bedingte Höchstgeschwindigkeit", props["description"])
                                continue
                            if layer in {"potential_streets", "conditional_gap_streets"}:
                                self.assertIn("Potenzialgrund:", props["description"])
                            self.assertIn("30 km/h (Mo-Fr 07:00-17:00)", props["description"])
                            self.assertEqual(props["maxspeed_conditional_tag"], "30 @ (Mo-Fr 07:00-17:00)")
                            self.assertEqual(props["conditional_speed"], "30")
                            self.assertEqual(props["cond_speed_days"], "Mo-Fr")
                            self.assertEqual(props["cond_speed_starttime"], "07:00")
                            self.assertEqual(props["cond_speed_endtime"], "17:00")
                            if layer == "conditional_gap_streets":
                                self.assertEqual(props["gap_role"], "gap")
                                self.assertIs(props["is_conditional_gap"], True)
                                self.assertIn("Bedingter Lückenschluss", props["description"])
                                self.assertIn("https://www.openstreetmap.org/way/42", props["description"])
                                self.assertNotIn("einschließlich erforderlichem Anschluss", props["description"])
                                self.assertNotIn("Länge der Lücke nach Anordnung", props["description"])
                                self.assertNotIn("OSM-Näherung", props["description"])
                            elif layer == "potential_streets":
                                self.assertIs(props["is_conditional_gap"], False)
                                self.assertIn("Direkter Lückenschluss", props["description"])
            self.assertEqual(streets.maxspeed_class.tolist(), ["50", "50", "50"])


if __name__ == "__main__":
    unittest.main()
