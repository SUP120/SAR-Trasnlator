from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from shapely.geometry import box

from backend.app.pipeline.pairing import GeometryKey, Scene, select_pair
from backend.app.pipeline.quality import rate_quality
from backend.app.pipeline.raster import Grid, Parameters, RasterStack, detect, footprint_coverage
from backend.app.pipeline.windows import DateRange, EventDate, Preset, resolve_window

GEOMETRY = GeometryKey("ASCENDING", 12, "IW", ("VH", "VV"))
AOI = box(91, 26, 91.05, 26.05)


def scene(identifier, day, *, platform="S1A", geometry=GEOMETRY, footprint=AOI):
    return Scene(identifier, datetime(2020, 6, day, tzinfo=UTC), platform, geometry, footprint)


def coverage(pre, post):
    return footprint_coverage(AOI, pre, post)


@pytest.mark.parametrize("mismatch", [
    {"orbit_pass": "DESCENDING"}, {"relative_orbit": 13}, {"mode": "EW"}, {"polarizations": ("VV",)},
])
def test_pairing_rejects_each_incompatible_acquisition_property(mismatch):
    decision = select_pair([scene("pre", 1)], [scene("post", 8, geometry=replace(GEOMETRY, **mismatch))], coverage)
    assert decision.pair is None
    assert {rejection.reason for rejection in decision.rejections} == {"missing_before", "missing_after"}


def test_pairing_prioritizes_intersection_of_footprints_before_platform_preference():
    partial = box(91, 26, 91.025, 26.05)
    before = [scene("partial-before", 1, footprint=partial), scene("full-before", 3, platform="S1B")]
    after = [scene("full-after", 8)]
    decision = select_pair(before, after, coverage)
    assert decision.pair is not None
    assert decision.pair.coverage == pytest.approx(1)
    assert decision.pair.platforms == ("S1A", "S1B")
    assert decision.rejections[0].footprint_coverage == pytest.approx(.5, rel=.001)


def test_same_platform_wins_tie_and_uncovered_pairs_are_rejected():
    before = [scene("a", 1), scene("b", 3, platform="S1B")]
    after = [scene("c", 8)]
    decision = select_pair(reversed(before), after, coverage)
    assert decision.pair is not None
    assert [item.id for item in decision.pair.pre] == ["a"]
    bad = select_pair(before, [scene("outside", 8, footprint=box(92, 26, 93, 27))], coverage)
    assert bad.pair is None
    assert all(rejection.reason == "no_shared_coverage" for rejection in bad.rejections)


def test_windows_cover_requested_days_and_use_exclusive_end():
    date_used = date(2022, 6, 25)
    window = resolve_window(Preset(kind="preset", days=7), date_used)
    assert window.end_exclusive == date_used + timedelta(days=1)
    assert (window.end_exclusive - window.start).days == 7
    custom = resolve_window(EventDate(kind="event", date=date_used))
    assert (custom.event - custom.start).days == 30
    assert (custom.end_exclusive - custom.event).days == 12
    with pytest.raises(ValueError):
        DateRange(kind="range", start=date_used, event=date_used, end=date_used)


def test_detection_uses_measured_pixel_area_and_reports_each_exclusion():
    pre = np.full((8, 8), -11.0)
    post = pre.copy()
    post[0:3, 0:3] = -22
    post[7, 7] = -23  # Remove an isolated candidate pixel.
    post[5, 5] = -21
    post[5, 0] = -21
    occurrence = np.zeros_like(pre)
    occurrence[5, 0] = 90
    slope = np.zeros_like(pre)
    slope[5, 5] = 7
    pre[4, 4] = np.nan
    pixel_area = np.full_like(pre, 100)
    pixel_area[0, 0] = 150
    stack = RasterStack(Grid(0, 0, 8, 8, 10), pre, post, np.ones_like(pre, dtype=bool), pixel_area, occurrence, slope, None)
    result = detect(stack, Parameters())
    assert result.flood.sum() == 9
    assert result.stats["flood_ha"] == pytest.approx(.095)
    assert result.stats["valid_coverage_pct"] < 100
    assert result.excluded_ha == pytest.approx({key: .01 for key in ("preexisting_water", "terrain", "small_clusters")})


def test_quality_uses_threshold_boundaries_and_never_implies_probability():
    pair = select_pair([scene("a", 15), scene("b", 18)], [scene("c", 21), scene("d", 24)], coverage).pair
    assert pair is not None
    event = date(2020, 6, 20)
    assert rate_quality(pair, event, 95, 9).overall == "High"
    assert rate_quality(pair, event, 80, 30).overall == "Medium"
    assert rate_quality(pair, event, 79.99, 31).overall == "Low"
