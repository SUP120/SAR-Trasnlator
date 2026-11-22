"""Package derived land evidence for the two offline demos."""

from datetime import date
from os import getenv

from backend.app.api.land import DEMO_DIRECTORY, read_demos
from backend.app.providers.land_evidence import build_history, build_inspection, build_plot_evidence, load_rain


def main() -> None:
    project = getenv("EE_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("Set EE_PROJECT_ID and authenticate Earth Engine first.")
    failures = []
    for identifier, bundle in read_demos(DEMO_DIRECTORY).items():
        profile = bundle.profile
        for name, fetch in (
            ("monsoon-2024", lambda: load_rain(project, profile.aoi, date(2024, 7, 1), 42)),
            ("plot", lambda: build_plot_evidence(project, profile.aoi)),
            ("history", lambda: build_history(project, profile)),
            ("inspection", lambda: build_inspection(project, profile)),
        ):
            try:
                evidence = fetch()
                path = DEMO_DIRECTORY / identifier / f"{name}.json"
                pending = path.with_suffix(".tmp")
                pending.write_text(evidence.model_dump_json() + "\n", encoding="utf-8")
                pending.replace(path)
                print(identifier, name, path.stat().st_size, flush=True)
            except Exception as error:
                print(identifier, name, type(error).__name__, str(error), flush=True)
                failures.append(f"{identifier}/{name}")
    if failures:
        raise SystemExit("Failed to cache: " + ", ".join(failures))


if __name__ == "__main__":
    main()
