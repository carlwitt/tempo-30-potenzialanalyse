from dataclasses import dataclass

from typing import List

@dataclass
class PotentialCalculationResult:
    street_ids: List[int]
    opt_source_ids: List[int] | None = None
    source_street_pairs: List[tuple[int, int]] | None = None
