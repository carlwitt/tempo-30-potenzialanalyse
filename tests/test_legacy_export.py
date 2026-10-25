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


if __name__ == "__main__":
    unittest.main()
