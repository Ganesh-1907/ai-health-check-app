from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HeartGuard AI"
    api_prefix: str = "/api/v1"
    mongodb_url: str = "mongodb://localhost:27017/heart-disease"
    storage_dir: str = "./storage"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    ollama_vision_model: str = "qwen2.5vl:latest"
    google_places_api_key: str = ""
    # Stored as a comma-separated string so pydantic-settings doesn't try JSON-parse it
    allowed_origins: str = "http://localhost:8081,http://localhost:19006"
    risk_model_path: str = "./ml/models/heart_risk_model.joblib"
    jwt_secret: str = "changeme_use_a_long_random_string_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    gemini_api_keys: str = ""
    gemini_model: str = "gemini-1.5-flash"
    chat_store_messages: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve()

    @property
    def gemini_keys(self) -> list[str]:
        return [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]

    @property
    def risk_model_artifact(self) -> Path:
        return Path(self.risk_model_path).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    settings.risk_model_artifact.parent.mkdir(parents=True, exist_ok=True)
    return settings
