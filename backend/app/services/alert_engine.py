from __future__ import annotations

import re

from app.models.entities import Assessment, DailyLog, MedicalReport


class AlertEngine:
    def from_assessment(self, assessment: Assessment) -> list[dict]:
        alerts: list[dict] = []
        symptoms = {item.lower() for item in assessment.symptoms}

        if assessment.systolic_bp and assessment.systolic_bp >= 180:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Dangerously high blood pressure",
                    "message": "Seek urgent medical evaluation for very high blood pressure values.",
                    "triggered_by": ["systolic_bp"],
                }
            )
        if assessment.blood_sugar and assessment.blood_sugar >= 250:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Dangerously high blood sugar",
                    "message": "Very high blood sugar needs prompt medical attention.",
                    "triggered_by": ["blood_sugar"],
                }
            )
        if "chest pain" in symptoms and ("shortness of breath" in symptoms or "sweating" in symptoms):
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Possible emergency heart symptoms",
                    "message": "Chest pain with sweating or shortness of breath should be treated as urgent.",
                    "triggered_by": ["symptoms"],
                }
            )
        return alerts

    def from_daily_log(self, log: DailyLog) -> list[dict]:
        alerts: list[dict] = []
        if log.systolic_bp and log.systolic_bp >= 180:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Dangerously high BP in daily log",
                    "message": "Your latest BP log is in a dangerous range. Seek medical care urgently.",
                    "triggered_by": ["daily_log_bp"],
                }
            )
        if log.blood_sugar and log.blood_sugar >= 250:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Dangerously high sugar in daily log",
                    "message": "Your latest sugar log is in a dangerous range. Seek medical care urgently.",
                    "triggered_by": ["daily_log_sugar"],
                }
            )
        return alerts

    def from_report(self, report: MedicalReport) -> list[dict]:
        alerts: list[dict] = []
        findings = report.extracted_findings or {}
        metrics = findings.get("metrics", {}) if isinstance(findings, dict) else {}

        ejection_fraction = self._to_float(metrics.get("ejection_fraction"))
        blockage_percent = self._to_float(metrics.get("blockage_percent"))
        glucose = self._to_float(metrics.get("glucose"))
        blood_pressure = str(metrics.get("blood_pressure", ""))
        tmt_result = str(metrics.get("tmt_result", "")).lower()

        if ejection_fraction is not None and ejection_fraction < 35:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Low ejection fraction on uploaded report",
                    "message": "The uploaded report suggests reduced pumping function. Please seek prompt doctor review.",
                    "triggered_by": ["report_ejection_fraction"],
                }
            )

        if blockage_percent is not None and blockage_percent >= 70:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Significant blockage reported",
                    "message": "The uploaded report suggests high-grade coronary blockage and needs urgent cardiology review.",
                    "triggered_by": ["report_blockage"],
                }
            )

        if glucose is not None and glucose >= 250:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Very high glucose in uploaded report",
                    "message": "The uploaded report shows a very high glucose value. Please seek prompt medical advice.",
                    "triggered_by": ["report_glucose"],
                }
            )

        bp_match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", blood_pressure)
        if bp_match and int(bp_match.group(1)) >= 180:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Dangerously high BP in uploaded report",
                    "message": "The uploaded report contains a blood pressure value in a dangerous range.",
                    "triggered_by": ["report_blood_pressure"],
                }
            )

        if tmt_result == "positive":
            alerts.append(
                {
                    "severity": "high",
                    "title": "Positive treadmill test finding",
                    "message": "The uploaded TMT result appears positive and should be reviewed by a cardiologist.",
                    "triggered_by": ["report_tmt"],
                }
            )

        return alerts

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        return float(match.group(1))
