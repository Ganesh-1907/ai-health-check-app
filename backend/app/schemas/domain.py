from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─── Auth ────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    age: int
    gender: str
    location: str = ""
    contact_number: str = ""
    latitude: float | None = None
    longitude: float | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


# ─── User ─────────────────────────────────────────────────────────────────────

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


class UserRead(BaseModel):
    id: str
    name: str
    age: int
    gender: str
    location: str
    contact_number: str
    email: str = ""
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Assessment ───────────────────────────────────────────────────────────────

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
    id: str
    user_id: str
    bmi: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Risk Prediction ──────────────────────────────────────────────────────────

class RiskPredictionRead(BaseModel):
    id: str
    assessment_id: str
    risk_score: float
    risk_level: str
    confidence: float
    explanation: list[str]
    red_flags: list[str]
    summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Daily Log ────────────────────────────────────────────────────────────────

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
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Medical Report ───────────────────────────────────────────────────────────

class MedicalReportRead(BaseModel):
    id: str
    user_id: str
    report_type: str
    file_name: str
    content_type: str
    extracted_text: str
    extracted_findings: dict[str, Any]
    extraction_confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Recommendation ───────────────────────────────────────────────────────────

class RecommendationRead(BaseModel):
    id: str
    user_id: str
    assessment_id: str | None = None
    diet_plan: list[str]
    foods_to_avoid: list[str]
    medicine_guidance: list[str]
    daily_tips: list[str]
    hydration_goal_liters: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Alert ────────────────────────────────────────────────────────────────────

class AlertRead(BaseModel):
    id: str
    user_id: str
    severity: str
    title: str
    message: str
    triggered_by: list[str]
    acknowledged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Care Search ──────────────────────────────────────────────────────────────

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


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    risk_snapshot: str
    disclaimer: str


class ChatMessageRead(BaseModel):
    id: str
    user_id: str
    role: str
    content: str
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardRead(BaseModel):
    user: UserRead
    latest_assessment: AssessmentRead | None = None
    latest_prediction: RiskPredictionRead | None = None
    latest_recommendation: RecommendationRead | None = None
    active_alerts: list[AlertRead] = Field(default_factory=list)
    recent_daily_logs: list[DailyLogRead] = Field(default_factory=list)
    past_predictions: list[RiskPredictionRead] = Field(default_factory=list)
    reports: list[MedicalReportRead] = Field(default_factory=list)
