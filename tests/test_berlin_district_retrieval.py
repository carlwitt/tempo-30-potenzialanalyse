import unittest

from shapely.geometry import Point

from DataRetrieval.BerlinDistrictRetrieval import BerlinDistrictRetrieval


class BerlinDistrictRetrievalTests(unittest.TestCase):
    def test_builds_polygon_from_relation_ways_and_excludes_city_relation(self):
        corners = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        members = [
            {
                "type": "way",
                "role": "outer",
                "geometry": [{"lon": x, "lat": y} for x, y in corners[index:index + 2]],
            }
            for index in range(4)
        ]
        elements = [
            {"type": "relation", "id": 1, "tags": {"name": "District", "ref:DE-BE:BEZ": "01"}, "members": members},
            {"type": "relation", "id": 2, "tags": {"name": "Berlin"}, "members": members},
        ]
        retrieval = BerlinDistrictRetrieval()
        retrieval.datacache.load_file_from_cache = lambda key: {"elements": elements}

        districts = retrieval.fetch_districts()

        self.assertEqual(districts.district_id.tolist(), ["01"])
        self.assertTrue(districts.geometry.iloc[0].covers(Point(0.5, 0.5)))
        self.assertEqual(districts.crs.to_epsg(), 4326)


if __name__ == "__main__":
    unittest.main()
