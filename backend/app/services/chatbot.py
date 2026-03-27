from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models.entities import Assessment, ChatMessage, DailyLog, MedicalReport, RecommendationPlan, RiskPrediction, User
from app.services.clinical_reasoner import HeartClinicalReasoner, HeartTriageSummary
from app.services.heart_knowledge import get_heart_knowledge_base


class ChatbotService:
    model_timeout_seconds = 3.0

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
        model_candidates = list(dict.fromkeys([self.settings.ollama_model, "llama3.2:latest"]))
        for model_name in model_candidates:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        self.model_timeout_seconds,
                        connect=1.5,
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
                                "temperature": 0.2,
                                "num_predict": 220,
                            },
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a heart-health virtual assistant for a health monitoring app. "
                                        "Ground your answer in the provided user data. "
                                        "Never present a final diagnosis. "
                                        "If chest pain with sweating, fainting, severe breathlessness, or dangerous uploaded report findings appear, advise urgent emergency care. "
                                        "Keep answers structured, practical, safe, and specific to the user's current profile. "
                                        "Do not repeat the input dump back to the user."
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
            f"Question: {message}\n"
            f"User: {user.age} years old, {user.gender}, location {user.location}.\n"
            f"Risk: {prediction.risk_level if prediction else 'unknown'} at {prediction.risk_score if prediction else 'n/a'}%.\n"
            f"Symptoms: {assessment.symptoms if assessment else []}.\n"
            f"Key red flags: {triage.red_flags}.\n"
            f"Latest log: BP {latest_log.systolic_bp if latest_log else 'n/a'}/{latest_log.diastolic_bp if latest_log else 'n/a'}, sugar {latest_log.blood_sugar if latest_log else 'n/a'}, sleep {latest_log.sleep_hours if latest_log else 'n/a'}.\n"
            f"Latest report metrics: {report_metrics or {}}.\n"
            f"Useful evidence: {evidence_block}.\n"
            f"Care actions already recommended: {triage.care_actions}.\n"
            f"Conversation context: {history_block or '- none'}.\n"
            "Reply in exactly 4 labeled lines and do not repeat the input:\n"
            "Direct answer:\n"
            "Why it matters:\n"
            "Monitor next:\n"
            "Urgent care:"
        )

    @staticmethod
    def _fallback_reply(
        prediction: RiskPrediction | None,
        recommendation: RecommendationPlan | None,
        assessment: Assessment | None,
        triage: HeartTriageSummary,
    ) -> str:
        if not prediction:
            return "\n".join(
                [
                    "Direct answer: I can help, but I need more of your profile or assessment data first.",
                    "Why it matters: without recent readings, symptoms, or reports I may miss important heart-risk context.",
                    "Monitor next: complete the assessment, upload any recent report, and log BP, sugar, symptoms, and sleep.",
                    "Urgent care: if you have chest pain with sweating, fainting, or severe breathlessness, seek emergency care now.",
                ]
            )

        symptom_text = ", ".join(assessment.symptoms) if assessment else "current symptoms not available"
        advice = recommendation.daily_tips[0] if recommendation and recommendation.daily_tips else "Monitor your values closely."
        urgent_line = ", ".join(triage.red_flags) if triage.red_flags else "No immediate emergency signal is obvious from the latest saved data."
        why_line = (
            f"Your latest saved risk snapshot is {prediction.risk_level} at {prediction.risk_score}%, "
            f"and the current symptom context is {symptom_text}."
        )
        return "\n".join(
            [
                f"Direct answer: {advice}",
                f"Why it matters: {why_line}",
                "Monitor next: keep logging BP, sugar, symptoms, activity, sleep, and any new report findings.",
                f"Urgent care: {urgent_line} Consult a doctor for diagnosis and treatment.",
            ]
        )

    @staticmethod
    def _reply_is_usable(reply: str) -> bool:
        if not reply or len(reply.strip()) < 40:
            return False
        markers = ["User profile:", "Current user question:", "Latest risk:", "Question:"]
        if any(marker in reply for marker in markers):
            return False
        return True
