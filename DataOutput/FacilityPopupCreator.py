"""Build concise facility popups without discarding detailed source metadata."""

from collections import defaultdict

import geopandas as gpd
import pandas as pd


class FacilityPopupCreator:
    @staticmethod
    def _text(value) -> str | None:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
        return None

    @staticmethod
    def _related(segments: gpd.GeoDataFrame, layer: str) -> dict[int, list]:
        related = defaultdict(list)
        for _, segment in segments.loc[segments["facility_layer"] == layer].iterrows():
            related[segment["facility_id"]].append(segment)
        return related

    @staticmethod
    def create(
        facilities: gpd.GeoDataFrame, layer: str,
        proposed_segments: gpd.GeoDataFrame, covered_segments: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = facilities.copy()
        proposed = FacilityPopupCreator._related(proposed_segments, layer)
        covered = FacilityPopupCreator._related(covered_segments, layer)
        popups = []

        for _, facility in result.iterrows():
            name = FacilityPopupCreator._text(facility.get("name"))
            kind = FacilityPopupCreator._text(facility.get("facility_type"))
            title = name or kind or "Einrichtung ohne OSM-Namen"
            osm_url = FacilityPopupCreator._text(facility.get("osm_url"))
            parts = [f"[[{osm_url}|{title}]]" if osm_url else title]

            # Only show available metadata, so unnamed or operator-less places
            # do not acquire empty labels in the public popup.
            metadata = []
            for key, label in (("official_name", "Offizieller Name"),
                               ("alt_name", "Alternativer Name"),
                               ("operator", "Betreiber")):
                value = FacilityPopupCreator._text(facility.get(key))
                if value and value != name:
                    metadata.append(f"{label}: {value}")
            if metadata:
                parts.append("\n".join(metadata))

            candidate_value = facility.get("potential_candidate")
            candidate = pd.notna(candidate_value) and bool(candidate_value)
            if candidate:
                details = []
                if kind:
                    details.append(f"Einrichtungstyp laut OSM: {kind}")
                reason = FacilityPopupCreator._text(facility.get("potential_reason"))
                if reason:
                    details.append(reason)
                if details:
                    parts.append("\n".join(details))

                roads = {road["street_osm_id"]: road for road in proposed[facility["osm_id"]]}
                if roads:
                    lines = ["Tempo-30-Prüfabschnitte:"]
                    for road in roads.values():
                        lines.append(
                            f"[[{road['street_osm_url']}|{road['street_name']}]] — "
                            f"aktuell {road['current_speed_kmh']} km/h; Abstand {road['distance_m']:.1f} m"
                        )
                    parts.append("\n".join(lines))

                continuations = {road["street_osm_id"]: road for road in covered[facility["osm_id"]]}
                if continuations:
                    lines = ["Angrenzend bereits abgedeckt:"]
                    for road in continuations.values():
                        condition = FacilityPopupCreator._text(road.get("conditional_detail"))
                        status = road["coverage_status"] + (f" ({condition})" if condition else "")
                        lines.append(
                            f"[[{road['street_osm_url']}|{road['street_name']}]] — "
                            f"{status}; ab {road['distance_start_m']:.1f} m"
                        )
                    parts.append("\n".join(lines))

            status = FacilityPopupCreator._text(facility.get("facility_status"))
            if status == "target_group_unknown":
                parts.append("OSM-Zielgruppe nicht erfasst; kein bestätigtes Behinderten-Potenzial.")
            elif status == "different_target_group":
                parts.append("Laut OSM andere Zielgruppe; kein bestätigtes Behinderten-Potenzial.")

            street_view = FacilityPopupCreator._text(facility.get("google_street_view_url"))
            mapillary = FacilityPopupCreator._text(facility.get("mapillary_url"))
            photos = []
            if street_view:
                photos.append(f"[[{street_view}|Google Street View]]")
            if mapillary:
                photos.append(f"[[{mapillary}|Mapillary]]")
            if photos:
                parts.append("Fotos vor Ort: " + " ".join(photos))

            popups.append("\n\n".join(parts))

        result["popup_content"] = popups
        return result
