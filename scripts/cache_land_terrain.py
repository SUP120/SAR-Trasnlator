"""Fetch the elevation surfaces for the existing offline land studies."""

from os import getenv

from backend.app.api.land import DEMO_DIRECTORY, read_demos
from backend.app.providers.terrain import build_terrain


def main() -> None:
    project = getenv("EE_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("Set EE_PROJECT_ID and authenticate Earth Engine first.")
    for key, bundle in read_demos(DEMO_DIRECTORY).items():
        grid = build_terrain(project, bundle.profile.aoi)
        path = DEMO_DIRECTORY / key / "terrain.json"
        pending = path.with_suffix(".tmp")
        pending.write_text(grid.model_dump_json() + "\n", encoding="utf-8")
        pending.replace(path)
        values = [sample for row in grid.elevations_m for sample in row if sample is not None]
        print(key, len(values), grid.cell_m, min(values), max(values), flush=True)


if __name__ == "__main__":
    main()
