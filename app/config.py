from dataclasses import dataclass, field
from pathlib import Path
import os


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "si", "sí"}


def _list(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("TFGBOOST_DATA_DIR", "data"))
    upload_dir: Path = Path(os.getenv("TFGBOOST_UPLOAD_DIR", "uploads"))
    max_upload_mb: int = int(os.getenv("TFGBOOST_MAX_UPLOAD_MB", "15"))
    session_days: int = int(os.getenv("TFGBOOST_SESSION_DAYS", "7"))
    checklist_path: Path = Path(os.getenv("TFGBOOST_CHECKLIST", "app/checklist/tfg_checklist.json"))

    # Modelo por defecto: "<proveedor>:<modelo>", p. ej. "ollama:qwen3:8b",
    # "anthropic:claude-opus-5-5" o "none" (solo reglas, sin IA).
    default_model: str = os.getenv("TFGBOOST_DEFAULT_MODEL", "ollama:qwen3:8b")

    # --- Ollama (local) ---
    ollama_enabled: bool = _bool("TFGBOOST_OLLAMA_ENABLED", "true")
    ollama_url: str = os.getenv("TFGBOOST_OLLAMA_URL", "http://localhost:11434")
    # Lista de modelos ofrecidos. Cada entrada admite "@<contexto>" para fijar
    # num_ctx por modelo: "qwen3:8b@4096,llama3.1:8b@8192". Vacío = todos los instalados.
    ollama_models: tuple[str, ...] = field(default_factory=lambda: _list("TFGBOOST_OLLAMA_MODELS", "qwen3:8b@4096"))
    ollama_context_tokens: int = int(os.getenv("TFGBOOST_OLLAMA_CONTEXT_TOKENS", "4096"))
    ollama_timeout_seconds: int = int(os.getenv("TFGBOOST_OLLAMA_TIMEOUT_SECONDS", "600"))
    ollama_max_output_tokens: int = int(os.getenv("TFGBOOST_OLLAMA_MAX_OUTPUT_TOKENS", "1200"))
    # En CPU, dos análisis simultáneos se ralentizan mutuamente: se encolan.
    ollama_concurrency: int = int(os.getenv("TFGBOOST_OLLAMA_CONCURRENCY", "1"))

    # --- Claude (Anthropic API, por tokens) ---
    # La clave se lee de ANTHROPIC_API_KEY (o de un perfil de `ant auth login`).
    anthropic_enabled: bool = _bool("TFGBOOST_ANTHROPIC_ENABLED", "false")
    anthropic_models: tuple[str, ...] = field(default_factory=lambda: _list("TFGBOOST_ANTHROPIC_MODELS", "claude-opus-5-5,claude-sonnet-5-5,claude-haiku-5-5"))
    anthropic_effort: str = os.getenv("TFGBOOST_ANTHROPIC_EFFORT", "medium")
    anthropic_max_output_tokens: int = int(os.getenv("TFGBOOST_ANTHROPIC_MAX_OUTPUT_TOKENS", "16000"))
    anthropic_timeout_seconds: int = int(os.getenv("TFGBOOST_ANTHROPIC_TIMEOUT_SECONDS", "600"))
    # Reintento automático en otro modelo si el principal declina la petición.
    anthropic_fallbacks: bool = _bool("TFGBOOST_ANTHROPIC_FALLBACKS", "true")
    anthropic_concurrency: int = int(os.getenv("TFGBOOST_ANTHROPIC_CONCURRENCY", "4"))
    # --- OpenRouter (API compatible con OpenAI, pago por tokens) ---
    openrouter_enabled: bool = _bool("TFGBOOST_OPENROUTER_ENABLED", "false")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_url: str = os.getenv("TFGBOOST_OPENROUTER_URL", "https://openrouter.ai/api/v1")
    # Identificadores de OpenRouter; "@<tokens>" fija el contexto (si no, se lee del catálogo).
    openrouter_models: tuple[str, ...] = field(default_factory=lambda: _list("TFGBOOST_OPENROUTER_MODELS", "qwen/qwen3.5-35b-a3b,qwen/qwen3.5-122b-a10b,openai/gpt-oss-120b,google/gemma-3-27b-it"))
    # Incluye los tokens de razonamiento de los modelos que «piensan» (Qwen 3.5, gpt-oss…).
    openrouter_max_output_tokens: int = int(os.getenv("TFGBOOST_OPENROUTER_MAX_OUTPUT_TOKENS", "16000"))
    # Razonamiento: "auto" (desactivado; effort=low si el modelo lo exige), "off", "low", "medium" o "high".
    # Solo se envía a modelos que admiten el parámetro. Más esfuerzo = más tokens y coste.
    openrouter_reasoning: str = os.getenv("TFGBOOST_OPENROUTER_REASONING", "auto").strip().lower()
    openrouter_timeout_seconds: int = int(os.getenv("TFGBOOST_OPENROUTER_TIMEOUT_SECONDS", "300"))
    openrouter_concurrency: int = int(os.getenv("TFGBOOST_OPENROUTER_CONCURRENCY", "4"))
    # Exigir proveedores que admitan el esquema JSON (más fiable, algo menos de disponibilidad).
    openrouter_require_parameters: bool = _bool("TFGBOOST_OPENROUTER_REQUIRE_PARAMETERS", "true")
    openrouter_referer: str = os.getenv("TFGBOOST_OPENROUTER_REFERER", "")
    # Elección de proveedor: "cheap" (el más barato), "fast" (el más rápido sin superar el
    # precio publicado) o "default" (reparto de OpenRouter). En pruebas con Qwen 3.5 y peticiones
    # en paralelo, "cheap" tardó lo mismo que "fast" (~20 s) y costó la mitad.
    openrouter_routing: str = os.getenv("TFGBOOST_OPENROUTER_ROUTING", "cheap").strip().lower()

    # Peticiones simultáneas por análisis con modelos remotos (Claude, OpenRouter). La
    # primera va sola para dejar el borrador en caché; el resto, en paralelo. Mismo coste.
    llm_parallel_requests: int = int(os.getenv("TFGBOOST_LLM_PARALLEL_REQUESTS", "4"))

    # Límite de análisis por estudiante y día con proveedores de pago (0 = sin límite).
    remote_daily_limit: int = int(os.getenv("TFGBOOST_REMOTE_DAILY_LIMIT", "5"))

    # --- Triaje previo al tutor (encuesta, P17) ---
    submit_threshold: int = int(os.getenv("TFGBOOST_SUBMIT_THRESHOLD", "50"))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "tfgboost.sqlite3"


settings = Settings()
