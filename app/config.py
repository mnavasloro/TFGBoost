from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("TFGBOOST_DATA_DIR", "data"))
    upload_dir: Path = Path(os.getenv("TFGBOOST_UPLOAD_DIR", "uploads"))
    max_upload_mb: int = int(os.getenv("TFGBOOST_MAX_UPLOAD_MB", "15"))
    ollama_enabled: bool = os.getenv("TFGBOOST_OLLAMA_ENABLED", "true").lower() == "true"
    ollama_url: str = os.getenv("TFGBOOST_OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("TFGBOOST_OLLAMA_MODEL", "qwen3:8b")
    # Full-document inference on CPU can take several minutes per checklist item.
    ollama_timeout_seconds: int = int(os.getenv("TFGBOOST_OLLAMA_TIMEOUT_SECONDS", "600"))
    # Context tested to complete reliably with Qwen3 8B running on this CPU.
    ollama_context_tokens: int = int(os.getenv("TFGBOOST_OLLAMA_CONTEXT_TOKENS", "4096"))
    session_days: int = int(os.getenv("TFGBOOST_SESSION_DAYS", "7"))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "tfgboost.sqlite3"


settings = Settings()
