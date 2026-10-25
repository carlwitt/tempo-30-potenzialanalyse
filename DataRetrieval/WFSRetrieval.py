"""Fetch complete WFS feature layers with their source identity.

A server may cap a Berlin Kita page below the requested size, or interpret
EPSG:4326 axes in the opposite order. Use a projected request, continue
pagination until the dataset ends, and validate before caching; otherwise
facilities can be silently missed or placed outside Berlin.
"""

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import geopandas as gpd
from pyproj import CRS, Transformer
import requests
from shapely.geometry import shape


class WFSRetrieval:
    PROVENANCE_FIELDS = {
        "source_id", "source_feature_id", "source_name", "source_url",
        "source_type_name", "source_license_url",
    }

    def __init__(
        self, url: str, type_name: str, source_name: str,
        request_crs: str = "EPSG:3857", page_size: int = 1000,
        timeout: int = 60, cache_dir: str | Path | None = "overpass_cache/wfs",
        license_url: str | None = None, sort_by: str | None = None,
        max_pages: int = 10000,
    ):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("WFS URL must be an absolute HTTP(S) URL")
        if not type_name.strip() or not source_name.strip():
            raise ValueError("WFS type_name and source_name must not be empty")
        if page_size <= 0 or max_pages <= 0 or timeout <= 0:
            raise ValueError("WFS page_size, max_pages and timeout must be positive")
        # Accept a GetCapabilities URL without carrying its operation into GetFeature.
        operation_keys = {
            "service", "version", "request", "typenames", "typename", "outputformat",
            "srsname", "count", "startindex", "bbox", "sortby",
        }
        query = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in operation_keys]
        self.url = urlunsplit(parsed._replace(query=urlencode(query), fragment=""))
        self.type_name = type_name
        self.source_name = source_name
        self.request_crs = CRS.from_user_input(request_crs)
        # WFS EPSG:4326 uses latitude/longitude axis order on some servers.
        # A projected request CRS avoids silently swapping coordinates.
        if self.request_crs.is_geographic:
            raise ValueError("Use a projected request_crs to avoid WFS geographic axis-order ambiguity")
        self.page_size = page_size
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.license_url = license_url
        self.sort_by = sort_by
        self.max_pages = max_pages

    def _get(self, params):
        response = requests.get(
            self.url, params=params, timeout=self.timeout,
            headers={"User-Agent": "Speed-limit-30-tool", "Accept": "application/json, application/xml"},
        )
        response.raise_for_status()
        if response.content.lstrip().startswith(b"<"):
            root = ET.fromstring(response.content)
            errors = [el.text for el in root.iter()
                      if el.tag.split("}")[-1] in {"ExceptionText", "ServiceException"}]
            if errors:
                raise ValueError(f"WFS {self.source_name}: {'; '.join(filter(None, errors))}")
        return response

    def get_feature_types(self) -> list[dict[str, str | None]]:
        response = self._get({"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"})
        root = ET.fromstring(response.content)
        if root.attrib.get("version") != "2.0.0":
            raise ValueError("Only WFS 2.0.0 is supported")
        namespace = {"wfs": "http://www.opengis.net/wfs/2.0"}
        return [
            {key: feature.findtext(f"wfs:{key}", namespaces=namespace)
             for key in ("Name", "Title", "DefaultCRS")}
            for feature in root.findall(".//wfs:FeatureType", namespace)
        ]

    def _params(self, bbox):
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": self.type_name, "outputFormat": "application/json",
            "srsName": self.request_crs.to_string(), "count": self.page_size,
        }
        if self.sort_by:
            params["sortBy"] = self.sort_by
        if bbox is not None:
            if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
                raise ValueError("bbox must be (south, west, north, east) in WGS84")
            south, west, north, east = bbox
            if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
                raise ValueError("Invalid WGS84 bbox bounds")
            transformer = Transformer.from_crs("EPSG:4326", self.request_crs, always_xy=True)
            bounds = transformer.transform_bounds(west, south, east, north)
            params["bbox"] = ",".join(str(v) for v in bounds) + "," + self.request_crs.to_string()
        return params

    def _download(self, params):
        features = []
        seen = set()
        total = None
        for _ in range(self.max_pages):
            response = self._get({**params, "startIndex": len(features)})
            data = response.json()
            if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
                raise ValueError(f"WFS {self.source_name} did not return a GeoJSON FeatureCollection")
            declared_crs = (data.get("crs") or {}).get("properties", {}).get("name")
            if declared_crs and CRS.from_user_input(declared_crs) != self.request_crs:
                raise ValueError(f"WFS returned unexpected CRS: {declared_crs}")
            matched = data.get("numberMatched", data.get("totalFeatures"))
            if matched not in (None, "unknown"):
                if isinstance(matched, bool) or not str(matched).isdecimal():
                    raise ValueError(f"Invalid WFS numberMatched: {matched}")
                matched = int(matched)
                if total is not None and matched != total:
                    raise ValueError("WFS dataset changed during pagination; retry with refresh=True")
                total = matched
            page = data.get("features")
            if not isinstance(page, list):
                raise ValueError("WFS GeoJSON features must be a list")
            if not page:
                if total is not None and len(features) != total:
                    raise ValueError(f"Incomplete WFS response: {len(features)} of {total} features")
                return features
            for feature in page:
                feature_id = feature.get("id")
                if not isinstance(feature_id, (str, int)) or isinstance(feature_id, bool) or str(feature_id) == "":
                    raise ValueError("WFS feature is missing a stable GeoJSON id")
                feature_id = str(feature_id)
                if feature_id in seen:
                    raise ValueError(f"Duplicate WFS id {feature_id}; server may not support pagination")
                seen.add(feature_id)
                features.append(feature)
            if total is not None:
                if len(features) > total:
                    raise ValueError("WFS returned more features than numberMatched")
                if len(features) == total:
                    return features
            # With an unknown total, request an empty page rather than assuming
            # a short page means completion: servers can cap count themselves.
        raise ValueError(f"WFS pagination exceeded {self.max_pages} pages")

    def fetch(self, bbox=None, crs: str = "EPSG:4326", refresh: bool = False) -> gpd.GeoDataFrame:
        """bbox follows repository order (south, west, north, east), or None for all."""
        params = self._params(bbox)
        cache = None
        if self.cache_dir is not None:
            identity = json.dumps({"cache_version": 1, "url": self.url, "params": params}, sort_keys=True)
            key = hashlib.sha256(identity.encode()).hexdigest()
            cache = self.cache_dir / f"{key}.json"
        if cache is not None and cache.exists() and not refresh:
            print(f"Using cached WFS data for {self.source_name}")
            features = json.loads(cache.read_text(encoding="utf-8"))
        else:
            features = self._download(params)
            # Validate before persisting; no partial download becomes a valid cache.
            self._frame(features, crs)
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(features, ensure_ascii=False), encoding="utf-8")
        return self._frame(features, crs)

    def _frame(self, features, crs):
        records = []
        for feature in features:
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("WFS feature properties must be an object")
            if self.PROVENANCE_FIELDS.intersection(properties) or "geometry" in properties:
                raise ValueError("WFS attributes conflict with reserved geometry/provenance fields")
            if not feature.get("geometry"):
                raise ValueError(f"Missing geometry for WFS feature {feature.get('id')}")
            geometry = shape(feature["geometry"])
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError(f"Invalid geometry for WFS feature {feature.get('id')}")
            feature_id = str(feature["id"])
            records.append({
                **properties, "geometry": geometry,
                "source_id": f"{self.source_name}:{self.type_name}:{feature_id}",
                "source_feature_id": feature_id, "source_name": self.source_name,
                "source_url": self.url, "source_type_name": self.type_name,
                "source_license_url": self.license_url,
            })
        if not records:
            return gpd.GeoDataFrame(
                columns=[*sorted(self.PROVENANCE_FIELDS), "geometry"],
                geometry="geometry", crs=self.request_crs,
            ).to_crs(crs)
        return gpd.GeoDataFrame(records, geometry="geometry", crs=self.request_crs).to_crs(crs)
