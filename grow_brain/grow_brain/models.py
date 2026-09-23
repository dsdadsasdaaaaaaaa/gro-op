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


class PlantCreate(BaseModel):
    name: str
    owner: str = ""
    strain: str = "Liberty Haze"
    breeder: str = "Barney's Farm"
    seed_type: str = "feminized photoperiod"
    medium: Medium = "soil"
    pot_size_l: float = 11.0
    start_date: Optional[str] = None
    notes: str = ""
    notify_service: Optional[str] = None


class PlantUpdate(BaseModel):
    name: Optional[str] = None
    owner: Optional[str] = None
    strain: Optional[str] = None
    breeder: Optional[str] = None
    seed_type: Optional[str] = None
    medium: Optional[Medium] = None
    pot_size_l: Optional[float] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None
    notify_service: Optional[str] = None


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
    camera_entity: Optional[str] = None
    camera_capture_minutes: int = 30
    temp_offset_c: float = 0.0
    humidity_offset: float = 0.0
    price_per_kwh: Optional[float] = None
    currency: str = "CAD"
    advisor_month_usd: float = 0.0


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
    humidifier_tank_hours: Optional[float] = None  # hours of misting one tank lasts
    camera_entity: Optional[str] = None
    camera_capture_minutes: Optional[int] = None
    temp_offset_c: Optional[float] = None
    humidity_offset: Optional[float] = None
    price_per_kwh: Optional[float] = None
    currency: Optional[str] = None


class CameraSelect(BaseModel):
    entity_id: Optional[str] = None  # null/"" = off


class CameraAnalyse(BaseModel):
    plant_id: Optional[int] = None
    note: Optional[str] = None


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
    plant_id: Optional[int] = None
    kind: LogKind
    value: Optional[float] = None
    unit: Optional[str] = None
    context: Optional[str] = None
    note: Optional[str] = None


class TaskCreate(BaseModel):
    plant_id: Optional[int] = None
    title: str
    detail: Optional[str] = None
    due: Optional[str] = None
    priority: Literal["normal", "high"] = "normal"


class ChatRequest(BaseModel):
    message: str
    plant_id: Optional[int] = None


# ---------- Claude structured outputs ----------
# Keep these small and strict; the advisor fills them in.

class TaskDraft(BaseModel):
    plant_id: Optional[int] = Field(default=None, description="Id of the plant this is for, or null if it's about the whole tent")
    title: str = Field(description="Short imperative to-do for the grower, e.g. 'Water 1 L at pH 6.3'")
    detail: str = Field(default="", description="One or two sentences of how/why")
    due: Optional[str] = Field(default=None, description="YYYY-MM-DD or null")
    priority: Literal["normal", "high"] = "normal"


class PhotoRequestDraft(BaseModel):
    plant_id: Optional[int] = Field(default=None, description="Id of the plant to photograph (required unless it's the whole tent)")
    title: str = Field(description="What to photograph, e.g. 'Underside of a lower fan leaf'")
    instructions: str = Field(description="Exactly where to stand, what to include, lighting (grow light off + phone flash for true colours), distance, focus")
    reason: str = Field(description="Why this photo helps right now")


class TargetChange(BaseModel):
    field: Literal["temp_min_c", "temp_max_c", "humidity_min", "humidity_max", "vpd_min", "vpd_max"]
    to: float
    reason: str


class PlantBrief(BaseModel):
    plant_id: int
    headline: str = Field(description="One line for this plant")
    summary: str = Field(description="2–4 sentences for this plant's owner")


class BriefOut(BaseModel):
    per_plant: list[PlantBrief] = Field(default_factory=list, description="One entry per active plant")
    tasks_done: list[int] = Field(default_factory=list, description="Ids of OPEN tasks that are now finished or obsolete (the grower did them, or the plan changed). Close them here instead of asking the grower to.")
    headline: str = Field(description="One line, e.g. 'Day 26 – healthy, humidity creeping up'")
    summary: str = Field(description="3–6 plain-language sentences for a beginner")
    concerns: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list, description="What the human should do today, in order")
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)


class LogAdviceOut(BaseModel):
    tasks_done: list[int] = Field(default_factory=list, description="Ids of OPEN tasks that are now finished or obsolete (the grower did them, or the plan changed). Close them here instead of asking the grower to.")
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
    tasks_done: list[int] = Field(default_factory=list, description="Ids of OPEN tasks that are now finished or obsolete (the grower did them, or the plan changed). Close them here instead of asking the grower to.")
    summary: str
    health_score: int = Field(ge=0, le=10)
    findings: list[Finding] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)


class ChatOut(BaseModel):
    tasks_done: list[int] = Field(default_factory=list, description="Ids of OPEN tasks that are now finished or obsolete (the grower did them, or the plan changed). Close them here instead of asking the grower to.")
    reply: str = Field(description="The conversational answer, markdown-light plain text")
    target_changes: list[TargetChange] = Field(default_factory=list)
    photo_requests: list[PhotoRequestDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)
