from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models.entities import Assessment, ChatMessage, DailyLog, MedicalReport, RecommendationPlan, RiskPrediction, User
from app.services.clinical_reasoner import HeartClinicalReasoner, HeartTriageSummary
from app.services.heart_knowledge import get_heart_knowledge_base


class ChatbotService:
    model_timeout_seconds = 20.0

    def __init__(self) -> None:
        self.settings = get_settings()
        self.reasoner = HeartClinicalReasoner()
        self.knowledge_base = get_heart_knowledge_base()

    async def reply(
        self,
        user: User,
        message: str,
        prediction: RiskPrediction | None,
        assessment: Assessment | None,
        recommendation: RecommendationPlan | None,
        reports: list[MedicalReport] | None = None,
        recent_logs: list[DailyLog] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> str:
        triage = self.reasoner.build_summary(
            message=message,
            prediction=prediction,
            assessment=assessment,
            reports=reports or [],
            recent_logs=recent_logs or [],
        )
        prompt = self._build_prompt(
            user=user,
            message=message,
            prediction=prediction,
            assessment=assessment,
            recommendation=recommendation,
            reports=reports or [],
            recent_logs=recent_logs or [],
            history=history or [],
            triage=triage,
        )
        # Use first configured model, then a fallback local model name
        model_candidates = list(dict.fromkeys([self.settings.ollama_model, "llama3.2:latest", "llama3.1:8b"]))
        for model_name in model_candidates:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        self.model_timeout_seconds,
                        connect=2.0,
                        read=self.model_timeout_seconds,
                        write=self.model_timeout_seconds,
                        pool=self.model_timeout_seconds,
                    )
                ) as client:
                    response = await client.post(
                        f"{self.settings.ollama_base_url}/api/chat",
                        json={
                            "model": model_name,
                            "stream": False,
                            "options": {
                                "temperature": 0.4, # Slightly higher for more variety
                                "num_predict": 300,
                            },
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are an expert heart-health virtual assistant for the HeartGuard AI app. "
                                        "Ground your answer in the provided user health snapshots. "
                                        "Provide a conversational, practical, and safe response. "
                                        "Do not repeat the provided data back to the user; instead, interpret what it means for their heart health. "
                                        "If danger signals appear (chest pain, severe breathlessness, fainting), emphasize urgent care. "
                                        "Keep your answer under 250 tokens and focus on the user's specific health profile."
                                    ),
                                },
                                {"role": "user", "content": prompt},
                            ],
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    reply = payload.get("message", {}).get("content", "").strip()
                    if self._reply_is_usable(reply):
                        return reply
            except Exception:
                continue

        return self._fallback_reply(prediction, recommendation, assessment, triage)

    def _build_prompt(
        self,
        user: User,
        message: str,
        prediction: RiskPrediction | None,
        assessment: Assessment | None,
        recommendation: RecommendationPlan | None,
        reports: list[MedicalReport],
        recent_logs: list[DailyLog],
        history: list[ChatMessage],
        triage: HeartTriageSummary,
    ) -> str:
        retrieval_query = " ".join(
            [
                message,
                prediction.summary if prediction else "",
                " ".join(assessment.symptoms) if assessment else "",
                " ".join(str(report.extracted_findings) for report in reports[:3]),
            ]
        )
        evidence = self.knowledge_base.retrieve(retrieval_query, top_k=1)
        evidence_block = "\n".join([f"- {item['title']}: {item['text']}" for item in evidence]) or "- none"
        latest_report = reports[0] if reports else None
        report_metrics = (latest_report.extracted_findings or {}).get("metrics", {}) if latest_report else {}
        latest_log = recent_logs[0] if recent_logs else None
        history_block = "\n".join([f"{item.role}: {item.content}" for item in history[-2:]])
        return (
            f"User Question: {message}\n"
            f"Current Stats: {user.age} year old {user.gender}. Risk: {prediction.risk_level if prediction else 'unk'} at {prediction.risk_score if prediction else 'n/a'}%.\n"
            f"Symptoms: {assessment.symptoms if assessment else []}. Red flags: {triage.red_flags}.\n"
            f"Last reading: BP {latest_log.systolic_bp if latest_log else 'n/a'}/{latest_log.diastolic_bp if latest_log else 'n/a'}, Sugar {latest_log.blood_sugar if latest_log else 'n/a'}.\n"
            f"Report findings: {report_metrics or {}}.\n"
            f"Clinical Context: {evidence_block}.\n"
            f"Recent Context: {history_block or 'Initial message'}.\n"
            "Respond conversationally to the user's question. Structure your response with:\n"
            "1. A direct, clear answer.\n"
            "2. 'Why it matters' (context from their risk/symptoms).\n"
            "3. 'Next steps' (practical advice).\n"
            "4. 'Safety Note' (if urgent factors exist)."
        )

    @staticmethod
    def _fallback_reply(
        prediction: RiskPrediction | None,
        recommendation: RecommendationPlan | None,
        assessment: Assessment | None,
        triage: HeartTriageSummary,
    ) -> str:
        if not prediction:
            return (
                "Direct answer: I'm here to support your heart health, but I need your assessment data to provide specific insights.\n\n"
                "Why it matters: Personal health data like symptoms and BP readings help me give safe, tailored guidance.\n\n"
                "Next steps: Please complete your first AI assessment or log your vitals in the 'Tracking' tab.\n\n"
                "Safety Note: If you experience chest pain or fainting, seek emergency care immediately."
            )

        symptom_text = ", ".join(assessment.symptoms) if (assessment and assessment.symptoms) else "no recent symptoms"
        advice = recommendation.daily_tips[0] if (recommendation and recommendation.daily_tips) else "Monitor your heart health trends closely."
        urgent_line = ", ".join(triage.red_flags) if triage.red_flags else "No immediate emergency signals detected from your recent data."
        why_line = (
            f"Your latest risk level is {prediction.risk_level} ({prediction.risk_score}%) "
            f"with {symptom_text} recorded."
        )
        return (
            f"Direct answer: {advice}\n\n"
            f"Why it matters: {why_line}\n\n"
            "Next steps: Continue logging your vitals daily and follow your personalized diet tips.\n\n"
            f"Safety Note: {urgent_line} Always consult your doctor for medical decisions."
        )

    @staticmethod
    def _reply_is_usable(reply: str) -> bool:
        if not reply or len(reply.strip()) < 40:
            return False
        markers = ["User profile:", "Current user question:", "Latest risk:", "Question:"]
        if any(marker in reply for marker in markers):
            return False
        return True
