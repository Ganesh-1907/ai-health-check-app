from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import routes


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_bootstrap_and_dashboard() -> None:
    bootstrap = client.post("/api/v1/bootstrap/demo")
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert payload["user_id"] >= 1
    assert payload["dashboard"]["latest_prediction"]["risk_level"] in {"Low", "Medium", "High"}

    dashboard = client.get(f"/api/v1/users/{payload['user_id']}/dashboard")
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.json()
    assert dashboard_payload["user"]["name"] == "Demo User"
    assert len(dashboard_payload["recent_daily_logs"]) >= 1


def test_create_user_and_assessment() -> None:
    user = client.post(
        "/api/v1/users",
        json={
            "name": "API Test",
            "age": 49,
            "gender": "Female",
            "location": "Delhi",
            "contact_number": "8888888888",
        },
    )
    assert user.status_code == 200
    user_id = user.json()["id"]

    assessment = client.post(
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
    )
    assert assessment.status_code == 200
    assert assessment.json()["bmi"] > 0

    prediction = client.get(f"/api/v1/users/{user_id}/predictions/latest")
    assert prediction.status_code == 200
    assert prediction.json()["risk_score"] > 0


def test_report_upload_rescores_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    user = client.post(
        "/api/v1/users",
        json={
            "name": "Report Test",
            "age": 58,
            "gender": "Male",
            "location": "Mumbai",
            "contact_number": "7777777777",
        },
    )
    user_id = user.json()["id"]

    client.post(
        f"/api/v1/users/{user_id}/assessments",
        json={
            "systolic_bp": 136,
            "diastolic_bp": 86,
            "heart_rate": 88,
            "blood_sugar": 118,
            "cholesterol": 190,
            "height_cm": 170,
            "weight_kg": 79,
            "symptoms": ["fatigue"],
            "medical_history": {"family_history": True},
            "lifestyle": {"smoking": False, "exercise": "low", "sleep_hours": 6.1, "stress_level": "medium"},
        },
    )
    before_prediction = client.get(f"/api/v1/users/{user_id}/predictions/latest").json()

    def fake_parse(*args, **kwargs):
        return (
            "Angiogram report. Blockage 80%. LDL 182 mg/dL. EF 32%.",
            {
                "report_type": "angiogram",
                "metrics": {
                    "blockage_percent": "80",
                    "ldl": "182",
                    "ejection_fraction": "32",
                },
                "detected_markers": ["angiogram", "blockage", "ldl", "ejection fraction"],
            },
            0.93,
        )

    monkeypatch.setattr(routes.report_parser, "parse", fake_parse)
    upload = client.post(
        f"/api/v1/users/{user_id}/reports/upload",
        files={"file": ("report.png", BytesIO(b"fake"), "image/png")},
        data={"report_type": "angiogram"},
    )
    assert upload.status_code == 200

    after_prediction = client.get(f"/api/v1/users/{user_id}/predictions/latest")
    assert after_prediction.status_code == 200
    after_payload = after_prediction.json()
    assert after_payload["risk_score"] >= before_prediction["risk_score"]
    assert any("Uploaded angiogram suggests significant coronary blockage." in line for line in after_payload["explanation"])

    alerts = client.get(f"/api/v1/users/{user_id}/alerts")
    assert alerts.status_code == 200
    assert any("blockage" in alert["title"].lower() or "ejection fraction" in alert["title"].lower() for alert in alerts.json())


def test_text_report_upload_extracts_metrics_and_alerts() -> None:
    user = client.post(
        "/api/v1/users",
        json={
            "name": "Text Report Test",
            "age": 55,
            "gender": "Female",
            "location": "Bengaluru",
            "contact_number": "7000000000",
        },
    )
    assert user.status_code == 200
    user_id = user.json()["id"]

    upload = client.post(
        f"/api/v1/users/{user_id}/reports/upload",
        files={
            "file": (
                "report.txt",
                BytesIO(
                    (
                        "Angiogram summary\n"
                        "LDL 182 mg/dL\n"
                        "HDL 36 mg/dL\n"
                        "Triglycerides 224 mg/dL\n"
                        "Glucose 132 mg/dL\n"
                        "Blood pressure 148/92\n"
                        "Blockage 78%\n"
                        "Ejection fraction 34%\n"
                    ).encode("utf-8")
                ),
                "text/plain",
            )
        },
        data={"report_type": "angiogram"},
    )
    assert upload.status_code == 200
    payload = upload.json()
    metrics = payload["extracted_findings"]["metrics"]
    assert metrics["ldl"] == "182"
    assert metrics["blockage_percent"] == "78"
    assert metrics["ejection_fraction"] == "34"
    assert payload["extraction_confidence"] >= 0.72

    alerts = client.get(f"/api/v1/users/{user_id}/alerts")
    assert alerts.status_code == 200
    alert_titles = [item["title"].lower() for item in alerts.json()]
    assert any("blockage" in title or "ejection fraction" in title for title in alert_titles)


def test_corrupt_pdf_upload_still_succeeds_with_extraction_note() -> None:
    user = client.post(
        "/api/v1/users",
        json={
            "name": "Broken PDF Test",
            "age": 61,
            "gender": "Male",
            "location": "Delhi",
            "contact_number": "7111111111",
        },
    )
    assert user.status_code == 200
    user_id = user.json()["id"]

    upload = client.post(
        f"/api/v1/users/{user_id}/reports/upload",
        files={"file": ("corrupt.pdf", BytesIO(b"not-a-real-pdf"), "application/pdf")},
        data={"report_type": "tmt_report"},
    )
    assert upload.status_code == 200
    payload = upload.json()
    assert payload["file_name"] == "corrupt.pdf"
    assert payload["extracted_text"] == ""
    assert "note" in payload["extracted_findings"]


def test_daily_logs_are_ordered_by_date_then_creation_time() -> None:
    user = client.post(
        "/api/v1/users",
        json={
            "name": "Tracking Order Test",
            "age": 52,
            "gender": "Male",
            "location": "Bengaluru",
            "contact_number": "6666666666",
        },
    )
    assert user.status_code == 200
    user_id = user.json()["id"]

    first_log = client.post(
        f"/api/v1/users/{user_id}/daily-logs",
        json={
            "log_date": "2026-03-18",
            "systolic_bp": 128,
            "diastolic_bp": 82,
            "blood_sugar": 110,
            "weight_kg": 72,
            "steps": 6200,
            "sleep_hours": 7.2,
        },
    )
    assert first_log.status_code == 200

    second_log = client.post(
        f"/api/v1/users/{user_id}/daily-logs",
        json={
            "log_date": "2026-03-18",
            "systolic_bp": 134,
            "diastolic_bp": 88,
            "blood_sugar": 118,
            "weight_kg": 71.5,
            "steps": 7100,
            "sleep_hours": 7.8,
        },
    )
    assert second_log.status_code == 200

    dashboard = client.get(f"/api/v1/users/{user_id}/dashboard")
    assert dashboard.status_code == 200
    recent_log = dashboard.json()["recent_daily_logs"][0]
    assert recent_log["systolic_bp"] == 134.0
    assert recent_log["diastolic_bp"] == 88.0
    assert recent_log["blood_sugar"] == 118.0


def test_care_search_falls_back_to_location_aware_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_post(*args, **kwargs):
        raise httpx.ConnectError("offline fallback test")

    monkeypatch.setattr(httpx.AsyncClient, "post", failing_post)

    response = client.post(
        "/api/v1/care-search",
        json={"latitude": 12.9716, "longitude": 77.5946, "radius_meters": 5000},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 3
    assert payload[0]["distance_km"] <= payload[1]["distance_km"]
    assert any("bengaluru" in item["address"].lower() for item in payload)
    assert any(
        "jayadeva" in item["name"].lower()
        or "apollo" in item["name"].lower()
        or "manipal" in item["name"].lower()
        for item in payload
    )


def test_chat_endpoint_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = client.post("/api/v1/bootstrap/demo")
    user_id = bootstrap.json()["user_id"]

    async def fake_reply(*args, **kwargs):
        return "Direct answer: keep monitoring. Why it matters: current values still need doctor review."

    monkeypatch.setattr(routes.chatbot_service, "reply", fake_reply)

    response = client.post(
        "/api/v1/chat",
        json={"user_id": user_id, "message": "What should I do about my recent chest pain?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Direct answer" in payload["reply"]
    assert "Consult" in payload["disclaimer"]


def test_chat_falls_back_when_model_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = client.post("/api/v1/bootstrap/demo")
    user_id = bootstrap.json()["user_id"]

    async def failing_post(*args, **kwargs):
        raise httpx.ConnectError("ollama unavailable")

    monkeypatch.setattr(httpx.AsyncClient, "post", failing_post)

    response = client.post(
        "/api/v1/chat",
        json={"user_id": user_id, "message": "Explain what I should do after this report upload."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Direct answer:" in payload["reply"]
    assert "Why it matters:" in payload["reply"]
    assert "Monitor next:" in payload["reply"]
    assert "Urgent care:" in payload["reply"]

    history = client.get(f"/api/v1/users/{user_id}/chat-history")
    assert history.status_code == 200
    messages = history.json()
    assert messages[-2]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
