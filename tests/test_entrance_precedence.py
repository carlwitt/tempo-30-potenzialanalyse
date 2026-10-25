"""A mapped facility access must beat a fast road along a wall."""

import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from DataOutput.FacilityPopupCreator import FacilityPopupCreator
from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from PotentialCalculation.EntranceEvidence import EntranceEvidence
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult
from PotentialCalculation.ProximityPotential import ProximityPotential


class EntrancePrecedenceTests(unittest.TestCase):
    def test_mapped_entrance_selects_access_street_before_building_edge(self):
        streets = gpd.GeoDataFrame(
            {
                "osm_id": [1, 2], "name": ["Mauerstraße", "Eingangsstraße"],
                "highway": ["residential", "residential"],
                "maxspeed_class": ["50", "50"],
                "conditional_speed": [None, None],
                "public_motorcar": [True, True],
            },
            geometry=[LineString([(0, -2), (100, -2)]), LineString([(0, 22), (100, 22)])],
            crs="EPSG:25832",
        )
        facility = gpd.GeoDataFrame(
            {"osm_id": [10], "osm_node_ids": [[1000]]},
            geometry=[box(0, 0, 100, 20)], crs="EPSG:25832",
        )
        entrances = gpd.GeoDataFrame(
            {"osm_id": [1000]}, geometry=[Point(50, 20)], crs="EPSG:25832",
        )

        legacy = ProximityPotential.find_tempo50_segments_near_features(
            streets, facility, search_distance_m=5, prefer_main_entrances=False,
        )
        with_entrance = ProximityPotential.find_tempo50_segments_near_features(
            streets, facility, search_distance_m=5, main_entrances=entrances,
            prefer_main_entrances=True,
        )
        without_entrance = ProximityPotential.find_tempo50_segments_near_features(
            streets, facility, search_distance_m=5, main_entrances=entrances.iloc[0:0],
            prefer_main_entrances=True,
        )
        area_facility = facility.copy()
        area_facility.at[0, "osm_node_ids"] = []
        entrance_in_area = ProximityPotential.find_tempo50_segments_near_features(
            streets, area_facility, search_distance_m=5, main_entrances=entrances,
            prefer_main_entrances=True,
        )
        area_matching_disabled = ProximityPotential.find_tempo50_segments_near_features(
            streets, area_facility, search_distance_m=5, main_entrances=entrances,
            prefer_main_entrances=True, use_area_entrances=False,
        )
        wall_only = ProximityPotential.find_tempo50_segments_near_features(
            streets.iloc[[0]], facility, search_distance_m=5, main_entrances=entrances,
            prefer_main_entrances=True,
        )

        self.assertEqual(set(legacy.street_ids), {1, 2})
        self.assertEqual(set(with_entrance.street_ids), {2})
        self.assertEqual(set(without_entrance.street_ids), {1, 2})
        self.assertEqual(set(entrance_in_area.street_ids), {2})
        self.assertEqual(set(area_matching_disabled.street_ids), {1, 2})
        self.assertEqual(wall_only.street_ids, [])

    def test_potential_popup_links_the_mapped_entrance_for_review(self):
        facility = gpd.GeoDataFrame(
            {"osm_id": [10], "name": ["Kita"], "facility_type": ["Kindergarten"],
             "potential_candidate": [True], "main_entrance_osm_ids": [[1000]],
             "imagery_reference": ["OSM-Haupteingang auf Objektgrenze"]},
            geometry=[Point(0, 0)], crs="EPSG:25832",
        )
        empty_segments = gpd.GeoDataFrame({"facility_layer": []}, geometry=[], crs="EPSG:25832")
        result = FacilityPopupCreator.create(
            facility, "educational_buildings", empty_segments, empty_segments,
        )
        self.assertIn("https://www.openstreetmap.org/node/1000", result.popup_content.iloc[0])

    def test_proposed_street_clip_and_distance_follow_the_entrance(self):
        street = gpd.GeoDataFrame(
            {"osm_id": [2], "name": ["Eingangsstraße"], "maxspeed_class": ["50"]},
            geometry=[LineString([(0, 22), (100, 22)])], crs="EPSG:25832",
        )
        facility = gpd.GeoDataFrame(
            {"osm_id": [10], "name": ["Kita"], "osm_node_ids": [[1000]]},
            geometry=[box(0, 0, 100, 20)], crs="EPSG:25832",
        )
        entrances = gpd.GeoDataFrame(
            {"osm_id": [1000]}, geometry=[Point(50, 20)], crs="EPSG:25832",
        )
        preferred, matched = EntranceEvidence.preferred_geometry(facility, entrances)
        preferred["street_reference"] = ["OSM-Haupteingang" if i in matched else None
                                         for i in preferred.index]
        potential = {"educational_buildings": PotentialCalculationResult(
            street_ids=[2], opt_source_ids=[10], source_street_pairs=[(10, 2)],
        )}

        old_clip = FacilityStreetSegments.create(street, {"educational_buildings": facility}, potential)
        access_clip = FacilityStreetSegments.create(street, {"educational_buildings": preferred}, potential)

        self.assertGreater(old_clip.geometry.length.iloc[0], access_clip.geometry.length.iloc[0])
        self.assertEqual(access_clip.distance_m.iloc[0], 2.0)
        self.assertEqual(access_clip.distance_reference.iloc[0], "OSM-Haupteingang")
        self.assertEqual(access_clip.main_entrance_osm_ids.iloc[0], [1000])


if __name__ == "__main__":
    unittest.main()
