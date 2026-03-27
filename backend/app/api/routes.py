from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Alert, Assessment, ChatMessage, DailyLog, MedicalReport, RecommendationPlan, RiskPrediction, User
from app.schemas.domain import (
    AlertRead,
    AssessmentCreate,
    AssessmentRead,
    CareLocation,
    CareSearchRequest,
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    DailyLogCreate,
    DailyLogRead,
    DashboardRead,
    MedicalReportRead,
    RecommendationRead,
    RiskPredictionRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.alert_engine import AlertEngine
from app.services.chatbot import ChatbotService
from app.services.hospital_locator import HospitalLocator
from app.services.recommendation_engine import RecommendationEngine
from app.services.report_parser import ReportParser
from app.services.risk_engine import RiskEngine, calculate_bmi


router = APIRouter()
settings = get_settings()
risk_engine = RiskEngine()
recommendation_engine = RecommendationEngine()
alert_engine = AlertEngine()
report_parser = ReportParser()
hospital_locator = HospitalLocator()
chatbot_service = ChatbotService()


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _latest_assessment(db: Session, user_id: int) -> Assessment | None:
    statement = select(Assessment).where(Assessment.user_id == user_id).order_by(desc(Assessment.created_at)).limit(1)
    return db.scalar(statement)


def _latest_recommendation(db: Session, user_id: int) -> RecommendationPlan | None:
    statement = (
        select(RecommendationPlan)
        .where(RecommendationPlan.user_id == user_id)
        .order_by(desc(RecommendationPlan.created_at))
        .limit(1)
    )
    return db.scalar(statement)


def _latest_prediction_for_user(db: Session, user_id: int) -> RiskPrediction | None:
    statement = (
        select(RiskPrediction)
        .join(Assessment, Assessment.id == RiskPrediction.assessment_id)
        .where(Assessment.user_id == user_id)
        .order_by(desc(RiskPrediction.created_at))
        .limit(1)
    )
    return db.scalar(statement)


def _recent_reports(db: Session, user_id: int, limit: int = 5) -> list[MedicalReport]:
    statement = (
        select(MedicalReport)
        .where(MedicalReport.user_id == user_id)
        .order_by(desc(MedicalReport.created_at))
        .limit(limit)
    )
    return list(db.scalars(statement))


def _first_number(value: object) -> float | None:
    import re

    if value is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    return float(match.group(1))


def _dashboard_payload(db: Session, user_id: int) -> DashboardRead:
    user = _get_user_or_404(db, user_id)
    logs = list(
        db.scalars(
            select(DailyLog)
            .where(DailyLog.user_id == user_id)
            .order_by(desc(DailyLog.log_date), desc(DailyLog.created_at), desc(DailyLog.id))
            .limit(7),
        )
    )
    reports = list(
        db.scalars(
            select(MedicalReport)
            .where(MedicalReport.user_id == user_id)
            .order_by(desc(MedicalReport.created_at))
            .limit(5),
        )
    )
    alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.user_id == user_id, Alert.acknowledged.is_(False))
            .order_by(desc(Alert.created_at))
            .limit(5),
        )
    )

    return DashboardRead(
        user=user,
        latest_assessment=_latest_assessment(db, user_id),
        latest_prediction=_latest_prediction_for_user(db, user_id),
        latest_recommendation=_latest_recommendation(db, user_id),
        active_alerts=alerts,
        recent_daily_logs=logs,
        reports=reports,
    )


def _persist_assessment_bundle(db: Session, user: User, payload: AssessmentCreate) -> Assessment:
    data = payload.model_dump()
    data["bmi"] = calculate_bmi(data.get("height_cm"), data.get("weight_kg"))
    assessment = Assessment(user_id=user.id, **data)
    db.add(assessment)
    db.flush()

    _upsert_prediction_and_recommendation(db, user, assessment, _recent_reports(db, user.id))

    for alert_data in alert_engine.from_assessment(assessment):
        db.add(Alert(user_id=user.id, **alert_data))

    return assessment


def _upsert_prediction_and_recommendation(
    db: Session,
    user: User,
    assessment: Assessment,
    reports: list[MedicalReport],
) -> RiskPrediction:
    risk_result = risk_engine.score(assessment, reports=reports)
    prediction = assessment.prediction or db.scalar(
        select(RiskPrediction).where(RiskPrediction.assessment_id == assessment.id).limit(1)
    )
    if prediction is None:
        prediction = RiskPrediction(
            assessment_id=assessment.id,
            risk_score=risk_result.risk_score,
            risk_level=risk_result.risk_level,
            confidence=risk_result.confidence,
            explanation=risk_result.explanation,
            red_flags=risk_result.red_flags,
            summary=risk_result.summary,
        )
        db.add(prediction)
    else:
        prediction.risk_score = risk_result.risk_score
        prediction.risk_level = risk_result.risk_level
        prediction.confidence = risk_result.confidence
        prediction.explanation = risk_result.explanation
        prediction.red_flags = risk_result.red_flags
        prediction.summary = risk_result.summary
        db.add(prediction)
    db.flush()

    recommendation_payload = recommendation_engine.build(user, assessment, prediction, reports=reports)
    recommendation = db.scalar(
        select(RecommendationPlan)
        .where(RecommendationPlan.user_id == user.id, RecommendationPlan.assessment_id == assessment.id)
        .order_by(desc(RecommendationPlan.created_at))
        .limit(1)
    )
    if recommendation is None:
        db.add(
            RecommendationPlan(
                user_id=user.id,
                assessment_id=assessment.id,
                **recommendation_payload,
            )
        )
    else:
        recommendation.diet_plan = recommendation_payload["diet_plan"]
        recommendation.foods_to_avoid = recommendation_payload["foods_to_avoid"]
        recommendation.medicine_guidance = recommendation_payload["medicine_guidance"]
        recommendation.daily_tips = recommendation_payload["daily_tips"]
        recommendation.hydration_goal_liters = recommendation_payload["hydration_goal_liters"]
        db.add(recommendation)
    return prediction


def _assessment_seed_from_report(report: MedicalReport) -> dict:
    import re

    findings = report.extracted_findings or {}
    metrics = findings.get("metrics", {}) if isinstance(findings, dict) else {}
    seed = {
        "systolic_bp": None,
        "diastolic_bp": None,
        "heart_rate": _first_number(metrics.get("heart_rate")),
        "blood_sugar": _first_number(metrics.get("glucose")),
        "cholesterol": _first_number(metrics.get("cholesterol")),
        "height_cm": None,
        "weight_kg": None,
        "bmi": None,
        "symptoms": [],
        "symptom_details": {},
        "medical_history": {},
        "lifestyle": {},
        "notes": f"Auto-generated from uploaded {report.report_type} report.",
    }
    blood_pressure = str(metrics.get("blood_pressure", ""))
    match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", blood_pressure)
    if match:
        seed["systolic_bp"] = float(match.group(1))
        seed["diastolic_bp"] = float(match.group(2))
    return seed


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@router.post("/bootstrap/demo")
def bootstrap_demo(db: Session = Depends(get_db)) -> dict:
    statement = select(User).where(User.name == "Demo User").limit(1)
    user = db.scalar(statement)
    if not user:
        user = User(
            name="Demo User",
            age=54,
            gender="Male",
            location="Kolkata",
            contact_number="9999999999",
            latitude=22.5726,
            longitude=88.3639,
        )
        db.add(user)
        db.flush()

    has_assessment = db.scalar(select(Assessment).where(Assessment.user_id == user.id).limit(1))
    if not has_assessment:
        _persist_assessment_bundle(
            db,
            user,
            AssessmentCreate(
                systolic_bp=148,
                diastolic_bp=96,
                heart_rate=104,
                blood_sugar=162,
                cholesterol=232,
                height_cm=170,
                weight_kg=84,
                symptoms=["chest pain", "fatigue", "sweating"],
                medical_history={
                    "family_history": True,
                    "previous_heart_problems": False,
                    "hypertension": True,
                    "diabetes": False,
                    "surgeries": "none",
                },
                lifestyle={
                    "smoking": True,
                    "alcohol": "occasional",
                    "exercise": "low",
                    "sleep_hours": 5.5,
                    "stress_level": "high",
                    "food_habits": "mixed",
                },
                notes="Auto-seeded demo profile for app verification.",
            ),
        )

    existing_logs = list(db.scalars(select(DailyLog).where(DailyLog.user_id == user.id).limit(1)))
    if not existing_logs:
        demo_logs = [
            DailyLog(user_id=user.id, log_date=date.today() - timedelta(days=4), systolic_bp=132, diastolic_bp=84, blood_sugar=124, weight_kg=79.4, steps=5200, sleep_hours=6.8),
            DailyLog(user_id=user.id, log_date=date.today() - timedelta(days=3), systolic_bp=136, diastolic_bp=86, blood_sugar=130, weight_kg=79.0, steps=4800, sleep_hours=6.4),
            DailyLog(user_id=user.id, log_date=date.today() - timedelta(days=2), systolic_bp=142, diastolic_bp=90, blood_sugar=139, weight_kg=78.8, steps=4300, sleep_hours=6.0),
            DailyLog(user_id=user.id, log_date=date.today() - timedelta(days=1), systolic_bp=145, diastolic_bp=93, blood_sugar=152, weight_kg=78.7, steps=3900, sleep_hours=5.9),
            DailyLog(user_id=user.id, log_date=date.today(), systolic_bp=148, diastolic_bp=96, blood_sugar=164, weight_kg=78.5, steps=3500, sleep_hours=5.8),
        ]
        db.add_all(demo_logs)

    existing_messages = list(db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).limit(1)))
    if not existing_messages:
        db.add(
            ChatMessage(
                user_id=user.id,
                role="assistant",
                content="I can help you understand your heart-risk profile, uploaded reports, lifestyle guidance, and emergency warning signs.",
                metadata_json={},
            )
        )

    latest_assessment = _latest_assessment(db, user.id)
    if latest_assessment is not None:
        _upsert_prediction_and_recommendation(db, user, latest_assessment, _recent_reports(db, user.id))

    db.commit()
    return {
        "user_id": user.id,
        "dashboard": _dashboard_payload(db, user.id).model_dump(mode="json"),
    }


@router.post("/users", response_model=UserRead)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    return _get_user_or_404(db, user_id)


@router.put("/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    user = _get_user_or_404(db, user_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/assessments", response_model=AssessmentRead)
def create_assessment(user_id: int, payload: AssessmentCreate, db: Session = Depends(get_db)) -> Assessment:
    user = _get_user_or_404(db, user_id)
    assessment = _persist_assessment_bundle(db, user, payload)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/users/{user_id}/assessments/latest", response_model=AssessmentRead | None)
def get_latest_assessment(user_id: int, db: Session = Depends(get_db)) -> Assessment | None:
    _get_user_or_404(db, user_id)
    return _latest_assessment(db, user_id)


@router.get("/users/{user_id}/predictions/latest", response_model=RiskPredictionRead | None)
def get_latest_prediction(user_id: int, db: Session = Depends(get_db)) -> RiskPrediction | None:
    _get_user_or_404(db, user_id)
    return _latest_prediction_for_user(db, user_id)


@router.post("/users/{user_id}/daily-logs", response_model=DailyLogRead)
def create_daily_log(user_id: int, payload: DailyLogCreate, db: Session = Depends(get_db)) -> DailyLog:
    user = _get_user_or_404(db, user_id)
    log = DailyLog(user_id=user.id, **payload.model_dump())
    db.add(log)
    db.flush()

    for alert_data in alert_engine.from_daily_log(log):
        db.add(Alert(user_id=user.id, **alert_data))

    db.commit()
    db.refresh(log)
    return log


@router.get("/users/{user_id}/daily-logs", response_model=list[DailyLogRead])
def list_daily_logs(user_id: int, db: Session = Depends(get_db)) -> list[DailyLog]:
    _get_user_or_404(db, user_id)
    statement = (
        select(DailyLog)
        .where(DailyLog.user_id == user_id)
        .order_by(desc(DailyLog.log_date), desc(DailyLog.created_at), desc(DailyLog.id))
        .limit(30)
    )
    return list(db.scalars(statement))


@router.get("/users/{user_id}/recommendations/latest", response_model=RecommendationRead | None)
def get_latest_recommendation(user_id: int, db: Session = Depends(get_db)) -> RecommendationPlan | None:
    _get_user_or_404(db, user_id)
    return _latest_recommendation(db, user_id)


@router.get("/users/{user_id}/tips", response_model=list[str])
def get_latest_tips(user_id: int, db: Session = Depends(get_db)) -> list[str]:
    recommendation = _latest_recommendation(db, user_id)
    if not recommendation:
        return []
    return recommendation.daily_tips


@router.get("/users/{user_id}/alerts", response_model=list[AlertRead])
def list_alerts(user_id: int, db: Session = Depends(get_db)) -> list[Alert]:
    _get_user_or_404(db, user_id)
    statement = select(Alert).where(Alert.user_id == user_id).order_by(desc(Alert.created_at)).limit(20)
    return list(db.scalars(statement))


@router.post("/users/{user_id}/reports/upload", response_model=MedicalReportRead)
async def upload_report(
    user_id: int,
    report_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> MedicalReport:
    user = _get_user_or_404(db, user_id)
    extension = Path(file.filename or "").suffix or ".bin"
    file_name = f"{uuid.uuid4().hex}{extension}"
    file_path = settings.storage_path / file_name
    contents = await file.read()
    file_path.write_bytes(contents)

    extracted_text, findings, confidence = report_parser.parse(file_path, report_type, file.content_type or "")
    report = MedicalReport(
        user_id=user.id,
        report_type=report_type,
        file_name=file.filename or file_name,
        file_path=str(file_path),
        content_type=file.content_type or "",
        extracted_text=extracted_text,
        extracted_findings=findings,
        extraction_confidence=confidence,
    )
    db.add(report)
    db.flush()

    for alert_data in alert_engine.from_report(report):
        db.add(Alert(user_id=user.id, **alert_data))

    latest_assessment = _latest_assessment(db, user.id)
    if latest_assessment is None:
        seed = _assessment_seed_from_report(report)
        if any(seed[key] is not None for key in ["systolic_bp", "diastolic_bp", "heart_rate", "blood_sugar", "cholesterol"]):
            latest_assessment = Assessment(user_id=user.id, **seed)
            db.add(latest_assessment)
            db.flush()

    if latest_assessment is not None:
        _upsert_prediction_and_recommendation(db, user, latest_assessment, _recent_reports(db, user.id))

    db.commit()
    db.refresh(report)
    return report


@router.get("/users/{user_id}/reports", response_model=list[MedicalReportRead])
def list_reports(user_id: int, db: Session = Depends(get_db)) -> list[MedicalReport]:
    _get_user_or_404(db, user_id)
    statement = select(MedicalReport).where(MedicalReport.user_id == user_id).order_by(desc(MedicalReport.created_at))
    return list(db.scalars(statement))


@router.get("/users/{user_id}/chat-history", response_model=list[ChatMessageRead])
def get_chat_history(user_id: int, db: Session = Depends(get_db)) -> list[ChatMessage]:
    _get_user_or_404(db, user_id)
    statement = select(ChatMessage).where(ChatMessage.user_id == user_id).order_by(ChatMessage.created_at)
    return list(db.scalars(statement))


@router.get("/users/{user_id}/dashboard", response_model=DashboardRead)
def get_dashboard(user_id: int, db: Session = Depends(get_db)) -> DashboardRead:
    return _dashboard_payload(db, user_id)


@router.post("/care-search", response_model=list[CareLocation])
async def care_search(payload: CareSearchRequest) -> list[dict]:
    return await hospital_locator.search(
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    user = _get_user_or_404(db, payload.user_id)
    prediction = _latest_prediction_for_user(db, payload.user_id)
    assessment = _latest_assessment(db, payload.user_id)
    recommendation = _latest_recommendation(db, payload.user_id)
    reports = list(
        db.scalars(
            select(MedicalReport)
            .where(MedicalReport.user_id == payload.user_id)
            .order_by(desc(MedicalReport.created_at))
            .limit(3),
        )
    )
    recent_logs = list(
        db.scalars(
            select(DailyLog).where(DailyLog.user_id == payload.user_id).order_by(desc(DailyLog.log_date)).limit(5),
        )
    )
    history = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == payload.user_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(6),
        )
    )
    reply = await chatbot_service.reply(
        user=user,
        message=payload.message,
        prediction=prediction,
        assessment=assessment,
        recommendation=recommendation,
        reports=reports,
        recent_logs=recent_logs,
        history=list(reversed(history)),
    )

    db.add(ChatMessage(user_id=user.id, role="user", content=payload.message, metadata_json={}))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, metadata_json={}))
    db.commit()

    return ChatResponse(
        reply=reply,
        risk_snapshot=prediction.summary if prediction else "No prediction available yet.",
        disclaimer="This is support guidance only. Consult a doctor for diagnosis and treatment.",
    )
