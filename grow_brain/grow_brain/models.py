"""Pydantic models for the HTTP API (mirrors docs/API.md) and for Claude structured outputs."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------- Grow profile ----------

Stage = Literal["seedling", "veg", "flower", "flush", "drying", "curing", "done"]
Medium = Literal["soil", "coco", "hydro", "other"]


class GrowProfile(BaseModel):
    strain: str = "Liberty Haze"
    breeder: str = "Barney's Farm"
    seed_type: str = "feminized photoperiod"
    medium: Medium = "soil"
    pot_size_l: float = 11.0
    plant_count: int = 1
    start_date: Optional[str] = None  # YYYY-MM-DD
    stage: Stage = "seedling"
    stage_started: Optional[str] = None
    flower_start_date: Optional[str] = None
    expected_flower_days: int = 65
    exhaust_ducted: bool = False
    notes: str = ""


class GrowProfileUpdate(BaseModel):
    strain: Optional[str] = None
    breeder: Optional[str] = None
    seed_type: Optional[str] = None
    medium: Optional[Medium] = None
    pot_size_l: Optional[float] = None
    plant_count: Optional[int] = None
    start_date: Optional[str] = None
    stage_started: Optional[str] = None
    flower_start_date: Optional[str] = None
    expected_flower_days: Optional[int] = None
    exhaust_ducted: Optional[bool] = None
    notes: Optional[str] = None


class StageChange(BaseModel):
    stage: Stage


# ---------- Targets / settings ----------

class TargetsUpdate(BaseModel):
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    humidity_min: Optional[float] = None
    humidity_max: Optional[float] = None
    vpd_min: Optional[float] = None
    vpd_max: Optional[float] = None
    light_on_time: Optional[str] = None
    light_hours: Optional[float] = None


class SettingsModel(BaseModel):
    units: Literal["c", "f"] = "c"
    brief_time: str = "08:00"
    timezone: str = "UTC"
    auto_apply_advisor_targets: bool = True
    notify_service: Optional[str] = None
    notify_services_available: list[str] = Field(default_factory=list)
    model: str = "claude-opus-5"
    advisor_enabled: bool = False
    safety_temp_max_c: float = 35.0
    safety_temp_min_c: float = 12.0
    control_interval_s: int = 30
    min_switch_interval_s: int = 180


class SettingsUpdate(BaseModel):
    units: Optional[Literal["c", "f"]] = None
    brief_time: Optional[str] = None
    timezone: Optional[str] = None
    auto_apply_advisor_targets: Optional[bool] = None
    notify_service: Optional[str] = None
    model: Optional[str] = None
    safety_temp_max_c: Optional[float] = None
    safety_temp_min_c: Optional[float] = None
    control_interval_s: Optional[int] = None
    min_switch_interval_s: Optional[int] = None


# ---------- Devices ----------

class DeviceMapUpdate(BaseModel):
    entity_id: Optional[str] = None


class OverrideRequest(BaseModel):
    mode: Literal["auto", "on", "off"]
    minutes: Optional[int] = None


class PauseRequest(BaseModel):
    minutes: int = 30


# ---------- Log / tasks / photos / chat ----------

LogKind = Literal["ph", "ec", "ppm", "water", "feed", "height", "note", "observation",
                  "defoliation", "training", "transplant", "other"]


class LogCreate(BaseModel):
    kind: LogKind
    value: Optional[float] = None
    unit: Optional[str] = None
    context: Optional[str] = None
    note: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    detail: Optional[str] = None
    due: Optional[str] = None
    priority: Literal["normal", "high"] = "normal"


class ChatRequest(BaseModel):
    message: str


# ---------- Claude structured outputs ----------
# Keep these small and strict; the advisor fills them in.

class TaskDraft(BaseModel):
    title: str = Field(description="Short imperative to-do for the grower, e.g. 'Water 1 L at pH 6.3'")
    detail: str = Field(default="", description="One or two sentences of how/why")
    due: Optional[str] = Field(default=None, description="YYYY-MM-DD or null")
    priority: Literal["normal", "high"] = "normal"


class PhotoRequestDraft(BaseModel):
    title: str = Field(description="What to photograph, e.g. 'Underside of a lower fan leaf'")
    instructions: str = Field(description="Exactly where to stand, what to include, lighting (grow light off + phone flash for true colours), distance, focus")
    reason: str = Field(description="Why this photo helps right now")


class TargetChange(BaseModel):
    field: Literal["temp_min_c", "temp_max_c", "humidity_min", "humidity_max", "vpd_min", "vpd_max"]
    to: float
    reason: str


class BriefOut(BaseModel):
    headline: str = Field(description="One line, e.g. 'Day 26 – healthy, humidity creeping up'")
    summary: str = Field(description="3–6 plain-language sentences for a beginner")
    concerns: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list, description="What the human should do today, in order")
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)


class LogAdviceOut(BaseModel):
    summary: str
    steps: list[str] = Field(description="Concrete next steps, most important first")
    urgency: Literal["info", "attention", "urgent"] = "info"
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)


class Finding(BaseModel):
    title: str
    severity: Literal["info", "warn", "alert"]
    detail: str


class PhotoAnalysisOut(BaseModel):
    summary: str
    health_score: int = Field(ge=0, le=10)
    findings: list[Finding] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)


class ChatOut(BaseModel):
    reply: str = Field(description="The conversational answer, markdown-light plain text")
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)
