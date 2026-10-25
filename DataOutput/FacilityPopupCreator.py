"""Summarize a facility's nearby proposed and already slow streets.

A school's raw OSM metadata can be lengthy while its map popup needs the
matched road names, speeds and source links. Build that readable summary
from the exact street matches; keep the original metadata in the export
so reviewers can still verify the school and its source.
"""

from collections import defaultdict

import geopandas as gpd
import pandas as pd
from DataRetrieval.AdditionalFeatures import facility_url


class FacilityPopupCreator:
    @staticmethod
    def _text(value) -> str | None:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
        return None

    @staticmethod
    def _related(segments: gpd.GeoDataFrame, layer: str) -> dict[int | str, list]:
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
            url = FacilityPopupCreator._text(facility_url(facility))
            external = facility.get("element_type") == "external"
            parts = [title if external else (f"[[{url}|{title}]]" if url else title)]
            if kind:
                parts.append(f"Einrichtung: {kind}")
            if external:
                source_name = ("Amtliches Berliner Kita-Verzeichnis" if facility["source_name"] == "berlin_kita"
                               else facility["source_name"])
                source_link = f"[[{url}|{source_name}]]" if url else source_name
                parts.append(f"Quelle: {source_link} (kein zugeordnetes OSM-Objekt)")
            elif isinstance(facility.get("additional_sources"), list) and facility["additional_sources"]:
                names = ", ".join(dict.fromkeys(source["source_name"] for source in facility["additional_sources"]))
                parts.append(f"OSM mit ergänzenden Angaben aus: {names}")

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
                entrance_ids = facility.get("main_entrance_osm_ids")
                if isinstance(entrance_ids, list) and entrance_ids:
                    links = [
                        f"[[https://www.openstreetmap.org/node/{node_id}|OSM-Eingang {node_id}]]"
                        for node_id in dict.fromkeys(entrance_ids)
                    ]
                    reference = FacilityPopupCreator._text(facility.get("imagery_reference"))
                    parts.append("Haupteingang prüfen: " + ", ".join(links)
                                 + (f" ({reference})" if reference else ""))
                details = []
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
                            + (" zum OSM-Haupteingang" if road.get("distance_reference") == "OSM-Haupteingang" else "")
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
                parts.append("Fotos vor Ort\n" + "\n".join(photos))

            popups.append("\n\n".join(parts))

        result["popup_content"] = popups
        return result
