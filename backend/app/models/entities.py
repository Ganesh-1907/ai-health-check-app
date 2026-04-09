from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from beanie import Document
from beanie import PydanticObjectId
from pydantic import Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Document):
    name: str
    age: int
    gender: str
    location: str = ""
    contact_number: str = ""
    latitude: float | None = None
    longitude: float | None = None
    email: str = ""
    hashed_password: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "users"


class Assessment(Document):
    user_id: PydanticObjectId
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    heart_rate: float | None = None
    blood_sugar: float | None = None
    cholesterol: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    symptoms: list[str] = Field(default_factory=list)
    symptom_details: dict[str, Any] = Field(default_factory=dict)
    medical_history: dict[str, Any] = Field(default_factory=dict)
    lifestyle: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "assessments"


class RiskPrediction(Document):
    assessment_id: PydanticObjectId
    user_id: PydanticObjectId
    risk_score: float
    risk_level: str
    confidence: float
    explanation: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "risk_predictions"


class DailyLog(Document):
    user_id: PydanticObjectId
    log_date: date
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    blood_sugar: float | None = None
    weight_kg: float | None = None
    steps: int | None = None
    sleep_hours: float | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "daily_logs"


class MedicalReport(Document):
    user_id: PydanticObjectId
    report_type: str
    file_name: str
    file_path: str
    content_type: str = ""
    extracted_text: str = ""
    extracted_findings: dict[str, Any] = Field(default_factory=dict)
    extraction_confidence: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "medical_reports"


class RecommendationPlan(Document):
    user_id: PydanticObjectId
    assessment_id: PydanticObjectId | None = None
    diet_plan: list[str] = Field(default_factory=list)
    foods_to_avoid: list[str] = Field(default_factory=list)
    medicine_guidance: list[str] = Field(default_factory=list)
    daily_tips: list[str] = Field(default_factory=list)
    current_condition_signals: list[str] = Field(default_factory=list)
    future_risk_diseases: list[str] = Field(default_factory=list)
    potential_diseases: list[str] = Field(default_factory=list)
    causes: list[str] = Field(default_factory=list)
    remedies: list[str] = Field(default_factory=list)
    precautions: list[str] = Field(default_factory=list)
    hydration_goal_liters: float | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "recommendation_plans"


class Alert(Document):
    user_id: PydanticObjectId
    severity: str
    title: str
    message: str
    triggered_by: list[str] = Field(default_factory=list)
    acknowledged: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "alerts"


class ChatMessage(Document):
    user_id: PydanticObjectId
    role: str
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "chat_messages"
