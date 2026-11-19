from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read values from environment variables, and from a local .env file if present.
    # extra="ignore" means unknown variables in .env do not crash the app.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default on purpose: if DATABASE_URL is missing the app refuses to start.
    # SecretStr hides the value (it contains the password) when printed or logged.
    database_url: SecretStr

    # Signs login tokens. Anyone who knows it can forge a token for any user, so it
    # must be long, random and secret. No default on purpose.
    secret_key: SecretStr
    access_token_expire_minutes: int = 30

    app_env: str = "development"


@lru_cache
def get_settings() -> Settings:
    # Built once, then reused: reading and validating the environment on every
    # request would be wasteful.
    return Settings()
