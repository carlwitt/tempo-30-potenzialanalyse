"""Keep the uMap facility view focused while preserving audit records.

A school with no nearby street proposal remains in the full export and
district statistics, but need not clutter the optional map layer. Show
potential candidates from confirmed facilities only;
the full analysis layer still retains every traffic-adjacent facility for
verification.
"""


class MapFacilityLayer:
    @staticmethod
    def select(features, layer):
        visible = features["potential_candidate"].eq(True)
        if layer == "disability_facilities":
            visible &= features["facility_status"].eq("confirmed_disabled")
        return features.loc[visible].copy()
