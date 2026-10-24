from dataclasses import dataclass

from typing import List

@dataclass
class PotentialCalculationResult:
    street_ids: List[int]
    opt_source_ids: List[int] | None = None
    source_street_pairs: List[tuple[int, int]] | None = None
    # Outer list: both ends must be covered (AND). Inner list: one option suffices (OR).
    conditional_gap_dependencies: dict[int, list[list[tuple[str, int]]]] | None = None
    # Only for gaps whose two anchors are already mapped as Tempo 30.
    direct_gap_lengths_m: dict[int, float] | None = None
