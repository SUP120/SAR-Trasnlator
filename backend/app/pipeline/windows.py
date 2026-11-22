from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

DAY = timedelta(days=1)
SupportedDate = Annotated[date, Field(ge=date(1900, 1, 31), le=date(9999, 12, 19))]


class Preset(BaseModel):
    kind: Literal["preset"]
    days: Literal[7, 30, 90]


class EventDate(BaseModel):
    kind: Literal["event"]
    date: SupportedDate


class DateRange(BaseModel):
    kind: Literal["range"]
    start: SupportedDate
    event: SupportedDate
    end: SupportedDate

    @model_validator(mode="after")
    def valid_range(self) -> "DateRange":
        if not self.start < self.event <= self.end:
            raise ValueError("A custom range needs at least one day before the event and must include the event.")
        if (self.end - self.start).days >= 365:
            raise ValueError("Choose a total window of at most 365 days.")
        return self


Window = Annotated[Preset | EventDate | DateRange, Field(discriminator="kind")]


@dataclass(frozen=True)
class Periods:
    start: date
    event: date
    end_exclusive: date


def resolve_window(window: Window, latest: date | None = None) -> Periods:
    if isinstance(window, EventDate):
        return Periods(window.date - 30 * DAY, window.date, window.date + 12 * DAY)
    if isinstance(window, DateRange):
        return Periods(window.start, window.event, window.end + DAY)
    if latest is None:
        raise ValueError("No latest observation is available for this area.")
    end = latest + DAY
    post_days = min(12, (window.days + 1) // 2)
    return Periods(end - window.days * DAY, end - post_days * DAY, end)
