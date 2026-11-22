from datetime import date
from typing import Protocol

from ..aoi import AoiPolygon
from ..pipeline.pairing import Pair, Scene
from ..pipeline.raster import Grid, Parameters, RasterStack


class ProviderError(RuntimeError):
    pass


class SarProvider(Protocol):
    def latest(self, area: AoiPolygon) -> date | None: ...

    def scenes(self, area: AoiPolygon, start: date, end: date) -> list[Scene]: ...

    def pixels(self, area: AoiPolygon, pair: Pair, grid: Grid, params: Parameters) -> RasterStack: ...
