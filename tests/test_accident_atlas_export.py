import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from DataOutput.AccidentAtlasExport import AccidentAtlasExport


class AccidentAtlasExportTests(unittest.TestCase):
    def test_berlin_filter_and_severity_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cache = base / "cache"
            cache.mkdir()
            header = "UIDENTSTLAE;ULAND;UJAHR;UMONAT;UKATEGORIE;XGCSWGS84;YGCSWGS84\n"
            for year, category in ((2022, 1), (2023, 2), (2024, 3)):
                archive = AccidentAtlasExport.archive_path(year, cache)
                content = header + (
                    f"{year}abc;11;{year};06;{category};13,404;52,520\n"
                    f"{year}outside;09;{year};06;{category};11,500;48,100\n"
                )
                with ZipFile(archive, "w") as target:
                    target.writestr(f"csv/Unfallorte{year}.csv", content)

            output = base / "accidents.geojson"
            counts = AccidentAtlasExport.export(output=output, cache_dir=cache, years=(2022, 2023, 2024))
            features = json.loads(output.read_text(encoding="utf-8"))["features"]

            self.assertEqual(counts, {2022: 1, 2023: 1, 2024: 1})
            self.assertEqual([feature["properties"]["heat_weight"] for feature in features], [32, 16, 8])
            self.assertEqual([feature["properties"]["UKATEGORIE"] for feature in features], [1, 2, 3])
            self.assertTrue(all(feature["geometry"]["coordinates"] == [13.404, 52.52] for feature in features))


if __name__ == "__main__":
    unittest.main()
