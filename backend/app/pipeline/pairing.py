from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from shapely.geometry.base import BaseGeometry

MAX_SCENES_PER_COMPOSITE = 6


@dataclass(frozen=True, order=True)
class GeometryKey:
    orbit_pass: str
    relative_orbit: int
    mode: str
    polarizations: tuple[str, ...]


@dataclass(frozen=True)
class Scene:
    id: str
    acquired_at: datetime
    platform: str
    geometry: GeometryKey
    footprint: BaseGeometry


Scenes = tuple[Scene, ...]
Coverage = Callable[[Scenes, Scenes], float]


@dataclass(frozen=True)
class Pair:
    pre: Scenes
    post: Scenes
    coverage: float

    @property
    def platforms(self) -> tuple[str, ...]:
        return tuple(sorted({scene.platform for scene in (*self.pre, *self.post)}))


@dataclass(frozen=True)
class Rejection:
    geometry: GeometryKey
    reason: Literal["missing_before", "missing_after", "no_shared_coverage", "lower_rank"]
    platform: str | None = None
    footprint_coverage: float | None = None


@dataclass(frozen=True)
class Selection:
    pair: Pair | None
    rejections: tuple[Rejection, ...]


def group_scenes(scenes: Iterable[Scene]) -> dict[GeometryKey, list[Scene]]:
    groups: dict[GeometryKey, list[Scene]] = defaultdict(list)
    unique = {scene.id: scene for scene in scenes}
    for scene in sorted(unique.values(), key=lambda item: (item.acquired_at, item.id)):
        groups[scene.geometry].append(scene)
    return groups


def select_pair(before: Iterable[Scene], after: Iterable[Scene], coverage: Coverage) -> Selection:
    pre_groups, post_groups = group_scenes(before), group_scenes(after)
    rejections: list[Rejection] = []
    candidates: list[tuple[GeometryKey, str | None, Pair]] = []

    for key in sorted(pre_groups.keys() | post_groups.keys()):
        if key not in pre_groups:
            rejections.append(Rejection(key, "missing_before"))
            continue
        if key not in post_groups:
            rejections.append(Rejection(key, "missing_after"))
            continue

        pre, post = pre_groups[key], post_groups[key]
        common_platforms = sorted({scene.platform for scene in pre} & {scene.platform for scene in post})
        # Compare the closest scenes to the event for each group. A platform subset may preserve the same coverage.
        for platform in (*common_platforms, None) if len({scene.platform for scene in (*pre, *post)}) > 1 else (None,):
            selected_pre = tuple(scene for scene in pre if platform is None or scene.platform == platform)[-MAX_SCENES_PER_COMPOSITE:]
            selected_post = tuple(scene for scene in post if platform is None or scene.platform == platform)[:MAX_SCENES_PER_COMPOSITE]
            shared = coverage(selected_pre, selected_post)
            if shared > 0:
                candidates.append((key, platform, Pair(selected_pre, selected_post, shared)))
            else:
                rejections.append(Rejection(key, "no_shared_coverage", platform, 0))

    if not candidates:
        return Selection(None, tuple(rejections))

    def rank(candidate: tuple[GeometryKey, str | None, Pair]) -> tuple[float, bool, int, int]:
        pair = candidate[2]
        return round(pair.coverage, 6), len(pair.platforms) == 1, min(len(pair.pre), len(pair.post)), len(pair.pre) + len(pair.post)

    winner = max(range(len(candidates)), key=lambda index: rank(candidates[index]))
    for index, (key, platform, pair) in enumerate(candidates):
        if index != winner:
            rejections.append(Rejection(key, "lower_rank", platform, pair.coverage))
    return Selection(candidates[winner][2], tuple(rejections))
