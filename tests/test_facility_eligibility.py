import unittest

import geopandas as gpd
from shapely.geometry import Point

from PotentialCalculation.FacilityEligibility import FacilityEligibility


class FacilityEligibilityTests(unittest.TestCase):
    def test_disability_requires_explicit_osm_target_group(self):
        features = gpd.GeoDataFrame(
            {"social_facility_for": [None, "disabled", "senior;disabled", "juvenile"]},
            geometry=[Point(i, 0) for i in range(4)], crs="EPSG:4326",
        )

        result = FacilityEligibility.annotate_disability(features)

        self.assertEqual(result.facility_status.tolist(), [
            "target_group_unknown", "confirmed_disabled", "confirmed_disabled",
            "different_target_group",
        ])


if __name__ == "__main__":
    unittest.main()
