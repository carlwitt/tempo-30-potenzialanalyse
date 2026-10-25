"""Exercise the real entry point and workflow commands without network or export."""

from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import runpy
import shlex
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import LineString
import yaml

from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


ROOT = Path(__file__).resolve().parents[1]
FLAGS = (
    "public-road-candidates", "validate-osm-sources", "broaden-facilities",
    "additional-features", "prefer-main-entrances", "near-road-facilities",
    "confirmed-disability-only", "strict-gap-evidence", "clip-long-potentials",
    "filter-short-potentials", "simplify-crossings", "compact-playgrounds",
)


class AnalysisFeatureFlagTests(unittest.TestCase):
    def run_analysis(self, arguments):
        streets = gpd.GeoDataFrame(
            {"osm_id": [1], "name": ["Test"], "public_motorcar": [True],
             "maxspeed_class": ["50"], "conditional_speed": [None]},
            geometry=[LineString([(11, 48), (11.001, 48)])], crs="EPSG:4326",
        )
        facilities = gpd.GeoDataFrame(
            {"osm_id": [], "name": [], "amenity": [], "social_facility_for": []},
            geometry=[], crs="EPSG:4326",
        )
        paths = {
            "roads": "DataRetrieval.SegmentRetrieval.SegmentRetrieval.fetch_as_geodataframe",
            "zebras": "DataRetrieval.ZebraCrossingRetrieval.ZebraCrossingRetrieval.fetch_zebra_crossings",
            "buildings": "DataRetrieval.SpecificBuildingRetrieval.SpecificBuildingRetrieval.retrieve_building_data",
            "districts": "DataRetrieval.AdditionalFeatures.AdditionalFeatures.load_boundary",
            "entrances": "DataRetrieval.MainEntranceRetrieval.MainEntranceRetrieval.fetch_as_geodataframe",
            "additional": "DataRetrieval.AdditionalFeatures.AdditionalFeatures.apply",
            "nearby": "PotentialCalculation.FacilityStreetRelevance.FacilityStreetRelevance.filter_near_streets",
            "sources": "DataRetrieval.AdditionalFeatures.AdditionalFeatures.filter_sources",
            "network": "DataRetrieval.AdditionalFeatures.AdditionalFeatures.filter_network",
            "crossing_potential": "PotentialCalculation.ZebraPotential.ZebraPotential.find_tempo50_segments_near_zebra",
            "facility_potential": "PotentialCalculation.ProximityPotential.ProximityPotential.find_tempo50_segments_near_features",
            "gaps": "PotentialCalculation.GapPotential.Tempo50GapPotential.find_all_tempo_50_gaps",
            "annotation": "SpeedAnnotationUpdater.SpeedAnnotationUpdater.annotate_gdf_with_potential_type",
            "export": "DataOutput.GeoJsonCreator.GeoJsonCreator.create_geojson_layer_files",
            "accidents": "DataOutput.AccidentAtlasExport.AccidentAtlasExport.export",
            "plot": "DataOutput.StreetPlot.StreetPlot.plot_map",
            "print": "DataOutput.PrintOutput.PrintOutput.print_streets",
        }
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(patch(path)) for name, path in paths.items()}
            stack.enter_context(patch("sys.argv", ["main.py", *arguments]))
            stack.enter_context(patch("matplotlib.pyplot.get_backend", return_value="agg"))
            stack.enter_context(redirect_stdout(io.StringIO()))
            mocks["roads"].return_value = streets
            mocks["zebras"].return_value = facilities.copy()
            mocks["buildings"].return_value = {
                key: facilities.copy() for key in (
                    "educational_buildings", "hospitals", "elderly_homes",
                    "playgrounds", "disability_facilities",
                )
            }
            mocks["additional"].return_value = []
            for name in ("nearby", "sources", "network"):
                mocks[name].side_effect = lambda features, streets: features
            for name in ("crossing_potential", "facility_potential", "gaps"):
                mocks[name].return_value = PotentialCalculationResult([], [])
            mocks["annotation"].return_value = streets.assign(feature_type="T30_Potenzial_Schule")
            result = runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
        return result, mocks

    def test_defaults_do_not_opt_into_changed_rules(self):
        result, mocks = self.run_analysis([])
        self.assertEqual(result["options"].area, "München")
        for flag in FLAGS:
            self.assertFalse(getattr(result["options"], flag.replace("-", "_")), flag)
        for name in ("additional", "districts", "nearby"):
            mocks[name].assert_not_called()
        mocks["entrances"].assert_called_once()
        self.assertFalse(mocks["buildings"].call_args.kwargs["validate_osm_sources"])
        self.assertFalse(mocks["buildings"].call_args.kwargs["broaden_facilities"])
        self.assertFalse(mocks["facility_potential"].call_args.kwargs["public_only"])
        self.assertFalse(mocks["facility_potential"].call_args.kwargs["allow_addressed_offset"])
        self.assertFalse(mocks["gaps"].call_args.kwargs["strict_gap_evidence"])
        self.assertIn("regex", mocks["buildings"].call_args.kwargs["building_configs"]["educational_buildings"])

    def test_each_flag_can_be_selected_independently(self):
        for flag in FLAGS:
            with self.subTest(flag=flag):
                result, _ = self.run_analysis(["--" + flag])
                for other in FLAGS:
                    self.assertEqual(
                        getattr(result["options"], other.replace("-", "_")), other == flag,
                    )

    def test_weekly_workflows_select_the_intended_profiles(self):
        profiles = {
            "weekly_run.yml": set(),
            "weekly_run_berlin.yml": set(FLAGS),
            "weekly_run_potsdam.yml": set(FLAGS),
        }
        for workflow, expected in profiles.items():
            with self.subTest(workflow=workflow):
                config = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text())
                step = next(step for step in config["jobs"]["run-script"]["steps"]
                            if step["name"] == "Run main.py")
                command = shlex.split(step["run"].replace("\\\n", " "), comments=True)
                self.assertEqual(command[:2], ["python", "main.py"])
                result, mocks = self.run_analysis(command[2:])
                enabled = {flag for flag in FLAGS
                           if getattr(result["options"], flag.replace("-", "_"))}
                self.assertEqual(enabled, expected)
                self.assertEqual(mocks["additional"].called, "additional-features" in expected)
                self.assertEqual(mocks["districts"].called, "additional-features" in expected)
                boundary = (mocks["districts"].return_value
                            if "additional-features" in expected else None)
                self.assertIs(mocks["export"].call_args.kwargs["districts_gdf"], boundary)
                self.assertIs(mocks["network"].call_args.args[1], boundary)
                self.assertTrue(all(call.args[1] is boundary
                                    for call in mocks["sources"].call_args_list))
                mocks["entrances"].assert_called_once()
                self.assertEqual(
                    mocks["facility_potential"].call_args.kwargs["prefer_main_entrances"],
                    "prefer-main-entrances" in expected,
                )
                for flag in ("clip-long-potentials", "filter-short-potentials",
                             "simplify-crossings", "compact-playgrounds"):
                    self.assertEqual(mocks["export"].call_args.kwargs[flag.replace("-", "_")],
                                     flag in expected)


if __name__ == "__main__":
    unittest.main()
