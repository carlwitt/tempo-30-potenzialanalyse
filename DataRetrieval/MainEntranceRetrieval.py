"""Retrieve OSM nodes explicitly tagged as main entrances."""

import time

import geopandas as gpd
import requests
from shapely.geometry import Point

from DataRetrieval.OSMDataCache import OSMDataCache


class MainEntranceRetrieval:
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, timeout: int = 180):
        self.timeout = timeout
        self.datacache = OSMDataCache(datatype="main_entrances")

    def _build_query(self, bbox: tuple[float, float, float, float] | str) -> str:
        if isinstance(bbox, str):
            area = f'area[admin_level=6]["name"="{bbox}"]->.boundaryarea;'
            scope = "(area.boundaryarea)"
        else:
            area = ""
            south, west, north, east = bbox
            scope = f"({south},{west},{north},{east})"
        return f"""
            [out:json][timeout:{self.timeout}];
            {area}
            (
                node["entrance"="main"]{scope};
                node["routing:entrance"="main"]{scope};
            );
            out body;
        """

    def fetch_as_geodataframe(self, bbox: tuple[float, float, float, float] | str) -> gpd.GeoDataFrame:
        data = self.datacache.load_file_from_cache(bbox)
        if data is None:
            query = self._build_query(bbox)
            for attempt in range(6):
                try:
                    response = requests.post(
                        self.OVERPASS_URL,
                        data={"data": query},
                        timeout=self.timeout,
                        headers={"User-Agent": "Speed-limit-30-tool"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.exceptions.RequestException:
                    if attempt == 5:
                        raise
                    time.sleep(min(60, 2 ** attempt))
            self.datacache.store_data(data, bbox)

        records = [
            {"osm_id": node["id"], "geometry": Point(node["lon"], node["lat"])}
            for node in data["elements"]
            if node["type"] == "node"
            and (node.get("tags", {}).get("entrance") == "main"
                 or node.get("tags", {}).get("routing:entrance") == "main")
        ]
        return gpd.GeoDataFrame(records, columns=["osm_id", "geometry"], geometry="geometry", crs="EPSG:4326")
