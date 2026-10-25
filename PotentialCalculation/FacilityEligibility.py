"""Classify disability facilities by their explicit OSM target-group tag.

Problem: A name such as "Werkstatt Inklusion" can match the facility search
without proving whom the facility serves.
Goal: Use only confirmed disability facilities for the street potential.
Action: Read ``social_facility_for``; ``disabled`` confirms the target group,
another value rules it out, and a missing value remains unknown.
Impact: Suggestive names alone cannot create disability-related street
potential, while unconfirmed facilities remain in the full export for review.
"""

import re

import geopandas as gpd
import pandas as pd


class FacilityEligibility:
    @staticmethod
    def annotate_disability(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Classify ``senior;disabled`` as confirmed, ``juvenile`` as other.

        A blank target-group tag remains unknown and never creates a
        disability-related street candidate by itself.
        """
        result = features.copy()
        statuses = []
        for target in result["social_facility_for"]:
            groups = {part.strip().casefold() for part in re.split(
                r"[;,]", str(target) if pd.notna(target) else ""
            )}
            if "disabled" in groups:
                statuses.append("confirmed_disabled")
            elif groups - {""}:
                statuses.append("different_target_group")
            else:
                statuses.append("target_group_unknown")
        result["facility_status"] = statuses
        return result
