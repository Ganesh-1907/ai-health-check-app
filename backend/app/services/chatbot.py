import logging
from typing import Any

from app.core.config import get_settings
from app.models.entities import Assessment, ChatMessage, DailyLog, MedicalReport, RecommendationPlan, RiskPrediction, User
from app.services.clinical_reasoner import HeartClinicalReasoner, HeartTriageSummary
from app.services.heart_knowledge import get_heart_knowledge_base
from app.services.gemini import GeminiService

logger = logging.getLogger(__name__)


class ChatbotService:
    model_timeout_seconds = 20.0

    def __init__(self) -> None:
        self.settings = get_settings()
        self.reasoner = HeartClinicalReasoner()
        self.knowledge_base = get_heart_knowledge_base()
        self.gemini = GeminiService()

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
        
        # Build message history for Gemini
        gemini_history = []
        if history:
            for m in history:
                gemini_history.append({"role": m.role, "content": m.content})

        try:
            reply = await self.gemini.chat(gemini_history, prompt)
            if self._reply_is_usable(reply):
                return reply
        except Exception as e:
            logger.error(f"Gemini chat failed: {e}")

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
        system_rules = (
            "You are HeartGuard, a cautious cardiovascular-health assistant. "
            "Stay within heart and circulation topics, provide evidence-based education only, "
            "and avoid firm diagnoses or medication dosing. "
            "Respond in plain language with 2–3 concise sentences (max ~120 words) and no headings, lists, or numbering. "
            "If the question is unrelated to heart health, politely steer back to cardiovascular guidance. "
            "Always remind users to seek emergency care for severe chest pain, shortness of breath, fainting, or stroke signs."
        )
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
            f"System rules: {system_rules}\n"
            f"User Question: {message}\n"
            f"Current Stats: {user.age} year old {user.gender}. Risk: {prediction.risk_level if prediction else 'unk'} at {prediction.risk_score if prediction else 'n/a'}%.\n"
            f"Symptoms: {assessment.symptoms if assessment else []}. Red flags: {triage.red_flags}.\n"
            f"Last reading: BP {latest_log.systolic_bp if latest_log else 'n/a'}/{latest_log.diastolic_bp if latest_log else 'n/a'}, Sugar {latest_log.blood_sugar if latest_log else 'n/a'}.\n"
            f"Report findings: {report_metrics or {}}.\n"
            f"Clinical Context: {evidence_block}.\n"
            f"Recent Context: {history_block or 'Initial message'}.\n"
            "Respond conversationally to the user's question in 2–3 sentences, plain language, no headings, no lists, no numbering. "
            "Keep it under 120 words and avoid asking for extra personal identifiers. "
            "Always include a short safety reminder if any red flags or emergency signs are present."
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
