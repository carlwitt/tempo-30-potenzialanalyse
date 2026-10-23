import unittest

import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from DataOutput.PlaygroundConsolidation import PlaygroundConsolidation


class PlaygroundConsolidationTests(unittest.TestCase):
    def test_keeps_potentials_or_polygons(self):
        polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        playgrounds = gpd.GeoDataFrame(
            {
                "name": ["discard", "candidate", "area", "multi-area", "candidate line"],
                "potential_candidate": [False, True, False, None, True],
            },
            geometry=[
                Point(0, 0),
                Point(1, 1),
                polygon,
                MultiPolygon([polygon]),
                LineString([(0, 0), (1, 1)]),
            ],
            crs="EPSG:4326",
        )

        result = PlaygroundConsolidation.summarize_playground_features(playgrounds)

        self.assertEqual(result.name.tolist(), ["candidate", "area", "multi-area", "candidate line"])
        self.assertEqual(result.crs, playgrounds.crs)
        self.assertEqual(len(playgrounds), 5)


if __name__ == "__main__":
    unittest.main()
