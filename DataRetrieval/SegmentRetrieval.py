"""Retrieve OSM road ways and classify their usable speed evidence.

A residential way with no ``maxspeed`` tag is not confirmed Tempo 50;
one with a conditional Tempo-30 rule is not an open candidate either.
Keep the original tags and parsed conditions when building street
segments so gap and facility analyses share the same road facts.
"""

import requests
from typing import Tuple
import geopandas as gpd
from shapely.geometry import LineString
import time
import re

from pathlib import Path

from dataclasses import dataclass
from typing import List, Optional

from DataRetrieval.OSMDataCache import OSMDataCache
from DataRetrieval.RoadClassification import RoadClassification

class SegmentRetrieval:
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.datacache = OSMDataCache(datatype = "streets")

    def _build_query(
        self,
        bbox: Tuple[float, float, float, float] | str
    ) -> str:
        if(isinstance(bbox, str)):
            return """
            [out:json][timeout:{timeout}];
            (
            area[admin_level=6]["name"="{name}"]->.boundaryarea;
            way(area.boundaryarea)["highway"];
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
            way["highway"]
            ({south},{west},{north},{east});
            );
            out body;
            >;
            out skel qt;
            """

    def _fetch_raw(self, query: str) -> dict:
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


    def _fetch_raw_cached(self, bbox: Tuple[float, float, float, float]) -> dict:
        cached_data = self.datacache.load_file_from_cache(bbox)

        if(cached_data is not None):
            print("Using cached data for streets")
            return cached_data
        else:
            print("Quering overpass API for streets...")
            # not cached → query Overpass
            query = self._build_query(bbox)
            data = self._fetch_raw(query)

            self.datacache.store_data(data = data, bbox = bbox)

            return data

    def fetch_as_geodataframe(
        self,
        bbox: Tuple[float, float, float, float],
        crs: str = "EPSG:4326",
        include_nonpublic: bool = False,
        modern_speed_classes: bool = True,
    ) -> gpd.GeoDataFrame:
        data = self._fetch_raw_cached(bbox)

        # Nodes sammeln
        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in data["elements"]
            if el["type"] == "node"
        }

        records = []

        for el in data["elements"]:
            if el["type"] != "way":
                continue

            tags = el.get("tags", {})
            public_motorcar = RoadClassification.allows_public_motorcar(tags)
            if not include_nonpublic and not public_motorcar:
                continue
            # The established speed-context export included nonpublic roads,
            # but excluded these non-road path classes. Preserve that scope.
            if include_nonpublic and tags.get("highway") in {"footway", "cycleway", "path", "steps"}:
                continue

            missing = [nid for nid in el["nodes"] if nid not in nodes]
            if missing:
                raise ValueError(f"Incomplete geometry for OSM way {el['id']}: missing nodes {missing[:5]}")
            coords = [nodes[nid] for nid in el["nodes"]]
            if len(coords) < 2:
                continue
            
            new_entry = create_gdf_entry(
                el, tags["highway"], coords, tags,
                modern_speed_classes=modern_speed_classes,
            )
            new_entry["public_motorcar"] = public_motorcar
           
            records.append(new_entry)

        result_df = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)

        result_df_sorted = result_df.sort_values(by="name", na_position="last")
        return result_df_sorted


def create_gdf_entry(el, highway, coords, tags, modern_speed_classes=True):
    maxspeed = tags.get("maxspeed")
    zone_maxspeed = tags.get("zone:maxspeed")

    max_speed_conditional_str = tags.get("maxspeed:conditional")
    try:
        conditional_speed = parse_conditional_speed(max_speed_conditional_str)
    except (AttributeError, TypeError, ValueError):
        conditional_speed = None
    
    new_entry = {
        "osm_id": el["id"],
        "name": tags.get("name"),
        "highway": highway,
        "service": tags.get("service"),
        "access": tags.get("access"),
        "vehicle": tags.get("vehicle"),
        "motor_vehicle": tags.get("motor_vehicle"),
        "motorcar": tags.get("motorcar"),
        "bicycle_road": tags.get("bicycle_road"),
        "living_street": tags.get("living_street"),
        "public_motorcar": True,
        "maxspeed_tag": maxspeed,
        "maxspeed_conditional_tag": max_speed_conditional_str,
        "zone_maxspeed_tag": zone_maxspeed,
        "maxspeed_type_tag": tags.get("maxspeed:type"),
        "source_maxspeed_tag": tags.get("source:maxspeed"),
        "maxspeed_class": (
            RoadClassification.classify_speed(tags) if modern_speed_classes
            else RoadClassification.classify_speed_legacy(tags)
        ),
        "geometry": LineString(coords)
    }

    if(conditional_speed is None):
        # The detail parser does not cover every valid OSM condition (such as
        # two time ranges or multiple rules). Still recognise a 30 km/h rule
        # so it cannot become an unsupported open facility/gap potential.
        new_entry["conditional_speed"] = (
            "30" if modern_speed_classes and has_conditional_tempo_30(max_speed_conditional_str)
            else None
        )
        new_entry["cond_speed_days"] = None
        new_entry["cond_speed_starttime"] = None
        new_entry["cond_speed_endtime"] = None
        new_entry["cond_speed_special"] = None
    else:
        new_entry["conditional_speed"] = str(conditional_speed.speed)
        new_entry["cond_speed_days"] = str.join(",", conditional_speed.days)
        new_entry["cond_speed_starttime"] = conditional_speed.start_time
        new_entry["cond_speed_endtime"] = conditional_speed.end_time
        new_entry["cond_speed_special"] = str.join(",", conditional_speed.special)

    return new_entry


def has_conditional_tempo_30(raw: str | None) -> bool:
    return isinstance(raw, str) and bool(re.search(r"(?:^|;)\s*30\s*@", raw))



@dataclass
class ConditionalSpeed:
    speed: int
    days: List[str]
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    special: List[str] = None

def parse_conditional_speed(cond_str: str) -> ConditionalSpeed:
    """
    Parse a conditional speed limit string like:
    "Conditional 50 @ (Mo-Fr 18:00-07:00; Sa, Su, PH)"
    """
    # Remove 'Conditional' prefix
    cond_str = cond_str.replace("Conditional", "").strip()
    
    # Split speed and the rest
    try:
        speed_part, period_part = cond_str.split("@")
    except ValueError:
        raise ValueError(f"Cannot parse speed string: {cond_str}")
    
    speed = int(speed_part.strip())
    
    # Remove parentheses and split by ';'
    period_part = period_part.strip().lstrip("(").rstrip(")")
    parts = [p.strip() for p in period_part.split(";")]
    
    days = []
    special = []
    start_time = None
    end_time = None
    
    for p in parts:
        # Check if there is a time range
        if "-" in p and any(day in p for day in ["Mo","Tu","We","Th","Fr","Sa","Su"]):
            # Example: Mo-Fr 18:00-07:00
            day_part, time_part = p.split(" ", 1)
            days.extend([day_part])
            start_time, end_time = time_part.split("-")
        else:
            # Any remaining part is treated as special days
            special.extend([d.strip() for d in p.split(",")])
    
    return ConditionalSpeed(speed=speed, days=days, start_time=start_time, end_time=end_time, special=special)
