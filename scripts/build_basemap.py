"""Build the bundled South Asia reference map from downloaded Natural Earth files."""

import argparse
import io
import json
from math import atan, degrees, pi, radians, sinh, tan, log
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from shapely import set_precision
from shapely.geometry import box, mapping, shape

REGION = box(65, 7, 102, 36)
SOURCE = Path("data/local/natural-earth")
DESTINATION = Path("frontend/public")


def features(directory: Path, filename: str):
    return json.loads((directory / f"{filename}.geojson").read_text(encoding="utf-8"))["features"]


def linework(directory: Path, source: str, polygon_boundaries: bool = False):
    lines = []
    for feature in features(directory, source):
        geometry = shape(feature["geometry"])
        if not geometry.intersects(REGION):
            continue
        if polygon_boundaries:
            geometry = geometry.boundary
        clipped = geometry.intersection(REGION).simplify(0.002)
        if clipped.length > 0:
            lines.append({"type": "Feature", "properties": {}, "geometry": mapping(set_precision(clipped, 0.0001))})
    return {"type": "FeatureCollection", "features": lines}


def places(directory: Path):
    points = []
    for feature in features(directory, "ne_10m_populated_places"):
        point = shape(feature["geometry"])
        if not REGION.covers(point):
            continue
        info = feature["properties"]
        name = info.get("NAME_EN") or info["NAME"]
        points.append((info["SCALERANK"], -info["POP_MAX"], name, round(point.y, 5), round(point.x, 5)))
    return [{"name": name, "lat": lat, "lon": lon, "rank": rank} for rank, _, name, lat, lon in sorted(points)]


def mercator(latitude: float) -> float:
    return log(tan(pi / 4 + radians(latitude) / 2))


def shade_relief(directory: Path, destination: Path):
    west, south, east, north = REGION.bounds
    with ZipFile(directory / "GRAY_50M_SR_W.zip") as archive:
        with Image.open(io.BytesIO(archive.read("GRAY_50M_SR_W.tif"))) as source:
            pixels_per_degree = source.width / 360
            left = round((west + 180) * pixels_per_degree)
            top = round((90 - north) * pixels_per_degree)
            right = round((east + 180) * pixels_per_degree)
            bottom = round((90 - south) * pixels_per_degree)
            cropped = source.crop((left, top, right, bottom))

    north_y, south_y = mercator(north), mercator(south)
    height = round(degrees(north_y - south_y) * pixels_per_degree)
    projected = Image.new("L", (cropped.width, height))
    for row in range(height):
        latitude = degrees(atan(sinh(north_y - (row + 0.5) / height * (north_y - south_y))))
        original_y = (north - latitude) * pixels_per_degree
        stripe = cropped.transform(
            (cropped.width, 1), Image.Transform.AFFINE, (1, 0, 0, 0, 0, original_y), Image.Resampling.BILINEAR,
        )
        projected.paste(stripe, (0, row))

    # Recolor the grayscale terrain for contrast with the study boundary.
    channels = [projected.point([round(low + (high - low) * value / 255) for value in range(256)])
                for low, high in [(2, 51), (9, 72), (20, 88)]]
    Image.merge("RGB", channels).save(destination / "south-asia-relief.webp", quality=90, method=6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=DESTINATION)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    layers = {
        "countries": linework(args.source, "ne_50m_admin_0_countries", polygon_boundaries=True),
        "boundaries": linework(args.source, "ne_50m_admin_1_states_provinces_lines"),
        "rivers": linework(args.source, "ne_10m_rivers_lake_centerlines"),
        "places": places(args.source),
    }
    (args.output / "south-asia.json").write_text(json.dumps(layers, separators=(",", ":")) + "\n", encoding="utf-8")
    shade_relief(args.source, args.output)


if __name__ == "__main__":
    main()
