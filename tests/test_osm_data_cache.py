"""An Overpass timeout can return a syntactically valid but incomplete response.
Check validation on read and write so a partial road network never becomes
trusted cache data.
"""

import json
import tempfile
import unittest
from pathlib import Path

from DataRetrieval.OSMDataCache import OSMDataCache


class OSMDataCacheTests(unittest.TestCase):
    def test_rejects_incomplete_overpass_response_before_caching(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = OSMDataCache("streets", cache_dir=directory)
            bbox = (52.0, 13.0, 52.1, 13.1)
            with self.assertRaisesRegex(ValueError, "Incomplete Overpass response"):
                cache.store_data({"elements": [], "remark": "runtime error"}, bbox)
            self.assertFalse(cache._cache_path(bbox).exists())

    def test_rejects_invalid_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = OSMDataCache("streets", cache_dir=directory)
            bbox = (52.0, 13.0, 52.1, 13.1)
            Path(cache._cache_path(bbox)).write_text(json.dumps({"error": "timeout"}))
            with self.assertRaisesRegex(ValueError, "missing elements list"):
                cache.load_file_from_cache(bbox)

    def test_complete_response_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = OSMDataCache("streets", cache_dir=directory)
            bbox = (52.0, 13.0, 52.1, 13.1)
            data = {"elements": [{"type": "node", "id": 1, "lon": 13.0, "lat": 52.0}]}
            cache.store_data(data, bbox)
            self.assertEqual(cache.load_file_from_cache(bbox), data)
