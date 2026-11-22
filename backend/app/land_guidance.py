from typing import Literal

from pydantic import BaseModel

from .land import LandProfile, Narrative

Role = Literal["farmer", "buyer", "analyst", "planner"]
Purpose = Literal["crops", "site", "water", "change"]

ROLE_LABELS: dict[Role, str] = {
    "farmer": "Farmer", "buyer": "Land buyer", "analyst": "Land analyst", "planner": "Local planner",
}
PURPOSE_LABELS: dict[Purpose, str] = {
    "crops": "Assess vegetation and crop conditions", "site": "Screen a plot before a site visit",
    "water": "Explore water and drought exposure", "change": "Track land change over time",
}

ROLE_CHECKS: dict[Role, str] = {
    "farmer": "Compare the imagery with your crop calendar, field observations, and local moisture readings before changing irrigation.",
    "buyer": "Walk the plot to check drainage and access. Confirm the legal boundary and ownership independently using local records.",
    "analyst": "Compare equivalent seasons and document the observation dates, valid coverage, and the source of each indicator.",
    "planner": "Compare the results with local drainage records, historical flood maps, and field observations around the study boundary.",
}


class GuidanceRequest(BaseModel):
    role: Role
    purpose: Purpose
    use_ai: bool = False


class LandGuidance(BaseModel):
    evidence: str
    checks: list[str]
    narrative: Narrative | None = None
    ai_status: Literal["not_requested", "unavailable", "busy", "failed", "ready"] = "not_requested"


def build_guidance(profile: LandProfile, request: GuidanceRequest) -> LandGuidance:
    vegetation = [row for row in profile.observations if row.ndvi is not None]
    classified = [row for row in profile.observations if row.land_cover_pct]
    water = [row for row in profile.observations if row.mapped_water_pct is not None]
    match request.purpose:
        case "crops":
            evidence = "Clear optical imagery was insufficient to summarize greenness for this window."
            if vegetation:
                first, last = vegetation[0], vegetation[-1]
                evidence = f"Vegetation greenness (NDVI) was {last.ndvi:g} in {last.start:%b %Y}."
                if len(vegetation) > 1:
                    evidence += f" It was {first.ndvi:g} in {first.start:%b %Y}, the earliest usable month in this window."
            check = "Compare images for the same crop stage. Greenness changes can reflect planting or harvest timing as well as stress."
        case "site":
            evidence = "There were no confident land-cover classifications in this window."
            if classified:
                last = classified[-1]
                label = max(last.land_cover_pct, key=last.land_cover_pct.__getitem__)
                evidence = (f"In {last.start:%b %Y}, {last.land_cover_pct[label]:g}% of classified pixels were {label.lower()}. "
                            f"Classification covered {last.classified_pct:g}% of the study area.")
            check = "Inspect the satellite image for places to check on the ground, especially water, built areas, and changes near the boundary."
        case "water":
            evidence = "There was insufficient clear imagery for an optical water estimate in this window."
            if water:
                last = water[-1]
                evidence = f"Optical observations mapped water across {last.mapped_water_pct:g}% of clear pixels in {last.start:%b %Y}."
            check = "Use Sentinel-1 flood screening for an event, and the rainfall scenario to compare modeled storage under chosen assumptions."
        case "change":
            evidence = f"{len(vegetation)} of {len(profile.observations)} monthly periods had usable optical greenness measurements."
            check = "Use the timeline to compare the same season across dates. Inspect coverage and imagery before attributing a change to the land itself."
    return LandGuidance(evidence=evidence, checks=[check, ROLE_CHECKS[request.role]])
