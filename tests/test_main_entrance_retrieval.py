import unittest

from DataRetrieval.MainEntranceRetrieval import MainEntranceRetrieval


class MainEntranceRetrievalTests(unittest.TestCase):
    def test_query_and_tag_filter(self):
        retrieval = MainEntranceRetrieval()
        query = retrieval._build_query((52.0, 13.0, 52.1, 13.1))
        self.assertIn('node["entrance"="main"](52.0,13.0,52.1,13.1)', query)
        self.assertIn('node["routing:entrance"="main"](52.0,13.0,52.1,13.1)', query)
        retrieval.datacache.load_file_from_cache = lambda bbox: {"elements": [
            {"type": "node", "id": 1, "lon": 13.01, "lat": 52.01, "tags": {"entrance": "main"}},
            {"type": "node", "id": 2, "lon": 13.02, "lat": 52.02, "tags": {"entrance": "yes"}},
            {"type": "node", "id": 3, "lon": 13.03, "lat": 52.03, "tags": {"routing:entrance": "main"}},
        ]}

        result = retrieval.fetch_as_geodataframe((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [1, 3])
        self.assertEqual(result.crs.to_epsg(), 4326)


if __name__ == "__main__":
    unittest.main()
