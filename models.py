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

    class Config:
        extra = "forbid"

class SemesterWindow(BaseModel):
    semester_start: str = Field(..., description="YYYY-MM-DD")
    semester_end: str = Field(..., description="YYYY-MM-DD")
    timezone: str = "Europe/Brussels"

    class Config:
        extra = "forbid"

# --- Planning / sync ---
class CreateRecurringOp(BaseModel):
    op: Literal["create_recurring"] = "create_recurring"
    event: ScheduleEvent
    first_start_iso: str = Field(..., description="ISO start datetime for the first occurrence")
    first_end_iso: str = Field(..., description="ISO end datetime for the first occurrence")
    rrule: str = Field(..., description="RRULE:FREQ=WEEKLY;UNTIL=...")

    class Config:
        extra = "forbid"

class UpdateEventOp(BaseModel):
    op: Literal["update"] = "update"
    google_event_id: str
    patch: dict

    class Config:
        extra = "forbid"

class DeleteEventOp(BaseModel):
    op: Literal["delete"] = "delete"
    google_event_id: str

    class Config:
        extra = "forbid"

MutationOp = Union[CreateRecurringOp, UpdateEventOp, DeleteEventOp]

class MutationPlan(BaseModel):
    operations: List[MutationOp]
    preview: str
    requires_confirmation: bool = True

    class Config:
        extra = "forbid"


# --- Execution ---
class ExecutionResult(BaseModel):
    op_index: int
    op_type: str
    status: Literal["success", "failed", "skipped"]
    message: str
    google_event_id: Optional[str] = None


class ExecutionReport(BaseModel):
    plan_preview: str
    total_ops: int
    executed_ops: int
    failed_ops: int
    results: List[ExecutionResult]

# --- Conflicts ---
class Conflict(BaseModel):
    type: Literal["overlap", "duplicate", "outside_semester", "ambiguous"]
    summary: str
    affected: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"

class ConflictReport(BaseModel):
    conflicts: List[Conflict]
    blocking: bool = True

    class Config:
        extra = "forbid"

# --- Negotiation / resolution ---
class AlternativeSlot(BaseModel):
    start_iso: str
    end_iso: str
    score: float | None = None

    class Config:
        extra = "forbid"


class ResolutionOption(BaseModel):
    operation_index: int
    suggested_start_iso: str
    suggested_end_iso: str
    note: str | None = None

    class Config:
        extra = "forbid"


class NegotiationOutcome(BaseModel):
    updated_plan: MutationPlan
    applied_resolutions: List[ResolutionOption] = Field(default_factory=list)
    unresolved_conflicts: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"
