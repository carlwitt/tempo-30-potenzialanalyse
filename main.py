import matplotlib.pyplot as plt
import sys

from DataRetrieval.SegmentRetrieval import SegmentRetrieval
from DataRetrieval.ZebraCrossingRetrieval import ZebraCrossingRetrieval
from DataRetrieval.SpecificBuildingRetrieval import SpecificBuildingRetrieval
from DataRetrieval.BerlinDistrictRetrieval import BerlinDistrictRetrieval
from DataRetrieval.MainEntranceRetrieval import MainEntranceRetrieval

from PotentialCalculation.ZebraPotential import ZebraPotential
from PotentialCalculation.ProximityPotential import ProximityPotential
from PotentialCalculation.FacilityEligibility import FacilityEligibility
from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance
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
main_entrances_gdf = MainEntranceRetrieval().fetch_as_geodataframe(used_bbox)

StreetPlot.plot_map(streets_gdf = streets_gdf, zebra_gdf = zebra_gdf)

building_configs = {
    "educational_buildings": {
        # OSM facility tags, not name keywords, determine eligibility (e.g. "Kita").
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
        # The old cache only queried amenity=hospital.
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
for key, facilities in building_data.items():
    building_data[key] = FacilityStreetRelevance.filter_near_streets(facilities, streets_gdf)
    print(f"Traffic-adjacent {key}: {len(building_data[key])}/{len(facilities)}")
if "disability_facilities" in building_data:
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
potential_results["gap"] = Tempo50GapPotential.find_all_tempo_50_gaps(
    gdf=streets_gdf, potential_results=potential_results
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

GeoJsonCreator.create_geojson_layer_files(folder_name = area_under_creation, streets_with_potential = streets_with_potential,
                                          streets_w_limit_gdf = streets_gdf, zebra_gdf = zebra_gdf, building_data = building_data,
                                          districts_gdf = districts_gdf, gap_street_ids = potential_results["gap"].street_ids,
                                          main_entrances_gdf = main_entrances_gdf,
                                          potential_results = potential_results)

if area_under_creation.lower() == "berlin":
    print(f"Berlin injury accidents by year: {AccidentAtlasExport.export()}")


# Plotting

StreetPlot.plot_map(streets_gdf = streets_updated_gdf, zebra_gdf = zebra_gdf, bdg_data = building_data)

plt.show()
