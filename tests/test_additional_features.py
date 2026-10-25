"""An official Kita may match an OSM place, or may be a distinct neighbor. Check
identity, ambiguity and idempotence so imports add missing records without
merging unrelated facilities.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, LineString

from DataRetrieval.AdditionalFeatures import AdditionalFeatures, facility_url
from DataRetrieval.WFSRetrieval import WFSRetrieval
from DataRetrieval.SegmentRetrieval import create_gdf_entry
from DataOutput.GeoJsonCreator import GeoJsonCreator
from DataOutput.FacilityPopupCreator import FacilityPopupCreator
from DataOutput.OSMVerificationMetadata import OSMVerificationMetadata
from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from PotentialCalculation.ProximityPotential import ProximityPotential


class AdditionalFeaturesTests(unittest.TestCase):
    @staticmethod
    def osm(names=("Kita Eins",), amenities=None):
        return gpd.GeoDataFrame(
            {"osm_id": list(range(1, len(names) + 1)), "name": names,
             "amenity": amenities or ["kindergarten"] * len(names),
             "street": ["Teststraße"] * len(names), "housenumber": ["1"] * len(names),
             "osm_url": [f"https://www.openstreetmap.org/node/{n+1}" for n in range(len(names))],
             "osm_node_ids": [[] for _ in names], "element_type": ["node"] * len(names),
             "official_name": [None] * len(names), "alt_name": [None] * len(names),
             "operator": [None] * len(names)},
            geometry=[Point(390000 + n * 5, 5820000) for n in range(len(names))],
            crs="EPSG:25833",
        )

    @staticmethod
    def external(name="Kita Eins", x=390002, source_id="official:kita:1"):
        return gpd.GeoDataFrame(
            {"source_id": [source_id], "source_name": ["official"],
             "source_url": ["https://example.org/wfs"], "source_feature_id": ["kita.1"],
             "source_license_url": ["https://example.org/license"],
             "name": [name], "street": ["Teststr."], "housenumber": ["1"],
             "operator": ["Träger"], "amenity": ["kindergarten"]},
            geometry=[Point(x, 5820000)], crs="EPSG:25833",
        )

    def test_matches_address_and_preserves_osm_geometry_and_name(self):
        osm = self.osm()
        external = self.external("Amtlicher Name")
        merged, stats = AdditionalFeatures.merge(osm, external, {"amenity": "kindergarten"})
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.name.iloc[0], "Kita Eins")
        self.assertEqual(merged.operator.iloc[0], "Träger")
        self.assertEqual(merged.osm_id.iloc[0], 1)
        self.assertTrue(merged.geometry.iloc[0].equals(osm.geometry.iloc[0]))
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(len(merged.additional_sources.iloc[0]), 1)
        self.assertNotIn("additional_sources", osm)

    def test_merge_is_idempotent_for_existing_source_identity(self):
        merged, _ = AdditionalFeatures.merge(self.osm(), self.external(), {"amenity": "kindergarten"})
        twice, stats = AdditionalFeatures.merge(merged, self.external(), {"amenity": "kindergarten"})
        self.assertEqual(stats["added"], 0)
        self.assertEqual(len(twice), 1)
        self.assertEqual(len(twice.additional_sources.iloc[0]), 1)

    def test_external_additions_are_idempotent_and_reprojected(self):
        external = self.external(x=391000).to_crs("EPSG:4326")
        merged, _ = AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})
        self.assertAlmostEqual(merged.geometry.iloc[1].x, 391000)
        twice, stats = AdditionalFeatures.merge(merged, external, {"amenity": "kindergarten"})
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(len(twice), 2)

    def test_empty_results_and_nullable_type_tags(self):
        osm = self.osm()
        osm.loc[0, "amenity"] = pd.NA
        merged, stats = AdditionalFeatures.merge(osm, self.external(), {"amenity": "kindergarten"})
        self.assertEqual(stats["added"], 1)
        empty, stats = AdditionalFeatures.merge(self.osm(), self.external().iloc[:0], {"amenity": "kindergarten"})
        self.assertEqual(stats["external"], 0)
        self.assertEqual(len(empty), 1)

    def test_repeated_osm_claim_and_duplicate_external_ids(self):
        external = pd.concat([self.external(), self.external(source_id="official:kita:2")], ignore_index=True)
        _, stats = AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})
        self.assertEqual(stats["matched"], 0)
        self.assertEqual(stats["ambiguous"], 2)
        external.loc[1, "source_id"] = "official:kita:1"
        with self.assertRaisesRegex(ValueError, "duplicate source_id"):
            AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})

    def test_name_match_without_address_and_different_crs(self):
        external = self.external().to_crs("EPSG:4326")
        external["street"] = None
        merged, stats = AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(merged.crs.to_epsg(), 25833)

    def test_nearby_different_kita_and_wrong_feature_type_are_not_merged(self):
        for amenities in (["school"], ["kindergarten"]):
            with self.subTest(amenities=amenities):
                external = self.external("Andere Einrichtung")
                external["housenumber"] = "2"
                merged, stats = AdditionalFeatures.merge(
                    self.osm(amenities=amenities), external, {"amenity": "kindergarten"},
                )
                self.assertEqual(stats["added"], 1)
                self.assertEqual(len(merged), 2)
                self.assertEqual(merged.iloc[1].osm_id, "official:kita:1")
                self.assertIsNone(merged.iloc[1].osm_url)
                self.assertEqual(facility_url(merged.iloc[1]), "https://example.org/wfs")

    def test_ambiguous_candidates_are_reported_and_not_added(self):
        merged, stats = AdditionalFeatures.merge(
            self.osm(("Kita Eins", "Kita Eins")), self.external(), {"amenity": "kindergarten"},
        )
        self.assertEqual(stats["ambiguous"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(len(merged), 2)

    def test_unnamed_containing_polygon_is_enriched(self):
        osm = self.osm((None,))
        osm.loc[0, "geometry"] = Polygon([
            (389990, 5819990), (390010, 5819990), (390010, 5820010), (389990, 5820010),
        ])
        external = self.external()
        external["street"] = None
        merged, stats = AdditionalFeatures.merge(osm, external, {"amenity": "kindergarten"})
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(merged.name.iloc[0], "Kita Eins")

    @patch("DataRetrieval.AdditionalFeatures.WFSRetrieval")
    def test_json_configuration_controls_mapping_tags_and_area(self, retrieval):
        retrieval.PROVENANCE_FIELDS = WFSRetrieval.PROVENANCE_FIELDS
        raw = self.external()
        raw["official_title"] = "Kita Papagei"
        retrieval.return_value.fetch.return_value = raw
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "additional_features.json"
            config.write_text(json.dumps({"sources": [{
                "name": "test", "areas": ["berlin"], "layer": "educational_buildings",
                "url": "https://example.org/wfs", "public_url": "https://example.org/kitas",
                "type_name": "test:kita",
                "tags": {"amenity": "kindergarten"}, "fields": {"name": "official_title"},
            }]}))
            data = {"educational_buildings": self.osm()}
            self.assertEqual(AdditionalFeatures.apply(data, "Potsdam", None, config), [])
            self.assertFalse(retrieval.called)
            reports = AdditionalFeatures.apply(data, "Berlin", None, config)
            self.assertEqual(reports[0]["external"], 1)
            self.assertEqual(reports[0]["matched"], 1)
            self.assertEqual(data["educational_buildings"].additional_sources.iloc[0][0]["source_url"],
                             "https://example.org/kitas")
            configuration = json.loads(config.read_text())
            configuration["sources"][0]["fields"] = {"name": "missing_field"}
            config.write_text(json.dumps(configuration))
            with self.assertRaisesRegex(ValueError, "Missing WFS field"):
                AdditionalFeatures.apply(data, "Berlin", None, config)
            configuration["sources"][0]["fields"] = {"osm_id": "official_title"}
            config.write_text(json.dumps(configuration))
            with self.assertRaisesRegex(ValueError, "reserved identity"):
                AdditionalFeatures.apply(data, "Berlin", None, config)

    def test_external_kita_flows_through_potential_segments_and_popups(self):
        external = self.external("Kita Papagei", x=391000)
        external["housenumber"] = "124"
        merged, _ = AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})
        roads = gpd.GeoDataFrame(
            {"osm_id": [123], "name": ["Treskowallee"], "highway": ["tertiary"],
             "maxspeed_class": ["50"], "conditional_speed": [None]},
            geometry=[LineString([(390990, 5820005), (391010, 5820005)])], crs=merged.crs,
        )
        potential = ProximityPotential.find_tempo50_segments_near_features(roads, merged, 20)
        self.assertIn("official:kita:1", potential.opt_source_ids)
        merged["potential_candidate"] = merged.osm_id.isin(potential.opt_source_ids)
        details = OSMVerificationMetadata.add_details(merged, "educational_buildings")
        segments = FacilityStreetSegments.create(
            roads, {"educational_buildings": merged}, {"educational_buildings": potential},
        )
        self.assertEqual(segments.facility_id.tolist(), ["official:kita:1"])
        popups = FacilityPopupCreator.create(
            details, "educational_buildings", segments, segments.iloc[0:0],
        )
        popup = popups.loc[popups.element_type.eq("external")].popup_content.iloc[0]
        self.assertIn("Kita Papagei", popup)
        self.assertIn("kein zugeordnetes OSM-Objekt", popup)
        self.assertNotIn("openstreetmap.org/node/official", popup)
        self.assertIn("https://example.org/wfs", popup)

    def test_geojson_uses_neutral_identity_without_fake_osm_links(self):
        external = self.external("Kita Papagei", x=391000)
        merged, _ = AdditionalFeatures.merge(self.osm(), external, {"amenity": "kindergarten"})
        merged = merged.to_crs("EPSG:4326")
        for column in ("short_name", "healthcare", "social_facility", "social_facility_for", "website"):
            merged[column] = None
        point = merged.geometry.iloc[1]
        merged.loc[0, "geometry"] = Point(point.x - 0.0004, point.y)
        merged.at[0, "osm_id"] = np.int64(1)
        roads = gpd.GeoDataFrame([create_gdf_entry(
            {"id": 123}, "tertiary",
            [(point.x - 0.001, point.y), (point.x + 0.001, point.y)],
            {"name": "Treskowallee", "highway": "tertiary", "maxspeed": "50"},
        ), create_gdf_entry(
            {"id": 124}, "tertiary",
            [(point.x + 0.001, point.y), (point.x + 0.002, point.y)],
            {"name": "Treskowallee", "highway": "tertiary", "maxspeed": "30"},
        )], crs=merged.crs)
        potential = ProximityPotential.find_tempo50_segments_near_features(roads, merged, 20)
        merged["potential_candidate"] = merged.osm_id.isin(potential.opt_source_ids)
        zebras = gpd.GeoDataFrame(
            {"potential_candidate": [], "street": []}, geometry=[], crs=merged.crs,
        )
        with tempfile.TemporaryDirectory() as directory:
            GeoJsonCreator.create_geojson_layer_files(
                directory, roads.loc[roads.osm_id.eq(123)].assign(feature_type="T30_Potenzial_Schule"),
                roads, zebras,
                {"educational_buildings": merged, "playgrounds": merged.iloc[:0]},
                potential_results={"educational_buildings": potential},
            )
            exported = json.loads((Path(directory) / "educational_buildings.geojson").read_text())
            properties = [feature["properties"] for feature in exported["features"]]
            official = next(feature for feature in properties if feature["element_type"] == "external")
            self.assertEqual(official["facility_id"], "official:kita:1")
            self.assertNotIn("osm_id", official)
            self.assertNotIn("osm_url", official)
            self.assertEqual(official["source_name"], "official")
            self.assertEqual(properties[0]["osm_id"], 1)
            self.assertTrue(official["potential_candidate"])
            self.assertIn("kein zugeordnetes OSM-Objekt", official["popup_content"])
            visible = json.loads((Path(directory) / "educational_buildings_map.geojson").read_text())
            self.assertEqual(
                len(visible["features"]),
                sum(feature["potential_candidate"] for feature in properties),
            )
            self.assertIn("official:kita:1", [
                feature["properties"]["facility_id"] for feature in visible["features"]
            ])
            streets_export = json.loads((Path(directory) / "potential_streets.geojson").read_text())
            self.assertIn("Kita Papagei ([[https://example.org/wfs|amtliche Quelle]])",
                          streets_export["features"][0]["properties"]["description"])
            segments = json.loads((Path(directory) / "facility_street_segments.geojson").read_text())
            self.assertEqual(
                {feature["properties"]["facility_id"] for feature in segments["features"]},
                {1, "official:kita:1"},
            )
            covered = json.loads((Path(directory) / "facility_covered_street_segments.geojson").read_text())
            self.assertEqual(
                {feature["properties"]["facility_id"] for feature in covered["features"]},
                {1, "official:kita:1"},
            )


if __name__ == "__main__":
    unittest.main()
