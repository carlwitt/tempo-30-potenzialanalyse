"""Check that one template produces an importable map for each area.

Building a new region by hand means configuring many remote layers.
Verify generated URLs, styles, descriptions and initial visibility so
the reusable builder produces a review map without repeating that setup.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from uMapFrontend import build_umap_configuration


HERE = Path(__file__).resolve().parents[1] / "uMapFrontend"
BACKUP = HERE / "umap_backup_tempo-30-potenziale-berlin.umap"
OUTPUT = HERE / "tempo-30-potenziale-berlin.umap"
REMOTE_BASE = "https://tempo-30.adfc-berlin.de/uMap"


class BerlinUMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup = json.loads(BACKUP.read_text(encoding="utf-8"))
        cls.generated = json.loads(OUTPUT.read_text(encoding="utf-8"))

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
            subprocess.run(
                ["sh", str(HERE / "build_berlin_map.sh"), "--output", str(target)],
                cwd=directory, env={**os.environ, "PYTHON": sys.executable}, check=True,
                capture_output=True, text=True,
            )
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.generated)

        self.assertEqual(self.generated["properties"]["center"], self.backup["properties"]["center"])
        self.assertEqual(self.generated["uri"], self.backup["uri"])
        self.assertEqual(self.generated["layers"][0]["layers"][0]["properties"]["name"], "Spielplätze")

    def test_all_berlin_exports_are_remote_layers_without_embedded_features(self):
        layers = list(self.leaves(self.generated["layers"]))
        urls = {layer["properties"]["remoteData"]["url"] for layer in layers}
        filenames = {
            "playgrounds_map.geojson", "zebra.geojson", "disability_facilities_map.geojson",
            "hospitals_map.geojson", "educational_buildings_map.geojson",
            "elderly_homes_map.geojson",
            "potential_streets_map.geojson",
            "conditional_gap_streets.geojson",
            "facility_covered_street_segments.geojson", "district_stats.geojson",
            "accidents.geojson",
        }

        self.assertEqual(len(layers), 11)
        self.assertEqual({url.rsplit("/", 1)[-1] for url in urls}, filenames)
        self.assertTrue(all(not layer["features"] for layer in layers))
        self.assertTrue(all(url.startswith(REMOTE_BASE + "/") for url in urls))
        self.assertEqual(len(self.generated["layers"]), 4)
        self.assertFalse(any(layer["properties"]["name"] == "OSM-Kontext und Prüffälle"
                             for layer in self.generated["layers"]))
        disability = next(layer["properties"] for layer in layers
                          if layer["properties"]["name"] == "Einrichtungen für Menschen mit Behinderung")
        self.assertEqual({rule["condition"] for rule in disability["rules"]}, {
            "potential_candidate=true",
        })
        self.assertNotIn("Orange markierte Objekte", disability["description"])
        self.assertNotIn("graue Objekte", disability["description"])

    def test_legacy_disability_review_styles_are_removed_from_template(self):
        indicators = json.loads(json.dumps(self.backup["layers"][0]))
        disability = next(layer["properties"] for layer in indicators["layers"]
                          if layer["properties"]["name"] == "Einrichtungen für Menschen mit Behinderung")
        for status in ("target_group_unknown", "different_target_group"):
            disability["rules"].append({
                "condition": f"facility_status={status}", "properties": {"color": "#999999"},
            })

        build_umap_configuration.complete_indicators(indicators)

        self.assertEqual({rule["condition"] for rule in disability["rules"]},
                         {"potential_candidate=true"})

    def test_yaml_contains_all_layer_descriptions_without_changing_text(self):
        with (HERE / "layer_descriptions.yaml").open(encoding="utf-8") as source:
            descriptions = yaml.safe_load(source)
        layers = self.generated["layers"] + list(self.leaves(self.generated["layers"]))
        checked = set()
        for layer in layers:
            props = layer["properties"]
            if "description" not in props:
                continue
            key = "Unfälle mit Personenschaden" if props.get("type") == "Heat" else props["name"]
            with self.subTest(layer=key):
                text = descriptions[key]
                self.assertIsInstance(text, str)
                self.assertEqual(text, text.strip())
                self.assertNotIn("\n", text)
                if key == "Unfälle mit Personenschaden":
                    text = text.format(area_name="Berlin", accident_start_year=2022)
                self.assertEqual(text, props["description"])
            checked.add(key)
        self.assertEqual(checked, set(descriptions))

    def test_generic_cli_replaces_all_remote_urls_and_area_metadata(self):
        with tempfile.TemporaryDirectory(prefix="umap configuration ") as directory:
            target = Path(directory) / "custom map.umap"
            subprocess.run(
                [sys.executable, str(HERE / "build_umap_configuration.py"),
                 "--backup", str(BACKUP), "--output", str(target),
                 "--remote-base", "https://example.org/potsdam/data/",
                 "--area-name", "Potsdam", "--map-name", "Tempo 30 Potsdam",
                 "--accident-start-year", "2023", "--accident-end-year", "2026"],
                check=True, capture_output=True, text=True,
            )
            generated = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(generated["properties"]["name"], "Tempo 30 Potsdam")
        for layer in self.leaves(generated["layers"]):
            self.assertTrue(layer["properties"]["remoteData"]["url"].startswith(
                "https://example.org/potsdam/data/"
            ))
        accident = generated["layers"][3]["properties"]
        self.assertEqual(accident["name"], "Unfälle mit Personenschaden 2023–2026")
        self.assertIn("in Potsdam seit 2023", accident["description"])
        self.assertNotIn("Berlin", accident["description"])
        self.assertEqual(generated["geometry"], self.backup["geometry"])

    def test_invalid_configuration_does_not_write_output_or_overwrite_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "map.umap"
            options = dict(
                backup=BACKUP, output=target, remote_base=REMOTE_BASE,
                area_name="Berlin", map_name="Test",
                accident_start_year=2022, accident_end_year=2025,
            )
            for overrides, message in (
                ({"accident_start_year": 2026}, "start year"),
                ({"remote_base": "data/"}, "absolute HTTP"),
                ({"output": BACKUP}, "overwrite"),
            ):
                with self.subTest(overrides=overrides):
                    with self.assertRaisesRegex(ValueError, message):
                        build_umap_configuration.build(**{**options, **overrides})
            self.assertFalse(target.exists())

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
        self.assertFalse(props["displayOnLoad"])
        self.assertEqual(types["realized_potential_pct_total"], "Number")
        self.assertEqual(types["gap_direct_potential"], "Number")
        self.assertEqual(types["gap_conditional_potential"], "Number")
        self.assertNotIn("analysis_scope", types)
        self.assertNotIn("categorized", props)

    def test_facility_layers_use_compact_popup_and_configured_descriptions(self):
        layers = list(self.leaves(self.generated["layers"]))
        facility_names = {
            "Spielplätze", "Einrichtungen für Menschen mit Behinderung",
            "Krankenhäuser", "Schulen und Kitas", "Senioren- und Pflegeeinrichtungen",
        }
        for layer in layers:
            props = layer["properties"]
            if props["name"] in facility_names:
                self.assertEqual(props["popupContentTemplate"], "{popup_content}")
                self.assertIn({"key": "popup_content", "type": "Text"}, props["fields"])
                self.assertTrue(props["remoteData"]["url"].endswith("_map.geojson"))
                self.assertFalse(props["displayOnLoad"])

        self.assertFalse(self.generated["layers"][0]["properties"]["displayOnLoad"])
        self.assertTrue(self.generated["layers"][1]["properties"]["displayOnLoad"])

        indicators = {layer["properties"]["name"]: layer["properties"]
                      for layer in self.generated["layers"][0]["layers"]}
        for name in facility_names:
            self.assertEqual(build_umap_configuration.LAYER_DESCRIPTIONS[name],
                             indicators[name]["description"])
        self.assertIn("werden aber in diesem Einrichtungs-Layer nicht erfasst",
                      indicators["Schulen und Kitas"]["description"])
        self.assertEqual(build_umap_configuration.LAYER_DESCRIPTIONS["Zebrastreifen"],
                         indicators["Zebrastreifen"]["description"])

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
        self.assertTrue(potential["displayOnLoad"])
        self.assertEqual(types["gap_length_current_m"], "Number")
        self.assertEqual(types["gap_length_with_prerequisites_m"], "Number")
        self.assertEqual(types["gap_length_after_m"], "Number")
        self.assertEqual(types["map_potential_type"], "String")
        self.assertEqual(potential["color"], "#d7191c")
        rules = {rule["condition"]: rule["properties"] for rule in potential["rules"]}
        self.assertEqual(rules["feature_type=Potenzial durch Zebrastreifen"]["color"], "#f28e2b")
        self.assertEqual(rules["feature_type=Potenzial durch Lückenschluss"]["color"], "#8e44ad")
        self.assertEqual(rules["gap_role=corridor_connection"]["color"], "#8e44ad")
        self.assertEqual(rules["gap_role=existing_connection"]["color"], "#1a9850")
        self.assertEqual(rules["map_potential_type=crossing"]["color"], "#f28e2b")
        self.assertEqual(rules["map_potential_type=gap"]["color"], "#8e44ad")
        self.assertEqual(rules["map_potential_type=existing_connection"]["color"], "#1a9850")

    def test_conditional_gaps_have_a_separate_toggleable_remote_layer(self):
        potential, conditional, covered = self.generated["layers"][1]["layers"]
        props = conditional["properties"]

        self.assertEqual(props["name"], "Bedingte Lückenschlüsse")
        self.assertEqual(props["remoteData"]["url"],
                         REMOTE_BASE + "/conditional_gap_streets.geojson")
        self.assertEqual(props["color"], "#8e44ad")
        self.assertEqual(props["dashArray"], "6,6")
        self.assertFalse(props["displayOnLoad"])
        self.assertEqual(props["popupContentTemplate"], "{description}")
        self.assertEqual(props["popupShape"], "Large")
        self.assertEqual(props["labelKey"], "name")
        rules = {rule["condition"]: rule["properties"] for rule in props["rules"]}
        self.assertEqual(set(rules), {
            "gap_role=existing_connection", "gap_role=corridor_connection",
        })
        self.assertEqual(rules["gap_role=existing_connection"]["color"], "#1a9850")
        self.assertEqual(rules["gap_role=corridor_connection"]["color"], "#8e44ad")
        self.assertEqual(covered["properties"]["name"], "Bereits abgedeckte Anschlussabschnitte")


if __name__ == "__main__":
    unittest.main()
