"""Add official facility records without duplicating uncertain OSM matches.

An official Berlin Kita may already exist in OSM under a slightly different
name. Match by strong address, name or containment evidence, preserve both
source identities, and leave ambiguous matches unresolved. This supplies
missing Kitas while preventing nearby but different places from merging.
"""

import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import pandas as pd

from DataRetrieval.WFSRetrieval import WFSRetrieval


def facility_url(feature):
    osm = feature.get("osm_url")
    return osm if isinstance(osm, str) and osm else feature.get("source_url")


class AdditionalFeatures:
    CONFIG = Path(__file__).resolve().parents[1] / "additional_features.json"

    @staticmethod
    def _normalized(value):
        if not isinstance(value, str):
            return ""
        text = value.lower().replace("ß", "ss").replace("straße", "str").replace("strasse", "str")
        return re.sub(r"[^a-z0-9äöü]", "", text)

    @staticmethod
    def merge(osm, external, tags):
        if not tags or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tags.items()):
            raise ValueError("Additional feature tags must map OSM tag names to string values")
        tag_columns = {key.replace(":", "_"): value for key, value in tags.items()}
        result = osm.copy().reset_index(drop=True)
        external = external.to_crs(osm.crs)
        if external.source_id.duplicated().any():
            raise ValueError("Additional features contain duplicate source_id values")
        metric = result.to_crs("EPSG:25832")
        incoming = external.to_crs("EPSG:25832")

        def count(frame):
            mask = pd.Series(True, index=frame.index)
            for column, value in tag_columns.items():
                mask &= frame[column].eq(value) if column in frame else False
            return int(mask.sum())

        stats = {"before": count(result),
                 "external": len(external), "matched": 0, "added": 0, "ambiguous": 0}
        provenance = [[] for _ in range(len(result))]
        if "additional_sources" in result:
            provenance = result.additional_sources.tolist()
        result["additional_sources"] = provenance
        known_by_source = defaultdict(list)
        for index, sources in enumerate(provenance):
            for source_id in {source["source_id"] for source in sources}:
                known_by_source[source_id].append(index)
        additions = []
        matches = []
        normalize = AdditionalFeatures._normalized
        for _, feature in incoming.iterrows():
            candidates = []
            known = known_by_source.get(feature["source_id"], [])
            nearby = [] if known else metric.sindex.query(feature.geometry.buffer(150), predicate="intersects")
            for index in nearby:
                existing = metric.iloc[index]
                if not all(
                    isinstance(existing.get(column), str) and existing[column] == value
                    for column, value in tag_columns.items()
                ):
                    continue
                distance = feature.geometry.distance(existing.geometry)
                name, other = normalize(feature.get("name")), normalize(existing.get("name"))
                address = all(
                    normalize(feature.get(key)) and normalize(feature.get(key)) == normalize(existing.get(key))
                    for key in ("street", "housenumber")
                )
                name_match = name and other and SequenceMatcher(None, name, other).ratio() >= 0.9
                # Geometry alone is only conclusive for an unnamed object that
                # contains the official point; proximity cannot identify a Kita.
                contained = not other and existing.geometry.covers(feature.geometry)
                if address or (name_match and distance <= 80) or contained:
                    candidates.append(index)
            candidates.extend(known)
            matches.append(candidates)
        # Resolve one-to-one identity before changing any records: two source
        # facilities claiming one OSM object must not depend on source order.
        claims = Counter(candidates[0] for candidates in matches if len(candidates) == 1)
        for position, candidates in enumerate(matches):
            original = external.iloc[position]
            source = {key: original.get(key) for key in (
                "source_id", "source_name", "source_url", "source_feature_id", "source_license_url",
            )}
            if len(candidates) > 1 or (candidates and claims[candidates[0]] > 1):
                stats["ambiguous"] += 1
                print(f"WARNING: Unresolved additional feature {original['source_id']}; not added to avoid duplicates")
                continue
            if candidates:
                index = candidates[0]
                result.at[index, "additional_sources"] = [
                    *[item for item in result.at[index, "additional_sources"]
                      if item["source_id"] != source["source_id"]], source,
                ]
                for key, value in original.items():
                    if key in {"geometry", "osm_id", "osm_url", "element_type", "osm_node_ids",
                               "facility_id", "additional_sources"} or key.startswith("source_"):
                        continue
                    current = result.at[index, key] if key in result else None
                    if (current is None or (isinstance(current, str) and not current.strip())
                            or (not isinstance(current, (list, dict)) and pd.isna(current))):
                        if key not in result:
                            result[key] = None
                        result.at[index, key] = value
                stats["matched"] += 1
            else:
                record = {column: None for column in result.columns}
                record.update(original.to_dict())
                record.update(tag_columns)
                # The legacy pipeline joins on osm_id. Use a namespaced string
                # internally, never an invented numeric OSM ID or OSM URL.
                record.update(osm_id=original["source_id"], element_type="external",
                              osm_url=None, osm_node_ids=[], additional_sources=[source])
                additions.append(record)
                stats["added"] += 1
        if additions:
            result = gpd.GeoDataFrame(
                pd.concat([result, gpd.GeoDataFrame(additions, geometry="geometry", crs=osm.crs)],
                          ignore_index=True), crs=osm.crs,
            )
        stats["after"] = count(result)
        return result, stats

    @staticmethod
    def apply(building_data, area, bbox, config_path=None):
        config = json.loads(Path(config_path or AdditionalFeatures.CONFIG).read_text(encoding="utf-8"))
        reports = []
        names = set()
        for source in config["sources"]:
            if source["name"] in names:
                raise ValueError(f"Duplicate additional source name: {source['name']}")
            names.add(source["name"])
            if area.lower() not in [name.lower() for name in source["areas"]]:
                continue
            layer = source["layer"]
            if layer not in building_data:
                raise ValueError(f"Additional source references missing facility layer: {layer}")
            reserved = WFSRetrieval.PROVENANCE_FIELDS | {
                "geometry", "osm_id", "osm_url", "element_type", "osm_node_ids",
                "facility_id", "additional_sources",
            }
            mapped_fields = {key.replace(":", "_") for key in (*source["fields"], *source["tags"])}
            if mapped_fields & reserved:
                raise ValueError(f"Additional source maps reserved identity fields: {source['name']}")
            retrieval = WFSRetrieval(
                source["url"], source["type_name"], source["name"],
                request_crs=source.get("request_crs", "EPSG:3857"),
                sort_by=source.get("sort_by"), license_url=source.get("license_url"),
            )
            data = retrieval.fetch(bbox=bbox)
            if source.get("public_url"):
                data["source_url"] = source["public_url"]
            for target, attribute in source["fields"].items():
                if attribute not in data and not data.empty:
                    raise ValueError(f"Missing WFS field {attribute} in {source['name']}")
                data[target] = data[attribute] if attribute in data else None
            for key, value in source["tags"].items():
                data[key.replace(":", "_")] = value
            building_data[layer], stats = AdditionalFeatures.merge(building_data[layer], data, source["tags"])
            report = {"source": source["name"], "layer": layer, **stats}
            print(f"Additional feature merge: {report}")
            reports.append(report)
        return reports
