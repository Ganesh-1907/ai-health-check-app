from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import pandas as pd
from kaggle.api.kaggle_api_extended import KaggleApi
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "ml" / "raw"
MODELS_DIR = BASE_DIR / "ml" / "models"
ARTIFACT_PATH = MODELS_DIR / "heart_risk_model.joblib"
METRICS_PATH = MODELS_DIR / "heart_risk_metrics.json"

DATASET_REF = "aasheesh200/framingham-heart-study-dataset"
CSV_PATH = RAW_DIR / "framingham-heart-study-dataset" / "framingham.csv"
FEATURES = [
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
TARGET = "target"


def ensure_dataset() -> Path:
    if CSV_PATH.exists():
        return CSV_PATH

    username = os.getenv("KAGGLE_USERNAME")
    key = os.getenv("KAGGLE_KEY")
    if not username or not key:
        raise RuntimeError("KAGGLE_USERNAME and KAGGLE_KEY are required to download the Framingham dataset.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key
    api = KaggleApi()
    api.authenticate()
    destination = RAW_DIR / "framingham-heart-study-dataset"
    destination.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(DATASET_REF, path=str(destination), unzip=True, quiet=False)
    return CSV_PATH


def load_frame() -> pd.DataFrame:
    csv_path = ensure_dataset()
    frame = pd.read_csv(csv_path)
    normalized = pd.DataFrame(
        {
            "age": frame["age"],
            "sex_male": frame["male"],
            "systolic_bp": frame["sysBP"],
            "diastolic_bp": frame["diaBP"],
            "cholesterol": frame["totChol"],
            "bmi": frame["BMI"],
            "heart_rate": frame["heartRate"],
            "high_blood_sugar": ((frame["glucose"].fillna(0) >= 126) | (frame["diabetes"].fillna(0) == 1)).astype(int),
            "current_smoker": frame["currentSmoker"],
            "diabetes": frame["diabetes"],
            "hypertension_history": ((frame["prevalentHyp"].fillna(0) == 1) | (frame["BPMeds"].fillna(0) == 1)).astype(int),
            "target": frame["TenYearCHD"],
        }
    )
    return normalized


def build_model() -> Pipeline:
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_transformer, FEATURES),
        ]
    )
    base_model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=2500, class_weight="balanced")),
        ]
    )
    return CalibratedClassifierCV(estimator=base_model, method="isotonic", cv=5)


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_frame().dropna(subset=[TARGET])
    x_train, x_test, y_train, y_test = train_test_split(
        frame[FEATURES],
        frame[TARGET],
        test_size=0.2,
        random_state=42,
        stratify=frame[TARGET],
    )

    model = build_model()
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_test)[:, 1]

    metrics = {
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_test, probabilities)), 4),
        "brier_score": round(float(brier_score_loss(y_test, probabilities)), 4),
        "training_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "positive_rate": round(float(frame[TARGET].mean()), 4),
    }

    metadata = {
        "model_name": "framingham_calibrated_logistic_regression",
        "dataset_ref": DATASET_REF,
        "features": FEATURES,
        "metrics": metrics,
    }

    joblib.dump({"model": model, "metadata": metadata}, ARTIFACT_PATH)
    METRICS_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Saved model artifact to {ARTIFACT_PATH}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
