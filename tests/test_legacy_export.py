"""The no-flag export must work without metadata from optional map filters."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import geopandas as gpd

from DataOutput.GeoJsonCreator import GeoJsonCreator
from DataRetrieval.BuildingRetrieval import BuildingRetrieval
from DataRetrieval.SegmentRetrieval import create_gdf_entry


class LegacyExportTests(unittest.TestCase):
    def test_unfiltered_short_and_empty_potentials_preserve_main_speed_classes(self):
        records = [
            create_gdf_entry(
                {"id": osm_id}, "residential", [(11, 48), (11.0001, 48)],
                {"highway": "residential", **tags}, modern_speed_classes=False,
            )
            for osm_id, tags in (
                (1, {"maxspeed": "50"}), (2, {"zone:maxspeed": "30"}),
            )
        ]
        streets = gpd.GeoDataFrame(records, crs="EPSG:4326")
        retrieval = BuildingRetrieval("playgrounds", {"leisure": ["playground"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": []}
        with redirect_stdout(io.StringIO()):
            facilities = retrieval.fetch("München")
        facilities["potential_candidate"] = False
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [], "street": []}, geometry=[], crs=streets.crs,
        )
        for ids in ([], [1]):
            with self.subTest(potential_ids=ids), tempfile.TemporaryDirectory() as directory:
                potentials = streets.loc[streets.osm_id.isin(ids)].assign(
                    feature_type="T30_Potenzial_Spielplatz",
                )
                with redirect_stdout(io.StringIO()):
                    GeoJsonCreator.create_geojson_layer_files(
                        directory, potentials, streets, zebras, {"playgrounds": facilities},
                        clip_long_potentials=False, filter_short_potentials=False,
                        simplify_crossings=False, compact_playgrounds=False,
                        modern_speed_context=False,
                    )
                exported = json.loads((Path(directory) / "potential_streets.geojson").read_text())
                self.assertEqual(
                    [feature["properties"]["osm_id"] for feature in exported["features"]], ids,
                )
                context = json.loads((Path(directory) / "streets_and_limit.geojson").read_text())
                zone = next(feature for feature in context["features"]
                            if feature["properties"]["osm_id"] == 2)
                self.assertEqual(zone["properties"]["maxspeed_class"], "30_Zone")

    def test_indicator_exports_keep_inactive_sources_before_playground_compaction(self):
        streets = gpd.GeoDataFrame([
            create_gdf_entry({"id": 1}, "residential", [(11, 48), (11.001, 48)],
                             {"highway": "residential", "maxspeed": "50"}),
        ], crs="EPSG:4326")
        buildings = {}
        for layer, amenities in (
            ("playgrounds", ["playground", "playground"]),
            ("educational_buildings", ["kindergarten", "school"]),
            ("hospitals", ["hospital", "hospital"]),
            ("disability_facilities", ["social_facility"] * 4),
        ):
            retrieval = BuildingRetrieval(layer, {"amenity": list(set(amenities))})
            raw = {"elements": [
                {"type": "node", "id": i + 10, "lat": 48, "lon": 11 + i * 0.001,
                 "tags": {"amenity": amenity, "name": f"Facility {i}"}}
                for i, amenity in enumerate(amenities)
            ]}
            retrieval._fetch_raw_cached = lambda bbox: raw
            with redirect_stdout(io.StringIO()):
                features = retrieval.fetch("München")
            features["potential_candidate"] = [False, True] * (len(features) // 2)
            if layer == "disability_facilities":
                features["facility_status"] = [
                    "confirmed_disabled", "confirmed_disabled", "target_group_unknown", "different_target_group",
                ]
            buildings[layer] = features
        zebras = gpd.GeoDataFrame({"potential_candidate": [], "street": []},
                                 geometry=[], crs=streets.crs)
        for compact in (False, True):
            with self.subTest(compact=compact), tempfile.TemporaryDirectory() as directory:
                with redirect_stdout(io.StringIO()):
                    GeoJsonCreator.create_geojson_layer_files(
                        directory, streets.iloc[:0].assign(feature_type=""), streets, zebras, buildings,
                        compact_playgrounds=compact,
                    )
                for layer in buildings:
                    data = json.loads((Path(directory) / f"{layer}_map.geojson").read_text())
                    properties = [feature["properties"] for feature in data["features"]]
                    self.assertEqual([p["osm_id"] for p in properties], [10, 11])
                    self.assertEqual([p["potential_candidate"] for p in properties], [False, True])
                    self.assertTrue(all("popup_content" in p for p in properties))
                full = json.loads((Path(directory) / "playgrounds.geojson").read_text())
                self.assertEqual(len(full["features"]), 1 if compact else 2)
                full = json.loads((Path(directory) / "disability_facilities.geojson").read_text())
                self.assertEqual(len(full["features"]), 4)


if __name__ == "__main__":
    unittest.main()
