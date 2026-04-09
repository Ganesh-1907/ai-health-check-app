from __future__ import annotations

import json
import logging
from typing import Any

from app.models.entities import Assessment, RiskPrediction, User
from app.services.gemini import GeminiService

logger = logging.getLogger(__name__)

class AIConsultant:
    def __init__(self) -> None:
        self.gemini = GeminiService()

    async def get_clinical_deep_dive(
        self,
        user: User,
        assessment: Assessment,
        prediction: RiskPrediction
    ) -> dict[str, Any]:
        """
        Generate a deep-dive analysis of the user's cardiovascular health state using Gemini.
        Returns potential diseases, causes, remedies, and precautions.
        """
        prompt = self._build_prompt(user, assessment, prediction)
        
        try:
            logger.info(f"Requesting AI Clinical Deep-Dive for user {user.id} (Risk: {prediction.risk_level})")
            response_text = await self.gemini.generate_content(prompt)
            fallback = self._heuristic_fallback(assessment, prediction)

            if not response_text or response_text.startswith("Gemini service"):
                logger.warning("Gemini returned an unavailable/service message. Using heuristic fallback.")
                return fallback

            insights = self._parse_response(response_text)
            merged_insights = self._merge_with_fallback(insights, fallback)
            return merged_insights
        except Exception as e:
            logger.error(f"Failed to get clinical deep dive due to exception: {e}")
            return self._heuristic_fallback(assessment, prediction)

    @staticmethod
    def _normalize_items(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return []

        cleaned: list[str] = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            cleaned.append(text)
        return list(dict.fromkeys(cleaned))

    def _merge_with_fallback(self, insights: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "current_condition_signals",
            "future_risk_diseases",
            "potential_diseases",
            "causes",
            "remedies",
            "precautions",
            "medicine_guidance",
        ]
        merged = {
            key: self._normalize_items(insights.get(key))
            for key in keys
        }

        if not merged["potential_diseases"]:
            merged["potential_diseases"] = list(
                dict.fromkeys([
                    *merged["current_condition_signals"],
                    *merged["future_risk_diseases"],
                ])
            )

        for key in keys:
            if not merged[key]:
                merged[key] = self._normalize_items(fallback.get(key))

        if not merged["potential_diseases"]:
            merged["potential_diseases"] = list(
                dict.fromkeys([
                    *merged["current_condition_signals"],
                    *merged["future_risk_diseases"],
                ])
            )

        return merged

    def _heuristic_fallback(self, assessment: Assessment, prediction: RiskPrediction) -> dict[str, Any]:
        """Provide a medical-grounded fallback if AI fails."""
        risk = prediction.risk_level
        
        if risk == "High":
            return {
                "current_condition_signals": ["Possible severe cardiovascular strain", "Possible uncontrolled hypertension pattern"],
                "future_risk_diseases": ["Possible acute coronary syndrome risk", "Possible stroke or heart failure risk"],
                "potential_diseases": ["Severe Cardiovascular Strain", "Hypertensive Emergency risk", "Critical Cardiac Imbalance"],
                "causes": ["Significantly elevated systolic/diastolic BP", "High physiological stress indicators", "Unstable health markers & symptoms"],
                "remedies": ["Immediate emergency medical evaluation", "Advanced cardiac diagnostic screening", "Urgent clinical intervention protocols"],
                "precautions": ["Absolute physical rest immediately", "Zero sodium and stimulant intake", "Continuous vital sign monitoring"],
                "medicine_guidance": [
                    "Discuss urgent doctor-supervised blood pressure and cardiac medication review immediately.",
                    "Do not self-start or self-stop heart medicines without clinician advice.",
                ],
            }
        elif risk == "Medium":
            return {
                "current_condition_signals": ["Possible early hypertension markers", "Possible metabolic imbalance pattern"],
                "future_risk_diseases": ["Possible coronary artery disease risk", "Possible diabetes-related heart complications"],
                "potential_diseases": ["Early-stage Hypertension indicators", "Metabolic Syndrome markers", "Progressive Cardiomyopathy risk"],
                "causes": ["Persistent elevation in BP or sugar", "Combined lifestyle and dietary stressors", "Inadequate sleep or high stress levels"],
                "remedies": ["Full clinical health baseline review", "Sodium-restricted DASH diet plan", "Structured moderate exercise (post-review)"],
                "precautions": ["Reduced sodium and processed sugar", "Consistent sleep and stress management", "Weekly tracking of all vitals"],
                "medicine_guidance": [
                    "Ask a doctor whether BP, sugar, or cholesterol medicines need review based on repeat readings.",
                    "Bring your last reports and this assessment result to the consultation.",
                ],
            }
        else:
            return {
                "current_condition_signals": ["No major current warning pattern detected from this assessment"],
                "future_risk_diseases": ["Low near-term cardiovascular progression risk if habits remain healthy"],
                "potential_diseases": ["Normal Cardiovascular profile", "Low preventative concern"],
                "causes": ["Healthy nutritional balance", "Stable blood pressure and sugar", "Active and low-stress lifestyle"],
                "remedies": ["Regular preventative screenings", "Continued balanced physical activity", "Maintaining current health habits"],
                "precautions": ["Routine annual heart checkups", "Proper hydration levels", "Sustained healthy lifestyle choices"],
                "medicine_guidance": [
                    "No new medicine should be started from this AI result alone.",
                    "Continue only the medicines already prescribed by your doctor.",
                ],
            }

    def _build_prompt(self, user: User, assessment: Assessment, prediction: RiskPrediction) -> str:
        symptoms = ", ".join(assessment.symptoms) or "None reported"
        history = json.dumps(assessment.medical_history)
        lifestyle = json.dumps(assessment.lifestyle)
        
        prompt = f"""
        You are a highly experienced cardiologist and clinical researcher. 
        Analyze the following cardiovascular health data and provide a detailed clinical deep-dive.

        USER PROFILE:
        - Name: {user.name}
        - Age: {user.age}
        - Gender: {user.gender}

        VITALS & METRICS:
        - Blood Pressure: {assessment.systolic_bp}/{assessment.diastolic_bp} mmHg
        - Heart Rate: {assessment.heart_rate} bpm
        - Blood Sugar: {assessment.blood_sugar} mg/dL
        - Cholesterol: {assessment.cholesterol} mg/dL
        - BMI: {assessment.bmi}

        SYMPTOMS: {symptoms}
        MEDICAL HISTORY: {history}
        LIFESTYLE: {lifestyle}

        AI RISK ASSESSMENT:
        - Risk Level: {prediction.risk_level}
        - Risk Score: {prediction.risk_score}%
        - Summary: {prediction.summary}

        TASK:
        Based on these parameters, identify possible current condition signals, future disease risks, and practical clinical guidance.
        Provide the output in STRICT JSON format with the following keys:
        - "current_condition_signals": A list of 2-3 possible CURRENT or already-emerging cardiovascular/metabolic conditions suggested by the data.
        - "future_risk_diseases": A list of 2-3 diseases or complications the user may be at risk of developing if the current pattern continues.
        - "potential_diseases": A combined list of 2-4 concise condition names covering the most relevant current and future risks.
        - "causes": A list of 3-4 likely causes or contributing factors based on the data.
        - "remedies": A list of 3-4 actionable remedies or clinical interventions.
        - "precautions": A list of 3-4 essential lifestyle or safety precautions.
        - "medicine_guidance": A list of 2-4 safe, doctor-discussion-oriented medication guidance points. Do not provide dosing and do not prescribe; only mention what medication categories a clinician may review.

        RESPONSE STYLE: Professional, clinical, yet accessible. Avoid definite diagnosis; use terms like "Possible", "Indications of", or "Risk for".
        ONLY RETURN THE JSON OBJECT. NO MARKDOWN, NO EXPLANATION.
        """
        return prompt

    def _parse_response(self, text: str) -> dict[str, Any]:
        try:
            # Basic cleanup in case Gemini returns markdown blocks
            clean_text = text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[-1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[-1].split("```")[0].strip()
            
            data = json.loads(clean_text)
            current_condition_signals = self._normalize_items(data.get("current_condition_signals", []))
            future_risk_diseases = self._normalize_items(data.get("future_risk_diseases", []))
            potential_diseases = self._normalize_items(data.get("potential_diseases", []))
            if not potential_diseases:
                potential_diseases = list(dict.fromkeys([*current_condition_signals, *future_risk_diseases]))
            return {
                "current_condition_signals": current_condition_signals,
                "future_risk_diseases": future_risk_diseases,
                "potential_diseases": potential_diseases,
                "causes": self._normalize_items(data.get("causes", [])),
                "remedies": self._normalize_items(data.get("remedies", [])),
                "precautions": self._normalize_items(data.get("precautions", [])),
                "medicine_guidance": self._normalize_items(data.get("medicine_guidance", [])),
            }
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}. Raw text: {text}")
            return {
                "current_condition_signals": ["Possible cardiovascular or metabolic imbalance pattern detected"],
                "future_risk_diseases": ["Future cardiovascular disease risk needs clinical review"],
                "potential_diseases": ["Complex cardiovascular state detected"],
                "causes": ["Multiple intersecting factors"],
                "remedies": ["Clinical evaluation required"],
                "precautions": ["Standard heart-healthy protocols recommended"],
                "medicine_guidance": ["Discuss medicine needs with a licensed clinician using your reports and repeated vitals."],
            }
