"""Point map reviewers at imagery of the relevant street location.

For a Kita with an entrance away from its polygon center, imagery at the
center can show the wrong road. Use the entrance when available, snap to
the nearby candidate street and add Street View or Mapillary links to
the popup; the link then reflects the location being assessed.
"""

from datetime import date

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.strtree import STRtree

from PotentialCalculation.EntranceEvidence import EntranceEvidence


class StreetImageryLinkCreator:
    MAX_SNAP_DISTANCE_M = 100

    @staticmethod
    def _location(geometry):
        if isinstance(geometry, (LineString, MultiLineString)):
            return geometry.interpolate(0.5, normalized=True)
        return geometry.representative_point()

    @staticmethod
    def add_links(
        features: gpd.GeoDataFrame,
        streets: gpd.GeoDataFrame,
        mapillary_since: date | None = None,
        main_entrances: gpd.GeoDataFrame | None = None,
        use_area_entrances: bool = True,
    ) -> gpd.GeoDataFrame:
        """Snap imagery from the entrance or feature to its nearest T50 street."""
        result = features.copy()
        if result.empty:
            result["description"] = []
            result["google_street_view_url"] = []
            result["mapillary_url"] = []
            if main_entrances is not None:
                result["imagery_reference"] = []
                result["main_entrance_osm_ids"] = []
            return result

        metric_crs = features.crs if features.crs.is_projected else features.estimate_utm_crs()
        metric_features = features.to_crs(metric_crs)
        if "maxspeed_class" not in streets:
            raise ValueError("Street imagery links require a maxspeed_class column")
        eligible_streets = streets[streets["maxspeed_class"].isin({"50", "60", "T50+"})]
        metric_streets = eligible_streets.to_crs(metric_crs)
        segments = [
            geometry for geometry in metric_streets.geometry
            if isinstance(geometry, (LineString, MultiLineString)) and not geometry.is_empty
        ]
        if not segments:
            result["google_street_view_url"] = [None] * len(result)
            result["mapillary_url"] = [None] * len(result)
            if main_entrances is not None:
                note = "keine Tempo-50/60-Straße im Gebiet"
                result["imagery_reference"] = [note] * len(result)
                result["main_entrance_osm_ids"] = [[] for _ in range(len(result))]
                descriptions = result["description"] if "description" in result else [None] * len(result)
                result["description"] = [
                    "\n".join(part for part in (description, f"Bildstandort: {note}")
                              if isinstance(part, str) and part.strip())
                    for description in descriptions
                ]
            return result

        tree = STRtree(segments)
        entrance_by_id = {}
        metric_entrances = None
        if main_entrances is not None and not main_entrances.empty:
            metric_entrances = main_entrances.to_crs(metric_crs)
            entrance_by_id = dict(zip(metric_entrances["osm_id"], metric_entrances.geometry))

        snapped_points = []
        references = []
        entrance_ids_by_feature = []
        for _, feature in metric_features.iterrows():
            entrances, reference, entrance_ids = EntranceEvidence.points_for_feature(
                feature, metric_entrances, entrance_by_id, use_area=use_area_entrances,
            )
            entrance_ids_by_feature.append(entrance_ids)
            if entrances:
                location = min(
                    entrances,
                    key=lambda point: segments[tree.nearest(point)].distance(point),
                )
                references.append(reference)
            else:
                location = StreetImageryLinkCreator._location(feature.geometry)
                references.append("angenähert; kein OSM-Haupteingang am Objekt")
            segment = segments[tree.nearest(location)]
            if location.distance(segment) > StreetImageryLinkCreator.MAX_SNAP_DISTANCE_M:
                snapped_points.append(None)
                references[-1] = "keine Tempo-50/60-Straße innerhalb von 100 m"
            else:
                snapped_points.append(segment.interpolate(segment.project(location)))

        # Both providers use WGS84 latitude/longitude, regardless of input CRS.
        viewpoints = gpd.GeoSeries(snapped_points, crs=metric_crs).to_crs("EPSG:4326")
        if mapillary_since is None:
            mapillary_since = date(date.today().year - 2, 1, 1)

        descriptions = result["description"] if "description" in result else [None] * len(result)
        popup_text = []
        street_view_urls = []
        mapillary_urls = []
        for description, point, reference in zip(descriptions, viewpoints, references):
            if point is None:
                street_view_urls.append(None)
                mapillary_urls.append(None)
                note = f"Bildstandort: {reference}" if main_entrances is not None else ""
                popup_text.append("\n".join(part for part in (description, note) if isinstance(part, str) and part.strip()))
                continue
            street_view_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={point.y:.7f}%2C{point.x:.7f}"
            mapillary_url = f"https://www.mapillary.com/app/?lat={point.y:.7f}&lng={point.x:.7f}&z=17&dateFrom={mapillary_since.isoformat()}"
            street_view_urls.append(street_view_url)
            mapillary_urls.append(mapillary_url)
            links = f"[[{street_view_url}|Google Street View]]\n[[{mapillary_url}|Mapillary]]"
            if main_entrances is not None:
                links = f"Bildstandort: {reference}\n{links}"
            if isinstance(description, str) and description.strip():
                links = f"{description.strip()}\n{links}"
            popup_text.append(links)
        result["description"] = popup_text
        result["google_street_view_url"] = street_view_urls
        result["mapillary_url"] = mapillary_urls
        if main_entrances is not None:
            result["imagery_reference"] = references
            result["main_entrance_osm_ids"] = entrance_ids_by_feature
        return result
