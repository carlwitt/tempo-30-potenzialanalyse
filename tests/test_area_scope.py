"""A Berlin bounding box also contains Brandenburg objects and roads. Check
source assignment, border clipping and complete gap roads so outside anchors
cannot create invisible connections.
"""

import unittest
import warnings

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from PotentialCalculation.AreaScope import AreaScope


class AreaScopeTests(unittest.TestCase):
    def test_sources_use_representative_point_in_district_area(self):
        districts = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:25832",
        )
        features = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3]},
            geometry=[Point(5, 5), Point(12, 5), Polygon([(8, 2), (12, 2), (12, 8), (8, 8)])],
            crs=districts.crs,
        )

        result = AreaScope.filter_sources(features, districts)

        self.assertEqual(result.osm_id.tolist(), [1, 3])
        self.assertEqual(features.osm_id.tolist(), [1, 2, 3])

    def test_export_geometry_is_clipped_to_district(self):
        districts = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            {"osm_id": [1, 2]},
            geometry=[LineString([(-5, 5), (15, 5)]), LineString([(20, 5), (30, 5)])],
            crs=districts.crs,
        )

        result = AreaScope.clip_geometries(streets, districts)

        self.assertEqual(result.osm_id.tolist(), [1])
        self.assertAlmostEqual(result.geometry.iloc[0].length, 10)

    def test_mixed_layer_keeps_source_geometry_types(self):
        districts = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:25832",
        )
        features = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3]},
            geometry=[Point(5, 5), Polygon([(8, 2), (12, 2), (12, 8), (8, 8)]),
                      LineString([(-5, 5), (15, 5)])], crs=districts.crs,
        )

        with warnings.catch_warnings(record=True) as emitted:
            result = AreaScope.clip_geometries(features, districts)

        self.assertEqual(result.osm_id.tolist(), [1, 2, 3])
        self.assertEqual(result.geometry.geom_type.tolist(), ["Point", "Polygon", "LineString"])
        self.assertFalse(emitted)

    def test_gap_network_excludes_boundary_crossings_and_external_anchors(self):
        districts = gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])],
            crs="EPSG:25832",
        )
        streets = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3]},
            geometry=[LineString([(1, 5), (9, 5)]),
                      LineString([(9, 5), (11, 5)]),
                      LineString([(11, 5), (12, 5)])],
            crs=districts.crs,
        )

        result = AreaScope.filter_complete_network(streets, districts)

        self.assertEqual(result.osm_id.tolist(), [1])
        self.assertEqual(streets.osm_id.tolist(), [1, 2, 3])
