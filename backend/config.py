from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Travel Content Studio"
    version: str = "0.1.0"
    api_port: int = 8420

    data_dir: Path = Path.home() / ".travel-content-studio"
    projects_dir: Path | None = None
    db_path: Path | None = None

    log_level: str = "INFO"
    ollama_host: str = "http://localhost:11434"
    comfyui_host: str = "http://localhost:8188"
    gpu_timeout: float = 300
    max_concurrent_jobs: int = 3

    model_config = {"env_prefix": "TCS_", "env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        if self.projects_dir is None:
            self.projects_dir = self.data_dir / "projects"
        if self.db_path is None:
            self.db_path = self.data_dir / "data.db"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
