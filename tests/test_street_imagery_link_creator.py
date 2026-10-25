"""A facility entrance can be closer to the relevant road than its center. Check
street snapping, distance limits and entrance selection so imagery links do
not point at an unrelated road.
"""

import unittest
from datetime import date

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from DataOutput.StreetImageryLinkCreator import StreetImageryLinkCreator


class StreetImageryLinkCreatorTests(unittest.TestCase):
    def test_links_snap_points_lines_and_polygons_to_nearest_t50_street(self):
        features = gpd.GeoDataFrame(
            {"description": ["Existing note", None, ""]},
            geometry=[
                Point(10, 5),
                LineString([(10, 16), (10, 22)]),
                Polygon([(5, 4), (7, 4), (7, 6), (5, 6)]),
            ],
            crs="EPSG:3857",
        )
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T50+", "T50+"]},
            geometry=[
                LineString([(0, 0), (20, 0)]),
                LineString([(0, 20), (20, 20)]),
            ],
            crs="EPSG:3857",
        )

        result = StreetImageryLinkCreator.add_links(features, streets, date(2024, 1, 1))

        snapped = gpd.GeoSeries(
            [Point(10, 0), Point(10, 20), Point(6, 0)], crs="EPSG:3857"
        ).to_crs("EPSG:4326")
        links = []
        for point in snapped:
            street_view = f"[[https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={point.y:.7f}%2C{point.x:.7f}|Google Street View]]"
            mapillary = f"[[https://www.mapillary.com/app/?lat={point.y:.7f}&lng={point.x:.7f}&z=17&dateFrom=2024-01-01|Mapillary]]"
            links.append(f"{street_view}\n{mapillary}")
        self.assertEqual(result.description.tolist(), [f"Existing note\n{links[0]}", links[1], links[2]])
        self.assertEqual(
            result.google_street_view_url.iloc[0],
            f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={snapped.iloc[0].y:.7f}%2C{snapped.iloc[0].x:.7f}",
        )
        self.assertIn("dateFrom=2024-01-01", result.mapillary_url.iloc[0])
        self.assertTrue(result.geometry.equals(features.geometry))
        self.assertEqual(result.crs, features.crs)
        self.assertEqual(features.description.iloc[0], "Existing note")
        self.assertTrue(features.description.isna().iloc[1])
        self.assertEqual(features.description.iloc[2], "")

    def test_empty_streets_leave_photo_links_empty(self):
        features = gpd.GeoDataFrame(geometry=[Point(10, 5)], crs="EPSG:3857")
        streets = gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")
        streets["maxspeed_class"] = []

        result = StreetImageryLinkCreator.add_links(features, streets)
        self.assertIsNone(result.google_street_view_url.iloc[0])
        self.assertIsNone(result.mapillary_url.iloc[0])

    def test_does_not_fall_back_to_t30_street(self):
        features = gpd.GeoDataFrame(geometry=[Point(10, 5)], crs="EPSG:3857")
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T30-", "Conditional-T30"]},
            geometry=[LineString([(0, 0), (20, 0)]), LineString([(0, 20), (20, 20)])],
            crs="EPSG:3857",
        )

        result = StreetImageryLinkCreator.add_links(features, streets)
        self.assertIsNone(result.google_street_view_url.iloc[0])
        self.assertIsNone(result.mapillary_url.iloc[0])

    def test_skips_closer_campus_road(self):
        features = gpd.GeoDataFrame(geometry=[Point(10, 5)], crs="EPSG:3857")
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["Keine Daten", "T50+"]},
            geometry=[
                LineString([(0, 4), (20, 4)]),
                LineString([(0, 20), (20, 20)]),
            ],
            crs="EPSG:3857",
        )

        result = StreetImageryLinkCreator.add_links(features, streets, date(2024, 1, 1))

        point = gpd.GeoSeries([Point(10, 20)], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
        self.assertIn(f"viewpoint={point.y:.7f}%2C{point.x:.7f}", result.description.iloc[0])
        self.assertIn(f"lat={point.y:.7f}&lng={point.x:.7f}", result.description.iloc[0])

    def test_distant_t50_street_does_not_create_misleading_photo_link(self):
        features = gpd.GeoDataFrame(
            {"description": ["Prüfhinweis"], "osm_node_ids": [[]]},
            geometry=[Point(10, 150)], crs="EPSG:3857",
        )
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T50+"]},
            geometry=[LineString([(0, 0), (20, 0)])], crs="EPSG:3857",
        )

        result = StreetImageryLinkCreator.add_links(
            features, streets, date(2024, 1, 1),
            main_entrances=gpd.GeoDataFrame(
                {"osm_id": []}, geometry=[], crs="EPSG:3857",
            ),
        )

        self.assertIsNone(result.google_street_view_url.iloc[0])
        self.assertIsNone(result.mapillary_url.iloc[0])
        self.assertIn("keine Tempo-50/60-Straße innerhalb von 100 m", result.description.iloc[0])

    def test_uses_only_main_entrances_on_the_osm_way(self):
        features = gpd.GeoDataFrame(
            {"osm_node_ids": [[1, 2], [4]]},
            geometry=[
                Polygon([(5, 5), (15, 5), (15, 17), (5, 17)]),
                Polygon([(30, 5), (40, 5), (40, 15), (30, 15)]),
            ],
            crs="EPSG:3857",
        )
        entrances = gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3]},
            geometry=[Point(5, 5), Point(15, 17), Point(10, 15)],
            crs="EPSG:3857",
        )
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T50+", "T50+"]},
            geometry=[LineString([(0, 0), (50, 0)]), LineString([(0, 20), (50, 20)])],
            crs="EPSG:3857",
        )

        result = StreetImageryLinkCreator.add_links(
            features, streets, date(2024, 1, 1), main_entrances=entrances
        )

        entrance_view = gpd.GeoSeries([Point(15, 20)], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
        self.assertIn(f"viewpoint={entrance_view.y:.7f}%2C{entrance_view.x:.7f}", result.description.iloc[0])
        self.assertEqual(result.imagery_reference.iloc[0], "OSM-Haupteingang auf Objektgrenze")
        self.assertIn("kein OSM-Haupteingang", result.description.iloc[1])
        self.assertEqual(result.geometry.geom_type.tolist(), ["Polygon", "Polygon"])

    def test_uses_contained_entrance_for_facility_area_but_not_playground(self):
        features = gpd.GeoDataFrame(
            {"osm_node_ids": [[1]]},
            geometry=[Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])],
            crs="EPSG:3857",
        )
        entrances = gpd.GeoDataFrame(
            {"osm_id": [2]}, geometry=[Point(15, 15)], crs="EPSG:3857",
        )
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T50+"]},
            geometry=[LineString([(0, 25), (20, 25)])], crs="EPSG:3857",
        )

        facility = StreetImageryLinkCreator.add_links(
            features, streets, date(2024, 1, 1), main_entrances=entrances
        )
        playground = StreetImageryLinkCreator.add_links(
            features, streets, date(2024, 1, 1), main_entrances=entrances,
            use_area_entrances=False,
        )

        self.assertIn("im Areal; Zuordnung angenähert", facility.imagery_reference.iloc[0])
        self.assertIn("kein OSM-Haupteingang", playground.imagery_reference.iloc[0])

    def test_default_mapillary_filter_starts_two_calendar_years_ago(self):
        features = gpd.GeoDataFrame(geometry=[Point(10, 5)], crs="EPSG:3857")
        streets = gpd.GeoDataFrame(
            {"maxspeed_class": ["T50+"]},
            geometry=[LineString([(0, 0), (20, 0)])], crs="EPSG:3857"
        )

        result = StreetImageryLinkCreator.add_links(features, streets)

        since = date(date.today().year - 2, 1, 1)
        self.assertIn(f"&dateFrom={since.isoformat()}|Mapillary]]", result.description.iloc[0])


if __name__ == "__main__":
    unittest.main()
