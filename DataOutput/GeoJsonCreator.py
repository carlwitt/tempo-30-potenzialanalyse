
"""Turn candidate evidence into inspectable map and analysis layers.

A direct gap can cross short OSM ways that the ordinary potential display
filter removes. Export those ways as connection context beside its two
Tempo-30 anchors; also clip Berlin geometry at the city border. Reviewers
can then follow each gap on the map without losing source identities.
"""

import json
from numbers import Integral

from pathlib import Path

import geopandas as gpd
import pandas as pd

from DataOutput.AdjacentCoveredSegments import AdjacentCoveredSegments
from DataOutput.ConditionalGapMetadata import ConditionalGapMetadata
from DataOutput.DistrictStatsCreator import DistrictStatsCreator
from DataOutput.FacilityPopupCreator import FacilityPopupCreator
from DataOutput.FacilityStreetSegments import FacilityStreetSegments
from DataOutput.MapFacilityLayer import MapFacilityLayer
from DataOutput.OSMVerificationMetadata import OSMVerificationMetadata
from DataOutput.PlaygroundConsolidation import PlaygroundConsolidation
from DataOutput.PotentialStreetConsolidation import PotentialStreetConsolidation
from DataOutput.PotentialStreetDisplay import PotentialStreetDisplay
from DataOutput.PotentialReasonAnnotator import PotentialReasonAnnotator
from DataOutput.SpeedLimitDescription import SpeedLimitDescription
from DataOutput.StreetImageryLinkCreator import StreetImageryLinkCreator
from DataOutput.ZebraCrossingSimplifier import ZebraCrossingSimplifier
from DataRetrieval.RoadClassification import RoadClassification
from PotentialCalculation.AreaScope import AreaScope


class GeoJsonCreator:
    @staticmethod
    def _json_default(value):
        # Mixed numeric OSM IDs and string source IDs can retain numpy integers.
        if isinstance(value, Integral):
            return int(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def create_geojson_layer_files(
        folder_name, streets_with_potential: gpd.GeoDataFrame, streets_w_limit_gdf,
        zebra_gdf, building_data, districts_gdf=None, gap_street_ids=None,
        main_entrances_gdf=None, potential_results=None,
    ):
        export_dir = Path("GEOJSON_EXPORT") / folder_name
        export_dir.mkdir(parents=True, exist_ok=True)

        export_data_dict = {}

        export_data_dict["zebra"] = zebra_gdf.copy()
        export_data_dict["potential_streets"] = streets_with_potential.copy()
        export_data_dict["streets_and_limit"] = streets_w_limit_gdf.copy()
        speed_columns = [
            "maxspeed_conditional_tag", "conditional_speed", "cond_speed_days",
            "cond_speed_starttime", "cond_speed_endtime", "cond_speed_special",
        ]
        for layer in ("streets_and_limit", "potential_streets"):
            if "maxspeed_conditional_tag" not in export_data_dict[layer]:
                export_data_dict[layer]["maxspeed_conditional_tag"] = None
        export_data_dict["streets_and_limit"]["description"] = [
            SpeedLimitDescription.describe(street)
            for _, street in export_data_dict["streets_and_limit"].iterrows()
        ]

        for key, data in building_data.items():
            export_data_dict[key] = data.copy()

        export_data_dict["potential_streets"] = PotentialStreetDisplay.clip_long_ways(
            export_data_dict["potential_streets"], {"zebra": zebra_gdf, **building_data},
            potential_results or {},
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
        gap_result = (potential_results or {}).get("gap")
        export_data_dict["potential_streets"] = ConditionalGapMetadata.annotate(
            export_data_dict["potential_streets"], gap_result, potential_results or {},
            {"zebra": zebra_gdf, **building_data},
        )
        export_data_dict["potential_streets"] = PotentialStreetConsolidation.filter_short_isolated(
            export_data_dict["potential_streets"]
        )
        export_data_dict["potential_streets"] = PotentialStreetConsolidation.consolidate_conditional_gaps(
            export_data_dict["potential_streets"], streets_w_limit_gdf
        )
        retained_street_ids = {
            street_id for ids in export_data_dict["potential_streets"]["source_osm_ids"]
            for street_id in ids
        }
        proposals = FacilityStreetSegments.create(
            streets_w_limit_gdf, building_data, potential_results or {}
        )
        proposals = FacilityStreetSegments.filter_short_isolated(proposals, retained_street_ids)
        export_data_dict["facility_street_segments"] = proposals

        visible_pairs = set(zip(
            proposals["facility_layer"], proposals["facility_id"], proposals["street_osm_id"]
        ))
        export_data_dict["facility_covered_street_segments"] = AdjacentCoveredSegments.create(
            streets_w_limit_gdf, building_data, potential_results or {},
            visible_proposal_pairs=visible_pairs,
        )

        export_data_dict["potential_streets"] = FacilityStreetSegments.annotate_potential_streets(
            export_data_dict["potential_streets"], export_data_dict["facility_street_segments"]
        )
        export_data_dict["potential_streets"] = AdjacentCoveredSegments.annotate_potential_streets(
            export_data_dict["potential_streets"], export_data_dict["facility_covered_street_segments"]
        )
        export_data_dict["potential_streets"] = ConditionalGapMetadata.render_popups(
            export_data_dict["potential_streets"], streets_w_limit_gdf, potential_results
        )

        # Bundle speed limits
        mapping = {
            "50": "T50+",
            "60": "T50+"
        }

        export_data_dict["streets_and_limit"]["maxspeed_class"] =  export_data_dict["streets_and_limit"]["maxspeed_class"].replace(mapping)
        covered = export_data_dict["streets_and_limit"]["maxspeed_class"].map(RoadClassification.is_covered_speed)
        export_data_dict["streets_and_limit"].loc[covered, "maxspeed_class"] = "T30-"

        # Override when conditional speed is 30
        conditional_only = (export_data_dict["streets_and_limit"]["conditional_speed"] == "30") & ~covered
        export_data_dict["streets_and_limit"].loc[conditional_only, "maxspeed_class"] = "Conditional-T30"
        
        # Convert to WGS84
        for entry in export_data_dict.keys():
            export_data_dict[entry] = export_data_dict[entry].to_crs("EPSG:4326")

        # Reduce unnecessary columns
        export_data_dict["potential_streets"] = export_data_dict["potential_streets"][[
            "osm_id",
            "name",
            "maxspeed_class",
            *speed_columns,
            "feature_type",
            "logical_segment_length_m",
            "logical_segment_way_count",
            "source_osm_ids",
            "is_conditional_gap",
            "gap_length_current_m",
            "gap_length_with_prerequisites_m",
            "gap_length_after_m",
            "gap_required_potentials",
            "gap_required_potential_types",
            "gap_required_street_osm_ids",
            "gap_existing_street_osm_ids",
            "gap_corridor_street_osm_ids",
            "description",
            "geometry"
        ]]
        conditional = export_data_dict["potential_streets"]["is_conditional_gap"].eq(True)
        export_data_dict["conditional_gap_streets"] = ConditionalGapMetadata.add_connection_context(
            export_data_dict["potential_streets"].loc[conditional], streets_w_limit_gdf
        )
        export_data_dict["potential_streets"] = export_data_dict["potential_streets"].loc[~conditional].copy()
        direct = export_data_dict["potential_streets"].loc[
            export_data_dict["potential_streets"]["gap_length_current_m"].notna()
        ]
        if not direct.empty:
            visible_source_ids = {
                street_id for ids in export_data_dict["potential_streets"]["source_osm_ids"]
                for street_id in ids
            }
            direct_with_context = ConditionalGapMetadata.add_connection_context(
                direct, streets_w_limit_gdf, gap_kind="direkte"
            )
            context = direct_with_context.loc[direct_with_context["gap_role"].ne("gap")]
            # A traversed way already drawn as a potential needs no second line.
            context = context.loc[
                context["gap_role"].ne("corridor_connection")
                | ~context["osm_id"].isin(visible_source_ids)
            ]
            export_data_dict["potential_streets"]["gap_role"] = "potential"
            export_data_dict["potential_streets"] = gpd.GeoDataFrame(
                pd.concat([export_data_dict["potential_streets"], context], ignore_index=True),
                geometry="geometry", crs=direct.crs,
            )

        export_data_dict["potential_streets"] = PotentialStreetDisplay.categorize(
            export_data_dict["potential_streets"], potential_results or {}
        )
        export_data_dict["conditional_gap_streets"] = PotentialStreetDisplay.categorize(
            export_data_dict["conditional_gap_streets"], potential_results or {}
        )

        export_data_dict["streets_and_limit"] = export_data_dict["streets_and_limit"][[
            "osm_id",
            "name",
            "maxspeed_class",
            *speed_columns,
            "description",
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
                districts_gdf, export_data_dict["zebra"], building_data, gap_streets,
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
            columns.extend(column for column in (
                "source_id", "source_feature_id", "source_name", "source_url",
                "source_type_name", "source_license_url", "additional_sources",
            ) if column in export_data_dict[building_type])
            export_data_dict[building_type] = export_data_dict[building_type][columns]
            export_data_dict[building_type] = OSMVerificationMetadata.add_details(
                export_data_dict[building_type], building_type
            )
            export_data_dict[building_type] = PotentialReasonAnnotator.add_reason(
                export_data_dict[building_type],
                "Warum prüfen? Diese Einrichtung liegt im Suchbereich einer OSM-Straße "
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
            export_data_dict[building_type] = FacilityPopupCreator.create(
                export_data_dict[building_type], building_type,
                export_data_dict["facility_street_segments"],
                export_data_dict["facility_covered_street_segments"],
            )
            export_data_dict[building_type] = export_data_dict[building_type].drop(columns="osm_node_ids")
            export_data_dict[building_type]["facility_id"] = export_data_dict[building_type]["osm_id"]
            external = export_data_dict[building_type]["element_type"].eq("external")
            if external.any():
                export_data_dict[building_type]["osm_id"] = export_data_dict[building_type]["osm_id"].astype(object)
                export_data_dict[building_type].loc[external, "osm_id"] = None

        export_data_dict["playgrounds"] = PlaygroundConsolidation.summarize_playground_features(playgroundGDF = export_data_dict["playgrounds"])

        if districts_gdf is not None:
            for layer, features in export_data_dict.items():
                if layer != "district_stats":
                    export_data_dict[layer] = AreaScope.clip_geometries(features, districts_gdf)

        # Keep complete facility snapshots for statistics and verification;
        # uMap receives a smaller view without already covered facilities.
        for layer in building_data:
            export_data_dict[f"{layer}_map"] = MapFacilityLayer.select(export_data_dict[layer], layer)

        # Export
        for entry in export_data_dict.keys():
            geojson = json.loads(export_data_dict[entry].to_json(default=GeoJsonCreator._json_default))

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
