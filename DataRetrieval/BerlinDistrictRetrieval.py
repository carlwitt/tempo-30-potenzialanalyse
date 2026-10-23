"""Retrieve Berlin Bezirk boundaries from OSM relations."""

import geopandas as gpd
import requests
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from DataRetrieval.OSMDataCache import OSMDataCache


class BerlinDistrictRetrieval:
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    QUERY = """
        [out:json][timeout:180];
        relation["boundary"="administrative"]["admin_level"="9"]["ref:DE-BE:BEZ"];
        out geom;
    """

    def __init__(self):
        self.datacache = OSMDataCache(datatype="districts_v1")

    @staticmethod
    def _polygon(relation):
        lines = {"outer": [], "inner": []}
        for member in relation.get("members", []):
            role = member.get("role")
            coords = member.get("geometry", [])
            if role in lines and len(coords) >= 2:
                lines[role].append(LineString([(point["lon"], point["lat"]) for point in coords]))

        outer = unary_union(list(polygonize(unary_union(lines["outer"]))))
        if outer.is_empty:
            raise ValueError(f"No polygon for Berlin district relation {relation['id']}")
        if lines["inner"]:
            inner = unary_union(list(polygonize(unary_union(lines["inner"]))))
            outer = outer.difference(inner)
        return outer

    def fetch_districts(self) -> gpd.GeoDataFrame:
        data = self.datacache.load_file_from_cache("berlin")
        if data is None:
            response = requests.post(
                self.OVERPASS_URL,
                data={"data": self.QUERY},
                timeout=200,
                headers={"User-Agent": "Speed-limit-30-tool"},
            )
            response.raise_for_status()
            data = response.json()
            self.datacache.store_data(data, "berlin")

        records = []
        for relation in data["elements"]:
            tags = relation.get("tags", {})
            district_id = tags.get("ref:DE-BE:BEZ")
            if relation["type"] != "relation" or not district_id:
                continue
            records.append({
                "district_id": district_id,
                "district_name": tags["name"],
                "osm_id": relation["id"],
                "geometry": BerlinDistrictRetrieval._polygon(relation),
            })

        if not records:
            raise ValueError("No Berlin district boundaries found")
        return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
