"""An official WFS can cap pages and report errors with HTTP 200. Check
pagination, axis order, source identity and caching so missing or misplaced
Kitas are detected.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pyproj import Transformer
import requests

from DataRetrieval.WFSRetrieval import WFSRetrieval


class WFSRetrievalTests(unittest.TestCase):
    @staticmethod
    def feature(feature_id="kita.1", **properties):
        return {
            "type": "Feature", "id": feature_id,
            "geometry": {"type": "Point", "coordinates": [390000, 5820000]},
            "properties": {"e_name": "Testkita", **properties},
        }

    @staticmethod
    def response(features, total="unknown", crs="urn:ogc:def:crs:EPSG::25833"):
        data = {
            "type": "FeatureCollection", "numberMatched": total, "features": features,
            "crs": {"type": "name", "properties": {"name": crs}},
        }
        response = Mock()
        response.json.return_value = data
        response.content = json.dumps(data).encode()
        return response

    @staticmethod
    def client(**kwargs):
        return WFSRetrieval(
            "https://example.org/wfs?request=GetCapabilities&service=WFS&dataset=test",
            type_name="test:facilities", source_name="official",
            request_crs="EPSG:25833", **{"cache_dir": None, **kwargs},
        )

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_fetches_server_capped_pages_and_preserves_attributes_and_identity(self, get):
        get.side_effect = [
            self.response([self.feature("a", extra="keep")], 2),
            self.response([self.feature("b")], 2),
        ]
        result = self.client(page_size=1000).fetch()

        self.assertEqual(len(result), 2)
        self.assertEqual(result.crs.to_epsg(), 4326)
        self.assertEqual(result.source_feature_id.tolist(), ["a", "b"])
        self.assertEqual(result.source_id.tolist(), ["official:test:facilities:a", "official:test:facilities:b"])
        self.assertEqual(result.extra.iloc[0], "keep")
        self.assertNotIn("osm_id", result)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["startIndex"], 1)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["version"], "2.0.0")
        self.assertEqual(get.call_args_list[0].args[0], "https://example.org/wfs?dataset=test")
        expected = Transformer.from_crs(25833, 4326, always_xy=True).transform(390000, 5820000)
        self.assertAlmostEqual(result.geometry.iloc[0].x, expected[0])
        self.assertAlmostEqual(result.geometry.iloc[0].y, expected[1])

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_unknown_total_needs_empty_page_not_just_a_short_page(self, get):
        get.side_effect = [
            self.response([self.feature("a")]),
            self.response([self.feature("b")]),
            self.response([]),
        ]
        result = self.client().fetch()
        self.assertEqual(len(result), 2)
        self.assertEqual(get.call_count, 3)

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_bbox_is_transformed_in_xy_order_and_output_crs_is_configurable(self, get):
        get.return_value = self.response([], 0)
        bbox = (52.478, 13.523, 52.480, 13.526)
        result = self.client(sort_by="e_nr").fetch(bbox=bbox, crs="EPSG:25832")
        params = get.call_args.kwargs["params"]
        transformer = Transformer.from_crs(4326, 25833, always_xy=True)
        expected = transformer.transform_bounds(13.523, 52.478, 13.526, 52.480)
        parts = params["bbox"].split(",")
        self.assertEqual(tuple(map(float, parts[:4])), expected)
        self.assertEqual(parts[-1], "EPSG:25833")
        self.assertEqual(params["sortBy"], "e_nr")
        self.assertTrue(result.empty)
        self.assertEqual(result.crs.to_epsg(), 25832)
        self.assertIn("source_id", result)

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_cache_refresh_and_distinct_request_keys(self, get):
        get.return_value = self.response([self.feature()], 1)
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=directory)
            original = client.fetch()
            cached = client.fetch(crs="EPSG:25833")
            self.assertEqual(get.call_count, 1)
            self.assertEqual(original.source_id.tolist(), cached.source_id.tolist())
            client.fetch(refresh=True)
            self.assertEqual(get.call_count, 2)
            client.fetch(bbox=(52, 13, 53, 14))
            self.assertEqual(get.call_count, 3)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_http_errors_are_not_swallowed(self, get):
        get.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(requests.HTTPError):
            self.client().fetch()

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_wfs_exception_report_with_http_200_is_not_success(self, get):
        get.return_value.content = (
            b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1">'
            b'<ows:Exception><ows:ExceptionText>Unknown layer</ows:ExceptionText>'
            b'</ows:Exception></ows:ExceptionReport>'
        )
        with self.assertRaisesRegex(ValueError, "Unknown layer"):
            self.client().fetch()

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_invalid_results_do_not_create_cache(self, get):
        bad_geometry = self.feature()
        bad_geometry["geometry"] = None
        missing_id = self.feature()
        del missing_id["id"]
        responses = [
            (self.response([self.feature("a"), self.feature("a")], 2), "Duplicate"),
            (self.response([missing_id], 1), "stable"),
            (self.response([bad_geometry], 1), "Missing geometry"),
            (self.response([self.feature(source_id="collision")], 1), "reserved"),
            (self.response([self.feature()], 1, "EPSG:4326"), "unexpected CRS"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for response, error in responses:
                with self.subTest(error=error):
                    get.return_value = response
                    with self.assertRaisesRegex(ValueError, error):
                        self.client(cache_dir=directory).fetch()
                    self.assertEqual(list(Path(directory).glob("*.json")), [])

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_incomplete_pagination_and_changing_total_are_explicit_errors(self, get):
        for second, error in (
            (self.response([], 2), "Incomplete"),
            (self.response([self.feature("b")], 3), "changed"),
            (self.response([self.feature("a")], 2), "Duplicate"),
        ):
            with self.subTest(error=error):
                get.side_effect = [self.response([self.feature("a")], 2), second]
                with self.assertRaisesRegex(ValueError, error):
                    self.client().fetch()

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_max_pages_guards_against_unbounded_download(self, get):
        get.return_value = self.response([self.feature()])
        with self.assertRaisesRegex(ValueError, "exceeded"):
            self.client(max_pages=1).fetch()

    @patch("DataRetrieval.WFSRetrieval.requests.get")
    def test_discovers_feature_types(self, get):
        get.return_value.content = b"""<wfs:WFS_Capabilities version="2.0.0"
          xmlns:wfs="http://www.opengis.net/wfs/2.0"><wfs:FeatureTypeList>
          <wfs:FeatureType><wfs:Name>kita:kita</wfs:Name><wfs:Title>Kitas</wfs:Title>
          <wfs:DefaultCRS>EPSG:25833</wfs:DefaultCRS></wfs:FeatureType>
          </wfs:FeatureTypeList></wfs:WFS_Capabilities>"""
        self.assertEqual(self.client().get_feature_types(), [
            {"Name": "kita:kita", "Title": "Kitas", "DefaultCRS": "EPSG:25833"},
        ])

    def test_invalid_configuration_and_bbox_are_rejected(self):
        for kwargs in ({"page_size": 0}, {"max_pages": 0}, {"timeout": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.client(**kwargs)
        for bbox in ((53, 13, 52, 14), (52, 14, 53, 13), (52, 13, 53), (52, 13, float("nan"), 14)):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                self.client().fetch(bbox=bbox)
        with self.assertRaisesRegex(ValueError, "projected"):
            WFSRetrieval("https://example.org", "kita", "test", request_crs="EPSG:4326")

if __name__ == "__main__":
    unittest.main()
