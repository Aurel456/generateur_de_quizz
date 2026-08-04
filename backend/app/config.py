"""Configuration du backend (CORS, identité). Les paramètres LLM/DB restent lus par
les modules métier existants via le `.env` de la racine du repo."""
import os

from dotenv import load_dotenv

load_dotenv()


def _csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() == "true"


class Settings:
    APP_NAME = "Quiz Generator API"
    APP_VERSION = "0.1.0-dsfr"
    DEBUG = _bool("DEBUG", True)

    # Découpage des documents (mode token par blocs).
    CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "10000"))
    CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "200"))

    # Mode one-shot : budget de contexte du modèle. Au-delà, les documents sont
    # découpés automatiquement (1 bloc par document, puis par tranches).
    ONESHOT_MAX_TOTAL_TOKENS = int(os.getenv("ONESHOT_MAX_TOTAL_TOKENS", "190000"))
    ONESHOT_SLICE_TOKENS = int(os.getenv("ONESHOT_SLICE_TOKENS", "50000"))

    CORS_ORIGINS = _csv(
        "CORS_ORIGINS",
        ["http://localhost:8081", "http://127.0.0.1:8081", "http://localhost:3052"],
    )
    CORS_CREDENTIALS = _bool("CORS_CREDENTIALS", False)
    # PUT est utilisé par l'enregistrement d'un atelier (`PUT /workshops/{code}`).
    CORS_METHODS = _csv("CORS_METHODS", ["GET", "POST", "PUT", "OPTIONS"])
    CORS_HEADERS = _csv("CORS_HEADERS", ["*"])


settings = Settings()
