"""Run the area analysis from source retrieval through GeoJSON export.

An area's bounding-box query can include neighboring facilities and roads.
AdditionalFeatures applies configured boundaries to sources and the gap
network, then the export clips geometry to the same boundary.
"""

import matplotlib.pyplot as plt
import argparse
import json
from pathlib import Path

from DataRetrieval.SegmentRetrieval import SegmentRetrieval
from DataRetrieval.ZebraCrossingRetrieval import ZebraCrossingRetrieval
from DataRetrieval.SpecificBuildingRetrieval import SpecificBuildingRetrieval
from DataRetrieval.MainEntranceRetrieval import MainEntranceRetrieval
from DataRetrieval.AdditionalFeatures import AdditionalFeatures

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

parser = argparse.ArgumentParser(description="Calculate Tempo-30 potential for one region.")
parser.add_argument("area", nargs="?", default="München")
parser.add_argument("--public-road-candidates", action="store_true",
                    help="Use motorcar access and updated speed tags to select candidate roads.")
parser.add_argument("--validate-osm-sources", action="store_true",
                    help="Reject Overpass support nodes and conflicting crossing tags.")
parser.add_argument("--broaden-facilities", action="store_true",
                    help="Use facility tags and relations beyond the former name filters.")
parser.add_argument("--additional-features", action="store_true",
                    help="Apply the area's configured external sources and spatial filters.")
parser.add_argument("--prefer-main-entrances", action="store_true",
                    help="Use mapped facility entrances before building geometry for street candidates.")
parser.add_argument("--near-road-facilities", action="store_true",
                    help="Keep only traffic-adjacent facilities in potential calculations.")
parser.add_argument("--confirmed-disability-only", action="store_true",
                    help="Require explicit OSM target-group evidence for disability potential.")
parser.add_argument("--strict-gap-evidence", action="store_true",
                    help="Require verifiable direct or conditional Tempo-30 connections.")
parser.add_argument("--clip-long-potentials", action="store_true",
                    help="Limit long non-gap street geometry to its supporting source.")
parser.add_argument("--filter-short-potentials", action="store_true",
                    help="Hide short, isolated potential segments from the map export.")
parser.add_argument("--simplify-crossings", action="store_true",
                    help="Merge crossing ways and duplicate crossing markers.")
parser.add_argument("--compact-playgrounds", action="store_true",
                    help="Hide non-candidate playground points from the full export.")
options = parser.parse_args()
area_under_creation = options.area

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
streets_context_gdf = sr.fetch_as_geodataframe(
    used_bbox, include_nonpublic=True, modern_speed_classes=options.public_road_candidates,
)
streets_gdf = (
    streets_context_gdf.loc[streets_context_gdf["public_motorcar"].eq(True)].copy()
    if options.public_road_candidates else streets_context_gdf.copy()
)

zebra_retrieval = ZebraCrossingRetrieval(timeout=120)
zebra_gdf = zebra_retrieval.fetch_zebra_crossings(
    used_bbox, validate_osm_sources=options.validate_osm_sources,
)
districts_gdf = (
    AdditionalFeatures.load_boundary(area_under_creation)
    if options.additional_features else None
)
zebra_gdf = AdditionalFeatures.filter_sources(zebra_gdf, districts_gdf)
# Entrance evidence is useful in every export, including imagery links.
# Only its use for candidate selection is controlled by a workflow flag.
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

if not options.broaden_facilities:
    # These name predicates and the hospital cache key are the published
    # Munich rule set. Keep them until a region's workflow opts into the
    # broader tag-based facility search.
    building_configs["educational_buildings"]["regex"] = (
        r"(kindergarten|grundschule|hauptschule|realschule|mittelschule|gymnasium|"
        r"gesamtschule|sonderpädagogisches|berufschul|berufoberschule|montessori|"
        r"japanische|simmernschule)"
    )
    building_configs["hospitals"]["regex"] = r"(krankenhaus|klinikum)"
    building_configs["hospitals"]["tags"].pop("healthcare")
    building_configs["hospitals"].pop("cache_datatype")
    building_configs["elderly_homes"]["regex"] = r"(pflegeheim|pflege-heim|senior|alten|residenz|stift)"
    building_configs["elderly_homes"].pop("senior_assisted_living_only")

building_data = SpecificBuildingRetrieval.retrieve_building_data(
    bbox=used_bbox, building_configs=building_configs,
    validate_osm_sources=options.validate_osm_sources,
    broaden_facilities=options.broaden_facilities,
)
kita_before = None
if "educational_buildings" in building_data:
    education = building_data["educational_buildings"]
    kita_before = education.loc[education["amenity"].eq("kindergarten")].copy()
    kita_before = AdditionalFeatures.filter_sources(kita_before, districts_gdf)
merge_reports = (
    AdditionalFeatures.apply(building_data, area_under_creation, used_bbox)
    if options.additional_features else []
)
traffic_adjacent_buildings = {}
for key, facilities in building_data.items():
    facilities = AdditionalFeatures.filter_sources(facilities, districts_gdf)
    if key == "disability_facilities":
        # A name like "Werkstatt Inklusion" is only a search hint; preserve
        # the explicit OSM target-group status on the full source layer.
        facilities = FacilityEligibility.annotate_disability(facilities)
    # Existing consumers receive every in-area source. Only nearby sources
    # enter the calculation; the optional map views stay compact separately.
    building_data[key] = facilities
    traffic_adjacent_buildings[key] = (
        FacilityStreetRelevance.filter_near_streets(facilities, streets_gdf)
        if options.near_road_facilities else facilities
    )
    print(f"Traffic-adjacent {key}: {len(traffic_adjacent_buildings[key])}/{len(facilities)}")

#######################################
# Identify potential
#######################################

potential_results : dict[str, PotentialCalculationResult] = {}


# Zebra crossings
print("Identifying Zebra Crossings ...")
potential_results["zebra"] = ZebraPotential.find_tempo50_segments_near_zebra(
    streets_gdf=streets_gdf, zebras_gdf=zebra_gdf, search_distance_m=15,
    public_only=options.public_road_candidates,
)

for key in building_data.keys():
    print(f"Identifiying Street near {key}")
    eligible = traffic_adjacent_buildings[key]
    if key == "disability_facilities" and options.confirmed_disability_only:
        eligible = eligible.loc[eligible["facility_status"] == "confirmed_disabled"]
    potential_results[key] = ProximityPotential.find_tempo50_segments_near_features(
        streets_gdf=streets_gdf, features_gdf=eligible, search_distance_m=20,
        public_only=options.public_road_candidates,
        allow_addressed_offset=options.additional_features,
        main_entrances=main_entrances_gdf,
        prefer_main_entrances=options.prefer_main_entrances,
        use_area_entrances=key != "playgrounds",
    )

print("Identifying Gaps ...")
# A gap anchor outside the configured boundary would disappear from the
# clipped map. Keep the analysis network and export boundary consistent.
gap_search_streets = AdditionalFeatures.filter_network(streets_gdf, districts_gdf)
potential_results["gap"] = Tempo50GapPotential.find_all_tempo_50_gaps(
    gdf=gap_search_streets, potential_results=potential_results,
    strict_gap_evidence=options.strict_gap_evidence,
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
                                          potential_results = potential_results,
                                          streets_context_gdf = streets_context_gdf,
                                          clip_long_potentials=options.clip_long_potentials,
                                          filter_short_potentials=options.filter_short_potentials,
                                          simplify_crossings=options.simplify_crossings,
                                          compact_playgrounds=options.compact_playgrounds,
                                          modern_speed_context=options.public_road_candidates,
                                          prefer_main_entrances=options.prefer_main_entrances)

if merge_reports and kita_before is not None:
    before_near = (
        FacilityStreetRelevance.filter_near_streets(kita_before, streets_gdf)
        if options.near_road_facilities else kita_before
    )
    before_potential = ProximityPotential.find_tempo50_segments_near_features(
        streets_gdf, before_near, search_distance_m=20,
        public_only=options.public_road_candidates,
        allow_addressed_offset=options.additional_features,
    )
    after = traffic_adjacent_buildings["educational_buildings"]
    after = after.loc[after["amenity"].eq("kindergarten")]
    # The traffic subset has no export annotation. Count Kita IDs directly
    # from the calculation result so the full source export stays separate.
    after_potential_ids = potential_results["educational_buildings"].opt_source_ids or []
    statistics = {
        "sources": merge_reports,
        "kitas": {
            "before": {"retrieved": len(kita_before), "traffic_adjacent": len(before_near),
                       "potential": len(before_potential.opt_source_ids or [])},
            "after": {"traffic_adjacent": len(after),
                      "potential": int(after["osm_id"].isin(after_potential_ids).sum())},
        },
    }
    report_path = Path("GEOJSON_EXPORT") / area_under_creation / "additional_features_statistics.json"
    report_path.write_text(json.dumps(statistics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Additional feature statistics: {statistics}")

if area_under_creation.lower() == "berlin":
    print(f"Berlin injury accidents by year: {AccidentAtlasExport.export()}")


# Plotting

StreetPlot.plot_map(streets_gdf = streets_updated_gdf, zebra_gdf = zebra_gdf, bdg_data = building_data)

if plt.get_backend().lower() != "agg":
    plt.show()
