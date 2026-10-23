"""Show the OSM source and its institution metadata in facility popups."""

import geopandas as gpd
import pandas as pd


class OSMVerificationMetadata:
    @staticmethod
    def _facility_type(feature, category: str | None) -> str | None:
        amenity = feature.get("amenity")
        subtype = feature.get("social_facility")
        if category == "educational_buildings":
            return {"kindergarten": "Kindertagesstätte", "school": "Schule"}.get(amenity, "Bildungseinrichtung")
        if category == "hospitals":
            return "Krankenhaus (OSM-Kennzeichnung)"
        if category == "elderly_homes":
            return {
                "nursing_home": "Pflegeheim", "assisted_living": "Betreutes Wohnen für Senior:innen",
            }.get(subtype, "Senioren- oder Pflegeeinrichtung (OSM-Kennzeichnung)")
        if category == "playgrounds":
            return "Spielplatz"
        if category == "disability_facilities":
            labels = {
                "workshop": "Soziale Werkstatt", "outreach": "Beratungs-/Unterstützungsangebot",
                "assisted_living": "Betreutes Wohnen", "nursing_home": "Pflegeeinrichtung",
                "day_centre": "Tagesstätte",
            }
            return labels.get(subtype, "Soziale Einrichtung; Untertyp in OSM nicht erfasst")
        return None

    @staticmethod
    def add_details(features: gpd.GeoDataFrame, category: str | None = None) -> gpd.GeoDataFrame:
        result = features.copy()
        descriptions = []
        facility_types = []

        for _, feature in result.iterrows():
            name = feature["name"]
            lines = [f"Name laut OSM: {name}" if pd.notna(name) and str(name).strip()
                     else "Kein Name in OSM erfasst."]
            facility_type = OSMVerificationMetadata._facility_type(feature, category)
            facility_types.append(facility_type)
            if facility_type:
                lines.append(f"Einrichtungstyp laut OSM: {facility_type}")
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

            lines.append(f"[[{feature['osm_url']}|OSM-Objekt prüfen]]")
            descriptions.append("\n".join(lines))

        result["description"] = descriptions
        if category is not None:
            result["facility_type"] = facility_types
        return result
