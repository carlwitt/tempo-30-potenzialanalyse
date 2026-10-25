"""Retrieve crossing features rather than their geometry support nodes.

An Overpass query for a zebra crossing way includes its member nodes.
Retain only nodes or ways whose own tags establish a zebra crossing;
otherwise a single marked way could create several false crossings.
"""

import requests
import time
from pathlib import Path
from typing import Tuple

import geopandas as gpd
from shapely.geometry import Point, LineString

from DataRetrieval.OSMDataCache import OSMDataCache

class ZebraCrossingRetrieval:
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.datacache = OSMDataCache(datatype = "zebra_crossing")

    def _build_query(self, bbox: Tuple[float, float, float, float]) -> str:
        if(isinstance(bbox, str)):
            return """
            [out:json][timeout:{timeout}];
            (
            area[admin_level=6]["name"="{name}"]->.boundaryarea;
            node["crossing"="zebra"](area.boundaryarea);
            way["crossing"="zebra"](area.boundaryarea);

            node["crossing:markings"="zebra"](area.boundaryarea);
            way["crossing:markings"="zebra"](area.boundaryarea);

            node["crossing_ref"="zebra"](area.boundaryarea);
            way["crossing_ref"="zebra"](area.boundaryarea);
            );
            out body;
            >;
            out skel qt;
            """.format(timeout=self.timeout, name = bbox)
        else:
            south, west, north, east = bbox

            return f"""
            [out:json][timeout:{self.timeout}];
            (
            node["crossing"="zebra"]({south},{west},{north},{east});
            way["crossing"="zebra"]({south},{west},{north},{east});
            node["highway"="crossing"]["crossing"="zebra"]({south},{west},{north},{east});
            way["highway"="crossing"]["crossing"="zebra"]({south},{west},{north},{east});
            node[crossing != "zebra"]["crossing:markings" = "zebra"]({south},{west},{north},{east});
            way[crossing != "zebra"]["crossing:markings" = "zebra"]({south},{west},{north},{east});
            node[crossing_ref = "zebra"]({south},{west},{north},{east});
            way[crossing_ref = "zebra"]({south},{west},{north},{east});
            );
            out body;
            >;
            out skel qt;
            """

    def _fetch_raw_cached(self, bbox: Tuple[float, float, float, float]) -> dict:
        cached_data = self.datacache.load_file_from_cache(bbox)
        if(cached_data is not None):
            print("Using cached data for zebra crossing")
            return cached_data
        else:
            print("Querying OverpassAPI for Zebra Crossings")
            # not cached → query Overpass
            query = self._build_query(bbox)

            data = self._fetch_raw(query=query)

            self.datacache.store_data(data = data, bbox = bbox)

            return data
        
    def _fetch_raw(self, query):
        for attempt in range(0, 6):
            try:
                headers = {
                    'Accept': 'application/json',
                    'Content-Type': 'text/plain',
                    'User-Agent': 'Speed-limit-30-tool', 
                }
                response = requests.post(self.OVERPASS_URL, data={"data": query}, timeout=self.timeout, headers=headers)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException:
                    wait = min(60, 2 ** attempt)
                    print(f"Retrying in {wait}s...")
                    time.sleep(wait)

        raise RuntimeError("Overpass failed")

    def fetch_zebra_crossings(self, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        data = self._fetch_raw_cached(bbox)

        # Nodes sammeln (für Wege)
        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in data["elements"]
            if el["type"] == "node"
        }

        records = []

        for el in data["elements"]:
            tags = el.get("tags", {})

            # The recursive Overpass query also returns nodes used only to
            # construct a crossing way. Keep a feature only if it satisfies
            # one of the zebra predicates from the query itself.
            if not any(tags.get(key) == "zebra" for key in (
                "crossing", "crossing:markings", "crossing_ref"
            )):
                continue
            # Markings or a legacy zebra reference do not establish an
            # unsignalized crossing when a more specific tag disagrees.
            if (tags.get("crossing") in {"no", "unmarked", "traffic_signals"}
                    or tags.get("crossing:markings") in {"no", "none"}):
                continue

            if el["type"] == "node":
                geom = Point(el["lon"], el["lat"])

            elif el["type"] == "way":
                missing = [nid for nid in el.get("nodes", []) if nid not in nodes]
                if missing:
                    raise ValueError(f"Incomplete geometry for OSM way {el['id']}: missing nodes {missing[:5]}")
                coords = [nodes[nid] for nid in el.get("nodes", [])]
                if len(coords) < 2:
                    continue
                geom = LineString(coords)

            else:
                continue

            records.append({
                "osm_id": el["id"],
                "element_type": el["type"],
                "crossing": tags.get("crossing"),
                "highway": tags.get("highway"),
                "name": tags.get("name"),
                "street" : tags.get("addr:street"),
                "geometry": geom
            })

        if(len(records) > 0):
            return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
        else:
            print("No crossings identified")
            return gpd.GeoDataFrame(
                columns=["osm_id", "element_type", "crossing", "highway", "name", "street", "geometry"],
                geometry="geometry", crs="EPSG:4326",
            )
