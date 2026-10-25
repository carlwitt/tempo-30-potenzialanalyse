import copy
import unittest

from DataOutput.compare_munich_baseline import compare_layer


class MunichBaselineComparisonTests(unittest.TestCase):
    @staticmethod
    def collection():
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "id": "0",
            "properties": {"osm_id": 42, "potential_candidate": True},
            "geometry": {"type": "LineString", "coordinates": [[11, 48], [11.01, 48.01]]},
        }]}

    def test_additive_properties_and_feature_ids_do_not_change_result(self):
        baseline = self.collection()
        candidate = copy.deepcopy(baseline)
        candidate["features"][0]["id"] = "99"
        candidate["features"][0]["properties"]["description"] = "New popup"
        candidate["features"][0]["geometry"]["coordinates"].reverse()
        result = compare_layer(baseline, candidate)
        self.assertEqual(result["unchanged_features"], 1)
        self.assertEqual(result["added_or_changed_features"], 0)

    def test_equal_counts_do_not_hide_changed_potential_decisions(self):
        baseline = self.collection()
        candidate = copy.deepcopy(baseline)
        candidate["features"][0]["properties"]["potential_candidate"] = False
        result = compare_layer(baseline, candidate)
        self.assertEqual(result["missing_or_changed_features"], 1)
        self.assertEqual(result["added_or_changed_features"], 1)
        self.assertEqual(result["missing_or_changed_osm_ids"], [42])

    def test_geometry_and_duplicate_features_are_compared(self):
        baseline = self.collection()
        candidate = copy.deepcopy(baseline)
        candidate["features"].append(copy.deepcopy(candidate["features"][0]))
        self.assertEqual(compare_layer(baseline, candidate)["added_or_changed_features"], 1)
        candidate["features"] = candidate["features"][:1]
        candidate["features"][0]["geometry"]["coordinates"][1][0] += 0.001
        self.assertEqual(compare_layer(baseline, candidate)["missing_or_changed_features"], 1)


if __name__ == "__main__":
    unittest.main()
