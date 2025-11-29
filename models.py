from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Union
from enum import Enum

class DayOfWeek(str, Enum):
    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"

class ScheduleEvent(BaseModel):
    title: str
    day_of_week: DayOfWeek
    start_time: str = Field(..., description="HH:MM local time")
    end_time: str = Field(..., description="HH:MM local time")
    location: Optional[str] = None
    recurrence: Literal["weekly", "once", "unknown"] = "weekly"
    notes: Optional[str] = None

    # traceability/debug
    source: Literal["pdf", "image", "manual"] = "manual"
    source_hint: Optional[str] = None

class SemesterWindow(BaseModel):
    semester_start: str = Field(..., description="YYYY-MM-DD")
    semester_end: str = Field(..., description="YYYY-MM-DD")
    timezone: str = "Europe/Brussels"

# --- Planning / sync ---
class CreateRecurringOp(BaseModel):
    op: Literal["create_recurring"] = "create_recurring"
    event: ScheduleEvent
    rrule: str = Field(..., description="RRULE:FREQ=WEEKLY;UNTIL=...")

class UpdateEventOp(BaseModel):
    op: Literal["update"] = "update"
    google_event_id: str
    patch: dict

class DeleteEventOp(BaseModel):
    op: Literal["delete"] = "delete"
    google_event_id: str

MutationOp = Union[CreateRecurringOp, UpdateEventOp, DeleteEventOp]

class MutationPlan(BaseModel):
    operations: List[MutationOp]
    preview: str
    requires_confirmation: bool = True

# --- Conflicts ---
class Conflict(BaseModel):
    type: Literal["overlap", "duplicate", "outside_semester", "ambiguous"]
    summary: str
    affected: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

class ConflictReport(BaseModel):
    conflicts: List[Conflict]
    blocking: bool = True
