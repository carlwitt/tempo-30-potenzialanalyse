# Define your configuration dictionary
from DataRetrieval.BuildingRetrieval import BuildingRetrieval

class SpecificBuildingRetrieval:
    def retrieve_building_data(bbox, building_configs, validate_osm_sources=True,
                               broaden_facilities=True):


        # Store results here
        building_data = {}

        # Loop through the configs
        for datatype, config in building_configs.items():
            retrieval = BuildingRetrieval(
                datatype=config.get("cache_datatype", datatype),
                tags=config["tags"],
                name_filter_regex=config.get("regex", None),
                senior_assisted_living_only=config.get("senior_assisted_living_only", False),
                validate_osm_sources=validate_osm_sources,
                broaden_facilities=broaden_facilities,
            )
            
            gdf = retrieval.fetch(bbox)

            if gdf is not None:
                building_data[datatype] = gdf

                print(f"\n=== {datatype} ===")
                print("Names:")
                print(gdf["name"].head())
                print(f"Total {datatype} found: {len(gdf)}")
            else:
                print(f"Found no data for {datatype}")
        
        return building_data
