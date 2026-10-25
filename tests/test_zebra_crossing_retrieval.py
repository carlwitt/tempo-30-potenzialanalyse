"""An Overpass crossing way includes member nodes that are not crossings
themselves. Check conflicting tags and missing geometry nodes so a single way
does not create false zebra records.
"""

import unittest

from DataRetrieval.ZebraCrossingRetrieval import ZebraCrossingRetrieval


class ZebraCrossingRetrievalTests(unittest.TestCase):
    def test_way_support_nodes_are_not_imported_as_crossings(self):
        elements = [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0},
            {"type": "node", "id": 2, "lon": 13.001, "lat": 52.001,
             "tags": {"kerb": "lowered"}},
            {"type": "way", "id": 3, "nodes": [1, 2],
             "tags": {"crossing:markings": "zebra"}},
            {"type": "node", "id": 4, "lon": 13.002, "lat": 52.002,
             "tags": {"crossing_ref": "zebra"}},
        ]
        retrieval = ZebraCrossingRetrieval()
        retrieval._fetch_raw_cached = lambda bbox: {"elements": elements}

        result = retrieval.fetch_zebra_crossings((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [3, 4])
        self.assertEqual(result.element_type.tolist(), ["way", "node"])
        self.assertEqual(len(result.geometry.iloc[0].coords), 2)
        legacy = retrieval.fetch_zebra_crossings(
            (52.0, 13.0, 52.1, 13.1), validate_osm_sources=False,
        )
        self.assertEqual(legacy.osm_id.tolist(), [1, 2, 3, 4])

    def test_explicit_unmarked_or_no_markings_override_zebra_reference(self):
        elements = [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0,
             "tags": {"crossing_ref": "zebra", "crossing": "unmarked"}},
            {"type": "node", "id": 2, "lon": 13.001, "lat": 52.0,
             "tags": {"crossing_ref": "zebra", "crossing:markings": "no"}},
            {"type": "node", "id": 4, "lon": 13.003, "lat": 52.0,
             "tags": {"crossing_ref": "zebra", "crossing": "traffic_signals"}},
            {"type": "node", "id": 3, "lon": 13.002, "lat": 52.0,
             "tags": {"crossing:markings": "zebra"}},
        ]
        retrieval = ZebraCrossingRetrieval()
        retrieval._fetch_raw_cached = lambda bbox: {"elements": elements}

        result = retrieval.fetch_zebra_crossings((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [3])

    def test_empty_result_keeps_columns_for_pipeline(self):
        retrieval = ZebraCrossingRetrieval()
        retrieval._fetch_raw_cached = lambda bbox: {"elements": []}

        result = retrieval.fetch_zebra_crossings((52.0, 13.0, 52.1, 13.1))

        self.assertTrue(result.empty)
        self.assertEqual(result.crs.to_string(), "EPSG:4326")
        self.assertIn("osm_id", result)
        self.assertIn("geometry", result)

    def test_missing_way_node_cannot_create_shortcut_crossing(self):
        retrieval = ZebraCrossingRetrieval()
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0},
            {"type": "node", "id": 3, "lon": 13.01, "lat": 52.0},
            {"type": "way", "id": 40, "nodes": [1, 2, 3],
             "tags": {"crossing:markings": "zebra"}},
        ]}
        with self.assertRaisesRegex(ValueError, "Incomplete geometry for OSM way 40"):
            retrieval.fetch_zebra_crossings((52.0, 13.0, 52.1, 13.1))


if __name__ == "__main__":
    unittest.main()
