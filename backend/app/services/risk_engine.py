from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.entities import Assessment, MedicalReport
from app.services.trained_risk_model import get_trained_risk_model


@dataclass
class RiskResult:
    risk_score: float
    risk_level: str
    confidence: float
    explanation: list[str]
    red_flags: list[str]
    summary: str


@dataclass
class ReportSignals:
    overrides: dict[str, float]
    additional_score: float
    explanation: list[str]
    red_flags: list[str]


def calculate_bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if not height_cm or not weight_kg or height_cm <= 0:
        return None
    meters = height_cm / 100
    return round(weight_kg / (meters * meters), 2)


class RiskEngine:
    def __init__(self) -> None:
        self.trained_model = get_trained_risk_model()

    def score(self, assessment: Assessment, reports: list[MedicalReport] | None = None) -> RiskResult:
        report_signals = self._derive_report_signals(reports or [])
        heuristic_score, explanation, red_flags = self._heuristic_score(assessment, report_signals.overrides)
        model_probability, model_meta = self.trained_model.predict_probability(
            assessment,
            metric_overrides=report_signals.overrides,
        )

        if model_probability is not None:
            model_score = model_probability * 100
            base_score = (0.65 * model_score) + (0.35 * heuristic_score)
            explanation.insert(
                0,
                f"Calibrated model estimate contributed {round(model_score, 1)}% based on structured cardiovascular factors.",
            )
            confidence = 0.86 if self.trained_model.available else 0.72
            if model_meta.get("model_name"):
                explanation.append(f"Prediction source: {model_meta['model_name']}.")
        else:
            base_score = heuristic_score
            confidence = 0.7 if assessment.bmi and assessment.blood_sugar and assessment.cholesterol else 0.62
            explanation.insert(0, "Heuristic risk estimate used because no trained model artifact is loaded.")

        final_score = round(min(99.0, base_score + report_signals.additional_score), 1)
        for line in report_signals.explanation:
            if line not in explanation:
                explanation.append(line)
        for flag in report_signals.red_flags:
            if flag not in red_flags:
                red_flags.append(flag)
        if report_signals.explanation:
            confidence = min(0.92, confidence + 0.03)

        if final_score >= 70 or red_flags:
            risk_level = "High"
        elif final_score >= 40:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        summary = (
            f"Estimated heart disease risk is {risk_level} at {final_score}%. "
            "This is a support estimate and should be interpreted with clinician review."
        )
        return RiskResult(
            risk_score=final_score,
            risk_level=risk_level,
            confidence=confidence,
            explanation=explanation or ["Baseline risk estimated from available inputs."],
            red_flags=red_flags,
            summary=summary,
        )

    def _heuristic_score(
        self,
        assessment: Assessment,
        overrides: dict[str, float] | None = None,
    ) -> tuple[float, list[str], list[str]]:
        score = 10.0
        explanation: list[str] = []
        red_flags: list[str] = []
        effective = overrides or {}
        symptoms = {symptom.strip().lower() for symptom in assessment.symptoms}
        history = {str(key).lower(): value for key, value in assessment.medical_history.items()}
        lifestyle = {str(key).lower(): value for key, value in assessment.lifestyle.items()}
        systolic_bp = effective.get("systolic_bp", assessment.systolic_bp)
        diastolic_bp = effective.get("diastolic_bp", assessment.diastolic_bp)
        blood_sugar = effective.get("blood_sugar", assessment.blood_sugar)
        cholesterol = effective.get("cholesterol", assessment.cholesterol)
        heart_rate = effective.get("heart_rate", assessment.heart_rate)

        if assessment.user.age >= 60:
            score += 12
            explanation.append("Age is increasing baseline cardiovascular risk.")
        elif assessment.user.age >= 45:
            score += 7
            explanation.append("Age contributes moderate baseline cardiovascular risk.")

        if systolic_bp and systolic_bp >= 180:
            score += 18
            red_flags.append("Very high systolic blood pressure.")
        elif systolic_bp and systolic_bp >= 140:
            score += 12
            explanation.append("Elevated systolic blood pressure raises risk.")
        elif systolic_bp and systolic_bp >= 130:
            score += 7
            explanation.append("Borderline elevated blood pressure contributes risk.")

        if diastolic_bp and diastolic_bp >= 120:
            score += 15
            red_flags.append("Very high diastolic blood pressure.")
        elif diastolic_bp and diastolic_bp >= 90:
            score += 10
            explanation.append("Elevated diastolic blood pressure raises risk.")

        if blood_sugar and blood_sugar >= 200:
            score += 16
            red_flags.append("Very high blood sugar.")
        elif blood_sugar and blood_sugar >= 126:
            score += 11
            explanation.append("High blood sugar pattern raises risk.")

        if cholesterol and cholesterol >= 240:
            score += 11
            explanation.append("High cholesterol increases cardiovascular risk.")
        elif cholesterol and cholesterol >= 200:
            score += 6
            explanation.append("Borderline high cholesterol contributes risk.")

        if assessment.bmi and assessment.bmi >= 30:
            score += 8
            explanation.append("BMI indicates obesity-related heart risk.")
        elif assessment.bmi and assessment.bmi >= 25:
            score += 4
            explanation.append("BMI indicates overweight status.")

        if heart_rate and heart_rate >= 120:
            score += 7
            explanation.append("Elevated heart rate may indicate increased cardiac stress.")

        if "chest pain" in symptoms:
            score += 14
            explanation.append("Chest pain is a major symptom requiring attention.")
        if "shortness of breath" in symptoms:
            score += 12
            explanation.append("Shortness of breath is a significant cardiovascular symptom.")
        if "dizziness" in symptoms:
            score += 6
            explanation.append("Dizziness increases concern in the current context.")
        if "fatigue" in symptoms:
            score += 4
            explanation.append("Fatigue can contribute to the overall risk picture.")
        if "sweating" in symptoms and "chest pain" in symptoms:
            score += 12
            red_flags.append("Chest pain with sweating can indicate emergency risk.")

        if history.get("previous_heart_problems"):
            score += 14
            explanation.append("Previous heart disease history strongly increases risk.")
        if history.get("surgeries"):
            score += 5
            explanation.append("Prior surgeries/interventions increase medical complexity.")
        if history.get("family_history"):
            score += 8
            explanation.append("Family history increases inherited cardiovascular risk.")

        if lifestyle.get("smoking"):
            score += 12
            explanation.append("Smoking materially increases cardiovascular risk.")
        if lifestyle.get("alcohol"):
            score += 4
            explanation.append("Alcohol use should be assessed in the overall heart-risk profile.")
        if str(lifestyle.get("exercise", "")).lower() in {"none", "low", "sedentary"}:
            score += 8
            explanation.append("Low exercise level is contributing to the risk score.")
        sleep_hours = self._to_float(lifestyle.get("sleep_hours"))
        if sleep_hours is not None and sleep_hours < 6:
            score += 4
            explanation.append("Insufficient sleep can worsen cardiovascular health.")
        if str(lifestyle.get("stress_level", "")).lower() in {"high", "severe"}:
            score += 6
            explanation.append("High stress level is increasing the risk estimate.")

        return score, explanation, red_flags

    def _derive_report_signals(self, reports: list[MedicalReport]) -> ReportSignals:
        overrides: dict[str, float] = {}
        explanation: list[str] = []
        red_flags: list[str] = []
        additional_score = 0.0

        for report in reports[:5]:
            findings = report.extracted_findings or {}
            metrics = findings.get("metrics", {}) if isinstance(findings, dict) else {}
            if not isinstance(metrics, dict):
                continue

            self._update_override(overrides, "cholesterol", self._to_float(metrics.get("cholesterol")))
            self._update_override(overrides, "blood_sugar", self._to_float(metrics.get("glucose")))
            self._update_override(overrides, "heart_rate", self._to_float(metrics.get("heart_rate")))

            blood_pressure = str(metrics.get("blood_pressure", ""))
            bp_match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", blood_pressure)
            if bp_match:
                self._update_override(overrides, "systolic_bp", float(bp_match.group(1)))
                self._update_override(overrides, "diastolic_bp", float(bp_match.group(2)))

            ldl = self._to_float(metrics.get("ldl"))
            hdl = self._to_float(metrics.get("hdl"))
            triglycerides = self._to_float(metrics.get("triglycerides"))
            ejection_fraction = self._to_float(metrics.get("ejection_fraction"))
            blockage_percent = self._to_float(metrics.get("blockage_percent"))
            tmt_result = str(metrics.get("tmt_result", "")).lower()

            if ldl is not None and ldl >= 160:
                additional_score += 8
                explanation.append("Uploaded report shows markedly elevated LDL.")
            elif ldl is not None and ldl >= 130:
                additional_score += 4
                explanation.append("Uploaded report shows elevated LDL.")

            if hdl is not None and hdl < 40:
                additional_score += 4
                explanation.append("Uploaded report shows low HDL.")

            if triglycerides is not None and triglycerides >= 200:
                additional_score += 4
                explanation.append("Uploaded report shows elevated triglycerides.")

            if ejection_fraction is not None and ejection_fraction < 40:
                additional_score += 12
                explanation.append("Uploaded Echo report suggests reduced ejection fraction.")
                if ejection_fraction < 30:
                    red_flags.append("Very low ejection fraction reported.")

            if blockage_percent is not None and blockage_percent >= 70:
                additional_score += 18
                explanation.append("Uploaded angiogram suggests significant coronary blockage.")
                red_flags.append("Significant coronary blockage reported.")
            elif blockage_percent is not None and blockage_percent >= 50:
                additional_score += 10
                explanation.append("Uploaded angiogram suggests moderate coronary blockage.")

            if tmt_result == "positive":
                additional_score += 8
                explanation.append("Uploaded TMT result appears positive for ischemic concern.")

        return ReportSignals(
            overrides=overrides,
            additional_score=additional_score,
            explanation=list(dict.fromkeys(explanation)),
            red_flags=list(dict.fromkeys(red_flags)),
        )

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        return float(match.group(1))

    @staticmethod
    def _update_override(overrides: dict[str, float], key: str, value: float | None) -> None:
        if value is None:
            return
        overrides[key] = max(overrides.get(key, value), value)
