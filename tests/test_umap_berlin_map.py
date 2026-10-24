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
            "disability_facilities_review.geojson", "streets_and_limit.geojson",
        }

        self.assertEqual(len(layers), 12)
        self.assertEqual({url.rsplit("/", 1)[-1] for url in urls}, filenames)
        self.assertTrue(all(not layer["features"] for layer in layers))
        self.assertTrue(all(url.startswith(build_berlin_map.REMOTE_BASE + "/") for url in urls))

    def test_district_metric_fields_are_numeric_and_not_categorized(self):
        props = self.generated["layers"][2]["properties"]
        types = {field["key"]: field["type"] for field in props["fields"]}

        self.assertEqual(props["type"], "Choropleth")
        self.assertEqual(types["realized_potential_pct_total"], "Number")
        self.assertEqual(types["gap_direct_potential"], "Number")
        self.assertEqual(types["gap_conditional_potential"], "Number")
        self.assertNotIn("analysis_scope", types)
        self.assertNotIn("categorized", props)


if __name__ == "__main__":
    unittest.main()
