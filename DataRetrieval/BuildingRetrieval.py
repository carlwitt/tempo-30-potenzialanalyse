import re
import requests
import time
import geopandas as gpd

from typing import Tuple, Optional, List, Dict

from shapely.geometry import Point, LineString, Polygon

from DataRetrieval.OSMDataCache import OSMDataCache


class BuildingRetrieval:
    """
    Retrieve tagged OSM facilities and their geometry via Overpass.
    """

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(
        self,
        datatype: str,
        tags: Dict[str, List[str]],
        name_filter_regex: Optional[str] = None,
        senior_assisted_living_only: bool = False,
        timeout: int = 60,
    ):
        self.tags = tags
        self.timeout = timeout
        self.senior_assisted_living_only = senior_assisted_living_only
        self.name_filter_regex = (
            re.compile(name_filter_regex, re.IGNORECASE)
            if name_filter_regex
            else None
        )

        self.datacache = OSMDataCache(datatype=datatype)

    # ------------------------------------------------------------------
    # Query builder
    # ------------------------------------------------------------------
    def _build_query(self, bbox: Tuple[float, float, float, float]) -> str:
        def build_blocks(bbox_str):
            blocks = []
            for key, values in self.tags.items():
                regex = "|".join(values)

                blocks.append(f'node["{key}"~"{regex}"]{bbox_str};')
                blocks.append(f'way["{key}"~"{regex}"]{bbox_str};')
                blocks.append(f'relation["{key}"~"{regex}"]{bbox_str};')

            return "\n".join(blocks)

        if isinstance(bbox, str):
            return f"""
            [out:json][timeout:{self.timeout}];
            (
            area[admin_level=6]["name"="{bbox}"]->.boundaryarea;
            {build_blocks("(area.boundaryarea)")}
            );
            out tags body;
            >;
            out skel qt;
            """
        else:
            south, west, north, east = bbox
            bbox_str = f"({south},{west},{north},{east})"

            return f"""
            [out:json][timeout:{self.timeout}];
            (
            {build_blocks(bbox_str)}
            );
            out tags body;
            >;
            out skel qt;
            """

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    def _fetch_raw_cached(self, bbox):
        cached = self.datacache.load_file_from_cache(bbox)

        if cached is not None:
            print(f"Using cached data for {self.datacache.datatype}")
            return cached
        else:
            print(f"Querying Overpass API for {self.datacache.datatype}...")
            query = self._build_query(bbox)

            data = self._fetch_raw(query=query)
            self.datacache.store_data(data=data, bbox=bbox)

            return data
        
    def _fetch_raw(self, query : str):
        for attempt in range(6):
            try:
                headers = {
                    'Accept': 'application/json',
                    'Content-Type': 'text/plain',
                    'User-Agent': 'Speed-limit-30-tool', 
                }

                response = requests.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    timeout=self.timeout,
                    headers=headers
                )
                response.raise_for_status()

                return response.json()

            except requests.exceptions.RequestException:
                wait = min(60, 2 ** attempt)
                print(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise RuntimeError("Overpass failed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch(self, bbox) -> Optional[gpd.GeoDataFrame]:
        data = self._fetch_raw_cached(bbox)

        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in data["elements"]
            if el["type"] == "node"
        }

        records = []

        for el in data["elements"]:
            tags = el.get("tags", {})

            # Recursive Overpass results also contain geometry support nodes.
            if not any(tags.get(key) in values for key, values in self.tags.items()):
                continue

            # Assisted living also covers non-senior groups; keep only explicit senior sites.
            if self.senior_assisted_living_only and tags.get("social_facility") == "assisted_living":
                groups = {group.strip() for group in re.split(r"[;,]", tags.get("social_facility:for", ""))}
                if "senior" not in groups:
                    continue

            # ---------------- Geometry ----------------
            if el["type"] == "node":
                geom = Point(el["lon"], el["lat"])

            elif el["type"] == "way":
                coords = [nodes[n] for n in el.get("nodes", []) if n in nodes]

                if len(coords) < 2:
                    continue

                if coords[0] == coords[-1] and len(coords) >= 3:
                    geom = Polygon(coords)
                else:
                    geom = LineString(coords)

            else:
                continue

            # ---------------- Name filter ----------------
            name = tags.get("name")
            if self.name_filter_regex:
                if name is None or not self.name_filter_regex.search(name):
                    continue

            # ---------------- Record ----------------
            record = {
                "osm_id": el["id"],
                "element_type": el["type"],
                "osm_node_ids": el.get("nodes", []),
                "osm_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                "name": name,
                "official_name": tags.get("official_name"),
                "alt_name": tags.get("alt_name"),
                "short_name": tags.get("short_name"),
                "amenity": tags.get("amenity"),
                "healthcare": tags.get("healthcare"),
                "social_facility": tags.get("social_facility"),
                "social_facility_for": tags.get("social_facility:for"),
                "street": tags.get("addr:street"),
                "housenumber": tags.get("addr:housenumber"),
                "website": tags.get("website") or tags.get("contact:website"),
                "operator": tags.get("operator"),
                "geometry": geom,
            }


            records.append(record)

        if not records:
            print("No results found.")
            return None

        return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
