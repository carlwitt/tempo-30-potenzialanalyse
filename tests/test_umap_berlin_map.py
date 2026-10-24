import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uMapFrontend import build_berlin_map


class BerlinUMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup = json.loads(build_berlin_map.BACKUP.read_text(encoding="utf-8"))
        cls.generated = json.loads(build_berlin_map.OUTPUT.read_text(encoding="utf-8"))

    @staticmethod
    def leaves(layers):
        for layer in layers:
            if "layers" in layer:
                yield from BerlinUMapTests.leaves(layer["layers"])
            else:
                yield layer

    def test_output_is_reproducible_and_backup_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "berlin.umap"
            with patch.object(build_berlin_map, "OUTPUT", target):
                self.assertEqual(build_berlin_map.build(), self.generated)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.generated)

        self.assertEqual(self.generated["properties"]["center"], self.backup["properties"]["center"])
        self.assertEqual(self.generated["uri"], self.backup["uri"])
        self.assertEqual(self.generated["layers"][0]["layers"][0]["properties"]["name"], "Spielplätze")

    def test_all_berlin_exports_are_remote_layers_without_embedded_features(self):
        layers = list(self.leaves(self.generated["layers"]))
        urls = {layer["properties"]["remoteData"]["url"] for layer in layers}
        filenames = {
            "playgrounds.geojson", "zebra.geojson", "disability_facilities.geojson",
            "hospitals.geojson", "educational_buildings.geojson", "elderly_homes.geojson",
            "potential_streets.geojson", "facility_street_segments.geojson",
            "facility_covered_street_segments.geojson", "district_stats.geojson",
            "disability_facilities_review.geojson", "accidents.geojson",
        }

        self.assertEqual(len(layers), 12)
        self.assertEqual({url.rsplit("/", 1)[-1] for url in urls}, filenames)
        self.assertTrue(all(not layer["features"] for layer in layers))
        self.assertTrue(all(url.startswith(build_berlin_map.REMOTE_BASE + "/") for url in urls))
        self.assertEqual(len(self.generated["layers"]), 4)
        self.assertFalse(any(layer["properties"]["name"] == "OSM-Kontext und Prüffälle"
                             for layer in self.generated["layers"]))

    def test_accidents_are_one_weighted_heat_layer(self):
        heat = self.generated["layers"][3]["properties"]
        self.assertEqual(heat["type"], "Heat")
        self.assertEqual(heat["heat"]["intensityProperty"], "heat_weight")
        self.assertEqual(heat["remoteData"]["url"].rsplit("/", 1)[-1], "accidents.geojson")
        self.assertFalse(heat["displayOnLoad"])

    def test_district_metric_fields_are_numeric_and_not_categorized(self):
        props = self.generated["layers"][2]["properties"]
        types = {field["key"]: field["type"] for field in props["fields"]}

        self.assertEqual(props["type"], "Choropleth")
        self.assertEqual(types["realized_potential_pct_total"], "Number")
        self.assertEqual(types["gap_direct_potential"], "Number")
        self.assertEqual(types["gap_conditional_potential"], "Number")
        self.assertNotIn("analysis_scope", types)
        self.assertNotIn("categorized", props)

    def test_facility_layers_use_compact_popup_and_legal_descriptions(self):
        layers = list(self.leaves(self.generated["layers"]))
        facility_names = {
            "Spielplätze", "Einrichtungen für Menschen mit Behinderung",
            "Krankenhäuser", "Schulen und Kitas", "Senioren- und Pflegeeinrichtungen",
            "Behinderteneinrichtungen – ungeklärt",
        }
        for layer in layers:
            props = layer["properties"]
            if props["name"] in facility_names:
                self.assertEqual(props["popupContentTemplate"], "{popup_content}")
                self.assertIn({"key": "popup_content", "type": "Text"}, props["fields"])

        indicators = {layer["properties"]["name"]: layer["properties"]
                      for layer in self.generated["layers"][0]["layers"]}
        for name in facility_names - {"Behinderteneinrichtungen – ungeklärt"}:
            self.assertIn("§ 45 Abs. 9 Satz 4 Nr. 6 StVO", indicators[name]["description"])
        self.assertIn("werden aber in diesem Einrichtungs-Layer nicht erfasst",
                      indicators["Schulen und Kitas"]["description"])
        self.assertIn("Nr. 6 StVO", indicators["Zebrastreifen"]["description"])

    def test_zebra_marker_matches_backup_while_segments_remain_visible(self):
        def zebra_properties(map_data):
            return next(layer["properties"] for layer in map_data["layers"][0]["layers"]
                        if layer["properties"]["name"] == "Zebrastreifen")

        original = zebra_properties(self.backup)
        generated = zebra_properties(self.generated)
        for key in ("iconUrl", "iconOpacity", "color", "rules", "fill"):
            self.assertEqual(generated[key], original[key], key)
        self.assertNotIn("iconClass", generated)
        self.assertTrue(generated["stroke"])
        self.assertEqual(generated["weight"], 4)
        self.assertEqual(generated["remoteData"]["url"], original["remoteData"]["url"])

    def test_street_layer_uses_section_name_and_numeric_gap_lengths(self):
        potential = self.generated["layers"][1]["layers"][0]["properties"]
        types = {field["key"]: field["type"] for field in potential["fields"]}

        self.assertEqual(potential["name"], "Straßenabschnitte mit Tempo-30-Potenzial")
        self.assertEqual(types["gap_length_current_m"], "Number")
        self.assertEqual(types["gap_length_after_m"], "Number")


if __name__ == "__main__":
    unittest.main()
