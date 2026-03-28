from __future__ import annotations

import beanie
import motor.motor_asyncio

from app.core.config import get_settings


async def init_db() -> None:
    settings = get_settings()
    client: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
        settings.mongodb_url
    )
    # Extract the database name from the URL (last path segment)
    db_name = settings.mongodb_url.rsplit("/", 1)[-1] or "heart-disease"
    database = client[db_name]

    # Import document classes here to avoid circular imports
    from app.models.entities import (
        Alert,
        Assessment,
        ChatMessage,
        DailyLog,
        MedicalReport,
        RecommendationPlan,
        RiskPrediction,
        User,
    )

    await beanie.init_beanie(
        database=database,
        document_models=[
            User,
            Assessment,
            RiskPrediction,
            DailyLog,
            MedicalReport,
            RecommendationPlan,
            Alert,
            ChatMessage,
        ],
    )
