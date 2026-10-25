"""Explain both the normal speed and any conditional limit in a popup.

A road tagged 50 km/h with ``maxspeed:conditional=30 @ (Mo-Fr 07:00-17:00)``
is already slow at certain times. Render the condition alongside the base
limit so the map does not imply an unrestricted 50 km/h road.
"""

import re

import pandas as pd


class SpeedLimitDescription:
    @staticmethod
    def _text(value):
        return str(value).strip() if pd.notna(value) and str(value).strip() else None

    @staticmethod
    def describe(street):
        speed = street["maxspeed_class"]
        if speed == "walk":
            base = "Schrittgeschwindigkeit"
        elif speed == "30_Zone":
            base = "Tempo-30-Zone"
        elif str(speed).isdecimal():
            base = f"{speed} km/h"
        else:
            base = str(speed)
        lines = [f"Höchstgeschwindigkeit: {base}"]

        raw = SpeedLimitDescription._text(street.get("maxspeed_conditional_tag"))
        if raw:
            conditional = re.sub(r"(\d+)\s*@\s*\(([^()]*)\)", r"\1 km/h (\2)", raw)
        else:
            speed = SpeedLimitDescription._text(street.get("conditional_speed"))
            if not speed:
                return lines[0]
            days = SpeedLimitDescription._text(street.get("cond_speed_days"))
            start = SpeedLimitDescription._text(street.get("cond_speed_starttime"))
            end = SpeedLimitDescription._text(street.get("cond_speed_endtime"))
            special = SpeedLimitDescription._text(street.get("cond_speed_special"))
            times = f"{start}-{end}" if start and end else None
            condition = " ".join(part for part in (days, times, special) if part)
            conditional = f"{speed} km/h" + (f" ({condition})" if condition else " (Bedingung nicht erfasst)")
        lines.append(f"Bedingte Höchstgeschwindigkeit: {conditional}")
        return "\n\n".join(lines)
