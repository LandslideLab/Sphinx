from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPHINX_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./sphinx.db"
    api_port: int = 8001
    mcp_port: int = 8100
    cors_origins: list[str] = ["*"]
    scheduler_interval_seconds: float = 1.0
    default_policy_seed: bool = True
    seed_demo_data: bool = False
    log_level: str = "info"


settings = Settings()
