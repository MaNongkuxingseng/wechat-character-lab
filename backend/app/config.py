from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行时配置（runtime settings），读取环境变量和可选的 .env 文件。"""

    app_name: str = "WeChat Character Lab API"
    database_url: str = "sqlite:///../data/character_lab.db"
    inbox_path: str = "data/inbox"
    log_level: str = "INFO"
    semantic_llm_enabled: bool = False
    semantic_llm_allow_message_content: bool = False
    semantic_llm_endpoint: str | None = None
    semantic_llm_model: str | None = None
    semantic_llm_api_key: SecretStr | None = None
    semantic_llm_timeout_seconds: float = 30.0
    semantic_llm_max_input_chars: int = 100_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """返回当前进程共享的配置快照（settings snapshot）。"""
    return Settings()
