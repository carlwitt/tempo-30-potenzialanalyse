import unittest
import json

import geopandas as gpd
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

    def test_one_future_anchor_adds_conditional_gap(self):
        streets = self._streets(["30", "50", "50"])
        potentials = {"playgrounds": PotentialCalculationResult([30], [1], [(1, 30)])}

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertIn(20, result.street_ids)
        self.assertEqual(result.conditional_gap_dependencies[20], [[("playgrounds", 30)]])
        self.assertNotIn(30, result.conditional_gap_dependencies)
        self.assertNotIn(20, result.direct_gap_lengths_m)

    def test_existing_conditional_speed_is_not_a_future_dependency(self):
        streets = self._streets(["30", "50", "50"])
        streets.loc[streets.osm_id == 30, "conditional_speed"] = "30"

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets)

        self.assertIn(20, result.street_ids)
        self.assertNotIn(20, result.conditional_gap_dependencies)
        self.assertEqual(result.direct_gap_lengths_m[20], 100.0)

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

    def test_two_future_anchors_keep_and_or_logic(self):
        streets = self._streets(["50", "50", "50"])
        potentials = {
            "educational_buildings": PotentialCalculationResult([10], [1], [(1, 10)]),
            "playgrounds": PotentialCalculationResult([10], [2], [(2, 10)]),
            "zebra": PotentialCalculationResult([30], [3], [(3, 30)]),
        }

        result = Tempo50GapPotential.find_all_tempo_50_gaps(streets, potentials)

        self.assertEqual(result.conditional_gap_dependencies[20], [
            [("educational_buildings", 10), ("playgrounds", 10)],
            [("zebra", 30)],
        ])

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
        self.assertIn("Tempo-50-Abschnitt einschließlich erforderlichem Anschluss: ca. 140,0 m", popup)
        self.assertIn("Länge der Lücke nach Anordnung: ca. 100,0 m", popup)
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
        self.assertIn("Länge zwischen bestehenden Tempo-30-Anschlüssen: ca. 100,0 m",
                      rendered.description.iloc[0])
        self.assertNotIn("erforderlichem Anschluss", rendered.description.iloc[0])

    def test_unnamed_anchor_uses_readable_fallback(self):
        option = {"potential_type": "zebra", "anchor_street_osm_id": 30,
                  "source_objects": [{"name": "Zebrastreifen",
                                      "osm_url": "https://www.openstreetmap.org/node/7"}]}

        _, sentence = ConditionalGapMetadata._option_sentence(option, {30: float("nan")})

        self.assertIn("auf dem Straßenabschnitt [[https://www.openstreetmap.org/way/30|OSM-Abschnitt 30]]", sentence)


if __name__ == "__main__":
    unittest.main()
