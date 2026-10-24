"""Aggregate potential statistics into Berlin district polygons."""

import geopandas as gpd
import pandas as pd


class DistrictStatsCreator:
    """Count source features by district; percentages are potential / total.

    A feature belongs to the district containing its representative point.
    Facility counts use the traffic-adjacent source features supplied by the
    pipeline, including playground points that the presentation layer later
    hides. "Realized" means no open potential under the current pipeline rules.
    A zero total has no percentage.
    """

    FACILITY_LAYERS = (
        "disability_facilities",
        "educational_buildings",
        "elderly_homes",
        "hospitals",
        "playgrounds",
    )

    @staticmethod
    def _assigned_features(districts: gpd.GeoDataFrame, features: gpd.GeoDataFrame | None):
        if features is None or features.empty:
            return

        locations = features.to_crs(districts.crs).copy()
        locations["geometry"] = locations.geometry.representative_point()
        for _, feature in locations.iterrows():
            matches = districts.index[districts.geometry.covers(feature.geometry)].tolist()
            if not matches:
                continue
            district = min(matches, key=lambda index: districts.at[index, "district_id"])
            yield district, feature

    @staticmethod
    def _counts(districts: gpd.GeoDataFrame, features: gpd.GeoDataFrame | None):
        counts = {index: [0, 0] for index in districts.index}
        for district, feature in DistrictStatsCreator._assigned_features(districts, features):
            counts[district][0] += 1
            potential = feature["potential_candidate"]
            counts[district][1] += int(pd.notna(potential) and bool(potential))
        return counts

    @staticmethod
    def create(
        districts: gpd.GeoDataFrame,
        crossings: gpd.GeoDataFrame,
        facilities: dict[str, gpd.GeoDataFrame] | None = None,
        gap_streets: gpd.GeoDataFrame | None = None,
        conditional_gap_street_ids: set[int] | None = None,
    ) -> gpd.GeoDataFrame:
        """Count markers, facilities and gap segments by district."""
        result = districts.to_crs("EPSG:4326").copy()
        markers = crossings.loc[crossings["display_role"] == "marker"]
        layers = {"crossing": markers}
        layers.update({name: (facilities or {}).get(name) for name in DistrictStatsCreator.FACILITY_LAYERS})
        disability = layers["disability_facilities"]
        if disability is not None and "facility_status" in disability:
            layers["disability_facilities"] = disability.loc[
                disability["facility_status"] == "confirmed_disabled"
            ]
        for name, features in layers.items():
            counts = DistrictStatsCreator._counts(result, features)
            result[f"{name}_total"] = [counts[index][0] for index in result.index]
            result[f"{name}_potential"] = [counts[index][1] for index in result.index]
            result[f"{name}_potential_pct"] = [
                round(100 * counts[index][1] / counts[index][0], 1) if counts[index][0] else None
                for index in result.index
            ]

        # Keep the existing plural fields and expose the requested playground labels.
        result["playgrounds"] = result["playgrounds_total"]
        result["playground_potential"] = result["playgrounds_potential"]
        result["playground_potential_pct"] = result["playgrounds_potential_pct"]

        gap_counts = {index: 0 for index in result.index}
        for district, _ in DistrictStatsCreator._assigned_features(result, gap_streets):
            gap_counts[district] += 1
        result["gap_potential"] = [gap_counts[index] for index in result.index]
        conditional_gap_streets = None
        if gap_streets is not None and conditional_gap_street_ids:
            conditional_gap_streets = gap_streets.loc[
                gap_streets["osm_id"].isin(conditional_gap_street_ids)
            ]
        conditional_counts = {index: 0 for index in result.index}
        for district, _ in DistrictStatsCreator._assigned_features(result, conditional_gap_streets):
            conditional_counts[district] += 1
        result["gap_conditional_potential"] = [conditional_counts[index] for index in result.index]
        result["gap_direct_potential"] = result["gap_potential"] - result["gap_conditional_potential"]

        # Gaps describe road segments, not a stock of covered/uncovered objects.
        result["all_types_total"] = result[[f"{name}_total" for name in layers]].sum(axis=1)
        result["all_types_potential"] = result[[f"{name}_potential" for name in layers]].sum(axis=1)
        result["all_types_realized"] = result["all_types_total"] - result["all_types_potential"]
        result["realized_potential_pct_total"] = [
            round(100 * realized / total, 1) if total else None
            for realized, total in zip(result["all_types_realized"], result["all_types_total"])
        ]
        return result
