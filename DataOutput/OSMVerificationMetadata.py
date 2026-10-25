"""Expose the OSM facts behind a facility shown on the map.

A point named "Kita" alone cannot explain why it was classified as a
kindergarten. Add its OSM link, type and available institution tags to the
popup so reviewers can inspect both the classification and the source.
"""

import geopandas as gpd
import pandas as pd
from DataRetrieval.AdditionalFeatures import facility_url


class OSMVerificationMetadata:
    @staticmethod
    def _facility_type(feature, category: str | None) -> str | None:
        amenity = feature.get("amenity")
        subtype = feature.get("social_facility")
        healthcare = feature.get("healthcare")
        if category == "educational_buildings":
            return {"kindergarten": "Kindergarten", "school": "Schule"}.get(amenity, "Bildungseinrichtung")
        if category == "hospitals":
            return "Krankenhaus"
        if category == "elderly_homes":
            return {
                "nursing_home": "Pflegeheim", "assisted_living": "Betreutes Wohnen für Senior:innen",
            }.get(subtype) or {
                "nursing_home": "Pflegeheim", "retirement_home": "Altenheim",
                "care_home": "Pflegeheim",
            }.get(amenity, "Senioren- oder Pflegeeinrichtung")
        if category == "playgrounds":
            return "Spielplatz"
        if category == "disability_facilities":
            labels = {
                "workshop": "Soziale Werkstatt", "outreach": "Beratungs-/Unterstützungsangebot",
                "assisted_living": "Betreutes Wohnen", "nursing_home": "Pflegeeinrichtung",
                "day_care": "Tagesstätte", "day_centre": "Tagesstätte",
                "group_home": "Wohngruppe", "rehabilitation": "Rehabilitationseinrichtung",
            }
            return labels.get(subtype) or {
                "rehabilitation": "Rehabilitationseinrichtung",
                "physiotherapy": "Physiotherapie",
            }.get(healthcare) or {
                "clinic": "Klinik", "craft": "Handwerksbetrieb",
            }.get(amenity, "Soziale Einrichtung; Untertyp in OSM nicht erfasst")
        return None

    @staticmethod
    def add_details(features: gpd.GeoDataFrame, category: str | None = None) -> gpd.GeoDataFrame:
        result = features.copy()
        descriptions = []
        facility_types = []

        for _, feature in result.iterrows():
            name = feature["name"]
            source = feature.get("source_name") if feature.get("element_type") == "external" else "OSM"
            if source == "OSM" and isinstance(feature.get("additional_sources"), list) and feature["additional_sources"]:
                source = "OSM / ergänzenden Quellen"
            lines = [f"Name laut {source}: {name}" if pd.notna(name) and str(name).strip()
                     else f"Kein Name in {source} erfasst."]
            facility_type = OSMVerificationMetadata._facility_type(feature, category)
            facility_types.append(facility_type)
            if facility_type:
                lines.append(f"Einrichtungstyp laut {source}: {facility_type}")
            target = feature.get("social_facility_for")
            if pd.notna(target) and str(target).strip():
                lines.append(f"OSM-Zielgruppe: {target}")
            status = feature.get("facility_status")
            if status == "target_group_unknown":
                lines.append("Einordnung ungeklärt: OSM nennt keine Zielgruppe. Kein bestätigtes Behinderten-Potenzial.")
            elif status == "different_target_group":
                lines.append("Keine Behinderteneinrichtung laut OSM-Zielgruppe; kein entsprechendes Potenzial.")

            for key, label in (("official_name", "Offizieller Name"),
                               ("alt_name", "Alternativer Name"),
                               ("operator", "Betreiber")):
                value = feature[key]
                if pd.notna(value) and str(value).strip() and value != name:
                    lines.append(f"{label}: {value}")

            label = "Externe Quelle prüfen" if feature.get("element_type") == "external" else "OSM-Objekt prüfen"
            lines.append(f"[[{facility_url(feature)}|{label}]]")
            descriptions.append("\n".join(lines))

        result["description"] = descriptions
        if category is not None:
            result["facility_type"] = facility_types
        return result
