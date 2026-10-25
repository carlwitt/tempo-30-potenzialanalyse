"""Carry street candidates and the evidence needed to explain them.

A direct gap needs its current length, two existing slow-road anchors and
any intervening OSM ways. A conditional gap needs its existing anchor and
alternative future measures. Keeping these fields distinct lets export
draw a continuous route without presenting future work as already built.
"""

from dataclasses import dataclass

from typing import List

@dataclass
class PotentialCalculationResult:
    street_ids: List[int]
    opt_source_ids: List[int | str] | None = None
    source_street_pairs: List[tuple[int | str, int]] | None = None
    # At most one future end per gap; its inner list contains alternative
    # facility/crossing measures (OR). The opposite end must already be T30.
    conditional_gap_dependencies: dict[int, list[list[tuple[str, int]]]] | None = None
    # Existing slow OSM ways actually reached at the opposite end of a
    # conditional gap. Keep these separate from the future prerequisites.
    conditional_gap_existing_anchors: dict[int, list[int]] | None = None
    # Intermediate OSM ways followed to reach both ends of any gap.
    gap_corridor_ways: dict[int, list[int]] | None = None
    # Only for gaps whose two anchors are already mapped as Tempo 30.
    direct_gap_lengths_m: dict[int, float] | None = None
    direct_gap_existing_anchors: dict[int, list[int]] | None = None
