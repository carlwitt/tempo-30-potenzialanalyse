"""Export Berlin injury accidents from the official annual Unfallatlas CSV archives.

The source archives are cached outside Git. Update YEARS when another annual
Unfallatlas release becomes available; missing archives are downloaded on demand.
"""

import csv
import io
import json
import shutil
from collections import Counter
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile


class AccidentAtlasExport:
    YEARS = (2022, 2023, 2024, 2025)
    BASE_URL = "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas"
    CACHE_DIR = Path("overpass_cache/unfallatlas")
    OUTPUT = Path("GEOJSON_EXPORT/Berlin/accidents.geojson")
    CATEGORIES = {1: "Unfall mit Todesfolge", 2: "Unfall mit Schwerverletzten", 3: "Unfall mit Leichtverletzten"}

    @staticmethod
    def archive_path(year, cache_dir=None):
        return (cache_dir or AccidentAtlasExport.CACHE_DIR) / f"Unfallorte{year}_EPSG25832_CSV.zip"

    @staticmethod
    def ensure_archive(year, cache_dir=None):
        archive = AccidentAtlasExport.archive_path(year, cache_dir)
        if archive.is_file():
            return archive

        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = archive.with_suffix(".zip.part")
        url = f"{AccidentAtlasExport.BASE_URL}/{archive.name}"
        try:
            with urlopen(url, timeout=120) as response, temporary.open("wb") as target:
                shutil.copyfileobj(response, target)
            with ZipFile(temporary) as source:
                if source.testzip() is not None:
                    raise ValueError(f"Damaged Unfallatlas archive: {url}")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
        return archive

    @staticmethod
    def features_for_year(year, archive):
        with ZipFile(archive) as source:
            csv_names = [name for name in source.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"Expected one CSV in {archive}, found {csv_names}")
            with source.open(csv_names[0]) as raw:
                rows = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""), delimiter=";")
                required = {"UIDENTSTLAE", "ULAND", "UJAHR", "UMONAT", "UKATEGORIE", "XGCSWGS84", "YGCSWGS84"}
                if not required.issubset(rows.fieldnames or []):
                    raise ValueError(f"Unrecognized Unfallatlas CSV schema in {archive}")

                for row in rows:
                    if row["ULAND"] != "11":  # Berlin's official federal-state key.
                        continue
                    category = int(row["UKATEGORIE"])
                    if category not in AccidentAtlasExport.CATEGORIES or int(row["UJAHR"]) != year:
                        raise ValueError(f"Unexpected Unfallatlas category/year in {archive}: {row}")
                    longitude = float(row["XGCSWGS84"].replace(",", "."))
                    latitude = float(row["YGCSWGS84"].replace(",", "."))
                    if not (13.0 < longitude < 14.0 and 52.0 < latitude < 53.0):
                        raise ValueError(f"Invalid Berlin Unfallatlas coordinates in {archive}: {row}")

                    yield {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                        "properties": {
                            "accident_id": row["UIDENTSTLAE"],
                            "UJAHR": year,
                            "UMONAT": int(row["UMONAT"]),
                            "UKATEGORIE": category,
                            "heat_weight": 2 ** (6 - category),
                            "description": AccidentAtlasExport.CATEGORIES[category],
                        },
                    }

    @staticmethod
    def export(output=None, cache_dir=None, years=None):
        output = output or AccidentAtlasExport.OUTPUT
        years = years or AccidentAtlasExport.YEARS
        archives = [(year, AccidentAtlasExport.ensure_archive(year, cache_dir)) for year in years]
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".part")
        counts = Counter()
        try:
            with temporary.open("w", encoding="utf-8") as target:
                target.write('{"type":"FeatureCollection","features":[')
                first = True
                for year, archive in archives:
                    for feature in AccidentAtlasExport.features_for_year(year, archive):
                        if not first:
                            target.write(",")
                        json.dump(feature, target, ensure_ascii=False, separators=(",", ":"))
                        first = False
                        counts[year] += 1
                target.write("]}")
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        return dict(counts)
