"""A private driveway or untagged residential road must not become a Tempo-50
proposal. Check access precedence and speed classification with
representative OSM tags.
"""

import unittest
from unittest.mock import patch

from DataRetrieval.RoadClassification import RoadClassification
from DataRetrieval.SegmentRetrieval import SegmentRetrieval


class RoadClassificationTests(unittest.TestCase):
    def test_public_motorcar_access_respects_highway_and_access_hierarchy(self):
        examples = [
            ({"highway": "living_street"}, True),
            ({"highway": "service", "service": "alley"}, True),
            ({"highway": "service", "service": "driveway"}, False),
            ({"highway": "service", "service": "driveway", "access": "customers"}, True),
            ({"highway": "residential", "access": "private"}, False),
            ({"highway": "residential", "access": "no", "motor_vehicle": "destination"}, True),
            ({"highway": "residential", "vehicle": "yes", "motorcar": "no"}, False),
            ({"highway": "residential", "motor_vehicle": "private"}, False),
            ({"highway": "residential", "motor_vehicle": "private;destination"}, False),
            ({"highway": "residential", "motor_vehicle": "delivery"}, False),
            ({"highway": "pedestrian", "motorcar": "yes"}, False),
            ({"highway": "footway", "motorcar": "yes"}, False),
            ({"highway": "track"}, False),
            ({"highway": "track", "motorcar": "yes"}, True),
            ({"highway": "residential", "bicycle_road": "yes"}, False),
            ({"highway": "residential", "bicycle_road": "yes", "motor_vehicle": "destination"}, True),
        ]
        for tags, expected in examples:
            with self.subTest(tags=tags):
                self.assertIs(RoadClassification.allows_public_motorcar(tags), expected)

    def test_low_speed_osm_classification_never_fabricates_tempo_50(self):
        examples = [
            ({"highway": "living_street"}, "walk"),
            ({"highway": "service", "living_street": "yes"}, "walk"),
            ({"highway": "residential", "maxspeed": "walk"}, "walk"),
            ({"highway": "residential", "zone:maxspeed": "DE:30"}, "30_Zone"),
            ({"highway": "residential", "maxspeed:type": "DE:zone30"}, "30_Zone"),
            ({"highway": "residential", "source:maxspeed": "DE:zone:30"}, "30_Zone"),
            ({"highway": "residential", "zone:maxspeed": "DE:20"}, "20"),
            ({"highway": "residential", "maxspeed": "50", "zone:maxspeed": "DE:30"}, "30_Zone"),
            ({"highway": "residential", "maxspeed": "50"}, "50"),
            ({"highway": "residential", "source:maxspeed": "DE:urban"}, "Keine Daten"),
            ({"highway": "residential", "bicycle_road": "yes"}, "30"),
            ({"highway": "residential", "maxspeed": "5"}, "5"),
            ({"highway": "residential", "maxspeed": "40"}, "40"),
        ]
        for tags, expected in examples:
            with self.subTest(tags=tags):
                self.assertEqual(RoadClassification.classify_speed(tags), expected)
        self.assertTrue(RoadClassification.is_covered_speed("walk"))
        self.assertTrue(RoadClassification.is_covered_speed("5"))
        self.assertFalse(RoadClassification.is_covered_speed("Keine Daten"))
        self.assertFalse(RoadClassification.is_covered_speed("50"))

    def test_retrieval_omits_private_and_pedestrian_ways_before_potential_calculation(self):
        nodes = [
            {"type": "node", "id": n, "lon": 13 + n * 0.001, "lat": 52}
            for n in range(1, 9)
        ]
        ways = [
            {"type": "way", "id": 10, "nodes": [1, 2],
             "tags": {"highway": "living_street", "name": "Spielstraße"}},
            {"type": "way", "id": 20, "nodes": [3, 4],
             "tags": {"highway": "residential", "access": "private", "maxspeed": "50"}},
            {"type": "way", "id": 30, "nodes": [5, 6],
             "tags": {"highway": "pedestrian", "maxspeed": "50"}},
            {"type": "way", "id": 40, "nodes": [7, 8],
             "tags": {"highway": "service", "access": "customers", "maxspeed": "30"}},
        ]
        with patch.object(SegmentRetrieval, "_fetch_raw_cached", return_value={"elements": nodes + ways}):
            result = SegmentRetrieval().fetch_as_geodataframe((52, 13, 52.1, 13.1))

        self.assertEqual(set(result.osm_id), {10, 40})
        self.assertEqual(result.set_index("osm_id").loc[10, "maxspeed_class"], "walk")
        self.assertTrue(result.public_motorcar.all())

    def test_missing_way_node_cannot_create_shortcut_street(self):
        elements = [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0},
            {"type": "node", "id": 3, "lon": 13.01, "lat": 52.0},
            {"type": "way", "id": 40, "nodes": [1, 2, 3],
             "tags": {"highway": "residential", "maxspeed": "50"}},
        ]
        with patch.object(SegmentRetrieval, "_fetch_raw_cached", return_value={"elements": elements}):
            with self.assertRaisesRegex(ValueError, "Incomplete geometry for OSM way 40"):
                SegmentRetrieval().fetch_as_geodataframe((52, 13, 52.1, 13.1))


if __name__ == "__main__":
    unittest.main()
