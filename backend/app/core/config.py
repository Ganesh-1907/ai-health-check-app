from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HeartGuard AI"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/heartguard.db"
    storage_dir: str = "./storage"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    ollama_vision_model: str = "qwen2.5vl:latest"
    google_places_api_key: str = ""
    allowed_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]
    risk_model_path: str = "./ml/models/heart_risk_model.joblib"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve()

    @property
    def risk_model_artifact(self) -> Path:
        return Path(self.risk_model_path).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)
    settings.risk_model_artifact.parent.mkdir(parents=True, exist_ok=True)
    return settings
