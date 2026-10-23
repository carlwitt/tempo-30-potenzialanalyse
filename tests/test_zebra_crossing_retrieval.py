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


if __name__ == "__main__":
    unittest.main()
