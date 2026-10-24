import unittest

import geopandas as gpd
from shapely.geometry import Point

from DataOutput.OSMVerificationMetadata import OSMVerificationMetadata


class OSMVerificationMetadataTests(unittest.TestCase):
    def test_each_facility_layer_gets_a_specific_popup_classification(self):
        examples = [
            ("educational_buildings", {"amenity": "kindergarten"}, "Kindergarten"),
            ("educational_buildings", {"amenity": "school"}, "Schule"),
            ("hospitals", {"amenity": "hospital"}, "Krankenhaus"),
            ("elderly_homes", {"amenity": "retirement_home"}, "Altenheim"),
            ("playgrounds", {"leisure": "playground"}, "Spielplatz"),
            ("disability_facilities", {"social_facility": "workshop"}, "Soziale Werkstatt"),
            ("disability_facilities", {"amenity": "craft"}, "Handwerksbetrieb"),
            ("disability_facilities", {"healthcare": "physiotherapy"}, "Physiotherapie"),
        ]
        for category, tags, expected in examples:
            with self.subTest(category=category, tags=tags):
                self.assertEqual(OSMVerificationMetadata._facility_type(tags, category), expected)

    def test_adds_source_and_only_available_institution_names(self):
        features = gpd.GeoDataFrame(
            {
                "name": ["Klinik A", None],
                "official_name": ["Klinikum A", None],
                "alt_name": ["Klinik A", None],
                "operator": ["Träger A", None],
                "osm_url": ["https://www.openstreetmap.org/way/1", "https://www.openstreetmap.org/way/2"],
            },
            geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326",
        )

        result = OSMVerificationMetadata.add_details(features)

        self.assertIn("Name laut OSM: Klinik A", result.description.iloc[0])
        self.assertIn("Offizieller Name: Klinikum A", result.description.iloc[0])
        self.assertIn("Betreiber: Träger A", result.description.iloc[0])
        self.assertNotIn("Alternativer Name", result.description.iloc[0])
        self.assertIn("Kein Name in OSM erfasst.", result.description.iloc[1])
        self.assertIn("https://www.openstreetmap.org/way/2", result.description.iloc[1])

    def test_unclassified_social_facility_is_not_described_as_disability_facility(self):
        features = gpd.GeoDataFrame(
            {
                "name": ["Soziale Schreibwerkstatt"], "official_name": [None],
                "alt_name": [None], "operator": [None],
                "osm_url": ["https://www.openstreetmap.org/node/1"],
                "amenity": ["social_facility"], "social_facility": [None],
                "social_facility_for": [None], "facility_status": ["target_group_unknown"],
            },
            geometry=[Point(0, 0)], crs="EPSG:4326",
        )

        result = OSMVerificationMetadata.add_details(features, "disability_facilities")

        self.assertIn("Untertyp in OSM nicht erfasst", result.description.iloc[0])
        self.assertIn("kein bestätigtes behinderten-potenzial", result.description.iloc[0].lower())


if __name__ == "__main__":
    unittest.main()
