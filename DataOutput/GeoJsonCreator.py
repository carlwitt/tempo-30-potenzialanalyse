
import json

from pathlib import Path

import geopandas as gpd

from DataOutput.AdjacentCoveredSegments import AdjacentCoveredSegments
from DataOutput.ConditionalGapMetadata import ConditionalGapMetadata
from DataOutput.DistrictStatsCreator import DistrictStatsCreator
from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from DataOutput.OSMVerificationMetadata import OSMVerificationMetadata
from DataOutput.PlaygroundConsolidation import PlaygroundConsolidation
from DataOutput.PotentialStreetConsolidation import PotentialStreetConsolidation
from DataOutput.PotentialReasonAnnotator import PotentialReasonAnnotator
from DataOutput.StreetImageryLinkCreator import StreetImageryLinkCreator
from DataOutput.ZebraCrossingSimplifier import ZebraCrossingSimplifier


class GeoJsonCreator:
    def create_geojson_layer_files(
        folder_name, streets_with_potential: gpd.GeoDataFrame, streets_w_limit_gdf,
        zebra_gdf, building_data, districts_gdf=None, gap_street_ids=None,
        main_entrances_gdf=None, potential_results=None,
    ):
        export_dir = Path("GEOJSON_EXPORT") / folder_name
        export_dir.mkdir(parents=True, exist_ok=True)

        export_data_dict = {}

        export_data_dict["zebra"] = zebra_gdf.copy()
        export_data_dict["potential_streets"] = PotentialStreetConsolidation.filter_short_isolated(
            streets_with_potential
        )
        export_data_dict["streets_and_limit"] = streets_w_limit_gdf.copy()

        for key, data in building_data.items():
            export_data_dict[key] = data.copy()
        export_data_dict["facility_street_segments"] = FacilityStreetSegments.create(
            streets_w_limit_gdf, building_data, potential_results or {}
        )
        export_data_dict["facility_covered_street_segments"] = AdjacentCoveredSegments.create(
            streets_w_limit_gdf, building_data, potential_results or {}
        )

        export_data_dict["potential_streets"]["feature_type"] = \
            export_data_dict["potential_streets"]["feature_type"].map({
                "T30_Potenzial_Zebrastreifen": "Potenzial durch Zebrastreifen",
                "T30_Potenzial_Schule": "Potenzial durch Bildungseinrichtung",
                "T30_Potenzial_Luecke": "Potenzial durch Lückenschluss",
                "T30_Potenzial_Krankenhaus": "Potenzial durch Krankenhaus",
                "T30_Potenzial_Altenheim": "Potenzial durch Seniorenwohnheim",
                "T30_Potenzial_Spielplatz": "Potenzial durch Spielplatz",
                "T30_Potenzial_Behinderteneinrichtung": "Potenzial durch Behinderteneinrichtung",
                "T30_Potenzial_Multifaktor" : "Potenzial durch mehrere Faktoren"
            })
        export_data_dict["potential_streets"] = FacilityStreetSegments.annotate_potential_streets(
            export_data_dict["potential_streets"], export_data_dict["facility_street_segments"]
        )
        export_data_dict["potential_streets"] = AdjacentCoveredSegments.annotate_potential_streets(
            export_data_dict["potential_streets"], export_data_dict["facility_covered_street_segments"]
        )
        gap_result = (potential_results or {}).get("gap")
        export_data_dict["potential_streets"] = ConditionalGapMetadata.annotate(
            export_data_dict["potential_streets"], gap_result, potential_results or {},
            {"zebra": zebra_gdf, **building_data},
        )

        # Bundle speed limits
        mapping = {
            "10": "T30-",
            "20": "T30-",
            "30": "T30-",
            "50": "T50+",
            "60": "T50+"
        }

        export_data_dict["streets_and_limit"]["maxspeed_class"] =  export_data_dict["streets_and_limit"]["maxspeed_class"].replace(mapping)

        # Override when conditional speed is 30
        export_data_dict["streets_and_limit"].loc[export_data_dict["streets_and_limit"]["conditional_speed"] == "30", "maxspeed_class"] = "Conditional-T30"
        
        # Convert to WGS84
        for entry in export_data_dict.keys():
            export_data_dict[entry] = export_data_dict[entry].to_crs("EPSG:4326")

        # Reduce unnecessary columns
        export_data_dict["potential_streets"] = export_data_dict["potential_streets"][[
            "osm_id",
            "name",
            "maxspeed_class",
            "feature_type",
            "logical_segment_length_m",
            "logical_segment_way_count",
            "is_conditional_gap",
            "gap_required_potentials",
            "gap_required_potential_types",
            "gap_required_street_osm_ids",
            "description",
            "geometry"
        ]]

        export_data_dict["streets_and_limit"] = export_data_dict["streets_and_limit"][[
            "osm_id",
            "name",
            "maxspeed_class",
            "conditional_speed",
            "cond_speed_days",
            "cond_speed_starttime",
            "cond_speed_endtime",
            "cond_speed_special",
            "geometry"
        ]]

        export_data_dict["zebra"] = export_data_dict["zebra"][[
            "geometry",
            "potential_candidate",
            "street"
        ]]

        export_data_dict["zebra"] = ZebraCrossingSimplifier.simplify(export_data_dict["zebra"])
        export_data_dict["zebra"] = PotentialReasonAnnotator.add_reason(
            export_data_dict["zebra"],
            "Potenzial: Tempo-50/60-Straße innerhalb von 15 m des Zebrastreifens.",
        )
        export_data_dict["zebra"] = StreetImageryLinkCreator.add_links(
            export_data_dict["zebra"], export_data_dict["streets_and_limit"]
        )
        if districts_gdf is not None:
            gap_streets = streets_w_limit_gdf.loc[
                streets_w_limit_gdf["osm_id"].isin(gap_street_ids or [])
            ]
            export_data_dict["district_stats"] = DistrictStatsCreator.create(
                districts_gdf, export_data_dict["zebra"], streets_w_limit_gdf,
                building_data, gap_streets,
                conditional_gap_street_ids=set(
                    (gap_result.conditional_gap_dependencies or {}) if gap_result else {}
                ),
            )

        for building_type in building_data.keys():
            columns = [
                "osm_id",
                "element_type",
                "osm_node_ids",
                "osm_url",
                "name",
                "official_name",
                "alt_name",
                "short_name",
                "amenity",
                "healthcare",
                "social_facility",
                "social_facility_for",
                "geometry",
                "potential_candidate",
                "street",
                "housenumber",
                "website",
                "operator"
            ]
            if "facility_status" in export_data_dict[building_type]:
                columns.append("facility_status")
            export_data_dict[building_type] = export_data_dict[building_type][columns]
            export_data_dict[building_type] = OSMVerificationMetadata.add_details(
                export_data_dict[building_type], building_type
            )
            export_data_dict[building_type] = PotentialReasonAnnotator.add_reason(
                export_data_dict[building_type],
                "Warum prüfen? Diese Einrichtung liegt höchstens 20 m an einer OSM-Straße "
                "mit 50/60 km/h ohne erfasstes bedingtes Tempo 30. Ein langsamerer Abschnitt "
                "könnte Wege und Querungen im Umfeld schützen; Nutzung und Grenzen vor Ort prüfen.",
            )
            export_data_dict[building_type] = FacilityStreetSegments.annotate_facilities(
                export_data_dict[building_type], export_data_dict["facility_street_segments"], building_type
            )
            export_data_dict[building_type] = AdjacentCoveredSegments.annotate_facilities(
                export_data_dict[building_type], export_data_dict["facility_covered_street_segments"], building_type
            )
            export_data_dict[building_type] = StreetImageryLinkCreator.add_links(
                export_data_dict[building_type], export_data_dict["streets_and_limit"],
                main_entrances=main_entrances_gdf,
                use_area_entrances=building_type != "playgrounds",
            )
            export_data_dict[building_type] = export_data_dict[building_type].drop(columns="osm_node_ids")

        if "disability_facilities" in export_data_dict:
            disability = export_data_dict["disability_facilities"]
            confirmed = disability["facility_status"] == "confirmed_disabled"
            export_data_dict["disability_facilities_review"] = disability.loc[~confirmed].copy()
            export_data_dict["disability_facilities"] = disability.loc[confirmed].copy()

        export_data_dict["playgrounds"] = PlaygroundConsolidation.summarize_playground_features(playgroundGDF = export_data_dict["playgrounds"])

        # Export
        for entry in export_data_dict.keys():
            geojson = json.loads(export_data_dict[entry].to_json())

            # Keep null district percentages when a district has no such feature.
            if entry != "district_stats":
                for f in geojson["features"]:
                    f["properties"] = {k: v for k, v in f["properties"].items() if v is not None}

            filename = entry + ".geojson"
            output_file = export_dir / filename
            
            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(geojson, file, separators=(",", ":"), ensure_ascii=False)

                print(f"\n✅ GeoJSON successfully written to: {output_file}")
                print(f"Total features exported: {len(export_data_dict[entry])}")
