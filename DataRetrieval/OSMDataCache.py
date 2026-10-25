"""Cache complete Overpass responses for repeatable local analysis.

An Overpass timeout may return JSON with a ``remark`` but an incomplete
``elements`` list. Validate before saving and after loading, so a partial
Berlin road or facility query cannot silently become the analysis input.
"""

from typing import Tuple
import hashlib
from pathlib import Path
import json

class OSMDataCache:
    def __init__(self, datatype, cache_dir: str = "./overpass_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.datatype = datatype

    def load_file_from_cache(self, bbox):
        cache_file = self._cache_path(bbox)

        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._validate(data)
            return data
        
        return None

    def _bbox_cache_key(self, bbox: Tuple[float, float, float, float]) -> str:
        if(not isinstance(bbox, str)):
            bbox_str = "_".join(f"{v:.6f}" for v in bbox)
        else:
            bbox_str = bbox
        return hashlib.md5(bbox_str.encode("utf-8")).hexdigest()

    def _cache_path(self : str, bbox: Tuple[float, float, float, float]) -> Path:
        return self.cache_dir / f"{self.datatype}_{self._bbox_cache_key(bbox)}.json"
    
    def store_data(self, data, bbox):
        self._validate(data)
        cache_file = self._cache_path(bbox)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
            raise ValueError("Invalid Overpass response: missing elements list")
        if data.get("remark"):
            raise ValueError(f"Incomplete Overpass response: {data['remark']}")
