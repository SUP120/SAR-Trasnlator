from datetime import date
from typing import Literal

from pydantic import BaseModel

from .pairing import Pair

Grade = Literal["Good", "Fair", "Poor"]


class Factor(BaseModel):
    name: str
    observed: str
    grade: Grade


class Quality(BaseModel):
    overall: Literal["High", "Medium", "Low"]
    factors: list[Factor]


def rate_quality(pair: Pair, event: date, coverage: float, terrain: float) -> Quality:
    before = min(abs((scene.acquired_at.date() - event).days) for scene in pair.pre)
    after = min(abs((scene.acquired_at.date() - event).days) for scene in pair.post)
    gap = max(before, after)
    scenes = min(len(pair.pre), len(pair.post))
    factors = [
        Factor(name="Orbit compatibility", observed=", ".join(pair.platforms),
               grade="Good" if len(pair.platforms) == 1 else "Fair"),
        Factor(name="Observation gap", observed=f"{before} days before / {after} days after",
               grade="Good" if gap <= 12 else "Fair" if gap <= 24 else "Poor"),
        Factor(name="Shared valid coverage", observed=f"{coverage:.1f}%",
               grade="Good" if coverage >= 95 else "Fair" if coverage >= 80 else "Poor"),
        Factor(name="Scenes per composite", observed=f"{len(pair.pre)} before / {len(pair.post)} after",
               grade="Good" if scenes >= 3 else "Fair" if scenes == 2 else "Poor"),
        Factor(name="Terrain exclusion", observed=f"{terrain:.1f}%",
               grade="Good" if terrain < 10 else "Fair" if terrain <= 30 else "Poor"),
    ]
    grades = [factor.grade for factor in factors]
    return Quality(overall="Low" if "Poor" in grades else "High" if grades.count("Fair") <= 1 else "Medium",
                   factors=factors)
