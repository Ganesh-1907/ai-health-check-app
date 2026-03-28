from __future__ import annotations

from functools import lru_cache
from typing import Any

import joblib
import pandas as pd

from app.core.config import get_settings
from app.models.entities import Assessment, User


MODEL_FEATURES = [
    "age",
    "sex_male",
    "systolic_bp",
    "diastolic_bp",
    "cholesterol",
    "bmi",
    "heart_rate",
    "high_blood_sugar",
    "current_smoker",
    "diabetes",
    "hypertension_history",
]


class TrainedRiskModel:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.available = False
        self.metadata: dict[str, Any] = {}
        self.pipeline = None
        self._load()

    def _load(self) -> None:
        artifact_path = self.settings.risk_model_artifact
        if not artifact_path.exists():
            return
        artifact = joblib.load(artifact_path)
        self.pipeline = artifact["model"]
        self.metadata = artifact.get("metadata", {})
        self.available = True

    def predict_probability(
        self,
        assessment: Assessment,
        user: User,
        metric_overrides: dict[str, float] | None = None,
    ) -> tuple[float | None, dict[str, Any]]:
        if not self.available or self.pipeline is None:
            return None, {}

        overrides = metric_overrides or {}
        systolic_bp = overrides.get("systolic_bp", assessment.systolic_bp)
        diastolic_bp = overrides.get("diastolic_bp", assessment.diastolic_bp)
        cholesterol = overrides.get("cholesterol", assessment.cholesterol)
        heart_rate = overrides.get("heart_rate", assessment.heart_rate)
        blood_sugar = overrides.get("blood_sugar", assessment.blood_sugar)

        feature_row = {
            "age": user.age,
            "sex_male": 1.0 if str(user.gender).strip().lower() in {"male", "m"} else 0.0,
            "systolic_bp": systolic_bp,
            "diastolic_bp": diastolic_bp,
            "cholesterol": cholesterol,
            "bmi": assessment.bmi,
            "heart_rate": heart_rate,
            "high_blood_sugar": 1.0 if blood_sugar and blood_sugar >= 126 else 0.0,
            "current_smoker": 1.0 if assessment.lifestyle.get("smoking") else 0.0,
            "diabetes": 1.0 if assessment.medical_history.get("diabetes") or (blood_sugar and blood_sugar >= 126) else 0.0,
            "hypertension_history": 1.0
            if assessment.medical_history.get("hypertension")
            or (systolic_bp and systolic_bp >= 140)
            or (diastolic_bp and diastolic_bp >= 90)
            else 0.0,
        }
        frame = pd.DataFrame([feature_row], columns=MODEL_FEATURES)
        probability = float(self.pipeline.predict_proba(frame)[0][1])
        return probability, {"feature_row": feature_row, "model_name": self.metadata.get("model_name", "unknown")}


@lru_cache
def get_trained_risk_model() -> TrainedRiskModel:
    return TrainedRiskModel()
