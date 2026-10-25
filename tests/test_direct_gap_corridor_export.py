"""A short intermediate OSM way can be filtered from ordinary display but still
connect a direct gap to a Tempo-30 anchor. Check the exported chain so both
anchors remain visibly reachable.
"""

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape

from DataOutput.GeoJsonCreator import GeoJsonCreator
from DataRetrieval.SegmentRetrieval import create_gdf_entry
from PotentialCalculation.GapPotential import Tempo50GapPotential


class DirectGapCorridorExportTests(unittest.TestCase):
    def test_short_traversed_way_still_connects_direct_gap_to_both_anchors(self):
        positions = (13.0, 13.001, 13.002, 13.0021, 13.003)
        speeds = ("30", "50", "50", "30")
        records = [
            create_gdf_entry(
                {"id": osm_id}, "tertiary",
                [(positions[index], 52.5), (positions[index + 1], 52.5)],
                {"highway": "tertiary", "name": "Teststraße", "maxspeed": speeds[index]},
            )
            for index, osm_id in enumerate((10, 20, 30, 40))
        ]
        streets = gpd.GeoDataFrame(records, crs="EPSG:4326")
        gaps = Tempo50GapPotential.find_all_tempo_50_gaps(streets)
        self.assertEqual(gaps.gap_corridor_ways[20], [30])

        potentials = streets.loc[streets.osm_id.isin(gaps.street_ids)].copy()
        potentials["feature_type"] = "T30_Potenzial_Luecke"
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [], "street": []}, geometry=[], crs=streets.crs,
        )
        playgrounds = gpd.GeoDataFrame(
            columns=[
                "osm_id", "element_type", "osm_node_ids", "osm_url", "name",
                "official_name", "alt_name", "short_name", "amenity", "healthcare",
                "social_facility", "social_facility_for", "potential_candidate", "street",
                "housenumber", "website", "operator", "geometry",
            ], geometry="geometry", crs=streets.crs,
        )
        with tempfile.TemporaryDirectory() as directory:
            GeoJsonCreator.create_geojson_layer_files(
                directory, potentials, streets, zebras, {"playgrounds": playgrounds},
                potential_results={"gap": gaps},
            )
            data = json.loads((Path(directory) / "potential_streets.geojson").read_text())

        by_id = {feature["properties"]["osm_id"]: feature for feature in data["features"]}
        self.assertEqual(set(by_id), {10, 20, 30, 40})
        self.assertEqual(by_id[30]["properties"]["gap_role"], "corridor_connection")
        self.assertEqual(by_id[20]["properties"]["gap_corridor_street_osm_ids"], [30])
        self.assertEqual(by_id[30]["properties"]["related_gap_osm_ids"], [20])
        self.assertEqual([by_id[osm_id]["properties"]["map_potential_type"] for osm_id in (10, 20, 30, 40)],
                         ["existing_connection", "gap", "gap", "existing_connection"])
        geometries = {osm_id: shape(feature["geometry"]) for osm_id, feature in by_id.items()}
        for first, second in ((10, 20), (20, 30), (30, 40)):
            self.assertLess(geometries[first].distance(geometries[second]), 1e-8)


if __name__ == "__main__":
    unittest.main()
