"""Separate OSM evidence for a disability facility from a suggestive name."""

import re

import geopandas as gpd
import pandas as pd


class FacilityEligibility:
    @staticmethod
    def annotate_disability(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        result = features.copy()
        statuses = []
        for target in result["social_facility_for"]:
            groups = {part.strip() for part in re.split(r"[;,]", str(target) if pd.notna(target) else "")}
            if "disabled" in groups:
                statuses.append("confirmed_disabled")
            elif groups - {""}:
                statuses.append("different_target_group")
            else:
                statuses.append("target_group_unknown")
        result["facility_status"] = statuses
        return result
