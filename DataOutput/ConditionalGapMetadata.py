"""Explain which future measures would turn a gap into a direct T30 connection."""

from collections import defaultdict

import geopandas as gpd
import pandas as pd


class ConditionalGapMetadata:
    LABELS = {
        "zebra": "Zebrastreifen",
        "educational_buildings": "Bildungseinrichtung",
        "hospitals": "Krankenhaus",
        "elderly_homes": "Senioren-/Pflegeeinrichtung",
        "playgrounds": "Spielplatz",
        "disability_facilities": "Behinderteneinrichtung",
    }

    @staticmethod
    def _sources_by_street(potential_results, source_layers):
        result = defaultdict(list)
        for kind, potential in potential_results.items():
            features = source_layers.get(kind)
            if features is None or features.empty:
                continue
            by_id = defaultdict(list)
            for _, feature in features.iterrows():
                by_id[feature["osm_id"]].append(feature)
            for source_id, street_id in potential.source_street_pairs or []:
                for feature in by_id[source_id]:
                    url = feature.get("osm_url")
                    if not isinstance(url, str) or not url:
                        url = f"https://www.openstreetmap.org/{feature['element_type']}/{source_id}"
                    name = feature.get("name")
                    result[(kind, street_id)].append({
                        "name": str(name) if pd.notna(name) and str(name).strip() else ConditionalGapMetadata.LABELS.get(kind, kind),
                        "osm_url": url,
                    })
        return result

    @staticmethod
    def annotate(streets: gpd.GeoDataFrame, gap_result, potential_results, source_layers):
        """Add a Boolean plus AND/OR dependency groups to the street export."""
        result = streets.copy()
        dependencies = (gap_result.conditional_gap_dependencies or {}) if gap_result else {}
        sources_by_street = ConditionalGapMetadata._sources_by_street(potential_results, source_layers)
        is_conditional = []
        required_groups = []
        required_types = []
        required_street_ids = []
        descriptions = []

        for _, street in result.iterrows():
            groups = dependencies.get(street["osm_id"], [])
            is_conditional.append(bool(groups))
            details = []
            popup = [street["description"]] if isinstance(street["description"], str) else []
            if groups:
                popup.append(
                    "Bedingter Lückenschluss: Mindestens ein Anschluss ist noch kein "
                    "bestehendes Tempo 30. Erst die folgenden Maßnahmen könnten ihn ermöglichen:"
                )
            for group_index, group in enumerate(groups, start=1):
                options = []
                popup.append(f"Anschluss {group_index} (eine der Alternativen genügt):")
                for kind, anchor_id in group:
                    seen = set()
                    objects = []
                    for source in sources_by_street[(kind, anchor_id)]:
                        if source["osm_url"] not in seen:
                            objects.append(source)
                            seen.add(source["osm_url"])
                    label = ConditionalGapMetadata.LABELS.get(kind, kind)
                    anchor_url = f"https://www.openstreetmap.org/way/{anchor_id}"
                    options.append({
                        "potential_type": kind,
                        "potential_label": label,
                        "anchor_street_osm_id": int(anchor_id),
                        "source_objects": objects,
                    })
                    popup.append(f"{label}: [[{anchor_url}|OSM-Straßenway {anchor_id}]]")
                    for source in objects[:3]:
                        popup.append(f"[[{source['osm_url']}|{source['name']}]]")
                    if len(objects) > 3:
                        popup.append(f"… und {len(objects) - 3} weitere OSM-Objekte")
                details.append(options)
            required_groups.append(details)
            required_types.append(" + ".join(
                " / ".join(option["potential_label"] for option in group) for group in details
            ) if details else None)
            required_street_ids.append(sorted({
                option["anchor_street_osm_id"] for group in details for option in group
            }))
            descriptions.append("\n".join(popup))

        result["is_conditional_gap"] = is_conditional
        result["gap_required_potentials"] = required_groups
        result["gap_required_potential_types"] = required_types
        result["gap_required_street_osm_ids"] = required_street_ids
        result["description"] = descriptions
        return result
