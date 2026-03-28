from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.db import session as db_session
from app.api import routes as route_module
import beanie
from app.models.entities import (
    Alert, Assessment, ChatMessage, DailyLog, MedicalReport,
    RecommendationPlan, RiskPrediction, User,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def init_mock_db():
    """Use mongomock instead of a real MongoDB for every test."""
    client = AsyncMongoMockClient()
    await beanie.init_beanie(
        database=client["test_db"],
        document_models=[User, Assessment, RiskPrediction, DailyLog, MedicalReport, RecommendationPlan, Alert, ChatMessage],
    )
    yield
    # Drop all collections after the test
    for col in [User, Assessment, RiskPrediction, DailyLog, MedicalReport, RecommendationPlan, Alert, ChatMessage]:
        await col.find_all().delete()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Helper: signup a test user and return auth headers."""
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "test@example.com",
        "password": "Test@1234",
        "name": "Test User",
        "age": 45,
        "gender": "Male",
        "location": "Bengaluru",
        "contact_number": "9000000001",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "user_id": resp.json()["user_id"]}


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_signup_and_login(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "demo@example.com",
        "password": "Demo@1234",
        "name": "Demo User",
        "age": 54,
        "gender": "Male",
        "location": "Kolkata",
        "contact_number": "9999999999",
    })
    assert resp.status_code == 200
    payload = resp.json()
    assert "access_token" in payload
    assert len(payload["user_id"]) == 24  # MongoDB ObjectId hex

    login = await client.post("/api/v1/auth/login", json={
        "email": "demo@example.com",
        "password": "Demo@1234",
    })
    assert login.status_code == 200
    assert "access_token" in login.json()

    bad_login = await client.post("/api/v1/auth/login", json={
        "email": "demo@example.com",
        "password": "WrongPassword",
    })
    assert bad_login.status_code == 401


@pytest.mark.anyio
async def test_create_user_and_assessment(client: AsyncClient, auth_headers: dict) -> None:
    user_id = auth_headers["user_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "user_id"}

    assessment = await client.post(
        f"/api/v1/users/{user_id}/assessments",
        json={
            "systolic_bp": 142,
            "diastolic_bp": 91,
            "heart_rate": 96,
            "blood_sugar": 134,
            "cholesterol": 216,
            "height_cm": 164,
            "weight_kg": 78,
            "symptoms": ["fatigue", "shortness of breath"],
            "medical_history": {"family_history": True, "hypertension": True},
            "lifestyle": {"smoking": False, "exercise": "low", "sleep_hours": 5.8, "stress_level": "high"},
        },
        headers=headers,
    )
    assert assessment.status_code == 200
    assert assessment.json()["bmi"] > 0

    prediction = await client.get(f"/api/v1/users/{user_id}/predictions/latest", headers=headers)
    assert prediction.status_code == 200
    assert prediction.json()["risk_score"] > 0


@pytest.mark.anyio
async def test_report_upload_extracts_metrics_and_alerts(client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO
    user_id = auth_headers["user_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "user_id"}

    def fake_parse(*args, **kwargs):  # type: ignore[no-untyped-def]
        return (
            "Angiogram report. Blockage 80%. LDL 182 mg/dL. EF 32%.",
            {
                "report_type": "angiogram",
                "metrics": {"blockage_percent": "80", "ldl": "182", "ejection_fraction": "32"},
                "detected_markers": ["angiogram", "blockage", "ldl", "ejection fraction"],
            },
            0.93,
        )

    monkeypatch.setattr(route_module.report_parser, "parse", fake_parse)

    upload = await client.post(
        f"/api/v1/users/{user_id}/reports/upload",
        files={"file": ("report.png", BytesIO(b"fake"), "image/png")},
        data={"report_type": "angiogram"},
        headers=headers,
    )
    assert upload.status_code == 200
    payload = upload.json()
    assert payload["extraction_confidence"] == 0.93

    alerts = await client.get(f"/api/v1/users/{user_id}/alerts", headers=headers)
    assert alerts.status_code == 200


@pytest.mark.anyio
async def test_daily_log_and_dashboard(client: AsyncClient, auth_headers: dict) -> None:
    user_id = auth_headers["user_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "user_id"}

    log = await client.post(
        f"/api/v1/users/{user_id}/daily-logs",
        json={"log_date": "2026-03-28", "systolic_bp": 128, "diastolic_bp": 82, "blood_sugar": 110, "weight_kg": 72, "steps": 6200, "sleep_hours": 7.2},
        headers=headers,
    )
    assert log.status_code == 200

    dashboard = await client.get(f"/api/v1/users/{user_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["user"]["name"] == "Test User"
    assert len(data["recent_daily_logs"]) >= 1


@pytest.mark.anyio
async def test_chat_endpoint_contract(client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = auth_headers["user_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "user_id"}

    async def fake_reply(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "Direct answer: monitor daily. Why it matters: values need review."

    monkeypatch.setattr(route_module.chatbot_service, "reply", fake_reply)

    resp = await client.post(
        "/api/v1/chat",
        json={"user_id": user_id, "message": "What should I do?"},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "Direct answer" in payload["reply"]
    assert "Consult" in payload["disclaimer"]
