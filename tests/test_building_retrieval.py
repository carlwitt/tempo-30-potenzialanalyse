"""A school's OSM way brings geometry support nodes and may have no telling
name. Check tag-based facility selection, relation geometry and source
identity so support nodes and name guesses do not inflate counts.
"""

import unittest

from DataRetrieval.BuildingRetrieval import BuildingRetrieval


class BuildingRetrievalTests(unittest.TestCase):
    def test_support_nodes_are_not_imported_as_facilities(self):
        elements = [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0},
            {"type": "node", "id": 2, "lon": 13.001, "lat": 52.0, "tags": {"entrance": "yes"}},
            {"type": "node", "id": 3, "lon": 13.001, "lat": 52.001},
            {"type": "node", "id": 4, "lon": 13.002, "lat": 52.002, "tags": {"leisure": "playground"}},
            {"type": "way", "id": 5, "nodes": [1, 2, 3, 1], "tags": {"leisure": "playground"}},
        ]
        retrieval = BuildingRetrieval("playgrounds", {"leisure": ["playground"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": elements}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [4, 5])
        self.assertEqual(result.geometry.geom_type.tolist(), ["Point", "Polygon"])
        self.assertEqual(result.osm_node_ids.tolist(), [[], [1, 2, 3, 1]])
        self.assertEqual(result.osm_url.tolist(), [
            "https://www.openstreetmap.org/node/4",
            "https://www.openstreetmap.org/way/5",
        ])

    def test_preserves_osm_names_and_website(self):
        retrieval = BuildingRetrieval("hospitals", {"amenity": ["hospital"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [{
            "type": "node", "id": 42, "lon": 13.0, "lat": 52.0,
            "tags": {
                "amenity": "hospital", "name": "Clinic A", "alt_name": "Clinic B",
                "official_name": "Official Clinic", "website": "https://example.org",
                "operator": "Operator", "healthcare": "hospital",
            },
        }]}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.name.iloc[0], "Clinic A")
        self.assertEqual(result.alt_name.iloc[0], "Clinic B")
        self.assertEqual(result.official_name.iloc[0], "Official Clinic")
        self.assertEqual(result.website.iloc[0], "https://example.org")
        self.assertEqual(result.healthcare.iloc[0], "hospital")

    def test_tagged_kindergarten_does_not_require_a_name_keyword(self):
        retrieval = BuildingRetrieval("educational_buildings", {"amenity": ["school", "kindergarten"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [{
            "type": "node", "id": 43, "lon": 13.0, "lat": 52.0,
            "tags": {"amenity": "kindergarten", "name": "Kita Sonnenschein"},
        }]}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [43])

    def test_healthcare_hospital_works_without_amenity_or_name_keyword(self):
        retrieval = BuildingRetrieval(
            "hospitals_with_healthcare", {"amenity": ["hospital"], "healthcare": ["hospital"]}
        )
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [{
            "type": "node", "id": 44, "lon": 13.0, "lat": 52.0,
            "tags": {"healthcare": "hospital", "name": "Klinik Havelhöhe"},
        }]}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [44])

    def test_assisted_living_requires_explicit_senior_target_group(self):
        retrieval = BuildingRetrieval(
            "elderly_homes", {"social_facility": ["assisted_living", "nursing_home"]},
            senior_assisted_living_only=True,
        )
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [
            {"type": "node", "id": 45, "lon": 13.0, "lat": 52.0,
             "tags": {"social_facility": "assisted_living", "social_facility:for": "disabled"}},
            {"type": "node", "id": 46, "lon": 13.0, "lat": 52.0,
             "tags": {"social_facility": "assisted_living", "social_facility:for": "senior;disabled"}},
            {"type": "node", "id": 47, "lon": 13.0, "lat": 52.0,
             "tags": {"social_facility": "nursing_home"}},
        ]}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [46, 47])

    def test_multipolygon_relation_is_imported_with_hole_and_identity(self):
        coordinates = [
            (13.0, 52.0), (13.01, 52.0), (13.01, 52.01), (13.0, 52.01), (13.0, 52.0),
            (13.004, 52.004), (13.006, 52.004), (13.006, 52.006),
            (13.004, 52.006), (13.004, 52.004),
        ]
        elements = [
            {"type": "node", "id": index, "lon": lon, "lat": lat}
            for index, (lon, lat) in enumerate(coordinates, start=1)
        ] + [
            {"type": "way", "id": 20, "nodes": [1, 2, 3, 4, 5]},
            {"type": "way", "id": 21, "nodes": [6, 7, 8, 9, 10]},
            {"type": "relation", "id": 30, "tags": {"type": "multipolygon", "amenity": "hospital"},
             "members": [{"type": "way", "ref": 20, "role": "outer"},
                         {"type": "way", "ref": 21, "role": "inner"}]},
        ]
        retrieval = BuildingRetrieval("hospitals", {"amenity": ["hospital"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": elements}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [30])
        self.assertEqual(result.element_type.tolist(), ["relation"])
        self.assertEqual(result.osm_url.iloc[0], "https://www.openstreetmap.org/relation/30")
        self.assertEqual(len(result.geometry.iloc[0].interiors), 1)
        self.assertEqual(set(result.osm_node_ids.iloc[0]), set(range(1, 11)))

    def test_explicit_disabled_target_survives_name_filter(self):
        retrieval = BuildingRetrieval(
            "disability_facilities", {"amenity": ["social_facility"]},
            name_filter_regex="behindert|werkstatt",
        )
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [
            {"type": "node", "id": 31, "lon": 13.0, "lat": 52.0,
             "tags": {"amenity": "social_facility", "name": "Haus Zoar",
                      "social_facility:for": "senior;disabled"}},
            {"type": "node", "id": 32, "lon": 13.0, "lat": 52.0,
             "tags": {"amenity": "social_facility", "name": "Haus Nur Senioren",
                      "social_facility:for": "senior"}},
        ]}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertEqual(result.osm_id.tolist(), [31])

    def test_empty_facility_source_has_exportable_schema(self):
        retrieval = BuildingRetrieval("hospitals", {"amenity": ["hospital"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": []}

        result = retrieval.fetch((52.0, 13.0, 52.1, 13.1))

        self.assertTrue(result.empty)
        self.assertEqual(result.crs.to_string(), "EPSG:4326")
        self.assertTrue({"osm_id", "amenity", "name", "geometry"}.issubset(result.columns))

    def test_missing_way_node_cannot_create_shortcut_facility(self):
        retrieval = BuildingRetrieval("playgrounds", {"leisure": ["playground"]})
        retrieval._fetch_raw_cached = lambda bbox: {"elements": [
            {"type": "node", "id": 1, "lon": 13.0, "lat": 52.0},
            {"type": "node", "id": 3, "lon": 13.01, "lat": 52.0},
            {"type": "way", "id": 40, "nodes": [1, 2, 3],
             "tags": {"leisure": "playground"}},
        ]}
        with self.assertRaisesRegex(ValueError, "Incomplete geometry for OSM way 40"):
            retrieval.fetch((52.0, 13.0, 52.1, 13.1))


if __name__ == "__main__":
    unittest.main()
