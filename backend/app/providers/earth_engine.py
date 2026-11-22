from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

import numpy as np
from shapely.geometry import shape

from ..aoi import AoiPolygon
from ..pipeline.pairing import GeometryKey, Pair, Scene
from ..pipeline.raster import EARTH_ENGINE_CRS_WKT, Grid, Parameters, RasterStack
from .base import ProviderError

COLLECTION = "COPERNICUS/S1_GRD"
DEM = "COPERNICUS/DEM/GLO30_2024_1"
JRC = "JRC/GSW1_4/GlobalSurfaceWater"
MERIT = "MERIT/Hydro/v1_0_1"
MISSING = -9999.0
MAX_METADATA = 240
PROPERTIES = (
    "system:time_start", "platform_number", "orbitProperties_pass",
    "relativeOrbitNumber_start", "instrumentMode", "transmitterReceiverPolarisation",
)


class EarthEngineProvider:
    def __init__(self, project: str):
        self._project = project
        self._ee: Any = None
        self._lock = Lock()

    def _sdk(self):
        with self._lock:
            if self._ee is None:
                try:
                    import ee
                    from google.auth.exceptions import GoogleAuthError
                except ImportError as error:
                    raise ProviderError("Install the optional Earth Engine dependencies to enable live analysis.") from error
                try:
                    ee.Initialize(project=self._project)
                    ee.data.setDeadline(35_000)
                    ee.data.setMaxRetries(1)
                except (ee.EEException, GoogleAuthError, OSError) as error:
                    raise ProviderError("Earth Engine could not authenticate. Check the registered project and local credentials.") from error
                self._ee = ee
            return self._ee

    def _area(self, aoi: AoiPolygon):
        return self._sdk().Geometry.Polygon(aoi.model_dump(mode="json")["coordinates"], "EPSG:4326", False)

    def _collection(self, area):
        ee = self._sdk()
        return (ee.ImageCollection(COLLECTION).filterBounds(area)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.eq("resolution_meters", 10))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))

    def latest(self, area: AoiPolygon) -> date | None:
        ee = self._sdk()
        try:
            timestamp = self._collection(self._area(area)).aggregate_max("system:time_start").getInfo()
        except ee.EEException as error:
            raise ProviderError("Earth Engine could not look up the latest usable observation.") from error
        return datetime.fromtimestamp(timestamp / 1000, UTC).date() if timestamp is not None else None

    def scenes(self, area: AoiPolygon, start: date, end: date) -> list[Scene]:
        ee = self._sdk()
        region = self._area(area)
        collection = self._collection(region).filterDate(str(start), str(end)).sort("system:time_start")

        def metadata(item):
            image = ee.Image(item)
            footprint = image.geometry().intersection(region, ee.ErrorMargin(5))
            # Earth Engine promotes a feature's system:index out of its properties.
            return ee.Feature(footprint, image.toDictionary(list(PROPERTIES))).set("scene_index", image.get("system:index"))

        try:
            features = ee.FeatureCollection(collection.toList(MAX_METADATA + 1).map(metadata)).getInfo()["features"]
        except ee.EEException as error:
            raise ProviderError("Earth Engine could not fetch scene metadata. Try again or choose a shorter window.") from error
        if len(features) > MAX_METADATA:
            raise ProviderError("The window returned too many scenes. Choose a shorter window.")
        scenes = []
        for feature in features:
            data = feature["properties"]
            scene_index = data.get("scene_index")
            if not scene_index or not feature["geometry"] or any(data.get(key) is None for key in PROPERTIES):
                continue
            footprint = shape(feature["geometry"])
            if not footprint.is_valid:
                footprint = footprint.buffer(0)
            if footprint.is_empty or footprint.area == 0:
                continue
            geometry = GeometryKey(data["orbitProperties_pass"], int(data["relativeOrbitNumber_start"]),
                                   data["instrumentMode"], tuple(sorted(data["transmitterReceiverPolarisation"])))
            scenes.append(Scene(f"{COLLECTION}/{scene_index}",
                                datetime.fromtimestamp(data["system:time_start"] / 1000, UTC),
                                f'S1{data["platform_number"]}', geometry, footprint))
        return scenes

    def pixels(self, area: AoiPolygon, pair: Pair, grid: Grid, params: Parameters) -> RasterStack:
        ee = self._sdk()
        region = self._area(area)
        projection = ee.Projection(EARTH_ENGINE_CRS_WKT).atScale(grid.scale_m)

        def composite(scenes, band):
            vv = (ee.ImageCollection.fromImages([ee.Image(scene.id).select("VV") for scene in scenes])
                  .median().setDefaultProjection(projection))
            return vv.focalMedian(radius=params.speckle_radius_m, units="meters").updateMask(vv.mask()).rename(band)

        terrain = ee.ImageCollection(DEM).filterBounds(region.buffer(150)).select("DEM")
        terrain_projection = ee.Image(terrain.first()).projection()
        slope = ee.Terrain.slope(terrain.mosaic().setDefaultProjection(terrain_projection)).rename("slope")
        layers = [composite(pair.pre, "pre"), composite(pair.post, "post"),
                  ee.Image.constant(1).clip(region).rename("aoi"), ee.Image.pixelArea().rename("pixel_area"),
                  ee.Image(JRC).select("occurrence").unmask(0).rename("occurrence"),
                  slope, ee.Image(MERIT).select("hnd").rename("hand")]
        image = ee.Image.cat(layers).toFloat().unmask(MISSING, sameFootprint=False)
        try:
            pixels = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": grid.ee_grid()})
        except ee.EEException as error:
            raise ProviderError("Earth Engine could not compute the raster. Check quota and try a smaller study area.") from error

        def band(name: str):
            return np.where(pixels[name] == MISSING, np.nan, pixels[name])

        return RasterStack(grid, band("pre"), band("post"), pixels["aoi"] == 1, band("pixel_area"),
                           band("occurrence"), band("slope"), band("hand"))
