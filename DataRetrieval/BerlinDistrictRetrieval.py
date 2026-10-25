"""Retrieve district boundaries from OSM relations, defaulting to Berlin."""

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

    def __init__(self, *, query=None, id_tag="ref:DE-BE:BEZ",
                 cache_key="berlin", cache_datatype="districts_v1"):
        self.query = self.QUERY if query is None else query
        self.id_tag = id_tag
        self.cache_key = cache_key
        self.datacache = OSMDataCache(datatype=cache_datatype)

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
            raise ValueError(f"No polygon for district relation {relation['id']}")
        if lines["inner"]:
            inner = unary_union(list(polygonize(unary_union(lines["inner"]))))
            outer = outer.difference(inner)
        return outer

    def fetch_districts(self) -> gpd.GeoDataFrame:
        data = self.datacache.load_file_from_cache(self.cache_key)
        if data is None:
            response = requests.post(
                self.OVERPASS_URL,
                data={"data": self.query},
                timeout=200,
                headers={"User-Agent": "Speed-limit-30-tool"},
            )
            response.raise_for_status()
            data = response.json()
            self.datacache.store_data(data, self.cache_key)

        records = []
        for relation in data["elements"]:
            tags = relation.get("tags", {})
            district_id = tags.get(self.id_tag)
            if relation["type"] != "relation" or not district_id:
                continue
            records.append({
                "district_id": district_id,
                "district_name": tags["name"],
                "osm_id": relation["id"],
                "geometry": BerlinDistrictRetrieval._polygon(relation),
            })

        if not records:
            raise ValueError(f"No district boundaries found for {self.cache_key}")
        return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
