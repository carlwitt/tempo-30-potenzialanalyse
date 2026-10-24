import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point

from DataOutput.FacilityPopupCreator import FacilityPopupCreator


class FacilityPopupCreatorTests(unittest.TestCase):
    @staticmethod
    def empty_segments():
        return gpd.GeoDataFrame(
            columns=["facility_layer", "facility_id", "street_osm_id", "geometry"],
            geometry="geometry", crs="EPSG:4326",
        )

    def test_kita_popup_uses_linked_title_operator_and_one_photo_line(self):
        street_view = "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=52.5397309%2C13.4201186"
        mapillary = "https://www.mapillary.com/app/?lat=52.5397309&lng=13.4201186&z=17&dateFrom=2024-01-01"
        facilities = gpd.GeoDataFrame(
            {
                "osm_id": [268916255], "name": ["Evangelische Kita Elias"],
                "osm_url": ["https://www.openstreetmap.org/node/268916255"],
                "operator": ["Evangelischer Kirchenkreisverband für Kindertageseinrichtungen Berlin Mitte-Nord"],
                "potential_candidate": [False],
                "google_street_view_url": [street_view], "mapillary_url": [mapillary],
            },
            geometry=[Point(13.42, 52.54)], crs="EPSG:4326",
        )

        result = FacilityPopupCreator.create(
            facilities, "educational_buildings", self.empty_segments(), self.empty_segments()
        )

        self.assertEqual(result.popup_content.iloc[0], (
            "[[https://www.openstreetmap.org/node/268916255|Evangelische Kita Elias]]\n\n"
            "Betreiber: Evangelischer Kirchenkreisverband für Kindertageseinrichtungen Berlin Mitte-Nord\n\n"
            f"Fotos vor Ort: [[{street_view}|Google Street View]] [[{mapillary}|Mapillary]]"
        ))
        self.assertNotIn("popup_content", facilities)

    def test_potential_popup_retains_reason_and_matched_street(self):
        facilities = gpd.GeoDataFrame(
            {
                "osm_id": [7], "name": [None], "facility_type": ["Kindertagesstätte"],
                "osm_url": ["https://www.openstreetmap.org/way/7"],
                "potential_candidate": [True], "potential_reason": ["Tempo 50 in der Nähe."],
                "google_street_view_url": ["https://example.org/streetview"],
                "mapillary_url": ["https://example.org/mapillary"],
            },
            geometry=[Point(13.42, 52.54)], crs="EPSG:4326",
        )
        proposed = gpd.GeoDataFrame(
            {
                "facility_layer": ["educational_buildings"], "facility_id": [7],
                "street_osm_id": [11], "street_osm_url": ["https://www.openstreetmap.org/way/11"],
                "street_name": ["Schulstraße"], "current_speed_kmh": [50], "distance_m": [12.4],
            },
            geometry=[LineString([(13.42, 52.54), (13.421, 52.54)])], crs="EPSG:4326",
        )

        result = FacilityPopupCreator.create(
            facilities, "educational_buildings", proposed, self.empty_segments()
        )

        popup = result.popup_content.iloc[0]
        self.assertIn("[[https://www.openstreetmap.org/way/7|Kindertagesstätte]]", popup)
        self.assertIn("Tempo 50 in der Nähe.", popup)
        self.assertIn("[[https://www.openstreetmap.org/way/11|Schulstraße]] — aktuell 50 km/h; Abstand 12.4 m", popup)
        self.assertIn("Fotos vor Ort:", popup)
        self.assertNotIn("Betreiber:", popup)


if __name__ == "__main__":
    unittest.main()
