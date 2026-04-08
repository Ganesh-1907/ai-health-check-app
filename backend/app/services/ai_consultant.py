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
            insights = self._parse_response(response_text)
            
            # If AI returned empty lists but risk is elevated, use heuristics to fill the gaps
            is_empty = not insights.get("potential_diseases") or len(insights.get("potential_diseases", [])) == 0
            if is_empty and prediction.risk_level != "Low":
                logger.warning(f"AI returned empty insights for elevated risk ({prediction.risk_level}), falling back to heuristics.")
                fallback = self._heuristic_fallback(assessment, prediction)
                for key in ["potential_diseases", "causes", "remedies", "precautions"]:
                    # Fill if missing or empty
                    if not insights.get(key) or len(insights.get(key, [])) == 0:
                        insights[key] = fallback[key]
            
            # Final safety check: if still empty (e.g. Low risk AI fail), use basic defaults
            if not insights.get("potential_diseases") or len(insights.get("potential_diseases", [])) == 0:
                 insights = self._heuristic_fallback(assessment, prediction)
                 
            return insights
        except Exception as e:
            logger.error(f"Failed to get clinical deep dive due to exception: {e}")
            return self._heuristic_fallback(assessment, prediction)

    def _heuristic_fallback(self, assessment: Assessment, prediction: RiskPrediction) -> dict[str, Any]:
        """Provide a medical-grounded fallback if AI fails."""
        risk = prediction.risk_level
        
        if risk == "High":
            return {
                "potential_diseases": ["Severe Cardiovascular Strain", "Hypertensive Emergency risk", "Critical Cardiac Imbalance"],
                "causes": ["Significantly elevated systolic/diastolic BP", "High physiological stress indicators", "Unstable health markers & symptoms"],
                "remedies": ["Immediate emergency medical evaluation", "Advanced cardiac diagnostic screening", "Urgent clinical intervention protocols"],
                "precautions": ["Absolute physical rest immediately", "Zero sodium and stimulant intake", "Continuous vital sign monitoring"]
            }
        elif risk == "Medium":
            return {
                "potential_diseases": ["Early-stage Hypertension indicators", "Metabolic Syndrome markers", "Progressive Cardiomyopathy risk"],
                "causes": ["Persistent elevation in BP or sugar", "Combined lifestyle and dietary stressors", "Inadequate sleep or high stress levels"],
                "remedies": ["Full clinical health baseline review", "Sodium-restricted DASH diet plan", "Structured moderate exercise (post-review)"],
                "precautions": ["Reduced sodium and processed sugar", "Consistent sleep and stress management", "Weekly tracking of all vitals"]
            }
        else:
            return {
                "potential_diseases": ["Normal Cardiovascular profile", "Low preventative concern"],
                "causes": ["Healthy nutritional balance", "Stable blood pressure and sugar", "Active and low-stress lifestyle"],
                "remedies": ["Regular preventative screenings", "Continued balanced physical activity", "Maintaining current health habits"],
                "precautions": ["Routine annual heart checkups", "Proper hydration levels", "Sustained healthy lifestyle choices"]
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
        Based on these parameters, identify potential cardiovascular diseases or syndromes the user might be at risk for or exhibiting signs of.
        Provide the output in STRICT JSON format with the following keys:
        - "potential_diseases": A list of 2-3 specific medical conditions or syndromes (e.g., "Stage 1 Hypertension", "Stable Angina", "Metabolic Syndrome").
        - "causes": A list of 3-4 likely causes or contributing factors based on the data.
        - "remedies": A list of 3-4 actionable remedies or clinical interventions.
        - "precautions": A list of 3-4 essential lifestyle or safety precautions.

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
            return {
                "potential_diseases": data.get("potential_diseases", []),
                "causes": data.get("causes", []),
                "remedies": data.get("remedies", []),
                "precautions": data.get("precautions", [])
            }
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}. Raw text: {text}")
            return {
                "potential_diseases": ["Complex cardiovascular state detected"],
                "causes": ["Multiple intersecting factors"],
                "remedies": ["Clinical evaluation required"],
                "precautions": ["Standard heart-healthy protocols recommended"]
            }
