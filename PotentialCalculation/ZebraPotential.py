"""Find eligible faster roads near confirmed zebra crossings.

A zebra marker beside a 50 km/h road can support a local proposal, while
an unrelated distant crossing cannot. Measure in a metric CRS and retain
each crossing-to-road pair for map display and source verification.
"""

import geopandas as gpd

from PotentialCalculation.FacilityStreetRelevance import FacilityStreetRelevance
from PotentialCalculation.PotentialCalculationResult import PotentialCalculationResult


class ZebraPotential:
    @staticmethod
    def find_tempo50_segments_near_zebra(
        streets_gdf: gpd.GeoDataFrame,
        zebras_gdf: gpd.GeoDataFrame,
        search_distance_m: float = 15.0,
        metric_crs: str = "EPSG:25832"
    ) -> PotentialCalculationResult:
        """
        Ermittelt OSM_IDs von Tempo-50/60-Straßenabschnitten,
        die sich ≤ search_distance_m zu einem Zebrastreifen befinden.
        Gibt zusätzlich alle beteiligten Zebrastreifen-IDs zurück.
        """

        if streets_gdf is None or streets_gdf.empty:
            return PotentialCalculationResult([], [])

        if zebras_gdf is None or zebras_gdf.empty:
            return PotentialCalculationResult([], [])

        tempo50_or_60 = FacilityStreetRelevance.potential_streets(streets_gdf)

        if tempo50_or_60.empty:
            return PotentialCalculationResult([], [])

        # -----------------------------
        # In metrisches CRS projizieren
        # -----------------------------
        if tempo50_or_60.crs != metric_crs:
            tempo50_or_60 = tempo50_or_60.to_crs(metric_crs)

        zebras = zebras_gdf.copy()
        if zebras.crs != metric_crs:
            zebras = zebras.to_crs(metric_crs)

        # -----------------------------
        # Zebrastreifen puffern
        # -----------------------------
        zebras_buffered = zebras.copy()
        zebras_buffered["geometry"] = zebras_buffered.geometry.buffer(search_distance_m)

        zebras_buffered = zebras_buffered[["osm_id", "geometry"]].rename(
            columns={"osm_id": "zebra_id"}
        )

        # -----------------------------
        # Spatial Join
        # -----------------------------
        joined = gpd.sjoin(
            tempo50_or_60,
            zebras_buffered,
            how="inner",
            predicate="intersects"
        )

        if joined.empty:
            return PotentialCalculationResult([], [])

        # -----------------------------
        # Ergebnis
        # -----------------------------
        street_ids = joined["osm_id"].drop_duplicates().tolist()
        zebra_ids = joined["zebra_id"].drop_duplicates().tolist()
        source_street_pairs = list(
            joined[["zebra_id", "osm_id"]].drop_duplicates().itertuples(index=False, name=None)
        )

        return PotentialCalculationResult(
            street_ids=street_ids,
            opt_source_ids=zebra_ids,
            source_street_pairs=source_street_pairs,
        )
