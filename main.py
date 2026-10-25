"""Run the area analysis from source retrieval through GeoJSON export.

For Berlin, a bounding-box query also sees Brandenburg facilities and
roads. Assign sources to Berlin, search gaps on complete Berlin roads,
then export clipped geometry. This keeps candidate counts and visible
gap anchors consistent with the requested city.
"""

import matplotlib.pyplot as plt
import sys
import json
from pathlib import Path

from DataRetrieval.SegmentRetrieval import SegmentRetrieval
from DataRetrieval.ZebraCrossingRetrieval import ZebraCrossingRetrieval
from DataRetrieval.SpecificBuildingRetrieval import SpecificBuildingRetrieval
from DataRetrieval.BerlinDistrictRetrieval import BerlinDistrictRetrieval
from DataRetrieval.MainEntranceRetrieval import MainEntranceRetrieval
from DataRetrieval.AdditionalFeatures import AdditionalFeatures

from PotentialCalculation.ZebraPotential import ZebraPotential
from PotentialCalculation.ProximityPotential import ProximityPotential
from PotentialCalculation.FacilityEligibility import FacilityEligibility
from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance
from PotentialCalculation.AreaScope import AreaScope
from PotentialCalculation.GapPotential import Tempo50GapPotential
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult

from SpeedAnnotationUpdater import SpeedAnnotationUpdater
from BoundingBoxStorage import BoundingBoxStorage

from DataOutput.GeoJsonCreator import GeoJsonCreator
from DataOutput.AccidentAtlasExport import AccidentAtlasExport
from DataOutput.PrintOutput import PrintOutput
from DataOutput.StreetPlot import StreetPlot

if len(sys.argv) > 1:
    area_under_creation = sys.argv[1]
else:
    area_under_creation = "München"

print(f"Calculating potential for: {area_under_creation}")

# Select Bounding Box
if(area_under_creation != "München"):
    used_bbox = BoundingBoxStorage.get(area_under_creation)
else:
    used_bbox : str = "München" # Special case -> Handled differently in overpass query



#######################################
# Retrieve (and print) raw data
#######################################

sr = SegmentRetrieval()
streets_gdf = sr.fetch_as_geodataframe(used_bbox)

zebra_retrieval = ZebraCrossingRetrieval(timeout=120)
zebra_gdf = zebra_retrieval.fetch_zebra_crossings(used_bbox)
districts_gdf = BerlinDistrictRetrieval().fetch_districts() if area_under_creation.lower() == "berlin" else None
if districts_gdf is not None:
    zebra_gdf = AreaScope.filter_sources(zebra_gdf, districts_gdf)
main_entrances_gdf = MainEntranceRetrieval().fetch_as_geodataframe(used_bbox)

StreetPlot.plot_map(streets_gdf = streets_gdf, zebra_gdf = zebra_gdf)

building_configs = {
    "educational_buildings": {
        # A school or Kita can have an unrelated name. Require its OSM amenity
        # tag so the name cannot alone create an education street candidate.
        "tags": {
            "amenity": ["school", "kindergarten"]
        },
        "speed_annotation" : "T30_Potenzial_Schule"
    },
    "hospitals": {
        "tags": {
            "amenity": ["hospital"],
            "healthcare": ["hospital"],
        },
        # The previous hospital cache omitted healthcare=hospital features.
        # Use a new key so those missing records are fetched and evaluated.
        "cache_datatype": "hospitals_with_healthcare",
        "speed_annotation" : "T30_Potenzial_Krankenhaus"
    },
    "elderly_homes": {
        "tags": {
            "amenity": ["nursing_home", "retirement_home", "care_home"],
            "social_facility": ["nursing_home", "assisted_living"]
        },
        "senior_assisted_living_only": True,
        "speed_annotation" : "T30_Potenzial_Altenheim"
    },
    "playgrounds": {
        "tags": {
            "amenity": ["playground"],
            "leisure": ["playground"]
    },
    "regex": None,
    "speed_annotation": "T30_Potenzial_Spielplatz"
    },
    "disability_facilities": {
        "tags": {
            "amenity": ["social_facility", "clinic","craft"],
            "social_facility": [
                "assisted_living",
                "group_home",
                "workshop",
                "rehabilitation",
                "day_care"
            ],
            "healthcare": ["rehabilitation", "physiotherapy"]
    },
        "regex": r"(behinderung|behindert|lebenshilfe|inklusion|förderstätte|werkstatt|werkstätten)",
        "speed_annotation": "T30_Potenzial_Behinderteneinrichtung"
    }
}

building_data = SpecificBuildingRetrieval.retrieve_building_data(bbox = used_bbox, building_configs = building_configs)
kita_before = None
if "educational_buildings" in building_data:
    education = building_data["educational_buildings"]
    kita_before = education.loc[education["amenity"].eq("kindergarten")].copy()
    if districts_gdf is not None:
        kita_before = AreaScope.filter_sources(kita_before, districts_gdf)
merge_reports = AdditionalFeatures.apply(building_data, area_under_creation, used_bbox)
for key, facilities in building_data.items():
    if districts_gdf is not None:
        facilities = AreaScope.filter_sources(facilities, districts_gdf)
    building_data[key] = FacilityStreetRelevance.filter_near_streets(facilities, streets_gdf)
    print(f"Traffic-adjacent {key}: {len(building_data[key])}/{len(facilities)}")
if "disability_facilities" in building_data:
    # A name like "Werkstatt Inklusion" is only a search hint; preserve the
    # explicit OSM target-group status before calculating street potential.
    building_data["disability_facilities"] = FacilityEligibility.annotate_disability(
        building_data["disability_facilities"]
    )

#######################################
# Identify potential
#######################################

potential_results : dict[str, PotentialCalculationResult] = {}


# Zebra crossings
print("Identifying Zebra Crossings ...")
potential_results["zebra"] = ZebraPotential.find_tempo50_segments_near_zebra(streets_gdf = streets_gdf, zebras_gdf = zebra_gdf, search_distance_m = 15)

for key in building_data.keys():
    print(f"Identifiying Street near {key}")
    eligible = building_data[key]
    if key == "disability_facilities":
        eligible = eligible.loc[eligible["facility_status"] == "confirmed_disabled"]
    potential_results[key] = ProximityPotential.find_tempo50_segments_near_features(
        streets_gdf=streets_gdf, features_gdf=eligible, search_distance_m=20
    )

print("Identifying Gaps ...")
# A Brandenburg road may connect to a Berlin gap in the query bbox but
# disappear from the clipped map. Trace only whole Berlin ways so every
# accepted anchor and corridor can also be displayed.
gap_search_streets = (
    AreaScope.filter_complete_network(streets_gdf, districts_gdf)
    if districts_gdf is not None else streets_gdf
)
potential_results["gap"] = Tempo50GapPotential.find_all_tempo_50_gaps(
    gdf=gap_search_streets, potential_results=potential_results
)


#######################################
# Annotate features as relevant for potential
#######################################

zebra_gdf["potential_candidate"] = zebra_gdf["osm_id"].isin(potential_results["zebra"].opt_source_ids)

for key, bdg_data in building_data.items():
    corresponding_result = potential_results[key]
    bdg_data["potential_candidate"] = bdg_data["osm_id"].isin(corresponding_result.opt_source_ids)

#######################################
# Create street dataset w. Annotations
#######################################

streets_updated_gdf = SpeedAnnotationUpdater.annotate_gdf_with_potential_type(streets_gdf, potential_results, building_configs)


#######################################
# File / Print / Map Output
#######################################

streets_with_potential = streets_updated_gdf[
    streets_updated_gdf["feature_type"].str.startswith("T30_Potenzial", na=False)
]

# Print if required
PrintOutput.print_streets(streets_with_potential)

GeoJsonCreator.create_geojson_layer_files(folder_name = area_under_creation.lower(), streets_with_potential = streets_with_potential,
                                          streets_w_limit_gdf = streets_gdf, zebra_gdf = zebra_gdf, building_data = building_data,
                                          districts_gdf = districts_gdf, gap_street_ids = potential_results["gap"].street_ids,
                                          main_entrances_gdf = main_entrances_gdf,
                                          potential_results = potential_results)

if merge_reports and kita_before is not None:
    before_near = FacilityStreetRelevance.filter_near_streets(kita_before, streets_gdf)
    before_potential = ProximityPotential.find_tempo50_segments_near_features(
        streets_gdf, before_near, search_distance_m=20,
    )
    after = building_data["educational_buildings"]
    after = after.loc[after["amenity"].eq("kindergarten")]
    statistics = {
        "sources": merge_reports,
        "kitas": {
            "before": {"retrieved": len(kita_before), "traffic_adjacent": len(before_near),
                       "potential": len(before_potential.opt_source_ids or [])},
            "after": {"traffic_adjacent": len(after),
                      "potential": int(after["potential_candidate"].sum())},
        },
    }
    report_path = Path("GEOJSON_EXPORT") / area_under_creation.lower() / "additional_features_statistics.json"
    report_path.write_text(json.dumps(statistics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Additional feature statistics: {statistics}")

if area_under_creation.lower() == "berlin":
    print(f"Berlin injury accidents by year: {AccidentAtlasExport.export()}")


# Plotting

StreetPlot.plot_map(streets_gdf = streets_updated_gdf, zebra_gdf = zebra_gdf, bdg_data = building_data)

if plt.get_backend().lower() != "agg":
    plt.show()
