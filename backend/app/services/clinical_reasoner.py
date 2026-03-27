from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.entities import Assessment, DailyLog, MedicalReport, RiskPrediction


@dataclass
class HeartTriageSummary:
    concern_level: str
    identified_symptoms: list[str]
    red_flags: list[str]
    follow_up_questions: list[str]
    care_actions: list[str]


class HeartClinicalReasoner:
    def __init__(self) -> None:
        self.symptom_aliases = {
            "chest pain": ["chest pain", "chest tightness", "pressure in chest", "pressure on chest"],
            "shortness of breath": ["shortness of breath", "breathless", "difficulty breathing", "can't breathe"],
            "dizziness": ["dizziness", "lightheaded", "vertigo", "giddy"],
            "fatigue": ["fatigue", "tiredness", "weakness", "exhausted"],
            "sweating": ["sweating", "cold sweat", "clammy"],
            "palpitations": ["palpitations", "racing heart", "irregular heartbeat", "fluttering"],
            "fainting": ["fainting", "passed out", "loss of consciousness", "blackout"],
            "jaw or arm pain": ["jaw pain", "left arm pain", "arm pain", "radiating pain"],
        }
        self.follow_up_by_symptom = {
            "chest pain": [
                "Is the pain pressure-like, sharp, or burning, and does it spread to the arm, jaw, or back?",
                "Did the pain start with exertion, stress, or at rest?",
            ],
            "shortness of breath": [
                "Can you speak full sentences comfortably, or do you become breathless while talking?",
                "Did the breathing difficulty start suddenly or build gradually?",
            ],
            "dizziness": [
                "Did you feel close to fainting, and was there chest discomfort or palpitations at the same time?",
            ],
            "fatigue": [
                "Is the fatigue new and unusual for you, especially with chest discomfort or breathlessness?",
            ],
        }

    def build_summary(
        self,
        message: str,
        prediction: RiskPrediction | None,
        assessment: Assessment | None,
        reports: list[MedicalReport],
        recent_logs: list[DailyLog],
    ) -> HeartTriageSummary:
        corpus_parts = [message or ""]
        if assessment:
            corpus_parts.extend(assessment.symptoms)
            corpus_parts.append(assessment.notes or "")
        for report in reports[:3]:
            corpus_parts.append(report.extracted_text or "")
        corpus = " ".join(corpus_parts).lower()

        symptoms = sorted(
            {
                symptom
                for symptom, aliases in self.symptom_aliases.items()
                if any(alias in corpus for alias in aliases)
            }
        )

        red_flags: list[str] = []
        if any(flag in corpus for flag in ["chest pain with sweating", "pressure in chest with sweating"]):
            red_flags.append("Chest pain with sweating can indicate an emergency.")
        if "chest pain" in symptoms and "shortness of breath" in symptoms:
            red_flags.append("Chest pain with shortness of breath can indicate an emergency.")
        if "fainting" in symptoms:
            red_flags.append("Fainting or loss of consciousness requires urgent medical attention.")
        if prediction and prediction.risk_level == "High":
            red_flags.append("Your latest prediction already places you in a high-risk category.")

        for report in reports[:3]:
            report_flags = self._report_red_flags(report)
            for flag in report_flags:
                if flag not in red_flags:
                    red_flags.append(flag)

        if recent_logs:
            latest = recent_logs[0]
            if latest.systolic_bp and latest.systolic_bp >= 180:
                red_flags.append("Recent daily logs show dangerously high systolic blood pressure.")
            if latest.blood_sugar and latest.blood_sugar >= 250:
                red_flags.append("Recent daily logs show dangerously high blood sugar.")

        if red_flags:
            concern_level = "emergency"
        elif prediction and prediction.risk_level == "High":
            concern_level = "high"
        elif len(symptoms) >= 2:
            concern_level = "moderate"
        else:
            concern_level = "low"

        follow_up_questions = [
            "When did the symptoms start, and are they improving or worsening?",
            "Do you have known diabetes, hypertension, previous heart disease, or current heart medicines?",
        ]
        for symptom in symptoms:
            for question in self.follow_up_by_symptom.get(symptom, []):
                if question not in follow_up_questions:
                    follow_up_questions.append(question)

        care_actions = self._care_actions(concern_level)
        return HeartTriageSummary(
            concern_level=concern_level,
            identified_symptoms=symptoms,
            red_flags=red_flags,
            follow_up_questions=follow_up_questions[:6],
            care_actions=care_actions,
        )

    @staticmethod
    def _report_red_flags(report: MedicalReport) -> list[str]:
        findings = report.extracted_findings or {}
        metrics = findings.get("metrics", {}) if isinstance(findings, dict) else {}
        red_flags: list[str] = []

        ejection_fraction = HeartClinicalReasoner._to_float(metrics.get("ejection_fraction"))
        blockage_percent = HeartClinicalReasoner._to_float(metrics.get("blockage_percent"))
        tmt_result = str(metrics.get("tmt_result", "")).lower()

        if ejection_fraction is not None and ejection_fraction < 35:
            red_flags.append("Low ejection fraction on report suggests reduced pumping function.")
        if blockage_percent is not None and blockage_percent >= 70:
            red_flags.append("Report suggests significant coronary blockage.")
        if tmt_result == "positive":
            red_flags.append("Positive TMT result requires cardiology follow-up.")
        return red_flags

    @staticmethod
    def _care_actions(concern_level: str) -> list[str]:
        if concern_level == "emergency":
            return [
                "Seek emergency medical care immediately or call local emergency services.",
                "Do not drive yourself if you are having severe symptoms or feel faint.",
            ]
        if concern_level == "high":
            return [
                "Arrange urgent clinical or cardiology review as soon as possible.",
                "Reduce exertion until a clinician reviews the current symptoms and numbers.",
            ]
        if concern_level == "moderate":
            return [
                "Monitor symptoms closely and arrange clinical review within 24 to 48 hours.",
                "Log BP, sugar, pulse, sleep, and worsening symptoms carefully.",
            ]
        return [
            "Continue monitoring symptoms and daily health values.",
            "Seek medical review if symptoms persist, worsen, or new warning signs appear.",
        ]

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        return float(match.group(1))
