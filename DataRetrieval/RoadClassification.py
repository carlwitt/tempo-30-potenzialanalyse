"""Decide which OSM roads are public and what their tags say about speed.

A private driveway or bicycle road must not create a car-traffic gap; an
untagged speed must not be guessed as Tempo 50. Apply specific access tags
before general ones and keep unknown speeds unknown, so only supported
road evidence enters the potential calculation.
"""

import re

import pandas as pd


class RoadClassification:
    MOTOR_ROADS = frozenset({
        "motorway", "motorway_link", "trunk", "trunk_link",
        "primary", "primary_link", "secondary", "secondary_link",
        "tertiary", "tertiary_link", "unclassified", "residential",
        "living_street", "service", "road",
    })
    EXCLUDED_SERVICE = frozenset({
        "driveway", "parking_aisle", "emergency_access", "drive-through",
        "training", "delivery",
    })
    PUBLIC_ACCESS = frozenset({"yes", "designated", "permissive", "destination", "customers"})
    ACCESS_KEYS = ("motorcar", "motor_vehicle", "vehicle", "access")

    @staticmethod
    def _access(tags):
        """The most specific tagged vehicle restriction takes precedence."""
        for key in RoadClassification.ACCESS_KEYS:
            value = tags.get(key)
            if pd.isna(value) or not str(value).strip():
                continue
            options = {part.strip().lower() for part in str(value).split(";")}
            if options & {"private", "no"}:
                return False
            return bool(options & RoadClassification.PUBLIC_ACCESS)
        return None

    @staticmethod
    def _is_bicycle_road(tags) -> bool:
        return (
            tags.get("bicycle_road") == "yes"
            or str(tags.get("maxspeed:type") or "").lower() == "de:bicycle_road"
            or str(tags.get("source:maxspeed") or "").lower() == "de:bicycle_road"
        )

    @staticmethod
    def allows_public_motorcar(tags) -> bool:
        highway = tags.get("highway")
        access = RoadClassification._access(tags)
        if highway not in RoadClassification.MOTOR_ROADS and highway != "track":
            return False
        if access is False:
            return False
        if highway == "track":
            return access is True
        if RoadClassification._is_bicycle_road(tags) and access is not True:
            return False
        if highway == "service" and tags.get("service") in RoadClassification.EXCLUDED_SERVICE:
            return access is True
        return True

    @staticmethod
    def _zone_speed(tags):
        zone = tags.get("zone:maxspeed")
        if zone:
            match = re.fullmatch(r"(?:DE:)?(10|20|30)", str(zone), re.IGNORECASE)
            if match:
                return match.group(1)

        for key in ("maxspeed:type", "source:maxspeed"):
            value = str(tags.get(key) or "")
            match = re.fullmatch(r"DE:zone:?([123]0)", value, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def classify_speed(tags) -> str:
        """Never infer urban Tempo 50 from a missing maxspeed tag."""
        explicit = str(tags.get("maxspeed") or "").strip().lower()
        kind = str(tags.get("maxspeed:type") or "").lower()
        source = str(tags.get("source:maxspeed") or "").lower()
        living = (
            tags.get("highway") == "living_street"
            or tags.get("living_street") == "yes"
            or kind in {"de:living_street", "living_street"}
            or source in {"de:living_street", "de:walk", "living_street"}
            or explicit == "walk"
        )
        if living:
            return "walk"

        zone = RoadClassification._zone_speed(tags)
        if explicit.isdecimal() and int(explicit) <= 30:
            return "30_Zone" if explicit == "30" and zone == "30" else explicit
        if zone:
            return "30_Zone" if zone == "30" else zone

        if RoadClassification._is_bicycle_road(tags):
            return "30"
        if explicit.isdecimal():
            return explicit
        return "Keine Daten"

    @staticmethod
    def classify_speed_legacy(tags) -> str:
        """Match the published Munich classes before inferred low-speed tags."""
        explicit = tags.get("maxspeed")
        if explicit in {"10", "20", "30"}:
            return explicit
        if tags.get("zone:maxspeed") == "30":
            return "30_Zone"
        if explicit in {"50", "60"}:
            return explicit
        return "Keine Daten"

    @staticmethod
    def is_covered_speed(value) -> bool:
        return value in {"walk", "30_Zone"} or str(value).isdecimal() and int(value) <= 30
