"""A name suggesting a disability facility is insufficient evidence. Check that
only the explicit OSM disabled target group is confirmed while other or
missing groups remain distinguishable.
"""

import unittest

import geopandas as gpd
from shapely.geometry import Point

from PotentialCalculation.FacilityEligibility import FacilityEligibility


class FacilityEligibilityTests(unittest.TestCase):
    def test_disability_requires_explicit_osm_target_group(self):
        features = gpd.GeoDataFrame(
            {"social_facility_for": [None, "disabled", "senior;disabled", "juvenile", " Disabled ; senior "]},
            geometry=[Point(i, 0) for i in range(5)], crs="EPSG:4326",
        )

        result = FacilityEligibility.annotate_disability(features)

        self.assertEqual(result.facility_status.tolist(), [
            "target_group_unknown", "confirmed_disabled", "confirmed_disabled",
            "different_target_group", "confirmed_disabled",
        ])


if __name__ == "__main__":
    unittest.main()
