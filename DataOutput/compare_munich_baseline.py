"""Compare analysis results with a freshly computed main-branch export.

Only additive properties and files are ignored. Existing properties, feature
multiplicities and geometry must match, independently of GeoJSON feature IDs
or ordering. Coordinates are rounded to eight decimals (about one millimetre)
to ignore projection round-off.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

from shapely.geometry import mapping, shape


def _rounded(value):
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    return round(value, 8) if isinstance(value, float) else value


def compare_layer(baseline, candidate):
    for collection in (baseline, candidate):
        if collection.get("type") != "FeatureCollection":
            raise ValueError("Expected a GeoJSON FeatureCollection")
    fields = sorted({
        key for feature in baseline["features"] for key in feature["properties"]
    })

    def records(collection):
        result = Counter()
        for feature in collection["features"]:
            properties = {key: feature["properties"].get(key) for key in fields}
            # Existing optional facility names may be exported as an empty string.
            if properties.get("name") == "":
                properties["name"] = None
            geometry = mapping(shape(feature["geometry"]).normalize())
            result[json.dumps(
                {"properties": properties, "geometry": _rounded(geometry)},
                sort_keys=True, ensure_ascii=False,
            )] += 1
        return result

    old, new = records(baseline), records(candidate)
    missing, added = old - new, new - old
    return {
        "baseline_features": sum(old.values()),
        "candidate_features": sum(new.values()),
        "unchanged_features": sum((old & new).values()),
        "missing_or_changed_features": sum(missing.values()),
        "added_or_changed_features": sum(added.values()),
        "compared_fields": fields,
        "missing_or_changed_osm_ids": sorted({
            json.loads(record)["properties"]["osm_id"]
            for record in missing if json.loads(record)["properties"].get("osm_id") is not None
        }),
        "added_or_changed_osm_ids": sorted({
            json.loads(record)["properties"]["osm_id"]
            for record in added if json.loads(record)["properties"].get("osm_id") is not None
        }),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    files = sorted(args.baseline.glob("*.geojson"))
    if not files:
        parser.error(f"No baseline GeoJSON files in {args.baseline}")
    report = {}
    for baseline in files:
        candidate = args.candidate / baseline.name
        report[baseline.name] = compare_layer(
            json.loads(baseline.read_text(encoding="utf-8")),
            json.loads(candidate.read_text(encoding="utf-8")),
        )
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, result in report.items():
        print(f"{name}: {result['unchanged_features']}/{result['baseline_features']} unchanged, "
              f"{result['missing_or_changed_features']} missing/changed, "
              f"{result['added_or_changed_features']} added/changed")
    return int(any(
        result["missing_or_changed_features"] or result["added_or_changed_features"]
        for result in report.values()
    ))


if __name__ == "__main__":
    raise SystemExit(main())
