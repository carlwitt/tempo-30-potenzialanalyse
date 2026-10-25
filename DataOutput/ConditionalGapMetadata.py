"""Attach verifiable anchors and connecting roads to each gap.

A gap beside a Kita may have an existing Tempo-30 anchor at one end and a
facility-dependent anchor at the other. Record both ends, the traversed OSM
ways and any prerequisite separately. Popups and map lines can then show
the whole connection and make a conditional gap's remaining measure clear.
"""

from collections import defaultdict

import geopandas as gpd
import pandas as pd

from DataOutput.SpeedLimitDescription import SpeedLimitDescription
from DataRetrieval.AdditionalFeatures import facility_url
from DataRetrieval.RoadClassification import RoadClassification


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
                    url = facility_url(feature)
                    if (not isinstance(url, str) or not url) and feature.get("element_type") != "external":
                        url = f"https://www.openstreetmap.org/{feature['element_type']}/{source_id}"
                    name = feature.get("name")
                    result[(kind, street_id)].append({
                        "name": str(name) if pd.notna(name) and str(name).strip() else ConditionalGapMetadata.LABELS.get(kind, kind),
                        "osm_url": url,
                        "source_id": source_id,
                        "external": feature.get("element_type") == "external",
                    })
        return result

    @staticmethod
    def annotate(streets: gpd.GeoDataFrame, gap_result, potential_results, source_layers):
        """Describe alternatives at the sole future end of a conditional gap."""
        result = streets.copy()
        dependencies = (gap_result.conditional_gap_dependencies or {}) if gap_result else {}
        existing_anchors = (gap_result.conditional_gap_existing_anchors or {}) if gap_result else {}
        corridor_ways = (gap_result.gap_corridor_ways or {}) if gap_result else {}
        direct_lengths = (gap_result.direct_gap_lengths_m or {}) if gap_result else {}
        direct_anchors = (gap_result.direct_gap_existing_anchors or {}) if gap_result else {}
        sources_by_street = ConditionalGapMetadata._sources_by_street(potential_results, source_layers)
        is_conditional = []
        required_groups = []
        required_types = []
        required_street_ids = []

        for _, street in result.iterrows():
            groups = dependencies.get(street["osm_id"], [])
            if len(groups) > 1:
                raise ValueError(f"Gap {street['osm_id']} has more than one future T30 end")
            is_conditional.append(bool(groups))
            details = []
            for group in groups:
                options = []
                for kind, anchor_id in group:
                    seen = set()
                    objects = []
                    for source in sources_by_street[(kind, anchor_id)]:
                        if source["source_id"] not in seen:
                            objects.append(source)
                            seen.add(source["source_id"])
                    label = ConditionalGapMetadata.LABELS.get(kind, kind)
                    options.append({
                        "potential_type": kind,
                        "potential_label": label,
                        "anchor_street_osm_id": int(anchor_id),
                        "source_objects": objects,
                    })
                details.append(options)
            required_groups.append(details)
            required_types.append(" + ".join(
                " / ".join(option["potential_label"] for option in group) for group in details
            ) if details else None)
            required_street_ids.append(sorted({
                option["anchor_street_osm_id"] for group in details for option in group
            }))

        result["is_conditional_gap"] = is_conditional
        result["gap_required_potentials"] = required_groups
        result["gap_required_potential_types"] = required_types
        result["gap_required_street_osm_ids"] = required_street_ids
        result["gap_existing_street_osm_ids"] = [
            sorted(set(existing_anchors.get(street_id, []) if conditional else direct_anchors.get(street_id, [])))
            for street_id, conditional in zip(result["osm_id"], is_conditional)
        ]
        result["gap_corridor_street_osm_ids"] = [
            sorted(set(corridor_ways.get(street_id, []))) for street_id in result["osm_id"]
        ]
        result["gap_length_current_m"] = [
            direct_lengths.get(street_id) if not conditional else None
            for street_id, conditional in zip(result["osm_id"], is_conditional)
        ]
        return result

    @staticmethod
    def _option_sentence(option, street_names):
        anchor_id = option["anchor_street_osm_id"]
        anchor_url = f"https://www.openstreetmap.org/way/{anchor_id}"
        raw_name = street_names.get(anchor_id)
        anchor_name = str(raw_name).strip() if pd.notna(raw_name) and str(raw_name).strip() else f"OSM-Abschnitt {anchor_id}"
        anchor = f"[[{anchor_url}|{anchor_name}]]"
        feminine = anchor_name.lower().endswith(("straße", "strasse", "allee"))
        heading = f"zur {anchor}" if feminine else f"zum Straßenabschnitt {anchor}"
        location = f"auf der {anchor}" if feminine else f"auf dem Straßenabschnitt {anchor}"
        source = (option["source_objects"] or [None])[0]
        if source:
            if source.get("external"):
                source_link = source["name"]
                if source.get("osm_url"):
                    source_link += f" ([[{source['osm_url']}|amtliche Quelle]])"
            else:
                source_link = f"[[{source['osm_url']}|{source['name']}]]"
            place = f"am {source_link}" if option["potential_type"] == "zebra" else f"bei {source_link}"
            return heading, f"wenn {place} {location} Tempo 30 angeordnet wird"
        return heading, f"wenn das Potenzial {location} umgesetzt wird"

    @staticmethod
    def render_popups(streets: gpd.GeoDataFrame, reference_streets=None, potential_results=None):
        result = streets.copy()
        street_names = {}
        reference_by_id = {}
        if reference_streets is not None:
            street_names = dict(zip(reference_streets["osm_id"], reference_streets["name"]))
            reference_by_id = {int(street["osm_id"]): street for _, street in reference_streets.iterrows()}

        potential_types = defaultdict(set)
        for kind, potential in (potential_results or {}).items():
            for street_id in potential.street_ids:
                potential_types[int(street_id)].add(kind)

        descriptions = []
        for _, street in result.iterrows():
            lines = [street["description"]] if isinstance(street.get("description"), str) else []
            groups = street["gap_required_potentials"]
            source_ids = street.get("source_osm_ids") or [street["osm_id"]]
            kinds = {kind for source_id in source_ids for kind in potential_types[int(source_id)]}
            direct = pd.notna(street.get("gap_length_current_m"))
            reasons = [ConditionalGapMetadata.LABELS.get(kind, kind) for kind in sorted(kinds - {"gap"})]
            if direct:
                reasons.append("direkter Lückenschluss zwischen bestehenden Tempo-30-Abschnitten")
            elif groups:
                reasons.append("bedingter Lückenschluss mit noch offener Tempo-30-Maßnahme")
            if not reasons:
                reasons = [str(street.get("feature_type") or "Tempo-30-Potenzial")]
            lines.append("Potenzialgrund: " + ", ".join(reasons) + ".")
            corridor_ids = [
                street_id for street_id in street.get("gap_corridor_street_osm_ids", [])
                if street_id not in source_ids
            ]
            if corridor_ids and (groups or direct):
                links = ", ".join(
                    f"[[https://www.openstreetmap.org/way/{street_id}|{street_id}]]"
                    for street_id in corridor_ids
                )
                lines.append(f"Lückenschlusspotenzial entlang dieser Straßenabschnitte: {links}")
            if groups:
                for anchor_id in street.get("gap_existing_street_osm_ids", []):
                    anchor = reference_by_id.get(int(anchor_id))
                    if anchor is not None:
                        name = anchor.get("name")
                        name = str(name).strip() if pd.notna(name) and str(name).strip() else f"OSM-Abschnitt {anchor_id}"
                        lines.append(
                            f"Bestehender Tempo-30-Anschluss: [[https://www.openstreetmap.org/way/{anchor_id}|{name}]] "
                            f"({SpeedLimitDescription.describe(anchor)})"
                        )
                if len(groups) == 1 and len(groups[0]) == 1:
                    heading, condition = ConditionalGapMetadata._option_sentence(groups[0][0], street_names)
                    lines.append(f"Bedingter Lückenschluss {heading}: Möglich, {condition}.")
                else:
                    lines.append("Bedingter Lückenschluss: Möglich nach folgenden Maßnahmen:")
                    for index, group in enumerate(groups, start=1):
                        choices = [ConditionalGapMetadata._option_sentence(option, street_names)[1]
                                   for option in group]
                        lines.append(f"Anschluss {index} (eine Alternative genügt): " + " oder ".join(choices) + ".")

            else:
                current = street.get("gap_length_current_m")
                if pd.notna(current):
                    current_text = f"{current:.1f}".replace(".", ",")
                    lines.append(f"Direkter Lückenschluss: ca. {current_text} m zwischen zwei bestehenden Tempo-30-Anschlüssen.")
                    for anchor_id in street.get("gap_existing_street_osm_ids", []):
                        anchor = reference_by_id.get(int(anchor_id))
                        if anchor is None:
                            continue
                        name = anchor.get("name")
                        name = str(name).strip() if pd.notna(name) and str(name).strip() else f"OSM-Abschnitt {anchor_id}"
                        lines.append(
                            f"Bestehender Tempo-30-Anschluss: [[https://www.openstreetmap.org/way/{anchor_id}|{name}]] "
                            f"({SpeedLimitDescription.describe(anchor)})"
                        )
            descriptions.append("\n\n".join(lines))

        result["description"] = descriptions
        return result

    @staticmethod
    def add_connection_context(gaps: gpd.GeoDataFrame, reference_streets, *, gap_kind="bedingte"):
        """Show existing anchors and traversed roads beside their visible gaps."""
        result = gaps.copy()
        result["gap_role"] = "gap"
        result["target_speed_kmh"] = 30
        result["existing_speed_conditional"] = False
        result["related_gap_osm_ids"] = [[] for _ in range(len(result))]
        if result.empty:
            return result

        connections = {
            "corridor_connection": defaultdict(set),
            "existing_connection": defaultdict(set),
        }
        required_ids = set()
        visible_gap_ids = {
            int(source_id) for source_ids in result["source_osm_ids"] for source_id in source_ids
        }
        for _, gap in result.iterrows():
            for anchor_id in gap["gap_required_street_osm_ids"]:
                required_ids.add(int(anchor_id))
            for anchor_id in gap.get("gap_existing_street_osm_ids", []):
                connections["existing_connection"][int(anchor_id)].update(gap["source_osm_ids"])
            for street_id in gap.get("gap_corridor_street_osm_ids", []):
                if int(street_id) not in visible_gap_ids:
                    connections["corridor_connection"][int(street_id)].update(gap["source_osm_ids"])

        reference = reference_streets.to_crs(gaps.crs).drop_duplicates("osm_id").set_index("osm_id")
        missing_required = required_ids - set(reference.index)
        if missing_required:
            raise ValueError(f"Missing required connection streets: {sorted(missing_required)}")
        missing_existing = set(connections["existing_connection"]) - set(reference.index)
        if missing_existing:
            raise ValueError(f"Missing existing connection streets: {sorted(missing_existing)}")
        missing_corridor = set(connections["corridor_connection"]) - set(reference.index)
        if missing_corridor:
            raise ValueError(f"Missing corridor streets: {sorted(missing_corridor)}")

        records = []
        for role, group in connections.items():
            for anchor_id, gap_ids in sorted(group.items()):
                street = reference.loc[anchor_id]
                name = street["name"]
                name = str(name).strip() if pd.notna(name) and str(name).strip() else f"OSM-Abschnitt {anchor_id}"
                link = f"[[https://www.openstreetmap.org/way/{anchor_id}|{name}]]"
                gap_links = ", ".join(
                    f"[[https://www.openstreetmap.org/way/{gap_id}|{gap_id}]]"
                    for gap_id in sorted(gap_ids)
                )
                existing = role == "existing_connection"
                if existing and not RoadClassification.is_covered_speed(street.get("maxspeed_class")):
                    raise ValueError(f"Existing connection {anchor_id} is not permanently Tempo 30 or slower")
                if not existing:
                    description = (
                        f"Lückenschlusspotenzial: {link}\n\n"
                        f"Aktueller OSM-Ist-Zustand:\n{SpeedLimitDescription.describe(street)}\n\n"
                        "Dieser Straßenabschnitt wurde bei der Suche zwischen Lücke und Anschluss durchlaufen.\n\n"
                        f"Zugehörige {gap_kind} Lückenschlüsse: {gap_links}"
                    )
                else:
                    description = (
                        f"Bestehender Tempo-30-Anschluss: {link}\n\n"
                        + "Aktueller OSM-Ist-Zustand:\n"
                        + SpeedLimitDescription.describe(street)
                        + f"\n\nZugehörige {gap_kind} Lückenschlüsse: {gap_links}"
                    )
                records.append({
                    **{key: value for key, value in street.items() if key in result.columns},
                    "osm_id": anchor_id,
                    "name": name,
                    "source_osm_ids": [anchor_id],
                    "is_conditional_gap": False,
                    "gap_role": role,
                    "target_speed_kmh": None,
                    "existing_speed_conditional": False,
                    "related_gap_osm_ids": sorted(gap_ids),
                    "description": description,
                    "geometry": street.geometry,
                })
        if not records:
            return result
        anchors = gpd.GeoDataFrame(records, geometry="geometry", crs=gaps.crs)
        return gpd.GeoDataFrame(pd.concat([anchors, result], ignore_index=True), crs=gaps.crs)
