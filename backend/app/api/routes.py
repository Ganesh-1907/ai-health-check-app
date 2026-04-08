from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.models.entities import Alert, Assessment, ChatMessage, DailyLog, MedicalReport, RecommendationPlan, RiskPrediction, User
from app.models.entities import utcnow
from app.schemas.domain import (
    AlertRead,
    AssessmentCreate,
    AssessmentRead,
    AssessmentResponse,
    CareLocation,
    CareSearchRequest,
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    DailyLogCreate,
    DailyLogRead,
    DashboardRead,
    LoginRequest,
    MedicalReportRead,
    RecommendationRead,
    RiskPredictionRead,
    SignupRequest,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from app.services.alert_engine import AlertEngine
from app.services.auth import create_access_token, get_current_user, hash_password, verify_password
from app.services.chatbot import ChatbotService
from app.services.hospital_locator import HospitalLocator
from app.services.recommendation_engine import RecommendationEngine
from app.services.report_parser import ReportParser
from app.services.retinal_engine import RetinalAnalysisEngine
from app.services.risk_engine import RiskEngine, calculate_bmi
from app.services.mri_engine import MRIEngine
from app.services.ai_consultant import AIConsultant

router = APIRouter()
settings = get_settings()
risk_engine = RiskEngine()
recommendation_engine = RecommendationEngine()
alert_engine = AlertEngine()
report_parser = ReportParser()
hospital_locator = HospitalLocator()
chatbot_service = ChatbotService()
mri_engine = MRIEngine()
retinal_engine = RetinalAnalysisEngine()
ai_consultant = AIConsultant()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _str_id(doc) -> str:  # type: ignore[no-untyped-def]
    return str(doc.id)


def _oid(raw: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid id: {raw}") from exc


async def _get_user_or_404(user_id: str) -> User:
    user = await User.get(_oid(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _latest_assessment(user_id: str) -> Assessment | None:
    return await Assessment.find(
        Assessment.user_id == _oid(user_id)
    ).sort(-Assessment.created_at).limit(1).first_or_none()


async def _latest_recommendation(user_id: str) -> RecommendationPlan | None:
    return await RecommendationPlan.find(
        RecommendationPlan.user_id == _oid(user_id)
    ).sort(-RecommendationPlan.created_at).limit(1).first_or_none()


async def _latest_prediction_for_user(user_id: str) -> RiskPrediction | None:
    return await RiskPrediction.find(
        RiskPrediction.user_id == _oid(user_id)
    ).sort(-RiskPrediction.created_at).limit(1).first_or_none()


async def _recent_reports(user_id: str, limit: int = 5) -> list[MedicalReport]:
    return await MedicalReport.find(
        MedicalReport.user_id == _oid(user_id)
    ).sort(-MedicalReport.created_at).limit(limit).to_list()


def _user_to_read(user: User) -> UserRead:
    return UserRead(
        id=str(user.id),
        name=user.name,
        age=user.age,
        gender=user.gender,
        location=user.location,
        contact_number=user.contact_number,
        email=user.email,
        latitude=user.latitude,
        longitude=user.longitude,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _assessment_to_read(a: Assessment) -> AssessmentRead:
    return AssessmentRead(
        id=str(a.id),
        user_id=str(a.user_id),
        systolic_bp=a.systolic_bp,
        diastolic_bp=a.diastolic_bp,
        heart_rate=a.heart_rate,
        blood_sugar=a.blood_sugar,
        cholesterol=a.cholesterol,
        height_cm=a.height_cm,
        weight_kg=a.weight_kg,
        bmi=a.bmi,
        symptoms=a.symptoms,
        symptom_details=a.symptom_details,
        medical_history=a.medical_history,
        lifestyle=a.lifestyle,
        notes=a.notes,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _prediction_to_read(p: RiskPrediction) -> RiskPredictionRead:
    return RiskPredictionRead(
        id=str(p.id),
        assessment_id=str(p.assessment_id),
        risk_score=p.risk_score,
        risk_level=p.risk_level,
        confidence=p.confidence,
        explanation=p.explanation,
        red_flags=p.red_flags,
        summary=p.summary,
        created_at=p.created_at,
    )


def _log_to_read(log: DailyLog) -> DailyLogRead:
    return DailyLogRead(
        id=str(log.id),
        user_id=str(log.user_id),
        log_date=log.log_date,
        systolic_bp=log.systolic_bp,
        diastolic_bp=log.diastolic_bp,
        blood_sugar=log.blood_sugar,
        weight_kg=log.weight_kg,
        steps=log.steps,
        sleep_hours=log.sleep_hours,
        notes=log.notes,
        created_at=log.created_at,
        updated_at=log.updated_at,
    )


def _report_to_read(r: MedicalReport) -> MedicalReportRead:
    return MedicalReportRead(
        id=str(r.id),
        user_id=str(r.user_id),
        report_type=r.report_type,
        file_name=r.file_name,
        content_type=r.content_type,
        extracted_text=r.extracted_text,
        extracted_findings=r.extracted_findings,
        extraction_confidence=r.extraction_confidence,
        created_at=r.created_at,
    )


def _recommendation_to_read(rc: RecommendationPlan) -> RecommendationRead:
    return RecommendationRead(
        id=str(rc.id),
        user_id=str(rc.user_id),
        assessment_id=str(rc.assessment_id) if rc.assessment_id else None,
        diet_plan=rc.diet_plan,
        foods_to_avoid=rc.foods_to_avoid,
        medicine_guidance=rc.medicine_guidance,
        daily_tips=rc.daily_tips,
        potential_diseases=rc.potential_diseases,
        causes=rc.causes,
        remedies=rc.remedies,
        precautions=rc.precautions,
        hydration_goal_liters=rc.hydration_goal_liters,
        created_at=rc.created_at,
    )


def _alert_to_read(a: Alert) -> AlertRead:
    return AlertRead(
        id=str(a.id),
        user_id=str(a.user_id),
        severity=a.severity,
        title=a.title,
        message=a.message,
        triggered_by=a.triggered_by,
        acknowledged=a.acknowledged,
        created_at=a.created_at,
    )


async def _dashboard_payload(user_id: str) -> DashboardRead:
    user = await _get_user_or_404(user_id)
    assessment = await _latest_assessment(user_id)
    prediction = await _latest_prediction_for_user(user_id)
    recommendation = await _latest_recommendation(user_id)
    logs = await DailyLog.find(
        DailyLog.user_id == _oid(user_id)
    ).sort(-DailyLog.log_date, -DailyLog.created_at).limit(31).to_list()
    reports = await _recent_reports(user_id, limit=5)
    past_predictions = await RiskPrediction.find(
        RiskPrediction.user_id == _oid(user_id)
    ).sort(-RiskPrediction.created_at).limit(50).to_list()
    alerts = await Alert.find(
        Alert.user_id == _oid(user_id),
        Alert.acknowledged == False,  # noqa: E712
    ).sort(-Alert.created_at).limit(5).to_list()
    return DashboardRead(
        user=_user_to_read(user),
        latest_assessment=_assessment_to_read(assessment) if assessment else None,
        latest_prediction=_prediction_to_read(prediction) if prediction else None,
        latest_recommendation=_recommendation_to_read(recommendation) if recommendation else None,
        active_alerts=[_alert_to_read(a) for a in alerts],
        recent_daily_logs=[_log_to_read(log) for log in logs],
        past_predictions=[_prediction_to_read(p) for p in past_predictions],
        reports=[_report_to_read(r) for r in reports],
    )


async def _upsert_prediction_and_recommendation(
    user: User,
    assessment: Assessment,
    reports: list[MedicalReport],
) -> tuple[RiskPrediction, RecommendationPlan]:
    risk_result = risk_engine.score(assessment, user=user, reports=reports)
    existing_prediction = await RiskPrediction.find_one(
        RiskPrediction.assessment_id == assessment.id
    )
    if existing_prediction is None:
        prediction = RiskPrediction(
            assessment_id=assessment.id,
            user_id=user.id,
            risk_score=risk_result.risk_score,
            risk_level=risk_result.risk_level,
            confidence=risk_result.confidence,
            explanation=risk_result.explanation,
            red_flags=risk_result.red_flags,
            summary=risk_result.summary,
        )
        await prediction.insert()
    else:
        existing_prediction.risk_score = risk_result.risk_score
        existing_prediction.risk_level = risk_result.risk_level
        existing_prediction.confidence = risk_result.confidence
        existing_prediction.explanation = risk_result.explanation
        existing_prediction.red_flags = risk_result.red_flags
        existing_prediction.summary = risk_result.summary
        existing_prediction.updated_at = utcnow()
        await existing_prediction.save()
        prediction = existing_prediction

    recommendation_payload = recommendation_engine.build(user, assessment, prediction, reports=reports)
    
    # Enrich with AI Clinical Insights
    clinical_insights = await ai_consultant.get_clinical_deep_dive(user, assessment, prediction)
    recommendation_payload.update(clinical_insights)

    existing_recommendation = await RecommendationPlan.find_one(
        RecommendationPlan.user_id == user.id,
        RecommendationPlan.assessment_id == assessment.id,
    )
    if existing_recommendation is None:
        recommendation = RecommendationPlan(
            user_id=user.id,
            assessment_id=assessment.id,
            **recommendation_payload,
        )
        await recommendation.insert()
    else:
        existing_recommendation.diet_plan = recommendation_payload["diet_plan"]
        existing_recommendation.foods_to_avoid = recommendation_payload["foods_to_avoid"]
        existing_recommendation.medicine_guidance = recommendation_payload["medicine_guidance"]
        existing_recommendation.daily_tips = recommendation_payload["daily_tips"]
        existing_recommendation.potential_diseases = recommendation_payload["potential_diseases"]
        existing_recommendation.causes = recommendation_payload["causes"]
        existing_recommendation.remedies = recommendation_payload["remedies"]
        existing_recommendation.precautions = recommendation_payload["precautions"]
        existing_recommendation.hydration_goal_liters = recommendation_payload["hydration_goal_liters"]
        existing_recommendation.updated_at = utcnow()
        await existing_recommendation.save()
        recommendation = existing_recommendation
    return prediction, recommendation


async def _persist_assessment_bundle(user: User, payload: AssessmentCreate) -> AssessmentResponse:
    data = payload.model_dump()
    data["bmi"] = calculate_bmi(data.get("height_cm"), data.get("weight_kg"))
    assessment = Assessment(user_id=user.id, **data)
    await assessment.insert()
    reports = await _recent_reports(str(user.id))
    prediction, recommendation = await _upsert_prediction_and_recommendation(user, assessment, reports)
    
    for alert_data in alert_engine.from_assessment(assessment):
        await Alert(user_id=user.id, **alert_data).insert()
        
    return {
        "assessment": _assessment_to_read(assessment),
        "prediction": _prediction_to_read(prediction),
        "recommendation": _recommendation_to_read(recommendation) if recommendation else None
    }


def _first_number(value: object) -> float | None:
    import re
    if value is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    return float(match.group(1))


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


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest) -> TokenResponse:
    existing = await User.find_one(User.email == payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        age=payload.age,
        gender=payload.gender,
        location=payload.location,
        contact_number=payload.contact_number,
        latitude=payload.latitude,
        longitude=payload.longitude,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    await user.insert()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user_id=str(user.id), name=user.name)


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await User.find_one(User.email == payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user_id=str(user.id), name=user.name)


# ─── Users ────────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> UserRead:
    user = await _get_user_or_404(user_id)
    return _user_to_read(user)


@router.put("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> UserRead:
    user = await _get_user_or_404(user_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    user.updated_at = utcnow()
    await user.save()
    return _user_to_read(user)


# ─── Assessments ──────────────────────────────────────────────────────────────

@router.post("/users/{user_id}/v2-assessments", response_model=AssessmentResponse)
async def create_assessment(
    user_id: str,
    payload: AssessmentCreate,
    current_user: User = Depends(get_current_user),
) -> AssessmentResponse:
    user = await _get_user_or_404(user_id)
    return await _persist_assessment_bundle(user, payload)


@router.get("/users/{user_id}/assessments/latest", response_model=AssessmentRead | None)
async def get_latest_assessment(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> AssessmentRead | None:
    await _get_user_or_404(user_id)
    assessment = await _latest_assessment(user_id)
    return _assessment_to_read(assessment) if assessment else None


# ─── Predictions ──────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/predictions/latest", response_model=RiskPredictionRead | None)
async def get_latest_prediction(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> RiskPredictionRead | None:
    await _get_user_or_404(user_id)
    prediction = await _latest_prediction_for_user(user_id)
    return _prediction_to_read(prediction) if prediction else None


# ─── Daily Logs ───────────────────────────────────────────────────────────────

@router.post("/users/{user_id}/daily-logs", response_model=DailyLogRead)
async def create_daily_log(
    user_id: str,
    payload: DailyLogCreate,
    current_user: User = Depends(get_current_user),
) -> DailyLogRead:
    user = await _get_user_or_404(user_id)
    log = DailyLog(user_id=user.id, **payload.model_dump())
    await log.insert()
    for alert_data in alert_engine.from_daily_log(log):
        await Alert(user_id=user.id, **alert_data).insert()
    return _log_to_read(log)


@router.get("/users/{user_id}/daily-logs", response_model=list[DailyLogRead])
async def list_daily_logs(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> list[DailyLogRead]:
    await _get_user_or_404(user_id)
    logs = await DailyLog.find(
        DailyLog.user_id == _oid(user_id)
    ).sort(-DailyLog.log_date, -DailyLog.created_at).limit(30).to_list()
    return [_log_to_read(log) for log in logs]


# ─── Recommendations ──────────────────────────────────────────────────────────

@router.get("/users/{user_id}/recommendations/latest", response_model=RecommendationRead | None)
async def get_latest_recommendation(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> RecommendationRead | None:
    await _get_user_or_404(user_id)
    rec = await _latest_recommendation(user_id)
    return _recommendation_to_read(rec) if rec else None


@router.get("/users/{user_id}/tips", response_model=list[str])
async def get_latest_tips(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> list[str]:
    rec = await _latest_recommendation(user_id)
    return rec.daily_tips if rec else []


# ─── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/alerts", response_model=list[AlertRead])
async def list_alerts(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> list[AlertRead]:
    await _get_user_or_404(user_id)
    alerts = await Alert.find(
        Alert.user_id == _oid(user_id)
    ).sort(-Alert.created_at).limit(20).to_list()
    return [_alert_to_read(a) for a in alerts]


# ─── Reports ──────────────────────────────────────────────────────────────────

@router.post("/users/{user_id}/reports/upload", response_model=MedicalReportRead)
async def upload_report(
    user_id: str,
    report_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> MedicalReportRead:
    user = await _get_user_or_404(user_id)
    extension = Path(file.filename or "").suffix or ".bin"
    file_name = f"{uuid.uuid4().hex}{extension}"
    file_path = settings.storage_path / file_name
    contents = await file.read()
    file_path.write_bytes(contents)

    extracted_text, findings, confidence = await report_parser.parse(file_path, report_type, file.content_type or "")
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
    await report.insert()

    for alert_data in alert_engine.from_report(report):
        await Alert(user_id=user.id, **alert_data).insert()

    latest_assessment = await _latest_assessment(user_id)
    if latest_assessment is None:
        seed = _assessment_seed_from_report(report)
        if any(seed[k] is not None for k in ["systolic_bp", "diastolic_bp", "heart_rate", "blood_sugar", "cholesterol"]):
            latest_assessment = Assessment(user_id=user.id, **seed)
            await latest_assessment.insert()

    if latest_assessment is not None:
        reports = await _recent_reports(user_id)
        await _upsert_prediction_and_recommendation(user, latest_assessment, reports)

    return _report_to_read(report)


@router.get("/users/{user_id}/reports", response_model=list[MedicalReportRead])
async def list_reports(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> list[MedicalReportRead]:
    await _get_user_or_404(user_id)
    reports = await MedicalReport.find(
        MedicalReport.user_id == _oid(user_id)
    ).sort(-MedicalReport.created_at).to_list()
    return [_report_to_read(r) for r in reports]


# ─── Chat ─────────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/chat-history", response_model=list[ChatMessageRead])
async def get_chat_history(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> list[ChatMessageRead]:
    await _get_user_or_404(user_id)
    messages = await ChatMessage.find(
        ChatMessage.user_id == _oid(user_id)
    ).sort(ChatMessage.created_at).to_list()
    return [
        ChatMessageRead(
            id=str(m.id),
            user_id=str(m.user_id),
            role=m.role,
            content=m.content,
            metadata_json=m.metadata_json,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    user = await _get_user_or_404(payload.user_id)
    prediction = await _latest_prediction_for_user(payload.user_id)
    assessment = await _latest_assessment(payload.user_id)
    recommendation = await _latest_recommendation(payload.user_id)
    reports = await _recent_reports(payload.user_id, limit=3)
    recent_logs = await DailyLog.find(
        DailyLog.user_id == _oid(payload.user_id)
    ).sort(-DailyLog.log_date).limit(5).to_list()
    history_docs = await ChatMessage.find(
        ChatMessage.user_id == _oid(payload.user_id)
    ).sort(-ChatMessage.created_at).limit(6).to_list() if settings.chat_store_messages else []
    history = list(reversed(history_docs)) if settings.chat_store_messages else []

    reply = await chatbot_service.reply(
        user=user,
        message=payload.message,
        prediction=prediction,
        assessment=assessment,
        recommendation=recommendation,
        reports=reports,
        recent_logs=recent_logs,
        history=history,
    )

    if settings.chat_store_messages:
        await ChatMessage(user_id=user.id, role="user", content=payload.message, metadata_json={}).insert()
        await ChatMessage(user_id=user.id, role="assistant", content=reply, metadata_json={}).insert()

    return ChatResponse(
        reply=reply,
        risk_snapshot=prediction.summary if prediction else "No prediction available yet.",
        disclaimer="This is support guidance only. Consult a doctor for diagnosis and treatment.",
    )


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/dashboard", response_model=DashboardRead)
async def get_dashboard(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> DashboardRead:
    return await _dashboard_payload(user_id)


# ─── Care Search ──────────────────────────────────────────────────────────────

@router.post("/care-search", response_model=list[CareLocation])
async def care_search(
    payload: CareSearchRequest,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return await hospital_locator.search(
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
    )


# ─── Imaging Analysis ────────────────────────────────────────────────────────

@router.post("/retinal-analysis")
async def retinal_analysis(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Analyze retinal images for cardiovascular risk visualization."""
    contents = await file.read()
    from io import BytesIO

    result = retinal_engine.predict(BytesIO(contents))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ─── MRI Prediction ──────────────────────────────────────────────────────────

@router.post("/mri-prediction")
async def mri_prediction(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Classify brain MRI images for tumor detection."""
    contents = await file.read()
    from io import BytesIO
    result = mri_engine.predict(BytesIO(contents))
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result
