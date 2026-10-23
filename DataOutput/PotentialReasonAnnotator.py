"""Add a human-readable explanation to potential feature popups."""

import geopandas as gpd
import pandas as pd


class PotentialReasonAnnotator:
    @staticmethod
    def add_reason(features: gpd.GeoDataFrame, reason: str) -> gpd.GeoDataFrame:
        """Annotate true potential candidates without changing their classification."""
        result = features.copy()
        descriptions = result["description"] if "description" in result else [None] * len(result)
        notes = []
        popup_text = []
        for candidate, description in zip(result["potential_candidate"], descriptions):
            note = reason if pd.notna(candidate) and bool(candidate) else None
            notes.append(note)
            if note and isinstance(description, str) and description.strip():
                popup_text.append(f"{description.strip()}\n{note}")
            else:
                popup_text.append(note or description)

        result["potential_reason"] = notes
        result["description"] = popup_text
        return result
