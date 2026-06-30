import secrets
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    PROJECT_NAME: str = "backlog keeper bot"
    DEBUG: bool = False

    DISCORD_TOKEN: str = secrets.token_urlsafe(32)
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    GUILD_ID: int = -1


def get_config() -> Config:
    return Config()
