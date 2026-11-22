"""Rebuild the measured portions of the two land demo bundles from Earth Engine."""

import os
from datetime import date
from pathlib import Path

from PIL import Image

from backend.app.aoi import AoiPolygon
from backend.app.land import LandRequest
from backend.app.providers.land_optical import build_profile

DEMOS = (
    ("punjab-farmland", "Farmland near Ludhiana, Punjab", "farmland", (75.765, 30.947, 75.784, 30.965), "Crops"),
    ("thar-dryland", "Dry land west of Jaisalmer, Rajasthan", "dryland", (70.299, 26.95, 70.323, 26.969), "Bare ground"),
)
DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "land_demos"


def main() -> None:
    project = os.getenv("EE_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("Set EE_PROJECT_ID and authenticate Earth Engine first.")
    for slug, title, terrain, (west, south, east, north), expected in DEMOS:
        area = AoiPolygon(type="Polygon", coordinates=[[(west, south), (east, south), (east, north), (west, north), (west, south)]])
        bundle = build_profile(project, LandRequest(aoi=area, end=date(2025, 3, 31), months=6), 100)
        profile = bundle.profile.model_copy(update={"id": slug, "title": title, "terrain": terrain})
        baseline = next((snapshot for snapshot in profile.observations if snapshot.start == profile.scenario_period), None)
        if bundle.cover is None or baseline is None or baseline.land_cover_pct.get(expected, 0) <= 50:
            raise SystemExit(f"No suitable {expected.lower()} baseline for {title}.")
        if sum(snapshot.ndvi is not None for snapshot in profile.observations) < 3:
            raise SystemExit(f"Insufficient clear observations for {title}.")
        directory = DIRECTORY / slug
        directory.mkdir(parents=True, exist_ok=True)
        Image.fromarray(bundle.cover).save(directory / "cover.png", optimize=True)
        # A fresh observation run invalidates any previously reviewed narrative.
        (directory / "profile.json").write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(title, "baseline", baseline.start, expected, baseline.land_cover_pct[expected], flush=True)


if __name__ == "__main__":
    main()
