"""The live Munich layer schema stays readable after additive exports."""

import unittest

from DataOutput.verify_munich_export import check_layer


class MunichExportContractTests(unittest.TestCase):
    def test_additional_properties_are_allowed_but_legacy_fields_and_shapes_remain(self):
        contract = {
            "geometry_types": ["LineString"],
            "required_fields": ["osm_id"],
            "field_types": {"osm_id": ["number"], "name": ["string"]},
        }
        feature = {
            "type": "Feature", "id": "0",
            "properties": {"osm_id": 1, "name": "Teststraße", "new_field": True},
            "geometry": {"type": "LineString", "coordinates": [[11, 48], [11.1, 48.1]]},
        }
        self.assertEqual(check_layer({"type": "FeatureCollection", "features": [feature]}, contract), [])

        feature["properties"]["osm_id"] = "1"
        feature["geometry"]["type"] = "MultiLineString"
        errors = check_layer({"type": "FeatureCollection", "features": [feature]}, contract)
        self.assertTrue(any("changed type for osm_id" in error for error in errors))
        self.assertTrue(any("unexpected geometry" in error for error in errors))

        del feature["properties"]["osm_id"]
        errors = check_layer({"type": "FeatureCollection", "features": [feature]}, contract)
        self.assertTrue(any("missing required osm_id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
