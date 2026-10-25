"""A gap can reach two existing slow roads or depend on one future facility
measure. Check anchor independence, conditional speeds and traversed roads so
the result states which connection exists today.
"""

import unittest
import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from DataOutput.ConditionalGapMetadata import ConditionalGapMetadata
from PotentialCalculation.GapPotential import Tempo50GapPotential
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


class ConditionalGapTests(unittest.TestCase):
    @staticmethod
    def _streets(classes):
        x0, y = 390000, 5820000
        records = [
            (10, -100, 0),
            (20, 0, 100),
            (30, 100, 200),
        ]
        return gpd.GeoDataFrame(
            {
                "osm_id": [road[0] for road in records],
                "name": ["Teststraße"] * len(records),
                "maxspeed_class": classes,
                "conditional_speed": [None] * len(records),
            },
            geometry=[LineString([(x0 + start, y), (x0 + end, y)]) for _, start, end in records],
            crs="EPSG:25832",
        )

    def test_direct_gap_remains_direct_without_future_dependencies(self):
        streets = self._streets(["30", "50", "30"])

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)
        self.assertEqual(result.direct_gap_lengths_m[20], 100.0)
        self.assertEqual(result.direct_gap_existing_anchors[20], [10, 30])

    def test_living_street_and_zone_without_numeric_maxspeed_are_covered_anchors(self):
        streets = self._streets(["walk", "50", "30_Zone"])

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertIn(20, result.street_ids)
        self.assertEqual(result.direct_gap_lengths_m[20], 100.0)

    def test_one_existing_street_touching_both_ends_is_not_two_anchors(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20], "name": ["Teststraße"] * 2,
             "maxspeed_class": ["30", "50"], "conditional_speed": [None, None]},
            geometry=[
                LineString([(x0, y), (x0 - 10, y), (x0 - 10, y + 10),
                            (x0 + 110, y + 10), (x0 + 110, y), (x0 + 100, y)]),
                LineString([(x0, y), (x0 + 100, y)]),
            ], crs="EPSG:25832",
        )

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertNotIn(20, result.street_ids)

    def test_one_future_anchor_adds_conditional_gap(self):
        streets = self._streets(["30", "50", "50"])
        potentials = {"playgrounds": PotentialCalculationResult([30], [1], [(1, 30)])}

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertIn(20, result.street_ids)
        self.assertEqual(result.conditional_gap_dependencies[20], [[("playgrounds", 30)]])
        self.assertEqual(result.conditional_gap_existing_anchors[20], [10])
        self.assertNotIn(30, result.conditional_gap_dependencies)
        self.assertNotIn(20, result.direct_gap_lengths_m)

    def test_time_dependent_speed_is_not_an_existing_anchor(self):
        streets = self._streets(["30", "50", "50"])
        streets.loc[streets.osm_id == 30, "conditional_speed"] = "30"

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertNotIn(20, result.street_ids)

    def test_unknown_or_conditional_speed_cannot_bridge_gap_corridor(self):
        x0, y = 390000, 5820000
        for middle_class, middle_conditional in (("Keine Daten", None), ("50", "30")):
            with self.subTest(middle_class=middle_class, conditional=middle_conditional):
                streets = gpd.GeoDataFrame(
                    {"osm_id": [10, 20, 30, 40], "name": ["Teststraße"] * 4,
                     "maxspeed_class": ["30", "50", middle_class, "30"],
                     "conditional_speed": [None, None, middle_conditional, None]},
                    geometry=[LineString([(x0 + a, y), (x0 + b, y)])
                              for a, b in ((-100, 0), (0, 100), (100, 200), (200, 300))],
                    crs="EPSG:25832",
                )
                result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)
                self.assertNotIn(20, result.street_ids)

    def test_named_continuation_wins_over_straighter_cross_street(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20, 30, 40, 50],
             "name": ["Hauptstraße", "Hauptstraße", "Abzweig", "Hauptstraße", "Hauptstraße"],
             "maxspeed_class": ["30", "50", "Keine Daten", "50", "30"],
             "conditional_speed": [None] * 5},
            geometry=[LineString([(x0 + a, y + b), (x0 + c, y + d)]) for a, b, c, d in (
                (-100, 0, 0, 0), (0, 0, 100, 0), (100, 0, 200, 0),
                (100, 0, 200, 20), (200, 20, 300, 40),
            )], crs="EPSG:25832",
        )

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertIn(20, result.street_ids)
        self.assertEqual(result.direct_gap_existing_anchors[20], [10, 50])

    def test_existing_t30_beyond_future_anchor_keeps_gap_direct(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20, 30, 40], "name": ["Teststraße"] * 4,
             "maxspeed_class": ["30", "50", "50", "30"],
             "conditional_speed": [None] * 4},
            geometry=[LineString([(x0 + a, y), (x0 + b, y)]) for a, b in (
                (-100, 0), (0, 100), (100, 200), (200, 300)
            )],
            crs="EPSG:25832",
        )
        potentials = {"playgrounds": PotentialCalculationResult([30], [1], [(1, 30)])}

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)
        self.assertEqual(result.direct_gap_lengths_m[20], 200.0)

    def test_too_short_future_corridor_does_not_hide_valid_direct_gap(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [10, 20, 30, 40], "name": ["Teststraße"] * 4,
             "maxspeed_class": ["30", "50", "50", "30"],
             "conditional_speed": [None] * 4},
            geometry=[LineString([(x0 + a, y), (x0 + b, y)]) for a, b in (
                (-100, 0), (0, 20), (20, 40), (40, 140)
            )],
            crs="EPSG:25832",
        )
        potentials = {"playgrounds": PotentialCalculationResult([30], [1], [(1, 30)])}

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)

    def test_two_future_anchors_without_existing_t30_are_rejected(self):
        streets = self._streets(["50", "50", "50"])
        potentials = {
            "educational_buildings": PotentialCalculationResult([10], [1], [(1, 10)]),
            "playgrounds": PotentialCalculationResult([10], [2], [(2, 10)]),
            "zebra": PotentialCalculationResult([30], [3], [(3, 30)]),
        }

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertNotIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)
        prepared = Tempo50GapPotential.prepare_gdf(streets)
        found, groups = Tempo50GapPotential.evaluate_gap(
            prepared.loc[prepared.osm_id == 20].iloc[0], prepared,
            potential_types_by_street={10: {"playgrounds"}, 30: {"zebra"}},
        )
        self.assertFalse(found)
        self.assertEqual(groups, [])

    def test_one_future_end_keeps_alternative_measures_and_works_in_both_directions(self):
        for classes, anchor in ((["30", "50", "50"], 30), (["50", "50", "30"], 10)):
            with self.subTest(classes=classes):
                streets = self._streets(classes)
                potentials = {
                    "playgrounds": PotentialCalculationResult([anchor]),
                    "educational_buildings": PotentialCalculationResult([anchor]),
                }
                result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)
                self.assertEqual(result.conditional_gap_dependencies[20], [[
                    ("educational_buildings", anchor), ("playgrounds", anchor),
                ]])

    def test_existing_anchor_beyond_a_potential_allows_only_one_future_end(self):
        x0, y = 390000, 5820000
        for existing_side in ("left", "right"):
            with self.subTest(existing_side=existing_side):
                classes = ["30", "50", "50", "50"] if existing_side == "left" else ["50", "50", "50", "30"]
                streets = gpd.GeoDataFrame(
                    {"osm_id": [5, 10, 20, 30], "name": ["Teststraße"] * 4,
                     "maxspeed_class": classes, "conditional_speed": [None] * 4},
                    geometry=[LineString([(x0 + a, y), (x0 + b, y)])
                              for a, b in ((-200, -100), (-100, 0), (0, 100), (100, 200))],
                    crs="EPSG:25832",
                )
                # Use the middle way between two tagged future anchors.
                middle = 20 if existing_side == "left" else 10
                anchors = [10, 30] if existing_side == "left" else [5, 20]
                result = Tempo50GapPotential.find_all_tempo_50_gaps(
                    streets, {"playgrounds": PotentialCalculationResult(anchors)},
                )
                expected_anchor = 30 if existing_side == "left" else 5
                self.assertEqual(result.conditional_gap_dependencies[middle],
                                 [[("playgrounds", expected_anchor)]])
                self.assertEqual(
                    result.conditional_gap_existing_anchors[middle],
                    [5] if existing_side == "left" else [30],
                )
                self.assertEqual(
                    result.gap_corridor_ways[middle],
                    [10] if existing_side == "left" else [20],
                )

    def test_time_dependent_speed_cannot_anchor_a_conditional_gap(self):
        streets = self._streets(["50", "50", "50"])
        streets.loc[streets.osm_id == 10, "conditional_speed"] = "30"
        result = Tempo50GapPotential.find_all_tempo_50_gaps(
            streets, {"playgrounds": PotentialCalculationResult([30])},
        )
        self.assertNotIn(20, result.street_ids)

    def test_existing_t30_beyond_both_potential_anchors_keeps_gap_direct(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [5, 10, 20, 30, 40], "name": ["Teststraße"] * 5,
             "maxspeed_class": ["30", "50", "50", "50", "30"],
             "conditional_speed": [None] * 5},
            geometry=[LineString([(x0 + a, y), (x0 + b, y)]) for a, b in
                      ((-200, -100), (-100, 0), (0, 100), (100, 200), (200, 300))],
            crs="EPSG:25832",
        )
        result = Tempo50GapPotential.find_all_tempo_50_gaps(
            streets, {"playgrounds": PotentialCalculationResult([10, 30])},
        )
        self.assertIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)
        self.assertEqual(result.direct_gap_lengths_m[20], 300.0)

    def test_future_anchor_does_not_compensate_for_missing_opposite_connection(self):
        streets = self._streets(["50", "50", "50"])
        result = Tempo50GapPotential.find_all_tempo_50_gaps(
            streets, {"playgrounds": PotentialCalculationResult([30])},
        )
        self.assertNotIn(20, result.street_ids)

    def test_one_future_end_still_obeys_corridor_length_limits(self):
        streets = Tempo50GapPotential.prepare_gdf(self._streets(["30", "50", "50"]))
        middle = streets.loc[streets.osm_id == 20].iloc[0]
        for length, expected in ((29.9, False), (30.0, True), (500.0, True), (500.1, False)):
            with self.subTest(length=length):
                candidate = middle.copy()
                candidate["length_m"] = length
                found, groups, _ = Tempo50GapPotential._evaluate_gap_with_length(
                    candidate, streets, potential_types_by_street={30: {"playgrounds"}},
                )
                self.assertEqual(found, expected)
                self.assertEqual(len(groups), 1 if expected else 0)

    def test_two_future_ends_are_not_rescued_by_existing_t30_beyond_length_limit(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [5, 10, 20, 30], "name": ["Teststraße"] * 4,
             "maxspeed_class": ["30", "50", "50", "50"],
             "conditional_speed": [None] * 4},
            geometry=[LineString([(x0 + a, y), (x0 + b, y)])
                      for a, b in ((-600, -501), (-501, 0), (0, 100), (100, 200))],
            crs="EPSG:25832",
        )
        result = Tempo50GapPotential.find_all_tempo_50_gaps(
            streets, {"playgrounds": PotentialCalculationResult([10, 30])},
        )
        self.assertNotIn(20, result.street_ids)

    def test_gap_cannot_depend_on_another_gap(self):
        streets = self._streets(["30", "50", "50"])
        result = Tempo50GapPotential.find_all_tempo_50_gaps(
            streets, {"gap": PotentialCalculationResult([30])},
        )
        self.assertNotIn(20, result.street_ids)

    def test_export_rejects_dependencies_at_both_ends(self):
        streets = self._streets(["50", "50", "50"])
        result = PotentialCalculationResult(
            [20], conditional_gap_dependencies={20: [[("zebra", 10)], [("playgrounds", 30)]]},
        )
        with self.assertRaisesRegex(ValueError, "more than one future T30 end"):
            ConditionalGapMetadata.annotate(streets, result, {}, {})

    def test_popup_links_to_required_source_objects_and_sets_boolean(self):
        streets = self._streets(["30", "50", "50"])
        streets = streets.loc[streets.osm_id == 20].assign(description="Straße: Teststraße")
        gap_result = PotentialCalculationResult(
            [20], conditional_gap_dependencies={20: [[("playgrounds", 30)]]}
        )
        potentials = {
            "playgrounds": PotentialCalculationResult([30], [7], [(7, 30)])
        }
        playgrounds = gpd.GeoDataFrame(
            {"osm_id": [7], "element_type": ["way"], "name": ["Spielplatz am Park"],
             "osm_url": ["https://www.openstreetmap.org/way/7"]},
            geometry=[Point(390180, 5820005)], crs="EPSG:25832",
        )

        annotated = ConditionalGapMetadata.annotate(
            streets, gap_result, potentials, {"playgrounds": playgrounds}
        )
        annotated = ConditionalGapMetadata.render_popups(annotated, self._streets(["30", "50", "50"]))

        self.assertEqual(annotated.is_conditional_gap.tolist(), [True])
        self.assertEqual(annotated.gap_required_potential_types.tolist(), ["Spielplatz"])
        self.assertEqual(annotated.gap_required_street_osm_ids.tolist(), [[30]])
        self.assertIn("Spielplatz am Park", annotated.description.iloc[0])
        self.assertEqual(
            annotated.gap_required_potentials.iloc[0][0][0]["source_objects"][0]["osm_url"],
            "https://www.openstreetmap.org/way/7",
        )
        exported = json.loads(annotated.to_json())["features"][0]["properties"]
        self.assertIs(exported["is_conditional_gap"], True)
        self.assertEqual(exported["gap_required_potentials"][0][0]["potential_type"], "playgrounds")

    def test_conditional_popup_uses_one_source_link_and_named_anchor(self):
        streets = self._streets(["30", "50", "50"])
        potential = streets.loc[streets.osm_id == 20].assign(
            description="Straße: [[https://www.openstreetmap.org/way/20|Teststraße]]"
        )
        gap_result = PotentialCalculationResult(
            [20], conditional_gap_dependencies={20: [[("zebra", 30)]]}
        )
        zebras = gpd.GeoDataFrame(
            {"osm_id": [7, 8], "element_type": ["node", "way"],
             "name": [None, None],
             "osm_url": ["https://www.openstreetmap.org/node/7",
                         "https://www.openstreetmap.org/way/8"]},
            geometry=[Point(390200, 5820000), Point(390201, 5820000)], crs="EPSG:25832",
        )
        potentials = {"zebra": PotentialCalculationResult([30], [7, 8], [(7, 30), (8, 30)])}

        annotated = ConditionalGapMetadata.annotate(potential, gap_result, potentials, {"zebra": zebras})
        annotated["gap_length_with_prerequisites_m"] = 140.0
        annotated["gap_length_after_m"] = 100.0
        rendered = ConditionalGapMetadata.render_popups(annotated, streets)
        popup = rendered.description.iloc[0]

        self.assertIn("Lückenschluss zur [[https://www.openstreetmap.org/way/30|Teststraße]]", popup)
        self.assertIn("am [[https://www.openstreetmap.org/node/7|Zebrastreifen]]", popup)
        self.assertNotIn("https://www.openstreetmap.org/way/8", popup)
        self.assertNotIn("Tempo-50-Abschnitt einschließlich erforderlichem Anschluss", popup)
        self.assertNotIn("Länge der Lücke nach Anordnung", popup)
        self.assertNotIn("OSM-Näherung", popup)
        self.assertEqual(rendered.gap_length_with_prerequisites_m.iloc[0], 140.0)
        self.assertEqual(rendered.gap_length_after_m.iloc[0], 100.0)
        self.assertNotIn("Länge der Lücke aktuell", popup)
        self.assertIn("\n\n", popup)

    def test_direct_popup_only_uses_length_between_existing_tempo_30_anchors(self):
        streets = self._streets(["30", "50", "30"])
        potential = streets.loc[streets.osm_id == 20].assign(description="Straße: Teststraße")
        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        annotated = ConditionalGapMetadata.annotate(potential, result, {}, {})
        rendered = ConditionalGapMetadata.render_popups(annotated, streets)

        self.assertFalse(rendered.is_conditional_gap.iloc[0])
        self.assertEqual(rendered.gap_length_current_m.iloc[0], 100.0)
        self.assertIn("Direkter Lückenschluss: ca. 100,0 m",
                      rendered.description.iloc[0])
        self.assertIn("openstreetmap.org/way/10", rendered.description.iloc[0])
        self.assertIn("openstreetmap.org/way/30", rendered.description.iloc[0])
        self.assertNotIn("erforderlichem Anschluss", rendered.description.iloc[0])

        rendered["source_osm_ids"] = [[20]]
        layer = ConditionalGapMetadata.add_connection_context(
            rendered, streets, gap_kind="direkte"
        )
        anchors = layer.loc[layer.gap_role.eq("existing_connection")]
        self.assertEqual(set(anchors.osm_id), {10, 30})
        self.assertTrue(all(anchors.description.str.contains("Zugehörige direkte Lückenschlüsse")))

    def test_unnamed_anchor_uses_readable_fallback(self):
        option = {"potential_type": "zebra", "anchor_street_osm_id": 30,
                  "source_objects": [{"name": "Zebrastreifen",
                                      "osm_url": "https://www.openstreetmap.org/node/7"}]}

        _, sentence = ConditionalGapMetadata._option_sentence(option, {30: float("nan")})

        self.assertIn("auf dem Straßenabschnitt [[https://www.openstreetmap.org/way/30|OSM-Abschnitt 30]]", sentence)

    def test_required_alternatives_remain_metadata_without_extra_lines(self):
        streets = self._streets(["50", "50", "60"])
        streets.loc[streets.osm_id == 30, "name"] = None
        gaps = streets.loc[streets.osm_id.isin([10, 20])].copy()
        gaps["source_osm_ids"] = [[10], [20]]
        gaps["gap_required_street_osm_ids"] = [[20, 30], [30]]
        gaps["is_conditional_gap"] = True
        original = gaps.copy()

        result = ConditionalGapMetadata.add_connection_context(gaps, streets.to_crs("EPSG:4326"))
        self.assertEqual(result.gap_role.tolist(), ["gap", "gap"])
        self.assertEqual(result.osm_id.tolist(), [10, 20])
        self.assertEqual(result.gap_required_street_osm_ids.tolist(), [[20, 30], [30]])
        self.assertTrue(result.target_speed_kmh.eq(30).all())
        self.assertTrue(result.is_conditional_gap.all())
        self.assertNotIn("gap_role", original)
        self.assertNotIn("gap_role", gaps)
        self.assertEqual(result.crs, streets.crs)

    def test_missing_required_connection_is_reported(self):
        streets = self._streets(["30", "50", "30"])
        gaps = streets.loc[streets.osm_id == 20].copy()
        gaps["source_osm_ids"] = [[20]]
        gaps["gap_required_street_osm_ids"] = [[999]]

        with self.assertRaisesRegex(ValueError, "Missing required connection streets:.*999"):
            ConditionalGapMetadata.add_connection_context(gaps, streets)

    def test_conditional_layer_shows_only_gap_and_existing_end(self):
        streets = self._streets(["30", "50", "50"])
        gap = streets.loc[streets.osm_id == 20].copy()
        result = PotentialCalculationResult(
            [20], conditional_gap_dependencies={20: [[("playgrounds", 30)]]},
            conditional_gap_existing_anchors={20: [10]},
        )
        annotated = ConditionalGapMetadata.annotate(gap, result, {}, {})
        annotated["source_osm_ids"] = [[20]]
        annotated["description"] = "Straße: Teststraße"
        rendered = ConditionalGapMetadata.render_popups(annotated, streets)
        layer = ConditionalGapMetadata.add_connection_context(rendered, streets)
        roles = {row.gap_role: row for _, row in layer.iterrows()}

        self.assertEqual(set(roles), {"gap", "existing_connection"})
        self.assertEqual(roles["existing_connection"].osm_id, 10)
        self.assertEqual(roles["existing_connection"].related_gap_osm_ids, [20])
        self.assertEqual(roles["existing_connection"].maxspeed_class, "30")
        self.assertFalse(roles["existing_connection"].is_conditional_gap)
        self.assertTrue(pd.isna(roles["existing_connection"].target_speed_kmh))
        self.assertIn("Bestehender Tempo-30-Anschluss", roles["gap"].description)
        self.assertIn("openstreetmap.org/way/30", roles["gap"].description)
        self.assertIn("Höchstgeschwindigkeit: 30 km/h", roles["existing_connection"].description)

    def test_time_dependent_speed_end_cannot_be_exported_as_existing_connection(self):
        streets = self._streets(["50", "50", "50"])
        streets.loc[streets.osm_id == 10, "conditional_speed"] = "30"
        gap = streets.loc[streets.osm_id == 20].copy()
        gap["source_osm_ids"] = [[20]]
        gap["gap_required_street_osm_ids"] = [[30]]
        gap["gap_existing_street_osm_ids"] = [[10]]
        with self.assertRaisesRegex(ValueError, "not permanently Tempo 30"):
            ConditionalGapMetadata.add_connection_context(gap, streets)

    def test_intermediate_way_is_displayed_between_gap_and_existing_end(self):
        x0, y = 390000, 5820000
        streets = gpd.GeoDataFrame(
            {"osm_id": [5, 10, 20, 30], "name": ["Teststraße"] * 4,
             "maxspeed_class": ["30", "50", "50", "50"],
             "conditional_speed": [None] * 4},
            geometry=[LineString([(x0 + a, y), (x0 + b, y)])
                      for a, b in ((-200, -100), (-100, 0), (0, 100), (100, 200))],
            crs="EPSG:25832",
        )
        potential = {"playgrounds": PotentialCalculationResult([30])}
        gap_result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potential)
        gap = streets.loc[streets.osm_id == 20].copy()
        annotated = ConditionalGapMetadata.annotate(gap, gap_result, potential, {})
        annotated["source_osm_ids"] = [[20]]
        annotated["description"] = "Straße: Teststraße"
        layer = ConditionalGapMetadata.add_connection_context(annotated, streets)
        by_role = {row.gap_role: row for _, row in layer.iterrows()}

        self.assertEqual(by_role["corridor_connection"].osm_id, 10)
        self.assertEqual(by_role["corridor_connection"].related_gap_osm_ids, [20])
        self.assertIn("Lückenschlusspotenzial", by_role["corridor_connection"].description)
        self.assertEqual(by_role["existing_connection"].osm_id, 5)
        self.assertAlmostEqual(
            by_role["corridor_connection"].geometry.distance(by_role["gap"].geometry), 0,
        )


if __name__ == "__main__":
    unittest.main()
