"""Check that the Munich export still fits its live uMap GeoJSON contract.

The Munich map already loads eight remote files. A renamed file, missing
property, changed value type, or multipart geometry can break existing
consumers even when the new Berlin map renders correctly. The small contract
records those eight files as downloaded on 2026-10-25; new files and fields
remain free to grow independently.
"""

import json
from pathlib import Path


CONTRACT = Path(__file__).with_name("munich_remote_contract.json")
EXPORT = Path("GEOJSON_EXPORT/München")


def value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def check_layer(data, contract):
    errors = []
    if data.get("type") != "FeatureCollection":
        return ["Expected a GeoJSON FeatureCollection"]
    features = data.get("features")
    if not isinstance(features, list) or not features:
        return ["Expected a nonempty features array"]

    found_fields = set()
    for index, feature in enumerate(features):
        if feature.get("type") != "Feature" or not isinstance(feature.get("id"), str):
            errors.append(f"Feature {index}: expected a Feature with a string id")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            errors.append(f"Feature {index}: missing properties or geometry")
            continue
        found_fields.update(properties)
        if geometry.get("type") not in contract["geometry_types"]:
            errors.append(f"Feature {index}: unexpected geometry {geometry.get('type')}")
        for field in contract["required_fields"]:
            if field not in properties:
                errors.append(f"Feature {index}: missing required {field}")
        for field, value in properties.items():
            allowed = contract["field_types"].get(field)
            if allowed is not None and value_type(value) not in allowed:
                errors.append(f"Feature {index}: changed type for {field}")
            values = contract.get("field_values", {}).get(field)
            if values is not None and value not in values:
                errors.append(f"Feature {index}: unexpected value for {field}: {value}")

    for field in contract["field_types"].keys() - found_fields:
        errors.append(f"Removed legacy property {field}")
    return errors


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures = []
    for filename, layer_contract in contract["layers"].items():
        path = EXPORT / filename
        if not path.is_file():
            failures.append(f"{path}: missing legacy layer")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = check_layer(data, layer_contract)
        failures.extend(f"{path}: {error}" for error in errors[:10])
        if len(errors) > 10:
            failures.append(f"{path}: {len(errors) - 10} more errors")
        if not errors:
            print(f"OK {filename}: {len(data['features'])} features")
    if failures:
        raise SystemExit("Munich GeoJSON compatibility check failed:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
