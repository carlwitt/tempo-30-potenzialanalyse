"""Retrieve OSM facilities without treating query support nodes as places.

An Overpass way query also returns nodes used only to draw its geometry.
Build the facility from those nodes, then keep only objects matching the
requested tags (for example ``amenity=kindergarten``). This avoids
counting a school's outline nodes as additional schools.
"""

import re
import requests
import time
import geopandas as gpd

from typing import Tuple, Optional, List, Dict

from shapely.geometry import Point, LineString, Polygon
from shapely.ops import polygonize, unary_union

from DataRetrieval.OSMDataCache import OSMDataCache


class BuildingRetrieval:
    """Fetch tagged OSM nodes and ways, using support nodes only for geometry."""

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
    @staticmethod
    def _relation_geometry(relation, ways, nodes):
        if relation.get("tags", {}).get("type") != "multipolygon":
            return None, []
        outlines = {"outer": [], "inner": []}
        member_nodes = []
        for member in relation.get("members", []):
            if member.get("type") != "way" or member.get("role") not in outlines:
                continue
            way = ways.get(member["ref"])
            if way is None or any(node_id not in nodes for node_id in way["nodes"]):
                raise ValueError(f"Incomplete geometry for OSM relation {relation['id']}")
            member_nodes.extend(way["nodes"])
            outlines[member["role"]].append(LineString([nodes[node_id] for node_id in way["nodes"]]))
        if not outlines["outer"]:
            raise ValueError(f"OSM relation {relation['id']} has no outer ways")
        outer = list(polygonize(unary_union(outlines["outer"])))
        inner = list(polygonize(unary_union(outlines["inner"]))) if outlines["inner"] else []
        if not outer:
            raise ValueError(f"Cannot polygonize OSM relation {relation['id']}")
        geometry = unary_union(outer)
        if inner:
            geometry = geometry.difference(unary_union(inner))
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"Invalid geometry for OSM relation {relation['id']}")
        return geometry, list(dict.fromkeys(member_nodes))

    def fetch(self, bbox) -> Optional[gpd.GeoDataFrame]:
        data = self._fetch_raw_cached(bbox)

        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in data["elements"]
            if el["type"] == "node"
        }
        ways = {el["id"]: el for el in data["elements"] if el["type"] == "way"}

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
                missing = [node_id for node_id in el.get("nodes", []) if node_id not in nodes]
                if missing:
                    raise ValueError(f"Incomplete geometry for OSM way {el['id']}: missing nodes {missing[:5]}")
                coords = [nodes[node_id] for node_id in el.get("nodes", [])]

                if len(coords) < 2:
                    continue

                if coords[0] == coords[-1] and len(coords) >= 3:
                    geom = Polygon(coords)
                else:
                    geom = LineString(coords)

            elif el["type"] == "relation":
                geom, relation_node_ids = self._relation_geometry(el, ways, nodes)
                if geom is None:
                    continue

            else:
                continue

            # ---------------- Name filter ----------------
            name = tags.get("name")
            if self.name_filter_regex:
                target_groups = {
                    group.strip().casefold()
                    for group in re.split(r"[;,]", tags.get("social_facility:for", ""))
                }
                if "disabled" not in target_groups and (
                    name is None or not self.name_filter_regex.search(name)
                ):
                    continue

            # ---------------- Record ----------------
            record = {
                "osm_id": el["id"],
                "element_type": el["type"],
                "osm_node_ids": relation_node_ids if el["type"] == "relation" else el.get("nodes", []),
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

        columns = [
            "osm_id", "element_type", "osm_node_ids", "osm_url", "name",
            "official_name", "alt_name", "short_name", "amenity", "healthcare",
            "social_facility", "social_facility_for", "street", "housenumber",
            "website", "operator", "geometry",
        ]
        if not records:
            print("No results found.")
        return gpd.GeoDataFrame(records, columns=columns, geometry="geometry", crs="EPSG:4326")
