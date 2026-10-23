"""Create uMap popup links to street-level imagery near mapped locations."""

from datetime import date

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.strtree import STRtree


class StreetImageryLinkCreator:
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
            if main_entrances is not None:
                result["imagery_reference"] = []
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
            raise ValueError("Street imagery links require at least one T50 street segment")

        tree = STRtree(segments)
        entrance_by_id = {}
        metric_entrances = None
        if main_entrances is not None and not main_entrances.empty:
            metric_entrances = main_entrances.to_crs(metric_crs)
            entrance_by_id = dict(zip(metric_entrances["osm_id"], metric_entrances.geometry))

        snapped_points = []
        references = []
        for _, feature in metric_features.iterrows():
            node_ids = feature.get("osm_node_ids", [])
            entrances = [entrance_by_id[node_id] for node_id in node_ids if node_id in entrance_by_id]
            reference = "OSM-Haupteingang auf Objektgrenze"
            if not entrances and use_area_entrances and metric_entrances is not None \
                    and isinstance(feature.geometry, (Polygon, MultiPolygon)):
                matches = metric_entrances.sindex.query(feature.geometry, predicate="intersects")
                entrances = metric_entrances.geometry.iloc[matches].tolist()
                reference = "OSM-Haupteingang im Areal; Zuordnung angenähert"
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
            snapped_points.append(segment.interpolate(segment.project(location)))

        # Both providers use WGS84 latitude/longitude, regardless of input CRS.
        viewpoints = gpd.GeoSeries(snapped_points, crs=metric_crs).to_crs("EPSG:4326")
        if mapillary_since is None:
            mapillary_since = date(date.today().year - 2, 1, 1)

        descriptions = result["description"] if "description" in result else [None] * len(result)
        popup_text = []
        for description, point, reference in zip(descriptions, viewpoints, references):
            street_view_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={point.y:.7f}%2C{point.x:.7f}"
            mapillary_url = f"https://www.mapillary.com/app/?lat={point.y:.7f}&lng={point.x:.7f}&z=17&dateFrom={mapillary_since.isoformat()}"
            links = f"[[{street_view_url}|Google Street View]]\n[[{mapillary_url}|Mapillary]]"
            if main_entrances is not None:
                links = f"Bildstandort: {reference}\n{links}"
            if isinstance(description, str) and description.strip():
                links = f"{description.strip()}\n{links}"
            popup_text.append(links)
        result["description"] = popup_text
        if main_entrances is not None:
            result["imagery_reference"] = references
        return result
