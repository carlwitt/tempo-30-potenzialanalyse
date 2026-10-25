"""Find eligible Tempo-50/60 links between verifiable slow-road anchors.

A gap way can connect two existing Tempo-30 roads through several short
OSM ways, as at way 1414867517. Trace those intermediate ways and record
both reached anchors. If one end instead needs a separate facility or
crossing measure, record that prerequisite as a conditional gap.
"""

import math
from itertools import product

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from tqdm import tqdm

from DataRetrieval.RoadClassification import RoadClassification
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult

class Tempo50GapPotential:

    # -----------------------------------------------------
    # Vorbereitung
    # -----------------------------------------------------
    @staticmethod
    def prepare_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        gdf = gdf.to_crs("EPSG:25832").copy()  # proper length calc

        gdf["length_m"] = gdf.geometry.length
        gdf = gdf.to_crs("EPSG:3857").copy() # proper angle calc

        gdf["start_pt"] = gdf.geometry.apply(lambda g: Point(g.coords[0]))
        gdf["end_pt"] = gdf.geometry.apply(lambda g: Point(g.coords[-1]))
        
        gdf[["angle_start", "angle_end"]] = gdf.geometry.apply(
            lambda g: pd.Series(Tempo50GapPotential.calculate_segment_end_angles(g))
        )

        return gdf

    # -----------------------------------------------------
    # Winkelberechnung
    # -----------------------------------------------------
    @staticmethod
    def calculate_segment_end_angles(line) -> tuple[float, float]:
        """
        Returns compass bearings (0° = North, clockwise) for both ends of a LineString:
        - angle_start: from first point to second point
        - angle_end:   from last point to second-last point
        """

        coords = list(line.coords)

        if len(coords) < 2:
            raise ValueError("LineString must have at least two points")

        # --- start angle: first -> second
        x1, y1 = coords[0]
        x2, y2 = coords[1]

        dx_start = x2 - x1
        dy_start = y2 - y1
        angle_start = math.degrees(math.atan2(dx_start, dy_start)) % 360

        # --- end angle: last -> second-last
        xn, yn = coords[-1]
        xp, yp = coords[-2]

        dx_end = xp - xn
        dy_end = yp - yn
        angle_end = math.degrees(math.atan2(dx_end, dy_end)) % 360

        return angle_start, angle_end


    @staticmethod
    def axis_angle_diff(a1: float, a2: float) -> float:
        """
        Smallest difference between two compass bearings,
        ignoring opposite direction (i.e. 0° == 180°).
        """
        diff = abs(a1 - a2) % 360
        diff = min(diff, 360 - diff)
        return min(diff, abs(diff - 180))

    @staticmethod
    def evaluate_gap(
        seg,
        gdf,
        max_total_length: float = 500,
        min_total_length: float = 30,
        potential_types_by_street: dict[int, set[str]] | None = None,
    ) -> tuple[bool, list[list[tuple[str, int]]]]:
        found, groups, _ = Tempo50GapPotential._evaluate_gap_with_length(
            seg, gdf, max_total_length, min_total_length, potential_types_by_street
        )
        return found, groups

    @staticmethod
    def _evaluate_gap_with_length(
        seg,
        gdf,
        max_total_length: float = 500,
        min_total_length: float = 30,
        potential_types_by_street: dict[int, set[str]] | None = None,
    ) -> tuple[bool, list[list[tuple[str, int]]], float | None]:
        found, groups, length, _, _ = Tempo50GapPotential._evaluate_gap_with_anchors(
            seg, gdf, max_total_length, min_total_length, potential_types_by_street,
        )
        return found, groups, length

    @staticmethod
    def _evaluate_gap_with_anchors(
        seg,
        gdf,
        max_total_length: float = 500,
        min_total_length: float = 30,
        potential_types_by_street: dict[int, set[str]] | None = None,
    ) -> tuple[bool, list[list[tuple[str, int]]], float | None, list[int], list[int]]:
        potential_types_by_street = potential_types_by_street or {}

        ends = []
        for used_point, base_angle in (
            (seg.start_pt, seg.angle_start),
            (seg.end_pt, seg.angle_end),
        ):

            if Tempo50GapPotential.all_directions_tempo30(seg, used_point, gdf):
                touching = gdf[(gdf.geometry.touches(used_point)) & (gdf.index != seg.name)]
                ends.append([(0.0, [], sorted(int(value) for value in touching.osm_id), [])])
                continue

            ok, length, options, anchor_ids, corridor_ids = Tempo50GapPotential.follow_straight_chain(
                seg, used_point, base_angle, gdf,
                potential_types_by_street=potential_types_by_street,
            )
            if not ok:
                return False, [], None, [], []

            alternatives = [(length, options, anchor_ids, corridor_ids)]
            if options:
                # A prospective anchor can hide an existing T30 farther along
                # the same road. Keep that alternative to avoid rejecting a
                # valid one-future-end gap, or downgrading a direct gap.
                existing, existing_length, _, existing_anchor_ids, existing_corridor_ids = Tempo50GapPotential.follow_straight_chain(
                    seg, used_point, base_angle, gdf,
                )
                if existing:
                    alternatives.append((existing_length, [], existing_anchor_ids, existing_corridor_ids))
            ends.append(alternatives)

        candidates = []
        for first, second in product(*ends):
            required_groups = [options for _, options, _, _ in (first, second) if options]
            # Exactly one end may still need a separate measure; two future
            # anchors do not constitute a conditional gap.
            if len(required_groups) > 1:
                continue
            total = first[0] + second[0] + seg.length_m
            if min_total_length <= total <= max_total_length:
                existing_anchor_ids = sorted({
                    anchor_id for _, _, anchor_ids, _ in (first, second) for anchor_id in anchor_ids
                })
                if not required_groups and len(existing_anchor_ids) < 2:
                    # One mapped street touching both ends does not provide
                    # two independently verifiable Tempo-30 connections.
                    continue
                corridor_ids = sorted({
                    street_id for _, _, _, path in (first, second) for street_id in path
                })
                candidates.append((required_groups, total, existing_anchor_ids, corridor_ids))
        if not candidates:
            return False, [], None, [], []
        # Existing T30 at both ends takes precedence over a shorter future link.
        groups, total, existing_anchor_ids, corridor_ids = min(
            candidates, key=lambda item: (len(item[0]), item[1])
        )
        return True, groups, total, existing_anchor_ids, corridor_ids
       
    
    @staticmethod
    def all_directions_tempo30(seg, point, gdf):
        """
        If every connected segment at this point is Tempo-30, return True.
        """
        touching = gdf[(gdf.geometry.touches(point)) & (gdf.index != seg.name)]
        if touching.empty:
            return False
        
    
        return touching["maxspeed_class"].map(RoadClassification.is_covered_speed).all()


    @staticmethod
    def follow_straight_chain(
        start_seg, start_point, start_angle, gdf, max_depth=10, angle_tol=30,
        potential_types_by_street: dict[int, set[str]] | None = None,
    ):

        current_seg = start_seg
        current_point = start_point
        current_angle = start_angle

        visited = {start_seg.osm_id}
        total_length = 0.0  # Excludes the starting segment.
        corridor_ids = []
        gdf_spatial_index = gdf.sindex
        for _ in range(max_depth):

            # Query only streets at the current endpoint.
            possible = list(gdf_spatial_index.intersection(current_point.bounds))
            candidates = gdf.iloc[possible]

            candidates = candidates[
                (candidates.geometry.touches(current_point)) &
                (candidates.index != current_seg.name)
            ]

            if candidates.empty:
                return False, total_length, [], [], []

            continuations = []
            for _, cand in candidates.iterrows():
                if cand.start_pt.equals(current_point):
                    cand_angle = cand.angle_start
                elif cand.end_pt.equals(current_point):
                    cand_angle = cand.angle_end
                else:
                    continue

                diff = Tempo50GapPotential.axis_angle_diff(current_angle, cand_angle)
                if diff > angle_tol or cand.osm_id in visited:
                    continue
                current_name = current_seg["name"]
                same_name = (pd.notna(current_name) and pd.notna(cand["name"])
                             and current_name == cand["name"])
                continuations.append((not same_name, diff, int(cand.osm_id), cand))

            if not continuations:
                return False, total_length, [], [], []
            _, _, _, best_cand = min(continuations, key=lambda item: item[:3])

            # A permanent low-speed road closes this end of the gap.
            if RoadClassification.is_covered_speed(best_cand.maxspeed_class):
                return True, total_length, [], [int(best_cand.osm_id)], corridor_ids

            # A tagged facility/crossing potential would become the second
            # Tempo-30 anchor only after that separate measure is realized.
            potential_types = (potential_types_by_street or {}).get(best_cand.osm_id, set())
            if potential_types:
                options = [(kind, best_cand.osm_id) for kind in sorted(potential_types)]
                return True, total_length, options, [], corridor_ids

            # A corridor is part of the proposed change. Its current speed
            # must be known and continuously eligible; an untagged or already
            # conditionally slow way cannot silently bridge two anchors.
            if (best_cand.maxspeed_class not in {"50", "60"}
                    or best_cand.conditional_speed == "30"):
                return False, total_length, [], [], []

            visited.add(best_cand.osm_id)
            corridor_ids.append(int(best_cand.osm_id))
            total_length += best_cand.length_m

            if best_cand.start_pt.equals(current_point):
                current_point = best_cand.end_pt
                current_angle = best_cand.angle_end
            else:
                current_point = best_cand.start_pt
                current_angle = best_cand.angle_start

            current_seg = best_cand

        return False, total_length, [], [], []


    # -----------------------------------------------------
    # Hauptfunktion
    # -----------------------------------------------------
    @staticmethod
    def find_all_tempo_50_gaps(
        gdf: gpd.GeoDataFrame,
        potential_results: dict[str, PotentialCalculationResult] | None = None,
    ) -> PotentialCalculationResult:
        gdf = Tempo50GapPotential.prepare_gdf(gdf)

        # Only independent, still-open facility/crossing potentials may serve
        # as future anchors; a gap must never depend on another gap.
        potential_types_by_street = {}
        for kind, potential in (potential_results or {}).items():
            if kind == "gap":
                continue
            for street_id in potential.street_ids:
                potential_types_by_street.setdefault(street_id, set()).add(kind)

        classified_permanent_tempo50_or_60 = gdf[
            (gdf["maxspeed_class"].isin({"50", "60"})) &
            (gdf["length_m"] < 500) & 
            (gdf["conditional_speed"] != "30")
        ]

        result = []
        conditional_dependencies = {}
        conditional_existing_anchors = {}
        gap_corridor_ways = {}
        direct_lengths = {}
        direct_existing_anchors = {}

        for _, seg in tqdm(classified_permanent_tempo50_or_60.iterrows(),
                        total=len(classified_permanent_tempo50_or_60),
                        desc="Checking segments"):
            
            found, required_groups, corridor_length, existing_anchor_ids, corridor_ids = Tempo50GapPotential._evaluate_gap_with_anchors(
                seg, gdf, potential_types_by_street=potential_types_by_street
            )
            if found:
                result.append(seg.osm_id)
                gap_corridor_ways[seg.osm_id] = corridor_ids
                if required_groups:
                    conditional_dependencies[seg.osm_id] = required_groups
                    if not existing_anchor_ids:
                        raise ValueError(f"Conditional gap {seg.osm_id} has no existing Tempo 30 anchor")
                    conditional_existing_anchors[seg.osm_id] = existing_anchor_ids
                elif corridor_length is not None:
                    direct_lengths[seg.osm_id] = round(corridor_length, 1)
                    direct_existing_anchors[seg.osm_id] = existing_anchor_ids

        return PotentialCalculationResult(
            street_ids=result,
            conditional_gap_dependencies=conditional_dependencies,
            conditional_gap_existing_anchors=conditional_existing_anchors,
            gap_corridor_ways=gap_corridor_ways,
            direct_gap_lengths_m=direct_lengths,
            direct_gap_existing_anchors=direct_existing_anchors,
        )
