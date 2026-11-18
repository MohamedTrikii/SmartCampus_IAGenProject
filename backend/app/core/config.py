from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "SmartCampus AI"
    database_url: str = "postgresql+psycopg://smartcampus:smartcampus@localhost:5432/smartcampus"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    visitor_session_days: int = 7
    chat_history_window: int = 12  # nombre de messages renvoyés au LLM (mémoire courte)

    # LLM : "openai" = toute API compatible OpenAI (Ollama, vLLM, Groq...), "fake" = tests
    llm_provider: str = "openai"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_temperature: float = 0.3
    llm_timeout_s: float = 120.0

    cors_origins: list[str] = ["http://localhost:3000"]

    # Synchronisation automatique du catalogue depuis les sites officiels
    sync_sites: str = "IIT,ISB,ISA,2I2S,NAU"
    sync_interval_hours: int = 24
    sync_use_llm: bool = False  # le LLM complète les champs vides, chaque valeur est vérifiée dans la page
    sync_request_delay_s: float = 1.0


settings = Settings()
