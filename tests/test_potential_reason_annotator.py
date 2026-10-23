import unittest

import geopandas as gpd
from shapely.geometry import Point

from DataOutput.PotentialReasonAnnotator import PotentialReasonAnnotator


class PotentialReasonAnnotatorTests(unittest.TestCase):
    def test_only_true_candidates_get_reason_in_property_and_popup(self):
        features = gpd.GeoDataFrame(
            {
                "potential_candidate": [True, False, None, True],
                "description": [None, "Existing", None, "Existing"],
            },
            geometry=[Point(index, 0) for index in range(4)],
            crs="EPSG:4326",
        )

        result = PotentialReasonAnnotator.add_reason(features, "Nearby Tempo 50 street")

        self.assertEqual(result.potential_reason.iloc[[0, 3]].tolist(), ["Nearby Tempo 50 street"] * 2)
        self.assertTrue(result.potential_reason.iloc[[1, 2]].isna().all())
        self.assertEqual(result.description.iloc[0], "Nearby Tempo 50 street")
        self.assertEqual(result.description.iloc[1], "Existing")
        self.assertEqual(result.description.iloc[3], "Existing\nNearby Tempo 50 street")
        self.assertNotIn("potential_reason", features.columns)


if __name__ == "__main__":
    unittest.main()
