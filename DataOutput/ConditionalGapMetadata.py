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
        direct_lengths = (gap_result.direct_gap_lengths_m or {}) if gap_result else {}
        sources_by_street = ConditionalGapMetadata._sources_by_street(potential_results, source_layers)
        is_conditional = []
        required_groups = []
        required_types = []
        required_street_ids = []

        for _, street in result.iterrows():
            groups = dependencies.get(street["osm_id"], [])
            is_conditional.append(bool(groups))
            details = []
            for group in groups:
                options = []
                for kind, anchor_id in group:
                    seen = set()
                    objects = []
                    for source in sources_by_street[(kind, anchor_id)]:
                        if source["osm_url"] not in seen:
                            objects.append(source)
                            seen.add(source["osm_url"])
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
            source_link = f"[[{source['osm_url']}|{source['name']}]]"
            place = f"am {source_link}" if option["potential_type"] == "zebra" else f"bei {source_link}"
            return heading, f"wenn {place} {location} Tempo 30 angeordnet wird"
        return heading, f"wenn das Potenzial {location} umgesetzt wird"

    @staticmethod
    def render_popups(streets: gpd.GeoDataFrame, reference_streets=None):
        result = streets.copy()
        street_names = {}
        if reference_streets is not None:
            street_names = dict(zip(reference_streets["osm_id"], reference_streets["name"]))

        descriptions = []
        for _, street in result.iterrows():
            lines = [street["description"]] if isinstance(street.get("description"), str) else []
            groups = street["gap_required_potentials"]
            if groups:
                if len(groups) == 1 and len(groups[0]) == 1:
                    heading, condition = ConditionalGapMetadata._option_sentence(groups[0][0], street_names)
                    lines.append(f"Bedingter Lückenschluss {heading}: Möglich, {condition}.")
                else:
                    lines.append("Bedingter Lückenschluss: Möglich nach folgenden Maßnahmen:")
                    for index, group in enumerate(groups, start=1):
                        choices = [ConditionalGapMetadata._option_sentence(option, street_names)[1]
                                   for option in group]
                        lines.append(f"Anschluss {index} (eine Alternative genügt): " + " oder ".join(choices) + ".")

                with_prerequisites = street.get("gap_length_with_prerequisites_m")
                after = street.get("gap_length_after_m")
                if pd.notna(with_prerequisites):
                    length_text = f"{with_prerequisites:.1f}".replace(".", ",")
                    lines.append(f"Tempo-50-Abschnitt einschließlich erforderlichem Anschluss: ca. {length_text} m")
                if pd.notna(after):
                    after_text = f"{after:.1f}".replace(".", ",")
                    lines.append(f"Länge der Lücke nach Anordnung: ca. {after_text} m")
                if pd.notna(with_prerequisites) and pd.notna(after):
                    lines.append("OSM-Näherung: Der gesamte Anschlussabschnitt wird als künftiges Tempo 30 angenommen; Anordnungsgrenzen vor Ort prüfen.")
            else:
                current = street.get("gap_length_current_m")
                if pd.notna(current):
                    current_text = f"{current:.1f}".replace(".", ",")
                    lines.append(f"Länge zwischen bestehenden Tempo-30-Anschlüssen: ca. {current_text} m")
            descriptions.append("\n\n".join(lines))

        result["description"] = descriptions
        return result
