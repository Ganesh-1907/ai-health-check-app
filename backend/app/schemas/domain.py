from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    name: str
    age: int
    gender: str
    location: str = ""
    contact_number: str = ""
    latitude: float | None = None
    longitude: float | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    location: str | None = None
    contact_number: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class UserRead(UserCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssessmentCreate(BaseModel):
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    heart_rate: float | None = None
    blood_sugar: float | None = None
    cholesterol: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    symptoms: list[str] = Field(default_factory=list)
    symptom_details: dict[str, Any] = Field(default_factory=dict)
    medical_history: dict[str, Any] = Field(default_factory=dict)
    lifestyle: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class AssessmentRead(AssessmentCreate):
    id: int
    user_id: int
    bmi: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskPredictionRead(BaseModel):
    id: int
    assessment_id: int
    risk_score: float
    risk_level: str
    confidence: float
    explanation: list[str]
    red_flags: list[str]
    summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyLogCreate(BaseModel):
    log_date: date
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    blood_sugar: float | None = None
    weight_kg: float | None = None
    steps: int | None = None
    sleep_hours: float | None = None
    notes: str = ""


class DailyLogRead(DailyLogCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalReportRead(BaseModel):
    id: int
    user_id: int
    report_type: str
    file_name: str
    content_type: str
    extracted_text: str
    extracted_findings: dict[str, Any]
    extraction_confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecommendationRead(BaseModel):
    id: int
    user_id: int
    assessment_id: int | None = None
    diet_plan: list[str]
    foods_to_avoid: list[str]
    medicine_guidance: list[str]
    daily_tips: list[str]
    hydration_goal_liters: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRead(BaseModel):
    id: int
    user_id: int
    severity: str
    title: str
    message: str
    triggered_by: list[str]
    acknowledged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CareSearchRequest(BaseModel):
    latitude: float
    longitude: float
    radius_meters: int = 5000
    location_label: str = ""


class CareLocation(BaseModel):
    name: str
    kind: str
    latitude: float
    longitude: float
    distance_km: float
    address: str = ""
    phone: str = ""
    source: str = ""


class ChatRequest(BaseModel):
    user_id: int
    message: str


class ChatResponse(BaseModel):
    reply: str
    risk_snapshot: str
    disclaimer: str


class ChatMessageRead(BaseModel):
    id: int
    user_id: int
    role: str
    content: str
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardRead(BaseModel):
    user: UserRead
    latest_assessment: AssessmentRead | None = None
    latest_prediction: RiskPredictionRead | None = None
    latest_recommendation: RecommendationRead | None = None
    active_alerts: list[AlertRead] = Field(default_factory=list)
    recent_daily_logs: list[DailyLogRead] = Field(default_factory=list)
    reports: list[MedicalReportRead] = Field(default_factory=list)
